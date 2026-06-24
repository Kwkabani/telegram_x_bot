import json
import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from db.repository import PostRepository, UserRepository
from db.models import PostStatus
from x_browser.client import XBrowserClient
from utils import decrypt_token
from config import FERNET_KEY

logger = logging.getLogger(__name__)


class PostSweeper:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory

    async def sweep(self) -> int:
        deleted_count = 0
        async with self.session_factory() as session:
            repo = PostRepository(session)
            user_repo = UserRepository(session)
            expired_posts = await repo.get_expired_published()

            for post in expired_posts:
                try:
                    if not post.tweet_id:
                        await repo.update_status(
                            post.id, PostStatus.FAILED,
                            error_message="No tweet_id"
                        )
                        continue

                    user = await user_repo.get_by_id(post.user_id)
                    if not user:
                        logger.error(f"User not found for post {post.id}")
                        await repo.update_status(
                            post.id, PostStatus.FAILED,
                            error_message="User not found"
                        )
                        continue

                    if not user.cookies_data:
                        logger.error(f"No cookies for user {user.id}")
                        await repo.update_status(
                            post.id, PostStatus.FAILED,
                            error_message="No cookies"
                        )
                        continue

                    cookies = json.loads(decrypt_token(user.cookies_data, FERNET_KEY))
                    client = XBrowserClient(cookies)
                    success = await client.delete_tweet(post.tweet_id)

                    if success:
                        await repo.update_status(post.id, PostStatus.DELETED)
                        deleted_count += 1
                        logger.info(
                            f"Auto-deleted tweet {post.tweet_id} for user {user.id}"
                        )
                    else:
                        await repo.increment_attempts(post.id)
                        logger.warning(
                            f"Failed to delete tweet {post.tweet_id}, "
                            f"attempt {post.attempts + 1}"
                        )

                except Exception as e:
                    logger.error(f"Error sweeping post {post.id}: {e}")
                    await repo.increment_attempts(post.id)

            await session.commit()
        return deleted_count
