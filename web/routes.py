import logging
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
async def health_check():
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "3.0.0",
        "engine": "x_api",
    }


@router.get("/")
async def root():
    return {
        "message": "Telegram X Bot is running",
        "status": "active",
        "engine": "x_api",
        "auth": "cookies",
    }
