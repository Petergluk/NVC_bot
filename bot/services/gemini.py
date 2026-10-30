# NVC_bot/bot/services/gemini.py
# version: 4.0.0
# 2026-10-30T06:30:00Z
"""
Сервис-обертка для взаимодействия с Google Gemini API.

Version 4.0.0:
- UPGRADE: Поддержка современного SDK `google-genai` (с автоматическим фоллбэком
           на `google-generativeai`, если установлен старый пакет).
- FIX: Использование `safe_format_template` для безопасной подстановки
       переменных `{group_rules}` / `{{group_rules}}` и `{text}` / `{{text}}`
       без риска падения `KeyError` на произвольных фигурных скобках.
- ADD: Сохранение и восстановление выбранной модели Фасилитатора из БД.
"""
import logging
import json
from typing import Dict, List, Optional, Tuple, Any

try:
    from google import genai as modern_genai
    from google.genai import types as modern_types
    HAS_MODERN_GENAI = True
except ImportError:
    modern_genai = None
    modern_types = None
    HAS_MODERN_GENAI = False

try:
    import google.generativeai as legacy_genai
    from google.generativeai.types import GenerationConfig as LegacyGenerationConfig
    from google.generativeai import types as legacy_types
    HAS_LEGACY_GENAI = True
except ImportError:
    legacy_genai = None
    LegacyGenerationConfig = None
    legacy_types = None
    HAS_LEGACY_GENAI = False

from ..config import settings
from ..database import Database
from ..utils.formatters import safe_format_template

logger = logging.getLogger(__name__)
ai_logger = logging.getLogger('ai_requests')


class GeminiService:
    """
    Инкапсулирует логику работы с моделями Gemini (поддерживает google-genai и google-generativeai).
    """

    def __init__(self, model_names: Dict[str, str], db: Database, default_model: Optional[str] = None):
        self.db = db
        self.client = None

        if HAS_MODERN_GENAI:
            try:
                self.client = modern_genai.Client(api_key=settings.GEMINI_API_KEY)
                logger.info("Инициализирован современный SDK google-genai.", extra={'trace_id': 'init'})
            except Exception as e:
                logger.warning("Не удалось инициализировать google-genai Client: %s", e, extra={'trace_id': 'init'})

        if not self.client and HAS_LEGACY_GENAI:
            try:
                legacy_genai.configure(api_key=settings.GEMINI_API_KEY)
                logger.info("Ключ Gemini API сконфигурирован (legacy google-generativeai).", extra={'trace_id': 'init'})
            except Exception as e:
                logger.critical("КРИТИЧЕСКАЯ ОШИБКА: Не удалось сконфигурировать Gemini API.", exc_info=e, extra={'trace_id': 'init'})
                raise

        self.model_names = model_names
        self.models: Dict[str, str] = {model_id: model_id for model_id in model_names.values()}
        if not self.models:
            raise RuntimeError("Не удалось инициализировать AI-модели.")

        if default_model and default_model in self.models:
            self.current_model_id = default_model
        else:
            self.current_model_id = model_names.get("flash", next(iter(self.models.keys())))

    async def initialize_from_db(self) -> None:
        """Восстанавливает сохраненную в БД основную модель Фасилитатора."""
        saved_model = await self.db.get_facilitator_model()
        if saved_model in self.models:
            self.current_model_id = saved_model
            logger.info("Основная модель Фасилитатора загружена из БД: %s", saved_model, extra={'trace_id': 'init'})

    def switch_model(self, model_id: str) -> bool:
        if model_id in self.models:
            self.current_model_id = model_id
            logger.info("Активная модель переключена на: %s", model_id, extra={'trace_id': 'config'})
            return True
        logger.warning("Попытка переключиться на несуществующую модель: %s", model_id, extra={'trace_id': 'config'})
        return False

    def get_current_model(self) -> str:
        return self.current_model_id

    def get_available_models(self) -> List[str]:
        return list(self.models.keys())

    def _format_history_for_log(self, history: List[Dict]) -> str:
        """Форматирует историю чата в компактную строку для логов."""
        if not history:
            return "[]"
        return "\n".join([f"  [{item.get('role')}] {item.get('parts', [{}])[0].get('text', '')[:120]}..." for item in history])

    async def generate_response(
        self,
        question: str,
        task_instruction: str,
        trace_id: str,
        chat_history: Optional[List[Dict]] = None,
        user_mention: Optional[str] = None,
        model_override: Optional[str] = None,
        is_debug_mode: bool = False,
        chat_description: Optional[str] = None
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        model_id_to_use = model_override if model_override and model_override in self.models else self.current_model_id

        try:
            core_prompt = await self.db.get_prompt()
            if chat_description:
                core_prompt = safe_format_template(core_prompt, group_rules=chat_description)

            final_system_prompt = core_prompt
            if task_instruction and task_instruction.strip():
                final_system_prompt = f"{core_prompt}\n\n---\n\n{task_instruction}"

            gen_config_dict = await self.db.get_generation_config()
            history = chat_history or []

            if question:
                user_question_text = f"Сообщение от пользователя {user_mention}: {question}" if user_mention else question
            else:
                user_question_text = "Продолжай согласно инструкции."

            thinking_enabled_log_status = "OFF"
            response_text = ""
            full_usage_metadata: Dict[str, Any] = {}
            thoughts_log = ""

            if self.client and HAS_MODERN_GENAI:
                contents = []
                for item in history:
                    role = "model" if item.get("role") == "model" else "user"
                    part_text = item.get("parts", [{}])[0].get("text", "")
                    if part_text:
                        contents.append(modern_types.Content(role=role, parts=[modern_types.Part.from_text(text=part_text)]))
                contents.append(modern_types.Content(role="user", parts=[modern_types.Part.from_text(text=user_question_text)]))

                config_kwargs: Dict[str, Any] = {
                    "system_instruction": final_system_prompt,
                    "temperature": gen_config_dict.get("temperature"),
                    "top_p": gen_config_dict.get("top_p"),
                    "top_k": gen_config_dict.get("top_k"),
                    "max_output_tokens": gen_config_dict.get("max_output_tokens"),
                }
                if is_debug_mode and hasattr(modern_types, "ThinkingConfig"):
                    config_kwargs["thinking_config"] = modern_types.ThinkingConfig(include_thoughts=True)
                    thinking_enabled_log_status = "ON"

                logger.info("Отправка запроса к модели %s (google-genai, Thinking: %s)...", model_id_to_use, thinking_enabled_log_status, extra={'trace_id': trace_id})
                response = await self.client.aio.models.generate_content(
                    model=model_id_to_use,
                    contents=contents,
                    config=modern_types.GenerateContentConfig(**config_kwargs)
                )
                response_text = response.text or ""
                usage_obj = getattr(response, "usage_metadata", None)
            else:
                model = legacy_genai.GenerativeModel(
                    model_name=model_id_to_use,
                    system_instruction=final_system_prompt
                )
                if is_debug_mode:
                    try:
                        gen_config_dict['thinking_config'] = legacy_types.ThinkingConfig(include_thoughts=True)
                        thinking_enabled_log_status = "ON"
                    except AttributeError:
                        logger.warning("`ThinkingConfig` не поддерживается в legacy SDK. Используйте google-genai.", extra={'trace_id': trace_id})
                        thinking_enabled_log_status = "UNSUPPORTED"

                generation_config = LegacyGenerationConfig(**gen_config_dict)
                chat_session = model.start_chat(history=history)
                logger.info("Отправка запроса к модели %s (legacy SDK, Thinking: %s)...", model_id_to_use, thinking_enabled_log_status, extra={'trace_id': trace_id})
                response = await chat_session.send_message_async(
                    content=user_question_text,
                    generation_config=generation_config
                )
                response_text = response.text or ""
                usage_obj = getattr(response, "usage_metadata", None)

            if usage_obj:
                all_fields = [
                    "prompt_token_count", "cached_content_token_count",
                    "candidates_token_count", "total_token_count",
                    "tool_use_prompt_token_count", "thoughts_token_count",
                ]
                for field in all_fields:
                    full_usage_metadata[field] = getattr(usage_obj, field, None)

            if is_debug_mode:
                history_str = json.dumps(history, ensure_ascii=False)
                try:
                    if getattr(response, "candidates", None):
                        for candidate in response.candidates:
                            if candidate.content and candidate.content.parts:
                                for part in candidate.content.parts:
                                    if getattr(part, 'thought', False) and getattr(part, 'text', None):
                                        thoughts_log += f"\n{part.text}"
                                    elif isinstance(getattr(part, 'thought', None), str):
                                        thoughts_log += f"\n{part.thought}"
                except Exception as e:
                    thoughts_log = f" (ошибка извлечения: {e})"

                log_message = (
                    f"--- AI REQUEST (DEBUG) ---\n"
                    f"MODEL: {model_id_to_use}\n"
                    f"--- FINAL SYSTEM PROMPT ({len(final_system_prompt)} chars) ---\n{final_system_prompt}\n"
                    f"--- CHAT HISTORY ({len(history_str)} chars) ---\n{self._format_history_for_log(history)}\n"
                    f"--- QUESTION ({len(user_question_text)} chars) ---\n{user_question_text}\n"
                    f"--- THOUGHTS ---{thoughts_log if thoughts_log else ' (отсутствуют или не поддерживаются моделью)'}\n"
                    f"--- USAGE ---\n{json.dumps(full_usage_metadata, default=str, indent=2)}\n"
                    f"--- END REQUEST ---"
                )
            else:
                log_message = (
                    f"--- AI REQUEST ---\n"
                    f"MODEL: {model_id_to_use}\n"
                    f"FINAL_SYSTEM_PROMPT_LEN: {len(final_system_prompt)}\n"
                    f"CHAT_HISTORY_LEN: {len(json.dumps(history))}\n"
                    f"QUESTION: {user_question_text[:150]}...\n"
                    f"USAGE: total_tokens={full_usage_metadata.get('total_token_count', 'N/A')}\n"
                    f"--- END REQUEST ---"
                )
            ai_logger.info(log_message, extra={'trace_id': trace_id})

            return response_text, full_usage_metadata

        except Exception as e:
            logger.error("Ошибка при генерации ответа от Gemini: %s", e, exc_info=True, extra={'trace_id': trace_id})
            return f"Произошла ошибка при обращении к AI. Попробуйте позже. ({type(e).__name__})", None

    async def get_moderation_verdict(self, text: str, prompt_template: str, model_id: str, trace_id: str) -> bool:
        model_id_to_use = self.models.get(model_id)
        if not model_id_to_use:
            logger.error("Модель модерации %s не найдена.", model_id, extra={'trace_id': trace_id})
            return False

        prompt = safe_format_template(prompt_template, text=text)

        try:
            if self.client and HAS_MODERN_GENAI:
                response = await self.client.aio.models.generate_content(
                    model=model_id_to_use,
                    contents=prompt,
                    config=modern_types.GenerateContentConfig(
                        temperature=0.0, top_p=1.0, top_k=1, max_output_tokens=10
                    )
                )
                verdict = (response.text or "").strip().upper()
            else:
                model = legacy_genai.GenerativeModel(model_id_to_use)
                moderation_config = LegacyGenerationConfig(temperature=0.0, top_p=1.0, top_k=1, max_output_tokens=10)
                response = await model.generate_content_async([prompt], generation_config=moderation_config)
                verdict = (response.text or "").strip().upper()

            logger.debug("Ответ модератора для текста '%s...': '%s'", text[:50], verdict, extra={'trace_id': trace_id})
            return verdict.startswith("ДА")
        except Exception as e:
            logger.error("Ошибка при получении вердикта модерации: %s", e, extra={'trace_id': trace_id})
            return False
