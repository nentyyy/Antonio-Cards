from __future__ import annotations

MAIN_MENU_ITEMS: list[tuple[str, str, str]] = [
    ("main.profile", "profile", "👤 Профиль"),
    ("main.get_card", "get_card", "🃏 Получить карту"),
    ("main.bonus", "bonus", "🎁 Бонус"),
    ("main.top", "top", "🏆 Топ"),
    ("main.shop", "shop", "🛒 Магазин"),
    ("main.chest", "chest", "📦 Сундук"),
    ("main.premium", "premium", "💎 Премиум"),
    ("main.tasks", "tasks", "📜 Задания"),
    ("main.rp", "rp", "🎭 RP"),
    ("main.quote", "quote", "💬 Цитата"),
    ("main.sticker", "sticker", "🎨 Стикер"),
    ("main.games", "games", "🎲 Игры"),
    ("main.market", "market", "💱 Маркет"),
    ("main.marriage", "marriage", "💍 Брак"),
    ("main.settings", "settings", "⚙️ Настройки"),
    ("main.admin", "admin", "🛠 Админ-панель"),
]

MAIN_MENU_ALIASES: dict[str, str] = {
    "🛠 Админ-панель": "admin",
    "🛠 Админ панель": "admin",
    "Админ-панель": "admin",
    "Админ панель": "admin",
}

DEFAULT_BUTTON_LABELS: dict[str, str] = {
    key: label for key, _, label in MAIN_MENU_ITEMS
}
DEFAULT_BUTTON_LABELS.update(
    {
        "common.back": "🔙 Назад",
        "common.cancel": "❌ Отменить",
        "common.save": "💾 Сохранить",
        "common.skip_photo": "⏭ Пропустить фото",
        "profile.change_nick": "✏️ Сменить ник",
        "profile.inventory": "🎒 Инвентарь",
        "profile.stats": "📈 Статистика",
        "profile.economy": "💼 Экономика",
        "profile.cards": "🖼 Мои карточки",
        "nick.enter": "✅ Ввести новый ник",
        "get_card.bonus": "🎁 Получить бонус",
        "get_card.open_full": "🖼 Открыть карточку полностью",
        "get_card.collection": "📂 В коллекцию",
        "get_card.repeat_later": "🔁 Повторить позже",
        "bonus.check": "✅ Проверить",
        "top.points": "✨ По очкам",
        "top.cards": "🃏 По картам",
        "top.coins": "💰 По монетам",
        "top.rare": "💎 По редким",
        "top.level": "🏅 По уровню",
        "shop.offers": "🔥 Офферы",
        "shop.events": "🎉 Ивенты",
        "shop.boosters": "⚡ Бустеры",
        "shop.coins": "💰 Монеты",
        "shop.stars": "🌟 Звезды",
        "shop.chests": "📦 Сундуки",
        "shop.limits": "🎟 Лимитки",
        "shop.premium": "💎 Premium",
        "admin.users": "👥 Пользователи",
        "admin.cards": "🃏 Карточки",
        "admin.rarities": "💎 Редкости",
        "admin.limited": "🎟 Лимитированные",
        "admin.boosters": "⚡ Бустеры",
        "admin.shop": "🛒 Магазин",
        "admin.chests": "📦 Сундуки",
        "admin.tasks": "📜 Задания",
        "admin.rp": "🎭 RP-действия",
        "admin.tops": "🏆 Топы и сезоны",
        "admin.economy": "💰 Экономика",
        "admin.broadcast": "📢 Рассылка",
        "admin.events": "🎉 Ивенты",
        "admin.permissions": "🔐 Права",
        "admin.logs": "🧾 Логи",
        "admin.bot_settings": "⚙️ Настройки бота",
        "admin.media": "🖼 Медиа",
        "admin.exit": "🔙 Выход",
        "games.dice": "🎲 Кости",
        "games.slot": "🎰 Слоты",
        "games.darts": "🎯 Дартс",
        "games.football": "⚽ Футбол",
        "games.basketball": "🏀 Баскетбол",
        "market.buy": "🛒 Купить карточку",
        "market.sell": "📤 Выставить карточку",
        "market.search": "🔍 Поиск",
        "market.my_lots": "📜 Мои лоты",
        "market.history": "⏱ История",
        "market.limited": "⭐ Лимитированные",
        "market.buy_lot": "Купить",
        "market.cancel_lot": "Снять лот",
        "marriage.propose": "💍 Сделать предложение",
        "marriage.pair": "💞 Моя пара",
        "marriage.inbox": "📨 Входящие предложения",
        "marriage.accept": "✅ Принять",
        "marriage.decline": "❌ Отклонить",
        "settings.notifications": "🔔 Уведомления",
        "settings.locale": "🌐 Язык",
        "settings.privacy": "🔐 Приватность",
        "settings.confirm": "🧾 Подтверждение покупок",
        "settings.card_style": "🃏 Стиль выдачи карт",
        "settings.media": "🖼 Отображение медиа",
        "settings.safe_mode": "🛡 Безопасный режим",
        "quote.last_card": "🃏 По последней карте",
        "quote.custom": "✌️ По своему тексту",
        "admin.card.back": "🔙 К карточкам",
        "sticker.last_card": "🃏 Стикер по карте",
        "sticker.template": "🎨 Стикер по шаблону",
    }
)

DEFAULT_INPUT_PLACEHOLDERS: dict[str, str] = {
    "main_menu": "Выберите раздел",
}

DEFAULT_TEXT_TEMPLATES: dict[str, str] = {
    "screen.welcome": (
        "Добро пожаловать в Antonio Cards.\n\n"
        "Собирайте карточки, усиливайте профиль, выполняйте задания, открывайте сундуки, "
        "торгуйте на маркете и используйте RP-механики без лишних переходов.\n\n"
        "Основной путь построен на кнопках внизу. Откройте нужный раздел и двигайтесь дальше."
    ),
    "screen.help": (
        "Основные разделы доступны через меню и быстрые команды.\n\n"
        "Команды:\n"
        "/start — главный экран\n"
        "/profile — профиль\n"
        "/card — получить карту\n"
        "/bonus — бонусы\n"
        "/shop — магазин\n"
        "/games — мини-игры\n"
        "/top — рейтинги\n"
        "/admin — админ-панель"
    ),
    "screen.rp": "Выберите категорию. Если действию нужна цель, ответьте на сообщение пользователя и нажмите кнопку действия.",
    "screen.quote": "Здесь можно сделать цитату по последней карте или отправить свой текст.",
    "screen.sticker": "Здесь можно сделать стикер по последней карте или по шаблону с вашим текстом.",
    "screen.games": "Здесь выбирается мини-игра. У каждой игры свои ставки, награды и кулдаун.",
    "screen.market": "Здесь можно покупать карточки, выставлять свои лоты и смотреть историю торговли.",
    "screen.marriage": "Здесь можно сделать предложение, проверить входящие и открыть экран вашей пары.",
    "screen.settings": "Управляйте уведомлениями, языком, приватностью, стилем выдачи карт и безопасным режимом.",
}
