import asyncio
import logging
import os
import sys
from typing import Optional

from playwright.async_api import async_playwright, Browser, BrowserContext
from playwright_stealth import Stealth

logger = logging.getLogger(__name__)


async def _ensure_browser_installed(progress_callback=None) -> None:
    cache_dir = os.environ.get(
        "PLAYWRIGHT_BROWSERS_PATH",
        os.path.join(os.path.expanduser("~"), ".cache", "ms-playwright"),
    )
    if os.path.isdir(cache_dir):
        for entry in os.listdir(cache_dir):
            if entry.startswith("chromium"):
                return
    logger.info("Chromium browser not found, installing...")
    if progress_callback:
        await progress_callback("جارٍ تحميل متصفح كروم... (قد يستغرق دقيقة)")
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "playwright", "install", "chromium",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(
            f"Chromium install failed (exit {proc.returncode}): "
            f"{stdout.decode(errors='replace') if stdout else 'unknown'}"
        )
    logger.info("Chromium browser installed")


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

    async def get_browser(self, progress_callback=None) -> Browser:
        async with self._lock:
            if self._browser is None or not self._browser.is_connected():
                await _ensure_browser_installed(progress_callback)
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

    async def new_context(self, cookies: Optional[list] = None, progress_callback=None) -> BrowserContext:
        browser = await self.get_browser(progress_callback)
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
        await Stealth().apply_stealth_async(context)
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
