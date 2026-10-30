# NVC_bot/bot/handlers/callbacks/facilitator.py
# version: 3.0.0
# 2026-10-30T16:30:00Z

'''
Обработчики инлайн-кнопок для меню настроек ИИ-Фасилитатора (/settings).

Version 3.0.0:
- ADD: Переключатель проактивного фасилитатора споров (`toggle_proactive_facilitator`).
- UPGRADE: Отображение меток Free Tier / Paid Tier в меню выбора модели.
'''

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from ...utils.formatters import escape_markdown_v2, format_stats_text
from ..states import (
    FACILITATOR_SETTINGS,
    FACILITATOR_PROMPT_MENU,
)
from .callback_patterns import CallbackPrefix


class FacilitatorCallbackHandler:
    '''Обработчики для основной ветки /settings.'''

    async def show_facilitator_settings_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        '''Отображает главное меню настроек ИИ-фасилитатора.'''
        query = update.callback_query
        message = update.effective_message
        await self._safe_answer_query(query)

        model_status = self.gemini.get_current_model()
        debug_mode_enabled = await self.db.is_debug_mode_enabled()
        proactive_enabled = await self.db.is_proactive_facilitator_enabled()

        debug_status = "✅ Вкл" if debug_mode_enabled else "❌ Выкл"
        proactive_status = "✅ Вкл" if proactive_enabled else "❌ Выкл"

        kb = [
            [
                InlineKeyboardButton(f"🤖 Модель: {model_status}", callback_data=CallbackPrefix.FACILITATOR_MODEL),
                InlineKeyboardButton("📜 Промпт", callback_data=CallbackPrefix.FACILITATOR_PROMPT)
            ],
            [
                InlineKeyboardButton("⚙️ Генерация", callback_data=CallbackPrefix.GENERATION_SETTINGS),
                InlineKeyboardButton("📚 Контекст", callback_data=CallbackPrefix.CONTEXT_SETTINGS)
            ],
            [
                InlineKeyboardButton(f"🕊 Авто-медиатор споров: {proactive_status}", callback_data=CallbackPrefix.TOGGLE_PROACTIVE_FACILITATOR)
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

        text_parts = [
            "⚙️ *Настройки ИИ\-Фасилитатора*\n\n"
            f"• Основная модель: `{escape_markdown_v2(model_status)}`\n"
            f"• Проактивный медиатор при накале спора: *{escape_markdown_v2(proactive_status)}*"
        ]
        if debug_mode_enabled:
            text_parts.append(
                "\n_Режим отладки включен\. Ответы в группе и ЛС для администраторов содержат токен\-метрики\._"
            )
        text = "\n".join(text_parts)
        reply_markup = InlineKeyboardMarkup(kb)

        if query:
            await self._safe_edit_message(query, text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
        else:
            await message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)

        return FACILITATOR_SETTINGS

    async def toggle_debug_mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        '''Переключает режим отладки.'''
        query = update.callback_query
        new_state = await self.db.toggle_debug_mode()
        status_text = "включен (режим заметок)" if new_state else "выключен (режим диалога)"
        await self._safe_answer_query(query, f"Режим отладки {status_text}")
        return await self.show_facilitator_settings_menu(update, context)

    async def toggle_proactive_facilitator(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        '''Переключает режим проактивного вмешательства фасилитатора при серии триггеров в чате.'''
        query = update.callback_query
        new_state = await self.db.toggle_proactive_facilitator()
        await self._safe_answer_query(
            query,
            f"Авто-медиатор споров {'включен' if new_state else 'выключен'}"
        )
        return await self.show_facilitator_settings_menu(update, context)

    async def show_facilitator_model_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        '''Показывает меню выбора основной AI-модели (Free Tier и Paid Tier).'''
        query = update.callback_query
        await self._safe_answer_query(query)
        current = self.gemini.get_current_model()
        text = (
            f"🤖 *Выбор основной AI\-модели*\n\n"
            f"Текущая модель: `{escape_markdown_v2(current)}`\n"
            f"Модели с пометкой *Free* доступны на бесплатном тарифе AI Studio\."
        )
        kb = [
            [
                InlineKeyboardButton(
                    ("✅ " if name == current else "") + self.gemini.get_model_display_label(name),
                    callback_data=f"{CallbackPrefix.FACILITATOR_SET_MODEL}{name}"
                )
            ]
            for name in self.gemini.get_available_models()
        ]
        kb.append([InlineKeyboardButton("⬅️ Назад", callback_data=CallbackPrefix.BACK_TO_FACILITATOR_SETTINGS)])
        await self._safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN_V2)
        return FACILITATOR_SETTINGS

    async def switch_facilitator_model(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        '''Переключает активную модель Фасилитатора и сохраняет выбор в БД.'''
        query = update.callback_query
        model = query.data.replace(CallbackPrefix.FACILITATOR_SET_MODEL, "")
        if self.gemini.switch_model(model):
            await self.db.set_facilitator_model(model)
            await self._safe_answer_query(query, f"✅ Основная модель переключена на {model}")
        else:
            await self._safe_answer_query(query, "❌ Неизвестная модель", show_alert=True)
        return await self.show_facilitator_model_menu(update, context)

    async def show_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        '''Отображает статистику использования бота.'''
        query = update.callback_query
        await self._safe_answer_query(query)
        stats_data = await self.db.get_statistics()
        stats_text = format_stats_text(stats_data)
        kb = [[InlineKeyboardButton("⬅️ Назад", callback_data=CallbackPrefix.BACK_TO_FACILITATOR_SETTINGS)]]
        await self._safe_edit_message(query, stats_text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN_V2)
        return FACILITATOR_SETTINGS