import asyncio
import csv
import io
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.crawler import CollectedComment, CollectedVideo, PlaywrightTikTokCollector
from app.database import SessionLocal
from app.models import Comment, CrawlTask, TaskVideo, Video


_crawl_lock = asyncio.Lock()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def run_crawl_task(task_id: int) -> None:
    async with _crawl_lock:
        await _run_crawl_task(task_id)


async def _run_crawl_task(task_id: int) -> None:
    session = SessionLocal()
    try:
        task = session.get(CrawlTask, task_id)
        if task is None:
            return
        task.status = "running"
        task.started_at = utc_now()
        task.error_message = None
        session.commit()

        collector = PlaywrightTikTokCollector()

        async def save_video(collected, rank: int) -> None:
            _save_collected_video(session, task, collected, rank)
            session.commit()

        def get_cached_video(video_id: str) -> CollectedVideo | None:
            video = session.execute(
                select(Video)
                .options(joinedload(Video.comments))
                .where(Video.platform_video_id == video_id)
            ).unique().scalar_one_or_none()
            if video is None:
                return None
            top_level = sorted(
                (
                    comment
                    for comment in video.comments
                    if comment.parent_comment_id is None
                ),
                key=lambda comment: comment.id,
            )
            if task.max_comments > 0 and len(top_level) < task.max_comments:
                return None
            replies_by_parent: dict[str, list[Comment]] = {}
            for comment in sorted(video.comments, key=lambda item: item.id):
                if comment.parent_comment_id:
                    replies_by_parent.setdefault(comment.parent_comment_id, []).append(
                        comment
                    )
            collected_comments: list[CollectedComment] = []
            selected_top_level = (
                top_level[: task.max_comments] if task.max_comments > 0 else []
            )
            for comment in selected_top_level:
                collected_comments.append(_to_collected_comment(comment))
                collected_comments.extend(
                    _to_collected_comment(reply)
                    for reply in replies_by_parent.get(
                        comment.platform_comment_id, []
                    )[: task.max_replies]
                )
            return CollectedVideo(
                video_id=video.platform_video_id,
                url=video.url,
                description=video.description,
                author_name=video.author_name,
                author_url=video.author_url,
                cover_url=video.cover_url,
                published_at=video.published_at,
                like_count=video.like_count,
                comment_count=video.comment_count,
                share_count=video.share_count,
                comments=collected_comments,
            )

        collected_videos = await collector.collect(
            task.keyword,
            task.max_videos,
            task.max_comments,
            task.max_replies,
            on_video=save_video,
            get_cached_video=get_cached_video,
        )

        if not collected_videos:
            raise RuntimeError("采集完成，但没有得到可保存的视频。")

        task.status = "success"
        task.finished_at = utc_now()
        session.commit()
    except Exception as exc:
        session.rollback()
        task = session.get(CrawlTask, task_id)
        if task is not None:
            saved_videos = session.scalar(
                select(TaskVideo).where(TaskVideo.task_id == task_id).limit(1)
            )
            task.status = "partial" if saved_videos is not None else "failed"
            task.finished_at = utc_now()
            task.error_message = str(exc)[:2_000]
            session.commit()
    finally:
        session.close()


def _save_collected_video(session, task, collected, rank: int) -> None:
    video = session.scalar(
        select(Video).where(Video.platform_video_id == collected.video_id)
    )
    if video is None:
        video = Video(platform_video_id=collected.video_id, url=collected.url)
        session.add(video)

    video.url = collected.url
    video.description = collected.description
    video.author_name = collected.author_name
    video.author_url = collected.author_url
    video.cover_url = collected.cover_url
    video.published_at = collected.published_at
    video.like_count = collected.like_count
    video.comment_count = collected.comment_count
    video.share_count = collected.share_count
    video.updated_at = utc_now()
    session.flush()

    link = session.get(TaskVideo, (task.id, video.id))
    if link is None:
        session.add(TaskVideo(task_id=task.id, video_id=video.id, rank=rank))
    else:
        link.rank = rank

    for collected_comment in collected.comments:
        comment = session.scalar(
            select(Comment).where(
                Comment.platform_comment_id == collected_comment.comment_id
            )
        )
        if comment is None:
            comment = Comment(
                platform_comment_id=collected_comment.comment_id,
                video_id=video.id,
                content=collected_comment.content,
            )
            session.add(comment)
        comment.video_id = video.id
        comment.parent_comment_id = collected_comment.parent_comment_id
        comment.author_name = collected_comment.author_name
        comment.content = collected_comment.content
        comment.like_count = collected_comment.like_count
        comment.published_at = collected_comment.published_at


def _to_collected_comment(comment: Comment) -> CollectedComment:
    return CollectedComment(
        comment_id=comment.platform_comment_id,
        author_name=comment.author_name,
        content=comment.content,
        like_count=comment.like_count,
        published_at=comment.published_at,
        parent_comment_id=comment.parent_comment_id,
    )


def build_task_csv(task_id: int) -> str:
    session = SessionLocal()
    try:
        task = session.scalar(
            select(CrawlTask)
            .options(joinedload(CrawlTask.video_links).joinedload(TaskVideo.video))
            .where(CrawlTask.id == task_id)
        )
        if task is None:
            raise LookupError("任务不存在")

        output = io.StringIO()
        output.write("\ufeff")
        writer = csv.writer(output)
        writer.writerow(
            [
                "keyword",
                "rank",
                "video_id",
                "video_url",
                "author",
                "description",
                "like_count",
                "comment_count",
                "collected_comments",
            ]
        )
        for link in sorted(task.video_links, key=lambda item: item.rank):
            video = link.video
            writer.writerow(
                [
                    task.keyword,
                    link.rank,
                    video.platform_video_id,
                    video.url,
                    video.author_name,
                    video.description,
                    video.like_count,
                    video.comment_count,
                    len(video.comments),
                ]
            )
        return output.getvalue()
    finally:
        session.close()
