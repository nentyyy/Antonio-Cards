from __future__ import annotations

import asyncio

from aiogram.types import Message
from sqlalchemy import and_, func, select

from app.bot.context import display_name, ensure_user, ensure_user_background, h, is_admin_id, template_text
from app.bot.keyboards import ik_nick, ik_profile, main_menu
from app.bot.ui_defaults import DEFAULT_TEXT_TEMPLATES
from app.db.models import BcCard, BcCardInstance, Marriage, User, UserProfile
from app.db.session import SessionLocal
from app.services.brawl_cards_service import BrawlCardsService
from app.utils.time import utcnow


async def send_start(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else None
    async with SessionLocal() as session:
        body = await template_text(
            session,
            user_id,
            "screen.welcome",
            DEFAULT_TEXT_TEMPLATES["screen.welcome"],
        )
    text = (
        f"{h('✨ Antonio Cards')}\n"
        f"{body}\n\n"
        "Быстрые команды:\n"
        "/start — главный экран\n"
        "/help — подсказка по боту\n"
        "/admin — вход в админ-панель"
    )
    await message.answer(text, reply_markup=main_menu(is_admin=is_admin_id(user_id or 0)))


async def handle_start_command(message: Message) -> None:
    await send_start(message)
    if message.from_user is None:
        return
    asyncio.create_task(
        ensure_user_background(
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )
    )


async def render_help_screen(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else None
    async with SessionLocal() as session:
        body = await template_text(
            session,
            user_id,
            "screen.help",
            DEFAULT_TEXT_TEMPLATES["screen.help"],
        )
    is_admin = is_admin_id(user_id or 0)
    await message.answer(f"{h('🧭 Навигация')}\n{body}", reply_markup=main_menu(is_admin=is_admin))


async def screen_main(message: Message) -> None:
    await send_start(message)


async def screen_profile(message: Message) -> None:
    if message.from_user is None:
        return
    await ensure_user(message)
    async with SessionLocal() as session:
        service = BrawlCardsService(session)
        async with session.begin():
            user = await service.session.get(User, message.from_user.id)
            if user is None:
                await message.answer("Профиль не найден. Нажмите /start.")
                return
            profile = await service.session.get(UserProfile, message.from_user.id)
            if profile is None:
                profile = UserProfile(user_id=user.id)
                session.add(profile)
        premium_active = bool(user.premium_until and user.premium_until > utcnow())
        premium_str = "активен" if premium_active else "не активен"
        premium_until = user.premium_until.isoformat(timespec="seconds") if user.premium_until else "-"
        cards_total = await session.scalar(
            select(func.count()).select_from(BcCardInstance).where(BcCardInstance.user_id == user.id)
        )
        limited_count = await session.scalar(
            select(func.count())
            .select_from(BcCardInstance)
            .join(BcCard, BcCard.id == BcCardInstance.card_id)
            .where(and_(BcCardInstance.user_id == user.id, BcCard.is_limited.is_(True)))
        )
        marriage = await session.scalar(
            select(Marriage).where((Marriage.user1_id == user.id) | (Marriage.user2_id == user.id)).limit(1)
        )
        body = await template_text(
            session,
            message.from_user.id,
            "screen.profile",
            DEFAULT_TEXT_TEMPLATES["screen.profile"],
        )
    family_str = "в браке" if marriage else "не в браке"
    text = (
        f"{h('👤 Профиль')}\n"
        f"{body}\n\n"
        f"🆔 ID: `{user.id}`\n"
        f"🏷 Ник: {display_name(user)}\n"
        f"📅 Регистрация: {user.created_at.date().isoformat()}\n\n"
        f"🏅 Уровень: {profile.level}\n"
        f"📈 Опыт: {profile.exp}\n"
        f"✨ Очки: {user.total_points}\n"
        f"🪙 Монеты: {user.coins}\n"
        f"⭐ Звезды: {user.stars}\n\n"
        f"🃏 Карточки: {cards_total or 0}\n"
        f"🎟 Лимитки: {limited_count or 0}\n"
        f"💎 Premium: {premium_str} ({premium_until})\n"
        f"🎲 Игры: {profile.games_played} сыграно, {profile.games_won} побед\n"
        f"💱 Маркет: {profile.market_sold} продано, {profile.market_bought} куплено\n"
        f"💍 Семья: {family_str}\n"
        f"✅ Заданий выполнено: {profile.tasks_done}\n"
        f"⏱ Активность: {int(profile.activity_seconds // 3600)}ч"
    )
    await message.answer(text, reply_markup=ik_profile(), parse_mode="Markdown")


async def screen_nick(message: Message) -> None:
    text = (
        f"{h('✏️ Смена ника')}\n"
        "Здесь можно сменить ник.\n\n"
        "Правила:\n"
        "• длина 3-24 символа\n"
        "• буквы, цифры, пробел и символы _-[]().,!?:+@#\n"
        "• эмодзи в нике доступны только с Premium\n"
        "• кулдаун смены ника настраивается в админке\n\n"
        "Нажмите кнопку ниже и отправьте новый ник одним сообщением."
    )
    await message.answer(text, reply_markup=ik_nick())
