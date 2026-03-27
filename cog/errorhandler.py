from utils.imports import *

_error_cache = {}

async def send_error_webhook(ctx, error):
    now = datetime.now(timezone.utc)
    webhook_url = WEBHOOK_URL
    if not webhook_url:
        print("Webhook URL not set in .env")
        return

    try:
        tb_full = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        tb_short = "".join(traceback.format_exception_only(type(error), error))
        fingerprint = hashlib.sha256(tb_full.encode()).hexdigest()

        if fingerprint in _error_cache:
            if (now - _error_cache[fingerprint]).total_seconds() < 60:
                return
        _error_cache[fingerprint] = now

        user = getattr(ctx, "author", getattr(ctx, "user", None))
        user_name = getattr(user, "name", "Unknown")
        user_id = getattr(user, "id", "Unknown")
        guild = getattr(ctx, "guild", None)
        guild_name = getattr(guild, "name", "DM") if guild else "DM"
        guild_id = getattr(guild, "id", "DM") if guild else "DM"
        channel = getattr(ctx, "channel", None)
        channel_name = getattr(channel, "name", getattr(channel, "id", "Unknown"))
        channel_type = getattr(channel, "type", "Unknown")
        command = getattr(ctx.command, "qualified_name", getattr(ctx, "name", "Unknown"))
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


        async with aiohttp.ClientSession() as session:
            json_payload = {"embeds": [embed]}

            form = aiohttp.FormData()
            form.add_field("file",
                           tb_full.encode("utf-8"),
                           filename="error_log.txt",
                           content_type="text/plain")

            async with session.post(webhook_url, json=json_payload) as resp1:
                if resp1.status >= 400:
                    print(f"Webhook embed failed: {resp1.status}")

            async with session.post(webhook_url, data=form) as resp2:
                if resp2.status >= 400:
                    print(f"Webhook file upload failed: {resp2.status}")

    except Exception as e:
        print("send_error_webhook exception:", e)
async def cleanup_error_cache():
    while True:
        await asyncio.sleep(300)
        now = datetime.now(timezone.utc)

        to_delete = [
            k for k, v in _error_cache.items()
            if (now - v).total_seconds() > 300
        ]

        for k in to_delete:
            del _error_cache[k]

# ---------------------------------------


class ErrorHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._error_cache = {}
        self.task = bot.loop.create_task(cleanup_error_cache())

        bot.add_listener(self.on_global_error)

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

    async def on_global_error(self, event_method, *args, **kwargs):
        exc_type, exc_value, exc_tb = sys.exc_info()
        if exc_value is None:
            return

        ctx = None
        for arg in args:
            if isinstance(arg, (discord.Message, discord.Interaction, commands.Context)):
                ctx = arg
                break

        try:
            await send_error_webhook(ctx, exc_value)
        except Exception as e:
            print(f"Failed to send error to webhook: {e}")

        traceback.print_exception(exc_type, exc_value, exc_tb)


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
            await send_error_webhook(ctx, error)
            await self.send_error_embed(
                ctx,
                "Cooldown",
                f"This command is on cooldown. Try again {timestamp}."
            )
            return

        for error_type, (title, description) in error_map.items():
            if isinstance(error, error_type):
                await send_error_webhook(ctx, error)
                await self.send_error_embed(ctx, title, description)
                return

        embed = discord.Embed(
            color=discord.Color.red(),
            title="Command Error",
            description=f"{E} | An unexpected error occurred!\nPlease report this issue on [Github]({SUPPORT_SERVER})."
        )
        embed.set_author(name=getattr(ctx, "author", getattr(ctx, "user", None)))
        embed.add_field(name="Error", value=f"```py\n{error}```")
        await send_error_webhook(ctx, error)
        await ctx.reply(embed=embed)

    @commands.Cog.listener()
    async def on_application_command_error(self, ctx, error):
        now = datetime.now(timezone.utc)
        key = (ctx.user.id, getattr(ctx.command, 'name', 'unknown'), type(error))

        if key in self._error_cache:
            if now - self._error_cache[key] < timedelta(seconds=10):
                return
        self._error_cache[key] = now

        if isinstance(error, commands.CheckFailure):
            await send_error_webhook(ctx, error)
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
            await send_error_webhook(ctx, error)
            if not ctx.response.is_done():
                await ctx.respond(embed=embed, ephemeral=True)
            else:
                await ctx.followup.send(embed=embed, ephemeral=True)
        except discord.errors.HTTPException:
            pass


def setup(bot):
    bot.add_cog(ErrorHandler(bot))
