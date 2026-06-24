import asyncio
import logging
from typing import Optional

from playwright.async_api import async_playwright, Browser, BrowserContext

logger = logging.getLogger(__name__)

STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = { runtime: {} };
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
);
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5],
});
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en'],
});
"""


class PlaywrightManager:
    _instance = None
    _browser: Optional[Browser] = None

    def __init__(self):
        self._lock = asyncio.Lock()

    @classmethod
    def get_instance(cls) -> "PlaywrightManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def get_browser(self) -> Browser:
        async with self._lock:
            if self._browser is None or not self._browser.is_connected():
                pw = await async_playwright().start()
                self._browser = await pw.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--disable-web-security",
                        "--disable-features=IsolateOrigins,site-per-process",
                        "--window-size=1280,720",
                    ],
                )
                logger.info("Playwright browser launched")
            return self._browser

    async def new_context(self, cookies: Optional[list] = None) -> BrowserContext:
        browser = await self.get_browser()
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="America/New_York",
        )
        await context.add_init_script(STEALTH_SCRIPT)
        if cookies:
            await context.add_cookies(cookies)
        return context

    async def close_context(self, context: BrowserContext):
        await context.close()

    async def stop(self):
        async with self._lock:
            if self._browser:
                await self._browser.close()
                self._browser = None
