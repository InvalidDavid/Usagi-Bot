from utils.imports import *
from utils.helper.loghelper import LogsHelper
from utils.secrets import (
    LOG_GUILD_ID,
    LOG_CHANNEL_ID,
    LOG_ARROW,
    MEMBER_UPDATE_DELAY,
    AUDIT_LOG_DELAY,
    AUDIT_LOG_MAX_AGE,
    BULK_AUDIT_LOG_MAX_AGE,
    RECENT_BAN_TTL,
    RECENT_USER_UPDATE_TTL,
    RECENT_BULK_LOG_TTL,
    MEMBER_REMOVE_AUDIT_WAIT,
)

logger = logging.getLogger("bot.logging")


class Logs(LogsHelper, commands.Cog):
    LOG_GUILD_ID = LOG_GUILD_ID
    LOG_CHANNEL_ID = LOG_CHANNEL_ID

    ARROW = LOG_ARROW

    MEMBER_UPDATE_DELAY = MEMBER_UPDATE_DELAY
    AUDIT_LOG_DELAY = AUDIT_LOG_DELAY
    AUDIT_LOG_MAX_AGE = AUDIT_LOG_MAX_AGE
    BULK_AUDIT_LOG_MAX_AGE = BULK_AUDIT_LOG_MAX_AGE
    RECENT_BAN_TTL = RECENT_BAN_TTL
    RECENT_USER_UPDATE_TTL = RECENT_USER_UPDATE_TTL
    RECENT_BULK_LOG_TTL = RECENT_BULK_LOG_TTL
    MEMBER_REMOVE_AUDIT_WAIT = MEMBER_REMOVE_AUDIT_WAIT

    COLORS: dict[str, discord.Color] = {
        "member_join": discord.Color.green(),
        "member_left": discord.Color.red(),
        "member_ban": discord.Color.dark_red(),
        "member_unban": discord.Color.orange(),
        "member_update": discord.Color.gold(),
        "voice": discord.Color.dark_blue(),
        "channel_create": discord.Color.teal(),
        "channel_delete": discord.Color.dark_red(),
        "channel_update": discord.Color.dark_blue(),
        "thread_create": discord.Color.purple(),
        "thread_delete": discord.Color.dark_purple(),
        "thread_update": discord.Color.dark_orange(),
        "role_create": discord.Color.dark_green(),
        "role_delete": discord.Color.red(),
        "role_update": discord.Color.gold(),
        "message_edit": discord.Color.orange(),
        "message_delete": discord.Color.red(),
        "raw_delete": discord.Color.dark_red(),
        "bulk_delete": discord.Color.dark_grey(),
        "emoji_create": discord.Color.gold(),
        "emoji_delete": discord.Color.red(),
        "emoji_update": discord.Color.orange(),
        "guild_update": discord.Color.blurple(),
        "scheduled_event_create": discord.Color.green(),
        "scheduled_event_update": discord.Color.orange(),
        "scheduled_event_delete": discord.Color.red(),
        "sticker_create": discord.Color.dark_green(),
        "sticker_delete": discord.Color.red(),
        "sticker_update": discord.Color.orange(),
        "webhook_update": discord.Color.dark_gold(),
        "raw_message_delete": discord.Color.dark_red(),
        "raw_message_edit": discord.Color.orange(),
        "raw_member_remove": discord.Color.red(),
        "raw_thread_delete": discord.Color.dark_red(),
        "raw_thread_update": discord.Color.dark_blue(),
        "raw_thread_member_remove": discord.Color.orange(),
    }

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.allowed_mentions = discord.AllowedMentions.none()

        self._recent_bulk_log_keys: set[tuple[int, int, frozenset[int]]] = set()
        self._pending_member_updates: dict[tuple[int, int], dict[str, discord.Member]] = {}
        self._member_update_tasks: dict[tuple[int, int], asyncio.Task] = {}
        self._recent_bans: set[int] = set()
        self._recent_user_update_keys: set[tuple[int, str, str, str, str]] = set()
        self._background_tasks: set[asyncio.Task] = set()

    def cog_unload(self) -> None:
        for task in self._background_tasks:
            task.cancel()

        for task in self._member_update_tasks.values():
            task.cancel()

        self._background_tasks.clear()
        self._member_update_tasks.clear()
        self._pending_member_updates.clear()
        self._recent_bulk_log_keys.clear()
        self._recent_bans.clear()
        self._recent_user_update_keys.clear()

    def _create_task(
        self,
        coro: Coroutine[Any, Any, Any],
        *,
        name: Optional[str] = None,
    ) -> asyncio.Task:
        task = asyncio.create_task(coro, name=name)
        self._background_tasks.add(task)
        task.add_done_callback(self._on_background_task_done)
        return task

    def _on_background_task_done(self, task: asyncio.Task) -> None:
        self._background_tasks.discard(task)

        if task.cancelled():
            return

        exc = task.exception()
        if exc is not None:
            logger.exception("Unhandled task error in Logs cog.", exc_info=exc)

    async def _sleep_and_discard_ban(self, user_id: int, delay: float = RECENT_BAN_TTL) -> None:
        await asyncio.sleep(delay)
        self._recent_bans.discard(user_id)

    async def _sleep_and_discard_user_update_key(
        self,
        key: tuple[int, str, str, str, str],
        delay: float = RECENT_USER_UPDATE_TTL,
    ) -> None:
        await asyncio.sleep(delay)
        self._recent_user_update_keys.discard(key)

    async def _sleep_and_discard_bulk_key(
        self,
        guild_id: int,
        channel_id: int,
        message_ids: Iterable[int],
        delay: float = RECENT_BULK_LOG_TTL,
    ) -> None:
        await asyncio.sleep(delay)
        self._recent_bulk_log_keys.discard(self._bulk_log_key(guild_id, channel_id, message_ids))

    async def _flush_member_update(self, key: tuple[int, int]) -> None:
        try:
            await asyncio.sleep(self.MEMBER_UPDATE_DELAY)
        except asyncio.CancelledError:
            return

        current_task = asyncio.current_task()
        if self._member_update_tasks.get(key) is current_task:
            self._member_update_tasks.pop(key, None)

        payload = self._pending_member_updates.pop(key, None)
        if not payload:
            return

        before: discord.Member = payload["before"]
        after: discord.Member = payload["after"]

        if not self._is_target_guild(after.guild.id):
            return

        changes: list[str] = []
        nick_changed = before.nick != after.nick

        if nick_changed:
            changes.append(f"Nickname {self.ARROW} `{before.nick or 'None'}` → `{after.nick or 'None'}`")

        changes.extend(self._role_change_lines(before, after))

        before_timeout = self._member_timeout_until(before)
        after_timeout = self._member_timeout_until(after)

        if before_timeout != after_timeout:
            changes.append(
                f"Timeout {self.ARROW} {self._fmt_dt(before_timeout, 'R')} → {self._fmt_dt(after_timeout, 'R')}"
            )

        if not changes:
            return

        moderator_text = None
        reason_text = None

        if nick_changed:
            entry = await self._find_recent_member_audit_entry(
                after.guild,
                member_id=after.id,
                action=discord.AuditLogAction.member_update,
            )
            if entry is not None and entry.user is not None:
                actor = entry.user
                moderator_text = f"-# **Moderator:** {actor} • {actor.id}"
                if entry.reason:
                    reason_text = f"-# Reason: {entry.reason}"

        header_text = self._truncate(
            "\n".join(
                [
                    f"Member {self.ARROW} {after} • {after.mention}",
                    f"ID {self.ARROW} `{after.id}`",
                    f"Current Nick {self.ARROW} `{after.nick or 'None'}`",
                ]
            ),
            limit=800,
        )

        changes_text = self._truncate("\n".join(changes), limit=1400)

        items: list[Any] = [
            Section(
                TextDisplay("## Member Updated"),
                TextDisplay(header_text),
                accessory=discord.ui.Thumbnail(self._safe_avatar_url(after)),
            ),
            TextDisplay(changes_text),
        ]

        if moderator_text or reason_text:
            items.append(
                discord.ui.Separator(
                    divider=True,
                    spacing=discord.SeparatorSpacingSize.small,
                )
            )

            footer_lines: list[str] = []
            if moderator_text:
                footer_lines.append(moderator_text)
            if reason_text:
                footer_lines.append(reason_text)

            items.append(TextDisplay(self._truncate("\n".join(footer_lines), limit=300)))

        view = DesignerView(
            Container(
                *self._flatten_items(items),
                color=self._color("member_update"),
            )
        )
        await self._send_view(view=view)

    def _queue_member_update(self, before: discord.Member, after: discord.Member) -> None:
        key = (after.guild.id, after.id)

        existing = self._pending_member_updates.get(key)
        if existing is None:
            self._pending_member_updates[key] = {"before": before, "after": after}
        else:
            existing["after"] = after

        old_task = self._member_update_tasks.get(key)
        if old_task is not None and not old_task.done():
            old_task.cancel()

        task = self._create_task(self._flush_member_update(key), name=f"logs:member_update:{after.id}")
        self._member_update_tasks[key] = task

    def _mark_bulk_log_seen(self, guild_id: int, channel_id: int, message_ids: Iterable[int]) -> bool:
        key = self._bulk_log_key(guild_id, channel_id, message_ids)
        if key in self._recent_bulk_log_keys:
            return True
        self._recent_bulk_log_keys.add(key)
        return False

    async def _send_bulk_delete_log(
        self,
        *,
        guild_id: Optional[int],
        channel_id: int,
        message_ids: Iterable[int],
        cached_messages: Iterable[discord.Message],
    ) -> None:
        if not self._is_target_guild(guild_id):
            return

        normalized_ids = sorted({int(mid) for mid in message_ids})
        cached_list = list(cached_messages)
        total_count = len(normalized_ids)

        if guild_id is not None and self._mark_bulk_log_seen(guild_id, channel_id, normalized_ids):
            return

        if guild_id is not None:
            self._create_task(
                self._sleep_and_discard_bulk_key(guild_id, channel_id, normalized_ids),
                name=f"logs:bulk_delete:{channel_id}",
            )

        channel_obj = await self._resolve_channel_obj(channel_id)
        channel_name = getattr(channel_obj, "name", "Unknown")
        channel_label = self._channel_name(channel_obj) if channel_obj else f"`{channel_id}`"

        moderator = None
        guild = self.bot.get_guild(guild_id) if guild_id else None
        if guild is not None:
            moderator, _reason = await self._find_bulk_delete_actor(
                guild,
                channel_id=channel_id,
                total_count=total_count,
            )

        file_to_send = self._create_bulk_deleted_file(normalized_ids, cached_list)

        items: list[Any] = [
            TextDisplay("## Bulk Messages Deleted"),
            TextDisplay(
                f"**Channel**\n"
                f"Name {self.ARROW} {channel_name} | {channel_label}\n"
                f"ID {self.ARROW} `{channel_id}`"
            ),
            TextDisplay(
                f"**Total Messages**\n"
                f"{self.ARROW} `{total_count}`"
            ),
            discord.ui.Separator(
                divider=True,
                spacing=discord.SeparatorSpacingSize.small,
            ),
            TextDisplay("**Export**"),
            discord.ui.File(f"attachment://{file_to_send.filename}"),
        ]

        if moderator is not None:
            items.append(TextDisplay(f"-# **Moderator:** {moderator} • {moderator.id}"))
        else:
            items.append(TextDisplay("-# **Moderator:** Unknown"))

        view = DesignerView(
            Container(
                *self._flatten_items(items),
                color=self._color("bulk_delete"),
            )
        )
        await self._send_view(view=view, file=file_to_send)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if not self._is_target_guild(member.guild.id):
            return

        member = await self._get_fresh_member(member)

        header_text = self._truncate(
            "\n".join(
                [
                    f"Member {self.ARROW} {member} • {member.mention}",
                    f"ID {self.ARROW} `{member.id}`",
                    f"Bot {self.ARROW} `{member.bot}`",
                ]
            ),
            limit=800,
        )

        details_text = self._truncate(
            "\n".join(
                [
                    f"Account Created {self.ARROW} {self._fmt_dt(member.created_at, 'R')}",
                    f"Joined {self.ARROW} {self._fmt_dt(member.joined_at, 'R')}",
                ]
            ),
            limit=800,
        )

        view = DesignerView(
            Container(
                Section(
                    TextDisplay("## Member Joined"),
                    TextDisplay(header_text),
                    accessory=discord.ui.Thumbnail(self._safe_avatar_url(member)),
                ),
                TextDisplay(details_text),
                color=self._color("member_join"),
            )
        )
        await self._send_view(view=view)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if not self._is_target_guild(member.guild.id):
            return

        if member.id in self._recent_bans:
            return

        await asyncio.sleep(self.MEMBER_REMOVE_AUDIT_WAIT)

        if member.id in self._recent_bans:
            return

        ban_entry = await self._find_recent_member_audit_entry(
            member.guild,
            member_id=member.id,
            action=discord.AuditLogAction.ban,
            delay=0,
        )
        if ban_entry is not None:
            return

        kick_entry = await self._find_recent_member_audit_entry(
            member.guild,
            member_id=member.id,
            action=discord.AuditLogAction.kick,
            delay=0,
        )

        kicked = kick_entry is not None
        title = "## Member Kicked" if kicked else "## Member Left"

        actor_text = None
        reason_text = None

        if kicked and kick_entry.user is not None:
            actor = kick_entry.user
            actor_text = f"-# **Moderator:** {actor} • {actor.id}"
            if kick_entry.reason:
                reason_text = f"-# Reason: {kick_entry.reason}"

        header_text = self._truncate(
            "\n".join(
                [
                    f"Member {self.ARROW} {member} • {member.mention}",
                    f"ID {self.ARROW} `{member.id}`",
                ]
            ),
            limit=800,
        )

        details_text = self._truncate(
            "\n".join(
                [
                    f"Account Created {self.ARROW} {self._fmt_dt(member.created_at, 'R')}",
                    f"Joined {self.ARROW} {self._fmt_dt(member.joined_at, 'R')}",
                ]
            ),
            limit=800,
        )

        items: list[Any] = [
            Section(
                TextDisplay(title),
                TextDisplay(header_text),
                accessory=discord.ui.Thumbnail(self._safe_avatar_url(member)),
            ),
            TextDisplay(details_text),
        ]

        if actor_text or reason_text:
            items.append(
                discord.ui.Separator(
                    divider=True,
                    spacing=discord.SeparatorSpacingSize.small,
                )
            )

            footer_lines: list[str] = []
            if actor_text:
                footer_lines.append(actor_text)
            if reason_text:
                footer_lines.append(reason_text)

            items.append(TextDisplay(self._truncate("\n".join(footer_lines), limit=300)))

        view = DesignerView(
            Container(
                *self._flatten_items(items),
                color=self._color("member_left"),
            )
        )
        await self._send_view(view=view)

    @commands.Cog.listener()
    async def on_member_ban(
        self,
        guild: discord.Guild,
        user: Union[discord.User, discord.Member],
    ) -> None:
        if not self._is_target_guild(guild.id):
            return

        self._recent_bans.add(user.id)
        self._create_task(
            self._sleep_and_discard_ban(user.id),
            name=f"logs:recent_ban:{user.id}",
        )

        joined_at = getattr(user, "joined_at", None)

        actor_text = "-# **Moderator:** Unknown"
        reason_text = None

        entry = await self._find_recent_member_audit_entry(
            guild,
            member_id=user.id,
            action=discord.AuditLogAction.ban,
        )
        if entry is not None and entry.user is not None:
            actor = entry.user
            actor_text = f"-# **Moderator:** {actor} • {actor.id}"
            if entry.reason:
                reason_text = f"-# Reason: {entry.reason}"

        header_text = self._truncate(
            "\n".join(
                [
                    f"User {self.ARROW} {user} • {getattr(user, 'mention', str(user))}",
                    f"ID {self.ARROW} `{user.id}`",
                ]
            ),
            limit=800,
        )

        details_text = self._truncate(
            "\n".join(
                [
                    f"Account Created {self.ARROW} {self._fmt_dt(getattr(user, 'created_at', None), 'R')}",
                    f"Joined {self.ARROW} {self._fmt_dt(joined_at, 'R')}",
                ]
            ),
            limit=800,
        )

        footer_lines = [actor_text]
        if reason_text:
            footer_lines.append(reason_text)

        view = DesignerView(
            Container(
                Section(
                    TextDisplay("## Member Banned"),
                    TextDisplay(header_text),
                    accessory=discord.ui.Thumbnail(self._safe_avatar_url(user)),
                ),
                TextDisplay(details_text),
                discord.ui.Separator(
                    divider=True,
                    spacing=discord.SeparatorSpacingSize.small,
                ),
                TextDisplay(self._truncate("\n".join(footer_lines), limit=300)),
                color=self._color("member_ban"),
            )
        )
        await self._send_view(view=view)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        if not self._is_target_guild(guild.id):
            return

        actor_text = "-# **Moderator:** Unknown"
        reason_text = None

        entry = await self._find_recent_member_audit_entry(
            guild,
            member_id=user.id,
            action=discord.AuditLogAction.unban,
        )
        if entry is not None and entry.user is not None:
            actor = entry.user
            actor_text = f"-# **Moderator:** {actor} • {actor.id}"
            if entry.reason:
                reason_text = f"-# Reason: {entry.reason}"

        header_text = self._truncate(
            "\n".join(
                [
                    f"User {self.ARROW} `{user}`",
                    f"ID {self.ARROW} `{user.id}`",
                ]
            ),
            limit=800,
        )

        details_text = self._truncate(
            f"Account Created {self.ARROW} {self._fmt_dt(user.created_at, 'R')}",
            limit=800,
        )

        footer_lines = [actor_text]
        if reason_text:
            footer_lines.append(reason_text)

        view = DesignerView(
            Container(
                Section(
                    TextDisplay("## Member Unbanned"),
                    TextDisplay(header_text),
                    accessory=discord.ui.Thumbnail(self._safe_avatar_url(user)),
                ),
                TextDisplay(details_text),
                discord.ui.Separator(
                    divider=True,
                    spacing=discord.SeparatorSpacingSize.small,
                ),
                TextDisplay(self._truncate("\n".join(footer_lines), limit=300)),
                color=self._color("member_unban"),
            )
        )
        await self._send_view(view=view)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if not self._is_target_guild(after.guild.id):
            return

        relevant_change = False

        if before.nick != after.nick:
            relevant_change = True

        if set(self._role_map(before)) != set(self._role_map(after)):
            relevant_change = True

        if self._member_timeout_until(before) != self._member_timeout_until(after):
            relevant_change = True

        if not relevant_change:
            return

        self._queue_member_update(before, after)

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User) -> None:
        guild = self.bot.get_guild(self.LOG_GUILD_ID)
        if guild is None:
            return

        member = guild.get_member(after.id)
        if member is None:
            return

        before_avatar = str(before.avatar) if before.avatar else "None"
        after_avatar = str(after.avatar) if after.avatar else "None"

        before_global_name = getattr(before, "global_name", None) or "None"
        after_global_name = getattr(after, "global_name", None) or "None"

        changes: list[str] = []

        if before.name != after.name:
            changes.append(f"Username {self.ARROW} `{before.name}` → `{after.name}`")

        if before_global_name != after_global_name:
            changes.append(f"Global Name {self.ARROW} `{before_global_name}` → `{after_global_name}`")

        if before_avatar != after_avatar:
            changes.append(f"Avatar Changed {self.ARROW} Yes")

        if not changes:
            return

        dedupe_key = (
            after.id,
            before.name,
            after.name,
            before_global_name + "->" + after_global_name,
            before_avatar + "->" + after_avatar,
        )

        if dedupe_key in self._recent_user_update_keys:
            return

        self._recent_user_update_keys.add(dedupe_key)
        self._create_task(
            self._sleep_and_discard_user_update_key(dedupe_key),
            name=f"logs:user_update:{after.id}",
        )

        header_text = self._truncate(
            "\n".join(
                [
                    f"User {self.ARROW} {member} • {member.id}",
                    f"ID {self.ARROW} `{after.id}`",
                ]
            ),
            limit=800,
        )

        changes_text = self._truncate("\n".join(changes), limit=1400)

        view = DesignerView(
            Container(
                Section(
                    TextDisplay("## User Profile Updated"),
                    TextDisplay(header_text),
                    accessory=discord.ui.Thumbnail(self._safe_avatar_url(after)),
                ),
                TextDisplay(changes_text),
                color=self._color("member_update"),
            )
        )
        await self._send_view(view=view)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if not self._is_target_guild(member.guild.id):
            return

        before_channel = before.channel
        after_channel = after.channel

        if before_channel == after_channel:
            return

        if before_channel is None and after_channel is not None:
            change = f"Joined {self.ARROW} {after_channel.mention}"
        elif before_channel is not None and after_channel is None:
            change = f"Left {self.ARROW} {before_channel.mention}"
        elif before_channel is not None and after_channel is not None:
            change = f"Moved {self.ARROW} {before_channel.mention} → {after_channel.mention}"
        else:
            return

        header_text = self._truncate(
            "\n".join(
                [
                    f"Member {self.ARROW} {member} • {member.mention}",
                    f"ID {self.ARROW} `{member.id}`",
                ]
            ),
            limit=800,
        )

        view = DesignerView(
            Container(
                Section(
                    TextDisplay("## Voice Status Changed"),
                    TextDisplay(header_text),
                    accessory=discord.ui.Thumbnail(self._safe_avatar_url(member)),
                ),
                TextDisplay(change),
                color=self._color("voice"),
            )
        )
        await self._send_view(view=view)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        if not self._is_target_guild(channel.guild.id):
            return

        actor_text = "-# **Moderator:** Unknown"
        reason_text = None

        entry = await self._find_recent_channel_audit_entry(
            channel.guild,
            channel_id=channel.id,
            action=discord.AuditLogAction.channel_create,
        )
        if entry is not None and entry.user is not None:
            actor = entry.user
            actor_text = f"-# **Moderator:** {actor} • {actor.id}"
            if entry.reason:
                reason_text = f"-# Reason: {entry.reason}"

        details = self._truncate(
            "\n".join(
                [
                    f"Channel {self.ARROW} {channel.name} | {self._channel_name(channel)}",
                    f"ID {self.ARROW} `{channel.id}`",
                    f"Type {self.ARROW} `{type(channel).__name__}`",
                ]
            ),
            limit=1500,
        )

        footer_lines = [actor_text]
        if reason_text:
            footer_lines.append(reason_text)

        items: list[Any] = [
            TextDisplay("## Channel Created"),
            TextDisplay(details),
            discord.ui.Separator(
                divider=True,
                spacing=discord.SeparatorSpacingSize.small,
            ),
        ]

        jump_row = self._link_row(self._safe_jump_url(channel), label="Open Channel")
        if jump_row:
            items.append(jump_row)

        items.append(TextDisplay(self._truncate("\n".join(footer_lines), limit=300)))

        view = DesignerView(
            Container(
                *self._flatten_items(items),
                color=self._color("channel_create"),
            )
        )
        await self._send_view(view=view)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        if not self._is_target_guild(channel.guild.id):
            return

        actor_text = "-# **Moderator:** Unknown"
        reason_text = None

        entry = await self._find_recent_channel_audit_entry(
            channel.guild,
            channel_id=channel.id,
            action=discord.AuditLogAction.channel_delete,
        )
        if entry is not None and entry.user is not None:
            actor = entry.user
            actor_text = f"-# **Moderator:** {actor} • {actor.id}"
            if entry.reason:
                reason_text = f"-# Reason: {entry.reason}"

        details = self._truncate(
            "\n".join(
                [
                    f"Name {self.ARROW} `{channel.name}`",
                    f"ID {self.ARROW} `{channel.id}`",
                    f"Type {self.ARROW} `{type(channel).__name__}`",
                ]
            ),
            limit=1500,
        )

        footer_lines = [actor_text]
        if reason_text:
            footer_lines.append(reason_text)

        view = DesignerView(
            Container(
                TextDisplay("## Channel Deleted"),
                TextDisplay(details),
                discord.ui.Separator(
                    divider=True,
                    spacing=discord.SeparatorSpacingSize.small,
                ),
                TextDisplay(self._truncate("\n".join(footer_lines), limit=300)),
                color=self._color("channel_delete"),
            )
        )
        await self._send_view(view=view)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel) -> None:
        if not self._is_target_guild(after.guild.id):
            return

        changes: list[str] = []

        if before.name != after.name:
            changes.append(f"Name {self.ARROW} `{before.name}` → `{after.name}`")

        before_topic = getattr(before, "topic", None)
        after_topic = getattr(after, "topic", None)
        if before_topic != after_topic:
            changes.append(f"Topic {self.ARROW} `{before_topic or 'None'}` → `{after_topic or 'None'}`")

        if getattr(before, "position", None) != getattr(after, "position", None):
            changes.append(
                f"Position {self.ARROW} `{getattr(before, 'position', None)}` → `{getattr(after, 'position', None)}`"
            )

        if getattr(before, "category_id", None) != getattr(after, "category_id", None):
            changes.append(
                f"Category ID {self.ARROW} `{getattr(before, 'category_id', None)}` → `{getattr(after, 'category_id', None)}`"
            )

        before_overwrites = {
            getattr(target, "id", None): (target, overwrite)
            for target, overwrite in before.overwrites.items()
            if getattr(target, "id", None) is not None
        }
        after_overwrites = {
            getattr(target, "id", None): (target, overwrite)
            for target, overwrite in after.overwrites.items()
            if getattr(target, "id", None) is not None
        }

        added_ids = after_overwrites.keys() - before_overwrites.keys()
        removed_ids = before_overwrites.keys() - after_overwrites.keys()
        updated_ids = {
            target_id
            for target_id in (before_overwrites.keys() & after_overwrites.keys())
            if before_overwrites[target_id][1] != after_overwrites[target_id][1]
        }

        for target_id in sorted(added_ids):
            target, overwrite = after_overwrites[target_id]
            allow_txt, deny_txt = self._overwrite_to_lines(overwrite)

            changes.append(f"Overwrite Added {self.ARROW} {self._overwrite_target_label(target)}")

            if allow_txt != "None":
                changes.append(f"Allow {self.ARROW} {allow_txt}")
            if deny_txt != "None":
                changes.append(f"Deny {self.ARROW} {deny_txt}")

        for target_id in sorted(updated_ids):
            before_target, before_ow = before_overwrites[target_id]
            after_target, after_ow = after_overwrites[target_id]

            before_allow, before_deny = before_ow.pair()
            after_allow, after_deny = after_ow.pair()

            changes.append(
                f"Overwrite Updated {self.ARROW} {self._overwrite_target_label(after_target or before_target)}"
            )

            changes.extend(self._permission_delta_lines("Allow", before_allow, after_allow))
            changes.extend(self._permission_delta_lines("Deny", before_deny, after_deny))

        for target_id in sorted(removed_ids):
            target, overwrite = before_overwrites[target_id]
            allow_txt, deny_txt = self._overwrite_to_lines(overwrite)

            changes.append(f"Overwrite Removed {self.ARROW} {self._overwrite_target_label(target)}")

            if allow_txt != "None":
                changes.append(f"Allow {self.ARROW} {allow_txt}")
            if deny_txt != "None":
                changes.append(f"Deny {self.ARROW} {deny_txt}")

        if not changes:
            return

        actor_text = "-# **Moderator:** Unknown"
        reason_text = None

        entry = await self._find_recent_channel_or_overwrite_audit_entry(
            after.guild,
            channel_id=after.id,
        )
        if entry is not None:
            actor = getattr(entry, "user", None)
            if actor is not None:
                actor_text = f"-# **Moderator:** {actor} • {actor.id}"
            if entry.reason:
                reason_text = f"-# Reason: {entry.reason}"

        header_text = self._truncate(
            "\n".join(
                [
                    f"Channel {self.ARROW} {after.name} | {self._channel_name(after)}",
                    f"ID {self.ARROW} `{self._channel_id(after)}`",
                    f"Type {self.ARROW} `{type(after).__name__}`",
                ]
            ),
            limit=800,
        )

        changes_text = self._truncate("\n".join(changes), limit=1300)

        footer_lines = [actor_text]
        if reason_text:
            footer_lines.append(reason_text)

        items: list[Any] = [
            TextDisplay("## Channel Updated"),
            TextDisplay(header_text),
            TextDisplay(changes_text),
            discord.ui.Separator(
                divider=True,
                spacing=discord.SeparatorSpacingSize.small,
            ),
        ]

        jump_row = self._link_row(self._safe_jump_url(after), label="Open Channel")
        if jump_row:
            items.append(jump_row)

        items.append(TextDisplay(self._truncate("\n".join(footer_lines), limit=300)))

        view = DesignerView(
            Container(
                *self._flatten_items(items),
                color=self._color("channel_update"),
            )
        )
        await self._send_view(view=view)

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread) -> None:
        if not self._is_target_guild(thread.guild.id):
            return

        items: list[Any] = [
            TextDisplay("## Thread Created"),
            TextDisplay(
                f"Thread {self.ARROW} {thread.name} | {thread.mention}\n"
                f"ID {self.ARROW} `{thread.id}`\n"
                f"Owner {self.ARROW} {self._thread_owner_text(thread)}\n"
            ),
            discord.ui.Separator(
                divider=True,
                spacing=discord.SeparatorSpacingSize.small,
            ),
        ]

        jump_row = self._link_row(self._safe_jump_url(thread), label="Open Thread")
        if jump_row:
            items.append(jump_row)

        view = DesignerView(
            Container(
                *self._flatten_items(items),
                color=self._color("thread_create"),
            )
        )
        await self._send_view(view=view)

    @commands.Cog.listener()
    async def on_thread_delete(self, thread: discord.Thread) -> None:
        if not self._is_target_guild(thread.guild.id):
            return

        actor_text = "-# **Moderator:** Unknown"
        reason_text = None

        entry = await self._find_recent_thread_audit_entry(
            thread.guild,
            thread_id=thread.id,
            action=discord.AuditLogAction.thread_delete,
        )
        if entry is not None and entry.user is not None:
            actor = entry.user
            actor_text = f"-# **Moderator:** {actor} • {actor.id}"
            if entry.reason:
                reason_text = f"-# Reason: {entry.reason}"

        body_lines = [
            f"Name {self.ARROW} `{thread.name}`",
            f"ID {self.ARROW} `{thread.id}`",
        ]

        footer_lines = [actor_text]
        if reason_text:
            footer_lines.append(reason_text)

        view = DesignerView(
            Container(
                TextDisplay("## Thread Deleted"),
                TextDisplay(self._truncate("\n".join(body_lines), limit=1500)),
                discord.ui.Separator(
                    divider=True,
                    spacing=discord.SeparatorSpacingSize.small,
                ),
                TextDisplay(self._truncate("\n".join(footer_lines), limit=300)),
                color=self._color("thread_delete"),
            )
        )
        await self._send_view(view=view)

    @commands.Cog.listener()
    async def on_thread_update(self, before: discord.Thread, after: discord.Thread) -> None:
        if not self._is_target_guild(after.guild.id):
            return

        changes: list[str] = []

        if before.name != after.name:
            changes.append(f"Name {self.ARROW} `{before.name}` → `{after.name}`")

        if before.slowmode_delay != after.slowmode_delay:
            changes.append(f"Slow-mode {self.ARROW} `{before.slowmode_delay}s` → `{after.slowmode_delay}s`")

        if not changes:
            return

        items: list[Any] = [
            TextDisplay("## Thread Updated"),
            TextDisplay(
                f"Thread {self.ARROW} {after.name} | {after.mention}\n"
                f"ID {self.ARROW} `{after.id}`\n"
            ),
            TextDisplay(self._truncate("\n".join(changes), limit=1800)),
            discord.ui.Separator(
                divider=True,
                spacing=discord.SeparatorSpacingSize.small,
            ),
        ]

        jump_row = self._link_row(self._safe_jump_url(after), label="Open Thread")
        if jump_row:
            items.append(jump_row)

        view = DesignerView(
            Container(
                *self._flatten_items(items),
                color=self._color("thread_update"),
            )
        )
        await self._send_view(view=view)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        if not self._is_target_guild(role.guild.id):
            return

        actor_text = "-# **Moderator:**  Unknown"
        reason_text = None

        entry = await self._find_recent_role_audit_entry(
            role.guild,
            role_id=role.id,
            action=discord.AuditLogAction.role_delete,
        )
        if entry is not None and entry.user is not None:
            actor = entry.user
            actor_text = f"-# **Moderator:** {actor} • {actor.id}"
            if entry.reason:
                reason_text = f"-# Reason: {entry.reason}"

        details = self._truncate(
            "\n".join(
                [
                    f"Name {self.ARROW} {role.name}",
                    f"ID {self.ARROW} `{role.id}`",
                    f"Color {self.ARROW} `{role.color}`",
                ]
            ),
            limit=1500,
        )

        footer_lines = [actor_text]
        if reason_text:
            footer_lines.append(reason_text)

        view = DesignerView(
            Container(
                TextDisplay("## Role Deleted"),
                TextDisplay(details),
                discord.ui.Separator(
                    divider=True,
                    spacing=discord.SeparatorSpacingSize.small,
                ),
                TextDisplay(self._truncate("\n".join(footer_lines), limit=300)),
                color=self._color("role_delete"),
            )
        )
        await self._send_view(view=view)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        if not self._is_target_guild(role.guild.id):
            return

        actor_text = "-# **Moderator:** Unknown"
        reason_text = None

        entry = await self._find_recent_role_audit_entry(
            role.guild,
            role_id=role.id,
            action=discord.AuditLogAction.role_create,
        )
        if entry is not None and entry.user is not None:
            actor = entry.user
            actor_text = f"-# **Moderator:** {actor} • {actor.id}"
            if entry.reason:
                reason_text = f"-# Reason: {entry.reason}"

        details = self._truncate(
            "\n".join(
                [
                    f"Role {self.ARROW} {role.name} | {role.mention}",
                    f"ID {self.ARROW} `{role.id}`",
                    f"Color {self.ARROW} `{role.color}`",
                ]
            ),
            limit=1500,
        )

        footer_lines = [actor_text]
        if reason_text:
            footer_lines.append(reason_text)

        view = DesignerView(
            Container(
                TextDisplay("## Role Created"),
                TextDisplay(details),
                discord.ui.Separator(
                    divider=True,
                    spacing=discord.SeparatorSpacingSize.small,
                ),
                TextDisplay(self._truncate("\n".join(footer_lines), limit=300)),
                color=self._color("role_create"),
            )
        )
        await self._send_view(view=view)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role) -> None:
        if not self._is_target_guild(after.guild.id):
            return

        changes: list[str] = []

        if before.name != after.name:
            changes.append(f"Name {self.ARROW} `{before.name}` → `{after.name}`")

        if before.color != after.color:
            changes.append(f"Color {self.ARROW} `{before.color}` → `{after.color}`")

        if before.hoist != after.hoist:
            changes.append(f"Hoist {self.ARROW} `{before.hoist}` → `{after.hoist}`")

        if before.mentionable != after.mentionable:
            changes.append(f"Mentionable {self.ARROW} `{before.mentionable}` → `{after.mentionable}`")

        if before.position != after.position:
            changes.append(f"Position {self.ARROW} `{before.position}` → `{after.position}`")

        if before.permissions != after.permissions:
            changes.extend(self._permission_delta_lines("Permissions", before.permissions, after.permissions))

        if not changes:
            return

        actor_text = "-# **Moderator:** Unknown"
        reason_text = None

        entry = await self._find_recent_role_audit_entry(
            after.guild,
            role_id=after.id,
            action=discord.AuditLogAction.role_update,
        )

        if entry is not None and entry.user is not None:
            actor = entry.user
            actor_text = f"-# **Moderator:** {actor} • {actor.id}"
            if entry.reason:
                reason_text = f"-# Reason: {entry.reason}"

        header_text = self._truncate(
            "\n".join(
                [
                    f"Role {self.ARROW} {after.name} | {after.mention}",
                    f"ID {self.ARROW} `{after.id}`",
                ]
            ),
            limit=800,
        )

        changes_text = self._truncate("\n".join(changes), limit=1400)

        footer_lines = [actor_text]
        if reason_text:
            footer_lines.append(reason_text)

        footer_text = self._truncate("\n".join(footer_lines), limit=300)

        view = DesignerView(
            Container(
                TextDisplay("## Role Updated"),
                TextDisplay(header_text),
                TextDisplay(changes_text),
                discord.ui.Separator(
                    divider=True,
                    spacing=discord.SeparatorSpacingSize.small,
                ),
                TextDisplay(footer_text),
                color=self._color("role_update"),
            )
        )
        await self._send_view(view=view)

    @commands.Cog.listener()
    async def on_message_edit(self, msg_before: discord.Message, msg_after: discord.Message) -> None:
        if msg_before.guild is None or not self._is_target_guild(msg_before.guild.id):
            return

        if msg_before.author.bot or msg_after.author.bot:
            return

        if msg_before.author == self.bot.user or msg_after.author == self.bot.user:
            return

        before_attachments = [attachment.url for attachment in msg_before.attachments]
        after_attachments = [attachment.url for attachment in msg_after.attachments]

        if msg_before.content == msg_after.content and before_attachments == after_attachments:
            return

        items: list[Any] = [
            Section(
                TextDisplay("## Message Edited"),
                TextDisplay(
                    f"**Author**\n"
                    f"Name {self.ARROW} {msg_before.author} | {msg_before.author.mention}\n"
                    f"ID {self.ARROW} `{msg_before.author.id}`\n\n"
                    f"Channel {self.ARROW} {msg_before.channel.name} | {self._channel_name(msg_before.channel)}\n"
                    f"Message ID {self.ARROW} `{msg_before.id}`"
                ),
                accessory=discord.ui.Thumbnail(self._safe_avatar_url(msg_before.author)),
            ),
        ]

        if msg_before.content and msg_before.content.strip():
            items.append(TextDisplay("**Before**"))
            items.append(TextDisplay(self._truncate(msg_before.content)))
        elif msg_before.content != msg_after.content:
            items.append(TextDisplay(self._block_text("Before", "No text content")))

        if msg_after.content and msg_after.content.strip():
            items.append(TextDisplay("**After**"))
            items.append(TextDisplay(self._truncate(msg_after.content)))
        elif msg_before.content != msg_after.content:
            items.append(TextDisplay(self._block_text("After", "No text content")))

        if msg_before.content != msg_after.content:
            items.append(
                discord.ui.Separator(
                    divider=True,
                    spacing=discord.SeparatorSpacingSize.small,
                )
            )

        if before_attachments != after_attachments and msg_before.attachments:
            items.append(TextDisplay(self._block_text("Attachments Before", f"`{len(msg_before.attachments)}` file(s)")))
            gallery = self._attachment_gallery(msg_before.attachments)
            if gallery:
                items.append(gallery)

        if before_attachments != after_attachments and msg_after.attachments:
            items.append(TextDisplay(self._block_text("Attachments After", f"`{len(msg_after.attachments)}` file(s)")))
            gallery = self._attachment_gallery(msg_after.attachments)
            if gallery:
                items.append(gallery)

        if before_attachments != after_attachments:
            items.append(
                discord.ui.Separator(
                    divider=True,
                    spacing=discord.SeparatorSpacingSize.small,
                )
            )

        jump_row = self._link_row(msg_before.jump_url)
        if jump_row:
            items.append(jump_row)

        items.append(
            TextDisplay(
                f"-# Message ID: {msg_before.id} • Flags: {self._message_flags(msg_before)}\n"
                f"-# Created: {self._fmt_dt(msg_before.created_at, 'D')} • Edited: {self._fmt_dt(msg_after.edited_at, 'D') if msg_after.edited_at else 'Unknown'}"
            )
        )

        view = DesignerView(
            Container(
                *self._flatten_items(items),
                color=self._color("message_edit"),
            )
        )
        await self._send_view(view=view)

    @commands.Cog.listener()
    async def on_message_delete(self, msg: discord.Message) -> None:
        if msg.guild is None or not self._is_target_guild(msg.guild.id):
            return

        if msg.author.bot:
            return

        deleted_at = discord.utils.utcnow()

        items: list[Any] = [
            Section(
                TextDisplay("## Message Deleted"),
                TextDisplay(
                    f"**Author**\n"
                    f"Name {self.ARROW} {msg.author} | {msg.author.mention}\n"
                    f"ID {self.ARROW} `{msg.author.id}`\n\n"
                    f"Channel {self.ARROW} {msg.channel.name} | {self._channel_name(msg.channel)}\n"
                ),
                accessory=discord.ui.Thumbnail(self._safe_avatar_url(msg.author)),
            ),
        ]

        if msg.content and msg.content.strip():
            items.append(TextDisplay("**Content**"))
            items.append(TextDisplay(self._truncate(msg.content)))
            items.append(
                discord.ui.Separator(
                    divider=True,
                    spacing=discord.SeparatorSpacingSize.small,
                )
            )

        if msg.stickers:
            items.append(
                TextDisplay(
                    self._block_text(
                        "Stickers",
                        f"`{len(msg.stickers)}` sticker(s)",
                        *[f"`{sticker.name}`" for sticker in msg.stickers],
                    )
                )
            )
            items.append(
                discord.ui.Separator(
                    divider=True,
                    spacing=discord.SeparatorSpacingSize.small,
                )
            )

        attachment_gallery = self._attachment_gallery(msg.attachments)
        if attachment_gallery:
            items.append(TextDisplay(self._block_text("Attachments", f"`{len(msg.attachments)}` file(s)")))
            items.append(attachment_gallery)
            items.append(
                discord.ui.Separator(
                    divider=True,
                    spacing=discord.SeparatorSpacingSize.small,
                )
            )

        items.append(
            TextDisplay(
                f"-# Message ID: {msg.id} • Flags: {self._message_flags(msg)}\n"
                f"-# Deleted: {self._fmt_dt(deleted_at, 'f')}"
            )
        )

        view = DesignerView(
            Container(
                *self._flatten_items(items),
                color=self._color("message_delete"),
            )
        )
        await self._send_view(view=view)

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent) -> None:
        if not self._is_target_guild(payload.guild_id):
            return

        await self._send_bulk_delete_log(
            guild_id=payload.guild_id,
            channel_id=payload.channel_id,
            message_ids=payload.message_ids,
            cached_messages=list(payload.cached_messages),
        )

    @commands.Cog.listener()
    async def on_guild_emojis_update(
        self,
        guild: discord.Guild,
        before: Sequence[discord.GuildEmoji],
        after: Sequence[discord.GuildEmoji],
    ) -> None:
        if not self._is_target_guild(guild.id):
            return

        before_map = self._emoji_map(before)
        after_map = self._emoji_map(after)

        created_ids = sorted(after_map.keys() - before_map.keys())
        deleted_ids = sorted(before_map.keys() - after_map.keys())

        updated_ids = []
        for emoji_id in sorted(before_map.keys() & after_map.keys()):
            before_emoji = before_map[emoji_id]
            after_emoji = after_map[emoji_id]

            if (
                getattr(before_emoji, "name", None) != getattr(after_emoji, "name", None)
                or getattr(before_emoji, "animated", None) != getattr(after_emoji, "animated", None)
                or getattr(before_emoji, "available", None) != getattr(after_emoji, "available", None)
            ):
                updated_ids.append(emoji_id)

        if not created_ids and not deleted_ids and not updated_ids:
            return

        items: list[Any] = []
        color_key = "emoji_update"
        title = "## Emoji Updated"

        if created_ids and not deleted_ids and not updated_ids:
            color_key = "emoji_create"
            title = "## Emoji Created"
        elif deleted_ids and not created_ids and not updated_ids:
            color_key = "emoji_delete"
            title = "## Emoji Deleted"

        items.append(TextDisplay(title))

        for emoji_id in created_ids:
            emoji = after_map[emoji_id]
            items.append(TextDisplay(f"Created {self.ARROW} {self._emoji_label(emoji)}"))

        for emoji_id in deleted_ids:
            emoji = before_map[emoji_id]
            items.append(TextDisplay(f"Deleted {self.ARROW} {self._emoji_label(emoji)}"))

        for emoji_id in updated_ids:
            before_emoji = before_map[emoji_id]
            after_emoji = after_map[emoji_id]

            lines = [f"Emoji {self.ARROW} `{emoji_id}`"]

            if getattr(before_emoji, "name", None) != getattr(after_emoji, "name", None):
                lines.append(
                    f"Name {self.ARROW} `{getattr(before_emoji, 'name', 'Unknown')}` → `{getattr(after_emoji, 'name', 'Unknown')}`"
                )

            if getattr(before_emoji, "animated", None) != getattr(after_emoji, "animated", None):
                lines.append(
                    f"Animated {self.ARROW} `{getattr(before_emoji, 'animated', False)}` → `{getattr(after_emoji, 'animated', False)}`"
                )

            if getattr(before_emoji, "available", None) != getattr(after_emoji, "available", None):
                lines.append(
                    f"Available {self.ARROW} `{getattr(before_emoji, 'available', False)}` → `{getattr(after_emoji, 'available', False)}`"
                )

            items.append(TextDisplay(self._truncate("\n".join(lines), limit=1200)))

        entry = None
        if created_ids:
            entry = await self._find_recent_audit_entry_for_target(
                guild,
                target_id=created_ids[0],
                actions=discord.AuditLogAction.emoji_create,
            )
        elif deleted_ids:
            entry = await self._find_recent_audit_entry_for_target(
                guild,
                target_id=deleted_ids[0],
                actions=discord.AuditLogAction.emoji_delete,
            )
        elif updated_ids:
            entry = await self._find_recent_audit_entry_for_target(
                guild,
                target_id=updated_ids[0],
                actions=discord.AuditLogAction.emoji_update,
            )

        actor_text = "-# **Moderator:** Unknown"
        reason_text = None

        if entry is not None and entry.user is not None:
            actor = entry.user
            actor_text = f"-# **Moderator:** {actor} • {actor.id}"
            if entry.reason:
                reason_text = f"-# Reason: {entry.reason}"

        items.append(
            discord.ui.Separator(
                divider=True,
                spacing=discord.SeparatorSpacingSize.small,
            )
        )

        footer_lines = [actor_text]
        if reason_text:
            footer_lines.append(reason_text)

        items.append(TextDisplay(self._truncate("\n".join(footer_lines), limit=300)))

        view = DesignerView(
            Container(
                *self._flatten_items(items),
                color=self._color(color_key),
            )
        )
        await self._send_view(view=view)

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        if not self._is_target_guild(after.id):
            return

        def text_or_none(raw: Any) -> str:
            if raw is None:
                return "None"
            text = str(raw).strip()
            return text if text else "None"

        def channel_text(channel: Any) -> str:
            return self._guild_channel_ref(channel)

        changes: list[str] = []

        before_name = text_or_none(before.name)
        after_name = text_or_none(after.name)
        if before_name != after_name:
            changes.append(f"Name Changed {self.ARROW} `{before_name}` → `{after_name}`")

        before_description = text_or_none(getattr(before, "description", None))
        after_description = text_or_none(getattr(after, "description", None))
        if before_description == "None" and after_description != "None":
            changes.append(f"Description Added {self.ARROW} `{after_description}`")
        elif before_description != "None" and after_description == "None":
            changes.append(f"Description Removed {self.ARROW} `{before_description}`")
        elif before_description != after_description:
            changes.append(f"Description Changed {self.ARROW} `{before_description}` → `{after_description}`")

        if str(before.verification_level) != str(after.verification_level):
            changes.append(
                f"Verification Level Changed {self.ARROW} `{before.verification_level}` → `{after.verification_level}`"
            )

        if str(before.default_notifications) != str(after.default_notifications):
            changes.append(
                f"Default Notifications Changed {self.ARROW} `{before.default_notifications}` → `{after.default_notifications}`"
            )

        if str(before.explicit_content_filter) != str(after.explicit_content_filter):
            changes.append(
                f"Explicit Content Filter Changed {self.ARROW} `{before.explicit_content_filter}` → `{after.explicit_content_filter}`"
            )

        before_afk_timeout = text_or_none(getattr(before, "afk_timeout", None))
        after_afk_timeout = text_or_none(getattr(after, "afk_timeout", None))
        if before_afk_timeout != after_afk_timeout:
            changes.append(
                f"AFK Timeout Changed {self.ARROW} `{before_afk_timeout}` → `{after_afk_timeout}`"
            )

        before_locale = text_or_none(getattr(before, "preferred_locale", None))
        after_locale = text_or_none(getattr(after, "preferred_locale", None))
        if before_locale != after_locale:
            changes.append(
                f"Preferred Locale Changed {self.ARROW} `{before_locale}` → `{after_locale}`"
            )

        before_afk_channel = getattr(before, "afk_channel", None)
        after_afk_channel = getattr(after, "afk_channel", None)
        if before_afk_channel is None and after_afk_channel is not None:
            changes.append(f"AFK Channel Added {self.ARROW} {channel_text(after_afk_channel)}")
        elif before_afk_channel is not None and after_afk_channel is None:
            changes.append(f"AFK Channel Removed {self.ARROW} {channel_text(before_afk_channel)}")
        elif before_afk_channel != after_afk_channel:
            changes.append(
                f"AFK Channel Changed {self.ARROW} {channel_text(before_afk_channel)} → {channel_text(after_afk_channel)}"
            )

        before_system_channel = getattr(before, "system_channel", None)
        after_system_channel = getattr(after, "system_channel", None)
        if before_system_channel is None and after_system_channel is not None:
            changes.append(f"System Channel Added {self.ARROW} {channel_text(after_system_channel)}")
        elif before_system_channel is not None and after_system_channel is None:
            changes.append(f"System Channel Removed {self.ARROW} {channel_text(before_system_channel)}")
        elif before_system_channel != after_system_channel:
            changes.append(
                f"System Channel Changed {self.ARROW} {channel_text(before_system_channel)} → {channel_text(after_system_channel)}"
            )

        before_rules_channel = getattr(before, "rules_channel", None)
        after_rules_channel = getattr(after, "rules_channel", None)
        if before_rules_channel is None and after_rules_channel is not None:
            changes.append(f"Rules Channel Added {self.ARROW} {channel_text(after_rules_channel)}")
        elif before_rules_channel is not None and after_rules_channel is None:
            changes.append(f"Rules Channel Removed {self.ARROW} {channel_text(before_rules_channel)}")
        elif before_rules_channel != after_rules_channel:
            changes.append(
                f"Rules Channel Changed {self.ARROW} {channel_text(before_rules_channel)} → {channel_text(after_rules_channel)}"
            )

        before_public_updates = getattr(before, "public_updates_channel", None)
        after_public_updates = getattr(after, "public_updates_channel", None)
        if before_public_updates is None and after_public_updates is not None:
            changes.append(f"Public Updates Channel Added {self.ARROW} {channel_text(after_public_updates)}")
        elif before_public_updates is not None and after_public_updates is None:
            changes.append(f"Public Updates Channel Removed {self.ARROW} {channel_text(before_public_updates)}")
        elif before_public_updates != after_public_updates:
            changes.append(
                f"Public Updates Channel Changed {self.ARROW} {channel_text(before_public_updates)} → {channel_text(after_public_updates)}"
            )

        before_flags = set()
        after_flags = set()

        before_system_flags = getattr(before, "system_channel_flags", None)
        after_system_flags = getattr(after, "system_channel_flags", None)

        if before_system_flags is not None:
            for name in dir(before_system_flags):
                if name.startswith("_"):
                    continue
                flag_value = getattr(before_system_flags, name, None)
                if isinstance(flag_value, bool) and flag_value:
                    before_flags.add(name)

        if after_system_flags is not None:
            for name in dir(after_system_flags):
                if name.startswith("_"):
                    continue
                flag_value = getattr(after_system_flags, name, None)
                if isinstance(flag_value, bool) and flag_value:
                    after_flags.add(name)

        added_flags = sorted(after_flags - before_flags)
        removed_flags = sorted(before_flags - after_flags)

        if added_flags:
            changes.append(
                f"System Channel Flags Added {self.ARROW} " + ", ".join(f"`{flag}`" for flag in added_flags)
            )
        if removed_flags:
            changes.append(
                f"System Channel Flags Removed {self.ARROW} " + ", ".join(f"`{flag}`" for flag in removed_flags)
            )

        if not changes:
            return

        actor_text = "-# **Moderator:** Unknown"
        reason_text = None

        entry = await self._find_recent_guild_audit_entry(
            after,
            action=discord.AuditLogAction.guild_update,
        )
        if entry is not None and entry.user is not None:
            actor = entry.user
            actor_text = f"-# **Moderator:** {actor} • {actor.id}"
            if entry.reason:
                reason_text = f"-# Reason: {entry.reason}"

        items: list[Any] = [
            TextDisplay("## Server Updated"),
            TextDisplay(self._truncate("\n".join(changes), limit=1400)),
            discord.ui.Separator(
                divider=True,
                spacing=discord.SeparatorSpacingSize.small,
            ),
        ]

        footer_lines = [actor_text]
        if reason_text:
            footer_lines.append(reason_text)

        items.append(TextDisplay(self._truncate("\n".join(footer_lines), limit=300)))

        view = DesignerView(
            Container(
                *self._flatten_items(items),
                color=self._color("guild_update"),
            )
        )
        await self._send_view(view=view)

    @commands.Cog.listener()
    async def on_scheduled_event_create(self, event: discord.ScheduledEvent) -> None:
        guild = getattr(event, "guild", None)
        if guild is None or not self._is_target_guild(guild.id):
            return

        actor_text = "-# **Moderator:** Unknown"
        reason_text = None
        creator_text = await self._scheduled_event_creator_text(event)

        entry = await self._find_recent_scheduled_event_audit_entry(
            guild,
            event_id=event.id,
            action=discord.AuditLogAction.scheduled_event_create,
        )
        if entry is not None and entry.user is not None:
            actor = entry.user
            actor_text = f"-# **Moderator:** {actor} • {actor.id}"
            if entry.reason:
                reason_text = f"-# Reason: {entry.reason}"

        body = self._truncate(
            "\n".join(
                [
                    f"Name {self.ARROW} `{event.name}`",
                    f"ID {self.ARROW} `{event.id}`",
                    f"Status {self.ARROW} `{getattr(event, 'status', 'Unknown')}`",
                    f"Start {self.ARROW} {self._fmt_dt(getattr(event, 'start_time', None), 'f')}",
                    f"End {self.ARROW} {self._fmt_dt(getattr(event, 'end_time', None), 'f')}",
                    f"Location {self.ARROW} {self._scheduled_event_location_text(event)}",
                    f"Creator {self.ARROW} {creator_text}",
                    f"Description {self.ARROW} `{getattr(event, 'description', None) or 'None'}`",
                ]
            ),
            limit=1500,
        )

        footer_lines = [actor_text]
        if reason_text:
            footer_lines.append(reason_text)

        view = DesignerView(
            Container(
                TextDisplay("## Scheduled Event Created"),
                TextDisplay(body),
                discord.ui.Separator(
                    divider=True,
                    spacing=discord.SeparatorSpacingSize.small,
                ),
                TextDisplay(self._truncate("\n".join(footer_lines), limit=300)),
                color=self._color("scheduled_event_create"),
            )
        )
        await self._send_view(view=view)

    @commands.Cog.listener()
    async def on_scheduled_event_delete(self, event: discord.ScheduledEvent) -> None:
        guild = getattr(event, "guild", None)
        if guild is None or not self._is_target_guild(guild.id):
            return

        actor_text = "-# **Moderator:** Unknown"
        reason_text = None

        entry = await self._find_recent_scheduled_event_audit_entry(
            guild,
            event_id=event.id,
            action=discord.AuditLogAction.scheduled_event_delete,
        )
        if entry is not None and entry.user is not None:
            actor = entry.user
            actor_text = f"-# **Moderator:** {actor} • {actor.id}"
            if entry.reason:
                reason_text = f"-# Reason: {entry.reason}"

        body = self._truncate(
            "\n".join(
                [
                    f"Name {self.ARROW} `{event.name}`",
                    f"ID {self.ARROW} `{event.id}`",
                    f"Status {self.ARROW} `{getattr(event, 'status', 'Unknown')}`",
                    f"Start {self.ARROW} {self._fmt_dt(getattr(event, 'start_time', None), 'f')}",
                    f"End {self.ARROW} {self._fmt_dt(getattr(event, 'end_time', None), 'f')}",
                    f"Location {self.ARROW} {self._scheduled_event_location_text(event)}",
                ]
            ),
            limit=1500,
        )

        footer_lines = [actor_text]
        if reason_text:
            footer_lines.append(reason_text)

        view = DesignerView(
            Container(
                TextDisplay("## Scheduled Event Deleted"),
                TextDisplay(body),
                discord.ui.Separator(
                    divider=True,
                    spacing=discord.SeparatorSpacingSize.small,
                ),
                TextDisplay(self._truncate("\n".join(footer_lines), limit=300)),
                color=self._color("scheduled_event_delete"),
            )
        )
        await self._send_view(view=view)

    @commands.Cog.listener()
    async def on_scheduled_event_update(
        self,
        before: discord.ScheduledEvent,
        after: discord.ScheduledEvent,
    ) -> None:
        guild = getattr(after, "guild", None)
        if guild is None or not self._is_target_guild(guild.id):
            return

        changes: list[str] = []

        if before.name != after.name:
            changes.append(f"Name {self.ARROW} `{before.name}` → `{after.name}`")

        if getattr(before, "description", None) != getattr(after, "description", None):
            changes.append(
                f"Description {self.ARROW} `{getattr(before, 'description', None) or 'None'}` → `{getattr(after, 'description', None) or 'None'}`"
            )

        if getattr(before, "status", None) != getattr(after, "status", None):
            changes.append(
                f"Status {self.ARROW} `{getattr(before, 'status', None)}` → `{getattr(after, 'status', None)}`"
            )

        if getattr(before, "start_time", None) != getattr(after, "start_time", None):
            changes.append(
                f"Start {self.ARROW} {self._fmt_dt(getattr(before, 'start_time', None), 'f')} → {self._fmt_dt(getattr(after, 'start_time', None), 'f')}"
            )

        if getattr(before, "end_time", None) != getattr(after, "end_time", None):
            changes.append(
                f"End {self.ARROW} {self._fmt_dt(getattr(before, 'end_time', None), 'f')} → {self._fmt_dt(getattr(after, 'end_time', None), 'f')}"
            )

        if self._scheduled_event_location_text(before) != self._scheduled_event_location_text(after):
            changes.append(
                f"Location {self.ARROW} {self._scheduled_event_location_text(before)} → {self._scheduled_event_location_text(after)}"
            )

        if not changes:
            return

        actor_text = "-# **Moderator:** Unknown"
        reason_text = None

        entry = await self._find_recent_scheduled_event_audit_entry(
            guild,
            event_id=after.id,
            action=discord.AuditLogAction.scheduled_event_update,
        )
        if entry is not None and entry.user is not None:
            actor = entry.user
            actor_text = f"-# **Moderator:** {actor} • {actor.id}"
            if entry.reason:
                reason_text = f"-# Reason: {entry.reason}"

        items: list[Any] = [
            TextDisplay("## Scheduled Event Updated"),
            TextDisplay(
                self._truncate(
                    "\n".join(
                        [
                            f"Name {self.ARROW} `{after.name}`",
                            f"ID {self.ARROW} `{after.id}`",
                        ]
                    ),
                    limit=800,
                )
            ),
            TextDisplay(self._truncate("\n".join(changes), limit=1400)),
            discord.ui.Separator(
                divider=True,
                spacing=discord.SeparatorSpacingSize.small,
            ),
        ]

        footer_lines = [actor_text]
        if reason_text:
            footer_lines.append(reason_text)

        items.append(TextDisplay(self._truncate("\n".join(footer_lines), limit=300)))

        view = DesignerView(
            Container(
                *self._flatten_items(items),
                color=self._color("scheduled_event_update"),
            )
        )
        await self._send_view(view=view)

    @commands.Cog.listener()
    async def on_guild_stickers_update(self, guild: discord.Guild, before, after) -> None:
        if not self._is_target_guild(guild.id):
            return

        before_map = self._sticker_map(before)
        after_map = self._sticker_map(after)

        created_ids = sorted(after_map.keys() - before_map.keys())
        deleted_ids = sorted(before_map.keys() - after_map.keys())

        updated_ids: list[int] = []
        for sticker_id in sorted(before_map.keys() & after_map.keys()):
            b = before_map[sticker_id]
            a = after_map[sticker_id]

            if (
                getattr(b, "name", None) != getattr(a, "name", None)
                or getattr(b, "description", None) != getattr(a, "description", None)
                or getattr(b, "emoji", None) != getattr(a, "emoji", None)
                or getattr(b, "available", None) != getattr(a, "available", None)
            ):
                updated_ids.append(sticker_id)

        if not created_ids and not deleted_ids and not updated_ids:
            return

        title = "## Sticker Updated"
        color_key = "sticker_update"

        if created_ids and not deleted_ids and not updated_ids:
            title = "## Sticker Created"
            color_key = "sticker_create"
        elif deleted_ids and not created_ids and not updated_ids:
            title = "## Sticker Deleted"
            color_key = "sticker_delete"

        items: list[Any] = [TextDisplay(title)]

        for sticker_id in created_ids:
            items.append(TextDisplay(f"Created {self.ARROW} {self._sticker_label(after_map[sticker_id])}"))

        for sticker_id in deleted_ids:
            items.append(TextDisplay(f"Deleted {self.ARROW} {self._sticker_label(before_map[sticker_id])}"))

        for sticker_id in updated_ids:
            b = before_map[sticker_id]
            a = after_map[sticker_id]

            lines = [f"Sticker {self.ARROW} `{sticker_id}`"]

            if getattr(b, "name", None) != getattr(a, "name", None):
                lines.append(f"Name {self.ARROW} `{getattr(b, 'name', None)}` → `{getattr(a, 'name', None)}`")

            if getattr(b, "description", None) != getattr(a, "description", None):
                lines.append(
                    f"Description {self.ARROW} `{getattr(b, 'description', None) or 'None'}` → `{getattr(a, 'description', None) or 'None'}`"
                )

            if getattr(b, "emoji", None) != getattr(a, "emoji", None):
                lines.append(f"Emoji {self.ARROW} `{getattr(b, 'emoji', None)}` → `{getattr(a, 'emoji', None)}`")

            if getattr(b, "available", None) != getattr(a, "available", None):
                lines.append(
                    f"Available {self.ARROW} `{getattr(b, 'available', None)}` → `{getattr(a, 'available', None)}`"
                )

            items.append(TextDisplay(self._truncate("\n".join(lines), limit=1200)))

        actor_text = "-# **Moderator:** Unknown"
        reason_text = None
        entry = None

        if created_ids:
            entry = await self._find_recent_audit_entry_for_target(
                guild,
                target_id=created_ids[0],
                actions=discord.AuditLogAction.sticker_create,
            )
        elif deleted_ids:
            entry = await self._find_recent_audit_entry_for_target(
                guild,
                target_id=deleted_ids[0],
                actions=discord.AuditLogAction.sticker_delete,
            )
        elif updated_ids:
            entry = await self._find_recent_audit_entry_for_target(
                guild,
                target_id=updated_ids[0],
                actions=discord.AuditLogAction.sticker_update,
            )

        if entry is not None and entry.user is not None:
            actor = entry.user
            actor_text = f"-# **Moderator:** {actor} • {actor.id}"
            if entry.reason:
                reason_text = f"-# Reason: {entry.reason}"

        items.append(
            discord.ui.Separator(
                divider=True,
                spacing=discord.SeparatorSpacingSize.small,
            )
        )

        footer_lines = [actor_text]
        if reason_text:
            footer_lines.append(reason_text)

        items.append(TextDisplay(self._truncate("\n".join(footer_lines), limit=300)))

        view = DesignerView(
            Container(
                *self._flatten_items(items),
                color=self._color(color_key),
            )
        )
        await self._send_view(view=view)

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel) -> None:
        guild = getattr(channel, "guild", None)
        if guild is None or not self._is_target_guild(guild.id):
            return

        body = self._truncate(
            "\n".join(
                [
                    f"Channel {self.ARROW} {getattr(channel, 'name', 'Unknown')} | {self._channel_name(channel)}",
                    f"ID {self.ARROW} `{getattr(channel, 'id', 'Unknown')}`",
                    f"Type {self.ARROW} `{type(channel).__name__}`",
                ]
            ),
            limit=1200,
        )

        view = DesignerView(
            Container(
                TextDisplay("## Webhooks Updated"),
                TextDisplay(body),
                color=self._color("webhook_update"),
            )
        )
        await self._send_view(view=view)


def setup(bot: commands.Bot) -> None:
    bot.add_cog(Logs(bot))
