import json
import logging
import random
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sqlalchemy import update as sql_update

from db.repository import PostRepository, UserRepository
from db.models import Post, PostStatus
from x_browser.client import XBrowserClient
from x_api.rate_limiter import RateLimiter
from config import FERNET_KEY, DEFAULT_REPEAT_INTERVAL, MAX_CONTENT_LENGTH
from utils import decrypt_token

logger = logging.getLogger(__name__)

PREFIXES = ["", "— ", "⚡ ", "🔄 ", "💬 ", ""]
SUFFIXES = [
    "\n\n({i}/{total})",
    "\n\n— متابعة ({i}/{total})",
    "\n\n⬇️ الجزء {i}",
    "\n\n▪️ ({i}/{total})",
    "\n\n⏩ ({i}/{total})",
]


class ReproductionManager:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory

    async def process_repeats(self) -> int:
        published_count = 0
        async with self.session_factory() as session:
            post_repo = PostRepository(session)
            user_repo = UserRepository(session)

            posts_to_repeat = await post_repo.get_pending_repeats()
            now = datetime.utcnow()

            for post in posts_to_repeat:
                if not post.published_at:
                    continue

                elapsed = (now - post.published_at).total_seconds() / 60
                interval = post.repeat_interval or DEFAULT_REPEAT_INTERVAL

                if elapsed < interval:
                    continue

                try:
                    user = await user_repo.get_by_id(post.user_id)
                    if not user or not user.cookies_data:
                        continue

                    limiter = RateLimiter(post_repo)
                    check = await limiter.can_publish(user.id)
                    if not check.allowed:
                        logger.info(
                            f"Skipping repeat for post {post.id}: {check.message}"
                        )
                        continue

                    repeats_so_far = post.repeat_count - post.remaining_repeats
                    total = post.repeat_count
                    variation = self._generate_variation(
                        post.content, repeats_so_far + 1, total
                    )

                    cookies = json.loads(decrypt_token(user.cookies_data, FERNET_KEY))
                    async with XBrowserClient(cookies) as client:
                        media_path = post.media_path if post.media_path else None
                        tweet_id = await client.post_tweet(variation, media_path)

                    stmt = (
                        sql_update(Post)
                        .where(Post.id == post.id, Post.remaining_repeats > 0)
                        .values(
                            remaining_repeats=Post.remaining_repeats - 1,
                            published_at=now,
                            delete_at=now + timedelta(minutes=post.delete_after_minutes),
                            variation_content=variation,
                            tweet_id=tweet_id,
                        )
                    )
                    result = await session.execute(stmt)
                    await session.commit()

                    if result.rowcount > 0:
                        published_count += 1
                        logger.info(
                            f"Repeated post {post.id} for user {user.id} "
                            f"(repeat {repeats_so_far + 1}/{total})"
                        )

                except Exception as e:
                    logger.error(f"Error repeating post {post.id}: {e}")
                    try:
                        stmt = (
                            sql_update(Post)
                            .where(Post.id == post.id, Post.remaining_repeats > 0)
                            .values(
                                remaining_repeats=Post.remaining_repeats - 1,
                                attempts=Post.attempts + 1,
                            )
                        )
                        await session.execute(stmt)
                        await session.commit()
                    except Exception:
                        pass

        return published_count

    def _generate_variation(
        self, original_text: str, current: int, total: int
    ) -> str:
        prefix = random.choice(PREFIXES)
        suffix = random.choice(SUFFIXES).format(i=current, total=total)

        combined = prefix + original_text.rstrip()
        max_body_len = MAX_CONTENT_LENGTH - len(suffix) - 1

        if len(combined) > max_body_len:
            combined = combined[:max_body_len].rsplit(" ", 1)[0]

        return combined + suffix
