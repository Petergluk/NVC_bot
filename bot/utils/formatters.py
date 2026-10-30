# NVC_bot/bot/utils/formatters.py
# version: 2.0.0
# 2026-10-30T06:30:00Z
"""
Модуль с утилитарными функциями для форматирования текста.

Version 2.0.0:
- ADD: Добавлена функция `safe_format_template`, которая безопасно подставляет
       переменные как в формате `{var}`, так и `{{var}}`, не вызывая `KeyError`
       на произвольных фигурных скобках (например, JSON-примерах) в тексте промпта.
"""
from typing import Dict, Any, Optional
import re
import html


def escape_markdown_v2(text: str) -> str:
    """
    Экранирует специальные символы для `ParseMode.MARKDOWN_V2`.
    """
    escape_chars = r'\_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', str(text))


def escape_html(text: str) -> str:
    """
    Экранирует специальные символы HTML: <, > и &.
    """
    return html.escape(str(text))


def safe_format_template(template: str, **kwargs: Any) -> str:
    """
    Безопасно подставляет переменные в шаблон промпта.
    Поддерживает как одинарные `{key}`, так и двойные `{{key}}` скобки,
    и не падает с KeyError/ValueError, если в шаблоне или тексте пользователя
    встречаются сторонние фигурные скобки.
    """
    if not template:
        return ""
    result = template
    for key, value in kwargs.items():
        val_str = str(value) if value is not None else ""
        result = result.replace(f"{{{{{key}}}}}", val_str)
        result = result.replace(f"{{{key}}}", val_str)
    return result


def format_stats_text(stats: Dict[str, Any]) -> str:
    """
    Форматирует словарь со статистикой в человекочитаемый текст для MarkdownV2.
    """
    return (
        f"📊 *Статистика бота*\n\n"
        f"👥 Активных чатов: `{stats.get('active_chats', 0)}`\n"
        f"💬 Всего сообщений: `{stats.get('total_messages', 0)}`\n"
        f"🤖 Ответов AI: `{stats.get('ai_responses', 0)}`\n"
        f"⚖️ Срабатываний модерации: `{stats.get('moderation_actions', 0)}`\n"
        f"⚠️ Пользователей с варнами: `{stats.get('users_with_warnings', 0)}`"
    )


def safe_markdown_preview(text: str, length: int) -> str:
    """
    Создает безопасное для MarkdownV2 превью текста.
    """
    if len(text) > length:
        parts = text[:length].rsplit(' ', 1)
        preview = (parts[0] if parts else text[:length]) + "…"
    else:
        preview = text
    return escape_markdown_v2(preview)


def format_debug_info_text(
    usage_metadata: Optional[Dict[str, Any]],
    system_prompt_len: int,
    chat_history_len: int,
    question_len: int
) -> str:
    """
    Форматирует отладочную информацию о запросе в текстовый блок для MarkdownV2.
    """
    lines = [
        escape_markdown_v2("\n\n--- 🐞 DEBUG INFO ---"),
    ]

    if usage_metadata:
        token_components = {
            "Prompt Tokens": usage_metadata.get("prompt_token_count"),
            "Candidates Tokens": usage_metadata.get("candidates_token_count"),
            "Cached Tokens": usage_metadata.get("cached_content_token_count"),
            "Tool Use Tokens": usage_metadata.get("tool_use_prompt_token_count"),
            "Thinking Tokens": usage_metadata.get("thoughts_token_count"),
        }

        known_sum = 0
        for name, value in token_components.items():
            if value and value > 0:
                lines.append(f"*{escape_markdown_v2(name)}*: `{value}`")
                known_sum += value

        total_tokens = usage_metadata.get("total_token_count") or 0
        unaccounted = total_tokens - known_sum

        if unaccounted != 0:
            lines.append(f"*_{escape_markdown_v2('-> Неучтенные Токены')}_*: `{unaccounted}`")

        lines.append(f"*{escape_markdown_v2('Total Tokens (API)')}*: `{total_tokens if usage_metadata.get('total_token_count') is not None else 'N/A'}`")
    else:
        lines.append("*Token usage*: `N/A`")

    lines.extend([
        escape_markdown_v2("---"),
        f"*System Prompt Chars*: `{system_prompt_len}`",
        f"*Context Chars*: `{chat_history_len}`",
        f"*User Msg Chars*: `{question_len}`",
    ])

    return "\n".join(lines)