# Playwright Migration Plan - Step by Step

## 1. requirements.txt
Add at the end:
```
playwright>=1.60.0,<2.0
```

## 2. render.yaml
Change line 7:
```
buildCommand: pip install -r requirements.txt && playwright install chromium
```

## 3. x_browser/browser.py (NEW FILE)

```python
import asyncio
import logging
import os
from typing import Optional

from playwright.async_api import async_playwright, Browser, BrowserContext

logger = logging.getLogger(__name__)

STEALTH_SCRIPT = """
// Override navigator.webdriver
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// Override chrome.runtime
window.chrome = { runtime: {} };

// Override permissions
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
);

// Override plugins
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5],
});

// Override languages
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
```

## 4. x_browser/auth.py (NEW FILE)

```python
import json
import logging
import re
from typing import Optional, Tuple

from x_browser.browser import PlaywrightManager

logger = logging.getLogger(__name__)


async def login_with_credentials(
    username: str,
    password: str,
    on_2fa: Optional[callable] = None,
) -> Tuple[Optional[str], Optional[str], Optional[list]]:
    """
    Playwright login flow.
    Returns: (x_user_id, x_username, cookies_list)
    """
    pm = PlaywrightManager.get_instance()
    context = await pm.new_context()
    page = await context.new_page()

    try:
        await page.goto("https://x.com/login", wait_until="networkidle")
        await page.wait_for_timeout(2000)

        # Step 1: Enter username/email/phone
        username_input = page.locator('input[autocomplete="username"]')
        await username_input.fill(username)
        await page.click('span:has-text("Next")')
        await page.wait_for_timeout(2000)

        # Step 2: Handle unusual login (sometimes X asks for email/phone)
        try:
            unusual = page.locator('input[data-testid="ocfEnterTextTextInput"]')
            if await unusual.is_visible(timeout=2000):
                await unusual.fill(username)
                await page.click('span:has-text("Next")')
                await page.wait_for_timeout(2000)
        except Exception:
            pass

        # Step 3: Enter password
        password_input = page.locator('input[autocomplete="current-password"]')
        await password_input.fill(password)
        await page.click('span:has-text("Log in")')
        await page.wait_for_timeout(3000)

        # Step 4: Check for 2FA
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

        # Check if login succeeded
        await page.wait_for_url("**/home", timeout=15000)

        # Extract user info
        cookies = await context.cookies()

        # Get username from page
        x_username = None
        try:
            profile_link = page.locator('a[data-testid="AppTabBar_Profile_Link"]')
            href = await profile_link.get_attribute("href")
            if href:
                x_username = href.strip("/").split("/")[-1]
        except Exception:
            pass

        # Get user ID from cookies or page
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
    """Check if cookies are still valid and return user info."""
    pm = PlaywrightManager.get_instance()
    context = await pm.new_context(cookies)
    page = await context.new_page()

    try:
        await page.goto("https://x.com/home", wait_until="networkidle", timeout=30000)

        # Get username
        x_username = None
        try:
            profile_link = page.locator('a[data-testid="AppTabBar_Profile_Link"]')
            href = await profile_link.get_attribute("href")
            if href:
                x_username = href.strip("/").split("/")[-1]
        except Exception:
            pass

        # Get user ID
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
```

## 5. x_browser/client.py (NEW FILE)

```python
import json
import logging
import re
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

            # Type the tweet text
            tweet_input = page.locator('div[data-testid="tweetTextarea_0"]')
            await tweet_input.click()
            await page.wait_for_timeout(500)
            await tweet_input.fill(text)

            # Upload media if provided
            if media_path:
                file_input = page.locator('input[data-testid="fileInput"]')
                if await file_input.is_visible(timeout=5000):
                    await file_input.set_input_files(media_path)
                    await page.wait_for_timeout(3000)

            # Click Tweet button
            tweet_button = page.locator('button[data-testid="tweetButton"]')
            await tweet_button.click()

            # Wait for post to complete and get tweet URL
            await page.wait_for_timeout(3000)
            
            tweet_url = None
            try:
                # The page navigates to the tweet after posting
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

            # Click the ... (more) button
            more_button = page.locator('button[data-testid="caret"]')
            await more_button.click()
            await page.wait_for_timeout(1000)

            # Click Delete
            delete_button = page.locator('span:has-text("Delete")')
            await delete_button.click()
            await page.wait_for_timeout(1000)

            # Confirm deletion
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
```

## 6. x_browser/media.py (NEW FILE)

```python
import logging
from typing import Optional

from x_browser.browser import PlaywrightManager

logger = logging.getLogger(__name__)


async def upload_media(cookies: list, file_path: str) -> Optional[str]:
    """
    Upload media via X web interface. Returns media_id if successful.
    """
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

        # Get media ID from the preview
        media_id = None
        try:
            media_preview = page.locator('div[data-testid="attachment"]')
            preview_html = await media_preview.get_attribute("outerHTML")
            # Extract media_id from HTML
            import re
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
```

## 7. x_browser/session_keeper.py (NEW FILE)

```python
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from x_browser.browser import PlaywrightManager

logger = logging.getLogger(__name__)


class SessionKeeper:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    async def refresh_all_sessions(self):
        pm = PlaywrightManager.get_instance()
        session = self._session_factory()
        async with session:
            from db.repository import UserRepository
            repo = UserRepository(session)
            users = await repo.get_all()
            for user in users:
                if not user.cookies_data:
                    continue
                try:
                    import json
                    from utils import decrypt_token
                    cookies_str = decrypt_token(user.cookies_data, None)  # Will fix key
                    # ...
                except Exception as e:
                    logger.warning(f"Session refresh failed for user {user.id}: {e}")
```

## 8. db/models.py - Update User model

Change:
```python
# BEFORE:
oauth_token = Column(Text, default="", nullable=False)
oauth_refresh_token = Column(Text, default="", nullable=False)
token_expires_at = Column(DateTime, nullable=True)

# AFTER:
cookies_data = Column(Text, default="", nullable=False)
needs_login = Column(Boolean, default=False)
```

## 9. bot/states.py

Change:
```python
# BEFORE:
AWAITING_OAUTH_CODE = 3

# AFTER:
AWAITING_CREDENTIALS = 3  # replaces AWAITING_OAUTH_CODE
```

## 10. bot/handlers.py - Major changes

### login_button() - Change to ask for credentials:
```python
async def login_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🔐 *تسجيل الدخول إلى X*\n\n"
        "أرسل **اسم المستخدم** و **كلمة السر** لحساب X بالصيغة التالية:\n"
        "`username:password`\n\n"
        "🔒 كلمة السر لن تُخزَّن، سنستخدم الكوكيز فقط.\n"
        "⚠️ إذا فعّلت المصادقة الثنائية (2FA)، سيُطلب منك الرمز لاحقاً.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ إلغاء", callback_data="cancel")],
        ]),
    )
    return AWAITING_CREDENTIALS
```

### receive_credentials() - New function:
```python
async def receive_credentials(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if ":" not in text:
        await update.message.reply_text("❌ الصيغة خطأ. أرسل `username:password`")
        return AWAITING_CREDENTIALS

    username, password = text.split(":", 1)
    await update.message.reply_text("🔄 جاري تسجيل الدخول إلى X...")

    async def on_2fa():
        await update.message.reply_text(
            "📱 رمز التحقق الثنائي (2FA) مطلوب.\n"
            "أرسل الرمز المستلم على بريدك الإلكتروني أو تطبيق المصادقة."
        )
        # Wait for user to send 2FA code
        return await wait_for_2fa(context, update.effective_user.id)

    x_user_id, x_username, cookies = await login_with_credentials(
        username, password, on_2fa
    )
    if not x_username:
        await update.message.reply_text("❌ فشل تسجيل الدخول. تأكد من البيانات وحاول مرة أخرى.")
        return AWAITING_LOGIN

    # Save cookies to DB
    import json
    from utils import encrypt_token
    from config import FERNET_KEY
    encrypted_cookies = encrypt_token(json.dumps(cookies), FERNET_KEY)

    telegram_id = update.effective_user.id
    session = async_session_factory()
    async with session:
        repo = UserRepository(session)
        existing = await repo.get_by_telegram_id(telegram_id)
        if existing:
            await repo.update(existing, cookies_data=encrypted_cookies,
                              x_user_id=x_user_id, x_username=x_username)
        else:
            await repo.create(telegram_id=telegram_id, x_user_id=x_user_id,
                             x_username=x_username, cookies_data=encrypted_cookies)

    await update.message.reply_text(
        f"✅ *تم تسجيل الدخول بنجاح!*\n\nمرحباً @{x_username} 🎉\n"
        "يمكنك الآن البدء بالنشر.",
        reply_markup=main_menu_keyboard(),
    )
    return MAIN_MENU
```

### confirm_publish() - Use XBrowserClient:
```python
# In confirm_publish, replace:
if user.oauth_token:
    bearer_token = decrypt_token(user.oauth_token, FERNET_KEY)
    client = XAPIClient(bearer_token)
else:
    access_token = decrypt_token(user.access_token, FERNET_KEY)
    access_token_secret = decrypt_token(user.access_token_secret, FERNET_KEY)
    client = XAPIClient(access_token, access_token_secret)

# With:
import json
from x_browser.client import XBrowserClient
cookies = json.loads(decrypt_token(user.cookies_data, FERNET_KEY))
client = XBrowserClient(cookies)
```

### delete_post_by_id() - Same change as confirm_publish.

## 11. scheduler/sweeper.py and reproductions.py

Replace `XAPIClient` with `XBrowserClient` using cookies from DB.

## 12. Commit & Deploy

```bash
git add .
git commit -m "feat: migrate from X API to Playwright browser automation"
git push
# Then Manual Deploy on Render
```
