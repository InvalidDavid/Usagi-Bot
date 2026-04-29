from utils.imports import *
from utils.secrets import OWNER, TOKEN, GUILDS_ID
from utils.helper.mainhelper import (
    GlobalCache,
    setup_runtime_dirs,
    setup_logging,
    patch_mobile_status,
    safe_ping_ms,
    format_ping_ms,
    clear_runtime_caches,
    append_cache_result_lines,
    chunk_ini_output,
)


setup_runtime_dirs()
logger = setup_logging()
patch_mobile_status()


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
            1
            for guild in bot.guilds
            for member in guild.members
            if not member.bot
        )

        bots = sum(
            1
            for guild in bot.guilds
            for member in guild.members
            if member.bot
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

        width = max(len(info) for info in infos)

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
            discord.Activity(
                type=discord.ActivityType.custom,
                state="©️ made by InvalidDavid",
            ),
            discord.Activity(
                type=discord.ActivityType.custom,
                state="🏆 Check my profile out!",
            ),
            discord.Activity(
                type=discord.ActivityType.custom,
                state=ping_state,
            ),
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

        logger.info(
            "%s: Synced from %s (%s)",
            datetime.now(),
            ctx.author,
            ctx.author.id,
        )

        await ctx.reply("Slash commands are now synced. Wait a few seconds before using them.")

    @bot.command(name="cacheclear", hidden=True)
    @commands.is_owner()
    async def cacheclear(ctx: commands.Context) -> None:
        results = await clear_runtime_caches(bot, logger=logger)

        logger.info(
            "Manual full runtime cache clear executed by %s (%s) | results=%s",
            ctx.author,
            ctx.author.id,
            results,
        )

        lines: list[str] = [
            "[CacheClear]",
            "status=done",
            "",
        ]

        for name, result in results.items():
            append_cache_result_lines(lines, name, result)
            lines.append("")

        output = "\n".join(lines).strip()

        for chunk in chunk_ini_output(output):
            await ctx.reply(f"```ini\n{chunk}\n```")

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

        for chunk in chunk_ini_output(output):
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