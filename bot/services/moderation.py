# NVC_bot/bot/services/moderation.py
# version: 3.0.0
# 2026-10-30T06:30:00Z
"""
Сервис, отвечающий за модерацию сообщений в чате.

Version 3.0.0:
- PERF/FIX: Проверка локальных триггеров и исключений теперь выполняется ДО
            сетевого вызова `get_chat_administrators`, а список админов чата
            кэшируется на 5 минут (защита от HTTP 429 Too Many Requests).
- FIX: Использование `ChatPermissions(can_send_messages=False)` и UTC-времени
       `datetime.now(timezone.utc)` для `restrict_chat_member`.
- FIX: Использование `safe_format_template` вместо `.format()` (устранение KeyError).
- FIX: Добавлен fallback на отправку plain text при ошибке парсинга Markdown в `handle_violation`,
       а также запись сообщения нарушителя и ответа бота в историю чата.
"""
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Set, Tuple
from telegram import Update, ChatPermissions
from telegram.ext import ContextTypes
from telegram.error import TelegramError, BadRequest
from telegram.constants import ParseMode

from ..database import Database
from .gemini import GeminiService
from ..utils.formatters import safe_format_template

logger = logging.getLogger(__name__)

ADMIN_CACHE_TTL_SECONDS = 300.0


class ModerationService:
    """
    Инкапсулирует логику проверки сообщений и применения санкций.
    """

    def __init__(self, db: Database, gemini: GeminiService):
        self.db = db
        self.gemini = gemini
        self._admin_cache: Dict[int, Tuple[float, Set[int]]] = {}

    async def _is_user_chat_admin(self, chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE, trace_id: str) -> bool:
        """Проверяет, является ли пользователь администратором чата, с TTL-кэшем 5 минут."""
        now = time.monotonic()
        cached = self._admin_cache.get(chat_id)
        if cached and (now - cached[0]) < ADMIN_CACHE_TTL_SECONDS:
            return user_id in cached[1]

        try:
            chat_admins = await context.bot.get_chat_administrators(chat_id)
            admin_ids = {admin.user.id for admin in chat_admins}
            self._admin_cache[chat_id] = (now, admin_ids)
            return user_id in admin_ids
        except TelegramError as e:
            logger.warning("Не удалось получить список админов чата %d: %s", chat_id, e, extra={'trace_id': trace_id})
            return False

    async def check_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE, trace_id: str) -> bool:
        if not await self.db.is_moderation_enabled():
            return False

        user = update.effective_user
        chat = update.effective_chat
        text = update.message.text if update.message else None

        if not all([user, chat, text]):
            return False

        text_lower = text.lower()

        # 1. Сначала проверяем локальные триггеры и исключения (быстро, без сетевых запросов к Telegram API)
        triggers = await self.db.get_all_triggers_flat()
        if not any(re.search(r'\b' + re.escape(trigger) + r'\b', text_lower) for trigger in triggers):
            return False

        exceptions = await self.db.get_all_exceptions_flat()
        if any(exc in text_lower for exc in exceptions):
            logger.debug("Найден триггер и исключение. Проверка AI отменена.", extra={'trace_id': trace_id})
            return False

        # 2. Только если сработал триггер, проверяем, не админ ли автор сообщения (с кэшем)
        if await self._is_user_chat_admin(chat.id, user.id, context, trace_id):
            return False

        logger.info("Сообщение передается AI-судье.", extra={'trace_id': trace_id})
        prompt_template = await self.db.get_moderation_prompt()
        model_id = await self.db.get_moderation_model()

        return await self.gemini.get_moderation_verdict(text, prompt_template, model_id, trace_id)

    def _format_rules_list(self, rules: List[Dict]) -> str:
        if not rules:
            return "Правила санкций не настроены."
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
        if not all([user, chat, message]):
            return

        await self.db.increment_moderation_actions()
        new_warnings_count = await self.db.adjust_warnings(user.id, 1)
        logger.info("Пользователю %s выдано предупреждение. Всего: %d", user.id, new_warnings_count, extra={'trace_id': trace_id})

        sanction_rules = await self.db.get_sanction_rules()
        applied_sanction = next(
            (r for r in sorted(sanction_rules, key=lambda x: x['warnings'], reverse=True) if new_warnings_count >= r['warnings']),
            None
        )

        if applied_sanction:
            action, duration = applied_sanction['action'], applied_sanction.get('duration_hours')
            try:
                if action == 'MUTE' and duration:
                    until_dt = datetime.now(timezone.utc) + timedelta(hours=duration)
                    await context.bot.restrict_chat_member(
                        chat_id=chat.id,
                        user_id=user.id,
                        permissions=ChatPermissions(can_send_messages=False),
                        until_date=until_dt
                    )
                    logger.info("Пользователь %s замьючен в чате %s на %d часов.", user.id, chat.id, duration, extra={'trace_id': trace_id})
                elif action == 'BAN':
                    await context.bot.ban_chat_member(chat.id, user.id)
                    logger.info("Пользователь %s забанен в чате %s.", user.id, chat.id, extra={'trace_id': trace_id})
            except Exception as e:
                logger.error("Не удалось применить санкцию '%s' для %s: %s", action, user.id, e, extra={'trace_id': trace_id})

        user_display_mention = f"@{user.username}" if user.username else user.full_name

        try:
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

            formatted_instruction = safe_format_template(
                task_instruction_template,
                user_mention=user_display_mention,
                violator_message=text,
                warnings_count=new_warnings_count,
                rules_list=self._format_rules_list(sanction_rules),
                chat_history=history_str,
                group_rules=chat_description
            )

            ai_response, _ = await self.gemini.generate_response(
                question="",
                task_instruction=formatted_instruction,
                trace_id=trace_id,
                chat_description=chat_description
            )
        except Exception as e:
            logger.error("Ошибка при генерации ответа AI-фасилитатором: %s", e, exc_info=True, extra={'trace_id': trace_id})
            ai_response = f"⚠️ {user_display_mention}, ваше сообщение было расценено как 'ты-сообщение'. У вас {new_warnings_count} предупреждение(й)."

        # Сохраняем сообщение нарушителя и ответ модератора в историю чата
        await self.db.add_message(chat.id, user.full_name, text, is_bot=False)
        if ai_response:
            await self.db.add_message(chat.id, "bot", ai_response, is_bot=True)
            try:
                await message.reply_text(text=ai_response, parse_mode=ParseMode.MARKDOWN)
            except BadRequest as e:
                logger.warning("Ошибка парсинга Markdown в сообщении модерации (%s), отправляю без форматирования.", e, extra={'trace_id': trace_id})
                try:
                    await message.reply_text(text=ai_response)
                except TelegramError as fallback_err:
                    logger.error("Не удалось отправить сообщение о нарушении: %s", fallback_err, extra={'trace_id': trace_id})
