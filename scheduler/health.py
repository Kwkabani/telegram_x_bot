import logging
import os
import shutil
from datetime import datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from db.repository import UserRepository, PostRepository
from db.models import PostStatus, MediaStatus
from config import ADMIN_TELEGRAM_ID, PROJECT_ROOT

logger = logging.getLogger(__name__)


class HealthMonitor:
    """Monitors bot health and notifies admin of critical issues."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory

    async def check_and_notify(self, bot=None) -> list[str]:
        issues = []

        async with self.session_factory() as session:
            user_repo = UserRepository(session)
            post_repo = PostRepository(session)

            # Check for stuck posts (failed too many times)
            stuck_posts = await self._get_stuck_posts(session)
            if stuck_posts:
                msg = f"⚠️ {len(stuck_posts)} posts stuck in failed state"
                issues.append(msg)
                logger.warning(msg)

            # Check database file size
            db_path = PROJECT_ROOT / "data" / "bot.db"
            if db_path.exists():
                size_mb = db_path.stat().st_size / (1024 * 1024)
                if size_mb > 100:
                    msg = f"⚠️ Database file is {size_mb:.1f} MB, consider cleanup"
                    issues.append(msg)
                    logger.warning(msg)

            # Check temp directory
            temp_path = PROJECT_ROOT / "temp"
            if temp_path.exists():
                total_size = sum(
                    f.stat().st_size for f in temp_path.rglob("*") if f.is_file()
                )
                total_mb = total_size / (1024 * 1024)
                if total_mb > 500:
                    msg = f"⚠️ Temp directory is {total_mb:.1f} MB, consider cleanup"
                    issues.append(msg)
                    logger.warning(msg)

        if issues and bot and ADMIN_TELEGRAM_ID:
            try:
                await bot.send_message(
                    chat_id=ADMIN_TELEGRAM_ID,
                    text="🔍 *تقرير الصحة اليومي*\n\n" + "\n".join(issues),
                )
            except Exception as e:
                logger.error(f"Failed to notify admin: {e}")

        return issues

    async def _get_stuck_posts(self, session) -> list:
        from sqlalchemy import select
        from db.models import Post
        result = await session.execute(
            select(Post).where(
                Post.status.in_([PostStatus.FAILED]),
                Post.attempts >= 5,
            ).limit(20)
        )
        return list(result.scalars().all())

    async def cleanup_temp_files(self) -> int:
        """Remove temp files older than 1 hour."""
        temp_path = PROJECT_ROOT / "temp"
        if not temp_path.exists():
            return 0

        count = 0
        now = datetime.now()
        for f in temp_path.iterdir():
            if f.is_file():
                mtime = datetime.fromtimestamp(f.stat().st_mtime)
                if (now - mtime).total_seconds() > 3600:
                    f.unlink()
                    count += 1
        if count:
            logger.info(f"Cleaned up {count} temp files")
        return count
