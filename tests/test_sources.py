import asyncio
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from buho.config import Source
from buho.sources import fetch, parse, source_url

FIXTURES = Path(__file__).parent / "fixtures"


def src(**fields) -> Source:
    base = {"id": "test", "name": "Fuente", "category": "hermosillo"}
    return Source.model_validate(base | fields)


def parse_fixture(source: Source, name: str):
    return parse(source, (FIXTURES / name).read_bytes())


def test_rss_keeps_only_basic_fields() -> None:
    items = parse_fixture(
        src(type="rss", url="https://x", name="El Imparcial"), "elimparcial_sonora.xml"
    )
    assert len(items) == 5
    first = items[0]
    assert first.title.startswith("Polo se acerca a Hermosillo")
    assert first.url.startswith("https://www.elimparcial.com/son/hermosillo/")
    assert first.ext_id == first.url  # El Imparcial usa el link como guid
    assert first.author == "Redacción GH"
    assert first.outlet == "El Imparcial"
    assert first.published_at == datetime(2026, 9, 28, 3, 19, 58, tzinfo=UTC)
    assert any("Universidad de Sonora" in i.title for i in items)


def test_gnews_takes_outlet_from_source_and_strips_it_from_title() -> None:
    items = parse_fixture(src(type="gnews", query="Hermosillo when:1d"), "gnews_hermosillo.xml")
    assert len(items) == 5
    first = items[0]
    assert first.outlet == "El Imparcial"
    assert first.title.endswith("rachas de hasta 70 km/h: Climahillo")
    assert first.url.startswith("https://news.google.com/rss/articles/")  # sin resolver
    assert all(not i.title.endswith(f" - {i.outlet}") for i in items)


def test_gnews_url_is_urlencoded() -> None:
    url = source_url(src(type="gnews", query='"Universidad de Sonora" OR Unison when:1d'))
    assert url == (
        "https://news.google.com/rss/search?q=%22Universidad+de+Sonora%22+OR+Unison+when%3A1d"
        "&hl=es-419&gl=MX&ceid=MX%3Aes-419"
    )


@pytest.mark.parametrize(("name", "count"), [("ps_latam.xml", 3), ("nintendolife.xml", 3)])
def test_game_feeds_parse(name: str, count: int) -> None:
    items = parse_fixture(src(type="rss", url="https://x", category="videojuegos"), name)
    assert len(items) == count
    assert all(i.title and i.url.startswith("https://") and i.published_at for i in items)


def test_steam_keeps_only_official_announcements() -> None:
    items = parse_fixture(
        src(type="steam", appid=2246340, category="videojuegos"), "steam_mhwilds.json"
    )
    assert [i.title for i in items] == [
        "Khezu Stretches into Monster Hunter Wilds: Ascendance!",
        "Notice on Changes Coming to Character Edits",
        "The Elder Dragon Teostra Blazes into Monster Hunter Wilds: Ascendance!",
    ]
    assert all(i.ext_id.isdigit() for i in items)


def test_unison_listing() -> None:
    items = parse_fixture(
        src(type="unison", url="https://x", category="unison"), "unison_noticias.html"
    )
    assert len(items) == 6
    first = items[0]
    assert first.ext_id == "38864"
    assert first.url == "https://www.unison.mx/nota/?idnoti=38864"
    assert (
        first.title
        == "Rinde protesta Leticia María González Velásquez como jefa del DCEA en Unison Navojoa"
    )
    # 25 de septiembre, medianoche en Hermosillo (UTC−7)
    assert first.published_at == datetime(2026, 9, 25, 7, 0, tzinfo=UTC)


def test_unison_detects_html_change() -> None:
    with pytest.raises(ValueError, match="cambió el HTML"):
        parse(src(type="unison", url="https://x", category="unison"), b"<html>nada</html>")


def _fetch_with(handler, **kwargs):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch(client, src(type="rss", url="https://feed.test/rss"), **kwargs)

    return asyncio.run(run())


def test_fetch_sends_conditional_headers_and_accepts_304() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return httpx.Response(304)

    result = _fetch_with(handler, etag='W/"abc"', last_modified="Mon, 28 Sep 2026 04:37:59 GMT")
    assert result.status == 304
    assert seen["if-none-match"] == 'W/"abc"'
    assert seen["if-modified-since"] == "Mon, 28 Sep 2026 04:37:59 GMT"


def test_fetch_returns_validators_and_raises_on_errors() -> None:
    ok = _fetch_with(lambda r: httpx.Response(200, content=b"<rss/>", headers={"ETag": '"e1"'}))
    assert (ok.status, ok.body, ok.etag) == (200, b"<rss/>", '"e1"')
    with pytest.raises(httpx.HTTPStatusError):
        _fetch_with(lambda r: httpx.Response(503))
