from dataclasses import dataclass
import inspect

from utils.imports import *


# ---------------- PATHS ----------------
UTILS_DIR = "utils"
ERROR_DIR = "error"
DATA_DIR = "Data"


def setup_runtime_dirs() -> None:
    for directory in (UTILS_DIR, ERROR_DIR, DATA_DIR):
        if not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)


# ---------------- LOGGING ----------------
def setup_logging() -> logging.Logger:
    logger = logging.getLogger("bot")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(
        os.path.join(ERROR_DIR, "bot.log"),
        mode="w",
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    error_filename = os.path.join(
        ERROR_DIR,
        f"crash_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log",
    )
    error_handler = logging.FileHandler(
        error_filename,
        mode="w",
        encoding="utf-8",
        delay=True,
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)

    if not logger.handlers:
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)
        logger.addHandler(error_handler)

    discord_logger = logging.getLogger("discord")
    discord_logger.setLevel(logging.INFO)
    discord_logger.propagate = False

    if not discord_logger.handlers:
        discord_logger.addHandler(console_handler)
        discord_logger.addHandler(file_handler)
        discord_logger.addHandler(error_handler)

    return logger


# ---------------- GLOBAL CACHE ----------------
GLOBAL_CACHE_MAX_ENTRIES = 5000
GLOBAL_CACHE_DEFAULT_TTL_SECONDS = 15 * 60
GLOBAL_CACHE_CLEANUP_INTERVAL_SECONDS = 5 * 60


@dataclass(slots=True)
class CacheEntry:
    value: Any
    created_at: float
    touched_at: float
    expires_at: Optional[float] = None


class GlobalCache:
    def __init__(
        self,
        *,
        max_entries: int = GLOBAL_CACHE_MAX_ENTRIES,
        default_ttl: Optional[float] = GLOBAL_CACHE_DEFAULT_TTL_SECONDS,
        cleanup_interval: float = GLOBAL_CACHE_CLEANUP_INTERVAL_SECONDS,
        logger_: Optional[logging.Logger] = None,
    ):
        self.max_entries = max(1, int(max_entries))
        self.default_ttl = default_ttl
        self.cleanup_interval = max(5.0, float(cleanup_interval))
        self.logger = logger_ or logging.getLogger("bot.cache")

        self._store: dict[str, CacheEntry] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            self.logger.info(
                "Global cache started | max_entries=%s | default_ttl=%s | cleanup_interval=%ss",
                self.max_entries,
                self.default_ttl,
                int(self.cleanup_interval),
            )

    async def close(self) -> None:
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._cleanup_task
            self._cleanup_task = None

        cleared = await self.clear()
        self.logger.info(
            "Global cache stopped | cleared %s entr%s",
            cleared,
            "y" if cleared == 1 else "ies",
        )

    def _now(self) -> float:
        return time.monotonic()

    def _resolve_expires_at(self, ttl: Optional[float], now: float) -> Optional[float]:
        if ttl is None:
            ttl = self.default_ttl

        if ttl is None:
            return None

        ttl = float(ttl)
        if ttl <= 0:
            return now

        return now + ttl

    def _is_expired(self, entry: CacheEntry, now: float) -> bool:
        return entry.expires_at is not None and entry.expires_at <= now

    def _evict_one_locked(self, now: float) -> Optional[str]:
        expired_keys = [
            key
            for key, entry in self._store.items()
            if self._is_expired(entry, now)
        ]

        if expired_keys:
            key_to_remove = min(
                expired_keys,
                key=lambda key: self._store[key].expires_at or now,
            )
            self._store.pop(key_to_remove, None)
            return key_to_remove

        if not self._store:
            return None

        key_to_remove = min(
            self._store,
            key=lambda key: (
                self._store[key].touched_at,
                self._store[key].created_at,
            ),
        )
        self._store.pop(key_to_remove, None)
        return key_to_remove

    async def set(self, key: str, value: Any, ttl: Optional[float] = None) -> Any:
        key = str(key)
        now = self._now()
        expires_at = self._resolve_expires_at(ttl, now)

        async with self._lock:
            if expires_at is not None and expires_at <= now:
                self._store.pop(key, None)
                return value

            if key not in self._store and len(self._store) >= self.max_entries:
                self._evict_one_locked(now)

            self._store[key] = CacheEntry(
                value=value,
                created_at=now,
                touched_at=now,
                expires_at=expires_at,
            )
            return value

    async def get(self, key: str, default: Any = None) -> Any:
        key = str(key)
        now = self._now()

        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return default

            if self._is_expired(entry, now):
                self._store.pop(key, None)
                return default

            entry.touched_at = now
            return entry.value

    async def has(self, key: str) -> bool:
        sentinel = object()
        return await self.get(key, sentinel) is not sentinel

    async def delete(self, key: str) -> bool:
        key = str(key)
        async with self._lock:
            return self._store.pop(key, None) is not None

    async def pop(self, key: str, default: Any = None) -> Any:
        key = str(key)
        now = self._now()

        async with self._lock:
            entry = self._store.pop(key, None)
            if entry is None:
                return default

            if self._is_expired(entry, now):
                return default

            return entry.value

    async def clear(self) -> int:
        async with self._lock:
            cleared = len(self._store)
            self._store.clear()
            return cleared

    async def cleanup(self) -> int:
        now = self._now()

        async with self._lock:
            expired_keys = [
                key
                for key, entry in self._store.items()
                if self._is_expired(entry, now)
            ]

            for key in expired_keys:
                self._store.pop(key, None)

            return len(expired_keys)

    async def keys(self) -> list[str]:
        now = self._now()

        async with self._lock:
            expired_keys = [
                key
                for key, entry in self._store.items()
                if self._is_expired(entry, now)
            ]

            for key in expired_keys:
                self._store.pop(key, None)

            return list(self._store.keys())

    async def stats(self) -> dict[str, Any]:
        now = self._now()

        async with self._lock:
            expired = 0

            for key, entry in list(self._store.items()):
                if self._is_expired(entry, now):
                    self._store.pop(key, None)
                    expired += 1

            ttl_entries = sum(
                1 for entry in self._store.values()
                if entry.expires_at is not None
            )
            persistent_entries = len(self._store) - ttl_entries

            return {
                "entries": len(self._store),
                "expired_removed": expired,
                "max_entries": self.max_entries,
                "default_ttl": self.default_ttl,
                "cleanup_interval": self.cleanup_interval,
                "ttl_entries": ttl_entries,
                "persistent_entries": persistent_entries,
            }

    async def _cleanup_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self.cleanup_interval)
                removed = await self.cleanup()

                if removed:
                    self.logger.info(
                        "Global cache cleanup removed %s expired entr%s",
                        removed,
                        "y" if removed == 1 else "ies",
                    )

        except asyncio.CancelledError:
            return


# ---------------- MOBILE STATUS PATCH ----------------
_ORIGINAL_IDENTIFY = None
_MOBILE_PATCHED = False


def patch_mobile_status() -> None:
    global _ORIGINAL_IDENTIFY, _MOBILE_PATCHED

    if _MOBILE_PATCHED:
        return

    _ORIGINAL_IDENTIFY = discord.gateway.DiscordWebSocket.identify

    async def patched_identify(self):
        payload = {
            "op": self.IDENTIFY,
            "d": {
                "token": self.token,
                "properties": {
                    "$os": "Android",
                    "$browser": "Discord Android",
                    "$device": "Android",
                    "$referrer": "",
                    "$referring_domain": "",
                },
                "compress": True,
                "large_threshold": 250,
                "v": 3,
            },
        }

        if hasattr(self, "shard_id") and self.shard_id is not None:
            payload["d"]["shard"] = [
                self.shard_id,
                getattr(self, "shard_count", 1),
            ]

        if hasattr(self, "_connection") and self._connection:
            intents = getattr(self._connection, "intents", None)
            if intents:
                payload["d"]["intents"] = intents.value

            presence = getattr(self._connection, "_presence", None)
            if presence:
                payload["d"]["presence"] = presence

        await self.send_as_json(payload)

    discord.gateway.DiscordWebSocket.identify = patched_identify
    _MOBILE_PATCHED = True


# ---------------- PING HELPERS ----------------
def safe_ping_ms(latency: Any) -> Optional[int]:
    if not isinstance(latency, (int, float)):
        return None

    if latency != latency:
        return None

    if latency in (float("inf"), float("-inf")):
        return None

    ms = latency * 1000

    if ms < 0:
        return None

    return round(ms)


def format_ping_ms(latency: Any) -> str:
    ping = safe_ping_ms(latency)
    return f"{ping} ms" if ping is not None else "N/A"


# ---------------- CACHE CLEAR HELPERS ----------------
async def maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


CACHE_CLEAR_METHOD_NAMES = (
    "cache_clear",
    "clear_cache",
    "clear_caches",
    "clear_runtime_cache",
    "clear_runtime_caches",
    "invalidate_help_cache",
)

CACHE_ATTR_KEYWORDS = (
    "cache",
    "cached",
    "recent",
    "pending",
    "processed",
    "dedupe",
    "duplicate",
    "seen",
    "history",
    "tag_changes",
    "rate_limit",
    "ratelimit",
    "cooldown",
    "bucket",
    "temporary",
    "temp",
)

PROTECTED_ATTR_NAMES = {
    "bot",
    "client",
    "guild",
    "channel",
    "message",
    "logger",
    "webhook_url",
    "_session",
    "session",
}

TASK_DICTS_SAFE_TO_CANCEL = {
    "_member_update_tasks",
    "_attachment_cache_tasks",
}


def safe_len(value: Any) -> int:
    try:
        return len(value)
    except Exception:
        return 0


def is_asyncio_sync_primitive(value: Any) -> bool:
    return isinstance(
        value,
        (
            asyncio.Lock,
            asyncio.Event,
            asyncio.Semaphore,
            asyncio.Condition,
        ),
    )


def is_clearable_container(value: Any) -> bool:
    return isinstance(value, (dict, list, set))


def looks_like_cache_attr(name: str, value: Any) -> bool:
    if not name or name in PROTECTED_ATTR_NAMES:
        return False

    if name.startswith("__"):
        return False

    if callable(value):
        return False

    if isinstance(value, (logging.Logger, asyncio.Task)):
        return False

    if is_asyncio_sync_primitive(value):
        return False

    lowered = name.lower()
    return any(keyword in lowered for keyword in CACHE_ATTR_KEYWORDS)


def cancel_task_mapping(value: dict[Any, Any]) -> int:
    cancelled = 0

    for task in list(value.values()):
        if isinstance(task, asyncio.Task) and not task.done():
            task.cancel()
            cancelled += 1

    value.clear()
    return cancelled


def clear_cache_like_attrs(obj: Any, *, prefix: str = "") -> dict[str, Any]:
    cleared: dict[str, Any] = {}

    try:
        attrs = vars(obj)
    except TypeError:
        return cleared

    for attr_name, value in list(attrs.items()):
        full_name = f"{prefix}.{attr_name}" if prefix else attr_name

        if attr_name in TASK_DICTS_SAFE_TO_CANCEL and isinstance(value, dict):
            before = safe_len(value)
            cancelled = cancel_task_mapping(value)
            cleared[full_name] = {
                "before": before,
                "after": 0,
                "cancelled_tasks": cancelled,
            }
            continue

        if not looks_like_cache_attr(attr_name, value):
            continue

        if is_clearable_container(value):
            before = safe_len(value)
            value.clear()
            cleared[full_name] = {
                "before": before,
                "after": 0,
            }
            continue

        if isinstance(value, int) and (
            "bytes" in attr_name.lower()
            or "size" in attr_name.lower()
        ):
            before = value
            with contextlib.suppress(Exception):
                setattr(obj, attr_name, 0)
                cleared[full_name] = {
                    "before": before,
                    "after": 0,
                }

    return cleared


def clear_nested_cache_like_attrs(obj: Any) -> dict[str, Any]:
    cleared: dict[str, Any] = {}

    try:
        attrs = vars(obj)
    except TypeError:
        return cleared

    for attr_name, value in list(attrs.items()):
        if value is None:
            continue

        if attr_name in PROTECTED_ATTR_NAMES:
            continue

        if isinstance(value, (logging.Logger, asyncio.Task)):
            continue

        if is_asyncio_sync_primitive(value):
            continue

        if (
            attr_name.endswith("_logger")
            or attr_name.endswith("_helper")
            or attr_name.endswith("_manager")
        ):
            nested = clear_cache_like_attrs(value, prefix=attr_name)
            if nested:
                cleared.update(nested)

    return cleared


async def call_explicit_cache_clear(cog: Any) -> dict[str, Any]:
    for method_name in CACHE_CLEAR_METHOD_NAMES:
        method = getattr(cog, method_name, None)

        if not callable(method):
            continue

        result = await maybe_await(method())

        return {
            "method": method_name,
            "result": "OK" if result is None else result,
        }

    return {}


def iter_command_tree(command: Any):
    yield command

    children = (
        getattr(command, "commands", None)
        or getattr(command, "subcommands", None)
        or []
    )

    for child in children:
        yield from iter_command_tree(child)


def clear_command_cooldown_caches(bot: commands.Bot) -> dict[str, Any]:
    cleared = 0
    touched = 0

    command_sources = (
        getattr(bot, "commands", []) or [],
        getattr(bot, "application_commands", []) or [],
    )

    for source in command_sources:
        for command in source:
            for cmd in iter_command_tree(command):
                buckets = getattr(cmd, "_buckets", None)
                if buckets is None:
                    continue

                for attr_name in ("_cache", "cache"):
                    bucket_cache = getattr(buckets, attr_name, None)

                    if isinstance(bucket_cache, dict):
                        size = len(bucket_cache)
                        bucket_cache.clear()
                        cleared += size
                        touched += 1

    return {
        "commands_touched": touched,
        "cooldown_entries_cleared": cleared,
    }


async def clear_runtime_caches(
    bot: commands.Bot,
    *,
    logger: Optional[logging.Logger] = None,
) -> dict[str, Any]:
    logger = logger or logging.getLogger("bot")
    results: dict[str, Any] = {}

    global_cache_result: dict[str, Any] = {}
    global_cache_clear = getattr(bot, "cache_clear", None)

    if callable(global_cache_clear):
        try:
            global_cache_result["entries_cleared"] = await maybe_await(global_cache_clear())
        except Exception as exc:
            logger.exception("Failed to clear GlobalCache")
            global_cache_result["error"] = f"{type(exc).__name__}: {exc}"
    else:
        global_cache = getattr(bot, "global_cache", None)
        fallback_clear = getattr(global_cache, "clear", None)

        if callable(fallback_clear):
            try:
                global_cache_result["entries_cleared"] = await maybe_await(fallback_clear())
            except Exception as exc:
                logger.exception("Failed to clear fallback GlobalCache")
                global_cache_result["error"] = f"{type(exc).__name__}: {exc}"

    results["GlobalCache"] = global_cache_result or {"status": "not_found"}

    try:
        results["CommandCooldowns"] = clear_command_cooldown_caches(bot)
    except Exception as exc:
        logger.exception("Failed to clear command cooldown caches")
        results["CommandCooldowns"] = {"error": f"{type(exc).__name__}: {exc}"}

    for cog_name, cog in sorted(bot.cogs.items(), key=lambda item: item[0].lower()):
        cog_result: dict[str, Any] = {}

        try:
            explicit = await call_explicit_cache_clear(cog)
            if explicit:
                cog_result["explicit_clear"] = explicit
        except Exception as exc:
            logger.exception("Explicit cache clear failed for cog %s", cog_name)
            cog_result["explicit_clear_error"] = f"{type(exc).__name__}: {exc}"

        try:
            auto_attrs = clear_cache_like_attrs(cog)
            nested_attrs = clear_nested_cache_like_attrs(cog)

            if auto_attrs:
                cog_result["auto_attrs"] = auto_attrs

            if nested_attrs:
                cog_result["nested_attrs"] = nested_attrs

        except Exception as exc:
            logger.exception("Automatic cache clear failed for cog %s", cog_name)
            cog_result["auto_clear_error"] = f"{type(exc).__name__}: {exc}"

        if not cog_result:
            cog_result["status"] = "no_runtime_cache_found"

        results[cog_name] = cog_result

    return results


def append_cache_result_lines(
    lines: list[str],
    key: str,
    value: Any,
    *,
    indent: int = 0,
) -> None:
    pad = " " * indent

    if isinstance(value, dict):
        if not value:
            lines.append(f"{pad}{key}=OK")
            return

        lines.append(f"{pad}[{key}]")

        for child_key, child_value in value.items():
            append_cache_result_lines(
                lines,
                str(child_key),
                child_value,
                indent=indent + 2,
            )

        return

    if isinstance(value, list):
        lines.append(f"{pad}{key}={', '.join(map(str, value)) if value else '[]'}")
        return

    lines.append(f"{pad}{key}={value}")


def chunk_ini_output(text: str, *, limit: int = 1850) -> list[str]:
    chunks: list[str] = []
    current = ""

    for block in text.split("\n\n"):
        candidate = f"{current}\n\n{block}".strip() if current else block

        if len(candidate) > limit:
            if current:
                chunks.append(current)
            current = block
        else:
            current = candidate

    if current:
        chunks.append(current)

    return chunks