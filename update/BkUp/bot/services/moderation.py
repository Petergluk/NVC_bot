# NVC_bot/bot/services/moderation.py
# version: 2.0.0
# 2025-07-30T14:00:00Z
"""
Сервис, отвечающий за модерацию сообщений в чате.

Version 2.0.0:
- REFACTOR: Адаптация к композитной архитектуре промптов.
            - `handle_violation` теперь передает `task_instruction` в `GeminiService`.
            - Реализована подстановка переменной `{{group_rules}}`.
            - История чата теперь передается как часть инструкции, а не отдельным
              аргументом, что упрощает вызов сервиса.

Version 1.8.1:
- REFACTOR: Адаптация к новому формату `get_chat_history`, возвращающему
            `List[Dict]`. Добавлена внутренняя функция для преобразования
            структурированной истории в строку для шаблона.
"""
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Any
from telegram import Update, ReplyParameters
from telegram.ext import ContextTypes
from telegram.error import TelegramError, BadRequest
from telegram.constants import ParseMode

from ..database import Database
from .gemini import GeminiService
from ..config import settings

logger = logging.getLogger(__name__)

class ModerationService:
    """
    Инкапсулирует логику проверки сообщений и применения санкций.
    """

    def __init__(self, db: Database, gemini: GeminiService):
        self.db = db
        self.gemini = gemini

    async def check_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE, trace_id: str) -> bool:
        if not await self.db.is_moderation_enabled():
            return False

        user = update.effective_user
        chat = update.effective_chat
        text = update.message.text

        if not all([user, chat, text]):
            return False
        
        text_lower = text.lower()

        try:
            chat_admins = await context.bot.get_chat_administrators(chat.id)
            admin_ids = {admin.user.id for admin in chat_admins}
            if user.id in admin_ids:
                return False
        except TelegramError as e:
            logger.warning("Не удалось получить список админов чата %d: %s", chat.id, e, extra={'trace_id': trace_id})

        triggers = await self.db.get_all_triggers_flat()
        exceptions = await self.db.get_all_exceptions_flat()

        if not any(re.search(r'\b' + re.escape(trigger) + r'\b', text_lower) for trigger in triggers):
            return False

        if any(exc in text_lower for exc in exceptions):
            logger.debug("Найден триггер и исключение. Проверка AI отменена.", extra={'trace_id': trace_id})
            return False

        logger.info("Сообщение передается AI-судье.", extra={'trace_id': trace_id})
        prompt_template = await self.db.get_moderation_prompt()
        model_id = await self.db.get_moderation_model()
        
        return await self.gemini.get_moderation_verdict(text, prompt_template, model_id, trace_id)

    def _format_rules_list(self, rules: List[Dict]) -> str:
        if not rules: return "Правила санкций не настроены."
        lines = []
        for rule in sorted(rules, key=lambda x: x['warnings']):
            action_desc = "бан" if rule['action'] == 'BAN' else f"мьют на {rule['duration_hours']} ч."
            lines.append(f"- {rule['warnings']} предупреждений: {action_desc}")
        return "\n".join(lines)

    def _format_history_for_template(self, history: List[Dict[str, Any]]) -> str:
        """Преобразует структурированную историю в простую строку."""
        if not history:
            return "Контекст диалога пуст."
        
        lines = []
        for item in history:
            role = item.get("role", "user")
            text = item.get("parts", [{}])[0].get("text", "")
            if role == "user":
                lines.append(f"user: {text}")
            else:
                lines.append(f"bot: {text}")
        return "\n".join(lines)

    async def handle_violation(self, update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, trace_id: str) -> None:
        user = update.effective_user
        chat = update.effective_chat
        message = update.message
        if not all([user, chat, message]): return

        await self.db.increment_moderation_actions()
        new_warnings_count = await self.db.adjust_warnings(user.id, 1)
        logger.info("Пользователю %s выдано предупреждение. Всего: %d", user.id, new_warnings_count, extra={'trace_id': trace_id})
        
        sanction_rules = await self.db.get_sanction_rules()
        applied_sanction = next((r for r in sorted(sanction_rules, key=lambda x: x['warnings'], reverse=True) if new_warnings_count >= r['warnings']), None)

        if applied_sanction:
            action, duration = applied_sanction['action'], applied_sanction.get('duration_hours')
            try:
                if action == 'MUTE' and duration:
                    await context.bot.restrict_chat_member(chat.id, user.id, permissions={'can_send_messages': False}, until_date=datetime.now() + timedelta(hours=duration))
                    logger.info("Пользователь %s замьючен в чате %s на %d часов.", user.id, chat.id, duration, extra={'trace_id': trace_id})
                elif action == 'BAN':
                    await context.bot.ban_chat_member(chat.id, user.id)
                    logger.info("Пользователь %s забанен в чате %s.", user.id, chat.id, extra={'trace_id': trace_id})
            except Exception as e:
                logger.error("Не удалось применить санкцию '%s' для %s: %s", action, user.id, e, extra={'trace_id': trace_id})

        try:
            # Получаем описание чата для переменной {{group_rules}}
            try:
                chat_full = await context.bot.get_chat(chat.id)
                chat_description = chat_full.description or "Правила группы не указаны."
            except Exception as e:
                logger.warning("Не удалось получить описание чата %d: %s", chat.id, e, extra={'trace_id': trace_id})
                chat_description = "Правила группы не указаны."

            task_instruction_template = await self.db.get_moderation_task_template()
            context_config = await self.db.get_context_config()
            
            history_list = await self.db.get_chat_history(chat.id, context_config["context_judge_limit"])
            history_str = self._format_history_for_template(history_list)
            
            # Собираем инструкцию, подставляя все переменные
            formatted_instruction = task_instruction_template.format(
                user_mention=user.mention_markdown_v2(), violator_message=text,
                warnings_count=new_warnings_count, rules_list=self._format_rules_list(sanction_rules),
                chat_history=history_str, group_rules=chat_description
            )
            
            # "Вопрос" пуст, так как вся задача полностью описана в инструкции
            ai_response, _ = await self.gemini.generate_response(
                question="",
                task_instruction=formatted_instruction,
                trace_id=trace_id
            )
        except Exception as e:
            logger.error("Ошибка при генерации ответа AI-фасилитатором: %s", e, exc_info=True, extra={'trace_id': trace_id})
            ai_response = f"⚠️ {user.mention_markdown_v2()}, ваше сообщение было расценено как 'ты-сообщение'. У вас {new_warnings_count} предупреждение(й)."

        if ai_response:
            try:
                await message.reply_text(text=ai_response, parse_mode=ParseMode.MARKDOWN)
            except BadRequest as e:
                logger.error("Ошибка BadRequest при отправке сообщения о нарушении: %s", e, extra={'trace_id': trace_id})
