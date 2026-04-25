"""
KODED OS — Database Layer (aiosqlite)
Tables: tasks, opportunities, standup_log
"""

import aiosqlite
from config import DB_PATH


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                username    TEXT,
                context     TEXT,
                timezone    TEXT DEFAULT 'Africa/Lagos',
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                title       TEXT NOT NULL,
                track       TEXT DEFAULT 'general',
                due_time    TEXT,           -- e.g. "14:00" or NULL
                remind_at   TEXT,           -- scheduled reminder time
                done        INTEGER DEFAULT 0,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS opportunities (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                title       TEXT NOT NULL,
                type        TEXT DEFAULT 'general',  -- hackathon | internship | deadline | event
                deadline    TEXT,           -- ISO date "2025-05-30"
                notes       TEXT,
                done        INTEGER DEFAULT 0,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS standup_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                date        TEXT NOT NULL,
                type        TEXT NOT NULL,  -- morning | evening
                content     TEXT,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        """)
        # Migration: Add user_id column if it doesn't exist (for existing DBs)
        for table in ["tasks", "opportunities", "standup_log"]:
            try:
                await db.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER")
            except Exception:
                pass # Already exists
        await db.commit()


# ── User Settings ──────────────────────────────────────────────────────────

async def get_all_users() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users")
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_user(user_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def upsert_user(user_id: int, username: str = None, context: str = None, timezone: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        user = await get_user(user_id)
        if user:
            updates = []
            values = []
            if username is not None:
                updates.append("username = ?")
                values.append(username)
            if context is not None:
                updates.append("context = ?")
                values.append(context)
            if timezone is not None:
                updates.append("timezone = ?")
                values.append(timezone)
            
            if updates:
                set_clause = ", ".join(updates)
                values.append(user_id)
                await db.execute(f"UPDATE users SET {set_clause} WHERE user_id = ?", values)
        else:
            await db.execute(
                "INSERT INTO users (user_id, username, context, timezone) VALUES (?, ?, ?, ?)",
                (user_id, username, context, timezone or 'Africa/Lagos')
            )
        await db.commit()


# ── Tasks ──────────────────────────────────────────────────────────────────

async def add_task(user_id: int, title: str, track: str = "general", due_time: str = None, remind_at: str = None) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO tasks (user_id, title, track, due_time, remind_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, title, track, due_time, remind_at)
        )
        await db.commit()
        return cur.lastrowid


async def get_tasks(user_id: int, done: bool = False) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM tasks WHERE user_id = ? AND done = ? ORDER BY due_time ASC NULLS LAST, created_at ASC",
            (user_id, 1 if done else 0)
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def mark_task_done(user_id: int, task_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE tasks SET done = 1 WHERE id = ? AND user_id = ?", (task_id, user_id))
        await db.commit()


async def clear_tasks(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM tasks WHERE done = 0 AND user_id = ?", (user_id,))
        await db.commit()


# ── Opportunities ──────────────────────────────────────────────────────────

async def add_opportunity(user_id: int, title: str, opp_type: str = "general", deadline: str = None, notes: str = None) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO opportunities (user_id, title, type, deadline, notes) VALUES (?, ?, ?, ?, ?)",
            (user_id, title, opp_type, deadline, notes)
        )
        await db.commit()
        return cur.lastrowid


async def get_opportunities(user_id: int, done: bool = False) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM opportunities WHERE user_id = ? AND done = ? ORDER BY deadline ASC NULLS LAST",
            (user_id, 1 if done else 0)
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def mark_opportunity_done(user_id: int, opp_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE opportunities SET done = 1 WHERE id = ? AND user_id = ?", (opp_id, user_id))
        await db.commit()


# ── Standup Log ───────────────────────────────────────────────────────────

async def log_standup(user_id: int, date: str, standup_type: str, content: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO standup_log (user_id, date, type, content) VALUES (?, ?, ?, ?)",
            (user_id, date, standup_type, content)
        )
        await db.commit()


async def get_week_logs(user_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM standup_log WHERE user_id = ? AND created_at >= datetime('now', '-7 days') ORDER BY created_at ASC",
            (user_id,)
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

async def get_task_by_id(user_id: int, task_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id))
        row = await cur.fetchone()
        return dict(row) if row else None

async def update_task(user_id: int, task_id: int, **fields) -> bool:
    allowed = {"title", "track", "due_time", "remind_at", "notes", "done"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [task_id, user_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE tasks SET {set_clause} WHERE id = ? AND user_id = ?", values)
        await db.commit()
    return True

async def delete_task(user_id: int, task_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id))
        await db.commit()
        return cur.rowcount > 0

async def get_opportunity_by_id(user_id: int, opp_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM opportunities WHERE id = ? AND user_id = ?", (opp_id, user_id))
        row = await cur.fetchone()
        return dict(row) if row else None

async def update_opportunity(user_id: int, opp_id: int, **fields) -> bool:
    allowed = {"title", "type", "deadline", "notes", "link", "done"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [opp_id, user_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE opportunities SET {set_clause} WHERE id = ? AND user_id = ?", values)
        await db.commit()
    return True

async def delete_opportunity(user_id: int, opp_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("DELETE FROM opportunities WHERE id = ? AND user_id = ?", (opp_id, user_id))
        await db.commit()
        return cur.rowcount > 0
