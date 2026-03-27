import discord
import discord.gateway
from discord.ext import commands
from discord.commands import slash_command, SlashCommandGroup, Option, OptionChoice
from discord.ui import View, Button, Select
from discord.utils import format_dt
from discord import Activity, ActivityType
import os
from dotenv import load_dotenv
import datetime
from datetime import datetime, timezone, timedelta
import psutil
import platform
import time
import re
import requests
import aiohttp
import hashlib
import asyncio
import sys
import sqlite3
import random
import traceback
from io import BytesIO
import io

from discord import (
    ApplicationContext,
    ButtonStyle,
    Color,
    File,
    Interaction,
    SeparatorSpacingSize,
    User,
)
from discord.ui import (
    ActionRow,
    Button as UIButton,
    Container,
    DesignerView,
    MediaGallery,
    Section,
    Separator,
    TextDisplay,
    Thumbnail,
    button,
)

load_dotenv()

TOKEN = os.getenv("TOKEN")
OWNER = [int(user) for user in os.getenv("OWNER", "").split(",") if user.strip()]
GUILDS = [int(guild) for guild in os.getenv("GUILDS", "").split(",") if guild.strip()]
MOD_ROLE_IDS = [int(x) for x in os.getenv("MOD_ROLE_IDS", "").split(",") if x]
ADMIN_ROLE_IDS = [int(x) for x in os.getenv("ADMIN_ROLE_IDS", "").split(",") if x]
FORUM_ID = int(os.getenv("FORUM_ID"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
ERROREMOJI = os.getenv("E")
ERRORCHANNEL = os.getenv("ERRORCHANNEL")
SUPPORT_SERVER = os.getenv("SUPPORT_SERVER")

__all__ = [
    'BytesIO', 'discord', 'commands', 'slash_command', 'SlashCommandGroup',
    'Option', 'OptionChoice', 'View', 'Button', 'Select', 'format_dt',
    'Activity', 'ActivityType', 'os', 'load_dotenv', 'datetime', 'timezone',
    'timedelta', 'psutil', 'platform', 'time', 're', 'requests', 'aiohttp',
    'hashlib', 'asyncio', 'sys', 'sqlite3', 'random', 'traceback',
    'ApplicationContext', 'ButtonStyle', 'Color', 'File', 'Interaction',
    'SeparatorSpacingSize', 'User', 'ActionRow', 'UIButton', 'Container',
    'DesignerView', 'MediaGallery', 'Section', 'Separator', 'TextDisplay',
    'Thumbnail', 'button', 'io',
    'TOKEN', 'OWNER', 'GUILDS', 'MOD_ROLE_IDS', 'ADMIN_ROLE_IDS', 'FORUM_ID', 'WEBHOOK_URL', 'ERROREMOJI', 'SUPPORT_SERVER',
]
