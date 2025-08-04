# NVC_bot/bot/handlers/callbacks/facilitator.py
# version: 1.7.0
# 2025-07-29T18:00:00Z
"""
Обработчики инлайн-кнопок для меню настроек Фасилитатора.

Version 1.7.0:
- AUDIT-FIX: Полностью переработаны описания режима отладки для ясности.
             Описание теперь отображается только при включенном режиме.

Version 1.6.0:
- AUDIT-FIX: Обновлены тексты для режима отладки.
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from ...utils.formatters import format_stats_text, escape_markdown_v2
from ..states import FACILITATOR_SETTINGS
from .callback_patterns import CallbackPrefix


class FacilitatorCallbackHandler:
    """Обработчики для ветки /settings."""

    async def show_facilitator_settings_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Показывает главное меню настроек Фасилитатора."""
        query = update.callback_query
        message = update.effective_message
        await self._safe_answer_query(query)
        
        model_status = self.gemini.get_current_model()
        debug_mode_enabled = await self.db.is_debug_mode_enabled()
        
        debug_desc = ""
        if debug_mode_enabled:
            debug_status = "✅ Вкл"
            debug_desc = "_Режим отладки включен\\. В личном чате сообщения, не адресованные боту, логируются как заметки и не отправляются AI\\. Ответы содержат техническую информацию\\._"
        else:
            debug_status = "❌ Выкл"
            # В штатном режиме описание не нужно

        kb = [
            [
                InlineKeyboardButton(f"🤖 Модель ИИ: {escape_markdown_v2(model_status)}", callback_data=CallbackPrefix.FACILITATOR_MODEL),
                InlineKeyboardButton("📜 Промпт", callback_data=CallbackPrefix.FACILITATOR_PROMPT)
            ],
            [
                InlineKeyboardButton("⚙️ Генерация", callback_data=CallbackPrefix.GENERATION_SETTINGS),
                InlineKeyboardButton("📚 Контекст", callback_data=CallbackPrefix.CONTEXT_SETTINGS)
            ],
            [
                InlineKeyboardButton("👋 Приветствия", callback_data=CallbackPrefix.WELCOMES_MENU),
                InlineKeyboardButton(f"🐞 Отладка: {debug_status}", callback_data=CallbackPrefix.TOGGLE_DEBUG_MODE)
            ],
            [
                InlineKeyboardButton("📊 Статистика", callback_data=CallbackPrefix.FACILITATOR_STATS),
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
        
        current = self.gemini.get_current_model()
        text = f"🤖 *Выбор основной AI\\-модели*\n\nТекущая модель: *{escape_markdown_v2(current)}*"
        
        kb = [[InlineKeyboardButton(("✅ " if name == current else "") + escape_markdown_v2(name), callback_data=f"{CallbackPrefix.FACILITATOR_SET_MODEL}{name}")] for name in self.gemini.get_available_models()]
        kb.append([InlineKeyboardButton("⬅️ Назад", callback_data=CallbackPrefix.BACK_TO_FACILITATOR_SETTINGS)])
        
        await self._safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN_V2)
        return FACILITATOR_SETTINGS

    async def switch_facilitator_model(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Переключает основную AI-модель."""
        query = update.callback_query
        await self._safe_answer_query(query)
        await self._disable_keyboard(query)
        
        model = query.data.replace(CallbackPrefix.FACILITATOR_SET_MODEL, "")
        if self.gemini.switch_model(model):
            await query.answer(f"Модель переключена на {model}")
        else:
            await query.answer("Не удалось переключить модель.", show_alert=True)
            
        return await self.show_facilitator_model_menu(update, context)

    async def show_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Показывает меню со статистикой."""
        query = update.callback_query
        await self._safe_answer_query(query)
        
        stats = await self.db.get_statistics()
        kb = [[InlineKeyboardButton("⬅️ Назад", callback_data=CallbackPrefix.BACK_TO_FACILITATOR_SETTINGS)]]
        
        await self._safe_edit_message(query, format_stats_text(stats), reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN_V2)
        return FACILITATOR_SETTINGS
