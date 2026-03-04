"""
Fast OpenAI-Compatible Service - For LM Studio / vLLM / OpenAI endpoints.
Drop-in replacement for FastGeminiService when using non-Gemini providers.
"""
import os
import time
import json
from typing import Dict, Any, AsyncGenerator
from openai import AsyncOpenAI
from helpers.utils import get_logger, get_prompt, get_today_date_str

logger = get_logger(__name__)


class FastOpenAIService:
    """OpenAI-compatible LLM service for low-latency queries."""

    def __init__(self, model: str = None, lang: str = "en"):
        self.client = AsyncOpenAI(
            base_url=os.getenv("INFERENCE_ENDPOINT_URL", "http://localhost:1234/v1"),
            api_key=os.getenv("INFERENCE_API_KEY", "lm-studio"),
        )
        self.model = model or os.getenv("LLM_MODEL_NAME", "deepseek-r1-distill-qwen-14b")
        self.lang = lang
        self.system_prompt = get_prompt(lang, context={'today_date': get_today_date_str(lang)})
        logger.info(f"FastOpenAIService initialized: model={self.model}, lang={lang}")

    async def generate_response(
        self,
        query: str,
        metrics: Dict[str, Any],
    ) -> AsyncGenerator[str, None]:
        """Generate streaming response from OpenAI-compatible endpoint."""
        t_start = time.perf_counter()
        metrics['llm_start'] = t_start
        first_token_recorded = False

        try:
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": query},
                ],
                temperature=0.2,
                stream=True,
            )

            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    if not first_token_recorded:
                        metrics['first_token'] = time.perf_counter()
                        first_token_recorded = True
                    yield delta.content

            metrics['llm_end'] = time.perf_counter()

            if not first_token_recorded:
                logger.warning("LLM finished without yielding text, sending fallback.")
                fallback = "I couldn't generate a response. Please try again."
                yield fallback
                metrics['llm_end'] = time.perf_counter()

        except Exception as e:
            logger.error(f"FastOpenAI error: {e}")
            metrics['llm_end'] = time.perf_counter()
            yield f"I encountered an error: {str(e)[:100]}. Please try again."
