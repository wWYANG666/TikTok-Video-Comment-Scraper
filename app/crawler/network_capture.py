import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from playwright.async_api import Page, Response

from app.crawler.base import CollectedComment, CollectedVideo


logger = logging.getLogger(__name__)


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _first(mapping: dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return default


def _url_from_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return ""
    urls = _first(value, "url_list", "urlList", default=[])
    if isinstance(urls, list) and urls:
        return str(urls[0])
    return str(_first(value, "url", "uri", default=""))


def _iso_timestamp(value: Any) -> str:
    timestamp = _as_int(value)
    if not timestamp:
        return ""
    try:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return ""


def _video_candidates(value: Any, depth: int = 0):
    if depth > 8:
        return
    if isinstance(value, list):
        for item in value:
            yield from _video_candidates(item, depth + 1)
        return
    if not isinstance(value, dict):
        return

    video_id = _first(value, "id", "aweme_id", "awemeId")
    description = _first(value, "desc", "description")
    if video_id and (description or "video" in value) and (
        "author" in value or "author_info" in value or "authorInfo" in value
    ):
        yield value

    for nested in value.values():
        if isinstance(nested, (dict, list)):
            yield from _video_candidates(nested, depth + 1)


def parse_video_payload(payload: Any) -> list[CollectedVideo]:
    videos: dict[str, CollectedVideo] = {}
    for item in _video_candidates(payload):
        video_id = str(_first(item, "id", "aweme_id", "awemeId"))
        if not video_id:
            continue

        author = _first(item, "author", "author_info", "authorInfo", default={})
        if not isinstance(author, dict):
            author = {}
        author_name = str(
            _first(author, "unique_id", "uniqueId", "nickname", "name", default="")
        ).lstrip("@")

        stats = _first(item, "stats", "statistics", default={})
        if not isinstance(stats, dict):
            stats = {}
        video_data = item.get("video") if isinstance(item.get("video"), dict) else {}
        cover = _first(
            video_data,
            "cover",
            "origin_cover",
            "originCover",
            "dynamic_cover",
            default="",
        )
        url = (
            f"https://www.tiktok.com/@{author_name}/video/{video_id}"
            if author_name
            else f"https://www.tiktok.com/video/{video_id}"
        )

        videos[video_id] = CollectedVideo(
            video_id=video_id,
            url=url,
            description=str(_first(item, "desc", "description", default="")),
            author_name=author_name,
            author_url=f"https://www.tiktok.com/@{author_name}" if author_name else "",
            cover_url=_url_from_value(cover),
            published_at=_iso_timestamp(
                _first(item, "create_time", "createTime", default=0)
            ),
            like_count=_as_int(
                _first(stats, "digg_count", "diggCount", "like_count", default=0)
            ),
            comment_count=_as_int(
                _first(stats, "comment_count", "commentCount", default=0)
            ),
            share_count=_as_int(
                _first(stats, "share_count", "shareCount", default=0)
            ),
        )
    return list(videos.values())


def _comment_candidates(value: Any, parent_id: str | None = None, depth: int = 0):
    if depth > 8:
        return
    if isinstance(value, list):
        for item in value:
            yield from _comment_candidates(item, parent_id, depth + 1)
        return
    if not isinstance(value, dict):
        return

    comment_id = _first(value, "cid", "comment_id", "commentId")
    text = _first(value, "text", "content")
    current_parent = parent_id
    if comment_id and text not in (None, ""):
        yield value, parent_id
        current_parent = str(comment_id)

    for key, nested in value.items():
        if not isinstance(nested, (dict, list)):
            continue
        nested_parent = current_parent if key in {
            "reply_comment",
            "reply_comments",
            "replyComment",
            "replies",
        } else parent_id
        yield from _comment_candidates(nested, nested_parent, depth + 1)


def _explicit_parent_id(item: dict[str, Any]) -> str | None:
    value = _first(
        item,
        "parent_comment_id",
        "parentCommentId",
        "reply_id",
        "replyId",
        "reply_to_reply_id",
        "replyToReplyId",
        default="",
    )
    parent_id = str(value or "")
    return parent_id if parent_id not in {"", "0"} else None


def parse_comment_payload(
    payload: Any, fallback_parent_id: str | None = None
) -> list[CollectedComment]:
    comments: dict[str, CollectedComment] = {}
    for item, parent_id in _comment_candidates(payload):
        comment_id = str(_first(item, "cid", "comment_id", "commentId"))
        if not comment_id:
            continue
        user = item.get("user") if isinstance(item.get("user"), dict) else {}
        resolved_parent_id = parent_id or fallback_parent_id or _explicit_parent_id(item)
        if resolved_parent_id == comment_id:
            resolved_parent_id = fallback_parent_id
        comments[comment_id] = CollectedComment(
            comment_id=comment_id,
            author_name=str(
                _first(user, "unique_id", "uniqueId", "nickname", default="")
            ).lstrip("@"),
            content=str(_first(item, "text", "content", default="")),
            like_count=_as_int(
                _first(item, "digg_count", "diggCount", "like_count", default=0)
            ),
            published_at=_iso_timestamp(
                _first(item, "create_time", "createTime", default=0)
            ),
            parent_comment_id=resolved_parent_id,
        )
    return list(comments.values())


def merge_video(existing: CollectedVideo, incoming: CollectedVideo) -> CollectedVideo:
    for field_name in (
        "url",
        "description",
        "author_name",
        "author_url",
        "cover_url",
        "published_at",
    ):
        value = getattr(incoming, field_name)
        if value:
            setattr(existing, field_name, value)
    for field_name in ("like_count", "comment_count", "share_count"):
        value = getattr(incoming, field_name)
        if value:
            setattr(existing, field_name, value)
    return existing


class TikTokNetworkCapture:
    def __init__(self, raw_dir: Path) -> None:
        self.raw_dir = raw_dir
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.videos: dict[str, CollectedVideo] = {}
        self.comments_by_video: dict[str, dict[str, CollectedComment]] = {}
        self._pending: set[asyncio.Task[None]] = set()
        self._counter = 0

    def attach(self, page: Page) -> None:
        def schedule(response: Response) -> None:
            task = asyncio.create_task(self._handle_response(response))
            self._pending.add(task)
            task.add_done_callback(self._pending.discard)

        page.on("response", schedule)

    async def flush(self) -> None:
        while self._pending:
            await asyncio.gather(*list(self._pending), return_exceptions=True)

    def video_urls(self) -> list[str]:
        return [video.url for video in self.videos.values()]

    def get_video(self, video_id: str) -> CollectedVideo | None:
        return self.videos.get(video_id)

    def get_top_level_comments(
        self, video_id: str, limit: int
    ) -> list[CollectedComment]:
        comments = self.comments_by_video.get(video_id, {}).values()
        return [comment for comment in comments if not comment.parent_comment_id][:limit]

    def get_replies(
        self, video_id: str, parent_comment_id: str, limit: int
    ) -> list[CollectedComment]:
        if limit <= 0:
            return []
        comments = self.comments_by_video.get(video_id, {}).values()
        return [
            comment
            for comment in comments
            if comment.parent_comment_id == parent_comment_id
        ][:limit]

    def get_comments(
        self, video_id: str, max_comments: int, max_replies: int = 0
    ) -> list[CollectedComment]:
        result: list[CollectedComment] = []
        for comment in self.get_top_level_comments(video_id, max_comments):
            result.append(comment)
            result.extend(
                self.get_replies(video_id, comment.comment_id, max_replies)
            )
        return result

    async def _handle_response(self, response: Response) -> None:
        kind = self._classify(response.url)
        if not kind or response.request.resource_type not in {"xhr", "fetch"}:
            return
        try:
            payload = await response.json()
        except Exception:
            return

        self._counter += 1
        await asyncio.to_thread(self._save_raw, kind, response.url, payload)

        if kind in {"search", "video"}:
            for video in parse_video_payload(payload):
                existing = self.videos.get(video.video_id)
                self.videos[video.video_id] = (
                    merge_video(existing, video) if existing else video
                )
            return

        video_id = self._video_id_from_url(response.url)
        if not video_id:
            logger.debug("Comment response did not contain a video ID: %s", response.url)
            return
        bucket = self.comments_by_video.setdefault(video_id, {})
        fallback_parent_id = self._parent_comment_id_from_url(response.url)
        for comment in parse_comment_payload(payload, fallback_parent_id):
            bucket[comment.comment_id] = comment

    def _save_raw(self, kind: str, url: str, payload: Any) -> None:
        safe_url = self._safe_url(url)
        document = {"kind": kind, "url": safe_url, "payload": payload}
        path = self.raw_dir / f"{self._counter:03d}-{kind}.json"
        path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @staticmethod
    def _classify(url: str) -> str | None:
        path = urlparse(url).path.lower()
        if "/api/comment/list" in path:
            return "comments"
        if "/api/search/" in path:
            return "search"
        if "/api/item/detail" in path or "/api/video/detail" in path:
            return "video"
        return None

    @staticmethod
    def _video_id_from_url(url: str) -> str:
        query = parse_qs(urlparse(url).query)
        for key in ("aweme_id", "item_id", "video_id"):
            values = query.get(key)
            if values:
                return values[0]
        return ""

    @staticmethod
    def _parent_comment_id_from_url(url: str) -> str | None:
        parsed = urlparse(url)
        if "reply" not in parsed.path.lower():
            return None
        query = parse_qs(parsed.query)
        for key in ("comment_id", "parent_comment_id", "reply_id", "cid"):
            values = query.get(key)
            if values and values[0] not in {"", "0"}:
                return values[0]
        return None

    @staticmethod
    def _safe_url(url: str) -> str:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        allowed = []
        for key in (
            "aweme_id",
            "item_id",
            "video_id",
            "comment_id",
            "parent_comment_id",
            "reply_id",
            "cursor",
            "count",
        ):
            if query.get(key):
                allowed.append(f"{key}={query[key][0]}")
        suffix = f"?{'&'.join(allowed)}" if allowed else ""
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}{suffix}"
