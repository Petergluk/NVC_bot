# NVC_bot/bot/utils/formatters.py
# version: 2.2.0
# 2025-08-14T13:30:00Z
"""
Модуль с утилитарными функциями для форматирования текста.

Version 2.2.0:
- FEATURE: `format_stats_text` полностью переработана для отображения
           детальной статистики использования API по периодам и моделям.

Version 2.1.0:
- FIX: `format_debug_info_text` теперь корректно принимает и отображает
       `system_prompt_len`, получаемый из `gemini.py`.
"""
from typing import Dict, Any, Optional
import re
import html
import datetime

from ..config import MODEL_NAME_MAP

def escape_markdown_v2(text: str) -> str:
    escape_chars = r'\_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

def escape_html(text: str) -> str:
    return html.escape(text)

def truncate_for_log(text: str, head: int = 250, tail: int = 150) -> str:
    if not isinstance(text, str): text = str(text)
    if len(text) > head + tail + 20:
        return f"{text[:head]}\n... (усечено, всего {len(text)} симв.) ...\n{text[-tail:]}"
    return text

def format_stats_text(stats: Dict[str, Any]) -> str:
    """Форматирует расширенную статистику, включая использование API."""

    def _format_period_stats(period_data: Dict[str, Dict[str, int]]) -> str:
        if not period_data:
            return "_Нет данных за этот период\\._\n"
        
        lines = []
        sorted_models = sorted(period_data.items(), key=lambda item: item[1].get('requests', 0), reverse=True)
        
        for model_id, data in sorted_models:
            model_name = MODEL_NAME_MAP.get(model_id, model_id)
            requests = data.get('requests', 0)
            tokens = data.get('tokens', 0)
            lines.append(
                f"  `•` *{escape_markdown_v2(model_name)}*:\n"
                f"    Запросов: `{requests}` ⎥ Токенов: `{tokens:,}`"
            )
        return "\n".join(lines)

    lines = [
        f"📊 *Общая статистика бота*",
        f"👥 Активных чатов: `{stats.get('active_chats', 0)}`",
        f"💬 Всего сообщений в БД: `{stats.get('total_messages', 0)}`",
        f"🤖 Ответов AI \\(счетчик\\): `{stats.get('ai_responses', 0)}`",
        f"⚖️ Срабатываний модерации: `{stats.get('moderation_actions', 0)}`",
        f"⚠️ Пользователей с варнами: `{stats.get('users_with_warnings', 0)}`",
        "\n" + escape_markdown_v2("---") + "\n",
        "📈 *Статистика использования API*",
    ]

    usage = stats.get("usage", {})
    
    lines.append("\n🗓️ *Сегодня*")
    lines.append(_format_period_stats(usage.get('today', {})))
    
    lines.append("\n🗓️ *Вчера*")
    lines.append(_format_period_stats(usage.get('yesterday', {})))

    today_utc = datetime.datetime.now(datetime.UTC).date()
    
    days_in_week = today_utc.weekday() + 1
    week_stats = usage.get('week', {})
    total_week_req = sum(d.get('requests', 0) for d in week_stats.values())
    total_week_tok = sum(d.get('tokens', 0) for d in week_stats.values())
    avg_week_req = total_week_req / days_in_week if days_in_week > 0 else 0
    avg_week_tok = total_week_tok / days_in_week if days_in_week > 0 else 0
    lines.append(f"\n🗓️ *Среднее за неделю \\(в день, за {days_in_week}/7 дн\\.\\)*")
    lines.append(f"  Запросов: `{avg_week_req:.1f}` ⎥ Токенов: `{int(avg_week_tok):,}`")

    days_in_month = today_utc.day
    month_stats = usage.get('month', {})
    total_month_req = sum(d.get('requests', 0) for d in month_stats.values())
    total_month_tok = sum(d.get('tokens', 0) for d in month_stats.values())
    avg_month_req = total_month_req / days_in_month if days_in_month > 0 else 0
    avg_month_tok = total_month_tok / days_in_month if days_in_month > 0 else 0
    lines.append(f"\n🗓️ *Среднее за месяц \\(в день, за {days_in_month} дн\\.\\)*")
    lines.append(f"  Запросов: `{avg_month_req:.1f}` ⎥ Токенов: `{int(avg_month_tok):,}`")

    return "\n".join(lines)


def safe_markdown_preview(text: str, length: int) -> str:
    preview = text[:length].rsplit(' ', 1)[0] + "…" if len(text) > length else text
    return escape_markdown_v2(preview)

def format_debug_info_text(
    usage_metadata: Optional[Dict[str, Any]],
    system_prompt_len: int,
    chat_history_len: int,
    question_len: int
) -> str:
    lines = [escape_markdown_v2("\n\n--- 🐞 DEBUG INFO ---")]

    if usage_metadata:
        token_lines = []
        prompt_tokens = usage_metadata.get("prompt_token_count", 0)
        candidates_tokens = usage_metadata.get("candidates_token_count", 0)
        total_tokens = usage_metadata.get("total_token_count", 0)

        if prompt_tokens > 0: token_lines.append(f"*Prompt Tokens*: `{prompt_tokens}`")
        if candidates_tokens > 0: token_lines.append(f"*Candidates Tokens*: `{candidates_tokens}`")
        if total_tokens > 0: token_lines.append(f"*Total Tokens \\(API\\)*: `{total_tokens}`")
        
        if not token_lines: lines.append("*Token usage*: `N/A`")
        else: lines.extend(token_lines)
    else:
        lines.append("*Token usage*: `N/A`")
    
    lines.extend([
        escape_markdown_v2("---"),
        f"*System Prompt Chars*: `{system_prompt_len}`",
        f"*Context Chars*: `{chat_history_len}`",
        f"*User Msg Chars*: `{question_len}`",
    ])
    
    return "\n".join(lines)
