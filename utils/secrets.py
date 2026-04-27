import os
import re
from dotenv import load_dotenv

load_dotenv()


def _clean_env_value(value: str) -> str:
    value = value.strip()

    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()

    return value


def _get_env_str(name: str, default: str = "") -> str:
    raw = os.getenv(name)

    if raw is None:
        return default

    value = _clean_env_value(raw)
    return value if value else default


def _get_env_int(
    name: str,
    default: int = 0,
    *,
    min_value: int | None = None,
    max_value: int | None = None,
) -> int:
    raw = os.getenv(name)

    if raw is None:
        return default

    raw = _clean_env_value(raw)

    if not raw:
        return default

    try:
        value = int(raw)
    except ValueError:
        return default

    if min_value is not None and value < min_value:
        return default

    if max_value is not None and value > max_value:
        return default

    return value


def _get_env_float(
    name: str,
    default: float = 0.0,
    *,
    min_value: float | None = None,
    max_value: float | None = None,
) -> float:
    raw = os.getenv(name)

    if raw is None:
        return default

    raw = _clean_env_value(raw)

    if not raw:
        return default

    try:
        value = float(raw)
    except ValueError:
        return default

    if min_value is not None and value < min_value:
        return default

    if max_value is not None and value > max_value:
        return default

    return value


def _get_env_int_list(name: str) -> list[int]:
    raw = os.getenv(name, "")
    raw = _clean_env_value(raw)

    if not raw:
        return []

    values: list[int] = []
    seen: set[int] = set()

    for item in re.split(r"[,;\s]+", raw):
        item = item.strip()

        if not item:
            continue

        try:
            value = int(item)
        except ValueError:
            continue

        if value in seen:
            continue

        seen.add(value)
        values.append(value)

    return values


TOKEN = _get_env_str("TOKEN")
OWNER = _get_env_int_list("OWNER")
GUILDS_ID = _get_env_int_list("GUILDS")

WEBHOOK_URL = _get_env_str("WEBHOOK_URL")
ERROREMOJI = _get_env_str("ERROREMOJI", "❌")
SUPPORT_SERVER = _get_env_str("SUPPORT_SERVER")

LOG_GUILD_ID = _get_env_int("LOG_GUILD_ID", min_value=0)
LOG_CHANNEL_ID = _get_env_int("LOG_CHANNEL_ID", min_value=0)
LOG_ARROW = _get_env_str("LOG_ARROW", "➜")

MEMBER_UPDATE_DELAY = _get_env_float("MEMBER_UPDATE_DELAY", 1.5, min_value=0.0)
AUDIT_LOG_DELAY = _get_env_float("AUDIT_LOG_DELAY", 2.5, min_value=0.0)
AUDIT_LOG_MAX_AGE = _get_env_float("AUDIT_LOG_MAX_AGE", 30.0, min_value=1.0)
BULK_AUDIT_LOG_MAX_AGE = _get_env_float("BULK_AUDIT_LOG_MAX_AGE", 60.0, min_value=1.0)

RECENT_BAN_TTL = _get_env_float("RECENT_BAN_TTL", 5.0, min_value=0.1)
RECENT_USER_UPDATE_TTL = _get_env_float("RECENT_USER_UPDATE_TTL", 2.0, min_value=0.1)
RECENT_BULK_LOG_TTL = _get_env_float("RECENT_BULK_LOG_TTL", 3.0, min_value=0.1)
MEMBER_REMOVE_AUDIT_WAIT = _get_env_float("MEMBER_REMOVE_AUDIT_WAIT", 2.5, min_value=0.0)

__all__ = [
    "TOKEN",
    "OWNER",
    "GUILDS_ID",
    "WEBHOOK_URL",
    "ERROREMOJI",
    "SUPPORT_SERVER",
    "LOG_GUILD_ID",
    "LOG_CHANNEL_ID",
    "LOG_ARROW",
    "MEMBER_UPDATE_DELAY",
    "AUDIT_LOG_DELAY",
    "AUDIT_LOG_MAX_AGE",
    "BULK_AUDIT_LOG_MAX_AGE",
    "RECENT_BAN_TTL",
    "RECENT_USER_UPDATE_TTL",
    "RECENT_BULK_LOG_TTL",
    "MEMBER_REMOVE_AUDIT_WAIT",
]
