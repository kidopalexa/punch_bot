import sqlite3
import aiosqlite
from datetime import date
from typing import Optional

DB_PATH = "tracker.db"

MAX_GOALS_PER_USER = 3


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS goals (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id          INTEGER NOT NULL,
                goal_name        TEXT    NOT NULL,
                target_count     INTEGER NOT NULL,
                current_count    INTEGER NOT NULL DEFAULT 0,
                last_punch_date  TEXT    NOT NULL DEFAULT '',
                created_at       TEXT    NOT NULL DEFAULT (date('now')),
                UNIQUE(user_id, goal_name)
            )
        """)
        await db.commit()


# ---------------------------------------------------------------------------
# Goals
# ---------------------------------------------------------------------------

async def count_user_goals(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM goals WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def save_goal(user_id: int, goal_name: str, target: int) -> bool:
    """Returns False if user already has MAX_GOALS_PER_USER active goals."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM goals WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            if row and row[0] >= MAX_GOALS_PER_USER:
                return False

        await db.execute(
            """
            INSERT OR REPLACE INTO goals
                (user_id, goal_name, target_count, current_count, last_punch_date)
            VALUES (?, ?, ?, 0, '')
            """,
            (user_id, goal_name, target),
        )
        await db.commit()
    return True


async def get_user_goals(user_id: int) -> list[tuple]:
    """Returns list of (id, goal_name, target_count, current_count, last_punch_date)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT id, goal_name, target_count, current_count, last_punch_date
            FROM goals WHERE user_id = ?
            ORDER BY created_at
            """,
            (user_id,),
        ) as cur:
            return await cur.fetchall()


async def get_goal_by_id(goal_id: int) -> Optional[tuple]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, user_id, goal_name, target_count, current_count, last_punch_date FROM goals WHERE id = ?",
            (goal_id,),
        ) as cur:
            return await cur.fetchone()


async def punch_goal(goal_id: int) -> None:
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE goals SET current_count = current_count + 1, last_punch_date = ? WHERE id = ?",
            (today, goal_id),
        )
        await db.commit()


async def delete_goal(goal_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
        await db.commit()


# ---------------------------------------------------------------------------
# Scheduler helpers
# ---------------------------------------------------------------------------

async def get_users_pending_punch() -> list[tuple]:
    """Returns (user_id, goal_name) for goals not punched today and not completed."""
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT DISTINCT user_id, goal_name
            FROM goals
            WHERE current_count < target_count
              AND (last_punch_date != ? OR last_punch_date = '')
            """,
            (today,),
        ) as cur:
            return await cur.fetchall()