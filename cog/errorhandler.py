import discord
from discord.ext import commands
from datetime import datetime, timedelta, timezone

E = "❌"
SUPPORT_SERVER = "https://github.com/InvalidDavid/Y-K-Bot"


class ErrorHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._error_cache = {}

    @staticmethod
    async def send_error_embed(ctx, title, description, ephemeral=True):
        embed = discord.Embed(
            color=discord.Color.red(),
            title=title,
            description=f"{E} | {description}"
        )

        if isinstance(ctx, commands.Context):
            await ctx.reply(embed=embed)
        else:
            await ctx.respond(embed=embed, ephemeral=ephemeral)

    @staticmethod
    def cooldown_timestamp(seconds: float, show_absolute: bool = True) -> str:
        target_time = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        relative = discord.utils.format_dt(target_time, style='R')
        absolute = discord.utils.format_dt(target_time, style='F')
        return f"{relative} ({absolute})" if show_absolute else relative

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        error_map = {
            commands.MissingPermissions: ("Missing Permissions",
                                          "You lack the required permissions to use this command."),
            commands.BotMissingPermissions: ("Bot Missing Permissions",
                                            "I lack the required permissions to execute this command."),
            commands.MissingRole: ("Missing Role", "You need a specific role to use this command."),
            commands.MissingAnyRole: ("Missing Role", "You need at least one of the required roles to use this command."),
            commands.BotMissingAnyRole: ("Bot Missing Role", "I need at least one of the required roles to execute this command."),
            commands.NotOwner: ("Missing Permissions", "Only the bot owner can use this command."),
            commands.DisabledCommand: ("Command Disabled", "This command is currently disabled."),
            commands.CommandOnCooldown: ("Cooldown", "This command is on cooldown."),
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

        if isinstance(error, commands.CommandOnCooldown):
            timestamp = self.cooldown_timestamp(error.retry_after)
            await self.send_error_embed(
                ctx,
                "Cooldown",
                f"This command is on cooldown. Try again {timestamp}."
            )
            return

        for error_type, (title, description) in error_map.items():
            if isinstance(error, error_type):
                # Special case for cooldown to show time
                if isinstance(error, commands.CommandOnCooldown):
                    timestamp = self.cooldown_timestamp(error.retry_after)
                    description = f"This command is on cooldown. Try again {timestamp}."
                await self.send_error_embed(ctx, title, description)
                return

        embed = discord.Embed(
            color=discord.Color.red(),
            title="Command Error",
            description=f"{E} | An unexpected error occurred!\nPlease report this issue on [Github]({SUPPORT_SERVER})."
        )
        embed.set_author(name=getattr(ctx, "author", getattr(ctx, "user", None)))
        embed.add_field(name="Error", value=f"```py\n{error}```")
        await ctx.reply(embed=embed)

    @commands.Cog.listener()
    async def on_application_command_error(self, ctx, error):
        key = (ctx.user.id, getattr(ctx.command, 'name', 'unknown'), type(error))
        now = datetime.utcnow()

        if key in self._error_cache:
            if now - self._error_cache[key] < timedelta(seconds=10):
                return
        self._error_cache[key] = now

        if isinstance(error, commands.CheckFailure):
            await self.send_error_embed(
                ctx,
                "Insufficient Permissions",
                "You do not have permission to use this command.",
                ephemeral=True
            )
            return

        if isinstance(error, commands.CommandError):
            await self.on_command_error(ctx, error)
            return

        if isinstance(error, discord.ApplicationCommandInvokeError):
            original = error.original
            if isinstance(original, commands.CommandError):
                await self.on_command_error(ctx, original)
                return

        embed = discord.Embed(
            color=discord.Color.red(),
            title="Command Error",
            description=f"{E} | An unexpected error occurred!\nPlease report this issue on [Github]({SUPPORT_SERVER})."
        )
        embed.set_author(name=ctx.user)
        embed.add_field(name="Error", value=f"```py\n{error}```")

        try:
            if not ctx.response.is_done():
                await ctx.respond(embed=embed, ephemeral=True)
            else:
                await ctx.followup.send(embed=embed, ephemeral=True)
        except discord.errors.HTTPException:
            pass


def setup(bot):
    bot.add_cog(ErrorHandler(bot))
