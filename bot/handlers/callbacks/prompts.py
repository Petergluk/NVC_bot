# NVC_bot/bot/handlers/callbacks/prompts.py
# version: 1.9.0
# 2025-08-04T15:00:00Z
"""
Обработчики инлайн-кнопок для управления системными промптами.

Version 1.9.0:
- FEATURE: В меню редактирования "Промпта ИИ-Фасилитатора" добавлена
           подсказка о доступности переменной `{{group_rules}}`.

Version 1.8.0:
- FIX: Заменен вызов `context.user_data.clear()` на безопасную функцию
       `clear_conversation_user_data` для предотвращения сброса состояния
       диалога и исправления бага с неработающими диалогами.
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode, MessageLimit
from telegram.ext import ContextTypes, ConversationHandler

from ...config import settings
from ...utils.formatters import safe_markdown_preview, escape_markdown_v2
from ...utils.context_helpers import clear_conversation_user_data
from ..states import (FACILITATOR_PROMPT_MENU, MODERATION_PROMPT_MENU, MODERATION_TEMPLATE_MENU,
                      WELCOME_PROMPT_MENU, AWAIT_PROMPT_INPUT)
from .callback_patterns import CallbackPrefix

class PromptCallbackHandler:
    """Обработчики для меню управления текстами промптов."""

    async def _get_prompt_data(self, text_type: str) -> tuple:
        if text_type == "facilitator_prompt":
            content = await self.db.get_prompt()
            title = "📜 *Промпт ИИ\\-Фасилитатора*"
            back_cb = CallbackPrefix.BACK_TO_FACILITATOR_SETTINGS
            ret_state = FACILITATOR_PROMPT_MENU
            edit_cb = CallbackPrefix.EDIT_FACILITATOR_PROMPT
            reset_cb = CallbackPrefix.RESET_FACILITATOR_PROMPT
            return content, title, back_cb, ret_state, edit_cb, reset_cb
        elif text_type == "moderation_prompt":
            content = await self.db.get_moderation_prompt()
            title = "🔍 *Промпт Судьи*"
            back_cb = CallbackPrefix.BACK_TO_MODERATION_SETTINGS
            ret_state = MODERATION_PROMPT_MENU
            edit_cb = CallbackPrefix.EDIT_MODERATION_PROMPT
            reset_cb = CallbackPrefix.RESET_MODERATION_PROMPT
            return content, title, back_cb, ret_state, edit_cb, reset_cb
        elif text_type == "moderation_template":
            content = await self.db.get_moderation_task_template()
            title = "📝 *Промпт Сообщения о Санкции*"
            back_cb = CallbackPrefix.BACK_TO_MODERATION_SETTINGS
            ret_state = MODERATION_TEMPLATE_MENU
            edit_cb = CallbackPrefix.EDIT_MODERATION_TEMPLATE
            reset_cb = CallbackPrefix.RESET_MODERATION_TEMPLATE
            return content, title, back_cb, ret_state, edit_cb, reset_cb
        elif text_type == "welcome_prompt":
            content = await self.db.get_welcome_prompt()
            title = "👋 *Промпт Приветствия*"
            back_cb = CallbackPrefix.BACK_TO_WELCOMES_MENU
            ret_state = WELCOME_PROMPT_MENU
            edit_cb = CallbackPrefix.EDIT_WELCOME_PROMPT
            reset_cb = CallbackPrefix.RESET_WELCOME_PROMPT
            return content, title, back_cb, ret_state, edit_cb, reset_cb
        return None, None, None, None, None, None

    async def _show_text_management_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, text_type: str) -> int:
        query = update.callback_query
        if query:
            await self._safe_answer_query(query)
        
        text_content, title, back_cb, ret_state, edit_cb, reset_cb = await self._get_prompt_data(text_type)
        if text_content is None:
             return ConversationHandler.END

        kb = [[InlineKeyboardButton("✏️ Изменить", callback_data=edit_cb)]]
        
        preview = safe_markdown_preview(text_content, settings.PROMPT_PREVIEW_LENGTH)
        if len(text_content) > settings.PROMPT_PREVIEW_LENGTH:
            kb.append([InlineKeyboardButton("⬇️ Показать полностью", callback_data=f"{CallbackPrefix.SEND_FULL_PROMPT}{text_type}")])

        kb.extend([
            [InlineKeyboardButton("🔄 Сбросить", callback_data=reset_cb),
             InlineKeyboardButton("⬅️ Назад", callback_data=back_cb)]
        ])
        
        text = f"{title}:\n\n{preview}"
        
        await self._safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN_V2)
        return ret_state

    async def send_full_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        prompt_type = query.data.replace(CallbackPrefix.SEND_FULL_PROMPT, "")
        
        text_content, title, _, ret_state, _, _ = await self._get_prompt_data(prompt_type)
        
        if not text_content:
            await query.answer("❌ Не удалось найти текст промпта.", show_alert=True)
            return ret_state

        await query.answer()

        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"Полный текст для: {title}",
            parse_mode=ParseMode.MARKDOWN_V2
        )

        for i in range(0, len(text_content), MessageLimit.MAX_TEXT_LENGTH):
            chunk = text_content[i:i + MessageLimit.MAX_TEXT_LENGTH]
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=chunk
            )
        
        return ret_state

    async def show_facilitator_prompt_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        return await self._show_text_management_menu(update, context, "facilitator_prompt")

    async def show_moderation_prompt_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        return await self._show_text_management_menu(update, context, "moderation_prompt")
        
    async def show_moderation_template_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        return await self._show_text_management_menu(update, context, "moderation_template")

    async def show_welcome_prompt_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        return await self._show_text_management_menu(update, context, "welcome_prompt")

    async def request_prompt_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """
        Запрашивает у пользователя новый текст для промпта, не отображая текущий.
        Это предотвращает ошибки, связанные с превышением лимита длины сообщения.
        """
        query = update.callback_query
        await self._safe_answer_query(query)
        
        clear_conversation_user_data(context)

        cb_data = query.data
        prompt_type, prompt_text = "", ""
        
        if cb_data == CallbackPrefix.EDIT_FACILITATOR_PROMPT:
            prompt_type = "facilitator_prompt"
            prompt_text = (
                "Отправьте новый текст для *Промпта ИИ\\-Фасилитатора \\(Ядра Личности\\)*\\.\n\n"
                "*Доступные переменные:* `{{group_rules}}`\n\n"
                "Для отмены введите /cancel\\."
            )
        elif cb_data == CallbackPrefix.EDIT_MODERATION_PROMPT:
            prompt_type = "moderation_prompt"
            prompt_text = "Отправьте новый текст для *Промпта Судьи*\\.\n\n*Обязательная переменная:* `{{text}}`\n\nДля отмены введите /cancel\\."
        elif cb_data == CallbackPrefix.EDIT_MODERATION_TEMPLATE:
            prompt_type = "moderation_template"
            prompt_text = "Отправьте новый текст для *Промпта Сообщения о Санкции*\\.\n\n*Доступные переменные:* `{{user_mention}}`, `{{violator_message}}`, `{{warnings_count}}`, `{{rules_list}}`, `{{chat_history}}`, `{{group_rules}}`\n\nДля отмены введите /cancel\\."
        elif cb_data == CallbackPrefix.EDIT_WELCOME_PROMPT:
            prompt_type = "welcome_prompt"
            prompt_text = "Отправьте новый текст для *Промпта Приветствия*\\.\n\n*Обязательная переменная:* `{{user_mention}}`\n\nДля отмены введите /cancel\\."
        else:
            return ConversationHandler.END
            
        context.user_data["prompt_type"] = prompt_type
        context.user_data["original_update"] = update
        
        await self._safe_edit_message(query, prompt_text, reply_markup=None, parse_mode=ParseMode.MARKDOWN_V2)
        
        return AWAIT_PROMPT_INPUT

    async def reset_prompt_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await self._safe_answer_query(query)
        await self._disable_keyboard(query)
        
        cb_data = query.data
        if cb_data == CallbackPrefix.RESET_FACILITATOR_PROMPT:
            await self.db.reset_prompt()
            await query.answer("✅ Промпт Фасилитатора сброшен.")
            return await self.show_facilitator_prompt_menu(update, context)
        elif cb_data == CallbackPrefix.RESET_MODERATION_PROMPT:
            await self.db.reset_moderation_prompt()
            await query.answer("✅ Промпт Судьи сброшен.")
            return await self.show_moderation_prompt_menu(update, context)
        elif cb_data == CallbackPrefix.RESET_MODERATION_TEMPLATE:
            await self.db.reset_moderation_task_template()
            await query.answer("✅ Промпт Сообщения о Санкции сброшен.")
            return await self.show_moderation_template_menu(update, context)
        elif cb_data == CallbackPrefix.RESET_WELCOME_PROMPT:
            await self.db.reset_welcome_prompt()
            await query.answer("✅ Промпт Приветствия сброшен.")
            return await self.show_welcome_prompt_menu(update, context)
            
        return ConversationHandler.END
