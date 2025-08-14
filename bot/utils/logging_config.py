# NVC_bot/bot/utils/logging_config.py
# version: 3.4.0
# 2025-08-07T07:00:00Z
"""
Модуль для централизованной настройки логирования во всем приложении.

Version 3.4.0:
- FEATURE: Внедрен `RotatingFileHandler` для автоматической ротации лог-файлов
           по достижении размера в 2 МБ.
- REFACTOR: Удалена устаревшая функция `_cleanup_old_logs`, так как ее
            функциональность теперь покрывается `RotatingFileHandler`.

Version 3.3.0:
- REFACTOR: Установлен уровень логирования WARNING для `httpx` и `telegram`.
- REFACTOR: Форматтер для `ai_requests.log` упрощен.
"""
import logging
import sys
from logging.handlers import RotatingFileHandler
from datetime import datetime
from pathlib import Path

from ..config import DATA_DIR

class TraceIdFilter(logging.Filter):
    """
    Фильтр, который добавляет `trace_id` в каждую запись лога.
    """
    def filter(self, record):
        if not hasattr(record, 'trace_id'):
            record.trace_id = 'system'
        return True

def setup_logging():
    """
    Настраивает базовую конфигурацию логирования для проекта.
    """
    log_dir = DATA_DIR
    log_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    trace_filter = TraceIdFilter()

    # --- Настройка технического логгера (основного) ---
    tech_log_path = log_dir / f"technical_{timestamp}.log"
    tech_formatter = logging.Formatter("%(asctime)s - [%(trace_id)s] - %(name)s - %(levelname)s - %(message)s")
    
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(tech_formatter)
    stream_handler.addFilter(trace_filter)
    
    # FEATURE: Используем ротацию логов по размеру. 2 МБ на файл, храним 5 старых.
    tech_file_handler = RotatingFileHandler(
        tech_log_path, maxBytes=2*1024*1024, backupCount=5, encoding='utf-8'
    )
    tech_file_handler.setFormatter(tech_formatter)
    tech_file_handler.addFilter(trace_filter)
    
    logging.basicConfig(level=logging.INFO, handlers=[stream_handler, tech_file_handler], force=True)

    # --- Устранение шума от сторонних библиотек ---
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)

    # --- Настройка логгера для запросов к ИИ ---
    ai_log_path = log_dir / f"ai_requests_{timestamp}.log"
    ai_formatter = logging.Formatter(
        "%(asctime)s - [%(trace_id)s]\n%(message)s\n"
    )
    
    ai_logger = logging.getLogger('ai_requests')
    ai_logger.setLevel(logging.INFO)
    
    # FEATURE: Используем ротацию логов по размеру. 2 МБ на файл, храним 5 старых.
    ai_file_handler = RotatingFileHandler(
        ai_log_path, maxBytes=2*1024*1024, backupCount=5, encoding='utf-8'
    )
    ai_file_handler.setFormatter(ai_formatter)
    
    ai_logger.addHandler(ai_file_handler)
    ai_logger.propagate = False

    logger = logging.getLogger(__name__)
    logger.info("Конфигурация логирования настроена. Технический лог: %s, Лог запросов ИИ: %s", tech_log_path, ai_log_path, extra={'trace_id': 'init'})
