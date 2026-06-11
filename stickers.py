"""
stickers.py — стікери з паку NEWLIFE3_by_fStikBot.
file_id заповнюється автоматично при першому запуску через /loadstickers (адмін).
Поки file_id не завантажені — бот надсилає емодзі-замінники.
"""
import json
import os
import aiosqlite

DB_PATH = "tracker.db"

# Категорії стікерів і їх емодзі-замінники
STICKER_CATEGORIES = {
    "punch":     "💪",   # після пуншу
    "streak_3":  "🥉",
    "streak_7":  "🥈",
    "streak_14": "🥇",
    "streak_21": "💎",
    "streak_30": "👑",
    "finish":    "🏆",
    "morning":   "☀️",
    "fail":      "😤",
    "coach":     "🤖",
}

# file_id стікерів (заповнюється після /loadstickers)
_sticker_ids: dict[str, str] = {}


async def init_stickers_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS stickers (
                category TEXT PRIMARY KEY,
                file_id  TEXT NOT NULL
            )
        """)
        await db.commit()
    await _load_from_db()


async def _load_from_db() -> None:
    global _sticker_ids
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT category, file_id FROM stickers") as cur:
            rows = await cur.fetchall()
    _sticker_ids = {r[0]: r[1] for r in rows}


async def save_sticker(category: str, file_id: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO stickers (category, file_id) VALUES (?, ?)",
            (category, file_id),
        )
        await db.commit()
    _sticker_ids[category] = file_id


def get_sticker_id(category: str) -> str | None:
    return _sticker_ids.get(category)


def get_emoji(category: str) -> str:
    return STICKER_CATEGORIES.get(category, "✨")
