# NVC_bot/tests/conftest.py
# version: 1.0
# 2025-07-26T03:20:00Z
"""
Конфигурационный файл для pytest.
Содержит общие фикстуры, доступные для всех тестов в проекте.
"""
import asyncio
import pytest
import pytest_asyncio

# Добавляем корень проекта в sys.path, чтобы импорты работали корректно
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from bot.database import Database

@pytest.fixture(scope="session")
def event_loop():
    """
    Создает экземпляр цикла событий для всей тестовой сессии.
    Это необходимо для асинхронных тестов.
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest_asyncio.fixture(scope="function")
async def db_session() -> Database:
    """
    Асинхронная фикстура, которая создает и предоставляет чистую
    in-memory базу данных для каждого тестового запуска (function scope).
    
    Returns:
        Database: Инициализированный экземпляр Database.
    """
    # Используем in-memory базу данных для полной изоляции тестов
    db = Database()
    db.db_path = ":memory:" # Специальное имя для SQLite in-memory
    
    await db.initialize()
    await db.populate_defaults() # Заполняем значениями по умолчанию
    
    yield db # Предоставляем объект базы данных тесту
    
    # После выполнения теста закрываем соединение
    if db.conn:
        await db.conn.close()
