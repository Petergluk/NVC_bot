# NVC_bot/bot/utils/logging_config.py
# version: 3.3.0
# 2025-07-29T18:37:13Z
"""
Модуль для централизованной настройки логирования во всем приложении.

Version 3.3.0:
- REFACTOR: Установлен уровень логирования WARNING для библиотек `httpx` и `telegram`,
            чтобы убрать избыточный "шум" из технического лога.
- REFACTOR: Форматтер для `ai_requests.log` значительно упрощен.
            Теперь он ожидает полностью сформированное сообщение, что повышает
            надежность и предотвращает ошибки форматирования.
"""
import logging
import sys
import os
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

def _cleanup_old_logs(log_dir: Path, pattern: str, max_files: int):
    """Удаляет старые лог-файлы, соответствующие шаблону."""
    try:
        log_files = sorted(log_dir.glob(pattern), key=os.path.getmtime, reverse=True)
        if len(log_files) >= max_files:
            for old_log in log_files[max_files-1:]:
                os.remove(old_log)
    except Exception as e:
        print(f"Warning: Could not remove old log file. Error: {e}")

def setup_logging():
    """
    Настраивает базовую конфигурацию логирования для проекта.
    """
    log_dir = DATA_DIR
    log_dir.mkdir(exist_ok=True)
    
    _cleanup_old_logs(log_dir, "technical_*.log", 10)
    _cleanup_old_logs(log_dir, "ai_requests_*.log", 10)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    trace_filter = TraceIdFilter()

    # --- Настройка технического логгера (основного) ---
    tech_log_path = log_dir / f"technical_{timestamp}.log"
    tech_formatter = logging.Formatter("%(asctime)s - [%(trace_id)s] - %(name)s - %(levelname)s - %(message)s")
    
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(tech_formatter)
    stream_handler.addFilter(trace_filter)
    
    tech_file_handler = logging.FileHandler(tech_log_path, encoding='utf-8')
    tech_file_handler.setFormatter(tech_formatter)
    tech_file_handler.addFilter(trace_filter)
    
    # Устанавливаем базовую конфигурацию для нашего приложения на уровне INFO
    logging.basicConfig(level=logging.INFO, handlers=[stream_handler, tech_file_handler], force=True)

    # --- Устранение шума от сторонних библиотек ---
    # WHY: Устанавливаем более высокий уровень логирования для "болтливых" библиотек,
    #      чтобы в технический лог попадали только важные события (предупреждения и ошибки) от них.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)


    # --- Настройка логгера для запросов к ИИ ---
    ai_log_path = log_dir / f"ai_requests_{timestamp}.log"
    # Форматтер максимально прост, т.к. основное форматирование происходит в сервисе.
    ai_formatter = logging.Formatter(
        "%(asctime)s - [%(trace_id)s]\n%(message)s\n"
    )
    
    ai_logger = logging.getLogger('ai_requests')
    ai_logger.setLevel(logging.INFO)
    
    ai_file_handler = logging.FileHandler(ai_log_path, encoding='utf-8')
    ai_file_handler.setFormatter(ai_formatter)
    
    ai_logger.addHandler(ai_file_handler)
    ai_logger.propagate = False

    logger = logging.getLogger(__name__)
    logger.info("Конфигурация логирования настроена. Технический лог: %s, Лог запросов ИИ: %s", tech_log_path, ai_log_path, extra={'trace_id': 'init'})
