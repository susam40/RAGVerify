from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_address
from urllib.parse import urljoin, urlparse

import certifi
import httpx
import structlog

from app.core.config import Settings
from app.core.exceptions import FetchError

logger = structlog.get_logger(__name__)

ALLOWED_SCHEMES = {"http", "https"}
BLOCKED_HOSTS = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
}
RETRYABLE_STATUS = {429, 502, 503, 504}
ALLOWED_CONTENT_TYPES = {
    "text/html",
    "application/xhtml+xml",
    "text/plain",
}

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}


@dataclass(frozen=True, slots=True)
class FetchedDocument:
    requested_url: str
    final_url: str
    content_type: str
    body: bytes
    text: str


def validate_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise FetchError("Only http and https URLs are supported", status_code=400)

    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise FetchError("URL host is required", status_code=400)
    if host in BLOCKED_HOSTS or host.endswith(".localhost"):
        raise FetchError("URL host is not allowed", status_code=400)

    try:
        address = ip_address(host)
    except ValueError:
        return
    if not address.is_global:
        raise FetchError("URL host is not allowed", status_code=400)


def create_http_client(settings: Settings, verify: bool | str) -> httpx.AsyncClient:
    timeout = httpx.Timeout(
        settings.fetch_timeout_seconds,
        connect=settings.fetch_connect_timeout_seconds,
    )
    return httpx.AsyncClient(
        headers=DEFAULT_HEADERS,
        timeout=timeout,
        follow_redirects=True,
        verify=verify,
        max_redirects=5,
    )


def _media_type(content_type: str) -> str:
    return content_type.split(";", 1)[0].strip().lower()


def _is_ssl_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    return "certificate" in message or "ssl" in message


def _decode_body(response: httpx.Response) -> str:
    # Word-exported pages often declare windows-1254 in <meta> while the
    # HTTP body is UTF-8. Prefer the transport encoding, never the HTML meta.
    encoding = response.charset_encoding or "utf-8"
    try:
        return response.content.decode(encoding)
    except UnicodeDecodeError:
        return response.content.decode("utf-8", errors="replace")


async def _read_limited(response: httpx.Response, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > max_bytes:
            raise FetchError("Response exceeds maximum allowed size", status_code=413)
        chunks.append(chunk)
    return b"".join(chunks)


async def _send(
    client: httpx.AsyncClient,
    url: str,
    settings: Settings,
) -> httpx.Response:
    last_error: Exception | None = None
    attempts = settings.fetch_max_retries + 1

    for attempt in range(1, attempts + 1):
        try:
            request = client.build_request("GET", url)
            response = await client.send(request, stream=True)
            try:
                if response.status_code in RETRYABLE_STATUS and attempt < attempts:
                    await response.aread()
                    last_error = FetchError(
                        f"Upstream returned HTTP {response.status_code}",
                        status_code=502,
                    )
                    continue
                if response.status_code >= 400:
                    raise FetchError(
                        f"Upstream returned HTTP {response.status_code}",
                        status_code=502,
                    )
                body = await _read_limited(response, settings.fetch_max_bytes)
                headers = httpx.Headers(response.headers)
                headers.pop("content-encoding", None)
                headers.pop("content-length", None)
                headers.pop("transfer-encoding", None)
                return httpx.Response(
                    status_code=response.status_code,
                    headers=headers,
                    content=body,
                    request=response.request,
                    extensions=response.extensions,
                    default_encoding=response.charset_encoding or "utf-8",
                )
            finally:
                await response.aclose()
        except FetchError:
            raise
        except httpx.TimeoutException as exc:
            last_error = FetchError("Request timed out while fetching URL", status_code=504)
            if attempt >= attempts:
                raise last_error from exc
        except httpx.HTTPError as exc:
            if _is_ssl_error(exc):
                raise FetchError(f"Failed to fetch URL: {exc}", status_code=502) from exc
            last_error = exc
            if attempt >= attempts:
                break

    if isinstance(last_error, FetchError):
        raise last_error
    raise FetchError(f"Failed to fetch URL: {last_error}", status_code=502) from last_error


async def fetch_url(url: str, settings: Settings, client: httpx.AsyncClient) -> FetchedDocument:
    validate_public_url(url)

    try:
        response = await _send(client, url, settings)
    except FetchError:
        raise
    except httpx.HTTPError as exc:
        raise FetchError(f"Failed to fetch URL: {exc}", status_code=502) from exc

    content_type = _media_type(response.headers.get("content-type", "text/html"))
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise FetchError(
            f"Unsupported content type: {content_type or 'unknown'}",
            status_code=415,
        )

    text = response.text if content_type == "text/plain" else _decode_body(response)
    final_url = str(response.url)
    validate_public_url(final_url)

    logger.info(
        "document_fetched",
        url=url,
        final_url=final_url,
        status_code=response.status_code,
        content_type=content_type,
        bytes=len(response.content),
    )
    return FetchedDocument(
        requested_url=url,
        final_url=final_url,
        content_type=content_type,
        body=response.content,
        text=text,
    )


async def fetch_with_ssl_fallback(
    url: str,
    settings: Settings,
    insecure_hosts: set[str] | None = None,
) -> FetchedDocument:
    hosts = insecure_hosts if insecure_hosts is not None else set()
    host = (urlparse(url).hostname or "").lower()
    verify: bool | str = False if (not settings.fetch_ssl_verify or host in hosts) else certifi.where()
    try:
        async with create_http_client(settings, verify=verify) as client:
            return await fetch_url(url, settings, client)
    except FetchError as exc:
        if settings.fetch_ssl_verify and host not in hosts and _is_ssl_error(exc):
            hosts.add(host)
            logger.warning("ssl_verify_failed_retrying_insecure", url=url, error=str(exc))
            async with create_http_client(settings, verify=False) as client:
                return await fetch_url(url, settings, client)
        raise


def resolve_url(base_url: str, target: str) -> str:
    return urljoin(base_url, target)
