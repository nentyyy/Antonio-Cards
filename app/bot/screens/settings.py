from __future__ import annotations

from aiogram.types import Message

from app.bot.context import h, template_text
from app.bot.keyboards import ik_settings
from app.bot.ui_defaults import DEFAULT_TEXT_TEMPLATES
from app.db.session import SessionLocal
from app.services.brawl_cards_service import BrawlCardsService


async def render_settings_screen(message: Message) -> None:
    if message.from_user is None:
        return
    async with SessionLocal() as session:
        service = BrawlCardsService(session)
        user_settings = await service.user_settings(message.from_user.id)
        body = await template_text(
            session,
            message.from_user.id,
            "screen.settings",
            DEFAULT_TEXT_TEMPLATES["screen.settings"],
        )
    text = (
        f"{h('⚙️ Настройки')}\n{body}\n\n"
        f"🔔 Уведомления: {'вкл' if user_settings.notifications else 'выкл'}\n"
        f"🌐 Язык: {user_settings.locale}\n"
        f"🔐 Приватность: {'скрытая' if (user_settings.privacy or {}).get('hidden') else 'обычная'}\n"
        f"🧾 Подтверждение покупок: {'вкл' if user_settings.confirm_purchases else 'выкл'}\n"
        f"🃏 Стиль выдачи карт: {user_settings.card_style}\n"
        f"🖼 Отображение медиа: {'вкл' if user_settings.show_media else 'выкл'}\n"
        f"🛡 Безопасный режим: {'вкл' if user_settings.safe_mode else 'выкл'}"
    )
    await message.answer(text, reply_markup=ik_settings())
