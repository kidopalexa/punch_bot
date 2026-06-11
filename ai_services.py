import os
import random

try:
    import anthropic
    _client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    AI_ENABLED = bool(os.getenv("ANTHROPIC_API_KEY"))
except ImportError:
    _client = None
    AI_ENABLED = False

_HARD_REMINDERS = [
    "Час іде. Ціль «{goal}» сама себе не виконає. Зайди і постав пунш, або визнай, що здався.",
    "Вечірня перевірка. Ти сьогодні зробив крок до «{goal}»? Якщо ні — ти знаєш, чого варті твої обіцянки.",
    "Дисципліна — це робити те, що треба, коли не хочеться. Відкрий перфокарту «{goal}» і зафіксуй прогрес.",
    "Ще один день, ще одна можливість не злити. Ціль «{goal}» чекає.",
]

_PROGRESS_TEXTS = [
    "Перший крок — найважчий. Зроби його сьогодні.",
    "Початок покладено. Не зупиняйся.",
    "Половину пройдено. Ще трохи — і ціль закрита.",
    "Фінальна пряма. Не здавайся.",
    "Ціль закрита. Дисципліна — це результат.",
]


async def _ask_claude(prompt: str, max_tokens: int = 120) -> str:
    if not AI_ENABLED or not _client:
        return ""
    try:
        msg = await _client.messages.create(
            model="claude-opus-4-5",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text
    except Exception:
        return ""


async def generate_reminder(goal_name: str) -> str:
    result = await _ask_claude(
        f"Напиши жорстке, але коротке (2 речення) нагадування "
        f"для людини, яка сьогодні не виконала свою ціль: «{goal_name}». "
        "Без пустих слів, тільки по суті. Мова — українська."
    )
    return result or random.choice(_HARD_REMINDERS).format(goal=goal_name)


async def analyze_progress(goal_name: str, current: int, target: int) -> str:
    pct = int(current / target * 100)
    result = await _ask_claude(
        f"Людина виконала {current} з {target} кроків ({pct}%) до цілі «{goal_name}». "
        "Напиши одне коротке мотиваційне речення. Жорстко і по суті. Українська мова.",
        max_tokens=80,
    )
    if result:
        return result
    idx = min(int(pct / 25), len(_PROGRESS_TEXTS) - 1)
    return _PROGRESS_TEXTS[idx]


async def coach_answer(question: str, goals_summary: str) -> str:
    result = await _ask_claude(
        f"Ти — жорсткий, але справедливий коуч з дисципліни. "
        f"Поточні цілі користувача: {goals_summary}. "
        f"Питання: {question}\n"
        "Дай конкретну, коротку (3-4 речення) відповідь. Без води. Українська мова.",
        max_tokens=200,
    )
    return result or "Зосередься на своїх цілях і зроби наступний крок. Питання зайві — дія головна."