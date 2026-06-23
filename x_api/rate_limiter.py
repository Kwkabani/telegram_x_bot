import logging
from datetime import datetime, timedelta
from typing import Tuple, Optional

from config import MAX_ACTIVE_POSTS, MAX_POSTS_PER_HOUR
from db.repository import PostRepository

logger = logging.getLogger(__name__)


class RateLimitResult:
    def __init__(self, allowed: bool, message: str = ""):
        self.allowed = allowed
        self.message = message


class RateLimiter:
    def __init__(self, post_repo: PostRepository):
        self.post_repo = post_repo

    async def can_publish(self, user_id: int) -> RateLimitResult:
        active_count = await self.post_repo.count_active(user_id)
        if active_count >= MAX_ACTIVE_POSTS:
            oldest = await self.post_repo.get_oldest_active(user_id)
            if oldest and oldest.delete_at:
                remaining = (oldest.delete_at - datetime.utcnow()).seconds // 60
                msg = (
                    f"❌ لديك {MAX_ACTIVE_POSTS} منشورات نشطة حالياً.\n"
                    f"⏳ أقدم منشور سيُحذف بعد {remaining} دقيقة، انتظر ثم حاول مجدداً."
                )
            else:
                msg = (
                    f"❌ لديك {MAX_ACTIVE_POSTS} منشورات نشطة حالياً.\n"
                    f"احذف أحد المنشورات يدوياً ثم حاول مجدداً."
                )
            return RateLimitResult(False, msg)

        recent_count = await self.post_repo.count_recent(user_id, 60)
        if recent_count >= MAX_POSTS_PER_HOUR:
            oldest = await self.post_repo.get_oldest_recent(user_id, 60)
            if oldest and oldest.published_at:
                window_end = oldest.published_at + timedelta(hours=1)
                remaining = (window_end - datetime.utcnow()).seconds // 60
                msg = (
                    f"❌ تجاوزت حد {MAX_POSTS_PER_HOUR} منشورات في الساعة.\n"
                    f"⏳ انتظر {remaining} دقيقة حتى تفتح النافذة."
                )
            else:
                msg = (
                    f"❌ تجاوزت حد {MAX_POSTS_PER_HOUR} منشورات في الساعة.\n"
                    f"⏳ انتظر قليلاً ثم حاول مجدداً."
                )
            return RateLimitResult(False, msg)

        return RateLimitResult(True)

    async def can_repeat(self, user_id: int, repeat_count: int) -> RateLimitResult:
        projected_active = (await self.post_repo.count_active(user_id)) + repeat_count
        if projected_active > MAX_ACTIVE_POSTS:
            return RateLimitResult(
                False,
                f"❌ التكرار {repeat_count} مرات سيرفع المنشورات النشطة إلى "
                f"{projected_active}، وهذا يتجاوز الحد ({MAX_ACTIVE_POSTS})."
            )
        projected_recent = (await self.post_repo.count_recent(user_id, 60)) + repeat_count
        if projected_recent > MAX_POSTS_PER_HOUR:
            return RateLimitResult(
                False,
                f"❌ التكرار {repeat_count} مرات سيرفع منشورات الساعة إلى "
                f"{projected_recent}، وهذا يتجاوز الحد ({MAX_POSTS_PER_HOUR})."
            )
        return RateLimitResult(True)
