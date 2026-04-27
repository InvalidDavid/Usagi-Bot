from utils.imports import *
from utils.secrets import WEBHOOK_URL, ERROREMOJI, SUPPORT_SERVER

logger = logging.getLogger("bot.errors")

# Cache retention for webhook/slash dedup entries.
ERROR_CACHE_TTL_SECONDS = 300

# Suppress duplicate webhook reports for the same traceback fingerprint.
ERROR_WEBHOOK_DEDUP_SECONDS = 60

# Suppress repeated slash error responses for the same user/command/error type.
SLASH_ERROR_DEDUP_SECONDS = 10

# Keep embed/codeblock text safely below Discord field limits.
MAX_ERROR_FIELD_LENGTH = 1000

# Hard caps to prevent cache growth during error bursts.
MAX_WEBHOOK_ERROR_CACHE_SIZE = 250
MAX_SLASH_ERROR_CACHE_SIZE = 500

# Discord interaction timing rules.
INITIAL_INTERACTION_RESPONSE_DEADLINE_SECONDS = 3.0
FOLLOWUP_INTERACTION_TTL_SECONDS = 15 * 60.0
EPHEMERAL_FALLBACK_DELETE_AFTER_SECONDS = 30.0


def cooldown_timestamp(seconds: float, show_absolute: bool = True) -> str:
    target_time = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    relative = discord.utils.format_dt(target_time, style="R")
    absolute = discord.utils.format_dt(target_time, style="F")
    return f"{relative} ({absolute})" if show_absolute else relative


def shorten_codeblock_text(text, limit: int = MAX_ERROR_FIELD_LENGTH) -> str:
    text = str(text).strip() or "Unknown error"
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


ERROR_MAP: dict[type[Exception], tuple[str, str]] = {
    commands.MissingPermissions: ("Missing Permissions", "You lack the required permissions to use this command."),
    commands.BotMissingPermissions: ("Bot Missing Permissions", "I lack the required permissions to execute this command."),
    commands.MissingRole: ("Missing Role", "You need a specific role to use this command."),
    commands.MissingAnyRole: ("Missing Role", "You need at least one of the required roles to use this command."),
    commands.BotMissingAnyRole: ("Bot Missing Role", "I need at least one of the required roles to execute this command."),
    commands.NotOwner: ("Missing Permissions", "Only the bot owner can use this command."),
    commands.DisabledCommand: ("Command Disabled", "This command is currently disabled."),
    commands.CommandOnCooldown: ("Cooldown", "This command is on cooldown."),
    commands.MaxConcurrencyReached: ("Command Busy", "This command is already running too many times. Try again shortly."),
    commands.TooManyArguments: ("Too Many Arguments", "You provided too many arguments."),
    commands.MissingRequiredArgument: ("Missing Argument", "You are missing a required argument."),
    commands.BadArgument: ("Invalid Argument", "One of the provided arguments is invalid."),
    commands.BadUnionArgument: ("Invalid Argument", "I could not convert one of the provided arguments."),
    commands.BadLiteralArgument: ("Invalid Argument", "One of the values provided is not allowed."),
    commands.BadBoolArgument: ("Invalid Argument", "That is not a valid true or false value."),
    commands.ArgumentParsingError: ("Invalid Argument", "I could not parse the command arguments."),
    commands.UnexpectedQuoteError: ("Invalid Argument", "There is an unexpected quote in your command."),
    commands.InvalidEndOfQuotedStringError: ("Invalid Argument", "Quoted text is malformed."),
    commands.ExpectedClosingQuoteError: ("Invalid Argument", "A quoted string is missing a closing quote."),
    commands.ConversionError: ("Conversion Error", "I failed to convert one of the arguments."),
    commands.CheckAnyFailure: ("Access Denied", "You do not meet the requirements to use this command."),
    commands.CheckFailure: ("Access Denied", "You are not allowed to use this command."),
    commands.PrivateMessageOnly: ("DM Only", "This command can only be used in direct messages."),
    commands.NoPrivateMessage: ("No DM", "This command cannot be used in direct messages."),
    commands.NSFWChannelRequired: ("NSFW Channel Required", "You can only use this command in an NSFW channel."),
    commands.MessageNotFound: ("Not Found", "The message could not be found."),
    commands.MemberNotFound: ("Not Found", "The member could not be found."),
    commands.UserNotFound: ("Not Found", "The user could not be found."),
    commands.ChannelNotFound: ("Not Found", "The channel could not be found."),
    commands.ChannelNotReadable: ("Access Denied", "I cannot read messages in this channel."),
    commands.RoleNotFound: ("Not Found", "The role could not be found."),
    commands.EmojiNotFound: ("Not Found", "I could not find the emoji."),
    commands.PartialEmojiConversionFailure: ("Invalid Emoji", "This is not a valid emoji."),
    commands.GuildNotFound: ("Not Found", "The server could not be found."),
    commands.ThreadNotFound: ("Not Found", "The thread could not be found."),
    commands.BadInviteArgument: ("Invalid Invite", "That invite is invalid or could not be parsed."),
}

DISCORD_API_ERRORS: dict[type[Exception], tuple[str, str]] = {
    discord.Forbidden: ("Access Denied", "I do not have permission to do that."),
    discord.NotFound: ("Not Found", "The requested resource was not found."),
    discord.InteractionResponded: ("Interaction Already Replied", "This interaction has already been responded to."),
    discord.HTTPException: ("API Error", "Discord returned an API error."),
    discord.ClientException: ("Client Error", "A Discord client error occurred."),
    discord.InvalidData: ("Invalid Data", "Discord returned invalid data."),
    discord.LoginFailure: ("Login Failed", "The bot could not log in."),
    discord.GatewayNotFound: ("Gateway Error", "Discord gateway could not be found."),
    discord.ConnectionClosed: ("Connection Closed", "The connection to Discord was closed unexpectedly."),
}


class WebhookLogger:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
        self._session: Optional[aiohttp.ClientSession] = None
        self._error_cache: dict[str, datetime] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
        self._started = False

    async def start(self) -> None:
        if self._started:
            return

        self._started = True
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_cache_loop())

    async def close(self) -> None:
        self._started = False

        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

        if self._session and not self._session.closed:
            await self._session.close()

        self._session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=15)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def _cleanup_cache_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(ERROR_CACHE_TTL_SECONDS)
                self._prune_cache()
        except asyncio.CancelledError:
            return

    def _prune_cache(self) -> None:
        now = datetime.now(timezone.utc)

        expired_keys = [
            key
            for key, created_at in self._error_cache.items()
            if (now - created_at).total_seconds() > ERROR_CACHE_TTL_SECONDS
        ]
        for key in expired_keys:
            self._error_cache.pop(key, None)

        if len(self._error_cache) > MAX_WEBHOOK_ERROR_CACHE_SIZE:
            logger.warning("Webhook error cache exceeded max size, pruning oldest entries")
            overflow = len(self._error_cache) - MAX_WEBHOOK_ERROR_CACHE_SIZE
            oldest_keys = [
                key
                for key, _ in heapq.nsmallest(
                    overflow,
                    self._error_cache.items(),
                    key=lambda item: item[1],
                )
            ]
            for key in oldest_keys:
                self._error_cache.pop(key, None)

    async def send_error(self, ctx, error: Exception) -> None:
        now = datetime.now(timezone.utc)

        tb_full = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        tb_short = "".join(traceback.format_exception_only(type(error), error))
        fingerprint = hashlib.sha256(tb_full.encode("utf-8")).hexdigest()

        last_seen = self._error_cache.get(fingerprint)
        if last_seen is not None and (now - last_seen).total_seconds() < ERROR_WEBHOOK_DEDUP_SECONDS:
            return

        self._error_cache[fingerprint] = now
        self._prune_cache()

        user = getattr(ctx, "author", getattr(ctx, "user", None))
        user_name = getattr(user, "name", "Unknown")
        user_id = getattr(user, "id", "Unknown")

        guild = getattr(ctx, "guild", None)
        guild_name = getattr(guild, "name", "DM") if guild else "DM"
        guild_id = getattr(guild, "id", "DM") if guild else "DM"

        channel = getattr(ctx, "channel", None)
        channel_name = getattr(channel, "name", getattr(channel, "id", "Unknown"))
        channel_type = getattr(channel, "type", "Unknown")

        command_obj = getattr(ctx, "command", None)
        command_name = (
            getattr(command_obj, "qualified_name", getattr(command_obj, "name", "Unknown"))
            if command_obj else "Unknown"
        )

        event_type = type(ctx).__name__ if ctx is not None else "Unknown"
        discord_timestamp = f"<t:{int(now.timestamp())}:F>"

        embed = {
            "title": "🚨 Bot Error",
            "color": 0xED4245,
            "fields": [
                {"name": "User", "value": f"{user_name} (`{user_id}`)", "inline": True},
                {"name": "Guild", "value": f"{guild_name} (`{guild_id}`)", "inline": True},
                {"name": "Channel", "value": f"{channel_name} (`{channel_type}`)", "inline": True},
                {"name": "Command/Event", "value": f"{command_name} / `{event_type}`", "inline": True},
                {"name": "Time", "value": discord_timestamp, "inline": True},
                {"name": "Fingerprint", "value": f"`{fingerprint}`", "inline": False},
                {
                    "name": "Error Preview",
                    "value": f"```py\n{shorten_codeblock_text(tb_short, 900)}```",
                    "inline": False,
                },
            ],
        }

        payload_json = json.dumps({"embeds": [embed]})

        data = aiohttp.FormData()
        data.add_field("payload_json", payload_json, content_type="application/json")
        data.add_field(
            "file",
            tb_full.encode("utf-8"),
            filename="error.txt",
            content_type="text/plain",
        )

        try:
            session = await self._get_session()
            async with session.post(self.webhook_url, data=data) as response:
                if response.status >= 400:
                    body = await response.text()
                    logger.error(
                        "Webhook error: status=%s body=%s fingerprint=%s",
                        response.status,
                        body,
                        fingerprint,
                    )
        except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError):
            logger.exception("Failed to send error to webhook")


class ErrorHandler(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.webhook_logger: Optional[WebhookLogger] = WebhookLogger(WEBHOOK_URL) if WEBHOOK_URL else None
        self._slash_error_cache: dict[tuple[int, str, type[Exception]], datetime] = {}
        self._slash_cache_cleanup_task: Optional[asyncio.Task] = None
        self._background_started = False

    def cog_unload(self) -> None:
        self._background_started = False

        if self._slash_cache_cleanup_task is not None:
            self._slash_cache_cleanup_task.cancel()
            self._slash_cache_cleanup_task = None

        if self.webhook_logger is not None:
            self.bot.loop.create_task(self.webhook_logger.close())

    async def _start_background_tasks(self) -> None:
        if self._background_started:
            return

        self._background_started = True

        if self._slash_cache_cleanup_task is None or self._slash_cache_cleanup_task.done():
            self._slash_cache_cleanup_task = asyncio.create_task(self._cleanup_slash_error_cache_loop())

        if self.webhook_logger is not None:
            await self.webhook_logger.start()

        logger.info("Error handler background tasks started")

    async def _cleanup_slash_error_cache_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(ERROR_CACHE_TTL_SECONDS)
                self._prune_slash_error_cache()
        except asyncio.CancelledError:
            return

    def _prune_slash_error_cache(self) -> None:
        now = datetime.now(timezone.utc)

        expired_keys = [
            key
            for key, created_at in self._slash_error_cache.items()
            if (now - created_at).total_seconds() > ERROR_CACHE_TTL_SECONDS
        ]
        for key in expired_keys:
            self._slash_error_cache.pop(key, None)

        if len(self._slash_error_cache) > MAX_SLASH_ERROR_CACHE_SIZE:
            logger.warning("Slash error cache exceeded max size, pruning oldest entries")
            overflow = len(self._slash_error_cache) - MAX_SLASH_ERROR_CACHE_SIZE
            oldest_keys = [
                key
                for key, _ in heapq.nsmallest(
                    overflow,
                    self._slash_error_cache.items(),
                    key=lambda item: item[1],
                )
            ]
            for key in oldest_keys:
                self._slash_error_cache.pop(key, None)

    @staticmethod
    def unwrap_error(error: Exception) -> Exception:
        if isinstance(error, commands.CommandInvokeError) and getattr(error, "original", None):
            return error.original
        if isinstance(error, discord.ApplicationCommandInvokeError) and getattr(error, "original", None):
            return error.original
        return error

    @staticmethod
    def is_critical_error(error: Exception) -> bool:
        if isinstance(error, commands.CommandOnCooldown):
            return False
        if isinstance(error, tuple(ERROR_MAP.keys())):
            return False
        if isinstance(error, tuple(DISCORD_API_ERRORS.keys())):
            return False
        if isinstance(error, commands.CommandError):
            return False
        return True

    @staticmethod
    def build_basic_error_embed(title: str, description: str) -> discord.Embed:
        return discord.Embed(
            color=discord.Color.red(),
            title=title,
            description=f"{ERROREMOJI} | {description}",
        )

    @staticmethod
    def build_unexpected_error_embed(user_display: str, error: Exception) -> discord.Embed:
        embed = discord.Embed(
            color=discord.Color.red(),
            title="Command Error",
            description=(
                f"{ERROREMOJI} | An unexpected error occurred.\n"
                f"Please report this issue on [GitHub]({SUPPORT_SERVER})."
            ),
        )
        embed.set_author(name=user_display)
        embed.add_field(
            name="Error",
            value=f"```py\n{shorten_codeblock_text(error, 900)}```",
            inline=False,
        )
        return embed

    @staticmethod
    def _get_ctx_user(ctx) -> Optional[Union[discord.Member, discord.User]]:
        return getattr(ctx, "author", getattr(ctx, "user", None))

    @staticmethod
    def _interaction_age_seconds(interaction: Optional[discord.Interaction]) -> float:
        if interaction is None:
            return float("inf")

        created_at = getattr(interaction, "created_at", None)
        if created_at is None:
            return 0.0

        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        return max(0.0, (datetime.now(timezone.utc) - created_at).total_seconds())

    @classmethod
    def _can_send_initial_interaction_response(cls, interaction: Optional[discord.Interaction]) -> bool:
        return cls._interaction_age_seconds(interaction) < INITIAL_INTERACTION_RESPONSE_DEADLINE_SECONDS

    @classmethod
    def _can_send_interaction_followup(cls, interaction: Optional[discord.Interaction]) -> bool:
        return cls._interaction_age_seconds(interaction) < FOLLOWUP_INTERACTION_TTL_SECONDS

    async def _send_channel_fallback(
        self,
        ctx: Union[commands.Context, discord.ApplicationContext],
        embed: discord.Embed,
        *,
        delete_after: Optional[float] = None,
    ) -> bool:
        channel = getattr(ctx, "channel", None)
        if channel is None or not hasattr(channel, "send"):
            logger.warning("No usable channel fallback available for %s", type(ctx).__name__)
            return False

        user = self._get_ctx_user(ctx)
        content = getattr(user, "mention", None) if delete_after is not None else None

        try:
            await channel.send(content=content, embed=embed, delete_after=delete_after)
            return True
        except discord.Forbidden:
            logger.warning(
                "Missing permission to send fallback error message in channel=%s",
                getattr(channel, "id", None),
            )
            return False
        except discord.HTTPException:
            logger.exception("Failed to send fallback channel error message")
            return False

    async def _send_via_interaction_or_fallback(
        self,
        ctx: Union[commands.Context, discord.ApplicationContext],
        embed: discord.Embed,
        *,
        ephemeral: bool,
    ) -> None:
        interaction = getattr(ctx, "interaction", None)
        delete_after = EPHEMERAL_FALLBACK_DELETE_AFTER_SECONDS if ephemeral else None

        if interaction is None:
            if isinstance(ctx, commands.Context):
                try:
                    await ctx.reply(embed=embed, mention_author=False)
                    return
                except discord.HTTPException:
                    logger.exception("Failed to send prefix command error response")
                    return

            await self._send_channel_fallback(ctx, embed, delete_after=delete_after)
            return

        try:
            if interaction.response.is_done():
                if self._can_send_interaction_followup(interaction):
                    await interaction.followup.send(embed=embed, ephemeral=ephemeral)
                    return
            else:
                if self._can_send_initial_interaction_response(interaction):
                    await interaction.response.send_message(embed=embed, ephemeral=ephemeral)
                    return
        except discord.InteractionResponded:
            if self._can_send_interaction_followup(interaction):
                try:
                    await interaction.followup.send(embed=embed, ephemeral=ephemeral)
                    return
                except discord.NotFound:
                    logger.warning("Interaction followup token expired while sending error response")
                except discord.HTTPException:
                    logger.exception("Failed to send followup error response after race")
            else:
                logger.warning("Interaction was already responded to, but the followup token expired")
        except discord.NotFound:
            logger.warning("Interaction token expired or became invalid while sending error response")
        except discord.HTTPException:
            logger.exception("Failed to send interaction error response")

        sent = await self._send_channel_fallback(ctx, embed, delete_after=delete_after)
        if not sent:
            logger.warning("Failed to deliver error response after interaction fallback")

    async def send_error_embed(
        self,
        ctx: Union[commands.Context, discord.ApplicationContext],
        title: str,
        description: str,
        *,
        ephemeral: bool = True,
    ) -> None:
        embed = self.build_basic_error_embed(title, description)
        await self._send_via_interaction_or_fallback(ctx, embed, ephemeral=ephemeral)

    async def maybe_report_critical_error(self, ctx, error: Exception) -> None:
        if self.is_critical_error(error) and self.webhook_logger is not None:
            await self.webhook_logger.send_error(ctx, error)

    @staticmethod
    def resolve_known_error(error: Exception) -> Optional[tuple[str, str]]:
        if isinstance(error, commands.CommandOnCooldown):
            timestamp = cooldown_timestamp(error.retry_after)
            return "Cooldown", f"This command is on cooldown. Try again {timestamp}."

        for error_type, payload in ERROR_MAP.items():
            if isinstance(error, error_type):
                return payload

        for error_type, payload in DISCORD_API_ERRORS.items():
            if isinstance(error, error_type):
                return payload

        return None

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        await self._start_background_tasks()

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: Exception) -> None:
        error = self.unwrap_error(error)

        if isinstance(error, commands.CommandNotFound):
            return

        if getattr(ctx.command, "on_error", None):
            return

        cog = getattr(ctx.command, "cog", None)
        if cog is not None and hasattr(cog, "cog_command_error"):
            return

        known = self.resolve_known_error(error)
        if known is not None:
            title, description = known
            await self.send_error_embed(ctx, title, description, ephemeral=False)
            return

        await self.maybe_report_critical_error(ctx, error)

        embed = self.build_unexpected_error_embed(str(ctx.author), error)
        await self._send_via_interaction_or_fallback(ctx, embed, ephemeral=False)

    @commands.Cog.listener()
    async def on_application_command_error(self, ctx: discord.ApplicationContext, error: Exception) -> None:
        error = self.unwrap_error(error)

        command_obj = getattr(ctx, "command", None)
        command_name = getattr(command_obj, "qualified_name", getattr(command_obj, "name", "unknown")) if command_obj else "unknown"
        cache_key = (ctx.user.id, command_name, type(error))
        now = datetime.now(timezone.utc)

        last_seen = self._slash_error_cache.get(cache_key)
        if last_seen is not None and (now - last_seen).total_seconds() < SLASH_ERROR_DEDUP_SECONDS:
            logger.debug("Suppressed duplicate slash error: %s", cache_key)
            return

        self._slash_error_cache[cache_key] = now
        self._prune_slash_error_cache()

        known = self.resolve_known_error(error)
        if known is not None:
            title, description = known
            await self.send_error_embed(ctx, title, description, ephemeral=True)
            return

        await self.maybe_report_critical_error(ctx, error)

        embed = self.build_unexpected_error_embed(str(ctx.user), error)
        await self._send_via_interaction_or_fallback(ctx, embed, ephemeral=True)

    @commands.Cog.listener()
    async def on_error(self, event_method: str, *args, **_kwargs) -> None:
        exc_type, exc_value, exc_tb = sys.exc_info()
        if exc_value is None:
            return

        ctx = None
        for arg in args:
            if isinstance(arg, (discord.Message, discord.Interaction, commands.Context, discord.ApplicationContext)):
                ctx = arg
                break

        await self.maybe_report_critical_error(ctx, exc_value)
        logger.exception(
            "Unhandled global error in event %s (context: %s)",
            event_method,
            type(ctx).__name__ if ctx else "None",
            exc_info=(exc_type, exc_value, exc_tb),
        )


def setup(bot: commands.Bot) -> None:
    bot.add_cog(ErrorHandler(bot))
