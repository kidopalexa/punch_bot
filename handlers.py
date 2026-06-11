import os
import json
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
import stickers
from voice import transcribe_voice
from states import GoalCreation, ChallengeCreation

router = Router()

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _send_sticker_or_emoji(message: Message, category: str) -> None:
    file_id = stickers.get_sticker_id(category)
    if file_id:
        try:
            await message.answer_sticker(file_id)
            return
        except Exception:
            pass
    # fallback — просто емодзі в наступному повідомленні не потрібен,
    # емодзі вже вбудовані в текст


async def _goals_summary(user_id: int) -> str:
    goals = await db.get_user_goals(user_id)
    if not goals:
        return "немає активних цілей"
    return ", ".join(f"{g[1]} ({g[3]}/{g[2]})" for g in goals)


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------

@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    manifesto = (
        "🏴 <b>ПУНШ-КАРТА ДИСЦИПЛІНИ</b>\n\n"
        "Твій особистий AI-коуч і трекер цілей в одному боті.\n\n"
        "<b>Основні команди:</b>\n"
        "/goal — створити нову ціль\n"
        "/punch — пробити пунш\n"
        "/status — переглянути всі цілі\n"
        "/mystats — статистика і бейджі\n"
        "/challenge — виклик другу\n"
        "/delete — видалити ціль\n\n"
        "<b>💬 Або просто напиши мені будь-що</b> — відповім як коуч.\n"
        "<b>🎤 Надішли голосове</b> — розпізнаю і запишу пунш або відповім."
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
            "Видали одну через /delete."
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
        f"Ціль: <b>{name}</b>\n\nСкільки пунш-слотів? (1–60)",
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
    target_goal = next((g for g in goals if g[3] < g[2] and g[4] != today), None)
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
    sticker_cat = "punch"
    if new_streak in db.STREAK_BADGES:
        badge_text = f"\n\n🎖 <b>{db.STREAK_BADGES[new_streak]}</b>"
        sticker_cat = f"streak_{new_streak}"

    text = f"{card}\n\n<i>{ai_comment}</i>{badge_text}"

    if new_count >= g_target:
        sticker_cat = "finish"
        if edit:
            await message.edit_text(text)
        else:
            await message.answer(text)
        await message.answer(f"🔥 Фініш! Ціль <b>{g_name}</b> закрита!")
        await _send_sticker_or_emoji(message, sticker_cat)
        await db.delete_goal(goal_id)
    else:
        if edit:
            await message.edit_text(text, reply_markup=kb.punch_keyboard())
        else:
            await message.answer(text, reply_markup=kb.punch_keyboard())
        await _send_sticker_or_emoji(message, sticker_cat)


# ---------------------------------------------------------------------------
# 🎤 Голосові повідомлення
# ---------------------------------------------------------------------------

@router.message(F.voice)
async def handle_voice(message: Message, bot: Bot) -> None:
    await message.answer("🎤 Розпізнаю...")
    file = await bot.get_file(message.voice.file_id)
    file_bytes = await bot.download_file(file.file_path)
    raw = file_bytes.read() if hasattr(file_bytes, "read") else bytes(file_bytes)
    text = await transcribe_voice(raw)

    if not text:
        await message.answer("Не вдалося розпізнати. Спробуй ще раз або напиши текстом.")
        return

    await message.answer(f"🗣 <i>Розпізнано:</i> {text}")

    # Визначаємо намір
    goals = await db.get_user_goals(message.from_user.id)
    summary = await _goals_summary(message.from_user.id)
    intent_data = await ai_services.voice_intent(text, summary)
    intent = intent_data.get("intent", "other")
    goal_hint = intent_data.get("goal_hint", "")

    if intent == "punch" and goals:
        # Знаходимо найближчу ціль за підказкою
        today = date.today().isoformat()
        matched = None
        for g in goals:
            if g[3] < g[2] and g[4] != today:
                if goal_hint.lower() in g[1].lower() or g[1].lower() in goal_hint.lower():
                    matched = g
                    break
        if not matched:
            # Беремо першу доступну
            matched = next((g for g in goals if g[3] < g[2] and g[4] != today), None)

        if matched:
            await message.answer(f"✅ Записую пунш для цілі <b>{matched[1]}</b>!")
            await _do_punch(message, matched[0])
        else:
            await message.answer("Всі цілі вже відмічені сьогодні 👏")
    else:
        # Відповідаємо як коуч
        reply = await ai_services.coach_answer(text, summary)
        await message.answer(f"🤖 <b>Коуч:</b>\n\n{reply}")
        await _send_sticker_or_emoji(message, "coach")


# ---------------------------------------------------------------------------
# 💬 AI-коуч на будь-яке текстове повідомлення
# ---------------------------------------------------------------------------

@router.message(F.text & ~F.text.startswith("/"))
async def handle_free_text(message: Message, state: FSMContext) -> None:
    # Не перехоплюємо якщо є активний FSM стан
    current_state = await state.get_state()
    if current_state:
        return

    summary = await _goals_summary(message.from_user.id)
    reply = await ai_services.coach_coach_reply(message.text, summary)
    await message.answer(f"🤖 <b>Коуч:</b>\n\n{reply}")
    await _send_sticker_or_emoji(message, "coach")


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
# /challenge
# ---------------------------------------------------------------------------

@router.message(Command("challenge"))
async def cmd_challenge(message: Message, state: FSMContext) -> None:
    from states import ChallengeCreation
    await state.set_state(ChallengeCreation.waiting_for_opponent)
    await message.answer(
        "👥 <b>Челендж</b>\n\nВведи Telegram ID суперника.\n"
        "Як дізнатись ID: нехай напише <b>@userinfobot</b>",
        reply_markup=kb.cancel_keyboard(),
    )


@router.message(F.text, lambda m: True)
async def _challenge_opponent(message: Message, state: FSMContext) -> None:
    from states import ChallengeCreation
    if await state.get_state() != ChallengeCreation.waiting_for_opponent:
        return
    try:
        opponent_id = int(message.text.strip())
        if opponent_id == message.from_user.id:
            raise ValueError
    except ValueError:
        await message.answer("Введи коректний числовий Telegram ID.")
        return
    await state.update_data(opponent_id=opponent_id)
    await state.set_state(ChallengeCreation.waiting_for_goal_name)
    await message.answer("Введи назву спільної цілі:", reply_markup=kb.cancel_keyboard())


@router.message(F.text, lambda m: True)
async def _challenge_goal(message: Message, state: FSMContext) -> None:
    from states import ChallengeCreation
    if await state.get_state() != ChallengeCreation.waiting_for_goal_name:
        return
    name = message.text.strip()
    if not name or len(name) > 64:
        await message.answer("Назва 1–64 символи.")
        return
    await state.update_data(goal_name=name)
    await state.set_state(ChallengeCreation.waiting_for_count)
    await message.answer("Скільки пунш-слотів? (1–60)", reply_markup=kb.cancel_keyboard())


@router.message(F.text, lambda m: True)
async def _challenge_count(message: Message, state: FSMContext, bot: Bot) -> None:
    from states import ChallengeCreation
    if await state.get_state() != ChallengeCreation.waiting_for_count:
        return
    try:
        target = int(message.text.strip())
        if not (1 <= target <= 60):
            raise ValueError
    except ValueError:
        await message.answer("Введи число від 1 до 60.")
        return
    data = await state.get_data()
    await state.clear()
    opponent_id = data["opponent_id"]
    goal_name = data["goal_name"]
    challenge_id = await db.create_challenge(goal_name, target, message.from_user.id, opponent_id)
    markup = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Приймаю виклик!", callback_data=f"accept_challenge:{challenge_id}")
    ]])
    try:
        initiator = message.from_user.full_name or "Хтось"
        await bot.send_message(
            opponent_id,
            f"⚔️ <b>{initiator}</b> кидає тобі виклик!\n\n"
            f"Ціль: <b>{goal_name}</b> ({target} слотів)\nХто перший — переможець.",
            reply_markup=markup,
        )
        await message.answer(f"✅ Виклик відправлено! ID: <code>{challenge_id}</code>")
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
        f"⚔️ <b>Челендж прийнято!</b>\nЦіль: <b>{ch[1]}</b> ({ch[2]} слотів)",
        reply_markup=markup,
    )
    try:
        await bot.send_message(ch[3], f"⚔️ Суперник прийняв челендж <b>{ch[1]}</b>!")
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
        await callback.message.edit_text(f"🏆 <b>Ти переміг у челенджі «{ch[1]}»!</b>")
        await _send_sticker_or_emoji(callback.message, "finish")
        try:
            await bot.send_message(opponent_id, f"😔 Суперник переміг у челенджі <b>{ch[1]}</b>.")
        except Exception:
            pass
    else:
        await callback.answer(f"✅ Пунш! {new_count}/{target}")
        try:
            await bot.send_message(opponent_id, f"⚔️ Суперник пробив пунш! Рахунок: {new_count}/{target}")
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
        you = u1c if message.from_user.id == u1 else u2c
        opp = u2c if message.from_user.id == u1 else u1c
        await message.answer(f"⚔️ <b>{goal}</b>\nТи: {you}/{target} | Суперник: {opp}/{target}")


# ---------------------------------------------------------------------------
# /loadstickers — адмін команда для завантаження стікерів
# ---------------------------------------------------------------------------

@router.message(Command("loadstickers"))
async def cmd_load_stickers(message: Message, bot: Bot) -> None:
    if ADMIN_ID and message.from_user.id != ADMIN_ID:
        return
    sticker_set = await bot.get_sticker_set("NEWLIFE3_by_fStikBot")
    categories = list(stickers.STICKER_CATEGORIES.keys())
    loaded = 0
    for i, sticker in enumerate(sticker_set.stickers):
        if i < len(categories):
            await stickers.save_sticker(categories[i], sticker.file_id)
            loaded += 1
    await message.answer(f"✅ Завантажено {loaded} стікерів з паку NEWLIFE3.")


# ---------------------------------------------------------------------------
# FSM cancel
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "cancel_fsm")
async def cancel_fsm(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Скасовано.")
    await callback.answer()
