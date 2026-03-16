import discord
from discord.ext import commands
from discord.commands import SlashCommandGroup, Option

# ---------------- Mod ----------------

from discord.ui import View, Button, Select, Modal, InputText
from datetime import datetime, timedelta, timezone
import aiosqlite
from collections import defaultdict
from typing import List

DB_PATH = "Data/moderation.db"

ansi_blue = "\u001b[2;34m"
ansi_red = "\u001b[2;31m"
ansi_green = "\u001b[2;32m"
ansi_yellow = "\u001b[2;33m"
ansi_reset = "\u001b[0m"


class ModerationDatabase:
    def __init__(self):
        self.db_path = DB_PATH

    async def init_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''CREATE TABLE IF NOT EXISTS cases (
                case_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                action_type TEXT NOT NULL,
                reason TEXT,
                timestamp INTEGER NOT NULL,
                duration INTEGER,
                active INTEGER DEFAULT 1,
                message_id INTEGER
            )''')

            await db.execute('''CREATE TABLE IF NOT EXISTS warnings (
                warning_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                reason TEXT,
                timestamp INTEGER NOT NULL,
                case_id INTEGER
            )''')

            await db.execute('''CREATE TABLE IF NOT EXISTS automod_config (
                guild_id INTEGER PRIMARY KEY,
                spam_enabled INTEGER DEFAULT 0,
                links_enabled INTEGER DEFAULT 0,
                invites_enabled INTEGER DEFAULT 0,
                caps_enabled INTEGER DEFAULT 0,
                spam_threshold INTEGER DEFAULT 5,
                spam_interval INTEGER DEFAULT 10,
                caps_percentage INTEGER DEFAULT 70,
                action_type TEXT DEFAULT 'warn',
                log_channel_id INTEGER
            )''')

            await db.execute('''CREATE TABLE IF NOT EXISTS mod_config (
                guild_id INTEGER PRIMARY KEY,
                log_channel_id INTEGER,
                auto_punish INTEGER DEFAULT 1,
                warn_threshold INTEGER DEFAULT 3,
                quarantine_role_id INTEGER
            )''')

            await db.execute('''CREATE TABLE IF NOT EXISTS badwords (
                word_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                word TEXT NOT NULL,
                severity INTEGER DEFAULT 1
            )''')

            await db.execute('''CREATE TABLE IF NOT EXISTS appeals (
                appeal_id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                reason TEXT,
                timestamp INTEGER NOT NULL,
                status TEXT DEFAULT 'pending',
                reviewed_by INTEGER,
                review_note TEXT
            )''')

            await db.commit()

    async def add_case(self, guild_id: int, user_id: int, moderator_id: int,
                       action_type: str, reason: str = None, duration: int = None,
                       message_id: int = None):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                '''INSERT INTO cases (guild_id, user_id, moderator_id, action_type, 
                   reason, timestamp, duration, message_id) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                (guild_id, user_id, moderator_id, action_type, reason or "No reason provided",
                 int(datetime.now(timezone.utc).timestamp()), duration, message_id)
            )
            await db.commit()
            return cursor.lastrowid

    async def get_cases(self, guild_id: int, user_id: int = None, active_only: bool = False):
        async with aiosqlite.connect(self.db_path) as db:
            if user_id:
                query = 'SELECT * FROM cases WHERE guild_id = ? AND user_id = ?'
                params = (guild_id, user_id)
            else:
                query = 'SELECT * FROM cases WHERE guild_id = ?'
                params = (guild_id,)

            if active_only:
                query += ' AND active = 1'

            query += ' ORDER BY case_id DESC'

            async with db.execute(query, params) as cursor:
                return await cursor.fetchall()

    async def get_case_by_id(self, case_id: int, guild_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                    'SELECT * FROM cases WHERE case_id = ? AND guild_id = ?',
                    (case_id, guild_id)
            ) as cursor:
                return await cursor.fetchone()

    async def close_case(self, case_id: int, guild_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                'UPDATE cases SET active = 0 WHERE case_id = ? AND guild_id = ?',
                (case_id, guild_id)
            )
            await db.commit()

    async def add_warning(self, guild_id: int, user_id: int, moderator_id: int,
                          reason: str = None, case_id: int = None):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                '''INSERT INTO warnings (guild_id, user_id, moderator_id, reason, 
                   timestamp, case_id) VALUES (?, ?, ?, ?, ?, ?)''',
                (guild_id, user_id, moderator_id, reason,
                 int(datetime.now(timezone.utc).timestamp()), case_id)
            )
            await db.commit()
            return cursor.lastrowid

    async def get_warnings(self, guild_id: int, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                    'SELECT * FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY timestamp DESC',
                    (guild_id, user_id)
            ) as cursor:
                return await cursor.fetchall()

    async def clear_warnings(self, guild_id: int, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                'DELETE FROM warnings WHERE guild_id = ? AND user_id = ?',
                (guild_id, user_id)
            )
            await db.commit()

    async def get_automod_config(self, guild_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                    'SELECT * FROM automod_config WHERE guild_id = ?',
                    (guild_id,)
            ) as cursor:
                return await cursor.fetchone()

    async def set_automod_config(self, guild_id: int, **kwargs):
        async with aiosqlite.connect(self.db_path) as db:

            await db.execute(
                f'INSERT OR REPLACE INTO automod_config (guild_id, {", ".join(kwargs.keys())}) '
                f'VALUES (?, {", ".join("?" * len(kwargs))})',
                [guild_id] + list(kwargs.values())
            )
            await db.commit()

    async def get_mod_config(self, guild_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                    'SELECT * FROM mod_config WHERE guild_id = ?',
                    (guild_id,)
            ) as cursor:
                return await cursor.fetchone()

    async def set_mod_config(self, guild_id: int, **kwargs):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                f'INSERT OR REPLACE INTO mod_config (guild_id, {", ".join(kwargs.keys())}) '
                f'VALUES (?, {", ".join("?" * len(kwargs))})',
                [guild_id] + list(kwargs.values())
            )
            await db.commit()

    async def add_badword(self, guild_id: int, word: str, severity: int = 1):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                'INSERT INTO badwords (guild_id, word, severity) VALUES (?, ?, ?)',
                (guild_id, word.lower(), severity)
            )
            await db.commit()

    async def remove_badword(self, guild_id: int, word: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                'DELETE FROM badwords WHERE guild_id = ? AND word = ?',
                (guild_id, word.lower())
            )
            await db.commit()

    async def get_badwords(self, guild_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                    'SELECT * FROM badwords WHERE guild_id = ?',
                    (guild_id,)
            ) as cursor:
                return await cursor.fetchall()

    async def add_appeal(self, case_id: int, guild_id: int, user_id: int, reason: str):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                'INSERT INTO appeals (case_id, guild_id, user_id, reason, timestamp) VALUES (?, ?, ?, ?, ?)',
                (case_id, guild_id, user_id, reason, int(datetime.now(timezone.utc).timestamp()))
            )
            await db.commit()
            return cursor.lastrowid

    async def get_appeals(self, guild_id: int, status: str = None):
        async with aiosqlite.connect(self.db_path) as db:
            if status:
                query = 'SELECT * FROM appeals WHERE guild_id = ? AND status = ? ORDER BY timestamp DESC'
                params = (guild_id, status)
            else:
                query = 'SELECT * FROM appeals WHERE guild_id = ? ORDER BY timestamp DESC'
                params = (guild_id,)

            async with db.execute(query, params) as cursor:
                return await cursor.fetchall()

    async def update_appeal(self, appeal_id: int, status: str, reviewed_by: int = None,
                            review_note: str = None):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                'UPDATE appeals SET status = ?, reviewed_by = ?, review_note = ? WHERE appeal_id = ?',
                (status, reviewed_by, review_note, appeal_id)
            )
            await db.commit()


class CaseView(View):
    def __init__(self, cases: List, current_page: int = 0):
        super().__init__(timeout=180)
        self.cases = cases
        self.current_page = current_page
        self.max_pages = (len(cases) - 1) // 5 if cases else 0

        self.update_buttons()

    def get_embed(self):
        embed = discord.Embed(
            title="Case Overview",
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc)
        )

        if not self.cases:
            embed.description = "No cases yet, everything's chill here"
            return embed

        start_idx = self.current_page * 5
        end_idx = start_idx + 5
        page_cases = self.cases[start_idx:end_idx]

        for case in page_cases:
            case_id = case[0]
            user_id = case[2]
            mod_id = case[3]
            action = case[4]
            reason = case[5]
            timestamp = case[6]
            active = "Active" if case[8] else "Closed"

            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)

            embed.add_field(
                name=f"Case #{case_id} - {action.upper()}",
                value=f"```ansi\n{ansi_blue}User: {user_id}\nMod: {mod_id}\nReason: {reason}\nStatus: {active}\nDate: {dt.strftime('%d.%m.%Y %H:%M')}{ansi_reset}```",
                inline=False
            )

        embed.set_footer(text=f"Page {self.current_page + 1} of {self.max_pages + 1}")
        return embed

    def update_buttons(self):
        for child in self.children:
            if isinstance(child, Button):
                if child.custom_id == "prev":
                    child.disabled = self.current_page == 0
                elif child.custom_id == "next":
                    child.disabled = self.current_page >= self.max_pages

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, custom_id="prev")
    async def previous_page(self, button: Button, interaction: discord.Interaction):
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, custom_id="next")
    async def next_page(self, button: Button, interaction: discord.Interaction):
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)


class ReasonModal(Modal):
    def __init__(self, action_type: str, callback_func):
        super().__init__(title=f"{action_type} - Provide a reason")
        self.action_type = action_type
        self.callback_func = callback_func

        self.add_item(InputText(
            label="Reason",
            placeholder="Why are you doing this?",
            style=discord.InputTextStyle.long,
            required=False,
            max_length=500
        ))

    async def callback(self, interaction: discord.Interaction):
        reason = self.children[0].value or "No reason provided"
        await self.callback_func(interaction, reason)


class AppealModal(Modal):
    def __init__(self, case_id: int, db: ModerationDatabase):
        super().__init__(title=f"Appeal for Case #{case_id}")
        self.case_id = case_id
        self.db = db

        self.add_item(InputText(
            label="Reason",
            placeholder="Why should this case be overturned?",
            style=discord.InputTextStyle.long,
            required=True,
            min_length=10,
            max_length=1000
        ))

    async def callback(self, interaction: discord.Interaction):
        reason = self.children[0].value

        appeal_id = await self.db.add_appeal(
            self.case_id,
            interaction.guild.id,
            interaction.user.id,
            reason
        )

        embed = discord.Embed(
            title="Appeal submitted",
            description=f"```ansi\n{ansi_green}Your appeal for Case #{self.case_id} has been received.\nAppeal ID: #{appeal_id}\n\nWe'll take a look at it!{ansi_reset}```",
            color=discord.Color.green()
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)


class AppealReviewView(View):
    def __init__(self, appeal_data, db: ModerationDatabase, bot):
        super().__init__(timeout=None)
        self.appeal_data = appeal_data
        self.db = db
        self.bot = bot

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def accept_appeal(self, button: Button, interaction: discord.Interaction):
        appeal_id = self.appeal_data[0]
        case_id = self.appeal_data[1]
        guild_id = self.appeal_data[2]

        await self.db.update_appeal(appeal_id, "accepted", interaction.user.id, "Appeal was accepted")
        await self.db.close_case(case_id, guild_id)

        embed = discord.Embed(
            title="Appeal accepted",
            description=f"```ansi\n{ansi_green}Appeal #{appeal_id} has been accepted.\nCase #{case_id} is now closed.{ansi_reset}```",
            color=discord.Color.green()
        )

        for child in self.children:
            child.disabled = True

        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.danger)
    async def deny_appeal(self, button: Button, interaction: discord.Interaction):
        appeal_id = self.appeal_data[0]

        await self.db.update_appeal(appeal_id, "denied", interaction.user.id, "Appeal was denied")

        embed = discord.Embed(
            title="Appeal denied",
            description=f"```ansi\n{ansi_red}Appeal #{appeal_id} was unfortunately not accepted.{ansi_reset}```",
            color=discord.Color.red()
        )

        for child in self.children:
            child.disabled = True

        await interaction.response.edit_message(embed=embed, view=self)


class AutoModConfigSelect(Select):
    def __init__(self, current_config):
        options = [
            discord.SelectOption(
                label="Spam Protection",
                value="spam",
                description="Blocks repeated messages",
                default=current_config.get('spam_enabled', 0) == 1 if current_config else False
            ),
            discord.SelectOption(
                label="Link Filter",
                value="links",
                description="Filters out URLs",
                default=current_config.get('links_enabled', 0) == 1 if current_config else False
            ),
            discord.SelectOption(
                label="Invite Filter",
                value="invites",
                description="No Discord invites allowed",
                default=current_config.get('invites_enabled', 0) == 1 if current_config else False
            ),
            discord.SelectOption(
                label="Caps Filter",
                value="caps",
                description="Too many capital letters get blocked",
                default=current_config.get('caps_enabled', 0) == 1 if current_config else False
            )
        ]

        super().__init__(
            placeholder="Select AutoMod features",
            options=options,
            min_values=0,
            max_values=len(options)
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            f"Selected: {', '.join(self.values) if self.values else 'Nothing'}",
            ephemeral=True
        )

# ---------------- FORUM ----------------

from dotenv import load_dotenv
import os
import re

load_dotenv()

FORUM_ID = int(os.getenv("FORUM_ID"))

MOD_ROLE_IDS = [int(x) for x in os.getenv("MOD_ROLE_IDS", "").split(",") if x]
ADMIN_ROLE_IDS = [int(x) for x in os.getenv("ADMIN_ROLE_IDS", "").split(",") if x]

def is_mod_or_admin():
    async def predicate(ctx: discord.ApplicationContext):
        return any(r.id in MOD_ROLE_IDS + ADMIN_ROLE_IDS for r in ctx.author.roles)
    return commands.check(predicate)

async def tag_autocomplete(ctx: discord.AutocompleteContext):
    user_roles = [r.id for r in ctx.interaction.user.roles]
    if not any(r in MOD_ROLE_IDS + ADMIN_ROLE_IDS for r in user_roles):
        return []

    forum_channel: discord.ForumChannel = ctx.bot.get_channel(FORUM_ID)
    if not forum_channel:
        try:
            forum_channel = await ctx.bot.fetch_channel(FORUM_ID)
        except discord.NotFound:
            return []

    all_tags = [t.name for t in forum_channel.available_tags]
    value = ctx.value.lower()
    return [t for t in all_tags if value in t.lower()][:25]

# ---------------------------------------

class ModC(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = ModerationDatabase()
        self.spam_tracker = defaultdict(lambda: defaultdict(list))
        bot.loop.create_task(self.db.init_db())



    forum = SlashCommandGroup("forum", "Forum management commands")
    mod = SlashCommandGroup("mod", "Moderation Commands", default_member_permissions=discord.Permissions(moderate_members=True))


    # ---------------------------------------

    async def log_action(self, guild: discord.Guild, embed: discord.Embed):
        config = await self.db.get_mod_config(guild.id)
        if config and config[1]:
            log_channel = guild.get_channel(config[1])
            if log_channel:
                await log_channel.send(embed=embed)

    async def check_auto_punish(self, guild_id: int, user_id: int):
        config = await self.db.get_mod_config(guild_id)
        if not config or not config[2]:
            return False

        warnings = await self.db.get_warnings(guild_id, user_id)
        threshold = config[3] or 3

        if len(warnings) >= threshold:
            return True
        return False

    async def handle_automod_violation(self, message: discord.Message, violation_type: str):
        config = await self.db.get_automod_config(message.guild.id)
        if not config:
            return

        action_type = config[8] or 'warn'

        try:
            await message.delete()
        except discord.NotFound:
            pass
        except discord.Forbidden:
            pass
        except discord.HTTPException as e:
            print(f"Failed to delete message in auto-mod: {e}")

        if action_type == 'warn':
            case_id = await self.db.add_case(
                message.guild.id,
                message.author.id,
                self.bot.user.id,
                'automod_warn',
                f'AutoMod: {violation_type}'
            )

            await self.db.add_warning(
                message.guild.id,
                message.author.id,
                self.bot.user.id,
                f'AutoMod: {violation_type}',
                case_id
            )

            try:
                await message.author.send(
                    f"Hey, you've been warned on **{message.guild.name}**.\nReason: {violation_type}\nCase: #{case_id}"
                )
            except discord.Forbidden:
                pass
            except discord.HTTPException as e:
                print(f"Failed to DM user about warning: {e}")

        elif action_type == 'kick':
            try:
                await message.author.kick(reason=f'AutoMod: {violation_type}')
            except discord.Forbidden:
                pass
            except discord.HTTPException as e:
                print(f"Failed to kick user in auto-mod: {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        if message.author.guild_permissions.administrator:
            return

        config = await self.db.get_automod_config(message.guild.id)
        if not config:
            return

        if config[1]:
            user_messages = self.spam_tracker[message.guild.id][message.author.id]
            current_time = datetime.now(timezone.utc).timestamp()

            user_messages.append(current_time)
            user_messages = [t for t in user_messages if current_time - t < (config[5] or 10)]
            self.spam_tracker[message.guild.id][message.author.id] = user_messages

            if len(user_messages) >= (config[4] or 5):
                await self.handle_automod_violation(message, "Spam")
                self.spam_tracker[message.guild.id][message.author.id] = []
                return

        if config[2]:
            url_pattern = re.compile(r'https?://\S+')
            if url_pattern.search(message.content):
                await self.handle_automod_violation(message, "Unauthorized link")
                return

        if config[3]:
            invite_pattern = re.compile(r'discord(?:\.gg|app\.com/invite)/[a-zA-Z0-9]+')
            if invite_pattern.search(message.content):
                await self.handle_automod_violation(message, "Server advertisement")
                return

        if config[4]:
            if len(message.content) > 10:
                caps_count = sum(1 for c in message.content if c.isupper())
                caps_percentage = (caps_count / len(message.content)) * 100

                if caps_percentage >= (config[6] or 70):
                    await self.handle_automod_violation(message, "Too much caps lock")
                    return

        badwords = await self.db.get_badwords(message.guild.id)
        content_lower = message.content.lower()

        for word_data in badwords:
            word = word_data[2]
            if word in content_lower:
                await self.handle_automod_violation(message, f"Banned word used")
                return

    @mod.command(name="warn", description="Warns someone")
    async def warn(
            self,
            ctx: discord.ApplicationContext,
            member: discord.Member,
            reason: Option(str, "Reason?", required=False, default="No reason provided")
    ):
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.respond("They're above you in hierarchy, can't do that.", ephemeral=True)

        case_id = await self.db.add_case(
            ctx.guild.id,
            member.id,
            ctx.author.id,
            'warn',
            reason
        )

        await self.db.add_warning(
            ctx.guild.id,
            member.id,
            ctx.author.id,
            reason,
            case_id
        )

        warnings = await self.db.get_warnings(ctx.guild.id, member.id)

        embed = discord.Embed(
            title="Warning issued",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )

        embed.add_field(
            name="Offender",
            value=f"```ansi\n{ansi_blue}{member.mention}\nID: {member.id}{ansi_reset}```",
            inline=False
        )

        embed.add_field(
            name="Mod",
            value=f"```ansi\n{ansi_blue}{ctx.author.mention}{ansi_reset}```",
            inline=True
        )

        embed.add_field(
            name="Reason",
            value=f"```ansi\n{ansi_blue}{reason}{ansi_reset}```",
            inline=False
        )

        embed.add_field(
            name="Case ID",
            value=f"```ansi\n{ansi_blue}#{case_id}{ansi_reset}```",
            inline=True
        )

        embed.add_field(
            name="Total Warnings",
            value=f"```ansi\n{ansi_yellow}{len(warnings)}{ansi_reset}```",
            inline=True
        )

        await ctx.respond(embed=embed)
        await self.log_action(ctx.guild, embed)

        try:
            await member.send(f"You received a warning on **{ctx.guild.name}**.\nReason: {reason}\nCase: #{case_id}")
        except:
            pass

        should_punish = await self.check_auto_punish(ctx.guild.id, member.id)
        if should_punish:
            config = await self.db.get_mod_config(ctx.guild.id)
            if config and config[4]:
                quarantine_role = ctx.guild.get_role(config[4])
                if quarantine_role:
                    try:
                        await member.add_roles(quarantine_role, reason="Too many warnings collected")

                        auto_embed = discord.Embed(
                            title="Auto-punishment activated",
                            description=f"```ansi\n{ansi_red}{member.mention} was automatically quarantined (too many warnings){ansi_reset}```",
                            color=discord.Color.red()
                        )
                        await ctx.send(embed=auto_embed)
                    except:
                        pass

    @mod.command(name="kick", description="Kicks someone from the server")
    async def kick(
            self,
            ctx: discord.ApplicationContext,
            member: discord.Member,
            reason: Option(str, "Reason?", required=False, default="No reason provided")
    ):
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.respond("They're above you, you can't kick them.", ephemeral=True)

        case_id = await self.db.add_case(
            ctx.guild.id,
            member.id,
            ctx.author.id,
            'kick',
            reason
        )

        try:
            await member.send(
                f"You have been kicked from **{ctx.guild.name}**.\nReason: {reason}\nCase: #{case_id}\n\nBye!")
        except:
            pass

        try:
            await member.kick(reason=reason)
        except:
            return await ctx.respond("Kick didn't work.", ephemeral=True)

        embed = discord.Embed(
            title="User kicked",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )

        embed.add_field(
            name="Kicked",
            value=f"```ansi\n{ansi_yellow}{member.mention}\nID: {member.id}{ansi_reset}```",
            inline=False
        )

        embed.add_field(
            name="Mod",
            value=f"```ansi\n{ansi_yellow}{ctx.author.mention}{ansi_reset}```",
            inline=True
        )

        embed.add_field(
            name="Reason",
            value=f"```ansi\n{ansi_yellow}{reason}{ansi_reset}```",
            inline=False
        )

        embed.add_field(
            name="Case ID",
            value=f"```ansi\n{ansi_yellow}#{case_id}{ansi_reset}```",
            inline=True
        )

        await ctx.respond(embed=embed)
        return await self.log_action(ctx.guild, embed)

    @mod.command(name="ban", description="Bans someone permanently")
    async def ban(
            self,
            ctx: discord.ApplicationContext,
            member: discord.Member,
            delete_days: Option(int, "Delete messages (days)", min_value=0, max_value=7, default=0),
            reason: Option(str, "Reason?", required=False, default="No reason provided")
    ):
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.respond("Too powerful for you.", ephemeral=True)

        case_id = await self.db.add_case(
            ctx.guild.id,
            member.id,
            ctx.author.id,
            'ban',
            reason
        )

        try:
            await member.send(
                f"You have been banned from **{ctx.guild.name}**.\nReason: {reason}\nCase: #{case_id}\n\nCya!")
        except:
            pass

        try:
            await member.ban(reason=reason, delete_message_days=delete_days)
        except:
            return await ctx.respond("Ban didn't work.", ephemeral=True)

        embed = discord.Embed(
            title="User banned",
            color=discord.Color.dark_red(),
            timestamp=datetime.now(timezone.utc)
        )

        embed.add_field(
            name="Permanent ban issued",
            value=f"```ansi\n{ansi_red}{member.mention}\nID: {member.id}{ansi_reset}```",
            inline=False
        )

        embed.add_field(
            name="Mod",
            value=f"```ansi\n{ansi_red}{ctx.author.mention}{ansi_reset}```",
            inline=True
        )

        embed.add_field(
            name="Reason",
            value=f"```ansi\n{ansi_red}{reason}{ansi_reset}```",
            inline=False
        )

        embed.add_field(
            name="Messages deleted",
            value=f"```ansi\n{ansi_red}{delete_days} days{ansi_reset}```",
            inline=True
        )

        embed.add_field(
            name="Case ID",
            value=f"```ansi\n{ansi_red}#{case_id}{ansi_reset}```",
            inline=True
        )

        await ctx.respond(embed=embed)
        return await self.log_action(ctx.guild, embed)

    @mod.command(name="unban", description="Unbans someone")
    async def unban(
            self,
            ctx: discord.ApplicationContext,
            user_id: Option(str, "User ID", required=True),
            reason: Option(str, "Reason?", required=False, default="Second chance")
    ):
        try:
            user_id_int = int(user_id)
            user = await self.bot.fetch_user(user_id_int)
        except:
            return await ctx.respond("Invalid user ID.", ephemeral=True)

        try:
            await ctx.guild.unban(user, reason=reason)
        except:
            return await ctx.respond("They're not banned or something went wrong.", ephemeral=True)

        case_id = await self.db.add_case(
            ctx.guild.id,
            user.id,
            ctx.author.id,
            'unban',
            reason
        )

        embed = discord.Embed(
            title="Ban lifted",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )

        embed.add_field(
            name="Welcome back",
            value=f"```ansi\n{ansi_green}{user.name}\nID: {user.id}{ansi_reset}```",
            inline=False
        )

        embed.add_field(
            name="Mod",
            value=f"```ansi\n{ansi_green}{ctx.author.mention}{ansi_reset}```",
            inline=True
        )

        embed.add_field(
            name="Reason",
            value=f"```ansi\n{ansi_green}{reason}{ansi_reset}```",
            inline=False
        )

        embed.add_field(
            name="Case ID",
            value=f"```ansi\n{ansi_green}#{case_id}{ansi_reset}```",
            inline=True
        )

        await ctx.respond(embed=embed)
        return await self.log_action(ctx.guild, embed)

    @mod.command(name="timeout", description="Times someone out")
    async def timeout(
            self,
            ctx: discord.ApplicationContext,
            member: discord.Member,
            duration: Option(int, "How long? (Minutes)", required=True),
            reason: Option(str, "Reason?", required=False, default="No reason provided")
    ):
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.respond("Can't do that, they're above you.", ephemeral=True)

        duration_delta = timedelta(minutes=duration)

        try:
            await member.timeout(duration_delta, reason=reason)
        except:
            return await ctx.respond("Timeout didn't work.", ephemeral=True)

        case_id = await self.db.add_case(
            ctx.guild.id,
            member.id,
            ctx.author.id,
            'timeout',
            reason,
            duration * 60
        )

        end_time = datetime.now(timezone.utc) + duration_delta

        embed = discord.Embed(
            title="Timeout given",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )

        embed.add_field(
            name="Time out",
            value=f"```ansi\n{ansi_yellow}{member.mention}\nID: {member.id}{ansi_reset}```",
            inline=False
        )

        embed.add_field(
            name="Mod",
            value=f"```ansi\n{ansi_yellow}{ctx.author.mention}{ansi_reset}```",
            inline=True
        )

        embed.add_field(
            name="Duration",
            value=f"```ansi\n{ansi_yellow}{duration} minutes{ansi_reset}```",
            inline=True
        )

        embed.add_field(
            name="Ends",
            value=discord.utils.format_dt(end_time, 'R'),
            inline=True
        )

        embed.add_field(
            name="Reason",
            value=f"```ansi\n{ansi_yellow}{reason}{ansi_reset}```",
            inline=False
        )

        embed.add_field(
            name="Case ID",
            value=f"```ansi\n{ansi_yellow}#{case_id}{ansi_reset}```",
            inline=True
        )

        await ctx.respond(embed=embed)
        return await self.log_action(ctx.guild, embed)

    @mod.command(name="clear", description="Deletes messages")
    async def clear(
            self,
            ctx: discord.ApplicationContext,
            amount: Option(int, "How many?", min_value=1, max_value=100, required=True),
            member: Option(discord.Member, "Only from this user", required=False, default=None)
    ):
        await ctx.defer(ephemeral=True)

        def check(m):
            if member:
                return m.author == member
            return True

        deleted = await ctx.channel.purge(limit=amount, check=check)

        embed = discord.Embed(
            title="Messages deleted",
            description=f"```ansi\n{ansi_blue}{len(deleted)} messages were cleaned up{ansi_reset}```",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )

        if member:
            embed.add_field(
                name="From user",
                value=f"```ansi\n{ansi_blue}{member.mention}{ansi_reset}```"
            )

        await ctx.respond(embed=embed, ephemeral=True)
        await self.log_action(ctx.guild, embed)

    @mod.command(name="warnings", description="Shows all warnings of someone")
    async def warnings(
            self,
            ctx: discord.ApplicationContext,
            member: discord.Member
    ):
        warnings = await self.db.get_warnings(ctx.guild.id, member.id)

        embed = discord.Embed(
            title=f"Warnings for {member.display_name}",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )

        embed.add_field(
            name="Count",
            value=f"```ansi\n{ansi_yellow}{len(warnings)}{ansi_reset}```",
            inline=True
        )

        if warnings:
            for i, warn in enumerate(warnings[:10], 1):
                timestamp = warn[4]
                reason = warn[3]
                dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)

                embed.add_field(
                    name=f"Warning #{i}",
                    value=f"```ansi\n{ansi_yellow}Reason: {reason}\nDate: {dt.strftime('%d.%m.%Y %H:%M')}{ansi_reset}```",
                    inline=False
                )
        else:
            embed.description = "```ansi\n" + ansi_blue + "Clean record, no warnings" + ansi_reset + "```"

        await ctx.respond(embed=embed)

    @mod.command(name="clearwarnings", description="Deletes all warnings from someone")
    async def clearwarnings(
            self,
            ctx: discord.ApplicationContext,
            member: discord.Member
    ):
        warnings = await self.db.get_warnings(ctx.guild.id, member.id)

        if not warnings:
            return await ctx.respond("They don't have any warnings anyway.", ephemeral=True)

        await self.db.clear_warnings(ctx.guild.id, member.id)

        embed = discord.Embed(
            title="Warnings cleared",
            description=f"```ansi\n{ansi_green}All warnings from {member.mention} have been removed{ansi_reset}```",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )

        embed.add_field(
            name="Cleared",
            value=f"```ansi\n{ansi_green}{len(warnings)} total{ansi_reset}```"
        )

        await ctx.respond(embed=embed)
        return await self.log_action(ctx.guild, embed)

    @mod.command(name="case", description="Shows details of a case")
    async def case(
            self,
            ctx: discord.ApplicationContext,
            case_id: Option(int, "Case ID", required=True)
    ):
        case = await self.db.get_case_by_id(case_id, ctx.guild.id)

        if not case:
            return await ctx.respond("Case not found.", ephemeral=True)

        user_id = case[2]
        mod_id = case[3]
        action = case[4]
        reason = case[5]
        timestamp = case[6]
        duration = case[7]
        active = case[8]

        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)

        embed = discord.Embed(
            title=f"Case #{case_id}",
            color=discord.Color.blurple(),
            timestamp=dt
        )

        embed.add_field(
            name="Action",
            value=f"```ansi\n{ansi_blue}{action.upper()}{ansi_reset}```",
            inline=True
        )

        embed.add_field(
            name="Status",
            value=f"```ansi\n{ansi_blue}{'Active' if active else 'Closed'}{ansi_reset}```",
            inline=True
        )

        embed.add_field(
            name="User",
            value=f"```ansi\n{ansi_blue}ID: {user_id}{ansi_reset}```",
            inline=False
        )

        embed.add_field(
            name="Mod",
            value=f"```ansi\n{ansi_blue}ID: {mod_id}{ansi_reset}```",
            inline=True
        )

        embed.add_field(
            name="Reason",
            value=f"```ansi\n{ansi_blue}{reason}{ansi_reset}```",
            inline=False
        )

        if duration:
            embed.add_field(
                name="Duration",
                value=f"```ansi\n{ansi_blue}{duration // 60} minutes{ansi_reset}```",
                inline=True
            )

        return await ctx.respond(embed=embed)

    @mod.command(name="cases", description="Shows all cases")
    async def cases(
            self,
            ctx: discord.ApplicationContext,
            member: Option(discord.Member, "From which user?", required=False, default=None),
            active_only: Option(bool, "Only active cases", required=False, default=False)
    ):
        await ctx.defer()

        if member:
            cases = await self.db.get_cases(ctx.guild.id, member.id, active_only)
        else:
            cases = await self.db.get_cases(ctx.guild.id, None, active_only)

        if not cases:
            return await ctx.respond("No cases found.", ephemeral=True)

        view = CaseView(cases)
        return await ctx.respond(embed=view.get_embed(), view=view)

    @mod.command(name="closecase", description="Closes a case")
    async def closecase(
            self,
            ctx: discord.ApplicationContext,
            case_id: Option(int, "Case ID", required=True)
    ):
        case = await self.db.get_case_by_id(case_id, ctx.guild.id)

        if not case:
            return await ctx.respond("Case not found.", ephemeral=True)

        if not case[8]:
            return await ctx.respond("It's already closed.", ephemeral=True)

        await self.db.close_case(case_id, ctx.guild.id)

        embed = discord.Embed(
            title="Case closed",
            description=f"```ansi\n{ansi_green}Case #{case_id} is now closed{ansi_reset}```",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )

        await ctx.respond(embed=embed)
        return await self.log_action(ctx.guild, embed)

    @mod.command(name="quarantine", description="Quarantines someone")
    async def quarantine(
            self,
            ctx: discord.ApplicationContext,
            member: discord.Member,
            reason: Option(str, "Reason?", required=False, default="Suspicious")
    ):
        config = await self.db.get_mod_config(ctx.guild.id)

        if not config or not config[4]:
            return await ctx.respond("No quarantine role set up.", ephemeral=True)

        quarantine_role = ctx.guild.get_role(config[4])
        if not quarantine_role:
            return await ctx.respond("Quarantine role not found.", ephemeral=True)

        try:
            await member.add_roles(quarantine_role, reason=reason)
        except:
            return await ctx.respond("Couldn't assign role.", ephemeral=True)

        embed = discord.Embed(
            title="Quarantined",
            color=discord.Color.dark_orange(),
            timestamp=datetime.now(timezone.utc)
        )

        embed.add_field(
            name="Isolated",
            value=f"```ansi\n{ansi_yellow}{member.mention}\nID: {member.id}{ansi_reset}```",
            inline=False
        )

        embed.add_field(
            name="Mod",
            value=f"```ansi\n{ansi_yellow}{ctx.author.mention}{ansi_reset}```",
            inline=True
        )

        embed.add_field(
            name="Reason",
            value=f"```ansi\n{ansi_yellow}{reason}{ansi_reset}```",
            inline=False
        )

        await ctx.respond(embed=embed)
        return await self.log_action(ctx.guild, embed)

    @mod.command(name="unquarantine", description="Removes someone from quarantine")
    async def unquarantine(
            self,
            ctx: discord.ApplicationContext,
            member: discord.Member
    ):
        config = await self.db.get_mod_config(ctx.guild.id)

        if not config or not config[4]:
            return await ctx.respond("No quarantine role configured.", ephemeral=True)

        quarantine_role = ctx.guild.get_role(config[4])
        if not quarantine_role:
            return await ctx.respond("Quarantine role not found.", ephemeral=True)

        if quarantine_role not in member.roles:
            return await ctx.respond("They're not in quarantine.", ephemeral=True)

        try:
            await member.remove_roles(quarantine_role)
        except:
            return await ctx.respond("Couldn't remove role.", ephemeral=True)

        embed = discord.Embed(
            title="Quarantine lifted",
            description=f"```ansi\n{ansi_green}{member.mention} is free again{ansi_reset}```",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )

        await ctx.respond(embed=embed)
        return await self.log_action(ctx.guild, embed)

    setup_group = mod.create_subgroup("setup", "Set up moderation system")

    @setup_group.command(name="logchannel", description="Sets the log channel")
    async def setup_logchannel(
            self,
            ctx: discord.ApplicationContext,
            channel: discord.TextChannel
    ):
        await self.db.set_mod_config(ctx.guild.id, log_channel_id=channel.id)

        embed = discord.Embed(
            title="Log channel set",
            description=f"```ansi\n{ansi_green}Logs will now go to {channel.mention}{ansi_reset}```",
            color=discord.Color.green()
        )

        await ctx.respond(embed=embed)

    @setup_group.command(name="quarantinerole", description="Sets the quarantine role")
    async def setup_quarantinerole(
            self,
            ctx: discord.ApplicationContext,
            role: discord.Role
    ):
        await self.db.set_mod_config(ctx.guild.id, quarantine_role_id=role.id)

        embed = discord.Embed(
            title="Quarantine role set",
            description=f"```ansi\n{ansi_green}{role.name} is now the quarantine role{ansi_reset}```",
            color=discord.Color.green()
        )

        await ctx.respond(embed=embed)

    @setup_group.command(name="autopunish", description="Configures auto-punishment")
    async def setup_autopunish(
            self,
            ctx: discord.ApplicationContext,
            enabled: Option(bool, "On or off?", required=True),
            threshold: Option(int, "From how many warnings?", min_value=1, max_value=10, default=3)
    ):
        await self.db.set_mod_config(
            ctx.guild.id,
            auto_punish=1 if enabled else 0,
            warn_threshold=threshold
        )

        status = "enabled" if enabled else "disabled"

        embed = discord.Embed(
            title="Auto-punishment configured",
            description=f"```ansi\n{ansi_green}Auto-punishment is now {status}\nTriggers after {threshold} warnings{ansi_reset}```",
            color=discord.Color.green()
        )

        await ctx.respond(embed=embed)

    automod = SlashCommandGroup("automod", "AutoMod Settings",
                                default_member_permissions=discord.Permissions(administrator=True))

    @automod.command(name="configure", description="Sets up AutoMod")
    async def automod_configure(
            self,
            ctx: discord.ApplicationContext,
            spam: Option(bool, "Spam protection", required=False, default=False),
            links: Option(bool, "Link filter", required=False, default=False),
            invites: Option(bool, "Invite filter", required=False, default=False),
            caps: Option(bool, "Caps filter", required=False, default=False),
            action: Option(str, "What should happen?", choices=["warn", "kick"], default="warn")
    ):
        await self.db.set_automod_config(
            ctx.guild.id,
            spam_enabled=1 if spam else 0,
            links_enabled=1 if links else 0,
            invites_enabled=1 if invites else 0,
            caps_enabled=1 if caps else 0,
            action_type=action
        )

        features = []
        if spam:
            features.append("Spam Protection")
        if links:
            features.append("Link Filter")
        if invites:
            features.append("Invite Filter")
        if caps:
            features.append("Caps Filter")

        embed = discord.Embed(
            title="AutoMod configured",
            color=discord.Color.green()
        )

        embed.add_field(
            name="Active Features",
            value=f"```ansi\n{ansi_green}{', '.join(features) if features else 'Nothing active'}{ansi_reset}```",
            inline=False
        )

        embed.add_field(
            name="Action on violation",
            value=f"```ansi\n{ansi_green}{action}{ansi_reset}```",
            inline=True
        )

        await ctx.respond(embed=embed)

    @automod.command(name="settings", description="Shows AutoMod settings")
    async def automod_settings(self, ctx: discord.ApplicationContext):
        config = await self.db.get_automod_config(ctx.guild.id)

        embed = discord.Embed(
            title="AutoMod Settings",
            color=discord.Color.blurple()
        )

        if config:
            embed.add_field(
                name="Spam Protection",
                value=f"```ansi\n{ansi_blue}{'On' if config[1] else 'Off'}{ansi_reset}```",
                inline=True
            )

            embed.add_field(
                name="Link Filter",
                value=f"```ansi\n{ansi_blue}{'On' if config[2] else 'Off'}{ansi_reset}```",
                inline=True
            )

            embed.add_field(
                name="Invite Filter",
                value=f"```ansi\n{ansi_blue}{'On' if config[3] else 'Off'}{ansi_reset}```",
                inline=True
            )

            embed.add_field(
                name="Caps Filter",
                value=f"```ansi\n{ansi_blue}{'On' if config[4] else 'Off'}{ansi_reset}```",
                inline=True
            )

            embed.add_field(
                name="Action",
                value=f"```ansi\n{ansi_blue}{config[8] or 'warn'}{ansi_reset}```",
                inline=True
            )

            embed.add_field(
                name="Spam Threshold",
                value=f"```ansi\n{ansi_blue}{config[5] or 5} messages{ansi_reset}```",
                inline=True
            )
        else:
            embed.description = "```ansi\n" + ansi_blue + "AutoMod is not set up yet" + ansi_reset + "```"

        await ctx.respond(embed=embed)

    badword = SlashCommandGroup("badword", "Word Filter",
                                default_member_permissions=discord.Permissions(manage_messages=True))

    @badword.command(name="add", description="Adds a banned word")
    async def badword_add(
            self,
            ctx: discord.ApplicationContext,
            word: Option(str, "Which word?", required=True),
            severity: Option(int, "How severe? (1-3)", min_value=1, max_value=3, default=1)
    ):
        await self.db.add_badword(ctx.guild.id, word, severity)

        embed = discord.Embed(
            title="Word added to blacklist",
            description=f"```ansi\n{ansi_green}'{word}' is now banned\nSeverity: {severity}{ansi_reset}```",
            color=discord.Color.green()
        )

        await ctx.respond(embed=embed, ephemeral=True)

    @badword.command(name="remove", description="Removes a banned word")
    async def badword_remove(
            self,
            ctx: discord.ApplicationContext,
            word: Option(str, "Which word?", required=True)
    ):
        await self.db.remove_badword(ctx.guild.id, word)

        embed = discord.Embed(
            title="Word removed from blacklist",
            description=f"```ansi\n{ansi_green}'{word}' is now allowed again{ansi_reset}```",
            color=discord.Color.green()
        )

        await ctx.respond(embed=embed, ephemeral=True)

    @badword.command(name="list", description="Shows all banned words")
    async def badword_list(self, ctx: discord.ApplicationContext):
        words = await self.db.get_badwords(ctx.guild.id)

        embed = discord.Embed(
            title="Banned Words",
            color=discord.Color.blurple()
        )

        if words:
            word_list = [f"{w[2]} (Severity: {w[3]})" for w in words]
            embed.description = f"```ansi\n{ansi_blue}{chr(10).join(word_list)}{ansi_reset}```"
        else:
            embed.description = "```ansi\n" + ansi_blue + "No words blocked" + ansi_reset + "```"

        await ctx.respond(embed=embed, ephemeral=True)

    appeal = SlashCommandGroup("appeal", "Appeal System")

    @appeal.command(name="submit", description="Submits an appeal")
    async def appeal_submit(
            self,
            ctx: discord.ApplicationContext,
            case_id: Option(int, "Case ID", required=True)
    ):
        case = await self.db.get_case_by_id(case_id, ctx.guild.id)

        if not case:
            return await ctx.respond("Case not found.", ephemeral=True)

        if case[2] != ctx.author.id:
            return await ctx.respond("That's not your case.", ephemeral=True)

        if not case[8]:
            return await ctx.respond("The case is already closed.", ephemeral=True)

        modal = AppealModal(case_id, self.db)
        return await ctx.send_modal(modal)

    @appeal.command(name="review", description="Shows pending appeals")
    @commands.has_permissions(moderate_members=True)
    async def appeal_review(self, ctx: discord.ApplicationContext):
        appeals = await self.db.get_appeals(ctx.guild.id, "pending")

        if not appeals:
            return await ctx.respond("No pending appeals.", ephemeral=True)

        embed = discord.Embed(
            title="Pending Appeals",
            color=discord.Color.blurple()
        )

        for appeal in appeals[:5]:
            appeal_id = appeal[0]
            case_id = appeal[1]
            user_id = appeal[3]
            reason = appeal[4]
            timestamp = appeal[5]

            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)

            embed.add_field(
                name=f"Appeal #{appeal_id} - Case #{case_id}",
                value=f"```ansi\n{ansi_blue}User: {user_id}\nReason: {reason[:50]}...\nDate: {dt.strftime('%d.%m.%Y')}{ansi_reset}```",
                inline=False
            )

        if appeals:
            view = AppealReviewView(appeals[0], self.db, self.bot)
            return await ctx.respond(embed=embed, view=view)
        else:
            return await ctx.respond(embed=embed)

    @appeal.command(name="list", description="Shows all appeals")
    @commands.has_permissions(moderate_members=True)
    async def appeal_list(
            self,
            ctx: discord.ApplicationContext,
            status: Option(str, "Status", choices=["pending", "accepted", "denied"], required=False)
    ):
        appeals = await self.db.get_appeals(ctx.guild.id, status)

        embed = discord.Embed(
            title=f"Appeals {f'({status})' if status else ''}",
            color=discord.Color.blurple()
        )

        if not appeals:
            embed.description = "```ansi\n" + ansi_blue + "No appeals found" + ansi_reset + "```"
        else:
            for appeal in appeals[:10]:
                appeal_id = appeal[0]
                case_id = appeal[1]
                user_id = appeal[3]
                appeal_status = appeal[6]
                timestamp = appeal[5]

                dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)

                embed.add_field(
                    name=f"Appeal #{appeal_id}",
                    value=f"```ansi\n{ansi_blue}Case: #{case_id}\nUser: {user_id}\nStatus: {appeal_status}\nDate: {dt.strftime('%d.%m.%Y')}{ansi_reset}```",
                    inline=True
                )

        await ctx.respond(embed=embed)


    # ---------------------------------------




    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        if thread.parent_id != FORUM_ID:
            return
        try:
            starter_msg = await thread.fetch_message(thread.id)
            await starter_msg.pin()
        except (discord.NotFound, discord.Forbidden) as e:
            print(f"Could not pin thread starter message: {e}")

        embed = discord.Embed(
            title="Support Channel",
            description=
            "**Remember:**\n"
            "- If you are on the **latest version** of the App\n"
            "- Provide as much details as you can about the issue. (For example a step-by-step way on how to encounter that issue)\n"
            "- Screenshots or screen recordings can help us understand the issue better, so it's recommended you send at least one in your post.\n"
            ,
            color=discord.Color.blurple()
        )
        embed.set_footer(text="You can use !close to close your post.")

        await thread.send(f"{thread.owner.mention}", embed=embed)

    @forum.command(description="Change a thread's tag (2 use per post limit)")
    @is_mod_or_admin()
    async def change(
            self,
            ctx: discord.ApplicationContext,
            tag: Option(str, "Select a tag", autocomplete=tag_autocomplete)
    ):
        await ctx.defer(ephemeral=True)

        thread: discord.Thread = ctx.channel
        forum_channel: discord.ForumChannel = thread.parent
        if thread.parent_id != FORUM_ID:
            await ctx.respond("This command can only be used in the configured forum.", ephemeral=True)
            return
        tag_obj = next((t for t in forum_channel.available_tags if t.name == tag), None)
        if not tag_obj:
            await ctx.respond("Tag not found.", ephemeral=True)
            return

        # Removes previously "[..]" tags in title
        nt = re.sub(r"^\[.*?]\s*", "", thread.name)
        nt = f"[{tag_obj.name}] {nt}"

        await thread.edit(applied_tags=[tag_obj], name=nt)
        await ctx.respond(f"Thread tag set to: {tag_obj.name}", ephemeral=True)

    @forum.command(description="Close the thread (mod only)")
    @is_mod_or_admin()
    async def close(self, ctx: discord.ApplicationContext):
        thread: discord.Thread = ctx.channel

        if thread.parent_id != FORUM_ID:
            await ctx.respond(
                "This command can only be used in the configured forum.", ephemeral=True
            )
            return

        await thread.send("Thread has been locked 🔒")
        await ctx.respond(f"Closing thread {thread.name}", ephemeral=True)
        await thread.edit(archived=True, locked=True, name=f"🔒 {thread.name}")


    @forum.command(description="Unlock a thread (mod only)")
    @is_mod_or_admin()
    async def unlock(
        self,
        ctx: discord.ApplicationContext
    ):
        thread: discord.Thread = ctx.channel
        if thread.parent_id != FORUM_ID:
            await ctx.respond("This command can only be used in the configured forum.", ephemeral=True)
            return
        await thread.edit(archived=False, locked=False)
        await ctx.respond(f"Thread '{thread.name}' unlocked.", ephemeral=True)

    @commands.command(name="close", description="Close and archive your thread (author only)")
    async def close(self, ctx):
        thread: discord.Thread = ctx.channel

        if thread.parent_id != FORUM_ID:
            await ctx.reply("This command can only be used in the configured forum.")
            return

        if ctx.author != thread.owner:
            await ctx.reply("Only the thread author can close this thread.")
            return

        await ctx.reply("Thread closed and archived by author.")
        await thread.edit(locked=True, archived=True)

    # ---------------------------------------


def setup(bot: commands.Bot):
    bot.add_cog(ModC(bot))
