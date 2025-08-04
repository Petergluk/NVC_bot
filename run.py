# NVC_bot/run.py
# version: 1.3.0
# 2025-07-28T10:00:00Z
"""
Точка входа для запуска бота.
Этот файл находится в корне проекта и импортирует основную логику из пакета 'bot'.

Version 1.3.0:
- FIX: Возвращен вызов `asyncio.run()`, который теперь запускает
       корректно спроектированную асинхронную функцию `main()`.
"""
import asyncio
import sys
from pathlib import Path

# Добавляем корень проекта в sys.path для корректных импортов
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from bot.main import main

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        # Логика завершения уже находится в main(),
        # здесь просто перехватываем исключение, чтобы избежать
        # лишнего вывода в консоль.
        pass
