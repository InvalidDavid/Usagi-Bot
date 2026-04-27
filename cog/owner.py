from utils.imports import *

logger = logging.getLogger("bot.owner")

COGS_FOLDER = "cog"

# Cogs that u don't want to be shown in /cog owner list and in the autocomplete function as well cant be reloaded, unloaded etc.
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

# shows all cogs except the protected_cogs
def get_visible_cogs():
    return [c for c in get_all_cogs() if c not in PROTECTED_COGS]

# list all cogs
def module(name):
    return f"{COGS_FOLDER}.{name}"

# loaded cogs
def is_loaded(bot, name):
    return module(name) in bot.extensions

# protected cogs will not be shown
def is_protected(name):
    return name in PROTECTED_COGS

# checks for right names if you don't wait for the autocomplete
def is_valid_cog(name):
    return name in get_all_cogs()

def chunk_list(lst, size):
    return [lst[i:i + size] for i in range(0, len(lst), size)]

# reloads all cogs
async def ac_all(ctx: discord.AutocompleteContext):
    value = ctx.value.lower()
    return [
        c for c in get_visible_cogs()
        if value in c.lower()
    ]

# loading cog
async def ac_loaded(ctx: discord.AutocompleteContext):
    value = ctx.value.lower()

    return [
        c for c in get_visible_cogs()
        if is_loaded(ctx.bot, c) and value in c.lower()
    ]

# unloading cog
async def ac_unloaded(ctx: discord.AutocompleteContext):
    value = ctx.value.lower()

    return [
        c for c in get_visible_cogs()
        if not is_loaded(ctx.bot, c) and value in c.lower()
    ]


class GuildLeaveSelect(discord.ui.Select):
    def __init__(self, bot: discord.Bot, guilds: list[discord.Guild], owner_id: int, index: int):
        self.bot = bot
        self.owner_id = owner_id

        options = []
        for guild in guilds:
            member_count = guild.member_count if guild.member_count is not None else "?"
            label = guild.name[:100]
            description = f"ID: {guild.id} • Members: {member_count}"
            options.append(
                discord.SelectOption(
                    label=label,
                    description=description[:100],
                    value=str(guild.id)
                )
            )

        super().__init__(
            placeholder=f"Select a server to leave... ({index})",
            min_values=1,
            max_values=1,
            options=options,
            row=min(index - 1, 4)
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "❌ You are not allowed to use this menu.",
                ephemeral=True
            )
            return

        guild_id = int(self.values[0])
        guild = self.bot.get_guild(guild_id)

        if guild is None:
            await interaction.response.send_message(
                "❌ Guild not found. Maybe the bot already left it.",
                ephemeral=True
            )
            return

        guild_name = guild.name
        guild_member_count = guild.member_count if guild.member_count is not None else "?"

        try:
            await guild.leave()
            await interaction.response.send_message(
                f"👋 Left `{guild_name}` (`{guild_id}`) • Members: `{guild_member_count}`",
                ephemeral=True
            )
        except Exception as e:
            logger.exception("Failed to leave guild %s (%s)", guild_name, guild_id)
            await interaction.response.send_message(
                f"❌ Failed to leave `{guild_name}`\n```{e}```",
                ephemeral=True
            )


class GuildLeaveView(discord.ui.View):
    def __init__(self, bot: discord.Bot, guilds: list[discord.Guild], owner_id: int):
        super().__init__(timeout=180)
        self.owner_id = owner_id

        chunks = chunk_list(guilds, 25)
        for i, chunk in enumerate(chunks[:5], start=1):
            self.add_item(GuildLeaveSelect(bot, chunk, owner_id, i))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "❌ You are not allowed to use this menu.",
                ephemeral=True
            )
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


class OwnerC(commands.Cog):

    def __init__(self, bot: discord.Bot):
        self.bot = bot

    def _invalidate_help_cache(self) -> None:
        user_cog = self.bot.get_cog("User")
        if user_cog is not None and hasattr(user_cog, "invalidate_help_cache"):
            user_cog.invalidate_help_cache()

    owner = SlashCommandGroup("owner", "Owner commands")
    cog = owner.create_subgroup("cog", "Cog management")

    @owner.command(description="Show all servers and leave one with a dropdown menu")
    @commands.is_owner()
    async def servers(self, ctx: discord.ApplicationContext):
        guilds = sorted(self.bot.guilds, key=lambda g: g.name.lower())

        if not guilds:
            await ctx.respond("Bot is not in any servers.", ephemeral=True)
            return

        lines = []
        for i, guild in enumerate(guilds, start=1):
            member_count = guild.member_count if guild.member_count is not None else "?"
            lines.append(
                f"**{i}.** {guild.name}\n"
                f"- ID: `{guild.id}`\n"
                f"- Members: `{member_count}`"
            )

        embed = discord.Embed(
            title=f"🌍 Servers ({len(guilds)})",
            description="\n\n".join(lines[:20]),
            color=discord.Color.blurple()
        )

        if len(guilds) > 20:
            embed.set_footer(
                text=f"Showing first 20 of {len(guilds)} servers below. Use the dropdown to leave a server."
            )
        else:
            embed.set_footer(
                text="Use the dropdown below to leave a server."
            )

        view = GuildLeaveView(self.bot, guilds, ctx.author.id)
        await ctx.respond(embed=embed, view=view, ephemeral=True)

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
            self._invalidate_help_cache()
            await ctx.respond(f"✅ `{name}` loaded", ephemeral=True)
        except Exception as e:
            logger.exception("Failed to load cog %s", name)
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
            self._invalidate_help_cache()
            await ctx.respond(f"🔴 `{name}` unloaded", ephemeral=True)
        except Exception as e:
            logger.exception("Failed to unload cog %s", name)
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
            self._invalidate_help_cache()
            await ctx.respond(f"🔄 `{name}` reloaded", ephemeral=True)
        except Exception as e:
            logger.exception("Failed to reload cog %s", name)
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
                self._invalidate_help_cache()
            except Exception as e:
                logger.exception("Failed to reload cog %s during reload_all", cog)
                fail.append(f"{cog}: {e}")
        msg = "\n".join(
            [f"🔄 `{c}`" for c in ok] +
            [f"❌ {f}" for f in fail]
        )
        await ctx.followup.send(msg or "Nothing to reload.", ephemeral=True)


def setup(bot):
    bot.add_cog(OwnerC(bot))
