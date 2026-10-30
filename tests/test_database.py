# NVC_bot/tests/test_database.py
# version: 2.0.0
# 2026-10-30T06:30:00Z
"""
Модульные тесты для класса Database.
Использует in-memory базу данных для изоляции тестов.
"""
import pytest

from bot.database import Database
from bot.config import settings

pytestmark = pytest.mark.asyncio


class TestWelcomeSettings:
    async def test_welcome_enabled_by_default(self, db_session: Database):
        assert await db_session.is_welcome_enabled() is True

    async def test_toggle_welcome(self, db_session: Database):
        assert await db_session.is_welcome_enabled() is True
        new_state_off = await db_session.toggle_welcome()
        assert new_state_off is False
        assert await db_session.is_welcome_enabled() is False

        new_state_on = await db_session.toggle_welcome()
        assert new_state_on is True
        assert await db_session.is_welcome_enabled() is True

    async def test_get_default_welcome_model(self, db_session: Database):
        model = await db_session.get_welcome_model()
        assert model == settings.DEFAULT_WELCOME_MODEL

    async def test_set_and_get_welcome_model(self, db_session: Database):
        new_model = "gemini-2.5-pro"
        await db_session.set_welcome_model(new_model)
        saved_model = await db_session.get_welcome_model()
        assert saved_model == new_model

    async def test_get_default_welcome_prompt(self, db_session: Database):
        prompt = await db_session.get_welcome_prompt()
        assert prompt == settings.DEFAULT_WELCOME_PROMPT

    async def test_set_and_get_welcome_prompt(self, db_session: Database):
        new_prompt = "Привет, {user_mention}! Добро пожаловать."
        await db_session.set_welcome_prompt(new_prompt)
        saved_prompt = await db_session.get_welcome_prompt()
        assert saved_prompt == new_prompt

    async def test_reset_welcome_prompt(self, db_session: Database):
        custom_prompt = "Это временный промпт."
        await db_session.set_welcome_prompt(custom_prompt)
        assert await db_session.get_welcome_prompt() == custom_prompt
        await db_session.reset_welcome_prompt()
        reset_prompt = await db_session.get_welcome_prompt()
        assert reset_prompt == settings.DEFAULT_WELCOME_PROMPT

    async def test_facilitator_model_persistence(self, db_session: Database):
        assert await db_session.get_facilitator_model() == settings.GEMINI_PRO_MODEL
        await db_session.set_facilitator_model("gemini-2.5-flash")
        assert await db_session.get_facilitator_model() == "gemini-2.5-flash"

    async def test_chat_history_includes_user_name(self, db_session: Database):
        await db_session.add_message(1001, "Алексей", "Привет всем!", is_bot=False)
        await db_session.add_message(1001, "bot", "Здравствуйте!", is_bot=True)
        history = await db_session.get_chat_history(1001, 10)
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[0]["parts"][0]["text"] == "Алексей: Привет всем!"
        assert history[1]["role"] == "model"
        assert history[1]["parts"][0]["text"] == "Здравствуйте!"
