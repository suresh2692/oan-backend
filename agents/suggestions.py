from pydantic_ai import Agent, Tool
from pydantic_ai.settings import ModelSettings
from typing import List
from helpers.utils import get_prompt
from agents.models import LLM_MODEL
from agents.tools.search import search_documents


# Use str output to avoid tool_choice: "required" which some OpenRouter
# providers don't support.  The task layer parses the list from text.
suggestions_agent = Agent(
    name="Suggestions Agent",
    model=LLM_MODEL,
    system_prompt=get_prompt('suggestions_system'),
    output_type=str,
    retries=1,
    end_strategy='exhaustive',
    tools=[
        Tool(
            search_documents,
            takes_ctx=False,
        )
    ],
    model_settings=ModelSettings(
        parallel_tool_calls=False,
    )
)