# split_ai_code.py
# v. 2.5.3
# 2025-08-07T19:30:00.000Z
#!/usr/bin/env python3
"""
Двухрежимный скрипт для работы с кодом проекта.

Режим 1: Разбор (split)
Разбивает «сырой» вывод ИИ на реальные файлы проекта.
В конце каждой сессии предлагает отменить сделанные изменения.
Запуск: python split_ai_code.py <файл_вывода_AI.txt>

Режим 2: Сборка (gather)
Собирает все файлы проекта (по настраиваемым маскам) в один .txt файл.
Имя выходного файла: <имя_папки_проекта>_code.txt.
Исключает служебные папки.
Запуск: python split_ai_code.py gather

--- ИСТОРИЯ ИЗМЕНЕНИЙ ---
v. 2.5.3: FINAL FIX: Принудительная синхронизация модулей. Устранена постоянная критическая ошибка в обработке аргументов командной строки (sys.argv[1]).
v. 2.5.2: CRITICAL FIX: Исправлена регрессия в точке входа. Код приведен в соответствие с намерением (использование sys.argv[1] вместо sys.argv).
v. 2.5.1: FIX: Исправлена критическая ошибка в точке входа (AttributeError: 'list' object has no attribute 'lower').
v. 2.5.0: ИСПРАВЛЕНО: Ключевая ошибка в регулярном выражении для поиска блоков кода.
"""

import re
import sys
import shutil
from pathlib import Path
from typing import Tuple, Set, List, Dict

# --- КОНФИГУРАЦИЯ СБОРКИ (GATHER) ---
GATHER_FILE_PATTERNS: List[str] = ["*.py",  "*.txt", "*.yaml", "*.toml", "*.log", "project_history.md"]
EXCLUDED_GATHER_DIRS: Set[str] = {"temp", "doc", "update", ".github", ".venv", "__pycache__", ".pytest_cache" ".git"}
GATHER_SORT_ORDER: Dict[str, int] = {".py": 1, ".env": 2, ".yaml": 3, ".toml": 4, ".gitignore": 5, ".txt":7, ".md": 8,  ".log": 10}

# --- ОБЩИЕ РЕГУЛЯРНЫЕ ВЫРАЖЕНИЯ ---
CODE_BLOCK_RE = re.compile(r"^```(\w+)?\n(.*?)\n^```", re.S | re.M)
PATH_LINE_RE = re.compile(r"#\s*([^\n\r]+)")
PATH_CANDIDATE_RE = re.compile(r"^\s*(?:#\s*)?([a-zA-Z0-9._/-]+\/[a-zA-Z0-9._-]+)\s*$", re.M)


# --- ANSI ЦВЕТОВЫЕ КОДЫ ---
RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
RESET = '\033[0m'

# --- ОБЩИЕ УТИЛИТЫ ---
def format_size(size_bytes: int) -> str:
    """Форматирует размер файла в человекочитаемый вид (B, KB, MB)."""
    if size_bytes < 1024: return f"{size_bytes} B"
    if size_bytes < 1024**2: return f"{size_bytes/1024:.1f} KB"
    return f"{size_bytes/1024**2:.1f} MB"

# =============================================================================
# РЕЖИМ 1: СБОРКА ПРОЕКТА (GATHER)
# =============================================================================
def generate_project_tree(directory: Path, excluded_dirs: Set[str], prefix: str = "") -> List[str]:
    """Рекурсивно генерирует строковое представление дерева каталогов."""
    items = sorted([p for p in directory.iterdir() if p.name.lower() not in excluded_dirs], key=lambda x: (x.is_file(), x.name.lower()))
    tree_lines = []
    for i, item in enumerate(items):
        is_last = i == (len(items) - 1)
        connector = "└── " if is_last else "├── "
        tree_lines.append(f"{prefix}{connector}{item.name}")
        if item.is_dir():
            new_prefix = prefix + ("    " if is_last else "│   ")
            tree_lines.extend(generate_project_tree(item, excluded_dirs, new_prefix))
    return tree_lines

def _gather_latest_logs(project_root: Path, excluded_dirs: Set[str]) -> List[Path]:
    """Находит самые свежие лог-файлы для каждого типа (префикса)."""
    latest_logs: Dict[str, Path] = {}
    log_prefix_re = re.compile(r'^([a-zA-Z_]+)_')
    all_log_files = [
        p for p in project_root.rglob("*.log")
        if not any(part.lower() in excluded_dirs for part in p.relative_to(project_root).parts)
    ]
    for file_path in all_log_files:
        match = log_prefix_re.match(file_path.name)
        if match:
            prefix = match.group(1)
            if prefix not in latest_logs or file_path.name > latest_logs[prefix].name:
                latest_logs[prefix] = file_path
    return list(latest_logs.values())

def gather_files() -> None:
    """Собирает файлы проекта в один текстовый файл."""
    script_path = Path(sys.argv[0]).resolve()
    project_root = script_path.parent.parent
    output_filename = f"{project_root.name}_code.txt"
    output_file_path = script_path.parent / output_filename
    current_excluded_dirs = EXCLUDED_GATHER_DIRS.copy()
    current_excluded_dirs.add(script_path.parent.name.lower())
    print(f"🔍 Поиск файлов в: {project_root}")
    print(f"📋 Используемые маски: {', '.join(GATHER_FILE_PATTERNS)}")
    print(f"🚫 Исключенные папки: {', '.join(sorted(current_excluded_dirs))}")
    print("\n🏗️  Создание структуры проекта...")
    tree_header = f"# Project Structure: {project_root.name}/\n# -----------------"
    project_tree_lines = generate_project_tree(project_root, current_excluded_dirs)
    file_separator = "\n\n=======< FILE SEPARATOR >=======\n\n"
    collected_content = [tree_header, *project_tree_lines, file_separator]
    print("✅  Структура создана.")
    print("\n📚 Сбор содержимого файлов...")
    found_files: Set[Path] = set()
    general_patterns = [p for p in GATHER_FILE_PATTERNS if p != "*.log"]
    for pattern in general_patterns:
        for file_path in project_root.rglob(pattern):
            if not any(part.lower() in current_excluded_dirs for part in file_path.relative_to(project_root).parts):
                found_files.add(file_path)
    if "*.log" in GATHER_FILE_PATTERNS:
        latest_logs = _gather_latest_logs(project_root, current_excluded_dirs)
        for log_path in latest_logs:
            found_files.add(log_path)
    def sort_key(p: Path):
        return (GATHER_SORT_ORDER.get(p.suffix, 99), p.as_posix())
    sorted_files = sorted(list(found_files), key=sort_key)
    for file_path in sorted_files:
        relative_path = file_path.relative_to(project_root)
        try:
            content = file_path.read_text(encoding="utf-8")
            header = f"# {relative_path.as_posix()}"
            collected_content.extend([header, content, file_separator])
            print(f"  [+] Добавлен: {relative_path}")
        except Exception as e:
            print(f"  [!] Не удалось прочитать файл {relative_path}: {e}")
    if not sorted_files:
        print("❌ Не найдено ни одного подходящего файла для сборки.")
        return
    final_text = "\n".join(collected_content)
    output_file_path.write_text(final_text, encoding="utf-8")
    print(f"\n✅ Готово! Собрано файлов: {len(sorted_files)}.")
    print(f"📝 Результат сохранен в: {output_file_path} ({format_size(output_file_path.stat().st_size)})")

# =============================================================================
# РЕЖИМ 2: РАЗБОР ПРОЕКТА (SPLIT)
# =============================================================================
def find_project_root(script_path: Path, project_name: str) -> Path | None:
    """Находит корень проекта по имени, двигаясь вверх от пути скрипта."""
    for parent in script_path.parents:
        if parent.name == project_name: return parent
    return None

def find_path_in_preceding_text(text: str) -> Path | None:
    """Ищет путь к файлу в тексте, предшествующем блоку кода."""
    candidates = PATH_CANDIDATE_RE.findall(text)
    return Path(candidates[-1].strip()) if candidates else None

def split_path_and_code(block: str) -> Tuple[Path, str] | None:
    """Извлекает путь и код из блока, если путь указан в первой строке."""
    lines = block.splitlines()
    if not lines: return None
    match = PATH_LINE_RE.match(lines[0].strip())
    if not match: return None
    raw_path = match.group(1).strip()
    return (Path(raw_path), block.strip() + "\n") if "/" in raw_path or "\\" in raw_path else None

def save_code(target_path: Path, code: str, script_path: Path, project_root: Path | None) -> None:
    """
    Сохраняет код. Для файлов журнала (*.md) добавляет содержимое, для остальных — перезаписывает.
    Создает резервную копию перед любым изменением.
    """
    was_overwritten = target_path.is_file()
    old_size = 0
    if was_overwritten:
        old_size = target_path.stat().st_size
        backup_dir = script_path.parent / "BkUp"
        base_path = project_root if project_root else script_path.parent
        try:
            relative_backup_path = target_path.relative_to(base_path)
            backup_path = backup_dir / relative_backup_path
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target_path, backup_path)
            print(f"📦  Резервная копия создана: {backup_path.relative_to(script_path.parent)}")
        except Exception as e:
            print(f"❌  Ошибка при создании резервной копии: {e}")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    
    is_journal_file = target_path.name in ["Project_journal.md", "project_history.md"]
    status = ""

    if is_journal_file and was_overwritten:
        content_lines = code.splitlines()
        if content_lines and PATH_LINE_RE.match(content_lines[0].strip()):
            content_to_append = "\n".join(content_lines[1:])
        else:
            content_to_append = "\n".join(content_lines)
        
        with target_path.open("a", encoding="utf-8") as f:
            f.write("\n" + content_to_append.strip() + "\n")
        status = "➕  Дополнено"
    else:
        target_path.write_text(code, encoding="utf-8")
        status = "🔄  Перезаписан" if was_overwritten else "📝  Сохранен"

    new_size = target_path.stat().st_size
    
    significant_reduction = False
    if was_overwritten and not is_journal_file and old_size > 0 and (old_size - new_size) / old_size > 0.1:
        significant_reduction = True

    size_info = f"(старый: {format_size(old_size)}, новый: {format_size(new_size)})" if was_overwritten else f"({format_size(new_size)})"
    status_message = f"{status}: {target_path.relative_to(project_root if project_root else script_path.parent)} {size_info}"

    if significant_reduction:
        print(f"{RED}⚠️  {status_message} - ЗНАЧИТЕЛЬНОЕ УМЕНЬШЕНИЕ РАЗМЕРА!{RESET}")
    else:
        print(status_message)

def rollback_changes(changed_files: List[Tuple[Path, Path | None]], script_path: Path):
    """Откатывает изменения, восстанавливая файлы из резервных копий."""
    print(f"\n{YELLOW}--- НАЧАЛО ОПЕРАЦИИ ОТКАТА ---{RESET}")
    backup_dir = script_path.parent / "BkUp"
    for target_path, project_root in changed_files:
        base_path = project_root if project_root else script_path.parent
        try:
            relative_backup_path = target_path.relative_to(base_path)
            backup_path = backup_dir / relative_backup_path
            if backup_path.exists():
                shutil.copy2(backup_path, target_path)
                print(f"  ✅ Восстановлен: {target_path.relative_to(base_path)}")
            elif target_path.exists():
                target_path.unlink()
                print(f"  ✅ Удален новый файл: {target_path.relative_to(base_path)}")
        except Exception as e:
            print(f"  {RED}❌ Ошибка отката для {target_path}: {e}{RESET}")
    print(f"{GREEN}--- ОПЕРАЦИЯ ОТКАТА ЗАВЕРШЕНА ---{RESET}")

def split_files(input_file: Path) -> None:
    """Основная функция режима 'split'."""
    try:
        raw_text = "\n" + input_file.read_text(encoding="utf-8").strip() + "\n"
    except FileNotFoundError:
        print(f"❌  Ошибка: Файл не найден по пути '{input_file}'")
        sys.exit(1)
    except Exception as e:
        print(f"❌  Ошибка при чтении файла: {e}")
        sys.exit(1)

    script_path = Path(sys.argv[0]).resolve()
    modified_files: List[Tuple[Path, Path | None]] = []
    saved_count, noname_count, last_pos, found_blocks = 0, 1, 0, 0

    for match in CODE_BLOCK_RE.finditer(raw_text):
        found_blocks += 1
        lang, block_content = match.groups()
        block_content = block_content.strip()
        rel_path, code_to_save, project_root = None, None, None
        
        internal_result = split_path_and_code(block_content)
        if internal_result:
            rel_path, code_to_save = internal_result
        else:
            path_from_preceding = find_path_in_preceding_text(raw_text[last_pos:match.start()])
            if path_from_preceding:
                rel_path = path_from_preceding
                code_to_save = f"# {rel_path.as_posix()}\n{block_content}\n"
        
        if rel_path:
            project_name = rel_path.parts[0]
            project_root = find_project_root(script_path, project_name)
            final_path = (project_root / rel_path.relative_to(project_name)) if project_root else (script_path.parent / rel_path)
        else:
            extension = lang if lang else 'txt'
            final_path = script_path.parent / f"noname_{noname_count:02d}.{extension}"
            code_to_save = block_content + "\n"
            noname_count += 1
        
        save_code(final_path, code_to_save, script_path, project_root)
        modified_files.append((final_path, project_root))
        saved_count += 1
        last_pos = match.end()

    if not found_blocks:
        print("❌  Не найдено ни одного блока кода ```…```, который начинается и заканчивается на новой строке.")
        return
    print(f"\n{GREEN}✅  Готово! Обработано файлов: {saved_count}{RESET}")
    if modified_files:
        print(f"\n{YELLOW}--------------------------------------------------{RESET}")
        try:
            answer = input(f"Хотите отменить сделанные изменения? [y/N]: ").lower().strip()
            if answer == 'y':
                rollback_changes(modified_files, script_path)
            else:
                print(f"{GREEN}Изменения подтверждены. Операция завершена.{RESET}")
        except KeyboardInterrupt:
            print(f"\n{YELLOW}Операция прервана. Изменения сохранены.{RESET}")

# =============================================================================
# ТОЧКА ВХОДА
# =============================================================================
if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Использование:")
        print("  Режим разбора: python split_ai_code.py <файл_вывода_AI.txt>")
        print("  Режим сборки:  python split_ai_code.py gather")
        sys.exit(1)
    
    # ИСПРАВЛЕНО: Берем второй элемент (индекс 1), а не весь список.
    command = sys.argv[1]
    
    if command.lower() == "gather":
        gather_files()
    else:
        input_path = Path(command)
        split_files(input_path)