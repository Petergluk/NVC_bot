# NVC_bot/bot/handlers/direct.py
# Version: 1.2
# Last modified: 2025-08-04
"""
Обработчик личных сообщений, адресованных боту.

Изменения в версии 1.2:
- Вызов метода `gemini.generate_response` обновлен для использования
  параметра `content` вместо `question` в соответствии с обновлением сервиса.
"""
import logging
from telegram import Update
from telegram.ext import ContextTypes
from ..database import Database
from ..services.gemini import GeminiService

logger = logging.getLogger(__name__)

class DirectHandler:
    """Обрабатывает сообщения в личных чатах с ботом."""

    def __init__(self, db: Database, gemini_service: GeminiService, config: dict):
        self.db = db
        self.gemini = gemini_service
        self.config = config

    async def on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отвечает на прямое сообщение пользователя."""
        chat_id = update.message.chat_id
        user_message = update.message.text

        if not user_message:
            return

        try:
            # Получаем глобальные настройки для прямого диалога
            core_prompt = await self.db.get_prompt('core_prompt', self.config['prompts']['core'])
            direct_prompt = await self.db.get_prompt('direct_prompt', self.config['prompts']['direct'])
            system_instruction = f"{core_prompt}\n\n{direct_prompt}"
            model_id = await self.db.get_setting('main_model', self.config['models']['main'])

            # TODO: Реализовать получение истории чата для контекста
            chat_history = []

            response_text = await self.gemini.generate_response(
                content=user_message, # ИЗМЕНЕНО: question -> content
                system_instruction=system_instruction,
                model_id=model_id,
                chat_history=chat_history
            )
            await update.message.reply_text(response_text, parse_mode='HTML')

        except Exception as e:
            logger.error(f"Ошибка при обработке прямого сообщения от {chat_id}: {e}", exc_info=True)
            await update.message.reply_text("К сожалению, произошла внутренняя ошибка. Я уже сообщил о ней своим создателям.")
