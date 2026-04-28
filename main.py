from dataclasses import dataclass
from utils.imports import *
from utils.secrets import OWNER, TOKEN, GUILDS_ID
import inspect

# ---------------- PATHS ----------------
# automatically creates folders on bot start
UTILS_DIR = "utils"
ERROR_DIR = "error"
DATA_DIR = "Data"

for directory in (UTILS_DIR, ERROR_DIR, DATA_DIR):
    if not os.path.isdir(directory):
        os.makedirs(directory, exist_ok=True)

# ---------------- LOGGING ----------------
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

# reset every restart
file_handler = logging.FileHandler(
    os.path.join(ERROR_DIR, "bot.log"),
    mode="w",
    encoding="utf-8",
)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)

# create only if an actual error happens
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
        self.logger.info("Global cache stopped | cleared %s entr%s", cleared, "y" if cleared == 1 else "ies")

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
        expired_keys = [key for key, entry in self._store.items() if self._is_expired(entry, now)]
        if expired_keys:
            key_to_remove = min(expired_keys, key=lambda key: self._store[key].expires_at or now)
            self._store.pop(key_to_remove, None)
            return key_to_remove

        if not self._store:
            return None

        key_to_remove = min(
            self._store,
            key=lambda key: (self._store[key].touched_at, self._store[key].created_at),
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
            expired_keys = [key for key, entry in self._store.items() if self._is_expired(entry, now)]
            for key in expired_keys:
                self._store.pop(key, None)
            return len(expired_keys)

    async def keys(self) -> list[str]:
        now = self._now()

        async with self._lock:
            expired_keys = [key for key, entry in self._store.items() if self._is_expired(entry, now)]
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

            ttl_entries = sum(1 for entry in self._store.values() if entry.expires_at is not None)
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
                    self.logger.info("Global cache cleanup removed %s expired entr%s", removed, "y" if removed == 1 else "ies")
        except asyncio.CancelledError:
            return


# ---------------- MOBILE STATUS ----------------
# added a monkey patch so the bot can show a mobile status.
# remove this if you do not want that behavior.
# last tested on py-cord 2.7.2
# will only be fixed if discord patches it
original_identify = discord.gateway.DiscordWebSocket.identify


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
        payload["d"]["shard"] = [self.shard_id, getattr(self, "shard_count", 1)]

    if hasattr(self, "_connection") and self._connection:
        intents = getattr(self._connection, "intents", None)
        if intents:
            payload["d"]["intents"] = intents.value

        presence = getattr(self._connection, "_presence", None)
        if presence:
            payload["d"]["presence"] = presence

    await self.send_as_json(payload)


discord.gateway.DiscordWebSocket.identify = patched_identify
# ---------------------------------------


def safe_ping_ms(latency: Any) -> Optional[int]:
    if not isinstance(latency, (int, float)):
        return None

    if latency != latency:  # NaN check
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


class UsagiBot(commands.Bot):
    global_cache: "GlobalCache"
    cache: "GlobalCache"

    cache_get: Callable[..., Awaitable[Any]]
    cache_set: Callable[..., Awaitable[Any]]
    cache_has: Callable[..., Awaitable[bool]]
    cache_delete: Callable[..., Awaitable[bool]]
    cache_pop: Callable[..., Awaitable[Any]]
    cache_clear: Callable[..., Awaitable[int]]
    cache_cleanup: Callable[..., Awaitable[int]]
    cache_keys: Callable[..., Awaitable[list[str]]]
    cache_stats: Callable[..., Awaitable[dict[str, Any]]]

    startup_logged: bool

def build_bot() -> tuple[UsagiBot, Callable[[], Awaitable[None]]]:
    bot = UsagiBot(
        auto_sync_commands=True,
        intents=discord.Intents.all(),
        sync_commands=True,
        owner_ids=OWNER,
        command_prefix="=",
        help_command=None,
        debug_guilds=GUILDS_ID,
    )

    bot.global_cache = GlobalCache(logger_=logging.getLogger("bot.cache"))
    bot.cache = bot.global_cache
    bot.cache_get = bot.global_cache.get
    bot.cache_set = bot.global_cache.set
    bot.cache_has = bot.global_cache.has
    bot.cache_delete = bot.global_cache.delete
    bot.cache_pop = bot.global_cache.pop
    bot.cache_clear = bot.global_cache.clear
    bot.cache_cleanup = bot.global_cache.cleanup
    bot.cache_keys = bot.global_cache.keys
    bot.cache_stats = bot.global_cache.stats
    bot.startup_logged = False

    @bot.event
    async def on_ready() -> None:
        guilds = len(bot.guilds)
        users = sum(
            1 for g in bot.guilds
            for m in g.members
            if not m.bot
        )
        bots = sum(
            1 for g in bot.guilds
            for m in g.members
            if m.bot
        )
        ping = format_ping_ms(bot.latency)
        slash_commands = len(bot.application_commands)
        prefix_commands = len(bot.commands)

        infos = [
            f"Framework      : Pycord {discord.__version__}",
            f"Ping           : {ping}",
            f"Guilds         : {guilds}",
            f"Users          : {users:,}",
            f"Bots           : {bots:,}",
            f"Slash Commands : {slash_commands}",
            f"Prefix Commands: {prefix_commands}",
        ]

        width = max(len(i) for i in infos)
        logger.info(f"╔{'═' * (width + 2)}╗")
        for line in infos:
            logger.info(f"║ {line:<{width}} ║")
        logger.info(f"╚{'═' * (width + 2)}╝\n")

        if not bot.startup_logged:
            logger.info("Bot successfully started.")
            bot.startup_logged = True
        else:
            logger.info("Bot reconnected and is ready.")

        if not status_task.is_running():
            status_task.start()

    @tasks.loop(seconds=60)
    async def status_task() -> None:
        if not hasattr(status_task, "index"):
            status_task.index = 0

        ping = safe_ping_ms(bot.latency)
        ping_state = f"🏓 Ping: {ping}ms" if ping is not None else "🏓 Ping: N/A"

        statuses = [
            discord.Activity(type=discord.ActivityType.custom, state="©️ made by InvalidDavid"),
            discord.Activity(type=discord.ActivityType.custom, state="🏆 Check my profile out!"),
            discord.Activity(type=discord.ActivityType.custom, state=ping_state),
        ]

        activity = statuses[status_task.index]
        await bot.change_presence(activity=activity)
        status_task.index = (status_task.index + 1) % len(statuses)

    @status_task.before_loop
    async def before_status_task() -> None:
        await bot.wait_until_ready()

    @bot.command(description="Force load or reload all slash commands")
    @commands.is_owner()
    async def sync(ctx: commands.Context) -> None:
        await bot.sync_commands(force=True)
        user_cog = bot.get_cog("User")
        if user_cog is not None and hasattr(user_cog, "invalidate_help_cache"):
            user_cog.invalidate_help_cache()
        logger.info("%s: Synced from %s (%s)", datetime.now(), ctx.author, ctx.author.id)
        await ctx.reply("Slash commands are now synced. Wait a few seconds before using them.")

    async def _maybe_await(value: Any) -> Any:
        if inspect.isawaitable(value):
            return await value
        return value

    async def _clear_runtime_caches(bot: commands.Bot) -> dict[str, Any]:
        results: dict[str, Any] = {}

        # GlobalCache
        if hasattr(bot, "cache_clear") and callable(bot.cache_clear):
            try:
                results["GlobalCache"] = await _maybe_await(bot.cache_clear())
            except Exception as exc:
                logger.exception("Failed to clear GlobalCache")
                results["GlobalCache"] = f"ERROR: {type(exc).__name__}"

        # Cog caches
        for cog_name, cog in bot.cogs.items():
            clear_method = getattr(cog, "cache_clear", None)

            if callable(clear_method):
                try:
                    results[cog_name] = await _maybe_await(clear_method())
                except Exception as exc:
                    logger.exception("Failed to clear cache for cog %s", cog_name)
                    results[cog_name] = f"ERROR: {type(exc).__name__}"
                continue

        return results

    @bot.command(name="cacheclear", hidden=True)
    @commands.is_owner()
    async def cacheclear(ctx: commands.Context) -> None:
        results = await _clear_runtime_caches(bot)

        logger.info(
            "Manual full cache clear executed by %s (%s) | results=%s",
            ctx.author,
            ctx.author.id,
            results,
        )

        lines = ["[CacheClear]"]

        for name, result in results.items():
            lines.append(f"{name}={result}")

        await ctx.reply("```ini\n" + "\n".join(lines)[:1800] + "\n```")

    @bot.command(name="cachestats", hidden=True)
    @commands.is_owner()
    async def cachestats(ctx: commands.Context) -> None:
        sections: list[str] = []

        try:
            stats = await bot.cache_stats()
            sections.append(
                "\n".join(
                    [
                        "[GlobalCache]",
                        f"entries={stats['entries']}",
                        f"ttl_entries={stats['ttl_entries']}",
                        f"persistent_entries={stats['persistent_entries']}",
                        f"max_entries={stats['max_entries']}",
                        f"default_ttl={stats['default_ttl']}",
                        f"cleanup_interval={stats['cleanup_interval']}",
                        f"expired_removed={stats['expired_removed']}",
                    ]
                )
            )
        except Exception as exc:
            logger.exception("Failed to read global cache stats")
            sections.append(f"[GlobalCache]\nerror={type(exc).__name__}: {exc}")

        for cog_name, cog in sorted(bot.cogs.items(), key=lambda item: item[0].lower()):
            stats_func = getattr(cog, "cache_stats", None)
            if not callable(stats_func):
                continue

            try:
                cog_stats = stats_func()

                if hasattr(cog_stats, "__await__"):
                    cog_stats = await cog_stats

                if not isinstance(cog_stats, dict):
                    sections.append(f"[{cog_name}]\nerror=cache_stats did not return dict")
                    continue

                lines = [f"[{cog_name}]"]
                for key, value in cog_stats.items():
                    lines.append(f"{key}={value}")

                sections.append("\n".join(lines))

            except Exception as exc:
                logger.exception("Failed to read cache stats for cog %s", cog_name)
                sections.append(f"[{cog_name}]\nerror={type(exc).__name__}: {exc}")

        if not sections:
            await ctx.reply("No cache stats found.")
            return

        output = "\n\n".join(sections)

        chunks: list[str] = []
        current = ""

        for block in output.split("\n\n"):
            candidate = f"{current}\n\n{block}".strip() if current else block

            if len(candidate) > 1850:
                if current:
                    chunks.append(current)
                current = block
            else:
                current = candidate

        if current:
            chunks.append(current)

        for chunk in chunks:
            await ctx.reply(f"```ini\n{chunk}\n```")

    async def shutdown_bot() -> None:
        logger.info("Shutdown started.")

        if status_task.is_running():
            status_task.cancel()

        for ext in list(bot.extensions):
            try:
                bot.unload_extension(ext)
                logger.info(f"[-] Unloaded: {ext}")
            except discord.ExtensionError:
                logger.exception(f"[!] Failed to unload: {ext}")

        await bot.global_cache.close()
        await bot.close()
        logger.info("Shutdown finished.")

    return bot, shutdown_bot


async def main() -> None:
    bot, shutdown_bot = build_bot()
    await bot.global_cache.start()

    for filename in sorted(os.listdir("cog")):
        if not filename.endswith(".py"):
            continue
        if filename.startswith("_"):
            continue

        cog = f"cog.{filename[:-3]}"
        try:
            bot.load_extension(cog)
            logger.info(f"[+] Loaded: {cog}")
        except discord.ExtensionError:
            logger.exception(f"[!] Error {cog}")

    try:
        await bot.start(TOKEN)
    finally:
        await shutdown_bot()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by KeyboardInterrupt.")
