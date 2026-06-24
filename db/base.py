import logging
import os
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from config import DATABASE_URL, DB_FULL_PATH

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)


async def enable_wal() -> None:
    async with engine.connect() as conn:
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.execute(text("PRAGMA busy_timeout=5000"))
        await conn.commit()

async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _migrate_banned_column() -> None:
    """Add banned column to users table if it doesn't exist."""
    async with engine.connect() as conn:
        result = await conn.execute(text("PRAGMA table_info(users)"))
        columns = [row[1] for row in result]
        if "banned" not in columns:
            await conn.execute(text("ALTER TABLE users ADD COLUMN banned BOOLEAN DEFAULT 0"))
            await conn.commit()
            logger.info("Added 'banned' column to users table")


async def _migrate_oauth2_columns() -> None:
    """Add OAuth 2.0 columns to users table if they don't exist."""
    async with engine.connect() as conn:
        result = await conn.execute(text("PRAGMA table_info(users)"))
        columns = [row[1] for row in result]
        if "oauth_token" not in columns:
            await conn.execute(text("ALTER TABLE users ADD COLUMN oauth_token TEXT"))
            logger.info("Added 'oauth_token' column to users table")
        if "oauth_refresh_token" not in columns:
            await conn.execute(text("ALTER TABLE users ADD COLUMN oauth_refresh_token TEXT"))
            logger.info("Added 'oauth_refresh_token' column to users table")
        if "token_expires_at" not in columns:
            await conn.execute(text("ALTER TABLE users ADD COLUMN token_expires_at DATETIME"))
            logger.info("Added 'token_expires_at' column to users table")
        await conn.commit()


async def _migrate_cookies_column() -> None:
    async with engine.connect() as conn:
        result = await conn.execute(text("PRAGMA table_info(users)"))
        columns = [row[1] for row in result]
        if "cookies_data" not in columns:
            await conn.execute(text("ALTER TABLE users ADD COLUMN cookies_data TEXT"))
            logger.info("Added 'cookies_data' column to users table")
        await conn.commit()


async def _migrate_needs_login_column() -> None:
    async with engine.connect() as conn:
        result = await conn.execute(text("PRAGMA table_info(users)"))
        columns = [row[1] for row in result]
        if "needs_login" not in columns:
            await conn.execute(text("ALTER TABLE users ADD COLUMN needs_login BOOLEAN DEFAULT 0"))
            logger.info("Added 'needs_login' column to users table")
        await conn.commit()


async def init_db() -> None:
    from db.models import User, Post, TempMedia, BotConfig

    db_dir = Path(DB_FULL_PATH).parent
    db_dir.mkdir(parents=True, exist_ok=True)

    await enable_wal()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _migrate_banned_column()
    await _migrate_oauth2_columns()
    await _migrate_cookies_column()
    await _migrate_needs_login_column()
    logger.info("Database initialized")
