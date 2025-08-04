# NVC_bot/bot/utils/decorators.py
"""
Модуль с декораторами для логирования, проверки прав и обратной связи.
"""
import functools
import logging
from typing import Callable, Any
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatAction

# --- ИСПРАВЛЕНИЕ: Импортируем уже обработанный список ADMIN_IDS ---
from ..config import ADMIN_IDS

logger = logging.getLogger(__name__)

# --- ИСПРАВЛЕНИЕ: Преобразуем готовый список ID в множество для быстрой проверки ---
# Логика парсинга и обработки ошибок теперь централизована в config.py.
ADMIN_IDS_SET = set(ADMIN_IDS)
if not ADMIN_IDS_SET:
    logger.warning("Список ADMIN_IDS пуст или не задан в .env. "
                   "Административные команды будут недоступны.")


def admin_only(func: Callable) -> Callable:
    """
    Декоратор, который проверяет, является ли пользователь администратором.
    Разрешает выполнение функции только для пользователей, чьи ID есть в ADMIN_IDS_SET.
    """
    @functools.wraps(func)
    async def wrapper(self: Any, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs) -> Any:
        """Внутренняя обертка, выполняющая проверку."""
        if not update.effective_user:
            logger.warning("Не удалось определить пользователя для проверки прав доступа.")
            return None
        
        user_id = update.effective_user.id
        
        # --- ИСПРАВЛЕНИЕ: Используем ADMIN_IDS_SET для проверки ---
        if user_id not in ADMIN_IDS_SET:
            logger.warning("Пользователь %d попытался выполнить команду только для администраторов: %s",
                         user_id, func.__name__)
            # Проверяем, есть ли у сообщения атрибут message, чтобы ответить
            if update.message:
                await update.message.reply_text("⛔ У вас нет прав для выполнения этой команды.")
            return None
            
        return await func(self, update, context, *args, **kwargs)
        
    return wrapper


def log_action(action_name: str) -> Callable:
    """
    Декоратор для логирования действий пользователя.
    
    Args:
        action_name (str): Название действия для отображения в логе.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(self: Any, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs) -> Any:
            """Внутренняя обертка, выполняющая логирование."""
            user = update.effective_user
            chat = update.effective_chat
            
            if user and chat:
                log_message = (
                    f"Действие '{action_name}' вызвано пользователем {user.full_name} "
                    f"(ID: {user.id}, Username: @{user.username}) "
                    f"в чате '{getattr(chat, 'title', 'личный чат')}' (ID: {chat.id}, Type: {chat.type})."
                )
                logger.info(log_message)
            else:
                logger.info("Действие '%s' вызвано без определения пользователя/чата.", action_name)

            return await func(self, update, context, *args, **kwargs)
            
        return wrapper
    return decorator


def typing_action(func: Callable) -> Callable:
    """
    Декоратор, который отправляет действие 'typing...' в чат.
    Это дает пользователю понять, что бот обрабатывает запрос.
    """
    @functools.wraps(func)
    async def wrapper(self: Any, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs) -> Any:
        """Внутренняя обертка, отправляющая действие."""
        if update.effective_chat:
            # Отправляем действие "печатает..." перед выполнением основной логики
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id,
                action=ChatAction.TYPING
            )
        # Выполняем оригинальную функцию
        return await func(self, update, context, *args, **kwargs)
        
    return wrapper