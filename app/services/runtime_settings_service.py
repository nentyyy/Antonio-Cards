from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.ui_defaults import DEFAULT_BUTTON_LABELS, DEFAULT_INPUT_PLACEHOLDERS
from app.config import get_settings
from app.db.models import BcBonusTask, Setting
from app.infra.runtime import get_runtime

settings = get_settings()
runtime = get_runtime()

SYSTEM_SETTINGS_DEFAULTS: dict[str, dict[str, object]] = {
    "cooldowns": {
        "brawl_cards": int(settings.brawl_cooldown_seconds),
        "bonus": int(settings.bonus_cooldown_seconds),
        "nick_change": 24 * 3600,
        "dice": int(settings.dice_cooldown_seconds),
        "darts": 60,
        "football": 60,
        "basketball": 60,
        "guess_rarity": 60,
        "coinflip": 60,
        "card_battle": 60,
        "slot": 60,
        "premium_game_reduction": 20,
    },
    "rewards": {
        "bonus_coins": int(settings.bonus_reward_coins),
        "bonus_stars": int(settings.bonus_reward_stars),
        "market_fee_percent": 5,
    },
    "bonus_links": dict(settings.bonus_urls()),
    "button_labels": dict(DEFAULT_BUTTON_LABELS),
    "input_placeholders": dict(DEFAULT_INPUT_PLACEHOLDERS),
}


class RuntimeSettingsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_section(self, section: str) -> dict[str, object]:
        cache_key = f"system:{section}"
        cached = runtime.content_cache.get(cache_key)
        if isinstance(cached, dict):
            runtime.settings_snapshot[section] = dict(cached)
            return dict(cached)

        defaults = dict(SYSTEM_SETTINGS_DEFAULTS.get(section, {}))
        row = await self.session.get(Setting, f"bc:{section}")
        if row is None or not isinstance(row.value_json, dict):
            runtime.content_cache.set(cache_key, dict(defaults), 30.0)
            runtime.settings_snapshot[section] = dict(defaults)
            return defaults

        data = dict(defaults)
        data.update(row.value_json)
        runtime.content_cache.set(cache_key, dict(data), 30.0)
        runtime.settings_snapshot[section] = dict(data)
        return data

    async def set_section(self, section: str, payload: dict[str, object]) -> dict[str, object]:
        defaults = dict(SYSTEM_SETTINGS_DEFAULTS.get(section, {}))
        data = dict(defaults)
        data.update(payload)

        row = await self.session.get(Setting, f"bc:{section}")
        if row is None:
            row = Setting(key=f"bc:{section}", value_json=data)
            self.session.add(row)
        else:
            row.value_json = data

        await self.session.flush()
        runtime.content_cache.delete(f"system:{section}")
        runtime.settings_snapshot[section] = dict(data)
        return data

    async def set_value(self, section: str, key: str, value: object) -> dict[str, object]:
        data = await self.get_section(section)
        data[key] = value
        return await self.set_section(section, data)

    async def resolve_bonus_url(self, task: BcBonusTask) -> str:
        config = dict(task.config or {})
        url = str(config.get("url") or "").strip()
        if url:
            return url
        links = await self.get_section("bonus_links")
        return str(links.get(task.key) or "").strip()
