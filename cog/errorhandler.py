from utils.imports import *
from utils.secrets import WEBHOOK_URL
from utils.helper.errorhelper import (
    build_basic_error_embed,
    build_plain_component_error,
    build_unexpected_error_embed,
    can_send_initial_interaction_response,
    can_send_interaction_followup,
    get_ctx_user,
    is_critical_error,
    resolve_known_error,
    shorten_codeblock_text,
    unwrap_error,
)

logger = logging.getLogger("bot.errors")

ERROR_CACHE_TTL_SECONDS = 300
ERROR_WEBHOOK_DEDUP_SECONDS = 60
SLASH_ERROR_DEDUP_SECONDS = 10

MAX_WEBHOOK_ERROR_CACHE_SIZE = 250
MAX_SLASH_ERROR_CACHE_SIZE = 500

EPHEMERAL_FALLBACK_DELETE_AFTER_SECONDS = 30.0
REPORT_COMMAND_NOT_FOUND_TO_WEBHOOK = False


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

    def _is_duplicate(self, fingerprint: str, now: datetime) -> bool:
        last_seen = self._error_cache.get(fingerprint)

        if last_seen is not None and (now - last_seen).total_seconds() < ERROR_WEBHOOK_DEDUP_SECONDS:
            return True

        self._error_cache[fingerprint] = now
        self._prune_cache()
        return False

    @staticmethod
    def _safe_field(value: object, *, fallback: str = "Unknown", limit: int = 900) -> str:
        text = str(value).strip() if value is not None else fallback

        if not text:
            text = fallback

        text = text.replace("`", "'")

        if len(text) > limit:
            text = text[: limit - 3] + "..."

        return text

    @classmethod
    def describe_interaction(cls, ctx, item=None) -> str:
        interaction = ctx if isinstance(ctx, discord.Interaction) else getattr(ctx, "interaction", None)

        if interaction is None:
            return "No interaction object"

        interaction_type = cls._safe_field(getattr(interaction, "type", None))
        custom_id = "N/A"
        component_type = "N/A"
        values = "N/A"

        data = getattr(interaction, "data", None)
        if isinstance(data, dict):
            custom_id = cls._safe_field(data.get("custom_id"), fallback="N/A")
            component_type = cls._safe_field(data.get("component_type"), fallback="N/A")

            raw_values = data.get("values")
            if raw_values:
                values = cls._safe_field(", ".join(map(str, raw_values)), fallback="N/A")

        return (
            f"Type: {interaction_type}\n"
            f"Custom ID: {custom_id}\n"
            f"Component Type: {component_type}\n"
            f"Values: {values}"
        )

    @classmethod
    def describe_component_item(cls, item) -> str:
        if item is None:
            return "N/A"

        item_type = type(item).__name__
        custom_id = cls._safe_field(getattr(item, "custom_id", None), fallback="N/A")
        label = cls._safe_field(getattr(item, "label", None), fallback="N/A")
        placeholder = cls._safe_field(getattr(item, "placeholder", None), fallback="N/A")
        row = cls._safe_field(getattr(item, "row", None), fallback="N/A")

        view = getattr(item, "view", None)
        view_name = type(view).__name__ if view is not None else "N/A"

        return (
            f"Item: {item_type}\n"
            f"View: {view_name}\n"
            f"Custom ID: {custom_id}\n"
            f"Label: {label}\n"
            f"Placeholder: {placeholder}\n"
            f"Row: {row}"
        )

    async def send_error(
        self,
        ctx,
        error: Exception,
        *,
        item=None,
        source: Optional[str] = None,
    ) -> None:
        now = datetime.now(timezone.utc)

        tb_full = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        tb_short = "".join(traceback.format_exception_only(type(error), error))
        fingerprint = hashlib.sha256(tb_full.encode("utf-8", errors="replace")).hexdigest()

        if self._is_duplicate(fingerprint, now):
            return

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
            if command_obj
            else "Unknown"
        )

        event_type = type(ctx).__name__ if ctx is not None else "Unknown"
        discord_timestamp = f"<t:{int(now.timestamp())}:F>"

        interaction_info = self.describe_interaction(ctx, item=item)
        component_info = self.describe_component_item(item)

        message = getattr(ctx, "message", None)
        if message is None:
            interaction = ctx if isinstance(ctx, discord.Interaction) else getattr(ctx, "interaction", None)
            message = getattr(interaction, "message", None)

        message_id = getattr(message, "id", "N/A")
        source_text = source or event_type

        embed = {
            "title": "🚨 Bot Error",
            "color": 0xED4245,
            "fields": [
                {"name": "Source", "value": f"`{self._safe_field(source_text)}`", "inline": True},
                {"name": "User", "value": f"{user_name} (`{user_id}`)", "inline": True},
                {"name": "Guild", "value": f"{guild_name} (`{guild_id}`)", "inline": True},
                {"name": "Channel", "value": f"{channel_name} (`{channel_type}`)", "inline": True},
                {"name": "Message ID", "value": f"`{message_id}`", "inline": True},
                {"name": "Command/Event", "value": f"{command_name} / `{event_type}`", "inline": True},
                {"name": "Interaction", "value": f"```txt\n{interaction_info}```", "inline": False},
                {"name": "Component", "value": f"```txt\n{component_info}```", "inline": False},
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
            tb_full.encode("utf-8", errors="replace"),
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

        user = get_ctx_user(ctx)
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
                if can_send_interaction_followup(interaction):
                    await interaction.followup.send(embed=embed, ephemeral=ephemeral)
                    return
            else:
                if can_send_initial_interaction_response(interaction):
                    await interaction.response.send_message(embed=embed, ephemeral=ephemeral)
                    return

        except discord.InteractionResponded:
            if can_send_interaction_followup(interaction):
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

    async def send_plain_interaction_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        *,
        source: str = "Unknown interaction",
    ) -> None:
        try:
            content = build_plain_component_error(error, source=source)
        except TypeError:
            logger.warning(
                "build_plain_component_error does not support source=. Update utils.helper.errorhelper.",
                exc_info=True,
            )
            content = build_plain_component_error(error)

        try:
            if interaction.response.is_done():
                await interaction.followup.send(content=content, ephemeral=True)
            else:
                await interaction.response.send_message(content=content, ephemeral=True)

        except (discord.NotFound, discord.HTTPException):
            logger.exception("Failed to send component error response")

    async def send_error_embed(
        self,
        ctx: Union[commands.Context, discord.ApplicationContext],
        title: str,
        description: str,
        *,
        ephemeral: bool = True,
    ) -> None:
        embed = build_basic_error_embed(title, description)
        await self._send_via_interaction_or_fallback(ctx, embed, ephemeral=ephemeral)

    async def maybe_report_critical_error(self, ctx, error: Exception) -> None:
        if is_critical_error(error) and self.webhook_logger is not None:
            await self.webhook_logger.send_error(ctx, error)

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        await self._start_background_tasks()

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: Exception) -> None:
        error = unwrap_error(error)

        if isinstance(error, commands.CommandNotFound):
            if REPORT_COMMAND_NOT_FOUND_TO_WEBHOOK and self.webhook_logger is not None:
                await self.webhook_logger.send_error(ctx, error, source="Prefix command not found")
            return

        if getattr(ctx.command, "on_error", None):
            await self.maybe_report_critical_error(ctx, error)
            return

        cog = getattr(ctx.command, "cog", None)
        if cog is not None and hasattr(cog, "cog_command_error"):
            await self.maybe_report_critical_error(ctx, error)
            return

        known = resolve_known_error(error)
        if known is not None:
            title, description = known
            await self.send_error_embed(ctx, title, description, ephemeral=False)
            return

        await self.maybe_report_critical_error(ctx, error)

        embed = build_unexpected_error_embed(str(ctx.author), error)
        await self._send_via_interaction_or_fallback(ctx, embed, ephemeral=False)

    @commands.Cog.listener()
    async def on_application_command_error(self, ctx: discord.ApplicationContext, error: Exception) -> None:
        error = unwrap_error(error)

        command_obj = getattr(ctx, "command", None)
        command_name = (
            getattr(command_obj, "qualified_name", getattr(command_obj, "name", "unknown"))
            if command_obj
            else "unknown"
        )

        cache_key = (ctx.user.id, command_name, type(error))
        now = datetime.now(timezone.utc)

        last_seen = self._slash_error_cache.get(cache_key)
        if last_seen is not None and (now - last_seen).total_seconds() < SLASH_ERROR_DEDUP_SECONDS:
            logger.debug("Suppressed duplicate slash error: %s", cache_key)
            return

        self._slash_error_cache[cache_key] = now
        self._prune_slash_error_cache()

        known = resolve_known_error(error)
        if known is not None:
            title, description = known
            await self.send_error_embed(ctx, title, description, ephemeral=True)
            return

        await self.maybe_report_critical_error(ctx, error)

        embed = build_unexpected_error_embed(str(ctx.user), error)
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

        if self.webhook_logger is not None:
            await self.webhook_logger.send_error(ctx, exc_value, source=f"Event: {event_method}")

        logger.exception(
            "Unhandled global error in event %s (context: %s)",
            event_method,
            type(ctx).__name__ if ctx else "None",
            exc_info=(exc_type, exc_value, exc_tb),
        )

    @commands.Cog.listener()
    async def on_view_error(
        self,
        error: Exception,
        item,
        interaction: discord.Interaction,
    ) -> None:
        error = unwrap_error(error)

        item_name = type(item).__name__ if item is not None else "UnknownItem"
        custom_id = getattr(item, "custom_id", None) or "no-custom-id"
        label = getattr(item, "label", None)
        placeholder = getattr(item, "placeholder", None)

        source = f"View component: {item_name} | custom_id={custom_id}"

        if label:
            source += f" | label={label}"

        if placeholder:
            source += f" | placeholder={placeholder}"

        if self.webhook_logger is not None:
            await self.webhook_logger.send_error(
                interaction,
                error,
                item=item,
                source=source,
            )

        await self.send_plain_interaction_error(
            interaction,
            error,
            source=source,
        )

    @commands.Cog.listener()
    async def on_modal_error(
        self,
        error: Exception,
        interaction: discord.Interaction,
    ) -> None:
        error = unwrap_error(error)

        data = getattr(interaction, "data", None)
        custom_id = "unknown-modal"

        if isinstance(data, dict):
            custom_id = data.get("custom_id") or custom_id

        source = f"Modal submit: custom_id={custom_id}"

        if self.webhook_logger is not None:
            await self.webhook_logger.send_error(
                interaction,
                error,
                source=source,
            )

        await self.send_plain_interaction_error(
            interaction,
            error,
            source=source,
        )


def setup(bot: commands.Bot) -> None:
    bot.add_cog(ErrorHandler(bot))
