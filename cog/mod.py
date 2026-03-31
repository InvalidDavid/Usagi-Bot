from utils.imports import *
from datetime import timezone

GUILD_IDS = GUILDS


async def check_permissions(ctx: discord.ApplicationContext):
    if GUILD_IDS and ctx.guild_id not in GUILD_IDS:
        return False, "This command can only be used in the configured server."

    user_roles = [r.id for r in ctx.author.roles]
    if not any(r in MOD_ROLE_IDS + ADMIN_ROLE_IDS for r in user_roles):
        return False, "You need Mod or Admin role to use this command."

    return True, None


async def tag_autocomplete(ctx: discord.AutocompleteContext):
    if GUILD_IDS and ctx.interaction.guild_id not in GUILD_IDS:
        return []

    user_roles = [r.id for r in ctx.interaction.user.roles]
    if not any(r in MOD_ROLE_IDS + ADMIN_ROLE_IDS for r in user_roles):
        return []

    forum_channel: discord.ForumChannel = ctx.bot.get_channel(FORUM_ID)
    if not forum_channel:
        try:
            forum_channel = await ctx.bot.fetch_channel(FORUM_ID)
        except discord.NotFound:
            return []

    all_tags = [t.name for t in forum_channel.available_tags]
    value = ctx.value.lower()
    return [t for t in all_tags if value in t.lower()][:25]


class ModC(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    mod = SlashCommandGroup("mod", "Mod commands")

    @mod.command(name="purge", description="Clear messages")
    @commands.guild_only()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def purge(self, ctx: discord.ApplicationContext, amount: int):

        await ctx.defer(ephemeral=True)

        ok, error = await check_permissions(ctx)
        if not ok:
            return await ctx.followup.send(error, ephemeral=True)

        if amount < 1 or amount > 100:
            return await ctx.followup.send(
                "Amount must be between 1 and 100.",
                ephemeral=True
            )

        channel = ctx.channel

        if not isinstance(channel, discord.TextChannel):
            return await ctx.followup.send(
                "This command can only be used in text channels.",
                ephemeral=True
            )

        if not channel.permissions_for(ctx.guild.me).manage_messages:
            return await ctx.followup.send(
                "I need `Manage Messages` permission.",
                ephemeral=True
            )

        try:
            to_delete = []

            async for msg in channel.history(limit=amount * 5):
                if len(to_delete) >= amount:
                    break

                if msg.pinned:
                    continue

                to_delete.append(msg)

            if not to_delete:
                return await ctx.followup.send(
                    "No eligible messages found to delete.",
                    ephemeral=True
                )

            await channel.delete_messages(to_delete)

            deleted = to_delete
            authors = {msg.author for msg in deleted}
            author_count = len(authors)

            if deleted:
                oldest_dt = min(deleted, key=lambda m: m.created_at).created_at.astimezone(timezone.utc)
                newest_dt = max(deleted, key=lambda m: m.created_at).created_at.astimezone(timezone.utc)

                oldest_ts = int(oldest_dt.timestamp())
                newest_ts = int(newest_dt.timestamp())
            else:
                oldest_ts = newest_ts = None

            bot_count = sum(1 for m in deleted if m.author.bot)
            user_count = len(deleted) - bot_count
            await ctx.followup.send(
                (
                    f"🧹 **Purge completed**\n"
                    f"- Deleted: `{len(deleted)}` messages\n"
                    f"- Unique authors: `{author_count}`\n"
                    f"- Users: `{user_count}` | Bots: `{bot_count}`\n"
                    f"- Time range: {f'<t:{oldest_ts}:F>' if oldest_ts else 'N/A'} → {f'<t:{newest_ts}:F>' if newest_ts else 'N/A'}\n"
                ),
                ephemeral=True,
                delete_after=10,
            )

        except discord.Forbidden:
            await ctx.followup.send(
                "Missing permissions to delete messages.",
                ephemeral=True
            )

        except discord.HTTPException as e:
            await ctx.followup.send(
                f"Failed to delete messages: {e}",
                ephemeral=True
            )

        except Exception as e:
            print(e)
            await ctx.followup.send(
                "Unexpected error occurred.",
                ephemeral=True
            )



    forum = SlashCommandGroup("forum", "Forum management commands")

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        if GUILD_IDS and thread.guild.id not in GUILD_IDS:
            return
        if not isinstance(thread, discord.Thread) or thread.parent_id != FORUM_ID:
            return
        try:
            starter_msg = await thread.fetch_message(thread.id)
            M = None
            await starter_msg.pin()
        except Exception as e:
            M = "Couldn't pin starter message, no permissions for that."
            pass

        embed = discord.Embed(
            title="Support Channel",
            description=
            """
            Rules for asking for support:
            - Provide as much details as you can about the issue. (For example a step-by-step way on how to encounter that issue)
            - Screenshots or screen recordings can help us understand the issue better, so it's recommended you send at least one in your post.
            - Check <#1488492402623905913>..
            """
            ,
            color=discord.Color.blurple()
        )
        embed.set_footer(text="You can use !close to close your post.")

        await thread.send(f"{thread.owner.mention}\n-# {M}", embed=embed)

    @forum.command(description="Change a thread's tag (2 use per post limit)")
    async def tag(
            self,
            ctx: discord.ApplicationContext,
            tag: Option(str, "Select a tag", autocomplete=tag_autocomplete)
    ):
        if not await check_permissions(ctx):
            return

        await ctx.defer(ephemeral=True)

        thread = ctx.channel
        if not isinstance(thread, discord.Thread) or not isinstance(thread.parent,
                                                                    discord.ForumChannel) or thread.parent_id != FORUM_ID:
            await ctx.respond("This command can only be used in the configured forum.", ephemeral=True)
            return

        forum_channel: discord.ForumChannel = thread.parent
        tag_obj = next((t for t in forum_channel.available_tags if t.name == tag), None)
        if not tag_obj:
            await ctx.respond("Tag not found.", ephemeral=True)
            return

        nt = re.sub(r"^\[.*?]\s*", "", thread.name)
        nt = f"[{tag_obj.name}] {nt}"

        await thread.edit(applied_tags=[tag_obj], name=nt)
        await ctx.respond(f"Thread tag set to: {tag_obj.name}", ephemeral=True)

    @forum.command(description="Close the thread (mod only)")
    async def close(self, ctx: discord.ApplicationContext):
        if not await check_permissions(ctx):
            return

        thread = ctx.channel

        if not isinstance(thread, discord.Thread) or thread.parent_id != FORUM_ID:
            await ctx.respond(
                "This command can only be used in the configured forum.", ephemeral=True
            )
            return

        await thread.send("Thread has been locked 🔒")
        await ctx.respond(f"Closing thread {thread.name}", ephemeral=True)
        await thread.edit(archived=True, locked=True, name=f"🔒 {thread.name}")

    @forum.command(description="Unlock a thread (mod only)")
    async def unlock(
            self,
            ctx: discord.ApplicationContext
    ):
        if not await check_permissions(ctx):
            return

        thread = ctx.channel
        if not isinstance(thread, discord.Thread) or thread.parent_id != FORUM_ID:
            await ctx.respond("This command can only be used in the configured forum.", ephemeral=True)
            return
        await thread.edit(archived=False, locked=False)
        await ctx.respond(f"Thread '{thread.name}' unlocked.", ephemeral=True)

    @slash_command(name="close", description="Close and archive your thread (author only)")
    async def close(self, ctx):
        if GUILD_IDS and ctx.guild.id not in GUILD_IDS:
            await ctx.reply("This command can only be used in the configured server.")
            return

        thread = ctx.channel

        if not isinstance(thread, discord.Thread) or thread.parent_id != FORUM_ID:
            await ctx.reply("This command can only be used in the configured forum.")
            return

        if ctx.author != thread.owner:
            await ctx.reply("Only the thread author can close this thread.")
            return

        await ctx.reply("Thread closed and archived by author.")
        await thread.edit(locked=True, archived=True)


def setup(bot: commands.Bot):
    bot.add_cog(ModC(bot))
