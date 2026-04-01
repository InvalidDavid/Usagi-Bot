import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TOKEN")
OWNER = [int(user) for user in os.getenv("OWNER", "").split(",") if user.strip()]
GUILDS_ID = [int(guild) for guild in os.getenv("GUILDS", "").split(",") if guild.strip()]
MOD_ROLE_IDS = [int(x) for x in os.getenv("MOD_ROLE_IDS", "").split(",") if x]
ADMIN_ROLE_IDS = [int(x) for x in os.getenv("ADMIN_ROLE_IDS", "").split(",") if x]
FORUM_ID = int(os.getenv("FORUM_ID"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
ERROREMOJI = os.getenv("ERROREMOJI")
SUPPORT_SERVER = os.getenv("SUPPORT_SERVER")

__all__ = [

    'TOKEN', 'OWNER', 'GUILDS_ID', 'MOD_ROLE_IDS', 'ADMIN_ROLE_IDS', 'FORUM_ID', 'WEBHOOK_URL', 'ERROREMOJI', 'SUPPORT_SERVER',

]
