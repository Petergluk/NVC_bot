# NVC_bot/tests/test_utils.py
# version: 1.0
# 2025-07-26T03:20:00Z
"""
Модульные тесты для вспомогательных функций из пакета utils.
"""
import pytest

from bot.utils.formatters import format_stats_text
from bot.utils.validators import validate_prompt, validate_moderation_template

def test_format_stats_text():
    """
    Проверяет корректность форматирования строки статистики.
    """
    stats_data = {
        "active_chats": 5,
        "total_messages": 120,
        "ai_responses": 30,
        "moderation_actions": 10,
        "users_with_warnings": 3,
    }
    
    expected_string = (
        "📊 *Статистика бота*\n\n"
        "👥 Активных чатов: `5`\n"
        "💬 Всего сообщений: `120`\n"
        "🤖 Ответов AI: `30`\n"
        "⚖️ Срабатываний модерации: `10`\n"
        "⚠️ Пользователей с варнами: `3`"
    )
    
    assert format_stats_text(stats_data) == expected_string

def test_format_stats_text_empty():
    """
    Проверяет форматирование статистики с пустыми данными.
    """
    stats_data = {}
    
    expected_string = (
        "📊 *Статистика бота*\n\n"
        "👥 Активных чатов: `0`\n"
        "💬 Всего сообщений: `0`\n"
        "🤖 Ответов AI: `0`\n"
        "⚖️ Срабатываний модерации: `0`\n"
        "⚠️ Пользователей с варнами: `0`"
    )
    
    assert format_stats_text(stats_data) == expected_string
