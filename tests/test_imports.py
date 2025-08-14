# NVC_bot/tests/test_imports.py
"""
Тест для проверки корректности импортов всех модулей в проекте.

Это помогает выявить циклические зависимости и синтаксические ошибки
на раннем этапе, не запуская всего бота.
"""

import importlib
import pkgutil
import sys
from pathlib import Path
import pytest

# --- ИСПРАВЛЕНИЕ: Начало ---
# Добавляем корневую директорию проекта в sys.path.
# Это необходимо, чтобы Python мог найти пакет 'bot' при запуске тестов
# из любой директории, включая 'tests/'.
# 1. Получаем путь к текущему файлу (d:/.../tests/test_imports.py)
# 2. Берем его родительскую директорию (.../tests/)
# 3. Берем родительскую директорию еще раз (.../) - это и есть корень проекта.
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
# --- ИСПРАВЛЕНИЕ: Конец ---


def _iter_package_modules(package_root: str):
    """
    Рекурсивно обходит все подмодули в указанном пакете.

    Args:
        package_root (str): Имя корневого пакета (например, "bot").

    Yields:
        str: Полное имя каждого найденного модуля (например, "bot.handlers.user").
    """
    try:
        package = importlib.import_module(package_root)
        prefix = package.__name__ + "."
        
        # Используем pkgutil.walk_packages для надежного обхода
        for _, module_name, is_pkg in pkgutil.walk_packages(
            package.__path__, prefix=prefix
        ):
            if not is_pkg:
                yield module_name
    except ImportError as e:
        pytest.fail(f"Не удалось импортировать корневой пакет '{package_root}': {e}")


# Собираем все модули из нашего пакета 'bot'
ALL_MODULES = list(_iter_package_modules("bot"))

@pytest.mark.parametrize("module_name", ALL_MODULES)
def test_import_module(module_name: str):
    """
    Параметризованный тест, который пытается импортировать каждый модуль.

    Args:
        module_name (str): Имя модуля для импорта, предоставленное pytest.
    """
    try:
        importlib.import_module(module_name)
    except ImportError as e:
        pytest.fail(
            f"Ошибка импорта в модуле '{module_name}': {e}", pytrace=False
        )
