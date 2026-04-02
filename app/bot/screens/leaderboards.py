from __future__ import annotations

from aiogram.types import Message
from sqlalchemy import func, select

from app.bot.context import display_name, ensure_user, h
from app.bot.keyboards import ik_top_select
from app.db.models import BcCard, BcCardInstance, User, UserProfile
from app.db.session import SessionLocal


async def screen_top(message: Message) -> None:
    await message.answer(f"{h('🏆 Топ')}\nВыберите рейтинг.", reply_markup=ik_top_select())


async def screen_top_metric(message: Message, metric: str) -> None:
    if message.from_user is None:
        return
    await ensure_user(message)
    async with SessionLocal() as session:
        if metric == "points":
            rows = (await session.scalars(select(User).order_by(User.total_points.desc()).limit(10))).all()
            lines = [h("🏆 Топ по очкам")]
            for index, user in enumerate(rows, start=1):
                lines.append(f"{index}. {display_name(user)} — {user.total_points}✨")
        elif metric == "coins":
            rows = (await session.scalars(select(User).order_by(User.coins.desc()).limit(10))).all()
            lines = [h("🏆 Топ по монетам")]
            for index, user in enumerate(rows, start=1):
                lines.append(f"{index}. {display_name(user)} — {user.coins}🪙")
        elif metric == "cards":
            rows = (
                await session.execute(
                    select(User.id, User.nickname, User.first_name, func.count(BcCardInstance.id).label("cards"))
                    .join(BcCardInstance, BcCardInstance.user_id == User.id, isouter=True)
                    .group_by(User.id)
                    .order_by(func.count(BcCardInstance.id).desc())
                    .limit(10)
                )
            ).all()
            lines = [h("🏆 Топ по картам")]
            for index, (user_id, nickname, first_name, cards_count) in enumerate(rows, start=1):
                name = nickname or first_name or str(user_id)
                lines.append(f"{index}. {name} — {int(cards_count or 0)}🃏")
        elif metric == "level":
            rows = (
                await session.execute(
                    select(User.id, User.nickname, User.first_name, UserProfile.level)
                    .join(UserProfile, UserProfile.user_id == User.id, isouter=True)
                    .order_by(UserProfile.level.desc().nullslast())
                    .limit(10)
                )
            ).all()
            lines = [h("🏆 Топ по уровню")]
            for index, (user_id, nickname, first_name, level) in enumerate(rows, start=1):
                name = nickname or first_name or str(user_id)
                lines.append(f"{index}. {name} — {int(level or 1)}🏅")
        elif metric == "rare":
            rows = (
                await session.execute(
                    select(User.id, User.nickname, User.first_name, func.count(BcCardInstance.id).label("cards"))
                    .join(BcCardInstance, BcCardInstance.user_id == User.id, isouter=True)
                    .join(BcCard, BcCard.id == BcCardInstance.card_id, isouter=True)
                    .where(BcCard.rarity_key.in_(["epic", "mythic", "legendary", "exclusive", "event", "limited"]))
                    .group_by(User.id)
                    .order_by(func.count(BcCardInstance.id).desc())
                    .limit(10)
                )
            ).all()
            lines = [h("🏆 Топ по редким")]
            for index, (user_id, nickname, first_name, cards_count) in enumerate(rows, start=1):
                name = nickname or first_name or str(user_id)
                lines.append(f"{index}. {name} — {int(cards_count or 0)}💎")
        else:
            await screen_top(message)
            return
    lines.append("\nСезонные награды и правила будут показаны здесь после настройки в админке.")
    await message.answer("\n".join(lines), reply_markup=ik_top_select())
