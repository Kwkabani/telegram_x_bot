import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Bot
BOT_TOKEN: str = os.environ["BOT_TOKEN"]

# X API (OAuth 1.0a)
X_API_KEY: str = os.environ["X_API_KEY"]
X_API_SECRET: str = os.environ["X_API_SECRET"]

# X API (OAuth 2.0 PKCE)
X_CLIENT_ID: str = os.environ.get("X_CLIENT_ID", "")
X_CLIENT_SECRET: str = os.environ.get("X_CLIENT_SECRET", "")
X_CALLBACK_URL: str = os.environ.get("X_CALLBACK_URL", "")

# Database
DATABASE_PATH: str = os.environ.get("DATABASE_PATH", "data/bot.db")
PROJECT_ROOT: Path = Path(__file__).parent
DB_FULL_PATH: str = str(PROJECT_ROOT / DATABASE_PATH)
DATABASE_URL: str = f"sqlite+aiosqlite:///{DB_FULL_PATH}"

# Encryption (for token storage)
FERNET_KEY: str = os.environ["FERNET_KEY"]

# Web
WEB_HOST: str = os.environ.get("WEB_HOST", "0.0.0.0")
WEB_PORT: int = int(os.environ.get("WEB_PORT", "8080"))

# Admin
ADMIN_TELEGRAM_ID: int = int(os.environ.get("ADMIN_TELEGRAM_ID", "0"))
ADMIN_PASSWORD: str = os.environ.get("ADMIN_PASSWORD", "admin123")

# Cookie storage
COOKIES_DIR: str = str(PROJECT_ROOT / "data" / "cookies")

# Mini App
MINI_APP_URL: str = "https://telegram-x-bot-1.onrender.com/mini_app"

# Rate limits
MAX_ACTIVE_POSTS: int = int(os.environ.get("MAX_ACTIVE_POSTS", "7"))
MAX_POSTS_PER_HOUR: int = int(os.environ.get("MAX_POSTS_PER_HOUR", "7"))

# Post defaults
MAX_REPEAT_COUNT: int = int(os.environ.get("MAX_REPEAT_COUNT", "3"))
MAX_CONTENT_LENGTH: int = int(os.environ.get("MAX_CONTENT_LENGTH", "280"))
MAX_IMAGE_SIZE_MB: int = int(os.environ.get("MAX_IMAGE_SIZE_MB", "5"))
MAX_VIDEO_SIZE_MB: int = int(os.environ.get("MAX_VIDEO_SIZE_MB", "15"))
DEFAULT_REPEAT_INTERVAL: int = int(os.environ.get("DEFAULT_REPEAT_INTERVAL", "60"))

# Scheduler
SWEEPER_INTERVAL_SECONDS: int = int(os.environ.get("SWEEPER_INTERVAL_SECONDS", "60"))
REPEAT_CHECK_INTERVAL_SECONDS: int = int(os.environ.get("REPEAT_CHECK_INTERVAL_SECONDS", "30"))
CLEANUP_INTERVAL_SECONDS: int = int(os.environ.get("CLEANUP_INTERVAL_SECONDS", "3600"))
