import asyncio
import json
import logging
import os
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from bot.keyboards import (
    back_keyboard,
    cancel_keyboard,
    confirm_keyboard,
    cooldown_keyboard,
    delete_time_keyboard,
    login_keyboard,
    main_menu_keyboard,
    post_action_keyboard,
    repeat_keyboard,
    settings_keyboard,
    confirm_logout_keyboard,
    skip_media_keyboard,
)
import warnings

from bot.states import *
from config import (
    ADMIN_TELEGRAM_ID,
    FERNET_KEY,
    MAX_CONTENT_LENGTH,
    MAX_IMAGE_SIZE_MB,
    MAX_REPEAT_COUNT,
    MAX_VIDEO_SIZE_MB,
    PROJECT_ROOT,
)
from db.base import async_session_factory
from db.config_store import get_message, is_bot_paused
from db.models import PostStatus
from db.repository import PostRepository, UserRepository
from utils import decrypt_token, encrypt_token
from x_browser.auth import login_with_credentials
from x_browser.client import XBrowserClient
from x_api.rate_limiter import RateLimiter

warnings.filterwarnings("ignore", message="If 'per_message=False'")

logger = logging.getLogger(__name__)

TEMP_DIR = PROJECT_ROOT / "temp"


async def get_user_repo() -> UserRepository:
    session = async_session_factory()
    return UserRepository(session)


async def get_post_repo() -> PostRepository:
    session = async_session_factory()
    return PostRepository(session)


async def notify_admin(bot, message: str):
    if ADMIN_TELEGRAM_ID:
        try:
            await bot.send_message(chat_id=ADMIN_TELEGRAM_ID, text=message)
        except Exception as e:
            logger.error(f"Failed to notify admin: {e}")


def generate_variation(text: str, index: int, total: int) -> str:
    prefix = random.choice(["", "— ", "⚡ ", "🔄 "])
    suffixes = [
        f"\n\n{prefix}[{index}/{total}]",
        f"\n\n— متابعة ({index}/{total})",
        f"\n\n⬇️ ({index}/{total})",
    ]
    suffix = random.choice(suffixes)
    max_len = MAX_CONTENT_LENGTH - len(suffix)
    body = text[:max_len].rstrip()
    return body + suffix


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    session = async_session_factory()
    async with session:
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(user_id)

    if user and user.banned:
        msg = await get_message("ban_message")
        await update.message.reply_text(msg)
        return ConversationHandler.END

    if not user:
        session = async_session_factory()
        async with session:
            repo = UserRepository(session)
            user = await repo.create(telegram_id=user_id)
        logger.info(f"New user registered: {user_id}")

    if await is_bot_paused() and ADMIN_TELEGRAM_ID and user_id != ADMIN_TELEGRAM_ID:
        msg = await get_message("bot_paused")
        await update.message.reply_text(msg)
        return ConversationHandler.END

    if user and user.cookies_data:
        msg = await get_message("welcome_existing")
        await update.message.reply_text(msg, reply_markup=main_menu_keyboard())
        return MAIN_MENU

    msg = await get_message("welcome_new")
    await update.message.reply_text(msg, reply_markup=login_keyboard())
    return AWAITING_LOGIN


async def login_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "🔐 *تسجيل الدخول إلى X*\n\n"
        "أرسل *اسم المستخدم* أو *البريد الإلكتروني* لحساب X:\n\n"
        "⚠️ سيتم حذف الرسائل الحساسة تلقائياً بعد تسجيل الدخول.",
        reply_markup=cancel_keyboard(),
    )
    return AWAITING_CREDENTIALS


async def receive_credentials(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not text:
        return AWAITING_CREDENTIALS

    context.user_data["x_username_input"] = text
    context.user_data["login_username_msg_id"] = update.message.message_id

    await update.message.reply_text(
        "🔑 الآن أرسل *كلمة المرور* لحساب X:\n\n"
        "⚠️ لن تُحفظ كلمة المرور، وتُستخدم فقط لتسجيل الدخول لمرة واحدة.",
        reply_markup=cancel_keyboard(),
    )
    return AWAITING_PASSWORD


async def receive_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.user_data.get("awaiting_2fa"):
        code = update.message.text.strip()
        context.user_data["2fa_code"] = code
        context.user_data["2fa_event"].set()
        await update.message.reply_text("🔄 جاري التحقق من الرمز...")
        return MAIN_MENU

    password = update.message.text.strip()
    if not password:
        await update.message.reply_text("❌ كلمة المرور لا يمكن أن تكون فارغة.", reply_markup=cancel_keyboard())
        return AWAITING_PASSWORD

    username = context.user_data.get("x_username_input", "")
    pass_msg_id = update.message.message_id
    user_msg_id = context.user_data.get("login_username_msg_id")
    chat_id = update.effective_user.id

    await update.message.reply_text("🔄 جاري تسجيل الدخول إلى X...")

    context.user_data["2fa_event"] = asyncio.Event()
    context.user_data["2fa_code"] = None
    context.user_data["awaiting_2fa"] = False

    async def on_2fa():
        await context.bot.send_message(
            chat_id=chat_id,
            text="🔐 *مطلوب رمز التحقق (2FA)*\n\n"
                 "أرسل رمز التحقق المرسل إلى هاتفك أو بريدك الإلكتروني:",
        )
        context.user_data["awaiting_2fa"] = True
        await context.user_data["2fa_event"].wait()
        code = context.user_data["2fa_code"]
        context.user_data.pop("2fa_event", None)
        context.user_data.pop("2fa_code", None)
        context.user_data.pop("awaiting_2fa", None)
        return code

    try:
        x_user_id, x_username, cookies = await login_with_credentials(
            username, password, on_2fa=on_2fa
        )
    except Exception as e:
        logger.error(f"Login error: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ فشل تسجيل الدخول. تحقق من البيانات وحاول مرة أخرى.",
            reply_markup=login_keyboard(),
        )
        context.user_data.pop("x_username_input", None)
        context.user_data.pop("login_username_msg_id", None)
        return AWAITING_LOGIN

    if not cookies:
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ فشل تسجيل الدخول. تحقق من الاسم والباسورد وحاول مرة أخرى.",
            reply_markup=login_keyboard(),
        )
        context.user_data.pop("x_username_input", None)
        context.user_data.pop("login_username_msg_id", None)
        return AWAITING_LOGIN

    encrypted_cookies = encrypt_token(json.dumps(cookies), FERNET_KEY)

    session = async_session_factory()
    async with session:
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(chat_id)
        if user:
            await repo.update(
                user,
                x_user_id=x_user_id,
                x_username=x_username,
                cookies_data=encrypted_cookies,
                needs_login=False,
            )
        else:
            await repo.create(
                telegram_id=chat_id,
                x_user_id=x_user_id,
                x_username=x_username,
                cookies_data=encrypted_cookies,
            )

    for msg_id in (user_msg_id, pass_msg_id):
        if msg_id:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception:
                pass

    context.user_data.pop("x_username_input", None)
    context.user_data.pop("login_username_msg_id", None)

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"✅ *تم تسجيل الدخول بنجاح!*\n\n"
             f"مرحباً @{x_username} 🎉\n"
             "تم حفظ الجلسة بشكل آمن.\n"
             "يمكنك الآن البدء بالنشر.",
        reply_markup=main_menu_keyboard(),
    )
    return MAIN_MENU


async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    telegram_id = query.from_user.id
    if await is_bot_paused() and ADMIN_TELEGRAM_ID and telegram_id != ADMIN_TELEGRAM_ID:
        msg = await get_message("bot_paused")
        await query.edit_message_text(msg)
        return ConversationHandler.END

    if query.data == "new_post":
        return await start_new_post(query, context)
    elif query.data == "my_posts":
        return await show_my_posts(query, context)
    elif query.data == "settings":
        return await show_settings(query, context)
    elif query.data == "help":
        return await show_help(query, context)
    elif query.data == "back_to_menu":
        await query.edit_message_text(
            "👋 *القائمة الرئيسية*\n\nاختر أحد الخيارات:",
            reply_markup=main_menu_keyboard(),
        )
        return MAIN_MENU
    elif query.data == "cancel":
        context.user_data.pop("x_username_input", None)
        context.user_data.pop("login_username_msg_id", None)
        await query.edit_message_text(
            "✅ تم الإلغاء.",
            reply_markup=main_menu_keyboard(),
        )
        return MAIN_MENU

    return MAIN_MENU


async def show_help(query, context):
    await query.edit_message_text(
        "❓ *المساعدة*\n\n"
        "• 📝 **نشر منشور جديد**: أرسل نصاً (وصورة اختيارية)\n"
        "  وحدد وقت الحذف وعدد التكرارات.\n\n"
        "• 📋 **منشوراتي**: عرض المنشورات النشطة وحذفها يدوياً.\n\n"
        "• ⚙️ **الإعدادات**: ضبط وقت الحذف الافتراضي والتكرار.\n\n"
        "*سياسات الحماية:*\n"
        f"• حد أقصى {7} منشورات نشطة في نفس الوقت.\n"
        f"• حد أقصى {7} منشورات في الساعة.\n\n"
        "*ملاحظة:* أنت المسؤول الوحيد عن محتوى منشوراتك.",
        reply_markup=back_keyboard(),
    )
    return MAIN_MENU


async def start_new_post(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["post_data"] = {}
    await query.edit_message_text(
        "📝 *منشور جديد*\n\n"
        "أرسل نص المنشور (الحد الأقصى 280 حرفاً):\n"
        "يمكنك إرسال صورة بعد النص.",
        reply_markup=cancel_keyboard(),
    )
    return AWAITING_POST_TEXT


async def receive_post_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if len(text) > MAX_CONTENT_LENGTH:
        await update.message.reply_text(
            f"❌ النص طويل جداً! الحد الأقصى {MAX_CONTENT_LENGTH} حرفاً.\n"
            f"نصك الحالي: {len(text)} حرف. حاول اختصاره.",
            reply_markup=cancel_keyboard(),
        )
        return AWAITING_POST_TEXT

    if not text:
        await update.message.reply_text(
            "❌ النص لا يمكن أن يكون فارغاً.",
            reply_markup=cancel_keyboard(),
        )
        return AWAITING_POST_TEXT

    context.user_data["post_data"]["content"] = text
    await update.message.reply_text(
        "📷 هل تريد إضافة صورة؟\n"
        f"(الحد الأقصى {MAX_IMAGE_SIZE_MB} ميجابايت)\n"
        "أرسل الصورة أو اختر تخطي.",
        reply_markup=skip_media_keyboard(),
    )
    return AWAITING_POST_MEDIA


async def receive_post_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.photo:
        file = update.message.photo[-1]
        file_size = file.file_size or 0
        if file_size > MAX_IMAGE_SIZE_MB * 1024 * 1024:
            await update.message.reply_text(
                f"❌ الصورة كبيرة جداً! الحد الأقصى {MAX_IMAGE_SIZE_MB} ميجابايت.",
                reply_markup=skip_media_keyboard(),
            )
            return AWAITING_POST_MEDIA
        context.user_data["post_data"]["media_file_id"] = file.file_id
        context.user_data["post_data"]["media_type"] = "photo"
    elif update.message.document:
        file = update.message.document
        if file.mime_type and file.mime_type.startswith("image/"):
            file_size = file.file_size or 0
            if file_size > MAX_IMAGE_SIZE_MB * 1024 * 1024:
                await update.message.reply_text(
                    f"❌ الملف كبير جداً! الحد الأقصى {MAX_IMAGE_SIZE_MB} ميجابايت.",
                    reply_markup=skip_media_keyboard(),
                )
                return AWAITING_POST_MEDIA
            context.user_data["post_data"]["media_file_id"] = file.file_id
            context.user_data["post_data"]["media_type"] = "photo"
        else:
            await update.message.reply_text(
                "❌ هذا النوع من الملفات غير مدعوم. أرسل صورة أو اختر تخطي.",
                reply_markup=skip_media_keyboard(),
            )
            return AWAITING_POST_MEDIA
    else:
        await update.message.reply_text(
            "❌ هذا النوع غير مدعوم. أرسل صورة أو اختر تخطي.",
            reply_markup=skip_media_keyboard(),
        )
        return AWAITING_POST_MEDIA

    await update.message.reply_text(
        "✅ تم استلام الصورة.\nالآن اختر وقت الحذف:",
        reply_markup=delete_time_keyboard(),
    )
    return AWAITING_DELETE_TIME


async def skip_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["post_data"]["media_file_id"] = None
    await query.edit_message_text(
        "✅ بدون صورة.\nالآن اختر وقت الحذف:",
        reply_markup=delete_time_keyboard(),
    )
    return AWAITING_DELETE_TIME


async def handle_delete_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "delete_custom":
        await query.edit_message_text(
            "⏱️ أرسل وقت الحذف بالدقائق (مثلاً: 15):",
            reply_markup=cancel_keyboard(),
        )
        return AWAITING_CUSTOM_DELETE_TIME

    try:
        minutes = int(data.replace("delete_", ""))
    except ValueError:
        return AWAITING_DELETE_TIME

    context.user_data["post_data"]["delete_minutes"] = minutes

    await query.edit_message_text(
        "🔁 اختر عدد مرات التكرار:\n\n"
        "_ملاحظة: التكرار يعني إعادة نشر نفس المحتوى بفواصل زمنية._\n"
        "_لن يتم تكرار نفس النص حرفياً لمنع الحظر._",
        reply_markup=repeat_keyboard(),
    )
    return AWAITING_REPEAT_COUNT


async def handle_custom_delete_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    try:
        minutes = int(text)
        if minutes < 1 or minutes > 1440:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "❌ الرجاء إدخال رقم صحيح بين 1 و 1440 (دقيقة):"
        )
        return AWAITING_CUSTOM_DELETE_TIME

    context.user_data["post_data"]["delete_minutes"] = minutes
    await update.message.reply_text(
        "🔁 اختر عدد مرات التكرار:",
        reply_markup=repeat_keyboard(),
    )
    return AWAITING_REPEAT_COUNT


async def handle_repeat_count(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data
    try:
        count = int(data.replace("repeat_", ""))
    except ValueError:
        return AWAITING_REPEAT_COUNT

    context.user_data["post_data"]["repeat_count"] = count

    if count > 1:
        await query.edit_message_text(
            f"⚠️ *تنبيه:* اخترت تكرار المنشور {count} مرات.\n"
            "• سيتم نشر كل نسخة بفاصل زمني (60 دقيقة).\n"
            "• النص سيتم تنويع قليلاً لتجنب الحظر.\n"
            "• هذا سيستهلك من حصتك (7 منشورات/ساعة).\n\n"
            "هل أنت متأكد؟",
            reply_markup=confirm_keyboard(),
        )
    else:
        await show_confirmation(query, context)

    return AWAITING_CONFIRMATION


async def show_confirmation(query, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data.get("post_data", {})
    text = data.get("content", "")
    delete_min = data.get("delete_minutes", 0)
    repeat = data.get("repeat_count", 1)
    has_media = "✅ نعم" if data.get("media_file_id") else "❌ لا"

    summary = (
        "📋 *ملخص المنشور*\n\n"
        f"*النص:* {text[:100]}{'...' if len(text) > 100 else ''}\n"
        f"*صورة:* {has_media}\n"
        f"*وقت الحذف:* {delete_min} دقيقة\n"
        f"*التكرار:* {repeat} مرة {'واحدة' if repeat == 1 else 'مرات'}\n\n"
        "هل تريد النشر؟"
    )
    await query.edit_message_text(summary, reply_markup=confirm_keyboard())


async def confirm_publish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = context.user_data.get("post_data", {})
    telegram_id = update.effective_user.id

    if query.data == "confirm_cancel":
        context.user_data.pop("post_data", None)
        await query.edit_message_text(
            "✅ تم إلغاء المنشور.",
            reply_markup=main_menu_keyboard(),
        )
        return MAIN_MENU

    if query.data != "confirm_publish":
        return AWAITING_CONFIRMATION

    session = async_session_factory()
    async with session:
        try:
            user_repo = UserRepository(session)
            post_repo = PostRepository(session)
            user = await user_repo.get_by_telegram_id(telegram_id)

            if not user or not user.cookies_data:
                await query.edit_message_text(
                    "❌ حساب X غير مرتبط. الرجاء تسجيل الدخول أولاً.",
                    reply_markup=login_keyboard(),
                )
                return AWAITING_LOGIN

            limiter = RateLimiter(post_repo)
            check = await limiter.can_publish(user.id)
            if not check.allowed:
                await query.edit_message_text(
                    f"❌ *لا يمكن النشر الآن*\n\n{check.message}",
                    reply_markup=back_keyboard(),
                )
                return MAIN_MENU

            if data.get("repeat_count", 1) > 1:
                repeat_check = await limiter.can_repeat(user.id, data["repeat_count"])
                if not repeat_check.allowed:
                    await query.edit_message_text(
                        f"❌ *لا يمكن التكرار*\n\n{repeat_check.message}",
                        reply_markup=back_keyboard(),
                    )
                    return MAIN_MENU

            await query.edit_message_text("🔄 جاري النشر على X...")

            cookies = json.loads(decrypt_token(user.cookies_data, FERNET_KEY))
            client = XBrowserClient(cookies)

            media_path = None
            if data.get("media_file_id"):
                media_path = await download_media(
                    context, data["media_file_id"], user.id
                )
            tweet_id = await client.post_tweet(
                data["content"],
                media_path=media_path,
            )

            delete_at = datetime.utcnow() + timedelta(minutes=data["delete_minutes"])
            repeat_count = data.get("repeat_count", 1)
            remaining = repeat_count - 1

            await post_repo.create(
                user_id=user.id,
                tweet_id=tweet_id,
                content=data["content"],
                media_path=media_path,
                media_id=None,
                repeat_count=repeat_count,
                repeat_interval=60,
                remaining_repeats=remaining,
                delete_after_minutes=data["delete_minutes"],
                published_at=datetime.utcnow(),
                delete_at=delete_at,
                status=PostStatus.PUBLISHED,
            )

            context.user_data.pop("post_data", None)

            msg = (
                "✅ *تم النشر بنجاح!*\n\n"
                f"🆔 معرف التغريدة: `{tweet_id}`\n"
                f"⏰ سيتم الحذف تلقائياً بعد {data['delete_minutes']} دقيقة\n"
            )
            if remaining > 0:
                msg += f"🔄 متبقي {remaining} تكرارات (كل 60 دقيقة)\n"

            await query.edit_message_text(msg, reply_markup=main_menu_keyboard())

        except Exception as e:
            logger.error(f"Publish error: {e}")
            await query.edit_message_text(
                f"❌ حدث خطأ أثناء النشر:\n{str(e)[:200]}",
                reply_markup=back_keyboard(),
            )
            return MAIN_MENU

    return MAIN_MENU


async def download_media(
    context: ContextTypes.DEFAULT_TYPE, file_id: str, user_id: int
) -> Optional[str]:
    try:
        TEMP_DIR.mkdir(exist_ok=True)
        file = await context.bot.get_file(file_id)
        ext = ".jpg"
        local_path = str(
            TEMP_DIR / f"media_{user_id}_{datetime.utcnow().timestamp()}{ext}"
        )
        await file.download_to_drive(local_path)
        logger.info(f"Media downloaded to {local_path}")
        return local_path
    except Exception as e:
        logger.error(f"Media download error: {e}")
        return None


async def show_my_posts(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    telegram_id = query.from_user.id

    session = async_session_factory()
    async with session:
        user_repo = UserRepository(session)
        post_repo = PostRepository(session)
        user = await user_repo.get_by_telegram_id(telegram_id)

        if not user:
            await query.edit_message_text(
                "❌ يجب تسجيل الدخول أولاً.",
                reply_markup=login_keyboard(),
            )
            return AWAITING_LOGIN

        posts = await post_repo.get_active_by_user(user.id)

    if not posts:
        await query.edit_message_text(
            "📋 *لا توجد منشورات نشطة*\n\n"
            "لم تقم بنشر أي منشورات بعد، أو جميعها تم حذفها.",
            reply_markup=back_keyboard(),
        )
        return MAIN_MENU

    text = "📋 *المنشورات النشطة:*\n\n"
    for i, post in enumerate(posts[:10], 1):
        remaining = ""
        if post.delete_at:
            secs = (post.delete_at - datetime.utcnow()).total_seconds()
            mins = max(0, int(secs // 60))
            remaining = f"⏳ {mins} دقيقة متبقية"

        post_text = post.content[:50] + "..." if len(post.content) > 50 else post.content
        status_icon = "✅" if post.status == PostStatus.PUBLISHED else "⏳"
        text += f"{i}. {status_icon} {post_text}\n   {remaining}\n\n"

    buttons = [
        [InlineKeyboardButton(f"🗑️ حذف {i}", callback_data=f"delete_post_{p.id}")]
        for i, p in enumerate(posts[:10], 1)
    ]
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_to_menu")])
    markup = InlineKeyboardMarkup(buttons)

    await query.edit_message_text(text, reply_markup=markup)
    return MAIN_MENU


async def handle_my_posts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data.startswith("delete_post_"):
        try:
            post_id = int(query.data.replace("delete_post_", ""))
        except ValueError:
            return MAIN_MENU
        return await delete_post_by_id(query, context, post_id)

    return MAIN_MENU


async def delete_post_by_id(query, context: ContextTypes.DEFAULT_TYPE, post_id: int) -> int:
    telegram_id = query.from_user.id

    session = async_session_factory()
    async with session:
        post_repo = PostRepository(session)
        user_repo = UserRepository(session)
        post = await post_repo.get_by_id(post_id)

        if not post:
            await query.edit_message_text("❌ المنشور غير موجود.")
            return MAIN_MENU

        user = await user_repo.get_by_telegram_id(telegram_id)
        if not user or post.user_id != user.id:
            await query.edit_message_text("❌ هذا المنشور ليس لك.")
            return MAIN_MENU

        if post.tweet_id and user.cookies_data:
            try:
                cookies = json.loads(decrypt_token(user.cookies_data, FERNET_KEY))
                client = XBrowserClient(cookies)
                await client.delete_tweet(post.tweet_id)
                logger.info(f"Deleted tweet {post.tweet_id} for user {user.id}")
            except Exception as e:
                logger.error(f"Failed to delete tweet {post.tweet_id}: {e}")

        await post_repo.delete(post_id)

    await query.edit_message_text(
        "🗑️ *تم حذف المنشور*",
        reply_markup=main_menu_keyboard(),
    )
    return MAIN_MENU


async def show_settings(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    telegram_id = query.from_user.id

    session = async_session_factory()
    async with session:
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(telegram_id)

    if not user:
        await query.edit_message_text(
            "❌ يجب تسجيل الدخول أولاً.",
            reply_markup=login_keyboard(),
        )
        return AWAITING_LOGIN

    default_time = user.default_delete_minutes or "يُسأل كل مرة"
    default_repeat = user.default_repeat_count or 1
    cooldown = user.cooldown_minutes or 0

    text = (
        "⚙️ *الإعدادات*\n\n"
        f"⏰ *وقت الحذف الافتراضي:* {default_time} دقيقة\n"
        f"🔁 *التكرار الافتراضي:* {default_repeat} مرة\n"
        f"🌡️ *فترة التبريد:* {cooldown} دقيقة\n\n"
        "اختر ما تريد تعديله:"
    )
    await query.edit_message_text(text, reply_markup=settings_keyboard())
    return MAIN_MENU


async def handle_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data
    telegram_id = query.from_user.id

    session = async_session_factory()
    async with session:
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(telegram_id)

    if not user:
        await query.edit_message_text("❌ يجب تسجيل الدخول أولاً.")
        return MAIN_MENU

    if data == "set_default_time":
        await query.edit_message_text(
            "⏰ أرسل وقت الحذف الافتراضي بالدقائق\n"
            "(0 يعني أن البوت سيسألك في كل مرة):",
            reply_markup=cancel_keyboard(),
        )
        return AWAITING_SETTINGS_DELETE_TIME

    elif data == "set_default_repeat":
        await query.edit_message_text(
            "🔁 أرسل عدد التكرارات الافتراضي (1-3):",
            reply_markup=cancel_keyboard(),
        )
        return AWAITING_SETTINGS_REPEAT

    elif data == "set_cooldown":
        await query.edit_message_text(
            "🌡️ اختر فترة التبريد (بالدقائق):",
            reply_markup=cooldown_keyboard(),
        )
        return AWAITING_SETTINGS_COOLDOWN

    elif data == "logout":
        await query.edit_message_text(
            "🚪 *تسجيل الخروج من X*\n\n"
            "سيتم حذف بيانات الدخول الخاصة بحساب X المرتبط.\n"
            "لن تفقد منشوراتك السابقة على X، لكنك لن تستطيع إدارة المنشورات"
            " من البوت بعد الآن.\n\n"
            "هل أنت متأكد؟",
            reply_markup=confirm_logout_keyboard(),
        )
        return MAIN_MENU

    return MAIN_MENU


async def handle_confirm_logout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "confirm_logout":
        telegram_id = query.from_user.id
        session = async_session_factory()
        async with session:
            repo = UserRepository(session)
            user = await repo.get_by_telegram_id(telegram_id)
            if user:
                await repo.update(
                    user,
                    x_user_id=None,
                    x_username=None,
                    access_token="",
                    access_token_secret="",
                    oauth_token="",
                    oauth_refresh_token="",
                    token_expires_at=None,
                    cookies_data="",
                    needs_login=False,
                    default_delete_minutes=0,
                    default_repeat_count=1,
                    cooldown_minutes=0,
                )

        await query.edit_message_text(
            "✅ *تم تسجيل الخروج بنجاح*\n\n"
            "تم فصل حساب X الخاص بك.\n"
            "يمكنك تسجيل الدخول مرة أخرى في أي وقت بأمر /start",
            reply_markup=login_keyboard(),
        )
        return AWAITING_LOGIN

    return MAIN_MENU


async def handle_settings_delete_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    telegram_id = update.effective_user.id
    text = update.message.text.strip()

    try:
        minutes = int(text)
        if minutes < 0 or minutes > 1440:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ الرجاء إدخال رقم بين 0 و 1440.")
        return AWAITING_SETTINGS_DELETE_TIME

    session = async_session_factory()
    async with session:
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(telegram_id)
        if user:
            await repo.update(user, default_delete_minutes=minutes)

    await update.message.reply_text(
        f"✅ تم حفظ وقت الحذف الافتراضي: {minutes} دقيقة.",
        reply_markup=main_menu_keyboard(),
    )
    return MAIN_MENU


async def handle_settings_repeat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    telegram_id = update.effective_user.id
    text = update.message.text.strip()

    try:
        count = int(text)
        if count < 1 or count > MAX_REPEAT_COUNT:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            f"❌ الرجاء إدخال رقم بين 1 و {MAX_REPEAT_COUNT}."
        )
        return AWAITING_SETTINGS_REPEAT

    session = async_session_factory()
    async with session:
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(telegram_id)
        if user:
            await repo.update(user, default_repeat_count=count)

    await update.message.reply_text(
        f"✅ تم حفظ التكرار الافتراضي: {count} مرة.",
        reply_markup=main_menu_keyboard(),
    )
    return MAIN_MENU


async def handle_settings_cooldown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    telegram_id = query.from_user.id
    try:
        data = query.data
        minutes = int(data.replace("cooldown_", ""))
    except (ValueError, AttributeError):
        return MAIN_MENU

    session = async_session_factory()
    async with session:
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(telegram_id)
        if user:
            await repo.update(user, cooldown_minutes=minutes)

    await query.edit_message_text(
        f"✅ تم حفظ فترة التبريد: {minutes} دقيقة.",
        reply_markup=main_menu_keyboard(),
    )
    return MAIN_MENU


async def fallback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "❌ أمر غير معروف. استخدم /start للعودة إلى القائمة الرئيسية."
    )
    return MAIN_MENU


def get_conversation_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        per_user=True,
        per_chat=True,
        per_message=False,
        states={
            AWAITING_LOGIN: [
                CallbackQueryHandler(login_button, pattern="^login$"),
                CallbackQueryHandler(main_menu_handler, pattern="^cancel$"),
            ],
            AWAITING_CREDENTIALS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_credentials),
                CallbackQueryHandler(main_menu_handler, pattern="^cancel$"),
            ],
            AWAITING_PASSWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_password),
                CallbackQueryHandler(main_menu_handler, pattern="^cancel$"),
            ],
            MAIN_MENU: [
                CallbackQueryHandler(main_menu_handler, pattern="^(new_post|my_posts|settings|help|back_to_menu|cancel)$"),
                CallbackQueryHandler(handle_my_posts_callback, pattern="^delete_post_"),
                CallbackQueryHandler(handle_settings_callback, pattern="^(set_default_time|set_default_repeat|set_cooldown|logout)$"),
                CallbackQueryHandler(handle_confirm_logout, pattern="^(confirm_logout)$"),
            ],
            AWAITING_POST_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_post_text),
                CallbackQueryHandler(main_menu_handler, pattern="^cancel$"),
            ],
            AWAITING_POST_MEDIA: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_post_media),
                CallbackQueryHandler(skip_media, pattern="^skip_media$"),
                CallbackQueryHandler(main_menu_handler, pattern="^cancel$"),
            ],
            AWAITING_DELETE_TIME: [
                CallbackQueryHandler(handle_delete_time, pattern="^delete_"),
            ],
            AWAITING_CUSTOM_DELETE_TIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_delete_time),
                CallbackQueryHandler(main_menu_handler, pattern="^cancel$"),
            ],
            AWAITING_REPEAT_COUNT: [
                CallbackQueryHandler(handle_repeat_count, pattern="^repeat_"),
            ],
            AWAITING_CONFIRMATION: [
                CallbackQueryHandler(confirm_publish, pattern="^(confirm_publish|confirm_cancel)$"),
            ],
            AWAITING_SETTINGS_DELETE_TIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_settings_delete_time),
                CallbackQueryHandler(main_menu_handler, pattern="^cancel$"),
            ],
            AWAITING_SETTINGS_REPEAT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_settings_repeat),
                CallbackQueryHandler(main_menu_handler, pattern="^cancel$"),
            ],
            AWAITING_SETTINGS_COOLDOWN: [
                CallbackQueryHandler(handle_settings_cooldown, pattern="^cooldown_"),
                CallbackQueryHandler(main_menu_handler, pattern="^cancel$"),
            ],
        },
        fallbacks=[
            CommandHandler("start", start),
            MessageHandler(filters.COMMAND, fallback),
        ],
        name="main_conversation",
        persistent=False,
    )
