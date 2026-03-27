from utils.imports import *


COGS_FOLDER = "cog"

# Cogs that u dont want to be shown in /cog owner list and in the autocomplete function as well cant be reloaded, unloaded etc.
PROTECTED_COGS = {
    "errorhandler"
}


def get_all_cogs():
    if not os.path.isdir(COGS_FOLDER):
        return []

    return sorted(
        f[:-3] for f in os.listdir(COGS_FOLDER)
        if f.endswith(".py") and not f.startswith("_")
    )


def get_visible_cogs():
    return [c for c in get_all_cogs() if c not in PROTECTED_COGS]


def module(name):
    return f"{COGS_FOLDER}.{name}"


def is_loaded(bot, name):
    return module(name) in bot.extensions


def is_protected(name):
    return name in PROTECTED_COGS


def is_valid_cog(name):
    return name in get_all_cogs()


async def ac_all(ctx: discord.AutocompleteContext):
    value = ctx.value.lower()
    return [
        c for c in get_visible_cogs()
        if value in c.lower()
    ]


async def ac_loaded(ctx: discord.AutocompleteContext):
    value = ctx.value.lower()

    return [
        c for c in get_visible_cogs()
        if is_loaded(ctx.bot, c) and value in c.lower()
    ]


async def ac_unloaded(ctx: discord.AutocompleteContext):
    value = ctx.value.lower()

    return [
        c for c in get_visible_cogs()
        if not is_loaded(ctx.bot, c) and value in c.lower()
    ]


class OwnerC(commands.Cog):

    def __init__(self, bot: discord.Bot):
        self.bot = bot

    owner = SlashCommandGroup("owner", "Owner commands")
    cog = owner.create_subgroup("cog", "Cog management")

    # -----------------------------
    # Cog Manager
    # -----------------------------

    @cog.command(description="Show all manageable cogs")
    @commands.is_owner()
    async def list(self, ctx: discord.ApplicationContext):
        cogs = get_visible_cogs()
        if not cogs:
            await ctx.respond("No cogs found.", ephemeral=True)
            return
        lines = []
        for c in cogs:
            icon = "🟢" if is_loaded(self.bot, c) else "🔴"

            lines.append(f"{icon} `{c}`")
        embed = discord.Embed(
            title="⚙️ Cog Manager",
            description="\n".join(lines),
            color=discord.Color.blurple()
        )
        embed.set_footer(text="🟢 Loaded • 🔴 Unloaded")
        await ctx.respond(embed=embed, ephemeral=True)



    @cog.command(description="Load a cog")
    @commands.is_owner()
    async def load(
        self,
        ctx: discord.ApplicationContext,
        name: discord.Option(str, autocomplete=ac_unloaded)
    ):
        if not is_valid_cog(name):
            await ctx.respond("❌ Invalid cog.", ephemeral=True)
            return
        if is_protected(name):
            await ctx.respond("❌ This cog is protected.", ephemeral=True)
            return
        try:
            self.bot.load_extension(module(name))
            await ctx.respond(f"✅ `{name}` loaded", ephemeral=True)
        except Exception as e:
            traceback.print_exc()
            await ctx.respond(
                f"❌ Load failed\n```{e}```",
                ephemeral=True
            )



    @cog.command(description="Unload a cog")
    @commands.is_owner()
    async def unload(
        self,
        ctx: discord.ApplicationContext,
        name: discord.Option(str, autocomplete=ac_loaded)
    ):
        if not is_valid_cog(name):
            await ctx.respond("❌ Invalid cog.", ephemeral=True)
            return
        if is_protected(name):
            await ctx.respond("❌ This cog is protected.", ephemeral=True)
            return
        try:
            self.bot.unload_extension(module(name))
            await ctx.respond(f"🔴 `{name}` unloaded", ephemeral=True)
        except Exception as e:
            traceback.print_exc()
            await ctx.respond(
                f"❌ Unload failed\n```{e}```",
                ephemeral=True
            )



    @cog.command(description="Reload a cog")
    @commands.is_owner()
    async def reload(
        self,
        ctx: discord.ApplicationContext,
        name: discord.Option(str, autocomplete=ac_all)
    ):
        if not is_valid_cog(name):
            await ctx.respond("❌ Invalid cog.", ephemeral=True)
            return
        if is_protected(name):
            await ctx.respond("❌ This cog is protected.", ephemeral=True)
            return
        try:
            if is_loaded(self.bot, name):
                self.bot.reload_extension(module(name))
            else:
                self.bot.load_extension(module(name))
            await ctx.respond(f"🔄 `{name}` reloaded", ephemeral=True)
        except Exception as e:
            traceback.print_exc()
            await ctx.respond(
                f"❌ Reload failed\n```{e}```",
                ephemeral=True
            )



    @cog.command(description="Reload all manageable cogs")
    @commands.is_owner()
    async def reload_all(self, ctx: discord.ApplicationContext):
        await ctx.defer(ephemeral=True)

        ok = []
        fail = []

        for cog in get_visible_cogs():
            try:
                if is_loaded(self.bot, cog):
                    self.bot.reload_extension(module(cog))
                else:
                    self.bot.load_extension(module(cog))
                ok.append(cog)
            except Exception as e:
                fail.append(f"{cog}: {e}")
        msg = "\n".join(
            [f"🔄 `{c}`" for c in ok] +
            [f"❌ {f}" for f in fail]
        )
        await ctx.respond(msg or "Nothing to reload.", ephemeral=True)

    # -------------------------------------------------




def setup(bot):
    bot.add_cog(OwnerC(bot))
