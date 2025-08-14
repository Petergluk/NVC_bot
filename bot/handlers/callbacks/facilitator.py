# NVC_bot/bot/handlers/callbacks/facilitator.py
# version: 2.0.0
# 2025-08-07T16:00:00Z
"""
Обработчики инлайн-кнопок для меню настроек Фасилитатора.

Version 2.0.0:
- FEATURE: Добавлено меню управления настройками безопасности (`safety_settings`).

Version 1.9.0:
- FIX: Устранено некорректное экранирование имен моделей в кнопках.
- FEATURE: Внедрены человекочитаемые имена моделей в UI.
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from ...config import MODEL_NAME_MAP, SAFETY_LEVEL_MAP
from ...utils.formatters import format_stats_text, escape_markdown_v2
from ..states import FACILITATOR_SETTINGS, SAFETY_SETTINGS_MENU
from .callback_patterns import CallbackPrefix
from .base import BaseCallbackHandler


class FacilitatorCallbackHandler(BaseCallbackHandler):
    """Обработчики для ветки /settings."""

    async def show_facilitator_settings_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Показывает главное меню настроек Фасилитатора."""
        query = update.callback_query
        message = update.effective_message
        if query:
            await self._safe_answer_query(query)
        
        model_id = await self.db.get_main_model()
        model_display_name = MODEL_NAME_MAP.get(model_id, model_id)
        debug_mode_enabled = await self.db.is_debug_mode_enabled()
        
        debug_desc = ""
        if debug_mode_enabled:
            debug_status = "✅ Вкл"
            debug_desc = "_Режим отладки включен\\. В личном чате сообщения, не адресованные боту, логируются как заметки и не отправляются AI\\. Ответы содержат техническую информацию\\._"
        else:
            debug_status = "❌ Выкл"

        kb = [
            [
                InlineKeyboardButton(f"🤖 Модель ИИ: {model_display_name}", callback_data=CallbackPrefix.FACILITATOR_MODEL),
                InlineKeyboardButton("📜 Промпт", callback_data=CallbackPrefix.FACILITATOR_PROMPT)
            ],
            [
                InlineKeyboardButton("⚙️ Генерация", callback_data=CallbackPrefix.GENERATION_SETTINGS),
                InlineKeyboardButton("🛡️ Безопасность", callback_data=CallbackPrefix.SAFETY_SETTINGS)
            ],
            [
                InlineKeyboardButton("📚 Контекст", callback_data=CallbackPrefix.CONTEXT_SETTINGS),
                InlineKeyboardButton("👋 Приветствия", callback_data=CallbackPrefix.WELCOMES_MENU)
            ],
            [
                InlineKeyboardButton(f"🐞 Отладка: {debug_status}", callback_data=CallbackPrefix.TOGGLE_DEBUG_MODE),
                InlineKeyboardButton("📊 Статистика", callback_data=CallbackPrefix.FACILITATOR_STATS)
            ],
            [
                InlineKeyboardButton("❌ Закрыть", callback_data=CallbackPrefix.CLOSE_MENU)
            ]
        ]
        
        text_parts = ["⚙️ *Настройки ИИ\\-Фасилитатора*\n\nЗдесь настраивается основная личность и модель бота\\."]
        if debug_desc:
            text_parts.append(f"\n*Режим отладки*:\n{debug_desc}")
        
        text = "\n".join(text_parts)
        reply_markup = InlineKeyboardMarkup(kb)

        if query:
            await self._safe_edit_message(query, text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
        else:
            await message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
            
        return FACILITATOR_SETTINGS

    async def toggle_debug_mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Переключает режим отладки."""
        query = update.callback_query
        
        new_state = await self.db.toggle_debug_mode()
        status_text = "включен (режим заметок)" if new_state else "выключен (режим диалога)"
        
        await self._safe_answer_query(query, f"Режим отладки {status_text}")
        
        return await self.show_facilitator_settings_menu(update, context)

    async def show_facilitator_model_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Показывает меню выбора основной AI-модели."""
        query = update.callback_query
        await self._safe_answer_query(query)
        
        current_model_id = await self.db.get_main_model()
        current_model_display_name = MODEL_NAME_MAP.get(current_model_id, current_model_id)
        
        text = f"🤖 *Выбор основной AI\\-модели*\n\nТекущая модель: *{escape_markdown_v2(current_model_display_name)}*"
        
        kb = []
        for model_id in self.gemini.get_available_models():
            display_name = MODEL_NAME_MAP.get(model_id, model_id)
            button_text = ("✅ " if model_id == current_model_id else "") + display_name
            callback_data = f"{CallbackPrefix.FACILITATOR_SET_MODEL}{model_id}"
            kb.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
            
        kb.append([InlineKeyboardButton("⬅️ Назад", callback_data=CallbackPrefix.BACK_TO_FACILITATOR_SETTINGS)])
        
        await self._safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN_V2)
        return FACILITATOR_SETTINGS

    async def switch_facilitator_model(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Переключает основную AI-модель."""
        query = update.callback_query
        
        model_name = query.data.replace(CallbackPrefix.FACILITATOR_SET_MODEL, "")
        await self.db.set_main_model(model_name)
        
        display_name = MODEL_NAME_MAP.get(model_name, model_name)
        await self._safe_answer_query(query, f"Основная модель переключена на {display_name}")
            
        return await self.show_facilitator_model_menu(update, context)

    async def show_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Показывает меню со статистикой."""
        query = update.callback_query
        await self._safe_answer_query(query)
        
        stats = await self.db.get_statistics()
        kb = [[InlineKeyboardButton("⬅️ Назад", callback_data=CallbackPrefix.BACK_TO_FACILITATOR_SETTINGS)]]
        
        await self._safe_edit_message(query, format_stats_text(stats), reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN_V2)
        return FACILITATOR_SETTINGS

    async def show_safety_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Показывает меню выбора уровня безопасности."""
        query = update.callback_query
        await self._safe_answer_query(query)
        
        current_level = await self.db.get_safety_level()
        
        text = (
            f"🛡️ *Настройки Безопасности*\n\n"
            f"Этот параметр контролирует, насколько строго ИИ фильтрует потенциально небезопасный контент\\. "
            f"Настройка **не влияет** на ИИ\\-Судью, который всегда анализирует сообщения без фильтров\\.\n\n"
            f"Текущий уровень: *{escape_markdown_v2(SAFETY_LEVEL_MAP.get(current_level, 'Неизвестный'))}*"
        )
        
        kb = []
        for level_id, level_name in SAFETY_LEVEL_MAP.items():
            button_text = ("✅ " if level_id == current_level else "") + level_name
            callback_data = f"{CallbackPrefix.SAFETY_SET_LEVEL}{level_id}"
            kb.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
            
        kb.append([InlineKeyboardButton("⬅️ Назад", callback_data=CallbackPrefix.BACK_TO_FACILITATOR_SETTINGS)])
        
        await self._safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN_V2)
        return SAFETY_SETTINGS_MENU

    async def set_safety_level(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Устанавливает новый уровень безопасности."""
        query = update.callback_query
        
        level_id = query.data.replace(CallbackPrefix.SAFETY_SET_LEVEL, "")
        if level_id in SAFETY_LEVEL_MAP:
            await self.db.set_safety_level(level_id)
            await self._safe_answer_query(query, f"Уровень безопасности изменен.")
        else:
            await self._safe_answer_query(query, "Ошибка: неизвестный уровень безопасности.")
            
        return await self.show_safety_menu(update, context)
