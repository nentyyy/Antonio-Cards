from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import BotCommand

from app.bot.handlers import router as user_router
from app.config import get_settings
from app.db.seed import seed_defaults
from app.db.session import SessionLocal, init_db
from app.logging_setup import setup_logging
from app.middlewares.request_logging import RequestLoggingMiddleware
from app.services.runtime_settings_service import RuntimeSettingsService
from app.utils.text import install_aiogram_text_fixes


async def warm_runtime_settings() -> None:
    async with SessionLocal() as session:
        service = RuntimeSettingsService(session)
        for section in ("cooldowns", "rewards", "bonus_links", "button_labels", "input_placeholders"):
            await service.get_section(section)


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    install_aiogram_text_fixes()

    await init_db()
    await seed_defaults()
    await warm_runtime_settings()

    bot = Bot(token=settings.bot_token, session=AiohttpSession(timeout=15))
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Главный экран"),
            BotCommand(command="help", description="Подсказка по боту"),
            BotCommand(command="profile", description="Профиль"),
            BotCommand(command="card", description="Получить карту"),
            BotCommand(command="bonus", description="Бонусы"),
            BotCommand(command="shop", description="Магазин"),
            BotCommand(command="games", description="Мини-игры"),
            BotCommand(command="top", description="Рейтинги"),
            BotCommand(command="admin", description="Вход в админ-панель"),
        ]
    )
    dp = Dispatcher()
    dp.message.middleware(RequestLoggingMiddleware())
    dp.include_router(user_router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
