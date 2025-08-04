# NVC_bot/bot/handlers/callbacks/items.py
# version: 1.7.0
# 2025-07-28T23:00:00Z
"""
Обработчики инлайн-кнопок для управления триггерами и исключениями модерации.

Version 1.7.0:
- REFACTOR: Изменена логика `_format_list_for_display` для решения проблемы
            с лимитом на количество "сущностей" (entities) в Telegram.
- FIX: Вместо оборачивания каждого слова в `<code>`, теперь вся строка
       слов для одной категории оборачивается в один тег `<code>`. Это
       радикально снижает количество сущностей и предотвращает сбой форматирования.
"""
from typing import Dict, List

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from telegram.error import BadRequest, TelegramError
import logging

from ...utils.formatters import escape_markdown_v2, escape_html
from ..states import (MANAGE_TRIGGERS, AWAIT_TRIGGERS_TO_ADD, AWAIT_TRIGGERS_TO_DELETE,
                      MANAGE_EXCEPTIONS, AWAIT_EXCEPTIONS_TO_ADD, AWAIT_EXCEPTIONS_TO_DELETE)
from .callback_patterns import CallbackPrefix

logger = logging.getLogger(__name__)

class ItemCallbackHandler:
    """Обработчики для управления списками триггеров и исключений."""

    def _format_list_for_display(self, items: Dict[str, List[str]]) -> str:
        """
        Безопасно форматирует список для отображения в HTML.
        """
        if not items:
            return "Список пуст."
        lines = []
        for category, words in items.items():
            escaped_category = escape_html(category.capitalize())
            lines.append(f"<i>{escaped_category}</i>:")
            
            all_words_string = ", ".join(words)
            escaped_words = escape_html(all_words_string)
            lines.append(f"<code>{escaped_words}</code>")
            
        return "\n\n".join(lines)

    async def _show_item_management_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, item_type: str) -> int:
        query = update.callback_query
        await self._safe_answer_query(query)
        
        items, return_state, callbacks = {}, 0, {}
        if item_type == "triggers":
            items = await self.db.get_all_triggers()
            return_state = MANAGE_TRIGGERS
            callbacks = {"title": "🎯 <b>Управление триггерами</b>", "back": CallbackPrefix.BACK_TO_MODERATION_SETTINGS, "add": CallbackPrefix.TRIGGERS_ADD, "del": CallbackPrefix.TRIGGERS_DELETE, "reset": CallbackPrefix.TRIGGERS_RESET}
        elif item_type == "exceptions":
            items = await self.db.get_all_exceptions()
            return_state = MANAGE_EXCEPTIONS
            callbacks = {"title": "🛡️ <b>Управление исключениями</b>", "back": CallbackPrefix.BACK_TO_MODERATION_SETTINGS, "add": CallbackPrefix.EXCEPTIONS_ADD, "del": CallbackPrefix.EXCEPTIONS_DELETE, "reset": CallbackPrefix.EXCEPTIONS_RESET}
        
        text = f"{callbacks['title']}\n\n{self._format_list_for_display(items)}\n\nДля отмены введите /cancel."
        kb = [
            [InlineKeyboardButton("➕ Добавить", callback_data=callbacks["add"]), InlineKeyboardButton("➖ Удалить", callback_data=callbacks["del"])],
            [InlineKeyboardButton("🔄 Сбросить", callback_data=callbacks["reset"]), InlineKeyboardButton("⬅️ Назад", callback_data=callbacks["back"])]
        ]
        await self._safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
        return return_state

    async def show_triggers_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        return await self._show_item_management_menu(update, context, "triggers")

    async def show_exceptions_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        return await self._show_item_management_menu(update, context, "exceptions")

    async def request_items_add(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await self._safe_answer_query(query)
        cb_data = query.data
        
        text, return_state = "", 0
        if cb_data == CallbackPrefix.TRIGGERS_ADD:
            text, return_state = "Отправьте триггеры для добавления\\.\nФормат: `Категория: слово1, слово2`\nИли просто `слово1, слово2` для категории 'general'\\.", AWAIT_TRIGGERS_TO_ADD
        elif cb_data == CallbackPrefix.EXCEPTIONS_ADD:
            text, return_state = "Отправьте фразы\\-исключения для добавления\\.\nФормат: `Категория: фраза 1, фраза 2`\nИли просто `фраза 1, фраза 2` для категории 'general'\\.", AWAIT_EXCEPTIONS_TO_ADD
        
        context.user_data['original_update'] = update
        await self._safe_edit_message(query, text, reply_markup=None, parse_mode=ParseMode.MARKDOWN_V2)
        return return_state

    async def request_items_delete(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await self._safe_answer_query(query)
        cb_data = query.data
        
        text, return_state = "", 0
        if cb_data == CallbackPrefix.TRIGGERS_DELETE:
            text, return_state = "Отправьте триггеры для удаления, перечислив их через запятую\\.", AWAIT_TRIGGERS_TO_DELETE
        elif cb_data == CallbackPrefix.EXCEPTIONS_DELETE:
            text, return_state = "Отправьте фразы\\-исключения для удаления, перечислив их через запятую\\.", AWAIT_EXCEPTIONS_TO_DELETE
            
        context.user_data['original_update'] = update
        await self._safe_edit_message(query, text, reply_markup=None, parse_mode=ParseMode.MARKDOWN_V2)
        return return_state

    async def _handle_add_logic(self, update: Update, context: ContextTypes.DEFAULT_TYPE, item_type: str) -> int:
        msg = update.message
        text = msg.text.strip()
        category = 'general'
        if ':' in text:
            category, text = (part.strip() for part in text.split(':', 1))
            
        items = [item.strip().lower() for item in text.split(',') if item.strip()]
        added_count = 0
        
        add_func = self.db.add_trigger if item_type == "triggers" else self.db.add_exception
        for item in items:
            if await add_func(item, category): added_count += 1
        
        try: await msg.delete()
        except (BadRequest, TelegramError) as e: logger.warning("Не удалось удалить сообщение пользователя: %s", e)

        original_update = context.user_data.pop('original_update', None)
        if original_update and original_update.callback_query:
            await self._safe_answer_query(original_update.callback_query, text=f"✅ Добавлено {added_count} из {len(items)} в '{category}'.")
            await self._show_item_management_menu(original_update, context, item_type)
            
        return MANAGE_TRIGGERS if item_type == "triggers" else MANAGE_EXCEPTIONS

    async def _handle_delete_logic(self, update: Update, context: ContextTypes.DEFAULT_TYPE, item_type: str) -> int:
        msg = update.message
        items_to_delete = [item.strip().lower() for item in msg.text.strip().split(',') if item.strip()]
        deleted_count = 0
        
        delete_func = self.db.delete_trigger if item_type == "triggers" else self.db.delete_exception
        for item in items_to_delete:
            if await delete_func(item): deleted_count += 1

        try: await msg.delete()
        except (BadRequest, TelegramError) as e: logger.warning("Не удалось удалить сообщение пользователя: %s", e)

        original_update = context.user_data.pop('original_update', None)
        if original_update and original_update.callback_query:
            await self._safe_answer_query(original_update.callback_query, text=f"✅ Удалено {deleted_count} из {len(items_to_delete)} элементов.")
            await self._show_item_management_menu(original_update, context, item_type)
            
        return MANAGE_TRIGGERS if item_type == "triggers" else MANAGE_EXCEPTIONS

    async def handle_triggers_add(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        return await self._handle_add_logic(update, context, "triggers")

    async def handle_triggers_delete(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        return await self._handle_delete_logic(update, context, "triggers")

    async def handle_exceptions_add(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        return await self._handle_add_logic(update, context, "exceptions")

    async def handle_exceptions_delete(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        return await self._handle_delete_logic(update, context, "exceptions")

    async def reset_items(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        item_type = "triggers" if query.data == CallbackPrefix.TRIGGERS_RESET else "exceptions"
        
        await self._safe_answer_query(query, text="Выполняется сброс...")
        if item_type == "triggers": await self.db.reset_triggers()
        else: await self.db.reset_exceptions()
        
        return await self._show_item_management_menu(update, context, item_type)
