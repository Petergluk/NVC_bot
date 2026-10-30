# NVC_bot/bot/services/moderation.py
# version: 6.0.0
# 2026-10-30T16:30:00Z

'''
Сервис, отвечающий за логику автоматической модерации сообщений.

Version 6.0.0:
- ADD: Мягкий режим пре-модерации: удаление токсичного оригинала в группе,
       отправка исходного текста и мягкой ННО-версии автору в ЛС (с fallback под спойлер,
       если ЛС закрыта) и публикация предупреждения с кнопкой «⚖️ Оспорить».
- ADD: Проактивный фасилитатор (авто-детект закипания спора при серии триггеров в чате).
- ADD: Интеграция с `ModerationVerdict` (Structured Outputs).
'''

import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Set, Tuple, Optional

from telegram import Update, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden, TelegramError

from ..config import settings
from ..database import Database
from .gemini import GeminiService, ModerationVerdict
from ..utils.formatters import safe_format_template

logger = logging.getLogger(__name__)

ADMIN_CACHE_TTL_SECONDS = 300  # 5 минут
PROACTIVE_WINDOW_SECONDS = 300  # 5 минут для детекта закипания спора


class ModerationService:
    '''Инкапсулирует логику проверки сообщений и применения санкций.'''

    def __init__(self, db: Database, gemini_service: GeminiService):
        self.db = db
        self.gemini = gemini_service
        self._admin_cache: Dict[int, Tuple[float, Set[int]]] = {}
        self._last_verdict_by_trace: Dict[str, ModerationVerdict] = {}
        self._recent_chat_triggers: Dict[int, List[float]] = {}

    async def _is_user_chat_admin(
        self, chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE, trace_id: str
    ) -> bool:
        '''Проверяет, является ли пользователь администратором чата, используя 5-минутный кэш.'''
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

    def _record_trigger_and_check_heated_dispute(self, chat_id: int) -> bool:
        '''Фиксирует срабатывание конфликтного триггера в чате и проверяет порог закипания спора.'''
        now = time.monotonic()
        recent = [ts for ts in self._recent_chat_triggers.get(chat_id, []) if (now - ts) <= PROACTIVE_WINDOW_SECONDS]
        recent.append(now)
        self._recent_chat_triggers[chat_id] = recent
        if len(recent) >= settings.DEFAULT_PROACTIVE_TRIGGER_THRESHOLD:
            self._recent_chat_triggers[chat_id] = []
            return True
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

        # 1. Локальные триггеры и исключения (мгновенно, без сетевых запросов к Telegram API)
        triggers = await self.db.get_all_triggers_flat()
        if not any(re.search(r'\b' + re.escape(trigger) + r'\b', text_lower) for trigger in triggers):
            return False

        exceptions = await self.db.get_all_exceptions_flat()
        if any(exc in text_lower for exc in exceptions):
            logger.debug("Найден триггер и исключение. Проверка AI отменена.", extra={'trace_id': trace_id})
            return False

        # Фиксируем триггер для проактивного детектора накала дискуссии
        is_heated = self._record_trigger_and_check_heated_dispute(chat.id)
        context.chat_data["heated_dispute_detected"] = is_heated

        # 2. Проверяем, не админ ли автор сообщения (с 5-минутным TTL-кэшем)
        if await self._is_user_chat_admin(chat.id, user.id, context, trace_id):
            return False

        logger.info("Сообщение передается AI-судье.", extra={'trace_id': trace_id})
        prompt_template = await self.db.get_moderation_prompt()
        model_id = await self.db.get_moderation_model()

        verdict_obj = await self.gemini.evaluate_moderation_structured(
            text=text,
            prompt_template=prompt_template,
            model_id=model_id,
            trace_id=trace_id
        )
        if len(self._last_verdict_by_trace) > 200:
            self._last_verdict_by_trace.clear()
        self._last_verdict_by_trace[trace_id] = verdict_obj
        return verdict_obj.is_violation

    async def maybe_intervene_in_heated_dispute(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, trace_id: str
    ) -> None:
        '''
        Если в чате накопилась серия конфликтных триггеров (даже без жесткого нарушения),
        проактивный фасилитатор мягко напоминает о потребностях сторон.
        '''
        if not context.chat_data.pop("heated_dispute_detected", False):
            return
        if not await self.db.is_proactive_facilitator_enabled():
            return
        chat = update.effective_chat
        if not chat:
            return
        try:
            context_config = await self.db.get_context_config()
            history_list = await self.db.get_chat_history(chat.id, min(8, context_config["context_messages_limit"]))
            note, _ = await self.gemini.generate_response(
                question="",
                task_instruction=(
                    "В чате нарастает эмоциональное напряжение (несколько резких реплик подряд). "
                    "Напиши короткую (2-3 предложения), очень теплую и ненавязчивую реплику фасилитатора ННО: "
                    "отметь общие ценности участников и предложи сфокусироваться на чувствах и потребностях."
                ),
                chat_history=history_list,
                trace_id=trace_id,
            )
            if note:
                await context.bot.send_message(chat_id=chat.id, text=f"🕊 {note}")
                await self.db.add_message(chat.id, "bot", note, is_bot=True)
        except Exception as e:
            logger.warning("Ошибка проактивного фасилитатора в чате %d: %s", chat.id, e, extra={'trace_id': trace_id})

    def _format_rules_list(self, rules: List[Dict]) -> str:
        if not rules:
            return "Правила санкций не настроены."
        lines = []
        for rule in sorted(rules, key=lambda x: x['warnings']):
            action_desc = "бан" if rule['action'] == 'BAN' else f"мьют на {rule['duration_hours']} ч."
            lines.append(f"- {rule['warnings']} предупреждений: {action_desc}")
        return "\n".join(lines)

    def _format_history_for_template(self, history: List[Dict[str, Any]]) -> str:
        '''Преобразует структурированную историю в простую строку.'''
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

        verdict_obj = self._last_verdict_by_trace.pop(trace_id, None)
        suggested_nvc = verdict_obj.suggested_nvc if verdict_obj else ""
        violated_rule = (verdict_obj.violated_rule if verdict_obj and verdict_obj.violated_rule else "Ты-сообщение / оценка")

        if not suggested_nvc:
            nvc_res = await self.gemini.translate_to_nvc(text, trace_id=trace_id)
            suggested_nvc = nvc_res.natural_nvc_phrase

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
        is_soft_mode = await self.db.is_soft_moderation_enabled()

        # Создаем запись для апелляции (кнопка «⚖️ Оспорить»)
        appeal_id = await self.db.create_appeal(
            chat_id=chat.id,
            user_id=user.id,
            user_name=user_display_mention,
            original_text=text,
            suggested_nvc=suggested_nvc,
            rule_violated=violated_rule
        )

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
            ai_response = (
                f"⚠️ {user_display_mention}, ваше сообщение содержало резкую формулировку ({violated_rule}). "
                f"Предупреждений: {new_warnings_count}."
            )

        # Мягкий режим пре-модерации: удаляем токсичный оригинал в чате и шлем автору в ЛС его текст + мягкую ННО-версию
        dm_sent_successfully = False
        if is_soft_mode:
            try:
                await context.bot.delete_message(chat_id=chat.id, message_id=message.message_id)
                logger.info("Токсичное сообщение %d удалено в мягком режиме пре-модерации.", message.message_id, extra={'trace_id': trace_id})
            except TelegramError as del_err:
                logger.warning("Не удалось удалить сообщение %d (проверьте права администратора у бота): %s", message.message_id, del_err, extra={'trace_id': trace_id})

            dm_card_text = (
                f"🌱 Здравствуйте, {user.first_name or user_display_mention}!\n\n"
                f"Ваше сообщение в чате «{chat.title or 'группе'}» было скрыто мягкой пре-модерацией "
                f"(причина: {violated_rule}).\n\n"
                f"📝 Ваш исходный текст (чтобы вы его не потеряли):\n"
                f"«{text}»\n\n"
                f"💚 Предлагаемая формулировка на языке ННО (можно скопировать и отправить в чат):\n"
                f"«{suggested_nvc}»"
            )
            try:
                await context.bot.send_message(chat_id=user.id, text=dm_card_text)
                dm_sent_successfully = True
            except (Forbidden, TelegramError) as dm_err:
                logger.info("Личка пользователя %d недоступна (%s), добавляем ННО-подсказку в сообщение чата.", user.id, dm_err, extra={'trace_id': trace_id})

        if is_soft_mode and not dm_sent_successfully and suggested_nvc:
            ai_response += (
                f"\n\n💡 Вариант на языке ННО (напишите боту в ЛС, чтобы получать черновики лично):\n"
                f"«{suggested_nvc}»"
            )
        elif is_soft_mode and dm_sent_successfully:
            ai_response += "\n\n📩 Исходный текст и мягкий вариант на языке ННО отправлены вам в личные сообщения."

        # Сохраняем факт нарушения и ответ модератора в историю чата
        await self.db.add_message(chat.id, user.full_name, f"[УДАЛЕНО МОДЕРАТОРОМ]: {text}", is_bot=False)
        if ai_response:
            await self.db.add_message(chat.id, "bot", ai_response, is_bot=True)
            appeal_kb = None
            if appeal_id > 0:
                appeal_kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("⚖️ Оспорить предупреждение", callback_data=f"appeal_create_{appeal_id}")]
                ])
            try:
                await context.bot.send_message(
                    chat_id=chat.id,
                    text=ai_response,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=appeal_kb
                )
            except BadRequest as e:
                logger.warning("Ошибка парсинга Markdown в сообщении модерации (%s), отправляю без форматирования.", e, extra={'trace_id': trace_id})
                try:
                    await context.bot.send_message(
                        chat_id=chat.id,
                        text=ai_response,
                        reply_markup=appeal_kb
                    )
                except TelegramError as fallback_err:
                    logger.error("Не удалось отправить сообщение о нарушении: %s", fallback_err, extra={'trace_id': trace_id})