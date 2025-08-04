# NVC_bot/bot/handlers/callbacks/base.py
# version: 1.1.0
# 2025-07-28T21:00:00Z
"""
Базовый класс и общие вспомогательные методы для обработчиков инлайн-кнопок.

Version 1.1.0:
- FIX: Улучшена обработка исключений в `_safe_edit_message` для более
       точного логирования ошибок `Message is too long` и `Message is not modified`.
"""
import logging
from typing import Any

from telegram import CallbackQuery, Message
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from ...database import Database
from ...services.gemini import GeminiService

logger = logging.getLogger(__name__)

class BaseCallbackHandler:
    """Содержит общие методы для всех обработчиков колбэков."""

    def __init__(self, db: Database, gemini: GeminiService) -> None:
        """
        Инициализация базового обработчика.

        Args:
            db (Database): Экземпляр для работы с базой данных.
            gemini (GeminiService): Экземпляр для работы с Gemini API.
        """
        self.db = db
        self.gemini = gemini

    async def _safe_edit_message(self, query: CallbackQuery, text: str, **kw: Any) -> Message | None:
        """Безопасно редактирует сообщение, на которое нажал пользователь."""
        if not query or not query.message:
            logger.warning("Попытка редактировать сообщение без query или query.message.")
            return None
        try:
            # Мы не обрезаем текст здесь, чтобы иметь возможность отловить ошибку о длине
            return await query.message.edit_text(text, **kw)
        except BadRequest as exc:
            # FIX: Детальная обработка исключений BadRequest
            if "Message is too long" in str(exc):
                logger.warning("Не удалось отредактировать сообщение: превышен лимит длины (4096 символов).")
                await self._safe_answer_query(query, "❌ Ошибка: Слишком много текста для отображения.", show_alert=True)
            elif "Message is not modified" in str(exc):
                # Это не ошибка, просто игнорируем
                await self._safe_answer_query(query)
            else:
                logger.error("Telegram BadRequest при редактировании сообщения: %s", exc)
                await self._safe_answer_query(query, "Произошла ошибка при обновлении меню.", show_alert=True)
            return None

    async def _safe_answer_query(self, query: CallbackQuery | None, *args, **kwargs) -> None:
        """Безопасно отвечает на callback query, игнорируя устаревшие."""
        if not query: return
        try:
            await query.answer(*args, **kwargs)
        except BadRequest as e:
            if "Query is too old" in str(e):
                logger.warning("Попытка ответить на устаревший query. Игнорируется.")
            else:
                logger.error("Неожиданная ошибка BadRequest при ответе на query: %s", e)
    
    async def _disable_keyboard(self, query: CallbackQuery) -> None:
        """Безопасно удаляет клавиатуру у сообщения."""
        if not query or not query.message: return
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                logger.warning("Не удалось убрать клавиатуру: %s", e)
