import time
import uuid
from helpers.utils import get_logger
from fastapi import APIRouter, HTTPException
from app.models.requests import TranscribeRequest
from app.models.responses import TranscribeResponse
from app.core.telemetry import get_tracer, get_meter
from app.services.providers.transcription import get_transcription_provider, TranscriptionException

logger = get_logger(__name__)

router = APIRouter(prefix="/transcribe", tags=["transcribe"])

# OpenTelemetry instrumentation
tracer = get_tracer(__name__)
meter = get_meter(__name__)

# Metrics
transcribe_duration = meter.create_histogram(
    "transcribe.duration",
    unit="ms",
    description="Transcribe endpoint duration in milliseconds"
)
transcribe_errors = meter.create_counter(
    "transcribe.errors",
    description="Transcribe error count"
)

@router.post("/", response_model=TranscribeResponse)
async def transcribe(request: TranscribeRequest):
    """Handles transcription of audio using Azure Speech-to-Text service."""

    if not request.audio_content:
        raise HTTPException(status_code=400, detail="audio_content is required")

    with tracer.start_as_current_span("transcribe_request") as span:
        start = time.time()
        session_id = request.session_id or str(uuid.uuid4())
        lang_code = request.lang_code
        span.set_attribute("session.id", session_id)
        span.set_attribute("lang_code", lang_code)

        try:
            provider = get_transcription_provider()

            with tracer.start_as_current_span("transcribe_audio"):
                transcription = await provider.transcribe(request.audio_content, lang_code)
            logger.info(f"Transcription: {transcription}")

            duration_ms = (time.time() - start) * 1000
            transcribe_duration.record(duration_ms, {"lang_code": lang_code})
            span.set_attribute("transcribe.duration_ms", duration_ms)
            span.set_attribute("transcribe.text_length", len(transcription) if transcription else 0)

            return TranscribeResponse(
                status='success',
                text=transcription,
                lang_code=lang_code,
                session_id=session_id
            )
        except TranscriptionException as e:
            transcribe_errors.add(1, {"error_type": type(e).__name__})
            span.record_exception(e)
            span.set_attribute("error", True)
            logger.error(f"Transcription error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")
        except Exception as e:
            transcribe_errors.add(1, {"error_type": type(e).__name__})
            span.record_exception(e)
            span.set_attribute("error", True)
            logger.error(f"Transcription error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")
