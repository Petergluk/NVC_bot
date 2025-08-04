# NVC_bot/bot/handlers/callbacks/callback_patterns.py
# version: 1.1.0
# 2025-07-28T18:00:00Z
"""
Централизованное хранилище для всех строк `callback_data`.

Этот модуль устраняет "магические строки" из кода, предоставляя
константы для всех идентификаторов, используемых в Inline-кнопках.
Это повышает надежность и упрощает поддержку.

Version 1.1.0:
- ADD: Добавлены префиксы для управления настройками контекста.
"""

class CallbackPrefix:
    """
    Класс-пространство имен для всех префиксов и полных идентификаторов callback_data.
    """
    # --- Общие ---
    CLOSE_MENU = "close_menu"

    # --- Ветвь /settings (Фасилитатор) ---
    BACK_TO_FACILITATOR_SETTINGS = "back_to_facilitator_settings"
    FACILITATOR_MODEL = "facilitator_model"
    FACILITATOR_SET_MODEL = "facilitator_set_model_"
    FACILITATOR_STATS = "facilitator_stats"
    FACILITATOR_PROMPT = "facilitator_prompt"
    TOGGLE_DEBUG_MODE = "toggle_debug_mode"

    # --- Подменю Параметров Генерации ---
    GENERATION_SETTINGS = "generation_settings"
    GEN_CONFIG_EDIT = "gen_config_edit_"
    GEN_CONFIG_RESET = "gen_config_reset"

    # --- Подменю Настроек Контекста ---
    CONTEXT_SETTINGS = "context_settings"
    CONTEXT_CONFIG_EDIT = "context_config_edit_"
    CONTEXT_CONFIG_RESET = "context_config_reset"

    # --- Подменю Приветствий ---
    WELCOMES_MENU = "welcomes_menu"
    BACK_TO_WELCOMES_MENU = "back_to_welcomes_menu"
    WELCOMES_TOGGLE = "welcomes_toggle"
    WELCOMES_MODEL = "welcomes_model"
    WELCOMES_PROMPT = "welcomes_prompt"
    WELCOMES_SET_MODEL = "welcomes_set_model_"

    # --- Ветвь /moderate (Модерация) ---
    BACK_TO_MODERATION_SETTINGS = "back_to_moderation_settings"
    MODERATE_TOGGLE = "moderate_toggle"
    MODERATE_PROMPT = "moderate_prompt"
    MODERATE_TEMPLATE = "moderate_template"
    MODERATE_MODEL = "moderate_model"
    MODERATE_SET_MODEL = "moderate_set_model_"
    MODERATE_SANCTIONS = "moderate_sanctions"
    MODERATE_USERS = "moderate_users"
    MANAGE_TRIGGERS = "manage_triggers"
    MANAGE_EXCEPTIONS = "manage_exceptions"

    # --- Подменю Триггеров и Исключений ---
    TRIGGERS_ADD = "triggers_add"
    TRIGGERS_DELETE = "triggers_delete"
    TRIGGERS_RESET = "triggers_reset"
    EXCEPTIONS_ADD = "exceptions_add"
    EXCEPTIONS_DELETE = "exceptions_delete"
    EXCEPTIONS_RESET = "exceptions_reset"

    # --- Подменю Санкций ---
    SANCTION_SET = "sanction_set_"
    BACK_TO_SANCTIONS_MENU = "back_to_sanctions_menu"
    RESET_WARNS = "reset_warns_"

    # --- Управление Промптами ---
    SEND_FULL_PROMPT = "send_full_prompt_"
    EDIT_FACILITATOR_PROMPT = "edit_facilitator_prompt"
    RESET_FACILITATOR_PROMPT = "reset_facilitator_prompt"
    EDIT_MODERATION_PROMPT = "edit_moderation_prompt"
    RESET_MODERATION_PROMPT = "reset_moderation_prompt"
    EDIT_MODERATION_TEMPLATE = "edit_moderation_template"
    RESET_MODERATION_TEMPLATE = "reset_moderation_template"
    EDIT_WELCOME_PROMPT = "edit_welcome_prompt"
    RESET_WELCOME_PROMPT = "reset_welcome_prompt"
