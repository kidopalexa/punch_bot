import os
import random
import json

try:
    import anthropic
    _client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    AI_ENABLED = bool(os.getenv("ANTHROPIC_API_KEY"))
except ImportError:
    _client = None
    AI_ENABLED = False

_HARD_REMINDERS = [
    "Час іде. Ціль «{goal}» сама себе не виконає. Зайди і постав пунш.",
    "Вечірня перевірка. Ти зробив крок до «{goal}»? Якщо ні — повертайся.",
    "Дисципліна — робити те, що треба, коли не хочеться. «{goal}» чекає.",
    "Ще один день, ще одна можливість не злити. Ціль «{goal}» чекає.",
]

_PROGRESS_TEXTS = [
    "Перший крок — найважчий. Зроби його сьогодні.",
    "Початок покладено. Не зупиняйся.",
    "Половину пройдено. Ще трохи — і ціль закрита.",
    "Фінальна пряма. Не здавайся.",
    "Ціль закрита. Дисципліна — це результат.",
]

COACH_SYSTEM = (
    "Ти — жорсткий, але справедливий особистий коуч з дисципліни і продуктивності. "
    "Стиль: конкретно, без води, по суті. Не підлизуєшся, не жалієш. "
    "Завжди відповідаєш українською мовою. Максимум 4 речення. "
    "Якщо скаржиться — даєш конкретний крок. Якщо питає — одну чітку дію."
)


async def _ask_claude(prompt: str, max_tokens: int = 200, system: str = COACH_SYSTEM) -> str:
    if not AI_ENABLED or not _client:
        return ""
    try:
        msg = await _client.messages.create(
            model="claude-opus-4-5",
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception:
        return ""


async def generate_reminder(goal_name: str) -> str:
    result = await _ask_claude(
        f"Людина не виконала сьогодні ціль: «{goal_name}». Нагадай жорстко і коротко."
    )
    return result or random.choice(_HARD_REMINDERS).format(goal=goal_name)


async def analyze_progress(goal_name: str, current: int, target: int) -> str:
    pct = int(current / target * 100)
    result = await _ask_claude(
        f"Людина виконала {current} з {target} кроків ({pct}%) до цілі «{goal_name}». "
        "Одне речення — реакція коуча.",
        max_tokens=80,
    )
    if result:
        return result
    idx = min(int(pct / 25), len(_PROGRESS_TEXTS) - 1)
    return _PROGRESS_TEXTS[idx]


async def coach_reply(user_message: str, goals_summary: str) -> str:
    result = await _ask_claude(
        f"Поточні цілі користувача: {goals_summary}.\n\nПовідомлення: {user_message}",
        max_tokens=250,
    )
    return result or "Зосередься на своїх цілях і зроби наступний крок."


async def morning_briefing(goals: list) -> str:
    if not goals:
        return "Сьогодні у тебе немає активних цілей. Створи нову через /goal і починай."
    goals_text = "\n".join(f"- {g[1]}: {g[3]}/{g[2]} виконано" for g in goals)
    result = await _ask_claude(
        f"Ранок. Ось цілі користувача:\n{goals_text}\n\n"
        "Дай короткий (3-4 речення) ранковий брифінг: що пріоритетно сьогодні і один конкретний крок.",
        max_tokens=200,
    )
    if result:
        return result
    lines = []
    for g in goals:
        pct = int(g[3] / g[2] * 100)
        lines.append(f"• {g[1]} — {pct}% виконано")
    lines.append("\nЗроби сьогодні хоча б один пунш по кожній цілі.")
    return "\n".join(lines)


async def voice_intent(text: str, goals_summary: str) -> dict:
    result = await _ask_claude(
        f"Цілі користувача: {goals_summary}\n"
        f"Текст: \"{text}\"\n\n"
        "Визнач намір. Якщо людина каже що виконала щось — intent=punch. "
        "Якщо питає — intent=question. Інакше — intent=other.\n"
        "Якщо punch — вкажи goal_hint (яку ціль найімовірніше виконала).\n"
        'Відповідай ТІЛЬКИ JSON: {"intent": "punch", "goal_hint": "назва"}',
        max_tokens=80,
        system="Відповідай тільки валідним JSON без зайвого тексту.",
    )
    try:
        clean = result.strip().strip("```json").strip("```").strip()
        return json.loads(clean)
    except Exception:
        return {"intent": "other", "goal_hint": ""}
