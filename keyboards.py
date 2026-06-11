from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def punch_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Пунш", callback_data="punch_action")]
    ])


def goals_select_keyboard(goals: list[tuple]) -> InlineKeyboardMarkup:
    rows = []
    for goal in goals:
        goal_id, name, target, current = goal[0], goal[1], goal[2], goal[3]
        rows.append([
            InlineKeyboardButton(
                text=f"{name}  {current}/{target}",
                callback_data=f"punch_goal:{goal_id}"
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Скасувати", callback_data="cancel_fsm")]
    ])
