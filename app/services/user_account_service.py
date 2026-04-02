from __future__ import annotations

import re
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User, UserProfile
from app.services.cooldown_service import CooldownService
from app.services.runtime_settings_service import RuntimeSettingsService
from app.utils.time import ensure_utc, utcnow

EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\u2600-\u26FF\u2700-\u27BF]+",
    flags=re.UNICODE,
)
NICKNAME_RE = re.compile(r"[0-9A-Za-zА-Яа-я _\-\[\]().,!?:+@#]{3,24}")


def contains_emoji(text: str) -> bool:
    return bool(EMOJI_RE.search(text))


class UserAccountService:
    def __init__(
        self,
        session: AsyncSession,
        cooldowns: CooldownService,
        runtime_settings: RuntimeSettingsService,
    ) -> None:
        self.session = session
        self.cooldowns = cooldowns
        self.runtime_settings = runtime_settings

    async def ensure_profile(self, user_id: int) -> UserProfile:
        profile = await self.session.get(UserProfile, user_id)
        if profile is None:
            profile = UserProfile(user_id=user_id)
            self.session.add(profile)
            await self.session.flush()
        return profile

    async def admin_update_user(self, target_user_id: int, field: str, value: str) -> tuple[bool, str]:
        user = await self.session.get(User, target_user_id)
        if user is None:
            return (False, "Профиль не найден.")

        profile = await self.ensure_profile(target_user_id)
        raw_value = value.strip()
        try:
            if field == "coins":
                user.coins = max(0, int(raw_value))
                result = f"Монеты обновлены: {user.coins}"
            elif field == "stars":
                user.stars = max(0, int(raw_value))
                result = f"Звёзды обновлены: {user.stars}"
            elif field == "points":
                user.total_points = max(0, int(raw_value))
                result = f"Очки обновлены: {user.total_points}"
            elif field == "level":
                profile.level = max(1, int(raw_value))
                result = f"Уровень обновлён: {profile.level}"
            elif field == "exp":
                profile.exp = max(0, int(raw_value))
                result = f"Опыт обновлён: {profile.exp}"
            elif field == "premium_days":
                days = int(raw_value)
                user.premium_until = None if days <= 0 else utcnow().replace(microsecond=0) + timedelta(days=days)
                premium_until = ensure_utc(user.premium_until)
                result = (
                    f"Premium до: {premium_until.isoformat(timespec='seconds')}"
                    if premium_until
                    else "Premium отключён."
                )
            elif field == "nickname":
                user.nickname = raw_value or None
                result = f"Ник обновлён: {user.nickname or '-'}"
            elif field.startswith("cooldown:"):
                action = field.split(":", maxsplit=1)[1].strip()
                if not action:
                    return (False, "Укажите action после cooldown:.")
                seconds = max(0, int(raw_value))
                await self.cooldowns.set(target_user_id, action, seconds)
                result = f"Кулдаун {action} установлен на {seconds}с."
            else:
                return (False, "Поле не поддерживается.")
        except ValueError:
            return (False, "Значение имеет неверный формат.")

        await self.session.flush()
        return (True, result)

    async def set_nickname(self, user_id: int, nickname: str) -> tuple[bool, str]:
        user = await self.session.get(User, user_id)
        if user is None:
            return (False, "Профиль не найден.")

        nickname = nickname.strip()
        if not 3 <= len(nickname) <= 24:
            return (False, "Длина ника: 3-24 символа.")
        if "\n" in nickname or "\r" in nickname:
            return (False, "Ник должен быть в одну строку.")

        premium_until = ensure_utc(user.premium_until)
        is_premium = bool(premium_until and premium_until > utcnow())
        if not is_premium and contains_emoji(nickname):
            return (False, "Эмодзи в нике доступны только с Premium.")
        if not NICKNAME_RE.fullmatch(nickname):
            if not (is_premium and contains_emoji(nickname)):
                return (False, "Разрешены: буквы, цифры, пробел и символы _-[]().,!?:+@#")

        cooldown = await self.cooldowns.get(user_id, "nick_change")
        if not cooldown.ready:
            left = cooldown.seconds_left
            return (False, f"Кулдаун смены ника: {left // 60}м {left % 60}с.")

        cooldowns = await self.runtime_settings.get_section("cooldowns")
        user.nickname = nickname
        await self.cooldowns.set(user_id, "nick_change", int(cooldowns.get("nick_change") or 24 * 3600))
        await self.session.flush()
        return (True, f"Ник обновлён: {nickname}")

    async def change_nickname(self, user_id: int, nickname: str) -> tuple[bool, str]:
        return await self.set_nickname(user_id, nickname)
