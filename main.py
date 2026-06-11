import asyncio
import logging
import sys
import os

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import database as db
import ai_services
import stickers
from handlers import router

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")


async def send_morning_briefing(bot: Bot) -> None:
    """Ранковий брифінг о 9:00 для всіх активних юзерів."""
    all_users = await db.get_all_active_user_ids()
    for user_id in all_users:
        try:
            goals = await db.get_user_goals(user_id)
            text = await ai_services.morning_briefing(goals)
            await bot.send_message(
                chat_id=user_id,
                text=f"☀️ <b>Ранковий брифінг</b>\n\n{text}",
            )
        except Exception as exc:
            logging.error("Briefing error %s: %s", user_id, exc)


async def send_daily_reminders(bot: Bot) -> None:
    """Вечірні нагадування о 20:00."""
    pending = await db.get_users_pending_punch()
    for user_id, goal_name in pending:
        try:
            text = await ai_services.generate_reminder(goal_name)
            await bot.send_message(
                chat_id=user_id,
                text=f"⚠️ <b>Системне нагадування</b>\n\n{text}",
            )
        except Exception as exc:
            logging.error("Reminder error %s: %s", user_id, exc)


async def main() -> None:
    if not TOKEN:
        logging.error("BOT_TOKEN не знайдено!")
        sys.exit(1)

    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    await db.init_db()
    await stickers.init_stickers_db()

    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    scheduler = AsyncIOScheduler(timezone="Europe/Berlin")
    scheduler.add_job(send_morning_briefing, "cron", hour=9, minute=0, kwargs={"bot": bot})
    scheduler.add_job(send_daily_reminders, "cron", hour=20, minute=0, kwargs={"bot": bot})
    scheduler.start()
    logging.info("Scheduler started.")

    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
