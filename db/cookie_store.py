import json
import logging
import os
from pathlib import Path

from config import COOKIES_DIR, FERNET_KEY
from utils import encrypt_token, decrypt_token

logger = logging.getLogger(__name__)

COOKIES_DIR_PATH = Path(COOKIES_DIR)


def _get_path(user_id: int) -> str:
    COOKIES_DIR_PATH.mkdir(parents=True, exist_ok=True)
    return str(COOKIES_DIR_PATH / f"{user_id}.json")


async def save_cookies(user_id: int, cookies_data: list | str | None) -> None:
    if cookies_data is None:
        return
    if isinstance(cookies_data, str):
        cookies_list = json.loads(decrypt_token(cookies_data, FERNET_KEY)) if cookies_data else None
        if not cookies_list:
            return
    elif isinstance(cookies_data, list):
        cookies_list = cookies_data
    else:
        return
    encrypted = encrypt_token(json.dumps(cookies_list), FERNET_KEY)
    path = _get_path(user_id)
    with open(path, "w", encoding="utf-8") as f:
        f.write(encrypted)
    logger.info(f"Cookies saved for user {user_id}")


async def load_cookies(user_id: int) -> list | None:
    path = _get_path(user_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            encrypted = f.read().strip()
        if not encrypted:
            return None
        decrypted = decrypt_token(encrypted, FERNET_KEY)
        return json.loads(decrypted)
    except Exception as e:
        logger.warning(f"Failed to load cookies for user {user_id}: {e}")
        return None


async def delete_cookies(user_id: int) -> None:
    path = _get_path(user_id)
    if os.path.exists(path):
        os.remove(path)
        logger.info(f"Cookies deleted for user {user_id}")
