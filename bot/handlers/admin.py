# NVC_bot/bot/handlers/admin.py
# version: 4.0.0
# 2026-10-30T06:30:00Z
"""
Обработчики команд, доступных только администраторам.

Version 4.0.0:
- FIX: Устранена гонка состояний в `handle_prompt_message` / `_commit_prompt_changes`,
       из-за которой после сохранения промпта бот оставался в состоянии `AWAIT_PROMPT_INPUT`
       и переставал реагировать на инлайн-кнопки меню.
- FIX: Добавлен `parse_mode=ParseMode.MARKDOWN_V2` для уведомления об успешном
       обновлении промпта и поддержка валидаторов с `{var}` и `{{var}}`.
"""
import logging
import re
import uuid
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode
from telegram.error import TelegramError, BadRequest

from ..utils.decorators import admin_only, log_action
from ..utils.validators import (
    validate_prompt,
    validate_moderation_prompt,
    validate_moderation_template,
    validate_welcome_prompt,
)
from ..utils.formatters import escape_markdown_v2, format_stats_text
from ..utils.context_helpers import clear_conversation_user_data
from ..database import Database
from ..services.gemini import GeminiService
from .callbacks import CallbackHandlers
from .states import (
    FACILITATOR_SETTINGS,
    MODERATION_SETTINGS,
    AWAIT_PROMPT_INPUT,
)

logger = logging.getLogger(__name__)


class AdminHandlers:
    """Класс, инкапсулирующий обработчики административных команд."""

    def __init__(self, db: Database, gemini_service: GeminiService):
        self.db = db
        self.gemini_service = gemini_service
        self.callback_handlers: CallbackHandlers | None = None

    def set_callback_handlers(self, callback_handlers: CallbackHandlers):
        self.callback_handlers = callback_handlers

    @admin_only
    @log_action("settings")
    async def settings_entry_point(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        if not self.callback_handlers:
            return ConversationHandler.END
        if update.message:
            try:
                await update.message.delete()
            except (BadRequest, TelegramError) as e:
                logger.warning("Не удалось удалить /settings: %s", e)
        await self.callback_handlers.show_facilitator_settings_menu(update, context)
        return FACILITATOR_SETTINGS

    @admin_only
    @log_action("moderate")
    async def moderate_entry_point(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        if not self.callback_handlers:
            return ConversationHandler.END
        if update.message:
            try:
                await update.message.delete()
            except (BadRequest, TelegramError) as e:
                logger.warning("Не удалось удалить /moderate: %s", e)
        await self.callback_handlers.show_moderate_settings_menu(update, context)
        return MODERATION_SETTINGS

    @admin_only
    @log_action("handle_prompt_message")
    async def handle_prompt_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """
        Валидирует, сохраняет новый текст промпта и возвращает пользователя
        в соответствующее меню управления промптом.
        """
        trace_id = context.user_data.get('trace_id', str(uuid.uuid4()))
        prompt_type = context.user_data.get("prompt_type")
        original_update = context.user_data.get("original_update")
        new_text = (update.message.text or "").strip() if update.message else ""

        if not all([prompt_type, new_text, original_update]) or not self.callback_handlers:
            logger.error("Недостаточно данных для сохранения промпта.", extra={'trace_id': trace_id})
            clear_conversation_user_data(context)
            return ConversationHandler.END

        original_query = original_update.callback_query
        chat_id = original_query.message.chat_id if (original_query and original_query.message) else update.effective_chat.id

        save_actions = {
            "facilitator_prompt": (validate_prompt, self.db.set_prompt, self.callback_handlers.show_facilitator_prompt_menu),
            "moderation_prompt": (validate_moderation_prompt, self.db.set_moderation_prompt, self.callback_handlers.show_moderation_prompt_menu),
            "moderation_template": (validate_moderation_template, self.db.set_moderation_task_template, self.callback_handlers.show_moderation_template_menu),
            "welcome_prompt": (validate_welcome_prompt, self.db.set_welcome_prompt, self.callback_handlers.show_welcome_prompt_menu),
        }

        action_tuple = save_actions.get(prompt_type)
        if not action_tuple:
            clear_conversation_user_data(context)
            return ConversationHandler.END

        validator, saver, menu_update_func = action_tuple
        error_message = validator(new_text)

        if error_message:
            await context.bot.send_message(
                chat_id=chat_id,
                text=fr"❌ Ошибка валидации: {escape_markdown_v2(error_message)}" "\n" r"Попробуйте отправить исправленный текст или введите /cancel\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return AWAIT_PROMPT_INPUT

        await saver(new_text)
        logger.info("Промпт '%s' успешно сохранен. Длина: %d", prompt_type, len(new_text), extra={'trace_id': trace_id})

        if update.message:
            try:
                await update.message.delete()
            except (BadRequest, TelegramError) as e:
                logger.warning("Не удалось удалить сообщение с новым промптом: %s", e)

        await context.bot.send_message(
            chat_id=chat_id,
            text=fr"✅ Промпт успешно обновлен\. Длина: `{len(new_text)}` симв\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )

        clear_conversation_user_data(context)
        return await menu_update_func(original_update, context)

    @admin_only
    @log_action("cancel_conversation")
    async def cancel_conversation(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        if 'prompt_commit_task' in context.user_data:
            context.user_data['prompt_commit_task'].cancel()

        query = update.callback_query
        if query and query.message:
            try:
                await query.delete_message()
            except (BadRequest, TelegramError) as e:
                logger.warning("Не удалось удалить сообщение меню при отмене: %s", e)
        elif update.message:
            original_update = context.user_data.get("original_update")
            try:
                await update.message.delete()
            except (BadRequest, TelegramError) as e:
                logger.warning("Не удалось удалить команду /cancel: %s", e)
            if original_update and self.callback_handlers and original_update.callback_query:
                try:
                    await original_update.callback_query.delete_message()
                except (BadRequest, TelegramError):
                    pass

        clear_conversation_user_data(context)
        return ConversationHandler.END

    @admin_only
    @log_action("stats")
    async def show_stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        stats = await self.db.get_statistics()
        text = format_stats_text(stats)
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)

    @admin_only
    @log_action("warnings")
    async def manage_warnings(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        args, message, trace_id = context.args, update.message, str(uuid.uuid4())
        target_id, amount_str = None, None

        if message.reply_to_message:
            target_id = message.reply_to_message.from_user.id
            if args:
                amount_str = args[0]
        elif len(args) >= 1:
            target_id_str = args[0]
            if len(args) > 1 and re.match(r"^[+-]?\d+$", args[1]):
                amount_str = args[1]
            try:
                if target_id_str.isdigit():
                    target_id = int(target_id_str)
                elif target_id_str.startswith('@'):
                    target_id = (await context.bot.get_chat(chat_id=target_id_str)).id
                else:
                    raise ValueError("Неверный формат")
            except (TelegramError, ValueError):
                await message.reply_text(
                    fr"❌ Не удалось найти пользователя `{escape_markdown_v2(target_id_str)}`\.",
                    parse_mode=ParseMode.MARKDOWN_V2
                )
                return

        if not target_id:
            await message.reply_text(
                r"*Как использовать:* `/warnings <user_id/@username> [+/-N]` или ответом на сообщение\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return

        try:
            user_info = await context.bot.get_chat(target_id)
            user_mention = escape_markdown_v2(f"@{user_info.username}" if user_info.username else user_info.full_name)
        except Exception as e:
            logger.warning("Не удалось получить инфо о пользователе %d: %s", target_id, e, extra={'trace_id': trace_id})
            user_mention = f"пользователь с ID `{target_id}`"

        if amount_str:
            if not re.match(r"^[+-]?\d+$", amount_str):
                await message.reply_text(r"❌ Неверный формат количества: `+1`, `\-1`\.", parse_mode=ParseMode.MARKDOWN_V2)
                return
            new_count = await self.db.adjust_warnings(target_id, int(amount_str))
            await message.reply_text(
                fr"✅ Варны для {user_mention} изменены\. Теперь: *{new_count}*\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
        else:
            count = await self.db.get_warnings(target_id)
            await message.reply_text(
                fr"ℹ️ У {user_mention} *{count}* варн\(ов\)\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
