# NVC_bot/bot/handlers/callbacks/moderation.py
# version: 1.4.0
# 2026-10-30T06:30:00Z
"""
Обработчики инлайн-кнопок для меню настроек Модерации.

Version 1.4.0:
- FIX: Устранены двойные вызовы `query.answer()` в `toggle_moderation`,
       `set_moderation_model` и `reset_user_warnings`.
- FIX: Из текста кнопок (`InlineKeyboardButton`) убрано лишнее экранирование
       `escape_markdown_v2`, которое выводило обратные слэши на кнопках.
"""
from typing import Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from ...utils.formatters import escape_markdown_v2
from ..states import (
    MODERATION_SETTINGS,
    MODERATION_MODEL_MENU,
    SANCTIONS_MENU,
    AWAIT_SANCTION_VALUE,
    USERS_MENU,
)
from .callback_patterns import CallbackPrefix


class ModerationCallbackHandler:
    """Обработчики для основной ветки /moderate."""

    async def show_moderate_settings_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Отображает главное меню настроек модерации."""
        query = update.callback_query
        message = update.effective_message
        await self._safe_answer_query(query)

        mod_enabled = await self.db.is_moderation_enabled()
        mod_status = "✅ Включена" if mod_enabled else "❌ Выключена"
        mod_model = await self.db.get_moderation_model()

        kb = [
            [InlineKeyboardButton(mod_status, callback_data=CallbackPrefix.MODERATE_TOGGLE)],
            [
                InlineKeyboardButton("🔍 Промпт Судьи", callback_data=CallbackPrefix.MODERATE_PROMPT),
                InlineKeyboardButton("📝 Промпт Санкций", callback_data=CallbackPrefix.MODERATE_TEMPLATE)
            ],
            [
                InlineKeyboardButton(f"⚖️ Модель: {mod_model}", callback_data=CallbackPrefix.MODERATE_MODEL),
                InlineKeyboardButton("🔨 Санкции", callback_data=CallbackPrefix.MODERATE_SANCTIONS)
            ],
            [
                InlineKeyboardButton("🎯 Триггеры", callback_data=CallbackPrefix.MANAGE_TRIGGERS),
                InlineKeyboardButton("🛡️ Исключения", callback_data=CallbackPrefix.MANAGE_EXCEPTIONS)
            ],
            [InlineKeyboardButton("👥 Пользователи", callback_data=CallbackPrefix.MODERATE_USERS)],
            [InlineKeyboardButton("❌ Закрыть", callback_data=CallbackPrefix.CLOSE_MENU)]
        ]
        text = r"🛂 *Настройки модерации*" "\n\n" r"Управление автоматическим ИИ\-модератором чата\."
        reply_markup = InlineKeyboardMarkup(kb)

        if query:
            await self._safe_edit_message(query, text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
        else:
            await message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)

        return MODERATION_SETTINGS

    async def toggle_moderation(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Переключает статус модерации (вкл/выкл)."""
        query = update.callback_query
        new_state = await self.db.toggle_moderation()
        await self._safe_answer_query(query, f"Модерация {'включена' if new_state else 'выключена'}")
        return await self.show_moderate_settings_menu(update, context)

    async def show_moderation_model_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Показывает меню выбора модели для модерации."""
        query = update.callback_query
        await self._safe_answer_query(query)

        current = await self.db.get_moderation_model()
        text = fr"⚖️ *Выбор ИИ\-Судьи*" "\n\n" fr"Текущий судья: *{escape_markdown_v2(current)}*"

        kb = [
            [InlineKeyboardButton(("✅ " if name == current else "") + name, callback_data=f"{CallbackPrefix.MODERATE_SET_MODEL}{name}")]
            for name in self.gemini.get_available_models()
        ]
        kb.append([InlineKeyboardButton("⬅️ Назад", callback_data=CallbackPrefix.BACK_TO_MODERATION_SETTINGS)])

        await self._safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN_V2)
        return MODERATION_MODEL_MENU

    async def set_moderation_model(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Устанавливает новую модель для модерации."""
        query = update.callback_query
        model = query.data.replace(CallbackPrefix.MODERATE_SET_MODEL, "")
        await self.db.set_moderation_model(model)
        await self._safe_answer_query(query, f"✅ ИИ-Судья переключён на {model}")
        return await self.show_moderation_model_menu(update, context)

    async def _get_sanctions_menu_content(self) -> Tuple[str, InlineKeyboardMarkup]:
        """Формирует текст и клавиатуру для меню санкций."""
        rules = await self.db.get_sanction_rules()
        rules_map = {(r['action'], r.get('duration_hours')): r['warnings'] for r in rules}

        mute_24 = rules_map.get(('MUTE', 24))
        mute_168 = rules_map.get(('MUTE', 168))
        ban = rules_map.get(('BAN', None))

        rules_lines = [
            fr"• Мьют на сутки \- *{mute_24}* пред\." if mute_24 else r"• Мьют на сутки \- *отключен*",
            fr"• Мьют на неделю \- *{mute_168}* пред\." if mute_168 else r"• Мьют на неделю \- *отключен*",
            fr"• Бан \- *{ban}* пред\." if ban else r"• Бан \- *отключен*"
        ]
        text = "🔨 *Настройка правил санкций*\n\n*Текущие правила:*\n" + "\n".join(rules_lines)

        kb = [
            [InlineKeyboardButton("Мьют на сутки", callback_data=f"{CallbackPrefix.SANCTION_SET}MUTE_24")],
            [InlineKeyboardButton("Мьют на неделю", callback_data=f"{CallbackPrefix.SANCTION_SET}MUTE_168")],
            [InlineKeyboardButton("Бан", callback_data=f"{CallbackPrefix.SANCTION_SET}BAN_None")],
            [InlineKeyboardButton("⬅️ Назад", callback_data=CallbackPrefix.BACK_TO_MODERATION_SETTINGS)]
        ]
        return text, InlineKeyboardMarkup(kb)

    async def show_sanctions_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Отображает меню управления санкциями."""
        query = update.callback_query
        await self._safe_answer_query(query)
        text, reply_markup = await self._get_sanctions_menu_content()
        await self._safe_edit_message(query, text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
        return SANCTIONS_MENU

    async def sanction_request_value(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Запрашивает количество предупреждений для установки правила санкции."""
        query = update.callback_query
        await self._safe_answer_query(query)

        data = query.data.replace(CallbackPrefix.SANCTION_SET, "")
        action, dur_str = data.split("_")
        duration = int(dur_str) if dur_str != "None" else None

        context.user_data["current_sanction"] = {"action": action, "duration_hours": duration}
        context.user_data["original_update"] = update

        txt = "бана" if action == 'BAN' else ("мьюта на сутки" if duration == 24 else "мьюта на неделю")

        await self._safe_edit_message(
            query,
            fr"Введите количество предупреждений для *{txt}*\." "\n" r"Число `0` удалит правило\.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Отмена", callback_data=CallbackPrefix.BACK_TO_SANCTIONS_MENU)]]),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return AWAIT_SANCTION_VALUE

    async def sanction_set_value(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Устанавливает новое значение для правила санкции."""
        msg = update.message
        try:
            warns = int(msg.text.strip())
            if warns < 0:
                raise ValueError
        except (ValueError, TypeError):
            await msg.reply_text(r"❌ Введите целое неотрицательное число\.", parse_mode=ParseMode.MARKDOWN_V2)
            return AWAIT_SANCTION_VALUE

        sanction = context.user_data.pop("current_sanction", None)
        if not sanction:
            await msg.reply_text(r"❌ Внутренняя ошибка\.", parse_mode=ParseMode.MARKDOWN_V2)
            return await self.show_moderate_settings_menu(update, context)

        rules = await self.db.get_sanction_rules()
        rules = [
            r for r in rules
            if not (r["action"] == sanction["action"] and r.get("duration_hours") == sanction.get("duration_hours"))
        ]

        if warns > 0:
            rules.append({"warnings": warns, **sanction})

        await self.db.set_sanction_rules(rules)
        try:
            await context.bot.delete_message(msg.chat_id, msg.message_id)
        except Exception:
            pass

        original_update = context.user_data.pop('original_update', None)
        if original_update and original_update.callback_query:
            await self._safe_answer_query(original_update.callback_query, "✅ Правила обновлены.")
            text, reply_markup = await self._get_sanctions_menu_content()
            await self._safe_edit_message(original_update.callback_query, text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)

        return SANCTIONS_MENU

    async def show_users_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Отображает меню пользователей с предупреждениями."""
        query = update.callback_query
        await self._safe_answer_query(query)

        users = await self.db.get_all_users_with_warnings()
        lines, kb = ["👥 *Пользователи с предупреждениями*\n"], []

        if not users:
            lines.append(r"Чисто — нарушителей нет\.")
        else:
            for rec in users:
                uid, count = rec["user_id"], rec["count"]
                try:
                    tg_user = await context.bot.get_chat(uid)
                    uname = escape_markdown_v2(f"@{tg_user.username}" if tg_user.username else tg_user.full_name)
                    btn_uname = tg_user.username or tg_user.first_name
                except Exception:
                    uname = f"`{uid}`"
                    btn_uname = f"ID: {uid}"
                lines.append(fr"• {uname} — *{count}* пред\.")
                kb.append([InlineKeyboardButton(f"❌ Сбросить для {btn_uname}", callback_data=f"{CallbackPrefix.RESET_WARNS}{uid}")])

        kb.append([InlineKeyboardButton("⬅️ Назад", callback_data=CallbackPrefix.BACK_TO_MODERATION_SETTINGS)])

        await self._safe_edit_message(query, "\n".join(lines), reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN_V2)
        return USERS_MENU

    async def reset_user_warnings(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Сбрасывает предупреждения для конкретного пользователя."""
        query = update.callback_query
        uid = int(query.data.replace(CallbackPrefix.RESET_WARNS, ""))
        await self.db.reset_warnings(uid)
        await self._safe_answer_query(query, "✅ Предупреждения пользователя сброшены.")
        return await self.show_users_menu(update, context)
