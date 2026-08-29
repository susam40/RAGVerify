from app.ingestion.html_cleaner import (
    clean_extracted_text,
    find_content_iframe_urls,
    html_to_readable_text,
    normalize_text,
    parse_html,
    title_from_text,
)


def test_html_to_readable_text_strips_chrome_and_keeps_body() -> None:
    html = """
    <html>
      <head><title>Mevzuat Bilgi Sistemi</title></head>
      <body>
        <nav>Menü Kanunlar Yönetmelikler</nav>
        <header>Logo</header>
        <article>
          <h1>7068 Sayılı Kanun</h1>
          <p>MADDE 1- Bu Kanunun amacı disiplinsizlik ve cezaları düzenlemektir.</p>
          <script>window.ads = true;</script>
          <p>MADDE 2- Bu Kanun emniyet personeli hakkında uygulanır.</p>
        </article>
        <footer>Çerez politikası</footer>
      </body>
    </html>
    """

    text = html_to_readable_text(html)

    assert "Menü Kanunlar" not in text
    assert "Çerez politikası" not in text
    assert "window.ads" not in text
    assert "MADDE 1- Bu Kanunun amacı disiplinsizlik ve cezaları düzenlemektir." in text
    assert "MADDE 2- Bu Kanun emniyet personeli hakkında uygulanır." in text
    assert "7068 Sayılı Kanun" in text


def test_normalize_text_collapses_whitespace() -> None:
    raw = "MADDE 1-\n\n\n  Bu   Kanun\u00a0amacıdır.  \n\n\nMADDE 2-\n"
    assert normalize_text(raw) == "MADDE 1-\n\nBu Kanun amacıdır.\n\nMADDE 2-"


def test_find_same_site_content_iframe() -> None:
    html = """
    <html><body>
      <iframe src="/anasayfa/MevzuatFihristDetayIframe?MevzuatNo=7068"></iframe>
      <iframe src="https://doubleclick.net/ad"></iframe>
    </body></html>
    """
    soup = parse_html(html)
    urls = find_content_iframe_urls(
        soup,
        "https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=7068",
    )
    assert urls == [
        "https://www.mevzuat.gov.tr/anasayfa/MevzuatFihristDetayIframe?MevzuatNo=7068"
    ]


def test_title_skips_generic_portal_name() -> None:
    text = "7068 Sayılı Kanun\nMADDE 1- Amaç"
    assert title_from_text(text, "Mevzuat Bilgi Sistemi") == "7068 Sayılı Kanun"


def test_clean_extracted_text_removes_word_wrap_and_footnote_marks() -> None:
    raw = """
TÜRKİYE CUMHURİYETİ
ANAYASASI
[1]

[2]

Kanun
Numarası :
2709

I. Devletin şekli

Madde 1 –
Türkiye
Devleti bir Cumhuriyettir.

II. Cumhuriyetin
nitelikleri

IV.
Değiştirilemeyecek hükümler

Madde
2 –
Türkiye Cumhuriyeti, toplumun huzuru,
milli dayanışma ve adalet anlayışı içinde, demokratik bir hukuk Devletidir.
(…)
[7]

[117]

1/8/2010 tarihli ve 27659 sayılı Resmî Gazete’de yayımlanan karar.
"""
    text = clean_extracted_text(raw)

    assert "[1]" not in text
    assert "[2]" not in text
    assert "[7]" not in text
    assert "Kanun Numarası : 2709" in text
    assert "Madde 1 – Türkiye Devleti bir Cumhuriyettir." in text
    assert "Madde 2 – Türkiye Cumhuriyeti, toplumun huzuru, milli dayanışma" in text
    assert "II. Cumhuriyetin nitelikleri" in text
    assert "IV. Değiştirilemeyecek hükümler" in text
    assert "Cumhuriyettir.\nII. Cumhuriyetin" in text
    assert "[117] 1/8/2010 tarihli" in text
    assert "Devletidir. (…)" in text
