from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

from app.config import get_settings
from app.db.models import User
from app.db.session import SessionLocal
from app.services.brawl_cards_service import BrawlCardsService


def h(title: str) -> str:
    return f"{title}\n------------------"


def display_name(user: User) -> str:
    return user.nickname or user.first_name or str(user.id)


async def ensure_user(message: Message) -> User | None:
    if message.from_user is None:
        return None
    async with SessionLocal() as session:
        service = BrawlCardsService(session)
        user = await service.ensure_user(
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )
        await session.commit()
        return user


async def ensure_user_background(user_id: int, username: str | None, first_name: str) -> None:
    async with SessionLocal() as session:
        service = BrawlCardsService(session)
        await service.ensure_user(user_id=user_id, username=username, first_name=first_name)
        await session.commit()


def is_admin_id(user_id: int) -> bool:
    return user_id in get_settings().admin_id_set()


async def safe_callback_answer(callback: CallbackQuery, text: str | None = None) -> None:
    try:
        await callback.answer(text)
    except TelegramBadRequest:
        pass


async def template_text(session, user_id: int | None, key: str, fallback: str) -> str:
    service = BrawlCardsService(session)
    locale = "ru"
    if user_id is not None:
        settings = await service.ensure_settings(user_id)
        locale = settings.locale
    return await service.get_template_text(key, locale, fallback)
