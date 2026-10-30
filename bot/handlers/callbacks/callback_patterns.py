# NVC_bot/bot/handlers/callbacks/callback_patterns.py
# version: 3.0.0
# 2026-10-30T16:30:00Z

'''
Централизованное хранилище префиксов и констант для callback_data инлайн-кнопок.

Version 3.0.0:
- ADD: Константы для переключения мягкого режима пре-модерации (`MODERATE_SOFT_TOGGLE`),
       автоамнистии в меню санкций (`SANCTION_TOGGLE_AMNESTY`, `SANCTION_CYCLE_AMNESTY_DAYS`)
       и проактивного фасилитатора споров (`TOGGLE_PROACTIVE_FACILITATOR`).
'''


class CallbackPrefix:
    '''Префиксы и точные идентификаторы callback_data для инлайн-меню.'''

    # --- Общие действия ---
    CLOSE_MENU = "close_menu"

    # --- Ветвь /settings (Фасилитатор) ---
    BACK_TO_FACILITATOR_SETTINGS = "back_to_facilitator_settings"
    FACILITATOR_MODEL = "facilitator_model"
    FACILITATOR_SET_MODEL = "facilitator_set_model_"
    FACILITATOR_PROMPT = "facilitator_prompt"
    FACILITATOR_STATS = "facilitator_stats"
    TOGGLE_DEBUG_MODE = "toggle_debug_mode"
    TOGGLE_PROACTIVE_FACILITATOR = "toggle_proactive_facilitator"

    # --- Подменю Генерации и Контекста ---
    GENERATION_SETTINGS = "generation_settings"
    GEN_CONFIG_EDIT = "gen_config_edit_"
    GEN_CONFIG_RESET = "gen_config_reset"
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
    MODERATE_SOFT_TOGGLE = "moderate_soft_toggle"
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

    # --- Подменю Санкций и Автоамнистии ---
    SANCTION_SET = "sanction_set_"
    SANCTION_TOGGLE_AMNESTY = "sanction_toggle_amnesty"
    SANCTION_CYCLE_AMNESTY_DAYS = "sanction_cycle_amnesty_days"
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