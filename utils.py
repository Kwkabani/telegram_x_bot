import logging
import os
import asyncio
from pathlib import Path
from logging.handlers import RotatingFileHandler
from cryptography.fernet import Fernet


def setup_logging() -> None:
    logs_dir = Path(__file__).parent / "logs"
    logs_dir.mkdir(exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    file_handler = RotatingFileHandler(
        str(logs_dir / "bot.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    ))
    root_logger.addHandler(file_handler)

    is_render = os.environ.get("RENDER", "") == "true" or os.environ.get("PORT", "")
    if not is_render:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(
            "%(levelname)s: %(message)s"
        ))
        root_logger.addHandler(console_handler)


def encrypt_token(token: str, key: str) -> str:
    if not token:
        return ""
    f = Fernet(key.encode())
    return f.encrypt(token.encode()).decode()


def decrypt_token(encrypted: str, key: str) -> str:
    if not encrypted:
        return ""
    f = Fernet(key.encode())
    return f.decrypt(encrypted.encode()).decode()


async def run_sync(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)
