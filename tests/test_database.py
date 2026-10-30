# NVC_bot/tests/test_database.py
# version: 3.0.0
# 2026-10-30T16:30:00Z

'''
Модульные тесты для класса Database (включая функции v3.0: мягкую пре-модерацию,
апелляции, автоамнистию и выбор моделей во главе с gemini-3.8-flash).
'''

import pytest
from bot.database import Database
from bot.config import settings, AVAILABLE_MODELS_CATALOG, Settings

pytestmark = pytest.mark.asyncio


class TestWelcomeAndModels:
    async def test_default_models_are_gemini_3_8_flash(self, db_session: Database):
        assert settings.DEFAULT_WELCOME_MODEL == "gemini-3.8-flash"
        assert settings.DEFAULT_MODERATION_MODEL == "gemini-3.8-flash"
        assert Settings.model_fields["GEMINI_FLASH_MODEL"].default == "gemini-3.8-flash"
        assert "gemini-3.8-flash" in AVAILABLE_MODELS_CATALOG
        assert "gemma-4" in AVAILABLE_MODELS_CATALOG
        assert AVAILABLE_MODELS_CATALOG["gemini-3.8-flash"]["tier"] == "free"
        assert AVAILABLE_MODELS_CATALOG["gemini-4-argon"]["tier"] == "paid"

    async def test_welcome_enabled_by_default(self, db_session: Database):
        assert await db_session.is_welcome_enabled() is True

    async def test_toggle_welcome(self, db_session: Database):
        assert await db_session.is_welcome_enabled() is True
        new_state_off = await db_session.toggle_welcome()
        assert new_state_off is False
        assert await db_session.is_welcome_enabled() is False


class TestSoftModerationAndAppeals:
    async def test_soft_moderation_toggle(self, db_session: Database):
        assert await db_session.is_soft_moderation_enabled() is True
        state = await db_session.toggle_soft_moderation()
        assert state is False
        assert await db_session.is_soft_moderation_enabled() is False

    async def test_create_and_update_appeal(self, db_session: Database):
        appeal_id = await db_session.create_appeal(
            chat_id=-10012345,
            user_id=777,
            user_name="@tester",
            original_text="Ты никогда меня не слушаешь!",
            suggested_nvc="Когда мои слова перебивают, я чувствую досаду, мне важно быть услышанным.",
            rule_violated="Ты-сообщение"
        )
        assert appeal_id > 0
        appeal = await db_session.get_appeal(appeal_id)
        assert appeal is not None
        assert appeal["status"] == "pending"
        assert appeal["user_id"] == 777

        updated = await db_session.update_appeal_status(appeal_id, "approved")
        assert updated is True
        appeal_after = await db_session.get_appeal(appeal_id)
        assert appeal_after["status"] == "approved"


class TestAutoAmnesty:
    async def test_auto_amnesty_settings_and_execution(self, db_session: Database):
        assert await db_session.is_auto_amnesty_enabled() is True
        assert await db_session.get_auto_amnesty_days() == 7

        await db_session.set_auto_amnesty_days(14)
        assert await db_session.get_auto_amnesty_days() == 14

        # Выдаем 2 предупреждения и искусственно сдвигаем дату на 15 дней назад
        await db_session.set_warnings(555, 2)
        await db_session.conn.execute(
            "UPDATE user_warnings SET last_warning_at = datetime('now', '-15 days') WHERE user_id = 555"
        )
        await db_session.conn.commit()

        pardoned = await db_session.apply_auto_amnesty(days=14)
        assert len(pardoned) == 1
        assert pardoned[0]["user_id"] == 555
        assert pardoned[0]["new_count"] == 1
        assert await db_session.get_warnings(555) == 1