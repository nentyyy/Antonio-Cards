from __future__ import annotations

import random
import re
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import DEFAULT_DROP_RATES, DEFAULT_SHOP_PRICES, get_settings
from app.db.models import (
    CardCatalog,
    Cooldown,
    MarketListing,
    MarketStatus,
    Marriage,
    Setting,
    Transaction,
    User,
    UserBooster,
    UserCard,
    UserState,
)
from app.utils.time import utcnow

settings = get_settings()


@dataclass
class CooldownState:
    ready: bool
    seconds_left: int


def _normalize_rates(rates: dict[str, float]) -> dict[str, float]:
    safe = {k: max(0.0, float(v)) for k, v in rates.items()}
    total = sum(safe.values())
    if total <= 0:
        safe = DEFAULT_DROP_RATES.copy()
        total = sum(safe.values())
    return {k: (v / total) * 100.0 for k, v in safe.items()}


def _is_emoji_allowed(user: User) -> bool:
    return bool(user.premium_until and user.premium_until > utcnow())


EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F5FF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF"
    "\u2600-\u26FF"
    "\u2700-\u27BF"
    "]+",
    flags=re.UNICODE,
)


def _contains_emoji(text: str) -> bool:
    return bool(EMOJI_RE.search(text))


class GameService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def ensure_user(self, user_id: int, username: str | None, first_name: str) -> User:
        user = await self.session.get(User, user_id)
        now = utcnow()
        if user is None:
            user = User(id=user_id, username=username, first_name=first_name, last_active_at=now)
            self.session.add(user)
        else:
            user.username = username
            user.first_name = first_name
            user.last_active_at = now
        await self.session.flush()
        return user

    async def get_user(self, user_id: int) -> User | None:
        return await self.session.get(User, user_id)

    async def set_nickname(self, user_id: int, nickname: str) -> tuple[bool, str]:
        user = await self.session.get(User, user_id)
        if user is None:
            return False, "User not found"

        if len(nickname) > 32:
            return False, "Nickname is too long (max 32 chars)."

        allow_emoji = _is_emoji_allowed(user)
        if not allow_emoji:
            if _contains_emoji(nickname):
                return False, "Emoji in nickname is premium-only."

        user.nickname = nickname
        await self.session.flush()
        return True, f"Nickname set to: {nickname}"

    async def get_setting(self, key: str, default: dict) -> dict:
        row = await self.session.get(Setting, key)
        if row is None:
            row = Setting(key=key, value_json=default)
            self.session.add(row)
            await self.session.flush()
            return dict(default)
        return dict(row.value_json or default)

    async def set_setting(self, key: str, value: dict) -> None:
        row = await self.session.get(Setting, key)
        if row is None:
            row = Setting(key=key, value_json=value)
            self.session.add(row)
        else:
            row.value_json = value
        await self.session.flush()

    async def get_drop_rates(self) -> dict[str, float]:
        rates = await self.get_setting("drop_rates", DEFAULT_DROP_RATES)
        merged = DEFAULT_DROP_RATES.copy()
        merged.update({k: float(v) for k, v in rates.items() if k in merged})
        return _normalize_rates(merged)

    async def set_drop_rates(self, rates: dict[str, float]) -> dict[str, float]:
        normalized = _normalize_rates(rates)
        await self.set_setting("drop_rates", normalized)
        return normalized

    async def get_shop_prices(self) -> dict:
        prices = await self.get_setting("shop_prices", DEFAULT_SHOP_PRICES)
        merged = DEFAULT_SHOP_PRICES.copy()
        merged.update(prices)
        return merged

    async def set_shop_prices(self, prices: dict) -> dict:
        current = await self.get_shop_prices()
        current.update(prices)
        await self.set_setting("shop_prices", current)
        return current

    async def get_cooldown(self, user_id: int, action: str) -> CooldownState:
        now = utcnow()
        row = await self.session.get(Cooldown, {"user_id": user_id, "action": action})
        if row is None or row.available_at <= now:
            return CooldownState(ready=True, seconds_left=0)
        delta = int((row.available_at - now).total_seconds())
        return CooldownState(ready=False, seconds_left=max(1, delta))

    async def set_cooldown(self, user_id: int, action: str, seconds: int) -> None:
        available_at = utcnow() + timedelta(seconds=max(0, seconds))
        row = await self.session.get(Cooldown, {"user_id": user_id, "action": action})
        if row is None:
            row = Cooldown(user_id=user_id, action=action, available_at=available_at)
            self.session.add(row)
        else:
            row.available_at = available_at
        await self.session.flush()

    async def _get_boosters(self, user_id: int) -> UserBooster:
        row = await self.session.get(UserBooster, user_id)
        if row is None:
            row = UserBooster(user_id=user_id, luck_count=0, timewarp_count=0)
            self.session.add(row)
            await self.session.flush()
        return row

    async def _record_tx(
        self,
        user_id: int,
        tx_type: str,
        currency: str,
        amount_spent: int,
        payload: dict,
    ) -> None:
        self.session.add(
            Transaction(
                user_id=user_id,
                type=tx_type,
                currency=currency,
                amount_spent=amount_spent,
                payload=payload,
            )
        )
        await self.session.flush()

    async def _choose_rarity(self, user: User, use_luck_booster: bool) -> str:
        rates = await self.get_drop_rates()
        if user.premium_until and user.premium_until > utcnow():
            rates["mythic"] *= 1.35
            rates["legendary"] *= 1.35
            rates = _normalize_rates(rates)

        if use_luck_booster:
            rates["rare"] *= 1.35
            rates["mythic"] *= 1.35
            rates["legendary"] *= 1.35
            rates = _normalize_rates(rates)

        keys = list(rates.keys())
        weights = [rates[k] for k in keys]
        return random.choices(keys, weights=weights, k=1)[0]

    async def _random_card(self, rarity: str, fallback_any: bool = True) -> CardCatalog | None:
        card = await self.session.scalar(
            select(CardCatalog)
            .where(and_(CardCatalog.rarity == rarity, CardCatalog.is_active.is_(True)))
            .order_by(func.random())
            .limit(1)
        )
        if card is not None:
            return card
        if not fallback_any:
            return None
        return await self.session.scalar(
            select(CardCatalog)
            .where(CardCatalog.is_active.is_(True))
            .order_by(func.random())
            .limit(1)
        )

    async def _grant_card(
        self,
        user: User,
        card: CardCatalog,
        count: int,
        source: str,
        premium_coin_bonus: bool = False,
    ) -> int:
        now = utcnow()
        row = await self.session.get(UserCard, {"user_id": user.id, "card_id": card.card_id})
        new_unique = 0
        if row is None:
            row = UserCard(user_id=user.id, card_id=card.card_id, amount=0, first_drop_at=now, last_drop_at=now)
            self.session.add(row)
            new_unique = 1

        row.amount += count
        row.last_drop_at = now

        coins_gain = card.coin_reward * count
        if premium_coin_bonus:
            coins_gain = int(coins_gain * 1.3)

        user.total_points += card.base_points * count
        user.cards_total += count
        user.cards_unique += new_unique
        user.coins += coins_gain

        state = await self.session.get(UserState, user.id)
        if state is None:
            state = UserState(user_id=user.id, last_card_id=card.card_id, last_card_got_at=now)
            self.session.add(state)
        else:
            state.last_card_id = card.card_id
            state.last_card_got_at = now

        await self._record_tx(
            user.id,
            tx_type=f"card_grant_{source}",
            currency="card",
            amount_spent=-count,
            payload={"card_id": card.card_id, "rarity": card.rarity, "count": count},
        )
        await self._record_tx(
            user.id,
            tx_type=f"coins_reward_{source}",
            currency="coins",
            amount_spent=-coins_gain,
            payload={"card_id": card.card_id, "count": count},
        )
        return coins_gain

    async def brawl(self, user_id: int) -> dict:
        async with self.session.begin():
            user = await self.session.scalar(select(User).where(User.id == user_id).with_for_update())
            if user is None:
                raise ValueError("User not found")

            cd = await self.get_cooldown(user_id, "brawl")
            if not cd.ready:
                return {"ok": False, "cooldown": cd.seconds_left}

            boosters = await self._get_boosters(user_id)
            use_luck = boosters.luck_count > 0
            use_timewarp = boosters.timewarp_count > 0
            if use_luck:
                boosters.luck_count -= 1
            if use_timewarp:
                boosters.timewarp_count -= 1

            rarity = await self._choose_rarity(user, use_luck_booster=use_luck)
            card = await self._random_card(rarity)
            if card is None:
                return {"ok": False, "error": "Cards catalog is empty"}

            premium = bool(user.premium_until and user.premium_until > utcnow())
            coins_gain = await self._grant_card(user, card, 1, source="brawl", premium_coin_bonus=premium)

            cooldown_seconds = int((await self.get_setting("cooldowns", {})).get("brawl", settings.brawl_cooldown_seconds))
            if premium:
                cooldown_seconds = int(cooldown_seconds * 0.75)
            if use_timewarp:
                cooldown_seconds = max(300, cooldown_seconds - 3600)
            await self.set_cooldown(user_id, "brawl", cooldown_seconds)

            card_amount = await self.session.scalar(
                select(UserCard.amount).where(and_(UserCard.user_id == user_id, UserCard.card_id == card.card_id))
            )

            return {
                "ok": True,
                "card_id": card.card_id,
                "title": card.title,
                "description": card.description,
                "rarity": card.rarity,
                "base_points": card.base_points,
                "coin_reward": coins_gain,
                "amount": card_amount or 1,
                "image_file_id": card.image_file_id,
                "cooldown": cooldown_seconds,
                "used_luck": use_luck,
                "used_timewarp": use_timewarp,
            }

    async def claim_bonus(self, user_id: int) -> dict:
        async with self.session.begin():
            user = await self.session.scalar(select(User).where(User.id == user_id).with_for_update())
            if user is None:
                raise ValueError("User not found")

            cd = await self.get_cooldown(user_id, "bonus")
            if not cd.ready:
                return {"ok": False, "cooldown": cd.seconds_left}

            reward_coins = int((await self.get_setting("rewards", {})).get("bonus_coins", settings.bonus_reward_coins))
            reward_stars = int((await self.get_setting("rewards", {})).get("bonus_stars", settings.bonus_reward_stars))

            user.coins += reward_coins
            user.stars += reward_stars
            await self._record_tx(
                user_id,
                tx_type="bonus_reward",
                currency="coins",
                amount_spent=-reward_coins,
                payload={"stars": reward_stars},
            )
            if reward_stars:
                await self._record_tx(
                    user_id,
                    tx_type="bonus_reward",
                    currency="stars",
                    amount_spent=-reward_stars,
                    payload={},
                )

            cd_seconds = int((await self.get_setting("cooldowns", {})).get("bonus", settings.bonus_cooldown_seconds))
            await self.set_cooldown(user_id, "bonus", cd_seconds)
            return {"ok": True, "coins": reward_coins, "stars": reward_stars, "cooldown": cd_seconds}

    async def dice_play(self, user_id: int, dice_value: int) -> dict:
        rewards = {1: 0, 2: 10, 3: 20, 4: 35, 5: 55, 6: 90}
        async with self.session.begin():
            user = await self.session.scalar(select(User).where(User.id == user_id).with_for_update())
            if user is None:
                raise ValueError("User not found")

            cd = await self.get_cooldown(user_id, "diceplay")
            if not cd.ready:
                return {"ok": False, "cooldown": cd.seconds_left}

            premium = bool(user.premium_until and user.premium_until > utcnow())
            reward = rewards.get(dice_value, 0)
            user.coins += reward
            await self._record_tx(
                user_id,
                tx_type="dice_reward",
                currency="coins",
                amount_spent=-reward,
                payload={"dice": dice_value},
            )

            cd_seconds = int((await self.get_setting("cooldowns", {})).get("diceplay", settings.dice_cooldown_seconds))
            if premium:
                cd_seconds = int(cd_seconds * 0.7)
            await self.set_cooldown(user_id, "diceplay", cd_seconds)
            return {"ok": True, "reward": reward, "cooldown": cd_seconds}

    async def activate_premium(self, user_id: int, days: int = 30, cost_stars: int | None = None) -> dict:
        async with self.session.begin():
            user = await self.session.scalar(select(User).where(User.id == user_id).with_for_update())
            if user is None:
                raise ValueError("User not found")

            prices = await self.get_shop_prices()
            price = cost_stars if cost_stars is not None else int(prices.get("premium_30d_stars", 50))
            if user.stars < price:
                return {"ok": False, "error": "Not enough stars", "price": price}

            user.stars -= price
            base = user.premium_until if user.premium_until and user.premium_until > utcnow() else utcnow()
            user.premium_until = base + timedelta(days=days)

            await self._record_tx(
                user_id,
                tx_type="premium_purchase",
                currency="stars",
                amount_spent=price,
                payload={"days": days},
            )
            return {"ok": True, "until": user.premium_until, "price": price}

    async def buy_booster(self, user_id: int, booster_name: str) -> dict:
        if booster_name not in {"luck", "timewarp"}:
            return {"ok": False, "error": "Unknown booster"}

        async with self.session.begin():
            user = await self.session.scalar(select(User).where(User.id == user_id).with_for_update())
            if user is None:
                raise ValueError("User not found")

            prices = await self.get_shop_prices()
            key = "luck_booster_coins" if booster_name == "luck" else "timewarp_booster_coins"
            price = int(prices.get(key, 250))
            if user.coins < price:
                return {"ok": False, "error": "Not enough coins", "price": price}

            user.coins -= price
            boosters = await self._get_boosters(user_id)
            if booster_name == "luck":
                boosters.luck_count += 1
            else:
                boosters.timewarp_count += 1

            await self._record_tx(
                user_id,
                tx_type="shop_booster",
                currency="coins",
                amount_spent=price,
                payload={"booster": booster_name},
            )

            return {
                "ok": True,
                "booster": booster_name,
                "price": price,
                "luck": boosters.luck_count,
                "timewarp": boosters.timewarp_count,
            }

    async def buy_coin_pack(self, user_id: int, pack: str) -> dict:
        if pack not in {"small", "big"}:
            return {"ok": False, "error": "Unknown pack"}

        async with self.session.begin():
            user = await self.session.scalar(select(User).where(User.id == user_id).with_for_update())
            if user is None:
                raise ValueError("User not found")

            prices = await self.get_shop_prices()
            stars_key = f"coins_pack_{pack}_stars"
            amount_key = f"coins_pack_{pack}_amount"
            stars_price = int(prices.get(stars_key, 5))
            coin_amount = int(prices.get(amount_key, 500))
            if user.stars < stars_price:
                return {"ok": False, "error": "Not enough stars", "price": stars_price}

            user.stars -= stars_price
            user.coins += coin_amount

            await self._record_tx(
                user_id,
                tx_type="shop_coin_pack",
                currency="stars",
                amount_spent=stars_price,
                payload={"pack": pack, "coins": coin_amount},
            )
            await self._record_tx(
                user_id,
                tx_type="shop_coin_pack_reward",
                currency="coins",
                amount_spent=-coin_amount,
                payload={"pack": pack},
            )

            return {"ok": True, "pack": pack, "stars": stars_price, "coins": coin_amount}

    async def open_chest(self, user_id: int, rarity: str) -> dict:
        rarity = rarity.lower()
        if rarity not in {"common", "rare", "mythic", "legendary"}:
            return {"ok": False, "error": "Unknown chest rarity"}

        async with self.session.begin():
            user = await self.session.scalar(select(User).where(User.id == user_id).with_for_update())
            if user is None:
                raise ValueError("User not found")

            prices = await self.get_shop_prices()
            price = int(prices.get(f"chest_{rarity}_coins", 1000))
            if user.coins < price:
                return {"ok": False, "error": "Not enough coins", "price": price}

            user.coins -= price
            await self._record_tx(
                user_id,
                tx_type="chest_purchase",
                currency="coins",
                amount_spent=price,
                payload={"rarity": rarity},
            )

            premium = bool(user.premium_until and user.premium_until > utcnow())
            gained: list[dict] = []
            for _ in range(5):
                card = await self._random_card(rarity, fallback_any=False)
                if card is None:
                    continue
                coins = await self._grant_card(user, card, 1, source=f"chest_{rarity}", premium_coin_bonus=premium)
                amount = await self.session.scalar(
                    select(UserCard.amount).where(and_(UserCard.user_id == user_id, UserCard.card_id == card.card_id))
                )
                gained.append(
                    {
                        "card_id": card.card_id,
                        "title": card.title,
                        "rarity": card.rarity,
                        "coins": coins,
                        "amount": amount or 1,
                    }
                )

            return {"ok": True, "rarity": rarity, "price": price, "cards": gained}

    async def top(self, metric: str) -> list[User]:
        column = {
            "points": User.total_points,
            "cards": User.cards_total,
            "coins": User.coins,
        }.get(metric, User.total_points)
        rows = await self.session.scalars(select(User).order_by(column.desc()).limit(10))
        return list(rows)

    async def last_card(self, user_id: int) -> CardCatalog | None:
        card = await self.session.scalar(
            select(CardCatalog)
            .join(UserState, UserState.last_card_id == CardCatalog.card_id)
            .where(UserState.user_id == user_id)
        )
        return card

    async def boosters_info(self, user_id: int) -> UserBooster:
        return await self._get_boosters(user_id)

    async def create_marriage(self, user1_id: int, user2_id: int) -> dict:
        if user1_id == user2_id:
            return {"ok": False, "error": "Cannot marry yourself"}

        async with self.session.begin():
            existing = await self.session.scalar(
                select(Marriage).where(
                    or_(
                        Marriage.user1_id.in_([user1_id, user2_id]),
                        Marriage.user2_id.in_([user1_id, user2_id]),
                    )
                )
            )
            if existing:
                return {"ok": False, "error": "One of users is already married"}

            pair = Marriage(user1_id=user1_id, user2_id=user2_id)
            self.session.add(pair)
            await self.session.flush()
            return {"ok": True, "pair_id": pair.id}

    async def get_market_listings(self, limit: int = 20) -> list[MarketListing]:
        rows = await self.session.scalars(
            select(MarketListing)
            .where(MarketListing.status == MarketStatus.ACTIVE.value)
            .order_by(MarketListing.created_at.desc())
            .limit(limit)
        )
        return list(rows)

    async def get_market_listings_view(self, limit: int = 20) -> list[dict]:
        rows = await self.session.execute(
            select(MarketListing, CardCatalog.title, CardCatalog.rarity)
            .join(CardCatalog, CardCatalog.card_id == MarketListing.card_id)
            .where(MarketListing.status == MarketStatus.ACTIVE.value)
            .order_by(MarketListing.created_at.desc())
            .limit(limit)
        )
        data: list[dict] = []
        for listing, title, rarity in rows.all():
            data.append(
                {
                    "id": listing.id,
                    "seller_id": listing.seller_id,
                    "card_id": listing.card_id,
                    "title": title,
                    "rarity": rarity,
                    "amount": listing.amount,
                    "currency": listing.currency,
                    "price": listing.price,
                }
            )
        return data

    async def market_sell(
        self, user_id: int, card_id: int, amount: int, currency: str, price: int
    ) -> dict:
        if currency not in {"coins", "stars"}:
            return {"ok": False, "error": "Currency must be coins or stars"}
        if amount <= 0 or price <= 0:
            return {"ok": False, "error": "Amount and price must be positive"}

        async with self.session.begin():
            card = await self.session.get(CardCatalog, card_id)
            if card is None or card.rarity != "limited":
                return {"ok": False, "error": "Only limited cards can be sold"}

            uc = await self.session.scalar(
                select(UserCard)
                .where(and_(UserCard.user_id == user_id, UserCard.card_id == card_id))
                .with_for_update()
            )
            if uc is None or uc.amount < amount:
                return {"ok": False, "error": "Not enough cards"}

            uc.amount -= amount
            user = await self.session.scalar(select(User).where(User.id == user_id).with_for_update())
            if user is None:
                return {"ok": False, "error": "User not found"}
            user.cards_total = max(0, user.cards_total - amount)
            if uc.amount == 0:
                user.cards_unique = max(0, user.cards_unique - 1)
            listing = MarketListing(
                seller_id=user_id,
                card_id=card_id,
                amount=amount,
                currency=currency,
                price=price,
                status=MarketStatus.ACTIVE.value,
            )
            self.session.add(listing)
            await self._record_tx(
                user_id,
                tx_type="market_list",
                currency="card",
                amount_spent=amount,
                payload={"card_id": card_id, "amount": amount, "price": price, "currency": currency},
            )
            await self.session.flush()
            return {"ok": True, "listing_id": listing.id}

    async def market_cancel(self, user_id: int, listing_id: int) -> dict:
        async with self.session.begin():
            listing = await self.session.scalar(
                select(MarketListing)
                .where(MarketListing.id == listing_id)
                .with_for_update()
            )
            if listing is None:
                return {"ok": False, "error": "Listing not found"}
            if listing.seller_id != user_id:
                return {"ok": False, "error": "Not your listing"}
            if listing.status != MarketStatus.ACTIVE.value:
                return {"ok": False, "error": "Listing is not active"}

            listing.status = MarketStatus.CANCELLED.value
            uc = await self.session.get(UserCard, {"user_id": user_id, "card_id": listing.card_id})
            user = await self.session.scalar(select(User).where(User.id == user_id).with_for_update())
            now = utcnow()
            new_unique = 0
            if uc is None:
                uc = UserCard(
                    user_id=user_id,
                    card_id=listing.card_id,
                    amount=listing.amount,
                    first_drop_at=now,
                    last_drop_at=now,
                )
                self.session.add(uc)
                new_unique = 1
            else:
                uc.amount += listing.amount
                uc.last_drop_at = now
            if user is not None:
                user.cards_total += listing.amount
                user.cards_unique += new_unique

            await self._record_tx(
                user_id,
                tx_type="market_cancel",
                currency="card",
                amount_spent=-listing.amount,
                payload={"listing_id": listing.id, "card_id": listing.card_id},
            )
            return {"ok": True}

    async def market_buy(self, buyer_id: int, listing_id: int) -> dict:
        async with self.session.begin():
            listing = await self.session.scalar(
                select(MarketListing)
                .where(MarketListing.id == listing_id)
                .with_for_update()
            )
            if listing is None or listing.status != MarketStatus.ACTIVE.value:
                return {"ok": False, "error": "Listing not available"}
            if listing.seller_id == buyer_id:
                return {"ok": False, "error": "Cannot buy your own listing"}

            buyer = await self.session.scalar(select(User).where(User.id == buyer_id).with_for_update())
            seller = await self.session.scalar(select(User).where(User.id == listing.seller_id).with_for_update())
            if buyer is None or seller is None:
                return {"ok": False, "error": "Buyer or seller not found"}

            prices = await self.get_shop_prices()
            fee_percent = int(prices.get("market_fee_percent", 5))
            fee = int(listing.price * fee_percent / 100)
            seller_gain = listing.price - fee

            if listing.currency == "coins":
                if buyer.coins < listing.price:
                    return {"ok": False, "error": "Not enough coins"}
                buyer.coins -= listing.price
                seller.coins += seller_gain
            else:
                if buyer.stars < listing.price:
                    return {"ok": False, "error": "Not enough stars"}
                buyer.stars -= listing.price
                seller.stars += seller_gain

            listing.status = MarketStatus.SOLD.value
            listing.buyer_id = buyer_id
            listing.bought_at = utcnow()

            uc = await self.session.get(UserCard, {"user_id": buyer_id, "card_id": listing.card_id})
            now = utcnow()
            new_unique = 0
            if uc is None:
                uc = UserCard(
                    user_id=buyer_id,
                    card_id=listing.card_id,
                    amount=listing.amount,
                    first_drop_at=now,
                    last_drop_at=now,
                )
                self.session.add(uc)
                new_unique = 1
            else:
                uc.amount += listing.amount
                uc.last_drop_at = now

            buyer.cards_total += listing.amount
            buyer.cards_unique += new_unique

            await self._record_tx(
                buyer_id,
                tx_type="market_buy",
                currency=listing.currency,
                amount_spent=listing.price,
                payload={"listing_id": listing.id, "card_id": listing.card_id, "amount": listing.amount},
            )
            await self._record_tx(
                listing.seller_id,
                tx_type="market_sale",
                currency=listing.currency,
                amount_spent=-seller_gain,
                payload={"listing_id": listing.id, "fee": fee},
            )
            return {
                "ok": True,
                "card_id": listing.card_id,
                "amount": listing.amount,
                "currency": listing.currency,
                "price": listing.price,
                "fee": fee,
            }

    async def admin_add_card(
        self,
        title: str,
        description: str,
        rarity: str,
        base_points: int,
        coin_reward: int,
        image_file_id: str | None,
    ) -> CardCatalog:
        if rarity not in {"common", "rare", "mythic", "legendary", "limited"}:
            raise ValueError("Invalid rarity")
        card = CardCatalog(
            title=title,
            description=description,
            rarity=rarity,
            base_points=base_points,
            coin_reward=coin_reward,
            image_file_id=image_file_id,
            is_active=True,
        )
        self.session.add(card)
        await self.session.flush()
        return card

    async def admin_edit_card(self, card_id: int, field: str, value: str) -> dict:
        card = await self.session.get(CardCatalog, card_id)
        if card is None:
            return {"ok": False, "error": "Card not found"}

        if field not in {
            "title",
            "description",
            "rarity",
            "base_points",
            "coin_reward",
            "image_file_id",
            "is_active",
        }:
            return {"ok": False, "error": "Invalid field"}

        if field in {"base_points", "coin_reward"}:
            setattr(card, field, int(value))
        elif field == "is_active":
            setattr(card, field, value.lower() in {"1", "true", "yes", "on"})
        else:
            setattr(card, field, value)

        await self.session.flush()
        return {"ok": True}

    async def stats(self) -> dict:
        users_total = await self.session.scalar(select(func.count()).select_from(User))
        cards_total = await self.session.scalar(select(func.count()).select_from(CardCatalog))
        tx_total = await self.session.scalar(select(func.count()).select_from(Transaction))
        premium_total = await self.session.scalar(
            select(func.count()).select_from(User).where(User.premium_until.is_not(None), User.premium_until > utcnow())
        )
        return {
            "users": int(users_total or 0),
            "cards": int(cards_total or 0),
            "transactions": int(tx_total or 0),
            "premium_users": int(premium_total or 0),
        }

    async def users_for_segment(self, segment: str) -> list[User]:
        q = select(User)
        now = utcnow()
        if segment == "premium":
            q = q.where(User.premium_until.is_not(None), User.premium_until > now)
        elif segment == "nonpremium":
            q = q.where(or_(User.premium_until.is_(None), User.premium_until <= now))
        elif segment == "active7d":
            q = q.where(User.last_active_at >= now - timedelta(days=7))
        rows = await self.session.scalars(q)
        return list(rows)

    async def get_user_collection(
        self, user_id: int, rarity: str | None = None, limit: int = 30
    ) -> list[dict]:
        query = (
            select(
                UserCard.card_id,
                UserCard.amount,
                CardCatalog.title,
                CardCatalog.rarity,
                CardCatalog.base_points,
            )
            .join(CardCatalog, CardCatalog.card_id == UserCard.card_id)
            .where(UserCard.user_id == user_id)
            .order_by(UserCard.amount.desc(), CardCatalog.base_points.desc())
            .limit(limit)
        )
        if rarity:
            query = query.where(CardCatalog.rarity == rarity)

        rows = await self.session.execute(query)
        return [
            {
                "card_id": card_id,
                "amount": amount,
                "title": title,
                "rarity": card_rarity,
                "base_points": base_points,
            }
            for card_id, amount, title, card_rarity, base_points in rows.all()
        ]

    async def get_marriage(self, user_id: int) -> Marriage | None:
        return await self.session.scalar(
            select(Marriage).where(or_(Marriage.user1_id == user_id, Marriage.user2_id == user_id))
        )

    async def admin_cards(
        self, rarity: str | None = None, active_only: bool = False, limit: int = 50
    ) -> list[CardCatalog]:
        query = select(CardCatalog).order_by(CardCatalog.card_id.desc()).limit(limit)
        if rarity:
            query = query.where(CardCatalog.rarity == rarity)
        if active_only:
            query = query.where(CardCatalog.is_active.is_(True))
        rows = await self.session.scalars(query)
        return list(rows)

    async def check_bonus_tasks(self, bot, user_id: int) -> tuple[bool, list[str]]:
        channels = settings.channels()
        if not channels:
            return True, []

        missing: list[str] = []
        for channel in channels:
            try:
                member = await bot.get_chat_member(channel, user_id)
                if member.status not in {"member", "administrator", "creator"}:
                    missing.append(channel)
            except Exception:
                missing.append(channel)
        return len(missing) == 0, missing
