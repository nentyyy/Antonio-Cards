from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession

from app.bot.handlers import router as user_router
from app.config import get_settings
from app.db.seed import seed_defaults
from app.db.session import init_db
from app.logging_setup import setup_logging
from app.middlewares.antiflood import AntiFloodMiddleware
from app.middlewares.request_logging import RequestLoggingMiddleware
from app.utils.text import install_aiogram_text_fixes


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    install_aiogram_text_fixes()

    await init_db()
    await seed_defaults()

    bot = Bot(token=settings.bot_token, session=AiohttpSession(timeout=60))
    dp = Dispatcher()
    dp.message.middleware(RequestLoggingMiddleware())
    dp.message.middleware(AntiFloodMiddleware(cooldown=0.7))
    dp.include_router(user_router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
