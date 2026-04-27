from utils.imports import *

logger = logging.getLogger("bot.logging")


class LogsHelper:
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

    @classmethod
    def _codeblock(cls, text: Optional[str]) -> str:
        safe = cls._truncate(text).replace("```", "'''")
        return f"```{safe}```"

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
        items = [
            discord.MediaGalleryItem(url=attachment.url)
            for attachment in attachments
            if getattr(attachment, "url", None)
        ]
        return MediaGallery(*items) if items else None

    @staticmethod
    def _sticker_gallery(stickers: Iterable[Any]) -> Optional[MediaGallery]:
        items = [
            discord.MediaGalleryItem(url=sticker.url)
            for sticker in stickers
            if getattr(sticker, "url", None)
        ]
        return MediaGallery(*items) if items else None

    @staticmethod
    def _create_deleted_ids_file(message_ids: Iterable[int]) -> discord.File:
        payload = "\n".join(str(mid) for mid in sorted({int(mid) for mid in message_ids})).encode("utf-8")
        return discord.File(BytesIO(payload), filename="deleted_message_ids.txt")

    @classmethod
    def _block_text(cls, title: str, *lines: str) -> str:
        clean = [str(line).strip() for line in lines if line is not None and str(line).strip()]
        if not clean:
            return f"**{title}**"
        return f"**{title}**\n" + "\n".join(f"{cls.ARROW} {line}" for line in clean)

    @classmethod
    def _code_items(cls, title: str, text: Optional[str]) -> list[TextDisplay]:
        return [
            TextDisplay(f"**{title}**"),
            TextDisplay(cls._codeblock(text)),
        ]

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
    def _display_name(user: Union[discord.User, discord.Member, None]) -> str:
        if user is None:
            return "Unknown"
        return getattr(user, "display_name", str(user))

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
    def _scheduled_event_location_text(event: Any) -> str:
        location = getattr(event, "location", None)
        if location:
            return str(location)

        channel = getattr(event, "channel", None)
        if channel is not None:
            mention = getattr(channel, "mention", None)
            return mention or getattr(channel, "name", str(channel))

        return "None"

    async def _scheduled_event_creator_text(
        self,
        event: Any,
        *,
        delay: float = 1.5,
    ) -> str:
        creator = getattr(event, "creator", None)
        if creator is not None:
            mention = getattr(creator, "mention", str(creator))
            return f"{creator} | {mention}"

        guild = getattr(event, "guild", None)
        event_id = getattr(event, "id", None)

        if guild is None or event_id is None:
            return "Unknown"

        if delay > 0:
            await asyncio.sleep(delay)

        try:
            fetched = await guild.fetch_scheduled_event(event_id)
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            fetched = None

        if fetched is not None:
            creator = getattr(fetched, "creator", None)
            if creator is not None:
                mention = getattr(creator, "mention", str(creator))
                return f"{creator} | {mention}"

            creator_id = getattr(fetched, "creator_id", None)
            if creator_id is not None:
                member = guild.get_member(creator_id)
                if member is not None:
                    return f"{member} | {member.mention}"
                return f"Unknown | `{creator_id}`"

        creator_id = getattr(event, "creator_id", None)
        if creator_id is not None:
            member = guild.get_member(creator_id)
            if member is not None:
                return f"{member} | {member.mention}"
            return f"Unknown | `{creator_id}`"

        return "Unknown"

    @staticmethod
    def _guild_channel_ref(channel: Any) -> str:
        if channel is None:
            return "None"
        mention = getattr(channel, "mention", None)
        return mention or f"`{getattr(channel, 'name', getattr(channel, 'id', 'Unknown'))}`"

    @staticmethod
    def _guild_system_flags_text(flags: Any) -> str:
        if flags is None:
            return "None"

        enabled = []
        for name in dir(flags):
            if name.startswith("_"):
                continue
            value = getattr(flags, name, None)
            if isinstance(value, bool) and value:
                enabled.append(name)

        return ", ".join(f"`{name}`" for name in sorted(enabled)) if enabled else "None"

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

        added_roles = [after_roles[role_id] for role_id in sorted(after_roles.keys() - before_roles.keys())]
        removed_roles = [before_roles[role_id] for role_id in sorted(before_roles.keys() - after_roles.keys())]

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
        return getattr(target, "id", None)

    def _store_recent_audit_entry(self, entry: discord.AuditLogEntry) -> None:
        guild = getattr(entry, "guild", None)
        guild_id = getattr(guild, "id", None)
        entry_id = getattr(entry, "id", None)
        print(guild, guild_id, entry_id)

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

            if self._audit_target_id(entry) != target_id:
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

            if extra_channel_id == channel_id:
                score += 5
            elif extra_channel_id is None:
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

    async def _find_recent_guild_audit_entry(
        self,
        guild: discord.Guild,
        *,
        action: discord.AuditLogAction,
        delay: Optional[float] = None,
    ) -> Optional[discord.AuditLogEntry]:
        actual_delay = self.AUDIT_LOG_DELAY if delay is None else delay

        cached_entry = self._find_cached_audit_entry_for_target(
            guild,
            target_id=guild.id,
            actions=action,
            max_age=self.AUDIT_LOG_MAX_AGE,
        )
        if cached_entry is not None:
            return cached_entry

        try:
            if actual_delay > 0:
                await asyncio.sleep(actual_delay)

            cached_entry = self._find_cached_audit_entry_for_target(
                guild,
                target_id=guild.id,
                actions=action,
                max_age=self.AUDIT_LOG_MAX_AGE,
            )
            if cached_entry is not None:
                return cached_entry

            async for entry in guild.audit_logs(limit=10, action=action):
                if self._audit_target_id(entry) != guild.id:
                    continue
                if not self._audit_entry_is_fresh(entry, max_age=self.AUDIT_LOG_MAX_AGE):
                    continue

                self._store_recent_audit_entry(entry)
                return entry

        except (discord.Forbidden, discord.HTTPException):
            return None

        return None

    async def _find_recent_scheduled_event_audit_entry(
        self,
        guild: discord.Guild,
        *,
        event_id: int,
        action: discord.AuditLogAction,
        delay: Optional[float] = None,
    ) -> Optional[discord.AuditLogEntry]:
        actual_delay = self.AUDIT_LOG_DELAY if delay is None else delay
        return await self._find_recent_audit_entry_for_target(
            guild,
            target_id=event_id,
            actions=action,
            delay=actual_delay,
            limit=10,
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
        actual_delay = self.AUDIT_LOG_DELAY if delay is None else delay
        actual_max_age = self.AUDIT_LOG_MAX_AGE if max_age is None else max_age

        cached_entry = self._find_cached_audit_entry_for_target(
            guild,
            target_id=target_id,
            actions=actions,
            max_age=actual_max_age,
        )
        if cached_entry is not None:
            return cached_entry

        try:
            if actual_delay > 0:
                await asyncio.sleep(actual_delay)

            cached_entry = self._find_cached_audit_entry_for_target(
                guild,
                target_id=target_id,
                actions=actions,
                max_age=actual_max_age,
            )
            if cached_entry is not None:
                return cached_entry

            if isinstance(actions, discord.AuditLogAction):
                async for entry in guild.audit_logs(limit=limit, action=actions):
                    if self._audit_target_id(entry) != target_id:
                        continue
                    if not self._audit_entry_is_fresh(entry, max_age=actual_max_age):
                        continue

                    self._store_recent_audit_entry(entry)
                    return entry

                return None

            action_set = set(actions)
            async for entry in guild.audit_logs(limit=limit):
                if entry.action not in action_set:
                    continue
                if self._audit_target_id(entry) != target_id:
                    continue
                if not self._audit_entry_is_fresh(entry, max_age=actual_max_age):
                    continue

                self._store_recent_audit_entry(entry)
                return entry

        except (discord.Forbidden, discord.HTTPException):
            return None

        return None

    async def _find_recent_member_audit_entry(
        self,
        guild: discord.Guild,
        *,
        member_id: int,
        action: discord.AuditLogAction,
        delay: Optional[float] = None,
    ) -> Optional[discord.AuditLogEntry]:
        actual_delay = self.AUDIT_LOG_DELAY if delay is None else delay
        return await self._find_recent_audit_entry_for_target(
            guild,
            target_id=member_id,
            actions=action,
            delay=actual_delay,
            limit=10,
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
        actual_delay = self.AUDIT_LOG_DELAY if delay is None else delay
        return await self._find_recent_audit_entry_for_target(
            guild,
            target_id=thread_id,
            actions=action,
            delay=actual_delay,
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
        actual_delay = self.AUDIT_LOG_DELAY if delay is None else delay
        return await self._find_recent_audit_entry_for_target(
            guild,
            target_id=role_id,
            actions=action,
            delay=actual_delay,
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
        actual_delay = self.AUDIT_LOG_DELAY if delay is None else delay
        return await self._find_recent_audit_entry_for_target(
            guild,
            target_id=channel_id,
            actions=action,
            delay=actual_delay,
            limit=10,
            max_age=self.AUDIT_LOG_MAX_AGE,
        )

    async def _find_recent_channel_or_overwrite_audit_entry(
        self,
        guild: discord.Guild,
        *,
        channel_id: int,
        delay: Optional[float] = None,
    ) -> Optional[discord.AuditLogEntry]:
        actual_delay = self.AUDIT_LOG_DELAY if delay is None else delay
        return await self._find_recent_audit_entry_for_target(
            guild,
            target_id=channel_id,
            actions={
                discord.AuditLogAction.channel_update,
                discord.AuditLogAction.overwrite_create,
                discord.AuditLogAction.overwrite_update,
                discord.AuditLogAction.overwrite_delete,
            },
            delay=actual_delay,
            limit=12,
            max_age=self.AUDIT_LOG_MAX_AGE,
        )

    async def _find_bulk_delete_actor(
            self,
            guild: discord.Guild,
            *,
            channel_id: int,
            total_count: int,
            delay: Optional[float] = None,
    ) -> tuple[Optional[discord.abc.User], Optional[str]]:
        actual_delay = self.AUDIT_LOG_DELAY if delay is None else delay

        if actual_delay > 0:
            await asyncio.sleep(actual_delay)

        deadline = time.monotonic() + 8.0
        best_entry: Optional[discord.AuditLogEntry] = None
        best_score = -1

        while True:
            cached = self._find_cached_bulk_delete_actor(
                guild,
                channel_id=channel_id,
                total_count=total_count,
            )
            if cached != (None, None):
                return cached

            try:
                async for entry in guild.audit_logs(
                        limit=15,
                        action=discord.AuditLogAction.message_bulk_delete,
                ):
                    if not self._audit_entry_is_fresh(entry, max_age=self.BULK_AUDIT_LOG_MAX_AGE):
                        continue

                    self._store_recent_audit_entry(entry)

                    extra = getattr(entry, "extra", None)
                    extra_channel = getattr(extra, "channel", None)
                    extra_channel_id = getattr(extra_channel, "id", None)
                    extra_count = getattr(extra, "count", None)

                    score = 0

                    if extra_channel_id == channel_id:
                        score += 5
                    elif extra_channel_id is None:
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

                    if score >= 10:
                        return entry.user, entry.reason

            except (discord.Forbidden, discord.HTTPException):
                return None, None

            if best_entry is not None and best_score >= 5:
                return best_entry.user, best_entry.reason

            if time.monotonic() >= deadline:
                break

            await asyncio.sleep(1.0)

        if best_entry is None:
            return None, None

        return best_entry.user, best_entry.reason

    async def _send_view(
        self,
        *,
        view: DesignerView,
        file: Optional[discord.File] = None,
    ) -> None:
        channel = await self._get_log_channel()
        if channel is None:
            logger.info("Log channel not found.")
            return

        send_kwargs: dict[str, Any] = {
            "view": view,
            "allowed_mentions": self.allowed_mentions,
        }

        if file is not None:
            send_kwargs["file"] = file

        try:
            await channel.send(**send_kwargs)
        except discord.Forbidden as exc:
            logger.warning("Forbidden while sending log view: %s", exc)
        except discord.HTTPException as exc:
            logger.warning("HTTPException while sending log view: %s | %s", exc.status, exc)
        except TypeError as exc:
            logger.warning("TypeError while sending log view: %s", exc)

    @staticmethod
    def _bulk_log_key(guild_id: int, channel_id: int, message_ids: Iterable[int]) -> tuple[int, int, frozenset[int]]:
        return guild_id, channel_id, frozenset(int(mid) for mid in message_ids)

    @staticmethod
    def _create_bulk_deleted_file(
        message_ids: Iterable[int],
        msgs: Iterable[discord.Message],
    ) -> discord.File:
        ids = sorted({int(mid) for mid in message_ids})
        cached_by_id = {int(msg.id): msg for msg in msgs}

        lines: list[str] = []

        for mid in ids:
            msg = cached_by_id.get(mid)

            if msg is None:
                lines.append(
                    "\n".join(
                        [
                            f"Message ID: {mid}",
                            "Author: Unavailable (message not cached)",
                            "Channel ID: Unknown",
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

            channel_id = getattr(msg.channel, "id", "Unknown")

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
                        f"Channel ID: {channel_id}",
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

    async def _get_fresh_member(self, member: discord.Member, delay: float = 1.5) -> discord.Member:
        # mention is already fine, so only refresh if you need fresher member data
        if member.joined_at is not None:
            return member

        await asyncio.sleep(delay)

        try:
            return await member.guild.fetch_member(member.id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return member
