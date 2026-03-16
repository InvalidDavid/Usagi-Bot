from __future__ import annotations

import traceback

import discord
from discord.commands import SlashCommandGroup
from discord.ext import commands

from internal.utils.extensions import extension_module, extension_names, is_extension_loaded


COGS_FOLDER = "cog"
PROTECTED_COGS = {"errorhandler"}


def _all_cogs() -> list[str]:
    return extension_names(COGS_FOLDER)


def _visible_cogs() -> list[str]:
    return [name for name in _all_cogs() if name not in PROTECTED_COGS]


async def _autocomplete(ctx: discord.AutocompleteContext, *, loaded: bool | None) -> list[str]:
    value = ctx.value.lower()
    results = []
    for cog_name in _visible_cogs():
        is_loaded = is_extension_loaded(ctx.bot, cog_name, COGS_FOLDER)
        if loaded is not None and is_loaded != loaded:
            continue
        if value in cog_name.lower():
            results.append(cog_name)
    return results


async def ac_all(ctx: discord.AutocompleteContext):
    return await _autocomplete(ctx, loaded=None)


async def ac_loaded(ctx: discord.AutocompleteContext):
    return await _autocomplete(ctx, loaded=True)


async def ac_unloaded(ctx: discord.AutocompleteContext):
    return await _autocomplete(ctx, loaded=False)


class OwnerCog(commands.Cog):
    owner = SlashCommandGroup("owner", "Owner commands")
    cog = owner.create_subgroup("cog", "Cog management")

    def __init__(self, bot: discord.Bot):
        self.bot = bot

    async def _run_cog_action(self, ctx: discord.ApplicationContext, name: str, action: str):
        if name not in _all_cogs():
            await ctx.respond("❌ Invalid cog.", ephemeral=True)
            return
        if name in PROTECTED_COGS:
            await ctx.respond("❌ This cog is protected.", ephemeral=True)
            return

        module_name = extension_module(name, COGS_FOLDER)
        try:
            if action == "load":
                self.bot.load_extension(module_name)
                await ctx.respond(f"✅ `{name}` loaded", ephemeral=True)
            elif action == "unload":
                self.bot.unload_extension(module_name)
                await ctx.respond(f"🔴 `{name}` unloaded", ephemeral=True)
            else:
                if is_extension_loaded(self.bot, name, COGS_FOLDER):
                    self.bot.reload_extension(module_name)
                else:
                    self.bot.load_extension(module_name)
                await ctx.respond(f"🔄 `{name}` reloaded", ephemeral=True)
        except Exception as exc:
            traceback.print_exc()
            await ctx.respond(f"❌ {action.title()} failed\n```{exc}```", ephemeral=True)

    @cog.command(description="Show all manageable cogs")
    @commands.is_owner()
    async def list(self, ctx: discord.ApplicationContext):
        cogs = _visible_cogs()
        if not cogs:
            await ctx.respond("No cogs found.", ephemeral=True)
            return
        lines = [
            f"{'🟢' if is_extension_loaded(self.bot, cog_name, COGS_FOLDER) else '🔴'} `{cog_name}`"
            for cog_name in cogs
        ]
        embed = discord.Embed(
            title="⚙️ Cog Manager",
            description="\n".join(lines),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="🟢 Loaded • 🔴 Unloaded")
        await ctx.respond(embed=embed, ephemeral=True)

    @cog.command(description="Load a cog")
    @commands.is_owner()
    async def load(self, ctx: discord.ApplicationContext, name: discord.Option(str, autocomplete=ac_unloaded)):
        await self._run_cog_action(ctx, name, "load")

    @cog.command(description="Unload a cog")
    @commands.is_owner()
    async def unload(self, ctx: discord.ApplicationContext, name: discord.Option(str, autocomplete=ac_loaded)):
        await self._run_cog_action(ctx, name, "unload")

    @cog.command(description="Reload a cog")
    @commands.is_owner()
    async def reload(self, ctx: discord.ApplicationContext, name: discord.Option(str, autocomplete=ac_all)):
        await self._run_cog_action(ctx, name, "reload")

    @cog.command(description="Reload all manageable cogs")
    @commands.is_owner()
    async def reload_all(self, ctx: discord.ApplicationContext):
        await ctx.defer(ephemeral=True)
        successes: list[str] = []
        failures: list[str] = []
        for cog_name in _visible_cogs():
            try:
                module_name = extension_module(cog_name, COGS_FOLDER)
                if is_extension_loaded(self.bot, cog_name, COGS_FOLDER):
                    self.bot.reload_extension(module_name)
                else:
                    self.bot.load_extension(module_name)
                successes.append(f"🔄 `{cog_name}`")
            except Exception as exc:
                failures.append(f"❌ {cog_name}: {exc}")
        await ctx.respond("\n".join(successes + failures) or "Nothing to reload.", ephemeral=True)


def setup(bot):
    bot.add_cog(OwnerCog(bot))
