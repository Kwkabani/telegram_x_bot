import logging
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import select, update, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import User, Post, PostStatus, TempMedia, MediaStatus

logger = logging.getLogger(__name__)


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> Optional[User]:
        result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_all(self) -> list[User]:
        result = await self.session.execute(select(User))
        return list(result.scalars().all())

    async def create(self, telegram_id: int, **kwargs) -> User:
        user = User(telegram_id=telegram_id, **kwargs)
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def update(self, user: User, **kwargs) -> User:
        for key, value in kwargs.items():
            if value is not None:
                setattr(user, key, value)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def delete(self, user: User) -> None:
        await self.session.delete(user)
        await self.session.commit()


class PostRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, **kwargs) -> Post:
        post = Post(**kwargs)
        self.session.add(post)
        await self.session.commit()
        await self.session.refresh(post)
        return post

    async def get_by_id(self, post_id: int) -> Optional[Post]:
        result = await self.session.execute(
            select(Post).where(Post.id == post_id)
        )
        return result.scalar_one_or_none()

    async def get_active_by_user(self, user_id: int, limit: int = 10) -> list[Post]:
        result = await self.session.execute(
            select(Post)
            .where(
                Post.user_id == user_id,
                Post.status.in_([PostStatus.PUBLISHED, PostStatus.PENDING])
            )
            .order_by(Post.published_at.desc().nullslast())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_active(self, user_id: int) -> int:
        result = await self.session.execute(
            select(func.count(Post.id))
            .where(
                Post.user_id == user_id,
                Post.status == PostStatus.PUBLISHED
            )
        )
        return result.scalar() or 0

    async def count_recent(self, user_id: int, minutes: int = 60) -> int:
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        result = await self.session.execute(
            select(func.count(Post.id))
            .where(
                Post.user_id == user_id,
                Post.published_at >= cutoff
            )
        )
        return result.scalar() or 0

    async def get_expired_published(self) -> list[Post]:
        now = datetime.utcnow()
        result = await self.session.execute(
            select(Post)
            .where(
                Post.status == PostStatus.PUBLISHED,
                Post.delete_at <= now
            )
        )
        return list(result.scalars().all())

    async def get_pending_repeats(self) -> list[Post]:
        result = await self.session.execute(
            select(Post)
            .where(
                Post.status == PostStatus.PUBLISHED,
                Post.remaining_repeats > 0,
                Post.published_at.isnot(None)
            )
        )
        return list(result.scalars().all())

    async def update_status(
        self, post_id: int, status: PostStatus,
        tweet_id: str = None, error_message: str = None
    ) -> None:
        values = {"status": status}
        if tweet_id is not None:
            values["tweet_id"] = tweet_id
        if error_message is not None:
            values["error_message"] = error_message
        await self.session.execute(
            update(Post).where(Post.id == post_id).values(**values)
        )
        await self.session.commit()

    async def decrement_repeats(self, post_id: int) -> None:
        post = await self.get_by_id(post_id)
        if post and post.remaining_repeats > 0:
            post.remaining_repeats -= 1
            await self.session.commit()

    async def increment_attempts(self, post_id: int) -> None:
        post = await self.get_by_id(post_id)
        if post:
            post.attempts += 1
            await self.session.commit()

    async def get_oldest_active(self, user_id: int) -> Optional[Post]:
        result = await self.session.execute(
            select(Post)
            .where(
                Post.user_id == user_id,
                Post.status == PostStatus.PUBLISHED
            )
            .order_by(Post.delete_at.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_oldest_recent(self, user_id: int, minutes: int = 60) -> Optional[Post]:
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        result = await self.session.execute(
            select(Post)
            .where(
                Post.user_id == user_id,
                Post.published_at >= cutoff
            )
            .order_by(Post.published_at.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def delete(self, post_id: int) -> None:
        await self.session.execute(
            update(Post).where(Post.id == post_id).values(status=PostStatus.DELETED)
        )
        await self.session.commit()


class MediaRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, **kwargs) -> TempMedia:
        media = TempMedia(**kwargs)
        self.session.add(media)
        await self.session.commit()
        await self.session.refresh(media)
        return media

    async def update(self, media: TempMedia, **kwargs) -> TempMedia:
        for key, value in kwargs.items():
            if value is not None:
                setattr(media, key, value)
        await self.session.commit()
        return media

    async def get_old_unprocessed(self, hours: int = 1) -> list[TempMedia]:
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        result = await self.session.execute(
            select(TempMedia)
            .where(
                TempMedia.status.in_([
                    MediaStatus.DOWNLOADING,
                    MediaStatus.UPLOADING,
                    MediaStatus.PROCESSING
                ]),
                TempMedia.created_at <= cutoff
            )
        )
        return list(result.scalars().all())
