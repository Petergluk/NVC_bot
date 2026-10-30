# NVC_bot/tests/test_utils.py
# version: 2.0.0
# 2026-10-30T06:30:00Z
"""
Модульные тесты для вспомогательных функций из пакета utils.
"""
from bot.utils.formatters import format_stats_text, safe_format_template
from bot.utils.validators import (
    validate_prompt,
    validate_moderation_prompt,
    validate_moderation_template,
    validate_welcome_prompt,
)


def test_format_stats_text():
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


def test_safe_format_template_supports_single_and_double_braces_and_json():
    template = (
        "Привет, {user_mention}! Правила: {{group_rules}}. "
        "Пример JSON в промпте: {'verdict': 'ДА'} и {неизвестная_скобка}"
    )
    rendered = safe_format_template(
        template,
        user_mention="@alice",
        group_rules="Без оскорблений"
    )
    assert "@alice" in rendered
    assert "Без оскорблений" in rendered
    assert "{'verdict': 'ДА'}" in rendered
    assert "{неизвестная_скобка}" in rendered


def test_validators_accept_single_and_double_braces():
    assert validate_moderation_prompt("Проверь: {text}") is None
    assert validate_moderation_prompt("Проверь: {{text}}") is None
    assert validate_moderation_prompt("Без переменной") is not None

    assert validate_welcome_prompt("Привет, {user_mention}") is None
    assert validate_welcome_prompt("Привет, {{user_mention}}") is None

    valid_tpl = "{user_mention} {violator_message} {warnings_count} {rules_list} {{chat_history}}"
    assert validate_moderation_template(valid_tpl) is None
