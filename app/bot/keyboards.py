from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup


BTN_PROFILE = "👤 Профиль"
BTN_GET_CARD = "🃏 Получить карту"
BTN_BONUS = "🎁 Бонус"
BTN_TOP = "🏆 Топ"
BTN_SHOP = "🛒 Магазин"
BTN_CHEST = "📦 Сундук"
BTN_PREMIUM = "💎 Премиум"
BTN_TASKS = "📜 Задания"
BTN_RP = "🎭 RP"
BTN_QUOTE = "💬 Цитата"
BTN_STICKER = "🎨 Стикер"
BTN_GAMES = "🎲 Игры"
BTN_MARKET = "💱 Маркет"
BTN_MARRIAGE = "💍 Брак"
BTN_SETTINGS = "⚙️ Настройки"
BTN_ADMIN = "🛠 Админ-панель"

MAIN_MENU_BUTTONS: list[str] = [
    BTN_PROFILE,
    BTN_GET_CARD,
    BTN_BONUS,
    BTN_TOP,
    BTN_SHOP,
    BTN_CHEST,
    BTN_PREMIUM,
    BTN_TASKS,
    BTN_RP,
    BTN_QUOTE,
    BTN_STICKER,
    BTN_GAMES,
    BTN_MARKET,
    BTN_MARRIAGE,
    BTN_SETTINGS,
    BTN_ADMIN,
]


def main_menu(*, is_admin: bool = False) -> ReplyKeyboardMarkup:
    buttons = [button for button in MAIN_MENU_BUTTONS if is_admin or button != BTN_ADMIN]
    rows: list[list[KeyboardButton]] = []
    for i in range(0, len(buttons), 2):
        rows.append([KeyboardButton(text=text) for text in buttons[i : i + 2]])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        input_field_placeholder="Выберите раздел...",
    )


def ik_nav(back_to: str = "main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data=f"nav:{back_to}")]]
    )


def ik_profile() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Сменить ник", callback_data="nav:nick")],
            [InlineKeyboardButton(text="🎒 Инвентарь", callback_data="nav:inventory")],
            [InlineKeyboardButton(text="📈 Статистика", callback_data="nav:stats")],
            [InlineKeyboardButton(text="💼 Экономика", callback_data="nav:economy")],
            [InlineKeyboardButton(text="🖼 Мои карточки", callback_data="nav:my_cards")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="nav:main")],
        ]
    )

def ik_nick() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Ввести новый ник", callback_data="act:nick:enter")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="nav:profile")],
        ]
    )


def ik_get_card() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Получить бонус", callback_data="nav:bonus")],
            [InlineKeyboardButton(text="🖼 Открыть карточку полностью", callback_data="act:card:open_full")],
            [InlineKeyboardButton(text="📂 В коллекцию", callback_data="act:card:to_collection")],
            [InlineKeyboardButton(text="🔁 Повторить позже", callback_data="act:card:repeat_later")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="nav:main")],
        ]
    )


def ik_bonus_tasks(task_buttons: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for key, title in task_buttons:
        rows.append([InlineKeyboardButton(text=title, callback_data=f"act:bonus:open:{key}")])
    rows.append([InlineKeyboardButton(text="✅ Проверить", callback_data="act:bonus:check")])
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="nav:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ik_list_nav(items: list[tuple[str, str]], prefix: str, back_to: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for key, title in items:
        rows.append([InlineKeyboardButton(text=title, callback_data=f"{prefix}:{key}")])
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"nav:{back_to}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ik_top_select() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✨ По очкам", callback_data="nav:top:points")],
            [InlineKeyboardButton(text="🃏 По картам", callback_data="nav:top:cards")],
            [InlineKeyboardButton(text="💰 По монетам", callback_data="nav:top:coins")],
            [InlineKeyboardButton(text="💎 По редким", callback_data="nav:top:rare")],
            [InlineKeyboardButton(text="🏅 По уровню", callback_data="nav:top:level")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="nav:main")],
        ]
    )


def ik_shop_categories() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔥 Офферы", callback_data="nav:shop_offers")],
            [InlineKeyboardButton(text="🎉 Ивенты", callback_data="nav:events")],
            [InlineKeyboardButton(text="⚡ Бустеры", callback_data="nav:shop:boosters")],
            [InlineKeyboardButton(text="💰 Монеты", callback_data="nav:shop:coins")],
            [InlineKeyboardButton(text="🌟 Звезды", callback_data="nav:shop:stars")],
            [InlineKeyboardButton(text="📦 Сундуки", callback_data="nav:shop:chests")],
            [InlineKeyboardButton(text="🎟 Лимитки", callback_data="nav:shop:limits")],
            [InlineKeyboardButton(text="💎 Premium", callback_data="nav:shop:premium")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="nav:main")],
        ]
    )

def ik_admin_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👥 Пользователи", callback_data="nav:admin:users")],
            [InlineKeyboardButton(text="🃏 Карточки", callback_data="nav:admin:cards")],
            [InlineKeyboardButton(text="💎 Редкости", callback_data="nav:admin:rarities")],
            [InlineKeyboardButton(text="🎟 Лимитированные", callback_data="nav:admin:limited")],
            [InlineKeyboardButton(text="⚡ Бустеры", callback_data="nav:admin:boosters")],
            [InlineKeyboardButton(text="🛒 Магазин", callback_data="nav:admin:shop")],
            [InlineKeyboardButton(text="📦 Сундуки", callback_data="nav:admin:chests")],
            [InlineKeyboardButton(text="📜 Задания", callback_data="nav:admin:tasks")],
            [InlineKeyboardButton(text="🎭 RP-действия", callback_data="nav:admin:rp")],
            [InlineKeyboardButton(text="🏆 Топы и сезоны", callback_data="nav:admin:tops")],
            [InlineKeyboardButton(text="💰 Экономика", callback_data="nav:admin:economy")],
            [InlineKeyboardButton(text="📢 Рассылка", callback_data="nav:admin:broadcast")],
            [InlineKeyboardButton(text="🎉 Ивенты", callback_data="nav:admin:events")],
            [InlineKeyboardButton(text="🔐 Права", callback_data="nav:admin:permissions")],
            [InlineKeyboardButton(text="🧾 Логи", callback_data="nav:admin:logs")],
            [InlineKeyboardButton(text="⚙️ Настройки бота", callback_data="nav:admin:bot_settings")],
            [InlineKeyboardButton(text="🖼 Медиа", callback_data="nav:admin:media")],
            [InlineKeyboardButton(text="🔙 Выход", callback_data="nav:main")],
        ]
    )


def ik_rp_categories(items: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=title, callback_data=f"nav:rp_cat:{key}")] for key, title in items]
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="nav:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ik_rp_actions(category_key: str, items: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=title, callback_data=f"act:rp:do:{key}")] for key, title in items]
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="nav:rp")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ik_games_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎲 Кости", callback_data="nav:game:dice")],
            [InlineKeyboardButton(text="🎯 Угадай редкость", callback_data="nav:game:guess_rarity")],
            [InlineKeyboardButton(text="🪙 Орел/решка", callback_data="nav:game:coinflip")],
            [InlineKeyboardButton(text="🃏 Битва карточек", callback_data="nav:game:card_battle")],
            [InlineKeyboardButton(text="🎰 Слот", callback_data="nav:game:slot")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="nav:main")],
        ]
    )


def ik_game_stakes(game_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Ставка 50🪙", callback_data=f"act:game:play:{game_key}:50")],
            [InlineKeyboardButton(text="Ставка 200🪙", callback_data=f"act:game:play:{game_key}:200")],
            [InlineKeyboardButton(text="Ставка 500🪙", callback_data=f"act:game:play:{game_key}:500")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="nav:games")],
        ]
    )


def ik_market_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Купить карточку", callback_data="nav:market_buy")],
            [InlineKeyboardButton(text="📤 Выставить карточку", callback_data="act:market:sell:start")],
            [InlineKeyboardButton(text="🔍 Поиск", callback_data="act:market:search:start")],
            [InlineKeyboardButton(text="📜 Мои лоты", callback_data="nav:market_my")],
            [InlineKeyboardButton(text="⏱ История", callback_data="nav:market_history")],
            [InlineKeyboardButton(text="⭐ Лимитированные", callback_data="nav:market_limited")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="nav:main")],
        ]
    )


def ik_market_lot_actions(lot_id: int, can_buy: bool, can_cancel: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if can_buy:
        rows.append([InlineKeyboardButton(text="Купить", callback_data=f"act:market:buy:{lot_id}")])
    if can_cancel:
        rows.append([InlineKeyboardButton(text="Снять лот", callback_data=f"act:market:cancel:{lot_id}")])
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="nav:market")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ik_marriage_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💍 Сделать предложение", callback_data="act:marriage:propose:start")],
            [InlineKeyboardButton(text="💞 Моя пара", callback_data="nav:marriage_pair")],
            [InlineKeyboardButton(text="📨 Входящие предложения", callback_data="nav:marriage_inbox")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="nav:main")],
        ]
    )


def ik_marriage_proposal(proposal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Принять", callback_data=f"act:marriage:accept:{proposal_id}")],
            [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"act:marriage:decline:{proposal_id}")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="nav:marriage")],
        ]
    )


def ik_settings() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔔 Уведомления", callback_data="act:settings:toggle:notifications")],
            [InlineKeyboardButton(text="🌐 Язык", callback_data="act:settings:cycle:locale")],
            [InlineKeyboardButton(text="🔐 Приватность", callback_data="act:settings:toggle:privacy")],
            [InlineKeyboardButton(text="🧾 Подтверждение покупок", callback_data="act:settings:toggle:confirm")],
            [InlineKeyboardButton(text="🃏 Стиль выдачи карт", callback_data="act:settings:cycle:card_style")],
            [InlineKeyboardButton(text="🖼 Отображение медиа", callback_data="act:settings:toggle:media")],
            [InlineKeyboardButton(text="🛡 Безопасный режим", callback_data="act:settings:toggle:safe_mode")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="nav:main")],
        ]
    )


def ik_quote_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🃏 По последней карте", callback_data="act:quote:last_card")],
            [InlineKeyboardButton(text="✍️ По своему тексту", callback_data="act:quote:custom")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="nav:main")],
        ]
    )


def ik_admin_card_wizard(*, can_skip_photo: bool = False) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if can_skip_photo:
        rows.append([InlineKeyboardButton(text="⏭ Пропустить фото", callback_data="act:admin:card:wizard:skip_photo")])
    rows.append([InlineKeyboardButton(text="❌ Отменить", callback_data="act:admin:card:wizard:cancel")])
    rows.append([InlineKeyboardButton(text="🔙 К карточкам", callback_data="nav:admin:cards")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ik_sticker_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🃏 Стикер по карте", callback_data="act:sticker:last_card")],
            [InlineKeyboardButton(text="🎨 Стикер по шаблону", callback_data="act:sticker:template")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="nav:main")],
        ]
    )
