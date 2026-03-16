import platform
import time
from datetime import datetime, timedelta, timezone

import discord
import psutil
from discord.commands import SlashCommandGroup, slash_command
from discord.ext import commands
from discord.utils import format_dt

from internal.utils.ansi import BLUE, RESET, block
from internal.views.help import HelpView


def is_owner_command(cmd) -> bool:
    if getattr(cmd, "owner_only", False):
        return True
    if hasattr(cmd, "subcommands") and any(getattr(subcommand, "owner_only", False) for subcommand in cmd.subcommands):
        return True
    return any(getattr(check, "__name__", "") == "predicate" and "is_owner" in repr(check) for check in getattr(cmd, "checks", []))


def is_visible_command(cmd) -> bool:
    return type(cmd).__name__ in {"SlashCommand", "SlashCommandGroup"} and not is_owner_command(cmd)


def gather_commands(cmd, prefix: str = "") -> list[tuple[str, str]]:
    if not is_visible_command(cmd):
        return []
    current_name = f"{prefix}{cmd.name}"
    if hasattr(cmd, "subcommands") and cmd.subcommands:
        commands_list = []
        for subcommand in cmd.subcommands:
            commands_list.extend(gather_commands(subcommand, prefix=f"{current_name} "))
        return commands_list
    return [(current_name.strip(), cmd.description or "No description")]


def build_help_pages(bot: commands.Bot, max_fields: int) -> tuple[list[discord.Embed], dict[int, dict]]:
    embeds: list[discord.Embed] = []
    page_info: dict[int, dict] = {}
    index = 0
    for cog_name, cog in bot.cogs.items():
        commands_list = getattr(cog, "get_commands", lambda: [])()
        visible_commands = []
        for command in commands_list:
            visible_commands.extend(gather_commands(command))
        if not visible_commands:
            continue

        chunks = [visible_commands[i:i + max_fields] for i in range(0, len(visible_commands), max_fields)]
        display_name = cog_name.removesuffix("Cog")
        for page_number, chunk in enumerate(chunks, start=1):
            total_pages = len(chunks)
            title = f"📂 {display_name} Commands"
            description = f"All commands from `{display_name}`"
            if total_pages > 1:
                title = f"{title} (Page {page_number}/{total_pages})"
                description = f"Commands from `{display_name}` - Page {page_number} of {total_pages}"
            embed = discord.Embed(title=title, description=description, color=discord.Color.blurple())
            for name, desc in chunk:
                embed.add_field(name=f"/{name}", value=desc[:97] + "..." if len(desc) > 100 else desc, inline=False)
            embeds.append(embed)
            page_info[index] = {"cog_name": display_name, "page": page_number, "total_pages": total_pages}
            index += 1
    return embeds, page_info


class UserCog(commands.Cog):
    info = SlashCommandGroup("info", "Infos")

    def __init__(self, bot):
        self.bot = bot
        self.max_fields_per_embed = 20
        self.start_time = datetime.now(timezone.utc)

    @staticmethod
    def format_timedelta(delta: timedelta) -> str:
        days = delta.days
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"🗓️ {days}d ⏰ {hours}h ⏳ {minutes}m ⏲️ {seconds}s"

    @info.command(name="bot", description="Detailed stats about the bot.")
    async def bot_info(self, ctx: discord.ApplicationContext):
        await ctx.defer()
        now = datetime.now(timezone.utc)
        uptime = now - self.start_time
        start = time.perf_counter()
        cpu_percent = psutil.cpu_percent(interval=0.1)
        ram_percent = psutil.virtual_memory().percent
        ws_ping = round(self.bot.latency * 1000, 2)
        cmd_latency = round((time.perf_counter() - start) * 1000, 2)

        try:
            await self.bot.http.request(discord.http.Route("GET", "/gateway"))
            api_ping = round((time.perf_counter() - start) * 1000, 2)
        except Exception:
            api_ping = None

        created_at = self.bot.user.created_at if self.bot.user else None
        created_text = "Not available" if not created_at else f"{format_dt(created_at, 'F')} ({format_dt(created_at, 'R')})"
        embed = discord.Embed(
            title="🤖 Bot Info",
            description="# [GitHub](https://github.com/InvalidDavid/Y-K-Bot)",
            color=discord.Color.blurple(),
            timestamp=now,
        )
        embed.add_field(name="🆔 Bot ID", value=block(str(self.bot.user.id if self.bot.user else "N/A"), BLUE), inline=True)
        embed.add_field(name="📛 Bot Name", value=block(str(self.bot.user or "N/A"), BLUE), inline=True)
        embed.add_field(name="📅 Bot created", value=created_text, inline=False)
        embed.add_field(
            name="🕰️ Bot Uptime",
            value=f"{block(self.format_timedelta(uptime), BLUE)}Last restart: {format_dt(self.start_time, 'F')} ({format_dt(self.start_time, 'R')})",
            inline=False,
        )
        embed.add_field(name="🏓 WebSocket Ping", value=block(f"{ws_ping} ms", BLUE), inline=True)
        embed.add_field(name="📡 API Ping", value=block(f"{api_ping if api_ping is not None else 'Error'} ms", BLUE), inline=True)
        embed.add_field(name="⚡ Command Reaction Time", value=block(f"{cmd_latency} ms", BLUE), inline=True)
        embed.add_field(name="💻 CPU", value=block(f"{cpu_percent:.1f}%", BLUE), inline=True)
        embed.add_field(name="🧠 RAM", value=block(f"{ram_percent:.2f}%", BLUE), inline=True)
        embed.add_field(name="🖥️ Platform", value=block(f"{platform.system()} {platform.release()}", BLUE), inline=True)
        embed.add_field(name="🐍 Python Version", value=block(platform.python_version(), BLUE), inline=True)
        embed.add_field(name="📦 Py-cord Version", value=block(discord.__version__, BLUE), inline=True)
        embed.set_footer(text=f"Requested from {ctx.author}", icon_url=ctx.author.display_avatar.url)
        await ctx.respond(embed=embed)

    @slash_command(name="help", description="Show all slash commands you can use.")
    async def help_command(self, ctx: discord.ApplicationContext):
        embeds, page_info = build_help_pages(self.bot, self.max_fields_per_embed)
        if not embeds:
            await ctx.respond("No visible commands found.", ephemeral=True)
            return
        view = HelpView(embeds, page_info)
        message = await ctx.respond(embed=embeds[0], view=view, ephemeral=True)
        view.message = await message.original_response()


def setup(bot):
    bot.add_cog(UserCog(bot))
