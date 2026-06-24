import logging
from typing import Optional

import httpx

from x_browser.http_media import upload_media_http

logger = logging.getLogger(__name__)

X_BEARER_TOKEN = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUyjRTSdBfJqdFpA0VSKhXQ%3D"
    "kIiTxRGKjNdFfBxSaQvHbiRjLfVnVdq7cS1LlZxY"
)

X_GRAPHQL_HASHES = {
    "CreateTweet": "SoVwUpLYRtBlVx8T7wOeXQ",
    "DeleteTweet": "VaenaVgh5q5M4fWZ89Jhxw",
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


class XHTTPClient:
    def __init__(self, cookies: list):
        self._cookies_list = cookies
        self._cookies_dict = {c["name"]: c["value"] for c in cookies}
        self._csrf_token = ""
        for c in cookies:
            if c["name"] == "ct0":
                self._csrf_token = c["value"]
                break

    def _headers(self) -> dict:
        return {
            "authorization": f"Bearer {X_BEARER_TOKEN}",
            "x-csrf-token": self._csrf_token,
            "content-type": "application/json",
            "origin": "https://x.com",
            "referer": "https://x.com/",
            "user-agent": USER_AGENT,
        }

    async def _graphql(self, operation: str, variables: dict) -> dict:
        query_id = X_GRAPHQL_HASHES[operation]
        url = f"https://x.com/i/api/graphql/{query_id}/{operation}"
        body = {"variables": variables, "queryId": query_id}

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                headers=self._headers(),
                json=body,
                cookies=self._cookies_dict,
                timeout=30,
            )
            if resp.status_code == 403:
                logger.warning(f"GraphQL {operation} returned 403, hash may be stale")
            resp.raise_for_status()
            data = resp.json()
            if data.get("errors"):
                raise Exception(f"GraphQL error: {data['errors']}")
            return data

    async def post_tweet(self, text: str, media_path: Optional[str] = None) -> str:
        media_id = None
        if media_path:
            media_id = await upload_media_http(self._cookies_list, media_path)

        variables = {
            "tweet_text": text,
            "dark_request": False,
            "media": {
                "media_entities": (
                    [{"media_id": media_id, "tagged_users": []}] if media_id
                    else []
                ),
                "possibly_sensitive": False,
            },
            "semantic_annotation_ids": [],
        }

        data = await self._graphql("CreateTweet", variables)
        result = data.get("data", {}).get("create_tweet", {})
        tweet_id = (
            result.get("tweet_results", {})
            .get("result", {})
            .get("rest_id")
        )
        if not tweet_id:
            raise Exception(f"Failed to extract tweet_id from response: {data}")
        logger.info(f"Tweet posted via HTTP: {tweet_id}")
        return tweet_id

    async def delete_tweet(self, tweet_id: str) -> bool:
        variables = {"tweet_id": tweet_id, "dark_request": False}
        data = await self._graphql("DeleteTweet", variables)
        result = (
            data.get("data", {})
            .get("delete_tweet", {})
            .get("tweet_results", {})
            .get("result", {})
        )
        success = result.get("rest_id") == tweet_id
        if success:
            logger.info(f"Tweet deleted via HTTP: {tweet_id}")
        return success
