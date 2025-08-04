# NVC_bot/bot/utils/context_helpers.py
# version: 1.0.0
# 2025-07-30T13:15:00Z
"""
Вспомогательные функции для работы с контекстом ConversationHandler.

Этот модуль предоставляет безопасные способы управления данными в `context.user_data`,
чтобы избежать случайного удаления внутренних ключей, используемых библиотекой
python-telegram-bot для отслеживания состояния диалога.

Зачем это нужно:
Прямой вызов `context.user_data.clear()` уничтожает ВСЕ данные, включая
служебные ключи, которые `ConversationHandler` использует для ведения
диалога. Это приводит к "амнезии" обработчика и непредсказуемому поведению.
Эта функция решает проблему, удаляя только те ключи, которые были явно
добавлены логикой нашего приложения.
"""
from telegram.ext import ContextTypes
import logging

logger = logging.getLogger(__name__)

def clear_conversation_user_data(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Безопасно очищает только те ключи из user_data, которые были установлены
    в ходе диалогов настроек, не затрагивая внутренние ключи PTB.

    Args:
        context (ContextTypes.DEFAULT_TYPE): Контекст бота, содержащий user_data.
    """
    # Список ключей, которые устанавливаются логикой нашего приложения в user_data
    # и должны быть очищены по завершении или отмене диалога.
    app_keys_to_clear = [
        "prompt_type",
        "prompt_buffer",
        "original_update",
        "prompt_commit_task",
        "context_param_key",
        "gen_param_key",
        "current_sanction",
        "trace_id",
    ]
    
    logger.debug("Очистка пользовательских ключей из user_data: %s", app_keys_to_clear)
    
    for key in app_keys_to_clear:
        if key in context.user_data:
            try:
                del context.user_data[key]
            except KeyError:
                # Это может произойти в редких случаях (например, при гонке состояний),
                # но это безопасно проигнорировать.
                pass
