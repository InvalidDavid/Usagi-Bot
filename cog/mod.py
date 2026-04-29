from utils.imports import *

logger = logging.getLogger("bot.mod")

TAG_CHANGE_LIMIT = 2
TAG_CHANGE_WINDOW_SECONDS = 300
TAG_CLEANUP_INTERVAL_SECONDS = 60.0


async def tag_thread(ctx: discord.AutocompleteContext):
    channel = ctx.interaction.channel
    if not isinstance(channel, discord.Thread):
        return []

    parent = channel.parent
    if not isinstance(parent, discord.ForumChannel):
        return []

    value = (ctx.value or "").lower().strip()
    all_tags = [tag.name for tag in parent.available_tags]

    if not value:
        return all_tags[:25]

    return [tag_name for tag_name in all_tags if value in tag_name.lower()][:25]


class ModC(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._thread_tag_changes: dict[int, list[float]] = defaultdict(list)
        self._thread_tag_change_lock = asyncio.Lock()
        self._tag_cleanup_task: Optional[asyncio.Task] = None

    mod = SlashCommandGroup("mod", "Mod commands")
    forum = SlashCommandGroup("forum", "Forum management commands")

    async def cog_load(self) -> None:
        if self._tag_cleanup_task is None or self._tag_cleanup_task.done():
            self._tag_cleanup_task = asyncio.create_task(
                self._tag_cleanup_loop(),
                name="mod:thread_tag_cleanup",
            )

    def cog_unload(self) -> None:
        if self._tag_cleanup_task is not None:
            self._tag_cleanup_task.cancel()
            self._tag_cleanup_task = None

        self._thread_tag_changes.clear()

    async def _tag_cleanup_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(TAG_CLEANUP_INTERVAL_SECONDS)

                async with self._thread_tag_change_lock:
                    self._prune_tag_changes_locked(time.monotonic())

        except asyncio.CancelledError:
            return

        except Exception:
            logger.exception("Thread tag cleanup loop crashed.")

    def _prune_tag_changes_locked(self, now: float) -> None:
        window_start = now - TAG_CHANGE_WINDOW_SECONDS

        stale_thread_ids: list[int] = []

        for thread_id, entries in self._thread_tag_changes.items():
            fresh_entries = [ts for ts in entries if ts > window_start]

            if fresh_entries:
                self._thread_tag_changes[thread_id] = fresh_entries
            else:
                stale_thread_ids.append(thread_id)

        for thread_id in stale_thread_ids:
            self._thread_tag_changes.pop(thread_id, None)

    def _command_mention(self, command_name: str) -> str:
        for command in self.bot.application_commands:
            cmd_id = getattr(command, "id", None)
            cmd_name = getattr(command, "name", None)

            if cmd_name == command_name and cmd_id:
                return f"</{cmd_name}:{cmd_id}>"

        return f"/{command_name}"

    @staticmethod
    def _get_forum_thread(channel: discord.abc.GuildChannel | discord.Thread | None) -> Optional[discord.Thread]:
        if isinstance(channel, discord.Thread) and isinstance(channel.parent, discord.ForumChannel):
            return channel
        return None

    @staticmethod
    def _normalized_thread_name_without_prefix(name: str) -> str:
        return re.sub(r"^\[.*?]\s*", "", name).strip()

    @staticmethod
    def _strip_lock_prefix(name: str) -> str:
        return re.sub(r"^🔒\s*", "", name).strip()

    async def _reserve_tag_change_slot(self, thread_id: int) -> tuple[bool, float]:
        async with self._thread_tag_change_lock:
            now = time.monotonic()
            self._prune_tag_changes_locked(now)

            entries = self._thread_tag_changes.get(thread_id, [])

            if len(entries) >= TAG_CHANGE_LIMIT:
                retry_after = max(0.0, entries[0] + TAG_CHANGE_WINDOW_SECONDS - now)
                return False, retry_after

            entries.append(now)
            self._thread_tag_changes[thread_id] = entries
            return True, now

    async def _rollback_tag_change_slot(self, thread_id: int, reserved_at: float) -> None:
        async with self._thread_tag_change_lock:
            entries = self._thread_tag_changes.get(thread_id)
            if not entries:
                return

            with contextlib.suppress(ValueError):
                entries.remove(reserved_at)

            if entries:
                self._thread_tag_changes[thread_id] = entries
            else:
                self._thread_tag_changes.pop(thread_id, None)

    # If you want in a specific thread channel to have a automatic message that pins and sends a embed then u can remove the # with "strg + /" or "ctrl + /" dont forget to mark it.
    # and change in THREADID the correct channel id, else u can complelty remove it

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        if not isinstance(thread.parent, discord.ForumChannel):
            return

        if thread.parent.id != 1488486275898933288:
            return

        pin_notice = None

        me = thread.guild.me
        if me is None and self.bot.user is not None:
            me = thread.guild.get_member(self.bot.user.id)

        if me is None:
            pin_notice = "Couldn't pin starter message, could not resolve bot member."
        else:
            permissions = thread.permissions_for(me)

            can_pin = (
                getattr(permissions, "pin_messages", False)
                or getattr(permissions, "manage_messages", False)
            )

            if not can_pin:
                pin_notice = "Couldn't pin starter message, missing pin/manage messages permission."
            else:
                starter_msg = None

                for attempt in range(5):
                    try:
                        starter_msg = await thread.fetch_message(thread.id)
                        break
                    except discord.NotFound:
                        await asyncio.sleep(1 + attempt)
                    except discord.Forbidden:
                        pin_notice = "Couldn't pin starter message, missing permissions."
                        break
                    except discord.HTTPException:
                        await asyncio.sleep(1 + attempt)

                if starter_msg is None and pin_notice is None:
                    pin_notice = "Couldn't find the starter message to pin."

                if starter_msg is not None:
                    try:
                        await starter_msg.pin(
                            reason=f"Auto-pin support starter message in thread {thread.id}"
                        )
                    except discord.Forbidden:
                        pin_notice = "Couldn't pin starter message, missing permissions."
                    except discord.NotFound:
                        pin_notice = "Couldn't find the starter message to pin."
                    except discord.HTTPException as e:
                        pin_notice = f"Couldn't pin starter message due to a Discord API error: {e}"

        embed = discord.Embed(
            title="Support Channel",
            description=(
                "Rules for asking for support:\n"
                "1. - <#1484655685542350990>\n"
                "2. - <#1488492402623905913>.\n"
            ),
            color=discord.Color.red()
        )
        embed.set_footer(text="You can use /close to close your post.")

        content = f"<@{thread.owner_id}>"
        if pin_notice:
            content += f"\n-# {pin_notice}"

        for attempt in range(5):
            try:
                await thread.send(content=content, embed=embed)
                return
            except discord.Forbidden as e:
                if "40058" in str(e):
                    await asyncio.sleep(1 + attempt)
                    continue
                raise
            except discord.HTTPException:
                await asyncio.sleep(1 + attempt)

    @mod.command(name="purge", description="Clear messages")
    @commands.guild_only()
    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True, read_message_history=True)
    async def purge(
            self,
            ctx: discord.ApplicationContext,
            amount: Option(int, "Amount of messages to delete", min_value=1, max_value=100),
    ):
        await ctx.defer(ephemeral=True)

        channel = ctx.channel
        if not isinstance(channel, discord.TextChannel):
            await ctx.followup.send("This command can only be used in text channels.", ephemeral=True)
            return

        audit_reason = f"Purge by {ctx.author} ({ctx.author.id})"

        deleted = await channel.purge(
            limit=amount,
            check=lambda msg: not msg.pinned,
            bulk=True,
            reason=audit_reason,
        )

        if not deleted:
            await ctx.followup.send("No eligible messages found to delete.", ephemeral=True)
            return

        authors = {msg.author.id for msg in deleted}
        bot_count = sum(1 for msg in deleted if msg.author.bot)
        user_count = len(deleted) - bot_count

        oldest_dt = min(msg.created_at for msg in deleted).astimezone(timezone.utc)
        newest_dt = max(msg.created_at for msg in deleted).astimezone(timezone.utc)

        await ctx.followup.send(
            (
                f"🧹 **Purge completed**\n"
                f"- Deleted: `{len(deleted)}` messages\n"
                f"- Unique authors: `{len(authors)}`\n"
                f"- Users: `{user_count}` | Bots: `{bot_count}`\n"
                f"- Time range: <t:{int(oldest_dt.timestamp())}:F> → <t:{int(newest_dt.timestamp())}:F>"
            ),
            ephemeral=True,
            delete_after=10,
        )

    @forum.command(description="Change a thread's tag")
    @commands.guild_only()
    @commands.has_permissions(manage_threads=True)
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def tag(
        self,
        ctx: discord.ApplicationContext,
        tag: Option(str, "Select a tag", autocomplete=tag_thread),
    ):
        await ctx.defer(ephemeral=True)

        thread = self._get_forum_thread(ctx.channel)
        if thread is None:
            await ctx.followup.send("This command can only be used in a forum thread.", ephemeral=True)
            return

        reserved, value = await self._reserve_tag_change_slot(thread.id)
        if not reserved:
            retry_seconds = max(1, int(value) + 1)
            await ctx.followup.send(
                f"This thread already had {TAG_CHANGE_LIMIT} tag changes in the last 5 minutes. Try again in `{retry_seconds}s`.",
                ephemeral=True,
            )
            return

        forum_channel: discord.ForumChannel = thread.parent
        tag_obj = next((t for t in forum_channel.available_tags if t.name == tag), None)

        if tag_obj is None:
            await self._rollback_tag_change_slot(thread.id, value)
            await ctx.followup.send("Tag not found.", ephemeral=True)
            return

        new_name = self._normalized_thread_name_without_prefix(thread.name)
        new_name = f"[{tag_obj.name}] {new_name}"

        try:
            await thread.edit(
                applied_tags=[tag_obj],
                name=new_name,
                reason=f"Tag changed by {ctx.author} ({ctx.author.id})"
            )
            await ctx.followup.send(f"Thread tag set to: {tag_obj.name}", ephemeral=True)
        except discord.Forbidden:
            await self._rollback_tag_change_slot(thread.id, value)
            await ctx.followup.send("I don't have permission to edit this thread.", ephemeral=True)
        except discord.HTTPException:
            await self._rollback_tag_change_slot(thread.id, value)
            await ctx.followup.send("Failed to update the thread tag.", ephemeral=True)

    @forum.command(name="reminder", description="Ping the thread owner to close the thread if it's done")
    @commands.guild_only()
    @commands.has_permissions(manage_threads=True)
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def reminder(self, ctx: discord.ApplicationContext):
        await ctx.defer(ephemeral=True)

        thread = self._get_forum_thread(ctx.channel)
        if thread is None:
            await ctx.followup.send("This command can only be used in a forum thread.", ephemeral=True)
            return

        if thread.owner_id is None:
            await ctx.followup.send("This thread has no detectable owner.", ephemeral=True)
            return

        allowed_mentions = discord.AllowedMentions(everyone=False, roles=False, users=True)
        close_mention = self._command_mention("close")

        try:
            await thread.send(
                content=f"## <@{thread.owner_id}> Done with your help thread?\n> Please close your own help thread by using {close_mention}, if you dont have any questions anymore.",
                allowed_mentions=allowed_mentions,
            )
            await ctx.followup.send("Reminder sent to the thread owner.", ephemeral=True)
        except discord.Forbidden:
            await ctx.followup.send("I don't have permission to send messages in this thread.", ephemeral=True)
        except discord.HTTPException:
            await ctx.followup.send("Failed to send the reminder.", ephemeral=True)

    @forum.command(name="close", description="Close the thread")
    @commands.guild_only()
    @commands.has_permissions(manage_threads=True)
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def close_thread(self, ctx: discord.ApplicationContext):
        thread = self._get_forum_thread(ctx.channel)
        if thread is None:
            await ctx.respond("This command can only be used in a forum thread.", ephemeral=True)
            return

        new_name = self._strip_lock_prefix(thread.name)
        new_name = f"🔒 {new_name}"

        await ctx.respond(f"Closing thread `{thread.name}`", ephemeral=True)

        try:
            await thread.edit(
                archived=True,
                locked=True,
                name=new_name,
                reason=f"Thread closed by moderator {ctx.author} ({ctx.author.id})",
            )
        except discord.Forbidden:
            await ctx.respond("I don't have permission to close this thread.", ephemeral=True)
        except discord.HTTPException:
            await ctx.respond("Failed to close the thread.", ephemeral=True)

    @forum.command(name="unlock", description="Unlock a thread")
    @commands.guild_only()
    @commands.has_permissions(manage_threads=True)
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def unlock_thread(self, ctx: discord.ApplicationContext):
        thread = self._get_forum_thread(ctx.channel)
        if thread is None:
            await ctx.respond("This command can only be used in a forum thread.", ephemeral=True)
            return

        new_name = self._strip_lock_prefix(thread.name)

        try:
            await thread.edit(
                archived=False,
                locked=False,
                name=new_name,
                reason=f"Thread unlocked by moderator {ctx.author} ({ctx.author.id})",
            )
            await ctx.respond(f"Thread `{thread.name}` unlocked.", ephemeral=True)
        except discord.Forbidden:
            await ctx.respond("I don't have permission to unlock this thread.", ephemeral=True)
        except discord.HTTPException:
            await ctx.respond("Failed to unlock the thread.", ephemeral=True)

    @slash_command(name="close", description="Close and archive your thread (author only)")
    @commands.guild_only()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def close(self, ctx: discord.ApplicationContext):
        thread = self._get_forum_thread(ctx.channel)
        if thread is None:
            await ctx.respond("This command can only be used in a forum thread.", ephemeral=True)
            return

        if ctx.author.id != thread.owner_id:
            await ctx.respond("Only the thread author can close this thread.", ephemeral=True)
            return

        now_utc = datetime.now(timezone.utc)
        embed = discord.Embed(
            description=f"Author has closed the thread: `{thread.name}`",
            color=discord.Color.embed_background(),
            timestamp=now_utc,
        )

        try:
            await ctx.respond(embed=embed, ephemeral=False)
            await thread.edit(
                locked=True,
                archived=True,
                reason=f"Thread closed by author {ctx.author} ({ctx.author.id})",
            )
        except discord.Forbidden:
            await ctx.respond("I don't have permission to close this thread.", ephemeral=True)
        except discord.HTTPException:
            raise


def setup(bot: commands.Bot):
    bot.add_cog(ModC(bot))
