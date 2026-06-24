import logging
import re
from typing import Optional

from x_browser.browser import PlaywrightManager
from x_browser.human import human_type, random_delay

logger = logging.getLogger(__name__)


async def post_tweet(text: str, cookies: list, progress_callback=None) -> tuple[Optional[str], list]:
    pm = PlaywrightManager.get_instance()
    context = await pm.create_stealth_context(cookies)
    page = await context.new_page()

    try:
        if progress_callback:
            await progress_callback("🔄 فتح X...")
        await page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)
        await random_delay(1, 3)

        textarea = None
        for sel in [
            '[data-testid="tweetTextarea_0"]',
            '[data-testid="tweetTextarea_0"] [role="textbox"]',
            '[data-testid="tweetTextarea_0"] .public-DraftEditor-content',
        ]:
            try:
                loc = page.locator(sel)
                if await loc.is_visible(timeout=3000):
                    textarea = loc
                    break
            except Exception:
                continue

        if not textarea:
            compose = page.locator('[data-testid="SideNav_NewTweet_Button"]')
            if await compose.is_visible(timeout=3000):
                await compose.click()
                await random_delay(1, 2)
                textarea = page.locator('[data-testid="tweetTextarea_0"]')
                await textarea.wait_for(state="visible", timeout=10000)

        if not textarea:
            raise Exception("Could not find tweet textarea")

        if progress_callback:
            await progress_callback("🔄 جاري كتابة المنشور...")
        await textarea.click()
        await random_delay(0.3, 0.8)
        await human_type(page, text)
        await random_delay(0.5, 1.5)

        tweet_btn = None
        for sel in [
            '[data-testid="tweetButtonInline"]',
            '[data-testid="tweetButton"]',
            'button:has-text("Tweet")',
            'div[data-testid*="tweetButton"]',
        ]:
            try:
                loc = page.locator(sel)
                if await loc.is_visible(timeout=2000):
                    tweet_btn = loc
                    break
            except Exception:
                continue

        if not tweet_btn:
            raise Exception("Could not find tweet button")

        if progress_callback:
            await progress_callback("🔄 جاري النشر...")
        await tweet_btn.click()
        await page.wait_for_timeout(5000)

        tweet_id = None
        match = re.search(r'/status/(\d+)', page.url)
        if match:
            tweet_id = match.group(1)

        cookies_new = await context.cookies()
        return tweet_id, cookies_new

    finally:
        await pm.close_context(context)


async def delete_tweet(tweet_id: str, cookies: list, progress_callback=None) -> list:
    pm = PlaywrightManager.get_instance()
    context = await pm.create_stealth_context(cookies)
    page = await context.new_page()

    try:
        if progress_callback:
            await progress_callback("🔄 فتح التغريدة...")
        await page.goto(f"https://x.com/user/status/{tweet_id}", wait_until="domcontentloaded", timeout=30000)
        await random_delay(1.5, 3)

        if progress_callback:
            await progress_callback("🔄 جاري الحذف...")

        caret = page.locator('[data-testid="caret"]')
        await caret.wait_for(state="visible", timeout=10000)
        await caret.click()
        await random_delay(0.5, 1)

        delete_opt = None
        for sel in [
            '//span[text()="Delete"]',
            '//span[contains(text(), "Delete")]',
            '[data-testid*="delete"]',
        ]:
            try:
                loc = page.locator(sel)
                if await loc.is_visible(timeout=2000):
                    delete_opt = loc
                    break
            except Exception:
                continue

        if not delete_opt:
            raise Exception("Could not find Delete option")

        await delete_opt.click()
        await random_delay(0.3, 0.8)

        confirm = page.locator('[data-testid="confirmationSheetConfirm"]')
        await confirm.wait_for(state="visible", timeout=5000)
        await confirm.click()
        await page.wait_for_timeout(3000)

        return await context.cookies()

    finally:
        await pm.close_context(context)
