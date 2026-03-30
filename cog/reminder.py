import uuid
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from utils.imports import *

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
        seconds = parse_duration(raw.replace("in ", ""))

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
        return now.replace(hour=h, minute=mi, second=0, microsecond=0)

    if seconds:
        return now + timedelta(seconds=seconds)

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

        view = ConfirmView(self.cog, self.user_id, self.guild_id, db_id, display_num)

        await interaction.response.send_message(
            f"Cancel reminder `#{display_num}`?",
            view=view,
            ephemeral=True
        )

        view.message = await interaction.original_response()


class ConfirmView(discord.ui.View):
    def __init__(self, cog, user_id, guild_id, db_id, display_num):
        super().__init__(timeout=30)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.db_id = db_id
        self.display_num = display_num
        self.message = None

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

        try:
            if self.message:
                await self.message.edit(content="⌛ Timeout — no action taken", view=self)
        except:
            pass

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.red)
    async def confirm(self, button, interaction: discord.Interaction):
        await interaction.response.defer()

        ok = self.cog.cancel_reminder(self.user_id, self.guild_id, self.db_id)

        if ok:
            await interaction.edit_original_response(
                content=f"✅ Reminder #{self.display_num} cancelled",
                view=None
            )
        else:
            await interaction.edit_original_response(
                content="❌ Failed",
                view=None
            )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.grey)
    async def cancel(self, button, interaction: discord.Interaction):
        await interaction.response.defer()

        await interaction.edit_original_response(
            content="❌ Cancelled",
            view=None
        )


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

    async def _cleanup_orphan_users(self):
        await self.bot.wait_until_ready()

        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute("""
                SELECT DISTINCT user_id, guild_id FROM reminders
            """).fetchall()

            removed = 0

            for user_id, guild_id in rows:
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    continue

                member = guild.get_member(user_id)
                if member is None:
                    conn.execute("""
                        DELETE FROM reminders
                        WHERE user_id=? AND guild_id=?
                    """, (user_id, guild_id))
                    removed += 1

            conn.commit()


    async def _start_scheduler_safe(self):
        await self.bot.wait_until_ready()

        if not self.scheduler.running:
            self.scheduler.start()
            print("🟢 Scheduler started safely")

    async def cleanup_job(self):
        try:
            now = int(time.time())

            with sqlite3.connect(DB_PATH) as conn:
                last = get_state(conn, "last_cleanup")

                if last and now - int(last) < 86400:
                    print("🧹 Cleanup skipped (already done within 24h)")
                    return

                cutoff = now - 86400

                conn.execute("""
                    DELETE FROM reminders
                    WHERE status IN ('done', 'cancelled')
                      AND created_at < ?
                """, (cutoff,))

                set_state(conn, "last_cleanup", str(now))
                conn.commit()

            print("🧹 Cleanup executed + timestamp stored")

        except Exception as e:
            print(f"❌ Cleanup failed: {e}")

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

    async def _auto_start_worker(self):
        await self.bot.wait_until_ready()
        if not self.worker_task or self.worker_task.done():
            self.worker_task = asyncio.create_task(self.worker_loop())

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
            conn.commit()


    reminder = discord.SlashCommandGroup("reminder", "Remind system")

    @reminder.command(name="create", description="Create a new reminder")
    async def create(self, ctx: discord.ApplicationContext, duration: str, message: str):
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
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute("""
                SELECT id, message, run_at, display_number
                FROM reminders
                WHERE user_id=? AND guild_id=? AND status='pending'
                ORDER BY display_number
            """, (ctx.author.id, ctx.guild.id)).fetchall()

        if not rows:
            return await ctx.respond("No reminders", ephemeral=True)

        reminders_with_numbers = [
            (r[3], r[0], r[1], r[2])
            for r in rows[:25]
        ]

        text = "\n".join([
            f"`#{display_num}` → <t:{run_at}:f> (<t:{run_at}:R>) | {msg}"
            for display_num, db_id, msg, run_at in reminders_with_numbers
        ])

        view = discord.ui.View()
        view.add_item(ReminderSelect(self, ctx.author.id, ctx.guild.id, reminders_with_numbers))

        return await ctx.respond(text, view=view, ephemeral=True)

    @reminder.command(name="status", description="Reminder status")
    @commands.is_owner()
    async def status(self, ctx: discord.ApplicationContext):
        worker_alive = self.worker_task and not self.worker_task.done()
        scheduler_running = self.scheduler.running

        with sqlite3.connect(DB_PATH) as conn:
            pending = conn.execute("SELECT COUNT(*) FROM reminders WHERE status='pending'").fetchone()[0]

        embed = discord.Embed(title="Reminder System Status",
                              color=discord.Color.green() if worker_alive and scheduler_running else discord.Color.red())
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

        await asyncio.sleep(1)

        await ctx.respond(
            f"✅ Test reminder created – you will receive it in a few seconds. Check that you see it appear in this channel.",
            ephemeral=True)

    def cancel_reminder(self, user_id, guild_id, rid):
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.execute("""
                UPDATE reminders
                SET status='cancelled'
                WHERE id=? AND user_id=? AND guild_id=? AND status='pending'
            """, (rid, user_id, guild_id))
            conn.commit()
            return cur.rowcount > 0

    async def worker_loop(self):
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            try:
                now = int(time.time())

                lock_token = str(uuid.uuid4())

                with sqlite3.connect(DB_PATH) as conn:
                    conn.execute("""
                        UPDATE reminders
                        SET status='processing',
                            lock_token=?
                        WHERE id = (
                            SELECT id FROM reminders
                            WHERE status='pending'
                              AND run_at <= ?
                            ORDER BY run_at ASC
                            LIMIT 1
                        )
                    """, (lock_token, now))
                    conn.commit()

                    row = conn.execute("""
                        SELECT id, user_id, channel_id, message, retries, run_at, display_number
                        FROM reminders
                        WHERE status='processing'
                          AND lock_token=?
                    """, (lock_token,)).fetchone()

                    next_run = conn.execute("""
                        SELECT MIN(run_at)
                        FROM reminders
                        WHERE status='pending'
                    """).fetchone()[0]

                if not row:
                    if next_run:
                        sleep_for = max(1, min(30, next_run - now))
                    else:
                        sleep_for = 5

                    await asyncio.sleep(sleep_for)
                    continue

                rid, uid, cid, msg, retries, run_at, display_num = row

                try:
                    channel = self.bot.get_channel(cid) or await self.bot.fetch_channel(cid)
                    user = await self.bot.fetch_user(uid)

                    am = discord.AllowedMentions(
                        everyone=False,
                        roles=False,
                        users=True
                    )
                    await channel.send(f"⏰ {user.mention} Reminder: `{msg}`", allowed_mentions=am)

                    sent_at = int(time.time())
                    diff = sent_at - run_at

                    if diff < 0:
                        print(f"✅ Sent reminder #{display_num} | in {-diff}s")
                    else:
                        print(f"✅ Sent reminder #{display_num} | {diff}s late")


                    with sqlite3.connect(DB_PATH) as conn:
                        conn.execute("""
                            UPDATE reminders
                            SET status='done'
                            WHERE id=? AND lock_token=?
                        """, (rid, lock_token))
                        conn.commit()

                except Exception as e:
                    retries += 1

                    print(f"❌ Reminder #{rid} failed | retry={retries}")

                    if retries >= MAX_RETRIES:
                        with sqlite3.connect(DB_PATH) as conn:
                            conn.execute("""
                                UPDATE reminders
                                SET status='failed'
                                WHERE id=? AND lock_token=?
                            """, (rid, lock_token))
                            conn.commit()

                    else:
                        delay = min(60 * (2 ** retries), 3600)
                        new_run = int(time.time()) + delay

                        with sqlite3.connect(DB_PATH) as conn:
                            conn.execute("""
                                UPDATE reminders
                                SET status='pending',
                                    retries=?,
                                    run_at=?,
                                    last_error=?
                                WHERE id=? AND lock_token=?
                            """, (retries, new_run, str(e), rid, lock_token))
                            conn.commit()

            except Exception:
                await asyncio.sleep(5)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("""
                    DELETE FROM reminders
                    WHERE user_id=? AND guild_id=?
                """, (member.id, member.guild.id))
                conn.commit()

            print(f"🗑️ Removed reminders for user {member.id} in guild {member.guild.id}")

        except Exception as e:
            print(f"❌ Failed to cleanup user reminders: {e}")

def setup(bot):
    bot.add_cog(Reminder(bot))
