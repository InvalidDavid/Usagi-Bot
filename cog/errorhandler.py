from utils.imports import *
from utils.secrets import WEBHOOK_URL, ERROREMOJI, SUPPORT_SERVER

logger = logging.getLogger("bot.errorhandler")

#   TEST VERSION MIGHT REVERT BACK TO THE OLD CODE

def cooldown_timestamp(seconds: float, show_absolute: bool = True) -> str:
    target_time = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    relative = discord.utils.format_dt(target_time, style='R')
    absolute = discord.utils.format_dt(target_time, style='F')
    return f"{relative} ({absolute})" if show_absolute else relative


error_map = {
    commands.MissingPermissions: ("Missing Permissions", "You lack the required permissions to use this command."),
    commands.BotMissingPermissions: ("Bot Missing Permissions",
                                     "I lack the required permissions to execute this command."),
    commands.MissingRole: ("Missing Role", "You need a specific role to use this command."),
    commands.MissingAnyRole: ("Missing Role", "You need at least one of the required roles to use this command."),
    commands.BotMissingAnyRole: ("Bot Missing Role",
                                 "I need at least one of the required roles to execute this command."),
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
    commands.CommandNotFound: ("Not Found", "The command could not be found."),
}

discord_api_errors = {
    discord.Forbidden: ("Access Denied", "I don't have permission to do that."),
    discord.NotFound: ("Not Found", "The requested resource was not found."),
    discord.HTTPException: ("API Error", "Discord API returned an error."),
}


class WebhookLogger:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
        self._session: Optional[aiohttp.ClientSession] = None
        self._error_cache = {}

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def send_error(self, ctx, error: Exception):
        now = datetime.now(timezone.utc)

        tb_full = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        tb_short = "".join(traceback.format_exception_only(type(error), error))
        fingerprint = hashlib.sha256(tb_full.encode()).hexdigest()

        if fingerprint in self._error_cache:
            if (now - self._error_cache[fingerprint]).total_seconds() < 60:
                return
        self._error_cache[fingerprint] = now

        user = getattr(ctx, "author", getattr(ctx, "user", None))
        user_name = getattr(user, "name", "Unknown")
        user_id = getattr(user, "id", "Unknown")
        guild = getattr(ctx, "guild", None)
        guild_name = getattr(guild, "name", "DM") if guild else "DM"
        guild_id = getattr(guild, "id", "DM") if guild else "DM"
        channel = getattr(ctx, "channel", None)
        channel_name = getattr(channel, "name", getattr(channel, "id", "Unknown"))
        channel_type = getattr(channel, "type", "Unknown")
        command = getattr(ctx.command, "qualified_name", getattr(ctx, "command_name", "Unknown"))
        event_type = type(ctx).__name__ if ctx else "Unknown"
        discord_timestamp = f"<t:{int(now.timestamp())}:F>"

        embed = {
            "title": "🚨 Bot Error",
            "color": 0xED4245,
            "fields": [
                {"name": "User", "value": f"{user_name} (`{user_id}`)", "inline": True},
                {"name": "Guild", "value": f"{guild_name} (`{guild_id}`)", "inline": True},
                {"name": "Channel", "value": f"{channel_name} (`{channel_type}`)", "inline": True},
                {"name": "Command/Event", "value": f"{command} / `{event_type}`", "inline": True},
                {"name": "Time", "value": discord_timestamp, "inline": True},
                {"name": "Fingerprint", "value": f"`{fingerprint}`", "inline": False},
                {"name": "Error Preview", "value": f"```py\n{tb_short.strip()}```", "inline": False},
            ],
        }

        payload_json = json.dumps({"embeds": [embed]})

        data = aiohttp.FormData()
        data.add_field("payload_json", payload_json, content_type="application/json")
        data.add_field("file", tb_full.encode("utf-8"), filename="error.txt", content_type="text/plain")

        session = await self._get_session()
        try:
            async with session.post(self.webhook_url, data=data) as resp:
                if resp.status >= 400:
                    logger.error("Webhook error: %s - %s", resp.status, await resp.text())
        except Exception:
            logger.exception("Failed to send webhook")

    async def cleanup_cache(self):
        while True:
            await asyncio.sleep(300)
            now = datetime.now(timezone.utc)
            to_delete = [k for k, v in self._error_cache.items() if (now - v).total_seconds() > 300]
            for k in to_delete:
                del self._error_cache[k]


class ErrorHandler(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.webhook_logger = None
        if WEBHOOK_URL:
            self.webhook_logger = WebhookLogger(WEBHOOK_URL)
            bot.loop.create_task(self.webhook_logger.cleanup_cache())

        self._slash_error_cache = {}

        bot.add_listener(self.on_global_error)

    def cog_unload(self):
        if self.webhook_logger:
            asyncio.create_task(self.webhook_logger.close())

    async def send_error_embed(self, ctx: Union[commands.Context, discord.ApplicationContext],
                               title: str, description: str, ephemeral: bool = True):
        embed = discord.Embed(
            color=discord.Color.red(),
            title=title,
            description=f"{ERROREMOJI} | {description}"
        )
        if isinstance(ctx, commands.Context):
            await ctx.reply(embed=embed, mention_author=False)
        else:
            if ctx.response.is_done():
                await ctx.followup.send(embed=embed, ephemeral=ephemeral)
            else:
                await ctx.respond(embed=embed, ephemeral=ephemeral)

    @staticmethod
    def is_critical_error(error: Exception) -> bool:
        if isinstance(error, commands.CommandOnCooldown):
            return False
        if isinstance(error, tuple(error_map.keys())):
            return False
        if isinstance(error, commands.CommandError):
            return False
        if isinstance(error, tuple(discord_api_errors.keys())):
            return False
        return True

    async def on_global_error(self, event_method, *args, **kwargs):
        exc_type, exc_value, exc_tb = sys.exc_info()
        if exc_value is None:
            return

        ctx = None
        for arg in args:
            if isinstance(arg, (discord.Message, discord.Interaction, commands.Context)):
                ctx = arg
                break

        if self.is_critical_error(exc_value):
            logger.exception("Unhandled global error in event %s", event_method)

        if self.is_critical_error(exc_value) and self.webhook_logger:
            await self.webhook_logger.send_error(ctx, exc_value)

        traceback.print_exception(exc_type, exc_value, exc_tb)

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: Exception):
        # Cooldown
        if isinstance(error, commands.CommandOnCooldown):
            timestamp = cooldown_timestamp(error.retry_after)
            await self.send_error_embed(ctx, "Cooldown",
                                        f"This command is on cooldown. Try again {timestamp}.")
            return

        for err_type, (title, desc) in error_map.items():
            if isinstance(error, err_type):
                await self.send_error_embed(ctx, title, desc)
                return

        for err_type, (title, desc) in discord_api_errors.items():
            if isinstance(error, err_type):
                await self.send_error_embed(ctx, title, desc)
                return

        embed = discord.Embed(
            color=discord.Color.red(),
            title="Command Error",
            description=f"{ERROREMOJI} | An unexpected error occurred!\n"
                        f"Please report this issue on [GitHub]({SUPPORT_SERVER})."
        )
        embed.set_author(name=ctx.author)
        embed.add_field(name="Error", value=f"```py\n{error}```")

        if self.is_critical_error(error):
            logger.exception("Unhandled prefix command error: %s", getattr(ctx.command, "qualified_name", "unknown"))

        if self.is_critical_error(error) and self.webhook_logger:
            await self.webhook_logger.send_error(ctx, error)

        await ctx.reply(embed=embed, mention_author=False)

    @commands.Cog.listener()
    async def on_application_command_error(self, ctx: discord.ApplicationContext, error: Exception):
        now = datetime.now(timezone.utc)
        key = (ctx.user.id, getattr(ctx.command, 'name', 'unknown'), type(error))

        if key in self._slash_error_cache:
            if now - self._slash_error_cache[key] < timedelta(seconds=10):
                return
        self._slash_error_cache[key] = now

        original = error
        if isinstance(error, discord.ApplicationCommandInvokeError):
            original = error.original

        if isinstance(original, commands.CheckFailure):
            if self.is_critical_error(original):
                logger.exception("Application command check failure: %s", getattr(ctx.command, "qualified_name", "unknown"))

            if self.is_critical_error(original) and self.webhook_logger:
                await self.webhook_logger.send_error(ctx, original)

            await self.send_error_embed(ctx, "Insufficient Permissions",
                                        "You do not have permission to use this command.",
                                        ephemeral=True)
            return

        if isinstance(original, commands.CommandOnCooldown):
            timestamp = cooldown_timestamp(original.retry_after)
            await self.send_error_embed(ctx, "Cooldown",
                                        f"This command is on cooldown. Try again {timestamp}.")
            return

        for err_type, (title, desc) in error_map.items():
            if isinstance(original, err_type):
                await self.send_error_embed(ctx, title, desc)
                return

        for err_type, (title, desc) in discord_api_errors.items():
            if isinstance(original, err_type):
                await self.send_error_embed(ctx, title, desc)
                return

        embed = discord.Embed(
            color=discord.Color.red(),
            title="Command Error",
            description=f"{ERROREMOJI} | An unexpected error occurred!\n"
                        f"Please report this issue on [GitHub]({SUPPORT_SERVER})."
        )
        embed.set_author(name=ctx.user)
        embed.add_field(name="Error", value=f"```py\n{original}```")

        if self.is_critical_error(original):
            logger.exception("Unhandled slash command error: %s", getattr(ctx.command, "qualified_name", "unknown"))

        if self.is_critical_error(original) and self.webhook_logger:
            await self.webhook_logger.send_error(ctx, original)

        if ctx.response.is_done():
            await ctx.followup.send(embed=embed, ephemeral=True)
        else:
            await ctx.respond(embed=embed, ephemeral=True)


def setup(bot: commands.Bot):
    bot.add_cog(ErrorHandler(bot))
