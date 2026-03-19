from __future__ import annotations
import random
import re
from dataclasses import dataclass
from datetime import timedelta
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import get_settings
from app.db.models import BcActiveBooster, BcAuditLog, BcBonusTask, BcBooster, BcCard, BcCardInstance, BcChest, BcChestDrop, BcEvent, BcInputState, BcMedia, BcRarity, BcRPAction, BcRPCategory, BcRPLog, BcShopItem, BcTask, BcTextTemplate, BcUserBonusTask, BcUserRole, BcUserTask, BcUserState, BcUserSettings, BcMarriageProposal, BcMarketLot, Cooldown, Marriage, Setting, User, UserProfile
from app.utils.time import ensure_utc, utcnow
settings = get_settings()

SYSTEM_SETTINGS_DEFAULTS: dict[str, dict[str, object]] = {
    'cooldowns': {
        'brawl_cards': int(settings.brawl_cooldown_seconds),
        'bonus': int(settings.bonus_cooldown_seconds),
        'nick_change': 24 * 3600,
        'dice': int(settings.dice_cooldown_seconds),
        'guess_rarity': 60,
        'coinflip': 60,
        'card_battle': 60,
        'slot': 60,
        'premium_game_reduction': 20,
    },
    'rewards': {
        'bonus_coins': int(settings.bonus_reward_coins),
        'bonus_stars': int(settings.bonus_reward_stars),
        'market_fee_percent': 5,
    },
    'bonus_links': dict(settings.bonus_urls()),
}

@dataclass(frozen=True)
class CooldownState:
    ready: bool
    seconds_left: int
EMOJI_RE = re.compile('[🌀-🗿😀-🙏🚀-\U0001f6ff🜀-🝿🞀-\U0001f7ff🠀-\U0001f8ff🤀-🧿🨀-\U0001fa6f🩰-\U0001faff☀-⛿✀-➿]+', flags=re.UNICODE)

def contains_emoji(text: str) -> bool:
    return bool(EMOJI_RE.search(text))

def normalize_weights(items: list[tuple[str, float]]) -> list[tuple[str, float]]:
    safe = [(k, max(0.0, float(w))) for k, w in items]
    total = sum((w for _, w in safe))
    if total <= 0:
        return [(k, 1.0) for k, _ in safe]
    return [(k, w / total) for k, w in safe]


def escape_md(text: str) -> str:
    for ch in ('\\', '_', '*', '[', ']', '(', ')', '`'):
        text = text.replace(ch, f'\\{ch}')
    return text

class BrawlCardsService:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def ensure_user(self, user_id: int, username: str | None, first_name: str) -> User:
        user = await self.session.get(User, user_id)
        now = utcnow()
        if user is None:
            user = User(id=user_id, username=username, first_name=first_name, last_active_at=now)
            self.session.add(user)
            await self.session.flush()
        else:
            user.username = username
            user.first_name = first_name
            user.last_active_at = now
            await self.session.flush()
        await self.ensure_profile(user_id)
        await self.ensure_settings(user_id)
        return user

    async def ensure_profile(self, user_id: int) -> UserProfile:
        prof = await self.session.get(UserProfile, user_id)
        if prof is None:
            prof = UserProfile(user_id=user_id)
            self.session.add(prof)
            await self.session.flush()
        return prof

    async def ensure_settings(self, user_id: int) -> BcUserSettings:
        row = await self.session.get(BcUserSettings, user_id)
        if row is None:
            row = BcUserSettings(user_id=user_id)
            self.session.add(row)
            await self.session.flush()
        return row

    async def is_premium(self, user_id: int) -> bool:
        user = await self.session.get(User, user_id)
        premium_until = ensure_utc(user.premium_until) if user else None
        return bool(user and premium_until and (premium_until > utcnow()))

    async def get_cooldown(self, user_id: int, action: str) -> CooldownState:
        now = utcnow()
        row = await self.session.get(Cooldown, {'user_id': user_id, 'action': action})
        available_at = ensure_utc(row.available_at) if row else None
        if row is None or available_at is None or available_at <= now:
            return CooldownState(ready=True, seconds_left=0)
        return CooldownState(ready=False, seconds_left=int((available_at - now).total_seconds()))

    async def set_cooldown(self, user_id: int, action: str, seconds: int) -> None:
        now = utcnow()
        available_at = now + timedelta(seconds=max(0, int(seconds)))
        row = await self.session.get(Cooldown, {'user_id': user_id, 'action': action})
        if row is None:
            row = Cooldown(user_id=user_id, action=action, available_at=available_at)
            self.session.add(row)
        else:
            row.available_at = available_at
        await self.session.flush()

    async def get_input_state(self, user_id: int) -> BcInputState | None:
        return await self.session.get(BcInputState, user_id)

    async def set_input_state(self, user_id: int, state: str, payload: dict | None=None) -> None:
        row = await self.session.get(BcInputState, user_id)
        if row is None:
            row = BcInputState(user_id=user_id, state=state, payload=payload or {})
            self.session.add(row)
        else:
            row.state = state
            row.payload = payload or {}
        await self.session.flush()

    async def clear_input_state(self, user_id: int) -> None:
        row = await self.session.get(BcInputState, user_id)
        if row is not None:
            await self.session.delete(row)
            await self.session.flush()

    async def get_system_section(self, section: str) -> dict[str, object]:
        defaults = dict(SYSTEM_SETTINGS_DEFAULTS.get(section, {}))
        row = await self.session.get(Setting, f'bc:{section}')
        if row is None or not isinstance(row.value_json, dict):
            return defaults
        data = dict(defaults)
        data.update(row.value_json)
        return data

    async def set_system_section(self, section: str, payload: dict[str, object]) -> dict[str, object]:
        defaults = dict(SYSTEM_SETTINGS_DEFAULTS.get(section, {}))
        data = dict(defaults)
        data.update(payload)
        row = await self.session.get(Setting, f'bc:{section}')
        if row is None:
            row = Setting(key=f'bc:{section}', value_json=data)
            self.session.add(row)
        else:
            row.value_json = data
        await self.session.flush()
        return data

    async def set_system_value(self, section: str, key: str, value: object) -> dict[str, object]:
        data = await self.get_system_section(section)
        data[key] = value
        return await self.set_system_section(section, data)

    async def resolve_bonus_url(self, task: BcBonusTask) -> str:
        cfg = dict(task.config or {})
        url = str(cfg.get('url') or '').strip()
        if url:
            return url
        links = await self.get_system_section('bonus_links')
        return str(links.get(task.key) or '').strip()

    async def admin_update_user(self, target_user_id: int, field: str, value: str) -> tuple[bool, str]:
        user = await self.session.scalar(select(User).where(User.id == target_user_id).with_for_update())
        if user is None:
            return (False, 'Пользователь не найден.')
        profile = await self.ensure_profile(target_user_id)
        field = field.strip().lower()
        raw_value = value.strip()
        try:
            if field == 'coins':
                user.coins = max(0, int(raw_value))
                result = f'Монеты обновлены: {user.coins}'
            elif field == 'stars':
                user.stars = max(0, int(raw_value))
                result = f'Звезды обновлены: {user.stars}'
            elif field == 'points':
                user.total_points = max(0, int(raw_value))
                result = f'Очки обновлены: {user.total_points}'
            elif field == 'level':
                profile.level = max(1, int(raw_value))
                result = f'Уровень обновлен: {profile.level}'
            elif field == 'exp':
                profile.exp = max(0, int(raw_value))
                result = f'Опыт обновлен: {profile.exp}'
            elif field == 'premium_days':
                days = int(raw_value)
                user.premium_until = None if days <= 0 else utcnow() + timedelta(days=days)
                premium_until = ensure_utc(user.premium_until)
                result = f'Premium до: {premium_until.isoformat(timespec="seconds")}' if premium_until else 'Premium отключен.'
            elif field == 'nickname':
                user.nickname = raw_value or None
                result = f'Ник обновлен: {user.nickname or "—"}'
            elif field.startswith('cooldown:'):
                action = field.split(':', maxsplit=1)[1].strip()
                if not action:
                    return (False, 'Укажите action после cooldown:.')
                seconds = max(0, int(raw_value))
                await self.set_cooldown(target_user_id, action, seconds)
                result = f'Кулдаун {action} установлен на {seconds}с.'
            else:
                return (False, 'Поле не поддерживается.')
        except ValueError:
            return (False, 'Значение имеет неверный формат.')
        await self.session.flush()
        return (True, result)

    async def set_nickname(self, user_id: int, nickname: str) -> tuple[bool, str]:
        user = await self.session.get(User, user_id)
        if user is None:
            return (False, 'Профиль не найден.')
        nickname = nickname.strip()
        if not 3 <= len(nickname) <= 24:
            return (False, 'Длина ника: 3–24 символа.')
        if '\n' in nickname or '\r' in nickname:
            return (False, 'Ник должен быть в одну строку.')
        is_premium = bool(ensure_utc(user.premium_until) and ensure_utc(user.premium_until) > utcnow())
        if not is_premium and contains_emoji(nickname):
            return (False, 'Эмодзи в нике доступны только с Premium.')
        if not re.fullmatch('[0-9A-Za-zА-Яа-я _\\\\-\\\\[\\\\]().,!?:+@#]{3,24}', nickname):
            if not (is_premium and contains_emoji(nickname)):
                return (False, 'Разрешены: буквы/цифры/пробел и символы _-[]().,!?:+@#')
        now = utcnow()
        cooldown_row = await self.session.get(Cooldown, {'user_id': user_id, 'action': 'nick_change'})
        if cooldown_row is not None and ensure_utc(cooldown_row.available_at) > now:
            left = int((ensure_utc(cooldown_row.available_at) - now).total_seconds())
            return (False, f'Кулдаун смены ника: {left // 60}Рј {left % 60}с.')
        cooldowns = await self.get_system_section('cooldowns')
        user.nickname = nickname
        await self.set_cooldown(user_id, 'nick_change', int(cooldowns.get('nick_change') or 24 * 3600))
        await self.session.flush()
        return (True, f'Ник обновлён: {nickname}')

    async def rarities(self) -> list[BcRarity]:
        rows = (await self.session.scalars(select(BcRarity).where(BcRarity.is_active.is_(True)).order_by(BcRarity.sort))).all()
        return list(rows)

    async def active_boosters(self, user_id: int) -> list[BcActiveBooster]:
        now = utcnow()
        rows = (await self.session.scalars(select(BcActiveBooster).where(BcActiveBooster.user_id == user_id).where(BcActiveBooster.active_until.is_(None) | (BcActiveBooster.active_until > now)))).all()
        return list(rows)

    async def bonus_tasks(self) -> list[BcBonusTask]:
        rows = (await self.session.scalars(select(BcBonusTask).where(BcBonusTask.is_active.is_(True)).order_by(BcBonusTask.sort))).all()
        return list(rows)

    async def user_bonus_task(self, user_id: int, task_key: str) -> BcUserBonusTask:
        row = await self.session.get(BcUserBonusTask, {'user_id': user_id, 'task_key': task_key})
        if row is None:
            row = BcUserBonusTask(user_id=user_id, task_key=task_key, completed_at=None, claimed_at=None, state={})
            self.session.add(row)
            await self.session.flush()
        return row

    async def mark_bonus_task_done(self, user_id: int, task_key: str) -> None:
        row = await self.user_bonus_task(user_id, task_key)
        if row.completed_at is None:
            row.completed_at = utcnow()
            await self.session.flush()

    async def bonus_claim_if_ready(self, user_id: int) -> tuple[bool, str]:
        tasks = await self.bonus_tasks()
        if not tasks:
            return (False, 'Бонусные задания не настроены.')
        for t in tasks:
            row = await self.user_bonus_task(user_id, t.key)
            if row.completed_at is None:
                return (False, 'Сначала выполните все бонусные задания и нажмите «Проверить».')
        cd = await self.get_cooldown(user_id, 'bonus')
        if not cd.ready:
            return (False, f'Кулдаун бонуса: {cd.seconds_left}s.')
        runtime_rewards = await self.get_system_section('rewards')
        runtime_cooldowns = await self.get_system_section('cooldowns')
        bonus_coins = int(runtime_rewards.get('bonus_coins') or settings.bonus_reward_coins)
        bonus_stars = int(runtime_rewards.get('bonus_stars') or settings.bonus_reward_stars)
        bonus_cooldown = int(runtime_cooldowns.get('bonus') or settings.bonus_cooldown_seconds)
        user = await self.session.scalar(select(User).where(User.id == user_id).with_for_update())
        if user is None:
            return (False, 'Профиль не найден.')
        user.coins += bonus_coins
        user.stars += bonus_stars
        await self.set_cooldown(user_id, 'bonus', bonus_cooldown)
        await self.session.flush()
        return (True, f'Бонус получен: +{bonus_coins}🪙 +{bonus_stars}⭐')

    async def shop_categories(self) -> list[str]:
        rows = (await self.session.scalars(select(func.distinct(BcShopItem.category_key)).where(BcShopItem.is_active.is_(True)))).all()
        return [str(x) for x in rows]

    async def shop_items(self, category_key: str) -> list[BcShopItem]:
        rows = (await self.session.scalars(select(BcShopItem).where(and_(BcShopItem.category_key == category_key, BcShopItem.is_active.is_(True))).order_by(BcShopItem.sort, BcShopItem.id))).all()
        return list(rows)

    async def shop_item(self, item_key: str) -> BcShopItem | None:
        return await self.session.scalar(select(BcShopItem).where(BcShopItem.key == item_key, BcShopItem.is_active.is_(True)))

    async def shop_offers(self, limit: int=6) -> list[BcShopItem]:
        rows = (
            await self.session.scalars(
                select(BcShopItem)
                .where(BcShopItem.is_active.is_(True))
                .order_by(BcShopItem.sort, BcShopItem.id)
                .limit(limit)
            )
        ).all()
        return list(rows)

    async def active_events(self) -> list[BcEvent]:
        now = utcnow()
        rows = (
            await self.session.scalars(
                select(BcEvent)
                .where(BcEvent.is_active.is_(True))
                .where(or_(BcEvent.starts_at.is_(None), BcEvent.starts_at <= now))
                .where(or_(BcEvent.ends_at.is_(None), BcEvent.ends_at >= now))
                .order_by(BcEvent.starts_at.desc().nullslast(), BcEvent.id.desc())
            )
        ).all()
        return list(rows)

    async def economy_overview(self, user_id: int) -> dict[str, object]:
        user = await self.session.get(User, user_id)
        profile = await self.ensure_profile(user_id)
        if user is None:
            raise ValueError('User not found')
        premium_until = ensure_utc(user.premium_until)
        active_boosters = await self.active_boosters(user_id)
        total_cards = await self.session.scalar(select(func.count()).select_from(BcCardInstance).where(BcCardInstance.user_id == user_id))
        unique_cards = await self.session.scalar(select(func.count(func.distinct(BcCardInstance.card_id))).where(BcCardInstance.user_id == user_id))
        card_cd = await self.get_cooldown(user_id, 'brawl_cards')
        bonus_cd = await self.get_cooldown(user_id, 'bonus')
        return {
            'coins': user.coins,
            'stars': user.stars,
            'points': user.total_points,
            'level': profile.level,
            'premium_until': premium_until,
            'cards_total': int(total_cards or 0),
            'cards_unique': int(unique_cards or 0),
            'boosters_active': len(active_boosters),
            'card_cooldown': card_cd.seconds_left,
            'bonus_cooldown': bonus_cd.seconds_left,
        }

    async def chests(self) -> list[BcChest]:
        rows = (await self.session.scalars(select(BcChest).where(BcChest.is_active.is_(True)).order_by(BcChest.sort))).all()
        return list(rows)

    async def tasks(self, kind: str | None=None) -> list[BcTask]:
        q = select(BcTask).where(BcTask.is_active.is_(True))
        if kind:
            q = q.where(BcTask.kind == kind)
        rows = (await self.session.scalars(q.order_by(BcTask.sort))).all()
        return list(rows)

    async def get_user_task(self, user_id: int, task: BcTask) -> BcUserTask:
        row = await self.session.get(BcUserTask, {'user_id': user_id, 'task_key': task.key})
        if row is None:
            row = BcUserTask(user_id=user_id, task_key=task.key, progress=0, completed_at=None, claimed_at=None, state={})
            self.session.add(row)
            await self.session.flush()
        return row

    async def _period_key(self, kind: str) -> str:
        now = utcnow()
        if kind == 'daily':
            return now.date().isoformat()
        if kind == 'weekly':
            y, w, _ = now.isocalendar()
            return f'{y}-W{w}'
        return 'static'

    async def refresh_task_period(self, row: BcUserTask, task: BcTask) -> None:
        period = await self._period_key(task.kind)
        if row.state.get('period') != period:
            row.state = {'period': period}
            row.progress = 0
            row.completed_at = None
            row.claimed_at = None
            await self.session.flush()

    async def inc_task_counter(self, user_id: int, counter: str, amount: int=1) -> None:
        tasks = await self.tasks()
        for task in tasks:
            cfg = dict(task.config or {})
            if cfg.get('counter') != counter:
                continue
            row = await self.get_user_task(user_id, task)
            await self.refresh_task_period(row, task)
            if row.completed_at is not None:
                continue
            row.progress += int(amount)
            if row.progress >= task.target:
                row.completed_at = utcnow()
            await self.session.flush()

    async def claim_task_reward(self, user_id: int, task_key: str) -> tuple[bool, str]:
        task = await self.session.get(BcTask, task_key)
        if task is None or not task.is_active:
            return (False, 'Задание не найдено.')
        row = await self.get_user_task(user_id, task)
        await self.refresh_task_period(row, task)
        if row.completed_at is None:
            return (False, 'Задание ещё не выполнено.')
        if row.claimed_at is not None:
            return (False, 'Награда уже получена.')
        user = await self.session.get(User, user_id)
        if user is None:
            return (False, 'Профиль не найден.')
        reward = dict(task.reward or {})
        coins = int(reward.get('coins') or 0)
        stars = int(reward.get('stars') or 0)
        points = int(reward.get('points') or 0)
        user.coins += coins
        user.stars += stars
        user.total_points += points
        row.claimed_at = utcnow()
        prof = await self.ensure_profile(user_id)
        prof.tasks_done += 1
        await self.session.flush()
        return (True, f'Награда получена: +{coins}🪙 +{stars}⭐ +{points}✨')

    async def record_game(self, user_id: int, won: bool) -> None:
        prof = await self.ensure_profile(user_id)
        prof.games_played += 1
        if won:
            prof.games_won += 1
        await self.session.flush()


    async def grant_shop_item(self, user_id: int, item_key: str, *, source: str='shop', payment_charge_id: str | None=None, amount_paid: int | None=None) -> tuple[bool, str]:
        user = await self.session.scalar(select(User).where(User.id == user_id).with_for_update())
        if user is None:
            return (False, '\u041f\u0440\u043e\u0444\u0438\u043b\u044c \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d.')
        item = await self.session.scalar(select(BcShopItem).where(BcShopItem.key == item_key, BcShopItem.is_active.is_(True)))
        if item is None:
            return (False, '\u0422\u043e\u0432\u0430\u0440 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d.')
        payload = dict(item.payload or {})
        typ = payload.get('type')
        if typ == 'booster':
            booster_key = str(payload.get('booster_key'))
            amount = int(payload.get('amount') or 1)
            await self.add_booster(user_id, booster_key, amount)
            message = f'\u041f\u043e\u043a\u0443\u043f\u043a\u0430 \u0443\u0441\u043f\u0435\u0448\u043d\u0430: {item.title} x{amount}'
        elif typ == 'activate_booster':
            booster_key = str(payload.get('booster_key'))
            stacks = int(payload.get('stacks') or 1)
            await self.activate_booster(user_id, booster_key, stacks=stacks)
            message = f'\u0410\u043a\u0442\u0438\u0432\u0438\u0440\u043e\u0432\u0430\u043d\u043e: {item.title}'
        elif typ == 'premium':
            days = int(payload.get('days') or 30)
            now = utcnow()
            premium_until = ensure_utc(user.premium_until)
            base = premium_until if premium_until and premium_until > now else now
            user.premium_until = base + timedelta(days=days)
            message = f'Premium \u0430\u043a\u0442\u0438\u0432\u0438\u0440\u043e\u0432\u0430\u043d \u043d\u0430 {days} \u0434.'
        elif typ == 'currency_exchange':
            frm = payload.get('from')
            to = payload.get('to')
            amount = int(payload.get('amount') or 0)
            if frm == 'stars' and to == 'coins':
                user.coins += amount
                message = f'\u041e\u0431\u043c\u0435\u043d \u0432\u044b\u043f\u043e\u043b\u043d\u0435\u043d: +{amount}\U0001fa99'
            else:
                return (False, '\u042d\u0442\u043e\u0442 \u043e\u0431\u043c\u0435\u043d \u043f\u043e\u043a\u0430 \u043d\u0435 \u043f\u043e\u0434\u0434\u0435\u0440\u0436\u0438\u0432\u0430\u0435\u0442\u0441\u044f.')
        else:
            message = '\u041f\u043e\u043a\u0443\u043f\u043a\u0430 \u0432\u044b\u043f\u043e\u043b\u043d\u0435\u043d\u0430.'
        self.session.add(
            BcAuditLog(
                actor_id=user_id,
                action='shop.grant',
                payload={
                    'item_key': item.key,
                    'source': source,
                    'payment_charge_id': payment_charge_id,
                    'amount_paid': amount_paid,
                },
            )
        )
        await self.session.flush()
        return (True, message)

    async def add_booster(self, user_id: int, booster_key: str, amount: int) -> None:
        booster = await self.session.get(BcBooster, booster_key)
        if booster is None:
            raise ValueError('Unknown booster')
        row = await self.session.scalar(select(BcActiveBooster).where(BcActiveBooster.user_id == user_id, BcActiveBooster.booster_key == booster_key))
        if row is None:
            row = BcActiveBooster(user_id=user_id, booster_key=booster_key, stacks=0, active_until=None, meta={})
            self.session.add(row)
        row.stacks = min(int(booster.max_stack), int(row.stacks) + int(amount))
        await self.session.flush()

    async def activate_booster(self, user_id: int, booster_key: str, stacks: int=1) -> None:
        booster = await self.session.get(BcBooster, booster_key)
        if booster is None:
            raise ValueError('Unknown booster')
        now = utcnow()
        row = await self.session.scalar(select(BcActiveBooster).where(BcActiveBooster.user_id == user_id, BcActiveBooster.booster_key == booster_key))
        if row is None:
            row = BcActiveBooster(user_id=user_id, booster_key=booster_key, stacks=0, active_until=None, meta={})
            self.session.add(row)
        row.stacks = min(int(booster.max_stack), int(row.stacks) + int(stacks))
        if booster.duration_seconds > 0:
            base = row.active_until if row.active_until and row.active_until > now else now
            row.active_until = base + timedelta(seconds=int(booster.duration_seconds))
        await self.session.flush()

    async def consume_booster_stack(self, user_id: int, booster_key: str, amount: int=1) -> bool:
        row = await self.session.scalar(select(BcActiveBooster).where(BcActiveBooster.user_id == user_id, BcActiveBooster.booster_key == booster_key))
        if row is None or row.stacks <= 0:
            return False
        row.stacks -= int(amount)
        if row.stacks <= 0 and row.active_until is None:
            await self.session.delete(row)
        await self.session.flush()
        return True

    async def choose_rarity_for_drop(self, user: User, use_luck: bool, extra_weight: dict[str, float] | None=None) -> BcRarity | None:
        rarities = await self.rarities()
        if not rarities:
            return None
        weights: list[tuple[str, float]] = []
        for r in rarities:
            if r.drop_mode not in {'normal', 'event'}:
                continue
            w = float(r.chance)
            if extra_weight and r.key in extra_weight:
                w += float(extra_weight[r.key])
            if ensure_utc(user.premium_until) and ensure_utc(user.premium_until) > utcnow():
                if r.key in {'mythic', 'legendary', 'exclusive'}:
                    w *= 1.25
            if use_luck:
                if r.key in {'rare', 'epic', 'mythic', 'legendary', 'exclusive'}:
                    w *= 1.35
            weights.append((r.key, w))
        norm = normalize_weights(weights)
        keys = [k for k, _ in norm]
        ws = [w for _, w in norm]
        chosen_key = random.choices(keys, weights=ws, k=1)[0]
        for r in rarities:
            if r.key == chosen_key:
                return r
        return rarities[0]

    async def random_card(self, rarity_key: str) -> BcCard | None:
        card = await self.session.scalar(select(BcCard).where(and_(BcCard.rarity_key == rarity_key, BcCard.is_active.is_(True))).order_by(func.random()).limit(1))
        if card is not None:
            return card
        return await self.session.scalar(select(BcCard).where(BcCard.is_active.is_(True)).order_by(func.random()).limit(1))

    async def grant_card(self, user: User, card: BcCard, source: str, rarity: BcRarity) -> BcCardInstance:
        is_premium = bool(ensure_utc(user.premium_until) and ensure_utc(user.premium_until) > utcnow())
        active = await self.active_boosters(user.id)
        points_mult = 1.0
        coins_mult = 1.0
        for b in active:
            booster = await self.session.get(BcBooster, b.booster_key)
            if booster is None:
                continue
            if booster.effect_type == 'coins_mult':
                coins_mult *= 1.0 + float(booster.effect_power) * max(1, int(b.stacks))
            if booster.effect_type == 'points_mult':
                points_mult *= 1.0 + float(booster.effect_power) * max(1, int(b.stacks))
        points = int(card.base_points * rarity.points_mult * points_mult)
        coins = int(card.base_coins * rarity.coins_mult * coins_mult)
        if is_premium:
            coins = int(coins * 1.15)
        inst = BcCardInstance(user_id=user.id, card_id=card.id, source=source, points_awarded=points, coins_awarded=coins, is_limited=bool(card.is_limited), limited_series_id=card.limited_series_id)
        self.session.add(inst)
        user.total_points += points
        user.coins += coins
        user.cards_total += 1
        await self.session.flush()
        state = await self.session.get(BcUserState, user.id)
        now = utcnow()
        if state is None:
            state = BcUserState(user_id=user.id, last_card_instance_id=inst.id, last_card_id=card.id, last_card_got_at=now)
            self.session.add(state)
        else:
            state.last_card_instance_id = inst.id
            state.last_card_id = card.id
            state.last_card_got_at = now
        await self.session.flush()
        return inst

    async def brawl_get_card(self, user_id: int) -> dict:
        user = await self.session.scalar(select(User).where(User.id == user_id).with_for_update())
        if user is None:
            return {'ok': False, 'error': 'Профиль не найден.'}
        cd = await self.get_cooldown(user_id, 'brawl_cards')
        if not cd.ready:
            return {'ok': False, 'cooldown': cd.seconds_left}
        active = await self.active_boosters(user_id)
        use_luck = any((b.booster_key == 'luck' and b.stacks > 0 for b in active))
        use_time = any((b.booster_key == 'time_accel' and b.stacks > 0 for b in active))
        use_limited = any((b.booster_key == 'limited_chance' for b in active))
        extra: dict[str, float] = {}
        if use_limited:
            extra['limited'] = 0.2
        rarity = await self.choose_rarity_for_drop(user, use_luck=use_luck, extra_weight=extra)
        if rarity is None:
            return {'ok': False, 'error': 'Нет настроенных редкостей.'}
        card = await self.random_card(rarity.key)
        if card is None:
            return {'ok': False, 'error': 'Каталог карт пуст (bc_cards).'}
        inst = await self.grant_card(user, card, source='brawl', rarity=rarity)
        runtime_cooldowns = await self.get_system_section('cooldowns')
        cooldown_seconds = int(runtime_cooldowns.get('brawl_cards') or settings.brawl_cooldown_seconds)
        if ensure_utc(user.premium_until) and ensure_utc(user.premium_until) > utcnow():
            cooldown_seconds = int(cooldown_seconds * 0.75)
        if use_time:
            cooldown_seconds = max(300, cooldown_seconds - 3600)
            await self.consume_booster_stack(user_id, 'time_accel', 1)
        if use_luck:
            await self.consume_booster_stack(user_id, 'luck', 1)
        await self.set_cooldown(user_id, 'brawl_cards', cooldown_seconds)
        await self.inc_task_counter(user_id, 'get_cards', 1)
        return {'ok': True, 'instance_id': inst.id, 'card': {'id': card.id, 'title': card.title, 'description': card.description, 'series': card.series, 'rarity_key': rarity.key, 'rarity_title': rarity.title, 'rarity_emoji': rarity.emoji, 'points': inst.points_awarded, 'coins': inst.coins_awarded, 'is_limited': bool(inst.is_limited), 'obtained_at': inst.obtained_at, 'image_file_id': card.image_file_id}, 'cooldown_seconds': cooldown_seconds}

    async def chest_open(self, user_id: int, chest_key: str) -> dict:
        user = await self.session.scalar(select(User).where(User.id == user_id).with_for_update())
        if user is None:
            return {'ok': False, 'error': 'Профиль не найден.'}
        chest = await self.session.get(BcChest, chest_key)
        if chest is None or not chest.is_active:
            return {'ok': False, 'error': 'Сундук не найден.'}
        if chest.price_coins is not None and user.coins < chest.price_coins:
            return {'ok': False, 'error': 'Недостаточно монет.'}
        if chest.price_stars is not None and user.stars < chest.price_stars:
            return {'ok': False, 'error': 'Недостаточно звёзд.'}
        drops = (await self.session.scalars(select(BcChestDrop).where(BcChestDrop.chest_key == chest_key))).all()
        if not drops:
            return {'ok': False, 'error': 'У сундука нет таблицы дропа.'}
        if chest.price_coins is not None:
            user.coins -= chest.price_coins
        if chest.price_stars is not None:
            user.stars -= chest.price_stars
        results: list[dict] = []
        for _ in range(max(1, chest.open_count)):
            rarity_key = random.choices([d.rarity_key for d in drops], weights=[float(d.weight) for d in drops], k=1)[0]
            rarity = await self.session.get(BcRarity, rarity_key)
            if rarity is None:
                continue
            card = await self.random_card(rarity_key)
            if card is None:
                continue
            inst = await self.grant_card(user, card, source=f'chest:{chest_key}', rarity=rarity)
            results.append({'instance_id': inst.id, 'title': card.title, 'rarity': f'{rarity.emoji} {rarity.title}', 'points': inst.points_awarded, 'coins': inst.coins_awarded})
        return {'ok': True, 'chest': {'key': chest.key, 'title': chest.title, 'emoji': chest.emoji}, 'drops': results}

    async def rp_categories(self) -> list[BcRPCategory]:
        rows = (await self.session.scalars(select(BcRPCategory).where(BcRPCategory.is_active.is_(True)).order_by(BcRPCategory.sort))).all()
        return list(rows)

    async def rp_actions(self, category_key: str | None=None) -> list[BcRPAction]:
        q = select(BcRPAction).where(BcRPAction.is_active.is_(True))
        if category_key:
            q = q.where(BcRPAction.category_key == category_key)
        rows = (await self.session.scalars(q.order_by(BcRPAction.sort, BcRPAction.key))).all()
        return list(rows)

    async def resolve_user_reference(self, value: str) -> User | None:
        raw = value.strip()
        if not raw:
            return None
        if raw.startswith('https://t.me/'):
            raw = raw.rsplit('/', maxsplit=1)[-1]
        if raw.startswith('@'):
            raw = raw[1:]
        if raw.isdigit():
            return await self.session.get(User, int(raw))
        return await self.session.scalar(select(User).where(func.lower(User.username) == raw.lower()))

    async def perform_rp_action_payload(self, actor_id: int, action_key: str, target_id: int | None, chat_type: str | None, chat_id: int | None, message_id: int | None) -> dict:
        action = await self.session.get(BcRPAction, action_key)
        if action is None or not action.is_active:
            return {'ok': False, 'message': 'RP-действие не найдено.'}

        scopes = dict(action.allowed_scopes or {})
        scope_key = 'private' if chat_type == 'private' else 'group'
        if scopes and not bool(scopes.get(scope_key, False)):
            return {'ok': False, 'message': f'Это RP-действие недоступно в режиме: {scope_key}.'}

        if action.requires_target and not target_id:
            return {'ok': False, 'need_target': True, 'message': 'Для этого действия нужна цель. Ответьте на сообщение пользователя или отправьте его ID/@username.'}
        if target_id and target_id == actor_id:
            return {'ok': False, 'message': 'Нельзя выбрать себя как цель.'}

        actor = await self.session.get(User, actor_id)
        if actor is None:
            return {'ok': False, 'message': 'Профиль не найден.'}
        target = await self.session.get(User, target_id) if target_id else None
        if action.requires_target and target is None:
            return {'ok': False, 'message': 'Цель не найдена.'}

        cd = await self.get_cooldown(actor_id, f'rp:{action_key}')
        if not cd.ready:
            return {'ok': False, 'message': f'Кулдаун RP-действия: {cd.seconds_left}с.'}

        templates = list(action.templates or []) or ['{actor} использует действие.']
        template = random.choice(templates)
        actor_name = actor.nickname or actor.first_name or str(actor.id)
        actor_ref = f'[{escape_md(actor_name)}](tg://user?id={actor.id})'
        if target is not None:
            target_name = target.nickname or target.first_name or str(target.id)
            target_ref = f'[{escape_md(target_name)}](tg://user?id={target.id})'
        else:
            target_name = 'кого-то'
            target_ref = target_name

        text = template.replace('{actor}', actor_ref).replace('{actor_name}', actor_name).replace('{target}', target_ref).replace('{target_name}', target_name)

        reward = dict(action.reward or {})
        coins = int(reward.get('coins') or 0)
        stars = int(reward.get('stars') or 0)
        points = int(reward.get('points') or 0)
        actor.coins += coins
        actor.stars += stars
        actor.total_points += points
        await self.inc_task_counter(actor_id, 'rp_action', 1)
        self.session.add(BcRPLog(actor_id=actor_id, target_id=target_id, action_key=action_key, chat_id=chat_id, message_id=message_id, text=text))
        await self.set_cooldown(actor_id, f'rp:{action_key}', int(action.cooldown_seconds))

        reward_line = ''
        if any((coins, stars, points)):
            reward_parts: list[str] = []
            if coins:
                reward_parts.append(f'+{coins}🪙')
            if stars:
                reward_parts.append(f'+{stars}⭐')
            if points:
                reward_parts.append(f'+{points}✨')
            reward_line = '\nНаграда: ' + ' '.join(reward_parts)

        media = await self.session.get(BcMedia, action.media_id) if action.media_id else None
        if media is not None and not media.is_active:
            media = None

        await self.session.flush()
        return {
            'ok': True,
            'text': f'{action.emoji} {text}{reward_line}',
            'media': media,
            'action': action,
        }

    async def perform_rp_action(self, actor_id: int, action_key: str, target_id: int | None, chat_id: int | None, message_id: int | None) -> tuple[bool, str]:
        result = await self.perform_rp_action_payload(actor_id, action_key, target_id, None, chat_id, message_id)
        return (bool(result.get('ok')), str(result.get('text') or result.get('message') or 'Ошибка.'))

    async def game_play(self, user_id: int, game_key: str, stake: int) -> tuple[bool, str]:
        user = await self.session.scalar(select(User).where(User.id == user_id).with_for_update())
        if user is None:
            return (False, 'Профиль не найден.')
        if stake <= 0:
            return (False, 'Ставка должна быть больше нуля.')
        if user.coins < stake:
            return (False, 'Недостаточно монет для ставки.')
        cd = await self.get_cooldown(user_id, f'game:{game_key}')
        if not cd.ready:
            return (False, f'Кулдаун игры: {cd.seconds_left}с.')
        user.coins -= stake
        win = False
        multiplier = 0.0
        extra = ''
        if game_key == 'dice':
            roll = random.randint(1, 6)
            multiplier = {1: 0.0, 2: 0.6, 3: 0.9, 4: 1.3, 5: 1.8, 6: 2.5}[roll]
            win = roll >= 4
            extra = f'Выпало: {roll}'
        elif game_key == 'guess_rarity':
            multiplier = random.choice([0.0, 0.0, 0.8, 1.6, 2.2])
            win = multiplier >= 0.8
            extra = 'Выбран случайный шанс редкости.'
        elif game_key == 'coinflip':
            win = random.choice([True, False])
            multiplier = 1.9 if win else 0.0
            extra = 'Орёл/решка решены.'
        elif game_key == 'card_battle':
            multiplier = random.choice([0.0, 0.7, 1.2, 2.0])
            win = multiplier >= 1.2
            extra = 'Битва карточек завершена.'
        elif game_key == 'slot':
            multiplier = random.choice([0.0, 0.0, 0.5, 1.2, 2.8, 4.0])
            win = multiplier >= 1.2
            extra = 'Барабаны остановлены.'
        else:
            user.coins += stake
            return (False, 'Неизвестная мини-игра.')
        payout = int(stake * multiplier)
        if payout > 0:
            user.coins += payout
        await self.record_game(user_id, won=win)
        await self.inc_task_counter(user_id, 'play_dice' if game_key == 'dice' else 'play_game', 1)
        runtime_cooldowns = await self.get_system_section('cooldowns')
        cooldown_seconds = int(runtime_cooldowns.get(game_key) or 60)
        if ensure_utc(user.premium_until) and ensure_utc(user.premium_until) > utcnow():
            reduction = int(runtime_cooldowns.get('premium_game_reduction') or 20)
            cooldown_seconds = max(5, cooldown_seconds - reduction)
        await self.set_cooldown(user_id, f'game:{game_key}', cooldown_seconds)
        await self.session.flush()
        delta = payout - stake
        status = 'Победа' if delta >= 0 else 'Поражение'
        return (True, f'{status}: {extra}\nСтавка: {stake}🪙\nВыплата: {payout}🪙\nИтог: {delta:+}🪙')

    async def market_lots(self, only_limited: bool=False, seller_id: int | None=None, buyer_or_seller_id: int | None=None, active_only: bool=True, limit: int=20) -> list[tuple[BcMarketLot, BcCard, User]]:
        q = select(BcMarketLot, BcCard, User).join(BcCardInstance, BcCardInstance.id == BcMarketLot.card_instance_id).join(BcCard, BcCard.id == BcCardInstance.card_id).join(User, User.id == BcMarketLot.seller_id)
        if active_only:
            q = q.where(BcMarketLot.status == 'active')
        if only_limited:
            q = q.where(BcCard.is_limited.is_(True))
        if seller_id is not None:
            q = q.where(BcMarketLot.seller_id == seller_id)
        if buyer_or_seller_id is not None:
            q = q.where(or_(BcMarketLot.seller_id == buyer_or_seller_id, BcMarketLot.buyer_id == buyer_or_seller_id))
        rows = (await self.session.execute(q.order_by(BcMarketLot.created_at.desc()).limit(limit))).all()
        return [(lot, card, seller) for lot, card, seller in rows]

    async def market_sell_instance(self, user_id: int, instance_id: int, currency: str, price: int) -> tuple[bool, str]:
        if currency not in {'coins', 'stars'}:
            return (False, 'Валюта только coins или stars.')
        if price <= 0:
            return (False, 'Цена должна быть положительной.')
        inst = await self.session.get(BcCardInstance, instance_id)
        if inst is None or inst.user_id != user_id:
            return (False, 'Экземпляр карты не найден.')
        if await self.session.scalar(select(BcMarketLot).where(BcMarketLot.card_instance_id == instance_id)):
            return (False, 'Эта карта уже выставлена.')
        runtime_rewards = await self.get_system_section('rewards')
        fee_percent = max(0, int(runtime_rewards.get('market_fee_percent') or 5))
        lot = BcMarketLot(seller_id=user_id, card_instance_id=instance_id, currency=currency, price=price, fee_percent=fee_percent, status='active', buyer_id=None)
        self.session.add(lot)
        await self.session.flush()
        return (True, f'Лот #{lot.id} выставлен на маркет.')

    async def market_buy_lot(self, user_id: int, lot_id: int) -> tuple[bool, str]:
        lot = await self.session.scalar(select(BcMarketLot).where(BcMarketLot.id == lot_id).with_for_update())
        if lot is None or lot.status != 'active':
            return (False, 'Лот недоступен.')
        if lot.seller_id == user_id:
            return (False, 'Нельзя купить свой лот.')
        buyer = await self.session.scalar(select(User).where(User.id == user_id).with_for_update())
        seller = await self.session.scalar(select(User).where(User.id == lot.seller_id).with_for_update())
        if buyer is None or seller is None:
            return (False, 'Профиль не найден.')
        if lot.currency == 'coins':
            if buyer.coins < lot.price:
                return (False, 'Недостаточно монет.')
            buyer.coins -= lot.price
            seller.coins += int(lot.price * (100 - lot.fee_percent) / 100)
        else:
            if buyer.stars < lot.price:
                return (False, 'Недостаточно звёзд.')
            buyer.stars -= lot.price
            seller.stars += int(lot.price * (100 - lot.fee_percent) / 100)
        inst = await self.session.get(BcCardInstance, lot.card_instance_id)
        if inst is None:
            return (False, 'Карта лота не найдена.')
        inst.user_id = user_id
        lot.status = 'sold'
        lot.buyer_id = user_id
        lot.bought_at = utcnow()
        await self.session.flush()
        return (True, 'Покупка успешно завершена.')

    async def market_cancel_lot(self, user_id: int, lot_id: int) -> tuple[bool, str]:
        lot = await self.session.get(BcMarketLot, lot_id)
        if lot is None:
            return (False, 'Лот не найден.')
        if lot.seller_id != user_id:
            return (False, 'Это не ваш лот.')
        if lot.status != 'active':
            return (False, 'Лот уже закрыт.')
        lot.status = 'cancelled'
        await self.session.flush()
        return (True, 'Лот снят с продажи.')

    async def marriage_of(self, user_id: int) -> Marriage | None:
        return await self.session.scalar(select(Marriage).where(or_(Marriage.user1_id == user_id, Marriage.user2_id == user_id)).limit(1))

    async def marriage_propose(self, proposer_id: int, target_id: int) -> tuple[bool, str]:
        if proposer_id == target_id:
            return (False, 'Нельзя предложить брак самому себе.')
        if await self.marriage_of(proposer_id) or await self.marriage_of(target_id):
            return (False, 'Один из пользователей уже состоит в браке.')
        pending = await self.session.scalar(select(BcMarriageProposal).where(BcMarriageProposal.proposer_id == proposer_id, BcMarriageProposal.target_id == target_id, BcMarriageProposal.status == 'pending'))
        if pending is not None:
            return (False, 'Предложение уже отправлено.')
        proposal = BcMarriageProposal(proposer_id=proposer_id, target_id=target_id, status='pending')
        self.session.add(proposal)
        await self.session.flush()
        return (True, f'Предложение отправлено. ID: {proposal.id}')

    async def marriage_inbox(self, user_id: int) -> list[BcMarriageProposal]:
        rows = (await self.session.scalars(select(BcMarriageProposal).where(BcMarriageProposal.target_id == user_id, BcMarriageProposal.status == 'pending').order_by(BcMarriageProposal.created_at.desc()))).all()
        return list(rows)

    async def marriage_decide(self, user_id: int, proposal_id: int, accept: bool) -> tuple[bool, str]:
        proposal = await self.session.get(BcMarriageProposal, proposal_id)
        if proposal is None or proposal.target_id != user_id or proposal.status != 'pending':
            return (False, 'Предложение не найдено.')
        proposal.status = 'accepted' if accept else 'declined'
        proposal.decided_at = utcnow()
        if not accept:
            await self.session.flush()
            return (True, 'Предложение отклонено.')
        if await self.marriage_of(proposal.proposer_id) or await self.marriage_of(proposal.target_id):
            await self.session.flush()
            return (False, 'Брак уже создан ранее.')
        self.session.add(Marriage(user1_id=proposal.proposer_id, user2_id=proposal.target_id))
        await self.session.flush()
        return (True, 'Поздравляем, брак зарегистрирован.')

    async def is_admin(self, user_id: int) -> bool:
        if user_id in get_settings().admin_id_set():
            return True
        role = await self.session.scalar(select(BcUserRole).where(BcUserRole.user_id == user_id).limit(1))
        return role is not None

    async def user_settings(self, user_id: int) -> BcUserSettings:
        return await self.ensure_settings(user_id)

    async def get_template_text(self, key: str, locale: str, fallback: str) -> str:
        row = await self.session.get(BcTextTemplate, {'key': key, 'locale': locale})
        if row is not None and row.text.strip():
            return row.text
        if locale != 'ru':
            row = await self.session.get(BcTextTemplate, {'key': key, 'locale': 'ru'})
            if row is not None and row.text.strip():
                return row.text
        return fallback

    async def upsert_template_text(self, key: str, locale: str, text: str) -> None:
        row = await self.session.get(BcTextTemplate, {'key': key, 'locale': locale})
        if row is None:
            self.session.add(BcTextTemplate(key=key, locale=locale, text=text))
        else:
            row.text = text
        await self.session.flush()

    async def toggle_setting(self, user_id: int, key: str) -> tuple[bool, str]:
        s = await self.ensure_settings(user_id)
        if key == 'notifications':
            s.notifications = not bool(s.notifications)
            await self.session.flush()
            return (True, f'Уведомления: {('РІРєР»' if s.notifications else 'выкл')}')
        if key == 'privacy':
            current = bool((s.privacy or {}).get('hidden'))
            s.privacy = {'hidden': not current}
            await self.session.flush()
            return (True, f'Приватность: {('скрытый профиль' if not current else 'открытый профиль')}')
        if key == 'confirm':
            s.confirm_purchases = not bool(s.confirm_purchases)
            await self.session.flush()
            return (True, f'Подтверждение покупок: {('РІРєР»' if s.confirm_purchases else 'выкл')}')
        if key == 'media':
            s.show_media = not bool(s.show_media)
            await self.session.flush()
            return (True, f'Показ медиа: {('РІРєР»' if s.show_media else 'выкл')}')
        if key == 'safe_mode':
            s.safe_mode = not bool(s.safe_mode)
            await self.session.flush()
            return (True, f'Безопасный режим: {('РІРєР»' if s.safe_mode else 'выкл')}')
        return (False, 'Неизвестная настройка.')

    async def cycle_setting(self, user_id: int, key: str) -> tuple[bool, str]:
        s = await self.ensure_settings(user_id)
        if key == 'locale':
            s.locale = 'en' if s.locale == 'ru' else 'ru'
            await self.session.flush()
            return (True, f'Язык: {s.locale.upper()}')
        if key == 'card_style':
            order = ['full', 'compact', 'minimal']
            current = s.card_style if s.card_style in order else 'full'
            idx = order.index(current)
            s.card_style = order[(idx + 1) % len(order)]
            await self.session.flush()
            return (True, f'Стиль карточек: {s.card_style}')
        return (False, 'Неизвестная настройка.')
