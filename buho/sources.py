"""Descarga y lectura de las fuentes de noticias.

Aquí solo se obtienen los items tal como vienen; limpiar, clasificar y agrupar
es trabajo de news.py.
"""

import html
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import feedparser
import httpx

from buho.config import Source

USER_AGENT = "BuhoBot/1.0 (uso personal)"
GNEWS_URL = "https://news.google.com/rss/search"
GNEWS_PARAMS = {"hl": "es-419", "gl": "MX", "ceid": "MX:es-419"}
STEAM_URL = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"
STEAM_OFFICIAL_FEED = "steam_community_announcements"
MAX_PARALLEL_DOWNLOADS = 3


@dataclass
class RawItem:
    source: str
    ext_id: str
    url: str
    title: str
    outlet: str
    summary: str = ""
    author: str = ""
    published_at: datetime | None = None  # UTC


@dataclass
class FetchResult:
    status: int  # 200, o 304 si no cambió desde la última descarga
    body: bytes
    etag: str | None
    last_modified: str | None


def new_client() -> httpx.AsyncClient:
    # El pool de httpx limita las descargas simultáneas; pool=None deja esperar
    # turno sin que cuente para el timeout de cada fuente.
    return httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        limits=httpx.Limits(max_connections=MAX_PARALLEL_DOWNLOADS),
    )


def source_url(src: Source) -> str:
    if src.type == "gnews":
        return f"{GNEWS_URL}?{urlencode({'q': src.query, **GNEWS_PARAMS})}"
    if src.type == "steam":
        return f"{STEAM_URL}?{urlencode({'appid': src.appid, 'count': 10, 'maxlength': 300})}"
    assert src.url is not None
    return src.url


async def fetch(
    client: httpx.AsyncClient,
    src: Source,
    etag: str | None = None,
    last_modified: str | None = None,
) -> FetchResult:
    headers = {}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    response = await client.get(
        source_url(src), headers=headers, timeout=httpx.Timeout(src.timeout_seconds, pool=None)
    )
    if response.status_code != 304:
        response.raise_for_status()
    return FetchResult(
        response.status_code,
        response.content,
        response.headers.get("etag"),
        response.headers.get("last-modified"),
    )


def parse(src: Source, body: bytes) -> list[RawItem]:
    if src.type == "steam":
        return parse_steam(src, body)
    if src.type == "unison":
        return parse_unison(src, body)
    return parse_feed(src, body)


def parse_feed(src: Source, body: bytes) -> list[RawItem]:
    feed = feedparser.parse(body)
    if feed.bozo and not feed.entries:
        raise ValueError(f"feed ilegible: {feed.bozo_exception}")
    items = []
    for entry in feed.entries:
        link = entry.get("link", "")
        title = entry.get("title", "").strip()
        outlet = src.name
        if src.type == "gnews":
            # Google News pone el medio en <source> y lo repite al final del título.
            outlet = entry.get("source", {}).get("title") or outlet
            title = title.removesuffix(f" - {outlet}").strip()
        parsed = entry.get("published_parsed") or entry.get("updated_parsed")
        items.append(
            RawItem(
                source=src.id,
                ext_id=entry.get("id") or link,
                url=link,
                title=title,
                outlet=outlet,
                summary=entry.get("summary", ""),
                author=entry.get("author", ""),
                published_at=datetime(*parsed[:6], tzinfo=UTC) if parsed else None,
            )
        )
    return items


def parse_steam(src: Source, body: bytes) -> list[RawItem]:
    news = json.loads(body)["appnews"]["newsitems"]
    return [
        RawItem(
            source=src.id,
            ext_id=str(n["gid"]),
            url=n["url"],
            title=n["title"].strip(),
            outlet=src.name,
            summary=n.get("contents", ""),
            author=n.get("author", ""),
            published_at=datetime.fromtimestamp(n["date"], UTC),
        )
        for n in news
        if n.get("feedname") == STEAM_OFFICIAL_FEED  # fuera notas de prensa externas
    ]


# El listado de https://www.unison.mx/noticias-anteriores/ no es WordPress. Cada nota es:
#   <a href=".../nota/?idnoti=N"> <i ...></i>Título, <span ...> 25 de septiembre de 2026</span></a>
UNISON_LIST_MARKER = 'class="noti-anteriores"'
UNISON_ITEM = re.compile(
    r'<a href="(?P<url>[^"]*/nota/\?idnoti=(?P<id>\d+))"[^>]*>(?P<title>.*?)'
    r"<span[^>]*>\s*(?P<day>\d{1,2}) de (?P<month>[a-z]+) de (?P<year>\d{4})\s*</span>",
    re.S | re.I,
)
UNISON_TZ = ZoneInfo("America/Hermosillo")
MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
          "septiembre", "octubre", "noviembre", "diciembre"]  # fmt: skip


def parse_unison(src: Source, body: bytes) -> list[RawItem]:
    text = body.decode("utf-8", errors="replace")
    if UNISON_LIST_MARKER not in text:
        raise ValueError("no encontré el listado de noticias: ¿cambió el HTML de la página?")
    items = []
    for m in UNISON_ITEM.finditer(text):
        title = html.unescape(re.sub(r"<[^>]+>", "", m["title"])).strip().rstrip(",").strip()
        # El sitio solo da la fecha: se toma la medianoche local de ese día.
        day = datetime(
            int(m["year"]), MONTHS.index(m["month"].lower()) + 1, int(m["day"]), tzinfo=UNISON_TZ
        )
        items.append(
            RawItem(
                source=src.id,
                ext_id=m["id"],
                url=html.unescape(m["url"]),
                title=title,
                outlet=src.name,
                published_at=day.astimezone(UTC),
            )
        )
    return items
