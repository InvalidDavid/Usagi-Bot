from __future__ import annotations

from datetime import datetime

import discord
from discord.ext import commands

from internal.config import Settings, load_settings
from internal.utils.extensions import load_all_extensions


class YKBot(commands.Bot):
    def __init__(self, settings: Settings):
        super().__init__(
            intents=discord.Intents.all(),
            debug_guilds=settings.guild_ids,
            sync_commands=True,
            owner_ids=settings.owner_ids,
            command_prefix="!",
            help_command=None,
        )
        self.settings = settings


def _member_counts(bot: commands.Bot) -> tuple[int, int]:
    humans = {member.id for guild in bot.guilds for member in guild.members if not member.bot}
    bots = {member.id for guild in bot.guilds for member in guild.members if member.bot}
    return len(humans), len(bots)


def _print_startup_banner(bot: commands.Bot) -> int:
    users, bots = _member_counts(bot)
    info_lines = [
        f"Framework      : Pycord {discord.__version__}",
        f"Ping           : {round(bot.latency * 1000)} ms",
        f"Guilds         : {len(bot.guilds)}",
        f"Users          : {users:,}",
        f"Bots           : {bots:,}",
        f"Slash Commands : {len(bot.application_commands)}",
        f"Prefix Commands: {len(bot.commands)}",
    ]
    width = max(len(line) for line in info_lines)
    print(f"╔{'═' * (width + 2)}╗")
    for line in info_lines:
        print(f"║ {line:<{width}} ║")
    print(f"╚{'═' * (width + 2)}╝\n")
    return users


def create_bot(settings: Settings | None = None) -> YKBot:
    bot = YKBot(settings or load_settings())

    @bot.event
    async def on_ready():
        users = _print_startup_banner(bot)
        await bot.change_presence(
            status=discord.Status.online,
            activity=discord.Game(name=f"{users:,} users"),
        )
        print("\nBot successfully started\n")

    @bot.slash_command(description="Force to load or reload all Slash commands")
    @commands.is_owner()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def sync(ctx):
        await bot.sync_commands(force=True)
        print(f"{datetime.now()}: Synced from {ctx.author} ({ctx.author.id})")
        await ctx.respond(
            "Slash commands are now synced. Wait a couple seconds before trying again!",
            ephemeral=True,
        )

    return bot


def run():
    settings = load_settings()
    if not settings.token:
        raise RuntimeError("TOKEN is not configured.")

    bot = create_bot(settings)
    for name, error in load_all_extensions(bot, settings.cogs_folder).items():
        if error is None:
            print(f"[+] Loaded: {name}")
        else:
            print(f"[!] Error {name}: {error}")
    bot.run(settings.token)
