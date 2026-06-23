import base64
import hashlib
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from urllib.parse import urlencode

import aiohttp
import tweepy

from config import X_API_KEY, X_API_SECRET, X_CLIENT_ID, X_CLIENT_SECRET, X_CALLBACK_URL

logger = logging.getLogger(__name__)

_pending_auths: dict[int, dict] = {}


def _generate_code_verifier() -> str:
    return secrets.token_urlsafe(64)[:128]


def _generate_code_challenge(verifier: str) -> str:
    sha256 = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(sha256).rstrip(b"=").decode()


def get_auth_url(telegram_id: int) -> str:
    code_verifier = _generate_code_verifier()
    code_challenge = _generate_code_challenge(code_verifier)
    state = secrets.token_urlsafe(32)

    _pending_auths[telegram_id] = {
        "code_verifier": code_verifier,
        "state": state,
    }

    params = {
        "response_type": "code",
        "client_id": X_CLIENT_ID,
        "redirect_uri": X_CALLBACK_URL,
        "scope": "tweet.read tweet.write users.read offline.access",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }

    return "https://twitter.com/i/oauth2/authorize?" + urlencode(params)


async def exchange_code(telegram_id: int, code: str) -> Tuple[str, str, int]:
    pending = _pending_auths.pop(telegram_id, None)
    if not pending:
        raise ValueError("لم تبدأ عملية تسجيل الدخول. جرب مرة أخرى.")

    code_verifier = pending["code_verifier"]

    auth_str = f"{X_CLIENT_ID}:{X_CLIENT_SECRET}"
    encoded_auth = base64.b64encode(auth_str.encode()).decode()

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://api.twitter.com/2/oauth2/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": X_CALLBACK_URL,
                "code_verifier": code_verifier,
            },
            headers={
                "Authorization": f"Basic {encoded_auth}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        ) as resp:
            data = await resp.json()

    if "access_token" not in data:
        raise ValueError(f"فشل تبادل الكود: {data.get('error', 'خطأ غير معروف')}")

    return data["access_token"], data.get("refresh_token", ""), data.get("expires_in", 7200)


async def refresh_oauth_token(refresh_token: str) -> Tuple[str, str, int]:
    auth_str = f"{X_CLIENT_ID}:{X_CLIENT_SECRET}"
    encoded_auth = base64.b64encode(auth_str.encode()).decode()

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://api.twitter.com/2/oauth2/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            headers={
                "Authorization": f"Basic {encoded_auth}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        ) as resp:
            data = await resp.json()

    if "access_token" not in data:
        raise ValueError(f"فشل تحديث التوكن: {data.get('error', 'خطأ غير معروف')}")

    return data["access_token"], data.get("refresh_token", refresh_token), data.get("expires_in", 7200)


async def validate_token(access_token: str) -> Tuple[Optional[str], Optional[str]]:
    try:
        client = tweepy.Client(bearer_token=access_token)
        me = client.get_me(user_auth=False)
        if me.data:
            return str(me.data.id), me.data.username
        return None, None
    except tweepy.TweepyException as e:
        logger.error(f"Token validation failed: {e}")
        return None, None


def extract_code_from_url(text: str) -> Optional[str]:
    match = re.search(r'[?&]code=([^&\s]+)', text)
    if match:
        return match.group(1)
    if re.match(r'^[a-zA-Z0-9_-]{10,}$', text.strip()):
        return text.strip()
    return None


async def validate_and_get_user(access_token: str, access_token_secret: str) -> Tuple[Optional[str], Optional[str]]:
    try:
        client = tweepy.Client(
            consumer_key=X_API_KEY,
            consumer_secret=X_API_SECRET,
            access_token=access_token,
            access_token_secret=access_token_secret,
        )
        me = client.get_me(user_auth=True)
        if me.data:
            return str(me.data.id), me.data.username
        return None, None
    except tweepy.TweepyException as e:
        logger.error(f"Token validation failed: {e}")
        return None, None


def get_auth_url_oauth1(telegram_id: int) -> str:
    auth = tweepy.OAuth1UserHandler(X_API_KEY, X_API_SECRET, callback="oob")
    url = auth.get_authorization_url()
    _pending_auths[telegram_id] = dict(auth.request_token)
    return url


def verify_pin(telegram_id: int, pin: str) -> Tuple[str, str]:
    token = _pending_auths.pop(telegram_id, None)
    if not token:
        raise ValueError("لم تبدأ عملية تسجيل الدخول. جرب مرة أخرى.")

    pin = pin.strip()
    if not pin.isdigit() or len(pin) < 6:
        raise ValueError("PIN غير صالح. أرسل الأرقام فقط.")

    auth = tweepy.OAuth1UserHandler(X_API_KEY, X_API_SECRET)
    auth.request_token = token
    access_token, access_token_secret = auth.get_access_token(pin)
    return access_token, access_token_secret
