# NVC_bot/bot/handlers/user.py
# version: 6.0.0
# 2026-10-30T16:30:00Z

'''
Обработчики команд и сообщений от обычных пользователей.

Version 6.0.0:
- ADD: Универсальный ННО-переводчик по командам `/nvc`, `/NNO` и кириллической `/ННО`
       в любом регистре (по реплаю в группе или с текстом после команды), без `/rephrase`.
- ADD: Перевод любых текстовых черновиков в личных сообщениях (ЛС) с ботом по 4 шагам ННО.
- ADD: Поддержка Inline-режима (`@ИмяБота <текст>`) для мгновенного перефразирования в любом чате.
- ADD: Обработка апелляций по кнопке «⚖️ Оспорить предупреждение» (`appeal_create_`, `appeal_approve_`, `appeal_reject_`).
'''

import asyncio
import logging
import re
import uuid
import json
from telegram import (
    Update,
    ReplyParameters,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from telegram.ext import ContextTypes
from telegram.constants import ChatType, ParseMode, ChatAction, MessageLimit
from telegram.error import BadRequest, TelegramError

from ..database import Database
from ..services.gemini import GeminiService
from ..services.moderation import ModerationService
from ..config import ADMIN_IDS, ADMIN_IDS_SET, PRIVATE_CHAT_REPLY, GROUP_START_MESSAGE, ADMIN_START_MESSAGE
from ..utils.decorators import log_action
from ..utils.formatters import format_debug_info_text, escape_markdown_v2, safe_format_template
from ..utils.validators import NVC_COMMAND_PATTERN

logger = logging.getLogger(__name__)

# Регулярное выражение для команд /nvc, /NNO и кириллической /ННО в любом регистре (без /rephrase)
NVC_COMMAND_PATTERN = re.compile(
    r"^/(?:nvc|nno|нно)(?:@[A-Za-z0-9_]+)?(?:\s+(?P<payload>[\s\\S]+))?$",
    re.IGNORECASE,
)


class UserHandlers:
    '''Класс, инкапсулирующий обработчики пользовательских команд и ННО-переводчика.'''

    def __init__(self, db: Database, gemini_service: GeminiService, moderation_service: ModerationService):
        self.db = db
        self.gemini = gemini_service
        self.moderation = moderation_service

    @log_action("nvc_translate")
    async def nvc_translate_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        '''
        Обрабатывает команды /nvc, /NNO и /ННО (в любом регистре):
        1. Если передан текст после команды (/ННО текст) — переводит его по 4 шагам ННО.
        2. Если команда отправлена ответом (reply) на сообщение — переводит исходное сообщение.
        '''
        message = update.message
        if not message or not message.text:
            return

        trace_id = str(uuid.uuid4())
        match = NVC_COMMAND_PATTERN.match(message.text.strip())
        payload = (match.group("payload").strip() if match and match.group("payload") else "")

        target_text = payload
        if not target_text and message.reply_to_message and message.reply_to_message.text:
            target_text = message.reply_to_message.text.strip()

        if not target_text:
            await message.reply_text(
                "🌱 Как пользоваться ННО-переводчиком:\n\n"
                "1️⃣ Ответьте командой /ННО (или /NNO, /nvc) на любое резкое сообщение в чате.\n"
                "2️⃣ Или напишите черновик после команды: /ННО Ты опять срываешь сроки!\n"
                "3️⃣ Или просто отправьте любую фразу мне в личные сообщения."
            )
            return

        await self._send_nvc_translation(message, context, target_text, trace_id)

    async def _send_nvc_translation(
        self, message, context: ContextTypes.DEFAULT_TYPE, raw_text: str, trace_id: str
    ) -> None:
        '''Выполняет 4-шаговый перевод на язык ННО и отправляет результат пользователю.'''
        chat_id = message.chat_id
        typing_task = asyncio.create_task(self._keep_typing_action(context, chat_id, trace_id))
        try:
            result = await self.gemini.translate_to_nvc(raw_text, trace_id=trace_id)
            await self.db.increment_ai_responses()
            formatted_reply = (
                "🌱 Перевод на язык Ненасильственного общения (ННО):\n\n"
                f"1️⃣ Наблюдение: {result.observation}\n"
                f"2️⃣ Чувство: {result.feeling}\n"
                f"3️⃣ Потребность: {result.need}\n"
                f"4️⃣ Просьба: {result.request}\n\n"
                f"💬 Готовая мягкая фраза для отправки:\n"
                f"«{result.natural_nvc_phrase}»"
            )
            await message.reply_text(formatted_reply)
        except Exception as e:
            logger.error("Ошибка при переводе фразы в ННО: %s", e, exc_info=True, extra={'trace_id': trace_id})
            await message.reply_text("Произошла ошибка при формировании ННО-перевода. Попробуйте еще раз.")
        finally:
            typing_task.cancel()

    async def handle_inline_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        '''
        Обрабатывает Inline-запросы (@ИмяБота <фраза>) для перевода на язык ННО прямо в строке ввода.
        '''
        inline_query = update.inline_query
        if not inline_query:
            return
        query_text = (inline_query.query or "").strip()
        if len(query_text) < 4:
            return

        trace_id = str(uuid.uuid4())
        try:
            result = await self.gemini.translate_to_nvc(query_text, trace_id=trace_id)
            articles = [
                InlineQueryResultArticle(
                    id=str(uuid.uuid4()),
                    title="🌱 Отправить мягкую ННО-формулировку",
                    description=result.natural_nvc_phrase[:120],
                    input_message_content=InputTextMessageContent(message_text=result.natural_nvc_phrase),
                ),
                InlineQueryResultArticle(
                    id=str(uuid.uuid4()),
                    title="🧩 Полный разбор по 4 шагам ННО",
                    description=f"Наблюдение · Чувство · Потребность · Просьба",
                    input_message_content=InputTextMessageContent(
                        message_text=(
                            f"🌱 Разбор по 4 шагам ННО:\n"
                            f"• Наблюдение: {result.observation}\n"
                            f"• Чувство: {result.feeling}\n"
                            f"• Потребность: {result.need}\n"
                            f"• Просьба: {result.request}\n\n"
                            f"💬 Итог: «{result.natural_nvc_phrase}»"
                        )
                    ),
                ),
            ]
            await inline_query.answer(articles, cache_time=5, is_personal=True)
        except Exception as e:
            logger.error("Ошибка в handle_inline_query: %s", e, extra={'trace_id': trace_id})

    async def handle_appeal_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        '''
        Обрабатывает нажатия на кнопку «⚖️ Оспорить предупреждение» в чате
        и кнопки решения администратора («✅ Снять варн и вернуть текст» / «❌ Оставить в силе»).
        '''
        query = update.callback_query
        user = update.effective_user
        if not query or not query.data or not user:
            return

        data = query.data
        if data.startswith("appeal_create_"):
            appeal_id = int(data.replace("appeal_create_", ""))
            appeal = await self.db.get_appeal(appeal_id)
            if not appeal:
                await query.answer("Запись об апелляции не найдена.", show_alert=True)
                return
            if user.id != appeal["user_id"] and user.id not in ADMIN_IDS_SET:
                await query.answer("Оспорить это предупреждение может только автор сообщения или администратор.", show_alert=True)
                return
            if appeal["status"] != "pending":
                await query.answer("Эта апелляция уже рассмотрена или отправлена.", show_alert=True)
                return

            await query.answer("✅ Апелляция отправлена администраторам на проверку.", show_alert=True)
            try:
                await query.message.edit_reply_markup(
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("⏳ Апелляция на рассмотрении админов", callback_data="appeal_noop")]
                    ])
                )
            except TelegramError:
                pass

            admin_text = (
                f"⚖️ Новая апелляция #{appeal_id}\n\n"
                f"👤 Участник: {appeal['user_name']} (ID: {appeal['user_id']})\n"
                f"📌 Правило: {appeal['rule_violated']}\n\n"
                f"📝 Удаленное сообщение:\n«{appeal['original_text']}»\n\n"
                f"🌱 Предложенная ННО-версия:\n«{appeal['suggested_nvc']}»"
            )
            admin_kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Снять варн и вернуть текст", callback_data=f"appeal_approve_{appeal_id}"),
                    InlineKeyboardButton("❌ Оставить в силе", callback_data=f"appeal_reject_{appeal_id}"),
                ]
            ])
            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(chat_id=admin_id, text=admin_text, reply_markup=admin_kb)
                except TelegramError as e:
                    logger.warning("Не удалось отправить апелляцию админу %d: %s", admin_id, e)

        elif data.startswith("appeal_approve_"):
            if user.id not in ADMIN_IDS_SET:
                await query.answer("Только администратор может одобрить апелляцию.", show_alert=True)
                return
            appeal_id = int(data.replace("appeal_approve_", ""))
            appeal = await self.db.get_appeal(appeal_id)
            if not appeal or appeal["status"] != "pending":
                await query.answer("Апелляция уже обработана.", show_alert=True)
                return

            await self.db.update_appeal_status(appeal_id, "approved")
            new_warns = await self.db.adjust_warnings(appeal["user_id"], -1)
            await query.answer("✅ Предупреждение снято, сообщение возвращено в чат!")
            try:
                await query.message.edit_text(
                    f"✅ Апелляция #{appeal_id} ОДОБРЕНА администратором {user.full_name}.\n"
                    f"Участнику {appeal['user_name']} списано 1 предупреждение (осталось: {new_warns}), "
                    f"исходный текст возвращён в группу."
                )
            except TelegramError:
                pass

            try:
                await context.bot.send_message(
                    chat_id=appeal["chat_id"],
                    text=(
                        f"✅ Апелляция удовлетворена модератором. Предупреждение с {appeal['user_name']} снято.\n\n"
                        f"Восстановленное сообщение от {appeal['user_name']}:\n«{appeal['original_text']}»"
                    ),
                )
            except TelegramError as e:
                logger.warning("Не удалось вернуть восстановленное сообщение в чат %d: %s", appeal["chat_id"], e)

        elif data.startswith("appeal_reject_"):
            if user.id not in ADMIN_IDS_SET:
                await query.answer("Только администратор может отклонить апелляцию.", show_alert=True)
                return
            appeal_id = int(data.replace("appeal_reject_", ""))
            appeal = await self.db.get_appeal(appeal_id)
            if not appeal or appeal["status"] != "pending":
                await query.answer("Апелляция уже обработана.", show_alert=True)
                return

            await self.db.update_appeal_status(appeal_id, "rejected")
            await query.answer("❌ Апелляция отклонена, предупреждение оставлено в силе.")
            try:
                await query.message.edit_text(
                    f"❌ Апелляция #{appeal_id} ОТКЛОНЕНА администратором {user.full_name}.\n"
                    f"Предупреждение для {appeal['user_name']} оставлено в силе."
                )
            except TelegramError:
                pass

        elif data == "appeal_noop":
            await query.answer("Апелляция уже передана администраторам чата.")

    @log_action("message")
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.message
        user = update.effective_user
        chat = update.effective_chat
        text = message.text if message else None
        trace_id = str(uuid.uuid4())
        context.user_data['trace_id'] = trace_id

        if not all([message, user, chat, text]):
            return

        # Если сообщение начинается с /nvc, /NNO или /ННО — передаем в переводчик ННО
        if NVC_COMMAND_PATTERN.match(text.strip()):
            await self.nvc_translate_command(update, context)
            return

        bot_username = (context.bot.username or "").lower()
        is_mention = bool(bot_username and f"@{bot_username}" in text.lower())
        is_reply_to_bot = bool(
            message.reply_to_message
            and message.reply_to_message.from_user
            and message.reply_to_message.from_user.id == context.bot.id
        )

        should_respond = False
        is_admin_private_chat = chat.type == ChatType.PRIVATE and user.id in ADMIN_IDS_SET

        if is_admin_private_chat:
            is_debug_mode = await self.db.is_debug_mode_enabled()
            if is_debug_mode:
                if is_mention or is_reply_to_bot:
                    logger.info("Причина: Админ в ЛС (Отладка ВКЛ), прямое обращение. Бот отвечает.", extra={'trace_id': trace_id})
                    should_respond = True
                else:
                    logger.info(f"Причина: Админ в ЛС (Отладка ВКЛ), заметка тестера. Логирую, не отвечаю. Текст: «{text}»", extra={'trace_id': trace_id})
                    await self.db.add_message(chat.id, user.full_name, text, is_bot=False)
                    should_respond = False
            else:
                logger.info("Причина: Админ в ЛС (Отладка ВЫКЛ), штатный режим. Бот отвечает.", extra={'trace_id': trace_id})
                should_respond = True

        elif chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
            if is_mention or is_reply_to_bot:
                logger.info("Причина: Группа + упоминание/ответ. Бот отвечает.", extra={'trace_id': trace_id})
                should_respond = True
            else:
                logger.info("Причина: Группа, нет упоминания. Передаю модератору.", extra={'trace_id': trace_id})
                is_violation = await self.moderation.check_message(update, context, trace_id)
                if is_violation:
                    await self.moderation.handle_violation(update, context, text, trace_id)
                else:
                    await self.db.add_message(chat.id, user.full_name, text, is_bot=False)
                    await self.moderation.maybe_intervene_in_heated_dispute(update, context, trace_id)

        elif chat.type == ChatType.PRIVATE:
            # Обычный участник в ЛС отправляет черновик -> переводим его фразу по 4 шагам ННО!
            logger.info("Причина: Участник в ЛС отправил черновик для ННО-перевода.", extra={'trace_id': trace_id})
            await self.db.add_message(chat.id, user.full_name, text, is_bot=False)
            await self._send_nvc_translation(message, context, text, trace_id)
            should_respond = False

        if should_respond:
            await self._respond_to_message(update, context, trace_id)

    @log_action("start")
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        chat = update.effective_chat
        if not user or not chat or not update.message:
            return

        if chat.type == ChatType.PRIVATE:
            if user.id in ADMIN_IDS_SET:
                await update.message.reply_text(ADMIN_START_MESSAGE)
            else:
                await update.message.reply_text(PRIVATE_CHAT_REPLY)
        elif chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
            await update.message.reply_text(GROUP_START_MESSAGE.format(bot_username=context.bot.username))

    @log_action("help")
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        text = (
            "Я — бот\-медиатор, помогающий практиковать Ненасильственное общение \(ННО / NVC\)\.\n\n"
            "*Для всех участников:*\n"
            "• `/nvc`, `/NNO` или `/ННО` \(ответом на сообщение или с текстом\) \- перевести резкую фразу по 4 шагам ННО\.\n"
            "• В личных сообщениях со мной \- отправьте любой черновик, и я помогу сформулировать его мягко\.\n"
            f"• Чтобы задать вопрос в группе, упомяните меня \(`@{escape_markdown_v2(context.bot.username or '')}`\) или ответьте на моё сообщение\.\n\n"
            "*Для администраторов \(в ЛС\):*\n"
            "/settings \- Настройки ИИ\-фасилитатора и выбор модели \(Gemini 3\.8 Flash и др\.\)\.\n"
            "/moderate \- Настройки модерации, мягкого режима и автоамнистии\.\n"
            "/stats \- Статистика\.\n"
            "/warnings \- Управление предупреждениями\.\n"
            "/cancel \- Отмена диалога\."
        )
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)

    @log_action("greet_new_members")
    async def greet_new_members(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self.db.is_welcome_enabled():
            return
        if not update.message or not update.message.new_chat_members:
            return

        trace_id = str(uuid.uuid4())
        chat = update.effective_chat
        try:
            chat_full = await context.bot.get_chat(chat.id)
            chat_description = chat_full.description or "Правила группы не указаны."
        except Exception as e:
            logger.warning("Не удалось получить описание чата %d: %s", chat.id, e, extra={'trace_id': trace_id})
            chat_description = "Правила группы не указаны."

        for member in update.message.new_chat_members:
            if member.is_bot:
                continue
            logger.info("Генерация приветствия для %s (%d)", member.full_name, member.id, extra={'trace_id': trace_id})
            try:
                task_instruction = await self.db.get_welcome_prompt()
                if not task_instruction:
                    logger.warning("Промпт приветствий пуст.", extra={'trace_id': trace_id})
                    continue

                formatted_instruction = safe_format_template(
                    task_instruction,
                    user_mention=member.mention_html(),
                    group_rules=chat_description
                ).replace("@имя_бота", f"@{context.bot.username}")

                model_id = await self.db.get_welcome_model()
                response_text, _ = await self.gemini.generate_response(
                    question="",
                    task_instruction=formatted_instruction,
                    trace_id=trace_id,
                    model_override=model_id,
                    chat_description=chat_description
                )
                if response_text:
                    try:
                        await context.bot.send_message(chat_id=chat.id, text=response_text, parse_mode=ParseMode.HTML)
                    except BadRequest:
                        await context.bot.send_message(chat_id=chat.id, text=response_text)
            except Exception as e:
                logger.error("Ошибка при генерации приветствия: %s", e, extra={'trace_id': trace_id})

    async def _keep_typing_action(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, trace_id: str) -> None:
        while True:
            try:
                await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
                await asyncio.sleep(4)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Ошибка в задаче 'typing': %s", e, extra={'trace_id': trace_id})
                break

    async def _send_long_message(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str, trace_id: str, **kwargs):
        if not text:
            logger.warning("Попытка отправить пустое сообщение.", extra={'trace_id': trace_id})
            return
        for i in range(0, len(text), MessageLimit.MAX_TEXT_LENGTH):
            chunk = text[i:i + MessageLimit.MAX_TEXT_LENGTH]
            await context.bot.send_message(chat_id=chat_id, text=chunk, **kwargs)

    async def _respond_to_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE, trace_id: str) -> None:
        user = update.effective_user
        message = update.message
        chat_id = message.chat_id
        question = message.text

        typing_task = asyncio.create_task(self._keep_typing_action(context, chat_id, trace_id))
        try:
            try:
                chat_full = await context.bot.get_chat(chat_id)
                chat_description = chat_full.description or "Правила группы не указаны."
            except Exception as e:
                logger.warning("Не удалось получить описание чата %d: %s", chat_id, e, extra={'trace_id': trace_id})
                chat_description = "Правила группы не указаны."

            context_config = await self.db.get_context_config()
            chat_history = await self.db.get_chat_history(chat_id, context_config["context_messages_limit"])
            user_mention = f"@{user.username}" if user.username else user.full_name
            is_debug_mode = await self.db.is_debug_mode_enabled()
            core_prompt = await self.db.get_prompt()

            response_text, usage_metadata = await self.gemini.generate_response(
                question=question,
                task_instruction="",
                chat_history=chat_history,
                trace_id=trace_id,
                user_mention=user_mention,
                is_debug_mode=is_debug_mode,
                chat_description=chat_description
            )

            await self.db.add_message(chat_id, user.full_name, question, is_bot=False)
            if response_text:
                await self.db.add_message(chat_id, "bot", response_text, is_bot=True)
                await self.db.increment_ai_responses()

            reply_params = ReplyParameters(message_id=message.message_id)
            try:
                await self._send_long_message(
                    context, chat_id, response_text, trace_id,
                    parse_mode=ParseMode.MARKDOWN, reply_parameters=reply_params
                )
            except BadRequest as e:
                if "Can't parse entities" in str(e):
                    logger.warning("Ошибка парсинга Markdown в ответе AI, отправляю как простой текст: %s", e, extra={'trace_id': trace_id})
                    await self._send_long_message(context, chat_id, response_text, trace_id, reply_parameters=reply_params)
                else:
                    logger.error("Ошибка BadRequest при отправке ответа AI: %s", e, extra={'trace_id': trace_id})
                    await message.reply_text("Произошла ошибка при отправке ответа.")

            if is_debug_mode and user.id in ADMIN_IDS_SET:
                debug_info = format_debug_info_text(
                    usage_metadata=usage_metadata,
                    system_prompt_len=len(core_prompt),
                    chat_history_len=len(json.dumps(chat_history, ensure_ascii=False)),
                    question_len=len(question)
                )
                await self._send_long_message(context, chat_id, debug_info, trace_id, parse_mode=ParseMode.MARKDOWN_V2)

        except Exception as e:
            logger.error("Критическая ошибка при генерации ответа: %s", e, exc_info=True, extra={'trace_id': trace_id})
            await message.reply_text("Произошла внутренняя ошибка.")
        finally:
            typing_task.cancel()