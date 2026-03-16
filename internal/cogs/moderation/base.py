from __future__ import annotations

import re
from collections import defaultdict

import discord
from discord.ext import commands

from internal.services.moderation_repository import ModerationRepository

from .groups import appeal, automod, badword, forum, mod, setup_group
from .helpers import safe_dm


INVITE_PATTERN = re.compile(r"discord(?:\.gg|app\.com/invite)/[a-zA-Z0-9]+")
URL_PATTERN = re.compile(r"https?://\S+")


class ModerationBase(commands.Cog):
    mod = mod
    setup_group = setup_group
    automod = automod
    badword = badword
    appeal = appeal
    forum = forum

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = ModerationRepository()
        self.spam_tracker = defaultdict(lambda: defaultdict(list))
        bot.loop.create_task(self.db.init_db())

    async def log_action(self, guild: discord.Guild, embed: discord.Embed):
        config = await self.db.get_mod_config(guild.id)
        channel_id = None if not config else config.get("log_channel_id")
        if not channel_id:
            return
        log_channel = guild.get_channel(channel_id)
        if log_channel:
            await log_channel.send(embed=embed)

    async def should_auto_punish(self, guild_id: int, user_id: int) -> bool:
        config = await self.db.get_mod_config(guild_id)
        if not config or not config.get("auto_punish"):
            return False
        threshold = config.get("warn_threshold") or 3
        warnings = await self.db.get_warnings(guild_id, user_id)
        return len(warnings) >= threshold

    async def handle_automod_violation(self, message: discord.Message, violation_type: str):
        config = await self.db.get_automod_config(message.guild.id)
        if not config:
            return
        action_type = config.get("action_type") or "warn"
        try:
            await message.delete()
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass

        if action_type == "warn":
            case_id = await self.db.add_case(
                message.guild.id,
                message.author.id,
                self.bot.user.id,
                "automod_warn",
                f"AutoMod: {violation_type}",
            )
            await self.db.add_warning(
                message.guild.id,
                message.author.id,
                self.bot.user.id,
                f"AutoMod: {violation_type}",
                case_id,
            )
            await safe_dm(
                message.author,
                f"Hey, you've been warned on **{message.guild.name}**.\nReason: {violation_type}\nCase: #{case_id}",
            )
            return

        if action_type == "kick":
            try:
                await message.author.kick(reason=f"AutoMod: {violation_type}")
            except (discord.Forbidden, discord.HTTPException):
                pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot or message.author.guild_permissions.administrator:
            return

        config = await self.db.get_automod_config(message.guild.id)
        if not config:
            return

        if config.get("spam_enabled"):
            timestamps = self.spam_tracker[message.guild.id][message.author.id]
            current_time = discord.utils.utcnow().timestamp()
            interval = config.get("spam_interval") or 10
            threshold = config.get("spam_threshold") or 5
            timestamps.append(current_time)
            self.spam_tracker[message.guild.id][message.author.id] = [stamp for stamp in timestamps if current_time - stamp < interval]
            if len(self.spam_tracker[message.guild.id][message.author.id]) >= threshold:
                await self.handle_automod_violation(message, "Spam")
                self.spam_tracker[message.guild.id][message.author.id].clear()
                return

        if config.get("links_enabled") and URL_PATTERN.search(message.content):
            await self.handle_automod_violation(message, "Unauthorized link")
            return
        if config.get("invites_enabled") and INVITE_PATTERN.search(message.content):
            await self.handle_automod_violation(message, "Server advertisement")
            return
        if config.get("caps_enabled") and len(message.content) > 10:
            caps_count = sum(1 for char in message.content if char.isupper())
            caps_percentage = (caps_count / len(message.content)) * 100
            if caps_percentage >= (config.get("caps_percentage") or 70):
                await self.handle_automod_violation(message, "Too much caps lock")
                return

        for word in await self.db.get_badwords(message.guild.id):
            if word["word"] in message.content.lower():
                await self.handle_automod_violation(message, "Banned word used")
                return
