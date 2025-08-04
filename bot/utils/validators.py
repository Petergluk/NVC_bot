# NVC_bot/bot/utils/validators.py
# version: 1.2.0
# 2025-07-26T10:00:00Z
"""
Функции-валидаторы для различных частей проекта.
"""
import re
from typing import Optional, List

def validate_prompt(prompt: str) -> Optional[str]:
    """
    Проверяет системный промпт на базовые требования.
    
    Args:
        prompt (str): Текст системного промпта.
        
    Returns:
        Optional[str]: Текст ошибки, если валидация не пройдена, иначе None.
    """
    if not prompt or len(prompt.strip()) < 50:
        return "Промпт слишком короткий. Опишите роль и задачу бота подробнее."
    return None

def validate_moderation_template(template: str) -> Optional[str]:
    """
    Проверяет шаблон сообщения о санкции на наличие обязательных переменных.

    Args:
        template (str): Текст шаблона.

    Returns:
        Optional[str]: Текст ошибки, если валидация не пройдена, иначе None.
    """
    # ИСПРАВЛЕНИЕ: Добавлена проверка на {user_mention}
    required_vars = [
        "{user_mention}",
        "{violator_message}",
        "{warnings_count}",
        "{rules_list}",
        "{chat_history}"
    ]
    missing_vars = [var for var in required_vars if var not in template]
    if missing_vars:
        return f"Шаблон должен содержать следующие переменные: {', '.join(missing_vars)}"
    return None

# ИСПРАВЛЕНИЕ: Функция extract_bot_mention удалена, так как ее логика
# была упрощена и перенесена непосредственно в обработчик handle_message.
