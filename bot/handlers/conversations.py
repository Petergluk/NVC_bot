# NVC_bot/bot/handlers/conversations.py
# version: 3.2.0
# 2025-07-28T18:00:00Z
"""
ConversationHandler для меню настроек.

Version 3.2.0:
- ADD: Добавлены состояния и обработчики для нового меню
       настроек контекста (`CONTEXT_SETTINGS`, `AWAIT_CONTEXT_VALUE`).
"""
from typing import TYPE_CHECKING
from telegram.ext import CallbackQueryHandler, CommandHandler, ConversationHandler, MessageHandler, filters

if TYPE_CHECKING:
    from .admin import AdminHandlers
    from .callbacks import CallbackHandlers

from .callbacks.callback_patterns import CallbackPrefix
from .states import *

def setup_conversations(admin_handlers: "AdminHandlers", callback_handlers: "CallbackHandlers") -> ConversationHandler:
    """
    Собирает и возвращает полностью настроенный ConversationHandler.
    """
    
    prompt_menu_handlers = [
        CallbackQueryHandler(callback_handlers.send_full_prompt, pattern=f"^{CallbackPrefix.SEND_FULL_PROMPT}"),
        CallbackQueryHandler(callback_handlers.request_prompt_input, pattern=f"^({CallbackPrefix.EDIT_FACILITATOR_PROMPT}|{CallbackPrefix.EDIT_MODERATION_PROMPT}|{CallbackPrefix.EDIT_MODERATION_TEMPLATE}|{CallbackPrefix.EDIT_WELCOME_PROMPT})$"),
        CallbackQueryHandler(callback_handlers.reset_prompt_handler, pattern=f"^({CallbackPrefix.RESET_FACILITATOR_PROMPT}|{CallbackPrefix.RESET_MODERATION_PROMPT}|{CallbackPrefix.RESET_MODERATION_TEMPLATE}|{CallbackPrefix.RESET_WELCOME_PROMPT})$"),
    ]

    return ConversationHandler(
        entry_points=[
            CommandHandler("settings", admin_handlers.settings_entry_point),
            CommandHandler("moderate", admin_handlers.moderate_entry_point),
        ],
        states={
            FACILITATOR_SETTINGS: [
                CallbackQueryHandler(callback_handlers.show_facilitator_model_menu, pattern=f"^{CallbackPrefix.FACILITATOR_MODEL}$"),
                CallbackQueryHandler(callback_handlers.switch_facilitator_model, pattern=f"^{CallbackPrefix.FACILITATOR_SET_MODEL}"),
                CallbackQueryHandler(callback_handlers.show_stats, pattern=f"^{CallbackPrefix.FACILITATOR_STATS}$"),
                CallbackQueryHandler(callback_handlers.show_facilitator_prompt_menu, pattern=f"^{CallbackPrefix.FACILITATOR_PROMPT}$"),
                CallbackQueryHandler(callback_handlers.show_welcomes_menu, pattern=f"^{CallbackPrefix.WELCOMES_MENU}$"),
                CallbackQueryHandler(callback_handlers.show_generation_settings_menu, pattern=f"^{CallbackPrefix.GENERATION_SETTINGS}$"),
                CallbackQueryHandler(callback_handlers.show_context_settings_menu, pattern=f"^{CallbackPrefix.CONTEXT_SETTINGS}$"),
                CallbackQueryHandler(callback_handlers.toggle_debug_mode, pattern=f"^{CallbackPrefix.TOGGLE_DEBUG_MODE}$"),
            ],
            FACILITATOR_PROMPT_MENU: [ *prompt_menu_handlers, CallbackQueryHandler(callback_handlers.show_facilitator_settings_menu, pattern=f"^{CallbackPrefix.BACK_TO_FACILITATOR_SETTINGS}$"), ],
            WELCOME_MENU: [ CallbackQueryHandler(callback_handlers.toggle_welcome, pattern=f"^{CallbackPrefix.WELCOMES_TOGGLE}$"), CallbackQueryHandler(callback_handlers.show_welcome_model_menu, pattern=f"^{CallbackPrefix.WELCOMES_MODEL}$"), CallbackQueryHandler(callback_handlers.show_welcome_prompt_menu, pattern=f"^{CallbackPrefix.WELCOMES_PROMPT}$"), CallbackQueryHandler(callback_handlers.show_facilitator_settings_menu, pattern=f"^{CallbackPrefix.BACK_TO_FACILITATOR_SETTINGS}$"), ],
            WELCOME_MODEL_MENU: [ CallbackQueryHandler(callback_handlers.set_welcome_model, pattern=f"^{CallbackPrefix.WELCOMES_SET_MODEL}"), CallbackQueryHandler(callback_handlers.show_welcomes_menu, pattern=f"^{CallbackPrefix.BACK_TO_WELCOMES_MENU}$"), ],
            WELCOME_PROMPT_MENU: [ *prompt_menu_handlers, CallbackQueryHandler(callback_handlers.show_welcomes_menu, pattern=f"^{CallbackPrefix.BACK_TO_WELCOMES_MENU}$"), ],
            GENERATION_SETTINGS: [ CallbackQueryHandler(callback_handlers.request_generation_value, pattern=f"^{CallbackPrefix.GEN_CONFIG_EDIT}"), CallbackQueryHandler(callback_handlers.reset_generation_config_handler, pattern=f"^{CallbackPrefix.GEN_CONFIG_RESET}$"), CallbackQueryHandler(callback_handlers.show_facilitator_settings_menu, pattern=f"^{CallbackPrefix.BACK_TO_FACILITATOR_SETTINGS}$"), ],
            CONTEXT_SETTINGS: [ CallbackQueryHandler(callback_handlers.request_context_value, pattern=f"^{CallbackPrefix.CONTEXT_CONFIG_EDIT}"), CallbackQueryHandler(callback_handlers.reset_context_config_handler, pattern=f"^{CallbackPrefix.CONTEXT_CONFIG_RESET}$"), CallbackQueryHandler(callback_handlers.show_facilitator_settings_menu, pattern=f"^{CallbackPrefix.BACK_TO_FACILITATOR_SETTINGS}$"), ],
            MODERATION_SETTINGS: [ CallbackQueryHandler(callback_handlers.toggle_moderation, pattern=f"^{CallbackPrefix.MODERATE_TOGGLE}$"), CallbackQueryHandler(callback_handlers.show_moderation_prompt_menu, pattern=f"^{CallbackPrefix.MODERATE_PROMPT}$"), CallbackQueryHandler(callback_handlers.show_moderation_template_menu, pattern=f"^{CallbackPrefix.MODERATE_TEMPLATE}$"), CallbackQueryHandler(callback_handlers.show_moderation_model_menu, pattern=f"^{CallbackPrefix.MODERATE_MODEL}$"), CallbackQueryHandler(callback_handlers.show_sanctions_menu, pattern=f"^{CallbackPrefix.MODERATE_SANCTIONS}$"), CallbackQueryHandler(callback_handlers.show_users_menu, pattern=f"^{CallbackPrefix.MODERATE_USERS}$"), CallbackQueryHandler(callback_handlers.show_triggers_menu, pattern=f"^{CallbackPrefix.MANAGE_TRIGGERS}$"), CallbackQueryHandler(callback_handlers.show_exceptions_menu, pattern=f"^{CallbackPrefix.MANAGE_EXCEPTIONS}$"), ],
            MODERATION_PROMPT_MENU: [ *prompt_menu_handlers, CallbackQueryHandler(callback_handlers.show_moderate_settings_menu, pattern=f"^{CallbackPrefix.BACK_TO_MODERATION_SETTINGS}$"), ],
            MODERATION_TEMPLATE_MENU: [ *prompt_menu_handlers, CallbackQueryHandler(callback_handlers.show_moderate_settings_menu, pattern=f"^{CallbackPrefix.BACK_TO_MODERATION_SETTINGS}$"), ],
            MODERATION_MODEL_MENU: [ CallbackQueryHandler(callback_handlers.set_moderation_model, pattern=f"^{CallbackPrefix.MODERATE_SET_MODEL}"), CallbackQueryHandler(callback_handlers.show_moderate_settings_menu, pattern=f"^{CallbackPrefix.BACK_TO_MODERATION_SETTINGS}$"), ],
            SANCTIONS_MENU: [ CallbackQueryHandler(callback_handlers.sanction_request_value, pattern=f"^{CallbackPrefix.SANCTION_SET}"), CallbackQueryHandler(callback_handlers.show_moderate_settings_menu, pattern=f"^{CallbackPrefix.BACK_TO_MODERATION_SETTINGS}$"), ],
            USERS_MENU: [ CallbackQueryHandler(callback_handlers.reset_user_warnings, pattern=f"^{CallbackPrefix.RESET_WARNS}"), CallbackQueryHandler(callback_handlers.show_moderate_settings_menu, pattern=f"^{CallbackPrefix.BACK_TO_MODERATION_SETTINGS}$"), ],
            MANAGE_TRIGGERS: [ CallbackQueryHandler(callback_handlers.request_items_add, pattern=f"^{CallbackPrefix.TRIGGERS_ADD}$"), CallbackQueryHandler(callback_handlers.request_items_delete, pattern=f"^{CallbackPrefix.TRIGGERS_DELETE}$"), CallbackQueryHandler(callback_handlers.reset_items, pattern=f"^{CallbackPrefix.TRIGGERS_RESET}$"), CallbackQueryHandler(callback_handlers.show_moderate_settings_menu, pattern=f"^{CallbackPrefix.BACK_TO_MODERATION_SETTINGS}$"), ],
            MANAGE_EXCEPTIONS: [ CallbackQueryHandler(callback_handlers.request_items_add, pattern=f"^{CallbackPrefix.EXCEPTIONS_ADD}$"), CallbackQueryHandler(callback_handlers.request_items_delete, pattern=f"^{CallbackPrefix.EXCEPTIONS_DELETE}$"), CallbackQueryHandler(callback_handlers.reset_items, pattern=f"^{CallbackPrefix.EXCEPTIONS_RESET}$"), CallbackQueryHandler(callback_handlers.show_moderate_settings_menu, pattern=f"^{CallbackPrefix.BACK_TO_MODERATION_SETTINGS}$"), ],
            
            AWAIT_PROMPT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handlers.handle_prompt_message)],
            AWAIT_GENERATION_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, callback_handlers.set_generation_value)],
            AWAIT_CONTEXT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, callback_handlers.set_context_value)],
            AWAIT_SANCTION_VALUE: [ MessageHandler(filters.TEXT & ~filters.COMMAND, callback_handlers.sanction_set_value), CallbackQueryHandler(callback_handlers.show_sanctions_menu, pattern=f"^{CallbackPrefix.BACK_TO_SANCTIONS_MENU}$"),],
            AWAIT_TRIGGERS_TO_ADD: [MessageHandler(filters.TEXT & ~filters.COMMAND, callback_handlers.handle_triggers_add)],
            AWAIT_TRIGGERS_TO_DELETE: [MessageHandler(filters.TEXT & ~filters.COMMAND, callback_handlers.handle_triggers_delete)],
            AWAIT_EXCEPTIONS_TO_ADD: [MessageHandler(filters.TEXT & ~filters.COMMAND, callback_handlers.handle_exceptions_add)],
            AWAIT_EXCEPTIONS_TO_DELETE: [MessageHandler(filters.TEXT & ~filters.COMMAND, callback_handlers.handle_exceptions_delete)],
        },
        fallbacks=[
            CommandHandler("cancel", admin_handlers.cancel_conversation),
            CallbackQueryHandler(admin_handlers.cancel_conversation, pattern=f"^{CallbackPrefix.CLOSE_MENU}$"),
            CallbackQueryHandler(callback_handlers.show_moderate_settings_menu, pattern=f"^{CallbackPrefix.BACK_TO_MODERATION_SETTINGS}$"),
            CallbackQueryHandler(callback_handlers.show_facilitator_settings_menu, pattern=f"^{CallbackPrefix.BACK_TO_FACILITATOR_SETTINGS}$"),
        ],
        per_message=False,
        allow_reentry=True,
    )
