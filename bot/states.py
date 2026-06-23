from telegram.ext import ConversationHandler

(
    MAIN_MENU,                      # 0
    AWAITING_LOGIN,                 # 1
    AWAITING_OAUTH_PIN,             # 2 - OAuth 1.0a PIN
    AWAITING_OAUTH_CODE,            # 3 - OAuth 2.0 PKCE code
    AWAITING_POST_TEXT,             # 4
    AWAITING_POST_MEDIA,            # 5
    AWAITING_DELETE_TIME,           # 6
    AWAITING_CUSTOM_DELETE_TIME,    # 7
    AWAITING_REPEAT_COUNT,          # 8
    AWAITING_CONFIRMATION,          # 9
    AWAITING_SETTINGS_DELETE_TIME,  # 10
    AWAITING_CUSTOM_SETTINGS_DELETE_TIME,  # 11
    AWAITING_SETTINGS_REPEAT,       # 12
    AWAITING_SETTINGS_COOLDOWN,     # 13
) = range(14)
