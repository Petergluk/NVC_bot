# NVC_bot/bot/database.py
# version: 3.0.0
# 2026-10-30T16:30:00Z

'''
Модуль для асинхронной работы с базой данных SQLite.

Version 3.0.0:
- ADD: Поддержка мягкого режима пре-модерации (`is_soft_moderation_enabled`, `toggle_soft_moderation`).
- ADD: Система апелляций (`appeals` таблица: `create_appeal`, `get_appeal`, `update_appeal_status`).
- ADD: Автоамнистия предупреждений (`last_warning_at` в `user_warnings`, `is_auto_amnesty_enabled`,
       `get_auto_amnesty_days`, `apply_auto_amnesty`).
- ADD: Настройка проактивного фасилитатора споров (`is_proactive_facilitator_enabled`).
'''

import logging
import json
from typing import Any, Dict, List, Optional, Type, TypeVar
from collections import defaultdict

import aiosqlite
from .config import DATA_DIR, settings

logger = logging.getLogger(__name__)
T = TypeVar('T')


class Database:
    '''
    Класс для управления базой данных SQLite.
    '''
    def __init__(self):
        self.db_path = DATA_DIR / "bot_database.sqlite3"
        self.conn: Optional[aiosqlite.Connection] = None
        logger.info("Объект Database создан. Путь к БД: %s", self.db_path)

    async def initialize(self):
        try:
            if str(self.db_path) != ":memory:":
                Path_obj = self.db_path.parent
                Path_obj.mkdir(parents=True, exist_ok=True)
            self.conn = await aiosqlite.connect(self.db_path)
            self.conn.row_factory = aiosqlite.Row
            await self._create_tables()
            logger.info("Подключение к базе данных установлено и таблицы проверены.")
        except aiosqlite.Error as e:
            logger.critical("КРИТИЧЕСКАЯ ОШИБКА при инициализации БД: %s", e, exc_info=True)
            raise

    async def close(self):
        '''Корректно закрывает соединение с базой данных.'''
        if self.conn:
            await self.conn.close()
            self.conn = None
            logger.info("Соединение с базой данных закрыто.")

    async def _create_tables(self):
        if not self.conn:
            raise RuntimeError("Подключение к БД не инициализировано.")
        async with self.conn.cursor() as cursor:
            await cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            await cursor.execute(
                "CREATE TABLE IF NOT EXISTS messages ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "chat_id INTEGER NOT NULL, "
                "user_name TEXT NOT NULL, "
                "text TEXT NOT NULL, "
                "is_bot BOOLEAN NOT NULL, "
                "timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)"
            )
            await cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_chat_time ON messages(chat_id, timestamp DESC)")
            await cursor.execute("CREATE TABLE IF NOT EXISTS statistics (key TEXT PRIMARY KEY, value INTEGER NOT NULL)")
            await cursor.execute(
                "CREATE TABLE IF NOT EXISTS user_warnings ("
                "user_id INTEGER PRIMARY KEY, "
                "count INTEGER NOT NULL DEFAULT 0, "
                "last_warning_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
            )
            await cursor.execute(
                "CREATE TABLE IF NOT EXISTS appeals ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "chat_id INTEGER NOT NULL, "
                "user_id INTEGER NOT NULL, "
                "user_name TEXT NOT NULL, "
                "original_text TEXT NOT NULL, "
                "suggested_nvc TEXT NOT NULL DEFAULT '', "
                "rule_violated TEXT NOT NULL DEFAULT '', "
                "status TEXT NOT NULL DEFAULT 'pending', "
                "created_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
            )
            await cursor.execute("CREATE TABLE IF NOT EXISTS moderation_triggers (id INTEGER PRIMARY KEY AUTOINCREMENT, trigger_word TEXT NOT NULL UNIQUE, category TEXT NOT NULL DEFAULT 'general')")
            await cursor.execute("CREATE TABLE IF NOT EXISTS moderation_exceptions (id INTEGER PRIMARY KEY AUTOINCREMENT, exception_phrase TEXT NOT NULL UNIQUE, category TEXT NOT NULL DEFAULT 'general')")

            # Миграции для существующих БД
            await cursor.execute("PRAGMA table_info(moderation_triggers)")
            if 'category' not in [row['name'] for row in await cursor.fetchall()]:
                await cursor.execute("ALTER TABLE moderation_triggers ADD COLUMN category TEXT NOT NULL DEFAULT 'general'")

            await cursor.execute("PRAGMA table_info(moderation_exceptions)")
            if 'category' not in [row['name'] for row in await cursor.fetchall()]:
                await cursor.execute("ALTER TABLE moderation_exceptions ADD COLUMN category TEXT NOT NULL DEFAULT 'general'")

            await cursor.execute("PRAGMA table_info(user_warnings)")
            if 'last_warning_at' not in [row['name'] for row in await cursor.fetchall()]:
                await cursor.execute("ALTER TABLE user_warnings ADD COLUMN last_warning_at DATETIME DEFAULT CURRENT_TIMESTAMP")

        await self.conn.commit()

    async def populate_defaults(self):
        if not self.conn:
            return
        async with self.conn.execute("SELECT COUNT(*) FROM moderation_triggers") as cursor:
            if (await cursor.fetchone())[0] == 0:
                logger.info("Таблица триггеров пуста. Заполняю...")
                await self.reset_triggers()
        async with self.conn.execute("SELECT COUNT(*) FROM moderation_exceptions") as cursor:
            if (await cursor.fetchone())[0] == 0:
                logger.info("Таблица исключений пуста. Заполняю...")
                await self.reset_exceptions()

    async def get_all_triggers(self) -> Dict[str, List[str]]:
        if not self.conn:
            return {}
        triggers = defaultdict(list)
        try:
            async with self.conn.execute("SELECT trigger_word, category FROM moderation_triggers ORDER BY category, id") as cursor:
                async for row in cursor:
                    triggers[row['category']].append(row['trigger_word'])
        except aiosqlite.Error as e:
            logger.error("Ошибка БД при получении триггеров: %s", e)
        return dict(triggers)

    async def get_all_triggers_flat(self) -> List[str]:
        if not self.conn:
            return []
        try:
            async with self.conn.execute("SELECT trigger_word FROM moderation_triggers") as cursor:
                return [row['trigger_word'] for row in await cursor.fetchall()]
        except aiosqlite.Error as e:
            logger.error("Ошибка БД при получении плоского списка триггеров: %s", e)
            return []

    async def add_trigger(self, trigger: str, category: str = 'general') -> bool:
        if not self.conn:
            return False
        try:
            await self.conn.execute("INSERT INTO moderation_triggers (trigger_word, category) VALUES (?, ?)", (trigger.lower().strip(), category))
            await self.conn.commit()
            return True
        except aiosqlite.IntegrityError:
            return False
        except aiosqlite.Error as e:
            logger.error("Ошибка БД при добавлении триггера '%s': %s", trigger, e)
            return False

    async def delete_trigger(self, trigger: str) -> bool:
        if not self.conn:
            return False
        try:
            cursor = await self.conn.execute("DELETE FROM moderation_triggers WHERE trigger_word = ?", (trigger.lower().strip(),))
            await self.conn.commit()
            return cursor.rowcount > 0
        except aiosqlite.Error as e:
            logger.error("Ошибка БД при удалении триггера '%s': %s", trigger, e)
            return False

    async def reset_triggers(self):
        if not self.conn:
            return
        try:
            async with self.conn.cursor() as cursor:
                await cursor.execute("DELETE FROM moderation_triggers")
                to_insert = [(w.lower().strip(), cat) for cat, words in settings.DEFAULT_TRIGGERS.items() for w in words]
                await cursor.executemany("INSERT OR IGNORE INTO moderation_triggers (trigger_word, category) VALUES (?, ?)", to_insert)
            await self.conn.commit()
        except aiosqlite.Error as e:
            logger.error("Ошибка БД при сбросе триггеров: %s", e)

    async def get_all_exceptions(self) -> Dict[str, List[str]]:
        if not self.conn:
            return {}
        exceptions = defaultdict(list)
        try:
            async with self.conn.execute("SELECT exception_phrase, category FROM moderation_exceptions ORDER BY category, id") as cursor:
                async for row in cursor:
                    exceptions[row['category']].append(row['exception_phrase'])
        except aiosqlite.Error as e:
            logger.error("Ошибка БД при получении исключений: %s", e)
        return dict(exceptions)

    async def get_all_exceptions_flat(self) -> List[str]:
        if not self.conn:
            return []
        try:
            async with self.conn.execute("SELECT exception_phrase FROM moderation_exceptions") as cursor:
                return [row['exception_phrase'] for row in await cursor.fetchall()]
        except aiosqlite.Error as e:
            logger.error("Ошибка БД при получении плоского списка исключений: %s", e)
            return []

    async def add_exception(self, phrase: str, category: str = 'general') -> bool:
        if not self.conn:
            return False
        try:
            await self.conn.execute("INSERT INTO moderation_exceptions (exception_phrase, category) VALUES (?, ?)", (phrase.lower().strip(), category))
            await self.conn.commit()
            return True
        except aiosqlite.IntegrityError:
            return False
        except aiosqlite.Error as e:
            logger.error("Ошибка БД при добавлении исключения '%s': %s", phrase, e)
            return False

    async def delete_exception(self, phrase: str) -> bool:
        if not self.conn:
            return False
        try:
            cursor = await self.conn.execute("DELETE FROM moderation_exceptions WHERE exception_phrase = ?", (phrase.lower().strip(),))
            await self.conn.commit()
            return cursor.rowcount > 0
        except aiosqlite.Error as e:
            logger.error("Ошибка БД при удалении исключения '%s': %s", phrase, e)
            return False

    async def reset_exceptions(self):
        if not self.conn:
            return
        try:
            async with self.conn.cursor() as cursor:
                await cursor.execute("DELETE FROM moderation_exceptions")
                to_insert = [(p.lower().strip(), cat) for cat, phrases in settings.DEFAULT_EXCEPTIONS.items() for p in phrases]
                await cursor.executemany("INSERT OR IGNORE INTO moderation_exceptions (exception_phrase, category) VALUES (?, ?)", to_insert)
            await self.conn.commit()
        except aiosqlite.Error as e:
            logger.error("Ошибка БД при сбросе исключений: %s", e)

    async def _get_setting(self, key: str, default: T, type_caster: Type[T] = str) -> T:
        if not self.conn:
            return default
        try:
            async with self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cursor:
                row = await cursor.fetchone()
                return type_caster(row['value']) if row else default
        except (aiosqlite.Error, ValueError, TypeError) as e:
            logger.error("Ошибка получения настройки '%s': %s. Возвращено значение по умолчанию.", key, e)
            return default

    async def _set_setting(self, key: str, value: Any):
        if not self.conn:
            return
        try:
            await self.conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
            await self.conn.commit()
        except aiosqlite.Error as e:
            logger.error("Ошибка БД при сохранении настройки '%s': %s", key, e)
            raise

    async def get_facilitator_model(self) -> str:
        return await self._get_setting("facilitator_model", settings.GEMINI_FLASH_MODEL, str)

    async def set_facilitator_model(self, model_name: str):
        await self._set_setting("facilitator_model", model_name)

    async def get_chat_history(self, chat_id: int, limit: int) -> List[Dict[str, Any]]:
        if not self.conn or limit <= 0:
            return []
        history = []
        try:
            sql = "SELECT user_name, text, is_bot FROM messages WHERE chat_id = ? ORDER BY timestamp DESC, id DESC LIMIT ?"
            async with self.conn.execute(sql, (chat_id, limit)) as cursor:
                rows = await cursor.fetchall()
                for row in reversed(rows):
                    role = "model" if row["is_bot"] else "user"
                    text = row["text"] if row["is_bot"] else f"{row['user_name']}: {row['text']}"
                    history.append({
                        "role": role,
                        "parts": [{"text": text}]
                    })
        except aiosqlite.Error as e:
            logger.error("Ошибка БД при получении истории чата %d: %s", chat_id, e)
        return history

    async def get_context_config(self) -> Dict[str, int]:
        defaults = settings.DEFAULT_CONTEXT_CONFIG
        return {
            "context_messages_limit": await self._get_setting("context_messages_limit", defaults["context_messages_limit"], int),
            "context_judge_limit": await self._get_setting("context_judge_limit", defaults["context_judge_limit"], int),
        }

    async def set_context_value(self, param: str, value: int):
        if param in settings.DEFAULT_CONTEXT_CONFIG:
            await self._set_setting(param, value)

    async def reset_context_config(self):
        for key, value in settings.DEFAULT_CONTEXT_CONFIG.items():
            await self._set_setting(key, value)

    async def get_generation_config(self) -> Dict[str, float | int]:
        defaults = settings.DEFAULT_GENERATION_CONFIG
        return {
            "temperature": await self._get_setting("temperature", defaults["temperature"], float),
            "top_p": await self._get_setting("top_p", defaults["top_p"], float),
            "top_k": await self._get_setting("top_k", defaults["top_k"], int),
            "max_output_tokens": await self._get_setting("max_output_tokens", defaults["max_output_tokens"], int),
        }

    async def set_generation_value(self, param: str, value: float | int):
        if param in settings.DEFAULT_GENERATION_CONFIG:
            await self._set_setting(param, value)

    async def reset_generation_config(self):
        for key, value in settings.DEFAULT_GENERATION_CONFIG.items():
            await self._set_setting(key, value)

    async def is_debug_mode_enabled(self) -> bool:
        return await self._get_setting("debug_mode_enabled", "false", str) == "true"

    async def toggle_debug_mode(self) -> bool:
        new_state = not await self.is_debug_mode_enabled()
        await self._set_setting("debug_mode_enabled", "true" if new_state else "false")
        return new_state

    async def is_proactive_facilitator_enabled(self) -> bool:
        default_str = "true" if settings.DEFAULT_PROACTIVE_FACILITATOR_ENABLED else "false"
        return await self._get_setting("proactive_facilitator_enabled", default_str, str) == "true"

    async def toggle_proactive_facilitator(self) -> bool:
        new_state = not await self.is_proactive_facilitator_enabled()
        await self._set_setting("proactive_facilitator_enabled", "true" if new_state else "false")
        return new_state

    async def get_prompt(self) -> str:
        return await self._get_setting("system_prompt", settings.DEFAULT_SYSTEM_PROMPT)

    async def set_prompt(self, prompt: str):
        await self._set_setting("system_prompt", prompt)

    async def reset_prompt(self):
        await self._set_setting("system_prompt", settings.DEFAULT_SYSTEM_PROMPT)

    async def get_moderation_prompt(self) -> str:
        return await self._get_setting("moderation_prompt", settings.DEFAULT_MODERATION_PROMPT)

    async def set_moderation_prompt(self, prompt: str):
        await self._set_setting("moderation_prompt", prompt)

    async def reset_moderation_prompt(self):
        await self._set_setting("moderation_prompt", settings.DEFAULT_MODERATION_PROMPT)

    async def get_moderation_task_template(self) -> str:
        return await self._get_setting("moderation_task_template", settings.DEFAULT_MODERATION_TASK_TEMPLATE)

    async def set_moderation_task_template(self, template: str):
        await self._set_setting("moderation_task_template", template)

    async def reset_moderation_task_template(self):
        await self._set_setting("moderation_task_template", settings.DEFAULT_MODERATION_TASK_TEMPLATE)

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

    async def is_soft_moderation_enabled(self) -> bool:
        default_str = "true" if settings.DEFAULT_SOFT_MODERATION_ENABLED else "false"
        return await self._get_setting("soft_moderation_enabled", default_str, str) == "true"

    async def toggle_soft_moderation(self) -> bool:
        new_state = not await self.is_soft_moderation_enabled()
        await self._set_setting("soft_moderation_enabled", "true" if new_state else "false")
        return new_state

    async def is_auto_amnesty_enabled(self) -> bool:
        default_str = "true" if settings.DEFAULT_AUTO_AMNESTY_ENABLED else "false"
        return await self._get_setting("auto_amnesty_enabled", default_str, str) == "true"

    async def toggle_auto_amnesty(self) -> bool:
        new_state = not await self.is_auto_amnesty_enabled()
        await self._set_setting("auto_amnesty_enabled", "true" if new_state else "false")
        return new_state

    async def get_auto_amnesty_days(self) -> int:
        return await self._get_setting("auto_amnesty_days", settings.DEFAULT_AUTO_AMNESTY_DAYS, int)

    async def set_auto_amnesty_days(self, days: int):
        await self._set_setting("auto_amnesty_days", max(1, int(days)))

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
        return await self._get_setting("welcome_prompt", settings.DEFAULT_WELCOME_PROMPT)

    async def set_welcome_prompt(self, prompt: str):
        await self._set_setting("welcome_prompt", prompt)

    async def reset_welcome_prompt(self):
        await self._set_setting("welcome_prompt", settings.DEFAULT_WELCOME_PROMPT)

    async def get_sanction_rules(self) -> List[Dict]:
        try:
            rules_json = await self._get_setting("sanction_rules", None, str)
            return json.loads(rules_json) if rules_json else settings.DEFAULT_SANCTION_RULES
        except (json.JSONDecodeError, TypeError) as e:
            logger.error("Ошибка декодирования правил санкций: %s. Возвращены правила по умолчанию.", e)
            return settings.DEFAULT_SANCTION_RULES

    async def set_sanction_rules(self, rules: List[Dict]):
        await self._set_setting("sanction_rules", json.dumps(rules))

    async def add_message(self, chat_id: int, user_name: str, text: str, is_bot: bool):
        if not self.conn:
            return
        try:
            await self.conn.execute(
                "INSERT INTO messages (chat_id, user_name, text, is_bot) VALUES (?, ?, ?, ?)",
                (chat_id, user_name, text, is_bot)
            )
            await self.conn.commit()
        except aiosqlite.Error as e:
            logger.error("Ошибка БД при добавлении сообщения: %s", e)
            raise

    async def _get_stat(self, key: str) -> int:
        if not self.conn:
            return 0
        try:
            async with self.conn.execute("SELECT value FROM statistics WHERE key = ?", (key,)) as cursor:
                row = await cursor.fetchone()
                return int(row['value']) if row else 0
        except aiosqlite.Error as e:
            logger.error("Ошибка БД при получении статистики '%s': %s", key, e)
            return 0

    async def _set_stat(self, key: str, value: int):
        if not self.conn:
            return
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
        if not self.conn:
            return {}
        try:
            async with self.conn.execute("SELECT COUNT(*) FROM messages") as t, \
                       self.conn.execute("SELECT COUNT(DISTINCT chat_id) FROM messages") as a, \
                       self.conn.execute("SELECT COUNT(*) FROM user_warnings WHERE count > 0") as u:
                return {
                    "total_messages": (await t.fetchone())[0],
                    "active_chats": (await a.fetchone())[0],
                    "users_with_warnings": (await u.fetchone())[0],
                    "ai_responses": await self._get_stat("ai_responses"),
                    "moderation_actions": await self._get_stat("moderation_actions"),
                }
        except aiosqlite.Error as e:
            logger.error("Ошибка БД при сборе общей статистики: %s", e)
            return {}

    async def get_warnings(self, user_id: int) -> int:
        if not self.conn:
            return 0
        try:
            async with self.conn.execute("SELECT count FROM user_warnings WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                return row['count'] if row else 0
        except aiosqlite.Error as e:
            logger.error("Ошибка БД при получении предупреждений для user_id %d: %s", user_id, e)
            return 0

    async def set_warnings(self, user_id: int, count: int):
        if not self.conn:
            return
        try:
            await self.conn.execute(
                "INSERT OR REPLACE INTO user_warnings (user_id, count, last_warning_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                (user_id, count)
            )
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
        if not self.conn:
            return []
        try:
            async with self.conn.execute("SELECT user_id, count, last_warning_at FROM user_warnings WHERE count > 0 ORDER BY count DESC") as cursor:
                return [dict(row) for row in await cursor.fetchall()]
        except aiosqlite.Error as e:
            logger.error("Ошибка БД при получении списка пользователей с предупреждениями: %s", e)
            return []

    async def apply_auto_amnesty(self, days: Optional[int] = None) -> List[Dict[str, Any]]:
        '''
        Списывает 1 предупреждение у пользователей, у которых с момента последнего
        предупреждения прошло не менее `days` дней.
        '''
        if not self.conn or not await self.is_auto_amnesty_enabled():
            return []
        amnesty_days = days if days is not None else await self.get_auto_amnesty_days()
        pardoned: List[Dict[str, Any]] = []
        try:
            sql = (
                "SELECT user_id, count FROM user_warnings "
                "WHERE count > 0 AND last_warning_at <= datetime('now', ?)"
            )
            modifier = f"-{int(amnesty_days)} days"
            async with self.conn.execute(sql, (modifier,)) as cursor:
                rows = await cursor.fetchall()
            for row in rows:
                uid = row["user_id"]
                new_cnt = max(0, row["count"] - 1)
                await self.conn.execute(
                    "UPDATE user_warnings SET count = ?, last_warning_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                    (new_cnt, uid)
                )
                pardoned.append({"user_id": uid, "old_count": row["count"], "new_count": new_cnt})
            if pardoned:
                await self.conn.commit()
        except aiosqlite.Error as e:
            logger.error("Ошибка БД при выполнении автоамнистии: %s", e)
        return pardoned

    # --- Методы для системы апелляций (Оспорить предупреждение) ---
    async def create_appeal(
        self,
        chat_id: int,
        user_id: int,
        user_name: str,
        original_text: str,
        suggested_nvc: str = "",
        rule_violated: str = "Ты-сообщение"
    ) -> int:
        if not self.conn:
            return 0
        try:
            cursor = await self.conn.execute(
                "INSERT INTO appeals (chat_id, user_id, user_name, original_text, suggested_nvc, rule_violated, status) "
                "VALUES (?, ?, ?, ?, ?, ?, 'pending')",
                (chat_id, user_id, user_name, original_text, suggested_nvc, rule_violated)
            )
            await self.conn.commit()
            return int(cursor.lastrowid or 0)
        except aiosqlite.Error as e:
            logger.error("Ошибка БД при создании апелляции: %s", e)
            return 0

    async def get_appeal(self, appeal_id: int) -> Optional[Dict[str, Any]]:
        if not self.conn:
            return None
        try:
            async with self.conn.execute("SELECT * FROM appeals WHERE id = ?", (appeal_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None
        except aiosqlite.Error as e:
            logger.error("Ошибка БД при чтении апелляции %d: %s", appeal_id, e)
            return None

    async def update_appeal_status(self, appeal_id: int, status: str) -> bool:
        if not self.conn:
            return False
        try:
            cursor = await self.conn.execute("UPDATE appeals SET status = ? WHERE id = ?", (status, appeal_id))
            await self.conn.commit()
            return cursor.rowcount > 0
        except aiosqlite.Error as e:
            logger.error("Ошибка БД при обновлении статуса апелляции %d: %s", appeal_id, e)
            return False