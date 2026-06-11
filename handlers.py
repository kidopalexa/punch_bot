import os
from datetime import date

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message, CallbackQuery, FSInputFile,
    InlineKeyboardMarkup, InlineKeyboardButton,
)

import database as db
import utils
import keyboards as kb
import ai_services
from states import GoalCreation, ChallengeCreation, CoachDialog

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
        "<b>Команди:</b>\n"
        "/goal — створити нову ціль\n"
        "/punch — пробити пунш\n"
        "/status — переглянути всі цілі\n"
        "/delete — видалити ціль\n"
        "/coach — запитати AI-коуча\n"
        "/challenge — кинути виклик другу\n"
        "/mystats — моя статистика"
    )
    photo_path = "cover.jpg"
    if os.path.exists(photo_path):
        await message.answer_photo(photo=FSInputFile(photo_path), caption=manifesto)
    else:
        await message.answer(manifesto)


# ---------------------------------------------------------------------------
# /goal  →  FSM
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
        "Введи назву нової цілі. Можна з емодзі:\n"
        "<code>🏃 Біг</code>\n<code>🇩🇪 Німецька</code>",
        reply_markup=kb.cancel_keyboard(),
    )


@router.message(GoalCreation.waiting_for_name)
async def goal_name_received(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if not name or len(name) > 64:
        await message.answer("Назва має бути від 1 до 64 символів.")
        return
    await state.update_data(goal_name=name)
    await state.set_state(GoalCreation.waiting_for_count)
    await message.answer(
        f"Ціль: <b>{name}</b>\n\nСкільки пунш-слотів? (1–60)\nПриклад: <code>30</code>",
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
        await message.answer(f"❌ У тебе вже {db.MAX_GOALS_PER_USER} цілі.")
        return
    card = utils.generate_card(goal_name, 0, target)
    await message.answer(card, reply_markup=kb.punch_keyboard())


# ---------------------------------------------------------------------------
# /punch
# ---------------------------------------------------------------------------

@router.message(Command("punch"))
async def cmd_punch(message: Message) -> None:
    goals = await db.get_user_goals(message.from_user.id)
    if not goals:
        await message.answer("Спочатку створи ціль через /goal")
        return
    if len(goals) == 1:
        await _do_punch(message, goals[0][0])
        return
    await message.answer("Обери ціль:", reply_markup=kb.goals_select_keyboard(goals))


@router.callback_query(F.data.startswith("punch_goal:"))
async def process_goal_selection(callback: CallbackQuery) -> None:
    goal_id = int(callback.data.split(":")[1])
    await callback.message.delete()
    await _do_punch(callback.message, goal_id)
    await callback.answer()


@router.callback_query(F.data == "punch_action")
async def process_inline_punch(callback: CallbackQuery) -> None:
    goals = await db.get_user_goals(callback.from_user.id)
    if not goals:
        await callback.answer("Ціль не знайдена.", show_alert=True)
        return
    today = date.today().isoformat()
    target_goal = next(
        (g for g in goals if g[3] < g[2] and g[4] != today), None
    )
    if target_goal is None:
        await callback.answer("Всі відмічені сьогодні. Повертайся завтра.", show_alert=True)
        return
    await _do_punch(callback.message, target_goal[0], edit=True)
    await callback.answer("✅ Зараховано!")


async def _do_punch(message: Message, goal_id: int, edit: bool = False) -> None:
    goal = await db.get_goal_by_id(goal_id)
    if not goal:
        await message.answer("Ціль не знайдена.")
        return
    g_id, g_user_id, g_name, g_target, g_current, g_last, g_streak = goal

    if g_current >= g_target:
        await message.answer("Цю ціль уже закрито! 🏆")
        return
    today = date.today().isoformat()
    if g_last == today:
        await message.answer("Відмова. Ти вже пробив слот сьогодні.")
        return

    new_streak = await db.punch_goal(goal_id)
    new_count = g_current + 1
    card = utils.generate_card(g_name, new_count, g_target)
    ai_comment = await ai_services.analyze_progress(g_name, new_count, g_target)

    # Бейдж за серію
    badge_text = ""
    if new_streak in db.STREAK_BADGES:
        badge_text = f"\n\n🎖 <b>{db.STREAK_BADGES[new_streak]}</b> — так тримати!"

    text = f"{card}\n\n<i>{ai_comment}</i>{badge_text}"

    if new_count >= g_target:
        if edit:
            await message.edit_text(text)
        else:
            await message.answer(text)
        await message.answer(f"🔥 Фініш! Ціль <b>{g_name}</b> закрита.")
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
        g_id, g_name, g_target, g_current, _, g_streak = goal
        card = utils.generate_card(g_name, g_current, g_target)
        streak_line = f"\n🔥 Серія: <b>{g_streak} днів</b>" if g_streak > 1 else ""
        await message.answer(card + streak_line, reply_markup=kb.punch_keyboard())


# ---------------------------------------------------------------------------
# /mystats
# ---------------------------------------------------------------------------

@router.message(Command("mystats"))
async def cmd_mystats(message: Message) -> None:
    goals = await db.get_user_goals(message.from_user.id)
    if not goals:
        await message.answer("Ще немає даних.")
        return
    lines = ["📊 <b>Твоя статистика:</b>\n"]
    for g_id, g_name, g_target, g_current, _, g_streak in goals:
        pct = int(g_current / g_target * 100)
        bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
        best_badge = ""
        for days in sorted(db.STREAK_BADGES.keys(), reverse=True):
            if g_streak >= days:
                best_badge = db.STREAK_BADGES[days]
                break
        lines.append(
            f"<b>{g_name}</b>\n"
            f"{bar} {pct}%\n"
            f"Прогрес: {g_current}/{g_target} | Серія: {g_streak} дн."
            + (f"\nБейдж: {best_badge}" if best_badge else "")
        )
    await message.answer("\n\n".join(lines))


# ---------------------------------------------------------------------------
# /delete
# ---------------------------------------------------------------------------

@router.message(Command("delete"))
async def cmd_delete(message: Message) -> None:
    goals = await db.get_user_goals(message.from_user.id)
    if not goals:
        await message.answer("Нема чого видаляти.")
        return
    rows = [[InlineKeyboardButton(
        text=f"🗑 {g[1]}  {g[3]}/{g[2]}",
        callback_data=f"delete_goal:{g[0]}",
    )] for g in goals]
    await message.answer("Обери ціль для видалення:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("delete_goal:"))
async def process_delete(callback: CallbackQuery) -> None:
    goal_id = int(callback.data.split(":")[1])
    goal = await db.get_goal_by_id(goal_id)
    if not goal or goal[1] != callback.from_user.id:
        await callback.answer("Ціль не знайдена.", show_alert=True)
        return
    await db.delete_goal(goal_id)
    await callback.message.edit_text(f"🗑 Ціль <b>{goal[2]}</b> видалена.")
    await callback.answer()


# ---------------------------------------------------------------------------
# /coach — AI коуч
# ---------------------------------------------------------------------------

@router.message(Command("coach"))
async def cmd_coach(message: Message, state: FSMContext) -> None:
    await state.set_state(CoachDialog.waiting_for_question)
    await message.answer(
        "🤖 <b>AI-коуч</b>\n\nЗадай своє питання про цілі, дисципліну або мотивацію:",
        reply_markup=kb.cancel_keyboard(),
    )


@router.message(CoachDialog.waiting_for_question)
async def coach_question_received(message: Message, state: FSMContext) -> None:
    await state.clear()
    goals = await db.get_user_goals(message.from_user.id)
    goals_summary = ", ".join(f"{g[1]} ({g[3]}/{g[2]})" for g in goals) or "немає активних цілей"
    await message.answer("⏳ Думаю...")
    answer = await ai_services.coach_answer(message.text, goals_summary)
    await message.answer(f"🤖 <b>Коуч:</b>\n\n{answer}")


# ---------------------------------------------------------------------------
# /challenge — челендж з другом
# ---------------------------------------------------------------------------

@router.message(Command("challenge"))
async def cmd_challenge(message: Message, state: FSMContext) -> None:
    await state.set_state(ChallengeCreation.waiting_for_opponent)
    await message.answer(
        "👥 <b>Челендж</b>\n\nПопроси друга написати боту /start, "
        "потім введи його Telegram ID.\n\n"
        "Як дізнатись ID друга: нехай напише @userinfobot",
        reply_markup=kb.cancel_keyboard(),
    )


@router.message(ChallengeCreation.waiting_for_opponent)
async def challenge_opponent_received(message: Message, state: FSMContext) -> None:
    try:
        opponent_id = int(message.text.strip())
        if opponent_id == message.from_user.id:
            raise ValueError
    except ValueError:
        await message.answer("Введи коректний числовий Telegram ID іншої людини.")
        return
    await state.update_data(opponent_id=opponent_id)
    await state.set_state(ChallengeCreation.waiting_for_goal_name)
    await message.answer("Введи назву спільної цілі (з емодзі):", reply_markup=kb.cancel_keyboard())


@router.message(ChallengeCreation.waiting_for_goal_name)
async def challenge_goal_name_received(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if not name or len(name) > 64:
        await message.answer("Назва 1–64 символи.")
        return
    await state.update_data(goal_name=name)
    await state.set_state(ChallengeCreation.waiting_for_count)
    await message.answer("Скільки пунш-слотів? (1–60)", reply_markup=kb.cancel_keyboard())


@router.message(ChallengeCreation.waiting_for_count)
async def challenge_count_received(message: Message, state: FSMContext, bot: Bot) -> None:
    try:
        target = int(message.text.strip())
        if not (1 <= target <= 60):
            raise ValueError
    except ValueError:
        await message.answer("Введи число від 1 до 60.")
        return
    data = await state.get_data()
    await state.clear()

    opponent_id: int = data["opponent_id"]
    goal_name: str = data["goal_name"]
    challenge_id = await db.create_challenge(goal_name, target, message.from_user.id, opponent_id)

    markup = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Приймаю виклик!", callback_data=f"accept_challenge:{challenge_id}")
    ]])
    initiator = message.from_user.full_name or "Хтось"
    try:
        await bot.send_message(
            opponent_id,
            f"⚔️ <b>{initiator}</b> кидає тобі виклик!\n\n"
            f"Ціль: <b>{goal_name}</b> ({target} пунш-слотів)\n"
            f"Хто закриє ціль першим — той переможець.",
            reply_markup=markup,
        )
        await message.answer(
            f"✅ Виклик відправлено! Чекай підтвердження від суперника.\n"
            f"ID челенджу: <code>{challenge_id}</code>"
        )
    except Exception:
        await message.answer("❌ Не вдалося написати суперникові. Перевір ID.")


@router.callback_query(F.data.startswith("accept_challenge:"))
async def accept_challenge(callback: CallbackQuery, bot: Bot) -> None:
    challenge_id = int(callback.data.split(":")[1])
    ch = await db.get_challenge(challenge_id)
    if not ch:
        await callback.answer("Челендж не знайдено.", show_alert=True)
        return

    markup = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Пунш у челенджі", callback_data=f"challenge_punch:{challenge_id}")
    ]])
    await callback.message.edit_text(
        f"⚔️ <b>Челендж прийнято!</b>\n\n"
        f"Ціль: <b>{ch[1]}</b> ({ch[2]} слотів)\n"
        f"Щодня тисни кнопку нижче.",
        reply_markup=markup,
    )
    try:
        await bot.send_message(
            ch[3],
            f"⚔️ Суперник прийняв челендж <b>{ch[1]}</b>! Починаємо!\n"
            f"ID: <code>{challenge_id}</code>\n"
            f"Пиши /challengestatus щоб бачити рахунок.",
        )
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("challenge_punch:"))
async def challenge_punch(callback: CallbackQuery, bot: Bot) -> None:
    challenge_id = int(callback.data.split(":")[1])
    new_count, target, is_winner = await db.punch_challenge(challenge_id, callback.from_user.id)

    if new_count == 0:
        await callback.answer("Вже пробив сьогодні!", show_alert=True)
        return

    ch = await db.get_challenge(challenge_id)
    opponent_id = ch[4] if callback.from_user.id == ch[3] else ch[3]

    if is_winner:
        await callback.message.edit_text(
            f"🏆 <b>Ти переміг у челенджі «{ch[1]}»!</b>\n"
            f"Результат: {new_count}/{target}"
        )
        try:
            await bot.send_message(
                opponent_id,
                f"😔 Суперник переміг у челенджі <b>{ch[1]}</b>. Наступного разу пощастить."
            )
        except Exception:
            pass
    else:
        await callback.answer(f"✅ Пунш! {new_count}/{target}")
        try:
            await bot.send_message(
                opponent_id,
                f"⚔️ Суперник пробив пунш у челенджі <b>{ch[1]}</b>. Рахунок: {new_count}/{target}"
            )
        except Exception:
            pass


@router.message(Command("challengestatus"))
async def cmd_challenge_status(message: Message) -> None:
    challenges = await db.get_user_challenges(message.from_user.id)
    if not challenges:
        await message.answer("Активних челенджів немає.")
        return
    for ch in challenges:
        _, goal, target, u1, u2, u1c, u2c, _, _, _, _ = ch
        you_count = u1c if message.from_user.id == u1 else u2c
        opp_count = u2c if message.from_user.id == u1 else u1c
        await message.answer(
            f"⚔️ <b>Челендж: {goal}</b>\n"
            f"Ти: {you_count}/{target}\n"
            f"Суперник: {opp_count}/{target}"
        )


# ---------------------------------------------------------------------------
# FSM cancel
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "cancel_fsm")
async def cancel_fsm(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Скасовано.")
    await callback.answer()