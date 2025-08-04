# NVC_bot/bot/handlers/states.py
# version: 1.1.0
# 2025-07-28T18:00:00Z
"""
Централизованное хранилище констант состояний для ConversationHandler.

Этот модуль определяет все состояния диалога как целые числа.
Он не имеет внутренних зависимостей от других модулей проекта,
чтобы предотвратить циклические импорты.

Version 1.1.0:
- ADD: Добавлены состояния для управления настройками контекста.
"""

(
    # Главные меню
    FACILITATOR_SETTINGS,
    MODERATION_SETTINGS,

    # Подменю настроек Фасилитатора
    FACILITATOR_PROMPT_MENU,
    WELCOME_MENU,
    WELCOME_MODEL_MENU,
    WELCOME_PROMPT_MENU,
    GENERATION_SETTINGS,
    CONTEXT_SETTINGS,           # NEW

    # Подменю настроек Модерации
    MODERATION_PROMPT_MENU,
    MODERATION_TEMPLATE_MENU,
    MODERATION_MODEL_MENU,
    SANCTIONS_MENU,
    USERS_MENU,
    MANAGE_TRIGGERS,
    MANAGE_EXCEPTIONS,

    # Состояния ожидания ввода от пользователя
    AWAIT_PROMPT_INPUT,
    AWAIT_GENERATION_VALUE,
    AWAIT_CONTEXT_VALUE,        # NEW
    AWAIT_SANCTION_VALUE,
    AWAIT_TRIGGERS_TO_ADD,
    AWAIT_TRIGGERS_TO_DELETE,
    AWAIT_EXCEPTIONS_TO_ADD,
    AWAIT_EXCEPTIONS_TO_DELETE,
) = range(23)
