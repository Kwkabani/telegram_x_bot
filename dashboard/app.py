import hashlib
import logging
import secrets
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from config import ADMIN_PASSWORD, PROJECT_ROOT, DATABASE_URL
from db.models import User, Post, PostStatus
from db.repository import UserRepository, PostRepository
from db.config_store import (
    get_all_messages, get_message, set_message, get_config, set_config,
    is_bot_paused, set_bot_paused, DEFAULT_MESSAGES, DEFAULT_CONFIG,
)

_dashboard_engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
)
_dashboard_session_factory = async_sessionmaker(
    _dashboard_engine, class_=AsyncSession, expire_on_commit=False
)

_admin_password_hash = hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest()
_session_token = secrets.token_urlsafe(32)

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="X Bot Dashboard", version="3.1.0")

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

_jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
    auto_reload=False,
    cache_size=0,
)


def render(name: str, context: dict) -> HTMLResponse:
    context.setdefault("refresh_interval", "30")
    template = _jinja_env.get_template(name)
    html = template.render(context)
    return HTMLResponse(content=html)


# ─── Auth Middleware ────────────────────────────────────────────────


def require_auth(func):
    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        token = request.cookies.get("admin_token")
        if token != _session_token:
            return RedirectResponse(url="/login?next_url=" + request.url.path)
        return await func(request, *args, **kwargs)
    return wrapper


# ─── Health ─────────────────────────────────────────────────────────


@app.get("/health")
async def health():
    return {"status": "ok", "version": "3.1.0"}


# ─── Routes ─────────────────────────────────────────────────────────


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = "", next_url: str = "/"):
    return render(
        "login.html", {"request": request, "error": error, "next_url": next_url}
    )


@app.post("/login")
async def login_post(request: Request):
    form = await request.form()
    password = form.get("password", "")
    next_url = form.get("next_url", "/")
    if hashlib.sha256(password.encode()).hexdigest() == _admin_password_hash:
        resp = RedirectResponse(url=next_url, status_code=303)
        resp.set_cookie(key="admin_token", value=_session_token, httponly=True, max_age=86400)
        return resp
    return RedirectResponse(url=f"/login?error=wrong&next_url={next_url}", status_code=303)


@app.get("/logout")
async def logout():
    resp = RedirectResponse(url="/login")
    resp.delete_cookie("admin_token")
    return resp


# ─── Pages ──────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
@require_auth
async def overview(request: Request):
    async with _dashboard_session_factory() as session:
        total_users = (await session.execute(
            select(func.count(User.id))
        )).scalar() or 0

        connected_users = (await session.execute(
            select(func.count(User.id)).where(
                User.cookies_data.isnot(None), User.cookies_data != ""
            )
        )).scalar() or 0

        total_posts = (await session.execute(
            select(func.count(Post.id))
        )).scalar() or 0

        active_posts = (await session.execute(
            select(func.count(Post.id)).where(Post.status == PostStatus.PUBLISHED)
        )).scalar() or 0

        failed_posts = (await session.execute(
            select(func.count(Post.id)).where(Post.status == PostStatus.FAILED)
        )).scalar() or 0

        deleted_posts = (await session.execute(
            select(func.count(Post.id)).where(Post.status == PostStatus.DELETED)
        )).scalar() or 0

        recent_posts = (await session.execute(
            select(Post, User.x_username).join(User, Post.user_id == User.id)
            .order_by(Post.created_at.desc()).limit(5)
        )).all()

    return render("overview.html", {
        "request": request,
        "refresh_interval": "10",
        "total_users": total_users,
        "connected_users": connected_users,
        "total_posts": total_posts,
        "active_posts": active_posts,
        "failed_posts": failed_posts,
        "deleted_posts": deleted_posts,
        "recent_posts": recent_posts,
    })


@app.get("/users", response_class=HTMLResponse)
@require_auth
async def users_page(request: Request, search: str = ""):
    async with _dashboard_session_factory() as session:
        if search:
            from sqlalchemy import cast, String
            result = await session.execute(
                select(User).where(
                    User.x_username.ilike(f"%{search}%") |
                    cast(User.telegram_id, String).ilike(f"%{search}%")
                ).order_by(User.created_at.desc())
            )
        else:
            result = await session.execute(
                select(User).order_by(User.created_at.desc())
            )
        users = result.scalars().all()

        user_post_counts = {}
        for u in users:
            count = (await session.execute(
                select(func.count(Post.id)).where(Post.user_id == u.id)
            )).scalar() or 0
            user_post_counts[u.id] = count

    return render("users.html", {
        "request": request,
        "users": users,
        "user_post_counts": user_post_counts,
        "search": search,
    })


@app.post("/users/{user_id}/disconnect")
@require_auth
async def disconnect_user(request: Request, user_id: int):
    async with _dashboard_session_factory() as session:
        repo = UserRepository(session)
        user = await repo.get_by_id(user_id)
        if user:
            await repo.update(
                user,
                x_user_id=None, x_username=None,
                access_token="", access_token_secret="",
                cookies_data="",
                needs_login=True,
                default_delete_minutes=0, default_repeat_count=1, cooldown_minutes=0,
            )
    return RedirectResponse(url="/users", status_code=303)


@app.post("/users/{user_id}/delete")
@require_auth
async def delete_user(request: Request, user_id: int):
    async with _dashboard_session_factory() as session:
        repo = UserRepository(session)
        user = await repo.get_by_id(user_id)
        if user:
            await repo.delete(user)
    return RedirectResponse(url="/users", status_code=303)


@app.post("/users/{user_id}/ban")
@require_auth
async def ban_user(request: Request, user_id: int):
    async with _dashboard_session_factory() as session:
        repo = UserRepository(session)
        user = await repo.get_by_id(user_id)
        if user:
            await repo.update(user, banned=not user.banned)
    return RedirectResponse(url="/users", status_code=303)


@app.get("/posts", response_class=HTMLResponse)
@require_auth
async def posts_page(request: Request, status: str = "", user_id: int = 0):
    async with _dashboard_session_factory() as session:
        query = select(Post, User.x_username).join(User, Post.user_id == User.id)

        if status:
            query = query.where(Post.status == PostStatus(status))
        if user_id:
            query = query.where(Post.user_id == user_id)

        query = query.order_by(Post.created_at.desc()).limit(100)
        result = await session.execute(query)
        posts = result.all()

        total_posts = (await session.execute(
            select(func.count(Post.id))
        )).scalar() or 0

        active_posts = (await session.execute(
            select(func.count(Post.id)).where(Post.status == PostStatus.PUBLISHED)
        )).scalar() or 0

    return render("posts.html", {
        "request": request,
        "posts": posts,
        "total_posts": total_posts,
        "active_posts": active_posts,
        "status_filter": status,
    })


@app.post("/posts/{post_id}/delete")
@require_auth
async def delete_post(request: Request, post_id: int):
    async with _dashboard_session_factory() as session:
        post_repo = PostRepository(session)
        post = await post_repo.get_by_id(post_id)
        if post:
            await post_repo.delete(post_id)
    return RedirectResponse(url="/posts", status_code=303)


@app.get("/logs", response_class=HTMLResponse)
@require_auth
async def logs_page(request: Request):
    log_path = PROJECT_ROOT / "logs" / "bot.log"
    lines = []
    if log_path.exists():
        content = log_path.read_text(encoding="utf-8", errors="replace")
        lines = content.strip().split("\n")[-200:]

    return render("logs.html", {
        "request": request,
        "log_lines": lines,
    })


@app.get("/scheduler", response_class=HTMLResponse)
@require_auth
async def scheduler_page(request: Request):
    return render("scheduler.html", {
        "request": request,
    })


# ─── Settings / Control Panel ────────────────────────────────────────


@app.get("/settings", response_class=HTMLResponse)
@require_auth
async def settings_page(request: Request, tab: str = "messages"):
    messages = await get_all_messages()
    paused = await is_bot_paused()

    async with _dashboard_session_factory() as session:
        total_users = (await session.execute(select(func.count(User.id)))).scalar() or 0
        total_posts = (await session.execute(select(func.count(Post.id)))).scalar() or 0
        active_posts = (await session.execute(select(func.count(Post.id)).where(Post.status == PostStatus.PUBLISHED))).scalar() or 0
        failed_posts = (await session.execute(select(func.count(Post.id)).where(Post.status == PostStatus.FAILED))).scalar() or 0
        deleted_posts = (await session.execute(select(func.count(Post.id)).where(Post.status == PostStatus.DELETED))).scalar() or 0

    feature_repeats = (await get_config("feature_repeats", "true")) == "true"
    feature_media = (await get_config("feature_media", "true")) == "true"
    max_active_posts = await get_config("max_active_posts", "7")
    max_posts_per_hour = await get_config("max_posts_per_hour", "7")

    return render("settings.html", {
        "request": request,
        "tab": tab,
        "messages": messages,
        "defaults": DEFAULT_MESSAGES,
        "bot_paused": paused,
        "feature_repeats": feature_repeats,
        "feature_media": feature_media,
        "max_active_posts": max_active_posts,
        "max_posts_per_hour": max_posts_per_hour,
        "total_users": total_users,
        "total_posts": total_posts,
        "active_posts": active_posts,
        "failed_posts": failed_posts,
        "deleted_posts": deleted_posts,
    })


@app.post("/settings/messages/{key}")
@require_auth
async def update_message(request: Request, key: str):
    form = await request.form()
    text = form.get("text", "")
    await set_message(key, text)
    return RedirectResponse(url="/settings?tab=messages", status_code=303)


@app.post("/settings/messages/{key}/reset")
@require_auth
async def reset_message(request: Request, key: str):
    from db.config_store import set_config
    await set_config("msg_" + key, "")
    return RedirectResponse(url="/settings?tab=messages", status_code=303)


@app.post("/settings/bot/pause")
@require_auth
async def toggle_pause(request: Request):
    paused = await is_bot_paused()
    await set_bot_paused(not paused)
    return RedirectResponse(url="/settings", status_code=303)


@app.post("/settings/config/{key}")
@require_auth
async def update_config(request: Request, key: str):
    form = await request.form()
    value = form.get("value", "")
    await set_config(key, value)
    return RedirectResponse(url="/settings?tab=features", status_code=303)


@app.get("/api/bot/status")
@require_auth
async def api_bot_status(request: Request):
    from db.config_store import get_bot_status
    import json
    from fastapi.responses import JSONResponse
    status = await get_bot_status()
    return JSONResponse(status)


def run_dashboard(host: str = "0.0.0.0", port: int = 5000):
    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="warning")
