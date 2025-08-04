# NVC_bot/bot/handlers/user.py
# version: 5.0.0
# 2025-07-30T14:00:00Z
"""
Обработчики команд и сообщений от обычных пользователей.

Version 5.0.0:
- REFACTOR: Адаптация к композитной архитектуре промптов.
            - `_respond_to_message` и `greet_new_members` теперь передают
              `task_instruction` вместо `system_prompt` в `GeminiService`.
            - Реализована логика получения описания чата для подстановки
              переменной `{{group_rules}}`.

Version 4.9.1:
- REFACTOR: Унифицирована логика форматирования. Теперь ParseMode.MARKDOWN
            используется как для обычного, так и для отладочного режима,
            чтобы обеспечить консистентное отображение ответов.
"""
import asyncio
import logging
import uuid
import json
from telegram import Update, ReplyParameters
from telegram.ext import ContextTypes
from telegram.constants import ChatType, ParseMode, ChatAction, MessageLimit
from telegram.error import BadRequest, TelegramError

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

    @log_action("message")
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.message
        user = update.effective_user
        chat = update.effective_chat
        text = message.text
        trace_id = str(uuid.uuid4())
        context.user_data['trace_id'] = trace_id

        if not all([message, user, chat, text]):
            return

        bot_username = context.bot.username.lower()
        is_mention = f"@{bot_username}" in text.lower()
        is_reply_to_bot = message.reply_to_message and message.reply_to_message.from_user.id == context.bot.id
        
        should_respond = False
        is_admin_private_chat = chat.type == ChatType.PRIVATE and user.id in ADMIN_IDS_SET

        if is_admin_private_chat:
            is_debug_mode = await self.db.is_debug_mode_enabled()
            if is_debug_mode:
                if is_mention or is_reply_to_bot:
                    logger.info("Причина: Админ в ЛС (Отладка ВКЛ), прямое обращение. Бот отвечает.", extra={'trace_id': trace_id})
                    should_respond = True
                else:
                    logger.info(f"Причина: Админ в ЛС (Отладка ВКЛ), заметка тестера. Логгирую, не отвечаю. Текст: «{text}»", extra={'trace_id': trace_id})
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
        
        elif chat.type == ChatType.PRIVATE:
            logger.info("Причина: Обычный пользователь в ЛС. Отвечаю заглушкой.", extra={'trace_id': trace_id})
            await self.db.add_message(chat.id, user.full_name, text, is_bot=False)
            await update.message.reply_text(PRIVATE_CHAT_REPLY)
            should_respond = False

        if should_respond:
            await self._respond_to_message(update, context, trace_id)

    @log_action("start")
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        chat = update.effective_chat
        if not user or not chat: return

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
        if not await self.db.is_welcome_enabled(): return
        if not update.message or not update.message.new_chat_members: return
        
        trace_id = str(uuid.uuid4())
        chat = update.effective_chat
        
        try:
            chat_full = await context.bot.get_chat(chat.id)
            chat_description = chat_full.description or "Правила группы не указаны."
        except Exception as e:
            logger.warning("Не удалось получить описание чата %d: %s", chat.id, e, extra={'trace_id': trace_id})
            chat_description = "Правила группы не указаны."

        for member in update.message.new_chat_members:
            if member.is_bot: continue
            logger.info("Генерация приветствия для %s (%d)", member.full_name, member.id, extra={'trace_id': trace_id})
            try:
                task_instruction = await self.db.get_welcome_prompt()
                if not task_instruction:
                    logger.warning("Промпт приветствий пуст.", extra={'trace_id': trace_id})
                    continue

                # Подставляем переменные в инструкцию
                formatted_instruction = task_instruction.format(user_mention=member.mention_html()).replace("@имя_бота", f"@{context.bot.username}")
                
                model_id = await self.db.get_welcome_model()
                
                # Для приветствия "вопрос" пуст, вся задача описана в инструкции
                response_text, _ = await self.gemini.generate_response(
                    question="",
                    task_instruction=formatted_instruction,
                    trace_id=trace_id,
                    model_override=model_id,
                    chat_description=chat_description
                )
                if response_text:
                    await context.bot.send_message(chat_id=chat.id, text=response_text, parse_mode=ParseMode.HTML)
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
            # Получаем описание чата для переменной {{group_rules}}
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

            # Для обычного ответа инструкция пуста, т.к. всё описано в "Ядре личности"
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
            
            parse_mode_for_response = ParseMode.MARKDOWN
            
            reply_params = ReplyParameters(message_id=message.message_id)
            try:
                await self._send_long_message(context, chat_id, response_text, trace_id, parse_mode=parse_mode_for_response, reply_parameters=reply_params)
            except BadRequest as e:
                if "Can't parse entities" in str(e):
                    logger.warning("Ошибка парсинга Markdown в ответе AI, отправляю как простой текст: %s", e, extra={'trace_id': trace_id})
                    await self._send_long_message(context, chat_id, response_text, trace_id, reply_parameters=reply_params)
                else:
                    logger.error("Ошибка BadRequest при отправке ответа AI: %s", e, extra={'trace_id': trace_id})
                    await message.reply_text("Произошла ошибка при отправке ответа.")

            if is_debug_mode and user.id in ADMIN_IDS_SET:
                # В `format_debug_info_text` больше не нужно передавать длины промптов,
                # так как эта информация теперь логируется в `ai_requests.log`
                debug_info = format_debug_info_text(
                    usage_metadata=usage_metadata,
                    system_prompt_len=0, # Устарело, но оставим для совместимости
                    chat_history_len=len(json.dumps(chat_history)),
                    question_len=len(question)
                )
                await self._send_long_message(context, chat_id, debug_info, trace_id, parse_mode=ParseMode.MARKDOWN_V2)

        except Exception as e:
            logger.error("Критическая ошибка при генерации ответа: %s", e, exc_info=True, extra={'trace_id': trace_id})
            await message.reply_text("Произошла внутренняя ошибка.")
        finally:
            typing_task.cancel()
