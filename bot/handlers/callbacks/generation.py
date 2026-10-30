# NVC_bot/bot/handlers/callbacks/generation.py
# version: 1.7.0
# 2026-10-30T06:30:00Z
"""
Обработчики инлайн-кнопок для меню настроек параметров генерации AI.

Version 1.7.0:
- FIX: Заменены вызовы `context.user_data.clear()` на `clear_conversation_user_data(context)`.
- FIX: Корректное описание типа числа (дробное / целое) в сообщении об ошибке валидации.
"""
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from telegram.error import BadRequest, TelegramError

from ...utils.formatters import escape_markdown_v2
from ...utils.context_helpers import clear_conversation_user_data
from ..states import FACILITATOR_SETTINGS, GENERATION_SETTINGS, AWAIT_GENERATION_VALUE
from .callback_patterns import CallbackPrefix

logger = logging.getLogger(__name__)


class GenerationCallbackHandler:
    """Обработчики для ветки /settings -> Параметры генерации."""

    GENERATION_PARAM_META = {
        "temperature": {"name": "Temperature", "type": float, "range": (0.0, 2.0)},
        "top_p": {"name": "Top P", "type": float, "range": (0.0, 1.0)},
        "top_k": {"name": "Top K", "type": int, "range": (1, 8192)},
        "max_output_tokens": {"name": "Max Tokens", "type": int, "range": (1, 8192)},
    }

    async def show_generation_settings_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        if query:
            await self._safe_answer_query(query)

        config = await self.db.get_generation_config()

        text_lines = [r"⚙️ *Параметры генерации AI*" "\n\n" r"Здесь можно тонко настроить поведение ИИ\-ассистента\." "\n"]

        buttons = []
        for key, meta in self.GENERATION_PARAM_META.items():
            value = config.get(key)
            text_lines.append(f"*{escape_markdown_v2(meta['name'])}*: `{value}`")
            buttons.append(InlineKeyboardButton(f"{meta['name']}", callback_data=f"{CallbackPrefix.GEN_CONFIG_EDIT}{key}"))

        kb = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
        kb.append([
            InlineKeyboardButton("🔄 Сбросить", callback_data=CallbackPrefix.GEN_CONFIG_RESET),
            InlineKeyboardButton("⬅️ Назад", callback_data=CallbackPrefix.BACK_TO_FACILITATOR_SETTINGS)
        ])

        text = "\n".join(text_lines)
        reply_markup = InlineKeyboardMarkup(kb)

        await self._safe_edit_message(query, text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
        return GENERATION_SETTINGS

    async def request_generation_value(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await self._safe_answer_query(query)

        param_key = query.data.replace(CallbackPrefix.GEN_CONFIG_EDIT, "")
        if param_key not in self.GENERATION_PARAM_META:
            return GENERATION_SETTINGS

        context.user_data["gen_param_key"] = param_key
        context.user_data["original_update"] = update

        current_value = (await self.db.get_generation_config()).get(param_key)

        help_texts = {
            "temperature": (
                r"✏️ *Изменение параметра: Temperature*" "\n\n"
                r"Этот параметр — *«термометр креативности»* бота\. Он контролирует, насколько случайными и творческими будут его ответы\." "\n\n"
                r"• *Низкие значения* \(`0.0` \- `0.4`\): Бот будет очень точным и последовательным\." "\n"
                r"• *Средние значения* \(`0.5` \- `0.8`\): Сбалансированный режим \(Рекомендуется\)\." "\n"
                r"• *Высокие значения* \(`0.9` и выше\): Высокая креативность\." "\n\n"
                rf"*Текущее значение: `{current_value}`*" "\n"
                r"*Введите число от `0.0` до `2.0`\.*" "\n\n"
                r"*Отправьте новое значение или /cancel для отмены\.*"
            ),
            "top_p": (
                r"✏️ *Изменение параметра: Top P*" "\n\n"
                r"Этот параметр — *«фильтр адекватности»*\. Он отсекает маловероятные слова при генерации ответа\." "\n\n"
                rf"*Текущее значение: `{current_value}`*" "\n"
                r"*Введите число от `0.0` до `1.0`\.*" "\n\n"
                r"*Отправьте новое значение или /cancel для отмены\.*"
            ),
            "top_k": (
                r"✏️ *Изменение параметра: Top K*" "\n\n"
                r"Ограничивает выбор следующего слова `K` самыми вероятными кандидатами\." "\n\n"
                rf"*Текущее значение: `{current_value}`*" "\n"
                r"*Введите целое число от `1` до `8192`\.*" "\n\n"
                r"*Отправьте новое значение или /cancel для отмены\.*"
            ),
            "max_output_tokens": (
                r"✏️ *Изменение параметра: Max Tokens*" "\n\n"
                r"Ограничитель максимальной длины ответа бота в токенах\." "\n\n"
                rf"*Текущее значение: `{current_value}`*" "\n"
                r"*Введите целое число от `1` до `8192`\.*" "\n\n"
                r"*Отправьте новое значение или /cancel для отмены\.*"
            )
        }

        text = help_texts.get(param_key, r"Ошибка: описание для этого параметра не найдено\.")
        await self._safe_edit_message(query, text, reply_markup=None, parse_mode=ParseMode.MARKDOWN_V2)
        return AWAIT_GENERATION_VALUE

    async def set_generation_value(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        msg = update.message
        param_key = context.user_data.get("gen_param_key")

        if not param_key or param_key not in self.GENERATION_PARAM_META:
            await msg.reply_text(r"❌ Внутренняя ошибка: не удалось определить параметр для изменения\.", parse_mode=ParseMode.MARKDOWN_V2)
            clear_conversation_user_data(context)
            return FACILITATOR_SETTINGS

        meta = self.GENERATION_PARAM_META[param_key]
        value_str = msg.text.strip().replace(',', '.')

        try:
            value = meta["type"](value_str)
            min_val, max_val = meta["range"]
            if min_val is not None and value < min_val:
                raise ValueError(f"значение должно быть не меньше {min_val}")
            if max_val is not None and value > max_val:
                raise ValueError(f"значение должно быть не больше {max_val}")
        except (ValueError, TypeError) as e:
            try:
                await msg.delete()
            except (BadRequest, TelegramError):
                pass
            original_update = context.user_data.get("original_update")
            if original_update and original_update.callback_query:
                num_type_label = "целое число" if meta["type"] is int else "число"
                error_text = (
                    fr"❌ *Неверное значение для {escape_markdown_v2(meta['name'])}*" "\n\n"
                    fr"Пожалуйста, введите *{num_type_label}* от `{meta['range'][0]}` до `{meta['range'][1]}`\." "\n"
                    fr"Ошибка: {escape_markdown_v2(str(e))}" "\n\n"
                    r"*Попробуйте снова или нажмите /cancel\.*"
                )
                await self._safe_edit_message(original_update.callback_query, error_text, parse_mode=ParseMode.MARKDOWN_V2)
            return AWAIT_GENERATION_VALUE

        await self.db.set_generation_config_value(param_key, value)

        try:
            await msg.delete()
        except (BadRequest, TelegramError) as e:
            logger.warning("Не удалось удалить сообщение пользователя при изменении параметра: %s", e)

        original_update = context.user_data.get("original_update")
        clear_conversation_user_data(context)

        if original_update:
            await self._safe_answer_query(original_update.callback_query, f"✅ {meta['name']} обновлен.")
            return await self.show_generation_settings_menu(original_update, context)

        return FACILITATOR_SETTINGS

    async def reset_generation_config_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await self.db.reset_generation_config()
        await self._safe_answer_query(query, "✅ Параметры генерации сброшены.")
        return await self.show_generation_settings_menu(update, context)
