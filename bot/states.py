from telegram.ext import ConversationHandler

(
    MAIN_MENU,                      # 0
    AWAITING_LOGIN,                 # 1
    AWAITING_CREDENTIALS,           # 2 - X username:password login
    AWAITING_POST_TEXT,             # 3
    AWAITING_POST_MEDIA,            # 4
    AWAITING_DELETE_TIME,           # 5
    AWAITING_CUSTOM_DELETE_TIME,    # 6
    AWAITING_REPEAT_COUNT,          # 7
    AWAITING_CONFIRMATION,          # 8
    AWAITING_SETTINGS_DELETE_TIME,  # 9
    AWAITING_CUSTOM_SETTINGS_DELETE_TIME,  # 10
    AWAITING_SETTINGS_REPEAT,       # 11
    AWAITING_SETTINGS_COOLDOWN,     # 12
) = range(13)
