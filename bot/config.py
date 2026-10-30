# NVC_bot/bot/config.py
# version: 3.0.0
# 2026-10-30T16:30:00Z

'''
Конфигурационный файл проекта.
Использует Pydantic для валидации переменных окружения.

Version 3.0.0:
- UPGRADE: Актуализирован полный список моделей по документации Google AI Studio Pricing
           (Free Tier: gemini-3.8-flash по умолчанию, gemini-3.6-flash, gemini-3.5-flash-lite,
           gemini-3.1-flash-lite, gemini-3-flash-preview, gemini-2.5-pro, gemini-2.5-flash,
           gemini-2.5-flash-lite, gemma-4; Paid Tier: gemini-4-argon, gemini-3.1-pro-preview).
- ADD: Настройки мягкой пре-модерации, автоамнистии предупреждений и проактивного фасилитатора.
'''

import os
import sys
import logging
from pathlib import Path
from typing import List, Dict

from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).parent.parent
DATA_DIR = ROOT_DIR / "data"
PROMPTS_DIR = ROOT_DIR / "prompts"

PROMPTS_DIR.mkdir(exist_ok=True)


def _load_prompt(file_name: str) -> str:
    '''
    Загружает промпт из файла, игнорируя строки-комментарии.
    Если файл не найден или пуст, возвращает пустую строку.
    '''
    file_path = PROMPTS_DIR / file_name
    if not file_path.exists():
        logging.warning("Файл промпта не найден: %s. Будет использовано пустое значение.", file_path)
        return ""
    try:
        raw_lines = file_path.read_text(encoding='utf-8').splitlines()
        prompt_lines = [line for line in raw_lines if not line.strip().startswith('#')]
        return "\n".join(prompt_lines).strip()
    except IOError as e:
        logging.error("Не удалось прочитать файл промпта %s: %s. Будет использовано пустое значение.", file_path, e)
        return ""


# Полный реестр актуальных моделей согласно документации Google AI Studio Pricing
AVAILABLE_MODELS_CATALOG: Dict[str, Dict[str, str]] = {
    # --- Free Tier (Доступны бесплатно) ---
    "gemini-3.8-flash": {
        "label": "Gemini 3.8 Flash (Free · По умолчанию)",
        "tier": "free",
        "description": "Актуальная быстрая мультимодальная модель для сложных рабочих процессов и агентов.",
    },
    "gemini-3.6-flash": {
        "label": "Gemini 3.6 Flash (Free · Сбалансированная)",
        "tier": "free",
        "description": "Сбалансированная модель предыдущего поколения Flash.",
    },
    "gemini-3.5-flash-lite": {
        "label": "Gemini 3.5 Flash-Lite (Free · Быстрая)",
        "tier": "free",
        "description": "Экономичная компактная модель для высоконагруженных задач, переводов и обработки данных.",
    },
    "gemini-3.1-flash-lite": {
        "label": "Gemini 3.1 Flash-Lite (Free · Компактная 3.1)",
        "tier": "free",
        "description": "Облегченная быстрая модель Flash-Lite линейки 3.1.",
    },
    "gemini-3-flash-preview": {
        "label": "Gemini 3 Flash Preview (Free · Базовая 3.0)",
        "tier": "free",
        "description": "Базовая модель Flash линейки 3.",
    },
    "gemini-2.5-pro": {
        "label": "Gemini 2.5 Pro (Free · Рассуждения)",
        "tier": "free",
        "description": "Продвинутая модель линейки 2.5 для рассуждений и анализа сложных конфликтов.",
    },
    "gemini-2.5-flash": {
        "label": "Gemini 2.5 Flash (Free · 1M + Thinking)",
        "tier": "free",
        "description": "Гибридная модель с контекстом до 1M токенов и настраиваемым бюджетом рассуждений.",
    },
    "gemini-2.5-flash-lite": {
        "label": "Gemini 2.5 Flash-Lite (Free · Легкая 2.5)",
        "tier": "free",
        "description": "Компактная версия линейки 2.5.",
    },
    "gemma-4": {
        "label": "Gemma 4 (Free · Открытая легковесная)",
        "tier": "free",
        "description": "Открытая легковесная модель с полностью бесплатным доступом по API.",
    },
    # --- Paid Tier (Только платный тариф) ---
    "gemini-4-argon": {
        "label": "Gemini 4 Argon [Paid · Флагман]",
        "tier": "paid",
        "description": "Флагманская модель глубоких рассуждений (только Paid Tier).",
    },
    "gemini-3.1-pro-preview": {
        "label": "Gemini 3.1 Pro Preview [Paid · Pro 3.1]",
        "tier": "paid",
        "description": "Продвинутая Pro-модель линейки 3.1 (только Paid Tier).",
    },
}


class Settings(BaseSettings):
    '''
    Класс для хранения и валидации настроек из переменных окружения.
    '''
    TELEGRAM_BOT_TOKEN: str = "000000000:TEST_TOKEN_PLACEHOLDER"
    GEMINI_API_KEY: str = "TEST_GEMINI_API_KEY"
    ADMIN_IDS_STR: str = "123456789"

    # --- Имена моделей Gemini (по умолчанию: gemini-3.8-flash) ---
    GEMINI_PRO_MODEL: str = "gemini-3.8-flash"
    GEMINI_FLASH_MODEL: str = "gemini-3.8-flash"
    GEMINI_LITE_MODEL: str = "gemini-3.5-flash-lite"

    # --- Настройки AI Моделей и Контекста ---
    CONTEXT_MESSAGES_LIMIT: int = 20
    CONTEXT_JUDGE_LIMIT: int = 10

    DEFAULT_GENERATION_CONFIG: Dict[str, float | int] = {
        "temperature": 0.7,
        "top_p": 0.95,
        "top_k": 40,
        "max_output_tokens": 4096,
    }

    DEFAULT_CONTEXT_CONFIG: Dict[str, int] = {
        "context_messages_limit": 20,
        "context_judge_limit": 10,
    }

    # --- Настройки Модерации и Автоамнистии по умолчанию ---
    DEFAULT_MODERATION_MODEL: str = "gemini-3.8-flash"
    DEFAULT_SOFT_MODERATION_ENABLED: bool = True
    DEFAULT_AUTO_AMNESTY_ENABLED: bool = True
    DEFAULT_AUTO_AMNESTY_DAYS: int = 7
    DEFAULT_PROACTIVE_FACILITATOR_ENABLED: bool = True
    DEFAULT_PROACTIVE_TRIGGER_THRESHOLD: int = 3

    DEFAULT_MODERATION_PROMPT: str = _load_prompt("default_moderation_prompt.txt")
    DEFAULT_MODERATION_TASK_TEMPLATE: str = _load_prompt("default_moderation_task_template.txt")

    DEFAULT_SANCTION_RULES: List[Dict[str, str | int | None]] = [
        {"warnings": 3, "action": "MUTE", "duration_hours": 24},
        {"warnings": 5, "action": "MUTE", "duration_hours": 168},
        {"warnings": 10, "action": "BAN", "duration_hours": None}
    ]

    DEFAULT_TRIGGERS: Dict[str, List[str]] = {
        "Прямые местоимения": ["ты", "тебя", "тебе", "тобой", "вы", "вас", "вам", "вами"],
        "Притяжательные местоимения": ["твой", "твоя", "твоё", "твои", "ваш", "ваша", "ваше", "ваши"],
        "Слова-обобщения и обвинения": ["всегда", "никогда", "вечно", "опять ты", "снова ты", "ты должен", "ты обязана", "вы должны", "по твоей вине", "из-за тебя"],
        "Оценочные суждения и ярлыки": ["бред", "чушь", "глупость", "ерунда", "ахинея", "ересь", "идиот", "дурак", "тупой", "неадекват", "клоун", "лицемер", "эгоист", "манипулятор", "токсик", "нытик"],
        "Сарказм и обесценивание": ["ну да конечно", "ага сейчас", "держи карман шире", "умник нашелся", "самый умный", "много знаешь", "кому ты лечишь", "не смеши", "очень умно", "великий эксперт", "диванный критик"],
        "Конфликтные конструкции": ["хватит", "прекрати", "замолчи", "заткнись", "угомонись", "отстань", "достал", "бесишь", "раздражаешь", "надоел", "сколько можно", "опять", "снова", "вечно", "никакого толку", "как обычно ты", "да кто ты такой", "нормальный", "тебе бы", "тебе стоит", "тебе следовало"]
    }

    DEFAULT_EXCEPTIONS: Dict[str, List[str]] = {
        "Благодарности": ["спасибо тебе", "спасибо вам", "благодарю тебя", "благодарю вас", "очень признателен", "очень признательна"],
        "Вежливые вопросы": ["как ты?", "как вы?", "как твои дела?", "как ваши дела?", "как поживаешь?", "как поживаете?"],
        "Вежливые просьбы": ["ты не мог бы", "вы не могли бы", "прошу тебя", "прошу вас"],
        "Поддержка/забота": ["ты в порядке?", "с тобой всё хорошо?", "вам помочь?", "тебе помочь?", "ты уверен?", "вы уверены?"],
        "Нейтральные упоминания": ["если ты хочешь", "когда ты сможешь", "где ты видел", "как ты находишь", "что ты предпочитаешь", "почему ты выбрал"],
        "Технические/нейтральные": ["ты упомянул", "вы говорили", "в твоем сообщении", "в вашем сообщении", "на твой вопрос", "на ваш вопрос"]
    }

    # --- Настройки приветствий по умолчанию ---
    DEFAULT_WELCOME_MODEL: str = "gemini-3.8-flash"
    DEFAULT_WELCOME_PROMPT: str = _load_prompt("default_welcome_prompt.txt")

    # --- Системный промпт по умолчанию ---
    DEFAULT_SYSTEM_PROMPT: str = _load_prompt("default_system_prompt.txt")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


_is_testing = "pytest" in sys.modules or os.environ.get("PYTEST_CURRENT_TEST") is not None

try:
    settings = Settings()
    if not _is_testing and (
        settings.TELEGRAM_BOT_TOKEN == "000000000:TEST_TOKEN_PLACEHOLDER"
        or settings.GEMINI_API_KEY == "TEST_GEMINI_API_KEY"
    ):
        logging.warning("Используются тестовые плейсхолдеры токенов. Проверьте файл .env перед запуском в продакшене.")
except Exception as e:
    logging.critical(f"КРИТИЧЕСКАЯ ОШИБКА: Не удалось загрузить конфигурацию. Проверьте файл .env. Ошибка: {e}")
    if not _is_testing:
        sys.exit(1)
    settings = Settings.model_construct()

try:
    ADMIN_IDS = [int(admin_id.strip()) for admin_id in settings.ADMIN_IDS_STR.split(',') if admin_id.strip()]
    ADMIN_IDS_SET = set(ADMIN_IDS)
except (ValueError, TypeError):
    logging.critical("КРИТИЧЕСКАЯ ОШИБКА: Переменная ADMIN_IDS_STR в .env имеет неверный формат.")
    if not _is_testing:
        sys.exit(1)
    ADMIN_IDS = []
    ADMIN_IDS_SET = set()

PRIVATE_CHAT_REPLY = (
    "🌱 Я — помощник по Ненасильственному общению (ННО / NVC).\n\n"
    "Напишите мне сюда любой черновик сообщения или резкую фразу, и я переведу её "
    "по 4 шагам ННО (Наблюдение → Чувство → Потребность → Просьба).\n\n"
    "В групповом чате вы также можете ответить на любое сообщение командой /ННО, /NNO или /nvc."
)
GROUP_START_MESSAGE = (
    "Поток сознания на связи. Чтобы задать вопрос, упомяните меня: @{bot_username}\n"
    "Для перевода резкой фразы на язык ННО используйте /ННО, /NNO или /nvc.\n\n"
    "Для списка команд используйте /help."
)
ADMIN_START_MESSAGE = (
    "Приветствую, Архитектор. Все системы v3.0 в вашем распоряжении.\n\n"
    "/settings - настройки AI фасилитатора и моделей Gemini 3.8.\n"
    "/moderate - настройки модерации, мягкого режима и автоамнистии.\n"
    "/nvc или /ННО - перевод фразы по 4 шагам ННО.\n"
    "/help - для полного списка команд."
)