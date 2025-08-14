# NVC_bot/bot/database.py
# version: 2.5.2
# 2025-08-14T15:00:00Z
"""
Модуль для асинхронной работы с базой данных SQLite.

Version 2.5.2:
- FIX: `get_usage_statistics` теперь использует параметризованные запросы
       с объектами datetime, отформатированными в строки ISO, что
       окончательно решает проблему с некорректной фильтрацией по датам.

Version 2.5.1:
- FIX: Исправлен SQL-запрос в `get_usage_statistics` для корректной
       фильтрации по датам.
"""
import logging
import json
from typing import Any, Dict, List, Optional, Type, TypeVar
from collections import defaultdict
import datetime

import aiosqlite

from .config import DATA_DIR, settings, _load_prompt

logger = logging.getLogger(__name__)
T = TypeVar('T')

class Database:
    """
    Класс для управления базой данных SQLite.
    """

    def __init__(self):
        self.db_path = DATA_DIR / "bot_database.sqlite3"
        self.conn: Optional[aiosqlite.Connection] = None
        logger.info("Объект Database создан. Путь к БД: %s", self.db_path)

    async def initialize(self):
        try:
            self.conn = await aiosqlite.connect(self.db_path)
            self.conn.row_factory = aiosqlite.Row
            await self._create_tables()
            logger.info("Подключение к базе данных установлено и таблицы проверены.")
        except aiosqlite.Error as e:
            logger.critical("КРИТИЧЕСКАЯ ОШИБКА при инициализации БД: %s", e, exc_info=True)
            raise

    async def _create_tables(self):
        if not self.conn: raise RuntimeError("Подключение к БД не инициализировано.")
        async with self.conn.cursor() as cursor:
            await cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    user_name TEXT NOT NULL,
                    text TEXT,
                    is_bot BOOLEAN NOT NULL,
                    reply_to_message_id INTEGER,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await cursor.execute("CREATE TABLE IF NOT EXISTS statistics (key TEXT PRIMARY KEY, value INTEGER NOT NULL)")
            await cursor.execute("CREATE TABLE IF NOT EXISTS user_warnings (user_id INTEGER PRIMARY KEY, count INTEGER NOT NULL DEFAULT 0)")
            await cursor.execute("CREATE TABLE IF NOT EXISTS moderation_triggers (id INTEGER PRIMARY KEY AUTOINCREMENT, trigger_word TEXT NOT NULL UNIQUE, category TEXT NOT NULL DEFAULT 'general')")
            await cursor.execute("CREATE TABLE IF NOT EXISTS moderation_exceptions (id INTEGER PRIMARY KEY AUTOINCREMENT, exception_phrase TEXT NOT NULL UNIQUE, category TEXT NOT NULL DEFAULT 'general')")
            
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS api_usage_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    model_id TEXT NOT NULL,
                    request_type TEXT NOT NULL,
                    prompt_tokens INTEGER NOT NULL DEFAULT 0,
                    completion_tokens INTEGER NOT NULL DEFAULT 0,
                    total_tokens INTEGER NOT NULL DEFAULT 0
                )
            """)

            await cursor.execute("PRAGMA table_info(messages)")
            columns = [row['name'] for row in await cursor.fetchall()]
            if 'message_id' not in columns:
                await cursor.execute("ALTER TABLE messages ADD COLUMN message_id INTEGER NOT NULL DEFAULT 0")
            if 'user_id' not in columns:
                await cursor.execute("ALTER TABLE messages ADD COLUMN user_id INTEGER NOT NULL DEFAULT 0")
            if 'reply_to_message_id' not in columns:
                await cursor.execute("ALTER TABLE messages ADD COLUMN reply_to_message_id INTEGER")

            await cursor.execute("PRAGMA table_info(moderation_triggers)")
            if 'category' not in [row['name'] for row in await cursor.fetchall()]:
                await cursor.execute("ALTER TABLE moderation_triggers ADD COLUMN category TEXT NOT NULL DEFAULT 'general'")
            
            await cursor.execute("PRAGMA table_info(moderation_exceptions)")
            if 'category' not in [row['name'] for row in await cursor.fetchall()]:
                await cursor.execute("ALTER TABLE moderation_exceptions ADD COLUMN category TEXT NOT NULL DEFAULT 'general'")

        await self.conn.commit()

    async def populate_defaults(self):
        if not self.conn: return
        async with self.conn.execute("SELECT COUNT(*) FROM moderation_triggers") as cursor:
            if (await cursor.fetchone())[0] == 0:
                logger.info("Таблица триггеров пуста. Заполняю...")
                await self.reset_triggers()
        async with self.conn.execute("SELECT COUNT(*) FROM moderation_exceptions") as cursor:
            if (await cursor.fetchone())[0] == 0:
                logger.info("Таблица исключений пуста. Заполняю...")
                await self.reset_exceptions()

    async def get_all_triggers(self) -> Dict[str, List[str]]:
        if not self.conn: return {}
        triggers = defaultdict(list)
        try:
            async with self.conn.execute("SELECT trigger_word, category FROM moderation_triggers ORDER BY category, id") as cursor:
                async for row in cursor:
                    triggers[row['category']].append(row['trigger_word'])
        except aiosqlite.Error as e: logger.error("Ошибка БД при получении триггеров: %s", e)
        return dict(triggers)

    async def get_all_triggers_flat(self) -> List[str]:
        if not self.conn: return []
        try:
            async with self.conn.execute("SELECT trigger_word FROM moderation_triggers") as cursor:
                return [row['trigger_word'] for row in await cursor.fetchall()]
        except aiosqlite.Error as e:
            logger.error("Ошибка БД при получении плоского списка триггеров: %s", e)
            return []

    async def add_trigger(self, trigger: str, category: str = 'general') -> bool:
        if not self.conn: return False
        try:
            await self.conn.execute("INSERT OR IGNORE INTO moderation_triggers (trigger_word, category) VALUES (?, ?)", (trigger.lower(), category.lower()))
            await self.conn.commit()
            return self.conn.total_changes > 0
        except aiosqlite.Error as e:
            logger.error("Ошибка БД при добавлении триггера '%s': %s", trigger, e)
            return False

    async def delete_trigger(self, trigger: str) -> bool:
        if not self.conn: return False
        try:
            await self.conn.execute("DELETE FROM moderation_triggers WHERE trigger_word = ?", (trigger.lower(),))
            await self.conn.commit()
            return self.conn.total_changes > 0
        except aiosqlite.Error as e:
            logger.error("Ошибка БД при удалении триггера '%s': %s", trigger, e)
            return False

    async def reset_triggers(self):
        if not self.conn: return
        try:
            async with self.conn.cursor() as cursor:
                await cursor.execute("DELETE FROM moderation_triggers")
                data_to_insert = [(word.lower(), category.lower()) for category, words in settings.DEFAULT_TRIGGERS.items() for word in words]
                await cursor.executemany("INSERT OR IGNORE INTO moderation_triggers (trigger_word, category) VALUES (?, ?)", data_to_insert)
            await self.conn.commit()
            logger.info("Таблица триггеров успешно сброшена к значениям по умолчанию.")
        except aiosqlite.Error as e:
            logger.error("Ошибка БД при сбросе триггеров: %s", e)
            await self.conn.rollback()

    async def get_all_exceptions(self) -> Dict[str, List[str]]:
        if not self.conn: return {}
        exceptions = defaultdict(list)
        try:
            async with self.conn.execute("SELECT exception_phrase, category FROM moderation_exceptions ORDER BY category, id") as cursor:
                async for row in cursor:
                    exceptions[row['category']].append(row['exception_phrase'])
        except aiosqlite.Error as e: logger.error("Ошибка БД при получении исключений: %s", e)
        return dict(exceptions)
    
    async def get_all_exceptions_flat(self) -> List[str]:
        if not self.conn: return []
        try:
            async with self.conn.execute("SELECT exception_phrase FROM moderation_exceptions") as cursor:
                return [row['exception_phrase'] for row in await cursor.fetchall()]
        except aiosqlite.Error as e:
            logger.error("Ошибка БД при получении плоского списка исключений: %s", e)
            return []

    async def add_exception(self, exception: str, category: str = 'general') -> bool:
        if not self.conn: return False
        try:
            await self.conn.execute("INSERT OR IGNORE INTO moderation_exceptions (exception_phrase, category) VALUES (?, ?)", (exception.lower(), category.lower()))
            await self.conn.commit()
            return self.conn.total_changes > 0
        except aiosqlite.Error as e:
            logger.error("Ошибка БД при добавлении исключения '%s': %s", exception, e)
            return False

    async def delete_exception(self, exception: str) -> bool:
        if not self.conn: return False
        try:
            await self.conn.execute("DELETE FROM moderation_exceptions WHERE exception_phrase = ?", (exception.lower(),))
            await self.conn.commit()
            return self.conn.total_changes > 0
        except aiosqlite.Error as e:
            logger.error("Ошибка БД при удалении исключения '%s': %s", exception, e)
            return False

    async def reset_exceptions(self):
        if not self.conn: return
        try:
            async with self.conn.cursor() as cursor:
                await cursor.execute("DELETE FROM moderation_exceptions")
                data_to_insert = [(phrase.lower(), category.lower()) for category, phrases in settings.DEFAULT_EXCEPTIONS.items() for phrase in phrases]
                await cursor.executemany("INSERT OR IGNORE INTO moderation_exceptions (exception_phrase, category) VALUES (?, ?)", data_to_insert)
            await self.conn.commit()
            logger.info("Таблица исключений успешно сброшена к значениям по умолчанию.")
        except aiosqlite.Error as e:
            logger.error("Ошибка БД при сбросе исключений: %s", e)
            await self.conn.rollback()

    async def get_chat_history(self, chat_id: int, limit: int) -> List[Dict[str, Any]]:
        if not self.conn:
            return []
        history = []
        try:
            query = "SELECT message_id, user_name, text, is_bot, reply_to_message_id FROM (SELECT message_id, user_name, text, is_bot, reply_to_message_id, timestamp FROM messages WHERE chat_id = ? ORDER BY timestamp DESC LIMIT ?) ORDER BY timestamp ASC"
            async with self.conn.execute(query, (chat_id, limit)) as cursor:
                async for row in cursor:
                    history.append(dict(row))
            return history
        except aiosqlite.Error as e:
            logger.error("Ошибка БД при получении истории чата %d: %s", chat_id, e)
            return []

    async def _get_setting(self, key: str, default: T, value_type: Type[T] = str) -> T:
        if not self.conn: return default
        try:
            async with self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cursor:
                row = await cursor.fetchone()
                return value_type(row['value']) if row else default
        except (aiosqlite.Error, ValueError, TypeError) as e:
            logger.error("Ошибка БД или приведения типа для настройки '%s': %s", key, e)
            return default

    async def _set_setting(self, key: str, value: Any):
        if not self.conn: return
        try:
            await self.conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
            await self.conn.commit()
        except aiosqlite.Error as e:
            logger.error("Ошибка БД при установке настройки '%s': %s", key, e)
            raise
    
    async def _delete_setting(self, key: str):
        if not self.conn: return
        try:
            await self.conn.execute("DELETE FROM settings WHERE key = ?", (key,))
            await self.conn.commit()
        except aiosqlite.Error as e:
            logger.error("Ошибка БД при удалении настройки '%s': %s", key, e)
            raise

    async def get_context_config(self) -> Dict[str, Any]:
        return {
            "context_messages_limit": await self._get_setting("ctx_msg_limit", settings.CONTEXT_MESSAGES_LIMIT, int),
            "context_judge_limit": await self._get_setting("ctx_judge_limit", settings.CONTEXT_JUDGE_LIMIT, int),
        }

    async def set_context_config_value(self, key: str, value: Any):
        db_key_map = {"context_messages_limit": "ctx_msg_limit", "context_judge_limit": "ctx_judge_limit"}
        if key in db_key_map: await self._set_setting(db_key_map[key], value)
        else: logger.warning("Попытка установить неизвестный параметр контекста: %s", key)

    async def reset_context_config(self):
        for key in ["ctx_msg_limit", "ctx_judge_limit"]: await self._delete_setting(key)
        logger.info("Параметры контекста сброшены.")

    async def get_generation_config(self) -> Dict[str, Any]:
        return {
            "temperature": await self._get_setting("gen_temp", settings.DEFAULT_TEMPERATURE, float),
            "top_p": await self._get_setting("gen_top_p", settings.DEFAULT_TOP_P, float),
            "top_k": await self._get_setting("gen_top_k", settings.DEFAULT_TOP_K, int),
            "max_output_tokens": await self._get_setting("gen_max_tokens", settings.DEFAULT_MAX_OUTPUT_TOKENS, int),
        }

    async def set_generation_config_value(self, key: str, value: Any):
        db_key_map = {"temperature": "gen_temp", "top_p": "gen_top_p", "top_k": "gen_top_k", "max_output_tokens": "gen_max_tokens"}
        if key in db_key_map: await self._set_setting(db_key_map[key], value)
        else: logger.warning("Попытка установить неизвестный параметр генерации: %s", key)

    async def reset_generation_config(self):
        for key in ["gen_temp", "gen_top_p", "gen_top_k", "gen_max_tokens"]: await self._delete_setting(key)
        logger.info("Параметры генерации AI сброшены.")

    async def get_safety_level(self) -> str:
        return await self._get_setting("safety_level", settings.DEFAULT_SAFETY_LEVEL)

    async def set_safety_level(self, level: str):
        await self._set_setting("safety_level", level)

    async def reset_safety_level(self):
        await self._delete_setting("safety_level")

    async def is_debug_mode_enabled(self) -> bool:
        return await self._get_setting("debug_mode_enabled", "false", str) == "true"

    async def toggle_debug_mode(self) -> bool:
        new_state = not await self.is_debug_mode_enabled()
        await self._set_setting("debug_mode_enabled", "true" if new_state else "false")
        return new_state

    async def get_main_model(self) -> str:
        return await self._get_setting("main_model", settings.GEMINI_PRO_MODEL)

    async def set_main_model(self, model_name: str):
        await self._set_setting("main_model", model_name)

    async def reset_main_model(self):
        await self._delete_setting("main_model")

    async def get_prompt(self) -> str:
        return await self._get_setting("system_prompt", _load_prompt("default_system_prompt.txt"))

    async def set_prompt(self, prompt: str):
        await self._set_setting("system_prompt", prompt)

    async def reset_prompt(self):
        await self._set_setting("system_prompt", _load_prompt("default_system_prompt.txt"))

    async def get_moderation_prompt(self) -> str:
        return await self._get_setting("moderation_prompt", _load_prompt("default_moderation_prompt.txt"))

    async def set_moderation_prompt(self, prompt: str):
        await self._set_setting("moderation_prompt", prompt)

    async def reset_moderation_prompt(self):
        await self._set_setting("moderation_prompt", _load_prompt("default_moderation_prompt.txt"))

    async def get_moderation_task_template(self) -> str:
        return await self._get_setting("moderation_task_template", _load_prompt("default_moderation_task_template.txt"))

    async def set_moderation_task_template(self, template: str):
        await self._set_setting("moderation_task_template", template)

    async def reset_moderation_task_template(self):
        await self._set_setting("moderation_task_template", _load_prompt("default_moderation_task_template.txt"))

    async def get_moderation_model(self) -> str:
        return await self._get_setting("moderation_model", settings.DEFAULT_MODERATION_MODEL)

    async def set_moderation_model(self, model_name: str):
        await self._set_setting("moderation_model", model_name)

    async def is_moderation_enabled(self) -> bool:
        return await self._get_setting("moderation_enabled", "true", str) == "true"

    async def toggle_moderation(self) -> bool:
        new_state = not await self.is_moderation_enabled()
        await self._set_setting("moderation_enabled", "true" if new_state else "false")
        return new_state

    async def is_welcome_enabled(self) -> bool:
        return await self._get_setting("welcome_enabled", "true", str) == "true"

    async def toggle_welcome(self) -> bool:
        new_state = not await self.is_welcome_enabled()
        await self._set_setting("welcome_enabled", "true" if new_state else "false")
        return new_state

    async def get_welcome_model(self) -> str:
        return await self._get_setting("welcome_model", settings.DEFAULT_WELCOME_MODEL)

    async def set_welcome_model(self, model_name: str):
        await self._set_setting("welcome_model", model_name)

    async def get_welcome_prompt(self) -> str:
        return await self._get_setting("welcome_prompt", _load_prompt("default_welcome_prompt.txt"))

    async def set_welcome_prompt(self, prompt: str):
        await self._set_setting("welcome_prompt", prompt)

    async def reset_welcome_prompt(self):
        await self._set_setting("welcome_prompt", _load_prompt("default_welcome_prompt.txt"))

    async def get_sanction_rules(self) -> List[Dict]:
        try:
            rules_json = await self._get_setting("sanction_rules", None, str)
            return json.loads(rules_json) if rules_json else settings.DEFAULT_SANCTION_RULES
        except (json.JSONDecodeError, TypeError) as e:
            logger.error("Ошибка декодирования правил санкций: %s. Возвращены правила по умолчанию.", e)
            return settings.DEFAULT_SANCTION_RULES

    async def set_sanction_rules(self, rules: List[Dict]):
        await self._set_setting("sanction_rules", json.dumps(rules))

    async def add_message(self, chat_id: int, message_id: int, user_id: int, user_name: str, text: Optional[str], is_bot: bool, reply_to_message_id: Optional[int] = None):
        if not self.conn: return
        try:
            await self.conn.execute(
                "INSERT INTO messages (chat_id, message_id, user_id, user_name, text, is_bot, reply_to_message_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (chat_id, message_id, user_id, user_name, text, is_bot, reply_to_message_id)
            )
            await self.conn.commit()
        except aiosqlite.Error as e:
            logger.error("Ошибка БД при добавлении сообщения: %s", e)
            raise

    async def _get_stat(self, key: str) -> int:
        if not self.conn: return 0
        try:
            async with self.conn.execute("SELECT value FROM statistics WHERE key = ?", (key,)) as cursor:
                row = await cursor.fetchone()
                return int(row['value']) if row else 0
        except aiosqlite.Error as e:
            logger.error("Ошибка БД при получении статистики '%s': %s", key, e)
            return 0

    async def _set_stat(self, key: str, value: int):
        if not self.conn: return
        try:
            await self.conn.execute("INSERT OR REPLACE INTO statistics (key, value) VALUES (?, ?)", (key, value))
            await self.conn.commit()
        except aiosqlite.Error as e:
            logger.error("Ошибка БД при установке статистики '%s': %s", key, e)
            raise

    async def increment_ai_responses(self):
        await self._set_stat("ai_responses", await self._get_stat("ai_responses") + 1)

    async def increment_moderation_actions(self):
        await self._set_stat("moderation_actions", await self._get_stat("moderation_actions") + 1)

    async def get_statistics(self) -> Dict[str, Any]:
        if not self.conn: return {}
        try:
            async with self.conn.execute("SELECT COUNT(*) FROM messages") as t, \
                       self.conn.execute("SELECT COUNT(DISTINCT chat_id) FROM messages") as a, \
                       self.conn.execute("SELECT COUNT(*) FROM user_warnings WHERE count > 0") as u:
                return {
                    "total_messages": (await t.fetchone())[0], "active_chats": (await a.fetchone())[0],
                    "users_with_warnings": (await u.fetchone())[0], "ai_responses": await self._get_stat("ai_responses"),
                    "moderation_actions": await self._get_stat("moderation_actions"),
                }
        except aiosqlite.Error as e:
            logger.error("Ошибка БД при сборе общей статистики: %s", e)
            return {}

    async def log_api_usage(self, model_id: str, request_type: str, usage_metadata: Dict[str, Any]):
        """Записывает информацию об использовании API в базу данных."""
        if not self.conn or not usage_metadata:
            return
        query = """
            INSERT INTO api_usage_log (model_id, request_type, prompt_tokens, completion_tokens, total_tokens)
            VALUES (?, ?, ?, ?, ?)
        """
        try:
            await self.conn.execute(query, (
                model_id,
                request_type,
                usage_metadata.get("prompt_token_count", 0),
                usage_metadata.get("candidates_token_count", 0),
                usage_metadata.get("total_token_count", 0),
            ))
            await self.conn.commit()
        except aiosqlite.Error as e:
            logger.error("Ошибка БД при записи лога использования API: %s", e)

    async def get_usage_statistics(self) -> Dict[str, Any]:
        """Собирает и агрегирует статистику использования API по разным периодам."""
        if not self.conn:
            return {}

        stats: Dict[str, Any] = {
            'today': defaultdict(lambda: defaultdict(int)),
            'yesterday': defaultdict(lambda: defaultdict(int)),
            'week': defaultdict(lambda: defaultdict(int)),
            'month': defaultdict(lambda: defaultdict(int)),
        }
        
        today_utc = datetime.datetime.now(datetime.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        
        periods = {
            'today': (today_utc, today_utc + datetime.timedelta(days=1)),
            'yesterday': (today_utc - datetime.timedelta(days=1), today_utc),
            'week': (today_utc - datetime.timedelta(days=today_utc.weekday()), today_utc + datetime.timedelta(days=1)),
            'month': (today_utc.replace(day=1), today_utc + datetime.timedelta(days=1)),
        }
        
        try:
            for period_name, (start_dt, end_dt) in periods.items():
                query = """
                    SELECT
                        model_id,
                        COUNT(*) as request_count,
                        SUM(total_tokens) as total_tokens
                    FROM api_usage_log
                    WHERE timestamp >= ? AND timestamp < ?
                    GROUP BY model_id
                """
                # Конвертируем datetime в строки формата, который точно понимает SQLite
                start_str = start_dt.strftime('%Y-%m-%d %H:%M:%S')
                end_str = end_dt.strftime('%Y-%m-%d %H:%M:%S')

                async with self.conn.execute(query, (start_str, end_str)) as cursor:
                    async for row in cursor:
                        stats[period_name][row['model_id']]['requests'] = row['request_count']
                        stats[period_name][row['model_id']]['tokens'] = row['total_tokens']
        except aiosqlite.Error as e:
            logger.error("Ошибка БД при сборе статистики использования API: %s", e)

        return stats

    async def get_warnings(self, user_id: int) -> int:
        if not self.conn: return 0
        try:
            async with self.conn.execute("SELECT count FROM user_warnings WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                return row['count'] if row else 0
        except aiosqlite.Error as e:
            logger.error("Ошибка БД при получении предупреждений для user_id %d: %s", user_id, e)
            return 0

    async def set_warnings(self, user_id: int, count: int):
        if not self.conn: return
        try:
            await self.conn.execute("INSERT OR REPLACE INTO user_warnings (user_id, count) VALUES (?, ?)", (user_id, count))
            await self.conn.commit()
        except aiosqlite.Error as e:
            logger.error("Ошибка БД при установке предупреждений для user_id %d: %s", user_id, e)
            raise

    async def adjust_warnings(self, user_id: int, amount: int) -> int:
        new_count = max(0, await self.get_warnings(user_id) + amount)
        await self.set_warnings(user_id, new_count)
        return new_count

    async def reset_warnings(self, user_id: int):
        await self.set_warnings(user_id, 0)

    async def get_all_users_with_warnings(self) -> List[Dict]:
        if not self.conn: return []
        try:
            async with self.conn.execute("SELECT user_id, count FROM user_warnings WHERE count > 0 ORDER BY count DESC") as cursor:
                return [dict(row) for row in await cursor.fetchall()]
        except aiosqlite.Error as e:
            logger.error("Ошибка БД при получении списка пользователей с предупреждениями: %s", e)
            return []
