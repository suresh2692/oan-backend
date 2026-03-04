import time
from fastapi.responses import StreamingResponse
import uuid
import asyncio
from fastapi import APIRouter, BackgroundTasks
from helpers.utils import get_logger
from app.utils import get_message_history
from app.tasks.suggestions import create_suggestions
from app.services.chat import stream_chat_messages
from app.models.requests import ChatRequest
from opentelemetry.trace import StatusCode
from app.core.telemetry import get_tracer, get_meter

logger = get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

# OpenTelemetry instrumentation
tracer = get_tracer(__name__)
meter = get_meter(__name__)

# Metrics
chat_requests = meter.create_counter(
    "chat.requests.total",
    description="Total number of chat requests"
)
chat_duration = meter.create_histogram(
    "chat.request.duration",
    unit="s",
    description="Chat request duration in seconds"
)
chat_errors = meter.create_counter(
    "chat.errors.total",
    description="Total number of chat errors"
)

@router.post("/")
async def chat(request: ChatRequest, background_tasks: BackgroundTasks):
    """Handles chat sessions between a user and the AI assistant."""
    session_id = request.session_id or str(uuid.uuid4())
    
    chat_requests.add(1, {"source_lang": request.source_lang, "target_lang": request.target_lang})
    start = time.time()

    logger.info(
        f"Chat request received - session_id: {session_id}, user_id: {request.user_id}, "
        f"source_lang: {request.source_lang}, target_lang: {request.target_lang}, query: {request.query}"
    )

    # Get the message history
    history = await get_message_history(session_id)
    logger.debug(f"Retrieved message history for session {session_id} - length: {len(history)}")

    # Create suggestions for the session: 1, 3, 5, 7, ...
    if (len(history)+1) % 2 == 1:
        logger.debug(f"Creating suggestions for session {session_id}")
        background_tasks.add_task(create_suggestions, session_id, request.target_lang)

    # Manually manage span so it stays open through the entire streaming lifecycle.
    # Using `with` would close the span when StreamingResponse is returned (~5ms),
    # not when the streaming actually completes.
    span = tracer.start_span("chat_request")
    span.set_attribute("session.id", session_id)
    span.set_attribute("user.id", request.user_id)
    span.set_attribute("chat.source_lang", request.source_lang)
    span.set_attribute("chat.target_lang", request.target_lang)

    async def run_async():
        logger.debug(f"Generator function run_async created for session {session_id}")
        try:
            # Log the event loop state
            loop = asyncio.get_running_loop()
            logger.debug(f"Using event loop {id(loop)} for session {session_id}")

            logger.debug(f"Starting streaming response for session {session_id}")
            chunks_yielded = 0
            async for chunk in stream_chat_messages(
                query=request.query,
                session_id=session_id,
                source_lang=request.source_lang,
                target_lang=request.target_lang,
                user_id=request.user_id,
                history=history
            ):
                chunks_yielded += 1
                yield chunk

            duration = time.time() - start
            chat_duration.record(duration, {"source_lang": request.source_lang, "target_lang": request.target_lang})
            span.set_attribute("chat.duration_seconds", duration)
            span.set_attribute("chat.chunks_yielded", chunks_yielded)
            span.set_status(StatusCode.OK)
            logger.info(f"Completed streaming response for session {session_id} - total chunks: {chunks_yielded}")
        except Exception as e:
            chat_errors.add(1, {"source_lang": request.source_lang, "target_lang": request.target_lang})
            span.record_exception(e)
            span.set_status(StatusCode.ERROR, str(e))
            logger.error(f"Error during streaming for session {session_id}: {str(e)}")
            raise
        finally:
            span.end()

    logger.debug(f"Creating StreamingHttpResponse for session {session_id}")
    response = StreamingResponse(
        run_async(),
        media_type='text/event-stream; charset=utf-8',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )
    logger.debug(f"StreamingHttpResponse created for session {session_id}")
    return response
