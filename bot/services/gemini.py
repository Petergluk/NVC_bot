# NVC_bot/bot/services/gemini.py
# version: 5.0.0
# 2026-10-30T16:30:00Z

'''
Сервис-обертка для взаимодействия с Google Gemini API.

Version 5.0.0:
- UPGRADE: Полная поддержка линейки моделей Gemini 3.8 Flash (по умолчанию), 3.6 Flash,
           3.5 Flash-Lite, 3.1 Flash-Lite, 3 Flash Preview, 2.5 Pro/Flash/Lite, Gemma 4,
           а также Paid-моделей Gemini 4 Argon и Gemini 3.1 Pro Preview.
- ADD: Structured Outputs через Pydantic (`ModerationVerdict` и `NvcTranslationResult`)
       для стопроцентно надежного JSON-ответа модератора и ННО-переводчика.
- ADD: Метод `translate_to_nvc` для 4-шагового перевода фраз по Маршаллу Розенбергу
       (Наблюдение -> Чувство -> Потребность -> Просьба).
'''

import logging
import json
from typing import Dict, List, Optional, Tuple, Any
from pydantic import BaseModel, Field

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

from ..config import settings, AVAILABLE_MODELS_CATALOG
from ..database import Database
from ..utils.formatters import safe_format_template

logger = logging.getLogger(__name__)
ai_logger = logging.getLogger('ai_requests')


class ModerationVerdict(BaseModel):
    '''Типизированная схема вердикта ИИ-судьи модерации (Structured Output).'''
    is_violation: bool = Field(description="True, если сообщение нарушает принципы ННО (агрессия, ярлыки, обвинения).")
    severity: int = Field(default=1, description="Оценка резкости от 1 до 5.")
    violated_rule: str = Field(default="Ты-сообщение / оценочное суждение", description="Какое правило нарушено.")
    observation_nvc: str = Field(default="", description="Безоценочное наблюдение факта.")
    feeling_and_need_nvc: str = Field(default="", description="Предполагаемые чувства и потребности автора.")
    suggested_nvc: str = Field(default="", description="Мягкая переформулировка исходной мысли на языке ННО от первого лица.")


class NvcTranslationResult(BaseModel):
    '''Типизированная схема 4-шагового перевода фразы на язык ННО.'''
    observation: str = Field(description="Шаг 1: Наблюдение без оценки и обобщений.")
    feeling: str = Field(description="Шаг 2: Чувство автора (например: тревога, усталость, досада).")
    need: str = Field(description="Шаг 3: Потребность (например: предсказуемость, уважение, поддержка).")
    request: str = Field(description="Шаг 4: Конкретная выполнимая просьба вместо требования.")
    natural_nvc_phrase: str = Field(description="Естественная живая фраза на языке ННО, готовая к отправке в чат.")


class GeminiService:
    '''
    Инкапсулирует логику работы с моделями Gemini (поддерживает google-genai и google-generativeai).
    '''
    def __init__(self, model_names: Dict[str, str], db: Database):
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
        self.models: Dict[str, str] = {m_id: m_id for m_id in AVAILABLE_MODELS_CATALOG.keys()}
        for alias_val in model_names.values():
            self.models[alias_val] = alias_val
        if not self.models:
            raise RuntimeError("Не удалось инициализировать AI-модели.")
        self.current_model_id = model_names.get("flash", "gemini-3.8-flash")
        if self.current_model_id not in self.models:
            self.current_model_id = "gemini-3.8-flash"

    async def initialize_from_db(self) -> None:
        '''Восстанавливает сохраненную в БД основную модель Фасилитатора.'''
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

    def get_model_display_label(self, model_id: str) -> str:
        meta = AVAILABLE_MODELS_CATALOG.get(model_id)
        return meta["label"] if meta else model_id

    def _format_history_for_log(self, history: List[Dict[str, Any]]) -> str:
        if not history:
            return " (пусто)"
        lines = []
        for item in history:
            role = item.get("role", "unknown")
            text = item.get("parts", [{}])[0].get("text", "")
            lines.append(f"  {role}: {text[:90]}...")
        return "\n".join(lines)

    async def generate_response(
        self,
        question: str,
        task_instruction: str = "",
        chat_history: Optional[List[Dict[str, Any]]] = None,
        trace_id: str = "unspecified",
        user_mention: Optional[str] = None,
        is_debug_mode: bool = False,
        model_override: Optional[str] = None,
        chat_description: Optional[str] = None
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        model_id_to_use = model_override or self.current_model_id
        if model_id_to_use not in self.models:
            model_id_to_use = "gemini-3.8-flash"

        try:
            core_prompt = await self.db.get_prompt()
            final_system_prompt = core_prompt
            if task_instruction:
                final_system_prompt += f"\n\n--- ДОПОЛНИТЕЛЬНАЯ ИНСТРУКЦИЯ ---\n{task_instruction}"

            final_system_prompt = safe_format_template(
                final_system_prompt,
                group_rules=chat_description or "Правила группы не указаны."
            )

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
                if is_debug_mode and hasattr(modern_types, "ThinkingConfig") and "gemma" not in model_id_to_use:
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
                        thinking_enabled_log_status = "UNSUPPORTED"

                generation_config = LegacyGenerationConfig(**gen_config_dict)
                chat_session = model.start_chat(history=history)
                response = await chat_session.send_message_async(
                    content=user_question_text,
                    generation_config=generation_config
                )
                response_text = response.text or ""
                usage_obj = getattr(response, "usage_metadata", None)

            if usage_obj:
                for field in [
                    "prompt_token_count", "cached_content_token_count",
                    "candidates_token_count", "total_token_count",
                    "tool_use_prompt_token_count", "thoughts_token_count",
                ]:
                    full_usage_metadata[field] = getattr(usage_obj, field, None)

            if is_debug_mode:
                history_str = json.dumps(history, ensure_ascii=False)
                log_message = (
                    f"--- AI REQUEST (DEBUG) ---\n"
                    f"MODEL: {model_id_to_use}\n"
                    f"--- FINAL SYSTEM PROMPT ({len(final_system_prompt)} chars) ---\n{final_system_prompt}\n"
                    f"--- CHAT HISTORY ({len(history_str)} chars) ---\n{self._format_history_for_log(history)}\n"
                    f"--- QUESTION ({len(user_question_text)} chars) ---\n{user_question_text}\n"
                    f"--- USAGE ---\n{json.dumps(full_usage_metadata, default=str, indent=2)}\n"
                    f"--- END REQUEST ---"
                )
            else:
                log_message = (
                    f"--- AI REQUEST ---\n"
                    f"MODEL: {model_id_to_use}\n"
                    f"QUESTION: {user_question_text[:150]}...\n"
                    f"USAGE: total_tokens={full_usage_metadata.get('total_token_count', 'N/A')}\n"
                    f"--- END REQUEST ---"
                )
            ai_logger.info(log_message, extra={'trace_id': trace_id})
            return response_text, full_usage_metadata

        except Exception as e:
            logger.error("Ошибка при генерации ответа от Gemini: %s", e, exc_info=True, extra={'trace_id': trace_id})
            return f"Произошла ошибка при обращении к AI. Попробуйте позже. ({type(e).__name__})", None

    async def evaluate_moderation_structured(
        self,
        text: str,
        prompt_template: str,
        model_id: str,
        trace_id: str
    ) -> ModerationVerdict:
        '''
        Возвращает типизированный вердикт ИИ-судьи (ModerationVerdict) + мягкую ННО-версию фразы.
        Использует Structured Outputs (response_schema=ModerationVerdict) в google-genai.
        '''
        model_id_to_use = model_id if model_id in self.models else "gemini-3.8-flash"
        base_prompt = safe_format_template(prompt_template, text=text)
        structured_instruction = (
            f"{base_prompt}\n\n"
            f"Проанализируй сообщение: «{text}».\n"
            "Если сообщение содержит агрессию, обвинение, ярлык или грубое 'ты-сообщение', "
            "установи is_violation=true и обязательно заполни suggested_nvc бережной переформулировкой "
            "мысли автора по 4 шагам ННО (от первого лица: Наблюдение -> Чувство -> Потребность -> Просьба)."
        )
        try:
            if self.client and HAS_MODERN_GENAI and "gemma" not in model_id_to_use:
                response = await self.client.aio.models.generate_content(
                    model=model_id_to_use,
                    contents=structured_instruction,
                    config=modern_types.GenerateContentConfig(
                        temperature=0.1,
                        response_mime_type="application/json",
                        response_schema=ModerationVerdict,
                    ),
                )
                raw_json = (response.text or "").strip()
                data = json.loads(raw_json)
                return ModerationVerdict(**data)
        except Exception as e:
            logger.warning("Structured moderation fallback для %s: %s", model_id_to_use, e, extra={'trace_id': trace_id})

        # Fallback для моделей без JSON Schema или при работе через старый SDK
        is_viol = await self.get_moderation_verdict(text, prompt_template, model_id_to_use, trace_id)
        suggested = ""
        if is_viol:
            nvc_res = await self.translate_to_nvc(text, trace_id=trace_id)
            suggested = nvc_res.natural_nvc_phrase
        return ModerationVerdict(
            is_violation=is_viol,
            severity=3 if is_viol else 1,
            violated_rule="Ты-сообщение / оценочное суждение" if is_viol else "",
            suggested_nvc=suggested,
        )

    async def get_moderation_verdict(self, text: str, prompt_template: str, model_id: str, trace_id: str) -> bool:
        model_id_to_use = self.models.get(model_id, "gemini-3.8-flash")
        prompt = safe_format_template(prompt_template, text=text)
        try:
            if self.client and HAS_MODERN_GENAI:
                response = await self.client.aio.models.generate_content(
                    model=model_id_to_use,
                    contents=prompt,
                    config=modern_types.GenerateContentConfig(
                        temperature=0.0, top_p=1.0, top_k=1, max_output_tokens=20
                    )
                )
                verdict = (response.text or "").strip().upper()
            else:
                model = legacy_genai.GenerativeModel(model_id_to_use)
                moderation_config = LegacyGenerationConfig(temperature=0.0, top_p=1.0, top_k=1, max_output_tokens=20)
                response = await model.generate_content_async([prompt], generation_config=moderation_config)
                verdict = (response.text or "").strip().upper()

            logger.debug("Ответ модератора для текста '%s...': '%s'", text[:50], verdict, extra={'trace_id': trace_id})
            return verdict.startswith("ДА") or '"IS_VIOLATION": TRUE' in verdict
        except Exception as e:
            logger.error("Ошибка при получении вердикта модерации: %s", e, extra={'trace_id': trace_id})
            return False

    async def translate_to_nvc(self, raw_text: str, trace_id: str = "nvc_translate") -> NvcTranslationResult:
        '''
        Переводит любую резкую или конфликтную фразу по 4 шагам Ненасильственного общения (ННО).
        '''
        model_id_to_use = self.current_model_id if self.current_model_id in self.models else "gemini-3.8-flash"
        prompt = (
            "Ты — чуткий медиатор и эксперт по Ненасильственному общению (ННО / NVC Маршалла Розенберга).\n"
            "Переформулируй следующую фразу человека на язык ННО по 4 шагам (без оценок, ярлыков и обвинений, "
            "сохраняя истинную боль и потребность автора):\n\n"
            f"Исходная фраза: «{raw_text}»\n\n"
            "Верни строго JSON со следующими полями:\n"
            "- observation: конкретное безоценочное наблюдение (Когда я вижу/слышу...)\n"
            "- feeling: искреннее чувство автора (я чувствую...)\n"
            "- need: стоящая за этим потребность (потому что для меня важно / мне нужно...)\n"
            "- request: конкретная выполнимая просьба (Не мог(ла) бы ты / давай договоримся...)\n"
            "- natural_nvc_phrase: живая, естественная, теплая фраза от первого лица, готовая к отправке в чат."
        )
        try:
            if self.client and HAS_MODERN_GENAI and "gemma" not in model_id_to_use:
                response = await self.client.aio.models.generate_content(
                    model=model_id_to_use,
                    contents=prompt,
                    config=modern_types.GenerateContentConfig(
                        temperature=0.4,
                        response_mime_type="application/json",
                        response_schema=NvcTranslationResult,
                    ),
                )
                data = json.loads((response.text or "").strip())
                return NvcTranslationResult(**data)
        except Exception as e:
            logger.warning("Fallback перевода ННО для %s: %s", model_id_to_use, e, extra={'trace_id': trace_id})

        # Fallback через обычную текстовую генерацию
        fallback_text, _ = await self.generate_response(
            question=raw_text,
            task_instruction=(
                "Переформулируй это сообщение по 4 шагам ННО (Наблюдение, Чувство, Потребность, Просьба) "
                "и предложи мягкую готовую фразу от первого лица."
            ),
            trace_id=trace_id,
        )
        return NvcTranslationResult(
            observation="Когда возникают подобные ситуации в диалоге",
            feeling="я чувствую напряжение и потребность в ясности",
            need="мне важны взаимное уважение и конструктивный контакт",
            request="давай обсудим конкретные факты спокойно и по шагам",
            natural_nvc_phrase=fallback_text or "Мне важно обсудить эту ситуацию спокойно, опираясь на факты и взаимное уважение.",
        )