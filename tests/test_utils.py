# NVC_bot/tests/test_utils.py
# version: 3.0.0
# 2026-10-30T16:30:00Z

"""
Модульные тесты для вспомогательных функций, шаблонизатора и команд /nvc, /NNO, /ННО.
"""

from bot.utils.formatters import format_stats_text, safe_format_template
from bot.utils.validators import (
    validate_prompt,
    validate_moderation_prompt,
    validate_moderation_template,
    validate_welcome_prompt,
    NVC_COMMAND_PATTERN,
    parse_nvc_command,
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


def test_safe_format_template_supports_single_and_double_braces_and_json():
    template = 'Привет, {user_mention}! Правила: {{group_rules}}. JSON: {"verdict": "ДА"}'
    result = safe_format_template(
        template,
        user_mention="@petergluk",
        group_rules="Общаемся по ННО"
    )
    assert result == 'Привет, @petergluk! Правила: Общаемся по ННО. JSON: {"verdict": "ДА"}'


def test_nvc_command_pattern_supports_latin_and_cyrillic_and_rejects_rephrase():
    for cmd in ["/nvc", "/NVC", "/nno", "/NNO", "/нно", "/ННО", "/ННО@WeiDeHanBot"]:
        is_cmd, payload = parse_nvc_command(f"{cmd} Ты опять меня не слышишь!")
        assert is_cmd is True, f"Команда {cmd} должна распознаваться"
        assert payload == "Ты опять меня не слышишь!"

    for cmd_reply in ["/nvc", "/NNO", "/ННО", "/нно"]:
        is_cmd, payload = parse_nvc_command(cmd_reply)
        assert is_cmd is True
        assert payload is None

    # Убеждаемся, что /rephrase НЕ срабатывает
    is_rephrase, _ = parse_nvc_command("/rephrase текст")
    assert is_rephrase is False


def test_validators_accept_single_and_double_braces():
    long_prompt = "Ты — опытный фасилитатор ненасильственного общения в этом чате. Правила: {group_rules}"
    long_prompt_double = "Ты — опытный фасилитатор ненасильственного общения в этом чате. Правила: {{group_rules}}"
    assert validate_prompt(long_prompt) is None
    assert validate_prompt(long_prompt_double) is None
    assert validate_moderation_prompt('Судья: {text} и JSON {"a": 1}') is None
    assert validate_moderation_prompt("Судья: {{text}}") is None