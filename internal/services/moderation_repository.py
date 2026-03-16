from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import aiosqlite


SCHEMA = (
    """CREATE TABLE IF NOT EXISTS cases (
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
    )""",
    """CREATE TABLE IF NOT EXISTS warnings (
        warning_id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        moderator_id INTEGER NOT NULL,
        reason TEXT,
        timestamp INTEGER NOT NULL,
        case_id INTEGER
    )""",
    """CREATE TABLE IF NOT EXISTS automod_config (
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
    )""",
    """CREATE TABLE IF NOT EXISTS mod_config (
        guild_id INTEGER PRIMARY KEY,
        log_channel_id INTEGER,
        auto_punish INTEGER DEFAULT 1,
        warn_threshold INTEGER DEFAULT 3,
        quarantine_role_id INTEGER
    )""",
    """CREATE TABLE IF NOT EXISTS badwords (
        word_id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        word TEXT NOT NULL,
        severity INTEGER DEFAULT 1
    )""",
    """CREATE TABLE IF NOT EXISTS appeals (
        appeal_id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_id INTEGER NOT NULL,
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        reason TEXT,
        timestamp INTEGER NOT NULL,
        status TEXT DEFAULT 'pending',
        reviewed_by INTEGER,
        review_note TEXT
    )""",
)


class ModerationRepository:
    def __init__(self, db_path: str = "Data/moderation.db"):
        self.db_path = db_path

    async def init_db(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            for statement in SCHEMA:
                await db.execute(statement)
            await db.commit()

    async def _execute(self, query: str, params: tuple = ()) -> int | None:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(query, params)
            await db.commit()
            return cursor.lastrowid

    async def _fetchone(self, query: str, params: tuple = ()) -> dict | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, params) as cursor:
                row = await cursor.fetchone()
        return dict(row) if row else None

    async def _fetchall(self, query: str, params: tuple = ()) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _timestamp() -> int:
        return int(datetime.now(timezone.utc).timestamp())

    @staticmethod
    def _upsert_query(table: str, fields: tuple[str, ...]) -> str:
        columns = ("guild_id", *fields)
        assignments = ", ".join(f"{field}=excluded.{field}" for field in fields)
        placeholders = ", ".join("?" for _ in columns)
        names = ", ".join(columns)
        return f"INSERT INTO {table} ({names}) VALUES ({placeholders}) ON CONFLICT(guild_id) DO UPDATE SET {assignments}"

    async def add_case(self, guild_id, user_id, moderator_id, action_type, reason=None, duration=None, message_id=None):
        return await self._execute(
            "INSERT INTO cases (guild_id, user_id, moderator_id, action_type, reason, timestamp, duration, message_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (guild_id, user_id, moderator_id, action_type, reason or "No reason provided", self._timestamp(), duration, message_id),
        )

    async def get_cases(self, guild_id, user_id=None, active_only=False):
        query = "SELECT * FROM cases WHERE guild_id = ?"
        params: list = [guild_id]
        if user_id is not None:
            query += " AND user_id = ?"
            params.append(user_id)
        if active_only:
            query += " AND active = 1"
        query += " ORDER BY case_id DESC"
        return await self._fetchall(query, tuple(params))

    async def get_case_by_id(self, case_id, guild_id):
        return await self._fetchone("SELECT * FROM cases WHERE case_id = ? AND guild_id = ?", (case_id, guild_id))

    async def close_case(self, case_id, guild_id):
        await self._execute("UPDATE cases SET active = 0 WHERE case_id = ? AND guild_id = ?", (case_id, guild_id))

    async def add_warning(self, guild_id, user_id, moderator_id, reason=None, case_id=None):
        return await self._execute(
            "INSERT INTO warnings (guild_id, user_id, moderator_id, reason, timestamp, case_id) VALUES (?, ?, ?, ?, ?, ?)",
            (guild_id, user_id, moderator_id, reason or "No reason provided", self._timestamp(), case_id),
        )

    async def get_warnings(self, guild_id, user_id):
        return await self._fetchall("SELECT * FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY timestamp DESC", (guild_id, user_id))

    async def clear_warnings(self, guild_id, user_id):
        await self._execute("DELETE FROM warnings WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))

    async def get_automod_config(self, guild_id):
        return await self._fetchone("SELECT * FROM automod_config WHERE guild_id = ?", (guild_id,))

    async def set_automod_config(self, guild_id, **kwargs):
        fields = tuple(kwargs.keys())
        await self._execute(self._upsert_query("automod_config", fields), (guild_id, *kwargs.values()))

    async def get_mod_config(self, guild_id):
        return await self._fetchone("SELECT * FROM mod_config WHERE guild_id = ?", (guild_id,))

    async def set_mod_config(self, guild_id, **kwargs):
        fields = tuple(kwargs.keys())
        await self._execute(self._upsert_query("mod_config", fields), (guild_id, *kwargs.values()))

    async def add_badword(self, guild_id, word, severity=1):
        await self._execute("INSERT INTO badwords (guild_id, word, severity) VALUES (?, ?, ?)", (guild_id, word.lower(), severity))

    async def remove_badword(self, guild_id, word):
        await self._execute("DELETE FROM badwords WHERE guild_id = ? AND word = ?", (guild_id, word.lower()))

    async def get_badwords(self, guild_id):
        return await self._fetchall("SELECT * FROM badwords WHERE guild_id = ?", (guild_id,))

    async def add_appeal(self, case_id, guild_id, user_id, reason):
        return await self._execute("INSERT INTO appeals (case_id, guild_id, user_id, reason, timestamp) VALUES (?, ?, ?, ?, ?)", (case_id, guild_id, user_id, reason, self._timestamp()))

    async def get_appeals(self, guild_id, status=None):
        if status:
            return await self._fetchall(
                "SELECT * FROM appeals WHERE guild_id = ? AND status = ? ORDER BY timestamp DESC",
                (guild_id, status),
            )
        return await self._fetchall(
            "SELECT * FROM appeals WHERE guild_id = ? ORDER BY timestamp DESC",
            (guild_id,),
        )

    async def update_appeal(self, appeal_id, status, reviewed_by=None, review_note=None):
        await self._execute(
            "UPDATE appeals SET status = ?, reviewed_by = ?, review_note = ? WHERE appeal_id = ?",
            (status, reviewed_by, review_note, appeal_id),
        )
