import aiohttp
from enum import Enum


class AniListMediaType(str, Enum):
    Anime = "ANIME"
    Manga = "MANGA"


MEDIA_FIELDS = """
id
siteUrl
title { romaji english native }
description(asHtml: true)
genres
coverImage { large color }
format
averageScore
startDate { year month day }
type
"""

SEARCH_MEDIA_QUERY = f"""
query ($search: String!, $type: MediaType) {{
  Page(page: 1, perPage: 1) {{
    media(search: $search, type: $type, sort: SEARCH_MATCH) {{
      {MEDIA_FIELDS}
    }}
  }}
}}
"""

MEDIA_BY_ID_QUERY = f"""
query ($id: Int!, $type: MediaType) {{
  Media(id: $id, type: $type) {{
    {MEDIA_FIELDS}
  }}
}}
"""

AUTOCOMPLETE_QUERY = """
query ($search: String!, $type: MediaType) {
  Page(page: 1, perPage: 10) {
    media(search: $search, type: $type, sort: SEARCH_MATCH) {
      id
      format
      type
      startDate { year }
      title { romaji english native }
    }
  }
}
"""


def _normalize_media_type(media_type) -> str | None:
    if isinstance(media_type, AniListMediaType):
        return media_type.value
    if isinstance(media_type, str) and media_type:
        return media_type.upper()
    return None


async def _post_graphql(query: str, variables: dict) -> dict | None:
    timeout = aiohttp.ClientTimeout(total=10)
    payload = {"query": query, "variables": variables}

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post("https://graphql.anilist.co", json=payload) as response:
            if response.status != 200:
                return None
            return await response.json()


def _pick_title(media: dict) -> str:
    titles = media.get("title", {})
    return titles.get("english") or titles.get("romaji") or titles.get("native") or "Unknown"


def _format_start_date(start_date: dict | None) -> str | None:
    if not start_date or not start_date.get("year"):
        return None
    month = start_date.get("month") or 1
    day = start_date.get("day") or 1
    return f"{start_date['year']}-{month:02d}-{day:02d}"


def _serialize_media(item: dict) -> dict:
    return {
        "id": item["id"],
        "title": _pick_title(item),
        "url": item["siteUrl"],
        "description": item.get("description", ""),
        "genres": item.get("genres", []),
        "cover": item.get("coverImage", {}).get("large"),
        "format": item.get("format") or "Unknown",
        "score": item.get("averageScore"),
        "color": item.get("coverImage", {}).get("color"),
        "start_date": _format_start_date(item.get("startDate")),
    }


def _autocomplete_label(item: dict) -> str:
    title = _pick_title(item)
    media_type = (item.get("type") or "").title()
    media_format = item.get("format") or "Unknown"
    year = item.get("startDate", {}).get("year")
    extras = [media_type or None, media_format, str(year) if year else None]
    suffix = ", ".join(part for part in extras if part)
    label = f"{title} ({suffix})" if suffix else title
    return label[:97] + "..." if len(label) > 100 else label


async def autocomplete_media_titles(search: str, media_type, limit: int = 10) -> list[dict[str, str]]:
    query = search.strip()
    if len(query) < 2:
        return []

    body = await _post_graphql(
        AUTOCOMPLETE_QUERY,
        {"search": query, "type": _normalize_media_type(media_type)},
    )
    media_items = (body or {}).get("data", {}).get("Page", {}).get("media") or []

    seen: set[str] = set()
    results: list[dict[str, str]] = []
    for item in media_items[:limit]:
        value = str(item["id"])
        if value in seen:
            continue
        seen.add(value)
        results.append({"label": _autocomplete_label(item), "value": value})
    return results


async def search_media(query: str, media_type) -> dict | None:
    normalized_type = _normalize_media_type(media_type)

    if query.isdigit():
        body = await _post_graphql(
            MEDIA_BY_ID_QUERY,
            {"id": int(query), "type": normalized_type},
        )
        item = (body or {}).get("data", {}).get("Media")
        if item is None and normalized_type is not None:
            body = await _post_graphql(MEDIA_BY_ID_QUERY, {"id": int(query), "type": None})
            item = (body or {}).get("data", {}).get("Media")
    else:
        body = await _post_graphql(
            SEARCH_MEDIA_QUERY,
            {"search": query, "type": normalized_type},
        )
        media_items = (body or {}).get("data", {}).get("Page", {}).get("media") or []
        item = media_items[0] if media_items else None

    if not item:
        return None

    return _serialize_media(item)
