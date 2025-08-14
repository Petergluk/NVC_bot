# NVC_bot/bot/services/moderation.py
# version: 4.4.0
# 2025-08-14T13:00:00Z
"""
Сервис, отвечающий за модерацию сообщений в чате.

Version 4.4.0:
- FIX: Убрано некорректное экранирование Markdown-символов
       при подготовке данных для AI, что искажало смысл
       передаваемого контекста.

Version 4.3.0:
- FIX: Убран аргумент `model_id` из вызова `gemini.get_moderation_verdict`.
"""
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Any
from telegram import Message
from telegram.ext import ContextTypes
from telegram.error import TelegramError, BadRequest
from telegram.constants import ParseMode

from ..database import Database
from .gemini import GeminiService
from ..utils.formatters import escape_markdown_v2

logger = logging.getLogger(__name__)

class ModerationService:
    """
    Инкапсулирует логику проверки сообщений и применения санкций.
    """

    def __init__(self, db: Database, gemini: GeminiService):
        self.db = db
        self.gemini = gemini

    async def check_message(self, message: Message, context: ContextTypes.DEFAULT_TYPE, trace_id: str) -> bool:
        if not await self.db.is_moderation_enabled(): return False
        user, chat, text = message.from_user, message.chat, message.text
        if not all([user, chat, text]): return False
        
        try:
            if user.id in {admin.user.id for admin in await context.bot.get_chat_administrators(chat.id)}:
                return False
        except TelegramError as e:
            logger.warning("Не удалось получить список админов чата %d: %s", chat.id, e, extra={'trace_id': trace_id})

        text_lower = text.lower()
        triggers = await self.db.get_all_triggers_flat()
        exceptions = await self.db.get_all_exceptions_flat()

        if not any(re.search(r'\b' + re.escape(trigger) + r'\b', text_lower, re.IGNORECASE) for trigger in triggers):
            return False
        if any(exc in text_lower for exc in exceptions):
            return False
        
        logger.info("Сообщение передается AI-судье.", extra={'trace_id': trace_id})
        
        context_config = await self.db.get_context_config()
        history_list = await self.db.get_chat_history(chat.id, context_config["context_judge_limit"])
        history_str = self._format_history_for_template(history_list)
        prompt_template = await self.db.get_moderation_prompt()
        is_debug_mode = await self.db.is_debug_mode_enabled()
        
        return await self.gemini.get_moderation_verdict(text, prompt_template, trace_id, is_debug_mode, history_str)

    def _format_history_for_template(self, history: List[Dict[str, Any]]) -> str:
        if not history: return "Контекст диалога пуст."
        messages_by_id = {msg['message_id']: msg for msg in history}
        lines = []
        for msg in history:
            line = f"{msg.get('user_name', 'bot')}:"
            if reply_id := msg.get('reply_to_message_id'):
                if reply_msg := messages_by_id.get(reply_id):
                    line += f" (в ответ на «{(reply_msg.get('text') or '')[:50]}...» от {reply_msg.get('user_name', 'unknown')})"
            line += f"\n> {msg.get('text', '')}"
            lines.append(line)
        return "\n\n".join(lines)

    def _format_sanction_rules(self, rules: List[Dict]) -> str:
        """
        Форматирует правила санкций в человекочитаемый Markdown-список.
        """
        if not rules:
            return "Правила санкций не настроены."

        def get_duration_text(hours: int) -> str:
            if hours == 1: return "1 час"
            if 2 <= hours <= 4: return f"{hours} часа"
            if hours == 24: return "1 сутки"
            if hours == 168: return "7 суток (неделю)"
            return f"{hours} часов"

        lines = ["Действующие в чате правила применения санкций:"]
        for rule in sorted(rules, key=lambda x: x['warnings']):
            warnings_count = rule['warnings']
            action = rule['action']
            
            if action == 'BAN':
                action_text = "полная блокировка в чате (бан)"
            elif action == 'MUTE' and 'duration_hours' in rule and rule['duration_hours']:
                duration_text = get_duration_text(rule['duration_hours'])
                action_text = f"временное ограничение на отправку сообщений (мьют) на {duration_text}"
            else:
                continue
            lines.append(f"• Накопление {warnings_count} предупреждений приводит к: {action_text}.")
        return "\n".join(lines)

    async def handle_violation(self, message: Message, context: ContextTypes.DEFAULT_TYPE, trace_id: str) -> None:
        user, chat, text = message.from_user, message.chat, message.text
        if not all([user, chat, text]): return

        await self.db.increment_moderation_actions()
        new_warnings_count = await self.db.adjust_warnings(user.id, 1)
        logger.info("Пользователю %s (%s) выдано предупреждение. Всего: %d", user.full_name, user.id, new_warnings_count, extra={'trace_id': trace_id})
        
        sanction_rules = await self.db.get_sanction_rules()
        applied_sanction = next((r for r in sorted(sanction_rules, key=lambda x: x['warnings'], reverse=True) if new_warnings_count >= r['warnings']), None)

        try:
            chat_description = (await context.bot.get_chat(chat.id)).description or "Правила группы не указаны."
        except Exception as e:
            logger.warning("Не удалось получить описание чата %d: %s", chat.id, e, extra={'trace_id': trace_id})
            chat_description = "Правила группы не указаны."

        task_template = await self.db.get_moderation_task_template()
        context_config = await self.db.get_context_config()
        history_list = await self.db.get_chat_history(chat.id, context_config["context_judge_limit"])
        
        # FIX: Убрано экранирование для переменных, отправляемых в AI.
        # Они должны быть в "сыром" виде.
        formatted_task_content = task_template.replace('{user_mention}', user.mention_markdown_v2()) # Этот уже экранирован
        formatted_task_content = formatted_task_content.replace('{violator_message}', text) # Без экранирования
        formatted_task_content = formatted_task_content.replace('{warnings_count}', str(new_warnings_count))
        formatted_task_content = formatted_task_content.replace('{chat_history}', self._format_history_for_template(history_list)) # Без экранирования
        formatted_task_content = formatted_task_content.replace('{group_rules}', chat_description) # Без экранирования
        formatted_task_content = formatted_task_content.replace('{moderation_rules}', self._format_sanction_rules(sanction_rules)) # Без экранирования
        formatted_task_content = formatted_task_content.replace('{bot_username}', f'@{context.bot.username}')
        
        is_debug_mode = await self.db.is_debug_mode_enabled()
        ai_response = ""
        
        try:
            ai_response, _, _ = await self.gemini.generate_response(
                question=formatted_task_content,
                chat_history=history_list,
                trace_id=trace_id,
                request_type="VIOLATION_MESSAGE",
                is_debug_mode=is_debug_mode
            )
        except Exception as e:
            logger.error("Ошибка при генерации ответа AI-фасилитатором: %s", e, exc_info=True, extra={'trace_id': trace_id})
            fallback_sanction = "Применена санкция в соответствии с правилами." if applied_sanction else ""
            ai_response = f"⚠️ {user.mention_markdown_v2()}, ваше сообщение было расценено как оценочное суждение. Это ваше *{new_warnings_count}*-е предупреждение. {fallback_sanction}"

        if ai_response:
            try:
                # Отправляем ответ с parse_mode=Markdown, т.к. AI должен генерировать валидную разметку
                await message.reply_text(text=ai_response, parse_mode=ParseMode.MARKDOWN)
            except BadRequest as e:
                if "Can't parse entities" in str(e):
                    # Если AI вернул некорректный Markdown, отправляем как простой текст
                    await message.reply_text(text=re.sub(r'[*_`\[\]()~>#+\-=|{}.!]', '', ai_response))
                else: 
                    logger.error("Неожиданная ошибка BadRequest: %s", e, extra={'trace_id': trace_id})

        if applied_sanction:
            action, duration = applied_sanction['action'], applied_sanction.get('duration_hours')
            try:
                if action == 'MUTE' and duration:
                    await context.bot.restrict_chat_member(chat.id, user.id, permissions={'can_send_messages': False}, until_date=datetime.now() + timedelta(hours=duration))
                    logger.info("Пользователь %s замьючен на %d часов.", user.id, duration, extra={'trace_id': trace_id})
                elif action == 'BAN':
                    await context.bot.ban_chat_member(chat.id, user.id)
                    logger.info("Пользователь %s забанен.", user.id, extra={'trace_id': trace_id})
            except Exception as e:
                logger.error("Не удалось применить санкцию '%s' для %s: %s", action, user.id, e, extra={'trace_id': trace_id})
