import asyncio
import logging
from typing import Optional

import tweepy

from config import X_API_KEY, X_API_SECRET
from utils import run_sync

logger = logging.getLogger(__name__)


class XAPIClient:
    def __init__(self, access_token: str, access_token_secret: Optional[str] = None):
        self._at = access_token
        self._ats = access_token_secret
        self._is_oauth2 = access_token_secret is None

    async def post_tweet(self, text: str, media_path: Optional[str] = None) -> str:
        return await run_sync(self._sync_post, text, media_path)

    def _sync_post(self, text: str, media_path: Optional[str] = None) -> str:
        if self._is_oauth2:
            client = tweepy.Client(bearer_token=self._at)
            tweet = client.create_tweet(text=text, user_auth=False)
            tweet_id = tweet.data["id"]
            logger.info(f"Tweet posted (OAuth2): {tweet_id}")
            return tweet_id
        else:
            client = tweepy.Client(
                consumer_key=X_API_KEY,
                consumer_secret=X_API_SECRET,
                access_token=self._at,
                access_token_secret=self._ats,
            )
            media_ids = []
            if media_path:
                auth = tweepy.OAuth1UserHandler(
                    X_API_KEY, X_API_SECRET, self._at, self._ats
                )
                api = tweepy.API(auth)
                media = api.media_upload(filename=media_path)
                media_ids = [media.media_id]
                logger.info(f"Media uploaded: {media.media_id}")

            tweet = client.create_tweet(text=text, media_ids=media_ids or None)
            tweet_id = tweet.data["id"]
            logger.info(f"Tweet posted (OAuth1): {tweet_id}")
            return tweet_id

    async def delete_tweet(self, tweet_id: str) -> bool:
        return await run_sync(self._sync_delete, tweet_id)

    def _sync_delete(self, tweet_id: str) -> bool:
        if self._is_oauth2:
            client = tweepy.Client(bearer_token=self._at)
            client.delete_tweet(tweet_id, user_auth=False)
            logger.info(f"Tweet deleted (OAuth2): {tweet_id}")
            return True
        else:
            client = tweepy.Client(
                consumer_key=X_API_KEY,
                consumer_secret=X_API_SECRET,
                access_token=self._at,
                access_token_secret=self._ats,
            )
        client.delete_tweet(tweet_id)
        logger.info(f"Tweet deleted: {tweet_id}")
        return True


class XAPIError(Exception):
    pass
