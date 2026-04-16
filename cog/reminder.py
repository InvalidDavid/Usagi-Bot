import uuid
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# line 803 gets confused due to line 9, don't remove it.
from dataclasses import dataclass
from typing import Optional
from datetime import datetime, timedelta

from utils.imports import *

logger = logging.getLogger("bot.reminder")

DB_PATH = "Data/reminders.db"

MAX_RETRIES = 5
MIN_REMINDER_SECONDS = 5
MAX_PENDING_REMINDERS_PER_USER = 25

CREATE_COOLDOWN_RATE = 2
CREATE_COOLDOWN_PER = 20
LIST_COOLDOWN_RATE = 2
LIST_COOLDOWN_PER = 5

LIST_LIMIT = 25
REMINDER_MESSAGE_MAX_LEN = 500
DELIVERY_MESSAGE_MAX_LEN = 1800

VIEW_TIMEOUT = 180
CONFIRM_TIMEOUT = 30

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

TIME_RE = re.compile(r"(?<!\d)(\d{1,2}):(\d{2})(?!\d)")
DATE_RE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
DURATION_RE = re.compile(r"(\d+)\s*([a-zA-Z]+)")


@dataclass(slots=True)
class ReminderRow:
    id: int
    user_id: int
    guild_id: int
    channel_id: int
    message: str
    display_number: int
    run_at: int
    retries: int
    lock_token: str


def parse_duration(text: str) -> int:
    matches = DURATION_RE.findall(text)
    if not matches:
        return 0

    total = 0
    for value_str, unit_raw in matches:
        value = int(value_str)
        unit = unit_raw.lower()

        matched = None
        for key in sorted(UNIT_MAP.keys(), key=len, reverse=True):
            if unit.startswith(key):
                matched = key
                break

        if matched is None:
            continue

        total += value * UNIT_MAP[matched]

    return total


def next_weekday(now: datetime, target_idx: int) -> datetime:
    days_ahead = (target_idx - now.weekday() + 7) % 7
    if days_ahead == 0:
        days_ahead = 7
    return now + timedelta(days=days_ahead)


def parse_time(text: str) -> Optional[datetime]:
    if not text:
        return None

    raw = text.strip().lower()
    now = datetime.now()

    duration_input = raw[3:] if raw.startswith("in ") else raw
    seconds = parse_duration(duration_input)
    if seconds > 0:
        return now + timedelta(seconds=seconds)

    date_match = DATE_RE.search(raw)
    time_match = TIME_RE.search(raw)

    if date_match:
        year, month, day = map(int, date_match.groups())
        hour, minute = 0, 0
        if time_match:
            hour, minute = map(int, time_match.groups())
        try:
            return datetime(year, month, day, hour, minute)
        except ValueError:
            return None

    if "tomorrow" in raw:
        base = now + timedelta(days=1)
        if time_match:
            hour, minute = map(int, time_match.groups())
            try:
                return base.replace(hour=hour, minute=minute, second=0, microsecond=0)
            except ValueError:
                return None
        return base.replace(second=0, microsecond=0)

    if "today" in raw:
        if time_match:
            hour, minute = map(int, time_match.groups())
            try:
                return now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            except ValueError:
                return None

    for day_name, idx in WEEKDAYS.items():
        if f"next {day_name}" in raw:
            base = next_weekday(now, idx)
            if time_match:
                hour, minute = map(int, time_match.groups())
                try:
                    return base.replace(hour=hour, minute=minute, second=0, microsecond=0)
                except ValueError:
                    return None
            return base.replace(hour=9, minute=0, second=0, microsecond=0)

    exact_time = TIME_RE.fullmatch(raw)
    if exact_time:
        hour, minute = map(int, exact_time.groups())
        try:
            candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        except ValueError:
            return None

        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate

    return None


def escape_reason_for_block(text: str) -> str:
    return discord.utils.escape_markdown(text or "No message")


def format_reminders(reminders: list[tuple[int, int, str, int]]) -> str:
    return "\n\n".join(
        f"**`#{display_num}`**\n"
        f"**When:** <t:{run_at}:f> (<t:{run_at}:R>)\n"
        f"**Reason:** `{escape_reason_for_block(msg)[:150]}`"
        for display_num, _db_id, msg, run_at in reminders
    )


class ReminderListView(discord.ui.View):
    def __init__(self, cog: "Reminder", user_id: int, guild_id: int, reminders=None, source_interaction=None):
        super().__init__(timeout=VIEW_TIMEOUT)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.source_interaction = source_interaction
        self.build(reminders if reminders is not None else [])

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Not your reminders.", ephemeral=True)
            return False
        return True

    def build(self, reminders) -> None:
        self.clear_items()
        if reminders:
            self.add_item(ReminderSelect(self.cog, self.user_id, self.guild_id, reminders))

    async def refresh_message(self) -> None:
        if not self.source_interaction:
            return

        reminders = await self.cog.get_user_pending_reminders(self.user_id, self.guild_id)

        if not reminders:
            with contextlib.suppress(Exception):
                await self.source_interaction.edit_original_response(content="No reminders.", view=None)
            return

        self.build(reminders)

        try:
            await self.source_interaction.edit_original_response(
                content=format_reminders(reminders),
                view=self,
            )
        except discord.HTTPException:
            logger.exception("Failed to refresh reminder list message")

    async def on_timeout(self) -> None:
        if not self.source_interaction:
            return

        try:
            await self.source_interaction.edit_original_response(
                content="Timed out.",
                view=None,
            )
        except discord.NotFound:
            pass
        except discord.HTTPException:
            logger.exception("Failed to update reminder list view on timeout")


class ReminderSelect(discord.ui.Select):
    def __init__(self, cog: "Reminder", user_id: int, guild_id: int, reminders):
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.reminder_map = {
            display_num: db_id
            for display_num, db_id, _msg, _run_at in reminders
        }

        options = [
            discord.SelectOption(
                label=f"#{display_num}",
                description=(msg[:80] if msg else "No message"),
                value=str(display_num),
            )
            for display_num, _db_id, msg, _run_at in reminders[:25]
        ]

        super().__init__(placeholder="Select reminder", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Not your reminders.", ephemeral=True)
            return

        display_num = int(self.values[0])
        db_id = self.reminder_map.get(display_num)

        if db_id is None:
            await interaction.response.send_message("Reminder no longer exists.", ephemeral=True)
            return

        parent_view = self.view if isinstance(self.view, ReminderListView) else None
        view = ConfirmView(self.cog, self.user_id, self.guild_id, db_id, display_num, parent_view=parent_view)

        with contextlib.suppress(discord.HTTPException):
            await interaction.response.edit_message()

        msg = await interaction.followup.send(
            f"Cancel reminder `#{display_num}`?",
            view=view,
            ephemeral=True,
            wait=True,
        )
        view.message = msg


class ConfirmView(discord.ui.View):
    def __init__(self, cog: "Reminder", user_id: int, guild_id: int, db_id: int, display_num: int, parent_view=None):
        super().__init__(timeout=CONFIRM_TIMEOUT)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.db_id = db_id
        self.display_num = display_num
        self.parent_view = parent_view
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm Cancel", style=discord.ButtonStyle.red)
    async def confirm(self, _button, interaction: discord.Interaction):
        await interaction.response.defer()

        ok = await self.cog.cancel_reminder(self.user_id, self.guild_id, self.db_id)

        if ok:
            if self.parent_view:
                await self.parent_view.refresh_message()

            await interaction.edit_original_response(
                content=f"✅ Reminder #{self.display_num} cancelled.",
                view=None,
            )
        else:
            await interaction.edit_original_response(
                content="❌ Failed. It may already have fired or been removed.",
                view=None,
            )

    @discord.ui.button(label="Close", style=discord.ButtonStyle.grey)
    async def cancel(self, _button, interaction: discord.Interaction):
        await interaction.response.defer()
        await interaction.edit_original_response(content="Cancelled.", view=None)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

        if not self.message:
            return

        try:
            await self.message.edit(content="Timed out.", view=None)
        except discord.NotFound:
            pass
        except discord.HTTPException:
            logger.exception("Failed to update confirm view on timeout")


class Reminder(commands.Cog):
    reminder = discord.SlashCommandGroup("reminder", "Reminder system")

    def __init__(self, bot):
        self.bot = bot

        self.db: Optional[aiosqlite.Connection] = None
        self.db_lock = asyncio.Lock()

        self.worker_task: Optional[asyncio.Task] = None
        self.start_task: Optional[asyncio.Task] = None
        self.start_lock = asyncio.Lock()

        # Worker wake signal: set this whenever DB changes may affect the next due reminder.
        self.wake_event = asyncio.Event()
        self.started = asyncio.Event()
        self.shutting_down = False

        # Cached next due timestamp so the worker doesn't keep querying MIN(run_at) while idle.
        self.next_due_hint: Optional[int] = None

        self.scheduler = AsyncIOScheduler()
        self.scheduler.add_job(
            self.cleanup_job,
            "interval",
            hours=24,
            id="reminder_cleanup",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )

        self.start_task = self.bot.loop.create_task(self._startup())

    def cog_unload(self):
        self.shutting_down = True
        self.wake_worker()

        if self.scheduler.running:
            with contextlib.suppress(discord.HTTPException):
                self.scheduler.shutdown(wait=False)

        if self.worker_task and not self.worker_task.done():
            self.worker_task.cancel()

        if self.start_task and not self.start_task.done():
            self.start_task.cancel()

    # Prevent duplicate startup on reconnects / reload races.
    async def _startup(self):
        async with self.start_lock:
            if self.started.is_set():
                return

            try:
                await self.bot.wait_until_ready()
                await self._open_db()
                await self._init_db()
                await self._rebuild_next_due_hint()
                await self._reclaim_stuck()
                await self._cleanup_orphan_users()

                if not self.scheduler.running:
                    self.scheduler.start()
                    logger.info("Reminder scheduler started")

                if self.worker_task is None or self.worker_task.done():
                    self.worker_task = asyncio.create_task(self.worker_loop(), name="reminder-worker")
                    logger.warning(
                        "Reminder worker started | task_id=%s cog_id=%s",
                        id(self.worker_task),
                        id(self),
                    )

                self.started.set()
                self.wake_worker()

            except (aiosqlite.Error, discord.HTTPException, discord.Forbidden, discord.NotFound):
                await self._close_db()
                raise

    async def _open_db(self):
        self.db = await aiosqlite.connect(DB_PATH)
        self.db.row_factory = aiosqlite.Row

        # WAL improves read/write behavior for this async reminder DB.
        await self.db.execute("PRAGMA journal_mode=WAL")
        await self.db.execute("PRAGMA synchronous=NORMAL")
        await self.db.execute("PRAGMA foreign_keys=ON")
        await self.db.commit()

    async def _close_db(self):
        if self.db is None:
            return

        db = self.db
        self.db = None

        try:
            await db.close()
            logger.info("Reminder DB connection closed")
        except (aiosqlite.Error, discord.HTTPException, discord.Forbidden, discord.NotFound):
            logger.exception("Failed to close reminder DB connection")

    def wake_worker(self):
        self.wake_event.set()

    async def _execute(self, sql: str, params=()):
        if self.db is None:
            raise RuntimeError("Database is not initialized")

        async with self.db_lock:
            cursor = await self.db.execute(sql, params)
            return cursor

    async def _fetchone(self, sql: str, params=()):
        cursor = await self._execute(sql, params)
        return await cursor.fetchone()

    async def _fetchall(self, sql: str, params=()):
        cursor = await self._execute(sql, params)
        return await cursor.fetchall()

    async def _execute_commit(self, sql: str, params=()):
        if self.db is None:
            raise RuntimeError("Database is not initialized")

        async with self.db_lock:
            cursor = await self.db.execute(sql, params)
            await self.db.commit()
            return cursor

    async def _init_db(self):
        if self.db is None:
            raise RuntimeError("Database is not initialized")

        async with self.db_lock:
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    message TEXT NOT NULL,
                    display_number INTEGER NOT NULL,
                    run_at INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    finished_at INTEGER,
                    status TEXT NOT NULL DEFAULT 'pending',
                    retries INTEGER NOT NULL DEFAULT 0,
                    lock_token TEXT,
                    last_error TEXT,
                    delivered_at INTEGER
                )
            """)

            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS system_state (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

            # Backward-compatible migration for older reminder DB files.
            cursor = await self.db.execute("PRAGMA table_info(reminders)")
            cols = {row[1] for row in await cursor.fetchall()}

            if "finished_at" not in cols:
                await self.db.execute("ALTER TABLE reminders ADD COLUMN finished_at INTEGER")

            if "status" not in cols:
                await self.db.execute("ALTER TABLE reminders ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'")

            if "retries" not in cols:
                await self.db.execute("ALTER TABLE reminders ADD COLUMN retries INTEGER NOT NULL DEFAULT 0")

            if "lock_token" not in cols:
                await self.db.execute("ALTER TABLE reminders ADD COLUMN lock_token TEXT")

            if "last_error" not in cols:
                await self.db.execute("ALTER TABLE reminders ADD COLUMN last_error TEXT")

            if "delivered_at" not in cols:
                await self.db.execute("ALTER TABLE reminders ADD COLUMN delivered_at INTEGER")

            await self.db.execute("""
                CREATE INDEX IF NOT EXISTS idx_reminders_status_run_at
                ON reminders(status, run_at, id)
            """)

            await self.db.execute("""
                CREATE INDEX IF NOT EXISTS idx_reminders_user_guild_status
                ON reminders(user_id, guild_id, status)
            """)

            await self.db.execute("""
                CREATE INDEX IF NOT EXISTS idx_reminders_guild_display_status
                ON reminders(guild_id, display_number, status)
            """)

            await self.db.execute("""
                CREATE INDEX IF NOT EXISTS idx_reminders_lock_token
                ON reminders(lock_token)
            """)

            await self.db.execute("""
                CREATE INDEX IF NOT EXISTS idx_reminders_delivered_at
                ON reminders(delivered_at)
            """)

            await self.db.commit()

    async def get_state(self, key: str) -> Optional[str]:
        row = await self._fetchone("SELECT value FROM system_state WHERE key=?", (key,))
        return row["value"] if row else None

    async def set_state(self, key: str, value: str):
        await self._execute_commit("""
            INSERT INTO system_state (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """, (key, value))

    async def _rebuild_next_due_hint(self):
        self.next_due_hint = await self.get_next_pending_run_at()

    async def _update_next_due_hint_after_insert(self, run_at: int):
        if self.next_due_hint is None or run_at < self.next_due_hint:
            self.next_due_hint = run_at

    # Rebuild cached next due time after DB mutations that may change scheduling.
    async def _update_next_due_hint_after_mutation(self):
        self.next_due_hint = await self.get_next_pending_run_at()

    # Sleep until the next due reminder unless create/cancel/retry wakes the worker earlier.
    async def _wait_until_due_or_woken(self):
        next_run = self.next_due_hint

        if next_run is None:
            self.wake_event.clear()
            await self.wake_event.wait()
            return

        delay = max(0.0, next_run - time.time())
        self.wake_event.clear()

        if delay <= 0:
            return

        try:
            await asyncio.wait_for(self.wake_event.wait(), timeout=delay)
        except asyncio.TimeoutError:
            pass

    async def count_user_pending_reminders(self, user_id: int, guild_id: int) -> int:
        row = await self._fetchone("""
            SELECT COUNT(*) AS count
            FROM reminders
            WHERE user_id=? AND guild_id=? AND status='pending'
        """, (user_id, guild_id))
        return int(row["count"])

    async def get_user_pending_reminders(self, user_id: int, guild_id: int):
        rows = await self._fetchall("""
            SELECT id, message, run_at, display_number
            FROM reminders
            WHERE user_id=? AND guild_id=? AND status='pending'
            ORDER BY display_number
            LIMIT ?
        """, (user_id, guild_id, LIST_LIMIT))

        return [
            (row["display_number"], row["id"], row["message"], row["run_at"])
            for row in rows
        ]

    async def create_reminder_record(self, user_id: int, guild_id: int, channel_id: int, message: str, run_at: int) -> int:
        if self.db is None:
            raise RuntimeError("Database is not initialized")

        now = int(time.time())

        async with self.db_lock:
            cursor = await self.db.execute("""
                SELECT display_number
                FROM reminders
                WHERE guild_id=? AND status='pending'
                ORDER BY display_number
            """, (guild_id,))
            rows = await cursor.fetchall()

            taken = {row["display_number"] for row in rows}
            display_number = 1
            while display_number in taken:
                display_number += 1

            await self.db.execute("""
                INSERT INTO reminders
                (user_id, guild_id, channel_id, message, display_number, run_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                guild_id,
                channel_id,
                message,
                display_number,
                run_at,
                now,
            ))
            await self.db.commit()

        await self._update_next_due_hint_after_insert(run_at)
        self.wake_worker()
        return display_number

    async def cancel_reminder(self, user_id: int, guild_id: int, rid: int) -> bool:
        cur = await self._execute_commit("""
            UPDATE reminders
            SET status='cancelled',
                finished_at=?,
                lock_token=NULL
            WHERE id=? AND user_id=? AND guild_id=? AND status='pending'
        """, (int(time.time()), rid, user_id, guild_id))

        ok = cur.rowcount > 0
        if ok:
            logger.info(
                "Cancelled reminder id=%s for user=%s guild=%s",
                rid,
                user_id,
                guild_id,
            )
            await self._update_next_due_hint_after_mutation()
            self.wake_worker()

        return ok

    async def cleanup_job(self):
        try:
            now = int(time.time())
            last = await self.get_state("last_cleanup")

            if last and now - int(last) < 86400:
                logger.info("Cleanup skipped (already done within 24h)")
                return

            cutoff = now - 86400

            if self.db is None:
                return

            async with self.db_lock:
                cur = await self.db.execute("""
                    DELETE FROM reminders
                    WHERE status IN ('done', 'cancelled', 'failed')
                      AND finished_at IS NOT NULL
                      AND finished_at < ?
                """, (cutoff,))

                await self.db.execute("""
                    INSERT INTO system_state (key, value)
                    VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """, ("last_cleanup", str(now)))
                await self.db.commit()

            logger.info("Cleanup executed | removed %s rows", cur.rowcount)

        except aiosqlite.Error:
            logger.exception("Cleanup failed")

    # Reclaim reminders left in processing after crash/reload.
    async def _reclaim_stuck(self):
        cur = await self._execute_commit("""
            UPDATE reminders
            SET status='pending',
                lock_token=NULL
            WHERE status='processing'
        """)

        if cur.rowcount > 0:
            logger.warning("Reclaimed %s stuck reminders back to pending", cur.rowcount)
            await self._update_next_due_hint_after_mutation()
            self.wake_worker()
        else:
            logger.info("No stuck reminders to reclaim")

    async def _cleanup_orphan_users(self):
        await self.bot.wait_until_ready()

        rows = await self._fetchall("""
            SELECT DISTINCT user_id, guild_id
            FROM reminders
        """)

        removed_users = 0
        removed_rows = 0

        for row in rows:
            user_id = row["user_id"]
            guild_id = row["guild_id"]

            guild = self.bot.get_guild(guild_id)
            if guild is None:
                continue

            member = guild.get_member(user_id)
            if member is None:
                try:
                    await guild.fetch_member(user_id)
                except discord.NotFound:
                    cur = await self._execute_commit("""
                        DELETE FROM reminders
                        WHERE user_id=? AND guild_id=?
                    """, (user_id, guild_id))

                    if cur.rowcount > 0:
                        removed_users += 1
                        removed_rows += cur.rowcount
                except (discord.Forbidden, discord.HTTPException):
                    continue

        if removed_rows > 0:
            logger.info(
                "Orphan cleanup removed %s reminders from %s users",
                removed_rows,
                removed_users,
            )
            await self._update_next_due_hint_after_mutation()
            self.wake_worker()

    # Atomically claim one due reminder using a unique lock token.
    async def claim_next_due_reminder(self) -> Optional[ReminderRow]:
        if self.db is None:
            raise RuntimeError("Database is not initialized")

        lock_token = str(uuid.uuid4())
        now = int(time.time())

        async with self.db_lock:
            cur = await self.db.execute("""
                UPDATE reminders
                SET status='processing',
                    lock_token=?
                WHERE id = (
                    SELECT id
                    FROM reminders
                    WHERE status='pending'
                      AND run_at <= ?
                    ORDER BY run_at ASC, id ASC
                    LIMIT 1
                )
            """, (lock_token, now))
            await self.db.commit()

            if cur.rowcount == 0:
                return None

            cursor = await self.db.execute("""
                SELECT id, user_id, guild_id, channel_id, message, display_number, run_at, retries, lock_token
                FROM reminders
                WHERE status='processing' AND lock_token=?
            """, (lock_token,))
            row = await cursor.fetchone()

        if row is None:
            logger.warning("Claim succeeded but fetch returned no row | lock_token=%s", lock_token)
            return None

        return ReminderRow(
            id=row["id"],
            user_id=row["user_id"],
            guild_id=row["guild_id"],
            channel_id=row["channel_id"],
            message=row["message"],
            display_number=row["display_number"],
            run_at=row["run_at"],
            retries=row["retries"],
            lock_token=row["lock_token"],
        )

    # Duplicate-send guard: only the first worker that sets delivered_at may send.
    async def mark_delivering(self, reminder: ReminderRow) -> bool:
        cur = await self._execute_commit("""
            UPDATE reminders
            SET delivered_at=?
            WHERE id=? AND lock_token=? AND status='processing' AND delivered_at IS NULL
        """, (int(time.time()), reminder.id, reminder.lock_token))

        if cur.rowcount == 0:
            logger.warning(
                "mark_delivering affected 0 rows | reminder_id=%s lock_token=%s",
                reminder.id,
                reminder.lock_token,
            )
            return False

        return True

    async def mark_done(self, reminder: ReminderRow, finished_at: int):
        cur = await self._execute_commit("""
            UPDATE reminders
            SET status='done',
                finished_at=?,
                lock_token=NULL
            WHERE id=? AND lock_token=? AND status='processing'
        """, (finished_at, reminder.id, reminder.lock_token))

        if cur.rowcount == 0:
            logger.warning(
                "mark_done affected 0 rows | reminder_id=%s lock_token=%s",
                reminder.id,
                reminder.lock_token,
            )

        await self._update_next_due_hint_after_mutation()

    async def mark_retry_or_failed(self, reminder: ReminderRow, error_text: str):
        retries = reminder.retries + 1
        error_text = error_text[:1000]

        if retries >= MAX_RETRIES:
            cur = await self._execute_commit("""
                UPDATE reminders
                SET status='failed',
                    finished_at=?,
                    retries=?,
                    last_error=?,
                    lock_token=NULL
                WHERE id=? AND lock_token=? AND status='processing'
            """, (int(time.time()), retries, error_text, reminder.id, reminder.lock_token))

            if cur.rowcount == 0:
                logger.warning(
                    "mark_failed affected 0 rows | reminder_id=%s lock_token=%s",
                    reminder.id,
                    reminder.lock_token,
                )
            else:
                logger.error("Reminder %s marked as failed after %s retries", reminder.id, retries)

            await self._update_next_due_hint_after_mutation()
            return

        delay = min(60 * (2 ** retries), 3600)
        new_run = int(time.time() + delay)

        cur = await self._execute_commit("""
            UPDATE reminders
            SET status='pending',
                retries=?,
                run_at=?,
                last_error=?,
                lock_token=NULL
            WHERE id=? AND lock_token=? AND status='processing'
        """, (retries, new_run, error_text, reminder.id, reminder.lock_token))

        if cur.rowcount == 0:
            logger.warning(
                "retry update affected 0 rows | reminder_id=%s lock_token=%s",
                reminder.id,
                reminder.lock_token,
            )
        else:
            logger.warning(
                "Reminder %s scheduled for retry=%s in %ss",
                reminder.id,
                retries,
                delay,
            )

        self.next_due_hint = new_run if self.next_due_hint is None else min(self.next_due_hint, new_run)
        self.wake_worker()

    async def get_next_pending_run_at(self) -> Optional[int]:
        row = await self._fetchone("""
            SELECT MIN(run_at) AS next_run
            FROM reminders
            WHERE status='pending'
        """)
        return row["next_run"] if row and row["next_run"] is not None else None

    # Channel first, DM fallback if channel delivery fails.
    async def deliver_reminder(self, reminder: ReminderRow):
        user = self.bot.get_user(reminder.user_id)
        if user is None:
            user = await self.bot.fetch_user(reminder.user_id)

        allowed_mentions = discord.AllowedMentions(
            everyone=False,
            roles=False,
            users=True,
        )

        safe_message = discord.utils.escape_mentions(reminder.message)[:DELIVERY_MESSAGE_MAX_LEN]

        logger.warning(
            "Delivering reminder | reminder_id=%s display=%s lock=%s cog_id=%s task_id=%s",
            reminder.id,
            reminder.display_number,
            reminder.lock_token,
            id(self),
            id(asyncio.current_task()),
        )

        try:
            channel = self.bot.get_channel(reminder.channel_id)
            if channel is None:
                channel = await self.bot.fetch_channel(reminder.channel_id)

            await channel.send(
                f"⏰ {user.mention} Reminder: `{safe_message}`",
                allowed_mentions=allowed_mentions,
            )
            return
        except (discord.HTTPException, discord.Forbidden, discord.NotFound) as channel_error:
            logger.warning(
                "Channel send failed for reminder #%s, trying DM: %r",
                reminder.display_number,
                channel_error,
            )

        await user.send(f"⏰ Reminder: `{safe_message}`")
        logger.info("Sent reminder #%s via DM", reminder.display_number)

    async def worker_loop(self):
        await self.started.wait()

        try:
            while not self.bot.is_closed() and not self.shutting_down:
                try:
                    processed = False

                    while True:
                        reminder = await self.claim_next_due_reminder()
                        if reminder is None:
                            break

                        processed = True

                        try:
                            send_claim_ok = await self.mark_delivering(reminder)
                            if not send_claim_ok:
                                continue

                            await self.deliver_reminder(reminder)

                            sent_at = int(time.time())
                            drift = sent_at - reminder.run_at
                            logger.info(
                                "Sent reminder #%s | drift=%ss",
                                reminder.display_number,
                                drift,
                            )

                            await self.mark_done(reminder, sent_at)

                        except Exception as exc:
                            logger.warning(
                                "Reminder %s failed | next_retry=%s | error=%r",
                                reminder.id,
                                reminder.retries + 1,
                                exc,
                            )
                            await self.mark_retry_or_failed(reminder, str(exc))

                    if processed:
                        await asyncio.sleep(0)
                        continue

                    await self._wait_until_due_or_woken()

                except asyncio.CancelledError:
                    raise
                # Outer worker safety-net: keep the loop alive on recoverable runtime/API/DB failures.
                except (aiosqlite.Error, discord.HTTPException, discord.Forbidden, discord.NotFound, RuntimeError):
                    logger.exception("Worker loop crashed temporarily")
                    await asyncio.sleep(1)
        finally:
            # Last-resort shutdown cleanup for bot stop / cog reload.
            await self._close_db()

    @reminder.command(name="create", description="Create a new reminder")
    @commands.guild_only()
    @commands.cooldown(CREATE_COOLDOWN_RATE, CREATE_COOLDOWN_PER, commands.BucketType.user)
    async def create(
        self,
        ctx: discord.ApplicationContext,
        duration: discord.Option(str, description="When the reminder should trigger"),
        message: discord.Option(str, description="Reminder message"),
    ):
        if ctx.guild is None or ctx.channel is None:
            await ctx.respond("This command can only be used in a server channel.")
            return

        if not message or not message.strip():
            await ctx.respond("Message cannot be empty.")
            return

        message = message.strip()

        if len(message) > REMINDER_MESSAGE_MAX_LEN:
            await ctx.respond(f"Message too long. Max {REMINDER_MESSAGE_MAX_LEN} characters.")
            return

        target = parse_time(duration)
        if target is None:
            await ctx.respond(
                "Use a valid time like `10s`, `5m`, `2h`, `1d`, `tomorrow 14:00`, or `2026-04-20 09:30`."
            )
            return

        run_at = int(target.timestamp())
        now = int(time.time())

        if run_at - now < MIN_REMINDER_SECONDS:
            await ctx.respond(f"Reminder must be at least {MIN_REMINDER_SECONDS} seconds in the future.")
            return

        pending_count = await self.count_user_pending_reminders(ctx.author.id, ctx.guild.id)
        if pending_count >= MAX_PENDING_REMINDERS_PER_USER:
            await ctx.respond(
                f"You already have {MAX_PENDING_REMINDERS_PER_USER} pending reminders in this server."
            )
            return

        display_number = await self.create_reminder_record(
            user_id=ctx.author.id,
            guild_id=ctx.guild.id,
            channel_id=ctx.channel.id,
            message=message,
            run_at=run_at,
        )

        logger.info(
            "Created reminder #%s for user %s in guild %s",
            display_number,
            ctx.author.id,
            ctx.guild.id,
        )

        allowed_mentions = discord.AllowedMentions(
            everyone=False,
            roles=False,
            users=True,
        )

        await ctx.respond(
            f"✅ Reminder `#{display_number}` → <t:{run_at}:f>\n-# Reason: `{escape_reason_for_block(message)}`",
            allowed_mentions=allowed_mentions,
        )

    @reminder.command(name="list", description="List reminders")
    @commands.guild_only()
    @commands.cooldown(LIST_COOLDOWN_RATE, LIST_COOLDOWN_PER, commands.BucketType.user)
    async def list(self, ctx: discord.ApplicationContext):
        if ctx.guild is None:
            await ctx.respond("This command can only be used in a server.", ephemeral=True)
            return

        reminders = await self.get_user_pending_reminders(ctx.author.id, ctx.guild.id)

        if not reminders:
            await ctx.respond("No reminders.", ephemeral=True)
            return

        view = ReminderListView(
            self,
            ctx.author.id,
            ctx.guild.id,
            reminders,
            source_interaction=ctx.interaction,
        )

        await ctx.respond(format_reminders(reminders), view=view, ephemeral=True)

    @reminder.command(name="status", description="Reminder status")
    @commands.guild_only()
    @commands.is_owner()
    async def status(self, ctx: discord.ApplicationContext):
        row_pending = await self._fetchone("SELECT COUNT(*) AS count FROM reminders WHERE status='pending'")
        row_processing = await self._fetchone("SELECT COUNT(*) AS count FROM reminders WHERE status='processing'")
        next_run = self.next_due_hint

        worker_alive = self.worker_task is not None and not self.worker_task.done()
        scheduler_running = self.scheduler.running

        embed = discord.Embed(
            title="Reminder System Status",
            color=discord.Color.green() if worker_alive and scheduler_running else discord.Color.red(),
        )
        embed.add_field(name="Worker Loop", value="✅ Running" if worker_alive else "❌ Not Running", inline=True)
        embed.add_field(name="Scheduler", value="✅ Running" if scheduler_running else "❌ Not Running", inline=True)
        embed.add_field(name="Pending", value=str(row_pending["count"]), inline=True)
        embed.add_field(name="Processing", value=str(row_processing["count"]), inline=True)
        embed.add_field(
            name="Next Reminder",
            value=f"<t:{next_run}:f> (<t:{next_run}:R>)" if next_run else "None",
            inline=False,
        )

        await ctx.respond(embed=embed, ephemeral=True)

    @reminder.command(name="test", description="Test reminder")
    @commands.guild_only()
    @commands.is_owner()
    async def test(self, ctx: discord.ApplicationContext):
        if ctx.guild is None or ctx.channel is None:
            await ctx.respond("This command can only be used in a server channel.", ephemeral=True)
            return

        run_at = int(time.time()) + 5

        display_number = await self.create_reminder_record(
            user_id=ctx.author.id,
            guild_id=ctx.guild.id,
            channel_id=ctx.channel.id,
            message="🧪 Test reminder",
            run_at=run_at,
        )

        logger.info("Created test reminder #%s", display_number)

        await ctx.respond(
            "✅ Test reminder created. You should receive it in a few seconds.",
            ephemeral=True,
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        try:
            cur = await self._execute_commit("""
                DELETE FROM reminders
                WHERE user_id=? AND guild_id=?
            """, (member.id, member.guild.id))

            if cur.rowcount > 0:
                logger.info(
                    "Removed reminders for user %s in guild %s",
                    member.id,
                    member.guild.id,
                )
                await self._update_next_due_hint_after_mutation()
                self.wake_worker()

        except (aiosqlite.Error, discord.HTTPException):
            logger.exception("Failed to cleanup user reminders")


def setup(bot):
    bot.add_cog(Reminder(bot))
