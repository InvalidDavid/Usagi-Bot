import re

import discord
from discord.commands import Option
from discord.ext import commands

from .groups import forum, is_mod_or_admin
from .helpers import forum_configured, lock_prefix, unlock_name


async def tag_autocomplete(ctx: discord.AutocompleteContext) -> list[str]:
    forum_id = forum_configured(ctx.bot)
    settings = getattr(ctx.bot, "settings", None)
    if not forum_id or settings is None:
        return []

    allowed_roles = set(settings.mod_role_ids + settings.admin_role_ids)
    if not any(role.id in allowed_roles for role in getattr(ctx.interaction.user, "roles", [])):
        return []

    forum_channel = ctx.bot.get_channel(forum_id)
    if forum_channel is None:
        try:
            forum_channel = await ctx.bot.fetch_channel(forum_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return []
    if not isinstance(forum_channel, discord.ForumChannel):
        return []
    value = ctx.value.lower()
    return [tag.name for tag in forum_channel.available_tags if value in tag.name.lower()][:25]


class ForumCommands:
    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        forum_id = forum_configured(self.bot)
        if not forum_id or thread.parent_id != forum_id:
            return
        try:
            starter_message = await thread.fetch_message(thread.id)
            await starter_message.pin()
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass

        embed = discord.Embed(
            title="Support Channel",
            description=(
                "**Remember:**\n"
                "- If you are on the **latest version** of the App\n"
                "- Provide as much detail as you can about the issue.\n"
                "- Screenshots or screen recordings can help us understand the issue better."
            ),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="You can use !close to close your post.")
        mention = thread.owner.mention if thread.owner else ""
        await thread.send(mention, embed=embed)

    @forum.command(description="Change a thread's tag (2 use per post limit)")
    @is_mod_or_admin()
    async def change(self, ctx: discord.ApplicationContext, tag: Option(str, "Select a tag", autocomplete=tag_autocomplete)):
        await ctx.defer(ephemeral=True)
        forum_id = forum_configured(self.bot)
        thread = ctx.channel
        if not forum_id or not isinstance(thread, discord.Thread) or thread.parent_id != forum_id:
            await ctx.respond("This command can only be used in the configured forum.", ephemeral=True)
            return

        forum_channel = thread.parent
        tag_obj = next((item for item in forum_channel.available_tags if item.name == tag), None)
        if not tag_obj:
            await ctx.respond("Tag not found.", ephemeral=True)
            return

        updated_name = re.sub(r"^\[.*?]\s*", "", thread.name)
        await thread.edit(applied_tags=[tag_obj], name=f"[{tag_obj.name}] {updated_name}")
        await ctx.respond(f"Thread tag set to: {tag_obj.name}", ephemeral=True)

    @forum.command(name="close", description="Close the thread (mod only)")
    @is_mod_or_admin()
    async def close_thread(self, ctx: discord.ApplicationContext):
        forum_id = forum_configured(self.bot)
        thread = ctx.channel
        if not forum_id or not isinstance(thread, discord.Thread) or thread.parent_id != forum_id:
            await ctx.respond("This command can only be used in the configured forum.", ephemeral=True)
            return
        await thread.send("Thread has been locked 🔒")
        await ctx.respond(f"Closing thread {thread.name}", ephemeral=True)
        await thread.edit(archived=True, locked=True, name=lock_prefix(thread.name))

    @forum.command(description="Unlock a thread (mod only)")
    @is_mod_or_admin()
    async def unlock(self, ctx: discord.ApplicationContext):
        forum_id = forum_configured(self.bot)
        thread = ctx.channel
        if not forum_id or not isinstance(thread, discord.Thread) or thread.parent_id != forum_id:
            await ctx.respond("This command can only be used in the configured forum.", ephemeral=True)
            return
        await thread.edit(archived=False, locked=False, name=unlock_name(thread.name))
        await ctx.respond(f"Thread '{thread.name}' unlocked.", ephemeral=True)

    @commands.command(name="close", description="Close and archive your thread (author only)")
    async def close_own_thread(self, ctx):
        forum_id = forum_configured(self.bot)
        thread = ctx.channel
        if not forum_id or not isinstance(thread, discord.Thread) or thread.parent_id != forum_id:
            await ctx.reply("This command can only be used in the configured forum.")
            return
        if ctx.author != thread.owner:
            await ctx.reply("Only the thread author can close this thread.")
            return
        await ctx.reply("Thread closed and archived by author.")
        await thread.edit(locked=True, archived=True, name=lock_prefix(thread.name))
