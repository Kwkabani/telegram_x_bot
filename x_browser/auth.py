import logging
from typing import Optional, Tuple

from x_browser.browser import PlaywrightManager

logger = logging.getLogger(__name__)


async def login_with_credentials(
    username: str,
    password: str,
    on_2fa: Optional[callable] = None,
) -> Tuple[Optional[str], Optional[str], Optional[list]]:
    pm = PlaywrightManager.get_instance()
    context = await pm.new_context()
    page = await context.new_page()

    try:
        await page.goto("https://x.com/login", wait_until="networkidle")
        await page.wait_for_timeout(2000)

        username_input = page.locator('input[autocomplete="username"]')
        await username_input.fill(username)
        await page.click('span:has-text("Next")')
        await page.wait_for_timeout(2000)

        try:
            unusual = page.locator('input[data-testid="ocfEnterTextTextInput"]')
            if await unusual.is_visible(timeout=2000):
                await unusual.fill(username)
                await page.click('span:has-text("Next")')
                await page.wait_for_timeout(2000)
        except Exception:
            pass

        password_input = page.locator('input[autocomplete="current-password"]')
        await password_input.fill(password)
        await page.click('span:has-text("Log in")')
        await page.wait_for_timeout(3000)

        try:
            two_fa_input = page.locator('input[data-testid="ocfEnterTextTextInput"]')
            if await two_fa_input.is_visible(timeout=3000):
                if on_2fa:
                    code = await on_2fa()
                    await two_fa_input.fill(code)
                    await page.click('span:has-text("Next")')
                    await page.wait_for_timeout(3000)
                else:
                    raise Exception("2FA required but no handler provided")
        except Exception as e:
            if "2FA required" in str(e):
                raise
            pass

        await page.wait_for_url("**/home", timeout=15000)

        cookies = await context.cookies()

        x_username = None
        try:
            profile_link = page.locator('a[data-testid="AppTabBar_Profile_Link"]')
            href = await profile_link.get_attribute("href")
            if href:
                x_username = href.strip("/").split("/")[-1]
        except Exception:
            pass

        x_user_id = None
        for c in cookies:
            if c["name"] == "twid":
                x_user_id = c["value"]
                break

        return x_user_id, x_username, cookies

    except Exception as e:
        logger.error(f"Login failed: {e}")
        return None, None, None
    finally:
        await pm.close_context(context)


async def validate_cookies(cookies: list) -> Tuple[Optional[str], Optional[str]]:
    pm = PlaywrightManager.get_instance()
    context = await pm.new_context(cookies)
    page = await context.new_page()

    try:
        await page.goto("https://x.com/home", wait_until="networkidle", timeout=30000)

        x_username = None
        try:
            profile_link = page.locator('a[data-testid="AppTabBar_Profile_Link"]')
            href = await profile_link.get_attribute("href")
            if href:
                x_username = href.strip("/").split("/")[-1]
        except Exception:
            pass

        x_user_id = None
        for c in cookies:
            if c["name"] == "twid":
                x_user_id = c["value"]
                break

        if x_username:
            return x_user_id, x_username
        return None, None
    except Exception as e:
        logger.error(f"Cookie validation failed: {e}")
        return None, None
    finally:
        await pm.close_context(context)
