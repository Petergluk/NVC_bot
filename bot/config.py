# NVC_bot/bot/config.py
# version: 2.0.0
# 2026-10-30T06:30:00Z
"""
Конфигурационный файл проекта.
Использует Pydantic для валидации переменных окружения.

Version 2.0.0:
- FIX: Безопасная инициализация Settings при запуске тестов (pytest) без файла .env,
       чтобы импорт пакета `bot` в CI/CD не завершал процесс через exit(1).
"""
import os
import sys
import logging
from pathlib import Path
from typing import List, Dict
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Загрузка переменных окружения из файла .env
load_dotenv()

# --- Пути к Директориям ---
ROOT_DIR = Path(__file__).parent.parent
DATA_DIR = ROOT_DIR / "data"
PROMPTS_DIR = ROOT_DIR / "prompts"
PROMPTS_DIR.mkdir(exist_ok=True)


def _load_prompt(file_name: str) -> str:
    """
    Загружает промпт из файла, игнорируя строки-комментарии.
    Если файл не найден или пуст, возвращает пустую строку.
    """
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


class Settings(BaseSettings):
    """
    Класс для хранения и валидации настроек из переменных окружения.
    """
    # --- Основные Токены и ID ---
    TELEGRAM_BOT_TOKEN: str = "000000000:TEST_TOKEN_PLACEHOLDER"
    GEMINI_API_KEY: str = "TEST_GEMINI_API_KEY"
    ADMIN_IDS_STR: str = "123456789"

    # --- Имена моделей Gemini (Free Tier) ---
    AVAILABLE_MODELS: List[str] = [
        "gemini-3.8-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-3-flash-preview",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.5-pro",
    ]

    DEFAULT_FACILITATOR_MODEL: str = "gemini-3.6-flash"
    DEFAULT_MODERATION_MODEL: str = "gemini-3.5-flash-lite"
    DEFAULT_WELCOME_MODEL: str = "gemini-3.5-flash-lite"

    # Обратная совместимость для старых переменных
    GEMINI_PRO_MODEL: str = "gemini-2.5-pro"
    GEMINI_FLASH_MODEL: str = "gemini-3.6-flash"
    GEMINI_LITE_MODEL: str = "gemini-3.5-flash-lite"

    # --- Настройки AI Моделей и Контекста ---
    CONTEXT_MESSAGES_LIMIT: int = 20
    CONTEXT_JUDGE_LIMIT: int = 10
    PROMPT_PREVIEW_LENGTH: int = 3600

    # --- Настройки генерации AI по умолчанию ---
    DEFAULT_TEMPERATURE: float = 0.7
    DEFAULT_TOP_P: float = 1.0
    DEFAULT_TOP_K: int = 32
    DEFAULT_MAX_OUTPUT_TOKENS: int = 4096

    # --- Настройки Модерации по Умолчанию ---
    DEFAULT_MODERATION_PROMPT: str = _load_prompt("default_moderation_prompt.txt")
    DEFAULT_MODERATION_TASK_TEMPLATE: str = _load_prompt("default_moderation_task_template.txt")
    DEFAULT_MODERATION_MODEL: str = "gemini-2.5-flash-lite"
    DEFAULT_SANCTION_RULES: List[dict] = [
        {'warnings': 3, 'action': 'MUTE', 'duration_hours': 24},
        {'warnings': 5, 'action': 'BAN', 'duration_hours': None}
    ]

    # --- Списки триггеров и исключений по умолчанию ---
    DEFAULT_TRIGGERS: Dict[str, List[str]] = {
        "Местоименные якори": ["ты", "тебя", "тебе", "тобой", "твой", "твоя", "твоё", "твои", "вы", "вас", "вам", "вами", "ваш", "ваша", "ваше", "ваши"],
        "Долженствование": ["должен", "должна", "должны", "должно", "обязан", "обязана", "обязаны", "надо", "нужно", "необходимо", "следует", "положено", "надлежит", "требуется", "приходится", "вынужден", "вынуждена", "не смей", "не смейте"],
        "Императивы": ["замолчи", "заткнись", "прекрати", "перестань", "брось", "убери", "сделай", "иди", "пойди", "уйди", "слушай", "послушай", "ответь", "отвечай", "верни", "надень", "сними", "подойди", "отойди", "закрой", "открой", "быстро", "срочно", "немедленно"],
        "Генерализаторы": ["всегда", "никогда", "вечно", "постоянно", "бесконечно", "совсем", "абсолютно", "каждый", "любой", "никто", "ничто", "поголовно", "сплошь", "целиком", "вы все"],
        "Обвинения": ["из-за тебя", "по твоей вине", "ты меня", "довёл", "доводишь", "испортил", "портишь", "вынудил", "заставил", "вот из-за тебя"],
        "Ярлыки": ["ленивый", "лентяй", "бездельник", "тупой", "глупый", "идиот", "дебил", "дурак", "безответственный", "никчёмный", "эгоист", "нарцисс", "псих", "манипулятор", "неряха", "истеричка", "психопат", "больной", "ненормальный", "мерзкий", "жадный"],
        "Чтение мыслей": ["ты думаешь", "ты считаешь", "ты хочешь", "ты пытаешься", "ты специально", "у тебя просто", "это потому что", "если ты не"],
        "Сравнения": ["хуже", "слабее", "глупее", "толще", "лучше бы", "будь как", "почему ты не как", "посмотри на", "раньше"],
        "Шантаж": ["стыдись", "позор", "опозорил", "как тебе не стыдно", "меня в гроб сведёшь", "не огорчай", "не расстраивай", "ты делаешь мне больно"],
        "Другие маркеры": ["опять", "снова", "вечно", "никакого толку", "как обычно ты", "да кто ты такой", "нормальный", "тебе бы", "тебе стоит", "тебе следовало"]
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
    DEFAULT_WELCOME_MODEL: str = "gemini-2.5-flash"
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

PRIVATE_CHAT_REPLY = "Этот бот предназначен для работы в групповых чатах. В личных сообщениях доступен только администраторам. По вопросам использования свяжитесь с @Petergluk"
GROUP_START_MESSAGE = (
    "Поток сознания на связи. Чтобы задать вопрос, упомяните меня: @{bot_username}\n\n"
    "Для списка команд используйте /help."
)
ADMIN_START_MESSAGE = (
    "Приветствую, Архитектор. Все системы в вашем распоряжении.\n\n"
    "/settings - настройки AI ассистента.\n"
    "/moderate - настройки модерации.\n"
    "/help - для полного списка команд."
)
