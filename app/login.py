import asyncio

from playwright.async_api import async_playwright

from app.config import PROFILE_DIR


async def main() -> None:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            str(PROFILE_DIR), headless=False, viewport={"width": 1440, "height": 960}
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://www.tiktok.com/", wait_until="domcontentloaded")
        print("请在打开的浏览器中完成 TikTok 登录。登录成功后回到终端按 Enter。")
        await asyncio.to_thread(input)
        await context.close()


if __name__ == "__main__":
    asyncio.run(main())

