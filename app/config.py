from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = Field(alias="BOT_TOKEN")
    admin_bot_token: str = Field(default="", alias="ADMIN_BOT_TOKEN")
    database_url: str = Field(alias="DATABASE_URL")

    admin_ids: str = Field(default="", alias="ADMIN_IDS")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    brawl_cooldown_seconds: int = Field(default=4 * 3600, alias="BRAWL_COOLDOWN_SECONDS")
    bonus_cooldown_seconds: int = Field(default=12 * 3600, alias="BONUS_COOLDOWN_SECONDS")
    dice_cooldown_seconds: int = Field(default=3600, alias="DICE_COOLDOWN_SECONDS")

    bonus_reward_coins: int = Field(default=150, alias="BONUS_REWARD_COINS")
    bonus_reward_stars: int = Field(default=1, alias="BONUS_REWARD_STARS")

    channel_tasks: str = Field(default="", alias="CHANNEL_TASKS")
    bonus_chat_url: str = Field(default="", alias="BONUS_CHAT_URL")
    bonus_subscribe_url: str = Field(default="", alias="BONUS_SUBSCRIBE_URL")
    bonus_news_url: str = Field(default="", alias="BONUS_NEWS_URL")
    bonus_invite_url: str = Field(default="", alias="BONUS_INVITE_URL")
    bonus_partner_url: str = Field(default="", alias="BONUS_PARTNER_URL")

    def admin_id_set(self) -> set[int]:
        ids: list[int] = []
        for raw in self.admin_ids.split(","):
            raw = raw.strip()
            if not raw:
                continue
            try:
                value = int(raw)
                if value not in ids:
                    ids.append(value)
            except ValueError:
                continue
        return set(ids)

    def channels(self) -> list[str]:
        return [x.strip() for x in self.channel_tasks.split(",") if x.strip()]

    def bonus_urls(self) -> dict[str, str]:
        return {
            "chat": self.bonus_chat_url.strip(),
            "subscribe": self.bonus_subscribe_url.strip(),
            "news": self.bonus_news_url.strip(),
            "invite": self.bonus_invite_url.strip(),
            "partner": self.bonus_partner_url.strip(),
        }


@lru_cache(1)
def get_settings() -> Settings:
    return Settings()


DEFAULT_DROP_RATES: dict[str, float] = {
    "common": 70.0,
    "rare": 20.0,
    "mythic": 8.0,
    "legendary": 2.0,
    "limited": 0.0,
}


DEFAULT_SHOP_PRICES: dict[str, Any] = {
    "luck_booster_coins": 250,
    "timewarp_booster_coins": 300,
    "premium_30d_stars": 50,
    "coins_pack_small_stars": 5,
    "coins_pack_small_amount": 500,
    "coins_pack_big_stars": 20,
    "coins_pack_big_amount": 2500,
    "chest_common_coins": 350,
    "chest_rare_coins": 900,
    "chest_mythic_coins": 2200,
    "chest_legendary_coins": 6000,
    "market_fee_percent": 5,
}
