import logging

from fastapi import FastAPI
from web.routes import router

logger = logging.getLogger(__name__)

app = FastAPI(title="Telegram X Bot", version="1.0.0")
app.include_router(router)
