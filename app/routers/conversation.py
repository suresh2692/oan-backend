import time
from fastapi import APIRouter, WebSocket
import uuid
from app.services.pipecat_pipeline import run_pipecat_pipeline
from app.core.telemetry import get_tracer, get_meter
from helpers.utils import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/conv", tags=["conversation"])

# OpenTelemetry instrumentation
tracer = get_tracer(__name__)
meter = get_meter(__name__)

# Metrics
ws_connections = meter.create_up_down_counter(
    "websocket.connections.active",
    description="Number of active WebSocket connections"
)
ws_duration = meter.create_histogram(
    "websocket.session.duration",
    unit="s",
    description="WebSocket session duration in seconds"
)

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for voice conversation using Pipecat.

    Query Parameters:
        lang (str): Language code (en, am). Default: en
    """
    # Accept the connection first
    await websocket.accept()

    lang = websocket.query_params.get("lang", "en")
    session_id = str(uuid.uuid4())
    logger.info(f"WebSocket connection request (Pipecat) received with lang={lang} session={session_id}")

    with tracer.start_as_current_span("websocket_session") as span:
        span.set_attribute("session.lang", lang)
        span.set_attribute("session.id", session_id)
        ws_connections.add(1, {"lang": lang})
        start = time.time()

        try:
            await run_pipecat_pipeline(websocket, session_id, lang=lang)
        except Exception as e:
            span.record_exception(e)
            span.set_attribute("error", True)
            logger.error(f"Pipecat pipeline error: {e}")
            try:
                await websocket.close()
            except Exception:
                pass
        finally:
            ws_connections.add(-1, {"lang": lang})
            duration = time.time() - start
            ws_duration.record(duration, {"lang": lang, "session_id": session_id})
            span.set_attribute("session.duration_seconds", duration)

