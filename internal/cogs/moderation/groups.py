import discord
from discord.commands import SlashCommandGroup
from discord.ext import commands


mod = SlashCommandGroup(
    "mod",
    "Moderation Commands",
    default_member_permissions=discord.Permissions(moderate_members=True),
)
setup_group = mod.create_subgroup("setup", "Set up moderation system")
automod = SlashCommandGroup(
    "automod",
    "AutoMod Settings",
    default_member_permissions=discord.Permissions(administrator=True),
)
badword = SlashCommandGroup(
    "badword",
    "Word Filter",
    default_member_permissions=discord.Permissions(manage_messages=True),
)
appeal = SlashCommandGroup("appeal", "Appeal System")
forum = SlashCommandGroup("forum", "Forum management commands")


def is_mod_or_admin():
    async def predicate(ctx: discord.ApplicationContext):
        settings = getattr(ctx.bot, "settings", None)
        if settings is None:
            return False
        allowed_roles = set(settings.mod_role_ids + settings.admin_role_ids)
        return any(role.id in allowed_roles for role in getattr(ctx.author, "roles", []))

    return commands.check(predicate)
