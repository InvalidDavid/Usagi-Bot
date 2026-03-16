from __future__ import annotations

from dataclasses import dataclass, field
from os import getenv

from dotenv import load_dotenv


@dataclass(slots=True)
class Settings:
    token: str
    guild_ids: list[int] = field(default_factory=list)
    owner_ids: list[int] = field(default_factory=list)
    forum_id: int | None = None
    mod_role_ids: list[int] = field(default_factory=list)
    admin_role_ids: list[int] = field(default_factory=list)
    cogs_folder: str = "cog"


def _parse_int_list(raw_value: str | None) -> list[int]:
    if not raw_value:
        return []

    values: list[int] = []
    for item in raw_value.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            values.append(int(item))
        except ValueError:
            continue
    return values


def _parse_optional_int(raw_value: str | None) -> int | None:
    if not raw_value:
        return None
    try:
        return int(raw_value)
    except ValueError:
        return None


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        token=getenv("TOKEN", "").strip(),
        guild_ids=_parse_int_list(getenv("GUILDS")),
        owner_ids=_parse_int_list(getenv("OWNER")),
        forum_id=_parse_optional_int(getenv("FORUM_ID")),
        mod_role_ids=_parse_int_list(getenv("MOD_ROLE_IDS")),
        admin_role_ids=_parse_int_list(getenv("ADMIN_ROLE_IDS")),
    )
