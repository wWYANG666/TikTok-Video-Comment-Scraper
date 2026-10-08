from contextlib import asynccontextmanager
from datetime import datetime, timezone
from math import ceil
from zoneinfo import ZoneInfo

from fastapi import BackgroundTasks, Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.config import STATIC_DIR, TEMPLATES_DIR
from app.database import get_db, init_db
from app.models import Comment, CrawlTask, TaskVideo, Video
from app.services import build_task_csv, run_crawl_task


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="TikTok 内容采集器", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)
BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def compact_number(value: int | None) -> str:
    number = int(value or 0)
    if number >= 100_000_000:
        return f"{number / 100_000_000:.1f}亿".replace(".0亿", "亿")
    if number >= 10_000:
        return f"{number / 10_000:.1f}万".replace(".0万", "万")
    if number >= 1_000:
        return f"{number / 1_000:.1f}K".replace(".0K", "K")
    return str(number)


def beijing_time(value: datetime | None, format_string: str = "%Y-%m-%d %H:%M") -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(BEIJING_TZ).strftime(format_string)


templates.env.filters["compact_number"] = compact_number
templates.env.filters["beijing_time"] = beijing_time


PAGE_SIZE = 10


def pagination(total: int, requested_page: int) -> dict[str, int]:
    pages = max(1, ceil(total / PAGE_SIZE))
    page = min(max(requested_page, 1), pages)
    return {
        "page": page,
        "pages": pages,
        "total": total,
        "offset": (page - 1) * PAGE_SIZE,
        "start": max(1, page - 2),
        "end": min(pages, page + 2),
    }


@app.get("/")
def task_list(
    request: Request,
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
):
    total_tasks = db.scalar(select(func.count()).select_from(CrawlTask)) or 0
    pager = pagination(total_tasks, page)
    tasks = db.scalars(
        select(CrawlTask)
        .order_by(CrawlTask.id.desc())
        .offset(pager["offset"])
        .limit(PAGE_SIZE)
    ).all()
    ordered_task_ids = db.scalars(
        select(CrawlTask.id).order_by(CrawlTask.id)
    ).all()
    task_numbers = {
        task_id: position for position, task_id in enumerate(ordered_task_ids, start=1)
    }
    task_ids = [task.id for task in tasks]
    video_counts = (
        dict(
            db.execute(
                select(TaskVideo.task_id, func.count(TaskVideo.video_id))
                .where(TaskVideo.task_id.in_(task_ids))
                .group_by(TaskVideo.task_id)
            ).all()
        )
        if task_ids
        else {}
    )
    summary = {
        "total": total_tasks,
        "active": db.scalar(
            select(func.count()).select_from(CrawlTask).where(
                CrawlTask.status.in_(["pending", "running"])
            )
        ) or 0,
        "success": db.scalar(
            select(func.count()).select_from(CrawlTask).where(
                CrawlTask.status == "success"
            )
        ) or 0,
        "videos": db.scalar(select(func.count(Video.id))) or 0,
    }
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "tasks": tasks,
            "task_numbers": task_numbers,
            "video_counts": video_counts,
            "summary": summary,
            "pagination": pager,
            "base_url": "/",
        },
    )


@app.post("/tasks")
def create_task(
    background_tasks: BackgroundTasks,
    keyword: str = Form(...),
    max_videos: int = Form(10),
    max_comments: int = Form(50),
    max_replies: int = Form(20),
    db: Session = Depends(get_db),
):
    keyword = keyword.strip()
    if not keyword:
        raise HTTPException(status_code=400, detail="关键词不能为空")
    task = CrawlTask(
        keyword=keyword,
        max_videos=max(1, min(max_videos, 50)),
        max_comments=max(0, min(max_comments, 500)),
        max_replies=max(0, min(max_replies, 100)),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    background_tasks.add_task(run_crawl_task, task.id)
    return RedirectResponse(url=f"/tasks/{task.id}", status_code=303)


@app.post("/tasks/{task_id}/delete")
def delete_task(
    task_id: int,
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
):
    task = db.get(CrawlTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status in {"pending", "running"}:
        raise HTTPException(status_code=409, detail="执行中的任务不能删除")

    video_ids = db.scalars(
        select(TaskVideo.video_id).where(TaskVideo.task_id == task_id)
    ).all()
    db.delete(task)
    db.flush()

    for video_id in video_ids:
        still_referenced = db.scalar(
            select(func.count()).select_from(TaskVideo).where(
                TaskVideo.video_id == video_id
            )
        ) or 0
        if still_referenced:
            continue
        video = db.get(Video, video_id)
        if video is not None:
            db.delete(video)

    db.commit()
    remaining_tasks = db.scalar(select(func.count()).select_from(CrawlTask)) or 0
    destination_page = min(page, max(1, ceil(remaining_tasks / PAGE_SIZE)))
    return RedirectResponse(url=f"/?page={destination_page}", status_code=303)


@app.get("/tasks/{task_id}")
def task_detail(
    task_id: int,
    request: Request,
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
):
    task = db.get(CrawlTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    task_number = db.scalar(
        select(func.count()).select_from(CrawlTask).where(CrawlTask.id <= task.id)
    ) or 1

    total_links = db.scalar(
        select(func.count()).select_from(TaskVideo).where(TaskVideo.task_id == task_id)
    ) or 0
    pager = pagination(total_links, page)
    links = db.scalars(
        select(TaskVideo)
        .options(joinedload(TaskVideo.video))
        .where(TaskVideo.task_id == task_id)
        .order_by(TaskVideo.rank)
        .offset(pager["offset"])
        .limit(PAGE_SIZE)
    ).all()
    comment_counts = {
        video_id: count
        for video_id, count in db.execute(
            select(Comment.video_id, func.count(Comment.id))
            .where(Comment.video_id.in_([link.video_id for link in links] or [-1]))
            .group_by(Comment.video_id)
        ).all()
    }
    return templates.TemplateResponse(
        request=request,
        name="task_detail.html",
        context={
            "task": task,
            "task_number": task_number,
            "links": links,
            "total_links": total_links,
            "comment_counts": comment_counts,
            "pagination": pager,
            "base_url": f"/tasks/{task_id}",
        },
    )


@app.post("/tasks/{task_id}/rerun")
def rerun_task(
    task_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    task = db.get(CrawlTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status == "running":
        return RedirectResponse(url=f"/tasks/{task.id}", status_code=303)
    task.status = "pending"
    task.error_message = None
    db.commit()
    background_tasks.add_task(run_crawl_task, task.id)
    return RedirectResponse(url=f"/tasks/{task.id}", status_code=303)


@app.get("/videos/{video_id}")
def video_detail(
    video_id: int,
    request: Request,
    page: int = Query(1, ge=1),
    task_id: int | None = Query(None, ge=1),
    db: Session = Depends(get_db),
):
    video = db.execute(
        select(Video)
        .options(
            joinedload(Video.task_links).joinedload(TaskVideo.task),
        )
        .where(Video.id == video_id)
    ).unique().scalar_one_or_none()
    if video is None:
        raise HTTPException(status_code=404, detail="视频不存在")
    current_link = next(
        (link for link in video.task_links if link.task_id == task_id), None
    )
    if task_id is not None and current_link is None:
        raise HTTPException(status_code=404, detail="该视频不属于指定任务")
    current_task = current_link.task if current_link is not None else None
    keyword_links = []
    seen_keywords = set()
    for link in video.task_links:
        if link.task.keyword in seen_keywords:
            continue
        seen_keywords.add(link.task.keyword)
        keyword_links.append((link.task_id, link.task.keyword))
    total_comments = db.scalar(
        select(func.count()).select_from(Comment).where(Comment.video_id == video_id)
    ) or 0
    total_top_level = db.scalar(
        select(func.count()).select_from(Comment).where(
            Comment.video_id == video_id,
            Comment.parent_comment_id.is_(None),
        )
    ) or 0
    pager = pagination(total_top_level, page)
    comments = db.scalars(
        select(Comment)
        .where(
            Comment.video_id == video_id,
            Comment.parent_comment_id.is_(None),
        )
        .order_by(Comment.id)
        .offset(pager["offset"])
        .limit(PAGE_SIZE)
    ).all()
    comment_ids = [comment.platform_comment_id for comment in comments]
    replies = db.scalars(
        select(Comment)
        .where(
            Comment.video_id == video_id,
            Comment.parent_comment_id.in_(comment_ids or [""]),
        )
        .order_by(Comment.id)
    ).all()
    replies_by_parent: dict[str, list[Comment]] = {comment_id: [] for comment_id in comment_ids}
    for reply in replies:
        if reply.parent_comment_id in replies_by_parent:
            replies_by_parent[reply.parent_comment_id].append(reply)
    return templates.TemplateResponse(
        request=request,
        name="video_detail.html",
        context={
            "video": video,
            "current_task": current_task,
            "comments": comments,
            "total_comments": total_comments,
            "total_top_level": total_top_level,
            "total_replies": max(0, total_comments - total_top_level),
            "replies_by_parent": replies_by_parent,
            "keyword_links": keyword_links,
            "pagination": pager,
            "base_url": (
                f"/videos/{video_id}?task_id={task_id}"
                if task_id is not None
                else f"/videos/{video_id}"
            ),
            "page_query_prefix": "&" if task_id is not None else "?",
        },
    )


@app.get("/tasks/{task_id}/export.csv")
def export_task(task_id: int):
    try:
        csv_content = build_task_csv(task_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="task-{task_id}.csv"'},
    )


@app.get("/health")
def health():
    return {"status": "ok"}
