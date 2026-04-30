from utils.imports import *

logger = logging.getLogger("bot.logging")


class LogsMsgHelper:
    def build_member_join_view(self, member: discord.Member) -> DesignerView:
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

        return DesignerView(
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

    def build_member_remove_view(
        self,
        *,
        member: discord.Member,
        title: str,
        actor: Optional[discord.abc.User],
        reason: Optional[str],
    ) -> DesignerView:
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

        footer_text = self._moderator_footer_text(actor=actor, reason=reason, unknown=False)
        if footer_text:
            items.append(
                discord.ui.Separator(
                    divider=True,
                    spacing=discord.SeparatorSpacingSize.small,
                )
            )
            items.append(TextDisplay(footer_text))

        return DesignerView(
            Container(
                *self._flatten_items(items),
                color=self._color("member_left"),
            )
        )

    def build_member_ban_view(
        self,
        *,
        user: Union[discord.User, discord.Member],
        actor: Optional[discord.abc.User],
        reason: Optional[str],
    ) -> DesignerView:
        joined_at = getattr(user, "joined_at", None)

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

        footer_text = self._moderator_footer_text(actor=actor, reason=reason, unknown=True)

        return DesignerView(
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
                TextDisplay(footer_text or "-# **Moderator:** Unknown"),
                color=self._color("member_ban"),
            )
        )

    def build_member_unban_view(
        self,
        *,
        user: discord.User,
        actor: Optional[discord.abc.User],
        reason: Optional[str],
    ) -> DesignerView:
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

        footer_text = self._moderator_footer_text(actor=actor, reason=reason, unknown=True)

        return DesignerView(
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
                TextDisplay(footer_text or "-# **Moderator:** Unknown"),
                color=self._color("member_unban"),
            )
        )

    def build_member_update_view(
        self,
        *,
        after: discord.Member,
        changes: list[str],
        actor: Optional[discord.abc.User],
        reason: Optional[str],
    ) -> DesignerView:
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

        footer_text = self._moderator_footer_text(actor=actor, reason=reason, unknown=False)
        if footer_text:
            items.append(
                discord.ui.Separator(
                    divider=True,
                    spacing=discord.SeparatorSpacingSize.small,
                )
            )
            items.append(TextDisplay(footer_text))

        return DesignerView(
            Container(
                *self._flatten_items(items),
                color=self._color("member_update"),
            )
        )

    def build_user_update_view(
        self,
        *,
        member: discord.Member,
        after: discord.User,
        changes: list[str],
    ) -> DesignerView:
        header_text = self._truncate(
            "\n".join(
                [
                    f"User {self.ARROW} {member} • {member.mention}",
                    f"ID {self.ARROW} `{after.id}`",
                ]
            ),
            limit=800,
        )

        changes_text = self._truncate("\n".join(changes), limit=1400)

        return DesignerView(
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

    def build_voice_state_view(
        self,
        *,
        member: discord.Member,
        change: str,
    ) -> DesignerView:
        header_text = self._truncate(
            "\n".join(
                [
                    f"Member {self.ARROW} {member} • {member.mention}",
                    f"ID {self.ARROW} `{member.id}`",
                ]
            ),
            limit=800,
        )

        return DesignerView(
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

    def build_channel_create_view(
        self,
        *,
        channel: discord.abc.GuildChannel,
        actor: Optional[discord.abc.User],
        reason: Optional[str],
    ) -> DesignerView:
        channel_kind = self._channel_kind(channel)

        details = self._truncate(
            "\n".join(
                [
                    f"{channel_kind} {self.ARROW} {getattr(channel, 'name', 'Unknown')} | {self._channel_name(channel)}",
                    f"ID {self.ARROW} `{getattr(channel, 'id', 'Unknown')}`",
                    f"Type {self.ARROW} `{type(channel).__name__}`",
                ]
            ),
            limit=1500,
        )

        items: list[Any] = [
            TextDisplay(f"## {channel_kind} Created"),
            TextDisplay(details),
            discord.ui.Separator(
                divider=True,
                spacing=discord.SeparatorSpacingSize.small,
            ),
        ]

        jump_row = self._link_row(self._safe_jump_url(channel), label=f"Open {channel_kind}")
        if jump_row:
            items.append(jump_row)

        footer_text = self._moderator_footer_text(actor=actor, reason=reason, unknown=True)
        if footer_text:
            items.append(TextDisplay(footer_text))

        return DesignerView(
            Container(
                *self._flatten_items(items),
                color=self._color("channel_create"),
            )
        )

    def build_channel_delete_view(
        self,
        *,
        channel: discord.abc.GuildChannel,
        actor: Optional[discord.abc.User],
        reason: Optional[str],
    ) -> DesignerView:
        channel_kind = self._channel_kind(channel)

        details = self._truncate(
            "\n".join(
                [
                    f"Name {self.ARROW} `{getattr(channel, 'name', 'Unknown')}`",
                    f"ID {self.ARROW} `{getattr(channel, 'id', 'Unknown')}`",
                    f"Type {self.ARROW} `{type(channel).__name__}`",
                ]
            ),
            limit=1500,
        )

        footer_text = self._moderator_footer_text(actor=actor, reason=reason, unknown=True)

        return DesignerView(
            Container(
                TextDisplay(f"## {channel_kind} Deleted"),
                TextDisplay(details),
                discord.ui.Separator(
                    divider=True,
                    spacing=discord.SeparatorSpacingSize.small,
                ),
                TextDisplay(footer_text or "-# **Moderator:** Unknown"),
                color=self._color("channel_delete"),
            )
        )

    def build_channel_update_view(
        self,
        *,
        channel: discord.abc.GuildChannel,
        channel_kind: str,
        changes: list[str],
        actor: Optional[discord.abc.User],
        reason: Optional[str],
    ) -> DesignerView:
        header_text = self._truncate(
            "\n".join(
                [
                    f"{channel_kind} {self.ARROW} {getattr(channel, 'name', 'Unknown')} | {self._channel_name(channel)}",
                    f"ID {self.ARROW} `{self._channel_id(channel)}`",
                    f"Type {self.ARROW} `{type(channel).__name__}`",
                ]
            ),
            limit=800,
        )

        changes_text = self._truncate("\n".join(changes), limit=1300)

        items: list[Any] = [
            TextDisplay(f"## {channel_kind} Updated"),
            TextDisplay(header_text),
            TextDisplay(changes_text),
            discord.ui.Separator(
                divider=True,
                spacing=discord.SeparatorSpacingSize.small,
            ),
        ]

        jump_row = self._link_row(self._safe_jump_url(channel), label=f"Open {channel_kind}")
        if jump_row:
            items.append(jump_row)

        footer_text = self._moderator_footer_text(actor=actor, reason=reason, unknown=True)
        if footer_text:
            items.append(TextDisplay(footer_text))

        return DesignerView(
            Container(
                *self._flatten_items(items),
                color=self._color("channel_update"),
            )
        )

    def build_thread_create_view(
        self,
        *,
        thread: discord.Thread,
        actor: Optional[discord.abc.User],
        reason: Optional[str],
    ) -> DesignerView:
        items: list[Any] = [
            TextDisplay("## Thread Created"),
            TextDisplay(
                f"Thread {self.ARROW} {thread.name} | {thread.mention}\n"
                f"ID {self.ARROW} `{thread.id}`\n"
                f"Owner {self.ARROW} {self._thread_owner_text(thread)}\n"
            ),
        ]

        jump_row = self._link_row(self._safe_jump_url(thread), label="Open Thread")
        if jump_row:
            items.append(
                discord.ui.Separator(
                    divider=True,
                    spacing=discord.SeparatorSpacingSize.small,
                )
            )
            items.append(jump_row)

        footer_text = self._moderator_footer_text(actor=actor, reason=reason, unknown=False)
        if footer_text:
            items.append(
                discord.ui.Separator(
                    divider=True,
                    spacing=discord.SeparatorSpacingSize.small,
                )
            )
            items.append(TextDisplay(footer_text))

        return DesignerView(
            Container(
                *self._flatten_items(items),
                color=self._color("thread_create"),
            )
        )

    def build_thread_delete_view(
        self,
        *,
        thread: discord.Thread,
        actor: Optional[discord.abc.User],
        reason: Optional[str],
    ) -> DesignerView:
        body_lines = [
            f"Name {self.ARROW} `{thread.name}`",
            f"ID {self.ARROW} `{thread.id}`",
        ]

        footer_text = self._moderator_footer_text(actor=actor, reason=reason, unknown=True)

        return DesignerView(
            Container(
                TextDisplay("## Thread Deleted"),
                TextDisplay(self._truncate("\n".join(body_lines), limit=1500)),
                discord.ui.Separator(
                    divider=True,
                    spacing=discord.SeparatorSpacingSize.small,
                ),
                TextDisplay(footer_text or "-# **Moderator:** Unknown"),
                color=self._color("thread_delete"),
            )
        )

    def build_thread_update_view(
        self,
        *,
        thread: discord.Thread,
        changes: list[str],
        actor: Optional[discord.abc.User],
        reason: Optional[str],
    ) -> DesignerView:
        items: list[Any] = [
            TextDisplay("## Thread Updated"),
            TextDisplay(
                f"Thread {self.ARROW} {thread.name} | {thread.mention}\n"
                f"ID {self.ARROW} `{thread.id}`\n"
            ),
            TextDisplay(self._truncate("\n".join(changes), limit=1800)),
        ]

        jump_row = self._link_row(self._safe_jump_url(thread), label="Open Thread")
        if jump_row:
            items.append(
                discord.ui.Separator(
                    divider=True,
                    spacing=discord.SeparatorSpacingSize.small,
                )
            )
            items.append(jump_row)

        footer_text = self._moderator_footer_text(actor=actor, reason=reason, unknown=False)
        if footer_text:
            items.append(
                discord.ui.Separator(
                    divider=True,
                    spacing=discord.SeparatorSpacingSize.small,
                )
            )
            items.append(TextDisplay(footer_text))

        return DesignerView(
            Container(
                *self._flatten_items(items),
                color=self._color("thread_update"),
            )
        )

    def build_role_create_view(
        self,
        *,
        role: discord.Role,
        actor: Optional[discord.abc.User],
        reason: Optional[str],
    ) -> DesignerView:
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

        footer_text = self._moderator_footer_text(actor=actor, reason=reason, unknown=True)

        return DesignerView(
            Container(
                TextDisplay("## Role Created"),
                TextDisplay(details),
                discord.ui.Separator(
                    divider=True,
                    spacing=discord.SeparatorSpacingSize.small,
                ),
                TextDisplay(footer_text or "-# **Moderator:** Unknown"),
                color=self._color("role_create"),
            )
        )

    def build_role_delete_view(
        self,
        *,
        role: discord.Role,
        actor: Optional[discord.abc.User],
        reason: Optional[str],
    ) -> DesignerView:
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

        footer_text = self._moderator_footer_text(actor=actor, reason=reason, unknown=True)

        return DesignerView(
            Container(
                TextDisplay("## Role Deleted"),
                TextDisplay(details),
                discord.ui.Separator(
                    divider=True,
                    spacing=discord.SeparatorSpacingSize.small,
                ),
                TextDisplay(footer_text or "-# **Moderator:** Unknown"),
                color=self._color("role_delete"),
            )
        )

    def build_role_update_view(
        self,
        *,
        role: discord.Role,
        changes: list[str],
        actor: Optional[discord.abc.User],
        reason: Optional[str],
    ) -> DesignerView:
        header_text = self._truncate(
            "\n".join(
                [
                    f"Role {self.ARROW} {role.name} | {role.mention}",
                    f"ID {self.ARROW} `{role.id}`",
                ]
            ),
            limit=800,
        )

        changes_text = self._truncate("\n".join(changes), limit=1400)
        footer_text = self._moderator_footer_text(actor=actor, reason=reason, unknown=True)

        return DesignerView(
            Container(
                TextDisplay("## Role Updated"),
                TextDisplay(header_text),
                TextDisplay(changes_text),
                discord.ui.Separator(
                    divider=True,
                    spacing=discord.SeparatorSpacingSize.small,
                ),
                TextDisplay(footer_text or "-# **Moderator:** Unknown"),
                color=self._color("role_update"),
            )
        )

    def build_message_edit_view(
        self,
        *,
        msg_before: discord.Message,
        msg_after: discord.Message,
    ) -> DesignerView:
        before_attachments = [attachment.url for attachment in msg_before.attachments]
        after_attachments = [attachment.url for attachment in msg_after.attachments]

        channel_name = getattr(msg_before.channel, "name", "Unknown")

        items: list[Any] = [
            Section(
                TextDisplay("## Message Edited"),
                TextDisplay(
                    f"**Author**\n"
                    f"Name {self.ARROW} {msg_before.author} | {msg_before.author.mention}\n"
                    f"ID {self.ARROW} `{msg_before.author.id}`\n\n"
                    f"Channel {self.ARROW} {channel_name} | {self._channel_name(msg_before.channel)}\n"
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
                f"-# Created: {self._fmt_dt(msg_before.created_at, 'D')} • "
                f"Edited: {self._fmt_dt(msg_after.edited_at, 'D') if msg_after.edited_at else 'Unknown'}"
            )
        )

        return DesignerView(
            Container(
                *self._flatten_items(items),
                color=self._color("message_edit"),
            )
        )

    async def build_bulk_delete_view(
        self,
        *,
        guild_id: Optional[int],
        channel_id: int,
        total_count: int,
        file_to_send: discord.File,
        moderator: Optional[discord.abc.User],
        reason: Optional[str],
    ) -> DesignerView:
        channel_obj = await self._resolve_channel_obj(channel_id)
        channel_name = getattr(channel_obj, "name", "Unknown")
        channel_label = self._channel_name(channel_obj) if channel_obj else f"`{channel_id}`"

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

        footer_lines: list[str] = []

        if moderator is not None:
            footer_lines.append(f"-# **Moderator:** {moderator} • {moderator.id}")

        reason_line = self._reason_line(reason)
        if reason_line:
            footer_lines.append(reason_line)

        if footer_lines:
            items.append(TextDisplay(self._truncate("\n".join(footer_lines), limit=350)))

        return DesignerView(
            Container(
                *self._flatten_items(items),
                color=self._color("bulk_delete"),
            )
        )

    def build_emoji_update_view(
        self,
        *,
        before_map: dict[int, Any],
        after_map: dict[int, Any],
        created_ids: list[int],
        deleted_ids: list[int],
        updated_ids: list[int],
        actor: Optional[discord.abc.User],
        reason: Optional[str],
    ) -> DesignerView:
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
                    f"Name {self.ARROW} `{getattr(before_emoji, 'name', 'Unknown')}` → "
                    f"`{getattr(after_emoji, 'name', 'Unknown')}`"
                )

            if getattr(before_emoji, "animated", None) != getattr(after_emoji, "animated", None):
                lines.append(
                    f"Animated {self.ARROW} `{getattr(before_emoji, 'animated', False)}` → "
                    f"`{getattr(after_emoji, 'animated', False)}`"
                )

            if getattr(before_emoji, "available", None) != getattr(after_emoji, "available", None):
                lines.append(
                    f"Available {self.ARROW} `{getattr(before_emoji, 'available', False)}` → "
                    f"`{getattr(after_emoji, 'available', False)}`"
                )

            items.append(TextDisplay(self._truncate("\n".join(lines), limit=1200)))

        items.append(
            discord.ui.Separator(
                divider=True,
                spacing=discord.SeparatorSpacingSize.small,
            )
        )

        footer_text = self._moderator_footer_text(actor=actor, reason=reason, unknown=True)
        items.append(TextDisplay(footer_text or "-# **Moderator:** Unknown"))

        return DesignerView(
            Container(
                *self._flatten_items(items),
                color=self._color(color_key),
            )
        )

    def build_guild_update_view(
        self,
        *,
        changes: list[str],
        actor: Optional[discord.abc.User],
        reason: Optional[str],
    ) -> DesignerView:
        footer_text = self._moderator_footer_text(actor=actor, reason=reason, unknown=True)

        return DesignerView(
            Container(
                TextDisplay("## Server Updated"),
                TextDisplay(self._truncate("\n".join(changes), limit=1400)),
                discord.ui.Separator(
                    divider=True,
                    spacing=discord.SeparatorSpacingSize.small,
                ),
                TextDisplay(footer_text or "-# **Moderator:** Unknown"),
                color=self._color("guild_update"),
            )
        )

    def build_sticker_update_view(
        self,
        *,
        before_map: dict[int, Any],
        after_map: dict[int, Any],
        created_ids: list[int],
        deleted_ids: list[int],
        updated_ids: list[int],
        actor: Optional[discord.abc.User],
        reason: Optional[str],
    ) -> DesignerView:
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

        created_stickers = [after_map[sticker_id] for sticker_id in created_ids]
        created_gallery = self._sticker_preview_gallery(created_stickers)

        if created_gallery:
            items.append(
                discord.ui.Separator(
                    divider=True,
                    spacing=discord.SeparatorSpacingSize.small,
                )
            )
            items.append(TextDisplay("**Preview**"))
            items.append(created_gallery)

        for sticker_id in deleted_ids:
            items.append(TextDisplay(f"Deleted {self.ARROW} {self._sticker_label(before_map[sticker_id])}"))

        for sticker_id in updated_ids:
            before_sticker = before_map[sticker_id]
            after_sticker = after_map[sticker_id]

            lines = [f"Sticker {self.ARROW} `{sticker_id}`"]

            if getattr(before_sticker, "name", None) != getattr(after_sticker, "name", None):
                lines.append(
                    f"Name {self.ARROW} `{getattr(before_sticker, 'name', None)}` → "
                    f"`{getattr(after_sticker, 'name', None)}`"
                )

            if getattr(before_sticker, "description", None) != getattr(after_sticker, "description", None):
                lines.append(
                    f"Description {self.ARROW} `{getattr(before_sticker, 'description', None) or 'None'}` → "
                    f"`{getattr(after_sticker, 'description', None) or 'None'}`"
                )

            if getattr(before_sticker, "emoji", None) != getattr(after_sticker, "emoji", None):
                lines.append(
                    f"Emoji {self.ARROW} `{getattr(before_sticker, 'emoji', None)}` → "
                    f"`{getattr(after_sticker, 'emoji', None)}`"
                )

            if getattr(before_sticker, "available", None) != getattr(after_sticker, "available", None):
                lines.append(
                    f"Available {self.ARROW} `{getattr(before_sticker, 'available', None)}` → "
                    f"`{getattr(after_sticker, 'available', None)}`"
                )

            items.append(TextDisplay(self._truncate("\n".join(lines), limit=1200)))

        updated_stickers = [after_map[sticker_id] for sticker_id in updated_ids]
        updated_gallery = self._sticker_preview_gallery(updated_stickers)

        if updated_gallery:
            items.append(
                discord.ui.Separator(
                    divider=True,
                    spacing=discord.SeparatorSpacingSize.small,
                )
            )
            items.append(TextDisplay("**Current Preview**"))
            items.append(updated_gallery)

        items.append(
            discord.ui.Separator(
                divider=True,
                spacing=discord.SeparatorSpacingSize.small,
            )
        )

        footer_text = self._moderator_footer_text(actor=actor, reason=reason, unknown=True)
        items.append(TextDisplay(footer_text or "-# **Moderator:** Unknown"))

        return DesignerView(
            Container(
                *self._flatten_items(items),
                color=self._color(color_key),
            )
        )

    def build_webhook_update_view(
        self,
        *,
        channel: discord.abc.GuildChannel,
        actor: Optional[discord.abc.User],
        reason: Optional[str],
    ) -> DesignerView:
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

        items: list[Any] = [
            TextDisplay("## Webhooks Updated"),
            TextDisplay(body),
        ]

        footer_text = self._moderator_footer_text(actor=actor, reason=reason, unknown=False)
        if footer_text:
            items.append(
                discord.ui.Separator(
                    divider=True,
                    spacing=discord.SeparatorSpacingSize.small,
                )
            )
            items.append(TextDisplay(footer_text))

        return DesignerView(
            Container(
                *self._flatten_items(items),
                color=self._color("webhook_update"),
            )
        )

    def build_deleted_message_view(
        self,
        *,
        message_id: int,
        channel_id: int,
        msg: discord.Message,
        cached_files: list[discord.File],
        moderator: Optional[discord.abc.User],
        delete_reason: Optional[str],
    ) -> DesignerView:
        deleted_at = discord.utils.utcnow()
        channel_name = getattr(msg.channel, "name", "Unknown")

        items: list[Any] = [
            Section(
                TextDisplay("## Message Deleted"),
                TextDisplay(
                    f"**Author**\n"
                    f"Name {self.ARROW} {msg.author} | {msg.author.mention}\n"
                    f"ID {self.ARROW} `{msg.author.id}`\n\n"
                    f"Channel {self.ARROW} {channel_name} | {self._channel_name(msg.channel)}\n"
                ),
                accessory=discord.ui.Thumbnail(self._safe_avatar_url(msg.author)),
            )
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

        if cached_files:
            items.append(TextDisplay(self._block_text("Cached Attachments", f"`{len(cached_files)}` file(s)")))

            for cached_file in cached_files:
                items.append(discord.ui.File(f"attachment://{cached_file.filename}"))

            items.append(
                discord.ui.Separator(
                    divider=True,
                    spacing=discord.SeparatorSpacingSize.small,
                )
            )

            gallery = self._media_gallery(
                attachments=getattr(msg, "attachments", []),
                stickers=getattr(msg, "stickers", []),
            )

            if gallery is not None:
                items.append(TextDisplay("**Preview**"))
                items.append(gallery)
                items.append(
                    discord.ui.Separator(
                        divider=True,
                        spacing=discord.SeparatorSpacingSize.small,
                    )
                )

        elif msg.attachments:
            items.append(
                TextDisplay(
                    self._block_text(
                        "Attachments",
                        f"`{len(msg.attachments)}` file(s), but no local cached copy was available.",
                    )
                )
            )

            gallery = self._attachment_gallery(msg.attachments)
            if gallery:
                items.append(gallery)

            items.append(
                discord.ui.Separator(
                    divider=True,
                    spacing=discord.SeparatorSpacingSize.small,
                )
            )



        footer_lines = [
            f"-# Message ID: {message_id} • Flags: {self._message_flags(msg)}",
            f"-# Deleted: {self._fmt_dt(deleted_at, 'f')}",
        ]

        if moderator is not None:
            footer_lines.append(f"-# **Moderator:** {moderator} • {moderator.id}")

            if delete_reason:
                footer_lines.append(f"-# Reason: {delete_reason}")

        items.append(TextDisplay("\n".join(footer_lines)))

        return DesignerView(
            Container(
                *self._flatten_items(items),
                color=self._color("message_delete"),
            )
        )

    async def build_raw_deleted_message_view(
        self,
        *,
        message_id: int,
        channel_id: int,
        cached_files: list[discord.File],
    ) -> DesignerView:
        deleted_at = discord.utils.utcnow()

        channel_obj = await self._resolve_channel_obj(channel_id)
        channel_label = self._channel_name(channel_obj) if channel_obj else f"`{channel_id}`"

        items: list[Any] = [
            TextDisplay("## Message Deleted"),
            TextDisplay(
                f"Message ID {self.ARROW} `{message_id}`\n"
                f"Channel {self.ARROW} {channel_label}\n\n"
                f"-# Content unavailable because message was not cached."
            ),
        ]

        if cached_files:
            items.append(
                discord.ui.Separator(
                    divider=True,
                    spacing=discord.SeparatorSpacingSize.small,
                )
            )
            items.append(TextDisplay(self._block_text("Cached Attachments", f"`{len(cached_files)}` file(s)")))

            for cached_file in cached_files:
                items.append(discord.ui.File(f"attachment://{cached_file.filename}"))

        else:
            items.append(
                discord.ui.Separator(
                    divider=True,
                    spacing=discord.SeparatorSpacingSize.small,
                )
            )
            items.append(TextDisplay("-# No cached attachments found."))

        items.append(
            TextDisplay(
                f"-# Deleted: {self._fmt_dt(deleted_at, 'f')}"
            )
        )

        return DesignerView(
            Container(
                *self._flatten_items(items),
                color=self._color("raw_message_delete"),
            )
        )