# NVC_bot/bot/handlers/callbacks/welcome.py
# version: 1.3.1
# 2025-07-28T19:45:00Z
"""
Обработчики инлайн-кнопок для меню настроек Приветствий.

Version 1.3.1:
- FIX: Все сообщения переведены на `ParseMode.MARKDOWN_V2`.
- FIX: Имена моделей экранируются для безопасного отображения.
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from ...utils.formatters import escape_markdown_v2
from ..states import WELCOME_MENU, WELCOME_MODEL_MENU
from .callback_patterns import CallbackPrefix

class WelcomeCallbackHandler:
    """Обработчики для ветки /settings -> Приветствия."""

    async def show_welcomes_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await self._safe_answer_query(query)

        welcome_enabled = await self.db.is_welcome_enabled()
        welcome_status = "✅ Включены" if welcome_enabled else "❌ Выключены"
        welcome_model = await self.db.get_welcome_model()

        kb = [
            [InlineKeyboardButton(welcome_status, callback_data=CallbackPrefix.WELCOMES_TOGGLE)],
            [InlineKeyboardButton(f"🤖 Модель ИИ: {escape_markdown_v2(welcome_model)}", callback_data=CallbackPrefix.WELCOMES_MODEL)],
            [InlineKeyboardButton("📜 Промпт", callback_data=CallbackPrefix.WELCOMES_PROMPT)],
            [InlineKeyboardButton("⬅️ Назад", callback_data=CallbackPrefix.BACK_TO_FACILITATOR_SETTINGS)]
        ]
        text = "👋 *Настройки приветствий*\n\nЗдесь настраивается автоматическое приветствие новых участников чата\\."
        reply_markup = InlineKeyboardMarkup(kb)

        await self._safe_edit_message(query, text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
        return WELCOME_MENU

    async def toggle_welcome(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await self._safe_answer_query(query)
        await self._disable_keyboard(query)
        
        new_state = await self.db.toggle_welcome()
        await query.answer(f"Приветствия {'включены' if new_state else 'выключены'}")
        
        return await self.show_welcomes_menu(update, context)

    async def show_welcome_model_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await self._safe_answer_query(query)
        
        current_model = await self.db.get_welcome_model()
        text = f"🤖 *Выбор AI\\-модели для приветствий*\n\nТекущая модель: *{escape_markdown_v2(current_model)}*"
        
        kb = [[InlineKeyboardButton(("✅ " if name == current_model else "") + escape_markdown_v2(name), callback_data=f"{CallbackPrefix.WELCOMES_SET_MODEL}{name}")] for name in self.gemini.get_available_models()]
        kb.append([InlineKeyboardButton("⬅️ Назад", callback_data=CallbackPrefix.BACK_TO_WELCOMES_MENU)])
        
        await self._safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN_V2)
        return WELCOME_MODEL_MENU

    async def set_welcome_model(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await self._safe_answer_query(query)
        await self._disable_keyboard(query)
        
        model_name = query.data.replace(CallbackPrefix.WELCOMES_SET_MODEL, "")
        await self.db.set_welcome_model(model_name)
        await query.answer(f"Модель для приветствий переключена на {model_name}")
        
        return await self.show_welcome_model_menu(update, context)
