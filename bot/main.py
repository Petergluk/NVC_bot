# NVC_bot/bot/main.py
# version: 3.0.0
# 2025-07-28T11:00:00Z
"""
Основной файл для инициализации и запуска Telegram-бота.

Version 3.0.0:
- ARCH: Архитектура обработчиков восстановлена до исходной, стабильной версии.
- ADD: Возвращен единый глобальный `MessageHandler` для `user_handlers.handle_message`.
- REMOVE: Удалены группы и сложные приоритеты обработчиков.
"""
import asyncio
import html
import json
import logging
import traceback
import uuid
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (Application, CommandHandler, ContextTypes,
                          MessageHandler, filters)
from telegram.request import HTTPXRequest

from .config import settings, ADMIN_IDS
from .database import Database
from .handlers.admin import AdminHandlers
from .handlers.callbacks import CallbackHandlers
from .handlers.conversations import setup_conversations
from .handlers.user import UserHandlers
from .services.gemini import GeminiService
from .services.moderation import ModerationService
from .utils.logging_config import setup_logging

logger = logging.getLogger(__name__)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    trace_id = context.user_data.get('trace_id', str(uuid.uuid4()))
    logger.error("Exception while handling an update:", exc_info=context.error, extra={'trace_id': trace_id})

    if not ADMIN_IDS: return

    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)

    update_summary = "N/A"
    if isinstance(update, Update):
        parts = []
        if update.effective_chat: parts.append(f"Chat: {update.effective_chat.title or 'Private'} ({update.effective_chat.id})")
        if update.effective_user: parts.append(f"User: {update.effective_user.full_name} ({update.effective_user.id})")
        if update.callback_query: parts.append(f"Callback: {update.callback_query.data}")
        elif update.effective_message: parts.append(f"Message: {update.effective_message.text[:70] if update.effective_message.text else '<No Text>'}")
        update_summary = " | ".join(parts)

    info_message = (
        f"<b>❗️ Исключение при обработке апдейта</b>\n\n"
        f"<b>Trace ID:</b> <code>{html.escape(trace_id)}</code>\n"
        f"<b>Сводка:</b>\n<pre>{html.escape(update_summary)}</pre>\n\n"
        f"<b>User Data:</b>\n<pre>{html.escape(str(context.user_data))}</pre>"
    )
    
    try:
        await context.bot.send_message(chat_id=ADMIN_IDS[0], text=info_message, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error("Не удалось отправить первую часть сообщения об ошибке: %s", e, extra={'trace_id': trace_id})

    traceback_header = "\n\n<pre>------- TRACEBACK -------\n"
    chunk_size = 4096 - len(traceback_header) - len("</pre>")
    
    for i in range(0, len(tb_string), chunk_size):
        chunk = tb_string[i:i+chunk_size]
        message_chunk = f"{traceback_header if i == 0 else '<pre>'}{html.escape(chunk)}</pre>"
        try:
            await context.bot.send_message(chat_id=ADMIN_IDS[0], text=message_chunk, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error("Не удалось отправить чанк traceback: %s", e, extra={'trace_id': trace_id})

async def main() -> None:
    """
    Главная асинхронная функция, которая настраивает и запускает бота.
    """
    setup_logging()
    
    db = Database()
    await db.initialize()
    await db.populate_defaults()

    gemini_service = GeminiService(
        model_names={"pro": settings.GEMINI_PRO_MODEL, "flash": settings.GEMINI_FLASH_MODEL, "lite": settings.GEMINI_LITE_MODEL},
        db=db
    )
    moderation_service = ModerationService(db, gemini_service)

    request = HTTPXRequest(connect_timeout=10.0, read_timeout=30.0, write_timeout=30.0)
    app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).job_queue(None).request(request).build()
    app.add_error_handler(error_handler)

    user_handlers = UserHandlers(db, gemini_service, moderation_service)
    admin_handlers = AdminHandlers(db, gemini_service)
    callback_handlers = CallbackHandlers(db, gemini_service)
    
    admin_handlers.set_callback_handlers(callback_handlers)

    # ConversationHandler для меню настроек. Имеет приоритет 0 по умолчанию.
    conv_handler = setup_conversations(admin_handlers, callback_handlers)
    app.add_handler(conv_handler)
    
    # Обработчики команд
    app.add_handler(CommandHandler("start", user_handlers.start_command))
    app.add_handler(CommandHandler("help", user_handlers.help_command))
    app.add_handler(CommandHandler("stats", admin_handlers.show_stats_command))
    app.add_handler(CommandHandler("warnings", admin_handlers.manage_warnings))
    
    # Обработчик входа новых участников
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, user_handlers.greet_new_members))

    # Глобальный обработчик всех текстовых сообщений.
    # ConversationHandler имеет более высокий приоритет и перехватит сообщение первым, если диалог активен.
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, user_handlers.handle_message))

    try:
        await app.initialize()
        await app.updater.start_polling()
        await app.start()
        logger.info("Бот запущен и готов к работе. Нажмите Ctrl+C для остановки.", extra={'trace_id': 'init'})
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Получен сигнал остановки.", extra={'trace_id': 'shutdown'})
    finally:
        logger.info("Начинаю процедуру выключения...", extra={'trace_id': 'shutdown'})
        if app.updater and app.updater.is_running:
            await app.updater.stop()
        if app.running:
            await app.stop()
        await app.shutdown()
        logger.info("Бот успешно остановлен.", extra={'trace_id': 'shutdown'})
