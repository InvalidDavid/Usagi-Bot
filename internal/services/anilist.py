from __future__ import annotations

import aiohttp


ANILIST_QUERY = """
query ($search: String!, $type: MediaType) {
  Page(page: 1, perPage: 1) {
    media(search: $search, type: $type) {
      id
      siteUrl
      title { romaji english native }
      description(asHtml: true)
      genres
      coverImage { large color }
      format
      averageScore
      startDate { year month day }
    }
  }
}
"""


def _pick_title(media: dict) -> str:
    titles = media.get("title", {})
    return titles.get("english") or titles.get("romaji") or titles.get("native") or "Unknown"


def _format_start_date(start_date: dict | None) -> str | None:
    if not start_date or not start_date.get("year"):
        return None
    month = start_date.get("month") or 1
    day = start_date.get("day") or 1
    return f"{start_date['year']}-{month:02d}-{day:02d}"


async def search_media(name: str, media_type: str) -> dict | None:
    timeout = aiohttp.ClientTimeout(total=10)
    payload = {"query": ANILIST_QUERY, "variables": {"search": name, "type": media_type}}

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post("https://graphql.anilist.co", json=payload) as response:
            if response.status != 200:
                return None
            body = await response.json()

    media = body.get("data", {}).get("Page", {}).get("media") or []
    if not media:
        return None

    item = media[0]
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
