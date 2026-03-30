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


def setup(bot: commands.Bot):
    bot.add_cog(ModC(bot))
