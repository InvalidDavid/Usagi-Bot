from utils.imports import *
from utils.secrets import GUILDS_ID, OWNER, TOKEN

# ---------------- LOGGING ----------------
os.makedirs("utils/error", exist_ok=True)

logger = logging.getLogger("bot")
logger.setLevel(logging.INFO)
logger.propagate = False

formatter = logging.Formatter(
    "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)

# reset every restart
file_handler = logging.FileHandler(
    "utils/error/bot.log",
    mode="w",
    encoding="utf-8"
)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)

# create only if an actual error happens
error_filename = f"utils/error/crash_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
error_handler = logging.FileHandler(
    error_filename,
    mode="w",
    encoding="utf-8",
    delay=True
)
error_handler.setLevel(logging.ERROR)
error_handler.setFormatter(formatter)

if not logger.handlers:
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    logger.addHandler(error_handler)

discord_logger = logging.getLogger("discord")
discord_logger.setLevel(logging.INFO)
discord_logger.propagate = False

if not discord_logger.handlers:
    discord_logger.addHandler(console_handler)
    discord_logger.addHandler(file_handler)
    discord_logger.addHandler(error_handler)
# -----------------------------------------


# ---------------- MOBILE STATUS ----------------
#  added a monkey patching, so I can get the mobile status on the bot
# if you don't want that you can remove the function from marking
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


bot = commands.Bot(
    intents=discord.Intents.all(),
    debug_guilds=GUILDS_ID,
    sync_commands=True,
    owner_ids=OWNER,
    command_prefix="=",
    help_command=None,
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
    logger.info(f"╔{'═' * (width + 2)}╗")
    for line in infos:
        logger.info(f"║ {line:<{width}} ║")

    logger.info(f"╚{'═' * (width + 2)}╝\n")

    a1 = Activity(
        type=ActivityType.custom,
        state="sth new? check bio"
    )
    # custom activity instead of saying "playing ..." it just says the text directly like a satus
    a2 = discord.Game(name=f"{users:,} users")
    await bot.change_presence(
        status=discord.Status.online,
        activity=a1
    )

    logger.info("Bot successfully started.")


@bot.command(description="Force to load or reload all Slash commands")
@commands.is_owner()
async def sync(ctx):
    await bot.sync_commands(force=True)
    logger.info(f"{datetime.now()}: Synced from {ctx.author} ({ctx.author.id})")
    await ctx.reply("Slash-Commands are now synced, wait for a couple seconds before using a Slash Command!")


if __name__ == "__main__":
    for filename in os.listdir("cog"):
        if filename.endswith(".py"):
            cog = f"cog.{filename[:-3]}"
            try:
                bot.load_extension(cog)
                logger.info(f"[+] Loaded: {cog}")
            except Exception:
                logger.exception(f"[!] Error {cog}")

    bot.run(TOKEN)
