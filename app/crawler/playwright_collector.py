import asyncio
import hashlib
import inspect
import logging
import os
import re
import socket
from datetime import datetime
from pathlib import Path
from collections.abc import Awaitable, Callable
from urllib.parse import quote_plus

from playwright.async_api import Locator, Page, async_playwright

from app.config import GUEST_PROFILE_DIR, OUTPUT_DIR
from app.crawler.base import CollectedComment, CollectedVideo, TikTokCollector
from app.crawler.network_capture import TikTokNetworkCapture, merge_video
from app.crawler.utils import parse_compact_number


logger = logging.getLogger(__name__)


class PlaywrightTikTokCollector(TikTokCollector):
    """Collect public TikTok data using browser responses with a DOM fallback."""

    async def collect(
        self,
        keyword: str,
        max_videos: int,
        max_comments: int,
        max_replies: int,
        on_video: Callable[[CollectedVideo, int], Awaitable[None]] | None = None,
        get_cached_video: Callable[[str], CollectedVideo | None] | None = None,
    ) -> list[CollectedVideo]:
        GUEST_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        raw_dir = self._create_run_dir(keyword)
        capture = TikTokNetworkCapture(raw_dir)
        headless = os.getenv("TIKTOK_HEADLESS", "0") == "1"

        async with async_playwright() as playwright:
            browser = None
            browser_process = None
            if not headless and self._find_browser_executable():
                browser, context, browser_process = await self._connect_normal_browser(
                    playwright
                )
            else:
                context = await playwright.chromium.launch_persistent_context(
                    str(GUEST_PROFILE_DIR),
                    viewport={"width": 1440, "height": 960},
                    locale="zh-CN",
                    timezone_id="Asia/Shanghai",
                    **self._browser_launch_options(headless),
                )
            page = context.pages[0] if context.pages else await context.new_page()
            capture.attach(page)
            try:
                urls = await self._search_video_urls(
                    page, capture, keyword, max_videos, raw_dir
                )
                videos: list[CollectedVideo | None] = [None] * len(urls)
                cached_indexes: set[int] = set()

                # Search responses already contain complete video metadata. Save
                # it immediately so results appear before comment collection.
                for index, url in enumerate(urls, start=1):
                    video_id = self._video_id_from_url(url)
                    cached = get_cached_video(video_id) if get_cached_video else None
                    video = cached or capture.get_video(video_id) or CollectedVideo(
                        video_id=video_id,
                        url=url,
                        description="",
                        author_name="",
                    )
                    video.url = url
                    videos[index - 1] = video
                    if cached is not None:
                        cached_indexes.add(index - 1)
                    await self._notify_video(on_video, video, index)

                semaphore = asyncio.Semaphore(2)

                async def collect_main(index: int, url: str) -> None:
                    if index - 1 in cached_indexes:
                        return
                    async with semaphore:
                        worker = await context.new_page()
                        capture.attach(worker)
                        try:
                            video = await self._collect_video_main(
                                worker, capture, url, max_comments
                            )
                            videos[index - 1] = video
                            await self._notify_video(on_video, video, index)
                        except Exception as exc:
                            logger.exception(
                                "Failed to collect main comments for %s: %s", url, exc
                            )
                            await self._safe_screenshot(
                                worker, raw_dir / f"video-{index:02d}-failed.png"
                            )
                        finally:
                            await worker.close()

                await asyncio.gather(
                    *(
                        collect_main(index, url)
                        for index, url in enumerate(urls, start=1)
                    )
                )

                # Reply collection is deliberately a second phase so it never
                # delays or changes the selected top-level comment sequence.
                if max_replies > 0:
                    async def collect_replies(index: int, url: str) -> None:
                        if index - 1 in cached_indexes:
                            return
                        video = videos[index - 1]
                        if video is None or not video.comments:
                            return
                        async with semaphore:
                            worker = await context.new_page()
                            capture.attach(worker)
                            try:
                                await self._collect_video_replies(
                                    worker, capture, url, video, max_replies
                                )
                                await self._notify_video(on_video, video, index)
                            except Exception as exc:
                                logger.exception(
                                    "Failed to collect replies for %s: %s", url, exc
                                )
                            finally:
                                await worker.close()

                    await asyncio.gather(
                        *(
                            collect_replies(index, url)
                            for index, url in enumerate(urls, start=1)
                        )
                    )

                return [video for video in videos if video is not None]
            finally:
                await capture.flush()
                if browser is not None:
                    await browser.close()
                else:
                    await context.close()
                if browser_process is not None and browser_process.returncode is None:
                    try:
                        await asyncio.wait_for(browser_process.wait(), timeout=5)
                    except TimeoutError:
                        browser_process.terminate()

    async def _search_video_urls(
        self,
        page: Page,
        capture: TikTokNetworkCapture,
        keyword: str,
        max_videos: int,
        raw_dir: Path,
    ) -> list[str]:
        await self._open_guest_search(page, keyword)

        found: dict[str, None] = {}
        unchanged_rounds = 0
        previous_count = 0
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 15

        while len(found) < max_videos and loop.time() < deadline:
            try:
                links = await page.locator('a[href*="/video/"]').evaluate_all(
                    "elements => elements.map(element => element.href)"
                )
            except Exception:
                links = []
            for link in links:
                self._add_video_url(found, link)

            await capture.flush()
            for link in capture.video_urls():
                self._add_video_url(found, link)

            unchanged_rounds = unchanged_rounds + 1 if len(found) == previous_count else 0
            previous_count = len(found)
            if len(found) >= max_videos:
                break
            if found and unchanged_rounds >= 3:
                break
            await page.mouse.wheel(0, 2_400)
            await page.wait_for_timeout(600)

        if not found:
            screenshot = raw_dir / "search-failed.png"
            await self._safe_screenshot(page, screenshot)
            raise RuntimeError(
                "游客搜索没有返回视频。请确认可见浏览器中的 TikTok 搜索页能够正常显示，"
                f"并检查诊断截图：{screenshot}"
            )
        return list(found)[:max_videos]

    async def _collect_video_main(
        self,
        page: Page,
        capture: TikTokNetworkCapture,
        url: str,
        max_comments: int,
    ) -> CollectedVideo:
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_timeout(350)
        self._raise_for_challenge(page)
        await self._dismiss_guest_overlays(page)

        video_id = self._video_id_from_url(url)

        dom_video = await self._collect_video_from_dom(page, url, video_id)
        comments = await self._collect_top_level_comments(
            page, capture, video_id, max_comments
        )
        await capture.flush()

        network_video = capture.get_video(video_id)
        video = merge_video(dom_video, network_video) if network_video else dom_video
        video.comments = comments
        return video

    async def _collect_video_replies(
        self,
        page: Page,
        capture: TikTokNetworkCapture,
        url: str,
        video: CollectedVideo,
        max_replies: int,
    ) -> None:
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_timeout(350)
        self._raise_for_challenge(page)
        await self._dismiss_guest_overlays(page)
        await self._wait_for_comment_dom(page)
        parent_ids = [comment.comment_id for comment in video.comments]
        await self._collect_replies_for_selected_comments(
            page, capture, video.video_id, parent_ids, max_replies
        )
        result: list[CollectedComment] = []
        for comment in video.comments:
            result.append(comment)
            result.extend(
                capture.get_replies(video.video_id, comment.comment_id, max_replies)
            )
        video.comments = result

    async def _collect_video_from_dom(
        self, page: Page, url: str, video_id: str
    ) -> CollectedVideo:
        description = await self._first_text(
            page, ['[data-e2e="browse-video-desc"]']
        )
        if not description:
            description = await self._first_text(
                page, ['meta[property="og:description"]'], attribute="content"
            )
        author_name = await self._first_text(
            page, ['[data-e2e="browse-username"]', 'h2[data-e2e="browser-nickname"]']
        )
        author_match = re.search(r"tiktok\.com/@([^/]+)", url)
        fallback_author = author_match.group(1) if author_match else ""
        author_name = author_name.lstrip("@") or fallback_author

        like_text = await self._first_text(page, ['[data-e2e="browse-like-count"]'])
        comment_text = await self._first_text(page, ['[data-e2e="browse-comment-count"]'])
        share_text = await self._first_text(page, ['[data-e2e="browse-share-count"]'])
        cover_url = await self._first_text(
            page, ['meta[property="og:image"]'], attribute="content"
        )

        return CollectedVideo(
            video_id=video_id,
            url=url,
            description=description,
            author_name=author_name,
            author_url=f"https://www.tiktok.com/@{fallback_author}" if fallback_author else "",
            cover_url=cover_url,
            like_count=parse_compact_number(like_text),
            comment_count=parse_compact_number(comment_text),
            share_count=parse_compact_number(share_text),
        )

    async def _collect_comments(
        self,
        page: Page,
        capture: TikTokNetworkCapture,
        video_id: str,
        max_comments: int,
        max_replies: int,
    ) -> list[CollectedComment]:
        top_level = await self._collect_top_level_comments(
            page, capture, video_id, max_comments
        )
        parent_ids = [
            comment.comment_id
            for comment in top_level
            if not comment.comment_id.startswith("dom-")
        ]
        if max_replies > 0 and parent_ids:
            await self._collect_replies_for_selected_comments(
                page, capture, video_id, parent_ids, max_replies
            )
        result: list[CollectedComment] = []
        for comment in top_level:
            result.append(comment)
            result.extend(
                capture.get_replies(video_id, comment.comment_id, max_replies)
            )
        return result

    async def _collect_top_level_comments(
        self,
        page: Page,
        capture: TikTokNetworkCapture,
        video_id: str,
        max_comments: int,
    ) -> list[CollectedComment]:
        if max_comments <= 0:
            return []

        await self._wait_for_comments_to_load(page, capture, video_id)
        dom_comments: dict[str, CollectedComment] = {}
        unchanged_rounds = 0
        previous_total = -1
        rounds = 0
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 20

        # Phase 1 only loads top-level comments. Reply expansion must not change
        # which comments are selected or their TikTok response order.
        while unchanged_rounds < 2 and rounds < 6 and loop.time() < deadline:
            rounds += 1
            await capture.flush()
            await self._read_visible_dom_comments(
                page, video_id, dom_comments, max_comments
            )
            network_comments = capture.get_top_level_comments(video_id, max_comments)
            combined_total = (
                len(network_comments) if network_comments else len(dom_comments)
            )
            unchanged_rounds = (
                unchanged_rounds + 1
                if combined_total == previous_total
                else 0
            )
            previous_total = combined_total
            if combined_total >= max_comments:
                break
            await self._scroll_comments(page)
            await page.wait_for_timeout(500)

        await capture.flush()
        ordered_network_comments = capture.get_top_level_comments(
            video_id, max_comments
        )
        combined: dict[str, CollectedComment] = {
            comment.comment_id: comment for comment in ordered_network_comments
        }
        if not combined:
            combined.update(dom_comments)
        return list(combined.values())[:max_comments]

    async def _collect_replies_for_selected_comments(
        self,
        page: Page,
        capture: TikTokNetworkCapture,
        video_id: str,
        parent_comment_ids: list[str],
        max_replies: int,
    ) -> None:
        await self._rewind_comments(page)
        unchanged_rounds = 0
        previous_total = -1
        rounds = 0
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 20
        observed_comments = 0

        while unchanged_rounds < 2 and rounds < 6 and loop.time() < deadline:
            rounds += 1
            clicked = await self._expand_visible_replies(
                page, max_clicks=min(len(parent_comment_ids), 8)
            )
            if clicked:
                await page.wait_for_timeout(500)
            await capture.flush()

            reply_total = sum(
                len(capture.get_replies(video_id, parent_id, max_replies))
                for parent_id in parent_comment_ids
            )
            unchanged_rounds = (
                unchanged_rounds + 1 if reply_total == previous_total else 0
            )
            previous_total = reply_total

            try:
                observed_comments = max(
                    observed_comments,
                    await page.locator('[data-e2e="comment-level-1"]').count(),
                )
            except Exception:
                pass
            if (
                unchanged_rounds >= 2
                and observed_comments >= len(parent_comment_ids)
            ):
                break
            await self._scroll_comments(page)
            await page.wait_for_timeout(500)

    async def _read_visible_dom_comments(
        self,
        page: Page,
        video_id: str,
        comments: dict[str, CollectedComment],
        limit: int,
    ) -> None:
        items = page.locator('[data-e2e="comment-level-1"]')
        try:
            count = await items.count()
        except Exception:
            return

        for index in range(count):
            item = items.nth(index)
            try:
                raw_text = (await item.inner_text()).strip()
            except Exception:
                continue
            if not raw_text:
                continue

            author = await self._text_inside(
                item, ['[data-e2e="comment-username-1"]', 'a[href*="/@"]']
            )
            lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
            content = self._pick_comment_content(lines, author)
            if not content:
                continue

            element_id = await item.get_attribute("id")
            digest = hashlib.sha1(
                f"{video_id}|{author}|{content}".encode("utf-8")
            ).hexdigest()[:20]
            comment_id = element_id or f"dom-{digest}"
            comments[comment_id] = CollectedComment(
                comment_id=comment_id,
                author_name=author.lstrip("@"),
                content=content,
            )
            if len(comments) >= limit:
                return

    @staticmethod
    async def _expand_visible_replies(page: Page, max_clicks: int) -> int:
        if max_clicks <= 0:
            return 0
        patterns = (
            re.compile(r"(?:查看|展开|更多|其他).{0,20}(?:回复|评论)"),
            re.compile(r"(?:view|load|show).{0,20}(?:repl)", re.IGNORECASE),
        )
        clicked = 0
        for pattern in patterns:
            candidates = page.get_by_text(pattern)
            try:
                count = min(await candidates.count(), 30)
            except Exception:
                continue
            for index in range(count):
                if clicked >= max_clicks:
                    return clicked
                candidate = candidates.nth(index)
                try:
                    text = (await candidate.inner_text()).strip()
                    if not text or not await candidate.is_visible():
                        continue
                    await candidate.click(timeout=750)
                    clicked += 1
                    await page.wait_for_timeout(150)
                except Exception:
                    continue
        return clicked

    @staticmethod
    async def _rewind_comments(page: Page) -> None:
        comments = page.locator('[data-e2e="comment-level-1"]')
        try:
            if await comments.count():
                await comments.first.scroll_into_view_if_needed()
        except Exception:
            pass
        try:
            await page.mouse.wheel(0, -10_000)
            await page.wait_for_timeout(500)
        except Exception:
            pass

    @staticmethod
    async def _notify_video(on_video, video: CollectedVideo, rank: int) -> None:
        if on_video is None:
            return
        callback_result = on_video(video, rank)
        if inspect.isawaitable(callback_result):
            await callback_result

    @staticmethod
    def _video_id_from_url(url: str) -> str:
        match = re.search(r"/video/(\d+)", url)
        if not match:
            raise ValueError(f"无法从链接提取视频 ID: {url}")
        return match.group(1)

    @staticmethod
    def _create_run_dir(keyword: str) -> Path:
        safe_keyword = re.sub(r"[^\w\-]+", "-", keyword, flags=re.UNICODE).strip("-")
        safe_keyword = safe_keyword[:40] or "search"
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        path = OUTPUT_DIR / "raw" / f"{timestamp}-{safe_keyword}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _add_video_url(found: dict[str, None], link: str) -> None:
        clean_url = link.split("?")[0]
        if re.search(r"/video/\d+", clean_url):
            found[clean_url] = None

    @staticmethod
    def _raise_for_challenge(page: Page) -> None:
        current_url = page.url.lower()
        if "captcha" in current_url or "/verify" in current_url:
            raise RuntimeError("TikTok 要求完成验证，请在可见浏览器中处理后重试。")

    async def _open_guest_search(self, page: Page, keyword: str) -> None:
        # TikTok's general search page is available to guests more consistently
        # than the dedicated /search/video route.
        search_url = f"https://www.tiktok.com/search?q={quote_plus(keyword)}"
        for attempt in range(3):
            await page.goto(search_url, wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_timeout(1_500 + attempt * 750)
            self._raise_for_challenge(page)
            await self._dismiss_guest_overlays(page)
            if not await self._has_server_error(page):
                return
            logger.warning("TikTok guest search returned a server error; retrying")
            await page.wait_for_timeout(750)
        logger.warning("TikTok guest search still shows a server error after retries")

    @staticmethod
    async def _has_server_error(page: Page) -> bool:
        try:
            text = await page.locator("body").inner_text(timeout=5_000)
        except Exception:
            return False
        messages = (
            "服务器出现问题",
            "服务出现问题",
            "Something went wrong",
            "Server error",
        )
        return any(message.lower() in text.lower() for message in messages)

    @staticmethod
    def _browser_launch_options(headless: bool) -> dict:
        options: dict = {"headless": headless}
        if headless:
            return options

        browser_path = PlaywrightTikTokCollector._find_browser_executable()
        if browser_path:
            options["executable_path"] = str(browser_path)
        return options

    @staticmethod
    def _find_browser_executable() -> Path | None:
        configured = os.getenv("TIKTOK_BROWSER_PATH", "").strip()
        candidates = [
            Path(configured) if configured else None,
            Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        ]
        return next(
            (candidate for candidate in candidates if candidate and candidate.is_file()),
            None,
        )

    async def _connect_normal_browser(self, playwright):
        browser_path = self._find_browser_executable()
        if browser_path is None:
            raise RuntimeError("没有找到 Edge、Chrome 或 Playwright Chromium。")

        port = self._available_port()
        process = await asyncio.create_subprocess_exec(
            str(browser_path),
            f"--remote-debugging-port={port}",
            "--remote-debugging-address=127.0.0.1",
            f"--user-data-dir={GUEST_PROFILE_DIR}",
            "--no-first-run",
            "--window-size=1440,960",
            "about:blank",
        )
        await self._wait_for_debug_port(port, process)
        browser = await playwright.chromium.connect_over_cdp(
            f"http://127.0.0.1:{port}"
        )
        if not browser.contexts:
            await browser.close()
            raise RuntimeError("浏览器已经启动，但没有可用的游客上下文。")
        return browser, browser.contexts[0], process

    @staticmethod
    def _available_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    @staticmethod
    async def _wait_for_debug_port(port: int, process) -> None:
        for _ in range(60):
            if process.returncode is not None:
                raise RuntimeError("游客浏览器启动后立即退出。")
            try:
                _, writer = await asyncio.open_connection("127.0.0.1", port)
                writer.close()
                await writer.wait_closed()
                return
            except OSError:
                await asyncio.sleep(0.25)
        process.terminate()
        raise RuntimeError("游客浏览器启动超时。")

    async def _wait_for_comments_to_load(
        self,
        page: Page,
        capture: TikTokNetworkCapture,
        video_id: str,
    ) -> None:
        await self._dismiss_guest_overlays(page)

        loop = asyncio.get_running_loop()
        deadline = loop.time() + 12
        while loop.time() < deadline:
            await self._open_comments_panel(page)
            await capture.flush()
            if capture.get_comments(video_id, 1):
                return
            try:
                if await page.locator('[data-e2e="comment-level-1"]').count():
                    return
            except Exception:
                pass
            await self._dismiss_guest_overlays(page)
            await page.wait_for_timeout(500)

    async def _wait_for_comment_dom(self, page: Page) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 12
        while loop.time() < deadline:
            await self._open_comments_panel(page)
            try:
                if await page.locator('[data-e2e="comment-level-1"]').count():
                    return
            except Exception:
                pass
            await self._dismiss_guest_overlays(page)
            await page.wait_for_timeout(500)

    @staticmethod
    async def _open_comments_panel(page: Page) -> None:
        for tab_text in ("评论", "Comments"):
            comment_tab = page.get_by_text(tab_text, exact=True).first
            try:
                if await comment_tab.count() and await comment_tab.is_visible():
                    await comment_tab.click(timeout=2_000)
                    return
            except Exception:
                continue

        comment_icon = page.locator('[data-e2e="comment-icon"]').first
        try:
            if await comment_icon.count() and await comment_icon.is_visible():
                await comment_icon.click(timeout=2_000)
        except Exception:
            pass

    @staticmethod
    async def _dismiss_guest_overlays(page: Page) -> None:
        for text in ("知道了", "Got it"):
            button = page.get_by_text(text, exact=True).last
            try:
                if await button.count() and await button.is_visible():
                    await button.click(timeout=2_000)
            except Exception:
                continue

    @staticmethod
    async def _scroll_comments(page: Page) -> None:
        comments = page.locator('[data-e2e="comment-level-1"]')
        try:
            count = await comments.count()
            if count:
                await comments.nth(count - 1).scroll_into_view_if_needed()
        except Exception:
            pass
        await page.mouse.wheel(0, 1_600)

    @staticmethod
    async def _safe_screenshot(page: Page, path: Path) -> None:
        try:
            await page.screenshot(path=str(path), full_page=True)
        except Exception:
            logger.exception("Could not save diagnostic screenshot")

    @staticmethod
    def _pick_comment_content(lines: list[str], author: str) -> str:
        ignored = {author, author.lstrip("@"), "Reply", "回复", "Like", "赞"}
        candidates = [line for line in lines if line not in ignored]
        return candidates[0] if candidates else ""

    @staticmethod
    async def _first_text(
        page: Page, selectors: list[str], attribute: str | None = None
    ) -> str:
        for selector in selectors:
            locator = page.locator(selector).first
            try:
                if await locator.count() == 0:
                    continue
                value = (
                    await locator.get_attribute(attribute)
                    if attribute
                    else await locator.inner_text()
                )
                if value:
                    return value.strip()
            except Exception:
                continue
        return ""

    @staticmethod
    async def _text_inside(item: Locator, selectors: list[str]) -> str:
        for selector in selectors:
            locator = item.locator(selector).first
            try:
                if await locator.count():
                    value = await locator.inner_text()
                    if value:
                        return value.strip()
            except Exception:
                continue
        return ""
