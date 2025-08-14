# NVC_bot/bot/handlers/callbacks/welcome.py
# version: 2.0.0
# 2025-08-12T15:45:00Z
"""
Обработчики инлайн-кнопок для меню настроек Приветствий.

Version 2.0.0:
- FIX: Текст кнопки "Промпт" изменен на "Текст Приветствия" для лучшего
       соответствия архитектуре "личность + задача".

Version 1.4.0:
- FIX: Устранено некорректное экранирование имен моделей в кнопках.
- FEATURE: Внедрены человекочитаемые имена моделей в UI из `MODEL_NAME_MAP`.
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from ...config import MODEL_NAME_MAP
from ...utils.formatters import escape_markdown_v2
from ..states import WELCOME_MENU, WELCOME_MODEL_MENU
from .callback_patterns import CallbackPrefix

class WelcomeCallbackHandler:
    """Обработчики для ветки /settings -> Приветствия."""

    async def show_welcomes_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        if query:
            await self._safe_answer_query(query)

        welcome_enabled = await self.db.is_welcome_enabled()
        welcome_status = "✅ Включены" if welcome_enabled else "❌ Выключены"
        
        welcome_model_id = await self.db.get_welcome_model()
        welcome_model_display_name = MODEL_NAME_MAP.get(welcome_model_id, welcome_model_id)

        kb = [
            [InlineKeyboardButton(welcome_status, callback_data=CallbackPrefix.WELCOMES_TOGGLE)],
            [InlineKeyboardButton(f"🤖 Модель ИИ: {welcome_model_display_name}", callback_data=CallbackPrefix.WELCOMES_MODEL)],
            # FIX: Кнопка переименована для ясности.
            [InlineKeyboardButton("📝 Текст Приветствия", callback_data=CallbackPrefix.WELCOMES_PROMPT)],
            [InlineKeyboardButton("⬅️ Назад", callback_data=CallbackPrefix.BACK_TO_FACILITATOR_SETTINGS)]
        ]
        text = "👋 *Настройки приветствий*\n\nЗдесь настраивается автоматическое приветствие новых участников чата\\."
        reply_markup = InlineKeyboardMarkup(kb)

        await self._safe_edit_message(query, text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
        return WELCOME_MENU

    async def toggle_welcome(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        
        new_state = await self.db.toggle_welcome()
        await query.answer(f"Приветствия {'включены' if new_state else 'выключены'}")
        
        return await self.show_welcomes_menu(update, context)

    async def show_welcome_model_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await self._safe_answer_query(query)
        
        current_model_id = await self.db.get_welcome_model()
        current_model_display_name = MODEL_NAME_MAP.get(current_model_id, current_model_id)
        
        text = f"🤖 *Выбор AI\\-модели для приветствий*\n\nТекущая модель: *{escape_markdown_v2(current_model_display_name)}*"
        
        kb = []
        for model_id in self.gemini.get_available_models():
            display_name = MODEL_NAME_MAP.get(model_id, model_id)
            button_text = ("✅ " if model_id == current_model_id else "") + display_name
            callback_data = f"{CallbackPrefix.WELCOMES_SET_MODEL}{model_id}"
            kb.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
            
        kb.append([InlineKeyboardButton("⬅️ Назад", callback_data=CallbackPrefix.BACK_TO_WELCOMES_MENU)])
        
        await self._safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN_V2)
        return WELCOME_MODEL_MENU

    async def set_welcome_model(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        
        model_id = query.data.replace(CallbackPrefix.WELCOMES_SET_MODEL, "")
        await self.db.set_welcome_model(model_id)
        
        display_name = MODEL_NAME_MAP.get(model_id, model_id)
        await query.answer(f"Модель для приветствий переключена на {display_name}")
        
        return await self.show_welcome_model_menu(update, context)
