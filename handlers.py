import os
from datetime import date

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton

import database as db
import utils
import keyboards as kb
import ai_services
from states import GoalCreation

router = Router()

# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------

@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    manifesto = (
        "🏴 <b>ПУНШ-КАРТА ДИСЦИПЛІНИ</b>\n\n"
        "Цей бот не буде тебе жаліти чи мотивувати. "
        "Мотивація зникає після першого ж важкого дня. "
        "Залишається лише система і звітність.\n\n"
        "<b>Твій алгоритм:</b>\n"
        "▪️ <b>Максимум 3 цілі.</b> Більше — ілюзія продуктивності.\n"
        "▪️ <b>Один день = один пунш.</b> Наздогнати неможливо.\n"
        "▪️ <b>Щовечора о 20:00</b> система нагадає про тих, хто ще не відмітився.\n\n"
        "<b>Команди:</b>\n"
        "/goal — створити нову ціль\n"
        "/punch — пробити пунш\n"
        "/status — переглянути всі цілі\n"
        "/delete — видалити ціль"
    )
    photo_path = "cover.jpg"
    if os.path.exists(photo_path):
        await message.answer_photo(photo=FSInputFile(photo_path), caption=manifesto)
    else:
        await message.answer(manifesto)


# ---------------------------------------------------------------------------
# /goal  →  FSM: назва → кількість
# ---------------------------------------------------------------------------

@router.message(Command("goal"))
async def cmd_goal(message: Message, state: FSMContext) -> None:
    count = await db.count_user_goals(message.from_user.id)
    if count >= db.MAX_GOALS_PER_USER:
        await message.answer(
            f"❌ Максимум {db.MAX_GOALS_PER_USER} цілі. "
            "Видали одну через /delete, щоб додати нову."
        )
        return

    await state.set_state(GoalCreation.waiting_for_name)
    await message.answer(
        "Введи назву нової цілі. Можна з емодзі на початку:\n"
        "<code>🏃 Біг</code>\n"
        "<code>🇩🇪 Німецька</code>",
        reply_markup=kb.cancel_keyboard(),
    )


@router.message(GoalCreation.waiting_for_name)
async def goal_name_received(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if not name or len(name) > 64:
        await message.answer("Назва має бути від 1 до 64 символів. Спробуй ще раз.")
        return

    await state.update_data(goal_name=name)
    await state.set_state(GoalCreation.waiting_for_count)
    await message.answer(
        f"Ціль: <b>{name}</b>\n\n"
        "Скільки пунш-слотів? (від 1 до 60)\n"
        "Приклад: <code>30</code>",
        reply_markup=kb.cancel_keyboard(),
    )


@router.message(GoalCreation.waiting_for_count)
async def goal_count_received(message: Message, state: FSMContext) -> None:
    try:
        target = int(message.text.strip())
        if not (1 <= target <= 60):
            raise ValueError
    except ValueError:
        await message.answer("Введи ціле число від 1 до 60.")
        return

    data = await state.get_data()
    goal_name: str = data["goal_name"]
    await state.clear()

    saved = await db.save_goal(message.from_user.id, goal_name, target)
    if not saved:
        await message.answer(
            f"❌ У тебе вже {db.MAX_GOALS_PER_USER} цілі. Видали одну через /delete."
        )
        return

    card = utils.generate_card(goal_name, 0, target)
    await message.answer(card, reply_markup=kb.punch_keyboard())


# ---------------------------------------------------------------------------
# /punch — вибір цілі → inline пунш
# ---------------------------------------------------------------------------

@router.message(Command("punch"))
async def cmd_punch(message: Message) -> None:
    goals = await db.get_user_goals(message.from_user.id)
    if not goals:
        await message.answer("Спочатку створи ціль через /goal")
        return

    if len(goals) == 1:
        # Одна ціль — одразу обробляємо
        await _do_punch(message, goals[0][0])
        return

    await message.answer(
        "Обери ціль, яку хочеш відмітити:",
        reply_markup=kb.goals_select_keyboard(goals),
    )


@router.callback_query(F.data.startswith("punch_goal:"))
async def process_goal_selection(callback: CallbackQuery) -> None:
    goal_id = int(callback.data.split(":")[1])
    await callback.message.delete()
    await _do_punch(callback.message, goal_id, user_id=callback.from_user.id)
    await callback.answer()


@router.callback_query(F.data == "punch_action")
async def process_inline_punch(callback: CallbackQuery) -> None:
    """Кнопка ✅ Пунш прямо під карткою (для єдиної цілі або після /goal)."""
    goals = await db.get_user_goals(callback.from_user.id)
    if not goals:
        await callback.answer("Ціль не знайдена. Створи нову через /goal.", show_alert=True)
        return

    # Беремо першу незавершену ціль, яку ще не пробивали сьогодні
    today = date.today().isoformat()
    target_goal = None
    for goal in goals:
        g_id, g_name, g_target, g_current, g_last = goal
        if g_current < g_target and g_last != today:
            target_goal = goal
            break

    if target_goal is None:
        await callback.answer(
            "Всі цілі або вже закриті, або відмічені сьогодні. Повертайся завтра.",
            show_alert=True,
        )
        return

    await _do_punch(callback.message, target_goal[0], edit=True)
    await callback.answer("✅ Зараховано! Побачимось завтра.")


async def _do_punch(
    message: Message,
    goal_id: int,
    user_id: int | None = None,
    edit: bool = False,
) -> None:
    goal = await db.get_goal_by_id(goal_id)
    if not goal:
        await message.answer("Ціль не знайдена.")
        return

    g_id, g_user_id, g_name, g_target, g_current, g_last = goal

    if g_current >= g_target:
        await message.answer("Цю ціль уже закрито! 🏆")
        return

    today = date.today().isoformat()
    if g_last == today:
        await message.answer("Відмова. Ти вже пробив слот сьогодні. Повертайся завтра.")
        return

    await db.punch_goal(goal_id)
    new_count = g_current + 1
    card = utils.generate_card(g_name, new_count, g_target)
    ai_comment = await ai_services.analyze_progress(g_name, new_count, g_target)
    text = f"{card}\n\n<i>{ai_comment}</i>"

    if new_count >= g_target:
        if edit:
            await message.edit_text(text)
        else:
            await message.answer(text)
        await message.answer(f"🔥 Фініш! Ціль <b>{g_name}</b> повністю закрита.")
        await db.delete_goal(goal_id)
    else:
        if edit:
            await message.edit_text(text, reply_markup=kb.punch_keyboard())
        else:
            await message.answer(text, reply_markup=kb.punch_keyboard())


# ---------------------------------------------------------------------------
# /status
# ---------------------------------------------------------------------------

@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    goals = await db.get_user_goals(message.from_user.id)
    if not goals:
        await message.answer("У тебе ще немає цілей. Створи першу через /goal")
        return

    for goal in goals:
        g_id, g_name, g_target, g_current, _ = goal
        card = utils.generate_card(g_name, g_current, g_target)
        await message.answer(card, reply_markup=kb.punch_keyboard())


# ---------------------------------------------------------------------------
# /delete — видалення цілі
# ---------------------------------------------------------------------------

@router.message(Command("delete"))
async def cmd_delete(message: Message) -> None:
    goals = await db.get_user_goals(message.from_user.id)
    if not goals:
        await message.answer("Нема чого видаляти.")
        return

    rows = []
    for goal in goals:
        g_id, g_name, g_target, g_current, _ = goal
        rows.append([
            InlineKeyboardButton(
                text=f"🗑 {g_name}  {g_current}/{g_target}",
                callback_data=f"delete_goal:{g_id}",
            )
        ])

    markup = InlineKeyboardMarkup(inline_keyboard=rows)
    await message.answer("Обери ціль для видалення:", reply_markup=markup)


@router.callback_query(F.data.startswith("delete_goal:"))
async def process_delete(callback: CallbackQuery) -> None:
    goal_id = int(callback.data.split(":")[1])
    goal = await db.get_goal_by_id(goal_id)

    if not goal or goal[1] != callback.from_user.id:
        await callback.answer("Ціль не знайдена або не твоя.", show_alert=True)
        return

    await db.delete_goal(goal_id)
    await callback.message.edit_text(f"🗑 Ціль <b>{goal[2]}</b> видалена.")
    await callback.answer()


# ---------------------------------------------------------------------------
# FSM: скасування
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "cancel_fsm")
async def cancel_fsm(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Скасовано.")
    await callback.answer()