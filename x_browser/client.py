import logging
from typing import Optional

from x_browser.http_client import XHTTPClient

logger = logging.getLogger(__name__)


class XBrowserClient:
    def __init__(self, cookies: list):
        self._http = XHTTPClient(cookies)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self._http.close()

    async def post_tweet(self, text: str, media_path: Optional[str] = None) -> str:
        return await self._http.post_tweet(text, media_path)

    async def delete_tweet(self, tweet_id: str) -> bool:
        return await self._http.delete_tweet(tweet_id)
