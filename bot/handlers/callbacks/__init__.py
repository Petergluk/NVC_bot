# NVC_bot/bot/handlers/callbacks/__init__.py
# version: 1.4.0
# 2025-07-28T18:00:00Z
"""
Основной пакет для обработчиков инлайн-кнопок.

Этот __init__.py собирает все части обработчиков из отдельных модулей
в один главный класс `CallbackHandlers` для удобства использования в других частях приложения.

Version 1.4.0:
- ADD: Добавлен `ContextCallbackHandler` для управления параметрами контекста.
"""
from .base import BaseCallbackHandler
from .facilitator import FacilitatorCallbackHandler
from .items import ItemCallbackHandler
from .moderation import ModerationCallbackHandler
from .prompts import PromptCallbackHandler
from .welcome import WelcomeCallbackHandler
from .generation import GenerationCallbackHandler
from .context import ContextCallbackHandler

class CallbackHandlers(
    ContextCallbackHandler,
    GenerationCallbackHandler,
    WelcomeCallbackHandler,
    FacilitatorCallbackHandler,
    ModerationCallbackHandler,
    ItemCallbackHandler,
    PromptCallbackHandler,
    # Base должен идти последним в MRO для `__init__`
    BaseCallbackHandler
):
    """
    Агрегирующий класс, который объединяет все обработчики обратных вызовов.
    Наследует функциональность из разделенных по логике классов-миксинов.
    """
    def __init__(self, db, gemini_service):
        """
        Инициализирует все базовые классы.
        """
        super().__init__(db, gemini_service)
