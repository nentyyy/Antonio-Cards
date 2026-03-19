from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def admin_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats")],
            [InlineKeyboardButton(text="🧩 Карты", callback_data="admin:cards")],
            [InlineKeyboardButton(text="⚙️ Настройки", callback_data="admin:settings")],
            [InlineKeyboardButton(text="📣 Рассылки", callback_data="admin:broadcast")],
        ]
    )


def cards_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить карту", callback_data="cards:add")],
            [InlineKeyboardButton(text="✏️ Редактировать карту", callback_data="cards:edit")],
            [InlineKeyboardButton(text="📋 Список карт", callback_data="cards:list")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin:main")],
        ]
    )


def settings_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎲 Шансы выпадения", callback_data="settings:drop")],
            [InlineKeyboardButton(text="⏱ Кулдауны", callback_data="settings:cooldown")],
            [InlineKeyboardButton(text="💰 Цены магазина", callback_data="settings:prices")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin:main")],
        ]
    )


def broadcast_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Всем", callback_data="broadcast:all")],
            [InlineKeyboardButton(text="Только premium", callback_data="broadcast:premium")],
            [InlineKeyboardButton(text="Без premium", callback_data="broadcast:nonpremium")],
            [InlineKeyboardButton(text="Активные за 7 дней", callback_data="broadcast:active7d")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin:main")],
        ]
    )
