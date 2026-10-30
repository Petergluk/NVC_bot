# NVC_bot/bot/handlers/callbacks/context.py
# version: 1.1.0
# 2026-10-30T06:30:00Z
"""
Обработчики инлайн-кнопок для меню настроек параметров контекста AI.

Version 1.1.0:
- FIX: Заменены вызовы `context.user_data.clear()` на `clear_conversation_user_data(context)`
       для предотвращения сброса служебного состояния ConversationHandler.
"""
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from telegram.error import BadRequest, TelegramError

from ...utils.formatters import escape_markdown_v2
from ...utils.context_helpers import clear_conversation_user_data
from ..states import FACILITATOR_SETTINGS, CONTEXT_SETTINGS, AWAIT_CONTEXT_VALUE
from .callback_patterns import CallbackPrefix

logger = logging.getLogger(__name__)


class ContextCallbackHandler:
    """Обработчики для ветки /settings -> Настройки контекста."""

    CONTEXT_PARAM_META = {
        "context_messages_limit": {"name": "Контекст диалога", "type": int, "range": (0, 100)},
        "context_judge_limit": {"name": "Контекст для Судьи", "type": int, "range": (0, 50)},
    }

    async def show_context_settings_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Показывает меню настроек лимитов контекста."""
        query = update.callback_query
        if query:
            await self._safe_answer_query(query)

        config = await self.db.get_context_config()

        text_lines = [
            "📚 *Настройки Контекста*\n",
            "Здесь настраивается, сколько последних сообщений бот 'помнит' при ответе или модерации\.",
            "• *Контекст диалога:* Глубина памяти для обычных ответов\.",
            "• *Контекст для Судьи:* Глубина памяти для анализа нарушений\.\n"
        ]

        buttons = []
        for key, meta in self.CONTEXT_PARAM_META.items():
            value = config.get(key)
            text_lines.append(f"*{escape_markdown_v2(meta['name'])}*: `{value}` сообщ\.")
            buttons.append(InlineKeyboardButton(f"{meta['name']}", callback_data=f"{CallbackPrefix.CONTEXT_CONFIG_EDIT}{key}"))

        kb = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
        kb.append([
            InlineKeyboardButton("🔄 Сбросить", callback_data=CallbackPrefix.CONTEXT_CONFIG_RESET),
            InlineKeyboardButton("⬅️ Назад", callback_data=CallbackPrefix.BACK_TO_FACILITATOR_SETTINGS)
        ])

        text = "\n".join(text_lines)
        reply_markup = InlineKeyboardMarkup(kb)

        await self._safe_edit_message(query, text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
        return CONTEXT_SETTINGS

    async def request_context_value(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Запрашивает новое значение для параметра контекста."""
        query = update.callback_query
        await self._safe_answer_query(query)

        param_key = query.data.replace(CallbackPrefix.CONTEXT_CONFIG_EDIT, "")
        if param_key not in self.CONTEXT_PARAM_META:
            return CONTEXT_SETTINGS

        meta = self.CONTEXT_PARAM_META[param_key]
        context.user_data["context_param_key"] = param_key
        context.user_data["original_update"] = update

        current_value = (await self.db.get_context_config()).get(param_key)
        min_val, max_val = meta["range"]

        text = (
            f"✏️ *Изменение параметра: {escape_markdown_v2(meta['name'])}*\n\n"
            f"Этот параметр определяет максимальное количество последних сообщений из истории чата, которое будет использоваться\.\n\n"
            f"*Текущее значение: `{current_value}`*\n"
            f"Введите целое число от `{min_val}` до `{max_val}`\.\n\n"
            "*Отправьте новое значение или /cancel для отмены\.*"
        )

        await self._safe_edit_message(query, text, reply_markup=None, parse_mode=ParseMode.MARKDOWN_V2)
        return AWAIT_CONTEXT_VALUE

    async def set_context_value(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Устанавливает новое значение для параметра контекста."""
        msg = update.message
        param_key = context.user_data.get("context_param_key")

        if not param_key or param_key not in self.CONTEXT_PARAM_META:
            await msg.reply_text("❌ Внутренняя ошибка: не удалось определить параметр для изменения\.", parse_mode=ParseMode.MARKDOWN_V2)
            clear_conversation_user_data(context)
            return FACILITATOR_SETTINGS

        meta = self.CONTEXT_PARAM_META[param_key]
        value_str = msg.text.strip()

        try:
            value = meta["type"](value_str)
            min_val, max_val = meta["range"]
            if not (min_val <= value <= max_val):
                raise ValueError(f"Значение должно быть в диапазоне от {min_val} до {max_val}.")
        except (ValueError, TypeError) as e:
            try:
                await msg.delete()
            except (BadRequest, TelegramError):
                pass
            original_update = context.user_data.get("original_update")
            if original_update and original_update.callback_query:
                error_text = (
                    f"❌ *Неверное значение для {escape_markdown_v2(meta['name'])}*\n\n"
                    f"Пожалуйста, введите *целое число* от `{meta['range'][0]}` до `{meta['range'][1]}`\.\n"
                    f"Ошибка: {escape_markdown_v2(str(e))}\n\n"
                    f"*Попробуйте снова или нажмите /cancel\.*"
                )
                await self._safe_edit_message(original_update.callback_query, error_text, parse_mode=ParseMode.MARKDOWN_V2)
            return AWAIT_CONTEXT_VALUE

        await self.db.set_context_config_value(param_key, value)

        try:
            await msg.delete()
        except (BadRequest, TelegramError) as e:
            logger.warning("Не удалось удалить сообщение пользователя при изменении параметра контекста: %s", e)

        original_update = context.user_data.get("original_update")
        clear_conversation_user_data(context)

        if original_update:
            await self._safe_answer_query(original_update.callback_query, f"✅ {meta['name']} обновлен.")
            return await self.show_context_settings_menu(original_update, context)

        return FACILITATOR_SETTINGS

    async def reset_context_config_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Сбрасывает параметры контекста к значениям по умолчанию."""
        query = update.callback_query
        await self.db.reset_context_config()
        await self._safe_answer_query(query, "✅ Параметры контекста сброшены.")
        return await self.show_context_settings_menu(update, context)