# NVC_bot/bot/handlers/user.py
# version: 8.4.0
# 2025-08-14T13:00:00Z
"""
Обработчики команд и сообщений от обычных пользователей.

Version 8.4.0:
- FEATURE: При входе нового пользователя в БД теперь записывается
           информативное системное сообщение вместо пустого.

Version 8.3.1:
- FIX: Унифицирован способ форматирования шаблона приветствия.
"""
import asyncio
import logging
import uuid
import json
import re
from typing import Optional
from telegram import Update, ReplyParameters, Message
from telegram.ext import ContextTypes
from telegram.constants import ChatType, ParseMode, ChatAction, MessageLimit
from telegram.error import BadRequest, TelegramError
from google.api_core.exceptions import FailedPrecondition, InternalServerError

from ..database import Database
from ..services.gemini import GeminiService
from ..services.moderation import ModerationService
from ..config import ADMIN_IDS_SET, PRIVATE_CHAT_REPLY, GROUP_START_MESSAGE, ADMIN_START_MESSAGE
from ..utils.decorators import log_action
from ..utils.formatters import format_debug_info_text, escape_markdown_v2

logger = logging.getLogger(__name__)

class UserHandlers:
    """Класс, инкапсулирующий обработчики пользовательских команд."""

    def __init__(self, db: Database, gemini_service: GeminiService, moderation_service: ModerationService):
        self.db = db
        self.gemini = gemini_service
        self.moderation = moderation_service

    async def _process_message(self, message: Message, context: ContextTypes.DEFAULT_TYPE) -> None:
        user, chat, text = message.from_user, message.chat, message.text
        trace_id = str(uuid.uuid4())
        context.user_data['trace_id'] = trace_id

        if not all([user, chat, text]): return

        bot_username = f"@{context.bot.username}"
        is_mention = bot_username.lower() in text.lower()
        is_reply_to_bot = message.reply_to_message and message.reply_to_message.from_user.id == context.bot.id
        should_respond = False
        is_admin_private_chat = chat.type == ChatType.PRIVATE and user.id in ADMIN_IDS_SET
        reply_to_id = message.reply_to_message.message_id if message.reply_to_message else None

        if is_admin_private_chat:
            is_debug_mode = await self.db.is_debug_mode_enabled()
            if is_debug_mode and not (is_mention or is_reply_to_bot):
                logger.info("[ЗАМЕТКА ТЕСТЕРА] Сообщение от админа %s в ЛС: '%s'", user.full_name, text, extra={'trace_id': trace_id})
                await self.db.add_message(chat.id, message.message_id, user.id, user.full_name, text, is_bot=False, reply_to_message_id=reply_to_id)
                return
            else:
                should_respond = True
        
        elif chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
            is_violation = await self.moderation.check_message(message, context, trace_id)
            if is_violation:
                await self.moderation.handle_violation(message, context, trace_id)
                return
            await self.db.add_message(chat.id, message.message_id, user.id, user.full_name, text, is_bot=False, reply_to_message_id=reply_to_id)
            if is_mention or is_reply_to_bot:
                should_respond = True
        
        elif chat.type == ChatType.PRIVATE:
            await self.db.add_message(chat.id, message.message_id, user.id, user.full_name, text, is_bot=False, reply_to_message_id=reply_to_id)
            await message.reply_text(PRIVATE_CHAT_REPLY)

        if should_respond:
            await self._respond_to_message(message, context, trace_id, is_admin_private_chat)

    @log_action("new_message")
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message: await self._process_message(update.message, context)

    @log_action("edited_message")
    async def handle_edited_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.edited_message: await self._process_message(update.edited_message, context)

    @log_action("start")
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user, chat = update.effective_user, update.effective_chat
        if not user or not chat: return
        if chat.type == ChatType.PRIVATE:
            await update.message.reply_text(ADMIN_START_MESSAGE if user.id in ADMIN_IDS_SET else PRIVATE_CHAT_REPLY)
        else:
            await update.message.reply_text(GROUP_START_MESSAGE.format(bot_username=context.bot.username))

    @log_action("help")
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        text = (
            "Я — бот, помогающий практиковать ненасильственное общение\\.\n\n"
            "**В групповых чатах:**\n"
            f"• Чтобы задать мне вопрос, упомяните меня \\(`@{escape_markdown_v2(context.bot.username)}`\\) или ответьте на моё сообщение\\.\n"
            "• Я также слежу за общением и могу реагировать на некоторые сообщения\\.\n\n"
            "**В личных сообщениях \\(только для администраторов\\):**\n"
            "/settings \\- Настройки личности ИИ\\-бота\\.\n"
            "/moderate \\- Настройки модерации\\.\n"
            "/stats \\- Статистика\\.\n"
            "/warnings \\- Управление предупреждениями\\.\n"
            "/cancel \\- Отмена диалога\\."
        )
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)

    @log_action("greet_new_members")
    async def greet_new_members(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self.db.is_welcome_enabled() or not update.message or not update.message.new_chat_members: return
        
        chat = update.effective_chat
        is_debug_mode = await self.db.is_debug_mode_enabled()
        
        async def _generate_and_send_welcome(member, chat_description, trace_id):
            """Внутренняя функция для выполнения в фоновой задаче."""
            try:
                # FEATURE: Запись в историю осмысленного системного сообщения
                system_message = f"Пользователь {member.full_name} присоединился к чату."
                await self.db.add_message(
                    chat_id=chat.id,
                    message_id=update.message.message_id,
                    user_id=member.id,
                    user_name="[Системное событие]",
                    text=system_message,
                    is_bot=False
                )
                logger.info("Генерация приветствия для %s (%d)", member.full_name, member.id, extra={'trace_id': trace_id})
                
                welcome_template = await self.db.get_welcome_prompt()
                if not welcome_template: return

                formatted_task_content = welcome_template.replace("{user_mention}", member.mention_html())
                formatted_task_content = formatted_task_content.replace("{group_rules}", chat_description)
                formatted_task_content = formatted_task_content.replace("{bot_username}", f"@{context.bot.username}")

                model_id = await self.db.get_welcome_model()
                
                response_text, _, _ = await self.gemini.generate_response(
                    question=formatted_task_content,
                    trace_id=trace_id,
                    request_type="WELCOME",
                    is_debug_mode=is_debug_mode,
                    model_override=model_id,
                    chat_description=chat_description,
                    chat_history=[]
                )
                if response_text:
                    sent = await context.bot.send_message(chat.id, response_text, parse_mode=ParseMode.HTML)
                    await self.db.add_message(chat.id, sent.message_id, context.bot.id, "bot", response_text, True)
            except Exception as e:
                logger.error("Ошибка при генерации приветствия в фоновой задаче: %s", e, extra={'trace_id': trace_id}, exc_info=True)

        try:
            chat_description = (await context.bot.get_chat(chat.id)).description or "Правила группы не указаны."
        except Exception as e:
            logger.warning("Не удалось получить описание чата %d: %s", chat.id, e)
            chat_description = "Правила группы не указаны."

        for member in update.message.new_chat_members:
            if member.is_bot: continue
            trace_id = str(uuid.uuid4())
            asyncio.create_task(_generate_and_send_welcome(member, chat_description, trace_id))

    async def _keep_typing_action(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, trace_id: str) -> None:
        while True:
            try:
                await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
                await asyncio.sleep(4)
            except asyncio.CancelledError: break
            except Exception as e:
                logger.warning("Ошибка в задаче 'typing': %s", e, extra={'trace_id': trace_id})
                break

    async def _send_long_message(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str, trace_id: str, **kwargs) -> Optional[Message]:
        if not text:
            logger.warning("Попытка отправить пустое сообщение.", extra={'trace_id': trace_id})
            return None
        sent_message = None
        try:
            for i in range(0, len(text), MessageLimit.MAX_TEXT_LENGTH):
                sent_message = await context.bot.send_message(chat_id=chat_id, text=text[i:i + MessageLimit.MAX_TEXT_LENGTH], **kwargs)
        except BadRequest as e:
            if "Can't parse entities" in str(e):
                logger.warning("Ошибка парсинга Markdown. Отправляю как простой текст. Ошибка: %s", e, extra={'trace_id': trace_id})
                kwargs.pop('parse_mode', None)
                for i in range(0, len(text), MessageLimit.MAX_TEXT_LENGTH):
                    sent_message = await context.bot.send_message(chat_id=chat_id, text=text[i:i + MessageLimit.MAX_TEXT_LENGTH], **kwargs)
            else: raise
        return sent_message

    async def _respond_to_message(self, message: Message, context: ContextTypes.DEFAULT_TYPE, trace_id: str, is_admin_private_chat: bool) -> None:
        user, chat_id, question = message.from_user, message.chat_id, message.text
        typing_task = asyncio.create_task(self._keep_typing_action(context, chat_id, trace_id))
        
        try:
            chat_description = (await context.bot.get_chat(chat_id)).description or "Правила группы не указаны."
        except Exception as e:
            logger.warning("Не удалось получить описание чата %d: %s", chat_id, e, extra={'trace_id': trace_id})
            chat_description = "Правила группы не указаны."

        try:
            context_config = await self.db.get_context_config()
            rich_chat_history = await self.db.get_chat_history(chat_id, context_config["context_messages_limit"])
            is_debug_mode = await self.db.is_debug_mode_enabled()

            response_text, usage_metadata, system_prompt_len = await self.gemini.generate_response(
                question=question,
                chat_history=rich_chat_history,
                trace_id=trace_id,
                request_type="RESPONSE",
                is_debug_mode=is_debug_mode,
                chat_description=chat_description,
                is_admin_chat=is_admin_private_chat
            )
            
            if response_text:
                reply_params = ReplyParameters(message_id=message.message_id)
                sent = await self._send_long_message(context, chat_id, response_text, trace_id, parse_mode=ParseMode.MARKDOWN, reply_parameters=reply_params)
                if sent:
                     await self.db.add_message(chat_id, sent.message_id, context.bot.id, "bot", response_text, True, message.message_id)
                     await self.db.increment_ai_responses()

            if is_debug_mode and is_admin_private_chat:
                debug_info = format_debug_info_text(
                    usage_metadata=usage_metadata,
                    system_prompt_len=system_prompt_len, 
                    chat_history_len=len(json.dumps(rich_chat_history)),
                    question_len=len(question)
                )
                await self._send_long_message(context, chat_id, debug_info, trace_id, parse_mode=ParseMode.MARKDOWN_V2)

        except Exception as e:
            error_message = f"Произошла ошибка. Администраторы уведомлены. (Trace ID: {trace_id})"
            logger.error("Критическая ошибка при генерации ответа: %s", e, exc_info=True, extra={'trace_id': trace_id})
            await message.reply_text(str(e) if isinstance(e, (FailedPrecondition, InternalServerError)) else error_message)
        finally:
            typing_task.cancel()
