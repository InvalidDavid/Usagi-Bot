from utils.imports import *

GUILD_IDS = GUILDS


async def check_permissions(ctx: discord.ApplicationContext):
    if GUILD_IDS and ctx.guild_id not in GUILD_IDS:
        await ctx.respond("This command can only be used in the configured server.", ephemeral=True)
        return False

    user_roles = [r.id for r in ctx.author.roles]
    if not any(r in MOD_ROLE_IDS + ADMIN_ROLE_IDS for r in user_roles):
        await ctx.respond("You need Mod or Admin role to use this command.", ephemeral=True)
        return False

    return True


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
            - that's it for now.
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
