# NVC_bot/bot/handlers/callbacks/moderation.py
# version: 2.0.0
# 2025-08-12T15:45:00Z
"""
Обработчики инлайн-кнопок для меню настроек Модерации.

Version 2.0.0:
- FEATURE: В главное меню модерации добавлена кнопка "Шаблон Сообщения"
           для управления текстом, который бот отправляет при нарушении.
- FEATURE: В меню установки санкций теперь отображается текущее значение
           количества варнов для данного правила.
- FIX: Некорректный текст на кнопке "Промпт Фасилитатора" заменен на
       "Шаблон Сообщения", что соответствует ее реальной функции.

Version 1.4.0:
- FIX: Устранено некорректное экранирование имен моделей в кнопках.
- FEATURE: Внедрены человекочитаемые имена моделей в UI из `MODEL_NAME_MAP`.
"""
from typing import Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler

from ...config import MODEL_NAME_MAP
from ...utils.formatters import escape_markdown_v2
from ..states import (MODERATION_SETTINGS, MODERATION_MODEL_MENU,
                      SANCTIONS_MENU, AWAIT_SANCTION_VALUE, USERS_MENU)
from .callback_patterns import CallbackPrefix

class ModerationCallbackHandler:
    """Обработчики для основной ветки /moderate."""

    async def show_moderate_settings_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Отображает главное меню настроек модерации."""
        query = update.callback_query
        message = update.effective_message
        if query:
            await self._safe_answer_query(query)

        mod_enabled = await self.db.is_moderation_enabled()
        mod_status = "✅ Включена" if mod_enabled else "❌ Выключена"
        
        mod_model_id = await self.db.get_moderation_model()
        mod_model_display_name = MODEL_NAME_MAP.get(mod_model_id, mod_model_id)

        kb = [
            [InlineKeyboardButton(mod_status, callback_data=CallbackPrefix.MODERATE_TOGGLE)],
            # FIX: Кнопка "Промпт Фасилитатора" заменена на актуальную "Шаблон Сообщения"
            [InlineKeyboardButton("🔍 Промпт Судьи", callback_data=CallbackPrefix.MODERATE_PROMPT), InlineKeyboardButton("📝 Шаблон Сообщения", callback_data=CallbackPrefix.MODERATE_TEMPLATE)],
            [InlineKeyboardButton(f"⚖️ Модель: {mod_model_display_name}", callback_data=CallbackPrefix.MODERATE_MODEL), InlineKeyboardButton("🔨 Санкции", callback_data=CallbackPrefix.MODERATE_SANCTIONS)],
            [InlineKeyboardButton("🎯 Триггеры", callback_data=CallbackPrefix.MANAGE_TRIGGERS), InlineKeyboardButton("🛡️ Исключения", callback_data=CallbackPrefix.MANAGE_EXCEPTIONS)],
            [InlineKeyboardButton("👥 Пользователи", callback_data=CallbackPrefix.MODERATE_USERS)],
            [InlineKeyboardButton("❌ Закрыть", callback_data=CallbackPrefix.CLOSE_MENU)]
        ]
        text = "🛂 *Настройки модерации*\n\nУправление автоматическим ИИ\\-модератором чата\\."
        reply_markup = InlineKeyboardMarkup(kb)

        if query:
            await self._safe_edit_message(query, text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
        else:
            await message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
            
        return MODERATION_SETTINGS

    async def toggle_moderation(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Переключает статус модерации (вкл/выкл)."""
        query = update.callback_query
        await self._safe_answer_query(query)
        
        new_state = await self.db.toggle_moderation()
        await query.answer(f"Модерация {'включена' if new_state else 'выключена'}")
        
        return await self.show_moderate_settings_menu(update, context)

    async def show_moderation_model_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Показывает меню выбора модели для модерации."""
        query = update.callback_query
        await self._safe_answer_query(query)
        
        current_model_id = await self.db.get_moderation_model()
        current_model_display_name = MODEL_NAME_MAP.get(current_model_id, current_model_id)
        
        text = f"⚖️ *Выбор ИИ\\-Судьи*\n\nТекущий судья: *{escape_markdown_v2(current_model_display_name)}*"
        
        kb = []
        for model_id in self.gemini.get_available_models():
            display_name = MODEL_NAME_MAP.get(model_id, model_id)
            button_text = ("✅ " if model_id == current_model_id else "") + display_name
            callback_data = f"{CallbackPrefix.MODERATE_SET_MODEL}{model_id}"
            kb.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

        kb.append([InlineKeyboardButton("⬅️ Назад", callback_data=CallbackPrefix.BACK_TO_MODERATION_SETTINGS)])
        
        await self._safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN_V2)
        return MODERATION_MODEL_MENU

    async def set_moderation_model(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Устанавливает новую модель для модерации."""
        query = update.callback_query
        
        model_id = query.data.replace(CallbackPrefix.MODERATE_SET_MODEL, "")
        await self.db.set_moderation_model(model_id)
        
        display_name = MODEL_NAME_MAP.get(model_id, model_id)
        await query.answer(f"ИИ-Судья переключён на {display_name}")
        
        return await self.show_moderation_model_menu(update, context)

    async def _get_sanctions_menu_content(self) -> Tuple[str, InlineKeyboardMarkup]:
        """Формирует текст и клавиатуру для меню санкций."""
        rules = await self.db.get_sanction_rules()
        rules_map = {(r['action'], r.get('duration_hours')): r['warnings'] for r in rules}
        
        mute_24 = rules_map.get(('MUTE', 24))
        mute_168 = rules_map.get(('MUTE', 168))
        ban = rules_map.get(('BAN', None))
        
        rules_lines = [
            f"• Мьют на сутки \\- *{mute_24 or 'отключен'}* пред\\.",
            f"• Мьют на неделю \\- *{mute_168 or 'отключен'}* пред\\.",
            f"• Бан \\- *{ban or 'отключен'}* пред\\."
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
        
        # FEATURE: Получаем текущее значение для отображения в подсказке
        rules = await self.db.get_sanction_rules()
        current_value_str = "не установлено"
        for rule in rules:
            if rule.get("action") == action and rule.get("duration_hours") == duration:
                current_value_str = str(rule.get("warnings", "ошибка"))
                break

        rule_name_map = { ('MUTE', 24): "мьюта на сутки", ('MUTE', 168): "мьюта на неделю", ('BAN', None): "бана", }
        rule_name = rule_name_map.get((action, duration), "неизвестного правила")

        message_text = (
            f"Введите количество предупреждений для *{rule_name}*\\.\n\n"
            f"*Текущее значение: `{current_value_str}`*\\.\n"
            f"Отправьте целое число\\. `0` — чтобы отключить правило\\."
        )

        await self._safe_edit_message(
            query,
            message_text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Отмена", callback_data=CallbackPrefix.BACK_TO_SANCTIONS_MENU)]]),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return AWAIT_SANCTION_VALUE

    async def sanction_set_value(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Устанавливает новое значение для правила санкции."""
        msg = update.message
        original_update = context.user_data.get('original_update')
        
        try:
            warns = int(msg.text.strip())
            if warns < 0: raise ValueError
        except (ValueError, TypeError):
            await msg.delete()
            if original_update and original_update.callback_query:
                await self._safe_edit_message(original_update.callback_query, "❌ Введите целое неотрицательное число\\.", parse_mode=ParseMode.MARKDOWN_V2)
            return AWAIT_SANCTION_VALUE

        sanction = context.user_data.pop("current_sanction", None)
        if not sanction:
            await msg.delete()
            if original_update and original_update.callback_query:
                await self._safe_edit_message(original_update.callback_query, "❌ Внутренняя ошибка, попробуйте снова\\.", parse_mode=ParseMode.MARKDOWN_V2)
            return SANCTIONS_MENU

        rules = await self.db.get_sanction_rules()
        rules = [r for r in rules if not (r["action"] == sanction["action"] and r.get("duration_hours") == sanction.get("duration_hours"))]
        
        if warns > 0:
            rules.append({"warnings": warns, **sanction})
            
        await self.db.set_sanction_rules(rules)
        await context.bot.delete_message(msg.chat_id, msg.message_id)
        
        context.user_data.pop('original_update', None)
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
            lines.append("Чисто — нарушителей нет\\.")
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
                lines.append(f"• {uname} — *{count}* пред\\.")
                kb.append([InlineKeyboardButton(f"❌ Сбросить для {btn_uname}", callback_data=f"{CallbackPrefix.RESET_WARNS}{uid}")])
                
        kb.append([InlineKeyboardButton("⬅️ Назад", callback_data=CallbackPrefix.BACK_TO_MODERATION_SETTINGS)])
        
        await self._safe_edit_message(query, "\n".join(lines), reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN_V2)
        return USERS_MENU

    async def reset_user_warnings(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Сбрасывает предупреждения для конкретного пользователя."""
        query = update.callback_query
        
        uid = int(query.data.replace(CallbackPrefix.RESET_WARNS, ""))
        await self.db.reset_warnings(uid)
        await query.answer("Предупреждения пользователя сброшены.")
        
        return await self.show_users_menu(update, context)
