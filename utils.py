COLS = 5  # пунші в рядку


def _extract_emoji(name: str) -> str:
    first = name.split()[0]
    # Якщо перший токен — не ASCII і не буква/цифра → емодзі
    return first if len(first) <= 2 and not first.isalnum() else "🟩"


def generate_card(name: str, current: int, target: int) -> str:
    emoji = _extract_emoji(name)
    empty = "⬜️"

    rows: list[str] = []
    for row_start in range(0, target, COLS):
        row_cells = []
        for i in range(row_start + 1, min(row_start + COLS, target) + 1):
            row_cells.append(emoji if i <= current else empty)
        rows.append(" ".join(row_cells))

    grid = "\n".join(rows)
    progress = f"📊 <b>{current}/{target}</b>"

    if current >= target:
        return (
            f"🏆 <b>ЦІЛЬ ВИКОНАНО:</b> {name}\n\n"
            f"{grid}\n\n"
            f"{progress}\n"
            f"Цей цикл закрито."
        )

    return (
        f"📌 <b>Активна ціль:</b> {name}\n\n"
        f"{grid}\n\n"
        f"{progress}"
    )


def goals_list_text(goals: list[tuple]) -> str:
    """Форматує список цілей (id, name, target, current, last_punch)."""
    if not goals:
        return "У тебе ще немає цілей. Створи першу через /goal"

    lines = ["<b>Твої цілі:</b>\n"]
    for goal_id, name, target, current, _ in goals:
        pct = int(current / target * 100)
        lines.append(f"• {name} — {current}/{target} ({pct}%)")
    return "\n".join(lines)