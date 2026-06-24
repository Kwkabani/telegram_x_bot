import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from x_browser.browser import PlaywrightManager

logger = logging.getLogger(__name__)

SCREENSHOT_DIR = Path(__file__).parent.parent / "logs" / "debug_screenshots"


class ScreenshotError(Exception):
    def __init__(self, message: str, screenshot_path: str = ""):
        super().__init__(message)
        self.screenshot_path = screenshot_path


async def _save_debug_screenshot(page, name: str) -> str:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = str(SCREENSHOT_DIR / f"{name}_{ts}.png")
    try:
        await page.screenshot(path=path, full_page=True)
        logger.info(f"Debug screenshot saved: {path}")
    except Exception as e:
        logger.warning(f"Failed to save screenshot: {e}")
    return path


async def _debug_info(page, label: str, callback=None):
    """Log URL, input count, and key element state at the current step."""
    try:
        url = page.url
        total_inputs = await page.locator("input").count()
        text_input = page.locator('input[name="text"]')
        text_count = await text_input.count()
        text_visible = await text_input.first.is_visible() if text_count > 0 else False
        msg = (
            f"[DEBUG {label}] url={url}"
            f" | inputs={total_inputs}"
            f" | input[name=text] count={text_count} visible={text_visible}"
        )
        logger.info(msg)
        if callback:
            await callback(msg)
    except Exception as e:
        logger.warning(f"Debug info failed at {label}: {e}")


async def _try_selectors(page, selectors: list, timeout: int = 15000):
    """Try each selector in sequence, return the first visible match."""
    per = max(3000, timeout // len(selectors))
    last_error = None
    for sel in selectors:
        try:
            loc = page.locator(sel)
            await loc.wait_for(state="visible", timeout=per)
            return loc
        except Exception as e:
            last_error = e
    raise Exception(f"No selector matched a visible element: {selectors}. Last error: {last_error}")


async def _get_page_text(page) -> str:
    try:
        text = await page.inner_text("body")
        return (text or "")[:500]
    except Exception:
        return ""


async def _is_on_login_page(page) -> bool:
    url = page.url.lower()
    return "login" in url or "i/flow" in url


async def _wait_for_login_complete(page, timeout: int = 60000) -> str:
    """Wait until login completes or an intermediate page is detected.
    Returns the type of page reached: 'home', 'verify_email', 'unusual', 'unknown'."""
    import asyncio
    deadline = datetime.utcnow().timestamp() + (timeout / 1000)

    home_selectors = [
        '[data-testid="AppTabBar_Home_Link"]',
        '[data-testid="SideNav_NewTweet_Button"]',
        '[data-testid="primaryColumn"]',
        'a[data-testid="AppTabBar_Profile_Link"]',
    ]

    while datetime.utcnow().timestamp() < deadline:
        await asyncio.sleep(1)
        url = page.url.lower()

        if "login" in url or "i/flow" in url:
            continue

        for sel in home_selectors:
            try:
                if await page.locator(sel).is_visible(timeout=1000):
                    return "home"
            except Exception:
                pass

        if "/home" in url or "/explore" in url or "/notifications" in url or "/messages" in url:
            return "home"

        body_text = await _get_page_text(page)

        if any(kw in body_text for kw in ["confirm your email", "verify your email", "check your email",
                                           "confirm your account", "verify email"]):
            return "verify_email"

        if any(kw in body_text for kw in ["unusual login", "suspicious activity", "confirm it's you",
                                           "enter your phone", "confirm your phone"]):
            return "unusual"

        if any(kw in body_text for kw in ["enter your phone number or username",
                                           "confirm your username", "enter your username"]):
            return "unusual"

        if any(kw in body_text for kw in ["captcha", "prove you're human", "security check"]):
            return "captcha"

        if url != "about:blank" and "x.com" in url and not _is_on_login_page(page):
            return "other"

    return "timeout"


async def login_with_credentials(
    username: str,
    password: str,
    on_2fa: Optional[callable] = None,
    progress_callback: Optional[callable] = None,
    debug_callback: Optional[callable] = None,
) -> Tuple[Optional[str], Optional[str], Optional[list]]:
    pm = PlaywrightManager.get_instance()
    context = await pm.new_context(progress_callback=progress_callback)
    page = await context.new_page()

    try:
        if progress_callback:
            await progress_callback("🔄 فتح صفحة تسجيل الدخول...")

        # ── Console & error logging ──
        page.on("console", lambda msg: logger.info(f"[BROWSER] {msg.type}: {msg.text[:200]}"))
        page.on("pageerror", lambda err: logger.error(f"[BROWSER_ERROR] {err}"))

        await page.goto("https://x.com/login", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(5000)
        await _debug_info(page, "after_goto", debug_callback)

        # ── Step screenshots dir ──
        step = 0

        # ── Step 1: Username ──
        step += 1
        await _save_debug_screenshot(page, f"login_step{step}_before_username")
        if progress_callback:
            await progress_callback("🔄 إدخال اسم المستخدم...")
        username_input = await _try_selectors(page, [
            'input[autocomplete="username"]',
            'input[name="text"]',
            'input[data-testid="ocfEnterTextTextInput"]',
        ])
        await username_input.fill(username)
        await page.locator(
            'button:has-text("Next"), span:has-text("Next"), '
            'button[type="submit"], div[role="button"]:has-text("Next"), '
            '[data-testid*="Login"], [data-testid*="Next"]'
        ).first.click()
        await page.wait_for_timeout(2000)
        await _save_debug_screenshot(page, f"login_step{step}_after_username")
        await _debug_info(page, "after_username", debug_callback)

        # ── Step 1b: Unusual activity check (enter username again) ──
        try:
            unusual = page.locator('input[data-testid="ocfEnterTextTextInput"]')
            if await unusual.is_visible(timeout=3000):
                if progress_callback:
                    await progress_callback("🔄 التحقق من النشاط غير المعتاد...")
                await unusual.fill(username)
                await page.locator(
                    'button:has-text("Next"), span:has-text("Next"), '
                    'button[type="submit"], div[role="button"]:has-text("Next")'
                ).first.click()
                await page.wait_for_timeout(2000)
                await _debug_info(page, "after_unusual", debug_callback)
        except Exception:
            pass

        # ── Step 2: Password ──
        step += 1
        await _save_debug_screenshot(page, f"login_step{step}_before_password")
        if progress_callback:
            await progress_callback("🔄 إدخال كلمة المرور...")
        password_input = await _try_selectors(page, [
            'input[autocomplete="current-password"]',
            'input[type="password"]',
        ])
        await password_input.fill(password)
        await page.locator(
            'button:has-text("Log in"), span:has-text("Log in"), '
            'button[type="submit"], div[role="button"]:has-text("Log in"), '
            '[data-testid*="Login"]'
        ).first.click()
        await page.wait_for_timeout(2000)
        await _save_debug_screenshot(page, f"login_step{step}_after_password")
        await _debug_info(page, "after_password", debug_callback)

        # ── Step 3: 2FA ──
        try:
            two_fa_input = page.locator('input[data-testid="ocfEnterTextTextInput"]')
            if await two_fa_input.is_visible(timeout=5000):
                if on_2fa:
                    if progress_callback:
                        await progress_callback("🔄 في انتظار رمز التحقق...")
                    code = await on_2fa()
                    await two_fa_input.fill(code)
                    await page.locator(
                        'button:has-text("Next"), span:has-text("Next"), '
                        'button[type="submit"], div[role="button"]:has-text("Next")'
                    ).first.click()
                    await page.wait_for_timeout(3000)
                    await _debug_info(page, "after_2fa", debug_callback)
                else:
                    raise Exception("2FA required but no handler provided")
        except Exception as e:
            if "2FA required" in str(e):
                raise
            pass

        # ── Step 4: Wait for post-login page ──
        step += 1
        await _save_debug_screenshot(page, f"login_step{step}_before_wait")
        if progress_callback:
            await progress_callback("🔄 جاري التحقق من تسجيل الدخول...")
        await _debug_info(page, "before_wait_login", debug_callback)

        login_result = await _wait_for_login_complete(page, timeout=60000)
        logger.info(f"Login result: {login_result}")
        await _save_debug_screenshot(page, f"login_step{step}_result_{login_result}")

        if login_result == "verify_email":
            sp = await _save_debug_screenshot(page, "verify_email")
            raise ScreenshotError("X requires email verification. Check your email inbox and try again.", sp)

        if login_result == "unusual":
            sp = await _save_debug_screenshot(page, "unusual_activity")
            raise ScreenshotError("X detected unusual login activity. Please log in manually from your phone to verify.", sp)

        if login_result == "captcha":
            sp = await _save_debug_screenshot(page, "captcha")
            raise ScreenshotError("X requires a CAPTCHA. Please log in manually from your phone to verify.", sp)

        if login_result == "timeout":
            sp = await _save_debug_screenshot(page, "login_timeout")
            raise ScreenshotError("Login timed out after 60 seconds.", sp)

        if login_result not in ("home", "other"):
            sp = await _save_debug_screenshot(page, "unknown_state")
            raise ScreenshotError(f"Unexpected page after login: {page.url[:100]}", sp)

        # ── Step 5: Collect cookies ──
        await page.wait_for_timeout(2000)
        cookies = await context.cookies()

        # ── Step 6: Extract user info ──
        x_username = None
        try:
            profile_link = page.locator('a[data-testid="AppTabBar_Profile_Link"]')
            href = await profile_link.get_attribute("href", timeout=5000)
            if href:
                x_username = href.strip("/").split("/")[-1]
        except Exception:
            pass

        if not x_username:
            for c in cookies:
                if c["name"] == "twid":
                    x_username = c["value"]
                    break

        x_user_id = None
        for c in cookies:
            if c["name"] == "twid":
                x_user_id = c["value"]
                break

        if not cookies:
            raise Exception("No cookies received after login")

        logger.info(f"Login successful for user {x_username}")
        return x_user_id, x_username, cookies

    except ScreenshotError:
        raise
    except Exception as e:
        logger.error(f"Login failed: {e}")
        sp = ""
        try:
            sp = await _save_debug_screenshot(page, "login_failed")
        except Exception:
            pass
        try:
            html_path = SCREENSHOT_DIR / f"login_failed_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.html"
            SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
            html = await page.content()
            with open(str(html_path), "w", encoding="utf-8") as f:
                f.write(html)
            logger.info(f"Debug HTML saved: {html_path}")
        except Exception:
            pass
        raise ScreenshotError(str(e), sp) from e
    finally:
        await pm.close_context(context)


async def validate_cookies(cookies: list) -> Tuple[Optional[str], Optional[str]]:
    pm = PlaywrightManager.get_instance()
    context = await pm.new_context(cookies)
    page = await context.new_page()

    try:
        await page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)

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
