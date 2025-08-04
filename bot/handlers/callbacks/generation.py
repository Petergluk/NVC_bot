# NVC_bot/bot/handlers/callbacks/generation.py
# version: 1.6.2
# 2025-07-28T20:30:00Z
"""
Обработчики инлайн-кнопок для меню настроек параметров генерации AI.

Version 1.6.2:
- FIX: Все тексты подсказок полностью экранированы для `ParseMode.MARKDOWN_V2`,
       чтобы окончательно устранить ошибки `Can't parse entities`.
"""
import logging
from typing import Dict
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from telegram.error import BadRequest, TelegramError

from ...utils.formatters import escape_markdown_v2
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
        
        text_lines = ["⚙️ *Параметры генерации AI*\n\nЗдесь можно тонко настроить поведение ИИ\\-ассистента\\.\n"]
        
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

        meta = self.GENERATION_PARAM_META[param_key]
        context.user_data["gen_param_key"] = param_key
        context.user_data["original_update"] = update
        
        current_value = (await self.db.get_generation_config()).get(param_key)

        # FIX: Полностью экранированные тексты
        help_texts = {
            "temperature": (
                f"✏️ *Изменение параметра: Temperature*\n\n"
                f"Этот параметр — *\"термометр креативности\"* бота\\. Он контролирует, насколько случайными и творческими будут его ответы\\.\n\n"
                f"• *Низкие значения* \\(`0.0` \\- `0.4`\\): Бот будет очень точным, последовательным и немного \"сухим\"\\. Идеально для задач, где нужен четкий ответ по фактам\\.\n"
                f"• *Средние значения* \\(`0.5` \\- `0.8`\\): Сбалансированный режим\\. Ответы будут достаточно живыми, но при этом строго по теме\\. *\\(Рекомендуется\\)*\\.\n"
                f"• *Высокие значения* \\(`0.9` и выше\\): Бот становится \"фантазером\" с креативностью на грани бреда\\. Может генерировать неожиданные идеи, но иногда рискует \"уйти\" от сути вопроса\\.\n\n"
                f"*Текущее значение: `{current_value}`*\n"
                f"*Введите десятичную дробь от `0.0` до `2.0`*\\.\n\n"
                "**Отправьте новое значение или /cancel для отмены\\.**"
            ),
            "top_p": (
                f"✏️ *Изменение параметра: Top P*\n\n"
                f"Этот параметр — *\"фильтр адекватности\"*\\. Он отсекает маловероятные, странные или неуместные слова при генерации ответа\\.\n\n"
                f"• *Высокие значения* \\(`0.95` \\- `1.0`\\): Фильтр почти выключен\\. Бот может использовать очень редкие и неожиданные слова\\.\n"
                f"• *Низкие значения* \\(ниже `0.8`\\): Очень строгий фильтр\\. Бот будет использовать только самые безопасные и предсказуемые слова\\.\n\n"
                f"*Совет:* _Обычно изменяют либо `Temperature`, либо `Top P`\\. Не рекомендуется задавать низкие значения для обоих одновременно\\._\n\n"
                f"*Текущее значение: `{current_value}`*\n"
                f"*Введите десятичную дробь от `0.0` до `1.0`*\\.\n\n"
                "**Отправьте новое значение или /cancel для отмены\\.**"
            ),
            "top_k": (
                f"✏️ *Изменение параметра: Top K*\n\n"
                f"Этот параметр ограничивает *\"активный словарь\"* бота на каждом шаге генерации ответа\\. Он заставляет модель выбирать следующее слово только из `K` самых вероятных кандидатов\\.\n\n"
                f"• *Низкие значения* \\(`1` \\- `10`\\): Делает ответы очень предсказуемыми\\. При `1` бот всегда будет выбирать самое очевидное слово\\.\n"
                f"• *Средние значения* \\(`11` \\- `40`\\): Сбалансированный режим, предоставляющий хороший выбор слов без излишней предсказуемости\\.\n"
                f"• *Высокие значения* \\(выше `40`\\): Дает боту больше свободы в выборе слов\\. Значения выше нескольких сотен практически не влияют на результат, так как активный словарь для конкретного контекста редко превышает это число\\.\n\n"
                f"*Совет:* _Этот параметр используется редко\\. Для контроля креативности лучше использовать `Temperature` или `Top P`\\._\n\n"
                f"*Текущее значение: `{current_value}`*\n"
                f"*Введите целое число от `1` до `8192`*\\.\n\n"
                "**Отправьте новое значение или /cancel для отмены\\.**"
            ),
            "max_output_tokens": (
                f"✏️ *Изменение параметра: Max Tokens*\n\n"
                f"Это прямой *ограничитель максимальной длины ответа* бота\\.\n\n"
                f"Он определяет, сколько \"частей слов\" \\(токенов\\) может содержать сгенерированный ответ\\. Это полезно, чтобы ответы не были слишком короткими или бесконечно длинными\\.\n\n"
                f"*Примерно: `100` токенов ≈ `60-70` слов на русском языке\\.*\n\n"
                f"*Текущее значение: `{current_value}`*\n"
                f"*Введите целое число от `1` до `8192`*\\.\n\n"
                "**Отправьте новое значение или /cancel для отмены\\.**"
            )
        }
        
        text = help_texts.get(param_key, "Ошибка: описание для этого параметра не найдено\\.")
        await self._safe_edit_message(query, text, reply_markup=None, parse_mode=ParseMode.MARKDOWN_V2)
        return AWAIT_GENERATION_VALUE

    async def set_generation_value(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        msg = update.message
        param_key = context.user_data.get("gen_param_key")

        if not param_key or param_key not in self.GENERATION_PARAM_META:
            await msg.reply_text("❌ Внутренняя ошибка: не удалось определить параметр для изменения\\.")
            context.user_data.clear()
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
            await msg.delete()
            original_update = context.user_data.get("original_update")
            if original_update and original_update.callback_query:
                error_text = (
                    f"❌ *Неверное значение для {escape_markdown_v2(meta['name'])}*\n\n"
                    f"Пожалуйста, введите *целое число* от `{meta['range'][0]}` до `{meta['range'][1]}`\\.\n"
                    f"Ошибка: {escape_markdown_v2(str(e))}\n\n"
                    f"**Попробуйте снова или нажмите /cancel\\.**"
                )
                await self._safe_edit_message(original_update.callback_query, error_text, parse_mode=ParseMode.MARKDOWN_V2)
            return AWAIT_GENERATION_VALUE

        await self.db.set_generation_config_value(param_key, value)
        
        try:
            await msg.delete()
        except (BadRequest, TelegramError) as e:
            logger.warning("Не удалось удалить сообщение пользователя при изменении параметра: %s", e)

        original_update = context.user_data.pop("original_update", None)
        context.user_data.clear()
        
        if original_update:
            await self._safe_answer_query(original_update.callback_query, f"✅ {meta['name']} обновлен.")
            return await self.show_generation_settings_menu(original_update, context)
        
        return FACILITATOR_SETTINGS

    async def reset_generation_config_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await self._safe_answer_query(query, "Выполняется сброс...")
        
        await self.db.reset_generation_config()
        
        await self._safe_answer_query(query, "✅ Параметры сброшены.")
        return await self.show_generation_settings_menu(update, context)
