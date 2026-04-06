from __future__ import annotations

from collections.abc import Iterator

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from app.bot.ui_defaults import (
    DEFAULT_BUTTON_LABELS,
    DEFAULT_INPUT_PLACEHOLDERS,
    MAIN_MENU_ALIASES,
    MAIN_MENU_ITEMS,
)
from app.infra.runtime import get_runtime

runtime = get_runtime()

ADMIN_MENU_BUTTONS: list[tuple[str, str]] = [
    ("admin.users", "nav:admin:users"),
    ("admin.cards", "nav:admin:cards"),
    ("admin.rarities", "nav:admin:rarities"),
    ("admin.limited", "nav:admin:limited"),
    ("admin.boosters", "nav:admin:boosters"),
    ("admin.shop", "nav:admin:shop"),
    ("admin.chests", "nav:admin:chests"),
    ("admin.tasks", "nav:admin:tasks"),
    ("admin.rp", "nav:admin:rp"),
    ("admin.tops", "nav:admin:tops"),
    ("admin.economy", "nav:admin:economy"),
    ("admin.broadcast", "nav:admin:broadcast"),
    ("admin.events", "nav:admin:events"),
    ("admin.permissions", "nav:admin:permissions"),
    ("admin.logs", "nav:admin:logs"),
    ("admin.bot_settings", "nav:admin:bot_settings"),
    ("admin.media", "nav:admin:media"),
    ("admin.exit", "nav:main"),
]


BTN_PROFILE = DEFAULT_BUTTON_LABELS["main.profile"]
BTN_GET_CARD = DEFAULT_BUTTON_LABELS["main.get_card"]
BTN_BONUS = DEFAULT_BUTTON_LABELS["main.bonus"]
BTN_TOP = DEFAULT_BUTTON_LABELS["main.top"]
BTN_SHOP = DEFAULT_BUTTON_LABELS["main.shop"]
BTN_CHEST = DEFAULT_BUTTON_LABELS["main.chest"]
BTN_PREMIUM = DEFAULT_BUTTON_LABELS["main.premium"]
BTN_TASKS = DEFAULT_BUTTON_LABELS["main.tasks"]
BTN_RP = DEFAULT_BUTTON_LABELS["main.rp"]
BTN_QUOTE = DEFAULT_BUTTON_LABELS["main.quote"]
BTN_STICKER = DEFAULT_BUTTON_LABELS["main.sticker"]
BTN_GAMES = DEFAULT_BUTTON_LABELS["main.games"]
BTN_MARKET = DEFAULT_BUTTON_LABELS["main.market"]
BTN_MARRIAGE = DEFAULT_BUTTON_LABELS["main.marriage"]
BTN_SETTINGS = DEFAULT_BUTTON_LABELS["main.settings"]
BTN_ADMIN = DEFAULT_BUTTON_LABELS["main.admin"]


def button_label(key: str, default: str | None = None) -> str:
    snapshot = runtime.settings_snapshot.get("button_labels")
    if isinstance(snapshot, dict):
        value = snapshot.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if default is not None:
        return default
    return DEFAULT_BUTTON_LABELS.get(key, key)


def input_placeholder(key: str, default: str | None = None) -> str:
    snapshot = runtime.settings_snapshot.get("input_placeholders")
    if isinstance(snapshot, dict):
        value = snapshot.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if default is not None:
        return default
    return DEFAULT_INPUT_PLACEHOLDERS.get(key, "")


def feature_flag_enabled(flag: str, default: bool = True) -> bool:
    snapshot = runtime.settings_snapshot.get("feature_flags")
    if isinstance(snapshot, dict):
        value = snapshot.get(flag)
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return bool(value)
    return default


def _safe_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        raw = value.strip().lower()
        if raw in {"1", "true", "yes", "on", "да"}:
            return True
        if raw in {"0", "false", "no", "off", "нет"}:
            return False
    return default


def main_menu_labels(*, include_admin: bool = True) -> list[str]:
    config = runtime.settings_snapshot.get("main_menu_items")
    labels: list[tuple[int, str]] = []
    for index, (key, screen, default) in enumerate(MAIN_MENU_ITEMS, start=1):
        cfg = config.get(key) if isinstance(config, dict) else {}
        order = _safe_int(cfg.get("order", index * 10), index * 10) if isinstance(cfg, dict) else index * 10
        visible = _safe_bool(cfg.get("visible", True), True) if isinstance(cfg, dict) else True
        admin_only = _safe_bool(cfg.get("admin_only", key == "main.admin"), key == "main.admin") if isinstance(cfg, dict) else key == "main.admin"
        if not visible:
            continue
        if admin_only and not include_admin:
            continue
        if not feature_flag_enabled(screen, True):
            continue
        labels.append((order, button_label(key, default)))
    labels.sort(key=lambda item: item[0])
    return [label for _, label in labels]


def screen_visible_in_menu(screen: str, *, include_admin: bool = True) -> bool:
    config = runtime.settings_snapshot.get("main_menu_items")
    for index, (key, current_screen, _default) in enumerate(MAIN_MENU_ITEMS, start=1):
        if current_screen != screen:
            continue
        cfg = config.get(key) if isinstance(config, dict) else {}
        visible = _safe_bool(cfg.get("visible", True), True) if isinstance(cfg, dict) else True
        admin_only = _safe_bool(cfg.get("admin_only", key == "main.admin"), key == "main.admin") if isinstance(cfg, dict) else key == "main.admin"
        if not visible:
            return False
        if admin_only and not include_admin:
            return False
        return feature_flag_enabled(screen, True)
    return True


def screen_by_main_menu_button(text: str) -> str | None:
    for key, screen, default in MAIN_MENU_ITEMS:
        if text == button_label(key, default):
            return screen
    return MAIN_MENU_ALIASES.get(text)


class MainMenuButtonSet:
    def __iter__(self) -> Iterator[str]:
        yield from main_menu_labels(include_admin=True)
        yield from MAIN_MENU_ALIASES.keys()

    def __contains__(self, value: object) -> bool:
        if not isinstance(value, str):
            return False
        return screen_by_main_menu_button(value) is not None

    def __len__(self) -> int:
        return len(main_menu_labels(include_admin=True)) + len(MAIN_MENU_ALIASES)


MAIN_MENU_BUTTONS = MainMenuButtonSet()


def main_menu(*, is_admin: bool = False) -> ReplyKeyboardMarkup:
    buttons = main_menu_labels(include_admin=is_admin)
    rows: list[list[KeyboardButton]] = []
    for index in range(0, len(buttons), 2):
        rows.append([KeyboardButton(text=text) for text in buttons[index : index + 2]])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        input_field_placeholder=input_placeholder("main_menu", DEFAULT_INPUT_PLACEHOLDERS["main_menu"]),
    )


def reply_menu_for_chat(chat_type: str | None, *, is_admin: bool = False) -> ReplyKeyboardMarkup | None:
    if chat_type != "private":
        return None
    return main_menu(is_admin=is_admin)


def ik_nav(back_to: str = "main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=button_label("common.back"), callback_data=f"nav:{back_to}")]
        ]
    )


def ik_profile() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=button_label("profile.change_nick"), callback_data="nav:nick")],
            [InlineKeyboardButton(text=button_label("profile.inventory"), callback_data="nav:inventory")],
            [InlineKeyboardButton(text=button_label("profile.stats"), callback_data="nav:stats")],
            [InlineKeyboardButton(text=button_label("profile.economy"), callback_data="nav:economy")],
            [InlineKeyboardButton(text=button_label("profile.cards"), callback_data="nav:my_cards")],
            [InlineKeyboardButton(text=button_label("common.back"), callback_data="nav:main")],
        ]
    )


def ik_nick() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=button_label("nick.enter"), callback_data="act:nick:enter")],
            [InlineKeyboardButton(text=button_label("common.back"), callback_data="nav:profile")],
        ]
    )


def ik_get_card() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=button_label("get_card.bonus"), callback_data="nav:bonus")],
            [InlineKeyboardButton(text=button_label("get_card.open_full"), callback_data="act:card:open_full")],
            [InlineKeyboardButton(text=button_label("get_card.collection"), callback_data="act:card:to_collection")],
            [InlineKeyboardButton(text=button_label("get_card.repeat_later"), callback_data="act:card:repeat_later")],
            [InlineKeyboardButton(text=button_label("common.back"), callback_data="nav:main")],
        ]
    )


def ik_bonus_tasks(task_buttons: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for key, title in task_buttons:
        rows.append([InlineKeyboardButton(text=title, callback_data=f"act:bonus:open:{key}")])
    rows.append([InlineKeyboardButton(text=button_label("bonus.check"), callback_data="act:bonus:check")])
    rows.append([InlineKeyboardButton(text=button_label("common.back"), callback_data="nav:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ik_list_nav(items: list[tuple[str, str]], prefix: str, back_to: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for key, title in items:
        rows.append([InlineKeyboardButton(text=title, callback_data=f"{prefix}:{key}")])
    rows.append([InlineKeyboardButton(text=button_label("common.back"), callback_data=f"nav:{back_to}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ik_top_select() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=button_label("top.points"), callback_data="nav:top:points")],
            [InlineKeyboardButton(text=button_label("top.cards"), callback_data="nav:top:cards")],
            [InlineKeyboardButton(text=button_label("top.coins"), callback_data="nav:top:coins")],
            [InlineKeyboardButton(text=button_label("top.rare"), callback_data="nav:top:rare")],
            [InlineKeyboardButton(text=button_label("top.level"), callback_data="nav:top:level")],
            [InlineKeyboardButton(text=button_label("common.back"), callback_data="nav:main")],
        ]
    )


def ik_shop_categories() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=button_label("shop.offers"), callback_data="nav:shop_offers")],
            [InlineKeyboardButton(text=button_label("shop.events"), callback_data="nav:events")],
            [InlineKeyboardButton(text=button_label("shop.boosters"), callback_data="nav:shop:boosters")],
            [InlineKeyboardButton(text=button_label("shop.coins"), callback_data="nav:shop:coins")],
            [InlineKeyboardButton(text=button_label("shop.stars"), callback_data="nav:shop:stars")],
            [InlineKeyboardButton(text=button_label("shop.chests"), callback_data="nav:shop:chests")],
            [InlineKeyboardButton(text=button_label("shop.limits"), callback_data="nav:shop:limits")],
            [InlineKeyboardButton(text=button_label("shop.premium"), callback_data="nav:shop:premium")],
            [InlineKeyboardButton(text=button_label("common.back"), callback_data="nav:main")],
        ]
    )


def ik_admin_main() -> InlineKeyboardMarkup:
    config = runtime.settings_snapshot.get("admin_menu_items")
    items: list[tuple[int, str, str]] = []
    for index, (key, callback_data) in enumerate(ADMIN_MENU_BUTTONS, start=1):
        cfg = config.get(key) if isinstance(config, dict) else {}
        order = _safe_int(cfg.get("order", index * 10), index * 10) if isinstance(cfg, dict) else index * 10
        visible = _safe_bool(cfg.get("visible", True), True) if isinstance(cfg, dict) else True
        if not visible:
            continue
        items.append((order, button_label(key), callback_data))
    items.sort(key=lambda item: item[0])
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=text, callback_data=callback_data)] for _, text, callback_data in items]
    )


def ik_rp_categories(items: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=title, callback_data=f"nav:rp_cat:{key}")] for key, title in items]
    rows.append([InlineKeyboardButton(text=button_label("common.back"), callback_data="nav:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ik_rp_actions(category_key: str, items: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=title, callback_data=f"act:rp:do:{key}")] for key, title in items]
    rows.append([InlineKeyboardButton(text=button_label("common.back"), callback_data="nav:rp")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ik_games_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=button_label("games.dice"), callback_data="nav:game:dice")],
            [InlineKeyboardButton(text=button_label("games.slot"), callback_data="nav:game:slot")],
            [InlineKeyboardButton(text=button_label("games.darts"), callback_data="nav:game:darts")],
            [InlineKeyboardButton(text=button_label("games.football"), callback_data="nav:game:football")],
            [InlineKeyboardButton(text=button_label("games.basketball"), callback_data="nav:game:basketball")],
            [InlineKeyboardButton(text=button_label("common.back"), callback_data="nav:main")],
        ]
    )


def ik_game_stakes(game_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Ставка 50🪙", callback_data=f"act:game:play:{game_key}:50")],
            [InlineKeyboardButton(text="Ставка 200🪙", callback_data=f"act:game:play:{game_key}:200")],
            [InlineKeyboardButton(text="Ставка 500🪙", callback_data=f"act:game:play:{game_key}:500")],
            [InlineKeyboardButton(text=button_label("common.back"), callback_data="nav:games")],
        ]
    )


def ik_market_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=button_label("market.buy"), callback_data="nav:market_buy")],
            [InlineKeyboardButton(text=button_label("market.sell"), callback_data="act:market:sell:start")],
            [InlineKeyboardButton(text=button_label("market.search"), callback_data="act:market:search:start")],
            [InlineKeyboardButton(text=button_label("market.my_lots"), callback_data="nav:market_my")],
            [InlineKeyboardButton(text=button_label("market.history"), callback_data="nav:market_history")],
            [InlineKeyboardButton(text=button_label("market.limited"), callback_data="nav:market_limited")],
            [InlineKeyboardButton(text=button_label("common.back"), callback_data="nav:main")],
        ]
    )


def ik_market_lot_actions(lot_id: int, can_buy: bool, can_cancel: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if can_buy:
        rows.append([InlineKeyboardButton(text=button_label("market.buy_lot"), callback_data=f"act:market:buy:{lot_id}")])
    if can_cancel:
        rows.append(
            [InlineKeyboardButton(text=button_label("market.cancel_lot"), callback_data=f"act:market:cancel:{lot_id}")]
        )
    rows.append([InlineKeyboardButton(text=button_label("common.back"), callback_data="nav:market")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ik_marriage_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=button_label("marriage.propose"), callback_data="act:marriage:propose:start")],
            [InlineKeyboardButton(text=button_label("marriage.pair"), callback_data="nav:marriage_pair")],
            [InlineKeyboardButton(text=button_label("marriage.inbox"), callback_data="nav:marriage_inbox")],
            [InlineKeyboardButton(text=button_label("common.back"), callback_data="nav:main")],
        ]
    )


def ik_marriage_proposal(proposal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=button_label("marriage.accept"), callback_data=f"act:marriage:accept:{proposal_id}")],
            [InlineKeyboardButton(text=button_label("marriage.decline"), callback_data=f"act:marriage:decline:{proposal_id}")],
            [InlineKeyboardButton(text=button_label("common.back"), callback_data="nav:marriage")],
        ]
    )


def ik_settings() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=button_label("settings.notifications"), callback_data="act:settings:toggle:notifications")],
            [InlineKeyboardButton(text=button_label("settings.locale"), callback_data="act:settings:cycle:locale")],
            [InlineKeyboardButton(text=button_label("settings.privacy"), callback_data="act:settings:toggle:privacy")],
            [InlineKeyboardButton(text=button_label("settings.confirm"), callback_data="act:settings:toggle:confirm")],
            [InlineKeyboardButton(text=button_label("settings.card_style"), callback_data="act:settings:cycle:card_style")],
            [InlineKeyboardButton(text=button_label("settings.media"), callback_data="act:settings:toggle:media")],
            [InlineKeyboardButton(text=button_label("settings.safe_mode"), callback_data="act:settings:toggle:safe_mode")],
            [InlineKeyboardButton(text=button_label("common.back"), callback_data="nav:main")],
        ]
    )


def ik_quote_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=button_label("quote.last_card"), callback_data="act:quote:last_card")],
            [InlineKeyboardButton(text=button_label("quote.custom"), callback_data="act:quote:custom")],
            [InlineKeyboardButton(text=button_label("common.back"), callback_data="nav:main")],
        ]
    )


def ik_admin_card_wizard(*, can_skip_photo: bool = False) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if can_skip_photo:
        rows.append([InlineKeyboardButton(text=button_label("common.skip_photo"), callback_data="act:admin:card:wizard:skip_photo")])
    rows.append([InlineKeyboardButton(text=button_label("common.cancel"), callback_data="act:admin:card:wizard:cancel")])
    rows.append([InlineKeyboardButton(text=button_label("admin.card.back"), callback_data="nav:admin:cards")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ik_sticker_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=button_label("sticker.last_card"), callback_data="act:sticker:last_card")],
            [InlineKeyboardButton(text=button_label("sticker.template"), callback_data="act:sticker:template")],
            [InlineKeyboardButton(text=button_label("common.back"), callback_data="nav:main")],
        ]
    )
