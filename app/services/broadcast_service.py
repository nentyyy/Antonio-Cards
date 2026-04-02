from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from sqlalchemy import select

from app.db.models import User
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


async def run_text_broadcast(bot: Bot, admin_id: int, text: str) -> None:
    async with SessionLocal() as session:
        user_ids = list((await session.scalars(select(User.id).order_by(User.id))).all())

    total = len(user_ids)
    sent = 0
    blocked = 0
    failed = 0

    for index, user_id in enumerate(user_ids, start=1):
        try:
            await bot.send_message(user_id, text)
            sent += 1
        except TelegramRetryAfter as exc:
            await asyncio.sleep(float(exc.retry_after) + 0.25)
            try:
                await bot.send_message(user_id, text)
                sent += 1
            except TelegramForbiddenError:
                blocked += 1
            except (TelegramBadRequest, Exception):
                failed += 1
                logger.exception("broadcast retry failed", extra={"user_id": user_id})
        except TelegramForbiddenError:
            blocked += 1
        except TelegramBadRequest:
            failed += 1
        except Exception:
            failed += 1
            logger.exception("broadcast failed", extra={"user_id": user_id})

        if index % 40 == 0:
            await asyncio.sleep(0.35)

    await bot.send_message(
        admin_id,
        (
            "📢 Рассылка завершена\n"
            f"Всего пользователей: {total}\n"
            f"Отправлено: {sent}\n"
            f"Заблокировали бота: {blocked}\n"
            f"Ошибок: {failed}"
        ),
    )
