import json
import logging

from x_browser.browser import PlaywrightManager
from utils import encrypt_token, decrypt_token

logger = logging.getLogger(__name__)


class SessionKeeper:
    def __init__(self, session_factory, fernet_key: str):
        self._session_factory = session_factory
        self._fernet_key = fernet_key

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
                    cookies_str = decrypt_token(user.cookies_data, self._fernet_key)
                    if not cookies_str:
                        continue
                    cookies = json.loads(cookies_str)
                    context = await pm.new_context(cookies)
                    page = await context.new_page()
                    try:
                        await page.goto(
                            "https://x.com/home",
                            wait_until="networkidle",
                            timeout=30000,
                        )
                        updated_cookies = await context.cookies()
                        encrypted = encrypt_token(
                            json.dumps(updated_cookies), self._fernet_key
                        )
                        await repo.update(user, cookies_data=encrypted)
                        logger.info(f"Session refreshed for user {user.id}")
                    except Exception as e:
                        logger.warning(
                            f"Session expired for user {user.id}: {e}"
                        )
                        await repo.update(user, needs_login=True)
                    finally:
                        await pm.close_context(context)
                except Exception as e:
                    logger.error(
                        f"Session keeper error for user {user.id}: {e}"
                    )
