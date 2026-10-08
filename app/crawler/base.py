from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field


@dataclass(slots=True)
class CollectedComment:
    comment_id: str
    author_name: str
    content: str
    like_count: int = 0
    published_at: str = ""
    parent_comment_id: str | None = None


@dataclass(slots=True)
class CollectedVideo:
    video_id: str
    url: str
    description: str
    author_name: str
    author_url: str = ""
    cover_url: str = ""
    published_at: str = ""
    like_count: int = 0
    comment_count: int = 0
    share_count: int = 0
    comments: list[CollectedComment] = field(default_factory=list)


class TikTokCollector(ABC):
    @abstractmethod
    async def collect(
        self,
        keyword: str,
        max_videos: int,
        max_comments: int,
        max_replies: int,
        on_video: Callable[[CollectedVideo, int], Awaitable[None]] | None = None,
        get_cached_video: Callable[[str], CollectedVideo | None] | None = None,
    ) -> list[CollectedVideo]:
        """Collect videos and their comments for one keyword."""
