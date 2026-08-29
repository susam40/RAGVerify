import asyncio

import pytest

from app.core.config import Settings
from app.core.exceptions import FetchError
from app.ingestion.fetcher import FetchedDocument, validate_public_url
from app.services.extract import extract_from_url


SHELL_HTML = """
<html>
  <head><title>Mevzuat Bilgi Sistemi</title></head>
  <body>
    <nav>Menü</nav>
    <iframe src="/anasayfa/MevzuatFihristDetayIframe?MevzuatNo=7068"></iframe>
  </body>
</html>
"""

IFRAME_HTML = """
<html>
  <body>
    <p><b>7068 Sayılı Kanun</b></p>
    <p>MADDE 1- Bu Kanunun amacı disiplinsizlik ve cezaları düzenlemektir.</p>
    <p>MADDE 2- Bu Kanun emniyet personeli hakkında uygulanır.</p>
  </body>
</html>
"""


def test_validate_public_url_rejects_localhost() -> None:
    with pytest.raises(FetchError):
        validate_public_url("http://localhost/secret")
    with pytest.raises(FetchError):
        validate_public_url("http://127.0.0.1/secret")
    with pytest.raises(FetchError):
        validate_public_url("file:///etc/passwd")


def test_extract_follows_content_iframe(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch(
        url: str,
        settings: Settings,
        insecure_hosts: set[str] | None = None,
    ) -> FetchedDocument:
        html = IFRAME_HTML if "MevzuatFihristDetayIframe" in url else SHELL_HTML
        return FetchedDocument(
            requested_url=url,
            final_url=url,
            content_type="text/html",
            body=html.encode(),
            text=html,
        )

    monkeypatch.setattr("app.services.extract.fetch_with_ssl_fallback", fake_fetch)

    result = asyncio.run(
        extract_from_url(
            "https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=7068",
            Settings(),
        )
    )

    assert result.title == "7068 Sayılı Kanun"
    assert "MADDE 1-" in result.text
    assert "MADDE 2-" in result.text
    assert "Menü" not in result.text
    assert "MevzuatFihristDetayIframe" in result.final_url


def test_extract_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from app.main import app
    from app.services.extract import ExtractedDocument

    async def fake_extract(url: str, settings: Settings) -> ExtractedDocument:
        return ExtractedDocument(
            url=url,
            final_url=url,
            title="7068 Sayılı Kanun",
            text="MADDE 1- Amaç\n\nMADDE 2- Kapsam",
            content_type="text/html",
        )

    monkeypatch.setattr("app.api.v1.documents.extract_from_url", fake_extract)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/documents/extract",
            json={"url": "https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=7068"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "7068 Sayılı Kanun"
    assert payload["char_count"] == len(payload["text"])
    assert payload["text"].startswith("MADDE 1-")
