from datetime import datetime, timezone
import re

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app, beijing_time
from app.models import Comment, CrawlTask, TaskVideo, Video


def test_home_and_health() -> None:
    with TestClient(app) as client:
        home = client.get("/")
        assert home.status_code == 200
        assert "CONTENT RESEARCH WORKSPACE" not in home.text
        assert "游客实时模式" not in home.text
        assert 'name="max_replies"' in home.text
        assert "单评论回复" in home.text
        assert 'name="keyword" value=' not in home.text
        assert 'placeholder="请输入搜索关键词"' in home.text

        health = client.get("/health")
        assert health.status_code == 200
        assert health.json() == {"status": "ok"}


def test_beijing_time_converts_utc_values() -> None:
    value = datetime(2026, 9, 22, 4, 30, tzinfo=timezone.utc)
    assert beijing_time(value) == "2026-09-22 12:30"


def test_beijing_time_treats_sqlite_naive_values_as_utc() -> None:
    value = datetime(2026, 9, 22, 4, 30)
    assert beijing_time(value, "%Y-%m-%d %H:%M") == "2026-09-22 12:30"


def test_delete_task_removes_orphans_and_renumbers_tasks() -> None:
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(test_engine)

    with Session(test_engine) as session:
        first = CrawlTask(keyword="first", status="failed")
        second = CrawlTask(keyword="second", status="success")
        shared = Video(platform_video_id="shared", url="https://example.com/shared")
        orphan = Video(platform_video_id="orphan", url="https://example.com/orphan")
        session.add_all([first, second, shared, orphan])
        session.flush()
        session.add_all(
            [
                TaskVideo(task_id=first.id, video_id=shared.id, rank=1),
                TaskVideo(task_id=first.id, video_id=orphan.id, rank=2),
                TaskVideo(task_id=second.id, video_id=shared.id, rank=1),
                Comment(
                    platform_comment_id="shared-comment",
                    video_id=shared.id,
                    content="keep",
                ),
                Comment(
                    platform_comment_id="orphan-comment",
                    video_id=orphan.id,
                    content="delete",
                ),
            ]
        )
        session.commit()
        first_id = first.id
        second_id = second.id

    def override_db():
        with Session(test_engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/tasks/{first_id}/delete?page=1", follow_redirects=False
            )
            assert response.status_code == 303
            assert response.headers["location"] == "/?page=1"

            home = client.get("/")
            assert 'class="task-id">#1</span><strong>second</strong>' in home.text
            assert f'/tasks/{second_id}/delete' in home.text

        with Session(test_engine) as session:
            assert session.get(CrawlTask, first_id) is None
            assert session.get(CrawlTask, second_id) is not None
            assert session.scalar(select(func.count()).select_from(Video)) == 1
            assert session.scalar(select(func.count()).select_from(Comment)) == 1
            assert session.scalar(select(Comment.content)) == "keep"
    finally:
        app.dependency_overrides.pop(get_db, None)
        test_engine.dispose()


def test_running_task_cannot_be_deleted() -> None:
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(test_engine)
    with Session(test_engine) as session:
        task = CrawlTask(keyword="active", status="running")
        session.add(task)
        session.commit()
        task_id = task.id

    def override_db():
        with Session(test_engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            response = client.post(f"/tasks/{task_id}/delete")
            assert response.status_code == 409
        with Session(test_engine) as session:
            assert session.get(CrawlTask, task_id) is not None
    finally:
        app.dependency_overrides.pop(get_db, None)
        test_engine.dispose()


def test_video_breadcrumb_preserves_source_task_context() -> None:
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(test_engine)
    with Session(test_engine) as session:
        first = CrawlTask(keyword="first task", status="success")
        second = CrawlTask(keyword="current task", status="success")
        video = Video(
            platform_video_id="shared-video",
            url="https://example.com/video",
            description="Shared video",
        )
        session.add_all([first, second, video])
        session.flush()
        session.add_all(
            [
                TaskVideo(task_id=first.id, video_id=video.id, rank=1),
                TaskVideo(task_id=second.id, video_id=video.id, rank=1),
                *[
                    Comment(
                        platform_comment_id=f"comment-{index}",
                        video_id=video.id,
                        content=f"Comment {index}",
                    )
                    for index in range(11)
                ],
            ]
        )
        session.commit()
        second_id = second.id
        video_id = video.id

    def override_db():
        with Session(test_engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            task_page = client.get(f"/tasks/{second_id}")
            expected_video_url = f"/videos/{video_id}?task_id={second_id}"
            assert expected_video_url in task_page.text

            detail = client.get(expected_video_url)
            assert f'href="/tasks/{second_id}">current task</a>' in detail.text
            assert (
                f'href="/videos/{video_id}?task_id={second_id}&amp;page=2"'
                in detail.text
            )

            direct_detail = client.get(f"/videos/{video_id}")
            breadcrumb = re.search(
                r'<nav class="breadcrumbs"[\s\S]*?</nav>', direct_detail.text
            )
            assert breadcrumb is not None
            assert 'href="/tasks/' not in breadcrumb.group(0)

            invalid_context = client.get(f"/videos/{video_id}?task_id=999")
            assert invalid_context.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)
        test_engine.dispose()
