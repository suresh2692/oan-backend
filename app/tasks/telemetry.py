import json
import asyncpg
from typing import Dict, Optional
from helpers.utils import get_logger

logger = get_logger(__name__)

_pool: Optional[asyncpg.Pool] = None


async def init_telemetry_pool(dsn: str):
    """Initialize asyncpg pool to telemetry DB. Called at startup."""
    global _pool
    _pool = await asyncpg.create_pool(dsn, min_size=2, max_size=5)
    logger.info("Telemetry DB pool initialized")


async def close_telemetry_pool():
    """Close pool. Called at shutdown."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def send_telemetry(telemetry_data: Dict) -> Dict:
    """
    Insert telemetry events into winston_logs table.
    Drop-in replacement for bharat-oan-api's HTTP POST version.

    The message column must be a JSON string with an events array.
    sync_status=0 means unprocessed (processor picks these up every 5 min).
    """
    if not _pool:
        logger.warning("Telemetry pool not initialized, skipping")
        return {"status": "skipped"}

    try:
        events = telemetry_data.get("events", [])
        message_json = json.dumps({"events": events})

        await _pool.execute(
            "INSERT INTO winston_logs (level, message, timestamp, sync_status) "
            "VALUES ($1, $2, NOW(), $3)",
            "info", message_json, 0
        )
        return {"status": "inserted", "event_count": len(events)}
    except Exception as e:
        logger.error(f"Telemetry insert failed: {e}")
        return {"status": "error", "error": str(e)}
