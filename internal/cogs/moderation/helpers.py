import discord

from internal.utils.embeds import add_ansi_field, make_embed


async def ensure_manageable(
    ctx: discord.ApplicationContext,
    member: discord.Member,
    message: str,
) -> bool:
    if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
        await ctx.respond(message, ephemeral=True)
        return False
    return True


async def safe_dm(user: discord.abc.User, message: str) -> None:
    try:
        await user.send(message)
    except (discord.Forbidden, discord.HTTPException):
        pass


def action_embed(title: str, color: discord.Color, description: str | None = None) -> discord.Embed:
    return make_embed(title, color, description, timestamp=discord.utils.utcnow())


def add_member_field(
    embed: discord.Embed,
    name: str,
    member: discord.abc.User,
    color: str,
    *,
    inline: bool = False,
):
    label = getattr(member, "mention", getattr(member, "name", "Unknown"))
    add_ansi_field(embed, name, f"{label}\nID: {member.id}", color=color, inline=inline)


def forum_configured(bot) -> int | None:
    settings = getattr(bot, "settings", None)
    return None if settings is None else settings.forum_id


def lock_prefix(name: str) -> str:
    return name if name.startswith("🔒 ") else f"🔒 {name}"


def unlock_name(name: str) -> str:
    return name.removeprefix("🔒 ")
