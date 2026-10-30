# NVC_bot/bot/utils/validators.py
# version: 3.0.0
# 2026-10-30T16:30:00Z

"""
Функции-валидаторы и парсер команд ННО-переводчика (/nvc, /NNO, /ННО).

Version 3.0.0:
- ADD: `NVC_COMMAND_PATTERN` и `parse_nvc_command` для распознавания латинских
       (`/nvc`, `/NVC`, `/nno`, `/NNO`) и кириллических (`/нно`, `/ННО`) команд
       в любом регистре (без `/rephrase`).
- FIX: Поддержка как одинарных `{var}`, так и двойных `{{var}}` переменных
       во всех шаблонах промптов.
"""

import re
from typing import Optional, List, Tuple

# Регулярное выражение для команд /nvc, /NNO и кириллической /ННО в любом регистре (без /rephrase)
NVC_COMMAND_PATTERN = re.compile(
    r"^/(?P<cmd>nvc|nno|нно)(?:@[A-Za-z0-9_]+)?(?:\s+(?P<payload>[\s\S]+))?$",
    re.IGNORECASE,
)


def parse_nvc_command(text: str) -> Tuple[bool, Optional[str]]:
    """
    Проверяет, начинается ли сообщение с команды /nvc, /NNO или /ННО (в любом регистре).
    Возвращает кортеж (is_nvc_command, payload_text_or_none).
    """
    if not text:
        return False, None
    match = NVC_COMMAND_PATTERN.match(text.strip())
    if not match:
        return False, None
    payload = match.group("payload")
    return True, payload.strip() if payload and payload.strip() else None


def _contains_placeholder(text: str, var_name: str) -> bool:
    """Проверяет наличие плейсхолдера `{var_name}` или `{{var_name}}` в тексте."""
    return f"{{{var_name}}}" in text or f"{{{{{var_name}}}}}" in text


def validate_prompt(prompt: str) -> Optional[str]:
    """
    Проверяет системный промпт на базовые требования.
    """
    if not prompt or len(prompt.strip()) < 50:
        return "Промпт слишком короткий. Опишите роль и задачу бота подробнее."
    return None


def validate_moderation_prompt(prompt: str) -> Optional[str]:
    """
    Проверяет промпт судьи модерации на наличие переменной `{text}`.
    """
    if not prompt or not _contains_placeholder(prompt, "text"):
        return "Промпт должен содержать переменную `{text}`."
    return None


def validate_welcome_prompt(prompt: str) -> Optional[str]:
    """
    Проверяет промпт приветствия на наличие переменной `{user_mention}`.
    """
    if not prompt or not _contains_placeholder(prompt, "user_mention"):
        return "Промпт должен содержать переменную `{user_mention}`."
    return None


def validate_moderation_template(template: str) -> Optional[str]:
    """
    Проверяет шаблон сообщения о санкции на наличие обязательных переменных.
    """
    required_vars: List[str] = [
        "user_mention",
        "violator_message",
        "warnings_count",
        "rules_list",
        "chat_history"
    ]
    missing_vars = [f"{{{var}}}" for var in required_vars if not _contains_placeholder(template, var)]

    if missing_vars:
        return f"Шаблон должен содержать следующие переменные: {', '.join(missing_vars)}"
    return None