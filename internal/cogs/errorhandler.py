from __future__ import annotations

from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands


ERROR_ICON = "❌"
SUPPORT_SERVER = "https://github.com/InvalidDavid/Y-K-Bot"
KNOWN_ERRORS = {
    commands.MissingPermissions: ("Missing Permissions", "You lack the required permissions to use this command."),
    commands.BotMissingPermissions: ("Bot Missing Permissions", "I lack the required permissions to execute this command."),
    commands.MissingRole: ("Missing Role", "You need a specific role to use this command."),
    commands.MissingAnyRole: ("Missing Role", "You need at least one of the required roles to use this command."),
    commands.BotMissingAnyRole: ("Bot Missing Role", "I need at least one of the required roles to execute this command."),
    commands.NotOwner: ("Missing Permissions", "Only the bot owner can use this command."),
    commands.DisabledCommand: ("Command Disabled", "This command is currently disabled."),
    commands.TooManyArguments: ("Too Many Arguments", "You provided too many arguments."),
    commands.MissingRequiredArgument: ("Missing Argument", "You are missing a required argument."),
    commands.PrivateMessageOnly: ("DM Only", "This command can only be used in direct messages."),
    commands.NoPrivateMessage: ("No DM", "This command cannot be used in DMs."),
    commands.NSFWChannelRequired: ("NSFW Channel Required", "You can only use this command in an NSFW channel."),
    commands.MessageNotFound: ("Not Found", "The message could not be found."),
    commands.MemberNotFound: ("Not Found", "The member could not be found."),
    commands.UserNotFound: ("Not Found", "The user could not be found."),
    commands.ChannelNotFound: ("Not Found", "The channel could not be found."),
    commands.ChannelNotReadable: ("Access Denied", "I cannot read messages in this channel."),
    commands.RoleNotFound: ("Not Found", "The role could not be found."),
    commands.EmojiNotFound: ("Not Found", "I could not find the emoji."),
    commands.PartialEmojiConversionFailure: ("Not Found", "This is not a valid emoji."),
}


class ErrorHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._error_cache: dict[tuple[int, str, type], datetime] = {}

    @staticmethod
    async def _send_embed(ctx, title: str, description: str, ephemeral: bool = True):
        embed = discord.Embed(
            color=discord.Color.red(),
            title=title,
            description=f"{ERROR_ICON} | {description}",
        )
        if isinstance(ctx, commands.Context):
            await ctx.reply(embed=embed)
            return
        await ctx.respond(embed=embed, ephemeral=ephemeral)

    @staticmethod
    def _cooldown_text(seconds: float) -> str:
        target = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        return f"{discord.utils.format_dt(target, 'R')} ({discord.utils.format_dt(target, 'F')})"

    async def _handle_known_error(self, ctx, error) -> bool:
        if isinstance(error, commands.CommandOnCooldown):
            await self._send_embed(ctx, "Cooldown", f"This command is on cooldown. Try again {self._cooldown_text(error.retry_after)}.")
            return True
        for error_type, (title, message) in KNOWN_ERRORS.items():
            if isinstance(error, error_type):
                await self._send_embed(ctx, title, message)
                return True
        if isinstance(error, commands.CheckFailure):
            await self._send_embed(ctx, "Insufficient Permissions", "You do not have permission to use this command.")
            return True
        return False

    async def _send_unexpected_error(self, ctx, error):
        embed = discord.Embed(
            color=discord.Color.red(),
            title="Command Error",
            description=f"{ERROR_ICON} | An unexpected error occurred!\nPlease report this issue on [Github]({SUPPORT_SERVER}).",
        )
        author = getattr(ctx, "author", getattr(ctx, "user", None))
        if author:
            embed.set_author(name=str(author))
        embed.add_field(name="Error", value=f"```py\n{error}```")
        try:
            if isinstance(ctx, commands.Context):
                await ctx.reply(embed=embed)
            elif hasattr(ctx, "response") and not ctx.response.is_done():
                await ctx.respond(embed=embed, ephemeral=True)
            else:
                await ctx.followup.send(embed=embed, ephemeral=True)
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if await self._handle_known_error(ctx, error):
            return
        await self._send_unexpected_error(ctx, error)

    @commands.Cog.listener()
    async def on_application_command_error(self, ctx, error):
        key = (ctx.user.id, getattr(ctx.command, "name", "unknown"), type(error))
        now = datetime.utcnow()
        if key in self._error_cache and now - self._error_cache[key] < timedelta(seconds=10):
            return
        self._error_cache[key] = now

        original = getattr(error, "original", error)
        if await self._handle_known_error(ctx, original):
            return
        await self._send_unexpected_error(ctx, original)


def setup(bot):
    bot.add_cog(ErrorHandler(bot))
