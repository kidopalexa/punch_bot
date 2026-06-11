import aiosqlite
from datetime import date, timedelta
from typing import Optional

DB_PATH = "tracker.db"

MAX_GOALS_PER_USER = 3

STREAK_BADGES = {
    3:  "🥉 Серія 3 дні",
    7:  "🥈 Серія 7 днів",
    14: "🥇 Серія 14 днів",
    21: "💎 Серія 21 день",
    30: "👑 Серія 30 днів",
}


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
                streak           INTEGER NOT NULL DEFAULT 0,
                created_at       TEXT    NOT NULL DEFAULT (date('now')),
                UNIQUE(user_id, goal_name)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS challenges (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                goal_name    TEXT    NOT NULL,
                target_count INTEGER NOT NULL,
                user1_id     INTEGER NOT NULL,
                user2_id     INTEGER NOT NULL,
                user1_count  INTEGER NOT NULL DEFAULT 0,
                user2_count  INTEGER NOT NULL DEFAULT 0,
                user1_last   TEXT    NOT NULL DEFAULT '',
                user2_last   TEXT    NOT NULL DEFAULT '',
                winner_id    INTEGER,
                created_at   TEXT    NOT NULL DEFAULT (date('now'))
            )
        """)
        # Migrate: add streak column if missing
        try:
            await db.execute("ALTER TABLE goals ADD COLUMN streak INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass
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
                (user_id, goal_name, target_count, current_count, last_punch_date, streak)
            VALUES (?, ?, ?, 0, '', 0)
            """,
            (user_id, goal_name, target),
        )
        await db.commit()
    return True


async def get_user_goals(user_id: int) -> list[tuple]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT id, goal_name, target_count, current_count, last_punch_date, streak
            FROM goals WHERE user_id = ?
            ORDER BY created_at
            """,
            (user_id,),
        ) as cur:
            return await cur.fetchall()


async def get_goal_by_id(goal_id: int) -> Optional[tuple]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT id, user_id, goal_name, target_count, current_count,
                      last_punch_date, streak FROM goals WHERE id = ?""",
            (goal_id,),
        ) as cur:
            return await cur.fetchone()


async def punch_goal(goal_id: int) -> int:
    """Returns new streak value."""
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT last_punch_date, streak FROM goals WHERE id = ?", (goal_id,)
        ) as cur:
            row = await cur.fetchone()
        last, streak = row if row else ('', 0)
        new_streak = (streak + 1) if last == yesterday else 1
        await db.execute(
            """UPDATE goals
               SET current_count = current_count + 1,
                   last_punch_date = ?,
                   streak = ?
               WHERE id = ?""",
            (today, new_streak, goal_id),
        )
        await db.commit()
    return new_streak


async def delete_goal(goal_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
        await db.commit()


async def get_users_pending_punch() -> list[tuple]:
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


# ---------------------------------------------------------------------------
# Challenges
# ---------------------------------------------------------------------------

async def create_challenge(goal_name: str, target: int, user1_id: int, user2_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO challenges (goal_name, target_count, user1_id, user2_id)
               VALUES (?, ?, ?, ?)""",
            (goal_name, target, user1_id, user2_id),
        )
        await db.commit()
        return cur.lastrowid


async def get_challenge(challenge_id: int) -> Optional[tuple]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT * FROM challenges WHERE id = ?", (challenge_id,)
        ) as cur:
            return await cur.fetchone()


async def get_user_challenges(user_id: int) -> list[tuple]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT * FROM challenges
               WHERE (user1_id = ? OR user2_id = ?) AND winner_id IS NULL""",
            (user_id, user_id),
        ) as cur:
            return await cur.fetchall()


async def punch_challenge(challenge_id: int, user_id: int) -> tuple[int, int, bool]:
    """Returns (new_count, target, is_winner)."""
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT * FROM challenges WHERE id = ?", (challenge_id,)
        ) as cur:
            ch = await cur.fetchone()
        if not ch:
            return 0, 0, False

        # ch: id, goal_name, target_count, user1_id, user2_id,
        #     user1_count, user2_count, user1_last, user2_last, winner_id, created_at
        _, goal_name, target, u1, u2, u1c, u2c, u1l, u2l, winner, _ = ch

        if user_id == u1:
            if u1l == today:
                return u1c, target, False
            new_count = u1c + 1
            await db.execute(
                "UPDATE challenges SET user1_count = ?, user1_last = ? WHERE id = ?",
                (new_count, today, challenge_id),
            )
        else:
            if u2l == today:
                return u2c, target, False
            new_count = u2c + 1
            await db.execute(
                "UPDATE challenges SET user2_count = ?, user2_last = ? WHERE id = ?",
                (new_count, today, challenge_id),
            )

        is_winner = new_count >= target
        if is_winner:
            await db.execute(
                "UPDATE challenges SET winner_id = ? WHERE id = ?",
                (user_id, challenge_id),
            )
        await db.commit()
    return new_count, target, is_winner