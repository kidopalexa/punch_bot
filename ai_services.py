import os
import anthropic

_client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


async def generate_reminder(goal_name: str) -> str:
    message = await _client.messages.create(
        model="claude-opus-4-5",
        max_tokens=120,
        messages=[{
            "role": "user",
            "content": (
                f"Напиши жорстке, але коротке (2 речення) нагадування "
                f"для людини, яка сьогодні не виконала свою ціль: «{goal_name}». "
                "Без пустих слів, тільки по суті. Мова — українська."
            )
        }]
    )
    return message.content[0].text


async def analyze_progress(goal_name: str, current: int, target: int) -> str:
    pct = int(current / target * 100)
    message = await _client.messages.create(
        model="claude-opus-4-5",
        max_tokens=80,
        messages=[{
            "role": "user",
            "content": (
                f"Людина виконала {current} з {target} кроків ({pct}%) до цілі «{goal_name}». "
                "Напиши одне коротке мотиваційне речення. Жорстко і по суті. Українська мова."
            )
        }]
    )
    return message.content[0].text