from __future__ import annotations

import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from app.ingestion.fetcher import resolve_url

DROP_TAGS = (
    "script",
    "style",
    "noscript",
    "svg",
    "canvas",
    "nav",
    "header",
    "footer",
    "aside",
    "form",
    "button",
    "input",
    "select",
    "textarea",
    "iframe",
    "object",
    "embed",
    "link",
    "meta",
)

MAIN_SELECTORS = (
    "article",
    "main",
    "[role=main]",
    "#content",
    "#main",
    "#mevzuatDetay",
    ".mevzuat",
    "#section-to-print",
)

SKIP_IFRAME_HOSTS = (
    "doubleclick.net",
    "googletagmanager.com",
    "google.com",
    "facebook.com",
    "twitter.com",
    "youtube.com",
)

_SPACE_RE = re.compile(r"[ \t\u00a0\u200b]+")
_FOOTNOTE_MARK = re.compile(r"^\[(\d+)\]$")
_ORPHAN_PUNCT = re.compile(r"^[:()\[\]–—\-./]+$")
_ARTICLE_WORD = re.compile(r"^(?:Madde|MADDE|GEÇİCİ\s+MADDE)$", re.IGNORECASE)
_ARTICLE_HEADER = re.compile(
    r"^(?:Madde|MADDE|GEÇİCİ\s+MADDE)(?:\s+\d+)?\s*[–\-]?\s*$",
    re.IGNORECASE,
)
_ARTICLE_NUMBER = re.compile(r"^\d+\s*[–\-]")
_CLAUSE_START = re.compile(r"^(?:\([0-9]+\)|[a-zçğıöşü]\))")
_SECTION_ORDINAL = re.compile(
    r"^(?:BİRİNCİ|İKİNCİ|ÜÇÜNCÜ|DÖRDÜNCÜ|BEŞİNCİ|ALTINCI|YEDİNCİ|"
    r"SEKİZİNCİ|DOKUZUNCU|ONUNCU|ON\s+BİRİNCİ|ON\s+İKİNCİ|"
    r"ON\s+ÜÇÜNCÜ|ON\s+DÖRDÜNCÜ)\s+(?:KISIM|BÖLÜM)\b",
    re.IGNORECASE,
)
_ROMAN_SECTION = re.compile(r"^[IVXLCDM]+\.\s+\S+")
_INCOMPLETE_PREFIX = re.compile(r"^\((?:Ek|Değişik|Mülga|İptal)?$", re.IGNORECASE)
_INCOMPLETE_ENUM = re.compile(r"^(?:[IVXLCDM]+\.|[A-ZÇĞİÖŞÜ]\.|[0-9]+\.|[A-ZÇĞİÖŞÜ]\))$")
_TITLE_NOISE = {
    "mevzuat bilgi sistemi",
    "untitled",
    "about",
}


def parse_html(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def extract_title(soup: BeautifulSoup) -> str | None:
    og = soup.find("meta", attrs={"property": "og:title"})
    if isinstance(og, Tag):
        content = og.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()

    if soup.title and soup.title.string:
        title = soup.title.string.strip()
        if title:
            return title

    heading = soup.find(["h1", "h2"])
    if isinstance(heading, Tag):
        text = heading.get_text(" ", strip=True)
        if text:
            return text
    return None


def find_content_iframe_urls(soup: BeautifulSoup, base_url: str, limit: int = 3) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for iframe in soup.find_all("iframe"):
        if not isinstance(iframe, Tag):
            continue
        src = iframe.get("src")
        if not isinstance(src, str) or not src.strip():
            continue
        if src.startswith(("javascript:", "data:", "about:")):
            continue

        absolute = resolve_url(base_url, src.strip())
        if absolute in seen or not _same_site(base_url, absolute):
            continue
        if _is_ad_host(absolute):
            continue

        seen.add(absolute)
        urls.append(absolute)
        if len(urls) >= limit:
            break
    return urls


def html_to_readable_text(html: str) -> str:
    soup = parse_html(html)
    return soup_to_readable_text(soup)


def soup_to_readable_text(soup: BeautifulSoup) -> str:
    root = _select_main(soup)
    if root is None:
        return ""

    for tag in root.find_all(DROP_TAGS):
        tag.decompose()

    for br in root.find_all("br"):
        br.replace_with("\n")

    raw = root.get_text("\n")
    return clean_extracted_text(raw)


def title_from_text(text: str, fallback: str | None) -> str | None:
    if fallback and fallback.strip().lower() not in _TITLE_NOISE:
        return fallback.strip()

    for line in text.splitlines():
        candidate = line.strip()
        if 8 <= len(candidate) <= 180 and not candidate.lower().startswith("madde "):
            return candidate
    return fallback


def clean_extracted_text(text: str) -> str:
    return reflow_wrapped_text(normalize_text(text))


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized: list[str] = []
    previous_blank = False

    for raw_line in text.split("\n"):
        line = _SPACE_RE.sub(" ", raw_line).strip()
        if not line:
            if normalized and not previous_blank:
                normalized.append("")
                previous_blank = True
            continue
        normalized.append(line)
        previous_blank = False

    return "\n".join(normalized).strip()


def reflow_wrapped_text(text: str) -> str:
    """Join Word-exported visual line breaks; keep article/section boundaries."""
    out: list[str] = []
    pending_blank = False
    pending_footnote: str | None = None

    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            pending_blank = True
            continue

        if _FOOTNOTE_MARK.fullmatch(line):
            pending_footnote = line
            continue
        if line in {"(…)", "(...)"}:
            if out:
                out[-1] = f"{out[-1]} {line}"
            pending_blank = False
            continue
        if line == ":":
            if out:
                out[-1] = f"{out[-1]} :"
            pending_blank = False
            continue
        if _ORPHAN_PUNCT.fullmatch(line):
            continue
        if re.fullmatch(r"\d{1,4}", line) and not (out and out[-1].endswith(":")):
            continue
        if pending_footnote:
            if _is_footnote_body(line):
                line = f"{pending_footnote} {line}"
            pending_footnote = None

        if not out:
            out.append(line)
            pending_blank = False
            continue

        prev = out[-1]
        joinable = _should_join(prev, line)
        if pending_blank and not _can_join_across_blank(prev):
            joinable = False

        if joinable:
            out[-1] = _join_lines(prev, line)
        else:
            out.append(line)
        pending_blank = False

    return "\n".join(out).strip()


def _is_footnote_body(line: str) -> bool:
    if len(line) >= 40:
        return True
    return bool(re.match(r"^\d{1,2}/\d{1,2}/\d{4}", line))


def _is_all_caps_heading(line: str) -> bool:
    letters = [char for char in line if char.isalpha()]
    return bool(letters) and all(char.isupper() for char in letters) and len(line) <= 80


def _is_new_block(line: str) -> bool:
    if _ARTICLE_WORD.fullmatch(line) or _ARTICLE_HEADER.fullmatch(line):
        return True
    if _ARTICLE_NUMBER.match(line):
        return True
    if _CLAUSE_START.match(line):
        return True
    if _SECTION_ORDINAL.match(line):
        return True
    if line.casefold() in {"başlangıç", "geçici maddeler"}:
        return True
    if _ROMAN_SECTION.match(line):
        return True
    return False


def _can_join_across_blank(prev: str) -> bool:
    return bool(
        _ARTICLE_HEADER.fullmatch(prev)
        or _ARTICLE_WORD.fullmatch(prev)
        or _INCOMPLETE_ENUM.fullmatch(prev)
        or prev.endswith(":")
        or _INCOMPLETE_PREFIX.fullmatch(prev)
    )


def _should_join(prev: str, nxt: str) -> bool:
    if _ARTICLE_HEADER.fullmatch(prev) or _ARTICLE_WORD.fullmatch(prev):
        return True
    if _INCOMPLETE_ENUM.fullmatch(prev):
        return True
    if _INCOMPLETE_PREFIX.fullmatch(prev) or prev.endswith("("):
        return True
    if prev.endswith((":", ",", ";")):
        return not _is_new_block(nxt)
    if _is_new_block(nxt):
        return False
    if _is_all_caps_heading(prev) and _is_all_caps_heading(nxt):
        return False
    if prev.endswith((".", "?", "!")) and (nxt[0].isupper() or _is_new_block(nxt)):
        return False
    return True


def _join_lines(prev: str, nxt: str) -> str:
    if prev.endswith("-") and len(prev) >= 2 and prev[-2].isalpha() and nxt[:1].islower():
        return prev[:-1] + nxt
    return f"{prev} {nxt}"


def _select_main(soup: BeautifulSoup) -> Tag | None:
    for selector in MAIN_SELECTORS:
        node = soup.select_one(selector)
        if isinstance(node, Tag) and node.get_text(strip=True):
            return node
    return soup.body if soup.body else soup


def _same_site(base_url: str, target_url: str) -> bool:
    base = urlparse(base_url)
    target = urlparse(target_url)
    if target.scheme not in {"http", "https"}:
        return False
    return (base.hostname or "").lower() == (target.hostname or "").lower()


def _is_ad_host(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == blocked or host.endswith(f".{blocked}") for blocked in SKIP_IFRAME_HOSTS)
