#!/usr/bin/env python3
import asyncio
import logging
import os
import signal
import sys
import threading
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import error as telegram_error
from telegram.ext import Application, CommandHandler
from telegram.request import HTTPXRequest

from config import BOT_TOKEN, DASHBOARD_PORT, WEB_HOST, WEB_PORT, PROJECT_ROOT
from singleton import BotSingleton
from db.base import init_db, async_session_factory
from bot.handlers import get_conversation_handler, start, notify_admin
from scheduler.sweeper import PostSweeper
from scheduler.reproductions import ReproductionManager
from scheduler.health import HealthMonitor
from utils import setup_logging

logger = logging.getLogger(__name__)


async def post_init(application: Application) -> None:
    logger.info("Initializing bot...")
    try:
        await application.bot.delete_webhook(drop_pending_updates=True)
        logger.info("Cleared any existing webhook/polling connection")
    except Exception as e:
        logger.warning(f"Could not delete webhook: {e}")

    await init_db()
    logger.info("Database initialized")

    scheduler = AsyncIOScheduler()
    session_factory = async_session_factory
    sweeper = PostSweeper(session_factory)
    reproduction_mgr = ReproductionManager(session_factory)
    health_monitor = HealthMonitor(session_factory)

    scheduler.add_job(
        sweeper.sweep,
        "interval",
        seconds=60,
        id="delete_sweeper",
        name="Delete expired posts",
        misfire_grace_time=30,
        replace_existing=True,
    )
    scheduler.add_job(
        reproduction_mgr.process_repeats,
        "interval",
        seconds=30,
        id="repeat_checker",
        name="Check and process post repeats",
        misfire_grace_time=30,
        replace_existing=True,
    )
    scheduler.add_job(
        health_monitor.cleanup_temp_files,
        "interval",
        seconds=3600,
        id="temp_cleanup",
        name="Clean up temp files",
        misfire_grace_time=120,
        replace_existing=True,
    )
    scheduler.add_job(
        health_monitor.check_and_notify,
        "interval",
        hours=24,
        id="health_check",
        name="Daily health check",
        kwargs={"bot": application.bot},
        misfire_grace_time=3600,
        replace_existing=True,
    )

    scheduler.start()
    application.bot_data["scheduler"] = scheduler
    application.bot_data["sweeper"] = sweeper
    application.bot_data["reproduction_mgr"] = reproduction_mgr

    logger.info("Bot initialization complete")


async def post_shutdown(application: Application) -> None:
    logger.info("Shutting down bot...")
    scheduler = application.bot_data.get("scheduler")
    if scheduler:
        scheduler.shutdown(wait=False)
    logger.info("Bot shutdown complete")


async def conflict_handler(update, context):
    if isinstance(context.error, telegram_error.Conflict):
        logger.warning("Conflict 409 detected. Terminating old connection via delete_webhook...")
        try:
            await context.bot.delete_webhook(drop_pending_updates=True)
            logger.info("Old connection terminated. Restarting polling...")
        except Exception as e:
            logger.error(f"Failed to terminate old connection: {e}")


def main() -> None:
    if "--web" in sys.argv:
        return run_web_server_sync()

    setup_logging()
    logger.info("Starting Telegram X Bot...")

    render_port = os.environ.get("PORT")
    if render_port:
        logger.info(f"Render mode detected (PORT={render_port}), starting web server in background")
        thread = threading.Thread(
            target=run_web_server_sync,
            kwargs={"port": int(render_port)},
            daemon=True,
            name="web_render",
        )
        thread.start()

    request = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0,
        connection_pool_size=256,
    )
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .request(request)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    application.add_handler(get_conversation_handler())
    application.add_error_handler(conflict_handler)

    if "--dashboard" in sys.argv:
        start_dashboard_in_thread()

    application.run_polling(
        allowed_updates=["message", "callback_query"],
        bootstrap_retries=3,
        drop_pending_updates=True,
    )


def run_web_server_sync(port: int = None) -> None:
    import uvicorn
    from web.app import app

    host = WEB_HOST
    port = port or WEB_PORT
    logger.info(f"Starting web server on {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")


def start_dashboard_in_thread() -> None:
    import uvicorn
    from dashboard.app import app

    def _run():
        logger.info(f"Starting dashboard on 0.0.0.0:{DASHBOARD_PORT}")
        uvicorn.run(app, host="0.0.0.0", port=DASHBOARD_PORT, log_level="info")

    thread = threading.Thread(target=_run, daemon=True, name="dashboard")
    thread.start()
    logger.info("Dashboard thread started")


if __name__ == "__main__":
    with BotSingleton(BOT_TOKEN):
        try:
            main()
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
        except Exception as e:
            logger.critical(f"Fatal error: {e}", exc_info=True)
            sys.exit(1)
