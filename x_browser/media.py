import logging
from typing import Optional

from x_browser.http_media import upload_media_http

logger = logging.getLogger(__name__)


async def upload_media(cookies: list, file_path: str) -> Optional[str]:
    return await upload_media_http(cookies, file_path)
