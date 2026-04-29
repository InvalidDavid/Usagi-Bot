from utils.imports import *
from utils.helper.loghelper import LogsHelper
from utils.helper.loghelpermsg import LogsMsgHelper
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

# dont change that, may break
NORMAL_DELETE_ATTACHMENT_CACHE_TTL = 10 * 60
NORMAL_DELETE_ATTACHMENT_MAX_FILE_BYTES = 25 * 1024 * 1024
NORMAL_DELETE_ATTACHMENT_MAX_TOTAL_BYTES = 75 * 1024 * 1024
NORMAL_DELETE_ATTACHMENT_MAX_FILES = 10
NORMAL_DELETE_ATTACHMENT_CACHE_MAX_MESSAGES = 250
NORMAL_DELETE_ATTACHMENT_CACHE_MAX_BYTES = 1024 * 1024 * 1024


class Logs(LogsHelper, LogsMsgHelper, commands.Cog):
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

    NORMAL_DELETE_ATTACHMENT_CACHE_TTL = NORMAL_DELETE_ATTACHMENT_CACHE_TTL
    NORMAL_DELETE_ATTACHMENT_MAX_FILE_BYTES = NORMAL_DELETE_ATTACHMENT_MAX_FILE_BYTES
    NORMAL_DELETE_ATTACHMENT_MAX_TOTAL_BYTES = NORMAL_DELETE_ATTACHMENT_MAX_TOTAL_BYTES
    NORMAL_DELETE_ATTACHMENT_MAX_FILES = NORMAL_DELETE_ATTACHMENT_MAX_FILES
    NORMAL_DELETE_ATTACHMENT_CACHE_MAX_MESSAGES = NORMAL_DELETE_ATTACHMENT_CACHE_MAX_MESSAGES
    NORMAL_DELETE_ATTACHMENT_CACHE_MAX_BYTES = NORMAL_DELETE_ATTACHMENT_CACHE_MAX_BYTES

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
        self._member_update_handles: dict[tuple[int, int], asyncio.Handle] = {}

        self._recent_bans: set[int] = set()
        self._recent_user_update_keys: set[tuple[int, str, str, str, str]] = set()

        self._background_tasks: set[asyncio.Task] = set()
        self._scheduled_handles: set[asyncio.Handle] = set()

        self._recent_audit_entries: dict[int, list[discord.AuditLogEntry]] = {}
        self._recent_audit_entry_ids: set[int] = set()

        self._message_attachment_cache: dict[int, dict[str, Any]] = {}
        self._message_attachment_cache_bytes = 0
        self._attachment_cache_tasks: dict[int, asyncio.Task] = {}

        self._recent_message_meta: dict[int, dict[str, Any]] = {}

        self._create_task(self._maintenance_loop(), name="logs:maintenance")


    def cache_stats(self) -> dict[str, Any]:
        for guild_id in list(self._recent_audit_entries.keys()):
            self._prune_recent_audit_entries(guild_id)

        self._prune_message_attachment_cache()
        self._prune_recent_message_meta()

        recent_audit_entries = sum(
            len(entries)
            for entries in self._recent_audit_entries.values()
        )

        return {
            "type": "event-state",
            "recent_bulk_log_keys": len(self._recent_bulk_log_keys),
            "pending_member_updates": len(self._pending_member_updates),
            "member_update_handles": sum(
                1 for handle in self._member_update_handles.values()
                if not handle.cancelled()
            ),
            "recent_bans": len(self._recent_bans),
            "recent_user_update_keys": len(self._recent_user_update_keys),
            "background_tasks": sum(
                1 for task in self._background_tasks
                if not task.done()
            ),
            "scheduled_handles": sum(
                1 for handle in self._scheduled_handles
                if not handle.cancelled()
            ),
            "attachment_cache_tasks": sum(
                1 for task in self._attachment_cache_tasks.values()
                if not task.done()
            ),
            "recent_audit_entries": recent_audit_entries,
            "recent_audit_entry_ids": len(self._recent_audit_entry_ids),
            "message_attachment_cache_entries": len(self._message_attachment_cache),
            "message_attachment_cache_bytes": self._message_attachment_cache_bytes,
            "message_attachment_cache_mib": round(self._message_attachment_cache_bytes / 1024 / 1024, 2),
            "message_attachment_cache_max_messages": self.NORMAL_DELETE_ATTACHMENT_CACHE_MAX_MESSAGES,
            "message_attachment_cache_max_mib": round(self.NORMAL_DELETE_ATTACHMENT_CACHE_MAX_BYTES / 1024 / 1024, 2),
            "message_attachment_cache_ttl_seconds": self.NORMAL_DELETE_ATTACHMENT_CACHE_TTL,
            "recent_message_meta": len(self._recent_message_meta),
        }

    def cog_unload(self) -> None:
        for task in list(self._background_tasks):
            task.cancel()

        for task in list(self._attachment_cache_tasks.values()):
            task.cancel()

        for handle in list(self._member_update_handles.values()):
            handle.cancel()

        for handle in list(self._scheduled_handles):
            handle.cancel()

        self._attachment_cache_tasks.clear()
        self._background_tasks.clear()
        self._scheduled_handles.clear()
        self._member_update_handles.clear()
        self._pending_member_updates.clear()
        self._recent_bulk_log_keys.clear()
        self._recent_bans.clear()
        self._recent_user_update_keys.clear()
        self._recent_audit_entries.clear()
        self._recent_audit_entry_ids.clear()
        self._message_attachment_cache.clear()
        self._message_attachment_cache_bytes = 0
        self._recent_message_meta.clear()

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
            logger.error(
                "Unhandled task error in Logs cog.",
                exc_info=(type(exc), exc, exc.__traceback__),
            )

    def _schedule_callback(
        self,
        delay: float,
        callback: Callable[..., Any],
        *args: Any,
    ) -> asyncio.Handle:
        loop = asyncio.get_running_loop()

        handle: Optional[asyncio.Handle] = None

        def wrapped() -> None:
            if handle is not None:
                self._scheduled_handles.discard(handle)

            try:
                callback(*args)
            except Exception:
                logger.exception("Scheduled callback failed in Logs cog.")

        handle = loop.call_later(max(float(delay), 0.0), wrapped)
        self._scheduled_handles.add(handle)
        return handle

    def _discard_recent_ban(self, user_id: int) -> None:
        self._recent_bans.discard(user_id)

    def _discard_recent_user_update_key(self, key: tuple[int, str, str, str, str]) -> None:
        self._recent_user_update_keys.discard(key)

    def _discard_recent_bulk_key(
        self,
        guild_id: int,
        channel_id: int,
        message_ids: Iterable[int],
    ) -> None:
        self._recent_bulk_log_keys.discard(
            self._bulk_log_key(guild_id, channel_id, message_ids)
        )

    async def _maintenance_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(60)

                try:
                    self._prune_message_attachment_cache()

                    for guild_id in list(self._recent_audit_entries):
                        self._prune_recent_audit_entries(guild_id)

                    self._prune_recent_message_meta()

                except Exception:
                    logger.exception("Logs maintenance iteration failed.")

        except asyncio.CancelledError:
            return

    @commands.Cog.listener()
    async def on_audit_log_entry(self, entry: discord.AuditLogEntry) -> None:
        guild = getattr(entry, "guild", None)
        if guild is None or not self._is_target_guild(guild.id):
            return

        self._store_recent_audit_entry(entry)

    async def _flush_member_update(self, key: tuple[int, int]) -> None:
        self._member_update_handles.pop(key, None)

        payload = self._pending_member_updates.pop(key, None)
        if not payload:
            return

        before: discord.Member = payload["before"]
        after: discord.Member = payload["after"]

        if not self._is_target_guild(after.guild.id):
            return

        changes: list[str] = []

        nick_changed = before.nick != after.nick
        roles_changed = set(self._role_map(before)) != set(self._role_map(after))
        timeout_changed = self._member_timeout_until(before) != self._member_timeout_until(after)

        if nick_changed:
            changes.append(f"Nickname {self.ARROW} `{before.nick or 'None'}` → `{after.nick or 'None'}`")

        changes.extend(self._role_change_lines(before, after))

        if timeout_changed:
            before_timeout = self._member_timeout_until(before)
            after_timeout = self._member_timeout_until(after)

            changes.append(
                f"Timeout {self.ARROW} {self._fmt_dt(before_timeout, 'R')} → {self._fmt_dt(after_timeout, 'R')}"
            )

        if not changes:
            return

        actor = None
        reason = None

        if nick_changed or timeout_changed:
            entry = await self._find_recent_member_audit_entry(
                after.guild,
                member_id=after.id,
                action=discord.AuditLogAction.member_update,
            )

            if entry is not None:
                entry_actor = entry.user

                if entry_actor is not None and getattr(entry_actor, "id", None) != after.id:
                    actor = entry_actor
                    reason = entry.reason

        if actor is None and roles_changed:
            role_action = getattr(discord.AuditLogAction, "member_role_update", None)

            if role_action is not None:
                entry = await self._find_recent_member_audit_entry(
                    after.guild,
                    member_id=after.id,
                    action=role_action,
                    delay=0,
                )

                if entry is not None:
                    entry_actor = entry.user

                    if entry_actor is not None and getattr(entry_actor, "id", None) != after.id:
                        actor = entry_actor
                        reason = entry.reason

        view = self.build_member_update_view(
            after=after,
            changes=changes,
            actor=actor,
            reason=reason,
        )
        await self._send_view(view=view)

    def _queue_member_update(self, before: discord.Member, after: discord.Member) -> None:
        key = (after.guild.id, after.id)

        existing = self._pending_member_updates.get(key)
        if existing is None:
            self._pending_member_updates[key] = {"before": before, "after": after}
        else:
            existing["after"] = after

        old_handle = self._member_update_handles.pop(key, None)
        if old_handle is not None:
            old_handle.cancel()

        handle: Optional[asyncio.Handle] = None

        def start_flush() -> None:
            if handle is not None:
                self._member_update_handles.pop(key, None)

            self._create_task(
                self._flush_member_update(key),
                name=f"logs:member_update:{after.id}",
            )

        handle = asyncio.get_running_loop().call_later(
            max(float(self.MEMBER_UPDATE_DELAY), 0.0),
            start_flush,
        )
        self._member_update_handles[key] = handle

    def _mark_bulk_log_seen(
        self,
        guild_id: int,
        channel_id: int,
        message_ids: Iterable[int],
    ) -> bool:
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

        cached_list = list(cached_messages)
        cached_by_id = {int(msg.id): msg for msg in cached_list}

        human_ids: set[int] = set()
        human_cached_messages: list[discord.Message] = []

        for raw_id in message_ids:
            message_id = int(raw_id)
            cached_msg = cached_by_id.get(message_id)

            if cached_msg is not None:
                if getattr(getattr(cached_msg, "author", None), "bot", False):
                    continue

                human_ids.add(message_id)
                human_cached_messages.append(cached_msg)
                continue

            meta = getattr(self, "_recent_message_meta", {}).get(message_id)

            if meta is None:
                continue

            if meta.get("author_bot"):
                continue

            human_ids.add(message_id)

        normalized_ids = sorted(human_ids)
        if not normalized_ids:
            return

        total_count = len(normalized_ids)

        if guild_id is not None and self._mark_bulk_log_seen(guild_id, channel_id, normalized_ids):
            return

        if guild_id is not None:
            self._schedule_callback(
                self.RECENT_BULK_LOG_TTL,
                self._discard_recent_bulk_key,
                guild_id,
                channel_id,
                tuple(normalized_ids),
            )

        guild = self.bot.get_guild(guild_id) if guild_id else None

        moderator = None
        reason = None

        if guild is not None:
            moderator, reason = await self._find_bulk_delete_actor(
                guild,
                channel_id=channel_id,
                total_count=total_count,
            )

        file_to_send = self._create_bulk_deleted_file(
            normalized_ids,
            human_cached_messages,
            channel_id=channel_id,
        )

        view = await self.build_bulk_delete_view(
            guild_id=guild_id,
            channel_id=channel_id,
            total_count=total_count,
            file_to_send=file_to_send,
            moderator=moderator,
            reason=reason,
        )

        await self._send_view(view=view, file=file_to_send)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if not self._is_target_guild(member.guild.id):
            return

        member = await self._get_fresh_member(member)

        view = self.build_member_join_view(member)
        await self._send_view(view=view)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if not self._is_target_guild(member.guild.id):
            return

        if member.id in self._recent_bans:
            return

        entry = await self._find_recent_member_remove_audit_entry(
            member.guild,
            member_id=member.id,
        )

        if member.id in self._recent_bans:
            return

        if entry is not None and entry.action == discord.AuditLogAction.ban:
            return

        kicked = entry is not None and entry.action == discord.AuditLogAction.kick
        title = "## Member Kicked" if kicked else "## Member Left"

        actor = entry.user if kicked and entry is not None else None
        reason = entry.reason if kicked and entry is not None else None

        view = self.build_member_remove_view(
            member=member,
            title=title,
            actor=actor,
            reason=reason,
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
        self._schedule_callback(
            self.RECENT_BAN_TTL,
            self._discard_recent_ban,
            user.id,
        )

        actor = None
        reason = None

        entry = await self._find_recent_member_audit_entry(
            guild,
            member_id=user.id,
            action=discord.AuditLogAction.ban,
        )

        if entry is not None:
            actor = entry.user
            reason = entry.reason

        view = self.build_member_ban_view(
            user=user,
            actor=actor,
            reason=reason,
        )
        await self._send_view(view=view)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        if not self._is_target_guild(guild.id):
            return

        actor = None
        reason = None

        entry = await self._find_recent_member_audit_entry(
            guild,
            member_id=user.id,
            action=discord.AuditLogAction.unban,
        )

        if entry is not None:
            actor = entry.user
            reason = entry.reason

        view = self.build_member_unban_view(
            user=user,
            actor=actor,
            reason=reason,
        )
        await self._send_view(view=view)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if not self._is_target_guild(after.guild.id):
            return

        relevant_change = (
            before.nick != after.nick
            or set(self._role_map(before)) != set(self._role_map(after))
            or self._member_timeout_until(before) != self._member_timeout_until(after)
        )

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
        self._schedule_callback(
            self.RECENT_USER_UPDATE_TTL,
            self._discard_recent_user_update_key,
            dedupe_key,
        )

        view = self.build_user_update_view(
            member=member,
            after=after,
            changes=changes,
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

        view = self.build_voice_state_view(
            member=member,
            change=change,
        )
        await self._send_view(view=view)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        if not self._is_target_guild(channel.guild.id):
            return

        actor = None
        reason = None

        entry = await self._find_recent_channel_audit_entry(
            channel.guild,
            channel_id=channel.id,
            action=discord.AuditLogAction.channel_create,
        )

        if entry is not None:
            actor = entry.user
            reason = entry.reason

        view = self.build_channel_create_view(
            channel=channel,
            actor=actor,
            reason=reason,
        )
        await self._send_view(view=view)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        if not self._is_target_guild(channel.guild.id):
            return

        actor = None
        reason = None

        entry = await self._find_recent_channel_audit_entry(
            channel.guild,
            channel_id=channel.id,
            action=discord.AuditLogAction.channel_delete,
        )

        if entry is not None:
            actor = entry.user
            reason = entry.reason

        view = self.build_channel_delete_view(
            channel=channel,
            actor=actor,
            reason=reason,
        )
        await self._send_view(view=view)

    @commands.Cog.listener()
    async def on_guild_channel_update(
        self,
        before: discord.abc.GuildChannel,
        after: discord.abc.GuildChannel,
    ) -> None:
        if not self._is_target_guild(after.guild.id):
            return

        changes: list[str] = []

        channel_kind = self._channel_kind(after)

        if before.name != after.name:
            changes.append(f"Name {self.ARROW} `{before.name}` → `{after.name}`")

        before_topic = getattr(before, "topic", None)
        after_topic = getattr(after, "topic", None)

        if before_topic != after_topic:
            changes.append(f"Topic {self.ARROW} `{before_topic or 'None'}` → `{after_topic or 'None'}`")

        before_category_id = getattr(before, "category_id", None)
        after_category_id = getattr(after, "category_id", None)

        if before_category_id != after_category_id:
            changes.append(f"Category ID {self.ARROW} `{before_category_id}` → `{after_category_id}`")

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

        actor = None
        reason = None

        entry = await self._find_recent_channel_or_overwrite_audit_entry(
            after.guild,
            channel_id=after.id,
            category_id=after_category_id,
        )

        if entry is not None:
            actor = entry.user
            reason = entry.reason

        view = self.build_channel_update_view(
            channel=after,
            channel_kind=channel_kind,
            changes=changes,
            actor=actor,
            reason=reason,
        )
        await self._send_view(view=view)

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread) -> None:
        if not self._is_target_guild(thread.guild.id):
            return

        actor = None
        reason = None

        thread_create_action = getattr(discord.AuditLogAction, "thread_create", None)

        if thread_create_action is not None:
            entry = await self._find_recent_thread_audit_entry(
                thread.guild,
                thread_id=thread.id,
                action=thread_create_action,
            )

            if entry is not None:
                entry_actor = getattr(entry, "user", None)
                owner_id = getattr(thread, "owner_id", None)

                # Own thread created by the owner = no moderator footer.
                if entry_actor is not None and getattr(entry_actor, "id", None) != owner_id:
                    actor = entry_actor
                    reason = entry.reason

        view = self.build_thread_create_view(
            thread=thread,
            actor=actor,
            reason=reason,
        )
        await self._send_view(view=view)

    @commands.Cog.listener()
    async def on_thread_delete(self, thread: discord.Thread) -> None:
        if not self._is_target_guild(thread.guild.id):
            return

        actor = None
        reason = None

        entry = await self._find_recent_thread_audit_entry(
            thread.guild,
            thread_id=thread.id,
            action=discord.AuditLogAction.thread_delete,
        )

        if entry is not None:
            actor = entry.user
            reason = entry.reason

        view = self.build_thread_delete_view(
            thread=thread,
            actor=actor,
            reason=reason,
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

        actor = None
        reason = None

        thread_update_action = getattr(discord.AuditLogAction, "thread_update", None)

        if thread_update_action is not None:
            entry = await self._find_recent_thread_audit_entry(
                after.guild,
                thread_id=after.id,
                action=thread_update_action,
            )

            if entry is not None:
                actor = entry.user
                reason = entry.reason

        view = self.build_thread_update_view(
            thread=after,
            changes=changes,
            actor=actor,
            reason=reason,
        )
        await self._send_view(view=view)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        if not self._is_target_guild(role.guild.id):
            return

        actor = None
        reason = None

        entry = await self._find_recent_role_audit_entry(
            role.guild,
            role_id=role.id,
            action=discord.AuditLogAction.role_create,
        )

        if entry is not None:
            actor = entry.user
            reason = entry.reason

        view = self.build_role_create_view(
            role=role,
            actor=actor,
            reason=reason,
        )
        await self._send_view(view=view)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        if not self._is_target_guild(role.guild.id):
            return

        actor = None
        reason = None

        entry = await self._find_recent_role_audit_entry(
            role.guild,
            role_id=role.id,
            action=discord.AuditLogAction.role_delete,
        )

        if entry is not None:
            actor = entry.user
            reason = entry.reason

        view = self.build_role_delete_view(
            role=role,
            actor=actor,
            reason=reason,
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
            changes.extend(
                self._permission_delta_lines("Permissions", before.permissions, after.permissions)
            )

        if not changes:
            return

        actor = None
        reason = None

        entry = await self._find_recent_role_audit_entry(
            after.guild,
            role_id=after.id,
            action=discord.AuditLogAction.role_update,
        )

        if entry is not None:
            actor = entry.user
            reason = entry.reason

        view = self.build_role_update_view(
            role=after,
            changes=changes,
            actor=actor,
            reason=reason,
        )
        await self._send_view(view=view)

    @commands.Cog.listener()
    async def on_message_edit(
        self,
        msg_before: discord.Message,
        msg_after: discord.Message,
    ) -> None:
        if msg_before.guild is None or not self._is_target_guild(msg_before.guild.id):
            return

        if msg_before.author.bot or msg_after.author.bot:
            return

        before_attachments = [attachment.url for attachment in msg_before.attachments]
        after_attachments = [attachment.url for attachment in msg_after.attachments]

        if msg_before.content == msg_after.content and before_attachments == after_attachments:
            return

        view = self.build_message_edit_view(
            msg_before=msg_before,
            msg_after=msg_after,
        )
        await self._send_view(view=view)

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        if not self._is_target_guild(payload.guild_id):
            return

        cached_message = payload.cached_message

        if cached_message is not None:
            if getattr(getattr(cached_message, "author", None), "bot", False):
                return

            await self._send_deleted_message_log(
                message_id=cached_message.id,
                channel_id=cached_message.channel.id,
                guild_id=cached_message.guild.id if cached_message.guild else payload.guild_id,
                msg=cached_message,
            )
            return

        meta = getattr(self, "_recent_message_meta", {}).get(int(payload.message_id))
        if meta is None:
            return

        if meta.get("author_bot"):
            return

        await self._send_deleted_message_log(
            message_id=payload.message_id,
            channel_id=payload.channel_id,
            guild_id=payload.guild_id,
            msg=None,
        )

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

        updated_ids: list[int] = []

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

        actor = entry.user if entry is not None else None
        reason = entry.reason if entry is not None else None

        view = self.build_emoji_update_view(
            before_map=before_map,
            after_map=after_map,
            created_ids=created_ids,
            deleted_ids=deleted_ids,
            updated_ids=updated_ids,
            actor=actor,
            reason=reason,
        )
        await self._send_view(view=view)

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        if not self._is_target_guild(after.id):
            return

        changes = self._guild_update_change_lines(before, after)

        if not changes:
            return

        actor = None
        reason = None

        entry = await self._find_recent_guild_audit_entry(
            after,
            action=discord.AuditLogAction.guild_update,
        )

        if entry is not None:
            actor = entry.user
            reason = entry.reason

        view = self.build_guild_update_view(
            changes=changes,
            actor=actor,
            reason=reason,
        )
        await self._send_view(view=view)

    @commands.Cog.listener()
    async def on_guild_stickers_update(
        self,
        guild: discord.Guild,
        before: Sequence[Any],
        after: Sequence[Any],
    ) -> None:
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

        actor = entry.user if entry is not None else None
        reason = entry.reason if entry is not None else None

        view = self.build_sticker_update_view(
            before_map=before_map,
            after_map=after_map,
            created_ids=created_ids,
            deleted_ids=deleted_ids,
            updated_ids=updated_ids,
            actor=actor,
            reason=reason,
        )
        await self._send_view(view=view)

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel) -> None:
        guild = getattr(channel, "guild", None)
        if guild is None or not self._is_target_guild(guild.id):
            return

        entry = await self._find_recent_webhook_audit_entry(channel)

        actor = entry.user if entry is not None else None
        reason = entry.reason if entry is not None else None

        view = self.build_webhook_update_view(
            channel=channel,
            actor=actor,
            reason=reason,
        )
        await self._send_view(view=view)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None:
            return

        self._store_recent_message_meta(message)

        if message.author.bot:
            return

        if not message.attachments:
            return

        task = self._create_task(
            self._cache_message_attachments(message),
            name=f"logs:attachment_cache:{message.id}",
        )

        self._attachment_cache_tasks[message.id] = task
        task.add_done_callback(
            lambda done_task, message_id=message.id: self._attachment_cache_tasks.pop(message_id, None)
        )


def setup(bot: commands.Bot) -> None:
    bot.add_cog(Logs(bot))