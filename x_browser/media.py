import logging
import re
from typing import Optional

from x_browser.browser import PlaywrightManager

logger = logging.getLogger(__name__)


async def upload_media(cookies: list, file_path: str) -> Optional[str]:
    pm = PlaywrightManager.get_instance()
    context = await pm.new_context(cookies)
    page = await context.new_page()

    try:
        await page.goto("https://x.com/compose/post", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)

        file_input = page.locator('input[data-testid="fileInput"]')
        if not await file_input.is_visible(timeout=5000):
            raise Exception("File input not found")

        await file_input.set_input_files(file_path)
        await page.wait_for_timeout(5000)

        media_id = None
        try:
            media_preview = page.locator('div[data-testid="attachment"]')
            preview_html = await media_preview.get_attribute("outerHTML")
            match = re.search(r'media_id=(\d+)', preview_html)
            if match:
                media_id = match.group(1)
        except Exception:
            pass

        logger.info(f"Media uploaded: {media_id}")
        return media_id

    except Exception as e:
        logger.error(f"Media upload failed: {e}")
        return None
    finally:
        await pm.close_context(context)
