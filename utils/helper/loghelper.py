from utils.imports import *

logger = logging.getLogger("bot.logging")


class LogsHelper:
    @staticmethod
    def _channel_kind(channel: Any) -> str:
        if isinstance(channel, discord.CategoryChannel):
            return "Category"
        if isinstance(channel, discord.TextChannel):
            return "Text Channel"
        if isinstance(channel, discord.VoiceChannel):
            return "Voice Channel"
        if isinstance(channel, discord.StageChannel):
            return "Stage Channel"
        if isinstance(channel, discord.ForumChannel):
            return "Forum Channel"
        if isinstance(channel, discord.Thread):
            return "Thread"
        return "Channel"

    @classmethod
    def _color(cls, key: str) -> discord.Color:
        return cls.COLORS.get(key, discord.Color.blurple())

    def _is_target_guild(self, guild_id: Optional[int]) -> bool:
        return guild_id == self.LOG_GUILD_ID

    @staticmethod
    def _safe_avatar_url(user: Union[discord.User, discord.Member, None]) -> Optional[str]:
        avatar = getattr(user, "display_avatar", None)
        return getattr(avatar, "url", None)

    @staticmethod
    def _safe_jump_url(obj: Any) -> Optional[str]:
        return getattr(obj, "jump_url", None)

    async def _get_log_channel(self) -> Optional[discord.abc.Messageable]:
        channel = self.bot.get_channel(self.LOG_CHANNEL_ID)
        if channel is not None:
            return channel

        try:
            return await self.bot.fetch_channel(self.LOG_CHANNEL_ID)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None

    async def _resolve_channel_obj(self, channel_id: int) -> Optional[Any]:
        channel = self.bot.get_channel(channel_id)
        if channel is not None:
            return channel

        guild = self.bot.get_guild(self.LOG_GUILD_ID)
        if guild is not None:
            channel = guild.get_channel(channel_id)
            if channel is not None:
                return channel

            get_thread = getattr(guild, "get_thread", None)
            if callable(get_thread):
                thread = get_thread(channel_id)
                if thread is not None:
                    return thread

        try:
            return await self.bot.fetch_channel(channel_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None

    @staticmethod
    def _fmt_dt(dt: Optional[datetime], style: str = "R") -> str:
        if dt is None:
            return "Unknown"
        return discord.utils.format_dt(dt, style)

    @staticmethod
    def _truncate(text: Optional[str], limit: int = 1600) -> str:
        if not text:
            return "[no text]"

        text = str(text).strip()
        if len(text) <= limit:
            return text

        return text[: limit - 3] + "..."

    @staticmethod
    def _message_flags(msg: discord.Message) -> str:
        flags = []

        if msg.pinned:
            flags.append("Pinned")
        if msg.tts:
            flags.append("TTS")
        if msg.mention_everyone:
            flags.append("@everyone")
        if msg.is_system():
            flags.append("System")

        return ", ".join(flags) if flags else "None"

    @staticmethod
    def _role_mentions(roles: Iterable[discord.Role]) -> str:
        role_list = list(roles)
        if not role_list:
            return "None"

        return ", ".join(role.mention for role in role_list)

    @staticmethod
    def _attachment_gallery(
        attachments: Iterable[discord.Attachment],
    ) -> Optional[MediaGallery]:
        items = []

        for attachment in attachments:
            url = getattr(attachment, "proxy_url", None) or getattr(attachment, "url", None)
            if url:
                items.append(discord.MediaGalleryItem(url=url))

        return MediaGallery(*items) if items else None

    @classmethod
    def _block_text(cls, title: str, *lines: str) -> str:
        clean = [str(line).strip() for line in lines if line is not None and str(line).strip()]

        if not clean:
            return f"**{title}**"

        return f"**{title}**\n" + "\n".join(f"{cls.ARROW} {line}" for line in clean)

    @staticmethod
    def _flatten_items(items: Iterable[Any]) -> list[Any]:
        flat: list[Any] = []

        for item in items:
            if item is None:
                continue

            if isinstance(item, (list, tuple)):
                flat.extend(sub for sub in item if sub is not None)
            else:
                flat.append(item)

        return flat

    @staticmethod
    def _sticker_preview_gallery(stickers: Iterable[Any]) -> Optional[MediaGallery]:
        items: list[Any] = []

        for sticker in stickers:
            url = getattr(sticker, "url", None)

            if url is None:
                asset = getattr(sticker, "asset", None)
                url = getattr(asset, "url", None)

            if not url:
                continue

            items.append(discord.MediaGalleryItem(url=str(url)))

        return MediaGallery(*items) if items else None

    @staticmethod
    def _channel_name(channel: Any) -> str:
        if channel is None:
            return "Unknown"

        mention = getattr(channel, "mention", None)
        return mention or f"`{getattr(channel, 'name', str(channel))}`"

    @staticmethod
    def _channel_id(channel: Any) -> str:
        return str(getattr(channel, "id", "Unknown"))

    @staticmethod
    def _member_timeout_until(member: discord.Member) -> Optional[datetime]:
        return getattr(
            member,
            "timed_out_until",
            getattr(member, "communication_disabled_until", None),
        )

    @staticmethod
    def _link_row(url: Optional[str], label: str = "Jump to Message") -> Optional[discord.ui.ActionRow]:
        if not url:
            return None

        return discord.ui.ActionRow(
            discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.link,
                url=url,
            )
        )

    @staticmethod
    def _permissions_to_text(perms: Optional[discord.Permissions]) -> str:
        if perms is None:
            return "None"

        enabled = [name for name, value in perms if value]
        if not enabled:
            return "None"

        return ", ".join(f"`{name}`" for name in enabled)

    @classmethod
    def _overwrite_to_lines(cls, overwrite: discord.PermissionOverwrite) -> tuple[str, str]:
        allow, deny = overwrite.pair()
        return cls._permissions_to_text(allow), cls._permissions_to_text(deny)

    @staticmethod
    def _overwrite_target_label(target: Any) -> str:
        if target is None:
            return "Unknown"

        target_id = getattr(target, "id", "Unknown")
        name = getattr(target, "name", None)

        if name == "@everyone":
            return f"@everyone (`{target_id}`)"

        if name:
            return f"{name} (`{target_id}`)"

        return f"{str(target)} (`{target_id}`)"

    @staticmethod
    def _permissions_to_set(perms: Optional[discord.Permissions]) -> set[str]:
        if perms is None:
            return set()

        return {name for name, value in perms if value}

    @classmethod
    def _permission_delta_lines(
        cls,
        prefix: str,
        before: Optional[discord.Permissions],
        after: Optional[discord.Permissions],
    ) -> list[str]:
        before_set = cls._permissions_to_set(before)
        after_set = cls._permissions_to_set(after)

        added = sorted(after_set - before_set)
        removed = sorted(before_set - after_set)

        lines: list[str] = []

        if added:
            lines.append(f"{prefix} Added {cls.ARROW} " + ", ".join(f"`{name}`" for name in added))

        if removed:
            lines.append(f"{prefix} Removed {cls.ARROW} " + ", ".join(f"`{name}`" for name in removed))

        return lines

    @staticmethod
    def _emoji_label(emoji: Any) -> str:
        emoji_id = getattr(emoji, "id", "Unknown")
        emoji_name = getattr(emoji, "name", "Unknown")
        emoji_repr = str(emoji) if getattr(emoji, "id", None) else emoji_name
        return f"{emoji_repr} • `{emoji_name}` • `{emoji_id}`"

    @staticmethod
    def _emoji_map(emojis: Iterable[Any]) -> dict[int, Any]:
        return {
            int(emoji.id): emoji
            for emoji in emojis
            if getattr(emoji, "id", None) is not None
        }

    @staticmethod
    def _sticker_map(stickers: Iterable[Any]) -> dict[int, Any]:
        return {
            int(sticker.id): sticker
            for sticker in stickers
            if getattr(sticker, "id", None) is not None
        }

    @classmethod
    def _sticker_label(cls, sticker: Any) -> str:
        sticker_id = getattr(sticker, "id", "Unknown")
        name = getattr(sticker, "name", "Unknown")
        emoji = getattr(sticker, "emoji", None) or "None"
        return f"`{name}` • `{sticker_id}` • Emoji {cls.ARROW} `{emoji}`"

    @staticmethod
    def _guild_channel_ref(channel: Any) -> str:
        if channel is None:
            return "None"

        mention = getattr(channel, "mention", None)
        return mention or f"`{getattr(channel, 'name', getattr(channel, 'id', 'Unknown'))}`"

    @staticmethod
    def _roles_without_default(member: discord.Member) -> list[discord.Role]:
        return [role for role in member.roles if role != member.guild.default_role]

    @classmethod
    def _role_map(cls, member: discord.Member) -> dict[int, discord.Role]:
        return {role.id: role for role in cls._roles_without_default(member)}

    @classmethod
    def _role_change_lines(cls, before: discord.Member, after: discord.Member) -> list[str]:
        before_roles = cls._role_map(before)
        after_roles = cls._role_map(after)

        added_roles = [
            after_roles[role_id]
            for role_id in sorted(after_roles.keys() - before_roles.keys())
        ]
        removed_roles = [
            before_roles[role_id]
            for role_id in sorted(before_roles.keys() - after_roles.keys())
        ]

        changes: list[str] = []

        if added_roles:
            changes.append(f"Roles Added {cls.ARROW} {cls._role_mentions(added_roles)}")

        if removed_roles:
            changes.append(f"Roles Removed {cls.ARROW} {cls._role_mentions(removed_roles)}")

        return changes

    @staticmethod
    def _thread_owner_text(thread: discord.Thread) -> str:
        owner = getattr(thread, "owner", None)

        if owner is not None:
            return f"{owner.name} | {owner.mention}"

        owner_id = getattr(thread, "owner_id", None)
        if owner_id is not None:
            return f"Unknown | <@{owner_id}>"

        return "Unknown | Unknown"

    @staticmethod
    def _audit_entry_is_fresh(
        entry: discord.AuditLogEntry,
        *,
        max_age: float,
    ) -> bool:
        created_at = getattr(entry, "created_at", None)
        if created_at is None:
            return True

        age = (discord.utils.utcnow() - created_at).total_seconds()
        return age <= max_age

    @staticmethod
    def _audit_target_id(entry: discord.AuditLogEntry) -> Optional[int]:
        target = getattr(entry, "target", None)
        target_id = getattr(target, "id", None)

        if target_id is None:
            return None

        with contextlib.suppress(TypeError, ValueError):
            return int(target_id)

        return None

    @staticmethod
    def _safe_int(value: Any) -> Optional[int]:
        if value is None:
            return None

        with contextlib.suppress(TypeError, ValueError):
            return int(value)

        return None

    async def _wait_for_audit_entry(
            self,
            guild: discord.Guild,
            *,
            actions: Union[discord.AuditLogAction, Iterable[discord.AuditLogAction]],
            target_ids: Iterable[int],
            limit: int = 20,
            timeout: float = 4.0,
            interval: float = 0.35,
            max_age: Optional[float] = None,
    ) -> Optional[discord.AuditLogEntry]:
        action_set = {actions} if isinstance(actions, discord.AuditLogAction) else set(actions)

        target_id_set: set[int] = set()
        for target_id in target_ids:
            target_id_int = self._safe_int(target_id)
            if target_id_int is not None:
                target_id_set.add(target_id_int)

        if not action_set or not target_id_set:
            return None

        actual_max_age = self.AUDIT_LOG_MAX_AGE if max_age is None else max_age

        async def check_once() -> Optional[discord.AuditLogEntry]:
            self._prune_recent_audit_entries(guild.id)

            for entry in self._recent_audit_entries.get(guild.id, []):
                if entry.action not in action_set:
                    continue

                if self._audit_target_id(entry) not in target_id_set:
                    continue

                if not self._audit_entry_is_fresh(entry, max_age=actual_max_age):
                    continue

                return entry

            try:
                async for entry in guild.audit_logs(limit=limit):
                    if entry.action not in action_set:
                        continue

                    if not self._audit_entry_is_fresh(entry, max_age=actual_max_age):
                        continue

                    self._store_recent_audit_entry(entry)

                    if self._audit_target_id(entry) in target_id_set:
                        return entry

            except (discord.Forbidden, discord.HTTPException):
                return None

            return None

        timeout = max(float(timeout), 0.0)
        interval = max(float(interval), 0.05)

        if timeout <= 0:
            return await check_once()

        deadline = time.monotonic() + timeout

        while True:
            entry = await check_once()
            if entry is not None:
                return entry

            if time.monotonic() >= deadline:
                return None

            await asyncio.sleep(interval)

    def _store_recent_audit_entry(self, entry: discord.AuditLogEntry) -> None:
        guild = getattr(entry, "guild", None)
        guild_id = getattr(guild, "id", None)
        entry_id = getattr(entry, "id", None)

        if guild_id is None or entry_id is None:
            return

        if not hasattr(self, "_recent_audit_entries"):
            self._recent_audit_entries = {}

        if not hasattr(self, "_recent_audit_entry_ids"):
            self._recent_audit_entry_ids = set()

        if entry_id in self._recent_audit_entry_ids:
            return

        self._recent_audit_entry_ids.add(entry_id)

        entries = self._recent_audit_entries.setdefault(guild_id, [])
        entries.insert(0, entry)

        self._prune_recent_audit_entries(guild_id)

    def _prune_recent_audit_entries(self, guild_id: int) -> None:
        if not hasattr(self, "_recent_audit_entries"):
            self._recent_audit_entries = {}

        if not hasattr(self, "_recent_audit_entry_ids"):
            self._recent_audit_entry_ids = set()

        entries = self._recent_audit_entries.get(guild_id)
        if not entries:
            return

        max_age = max(
            float(getattr(self, "AUDIT_LOG_MAX_AGE", 15)),
            float(getattr(self, "BULK_AUDIT_LOG_MAX_AGE", 20)),
            30.0,
        )

        fresh_entries: list[discord.AuditLogEntry] = []

        for entry in entries[:100]:
            entry_id = getattr(entry, "id", None)
            if entry_id is None:
                continue

            if not self._audit_entry_is_fresh(entry, max_age=max_age):
                continue

            fresh_entries.append(entry)

        self._recent_audit_entries[guild_id] = fresh_entries

        all_known_ids: set[int] = set()

        for guild_entries in self._recent_audit_entries.values():
            for entry in guild_entries:
                entry_id = getattr(entry, "id", None)
                if entry_id is not None:
                    all_known_ids.add(entry_id)

        self._recent_audit_entry_ids = all_known_ids

    def _find_cached_audit_entry_for_target(
            self,
            guild: discord.Guild,
            *,
            target_id: int,
            actions: Union[discord.AuditLogAction, Iterable[discord.AuditLogAction]],
            max_age: Optional[float] = None,
    ) -> Optional[discord.AuditLogEntry]:
        if not hasattr(self, "_recent_audit_entries"):
            self._recent_audit_entries = {}

        if not hasattr(self, "_recent_audit_entry_ids"):
            self._recent_audit_entry_ids = set()

        target_id_int = self._safe_int(target_id)
        if target_id_int is None:
            return None

        entries = self._recent_audit_entries.get(guild.id)
        if not entries:
            return None

        actual_max_age = self.AUDIT_LOG_MAX_AGE if max_age is None else max_age

        if isinstance(actions, discord.AuditLogAction):
            action_set = {actions}
        else:
            action_set = set(actions)

        self._prune_recent_audit_entries(guild.id)

        for entry in self._recent_audit_entries.get(guild.id, []):
            if entry.action not in action_set:
                continue

            if self._audit_target_id(entry) != target_id_int:
                continue

            if not self._audit_entry_is_fresh(entry, max_age=actual_max_age):
                continue

            return entry

        return None

    def _find_cached_bulk_delete_actor(
        self,
        guild: discord.Guild,
        *,
        channel_id: int,
        total_count: int,
    ) -> tuple[Optional[discord.abc.User], Optional[str]]:
        if not hasattr(self, "_recent_audit_entries"):
            self._recent_audit_entries = {}

        entries = self._recent_audit_entries.get(guild.id)
        if not entries:
            return None, None

        self._prune_recent_audit_entries(guild.id)

        best_entry: Optional[discord.AuditLogEntry] = None
        best_score = -1

        for entry in self._recent_audit_entries.get(guild.id, []):
            if entry.action != discord.AuditLogAction.message_bulk_delete:
                continue

            if not self._audit_entry_is_fresh(entry, max_age=self.BULK_AUDIT_LOG_MAX_AGE):
                continue

            extra = getattr(entry, "extra", None)
            extra_channel = getattr(extra, "channel", None)
            extra_channel_id = getattr(extra_channel, "id", None)
            extra_count = getattr(extra, "count", None)

            score = 0

            extra_channel_id_int = self._safe_int(extra_channel_id)

            if extra_channel_id_int == int(channel_id):
                score += 5
            elif extra_channel_id_int is None:
                score += 1
            else:
                continue

            if extra_count is not None:
                with contextlib.suppress(TypeError, ValueError):
                    extra_count_int = int(extra_count)

                    if extra_count_int == total_count:
                        score += 5
                    elif abs(extra_count_int - total_count) <= 3:
                        score += 2

            if score > best_score:
                best_score = score
                best_entry = entry

        if best_entry is None:
            return None, None

        return best_entry.user, best_entry.reason

    async def _find_recent_message_delete_actor(
            self,
            msg: discord.Message,
            *,
            timeout: Optional[float] = None,
    ) -> tuple[Optional[discord.abc.User], Optional[str]]:
        guild = msg.guild
        if guild is None:
            return None, None

        author_id = getattr(msg.author, "id", None)
        channel_id = getattr(msg.channel, "id", None)

        if author_id is None or channel_id is None:
            return None, None

        actual_timeout = max(float(timeout if timeout is not None else self.AUDIT_LOG_DELAY), 2.5)
        deadline = time.monotonic() + actual_timeout

        while True:
            self._prune_recent_audit_entries(guild.id)

            for entry in self._recent_audit_entries.get(guild.id, []):
                result = self._match_message_delete_entry(
                    entry,
                    author_id=int(author_id),
                    channel_id=int(channel_id),
                )
                if result is not None:
                    return result

            try:
                async for entry in guild.audit_logs(
                        limit=10,
                        action=discord.AuditLogAction.message_delete,
                ):
                    if not self._audit_entry_is_fresh(entry, max_age=self.AUDIT_LOG_MAX_AGE):
                        continue

                    self._store_recent_audit_entry(entry)

                    result = self._match_message_delete_entry(
                        entry,
                        author_id=int(author_id),
                        channel_id=int(channel_id),
                    )
                    if result is not None:
                        return result

            except (discord.Forbidden, discord.HTTPException):
                return None, None

            if time.monotonic() >= deadline:
                return None, None

            await asyncio.sleep(0.35)

    async def _find_recent_guild_audit_entry(
            self,
            guild: discord.Guild,
            *,
            action: discord.AuditLogAction,
            delay: Optional[float] = None,
    ) -> Optional[discord.AuditLogEntry]:
        timeout = self.AUDIT_LOG_DELAY if delay is None else float(delay)

        return await self._wait_for_audit_entry(
            guild,
            actions=action,
            target_ids=[guild.id],
            limit=10,
            timeout=max(timeout, 0.0),
            interval=0.35,
            max_age=self.AUDIT_LOG_MAX_AGE,
        )

    async def _find_recent_audit_entry_for_target(
            self,
            guild: discord.Guild,
            *,
            target_id: int,
            actions: Union[discord.AuditLogAction, Iterable[discord.AuditLogAction]],
            delay: Optional[float] = None,
            limit: int = 10,
            max_age: Optional[float] = None,
    ) -> Optional[discord.AuditLogEntry]:
        timeout = self.AUDIT_LOG_DELAY if delay is None else float(delay)

        return await self._wait_for_audit_entry(
            guild,
            actions=actions,
            target_ids=[target_id],
            limit=limit,
            timeout=max(timeout, 0.0),
            interval=0.35,
            max_age=max_age,
        )

    async def _find_recent_member_audit_entry(
        self,
        guild: discord.Guild,
        *,
        member_id: int,
        action: discord.AuditLogAction,
        delay: Optional[float] = None,
    ) -> Optional[discord.AuditLogEntry]:
        return await self._find_recent_audit_entry_for_target(
            guild,
            target_id=member_id,
            actions=action,
            delay=self.AUDIT_LOG_DELAY if delay is None else delay,
            limit=10,
            max_age=self.AUDIT_LOG_MAX_AGE,
        )

    async def _find_recent_member_remove_audit_entry(
        self,
        guild: discord.Guild,
        *,
        member_id: int,
    ) -> Optional[discord.AuditLogEntry]:
        actions = {
            discord.AuditLogAction.ban,
            discord.AuditLogAction.kick,
        }

        return await self._wait_for_audit_entry(
            guild,
            actions=actions,
            target_ids=[member_id],
            limit=10,
            timeout=max(float(self.MEMBER_REMOVE_AUDIT_WAIT), 2.5),
            interval=0.35,
            max_age=self.AUDIT_LOG_MAX_AGE,
        )

    async def _find_recent_thread_audit_entry(
        self,
        guild: discord.Guild,
        *,
        thread_id: int,
        action: discord.AuditLogAction,
        delay: Optional[float] = None,
    ) -> Optional[discord.AuditLogEntry]:
        return await self._find_recent_audit_entry_for_target(
            guild,
            target_id=thread_id,
            actions=action,
            delay=self.AUDIT_LOG_DELAY if delay is None else delay,
            limit=10,
            max_age=self.AUDIT_LOG_MAX_AGE,
        )

    async def _find_recent_role_audit_entry(
        self,
        guild: discord.Guild,
        *,
        role_id: int,
        action: discord.AuditLogAction,
        delay: Optional[float] = None,
    ) -> Optional[discord.AuditLogEntry]:
        return await self._find_recent_audit_entry_for_target(
            guild,
            target_id=role_id,
            actions=action,
            delay=self.AUDIT_LOG_DELAY if delay is None else delay,
            limit=10,
            max_age=self.AUDIT_LOG_MAX_AGE,
        )

    async def _find_recent_channel_audit_entry(
        self,
        guild: discord.Guild,
        *,
        channel_id: int,
        action: discord.AuditLogAction,
        delay: Optional[float] = None,
    ) -> Optional[discord.AuditLogEntry]:
        return await self._find_recent_audit_entry_for_target(
            guild,
            target_id=channel_id,
            actions=action,
            delay=self.AUDIT_LOG_DELAY if delay is None else delay,
            limit=10,
            max_age=self.AUDIT_LOG_MAX_AGE,
        )

    async def _find_recent_channel_or_overwrite_audit_entry(
        self,
        guild: discord.Guild,
        *,
        channel_id: int,
        category_id: Optional[int] = None,
    ) -> Optional[discord.AuditLogEntry]:
        actions = {
            discord.AuditLogAction.channel_update,
            discord.AuditLogAction.overwrite_create,
            discord.AuditLogAction.overwrite_update,
            discord.AuditLogAction.overwrite_delete,
        }

        target_ids: list[int] = []

        channel_id_int = self._safe_int(channel_id)
        if channel_id_int is not None:
            target_ids.append(channel_id_int)

        category_id_int = self._safe_int(category_id)
        if category_id_int is not None:
            target_ids.append(category_id_int)

        if not target_ids:
            return None

        return await self._wait_for_audit_entry(
            guild,
            actions=actions,
            target_ids=target_ids,
            limit=25,
            timeout=4.5,
            interval=0.35,
            max_age=self.AUDIT_LOG_MAX_AGE,
        )

    async def _find_recent_webhook_audit_entry(
            self,
            channel: discord.abc.GuildChannel,
    ) -> Optional[discord.AuditLogEntry]:
        guild = getattr(channel, "guild", None)
        if guild is None:
            return None

        actions = {
            getattr(discord.AuditLogAction, "webhook_create", None),
            getattr(discord.AuditLogAction, "webhook_update", None),
            getattr(discord.AuditLogAction, "webhook_delete", None),
        }
        actions.discard(None)

        if not actions:
            return None

        deadline = time.monotonic() + max(float(self.AUDIT_LOG_DELAY), 2.5)

        while True:
            self._prune_recent_audit_entries(guild.id)

            for entry in self._recent_audit_entries.get(guild.id, []):
                if self._webhook_entry_matches_channel(entry, channel):
                    return entry

            try:
                async for entry in guild.audit_logs(limit=15):
                    if entry.action not in actions:
                        continue

                    if not self._audit_entry_is_fresh(entry, max_age=self.AUDIT_LOG_MAX_AGE):
                        continue

                    self._store_recent_audit_entry(entry)

                    if self._webhook_entry_matches_channel(entry, channel):
                        return entry

            except discord.Forbidden:
                logger.warning("Missing View Audit Log permission while resolving webhook actor.")
                return None

            except discord.HTTPException as exc:
                logger.warning("Failed to fetch audit logs for webhook actor: %s", exc)
                return None

            if time.monotonic() >= deadline:
                return None

            await asyncio.sleep(0.35)

    def _webhook_entry_matches_channel(
            self,
            entry: discord.AuditLogEntry,
            channel: discord.abc.GuildChannel,
    ) -> bool:
        webhook_actions = {
            getattr(discord.AuditLogAction, "webhook_create", None),
            getattr(discord.AuditLogAction, "webhook_update", None),
            getattr(discord.AuditLogAction, "webhook_delete", None),
        }
        webhook_actions.discard(None)

        if entry.action not in webhook_actions:
            return False

        if not self._audit_entry_is_fresh(entry, max_age=self.AUDIT_LOG_MAX_AGE):
            return False

        channel_id = self._safe_int(getattr(channel, "id", None))
        if channel_id is None:
            return False

        target = getattr(entry, "target", None)
        target_channel_id = self._safe_int(getattr(target, "channel_id", None))

        extra = getattr(entry, "extra", None)
        extra_channel = getattr(extra, "channel", None)
        extra_channel_id = self._safe_int(getattr(extra_channel, "id", None))

        if target_channel_id is not None and target_channel_id != channel_id:
            return False

        if extra_channel_id is not None and extra_channel_id != channel_id:
            return False

        return True

    async def _find_bulk_delete_actor(
            self,
            guild: discord.Guild,
            *,
            channel_id: int,
            total_count: int,
            delay: Optional[float] = None,
    ) -> tuple[Optional[discord.abc.User], Optional[str]]:
        timeout = max(float(self.AUDIT_LOG_DELAY if delay is None else delay), 2.5)
        deadline = time.monotonic() + timeout

        best_entry: Optional[discord.AuditLogEntry] = None
        best_score = -1

        def score_entry(entry: discord.AuditLogEntry) -> int:
            if entry.action != discord.AuditLogAction.message_bulk_delete:
                return -1

            if not self._audit_entry_is_fresh(entry, max_age=self.BULK_AUDIT_LOG_MAX_AGE):
                return -1

            extra = getattr(entry, "extra", None)
            extra_channel = getattr(extra, "channel", None)
            extra_channel_id = getattr(extra_channel, "id", None)
            extra_count = getattr(extra, "count", None)

            score = 0

            extra_channel_id_int = self._safe_int(extra_channel_id)

            if extra_channel_id_int == int(channel_id):
                score += 5
            elif extra_channel_id_int is None:
                score += 1
            else:
                return -1
            if extra_count is not None:
                with contextlib.suppress(TypeError, ValueError):
                    extra_count_int = int(extra_count)

                    if extra_count_int == total_count:
                        score += 5
                    elif abs(extra_count_int - total_count) <= 3:
                        score += 2

            return score

        while True:
            self._prune_recent_audit_entries(guild.id)

            for entry in self._recent_audit_entries.get(guild.id, []):
                score = score_entry(entry)
                if score > best_score:
                    best_score = score
                    best_entry = entry

                if score >= 10:
                    return entry.user, entry.reason

            try:
                async for entry in guild.audit_logs(
                        limit=15,
                        action=discord.AuditLogAction.message_bulk_delete,
                ):
                    if not self._audit_entry_is_fresh(entry, max_age=self.BULK_AUDIT_LOG_MAX_AGE):
                        continue

                    self._store_recent_audit_entry(entry)

                    score = score_entry(entry)
                    if score > best_score:
                        best_score = score
                        best_entry = entry

                    if score >= 10:
                        return entry.user, entry.reason

            except (discord.Forbidden, discord.HTTPException):
                return None, None

            if best_entry is not None and best_score >= 5:
                return best_entry.user, best_entry.reason

            if time.monotonic() >= deadline:
                break

            await asyncio.sleep(0.35)

        if best_entry is None:
            return None, None

        return best_entry.user, best_entry.reason

    @staticmethod
    def _safe_attachment_filename(message_id: int, index: int, filename: Optional[str]) -> str:
        raw = str(filename or f"attachment_{index}").strip() or f"attachment_{index}"

        for bad in ("/", "\\", ":", "*", "?", '"', "<", ">", "|"):
            raw = raw.replace(bad, "_")

        if len(raw) > 80:
            raw = raw[:80]

        return f"{message_id}_{index}_{raw}"

    def _drop_cached_message_attachments(self, message_id: int) -> Optional[dict[str, Any]]:
        entry = self._message_attachment_cache.pop(message_id, None)

        if entry is not None:
            self._message_attachment_cache_bytes = max(
                0,
                self._message_attachment_cache_bytes - int(entry.get("size", 0)),
            )

        return entry

    def _prune_message_attachment_cache(self) -> None:
        now = time.monotonic()

        expired_ids = [
            message_id
            for message_id, entry in self._message_attachment_cache.items()
            if now - float(entry.get("created_at", now)) > self.NORMAL_DELETE_ATTACHMENT_CACHE_TTL
        ]

        for message_id in expired_ids:
            self._drop_cached_message_attachments(message_id)

        while (
            len(self._message_attachment_cache) > self.NORMAL_DELETE_ATTACHMENT_CACHE_MAX_MESSAGES
            or self._message_attachment_cache_bytes > self.NORMAL_DELETE_ATTACHMENT_CACHE_MAX_BYTES
        ):
            oldest_id = min(
                self._message_attachment_cache,
                key=lambda mid: float(self._message_attachment_cache[mid].get("created_at", now)),
            )
            self._drop_cached_message_attachments(oldest_id)

    async def _cache_message_attachments(self, message: discord.Message) -> None:
        if message.guild is None or not self._is_target_guild(message.guild.id):
            return

        if message.author.bot:
            return

        if not message.attachments:
            return

        self._prune_message_attachment_cache()

        files: list[dict[str, Any]] = []
        total_size = 0

        for index, attachment in enumerate(
            message.attachments[: self.NORMAL_DELETE_ATTACHMENT_MAX_FILES],
            start=1,
        ):
            attachment_size = int(getattr(attachment, "size", 0) or 0)

            if attachment_size <= 0:
                logger.debug(
                    "Skip attachment cache: message=%s file=%s reason=size<=0",
                    message.id,
                    getattr(attachment, "filename", None),
                )
                continue

            if attachment_size > self.NORMAL_DELETE_ATTACHMENT_MAX_FILE_BYTES:
                logger.info(
                    "Skip attachment cache: message=%s file=%s size=%s reason=file_too_large",
                    message.id,
                    getattr(attachment, "filename", None),
                    attachment_size,
                )
                continue

            if total_size + attachment_size > self.NORMAL_DELETE_ATTACHMENT_MAX_TOTAL_BYTES:
                logger.info(
                    "Skip attachment cache: message=%s file=%s size=%s total=%s reason=message_total_too_large",
                    message.id,
                    getattr(attachment, "filename", None),
                    attachment_size,
                    total_size,
                )
                continue

            try:
                data = await attachment.read(use_cached=True)
            except discord.HTTPException as exc:
                logger.warning(
                    "Failed attachment cache: message=%s file=%s size=%s error=%r",
                    message.id,
                    getattr(attachment, "filename", None),
                    attachment_size,
                    exc,
                )
                continue

            if not data:
                logger.warning(
                    "Empty attachment cache: message=%s file=%s size=%s",
                    message.id,
                    getattr(attachment, "filename", None),
                    attachment_size,
                )
                continue

            total_size += len(data)

            files.append(
                {
                    "filename": self._safe_attachment_filename(
                        message.id,
                        index,
                        getattr(attachment, "filename", None),
                    ),
                    "content_type": getattr(attachment, "content_type", None),
                    "data": data,
                }
            )

        if not files:
            return

        self._drop_cached_message_attachments(message.id)

        self._message_attachment_cache[message.id] = {
            "created_at": time.monotonic(),
            "size": total_size,
            "files": files,
        }
        self._message_attachment_cache_bytes += total_size

        self._prune_message_attachment_cache()

    def _consume_cached_message_attachment_files(self, message_id: int) -> list[discord.File]:
        entry = self._drop_cached_message_attachments(message_id)
        if not entry:
            return []

        files: list[discord.File] = []

        for item in entry.get("files", []):
            data = item.get("data")
            filename = item.get("filename")

            if not data or not filename:
                continue

            files.append(
                discord.File(
                    BytesIO(data),
                    filename=filename,
                )
            )

        return files

    @staticmethod
    def _reason_line(reason: Optional[str], *, limit: int = 300) -> Optional[str]:
        if reason is None:
            return None

        reason = str(reason).strip()
        if not reason:
            return None

        if len(reason) > limit:
            reason = reason[: limit - 3] + "..."

        return f"-# Reason: {reason}"

    def _moderator_footer_text(
            self,
            *,
            actor: Optional[discord.abc.User],
            reason: Optional[str],
            unknown: bool = True,
            label: str = "Moderator",
    ) -> Optional[str]:
        lines: list[str] = []

        if actor is not None:
            lines.append(f"-# **{label}:** {actor} • {actor.id}")
        elif unknown:
            lines.append(f"-# **{label}:** Unknown")

        reason_line = self._reason_line(reason)
        if reason_line:
            lines.append(reason_line)

        if not lines:
            return None

        return self._truncate("\n".join(lines), limit=350)

    async def _send_view(
        self,
        *,
        view: DesignerView,
        file: Optional[discord.File] = None,
        files: Optional[list[discord.File]] = None,
    ) -> None:
        channel = await self._get_log_channel()
        if channel is None:
            logger.info("Log channel not found.")
            return

        send_kwargs: dict[str, Any] = {
            "view": view,
            "allowed_mentions": self.allowed_mentions,
        }

        all_files: list[discord.File] = []

        if file is not None:
            all_files.append(file)

        if files:
            all_files.extend(files)

        if len(all_files) == 1:
            send_kwargs["file"] = all_files[0]
        elif len(all_files) > 1:
            send_kwargs["files"] = all_files

        try:
            await channel.send(**send_kwargs)

        except discord.Forbidden as exc:
            logger.warning("Forbidden while sending log view: %s", exc)

        except discord.HTTPException as exc:
            logger.warning("HTTPException while sending log view: %s | %s", exc.status, exc)

            if "file" in send_kwargs or "files" in send_kwargs:
                send_kwargs.pop("file", None)
                send_kwargs.pop("files", None)

                try:
                    await channel.send(**send_kwargs)
                    logger.warning("Retried log view without files after upload failure.")
                except discord.Forbidden as retry_exc:
                    logger.warning("Forbidden while retrying log view without files: %s", retry_exc)
                except discord.HTTPException as retry_exc:
                    logger.warning(
                        "Retry without files also failed: %s | %s",
                        retry_exc.status,
                        retry_exc,
                    )
                except TypeError as retry_exc:
                    logger.warning("TypeError while retrying log view without files: %s", retry_exc)

        except TypeError as exc:
            logger.warning("TypeError while sending log view: %s", exc)

    @staticmethod
    def _bulk_log_key(
            guild_id: int,
            channel_id: int,
            message_ids: Iterable[int],
    ) -> tuple[int, int, frozenset[int]]:
        return guild_id, channel_id, frozenset(
            int(mid)
            for mid in message_ids
            if mid is not None
        )

    @staticmethod
    def _create_bulk_deleted_file(
            message_ids: Iterable[int],
            msgs: Iterable[discord.Message],
            *,
            channel_id: Optional[int] = None,
    ) -> discord.File:
        ids = sorted({int(mid) for mid in message_ids})

        cached_by_id = {
            int(msg.id): msg
            for msg in msgs
            if not getattr(getattr(msg, "author", None), "bot", False)
        }

        lines: list[str] = []

        for mid in ids:
            msg = cached_by_id.get(mid)

            if msg is None:
                lines.append(
                    "\n".join(
                        [
                            f"Message ID: {mid}",
                            "Author: Unavailable (message not cached)",
                            f"Channel ID: {channel_id if channel_id is not None else 'Unknown'}",
                            "Flags: Unknown",
                            "Content: [unavailable]",
                            "Attachments:",
                            "- Unknown",
                            "Stickers:",
                            "- Unknown",
                            "-" * 72,
                        ]
                    )
                )
                continue

            created = msg.created_at.isoformat() if msg.created_at else "Unknown time"

            author = getattr(msg, "author", None)
            if author is not None:
                author_name = str(author)
                author_id = getattr(author, "id", "Unknown")
            elif getattr(msg, "webhook_id", None):
                author_name = f"Webhook ({msg.webhook_id})"
                author_id = "Webhook"
            else:
                author_name = "Unavailable (message not cached)"
                author_id = "Unknown"

            msg_channel_id = getattr(msg.channel, "id", channel_id or "Unknown")

            attachment_lines = [
                f"- {attachment.filename}: {attachment.url}"
                for attachment in getattr(msg, "attachments", [])
            ]

            sticker_lines = [
                f"- {sticker.name}: {getattr(sticker, 'url', 'No URL')}"
                for sticker in getattr(msg, "stickers", [])
            ]

            content = msg.content if msg.content else "[no text]"

            lines.append(
                "\n".join(
                    [
                        f"Time: {created}",
                        f"Author: {author_name} ({author_id})",
                        f"Channel ID: {msg_channel_id}",
                        f"Message ID: {msg.id}",
                        f"Flags: {LogsHelper._message_flags(msg)}",
                        f"Content: {content}",
                        "Attachments:",
                        *(attachment_lines if attachment_lines else ["- None"]),
                        "Stickers:",
                        *(sticker_lines if sticker_lines else ["- None"]),
                        "-" * 72,
                    ]
                )
            )

        payload = "\n".join(lines).encode("utf-8")

        return discord.File(
            BytesIO(payload),
            filename="logs.txt",
            description="Bulk deleted message export",
        )

    async def _get_fresh_member(self, member: discord.Member) -> discord.Member:
        if member.joined_at is not None:
            return member

        try:
            return await member.guild.fetch_member(member.id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return member

    def _guild_update_change_lines(self, before: discord.Guild, after: discord.Guild) -> list[str]:
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
            changes.append(f"AFK Timeout Changed {self.ARROW} `{before_afk_timeout}` → `{after_afk_timeout}`")

        before_locale = text_or_none(getattr(before, "preferred_locale", None))
        after_locale = text_or_none(getattr(after, "preferred_locale", None))

        if before_locale != after_locale:
            changes.append(f"Preferred Locale Changed {self.ARROW} `{before_locale}` → `{after_locale}`")

        channel_pairs = [
            ("AFK Channel", getattr(before, "afk_channel", None), getattr(after, "afk_channel", None)),
            ("System Channel", getattr(before, "system_channel", None), getattr(after, "system_channel", None)),
            ("Rules Channel", getattr(before, "rules_channel", None), getattr(after, "rules_channel", None)),
            (
                "Public Updates Channel",
                getattr(before, "public_updates_channel", None),
                getattr(after, "public_updates_channel", None),
            ),
        ]

        for label, before_channel, after_channel in channel_pairs:
            if before_channel is None and after_channel is not None:
                changes.append(f"{label} Added {self.ARROW} {channel_text(after_channel)}")
            elif before_channel is not None and after_channel is None:
                changes.append(f"{label} Removed {self.ARROW} {channel_text(before_channel)}")
            elif before_channel != after_channel:
                changes.append(
                    f"{label} Changed {self.ARROW} {channel_text(before_channel)} → {channel_text(after_channel)}"
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
                f"System Channel Flags Added {self.ARROW} "
                + ", ".join(f"`{flag}`" for flag in added_flags)
            )

        if removed_flags:
            changes.append(
                f"System Channel Flags Removed {self.ARROW} "
                + ", ".join(f"`{flag}`" for flag in removed_flags)
            )

        return changes

    async def _send_deleted_message_log(
        self,
        *,
        message_id: int,
        channel_id: int,
        guild_id: Optional[int],
        msg: Optional[discord.Message] = None,
    ) -> None:
        if not self._is_target_guild(guild_id):
            return

        cache_task = self._attachment_cache_tasks.get(message_id)
        if cache_task is not None and not cache_task.done():
            with contextlib.suppress(asyncio.TimeoutError, asyncio.CancelledError, discord.HTTPException):
                await asyncio.wait_for(asyncio.shield(cache_task), timeout=2.0)

        cached_files = self._consume_cached_message_attachment_files(message_id)

        if msg is not None:
            if msg.guild is None or not self._is_target_guild(msg.guild.id):
                return

            if msg.author.bot:
                return

            moderator, delete_reason = await self._find_recent_message_delete_actor(msg)

            view = self.build_deleted_message_view(
                message_id=message_id,
                channel_id=channel_id,
                msg=msg,
                cached_files=cached_files,
                moderator=moderator,
                delete_reason=delete_reason,
            )

        else:
            view = await self.build_raw_deleted_message_view(
                message_id=message_id,
                channel_id=channel_id,
                cached_files=cached_files,
            )

        await self._send_view(
            view=view,
            files=cached_files if cached_files else None,
        )

    def _store_recent_message_meta(self, message: discord.Message) -> None:
        self._recent_message_meta[int(message.id)] = {
            "created_at": time.monotonic(),
            "author_id": getattr(message.author, "id", None),
            "author_bot": bool(getattr(message.author, "bot", False)),
        }

    def _prune_recent_message_meta(self) -> None:
        if not hasattr(self, "_recent_message_meta"):
            self._recent_message_meta = {}

        now = time.monotonic()
        ttl = max(
            float(getattr(self, "NORMAL_DELETE_ATTACHMENT_CACHE_TTL", 600)),
            float(getattr(self, "RECENT_BULK_LOG_TTL", 30)),
            60.0,
        )

        expired = [
            message_id
            for message_id, meta in self._recent_message_meta.items()
            if now - float(meta.get("created_at", now)) > ttl
        ]

        for message_id in expired:
            self._recent_message_meta.pop(message_id, None)

    def _recent_message_was_bot(self, message_id: int) -> bool:
        meta = getattr(self, "_recent_message_meta", {}).get(int(message_id))
        return bool(meta and meta.get("author_bot"))

    def _match_message_delete_entry(
            self,
            entry: discord.AuditLogEntry,
            *,
            author_id: int,
            channel_id: int,
    ) -> Optional[tuple[Optional[discord.abc.User], Optional[str]]]:
        if entry.action != discord.AuditLogAction.message_delete:
            return None

        if not self._audit_entry_is_fresh(entry, max_age=self.AUDIT_LOG_MAX_AGE):
            return None

        entry_target_id = self._audit_target_id(entry)
        if entry_target_id != int(author_id):
            return None

        extra = getattr(entry, "extra", None)
        extra_channel = getattr(extra, "channel", None)
        extra_channel_id = self._safe_int(getattr(extra_channel, "id", None))

        if extra_channel_id is not None and extra_channel_id != int(channel_id):
            return None

        actor = getattr(entry, "user", None)
        if actor is None:
            return None

        if getattr(actor, "id", None) == int(author_id):
            return None, None

        return actor, getattr(entry, "reason", None)