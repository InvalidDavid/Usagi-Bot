import uuid
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from utils.imports import *

logger = logging.getLogger("bot.reminder")

DB_PATH = "Data/reminders.db"
MAX_RETRIES = 5

WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

UNIT_MAP = {
    "s": 1,
    "sec": 1, "second": 1, "seconds": 1,
    "m": 60,
    "min": 60, "minute": 60, "minutes": 60,
    "h": 3600,
    "hr": 3600, "hour": 3600, "hours": 3600,
    "d": 86400,
    "day": 86400, "days": 86400,
}

TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")
DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
DURATION_RE = re.compile(r"(\d+)\s*([a-zA-Z]+)")


def parse_duration(text: str):
    matches = DURATION_RE.findall(text)
    if not matches:
        return 0

    total = 0

    for value, unit in matches:
        value = int(value)
        unit = unit.lower()

        matched = None
        for k in UNIT_MAP:
            if unit.startswith(k):
                matched = k
                break

        if not matched:
            continue

        total += value * UNIT_MAP[matched]

    return total


def next_weekday(now, target_idx):
    days_ahead = (target_idx - now.weekday() + 7) % 7
    if days_ahead == 0:
        days_ahead = 7
    return now + timedelta(days=days_ahead)


def parse_time(text: str):
    if not text:
        return None

    raw = text.strip().lower()
    now = datetime.now()

    seconds = parse_duration(raw)

    if raw.startswith("in "):
        seconds = parse_duration(raw.replace("in ", "", 1))

    if seconds:
        return now + timedelta(seconds=seconds)

    date_match = DATE_RE.search(raw)
    time_match = re.search(r"(\d{1,2}):(\d{2})", raw)

    if date_match:
        y, m, d = map(int, date_match.groups())
        h, mi = 0, 0

        if time_match:
            h, mi = map(int, time_match.groups())

        return datetime(y, m, d, h, mi)

    if "tomorrow" in raw:
        base = now + timedelta(days=1)

        t = TIME_RE.search(raw)
        if t:
            h, mi = map(int, t.groups())
            return base.replace(hour=h, minute=mi, second=0, microsecond=0)

        return base

    for day, idx in WEEKDAYS.items():
        if f"next {day}" in raw:
            base = next_weekday(now, idx)

            t = TIME_RE.search(raw)
            if t:
                h, mi = map(int, t.groups())
                base = base.replace(hour=h, minute=mi, second=0, microsecond=0)

            return base

    exact_time = TIME_RE.fullmatch(raw)
    if exact_time:
        h, mi = map(int, exact_time.groups())
        candidate = now.replace(hour=h, minute=mi, second=0, microsecond=0)
        return candidate

    return None


def get_next_display_number(conn, guild_id):
    rows = conn.execute("""
        SELECT display_number FROM reminders
        WHERE guild_id=? AND status='pending'
        ORDER BY display_number
    """, (guild_id,)).fetchall()

    taken = {r[0] for r in rows}

    num = 1
    while num in taken:
        num += 1

    return num


def get_state(conn, key: str):
    row = conn.execute(
        "SELECT value FROM system_state WHERE key=?",
        (key,)
    ).fetchone()
    return row[0] if row else None


def set_state(conn, key: str, value: str):
    conn.execute("""
        INSERT INTO system_state (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
    """, (key, value))


class ReminderListView(discord.ui.View):
    def __init__(self, cog, user_id, guild_id, reminders=None, source_interaction=None):
        super().__init__(timeout=180)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.source_interaction = source_interaction

        self.build(reminders if reminders is not None else self.cog.get_user_pending_reminders(user_id, guild_id))

    def build(self, reminders):
        self.clear_items()

        if reminders:
            self.add_item(ReminderSelect(self.cog, self.user_id, self.guild_id, reminders))

    async def refresh_message(self):
        reminders = self.cog.get_user_pending_reminders(self.user_id, self.guild_id)

        if not self.source_interaction:
            return

        if not reminders:
            try:
                await self.source_interaction.edit_original_response(
                    content="No reminders",
                    view=None
                )
            except Exception:
                logger.exception("Failed to update reminder list to empty state")
            return

        self.build(reminders)

        text = "\n\n".join([
            f"**`#{display_num}`**\n"
            f"**When:** <t:{run_at}:f> (<t:{run_at}:R>)\n"
            f"**Reason:** `{msg}`"
            for display_num, db_id, msg, run_at in reminders
        ])

        try:
            await self.source_interaction.edit_original_response(
                content=text,
                view=self
            )
        except Exception:
            logger.exception("Failed to refresh reminder list message")

    async def on_timeout(self):
        if not self.source_interaction:
            return

        try:
            await self.source_interaction.edit_original_response(
                content="Timeoutet.",
                view=None
            )
        except discord.NotFound:
            return
        except Exception:
            logger.exception("Failed to update reminder list view on timeout")


class ReminderSelect(discord.ui.Select):
    def __init__(self, cog, user_id, guild_id, reminders):
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id

        self.reminder_map = {
            display_num: db_id
            for display_num, db_id, msg, run_at in reminders
        }

        options = [
            discord.SelectOption(
                label=f"#{display_num}",
                description=(msg[:80] if msg else ""),
                value=str(display_num)
            )
            for display_num, db_id, msg, run_at in reminders[:25]
        ]

        super().__init__(placeholder="Select reminder", options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not your reminders!", ephemeral=True)

        display_num = int(self.values[0])
        db_id = self.reminder_map[display_num]

        parent_view = self.view if isinstance(self.view, ReminderListView) else None
        view = ConfirmView(self.cog, self.user_id, self.guild_id, db_id, display_num, parent_view=parent_view)

        # this is a py-cord bug which allow us to "reset" the selectmenu
        await interaction.response.edit_message()

        if parent_view:
            await parent_view.refresh_message()

        msg = await interaction.followup.send(
            f"Cancel reminder `#{display_num}`?",
            view=view,
            ephemeral=True,
            wait=True
        )
        view.message = msg
        return None


class ConfirmView(discord.ui.View):
    def __init__(self, cog, user_id, guild_id, db_id, display_num, parent_view=None):
        super().__init__(timeout=30)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.db_id = db_id
        self.display_num = display_num
        self.parent_view = parent_view
        self.message = None

    @discord.ui.button(label="Confirm Cancel", style=discord.ButtonStyle.red)
    async def confirm(self, button, interaction: discord.Interaction):
        await interaction.response.defer()

        ok = self.cog.cancel_reminder(self.user_id, self.guild_id, self.db_id)

        if ok:
            if self.parent_view:
                await self.parent_view.refresh_message()

            await interaction.edit_original_response(
                content=f"✅ Reminder #{self.display_num} cancelled",
                view=None
            )
        else:
            await interaction.edit_original_response(
                content="❌ Failed",
                view=None
            )

    @discord.ui.button(label="Close", style=discord.ButtonStyle.grey)
    async def cancel(self, button, interaction: discord.Interaction):
        await interaction.response.defer()

        await interaction.edit_original_response(
            content="❌ Cancelled",
            view=None
        )

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

        if not self.message:
            return

        try:
            await self.message.edit(content="Timeoutet.", view=None)
        except discord.NotFound:
            return
        except Exception as e:
            logger.exception("Failed to update confirm view on timeout")

class Reminder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.worker_task = None

        self._init_db()

        self.scheduler = AsyncIOScheduler()
        self.scheduler.add_job(self.cleanup_job, "interval", hours=24)

        self.bot.loop.create_task(self._auto_start_worker())
        self.bot.loop.create_task(self._reclaim_stuck())
        self.bot.loop.create_task(self._start_scheduler_safe())
        self.bot.loop.create_task(self._cleanup_orphan_users())

    def _init_db(self):
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                guild_id INTEGER,
                channel_id INTEGER,
                message TEXT,
                display_number INTEGER,
                run_at INTEGER,
                created_at INTEGER,
                finished_at INTEGER,
                status TEXT DEFAULT 'pending',
                retries INTEGER DEFAULT 0,
                lock_token TEXT,
                last_error TEXT
            )
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS system_state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """)

            cols = [row[1] for row in conn.execute("PRAGMA table_info(reminders)").fetchall()]

            if "finished_at" not in cols:
                conn.execute("ALTER TABLE reminders ADD COLUMN finished_at INTEGER")

            conn.commit()

    def get_user_pending_reminders(self, user_id, guild_id):
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute("""
                SELECT id, message, run_at, display_number
                FROM reminders
                WHERE user_id=? AND guild_id=? AND status='pending'
                ORDER BY display_number
            """, (user_id, guild_id)).fetchall()

        return [
            (r[3], r[0], r[1], r[2])
            for r in rows[:25]
        ]

    async def _cleanup_orphan_users(self):
        await self.bot.wait_until_ready()

        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute("""
                SELECT DISTINCT user_id, guild_id
                FROM reminders
            """).fetchall()

            removed_users = 0
            removed_rows = 0

            for user_id, guild_id in rows:
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    continue

                member = guild.get_member(user_id)

                if member is None:
                    try:
                        member = await guild.fetch_member(user_id)
                    except discord.NotFound:
                        cur = conn.execute("""
                            DELETE FROM reminders
                            WHERE user_id=? AND guild_id=?
                        """, (user_id, guild_id))
                        if cur.rowcount > 0:
                            removed_users += 1
                            removed_rows += cur.rowcount
                    except discord.Forbidden:
                        continue
                    except discord.HTTPException:
                        continue

            conn.commit()

        if removed_rows > 0:
            logger.info(
                "Orphan cleanup removed %s reminders from %s users",
                removed_rows,
                removed_users
            )

    async def _start_scheduler_safe(self):
        await self.bot.wait_until_ready()

        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Scheduler started safely")

    async def cleanup_job(self):
        try:
            now = int(time.time())

            with sqlite3.connect(DB_PATH) as conn:
                last = get_state(conn, "last_cleanup")

                if last and now - int(last) < 86400:
                    logger.info("Cleanup skipped (already done within 24h)")
                    return

                cutoff = now - 86400

                cur = conn.execute("""
                    DELETE FROM reminders
                    WHERE status IN ('done', 'cancelled', 'failed')
                      AND finished_at IS NOT NULL
                      AND finished_at < ?
                """, (cutoff,))

                set_state(conn, "last_cleanup", str(now))
                conn.commit()

            logger.info("Cleanup executed | removed %s rows", cur.rowcount)

        except Exception:
            logger.exception("Cleanup failed")

    async def _reclaim_stuck(self):
        await self.bot.wait_until_ready()

        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                UPDATE reminders
                SET status='pending',
                    lock_token=NULL
                WHERE status='processing'
            """)
            conn.commit()

        logger.info("Reclaimed stuck reminders back to pending")

    async def _auto_start_worker(self):
        await self.bot.wait_until_ready()
        if not self.worker_task or self.worker_task.done():
            self.worker_task = asyncio.create_task(self.worker_loop())
            logger.info("Worker loop started")

    reminder = discord.SlashCommandGroup("reminder", "Remind system")

    @reminder.command(name="create", description="Create a new reminder")
    async def create(
        self,
        ctx: discord.ApplicationContext,
        duration: discord.Option(str, description="When the reminder should trigger"),
        message: discord.Option(str, description="Reminder message")
    ):
        target = parse_time(duration)
        if not target:
            return await ctx.respond("Use 10s / 5m / 2h / 1d format.", ephemeral=True)

        run_at = int(target.timestamp())

        if run_at - int(time.time()) < 5:
            return await ctx.respond("Min. 5s.", ephemeral=True)

        now = int(time.time())

        with sqlite3.connect(DB_PATH) as conn:
            display_number = get_next_display_number(conn, ctx.guild.id)

            conn.execute("""
                INSERT INTO reminders
                (user_id, guild_id, channel_id, message, display_number, run_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                ctx.author.id,
                ctx.guild.id,
                ctx.channel.id,
                message,
                display_number,
                run_at,
                now
            ))

            conn.commit()

        logger.info(
            "Created reminder #%s for user %s in guild %s",
            display_number,
            ctx.author.id,
            ctx.guild.id
        )

        am = discord.AllowedMentions(
            everyone=False,
            roles=False,
            users=True
        )

        return await ctx.respond(
            f"✅ Reminder `#{display_number}` → <t:{run_at}:f>\n-# Reason: `{message}`",
            allowed_mentions=am
        )

    @reminder.command(name="list", description="List reminders")
    async def list(self, ctx: discord.ApplicationContext):
        reminders_with_numbers = self.get_user_pending_reminders(ctx.author.id, ctx.guild.id)

        if not reminders_with_numbers:
            return await ctx.respond("No reminders", ephemeral=True)

        text = "\n\n".join([
            f"**`#{display_num}`**\n"
            f"**When:** <t:{run_at}:f> (<t:{run_at}:R>)\n"
            f"**Reason:** `{msg}`"
            for display_num, db_id, msg, run_at in reminders_with_numbers
        ])

        view = ReminderListView(
            self,
            ctx.author.id,
            ctx.guild.id,
            reminders_with_numbers,
            source_interaction=ctx.interaction
        )

        await ctx.respond(text, view=view, ephemeral=True)
        return None

    @reminder.command(name="status", description="Reminder status")
    @commands.is_owner()
    async def status(self, ctx: discord.ApplicationContext):
        worker_alive = self.worker_task and not self.worker_task.done()
        scheduler_running = self.scheduler.running

        with sqlite3.connect(DB_PATH) as conn:
            pending = conn.execute(
                "SELECT COUNT(*) FROM reminders WHERE status='pending'"
            ).fetchone()[0]

        embed = discord.Embed(
            title="Reminder System Status",
            color=discord.Color.green() if worker_alive and scheduler_running else discord.Color.red()
        )
        embed.add_field(name="Worker Loop", value="✅ Running" if worker_alive else "❌ Not Running", inline=True)
        embed.add_field(name="Scheduler", value="✅ Running" if scheduler_running else "❌ Not Running", inline=True)
        embed.add_field(name="Pending Reminders", value=str(pending), inline=True)

        await ctx.respond(embed=embed, ephemeral=True)

    @reminder.command(name="test", description="Test reminder")
    @commands.is_owner()
    async def test(self, ctx: discord.ApplicationContext):
        await ctx.defer(ephemeral=True)

        run_at = int(time.time()) + 5
        now = int(time.time())

        with sqlite3.connect(DB_PATH) as conn:
            display_number = get_next_display_number(conn, ctx.guild.id)
            conn.execute("""
                INSERT INTO reminders
                (user_id, guild_id, channel_id, message, display_number, run_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                ctx.author.id,
                ctx.guild.id,
                ctx.channel.id,
                "🧪 Test reminder",
                display_number,
                run_at,
                now
            ))
            conn.commit()

        logger.info("Created test reminder #%s", display_number)

        await asyncio.sleep(1)

        await ctx.respond(
            "✅ Test reminder created – you will receive it in a few seconds. Check that you see it appear in this channel.",
            ephemeral=True
        )

    def cancel_reminder(self, user_id, guild_id, rid):
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.execute("""
                UPDATE reminders
                SET status='cancelled',
                    finished_at=?,
                    lock_token=NULL
                WHERE id=? AND user_id=? AND guild_id=? AND status='pending'
            """, (int(time.time()), rid, user_id, guild_id))
            conn.commit()

            if cur.rowcount > 0:
                logger.info(
                    "Cancelled reminder id=%s for user %s in guild %s",
                    rid,
                    user_id,
                    guild_id
                )

            return cur.rowcount > 0

    async def worker_loop(self):
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            try:
                now = time.time()
                processed_any = False

                while True:
                    lock_token = str(uuid.uuid4())

                    with sqlite3.connect(DB_PATH) as conn:
                        conn.execute("""
                            UPDATE reminders
                            SET status='processing',
                                lock_token=?
                            WHERE id IN (
                                SELECT id FROM reminders
                                WHERE status='pending'
                                  AND run_at <= ?
                                ORDER BY run_at ASC
                                LIMIT 1
                            )
                        """, (lock_token, int(now)))
                        conn.commit()

                        row = conn.execute("""
                            SELECT id, user_id, channel_id, message, retries, run_at, display_number
                            FROM reminders
                            WHERE status='processing'
                              AND lock_token=?
                        """, (lock_token,)).fetchone()

                    if not row:
                        break

                    processed_any = True
                    rid, uid, cid, msg, retries, run_at, display_num = row

                    try:
                        user = self.bot.get_user(uid)
                        if user is None:
                            user = await self.bot.fetch_user(uid)

                        delivered = False

                        try:
                            channel = self.bot.get_channel(cid)
                            if channel is None:
                                channel = await self.bot.fetch_channel(cid)

                            am = discord.AllowedMentions(
                                everyone=False,
                                roles=False,
                                users=True
                            )

                            await channel.send(
                                f"⏰ {user.mention} Reminder: `{msg}`",
                                allowed_mentions=am
                            )
                            delivered = True

                        except Exception as channel_error:
                            logger.warning(
                                "Channel send failed for reminder #%s, trying DM: %s",
                                display_num,
                                channel_error
                            )
                            try:
                                await user.send(f"⏰ Reminder: `{msg}`")
                                delivered = True
                                logger.info("Sent reminder #%s via DM", display_num)
                            except Exception as dm_error:
                                with sqlite3.connect(DB_PATH) as conn:
                                    conn.execute("""
                                        DELETE FROM reminders
                                        WHERE id=? AND lock_token=?
                                    """, (rid, lock_token))
                                    conn.commit()

                                logger.warning(
                                    "Reminder #%s not available user | channel failed: %s | dm failed: %s | reminder deleted",
                                    display_num,
                                    channel_error,
                                    dm_error
                                )
                                continue

                        if delivered:
                            sent_at = time.time()
                            diff = sent_at - run_at

                            if diff < 0:
                                logger.info("Sent reminder #%s | %.3fs early", display_num, -diff)
                            else:
                                logger.info("Sent reminder #%s | %.3fs late", display_num, diff)

                            with sqlite3.connect(DB_PATH) as conn:
                                conn.execute("""
                                    UPDATE reminders
                                    SET status='done',
                                        finished_at=?,
                                        lock_token=NULL
                                    WHERE id=? AND lock_token=?
                                """, (int(sent_at), rid, lock_token))
                                conn.commit()

                    except Exception as e:
                        retries += 1
                        logger.warning("Reminder #%s failed | retry=%s | error=%s", rid, retries, e)

                        if retries >= MAX_RETRIES:
                            with sqlite3.connect(DB_PATH) as conn:
                                conn.execute("""
                                    UPDATE reminders
                                    SET status='failed',
                                        finished_at=?,
                                        lock_token=NULL,
                                        retries=?,
                                        last_error=?
                                    WHERE id=? AND lock_token=?
                                """, (int(time.time()), retries, str(e), rid, lock_token))
                                conn.commit()

                            logger.error("Reminder #%s marked as failed", rid)
                        else:
                            delay = min(60 * (2 ** retries), 3600)
                            new_run = int(time.time() + delay)

                            with sqlite3.connect(DB_PATH) as conn:
                                conn.execute("""
                                    UPDATE reminders
                                    SET status='pending',
                                        retries=?,
                                        run_at=?,
                                        last_error=?,
                                        lock_token=NULL
                                    WHERE id=? AND lock_token=?
                                """, (retries, new_run, str(e), rid, lock_token))
                                conn.commit()

                if processed_any:
                    await asyncio.sleep(0)
                    continue

                with sqlite3.connect(DB_PATH) as conn:
                    next_run = conn.execute("""
                        SELECT MIN(run_at)
                        FROM reminders
                        WHERE status='pending'
                    """).fetchone()[0]

                if next_run is None:
                    await asyncio.sleep(1.0)
                    continue

                delay = max(0.05, min(1.0, next_run - time.time()))
                await asyncio.sleep(delay)

            except Exception:
                logger.exception("Worker loop crashed temporarily")
                await asyncio.sleep(1)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        try:
            with sqlite3.connect(DB_PATH) as conn:
                cur = conn.execute("""
                    DELETE FROM reminders
                    WHERE user_id=? AND guild_id=?
                """, (member.id, member.guild.id))
                conn.commit()

            if cur.rowcount > 0:
                logger.info(
                    "Removed reminders for user %s in guild %s",
                    member.id,
                    member.guild.id
                )

        except Exception:
            logger.exception("Failed to cleanup user reminders")


def setup(bot):
    bot.add_cog(Reminder(bot))
