import asyncio
import json
from pathlib import Path

import httpx
import structlog

from app.core.config import Settings

logger = structlog.get_logger(__name__)

INDEX_MAPPING_PATH = Path("/app/infrastructure/opensearch/index_rag_documents.json")
LOCAL_INDEX_MAPPING_PATH = (
    Path(__file__).resolve().parents[3] / "infrastructure" / "opensearch" / "index_rag_documents.json"
)


def _load_index_body() -> dict:
    path = INDEX_MAPPING_PATH if INDEX_MAPPING_PATH.exists() else LOCAL_INDEX_MAPPING_PATH
    return json.loads(path.read_text(encoding="utf-8"))


async def ping_opensearch(settings: Settings) -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(settings.opensearch_url)
            return response.status_code == 200
    except httpx.HTTPError:
        return False


async def ensure_index(settings: Settings) -> None:
    body = _load_index_body()
    last_error: Exception | None = None

    for attempt in range(1, 16):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                exists = await client.head(f"{settings.opensearch_url}/{settings.opensearch_index}")
                if exists.status_code == 200:
                    logger.info(
                        "opensearch_index_exists",
                        index=settings.opensearch_index,
                    )
                    return

                created = await client.put(
                    f"{settings.opensearch_url}/{settings.opensearch_index}",
                    json=body,
                )
                created.raise_for_status()
                logger.info(
                    "opensearch_index_created",
                    index=settings.opensearch_index,
                    status_code=created.status_code,
                )
                return
        except (httpx.HTTPError, OSError) as exc:
            last_error = exc
            logger.warning(
                "opensearch_index_retry",
                attempt=attempt,
                error=str(exc),
            )
            await asyncio.sleep(2)

    raise RuntimeError(f"OpenSearch index bootstrap failed: {last_error}")
