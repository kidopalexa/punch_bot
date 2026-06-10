from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def punch_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Пунш", callback_data="punch_action")]
    ])


def goals_select_keyboard(goals: list[tuple]) -> InlineKeyboardMarkup:
    """
    goals: list of (id, goal_name, target_count, current_count, last_punch_date)
    Один рядок = одна ціль.
    """
    rows = []
    for goal_id, name, target, current, _ in goals:
        label = f"{name}  {current}/{target}"
        rows.append([
            InlineKeyboardButton(
                text=label,
                callback_data=f"punch_goal:{goal_id}"
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Скасувати", callback_data="cancel_fsm")]
    ])