from __future__ import annotations

from dataclasses import dataclass

import structlog

from app.core.config import Settings
from app.core.exceptions import ExtractError, FetchError
from app.ingestion.fetcher import FetchedDocument, fetch_with_ssl_fallback
from app.ingestion.html_cleaner import (
    clean_extracted_text,
    extract_title,
    find_content_iframe_urls,
    html_to_readable_text,
    parse_html,
    title_from_text,
)

logger = structlog.get_logger(__name__)

MIN_TEXT_CHARS = 40
MAX_IFRAME_HOPS = 2


@dataclass(frozen=True, slots=True)
class ExtractedDocument:
    url: str
    final_url: str
    title: str | None
    text: str
    content_type: str


async def extract_from_url(url: str, settings: Settings) -> ExtractedDocument:
    insecure_hosts: set[str] = set()
    fetched = await fetch_with_ssl_fallback(url, settings, insecure_hosts)
    document = await _extract_fetched(
        fetched,
        settings,
        hops_remaining=MAX_IFRAME_HOPS,
        insecure_hosts=insecure_hosts,
    )
    result = ExtractedDocument(
        url=url,
        final_url=document.final_url,
        title=document.title,
        text=document.text,
        content_type=document.content_type,
    )
    logger.info(
        "document_extracted",
        url=result.url,
        final_url=result.final_url,
        title=result.title,
        chars=len(result.text),
    )
    return result


async def _extract_fetched(
    fetched: FetchedDocument,
    settings: Settings,
    hops_remaining: int,
    insecure_hosts: set[str],
    visited: set[str] | None = None,
) -> ExtractedDocument:
    visited = visited or set()
    visited.add(fetched.final_url)

    if fetched.content_type == "text/plain":
        text = clean_extracted_text(fetched.text)
        if len(text) < MIN_TEXT_CHARS:
            raise ExtractError("No readable text found at URL")
        return ExtractedDocument(
            url=fetched.requested_url,
            final_url=fetched.final_url,
            title=None,
            text=text,
            content_type=fetched.content_type,
        )

    soup = parse_html(fetched.text)
    page_title = extract_title(soup)
    candidates = [_candidate_from_html(fetched, page_title)]

    if hops_remaining > 0:
        for iframe_url in find_content_iframe_urls(soup, fetched.final_url):
            if iframe_url in visited:
                continue
            try:
                iframe_doc = await fetch_with_ssl_fallback(iframe_url, settings, insecure_hosts)
                nested = await _extract_fetched(
                    iframe_doc,
                    settings,
                    hops_remaining=hops_remaining - 1,
                    insecure_hosts=insecure_hosts,
                    visited=visited,
                )
                candidates.append(nested)
                logger.info("document_iframe_followed", url=iframe_url, chars=len(nested.text))
            except (FetchError, ExtractError) as exc:
                logger.warning("document_iframe_skipped", url=iframe_url, error=str(exc))

    chosen = max(candidates, key=lambda item: len(item.text))
    if len(chosen.text) < MIN_TEXT_CHARS:
        raise ExtractError("No readable text found at URL")

    title = title_from_text(chosen.text, chosen.title or page_title)
    return ExtractedDocument(
        url=fetched.requested_url,
        final_url=chosen.final_url,
        title=title,
        text=chosen.text,
        content_type=chosen.content_type,
    )


def _candidate_from_html(fetched: FetchedDocument, page_title: str | None) -> ExtractedDocument:
    return ExtractedDocument(
        url=fetched.requested_url,
        final_url=fetched.final_url,
        title=page_title,
        text=html_to_readable_text(fetched.text),
        content_type=fetched.content_type,
    )

