from utils.imports import *
from utils.secrets import OWNER, SUPPORT_SERVER

logger = logging.getLogger("bot.user")

OWNER_COGS = {"Owner"}
APPLICATION_COMMAND_TYPES = {"SlashCommand", "SlashCommandGroup"}
PREFIX_COMMAND_TYPES = {"Command", "Group"}
BRIDGE_COMMAND_TYPES = {"BridgeCommand", "BridgeCommandGroup"}
HELP_TIMEOUT_SECONDS = 120


def get_owner_ids() -> set[int]:
    if OWNER is None:
        return set()
    if isinstance(OWNER, int):
        return {OWNER}
    if isinstance(OWNER, str):
        return {int(p) for p in re.split(r"[,;\s]+", OWNER) if p.strip().isdigit()}

    try:
        return {int(owner_id) for owner_id in OWNER}
    except TypeError:
        return set()


def is_bot_owner(user_id: int) -> bool:
    return user_id in get_owner_ids()


def safe_plain(value: object, *, fallback: str = "N/A", limit: int = 900) -> str:
    if value is None:
        return fallback

    text = str(value).strip()
    if not text:
        return fallback

    return text if len(text) <= limit else text[:limit - 1] + "…"


def safe_md(value: object, *, fallback: str = "N/A", limit: int = 900) -> str:
    text = safe_plain(value, fallback=fallback, limit=limit)
    return discord.utils.escape_markdown(text)


def format_datetime(value: Optional[datetime]) -> str:
    if value is None:
        return "N/A"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return f"{format_dt(value, 'F')} ({format_dt(value, 'R')})"


def yes_no(value: bool) -> str:
    return "✅ Yes" if value else "❌ No"


def format_number(value: object) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "N/A"


def status_name(value: object) -> str:
    raw = str(value or "unknown").lower()
    return {
        "online": "🟢 Online",
        "idle": "🌙 Idle",
        "dnd": "⛔ Do Not Disturb",
        "offline": "⚫ Offline / Invisible",
        "invisible": "⚫ Offline / Invisible",
    }.get(raw, raw.replace("_", " ").title())


def enum_name(value: object) -> str:
    name = getattr(value, "name", value)
    return safe_md(name).replace("_", " ").title()


def bytes_to_mib(value: Optional[int]) -> str:
    return f"{value / 1024 / 1024:.0f} MiB" if isinstance(value, int) and value > 0 else "N/A"


def limited_join(values: list[str], *, empty: str = "None", limit: int = 10) -> str:
    if not values:
        return empty

    shown = values[:limit]
    extra = len(values) - len(shown)
    return ", ".join(shown) + (f" +{extra} more" if extra else "")


def channel_mention(channel: object) -> str:
    return getattr(channel, "mention", None) or "N/A"


def important_permissions(member: discord.Member) -> str:
    if member.guild_permissions.administrator:
        return "👑 Administrator"

    important = (
        "manage_guild",
        "manage_roles",
        "manage_channels",
        "manage_messages",
        "manage_threads",
        "moderate_members",
        "ban_members",
        "kick_members",
        "manage_webhooks",
        "manage_emojis_and_stickers",
    )

    granted = [
        perm.replace("_", " ").title()
        for perm in important
        if getattr(member.guild_permissions, perm, False)
    ]
    return limited_join(granted, empty="None", limit=8)


def activity_text(activity: discord.Activity) -> Optional[str]:
    name = getattr(activity, "name", None)
    if not name:
        return None

    activity_type = getattr(activity, "type", None)
    type_name = getattr(activity_type, "name", None)
    prefix = f"{type_name.replace('_', ' ').title()}: " if type_name else ""
    return f"{prefix}{safe_plain(name, limit=80)}"


def command_emoji(name: str) -> str:
    mapping = {
        "help": "📚",
        "about": "🤖",
        "userinfo": "👤",
        "serverinfo": "🏠",
        "owner": "👑",
    }

    lowered = name.lower()
    for key, emoji in mapping.items():
        if key in lowered:
            return emoji

    return "🔹"


def get_prefix_display(bot) -> str:
    prefix = getattr(bot, "command_prefix", None)

    if isinstance(prefix, str):
        return prefix

    if isinstance(prefix, (list, tuple)) and prefix:
        return str(prefix[0])

    if isinstance(prefix, set) and prefix:
        return str(sorted(prefix)[0])

    return "<prefix>"


def command_mention(cmd_name: str, cmd_id: Optional[int], *, kind: str = "slash", prefix: str = "/") -> str:
    if kind == "slash":
        return f"</{cmd_name}:{cmd_id}>" if cmd_id else f"`/{cmd_name}`"

    if kind == "bridge":
        slash = f"</{cmd_name}:{cmd_id}>" if cmd_id else f"`/{cmd_name}`"
        return f"{slash} / `{prefix}{cmd_name}`"

    return f"`{prefix}{cmd_name}`"


def is_owner_command(cmd) -> bool:
    if getattr(cmd, "owner_only", False):
        return True

    for check in getattr(cmd, "checks", []):
        check_text = " ".join(
            str(part)
            for part in (
                getattr(check, "__name__", ""),
                getattr(check, "__qualname__", ""),
                repr(check),
            )
        ).lower()

        if "is_owner" in check_text or "is_bot_owner" in check_text or "owner_only" in check_text:
            return True

    return False


def command_kind(cmd) -> Optional[str]:
    type_name = type(cmd).__name__

    if type_name in APPLICATION_COMMAND_TYPES:
        return "slash"
    if type_name in BRIDGE_COMMAND_TYPES:
        return "bridge"
    if type_name in PREFIX_COMMAND_TYPES:
        return "prefix"

    return None


def is_visible_command(cmd, *, include_owner: bool = False) -> bool:
    if command_kind(cmd) is None:
        return False

    if getattr(cmd, "hidden", False) and not include_owner:
        return False

    if is_owner_command(cmd) and not include_owner:
        return False

    return True


def command_children(cmd):
    return list(getattr(cmd, "subcommands", None) or getattr(cmd, "commands", None) or [])


def command_description(cmd) -> str:
    return (
        getattr(cmd, "description", None)
        or getattr(cmd, "brief", None)
        or getattr(cmd, "help", None)
        or "No description"
    )


def iter_main_commands(bot):
    seen = set()

    for source in (
        getattr(bot, "application_commands", []) or [],
        getattr(bot, "commands", []) or [],
    ):
        for cmd in source:
            if getattr(cmd, "cog", None) is not None:
                continue

            key = (
                type(cmd).__name__,
                getattr(cmd, "qualified_name", None) or getattr(cmd, "name", None),
            )
            if key in seen:
                continue

            seen.add(key)
            yield cmd


def gather_commands_recursive(
    cmd,
    prefix: str = "",
    root_command_id: Optional[int] = None,
    *,
    include_owner: bool = False,
):
    if not is_visible_command(cmd, include_owner=include_owner):
        return []

    kind = command_kind(cmd) or "prefix"
    current_name = f"{prefix}{cmd.name}".strip()
    command_id = None if kind == "prefix" else root_command_id or getattr(cmd, "id", None)
    children = command_children(cmd)

    if children:
        result = []
        for sub in children:
            result.extend(
                gather_commands_recursive(
                    sub,
                    f"{current_name} ",
                    command_id,
                    include_owner=include_owner,
                )
            )
        return result

    return [(current_name, command_description(cmd), command_id, kind)]

class HelpView(View):
    def __init__(self, embeds, requester_id: int, page_info=None, *, timeout: int = HELP_TIMEOUT_SECONDS):
        super().__init__(timeout=timeout)
        self.timeout_seconds = timeout

        self.embeds = embeds
        self.requester_id = requester_id
        self.current_page = 0
        self.page_info = page_info or {}

        self.select_menu = Select(
            placeholder="📚 Jump to a command category...",
            options=self.build_select_options()
        )
        self.select_menu.callback = self.select_category

        self.first_button = Button(label="First", emoji="⏮️", style=discord.ButtonStyle.secondary)
        self.prev_button = Button(label="Back", emoji="⬅️", style=discord.ButtonStyle.secondary)
        self.next_button = Button(label="Next", emoji="➡️", style=discord.ButtonStyle.secondary)
        self.last_button = Button(label="Last", emoji="⏭️", style=discord.ButtonStyle.secondary)
        self.close_button = Button(label="Close", emoji="✖️", style=discord.ButtonStyle.danger)

        self.first_button.callback = self.first_page
        self.prev_button.callback = self.prev_page
        self.next_button.callback = self.next_page
        self.last_button.callback = self.last_page
        self.close_button.callback = self.close_help

        self.add_item(self.select_menu)
        self.add_item(self.first_button)
        self.add_item(self.prev_button)
        self.add_item(self.next_button)
        self.add_item(self.last_button)
        self.add_item(self.close_button)

        self.update_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.requester_id:
            return True

        await interaction.response.send_message(
            "Only the user who opened this help menu can use it.",
            ephemeral=True,
        )
        return False

    def build_select_options(self):
        max_options = 25
        total = len(self.embeds)

        if total <= max_options:
            start = 0
        else:
            start = max(0, min(self.current_page - 12, total - max_options))

        end = min(start + max_options, total)
        options = []

        for idx in range(start, end):
            embed = self.embeds[idx]

            if "📂" in embed.title:
                base_name = embed.title.split("📂 ")[1].split(" (Page")[0].split(" Commands")[0]
            else:
                base_name = embed.title[:50]

            if idx in self.page_info and self.page_info[idx]["total_pages"] > 1:
                label = f"{base_name} • Pg {self.page_info[idx]['page']}/{self.page_info[idx]['total_pages']}"
            else:
                label = base_name

            if len(label) > 100:
                label = label[:97] + "..."

            description = f"{len(embed.fields)} commands • Page {idx + 1}/{total}"
            if len(description) > 100:
                description = description[:97] + "..."

            options.append(
                discord.SelectOption(
                    label=label,
                    value=str(idx),
                    description=description,
                    emoji="📂" if "📂" in embed.title else "📄",
                    default=(idx == self.current_page),
                )
            )

        return options

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

        if not hasattr(self, "message"):
            return

        with contextlib.suppress(discord.HTTPException, discord.NotFound, AttributeError):
            embed = self.embeds[self.current_page]
            embed.set_footer(text="Help menu expired. Run /help again.")
            await self.message.edit(embed=embed, view=self)

    async def edit_current_page(self, interaction: discord.Interaction):
        self.update_buttons()
        await interaction.response.edit_message(
            embed=self.embeds[self.current_page],
            view=self,
        )

    async def first_page(self, interaction: discord.Interaction):
        self.current_page = 0
        await self.edit_current_page(interaction)

    async def prev_page(self, interaction: discord.Interaction):
        self.current_page = max(self.current_page - 1, 0)
        await self.edit_current_page(interaction)

    async def next_page(self, interaction: discord.Interaction):
        self.current_page = min(self.current_page + 1, len(self.embeds) - 1)
        await self.edit_current_page(interaction)

    async def last_page(self, interaction: discord.Interaction):
        self.current_page = len(self.embeds) - 1
        await self.edit_current_page(interaction)

    async def select_category(self, interaction: discord.Interaction):
        self.current_page = int(self.select_menu.values[0])
        await self.edit_current_page(interaction)

    async def close_help(self, interaction: discord.Interaction):
        await interaction.response.defer()

        with contextlib.suppress(discord.HTTPException, discord.NotFound):
            await interaction.delete_original_response()
            return

        with contextlib.suppress(discord.HTTPException, discord.NotFound, AttributeError):
            await interaction.message.delete()

    def update_buttons(self):
        self.first_button.disabled = self.current_page <= 0
        self.prev_button.disabled = self.current_page <= 0
        self.next_button.disabled = self.current_page >= len(self.embeds) - 1
        self.last_button.disabled = self.current_page >= len(self.embeds) - 1
        self.select_menu.options = self.build_select_options()

class InfoContainerView(DesignerView):
    def __init__(self, container: Container):
        super().__init__(timeout=None)
        self.add_item(container)

class AboutView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(
            Button(
                label="GitHub",
                emoji="🔗",
                style=discord.ButtonStyle.link,
                url=SUPPORT_SERVER,
            )
        )

class User(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.MAX_FIELDS_PER_EMBED = 20
        self.start_time = datetime.now(timezone.utc)

    def format_timedelta(self, delta: timedelta) -> str:
        days = delta.days
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"🗓️ {days}d ⏰ {hours}h ⏳ {minutes}m ⏲️ {seconds}s"

    def visible_command_count(self, *, include_owner: bool = False) -> int:
        total = 0

        for cmd in iter_main_commands(self.bot):
            total += len(gather_commands_recursive(cmd, include_owner=include_owner))

        for cog_name, cog in self.bot.cogs.items():
            if cog_name in OWNER_COGS and not include_owner:
                continue

            for cmd in getattr(cog, "get_commands", lambda: [])():
                total += len(gather_commands_recursive(cmd, include_owner=include_owner))

        return total

    async def fetch_user_profile(self, user_id: int) -> Optional[discord.User]:
        try:
            return await self.bot.fetch_user(user_id)
        except (discord.HTTPException, discord.NotFound, discord.Forbidden):
            return None

    async def build_userinfo_view(self, member: discord.Member) -> InfoContainerView:
        profile = await self.fetch_user_profile(member.id)
        now = datetime.now(timezone.utc)
        color = member.color if member.color and member.color.value else Color.blurple()

        devices = []
        for attr, label, emoji in (
            ("desktop_status", "Desktop", "🖥️"),
            ("mobile_status", "Mobile", "📱"),
            ("web_status", "Web", "🌐"),
        ):
            value = getattr(member, attr, None)
            if value is not None and value != discord.Status.offline:
                devices.append(f"{emoji} {label}: {status_name(value)}")

        activities = [
            text for activity in getattr(member, "activities", [])
            if (text := activity_text(activity))
        ]

        roles = [
            role.mention
            for role in sorted(member.roles[1:], key=lambda r: r.position, reverse=True)
            if not role.is_default()
        ]

        flags = []
        if profile and getattr(profile, "public_flags", None):
            with contextlib.suppress(Exception):
                for flag in profile.public_flags.all():
                    flag_name = getattr(flag, "name", None)

                    if flag_name is None:
                        flag_name = str(flag).split(".")[-1]

                    flags.append(str(flag_name).replace("_", " ").title())

        timeout_until = getattr(member, "timed_out_until", None)
        timeout_text = format_datetime(timeout_until) if timeout_until and timeout_until > now else "None"
        boost_since = getattr(member, "premium_since", None)
        guild_avatar = getattr(member, "guild_avatar", None)
        banner = getattr(profile, "banner", None) if profile else None
        accent_color = getattr(profile, "accent_color", None) if profile else None
        accent_text = f"#{accent_color.value:06X}" if accent_color else "N/A"

        header = (
            f"## 👤 User Info\n"
            f"### {safe_md(member.display_name, limit=120)}\n"
            f"- **Mention:** {member.mention}\n"
            f"- **Username:** `{safe_plain(member.name, limit=80)}`\n"
            f"- **Global:** `{safe_plain(getattr(member, 'global_name', None), limit=80)}`\n"
            f"- **ID:** `{member.id}` • **Bot:** `{yes_no(member.bot)}`"
        )

        profile_text = (
            f"### 🪪 Profile\n"
            f"- **Nick:** `{safe_plain(member.nick)}`\n"
            f"- **Status:** `{status_name(getattr(member, 'status', None))}`\n"
            f"- **Devices:** `{safe_plain(limited_join(devices), limit=250)}`\n"
            f"- **Activities:** `{safe_plain(limited_join(activities, limit=4), limit=400)}`\n"
            f"- **Badges:** `{safe_plain(limited_join(flags, limit=8), limit=300)}`\n"
            f"- **Accent:** `{accent_text}`"
        )

        server_text = (
            f"### 🏠 Server\n"
            f"- **Joined:** {format_datetime(getattr(member, 'joined_at', None))}\n"
            f"- **Created:** {format_datetime(member.created_at)}\n"
            f"- **Boosting:** {format_datetime(boost_since) if boost_since else 'N/A'}\n"
            f"- **Timeout:** {timeout_text}\n"
            f"- **Top role:** {member.top_role.mention if member.top_role and not member.top_role.is_default() else '`None`'}\n"
            f"- **Roles:** {limited_join(roles, limit=10)}\n"
            f"- **Key perms:** `{safe_plain(important_permissions(member), limit=300)}`"
        )

        container = Container(color=color)
        container.add_section(
            TextDisplay(header),
            accessory=Thumbnail(member.display_avatar.url, description=f"{member.display_name}'s avatar"),
        )
        container.add_separator(divider=True, spacing=SeparatorSpacingSize.small)
        container.add_text(profile_text)
        container.add_separator(divider=True, spacing=SeparatorSpacingSize.small)
        container.add_text(server_text)
        container.add_separator(divider=False, spacing=SeparatorSpacingSize.small)

        buttons = [
            UIButton(label="Avatar", emoji="🖼️", style=ButtonStyle.link, url=member.display_avatar.url)
        ]
        if guild_avatar:
            buttons.append(UIButton(label="Server Avatar", emoji="🏠", style=ButtonStyle.link, url=guild_avatar.url))
        if banner:
            buttons.append(UIButton(label="Banner", emoji="🎨", style=ButtonStyle.link, url=banner.url))

        container.add_row(*buttons[:5])
        return InfoContainerView(container)

    async def build_serverinfo_view(self, guild: Optional[discord.Guild]) -> InfoContainerView:
        if guild is None:
            container = Container(color=Color.red())
            container.add_text("## 🏠 Server Info\nThis command can only be used inside a server.")
            return InfoContainerView(container)

        now = datetime.now(timezone.utc)
        owner = guild.owner
        if owner is None and guild.owner_id:
            with contextlib.suppress(discord.HTTPException, discord.NotFound):
                owner = await guild.fetch_member(guild.owner_id)

        member_total = guild.member_count or len(guild.members)
        cached_bots = sum(1 for member in guild.members if member.bot)
        cached_humans = max(len(guild.members) - cached_bots, 0)

        forum_cls = getattr(discord, "ForumChannel", None)
        stage_cls = getattr(discord, "StageChannel", None)
        forum_channels = sum(1 for channel in guild.channels if forum_cls and isinstance(channel, forum_cls))
        stage_channels = sum(1 for channel in guild.channels if stage_cls and isinstance(channel, stage_cls))

        features = [feature.replace("_", " ").title() for feature in getattr(guild, "features", [])]
        stickers = getattr(guild, "stickers", [])
        scheduled_events = getattr(guild, "scheduled_events", [])
        vanity_code = getattr(guild, "vanity_url_code", None)
        description = safe_plain(getattr(guild, "description", None), fallback="No description set.", limit=250)

        header = (
            f"## 🏠 Server Info\n"
            f"### {safe_md(guild.name, limit=120)}\n"
            f"> {description}\n\n"
            f"- **ID:** `{guild.id}`\n"
            f"- **Owner:** {owner.mention if owner else f'`{guild.owner_id or "Unknown"}`'}\n"
            f"- **Created:** {format_datetime(guild.created_at)}\n"
            f"- **Locale:** `{safe_plain(getattr(guild, 'preferred_locale', None), limit=80)}`"
        )

        stats = (
            f"### 📊 Stats\n"
            f"- **Members:** `{format_number(member_total)}` total • `{format_number(cached_humans)}` humans cached • `{format_number(cached_bots)}` bots cached\n"
            f"- **Channels:** `{len(guild.text_channels)}` text • `{len(guild.voice_channels)}` voice • `{stage_channels}` stage • `{forum_channels}` forum • `{len(guild.categories)}` categories\n"
            f"- **Roles:** `{len(guild.roles)}` • **Threads:** `{len(getattr(guild, 'threads', []))}` • **Events:** `{len(scheduled_events)}`\n"
            f"- **Emojis:** `{len(guild.emojis)} / {getattr(guild, 'emoji_limit', 'N/A')}` • **Stickers:** `{len(stickers)} / {getattr(guild, 'sticker_limit', 'N/A')}`"
        )

        community = (
            f"### 🧭 Community & Limits\n"
            f"- **Rules:** {channel_mention(getattr(guild, 'rules_channel', None))} • **Updates:** {channel_mention(getattr(guild, 'public_updates_channel', None))}\n"
            f"- **System:** {channel_mention(getattr(guild, 'system_channel', None))} • **AFK:** {channel_mention(getattr(guild, 'afk_channel', None))}\n"
            f"- **Vanity:** `{safe_plain(vanity_code)}` • **AFK timeout:** `{getattr(guild, 'afk_timeout', 'N/A')}s`\n"
            f"- **Boosts:** `Tier {guild.premium_tier}` • `{guild.premium_subscription_count or 0}` boosts\n"
            f"- **Upload:** `{bytes_to_mib(getattr(guild, 'filesize_limit', None))}` • **Bitrate:** `{int(getattr(guild, 'bitrate_limit', 0) / 1000) if getattr(guild, 'bitrate_limit', 0) else 'N/A'} kbps`"
        )

        safety = (
            f"### 🛡️ Safety & Features\n"
            f"- **Verification:** `{enum_name(guild.verification_level)}`\n"
            f"- **Content filter:** `{enum_name(guild.explicit_content_filter)}`\n"
            f"- **MFA:** `{enum_name(guild.mfa_level)}` • **NSFW:** `{enum_name(getattr(guild, 'nsfw_level', 'N/A'))}`\n"
            f"- **Features:** `{safe_plain(limited_join(features, limit=16), limit=700)}`"
        )

        container = Container(color=Color.blurple())
        if guild.icon:
            container.add_section(
                TextDisplay(header),
                accessory=Thumbnail(guild.icon.url, description=f"{guild.name}'s icon"),
            )
        else:
            container.add_text(header)

        for text in (stats, community, safety):
            container.add_separator(divider=True, spacing=SeparatorSpacingSize.small)
            container.add_text(text)

        container.add_separator(divider=False, spacing=SeparatorSpacingSize.small)

        buttons = []
        if guild.icon:
            buttons.append(UIButton(label="Icon", emoji="🖼️", style=ButtonStyle.link, url=guild.icon.url))
        if guild.banner:
            buttons.append(UIButton(label="Banner", emoji="🎨", style=ButtonStyle.link, url=guild.banner.url))
        if guild.splash:
            buttons.append(UIButton(label="Splash", emoji="🌊", style=ButtonStyle.link, url=guild.splash.url))
        if buttons:
            container.add_row(*buttons[:5])

        return InfoContainerView(container)

    @slash_command(name="about", description="Detailed stats about the bot.")
    async def about(self, ctx: discord.ApplicationContext):
        await ctx.defer()

        now = datetime.now(timezone.utc)
        uptime = now - self.start_time
        command_start = time.perf_counter()

        created_at = self.bot.user.created_at if self.bot.user else None
        created_str = (
            "Not available"
            if not created_at
            else f"{format_dt(created_at, 'F')} ({format_dt(created_at, 'R')})"
        )

        ws_ping = round(self.bot.latency * 1000, 2)

        api_start = time.perf_counter()
        try:
            await self.bot.http.request(discord.http.Route("GET", "/gateway"))
            api_ping = round((time.perf_counter() - api_start) * 1000, 2)
        except Exception:
            api_ping = None

        cmd_latency = round((time.perf_counter() - command_start) * 1000, 2)

        embed = discord.Embed(
            title="🤖 Bot-Infos",
            description=f"# [Support / GitHub]({SUPPORT_SERVER})",
            color=discord.Color.blurple(),
            timestamp=now,
        )

        if self.bot.user:
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        embed.add_field(
            name="🆔 Bot ID",
            value=f"```{self.bot.user.id if self.bot.user else 'N/A'}```",
            inline=True,
        )
        embed.add_field(
            name="📛 Bot Name",
            value=f"```{self.bot.user}```",
            inline=True,
        )
        embed.add_field(
            name="📅 Bot created",
            value=created_str,
            inline=False,
        )
        embed.add_field(
            name="🕰️ Bot Uptime",
            value=(
                f"```{self.format_timedelta(uptime)}```"
                f"Last restart: {format_dt(self.start_time, 'F')} ({format_dt(self.start_time, 'R')})"
            ),
            inline=False,
        )
        embed.add_field(
            name="🏓 WebSocket Ping",
            value=f"```{ws_ping} ms```",
            inline=True,
        )
        embed.add_field(
            name="📡 API Ping",
            value=f"```{api_ping if api_ping is not None else 'Error'} ms```",
            inline=True,
        )
        embed.add_field(
            name="⚡ Command-Reaction Time",
            value=f"```{cmd_latency} ms```",
            inline=True,
        )
        embed.add_field(
            name="🌍 Servers",
            value=f"```{len(getattr(self.bot, 'guilds', []))}```",
            inline=True,
        )
        embed.add_field(
            name="👥 Cached Users",
            value=f"```{len(getattr(self.bot, 'users', []))}```",
            inline=True,
        )
        embed.add_field(
            name="🧩 Cogs",
            value=f"```{len(getattr(self.bot, 'cogs', {}))}```",
            inline=True,
        )
        embed.add_field(
            name="📚 Commands",
            value=f"```{self.visible_command_count(include_owner=is_bot_owner(ctx.author.id))}```",
            inline=True,
        )

        if is_bot_owner(ctx.author.id):
            process = psutil.Process(os.getpid())
            ram = psutil.virtual_memory()

            shard_count = getattr(self.bot, "shard_count", None)
            shard_id = getattr(ctx.guild, "shard_id", None) if ctx.guild else None

            cache_stats = None
            if hasattr(self.bot, "cache_stats"):
                cache_stats = await self.bot.cache_stats()

            embed.add_field(
                name="💻 System CPU",
                value=f"```{psutil.cpu_percent(interval=0.1):.1f}%```",
                inline=True,
            )
            embed.add_field(
                name="⚙️ Process CPU",
                value=f"```{process.cpu_percent(interval=0.1):.1f}%```",
                inline=True,
            )
            embed.add_field(
                name="🧠 System RAM",
                value=f"```{ram.percent:.2f}%```",
                inline=True,
            )
            embed.add_field(
                name="📦 Process RAM",
                value=f"```{process.memory_info().rss / 1024 / 1024:.1f} MiB```",
                inline=True,
            )
            embed.add_field(
                name="🧵 Threads",
                value=f"```{process.num_threads()}```",
                inline=True,
            )
            embed.add_field(
                name="🆔 PID",
                value=f"```{process.pid}```",
                inline=True,
            )
            embed.add_field(
                name="🖥️ Platform",
                value=f"```{platform.system()} {platform.release()}```",
                inline=True,
            )
            embed.add_field(
                name="🏗️ Machine",
                value=f"```{platform.machine() or 'N/A'}```",
                inline=True,
            )
            embed.add_field(
                name="🐍 Python",
                value=f"```{platform.python_version()}```",
                inline=True,
            )
            embed.add_field(
                name="📦 Py-cord",
                value=f"```{discord.__version__}```",
                inline=True,
            )
            embed.add_field(
                name="🧩 Shard",
                value=(
                    f"```ID: {shard_id if shard_id is not None else 'N/A'} / "
                    f"Count: {shard_count if shard_count is not None else 'N/A'}```"
                ),
                inline=False,
            )

            if cache_stats:
                embed.add_field(
                    name="🗃️ Global Cache",
                    value=(
                        "```"
                        f"Entries: {cache_stats['entries']} / {cache_stats['max_entries']}\n"
                        f"TTL entries: {cache_stats['ttl_entries']}\n"
                        f"Persistent: {cache_stats['persistent_entries']}\n"
                        f"Default TTL: {cache_stats['default_ttl']}\n"
                        f"Cleanup: {cache_stats['cleanup_interval']}s"
                        "```"
                    ),
                    inline=False,
                )

        embed.set_footer(
            text=f"Requested by {ctx.author}",
            icon_url=ctx.author.display_avatar.url,
        )

        await ctx.respond(embed=embed, view=AboutView())

    @slash_command(name="userinfo", description="Show compact information about a server member.")
    @commands.guild_only()
    async def userinfo(
            self,
            ctx: discord.ApplicationContext,
            member: Option(discord.Member, "User to inspect", required=False) = None,
    ):
        await ctx.defer()

        target = member or ctx.author
        if not isinstance(target, discord.Member):
            await ctx.respond("Could not resolve that user as a server member.", ephemeral=True)
            return

        view = await self.build_userinfo_view(target)
        await ctx.respond(view=view, allowed_mentions=discord.AllowedMentions.none())

    @slash_command(name="serverinfo", description="Show compact information about this server.")
    @commands.guild_only()
    async def serverinfo(self, ctx: discord.ApplicationContext):
        await ctx.defer()

        view = await self.build_serverinfo_view(ctx.guild)
        await ctx.respond(view=view, allowed_mentions=discord.AllowedMentions.none())

    @slash_command(name="help", description="Show all Slash commands that you can use.")
    async def help_command(self, ctx: discord.ApplicationContext):
        await ctx.defer(ephemeral=True)

        embeds = []
        page_info = {}
        prefix_display = get_prefix_display(self.bot)
        include_owner = is_bot_owner(ctx.author.id)

        categories = []

        main_cmds = []
        for cmd in iter_main_commands(self.bot):
            main_cmds.extend(gather_commands_recursive(cmd, include_owner=include_owner))

        if main_cmds:
            categories.append(("Main", main_cmds))

        for cog_name, cog in self.bot.cogs.items():
            if cog_name in OWNER_COGS and not include_owner:
                continue

            all_cmds = []
            for cmd in getattr(cog, "get_commands", lambda: [])():
                all_cmds.extend(gather_commands_recursive(cmd, include_owner=include_owner))

            if all_cmds:
                categories.append((cog_name, all_cmds))

        for cog_name, all_cmds in categories:
            all_cmds.sort(key=lambda item: item[0].lower())

            chunks = [
                all_cmds[i:i + self.MAX_FIELDS_PER_EMBED]
                for i in range(0, len(all_cmds), self.MAX_FIELDS_PER_EMBED)
            ]

            total_pages = len(chunks)
            cog_emoji = command_emoji(cog_name)

            for page_num, chunk in enumerate(chunks, 1):
                embed_index = len(embeds)

                if total_pages > 1:
                    title = f"📂 {cog_name} Commands (Page {page_num}/{total_pages})"
                    description = (
                        f"{cog_emoji} Commands from `{cog_name}`\n"
                        f"Page `{page_num}` of `{total_pages}`"
                    )
                else:
                    title = f"📂 {cog_name} Commands"
                    description = f"{cog_emoji} All visible commands from `{cog_name}`"

                embed = discord.Embed(
                    title=title,
                    description=description,
                    color=discord.Color.blurple(),
                    timestamp=datetime.now(timezone.utc),
                )

                page_info[embed_index] = {
                    "cog_name": cog_name,
                    "page": page_num,
                    "total_pages": total_pages,
                }

                for name, desc, cmd_id, kind in chunk:
                    label = command_mention(
                        name,
                        cmd_id,
                        kind=kind,
                        prefix=prefix_display,
                    )
                    command_type = {
                        "slash": "Slash",
                        "prefix": "Prefix",
                        "bridge": "Bridge",
                    }.get(kind, "Command")

                    embed.add_field(
                        name=f"{command_emoji(name)} {label}",
                        value=f"> `{command_type}` • {safe_plain(desc, limit=170)}",
                        inline=False,
                    )

                embeds.append(embed)

        if not embeds:
            await ctx.respond("No visible commands found.", ephemeral=True)
            return

        total = len(embeds)
        for idx, embed in enumerate(embeds, 1):
            embed.set_footer(
                text=f"Page {idx}/{total} • Use the menu or buttons below",
                icon_url=ctx.author.display_avatar.url,
            )

        view = HelpView(
            embeds,
            requester_id=ctx.author.id,
            page_info=page_info,
            timeout=HELP_TIMEOUT_SECONDS,
        )
        msg = await ctx.respond(embed=embeds[0], view=view, ephemeral=True)

        with contextlib.suppress(discord.HTTPException, discord.NotFound, AttributeError):
            view.message = await msg.original_response()


def setup(bot):
    bot.add_cog(User(bot))
