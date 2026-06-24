import logging
from typing import Optional

from x_browser.browser import PlaywrightManager

logger = logging.getLogger(__name__)


class XBrowserClient:
    def __init__(self, cookies: list):
        self._cookies = cookies

    async def post_tweet(self, text: str, media_path: Optional[str] = None) -> str:
        pm = PlaywrightManager.get_instance()
        context = await pm.new_context(self._cookies)
        page = await context.new_page()

        try:
            await page.goto("https://x.com/compose/post", wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)

            tweet_input = page.locator('div[data-testid="tweetTextarea_0"]')
            await tweet_input.click()
            await page.wait_for_timeout(500)
            await tweet_input.fill(text)

            if media_path:
                file_input = page.locator('input[data-testid="fileInput"]')
                if await file_input.is_visible(timeout=5000):
                    await file_input.set_input_files(media_path)
                    await page.wait_for_timeout(3000)

            tweet_button = page.locator('button[data-testid="tweetButton"]')
            await tweet_button.click()
            await page.wait_for_timeout(3000)

            tweet_url = None
            try:
                current_url = page.url
                if "/status/" in current_url:
                    tweet_url = current_url
            except Exception:
                pass

            if not tweet_url:
                raise Exception("Could not determine tweet URL after posting")

            tweet_id = tweet_url.split("/status/")[-1].split("?")[0]
            logger.info(f"Tweet posted via browser: {tweet_id}")
            return tweet_id

        except Exception as e:
            logger.error(f"Browser post failed: {e}")
            raise
        finally:
            await pm.close_context(context)

    async def delete_tweet(self, tweet_id: str) -> bool:
        pm = PlaywrightManager.get_instance()
        context = await pm.new_context(self._cookies)
        page = await context.new_page()

        try:
            tweet_url = f"https://x.com/i/status/{tweet_id}"
            await page.goto(tweet_url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)

            more_button = page.locator('button[data-testid="caret"]')
            await more_button.click()
            await page.wait_for_timeout(1000)

            delete_button = page.locator('span:has-text("Delete")')
            await delete_button.click()
            await page.wait_for_timeout(1000)

            confirm_button = page.locator('button[data-testid="confirmationSheetConfirm"]')
            await confirm_button.click()
            await page.wait_for_timeout(2000)

            logger.info(f"Tweet deleted via browser: {tweet_id}")
            return True

        except Exception as e:
            logger.error(f"Browser delete failed: {e}")
            raise
        finally:
            await pm.close_context(context)
