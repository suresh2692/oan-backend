import time
from opentelemetry.trace import StatusCode
from app.core.cache import cache
from app.core.telemetry import get_tracer, get_meter
from helpers.utils import get_logger
from app.utils import get_message_history, trim_history, format_message_pairs
from agents.suggestions import suggestions_agent
from langcodes import Language

logger = get_logger(__name__)

# OpenTelemetry instrumentation
tracer = get_tracer(__name__)
meter = get_meter(__name__)

# Metrics
suggestions_requests = meter.create_counter(
    "suggestions.requests.total",
    description="Total number of suggestion generation attempts"
)
suggestions_duration = meter.create_histogram(
    "suggestions.generation.duration",
    unit="s",
    description="Suggestion generation duration in seconds"
)
suggestions_errors = meter.create_counter(
    "suggestions.errors.total",
    description="Total number of suggestion generation errors"
)

SUGGESTIONS_CACHE_TTL = 60*30 # 30 minutes
SUGGESTIONS_EMPTY_CACHE_TTL = 60 # Cache empty results for 60s to prevent retry storms

async def create_suggestions(session_id: str, target_lang: str = 'mr'):
    """
    Create and save suggestions for a session
    """
    logger.info(f"Getting suggestions for session {session_id}")

    # Short-circuit if we recently failed (prevents retry storms on rate-limit)
    empty_key = f"suggestions_empty_{session_id}_{target_lang}"
    if await cache.get(empty_key):
        logger.debug(f"Skipping suggestions for session {session_id} - recently failed, waiting for cooldown")
        return {"status": "skipped", "message": "Cooldown active from recent failure"}

    span = tracer.start_span("suggestions_generation")
    span.set_attribute("session.id", session_id)
    span.set_attribute("suggestions.target_lang", target_lang)
    suggestions_requests.add(1, {"target_lang": target_lang})
    start = time.time()

    target_lang_name = Language.get(target_lang).display_name(target_lang)

    history   = trim_history(await get_message_history(session_id),
                             30_000,
                             include_tool_calls=False,
                             include_system_prompts=False
                             )
    message_pairs = "\n\n".join(format_message_pairs(history, 5))

    message       = f"**Conversation**\n\n{message_pairs}\n\n**Based on the conversation, suggest 3-5 questions the farmer can ask in {target_lang_name}.**"
    try:
        agent_run    = await suggestions_agent.run(message)
        suggestions = [x for x in agent_run.output]
    except Exception as e:
        suggestions_errors.add(1, {"target_lang": target_lang, "error_type": type(e).__name__})
        span.record_exception(e)
        span.set_status(StatusCode.ERROR, str(e))
        logger.warning(f"Suggestions agent failed: {e}. Using empty suggestions.")
        suggestions = []
        # Cache the failure to prevent retry storms
        await cache.set(empty_key, True, ttl=SUGGESTIONS_EMPTY_CACHE_TTL)
    finally:
        duration = time.time() - start
        suggestions_duration.record(duration, {"target_lang": target_lang})
        span.set_attribute("suggestions.duration_seconds", duration)
        span.set_attribute("suggestions.count", len(suggestions))
        if suggestions:
            span.set_status(StatusCode.OK)
        span.end()

    logger.info(f"Suggestions: {suggestions}")
    # Store suggestions in cache
    if suggestions:
        await cache.set(f"suggestions_{session_id}_{target_lang}", suggestions, ttl=SUGGESTIONS_CACHE_TTL)
        logger.info(f"Suggestions created and saved for session {session_id}")

    return {
        "status": "success" if suggestions else "skipped",
        "message": f"Suggestions {'created' if suggestions else 'skipped'} for session {session_id}"
    }