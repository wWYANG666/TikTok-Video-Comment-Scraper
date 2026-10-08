import asyncio

from app.crawler.base import CollectedComment
from app.crawler.playwright_collector import PlaywrightTikTokCollector


class FakeCandidate:
    def __init__(self, page, index: int) -> None:
        self.page = page
        self.index = index

    async def inner_text(self) -> str:
        return f"查看其他 {self.index + 1} 条回复"

    async def is_visible(self) -> bool:
        return True

    async def click(self, timeout: int) -> None:
        self.page.clicks += 1


class FakeCandidates:
    def __init__(self, page) -> None:
        self.page = page

    async def count(self) -> int:
        return 10

    def nth(self, index: int) -> FakeCandidate:
        return FakeCandidate(self.page, index)


class FakePage:
    def __init__(self) -> None:
        self.clicks = 0

    def get_by_text(self, _pattern) -> FakeCandidates:
        return FakeCandidates(self)

    async def wait_for_timeout(self, _milliseconds: int) -> None:
        return None


class EmptyLinks:
    async def evaluate_all(self, _script):
        return []


class FakeMouse:
    async def wheel(self, _x: int, _y: int) -> None:
        return None


class DelayedSearchPage:
    def __init__(self) -> None:
        self.mouse = FakeMouse()

    def locator(self, _selector: str) -> EmptyLinks:
        return EmptyLinks()

    async def wait_for_timeout(self, _milliseconds: int) -> None:
        return None


class DelayedSearchCapture:
    def __init__(self) -> None:
        self.flushes = 0

    async def flush(self) -> None:
        self.flushes += 1

    def video_urls(self):
        if self.flushes >= 5:
            return ["https://www.tiktok.com/@author/video/123456789"]
        return []


def test_reply_expansion_respects_click_limit() -> None:
    page = FakePage()

    clicked = asyncio.run(
        PlaywrightTikTokCollector._expand_visible_replies(page, max_clicks=3)
    )

    assert clicked == 3
    assert page.clicks == 3


def test_search_waits_for_a_delayed_first_result(tmp_path) -> None:
    collector = PlaywrightTikTokCollector()
    page = DelayedSearchPage()
    capture = DelayedSearchCapture()

    async def skip_open(_page, _keyword):
        return None

    collector._open_guest_search = skip_open
    urls = asyncio.run(
        collector._search_video_urls(page, capture, "keyword", 1, tmp_path)
    )

    assert urls == ["https://www.tiktok.com/@author/video/123456789"]
    assert capture.flushes >= 5


class OrderedCapture:
    def __init__(self) -> None:
        self.visible = 1
        self.comments = [
            CollectedComment(f"main-{index}", "user", f"Comment {index}")
            for index in range(1, 4)
        ]
        self.replies: dict[str, list[CollectedComment]] = {}

    async def flush(self) -> None:
        return None

    def get_top_level_comments(self, _video_id: str, limit: int):
        return self.comments[: self.visible][:limit]

    def get_replies(self, _video_id: str, parent_id: str, limit: int):
        return self.replies.get(parent_id, [])[:limit]


class TwoPhaseCollector(PlaywrightTikTokCollector):
    def __init__(self) -> None:
        self.events: list[object] = []
        self.capture = None

    async def _wait_for_comments_to_load(self, _page, capture, _video_id):
        self.capture = capture
        self.events.append("wait")

    async def _read_visible_dom_comments(
        self, _page, _video_id, _comments, _limit
    ) -> None:
        return None

    async def _scroll_comments(self, _page) -> None:
        self.events.append("scroll-main")
        self.capture.visible = min(3, self.capture.visible + 1)

    async def _collect_replies_for_selected_comments(
        self, _page, capture, _video_id, parent_ids, _max_replies
    ) -> None:
        self.events.append(("replies", list(parent_ids)))
        capture.replies[parent_ids[0]] = [
            CollectedComment(
                "reply-1",
                "responder",
                "Reply",
                parent_comment_id=parent_ids[0],
            )
        ]


def test_main_comments_are_frozen_before_reply_collection() -> None:
    collector = TwoPhaseCollector()
    capture = OrderedCapture()
    page = FakePage()

    comments = asyncio.run(
        collector._collect_comments(page, capture, "video-1", 3, 2)
    )

    assert collector.events == [
        "wait",
        "scroll-main",
        "scroll-main",
        ("replies", ["main-1", "main-2", "main-3"]),
    ]
    assert [comment.comment_id for comment in comments] == [
        "main-1",
        "reply-1",
        "main-2",
        "main-3",
    ]
