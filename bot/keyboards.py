from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton


def main_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("📝 منشور جديد", callback_data="new_post"),
            InlineKeyboardButton("📋 منشوراتي", callback_data="my_posts"),
        ],
        [
            InlineKeyboardButton("⚙️ الإعدادات", callback_data="settings"),
            InlineKeyboardButton("❓ مساعدة", callback_data="help"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def login_keyboard() -> InlineKeyboardMarkup:
    button = [[InlineKeyboardButton("🔗 تسجيل الدخول إلى X", callback_data="login")]]
    return InlineKeyboardMarkup(button)


def delete_time_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("5 دقائق", callback_data="delete_5"),
            InlineKeyboardButton("10 دقائق", callback_data="delete_10"),
        ],
        [
            InlineKeyboardButton("20 دقيقة", callback_data="delete_20"),
            InlineKeyboardButton("30 دقيقة", callback_data="delete_30"),
        ],
        [
            InlineKeyboardButton("ساعة", callback_data="delete_60"),
            InlineKeyboardButton("⏱️ مخصص", callback_data="delete_custom"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def repeat_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("مرة واحدة", callback_data="repeat_1"),
            InlineKeyboardButton("مرتين", callback_data="repeat_2"),
        ],
        [
            InlineKeyboardButton("3 مرات ⚠️", callback_data="repeat_3"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def confirm_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("✅ نشر", callback_data="confirm_publish"),
            InlineKeyboardButton("❌ إلغاء", callback_data="confirm_cancel"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def skip_media_keyboard() -> InlineKeyboardMarkup:
    button = [[InlineKeyboardButton("⏭️ تخطي الصورة", callback_data="skip_media")]]
    return InlineKeyboardMarkup(button)


def post_action_keyboard(post_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("🗑️ حذف", callback_data=f"delete_post_{post_id}"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def back_keyboard() -> InlineKeyboardMarkup:
    button = [[InlineKeyboardButton("🔙 رجوع", callback_data="back_to_menu")]]
    return InlineKeyboardMarkup(button)


def settings_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("⏰ وقت الحذف الافتراضي", callback_data="set_default_time"),
            InlineKeyboardButton("🔁 التكرار الافتراضي", callback_data="set_default_repeat"),
        ],
        [
            InlineKeyboardButton("🌡️ فترة التبريد", callback_data="set_cooldown"),
            InlineKeyboardButton("🔙 رجوع", callback_data="back_to_menu"),
        ],
        [
            InlineKeyboardButton("🚪 تسجيل الخروج من X", callback_data="logout"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def cooldown_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("0 دقيقة (بدون)", callback_data="cooldown_0"),
            InlineKeyboardButton("15 دقيقة", callback_data="cooldown_15"),
        ],
        [
            InlineKeyboardButton("30 دقيقة", callback_data="cooldown_30"),
            InlineKeyboardButton("60 دقيقة", callback_data="cooldown_60"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def oauth_help_keyboard() -> InlineKeyboardMarkup:
    button = [[InlineKeyboardButton("🔗 فتح رابط التوثيق", callback_data="login")]]
    return InlineKeyboardMarkup(button)


def cancel_keyboard() -> InlineKeyboardMarkup:
    button = [[InlineKeyboardButton("❌ إلغاء", callback_data="cancel")]]
    return InlineKeyboardMarkup(button)


def confirm_logout_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("✅ نعم، تسجيل الخروج", callback_data="confirm_logout"),
            InlineKeyboardButton("❌ إلغاء", callback_data="back_to_menu"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)
