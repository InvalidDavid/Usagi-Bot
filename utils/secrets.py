import os
from dotenv import load_dotenv

load_dotenv()


def _get_env_str(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip()


def _get_env_int_list(name: str) -> list[int]:
    raw = os.getenv(name, "")
    values: list[int] = []

    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue

        try:
            values.append(int(item))
        except ValueError:
            continue

    return values


TOKEN = _get_env_str("TOKEN")
OWNER = _get_env_int_list("OWNER")
GUILDS_ID = _get_env_int_list("GUILDS")
WEBHOOK_URL = _get_env_str("WEBHOOK_URL")
ERROREMOJI = _get_env_str("ERROREMOJI")
SUPPORT_SERVER = _get_env_str("SUPPORT_SERVER")

__all__ = [
    "TOKEN",
    "OWNER",
    "GUILDS_ID",
    "WEBHOOK_URL",
    "ERROREMOJI",
    "SUPPORT_SERVER",
]
