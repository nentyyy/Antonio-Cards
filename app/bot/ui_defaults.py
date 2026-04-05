from __future__ import annotations

MAIN_MENU_ITEMS: list[tuple[str, str, str]] = [
    ("main.profile", "profile", "👤 Профиль"),
    ("main.get_card", "get_card", "🃏 Карта"),
    ("main.bonus", "bonus", "🎁 Бонусы"),
    ("main.top", "top", "🏆 Топы"),
    ("main.shop", "shop", "🛒 Магазин"),
    ("main.chest", "chest", "📦 Сундуки"),
    ("main.premium", "premium", "💎 Premium"),
    ("main.tasks", "tasks", "📜 Задания"),
    ("main.rp", "rp", "🎭 RP"),
    ("main.quote", "quote", "💬 Цитата"),
    ("main.sticker", "sticker", "🎨 Стикер"),
    ("main.games", "games", "🎮 Игры"),
    ("main.market", "market", "💱 Маркет"),
    ("main.marriage", "marriage", "💍 Брак"),
    ("main.settings", "settings", "⚙️ Настройки"),
    ("main.admin", "admin", "🛠 Админка"),
]

MAIN_MENU_ALIASES: dict[str, str] = {
    "🛠 Админ-панель": "admin",
    "🛠 Админ панель": "admin",
    "Админ-панель": "admin",
    "Админ панель": "admin",
}

DEFAULT_BUTTON_LABELS: dict[str, str] = {key: label for key, _, label in MAIN_MENU_ITEMS}
DEFAULT_BUTTON_LABELS.update(
    {
        "common.back": "🔙 Назад",
        "common.cancel": "❌ Отмена",
        "common.save": "💾 Сохранить",
        "common.skip_photo": "⏭ Пропустить фото",
        "profile.change_nick": "✏️ Сменить ник",
        "profile.inventory": "🎒 Инвентарь",
        "profile.stats": "📈 Статистика",
        "profile.economy": "💼 Экономика",
        "profile.cards": "🖼 Коллекция",
        "nick.enter": "✅ Ввести новый ник",
        "get_card.bonus": "🎁 Бонусы",
        "get_card.open_full": "🖼 Открыть карточку",
        "get_card.collection": "📂 В коллекцию",
        "get_card.repeat_later": "🔁 Позже",
        "bonus.check": "✅ Проверить",
        "top.points": "✨ По очкам",
        "top.cards": "🃏 По картам",
        "top.coins": "💰 По монетам",
        "top.rare": "💎 По редким",
        "top.level": "🎖 По уровню",
        "shop.offers": "🔥 Офферы",
        "shop.events": "🎉 Ивенты",
        "shop.boosters": "⚡ Бустеры",
        "shop.coins": "💰 Монеты",
        "shop.stars": "⭐ Stars",
        "shop.chests": "📦 Сундуки",
        "shop.limits": "🎟 Лимитки",
        "shop.premium": "💎 Premium",
        "admin.users": "👥 Пользователи",
        "admin.cards": "🃏 Карточки",
        "admin.rarities": "💎 Редкости",
        "admin.limited": "🎟 Лимитки",
        "admin.boosters": "⚡ Бустеры",
        "admin.shop": "🛒 Магазин",
        "admin.chests": "📦 Сундуки",
        "admin.tasks": "📜 Задания",
        "admin.rp": "🎭 RP",
        "admin.tops": "🏆 Топы и сезоны",
        "admin.economy": "💰 Экономика",
        "admin.broadcast": "📢 Рассылка",
        "admin.events": "🎉 Ивенты",
        "admin.permissions": "🔐 Роли и права",
        "admin.logs": "🧾 Логи",
        "admin.bot_settings": "⚙️ Система",
        "admin.media": "🖼 Медиа",
        "admin.exit": "🔙 В меню",
        "games.dice": "🎲 Кости",
        "games.slot": "🎰 Слоты",
        "games.darts": "🎯 Дартс",
        "games.football": "⚽ Футбол",
        "games.basketball": "🏀 Баскетбол",
        "market.buy": "🛒 Купить",
        "market.sell": "📤 Продать",
        "market.search": "🔎 Поиск",
        "market.my_lots": "📜 Мои лоты",
        "market.history": "🧾 История",
        "market.limited": "🎟 Лимитки",
        "market.buy_lot": "Купить лот",
        "market.cancel_lot": "Снять лот",
        "marriage.propose": "💍 Сделать предложение",
        "marriage.pair": "💕 Моя пара",
        "marriage.inbox": "📨 Входящие",
        "marriage.accept": "✅ Принять",
        "marriage.decline": "❌ Отклонить",
        "settings.notifications": "🔔 Уведомления",
        "settings.locale": "🌐 Язык",
        "settings.privacy": "🔐 Приватность",
        "settings.confirm": "🧾 Подтверждение покупок",
        "settings.card_style": "🃏 Стиль карточек",
        "settings.media": "🖼 Показывать медиа",
        "settings.safe_mode": "🛡 Безопасный режим",
        "quote.last_card": "🃏 По последней карте",
        "quote.custom": "✍️ Свой текст",
        "admin.card.back": "🔙 К карточкам",
        "sticker.last_card": "🃏 По последней карте",
        "sticker.template": "🎨 По шаблону",
    }
)

DEFAULT_MAIN_MENU_CONFIG: dict[str, dict[str, object]] = {
    key: {
        "order": index * 10,
        "visible": True,
        "admin_only": key == "main.admin",
    }
    for index, (key, _, _) in enumerate(MAIN_MENU_ITEMS, start=1)
}

DEFAULT_ADMIN_MENU_CONFIG: dict[str, dict[str, object]] = {
    "admin.users": {"order": 10, "visible": True},
    "admin.cards": {"order": 20, "visible": True},
    "admin.rarities": {"order": 30, "visible": True},
    "admin.limited": {"order": 40, "visible": True},
    "admin.boosters": {"order": 50, "visible": True},
    "admin.shop": {"order": 60, "visible": True},
    "admin.chests": {"order": 70, "visible": True},
    "admin.tasks": {"order": 80, "visible": True},
    "admin.rp": {"order": 90, "visible": True},
    "admin.tops": {"order": 100, "visible": True},
    "admin.economy": {"order": 110, "visible": True},
    "admin.broadcast": {"order": 120, "visible": True},
    "admin.events": {"order": 130, "visible": True},
    "admin.permissions": {"order": 140, "visible": True},
    "admin.logs": {"order": 150, "visible": True},
    "admin.bot_settings": {"order": 160, "visible": True},
    "admin.media": {"order": 170, "visible": True},
    "admin.exit": {"order": 180, "visible": True},
}

DEFAULT_FEATURE_FLAGS: dict[str, bool] = {
    "profile": True,
    "get_card": True,
    "bonus": True,
    "top": True,
    "shop": True,
    "chest": True,
    "premium": True,
    "tasks": True,
    "rp": True,
    "quote": True,
    "sticker": True,
    "games": True,
    "market": True,
    "marriage": True,
    "settings": True,
    "admin": True,
}

DEFAULT_INPUT_PLACEHOLDERS: dict[str, str] = {
    "main_menu": "Выберите раздел",
}

DEFAULT_TEXT_TEMPLATES: dict[str, str] = {
    "screen.welcome": (
        "Добро пожаловать в Antonio Cards.\n\n"
        "Здесь собирают карточки, качают профиль, выполняют задания, открывают сундуки, торгуют на маркете "
        "и двигаются по системе без лишних экранов и мусора.\n\n"
        "Основная навигация находится в кнопках снизу."
    ),
    "screen.help": (
        "Основные команды:\n"
        "/start — главный экран\n"
        "/profile — профиль\n"
        "/card — получить карту\n"
        "/bonus — бонусы\n"
        "/shop — магазин\n"
        "/games — игры\n"
        "/top — рейтинги\n"
        "/admin — админка"
    ),
    "screen.bonus": "Выполняйте бонусные задачи и забирайте награды после проверки.",
    "screen.shop": "Здесь доступны офферы, Premium, сундуки, бустеры и валютные пакеты.",
    "screen.chest": "Откройте сундук, чтобы посмотреть цену, ограничения и состав дропа.",
    "screen.premium": (
        "Premium ускоряет игру: снижает cooldown, усиливает дроп и открывает расширенные возможности."
    ),
    "screen.tasks": "Следите за прогрессом задач и забирайте награды без лишних шагов.",
    "screen.events": "Здесь собраны активные события, акции и специальные режимы.",
    "screen.rp": "Выберите RP-категорию. Если действию нужна цель, используйте reply или укажите пользователя после выбора.",
    "screen.quote": "Соберите цитату по последней карточке или отправьте свой текст.",
    "screen.sticker": "Создайте стикер по последней карточке или шаблонному тексту.",
    "screen.games": "Выберите игру Telegram и поставьте монеты на реальный результат emoji-броска.",
    "screen.market": "Покупайте карточки игроков, выставляйте свои лоты и смотрите историю сделок.",
    "screen.marriage": "Здесь можно сделать предложение, открыть свою пару и проверить входящие заявки.",
    "screen.settings": "Управляйте уведомлениями, языком, приватностью и визуальными режимами.",
    "screen.profile": "Профиль, коллекция, прогресс, активные бустеры и экономика в одном месте.",
    "premium.payment_success": "Оплата прошла. Premium и другие бонусы уже зачислены.",
    "premium.payment_duplicate": "Этот платёж уже был обработан. Повторное начисление не выполнено.",
    "premium.payment_error": "Платёж не удалось обработать. Попробуйте позже или обратитесь в поддержку.",
}
