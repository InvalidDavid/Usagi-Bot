import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import datetime
import discord.gateway
from discord import Activity, ActivityType

# ---------------- MOBILE STATUS ----------------
#  added a monkey patching so i can get the mobile status on the bot
# if you dont want that you can remove the function from marking
original_identify = discord.gateway.DiscordWebSocket.identify

async def patched_identify(self):
    payload = {
        'op': self.IDENTIFY,
        'd': {
            'token': self.token,
            'properties': {
                '$os': 'Android',
                '$browser': 'Discord Android',
                '$device': 'Android',
                '$referrer': '',
                '$referring_domain': ''
            },
            'compress': True,
            'large_threshold': 250,
            'v': 3
        }
    }

    if hasattr(self, 'shard_id') and self.shard_id is not None:
        payload['d']['shard'] = [self.shard_id, getattr(self, 'shard_count', 1)]

    if hasattr(self, '_connection') and self._connection:
        intents = getattr(self._connection, 'intents', None)
        if intents:
            payload['d']['intents'] = intents.value

        presence = getattr(self._connection, '_presence', None)
        if presence:
            payload['d']['presence'] = presence

    await self.send_as_json(payload)

discord.gateway.DiscordWebSocket.identify = patched_identify

# ---------------------------------------

load_dotenv()

bot = commands.Bot(
    intents=discord.Intents.all(),
    debug_guilds=[int(guild) for guild in os.getenv("GUILDS", "").split(",") if guild.strip()],
    sync_commands=True,
    owner_ids=[int(user) for user in os.getenv("OWNER", "").split(",") if user.strip()],
    command_prefix="!",
    help_command=None
)


@bot.event
async def on_ready():
    guilds = len(bot.guilds)
    users = sum(
        1 for g in bot.guilds
        for m in g.members
        if not m.bot
    )
    bots = sum(
        1 for g in bot.guilds
        for m in g.members
        if m.bot
    )
    ping = round(bot.latency * 1000)
    slash_commands = len(bot.application_commands)
    prefix_commands = len(bot.commands)

    infos = [
        f"Framework      : Pycord {discord.__version__}",
        f"Ping           : {ping} ms",
        f"Guilds         : {guilds}",
        f"Users          : {users:,}",
        f"Bots           : {bots:,}",
        f"Slash Commands : {slash_commands}",
        f"Prefix Commands: {prefix_commands}",
    ]

    width = max(len(i) for i in infos)
    print(f"╔{'═' * (width + 2)}╗")
    for line in infos:
        print(f"║ {line:<{width}} ║")

    print(f"╚{'═' * (width + 2)}╝\n")

    a1 = Activity(
        type=ActivityType.custom,
        state="we support Yumi"
    )   # custom activity instead of saying "playing ..." it just say the text directly like a satus
    a2 = discord.Game(name=f"{users:,} users")
    await bot.change_presence(
        status=discord.Status.online,
        activity=a1
    )

    print("\nBot successfully started.")


@bot.command(description="Force to load or reload all Slash commands")
@commands.is_owner()
async def sync(ctx):
    await bot.sync_commands(force=True)
    print(f"{datetime.datetime.now()}: Synced from {ctx.author} ({ctx.author.id})")
    await ctx.reply("Slash-Commands are now synced, wait for a couple seconds before using a Slash Command!",
                    ephemeral=True)


if __name__ == "__main__":
    for filename in os.listdir("cog"):
        if filename.endswith(".py"):
            cog = f"cog.{filename[:-3]}"
            try:
                bot.load_extension(cog)
                print(f"[+] Loaded: {cog}")
            except Exception as e:
                print(f"[!] Error {cog}: {e}")

    bot.run(os.getenv("TOKEN"))
