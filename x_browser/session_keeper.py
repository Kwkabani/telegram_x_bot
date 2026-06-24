import json
import logging

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker

from db.repository import UserRepository
from utils import decrypt_token

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


class SessionKeeper:
    def __init__(self, session_factory: async_sessionmaker, fernet_key: str):
        self._session_factory = session_factory
        self._fernet_key = fernet_key

    async def refresh_all_sessions(self):
        async with self._session_factory() as session:
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
                    cookies_dict = {c["name"]: c["value"] for c in cookies}
                    csrf = cookies_dict.get("ct0", "")

                    async with httpx.AsyncClient() as client:
                        resp = await client.get(
                            "https://x.com/home",
                            headers={
                                "authorization": (
                                    "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAA"
                                    "AnNwIzUyjRTSdBfJqdFpA0VSKhXQ%3D"
                                    "kIiTxRGKjNdFfBxSaQvHbiRjLfVnVdq7cS1LlZxY"
                                ),
                                "x-csrf-token": csrf,
                                "user-agent": USER_AGENT,
                            },
                            cookies=cookies_dict,
                            follow_redirects=False,
                            timeout=15,
                        )
                        if resp.status_code == 200:
                            logger.info(f"Session valid for user {user.id}")
                        else:
                            logger.warning(
                                f"Session expired for user {user.id} "
                                f"(status {resp.status_code})"
                            )
                            await repo.update(user, needs_login=True)
                except Exception as e:
                    logger.error(f"Session keeper error for user {user.id}: {e}")
