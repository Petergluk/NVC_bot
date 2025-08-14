# NVC_bot/bot/services/gemini.py
# version: 7.0.4
# 2025-08-14T12:45:00Z
"""
Сервис-обертка для взаимодействия с Google Gemini API.

Version 7.0.4:
- FIX: Окончательно исправлена сигнатура `get_moderation_verdict` для
       устранения `TypeError`. Аргумент `model_override` теперь является
       строго именованным.

Version 7.0.3:
- FIX: Устранена ошибка `IndentationError`.
"""
import logging
import json
import re
import asyncio
import functools
from typing import Dict, List, Optional, Tuple, Any, Callable, Coroutine, Set

import google.generativeai as genai
from google.generativeai.types import GenerationConfig, HarmCategory, HarmBlockThreshold
from google.api_core.exceptions import FailedPrecondition, InternalServerError, ResourceExhausted
from telegram.ext import Application
from telegram.constants import ParseMode

from ..config import settings, ADMIN_IDS, MODEL_FALLBACK_CHAIN
from ..database import Database
from ..utils.formatters import truncate_for_log, escape_markdown_v2

logger = logging.getLogger(__name__)
ai_logger = logging.getLogger('ai_requests')

def _handle_api_exceptions(func: Callable[..., Coroutine]) -> Callable[..., Coroutine]:
    """
    Декоратор для обработки исключений API Gemini, включая лимиты.
    """
    @functools.wraps(func)
    async def wrapper(self: "GeminiService", *args, **kwargs) -> Any:
        max_retries = 3
        base_delay = 5

        model_id = kwargs.get('model_override')
        if not model_id:
            if func.__name__ == 'get_moderation_verdict':
                model_id = await self.db.get_moderation_model()
            else:
                model_id = await self.get_active_model_name()
        
        kwargs['model_override'] = model_id

        for attempt in range(max_retries):
            try:
                return await func(self, *args, **kwargs)
            except ResourceExhausted as e:
                trace_id = kwargs.get('trace_id', 'unknown')
                logger.warning(
                    "API Limit Reached (Attempt %d/%d) for model %s. Error: %s",
                    attempt + 1, max_retries, model_id, e, extra={'trace_id': trace_id}
                )

                if "per day" in str(e):
                    fallback_model = MODEL_FALLBACK_CHAIN.get(model_id)
                    tried_models = kwargs.get('_tried_models', set())
                    
                    if fallback_model and fallback_model not in tried_models:
                        await self._notify_admin(
                            f"⚠️ *Лимит API исчерпан*\n\n"
                            f"Суточный лимит для модели `{escape_markdown_v2(model_id)}` достигнут\\. "
                            f"Автоматически переключаюсь на резервную модель: `{escape_markdown_v2(fallback_model)}`\\."
                        )
                        tried_models.add(model_id)
                        kwargs['_tried_models'] = tried_models
                        kwargs['model_override'] = fallback_model
                        model_id = fallback_model
                        continue
                    else:
                        await self._notify_admin(
                            f"🚨 *КРИТИЧЕСКИЙ СБОЙ: Все лимиты исчерпаны*\n\n"
                            f"Суточный лимит для модели `{escape_markdown_v2(model_id)}` достигнут, и резервные модели также недоступны\\. "
                            f"Бот не сможет отвечать до сброса лимитов API\\."
                        )
                        raise e

                elif "per minute" in str(e):
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        logger.info("Retrying in %d seconds...", delay, extra={'trace_id': trace_id})
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.error("All retries failed for per-minute limit.", extra={'trace_id': trace_id})
                        raise e
                
                else:
                    raise e
        
        raise RuntimeError("Не удалось получить ответ от API после всех попыток.")

    return wrapper


class GeminiService:
    """
    Инкапсулирует логику работы с моделями Gemini.
    """
    def __init__(self, model_names: Dict[str, str], db: Database, app: Application):
        self.db = db
        self.app = app
        try:
            genai.configure(api_key=settings.GEMINI_API_KEY)
            logger.info("Ключ Gemini API успешно сконфигурирован.", extra={'trace_id': 'init'})
        except Exception as e:
            logger.critical("КРИТИЧЕСКАЯ ОШИБКА: Не удалось сконфигурировать Gemini API.", exc_info=e, extra={'trace_id': 'init'})
            raise

        self.model_names = model_names
        self.models: Dict[str, str] = {model_id: model_id for model_id in model_names.values()}
        logger.info("Модели Gemini зарегистрированы: %s", list(self.models.keys()))

    async def _notify_admin(self, message: str) -> None:
        if not ADMIN_IDS:
            logger.warning("Не удалось отправить уведомление: ADMIN_IDS не задан.")
            return
        try:
            await self.app.bot.send_message(
                chat_id=ADMIN_IDS[0],
                text=message,
                parse_mode=ParseMode.MARKDOWN_V2
            )
        except Exception as e:
            logger.error("Критическая ошибка при отправке уведомления администратору: %s", e)

    async def get_active_model_name(self) -> str:
        return await self.db.get_main_model()

    def get_available_models(self) -> List[str]:
        return list(self.models.keys())

    @_handle_api_exceptions
    async def generate_response(
        self,
        question: str,
        trace_id: str,
        request_type: str,
        is_debug_mode: bool,
        chat_history: Optional[List[Dict]] = None,
        model_override: Optional[str] = None,
        chat_description: Optional[str] = None,
        is_admin_chat: bool = False,
        _tried_models: Optional[Set[str]] = None
    ) -> Tuple[str, Optional[Dict[str, Any]], int]:
        model_id_to_use = model_override
        
        try:
            if is_admin_chat:
                safety_settings = {category: HarmBlockThreshold.BLOCK_NONE for category in HarmCategory if category != HarmCategory.HARM_CATEGORY_UNSPECIFIED}
                safety_level_str = "BLOCK_NONE (Admin Override)"
            else:
                safety_level_str = await self.db.get_safety_level()
                safety_level_enum = getattr(HarmBlockThreshold, safety_level_str, HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE)
                safety_settings = {
                    HarmCategory.HARM_CATEGORY_HARASSMENT: safety_level_enum,
                    HarmCategory.HARM_CATEGORY_HATE_SPEECH: safety_level_enum,
                    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: safety_level_enum,
                    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: safety_level_enum,
                }
            
            system_prompt = await self.db.get_prompt()
            if chat_description:
                system_prompt = system_prompt.replace("{{group_rules}}", chat_description).replace("{{bot_username}}", f"@{settings.TELEGRAM_BOT_TOKEN.split(':')[0]}")
            system_prompt_len = len(system_prompt)

            model = genai.GenerativeModel(model_name=model_id_to_use, system_instruction=system_prompt, safety_settings=safety_settings)
            
            gen_config_dict = await self.db.get_generation_config()
            generation_config = GenerationConfig(**gen_config_dict)
            
            rich_history = chat_history or []
            api_history = [{"role": "model" if h.get("is_bot") else "user", "parts": [{"text": h.get("text", "")}]} for h in rich_history]
            
            chat_session = model.start_chat(history=api_history)
            content_to_process = question if question.strip() else "Продолжай согласно инструкции."
            
            log_parts = [ f"--- AI REQUEST ({request_type}) ---", f"MODEL: {model_id_to_use}", f"SAFETY: {safety_level_str}" ]
            if is_debug_mode:
                log_parts.extend([
                    f"--- SYSTEM PROMPT ({system_prompt_len} chars) ---\n{system_prompt}",
                    f"--- CHAT HISTORY ({len(json.dumps(rich_history))} chars) ---\n{json.dumps(rich_history, ensure_ascii=False, indent=2)}",
                    f"--- CONTENT ({len(content_to_process)} chars) ---\n{content_to_process}"
                ])
            else:
                 log_parts.extend([
                    f"SYSTEM PROMPT: ({system_prompt_len} chars)",
                    f"CHAT HISTORY: ({len(json.dumps(rich_history))} items)",
                    f"--- CONTENT ({len(content_to_process)} chars) ---\n{truncate_for_log(content_to_process)}"
                 ])
            log_parts.append("--- END OF PAYLOAD ---")
            ai_logger.info("\n".join(log_parts), extra={'trace_id': trace_id})

            response = await chat_session.send_message_async(content=content_to_process, generation_config=generation_config)
            
            if not response.parts:
                finish_reason = response.candidates[0].finish_reason if response.candidates else 'UNKNOWN'
                logger.warning("Модель не вернула контент. Причина: %s.", finish_reason, extra={'trace_id': trace_id})
                return "К сожалению, я не могу ответить на это. Возможно, в запросе или контексте содержатся неоднозначные выражения.", None, system_prompt_len

            usage_metadata_obj = getattr(response, 'usage_metadata', {})
            full_usage_metadata = { "prompt_token_count": getattr(usage_metadata_obj, "prompt_token_count", 0), "candidates_token_count": getattr(usage_metadata_obj, "candidates_token_count", 0), "total_token_count": getattr(usage_metadata_obj, "total_token_count", 0), }
            ai_logger.info(f"--- USAGE INFO ---\n{json.dumps(full_usage_metadata, indent=2)}\n--- END REQUEST ---", extra={'trace_id': trace_id})

            return response.text, full_usage_metadata, system_prompt_len

        except FailedPrecondition as e:
            logger.critical("КРИТИЧЕСКАЯ ОШИБКА: API отклоняет запросы (геоблокировка?). Ошибка: %s", e, exc_info=True, extra={'trace_id': trace_id})
            raise FailedPrecondition("К сожалению, сервис временно недоступен. Возможно, это связано с региональными ограничениями (попробуйте использовать VPN).") from e
        except InternalServerError as e:
            logger.error("КРИТИЧЕСКАЯ ОШИБКА: Внутренняя ошибка сервера Google API. Ошибка: %s", e, exc_info=True, extra={'trace_id': trace_id})
            raise InternalServerError("Произошла внутренняя ошибка на стороне AI. Пожалуйста, попробуйте повторить ваш запрос через некоторое время.") from e
        except Exception as e:
            if not isinstance(e, ResourceExhausted):
                logger.error("Ошибка при генерации ответа от Gemini: %s", e, exc_info=True, extra={'trace_id': trace_id})
                raise Exception(f"Произошла ошибка при обращении к AI. (Тип: {type(e).__name__})") from e
            raise e

    @_handle_api_exceptions
    async def get_moderation_verdict(
        self,
        text: str,
        prompt_template: str,
        trace_id: str,
        is_debug_mode: bool,
        chat_history: str = "",
        *,
        model_override: Optional[str] = None,
        _tried_models: Optional[Set[str]] = None
    ) -> bool:
        model_id_to_use = model_override
        
        safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }
        
        model = genai.GenerativeModel(model_id_to_use, safety_settings=safety_settings)
        final_prompt = prompt_template.format(text=text, chat_history=chat_history)
        
        try:
            log_parts = [ f"--- AI REQUEST (MODERATION_VERDICT) ---", f"MODEL: {model_id_to_use}" ]
            if is_debug_mode:
                log_parts.extend([ f"--- TASK PROMPT ({len(prompt_template)} chars) ---\n{prompt_template}", f"--- CHAT HISTORY ({len(chat_history)} chars) ---\n{chat_history}", f"--- CONTENT ({len(text)} chars) ---\n{text}", ])
            else:
                log_parts.extend([ f"TASK PROMPT: ({len(prompt_template)} chars)", f"CHAT HISTORY: ({len(chat_history)} chars)", f"--- CONTENT ({len(text)} chars) ---\n{truncate_for_log(text)}" ])
            log_parts.append("--- END OF PAYLOAD ---")
            ai_logger.info("\n".join(log_parts), extra={'trace_id': trace_id})

            response = await model.generate_content_async([final_prompt], generation_config=GenerationConfig(temperature=0.0, response_mime_type="application/json"))
            
            usage_metadata_obj = getattr(response, 'usage_metadata', {})
            full_usage_metadata = { "prompt_token_count": getattr(usage_metadata_obj, "prompt_token_count", 0), "candidates_token_count": getattr(usage_metadata_obj, "candidates_token_count", 0), "total_token_count": getattr(usage_metadata_obj, "total_token_count", 0), }
            ai_logger.info(f"--- USAGE INFO ---\n{json.dumps(full_usage_metadata, indent=2)}\n--- END REQUEST ---", extra={'trace_id': trace_id})

            if not response.parts:
                logger.warning("Модель модерации не вернула контент. Finish reason: %s.", response.candidates[0].finish_reason, extra={'trace_id': trace_id})
                return False

            verdict_data = json.loads(re.sub(r'```json\n?|```', '', response.text, flags=re.DOTALL))
            ai_logger.info(f"--- MODERATION RESPONSE (JSON) ---\n{json.dumps(verdict_data, indent=2, ensure_ascii=False)}\n--- END RESPONSE ---", extra={'trace_id': trace_id})
            return verdict_data.get("is_violation") is True

        except (FailedPrecondition, InternalServerError) as e:
            logger.critical("КРИТИЧЕСКАЯ ОШИБКА: API модерации недоступно. Ошибка: %s", e, exc_info=True, extra={'trace_id': trace_id})
            return False
        except Exception as e:
            if not isinstance(e, ResourceExhausted):
                logger.error("Ошибка при получении вердикта модерации: %s", e, exc_info=True, extra={'trace_id': trace_id})
            return False
