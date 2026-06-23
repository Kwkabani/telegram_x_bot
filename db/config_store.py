import logging
from datetime import datetime
from sqlalchemy import select
from db.base import async_session_factory
from db.models import BotConfig

logger = logging.getLogger(__name__)

DEFAULT_MESSAGES: dict[str, str] = {
    "welcome_new": (
        "👋 *مرحباً بك في بوت النشر على X!*\n\n"
        "هذا البوت يتيح لك نشر منشورات على حسابك في X "
        "مع خاصية الحذف التلقائي بعد وقت محدد.\n\n"
        "*⚠️ تنبيه:*\n"
        "• نطبق حد 7 منشورات نشطة و 7 منشورات في الساعة لحماية حسابك.\n"
        "• أنت المسؤول الوحيد عن محتوى منشوراتك.\n\n"
        "للبدء، الرجاء تسجيل الدخول إلى حساب X:"
    ),
    "welcome_existing": (
        "👋 *مرحباً بك في بوت النشر على X!*\n\n"
        "حسابك مرتبط بمنصة X ✅\n"
        "يمكنك الآن نشر المنشورات وإدارتها."
    ),
    "ban_message": (
        "🚫 *حسابك محظور*\n\n"
        "عذراً، تم حظر حسابك من استخدام هذا البوت.\n"
        "للتواصل مع الدعم الفني، يرجى مراسلة المشرف."
    ),
    "bot_paused": (
        "🔧 *البوت متوقف مؤقتاً*\n\n"
        "يعود البوت للعمل قريباً. شكراً لصبرك."
    ),
}

DEFAULT_CONFIG: dict[str, str] = {
    "bot_paused": "false",
    "feature_repeats": "true",
    "feature_media": "true",
    "max_active_posts": "7",
    "max_posts_per_hour": "7",
}


async def get_config(key: str, fallback: str = "") -> str:
    async with async_session_factory() as session:
        result = await session.execute(
            select(BotConfig).where(BotConfig.key == key)
        )
        row = result.scalar_one_or_none()
    if row:
        return row.value
    return fallback


async def set_config(key: str, value: str) -> None:
    async with async_session_factory() as session:
        result = await session.execute(
            select(BotConfig).where(BotConfig.key == key)
        )
        row = result.scalar_one_or_none()
        if row:
            row.value = value
            row.updated_at = datetime.utcnow()
        else:
            session.add(BotConfig(key=key, value=value, updated_at=datetime.utcnow()))
        await session.commit()


async def get_message(key: str) -> str:
    val = await get_config("msg_" + key, "")
    if val:
        return val
    return DEFAULT_MESSAGES.get(key, "")


async def set_message(key: str, text: str) -> None:
    await set_config("msg_" + key, text)


async def is_bot_paused() -> bool:
    val = await get_config("bot_paused", "false")
    return val.lower() == "true"


async def set_bot_paused(paused: bool) -> None:
    await set_config("bot_paused", "true" if paused else "false")


async def get_all_messages() -> list[dict]:
    """Return all messages: defaults + overrides from DB merged."""
    result = []
    async with async_session_factory() as session:
        rows = (await session.execute(
            select(BotConfig).where(BotConfig.key.like("msg_%"))
        )).scalars().all()
        overrides = {r.key[4:]: r.value for r in rows}

    for key, default in DEFAULT_MESSAGES.items():
        result.append({
            "key": key,
            "default": default,
            "current": overrides.get(key, default),
            "is_overridden": key in overrides,
        })
    return result


async def get_bot_status() -> dict:
    """Return full bot status info."""
    import time
    paused = await is_bot_paused()
    return {
        "status": "paused" if paused else "online",
        "paused": paused,
        "uptime_seconds": int(time.time()),
    }
