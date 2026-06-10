"""
ai_services.py — заглушка під інтеграцію з AI (Claude / GPT).

Підключення:
    pip install anthropic   # або openai

Розкоментуй потрібний клієнт і замінь generate_reminder на реальний виклик.
"""
from __future__ import annotations

import os
import random

# import anthropic  # pip install anthropic
# _client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# ---------------------------------------------------------------------------
# Нагадування
# ---------------------------------------------------------------------------

_HARD_REMINDERS = [
    "Час іде. Ціль «{goal}» сама себе не виконає. Зайди і постав пунш, або визнай, що здався.",
    "Вечірня перевірка. Ти сьогодні зробив крок до «{goal}»? Якщо ні — ти знаєш, чого варті твої обіцянки.",
    "Дисципліна — це робити те, що треба, коли не хочеться. Відкрий перфокарту «{goal}» і зафіксуй прогрес.",
    "Ще один день, ще одна можливість не злити. Ціль «{goal}» чекає.",
    "Без пуншу за «{goal}» сьогодні — це не відпочинок, це відкат. Рухайся.",
]


async def generate_reminder(goal_name: str) -> str:
    """
    Повертає рядок нагадування.

    --- Заміна на Claude ---
    message = await _client.messages.create(
        model="claude-opus-4-5",
        max_tokens=120,
        messages=[{
            "role": "user",
            "content": (
                f"Напиши жорстке, але коротке (~2 речення) мотиваційне нагадування "
                f"для людини, яка сьогодні ще не виконала свою ціль: «{goal_name}». "
                "Без пустих слів, тільки по суті. Мова — українська."
            )
        }]
    )
    return message.content[0].text
    """
    return random.choice(_HARD_REMINDERS).format(goal=goal_name)


# ---------------------------------------------------------------------------
# Аналіз прогресу (майбутнє)
# ---------------------------------------------------------------------------

async def analyze_progress(goal_name: str, current: int, target: int) -> str:
    """
    Повертає короткий AI-коментар до поточного прогресу.
    Поки що — статичний текст.
    """
    pct = int(current / target * 100)
    if pct == 0:
        return "Перший крок — найважчий. Зроби його сьогодні."
    if pct < 30:
        return f"Початок покладено. {target - current} кроків залишилось — не зупиняйся."
    if pct < 70:
        return f"Половину пройдено. Ще {target - current} — і ціль закрита."
    if pct < 100:
        return f"Фінальна пряма. {target - current} кроків до перемоги."
    return "Ціль закрита. Дисципліна — це результат."