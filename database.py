"""
KODED OS — Database Layer (aiosqlite)
Tables: tasks, opportunities, standup_log
"""

import aiosqlite
from config import DB_PATH


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                track       TEXT DEFAULT 'general',
                due_time    TEXT,           -- e.g. "14:00" or NULL
                remind_at   TEXT,           -- scheduled reminder time
                done        INTEGER DEFAULT 0,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS opportunities (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                type        TEXT DEFAULT 'general',  -- hackathon | internship | deadline | event
                deadline    TEXT,           -- ISO date "2025-05-30"
                notes       TEXT,
                done        INTEGER DEFAULT 0,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS standup_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                date        TEXT NOT NULL,
                type        TEXT NOT NULL,  -- morning | evening
                content     TEXT,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()


# ── Tasks ──────────────────────────────────────────────────────────────────

async def add_task(title: str, track: str = "general", due_time: str = None, remind_at: str = None) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO tasks (title, track, due_time, remind_at) VALUES (?, ?, ?, ?)",
            (title, track, due_time, remind_at)
        )
        await db.commit()
        return cur.lastrowid


async def get_tasks(done: bool = False) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM tasks WHERE done = ? ORDER BY due_time ASC NULLS LAST, created_at ASC",
            (1 if done else 0,)
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def mark_task_done(task_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE tasks SET done = 1 WHERE id = ?", (task_id,))
        await db.commit()


async def clear_tasks():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM tasks WHERE done = 0")
        await db.commit()


# ── Opportunities ──────────────────────────────────────────────────────────

async def add_opportunity(title: str, opp_type: str = "general", deadline: str = None, notes: str = None) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO opportunities (title, type, deadline, notes) VALUES (?, ?, ?, ?)",
            (title, opp_type, deadline, notes)
        )
        await db.commit()
        return cur.lastrowid


async def get_opportunities(done: bool = False) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM opportunities WHERE done = ? ORDER BY deadline ASC NULLS LAST",
            (1 if done else 0,)
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def mark_opportunity_done(opp_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE opportunities SET done = 1 WHERE id = ?", (opp_id,))
        await db.commit()


# ── Standup Log ───────────────────────────────────────────────────────────

async def log_standup(date: str, standup_type: str, content: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO standup_log (date, type, content) VALUES (?, ?, ?)",
            (date, standup_type, content)
        )
        await db.commit()


async def get_week_logs() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM standup_log WHERE created_at >= datetime('now', '-7 days') ORDER BY created_at ASC"
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

async def get_task_by_id(task_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

async def update_task(task_id: int, **fields) -> bool:
    allowed = {"title", "track", "due_time", "remind_at", "notes", "done"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [task_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE tasks SET {set_clause} WHERE id = ?", values)
        await db.commit()
    return True

async def delete_task(task_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        await db.commit()
        return cur.rowcount > 0

async def get_opportunity_by_id(opp_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM opportunities WHERE id = ?", (opp_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

async def update_opportunity(opp_id: int, **fields) -> bool:
    allowed = {"title", "type", "deadline", "notes", "link", "done"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [opp_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE opportunities SET {set_clause} WHERE id = ?", values)
        await db.commit()
    return True

async def delete_opportunity(opp_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("DELETE FROM opportunities WHERE id = ?", (opp_id,))
        await db.commit()
        return cur.rowcount > 0
