from __future__ import annotations

RARITY_RU = {
    "common": "Обычная",
    "rare": "Редкая",
    "mythic": "Мифическая",
    "legendary": "Легендарная",
    "limited": "Лимитированная",
}

METRIC_ALIASES = {
    "очки": "points",
    "points": "points",
    "карты": "cards",
    "cards": "cards",
    "монеты": "coins",
    "coins": "coins",
}

SERVICE_ERROR_RU = {
    "User not found": "Пользователь не найден.",
    "Cards catalog is empty": "Каталог карт пуст. Добавьте карты через админ-бота.",
    "Not enough stars": "Недостаточно звезд.",
    "Not enough coins": "Недостаточно монет.",
    "Unknown booster": "Неизвестный бустер.",
    "Unknown pack": "Неизвестный набор.",
    "Unknown chest rarity": "Неизвестная редкость сундука.",
    "Cannot marry yourself": "Нельзя заключить брак с самим собой.",
    "One of users is already married": "Один из пользователей уже в браке.",
    "Currency must be coins or stars": "Валюта должна быть coins или stars.",
    "Amount and price must be positive": "Количество и цена должны быть больше нуля.",
    "Only limited cards can be sold": "На маркет можно выставлять только лимитированные карты.",
    "Not enough cards": "Недостаточно карт.",
    "Listing not found": "Лот не найден.",
    "Not your listing": "Это не ваш лот.",
    "Listing is not active": "Лот уже не активен.",
    "Listing not available": "Лот недоступен.",
    "Cannot buy your own listing": "Нельзя купить собственный лот.",
    "Buyer or seller not found": "Покупатель или продавец не найден.",
    "Card not found": "Карта не найдена.",
    "Invalid field": "Недопустимое поле для редактирования.",
    "Invalid rarity": "Некорректная редкость.",
}


def rarity_to_ru(rarity: str) -> str:
    return RARITY_RU.get(rarity, rarity)


def service_error_to_ru(error: str | None) -> str:
    if not error:
        return "Произошла ошибка операции."
    return SERVICE_ERROR_RU.get(error, error)
