import logging
import mimetypes
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

X_BEARER_TOKEN = (
    "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUyjRTSdBfJqdFpA0VSKhXQ%3D"
    "kIiTxRGKjNdFfBxSaQvHbiRjLfVnVdq7cS1LlZxY"
)


def _cookies_to_dict(cookies: list) -> dict:
    return {c["name"]: c["value"] for c in cookies}


def _csrf(cookies: list) -> str:
    for c in cookies:
        if c["name"] == "ct0":
            return c["value"]
    return ""


def _headers(cookies: list) -> dict:
    return {
        "authorization": X_BEARER_TOKEN,
        "x-csrf-token": _csrf(cookies),
        "origin": "https://x.com",
        "referer": "https://x.com/",
        "user-agent": USER_AGENT,
    }


async def upload_media_http(cookies: list, file_path: str) -> Optional[str]:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Media file not found: {file_path}")

    file_size = os.path.getsize(file_path)
    mime_type, _ = mimetypes.guess_type(file_path)
    mime_type = mime_type or "image/jpeg"
    is_video = mime_type.startswith("video/")
    media_category = "tweet_video" if is_video else "tweet_image"

    async with httpx.AsyncClient() as client:
        init_resp = await client.post(
            "https://upload.x.com/i/media/upload.json",
            params={"command": "INIT"},
            headers=_headers(cookies),
            json={
                "media_type": mime_type,
                "total_bytes": file_size,
                "media_category": media_category,
            },
            cookies=_cookies_to_dict(cookies),
            timeout=30,
        )
        init_resp.raise_for_status()
        init_data = init_resp.json()
        media_id = init_data.get("media_id_string")
        if not media_id:
            raise Exception(f"Failed to get media_id from INIT: {init_data}")

        with open(file_path, "rb") as f:
            append_resp = await client.post(
                "https://upload.x.com/i/media/upload.json",
                params={"command": "APPEND", "media_id": media_id, "segment_index": 0},
                headers={**_headers(cookies), "content-type": "application/octet-stream"},
                content=f,
                cookies=_cookies_to_dict(cookies),
                timeout=60,
            )
        append_resp.raise_for_status()

        finalize_resp = await client.post(
            "https://upload.x.com/i/media/upload.json",
            params={"command": "FINALIZE", "media_id": media_id},
            headers=_headers(cookies),
            cookies=_cookies_to_dict(cookies),
            timeout=30,
        )
        finalize_resp.raise_for_status()
        finalize_data = finalize_resp.json()

        media_id_string = finalize_data.get("media_id_string", media_id)
        logger.info(f"Media uploaded via HTTP: {media_id_string}")
        return media_id_string
