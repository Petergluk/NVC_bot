# NVC_bot/tests/test_database.py
# version: 1.1.0
# 2025-07-27T14:12:32Z
"""
Модульные тесты для класса Database.
Использует in-memory базу данных для изоляции тестов.

Version 1.1.0:
- FIX: Переименован тестовый класс TestGreetingSettings в TestWelcomeSettings для консистентности.
"""
import pytest

from bot.database import Database
from bot.config import settings

# Помечаем все тесты в этом файле как асинхронные
pytestmark = pytest.mark.asyncio

class TestWelcomeSettings:
    """
    Тестирует блок методов, отвечающих за настройки приветствий.
    """

    async def test_welcome_enabled_by_default(self, db_session: Database):
        """Проверяет, что приветствия включены по умолчанию."""
        assert await db_session.is_welcome_enabled() is True

    async def test_toggle_welcome(self, db_session: Database):
        """Проверяет переключение состояния приветствий."""
        # Начальное состояние - True
        assert await db_session.is_welcome_enabled() is True
        
        # Первое переключение -> False
        new_state_off = await db_session.toggle_welcome()
        assert new_state_off is False
        assert await db_session.is_welcome_enabled() is False

        # Второе переключение -> True
        new_state_on = await db_session.toggle_welcome()
        assert new_state_on is True
        assert await db_session.is_welcome_enabled() is True

    async def test_get_default_welcome_model(self, db_session: Database):
        """Проверяет, что по умолчанию возвращается правильная модель для приветствий."""
        model = await db_session.get_welcome_model()
        assert model == settings.DEFAULT_WELCOME_MODEL

    async def test_set_and_get_welcome_model(self, db_session: Database):
        """Проверяет установку и получение кастомной модели для приветствий."""
        new_model = "gemini-2.5-pro"
        await db_session.set_welcome_model(new_model)
        
        saved_model = await db_session.get_welcome_model()
        assert saved_model == new_model

    async def test_get_default_welcome_prompt(self, db_session: Database):
        """Проверяет, что по умолчанию возвращается правильный промпт приветствия."""
        prompt = await db_session.get_welcome_prompt()
        assert prompt == settings.DEFAULT_WELCOME_PROMPT

    async def test_set_and_get_welcome_prompt(self, db_session: Database):
        """Проверяет установку и получение кастомного промпта приветствия."""
        new_prompt = "Привет, {user_mention}! Добро пожаловать."
        await db_session.set_welcome_prompt(new_prompt)
        
        saved_prompt = await db_session.get_welcome_prompt()
        assert saved_prompt == new_prompt

    async def test_reset_welcome_prompt(self, db_session: Database):
        """Проверяет сброс промпта приветствия к значению по умолчанию."""
        # Сначала устанавливаем кастомный промпт
        custom_prompt = "Это временный промпт."
        await db_session.set_welcome_prompt(custom_prompt)
        assert await db_session.get_welcome_prompt() == custom_prompt
        
        # Теперь сбрасываем
        await db_session.reset_welcome_prompt()
        
        # Проверяем, что он вернулся к значению по умолчанию
        reset_prompt = await db_session.get_welcome_prompt()
        assert reset_prompt == settings.DEFAULT_WELCOME_PROMPT
