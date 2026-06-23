import logging
from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

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
        "auth": "oauth2_pkce",
    }


@router.get("/auth/x/callback", response_class=HTMLResponse)
async def x_callback(code: str = "", state: str = "", error: str = ""):
    if error:
        return f"""<html><body dir="rtl">
<h2>❌ تم رفض التفويض</h2>
<p>{error}</p>
<p>ارجع إلى البوت وحاول مرة أخرى.</p>
</body></html>"""

    if not code:
        return """<html><body dir="rtl">
<h2>❌ لم يتم استلام الكود</h2>
<p>تأكد من أن الرابط الذي فتحته صحيح.</p>
</body></html>"""

    return f"""<html><body dir="rtl" style="font-family: sans-serif; padding: 2em;">
<h2>✅ تم التفويض بنجاح!</h2>
<p>انسخ <b>الكود</b> التالي وأرسله إلى بوت التليجرام:</p>
<pre style="
    background: #f0f0f0;
    padding: 1em;
    border-radius: 8px;
    font-size: 1.1em;
    word-break: break-all;
    user-select: all;
">{code}</pre>
<p style="color: #666; font-size: 0.9em;">بعد نسخ الكود، ارجع إلى البوت وأرسله.</p>
</body></html>"""
