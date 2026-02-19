import time
import uuid
import base64
from helpers.tts import text_to_speech_bhashini
from helpers.utils import get_logger
from fastapi import APIRouter, HTTPException
from app.models.requests import TTSRequest
from app.models.responses import TTSResponse
from app.core.telemetry import get_tracer, get_meter

logger = get_logger(__name__)

router = APIRouter(prefix="/tts", tags=["tts"])

# OpenTelemetry instrumentation
tracer = get_tracer(__name__)
meter = get_meter(__name__)

# Metrics
tts_request_duration = meter.create_histogram(
    "tts.request.duration",
    unit="ms",
    description="TTS endpoint duration in milliseconds"
)
tts_errors = meter.create_counter(
    "tts.errors",
    description="TTS error count"
)

@router.post("/", response_model=TTSResponse)
async def tts(request: TTSRequest):
    """Handles text to speech conversion using Bhashini service."""

    if not request.text:
        raise HTTPException(status_code=400, detail="text is required")

    with tracer.start_as_current_span("tts_request") as span:
        start = time.time()
        session_id = request.session_id or str(uuid.uuid4())
        span.set_attribute("session.id", session_id)
        span.set_attribute("lang_code", request.lang_code)
        span.set_attribute("text.length", len(request.text))

        try:
            with tracer.start_as_current_span("text_to_speech"):
                audio_data = text_to_speech_bhashini(
                    request.text, request.lang_code, gender='female', sampling_rate=8000
                )

            # Base64 encode the binary audio data for JSON serialization
            if isinstance(audio_data, bytes):
                audio_data = base64.b64encode(audio_data).decode('utf-8')

            duration_ms = (time.time() - start) * 1000
            tts_request_duration.record(duration_ms, {"lang_code": request.lang_code})
            span.set_attribute("tts.duration_ms", duration_ms)

            return TTSResponse(
                status='success',
                audio_content=audio_data,
                session_id=session_id
            )
        except Exception as e:
            tts_errors.add(1, {"error_type": type(e).__name__, "lang_code": request.lang_code})
            span.record_exception(e)
            span.set_attribute("error", True)
            logger.error(f"TTS error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"TTS failed: {str(e)}")
