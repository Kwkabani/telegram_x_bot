import enum
from datetime import datetime
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, DateTime,
    Boolean, ForeignKey, Enum as SAEnum, JSON, UniqueConstraint
)
from sqlalchemy.orm import relationship
from db.base import Base


class PostStatus(str, enum.Enum):
    PENDING = "pending"
    PUBLISHED = "published"
    DELETED = "deleted"
    FAILED = "failed"


class MediaStatus(str, enum.Enum):
    DOWNLOADING = "downloading"
    UPLOADING = "uploading"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    x_user_id = Column(String, nullable=True)
    x_username = Column(String, nullable=True)
    access_token = Column(Text, nullable=True)
    access_token_secret = Column(Text, nullable=True)
    oauth_token = Column(Text, nullable=True)
    oauth_refresh_token = Column(Text, nullable=True)
    token_expires_at = Column(DateTime, nullable=True)
    default_delete_minutes = Column(Integer, default=0)
    default_repeat_count = Column(Integer, default=1)
    cooldown_minutes = Column(Integer, default=0)
    banned = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    posts = relationship("Post", back_populates="user", cascade="all, delete-orphan")
    temp_media = relationship("TempMedia", back_populates="user", cascade="all, delete-orphan")


class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    tweet_id = Column(String, nullable=True)
    content = Column(Text, nullable=False)
    variation_content = Column(Text, nullable=True)
    media_path = Column(String, nullable=True)
    media_id = Column(String, nullable=True)
    repeat_count = Column(Integer, default=1)
    repeat_interval = Column(Integer, default=5)
    remaining_repeats = Column(Integer, default=0)
    delete_after_minutes = Column(Integer, nullable=False)
    published_at = Column(DateTime, nullable=True)
    delete_at = Column(DateTime, nullable=True)
    status = Column(SAEnum(PostStatus), default=PostStatus.PENDING, index=True)
    attempts = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="posts")


class TempMedia(Base):
    __tablename__ = "temp_media"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    file_path = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    file_size = Column(Integer, default=0)
    x_media_id = Column(String, nullable=True)
    status = Column(SAEnum(MediaStatus), default=MediaStatus.DOWNLOADING)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="temp_media")


class BotConfig(Base):
    """Key-value store for bot messages, settings, and feature toggles."""
    __tablename__ = "bot_config"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow)
