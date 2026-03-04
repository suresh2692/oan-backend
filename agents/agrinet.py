import os
from pydantic_ai import Agent, RunContext
from helpers.utils import get_prompt, get_today_date_str, get_ethiopian_date_str
from agents.models import LLM_MODEL
from agents.tools import TOOLS
from agents.deps import FarmerContext

# Build model_settings based on provider (thinking_config is Gemini-only)
_llm_provider = os.getenv('LLM_PROVIDER', 'gemini').lower()
_model_settings = {"temperature": 0.2}
if _llm_provider == 'gemini':
    _model_settings["thinking_config"] = {"thinking_level": "MINIMAL"}

agrinet_agent = Agent(
    model=LLM_MODEL,
    name="AgriHelp Assistant",
    output_type=str,
    deps_type=FarmerContext,
    retries=1,
    tools=TOOLS,
    end_strategy='exhaustive',
    model_settings=_model_settings,
)

# Use dynamic system prompt like old backend
@agrinet_agent.system_prompt
def dynamic_system_prompt(ctx: RunContext[FarmerContext]) -> str:
    """Dynamic system prompt based on context"""
    lang = ctx.deps.lang_code if ctx.deps else "en"
    # Use Ethiopian calendar date for Amharic, Gregorian for others
    today_date = get_ethiopian_date_str() if lang == "am" else get_today_date_str()
    return get_prompt(lang, context={'today_date': today_date})

# Generator Agent (No Tools) - for Phase 2
_gen_settings = {"temperature": 0.2}
if _llm_provider == 'gemini':
    _gen_settings["thinking_config"] = {"thinking_level": "HIGH"}
    _gen_settings["safety_settings"] = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"},
    ]

generation_agent = Agent(
    model=LLM_MODEL,
    name="AgriHelp Generator",
    output_type=str,
    deps_type=FarmerContext,
    retries=3,
    tools=[],
    end_strategy='exhaustive',
    model_settings=_gen_settings,
)

@generation_agent.system_prompt
def generation_system_prompt(ctx: RunContext[FarmerContext]) -> str:
    lang = ctx.deps.lang_code if ctx.deps else "en"
    # Use Ethiopian calendar date for Amharic, Gregorian for others
    today_date = get_ethiopian_date_str() if lang == "am" else get_today_date_str()
    try:
        # Try to use generation-specific prompt (e.g. generation_en.md)
        return get_prompt(f"generation_{lang}", context={'today_date': today_date})
    except Exception:
        # Fallback to standard prompt with explicit override
        base_prompt = get_prompt(lang, context={'today_date': today_date})
        return f"{base_prompt}\n\nIMPORTANT: You are a response generator. Do not generate tool calls. Use the provided context to answer the user directly in text."
