# NVC_bot/bot/services/gemini.py
# version: 3.0.0
# 2025-07-30T14:00:00Z
"""
Сервис-обертка для взаимодействия с Google Gemini API.

Version 3.0.0:
- REFACTOR: Внедрена композитная архитектура промптов.
            - Метод `generate_response` теперь принимает `task_instruction` вместо `system_prompt`.
            - Финальный системный промпт динамически собирается из "Ядра личности" (из БД)
              и "Инструкции к задаче", обеспечивая консистентность поведения.
            - Добавлена обработка переменной `{{group_rules}}` через новый
              аргумент `chat_description`.
- NOTE: Метод `get_moderation_verdict` намеренно не затронут и не использует
        "Ядро личности" для сохранения своей технической точности.

Version 2.8.1:
- FIX: Устранена фатальная ошибка `AttributeError` при попытке использовать
         `ThinkingConfig`. Добавлен блок try-except, который предотвращает
         сбой и логирует, что функция недоступна в текущей версии SDK.
"""
import logging
import json
from typing import Dict, List, Optional, Tuple, Any

import google.generativeai as genai
from google.generativeai.types import GenerationConfig, content_types
from google.generativeai import types as genai_types

from ..config import settings
from ..database import Database

logger = logging.getLogger(__name__)
ai_logger = logging.getLogger('ai_requests')

class GeminiService:
    """
    Инкапсулирует логику работы с моделями Gemini.
    """

    def __init__(self, model_names: Dict[str, str], db: Database):
        self.db = db
        try:
            genai.configure(api_key=settings.GEMINI_API_KEY)
            logger.info("Ключ Gemini API успешно сконфигурирован.", extra={'trace_id': 'init'})
        except Exception as e:
            logger.critical("КРИТИЧЕСКАЯ ОШИБКА: Не удалось сконфигурировать Gemini API.", exc_info=e, extra={'trace_id': 'init'})
            raise

        self.model_names = model_names
        self.models: Dict[str, str] = {}
        for name, model_id in model_names.items():
            try:
                self.models[model_id] = model_id
                logger.info("Модель '%s' зарегистрирована для использования.", model_id, extra={'trace_id': 'init'})
            except Exception as e:
                logger.error("Ошибка при регистрации модели %s: %s", model_id, e, extra={'trace_id': 'init'})
        
        if not self.models:
            logger.critical("КРИТИЧЕСКАЯ ОШИБКА: Не удалось зарегистрировать ни одну AI-модель.", extra={'trace_id': 'init'})
            raise RuntimeError("Не удалось инициализировать AI-модели.")

        self.current_model_id = model_names.get("pro", next(iter(self.models.keys())))

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
        chat_history: List[Dict] = None,
        user_mention: Optional[str] = None,
        model_override: Optional[str] = None,
        is_debug_mode: bool = False,
        chat_description: Optional[str] = None
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        model_id_to_use = model_override if model_override and model_override in self.models else self.current_model_id
        
        try:
            # 1. Загружаем "Ядро личности"
            core_prompt = await self.db.get_prompt()
            
            # 2. Подставляем в "Ядро" правила группы, если они переданы
            if chat_description:
                core_prompt = core_prompt.replace("{{group_rules}}", chat_description)

            # 3. Собираем финальный системный промпт
            final_system_prompt = core_prompt
            if task_instruction and task_instruction.strip():
                final_system_prompt = f"{core_prompt}\n\n---\n\n{task_instruction}"

            model = genai.GenerativeModel(
                model_name=model_id_to_use,
                system_instruction=final_system_prompt
            )
            
            gen_config_dict = await self.db.get_generation_config()
            
            thinking_enabled_log_status = "OFF"
            if is_debug_mode:
                try:
                    gen_config_dict['thinking_config'] = genai_types.ThinkingConfig(include_thoughts=True)
                    thinking_enabled_log_status = "ON"
                except AttributeError:
                    logger.warning("Не удалось включить 'мысли': `ThinkingConfig` не найден в текущей версии SDK. Обновите google-generativeai.", extra={'trace_id': trace_id})
                    thinking_enabled_log_status = "UNSUPPORTED"

            generation_config = GenerationConfig(**gen_config_dict)
            
            history = chat_history or []
            chat_session = model.start_chat(history=history)
            
            user_question_text = f"Сообщение от пользователя {user_mention}: {question}" if user_mention and question else question
            
            logger.info("Отправка запроса к модели %s (Thinking: %s)...", model_id_to_use, thinking_enabled_log_status, extra={'trace_id': trace_id})
            
            response = await chat_session.send_message_async(
                content=user_question_text,
                generation_config=generation_config
            )
            
            usage_metadata_obj = getattr(response, 'usage_metadata', None)
            full_usage_metadata = {}
            if usage_metadata_obj:
                all_fields = [
                    "prompt_token_count", "cached_content_token_count", 
                    "candidates_token_count", "total_token_count",
                    "tool_use_prompt_token_count", "thoughts_token_count",
                ]
                for field in all_fields:
                    full_usage_metadata[field] = getattr(usage_metadata_obj, field, None)
                logger.info("Полные метаданные об использовании токенов извлечены.", extra={'trace_id': trace_id})
            else:
                logger.warning("Атрибут 'usage_metadata' не найден в ответе от Gemini API.", extra={'trace_id': trace_id})

            if is_debug_mode:
                history_str = json.dumps(history, ensure_ascii=False)
                
                thoughts_log = ""
                try:
                    if response.candidates:
                        for candidate in response.candidates:
                            if candidate.content and candidate.content.parts:
                                for part in candidate.content.parts:
                                    if hasattr(part, 'thought') and part.thought:
                                        thoughts_log += f"\n{part.thought}"
                except Exception as e:
                    thoughts_log = f" (ошибка извлечения: {e})"

                log_message = (
                    f"--- AI REQUEST (DEBUG) ---\n"
                    f"MODEL: {model_id_to_use}\n"
                    f"--- FINAL SYSTEM PROMPT ({len(final_system_prompt)} chars) ---\n{final_system_prompt}\n"
                    f"--- CHAT HISTORY ({len(history_str)} chars) ---\n{self._format_history_for_log(history)}\n"
                    f"--- QUESTION ({len(question)} chars) ---\n({user_mention or 'system'}): {question}\n"
                    f"--- THOUGHTS ---{thoughts_log if thoughts_log else ' (отсутствуют или не поддерживаются SDK)'}\n"
                    f"--- USAGE ---\n{json.dumps(full_usage_metadata, default=str, indent=2)}\n"
                    f"--- END REQUEST ---"
                )
            else:
                log_message = (
                    f"--- AI REQUEST ---\n"
                    f"MODEL: {model_id_to_use}\n"
                    f"FINAL_SYSTEM_PROMPT_LEN: {len(final_system_prompt)}\n"
                    f"CHAT_HISTORY_LEN: {len(json.dumps(history))}\n"
                    f"QUESTION: ({user_mention or 'system'}): {question[:150]}...\n"
                    f"USAGE: total_tokens={full_usage_metadata.get('total_token_count', 'N/A')}\n"
                    f"--- END REQUEST ---"
                )
            ai_logger.info(log_message, extra={'trace_id': trace_id})

            return response.text, full_usage_metadata

        except Exception as e:
            logger.error("Ошибка при генерации ответа от Gemini: %s", e, exc_info=True, extra={'trace_id': trace_id})
            return f"Произошла ошибка при обращении к AI. Попробуйте позже. ({type(e).__name__})", None

    async def get_moderation_verdict(self, text: str, prompt_template: str, model_id: str, trace_id: str) -> bool:
        model_id_to_use = self.models.get(model_id)
        if not model_id_to_use:
            logger.error("Модель модерации %s не найдена.", model_id, extra={'trace_id': trace_id})
            return False
        
        model = genai.GenerativeModel(model_id_to_use)
        prompt = prompt_template.format(text=text)
        
        try:
            moderation_config = GenerationConfig(temperature=0.0, top_p=1.0, top_k=1, max_output_tokens=10)
            response = await model.generate_content_async([prompt], generation_config=moderation_config)
            verdict = response.text.strip().upper()
            logger.debug("Ответ модератора для текста '%s...': '%s'", text[:50], verdict, extra={'trace_id': trace_id})
            return verdict == "ДА"
        except Exception as e:
            logger.error("Ошибка при получении вердикта модерации: %s", e, extra={'trace_id': trace_id})
            return False
