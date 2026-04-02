from __future__ import annotations

from sqlalchemy import select

from app.bot.ui_defaults import DEFAULT_TEXT_TEMPLATES
from app.config import DEFAULT_DROP_RATES, DEFAULT_SHOP_PRICES, get_settings
from app.db.models import (
    BcBonusTask,
    BcBooster,
    BcCard,
    BcChest,
    BcChestDrop,
    BcPermission,
    BcRarity,
    BcRole,
    BcRolePermission,
    BcRPCategory,
    BcRPAction,
    BcShopCategory,
    BcShopItem,
    BcTask,
    BcTextTemplate,
    CardCatalog,
    Setting,
)
from app.db.session import SessionLocal, init_db

settings = get_settings()


def _default_cooldowns() -> dict[str, int]:
    return {
        "brawl": settings.brawl_cooldown_seconds,
        "bonus": settings.bonus_cooldown_seconds,
        "diceplay": settings.dice_cooldown_seconds,
    }


def _default_rewards() -> dict[str, int]:
    return {
        "bonus_coins": settings.bonus_reward_coins,
        "bonus_stars": settings.bonus_reward_stars,
    }


async def seed_defaults() -> None:
    await init_db()
    async with SessionLocal() as session:
        async with session.begin():
            for key, value in {
                "drop_rates": DEFAULT_DROP_RATES,
                "shop_prices": DEFAULT_SHOP_PRICES,
                "cooldowns": _default_cooldowns(),
                "rewards": _default_rewards(),
            }.items():
                row = await session.get(Setting, key)
                if row is None:
                    session.add(Setting(key=key, value_json=value))

            cards_count = await session.scalar(select(CardCatalog).limit(1))
            if cards_count is None:
                seed_cards = [
                    ("Rusty Sword", "Starter common blade", "common", 3, 10),
                    ("Forest Guard", "Steady common defender", "common", 4, 12),
                    ("Arcane Archer", "Rare precise damage", "rare", 8, 20),
                    ("Storm Tamer", "Rare control mage", "rare", 9, 22),
                    ("Phoenix Child", "Mythic rebirth power", "mythic", 15, 35),
                    ("Astral Monk", "Mythic balance master", "mythic", 16, 38),
                    ("Dragon Emperor", "Legendary devastation", "legendary", 24, 55),
                    ("Titan of Dawn", "Legendary guardian", "legendary", 22, 52),
                    ("Festival Relic", "Limited event card", "limited", 30, 70),
                    ("Neon Valkyrie", "Limited season card", "limited", 31, 72),
                ]
                for title, desc, rarity, points, coins in seed_cards:
                    session.add(
                        CardCatalog(
                            title=title,
                            description=desc,
                            rarity=rarity,
                            base_points=points,
                            coin_reward=coins,
                            is_active=True,
                        )
                    )

            # ---- Brawl CARDS seed (new tables) ----
            existing_rarity = await session.scalar(select(BcRarity).limit(1))
            if existing_rarity is None:
                rarities = [
                    ("common", "Обычная", "⚪", 70.0, "#A0A0A0", 1.0, 1.0, True, False, "normal", 10),
                    ("rare", "Редкая", "🟦", 20.0, "#4DA3FF", 1.4, 1.2, True, False, "normal", 20),
                    ("epic", "Эпическая", "🟪", 7.0, "#B06CFF", 1.8, 1.4, True, True, "normal", 30),
                    ("mythic", "Мифическая", "🟥", 2.0, "#FF5A5A", 2.4, 1.7, True, True, "normal", 40),
                    ("legendary", "Легендарная", "🟨", 0.8, "#FFD24D", 3.2, 2.1, True, True, "normal", 50),
                    ("exclusive", "Эксклюзивная", "💠", 0.15, "#5DFFE0", 4.0, 2.7, False, True, "manual", 60),
                    ("event", "Ивентовая", "🎉", 0.05, "#FF7AD9", 4.5, 3.0, True, False, "event", 70),
                    ("limited", "Лимитированная", "🎟", 0.0, "#FFFFFF", 5.0, 3.5, True, True, "event", 80),
                ]
                for key, title, emoji, chance, color, pm, cm, in_chests, in_shop, mode, sort in rarities:
                    session.add(
                        BcRarity(
                            key=key,
                            title=title,
                            emoji=emoji,
                            chance=chance,
                            color=color,
                            points_mult=pm,
                            coins_mult=cm,
                            available_in_chests=in_chests,
                            available_in_shop=in_shop,
                            drop_mode=mode,
                            sort=sort,
                            is_active=True,
                        )
                    )

            existing_booster = await session.scalar(select(BcBooster).limit(1))
            if existing_booster is None:
                boosters = [
                    ("luck", "🍀 Удача", "🍀", "luck", 0.35, 250, None, 0),
                    ("time_accel", "⏳ Ускоритель времени", "⏳", "time", 0.25, 300, None, 0),
                    ("coin_mult", "💰 Монетный множитель", "💰", "coins_mult", 0.30, 500, None, 6 * 3600),
                    ("points_mult", "✨ Множитель очков", "✨", "points_mult", 0.30, 500, None, 6 * 3600),
                    ("limited_chance", "🎟 Шанс лимитки", "🎟", "limited", 0.10, 900, None, 6 * 3600),
                ]
                for key, title, emoji, etype, power, pcoins, pstars, dur in boosters:
                    session.add(
                        BcBooster(
                            key=key,
                            title=title,
                            emoji=emoji,
                            effect_type=etype,
                            effect_power=float(power),
                            price_coins=pcoins,
                            price_stars=pstars,
                            duration_seconds=int(dur),
                            stackable=True,
                            max_stack=10,
                            purchase_limit=None,
                            is_available=True,
                        )
                    )

            existing_shop_category = await session.scalar(select(BcShopCategory).limit(1))
            if existing_shop_category is None:
                categories = [
                    ("boosters", "⚡ Бустеры", "⚡", 10),
                    ("coins", "💰 Монеты", "💰", 20),
                    ("stars", "🌟 Звёзды", "🌟", 30),
                    ("chests", "📦 Сундуки", "📦", 40),
                    ("limits", "🎟 Лимитки", "🎟", 50),
                    ("premium", "💎 Премиум", "💎", 60),
                ]
                for key, title, emoji, sort in categories:
                    session.add(BcShopCategory(key=key, title=title, emoji=emoji, sort=sort, is_active=True))

            existing_shop_item = await session.scalar(select(BcShopItem).limit(1))
            if existing_shop_item is None:
                items = [
                    (
                        "boosters",
                        "buy_booster_luck",
                        "🍀 Удача",
                        "Одноразово повышает шанс редких карт при получении.",
                        250,
                        None,
                        None,
                        {"type": "booster", "booster_key": "luck", "amount": 1},
                        10,
                    ),
                    (
                        "boosters",
                        "buy_booster_time",
                        "⏳ Ускоритель времени",
                        "Одноразово сокращает кулдаун получения карты.",
                        300,
                        None,
                        None,
                        {"type": "booster", "booster_key": "time_accel", "amount": 1},
                        20,
                    ),
                    (
                        "boosters",
                        "buy_booster_coinmult",
                        "💰 Монетный множитель",
                        "На 6 часов повышает награду монет за карты.",
                        500,
                        None,
                        6 * 3600,
                        {"type": "activate_booster", "booster_key": "coin_mult", "stacks": 1},
                        30,
                    ),
                    (
                        "boosters",
                        "buy_booster_pointsmult",
                        "✨ Множитель очков",
                        "На 6 часов повышает награду очков за карты.",
                        500,
                        None,
                        6 * 3600,
                        {"type": "activate_booster", "booster_key": "points_mult", "stacks": 1},
                        40,
                    ),
                    (
                        "boosters",
                        "buy_booster_limited",
                        "🎟 Шанс лимитки",
                        "На 6 часов добавляет шанс лимитированной карты (если доступно).",
                        900,
                        None,
                        6 * 3600,
                        {"type": "activate_booster", "booster_key": "limited_chance", "stacks": 1},
                        50,
                    ),
                    (
                        "premium",
                        "premium_30d",
                        "💎 Премиум на 30 дней",
                        "Кулдауны ниже, шансы редких выше, эмодзи в нике и другие бонусы.",
                        None,
                        50,
                        30 * 24 * 3600,
                        {"type": "premium", "days": 30},
                        10,
                    ),
                    (
                        "coins",
                        "coins_pack_small",
                        "💰 Пак монет (малый)",
                        "Обмен: 5⭐ → 500🪙.",
                        None,
                        5,
                        None,
                        {"type": "currency_exchange", "from": "stars", "to": "coins", "amount": 500},
                        10,
                    ),
                    (
                        "coins",
                        "coins_pack_big",
                        "💰 Пак монет (большой)",
                        "Обмен: 20⭐ → 2500🪙.",
                        None,
                        20,
                        None,
                        {"type": "currency_exchange", "from": "stars", "to": "coins", "amount": 2500},
                        20,
                    ),
                ]
                for cat, key, title, desc, pcoins, pstars, dur, payload, sort in items:
                    session.add(
                        BcShopItem(
                            category_key=cat,
                            key=key,
                            title=title,
                            description=desc,
                            price_coins=pcoins,
                            price_stars=pstars,
                            duration_seconds=dur,
                            payload=payload,
                            is_active=True,
                            sort=sort,
                        )
                    )

            existing_chest = await session.scalar(select(BcChest).limit(1))
            if existing_chest is None:
                chests = [
                    ("common", "Обычный", "📦", "Стартовый сундук: чаще обычные.", 350, None, 1, 10),
                    ("rare", "Редкий", "📦", "Чаще редкие и эпические.", 900, None, 1, 20),
                    ("epic", "Эпический", "📦", "Шанс мифических заметно выше.", 1600, None, 1, 30),
                    ("mythic", "Мифический", "📦", "Высокий шанс легендарных.", 2200, None, 1, 40),
                    ("legendary", "Легендарный", "📦", "Премиальный дроп и гарантии.", 6000, None, 1, 50),
                    ("event", "Ивентовый", "🎉", "Дроп по ивент-таблице (если активен).", 2500, None, 1, 60),
                    ("limited", "🎟 Лимитированный", "🎟", "Сундук лимиток (в периоды релиза).", 8000, None, 1, 70),
                ]
                for key, title, emoji, desc, pcoins, pstars, open_count, sort in chests:
                    session.add(
                        BcChest(
                            key=key,
                            title=title,
                            emoji=emoji,
                            description=desc,
                            price_coins=pcoins,
                            price_stars=pstars,
                            open_count=open_count,
                            guarantees={},
                            limits={},
                            access={},
                            is_active=True,
                            sort=sort,
                        )
                    )

            existing_chest_drop = await session.scalar(select(BcChestDrop).limit(1))
            if existing_chest_drop is None:
                drops = [
                    ("common", "common", 80.0),
                    ("common", "rare", 18.0),
                    ("common", "epic", 2.0),
                    ("rare", "rare", 70.0),
                    ("rare", "epic", 25.0),
                    ("rare", "mythic", 5.0),
                    ("epic", "epic", 65.0),
                    ("epic", "mythic", 30.0),
                    ("epic", "legendary", 5.0),
                    ("mythic", "mythic", 70.0),
                    ("mythic", "legendary", 25.0),
                    ("mythic", "exclusive", 5.0),
                    ("legendary", "legendary", 80.0),
                    ("legendary", "exclusive", 20.0),
                    ("event", "event", 100.0),
                    ("limited", "limited", 100.0),
                ]
                for chest_key, rarity_key, weight in drops:
                    session.add(
                        BcChestDrop(
                            chest_key=chest_key,
                            rarity_key=rarity_key,
                            weight=float(weight),
                            min_count=1,
                            max_count=1,
                            meta={},
                        )
                    )

            existing_bonus_task = await session.scalar(select(BcBonusTask).limit(1))
            if existing_bonus_task is None:
                bonus_tasks = [
                    ("chat", "📺 Чат", "📺", "Зайди в наш чат и напиши любое сообщение.", "chat", {"url": ""}, 10),
                    (
                        "subscribe",
                        "📢 Подписаться",
                        "📢",
                        "Подпишись на канал проекта и вернись для проверки.",
                        "subscribe",
                        {"chat_id": None, "url": ""},
                        20,
                    ),
                    ("news", "⭐ Новости", "⭐", "Открой новости и отметь прочтение.", "link", {"url": ""}, 30),
                    ("invite", "👥 Пригласить друга", "👥", "Пригласи друга по реф-ссылке.", "invite", {}, 40),
                    ("partner", "🔗 Партнёр", "🔗", "Партнёрское действие (настраивается админом).", "custom", {}, 50),
                ]
                for key, title, emoji, desc, typ, cfg, sort in bonus_tasks:
                    session.add(
                        BcBonusTask(
                            key=key,
                            title=title,
                            emoji=emoji,
                            description=desc,
                            type=typ,
                            config=cfg,
                            sort=sort,
                            is_active=True,
                        )
                    )

            existing_task = await session.scalar(select(BcTask).limit(1))
            if existing_task is None:
                tasks = [
                    (
                        "daily_get_cards",
                        "daily",
                        "🃏 Ежедневно: получи 3 карты",
                        "Получай карты и прокачивай аккаунт.",
                        3,
                        {"coins": 200, "points": 10},
                        {"counter": "get_cards"},
                        10,
                    ),
                    (
                        "daily_play_dice",
                        "daily",
                        "🎲 Ежедневно: сыграй в кости",
                        "Сыграй один раз в мини-игру «Кости».",
                        1,
                        {"coins": 150, "stars": 1},
                        {"counter": "play_dice"},
                        20,
                    ),
                    (
                        "weekly_open_chest",
                        "weekly",
                        "📦 Еженедельно: открой сундук",
                        "Открой любой сундук в магазине.",
                        1,
                        {"coins": 500, "stars": 2},
                        {"counter": "open_chest"},
                        30,
                    ),
                ]
                for key, kind, title, desc, target, reward, cfg, sort in tasks:
                    session.add(
                        BcTask(
                            key=key,
                            kind=kind,
                            title=title,
                            description=desc,
                            target=target,
                            reward=reward,
                            expires_at=None,
                            check_type="counter",
                            config=cfg,
                            is_active=True,
                            sort=sort,
                        )
                    )

            for key, text in DEFAULT_TEXT_TEMPLATES.items():
                if await session.get(BcTextTemplate, {"key": key, "locale": "ru"}) is None:
                    session.add(BcTextTemplate(key=key, locale="ru", text=text))

            existing_rp_cat = await session.scalar(select(BcRPCategory).limit(1))
            if existing_rp_cat is None:
                cats = [
                    ("friendly", "Дружелюбные", "🤝", 10),
                    ("romantic", "Романтические", "💞", 20),
                    ("conflict", "Конфликтные", "😡", 30),
                    ("meme", "Мемные", "😂", 40),
                    ("social", "Социальные", "🗣", 50),
                    ("holiday", "Праздничные", "🎉", 60),
                    ("custom", "Кастомные", "🧩", 70),
                ]
                for key, title, emoji, sort in cats:
                    session.add(BcRPCategory(key=key, title=title, emoji=emoji, sort=sort, is_active=True))

            existing_rp_action = await session.scalar(select(BcRPAction).limit(1))
            if existing_rp_action is None:
                actions = [
                    ("hug", "friendly", "🤝 Обнять", "🤝", True, 30, ["{actor} обнял(а) {target}."]),
                    ("kiss", "romantic", "😘 Поцеловать", "😘", True, 45, ["{actor} поцеловал(а) {target}."]),
                    ("hit", "conflict", "😡 Ударить", "😡", True, 60, ["{actor} ударил(а) {target}."]),
                    ("laugh", "meme", "😂 Засмеяться", "😂", True, 20, ["{actor} засмеялся(лась) вместе с {target}."]),
                    ("gift", "social", "🎁 Подарить", "🎁", True, 40, ["{actor} подарил(а) подарок {target}."]),
                    ("flirt", "romantic", "🔥 Флирт", "🔥", True, 50, ["{actor} флиртует с {target}."]),
                    ("sleep", "meme", "💤 Усыпить", "💤", True, 90, ["{actor} усыпил(а) {target}."]),
                    ("praise", "friendly", "👑 Похвалить", "👑", True, 40, ["{actor} похвалил(а) {target}."]),
                    ("treat", "friendly", "🍰 Угостить", "🍰", True, 35, ["{actor} угостил(а) {target}."]),
                    ("protect", "social", "🛡 Защитить", "🛡", True, 60, ["{actor} защитил(а) {target}."]),
                    ("break", "conflict", "💔 Бросить", "💔", True, 120, ["{actor} бросил(а) {target}..."]),
                    ("propose", "romantic", "💍 Предложение", "💍", True, 120, ["{actor} делает предложение {target}."]),
                    ("congrats", "holiday", "🎉 Поздравить", "🎉", True, 30, ["{actor} поздравил(а) {target}!"]),
                ]
                for key, cat, title, emoji, req, cd, templates in actions:
                    session.add(
                        BcRPAction(
                            key=key,
                            category_key=cat,
                            title=title,
                            emoji=emoji,
                            requires_target=req,
                            cooldown_seconds=cd,
                            reward={},
                            templates=templates,
                            media_id=None,
                            restrictions={},
                            allowed_scopes={"private": True, "group": True},
                            is_active=True,
                            sort=100,
                        )
                    )

            existing_perm = await session.scalar(select(BcPermission).limit(1))
            if existing_perm is None:
                perms = [
                    ("admin.panel", "Доступ к админ-панели"),
                    ("users.view", "Просмотр пользователей"),
                    ("users.edit", "Редактирование пользователей"),
                    ("catalog.edit", "Управление карточками"),
                    ("rarities.edit", "Управление редкостями"),
                    ("boosters.edit", "Управление бустерами"),
                    ("shop.edit", "Управление магазином"),
                    ("chests.edit", "Управление сундуками"),
                    ("tasks.edit", "Управление заданиями"),
                    ("rp.edit", "Управление RP"),
                    ("events.edit", "Управление ивентами"),
                    ("broadcast", "Рассылка"),
                    ("economy.edit", "Экономика"),
                    ("logs.view", "Просмотр логов"),
                    ("media.edit", "Медиа"),
                ]
                for code, title in perms:
                    session.add(BcPermission(code=code, title=title))

            existing_role = await session.scalar(select(BcRole).limit(1))
            if existing_role is None:
                roles = [
                    ("owner", "Владелец"),
                    ("head_admin", "Главный админ"),
                    ("admin", "Админ"),
                    ("moderator", "Модератор"),
                    ("content_manager", "Контент-менеджер"),
                    ("event_manager", "Ивент-менеджер"),
                ]
                for key, title in roles:
                    session.add(BcRole(key=key, title=title, meta={}))

            existing_rp = await session.scalar(select(BcRolePermission).limit(1))
            if existing_rp is None:
                all_perm_codes = [
                    "admin.panel",
                    "users.view",
                    "users.edit",
                    "catalog.edit",
                    "rarities.edit",
                    "boosters.edit",
                    "shop.edit",
                    "chests.edit",
                    "tasks.edit",
                    "rp.edit",
                    "events.edit",
                    "broadcast",
                    "economy.edit",
                    "logs.view",
                    "media.edit",
                ]
                owner_roles = {"owner", "head_admin"}
                admin_role = {"admin"}
                moderator_role = {"moderator"}
                for role_key in owner_roles:
                    for code in all_perm_codes:
                        session.add(BcRolePermission(role_key=role_key, permission_code=code))
                for role_key in admin_role:
                    for code in [c for c in all_perm_codes if c not in {"economy.edit"}]:
                        session.add(BcRolePermission(role_key=role_key, permission_code=code))
                for role_key in moderator_role:
                    for code in ["admin.panel", "users.view", "logs.view", "broadcast"]:
                        session.add(BcRolePermission(role_key=role_key, permission_code=code))

            existing_bc_card = await session.scalar(select(BcCard).limit(1))
            if existing_bc_card is None:
                seed_bc_cards = [
                    ("core_rustblade", "Rustblade", "Старый, но верный клинок новичка.", "common", "Core", 3, 10),
                    ("core_dustguard", "Dust Guard", "Щитник, который держит линию до конца.", "common", "Core", 4, 12),
                    ("core_neon_scout", "Neon Scout", "Быстрый разведчик с неоновым следом.", "rare", "Core", 8, 20),
                    ("core_arc_witch", "Arc Witch", "Контроль электричества и нервов.", "rare", "Core", 9, 22),
                    ("core_ember_singer", "Ember Singer", "Песни пепла превращают страх в силу.", "epic", "Core", 12, 28),
                    ("core_void_juggler", "Void Juggler", "Ловкость на грани реальности.", "epic", "Core", 13, 30),
                    ("core_phoenix_kid", "Phoenix Kid", "Возрождается, если верить в удачу.", "mythic", "Core", 16, 38),
                    ("core_astral_monk", "Astral Monk", "Баланс, дисциплина и звёздная пыль.", "mythic", "Core", 17, 40),
                    ("core_dragon_emperor", "Dragon Emperor", "Легенда, которая не просит разрешения.", "legendary", "Core", 24, 55),
                    ("core_titan_dawn", "Titan of Dawn", "Страж рассвета и последней надежды.", "legendary", "Core", 22, 52),
                    ("excl_glitch_prince", "Glitch Prince", "Эксклюзив: ошибки мира служат ему.", "exclusive", "Exclusive", 30, 70),
                    ("excl_ice_oracle", "Ice Oracle", "Эксклюзив: видит исход ещё до начала.", "exclusive", "Exclusive", 29, 68),
                    ("event_firework_relic", "Firework Relic", "Ивент: реликт, пахнущий праздником.", "event", "Event", 28, 66),
                    ("event_snow_brawler", "Snow Brawler", "Ивент: бой без правил, но в шарфе.", "event", "Event", 27, 64),
                    ("limited_neon_valk", "Neon Valkyrie", "Лимитка: сезонный символ города.", "limited", "Limited", 31, 72),
                    ("limited_festival_mask", "Festival Mask", "Лимитка: маска, что меняет роль.", "limited", "Limited", 30, 70),
                ]
                for key, title, desc, rarity_key, series, points, coins in seed_bc_cards:
                    session.add(
                        BcCard(
                            key=key,
                            title=title,
                            description=desc,
                            rarity_key=rarity_key,
                            series=series,
                            tags=[],
                            base_points=points,
                            base_coins=coins,
                            drop_weight=1.0,
                            is_limited=rarity_key == "limited",
                            limited_series_id=None,
                            event_id=None,
                            image_file_id=None,
                            image_url=None,
                            media_id=None,
                            is_sellable=True,
                            is_active=True,
                            sort=100,
                            meta={},
                        )
                    )
