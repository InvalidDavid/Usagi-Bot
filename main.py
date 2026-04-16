from utils.imports import *
from utils.secrets import GUILDS_ID, OWNER, TOKEN

# ---------------- PATHS ----------------
UTILS_DIR = "utils"
ERROR_DIR = "error"
DATA_DIR = "Data"

for directory in (UTILS_DIR, ERROR_DIR, DATA_DIR):
    if not os.path.isdir(directory):
        os.makedirs(directory, exist_ok=True)

# ---------------- LOGGING ----------------
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
    os.path.join(ERROR_DIR, "bot.log"),
    mode="w",
    encoding="utf-8"
)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)

# create only if an actual error happens
error_filename = os.path.join(
    ERROR_DIR,
    f"crash_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
)
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
# added a monkey patch so the bot can show a mobile status.
# remove this if you do not want that behavior.
# last tested on py-cord 2.7.2
# will only be fixxed if discord patches it
original_identify = discord.gateway.DiscordWebSocket.identify


async def patched_identify(self):
    payload = {
        "op": self.IDENTIFY,
        "d": {
            "token": self.token,
            "properties": {
                "$os": "Android",
                "$browser": "Discord Android",
                "$device": "Android",
                "$referrer": "",
                "$referring_domain": ""
            },
            "compress": True,
            "large_threshold": 250,
            "v": 3
        }
    }

    if hasattr(self, "shard_id") and self.shard_id is not None:
        payload["d"]["shard"] = [self.shard_id, getattr(self, "shard_count", 1)]

    if hasattr(self, "_connection") and self._connection:
        intents = getattr(self._connection, "intents", None)
        if intents:
            payload["d"]["intents"] = intents.value

        presence = getattr(self._connection, "_presence", None)
        if presence:
            payload["d"]["presence"] = presence

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
async def on_ready() -> None:
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

    logger.info("Bot successfully started.")
    if not status_task.is_running():
        status_task.start()



@tasks.loop(seconds=60)
async def status_task() -> None:
    if not hasattr(status_task, "index"):
        status_task.index = 0

    statuses = [
        (discord.Activity(type=discord.ActivityType.custom, state="©️ made by InvalidDavid")),
        (discord.Activity(type=discord.ActivityType.custom, state="🏆 Check my profile out!")),
        (discord.Activity(type=discord.ActivityType.custom, state=f"🏓 Ping: {round(bot.latency * 1000)}ms")),
    ]

    activity = statuses[status_task.index]
    await bot.change_presence(activity=activity)

    status_task.index = (status_task.index + 1) % len(statuses)


@status_task.before_loop
async def before_status_task() -> None:
    await bot.wait_until_ready()


@bot.command(description="Force load or reload all slash commands")
@commands.is_owner()
async def sync(ctx):
    await bot.sync_commands(force=True)
    logger.info(f"{datetime.now()}: Synced from {ctx.author} ({ctx.author.id})")
    await ctx.reply("Slash commands are now synced. Wait a few seconds before using them.")


async def shutdown_bot() -> None:
    logger.info("Shutdown started.")

    # Stop custom background tasks first.
    if status_task.is_running():
        status_task.cancel()

    # Unload extensions so cog_unload() runs.
    for ext in list(bot.extensions):
        try:
            bot.unload_extension(ext)
            logger.info(f"[-] Unloaded: {ext}")
        except discord.ExtensionError:
            logger.exception(f"[!] Failed to unload: {ext}")

    # Close Discord connection last.
    await bot.close()
    logger.info("Shutdown finished.")


async def main() -> None:
    for filename in os.listdir("cog"):
        if filename.endswith(".py"):
            cog = f"cog.{filename[:-3]}"
            try:
                bot.load_extension(cog)
                logger.info(f"[+] Loaded: {cog}")
            except discord.ExtensionError:
                logger.exception(f"[!] Error {cog}")

    try:
        await bot.start(TOKEN)
    finally:
        await shutdown_bot()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by KeyboardInterrupt.")
