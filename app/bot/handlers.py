from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, Message, PreCheckoutQuery, ReplyKeyboardMarkup
from sqlalchemy import and_, func, select
from app.bot.context import display_name, ensure_user, h, is_admin_id, safe_callback_answer, template_text
from app.bot.keyboards import MAIN_MENU_BUTTONS, feature_flag_enabled, ik_admin_card_wizard, ik_admin_main, ik_bonus_tasks, ik_games_menu, ik_game_stakes, ik_get_card, ik_list_nav, ik_marriage_menu, ik_marriage_proposal, ik_market_lot_actions, ik_market_menu, ik_profile, ik_quote_menu, ik_rp_actions, ik_rp_categories, ik_shop_categories, ik_sticker_menu, ik_nav, main_menu, reply_menu_for_chat, screen_by_main_menu_button, screen_visible_in_menu
from app.bot.screens.core import handle_start_command, render_help_screen, screen_main, screen_nick, screen_profile
from app.bot.screens.leaderboards import screen_top, screen_top_metric
from app.bot.screens.settings import render_settings_screen
from app.bot.ui_defaults import DEFAULT_ADMIN_MENU_CONFIG, DEFAULT_BUTTON_LABELS, DEFAULT_INPUT_PLACEHOLDERS, DEFAULT_MAIN_MENU_CONFIG, DEFAULT_TEXT_TEMPLATES
from app.application.guards import user_action_guard
from app.config import get_settings
from app.db.models import BcActiveBooster, BcAuditLog, BcBonusTask, BcBooster, BcCard, BcCardInstance, BcChest, BcChestDrop, BcEvent, BcInputState, BcLimitedSeries, BcMarriageProposal, BcMedia, BcMarketLot, BcPermission, BcRole, BcRolePermission, BcRPAction, BcRPCategory, BcRarity, BcShopCategory, BcShopItem, BcTask, BcUserRole, BcUserState, BcUserSettings, Marriage, User, UserProfile
from app.db.session import SessionLocal
from app.services.brawl_cards_service import BrawlCardsService
from app.services.broadcast_service import run_text_broadcast
from app.utils.sticker import build_card_image
from app.utils.time import seconds_to_hms
router = Router(name='brawl_cards_user_bot')

PRIVATE_CHAT_SCREENS = {
    'profile',
    'inventory',
    'stats',
    'economy',
    'my_cards',
    'nick',
    'shop',
    'shop_offers',
    'chest',
    'premium',
    'tasks',
    'market',
    'marriage',
    'settings',
    'admin',
}


def chat_type_of(message: Message | None) -> str | None:
    return message.chat.type if message and message.chat else None


def user_menu(user_id: int | None, chat_type: str | None='private') -> ReplyKeyboardMarkup | None:
    return reply_menu_for_chat(chat_type, is_admin=is_admin_id(user_id or 0))


COOLDOWN_LABELS = {
    'brawl_cards': 'Карточка',
    'bonus': 'Бонус',
    'nick_change': 'Смена ника',
    'dice': 'Dice',
    'slot': 'Slot',
    'darts': 'Darts',
    'football': 'Football',
    'basketball': 'Basketball',
    'guess_rarity': 'Guess rarity',
    'coinflip': 'Coinflip',
    'card_battle': 'Card battle',
    'premium_game_reduction': 'Premium reduction',
}


def cooldown_label(key: str) -> str:
    return COOLDOWN_LABELS.get(key, key.replace('_', ' '))


async def send_rp_result(message: Message, text: str, media: BcMedia | None=None) -> None:
    reply_markup = user_menu(
        message.from_user.id if message.from_user else None,
        chat_type_of(message),
    )
    if media is None:
        await message.answer(text, reply_markup=reply_markup, parse_mode='Markdown')
        return
    file_id = media.telegram_file_id
    if media.kind == 'photo' and file_id:
        await message.answer_photo(file_id, caption=text, reply_markup=reply_markup, parse_mode='Markdown')
        return
    if media.kind == 'video' and file_id:
        await message.answer_video(file_id, caption=text, reply_markup=reply_markup, parse_mode='Markdown')
        return
    if media.kind == 'animation' and file_id:
        await message.answer_animation(file_id, caption=text, reply_markup=reply_markup, parse_mode='Markdown')
        return
    if media.kind == 'sticker' and file_id:
        await message.answer_sticker(file_id)
        await message.answer(text, reply_markup=reply_markup, parse_mode='Markdown')
        return
    await message.answer(text, reply_markup=reply_markup, parse_mode='Markdown')


async def screen_get_card(message: Message) -> None:
    if message.from_user is None:
        return
    await ensure_user(message)
    async with SessionLocal() as session:
        service = BrawlCardsService(session)
        async with session.begin():
            result = await service.brawl_get_card(message.from_user.id)
        if not result.get('ok'):
            if 'cooldown' in result:
                await message.answer(
                    f"{h('\U0001f0cf \u041f\u043e\u043b\u0443\u0447\u0438\u0442\u044c \u043a\u0430\u0440\u0442\u0443')}\n\u041a\u0443\u043b\u0434\u0430\u0443\u043d: {seconds_to_hms(int(result['cooldown']))}\n\n\u041f\u043e\u0434\u0441\u043a\u0430\u0437\u043a\u0430: Premium \u0438 \u0431\u0443\u0441\u0442\u0435\u0440\u044b \u043c\u043e\u0433\u0443\u0442 \u0441\u043e\u043a\u0440\u0430\u0449\u0430\u0442\u044c \u043e\u0436\u0438\u0434\u0430\u043d\u0438\u0435.",
                    reply_markup=ik_get_card(),
                )
                return
            await message.answer(f"{h('\U0001f0cf \u041f\u043e\u043b\u0443\u0447\u0438\u0442\u044c \u043a\u0430\u0440\u0442\u0443')}\n{result.get('error', '\u041e\u0448\u0438\u0431\u043a\u0430')}", reply_markup=ik_get_card())
            return
        card = result['card']
        title = card['title']
        rarity = f"{card['rarity_emoji']} {card['rarity_title']}"
        series = card['series']
        is_limited = '\u0434\u0430' if card['is_limited'] else '\u043d\u0435\u0442'
        obtained = card['obtained_at'].isoformat(timespec='seconds')
        text = (
            f"{h('\U0001f0cf \u041a\u0430\u0440\u0442\u0430 \u043f\u043e\u043b\u0443\u0447\u0435\u043d\u0430')}\n"
            f"\U0001faaa \u041d\u0430\u0437\u0432\u0430\u043d\u0438\u0435: *{title}*\n"
            f"\U0001f4da \u0421\u0435\u0440\u0438\u044f: `{series}`\n"
            f"\U0001f4a0 \u0420\u0435\u0434\u043a\u043e\u0441\u0442\u044c: {rarity}\n"
            f"\U0001f4dd \u041e\u043f\u0438\u0441\u0430\u043d\u0438\u0435: {card['description']}\n\n"
            f"\u2728 \u041e\u0447\u043a\u0438: +{card['points']}\n"
            f"\U0001fa99 \u041c\u043e\u043d\u0435\u0442\u044b: +{card['coins']}\n"
            f"\U0001f39f \u041b\u0438\u043c\u0438\u0442\u043a\u0430: {is_limited}\n"
            f"\U0001f5d3 \u0414\u0430\u0442\u0430: `{obtained}`"
        )
        file_id = card.get('image_file_id')
        if file_id:
            await message.answer_photo(file_id, caption=text, reply_markup=ik_get_card(), parse_mode='Markdown')
        else:
            await message.answer(text, reply_markup=ik_get_card(), parse_mode='Markdown')

async def screen_bonus(message: Message) -> None:
    async with SessionLocal() as session:
        service = BrawlCardsService(session)
        tasks = await service.bonus_tasks()
        body = await template_text(session, message.from_user.id if message.from_user else None, 'screen.bonus', DEFAULT_TEXT_TEMPLATES['screen.bonus'])
        btns = [(t.key, f"{t.emoji} {t.title}") for t in tasks]
    text = (
        f"{h('🎁 Бонус')}\n"
        f"Активных бонусных задач: {len(tasks)}\n"
        f"{body}"
    )
    await message.answer(text, reply_markup=ik_bonus_tasks(btns))

async def screen_shop(message: Message) -> None:
    if message.from_user is None:
        return
    await ensure_user(message)
    async with SessionLocal() as session:
        service = BrawlCardsService(session)
        categories = await service.shop_categories()
        body = await template_text(session, message.from_user.id, 'screen.shop', DEFAULT_TEXT_TEMPLATES['screen.shop'])
    lines = [
        h("\U0001f6d2 \u041c\u0430\u0433\u0430\u0437\u0438\u043d"),
        body,
        "",
    ]
    if categories:
        lines.append("\u0410\u043a\u0442\u0438\u0432\u043d\u044b\u0435 \u043a\u0430\u0442\u0435\u0433\u043e\u0440\u0438\u0438:")
        for category in categories[:8]:
            lines.append(f"\u2022 `{category}`")
        lines.append("")
        lines.append("\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u043d\u0443\u0436\u043d\u044b\u0439 \u0440\u0430\u0437\u0434\u0435\u043b \u043a\u043d\u043e\u043f\u043a\u0430\u043c\u0438 \u043d\u0438\u0436\u0435.")
    else:
        lines.append("\u041f\u043e\u043a\u0430 \u043d\u0435\u0442 \u0430\u043a\u0442\u0438\u0432\u043d\u044b\u0445 \u0442\u043e\u0432\u0430\u0440\u043e\u0432.")
    await message.answer("\n".join(lines), reply_markup=ik_shop_categories(), parse_mode="Markdown")

async def screen_shop_category(message: Message, category_key: str) -> None:
    if message.from_user is None:
        return
    await ensure_user(message)
    async with SessionLocal() as session:
        service = BrawlCardsService(session)
        items = await service.shop_items(category_key)
    if not items:
        await message.answer(f"{h('🛒 Магазин')}\nПока нет товаров в категории.", reply_markup=ik_shop_categories())
        return
    buttons = [(it.key, f"🧩 {it.title}") for it in items]
    await message.answer(f"{h('🛒 Магазин')}\nКатегория: `{category_key}`\nВыберите товар.", reply_markup=ik_list_nav(buttons, prefix='nav:shop_item', back_to='shop'), parse_mode='Markdown')

async def screen_shop_item(message: Message, item_key: str) -> None:
    if message.from_user is None:
        return
    await ensure_user(message)
    async with SessionLocal() as session:
        service = BrawlCardsService(session)
        item = await service.shop_item(item_key)
        if item is None:
            await message.answer(f"{h('\U0001f6d2 \u041c\u0430\u0433\u0430\u0437\u0438\u043d')}\n\u0422\u043e\u0432\u0430\u0440 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d.", reply_markup=ik_shop_categories())
            return
    price_lines: list[str] = []
    if item.price_coins is not None:
        price_lines.append(f"🪙 {item.price_coins}")
    if item.price_stars is not None:
        price_lines.append(f"⭐ {item.price_stars}")
    price_text = "\n".join(price_lines) if price_lines else "бесплатно"
    duration = seconds_to_hms(item.duration_seconds) if item.duration_seconds else "без срока"
    text = (
        f"{h('\U0001f6d2 \u0422\u043e\u0432\u0430\u0440')}\n"
        f"📦 *{item.title}*\n"
        f"📝 {item.description}\n\n"
        f"💳 Цена:\n{price_text}\n"
        f"⏱ Срок: {duration}"
    )
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    rows: list[list[InlineKeyboardButton]] = []
    if item.price_coins is not None:
        rows.append([InlineKeyboardButton(text="\u041a\u0443\u043f\u0438\u0442\u044c \u0437\u0430 \u043c\u043e\u043d\u0435\u0442\u044b", callback_data=f"act:buy:{item.key}:coins")])
    if item.price_stars is not None:
        rows.append([InlineKeyboardButton(text="\u041a\u0443\u043f\u0438\u0442\u044c \u0437\u0430 \u0437\u0432\u0435\u0437\u0434\u044b \u0431\u043e\u0442\u0430", callback_data=f"act:buy:{item.key}:stars")])
        rows.append([InlineKeyboardButton(text="⭐ Оплатить Telegram Stars", callback_data=f"act:buy_xtr:{item.key}")])
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"nav:shop:{item.category_key}")])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")

async def screen_chest(message: Message) -> None:
    async with SessionLocal() as session:
        service = BrawlCardsService(session)
        chests = await service.chests()
        body = await template_text(session, message.from_user.id if message.from_user else None, 'screen.chest', DEFAULT_TEXT_TEMPLATES['screen.chest'])
        items = [(c.key, f"{c.emoji} {c.title}") for c in chests]
    text = f"{h('📦 Сундуки')}\nДоступно сундуков: {len(chests)}\n{body}"
    await message.answer(text, reply_markup=ik_list_nav(items, prefix='nav:chest', back_to='main'))

async def screen_premium(message: Message) -> None:
    async with SessionLocal() as session:
        body = await template_text(session, message.from_user.id if message.from_user else None, 'screen.premium', DEFAULT_TEXT_TEMPLATES['screen.premium'])
        service = BrawlCardsService(session)
        items = await service.shop_items('premium')
    lines = [
        h('💎 Премиум'),
        body,
        '',
        'Что даёт:',
        '• меньше cooldown на карты и игры',
        '• выше шанс редких карт',
        '• больше награда за дроп',
        '• расширенные RP-возможности',
        '• визуальные отметки в профиле',
    ]
    buttons: list[tuple[str, str]] = []
    for item in items[:8]:
        price = f"{item.price_stars}⭐" if item.price_stars is not None else f"{item.price_coins}🪙"
        buttons.append((item.key, f"{item.title[:24]} • {price}"))
    if buttons:
        lines.extend(['', 'Пакеты:'])
        for item in items[:5]:
            price_parts: list[str] = []
            if item.price_stars is not None:
                price_parts.append(f"{item.price_stars}⭐")
            if item.price_coins is not None:
                price_parts.append(f"{item.price_coins}🪙")
            lines.append(f"• {item.title} — {' / '.join(price_parts)}")
        await message.answer('\n'.join(lines), reply_markup=ik_list_nav(buttons, prefix='nav:shop_item', back_to='main'))
        return
    text = (
        '\n'.join(lines)
        + "\n\nПакеты пока не настроены. Добавьте premium-товары в магазин через админку."
    )
    await message.answer(text, reply_markup=ik_shop_categories())

async def screen_tasks(message: Message) -> None:
    if message.from_user is None:
        return
    await ensure_user(message)
    async with SessionLocal() as session:
        service = BrawlCardsService(session)
        body = await template_text(session, message.from_user.id, 'screen.tasks', DEFAULT_TEXT_TEMPLATES['screen.tasks'])
        async with session.begin():
            tasks = await service.tasks()
            lines: list[str] = [h('\U0001f4dc \u0417\u0430\u0434\u0430\u043d\u0438\u044f'), body, '', 'Выберите задание и получите награду:']
            buttons: list[tuple[str, str]] = []
            for t in tasks:
                row = await service.get_user_task(message.from_user.id, t)
                await service.refresh_task_period(row, t)
                status = '\u2705' if row.claimed_at else '\U0001f7e9' if row.completed_at else '\u2b1b'
                lines.append(f"{status} {t.title} \u2014 {row.progress}/{t.target}")
                buttons.append((t.key, f"{status} {t.title[:28]}"))
    await message.answer('\n'.join(lines), reply_markup=ik_list_nav(buttons, prefix='nav:task', back_to='main'))

async def screen_rp(message: Message) -> None:
    async with SessionLocal() as session:
        service = BrawlCardsService(session)
        categories = await service.rp_categories()
        body = await template_text(session, message.from_user.id if message.from_user else None, 'screen.rp', DEFAULT_TEXT_TEMPLATES['screen.rp'])
        items = [(c.key, f"{c.emoji} {c.title}") for c in categories]
    text = f"{h('🎭 RP')}\n{body}"
    await message.answer(text, reply_markup=ik_rp_categories(items))

async def screen_quote(message: Message) -> None:
    async with SessionLocal() as session:
        body = await template_text(session, message.from_user.id if message.from_user else None, 'screen.quote', DEFAULT_TEXT_TEMPLATES['screen.quote'])
    text = f"{h('💬 Цитата')}\n{body}"
    await message.answer(text, reply_markup=ik_quote_menu())

async def screen_sticker(message: Message) -> None:
    async with SessionLocal() as session:
        body = await template_text(session, message.from_user.id if message.from_user else None, 'screen.sticker', DEFAULT_TEXT_TEMPLATES['screen.sticker'])
    text = f"{h('🎨 Стикер')}\n{body}"
    await message.answer(text, reply_markup=ik_sticker_menu())

async def screen_games(message: Message) -> None:
    async with SessionLocal() as session:
        body = await template_text(session, message.from_user.id if message.from_user else None, 'screen.games', DEFAULT_TEXT_TEMPLATES['screen.games'])
    text = f"{h('🎮 Игры')}\n{body}"
    await message.answer(text, reply_markup=ik_games_menu())


async def render_game_detail(message: Message, game_key: str) -> None:
    game_info = {
        'dice': ('🎲 Кости', 'Классический бросок кубика. Чем выше значение, тем выше выплата.'),
        'slot': ('🎰 Слоты', 'Реальный Telegram slot. Выплата зависит от фактического числового результата.'),
        'darts': ('🎯 Дартс', 'Чем ближе к центру, тем лучше множитель.'),
        'football': ('⚽ Футбол', 'Telegram футбольный удар. Голы дают повышенную выплату.'),
        'basketball': ('🏀 Баскетбол', 'Telegram бросок в кольцо. Чистое попадание награждается сильнее.'),
    }
    title, description = game_info.get(game_key, ('🎮 Игра', 'Игра не найдена.'))
    if game_key not in game_info:
        await screen_games(message)
        return
    text = (
        f"{h(title)}\n"
        f"{description}\n\n"
        "Ставка списывается до броска.\n"
        "Если Telegram не отправит emoji-результат, ставка будет возвращена.\n"
        "Кулдаун применяется после завершения игры."
    )
    await message.answer(text, reply_markup=ik_game_stakes(game_key))


async def screen_market(message: Message) -> None:
    async with SessionLocal() as session:
        body = await template_text(session, message.from_user.id if message.from_user else None, 'screen.market', DEFAULT_TEXT_TEMPLATES['screen.market'])
    text = f"{h('💱 Маркет')}\n{body}"
    await message.answer(text, reply_markup=ik_market_menu())


async def render_market_list(message: Message, mode: str) -> None:
    if message.from_user is None:
        return
    async with SessionLocal() as session:
        service = BrawlCardsService(session)
        if mode == 'buy':
            rows = await service.market_lots(active_only=True, limit=20)
            title = '🛒 Покупка'
        elif mode == 'limited':
            rows = await service.market_lots(only_limited=True, active_only=True, limit=20)
            title = '🎟 Лимитки'
        elif mode == 'my':
            rows = await service.market_lots(seller_id=message.from_user.id, limit=20, active_only=False)
            title = '📤 Мои лоты'
        else:
            rows = await service.market_lots(buyer_or_seller_id=message.from_user.id, limit=20, active_only=False)
            title = '🧾 История маркета'
    if not rows:
        await message.answer(f"{h(title)}\nПока нет подходящих лотов.", reply_markup=ik_market_menu())
        return
    buttons: list[tuple[str, str]] = []
    for lot, card, seller in rows:
        price_icon = '🪙' if lot.currency == 'coins' else '⭐'
        buttons.append((str(lot.id), f"#{lot.id} {card.title[:18]} • {lot.price}{price_icon}"))
    await message.answer(
        f"{h(title)}\nВыберите лот для подробного просмотра.",
        reply_markup=ik_list_nav(buttons, prefix='nav:market_lot', back_to='market'),
    )


async def render_market_lot(message: Message, lot_id: int) -> None:
    if message.from_user is None:
        return
    async with SessionLocal() as session:
        service = BrawlCardsService(session)
        target = await service.market_lot(lot_id)
    if target is None:
        await message.answer(f"{h('💱 Маркет')}\nЛот не найден.", reply_markup=ik_market_menu())
        return
    lot, card, seller = target
    price_icon = '🪙' if lot.currency == 'coins' else '⭐'
    status_map = {'active': 'активен', 'sold': 'продан', 'cancelled': 'снят'}
    text = (
        f"{h('💱 Лот маркета')}\n"
        f"Лот: #{lot.id}\n"
        f"Карточка: {card.title}\n"
        f"Редкость: {card.rarity_key}\n"
        f"Продавец: {display_name(seller)}\n"
        f"Цена: {lot.price}{price_icon}\n"
        f"Комиссия: {lot.fee_percent}%\n"
        f"Статус: {status_map.get(lot.status, lot.status)}"
    )
    can_buy = lot.status == 'active' and lot.seller_id != message.from_user.id
    can_cancel = lot.status == 'active' and lot.seller_id == message.from_user.id
    await message.answer(text, reply_markup=ik_market_lot_actions(lot.id, can_buy=can_buy, can_cancel=can_cancel))


async def screen_marriage(message: Message) -> None:
    async with SessionLocal() as session:
        body = await template_text(session, message.from_user.id if message.from_user else None, 'screen.marriage', DEFAULT_TEXT_TEMPLATES['screen.marriage'])
    text = f"{h('\U0001f48d \u0411\u0440\u0430\u043a')}\n{body}"
    await message.answer(text, reply_markup=ik_marriage_menu())


async def render_marriage_inbox(message: Message) -> None:
    if message.from_user is None:
        return
    async with SessionLocal() as session:
        service = BrawlCardsService(session)
        rows = await service.marriage_inbox(message.from_user.id)
    if not rows:
        await message.answer(f"{h('\U0001f48d \u0412\u0445\u043e\u0434\u044f\u0449\u0438\u0435 \u043f\u0440\u0435\u0434\u043b\u043e\u0436\u0435\u043d\u0438\u044f')}\n\u0412\u0445\u043e\u0434\u044f\u0449\u0438\u0445 \u043f\u0440\u0435\u0434\u043b\u043e\u0436\u0435\u043d\u0438\u0439 \u043d\u0435\u0442.", reply_markup=ik_marriage_menu())
        return
    for row in rows[:10]:
        text = f"{h('\U0001f48d \u041f\u0440\u0435\u0434\u043b\u043e\u0436\u0435\u043d\u0438\u0435')}\nID: `{row.id}`\n\u041e\u0442 \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044f: `{row.proposer_id}`\n\u0414\u0430\u0442\u0430: {row.created_at.date().isoformat()}"
        await message.answer(text, reply_markup=ik_marriage_proposal(row.id), parse_mode='Markdown')

async def screen_admin(message: Message) -> None:
    if message.from_user is None:
        return
    if not is_admin_id(message.from_user.id):
        allowed = ", ".join(str(x) for x in sorted(get_settings().admin_id_set()))
        await message.answer(
            f"{h('\U0001f6e0 \u0410\u0434\u043c\u0438\u043d-\u043f\u0430\u043d\u0435\u043b\u044c')}\n"
            f"\u0414\u043e\u0441\u0442\u0443\u043f \u0437\u0430\u043f\u0440\u0435\u0449\u0451\u043d.\n"
            f"\u0412\u0430\u0448 ID: `{message.from_user.id}`\n"
            f"\u0420\u0430\u0437\u0440\u0435\u0448\u0451\u043d\u043d\u044b\u0435 ID: `{allowed}`",
            reply_markup=main_menu(is_admin=is_admin_id(message.from_user.id)),
            parse_mode='Markdown',
        )
        return
    await message.answer(f"{h('\U0001f6e0 \u0410\u0434\u043c\u0438\u043d-\u043f\u0430\u043d\u0435\u043b\u044c')}\n\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0440\u0430\u0437\u0434\u0435\u043b.", reply_markup=ik_admin_main())

async def render_admin_section_v2(message: Message, section: str) -> bool:
    if message.from_user is None or not is_admin_id(message.from_user.id):
        return False
    async with SessionLocal() as session:
        if section == 'users':
            rows = (await session.scalars(select(User).order_by(User.created_at.desc()).limit(12))).all()
            lines = [h('👥 Пользователи'), 'Последние зарегистрированные:']
            for user in rows:
                name = user.nickname or user.first_name or str(user.id)
                lines.append(f"• {name} | ID {user.id} | {user.coins}🪙 | {user.stars}⭐")
            lines.append('')
            lines.append('Формат редактирования: `user_id|field|value`')
            lines.append('Поля: `coins`, `stars`, `points`, `level`, `exp`, `premium_days`, `nickname`, `cooldown:action`')
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text='✏️ Изменить пользователя', callback_data='act:admin:user:manage:start')],
                    [InlineKeyboardButton(text='🔙 Назад', callback_data='nav:admin')],
                ]
            )
            await message.answer('\n'.join(lines), reply_markup=kb, parse_mode='Markdown')
            return True
        if section == 'cards':
            rows = (await session.scalars(select(BcCard).order_by(BcCard.created_at.desc()).limit(20))).all()
            items = [(str(card.id), f"{card.title} | {card.rarity_key} | {card.series}") for card in rows]
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text='➕ Добавить карточку', callback_data='act:admin:card:create')],
                    *[[InlineKeyboardButton(text=title, callback_data=f"nav:admin_card:{key}")] for key, title in items],
                    [InlineKeyboardButton(text='🔙 Назад', callback_data='nav:admin')],
                ]
            )
            await message.answer(f"{h('🃏 Карточки')}\nВыберите карточку для просмотра или редактирования.", reply_markup=kb)
            return True
        if section == 'rarities':
            rows = (await session.scalars(select(BcRarity).order_by(BcRarity.sort, BcRarity.key).limit(20))).all()
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text='➕ Добавить редкость', callback_data='act:admin:rarity:create')],
                    *[
                        [InlineKeyboardButton(text=f"{row.emoji} {row.title} | {row.key}", callback_data=f"nav:admin_rarity:{row.key}")]
                        for row in rows
                    ],
                    [InlineKeyboardButton(text='🔙 Назад', callback_data='nav:admin')],
                ]
            )
            await message.answer(f"{h('💎 Редкости')}\nВыберите редкость для просмотра или редактирования.", reply_markup=kb)
            return True
        if section == 'boosters':
            rows = (await session.scalars(select(BcBooster).order_by(BcBooster.key).limit(20))).all()
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text='➕ Добавить бустер', callback_data='act:admin:booster:create')],
                    *[
                        [InlineKeyboardButton(text=f"{row.emoji} {row.title} | {row.key}", callback_data=f"nav:admin_booster:{row.key}")]
                        for row in rows
                    ],
                    [InlineKeyboardButton(text='🔙 Назад', callback_data='nav:admin')],
                ]
            )
            await message.answer(f"{h('⚡ Бустеры')}\nВыберите бустер для просмотра или редактирования.", reply_markup=kb)
            return True
        if section == 'chests':
            rows = (await session.scalars(select(BcChest).order_by(BcChest.sort, BcChest.key).limit(20))).all()
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text='➕ Добавить сундук', callback_data='act:admin:chest:create')],
                    *[
                        [InlineKeyboardButton(text=f"{row.emoji} {row.title} | {row.key}", callback_data=f"nav:admin_chest:{row.key}")]
                        for row in rows
                    ],
                    [InlineKeyboardButton(text='🔙 Назад', callback_data='nav:admin')],
                ]
            )
            await message.answer(f"{h('📦 Сундуки')}\nВыберите сундук для просмотра или редактирования.", reply_markup=kb)
            return True
        if section == 'limited':
            rows = (await session.scalars(select(BcLimitedSeries).order_by(BcLimitedSeries.created_at.desc()).limit(10))).all()
            lines = [h('🎟 Лимитированные'), 'Лимитированные серии:']
            if not rows:
                lines.append('• Серии ещё не созданы.')
            for row in rows:
                lines.append(f"• {row.title} | key={row.key} | released={int(row.is_released)}")
            await message.answer('\n'.join(lines), reply_markup=ik_admin_main())
            return True
        if section == 'shop':
            cats = (await session.scalars(select(BcShopCategory).order_by(BcShopCategory.sort))).all()
            items = (await session.scalars(select(BcShopItem).order_by(BcShopItem.sort).limit(20))).all()
            rows: list[list[InlineKeyboardButton]] = [
                [InlineKeyboardButton(text='➕ Категория', callback_data='act:admin:shop_category:create')],
                [InlineKeyboardButton(text='➕ Товар', callback_data='act:admin:shop_item:create')],
            ]
            for cat in cats[:8]:
                rows.append([InlineKeyboardButton(text=f"{cat.emoji} {cat.title}", callback_data=f"nav:admin_shopcat:{cat.key}")])
            for item in items[:10]:
                rows.append([InlineKeyboardButton(text=f"🛍 {item.title}", callback_data=f"nav:admin_shopitem:{item.id}")])
            rows.append([InlineKeyboardButton(text='🔙 Назад', callback_data='nav:admin')])
            kb = InlineKeyboardMarkup(inline_keyboard=rows)
            lines = [h('🛒 Магазин'), f'Категорий: {len(cats)}', f'Товаров: {len(items)}', '', 'Выберите категорию или товар для управления.']
            await message.answer('\n'.join(lines), reply_markup=kb)
            return True
        if section == 'tasks':
            rows = (await session.scalars(select(BcTask).order_by(BcTask.sort).limit(20))).all()
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text='➕ Добавить задание', callback_data='act:admin:task:create')],
                    *[
                        [InlineKeyboardButton(text=f"{'🟢' if task.is_active else '⚫'} {task.title}", callback_data=f"nav:admin_task:{task.key}")]
                        for task in rows
                    ],
                    [InlineKeyboardButton(text='🔙 Назад', callback_data='nav:admin')],
                ]
            )
            lines = [h('📜 Задания'), f'Активных и скрытых записей: {len(rows)}', '', 'Выберите задание для редактирования.']
            await message.answer('\n'.join(lines), reply_markup=kb)
            return True
        if section == 'rp':
            cats = (await session.scalars(select(BcRPCategory).order_by(BcRPCategory.sort))).all()
            acts = (await session.scalars(select(BcRPAction).order_by(BcRPAction.sort).limit(20))).all()
            rows: list[list[InlineKeyboardButton]] = [
                [InlineKeyboardButton(text='➕ Категория RP', callback_data='act:admin:rp_category:create')],
                [InlineKeyboardButton(text='➕ RP-действие', callback_data='act:admin:rp_action:create')],
            ]
            for cat in cats[:10]:
                rows.append([InlineKeyboardButton(text=f"{cat.emoji} {cat.title}", callback_data=f"nav:admin_rpcat:{cat.key}")])
            for act in acts[:10]:
                rows.append([InlineKeyboardButton(text=f"{act.emoji} {act.title}", callback_data=f"nav:admin_rpact:{act.key}")])
            rows.append([InlineKeyboardButton(text='🔙 Назад', callback_data='nav:admin')])
            kb = InlineKeyboardMarkup(inline_keyboard=rows)
            lines = [h('🎭 RP-действия'), f"Категорий: {len(cats)}", f"Действий: {len(acts)}", '', 'Выберите категорию или действие для редактирования.']
            await message.answer('\n'.join(lines), reply_markup=kb)
            return True
        if section == 'tops':
            users_total = int(await session.scalar(select(func.count()).select_from(User)) or 0)
            cards_total = int(await session.scalar(select(func.count()).select_from(BcCardInstance)) or 0)
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text='👥 К пользователям', callback_data='nav:admin:users')],
                    [InlineKeyboardButton(text='🃏 К карточкам', callback_data='nav:admin:cards')],
                    [InlineKeyboardButton(text='🔙 Назад', callback_data='nav:admin')],
                ]
            )
            await message.answer(f"{h('🏆 Топы и сезоны')}\nПользователей: {users_total}\nВыданных карт: {cards_total}\nКонтур рейтингов привязан к пользователям и карточкам.", reply_markup=kb)
            return True
        if section == 'economy':
            lots_total = int(await session.scalar(select(func.count()).select_from(BcMarketLot)) or 0)
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text='👥 Управление пользователем', callback_data='act:admin:user:manage:start')],
                    [InlineKeyboardButton(text='🛒 Магазин', callback_data='nav:admin:shop')],
                    [InlineKeyboardButton(text='📦 Сундуки', callback_data='nav:admin:chests')],
                    [InlineKeyboardButton(text='🔙 Назад', callback_data='nav:admin')],
                ]
            )
            await message.answer(f"{h('💰 Экономика')}\nЛотов на маркете: {lots_total}\nБаланс, цены и выдачи теперь управляются через пользователей, магазин и сундуки.", reply_markup=kb)
            return True
        if section == 'broadcast':
            total_users = int(await session.scalar(select(func.count()).select_from(User)) or 0)
            lines = [
                h('📢 Рассылка'),
                f'Получателей: {total_users}',
                '',
                'Рассылка отправляется в фоне батчами.',
                'Админский интерфейс не блокируется во время отправки.',
            ]
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text='📢 Запустить рассылку', callback_data='act:admin:broadcast:start')],
                    [InlineKeyboardButton(text='⚙️ К настройкам бота', callback_data='nav:admin:bot_settings')],
                    [InlineKeyboardButton(text='🔙 Назад', callback_data='nav:admin')],
                ]
            )
            await message.answer('\n'.join(lines), reply_markup=kb)
            return True
        if section == 'events':
            rows = (await session.scalars(select(BcEvent).order_by(BcEvent.created_at.desc()).limit(10))).all()
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text='➕ Добавить ивент', callback_data='act:admin:event:create')],
                    *[
                        [InlineKeyboardButton(text=f"{'🟢' if event.is_active else '⚫'} {event.title}", callback_data=f"nav:admin_event:{event.key}")]
                        for event in rows
                    ],
                    [InlineKeyboardButton(text='🔙 Назад', callback_data='nav:admin')],
                ]
            )
            lines = [h('🎉 Ивенты'), f'Ивентов в системе: {len(rows)}', '', 'Выберите ивент для управления.']
            if not rows:
                lines.append('Список пуст.')
            await message.answer('\n'.join(lines), reply_markup=kb)
            return True
        if section == 'permissions':
            roles = (await session.scalars(select(BcRole).order_by(BcRole.key))).all()
            perms = (await session.scalars(select(BcPermission).order_by(BcPermission.code).limit(20))).all()
            rows: list[list[InlineKeyboardButton]] = [
                [InlineKeyboardButton(text='➕ Роль', callback_data='act:admin:role:create')],
                [InlineKeyboardButton(text='➕ Право', callback_data='act:admin:permission:create')],
                [InlineKeyboardButton(text='👤 Выдать/снять роль', callback_data='act:admin:role:grant:start')],
                [InlineKeyboardButton(text='🔗 Привязать/снять право', callback_data='act:admin:role:link_permission:start')],
            ]
            for role in roles[:8]:
                assigned = int(await session.scalar(select(func.count()).select_from(BcUserRole).where(BcUserRole.role_key == role.key)) or 0)
                rows.append([InlineKeyboardButton(text=f"👥 {role.title} ({assigned})", callback_data=f"nav:admin_role:{role.key}")])
            for perm in perms[:8]:
                linked = int(await session.scalar(select(func.count()).select_from(BcRolePermission).where(BcRolePermission.permission_code == perm.code)) or 0)
                rows.append([InlineKeyboardButton(text=f"🔐 {perm.code} ({linked})", callback_data=f"nav:admin_perm:{perm.code}")])
            rows.append([InlineKeyboardButton(text='🔙 Назад', callback_data='nav:admin')])
            kb = InlineKeyboardMarkup(inline_keyboard=rows)
            lines = [h('🔐 Права'), f'Ролей: {len(roles)}', f'Прав: {len(perms)}', '', 'Управляйте доступами из одного раздела.']
            await message.answer('\n'.join(lines), reply_markup=kb)
            return True
        if section == 'logs':
            rows = (await session.scalars(select(BcAuditLog).order_by(BcAuditLog.created_at.desc()).limit(15))).all()
            lines = [h('🧾 Логи'), 'Последние записи аудита:']
            if not rows:
                lines.append('• Логи пока пусты.')
            for log in rows:
                lines.append(f"• {log.action} | actor={log.actor_id} | {log.created_at.isoformat(timespec='minutes')}")
            await message.answer('\n'.join(lines), reply_markup=ik_admin_main())
            return True
        if section == 'bot_settings':
            service = BrawlCardsService(session)
            cooldowns = await service.get_system_section('cooldowns')
            rewards = await service.get_system_section('rewards')
            links = await service.get_system_section('bonus_links')
            button_labels = await service.get_system_section('button_labels')
            input_placeholders = await service.get_system_section('input_placeholders')
            main_menu_items = await service.get_system_section('main_menu_items')
            admin_menu_items = await service.get_system_section('admin_menu_items')
            feature_flags = await service.get_system_section('feature_flags')
            welcome_text = await service.get_template_text('screen.welcome', 'ru', DEFAULT_TEXT_TEMPLATES['screen.welcome'])
            help_text = await service.get_template_text('screen.help', 'ru', DEFAULT_TEXT_TEMPLATES['screen.help'])
            disabled_main = sorted(key for key, value in main_menu_items.items() if isinstance(value, dict) and not bool(value.get('visible', True)))
            disabled_admin = sorted(key for key, value in admin_menu_items.items() if isinstance(value, dict) and not bool(value.get('visible', True)))
            feature_off = sorted(key for key, value in feature_flags.items() if value is False)
            cooldown_lines = [f"• {cooldown_label(key)}: {int(value or 0)}с" for key, value in sorted(cooldowns.items())]
            lines = [
                h('⚙️ Настройки бота'),
                'Здесь меняются таймеры, награды, меню, feature flags, тексты и рабочие параметры бота.',
                '',
                '⏱ Кулдауны:',
                *cooldown_lines,
                '',
                '🎁 Награды:',
                f"• Bonus coins: {int(rewards.get('bonus_coins') or 0)}",
                f"• Bonus stars: {int(rewards.get('bonus_stars') or 0)}",
                f"• Market fee: {int(rewards.get('market_fee_percent') or 0)}%",
                '',
                '🔗 Bonus-ссылки:',
                f"• chat: {links.get('chat') or '-'}",
                f"• subscribe: {links.get('subscribe') or '-'}",
                f"• news: {links.get('news') or '-'}",
                f"• invite: {links.get('invite') or '-'}",
                f"• partner: {links.get('partner') or '-'}",
                '',
                '🔘 Кнопки:',
                f"• main.profile: {button_labels.get('main.profile') or DEFAULT_BUTTON_LABELS['main.profile']}",
                f"• main.shop: {button_labels.get('main.shop') or DEFAULT_BUTTON_LABELS['main.shop']}",
                f"• main.admin: {button_labels.get('main.admin') or DEFAULT_BUTTON_LABELS['main.admin']}",
                f"• common.back: {button_labels.get('common.back') or DEFAULT_BUTTON_LABELS['common.back']}",
                '',
                '⌨️ Placeholder:',
                f"• main_menu: {input_placeholders.get('main_menu') or DEFAULT_INPUT_PLACEHOLDERS['main_menu']}",
                '',
                '🧭 Главное меню:',
                f"• скрыто: {', '.join(disabled_main[:4]) if disabled_main else 'нет'}",
                '🛠 Админ-меню:',
                f"• скрыто: {', '.join(disabled_admin[:4]) if disabled_admin else 'нет'}",
                '🚦 Feature flags:',
                f"• выключено: {', '.join(feature_off[:5]) if feature_off else 'нет'}",
                '',
                '👋 Приветствие:',
                (welcome_text[:180] + '...') if len(welcome_text) > 180 else welcome_text,
                '',
                '🧭 Помощь:',
                (help_text[:180] + '...') if len(help_text) > 180 else help_text,
            ]
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text='⏱ Изменить кулдауны', callback_data='act:admin:sys:edit:cooldowns')],
                    [InlineKeyboardButton(text='🎁 Изменить награды', callback_data='act:admin:sys:edit:rewards')],
                    [InlineKeyboardButton(text='🔗 Изменить bonus-ссылки', callback_data='act:admin:sys:edit:bonus_links')],
                    [InlineKeyboardButton(text='🔘 Изменить подписи кнопок', callback_data='act:admin:sys:edit:button_labels')],
                    [InlineKeyboardButton(text='⌨️ Изменить placeholder', callback_data='act:admin:sys:edit:input_placeholders')],
                    [InlineKeyboardButton(text='🧭 Изменить главное меню', callback_data='act:admin:sys:edit:main_menu_items')],
                    [InlineKeyboardButton(text='🛠 Изменить admin-меню', callback_data='act:admin:sys:edit:admin_menu_items')],
                    [InlineKeyboardButton(text='🚦 Изменить feature flags', callback_data='act:admin:sys:edit:feature_flags')],
                    [InlineKeyboardButton(text='👋 Изменить приветствие', callback_data='act:admin:template:edit:screen.welcome')],
                    [InlineKeyboardButton(text='🧭 Изменить help-текст', callback_data='act:admin:template:edit:screen.help')],
                    [InlineKeyboardButton(text='🧾 Открыть шаблон по ключу', callback_data='act:admin:template:pick')],
                    [InlineKeyboardButton(text='📢 Рассылка', callback_data='nav:admin:broadcast')],
                    [InlineKeyboardButton(text='🔙 Назад', callback_data='nav:admin')],
                ]
            )
            await message.answer('\n'.join(lines), reply_markup=kb)
            return True
        if section == 'media':
            rows = (await session.scalars(select(BcMedia).order_by(BcMedia.created_at.desc()).limit(12))).all()
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text='➕ Добавить медиа', callback_data='act:admin:media:create')],
                    *[
                        [InlineKeyboardButton(text=f"🖼 #{media.id} {media.title or media.kind}", callback_data=f"nav:admin_media:{media.id}")]
                        for media in rows
                    ],
                    [InlineKeyboardButton(text='🔙 Назад', callback_data='nav:admin')],
                ]
            )
            lines = [h('🖼 Медиа'), f'Последних объектов: {len(rows)}', '', 'Откройте запись для правки URL, file_id и статуса.']
            await message.answer('\n'.join(lines), reply_markup=kb)
            return True
    return False


async def screen_admin_card(message: Message, card_id: int) -> None:
    if message.from_user is None or not is_admin_id(message.from_user.id):
        await message.answer('Доступ запрещён.', reply_markup=user_menu(message.from_user.id if message.from_user else None))
        return
    async with SessionLocal() as session:
        card = await session.get(BcCard, card_id)
        if card is None:
            await message.answer('Карточка не найдена.', reply_markup=user_menu(message.from_user.id))
            return
        rarity = await session.get(BcRarity, card.rarity_key)
        rarity_line = card.rarity_key
        if rarity is not None:
            rarity_line = f"{rarity.emoji} {rarity.title} ({rarity.key})"
        text = '\n'.join(
            [
                h('🃏 Карточка'),
                f"ID: {card.id}",
                f"Key: {card.key}",
                f"Название: {card.title}",
                f"Описание: {card.description or '—'}",
                f"Редкость: {rarity_line}",
                f"Серия: {card.series}",
                f"Очки: {card.base_points}",
                f"Монеты: {card.base_coins}",
                f"Вес внутри редкости: {card.drop_weight}",
                f"Лимитка: {'да' if card.is_limited else 'нет'}",
                f"Продажа: {'да' if card.is_sellable else 'нет'}",
                f"Активна: {'да' if card.is_active else 'нет'}",
                f"Сортировка: {card.sort}",
                f"Фото: {'есть' if card.image_file_id else 'нет'}",
            ]
        )
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text='✏️ Редактировать', callback_data=f'act:admin:card:edit:{card.id}'),
                    InlineKeyboardButton(text='🖼 Фото', callback_data=f'act:admin:card:photo:{card.id}'),
                ],
                [
                    InlineKeyboardButton(
                        text='🔴 Деактивировать' if card.is_active else '🟢 Активировать',
                        callback_data=f'act:admin:card:toggle_active:{card.id}',
                    ),
                    InlineKeyboardButton(
                        text='🚫 Убрать из продажи' if card.is_sellable else '💰 В продажу',
                        callback_data=f'act:admin:card:toggle_sell:{card.id}',
                    ),
                ],
                [
                    InlineKeyboardButton(text='📄 Дублировать', callback_data=f'act:admin:card:duplicate:{card.id}'),
                    InlineKeyboardButton(text='🗑 Удалить', callback_data=f'act:admin:card:delete:{card.id}'),
                ],
                [InlineKeyboardButton(text='🔙 К карточкам', callback_data='nav:admin:cards')],
            ]
        )
        if card.image_file_id:
            await message.answer_photo(card.image_file_id, caption=text, reply_markup=kb)
            return
        await message.answer(text, reply_markup=kb)


async def screen_admin_rarity(message: Message, rarity_key: str) -> None:
    if message.from_user is None or not is_admin_id(message.from_user.id):
        await message.answer('Доступ запрещён.', reply_markup=user_menu(message.from_user.id if message.from_user else None))
        return
    async with SessionLocal() as session:
        rarity = await session.get(BcRarity, rarity_key)
        if rarity is None:
            await message.answer('Редкость не найдена.', reply_markup=user_menu(message.from_user.id))
            return
        cards_count = int(await session.scalar(select(func.count()).select_from(BcCard).where(BcCard.rarity_key == rarity.key)) or 0)
    text = '\n'.join(
        [
            h('💎 Редкость'),
            f"Key: {rarity.key}",
            f"Название: {rarity.emoji} {rarity.title}",
            f"Шанс редкости: {rarity.chance}",
            f"Цвет: {rarity.color}",
            f"Множитель очков при выдаче: {rarity.points_mult}",
            f"Множитель монет при выдаче: {rarity.coins_mult}",
            f"Drop mode: {rarity.drop_mode}",
            f"В сундуках: {'да' if rarity.available_in_chests else 'нет'}",
            f"В магазине: {'да' if rarity.available_in_shop else 'нет'}",
            f"Активна: {'да' if rarity.is_active else 'нет'}",
            f"Карточек с этой редкостью: {cards_count}",
        ]
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='✏️ Редактировать', callback_data=f'act:admin:rarity:edit:{rarity.key}')],
            [InlineKeyboardButton(text='🗑 Удалить', callback_data=f'act:admin:rarity:delete:{rarity.key}')],
            [InlineKeyboardButton(text='🔙 К редкостям', callback_data='nav:admin:rarities')],
        ]
    )
    await message.answer(text, reply_markup=kb)


async def screen_admin_booster(message: Message, booster_key: str) -> None:
    if message.from_user is None or not is_admin_id(message.from_user.id):
        await message.answer('Доступ запрещён.', reply_markup=user_menu(message.from_user.id if message.from_user else None))
        return
    async with SessionLocal() as session:
        booster = await session.get(BcBooster, booster_key)
        if booster is None:
            await message.answer('Бустер не найден.', reply_markup=user_menu(message.from_user.id))
            return
        active_count = int(
            await session.scalar(select(func.count()).select_from(BcActiveBooster).where(BcActiveBooster.booster_key == booster.key))
            or 0
        )
    text = '\n'.join(
        [
            h('⚡ Бустер'),
            f"Key: {booster.key}",
            f"Название: {booster.emoji} {booster.title}",
            f"Эффект: {booster.effect_type}",
            f"Сила: {booster.effect_power}",
            f"Цена coins: {booster.price_coins if booster.price_coins is not None else '-'}",
            f"Цена stars: {booster.price_stars if booster.price_stars is not None else '-'}",
            f"Длительность: {booster.duration_seconds}с",
            f"Макс. stack: {booster.max_stack}",
            f"Доступен: {'да' if booster.is_available else 'нет'}",
            f"Активных у пользователей: {active_count}",
        ]
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='✏️ Редактировать', callback_data=f'act:admin:booster:edit:{booster.key}')],
            [InlineKeyboardButton(text='🗑 Удалить', callback_data=f'act:admin:booster:delete:{booster.key}')],
            [InlineKeyboardButton(text='🔙 К бустерам', callback_data='nav:admin:boosters')],
        ]
    )
    await message.answer(text, reply_markup=kb)


async def screen_admin_chest(message: Message, chest_key: str) -> None:
    if message.from_user is None or not is_admin_id(message.from_user.id):
        await message.answer('Доступ запрещён.', reply_markup=user_menu(message.from_user.id if message.from_user else None))
        return
    async with SessionLocal() as session:
        chest = await session.get(BcChest, chest_key)
        if chest is None:
            await message.answer('Сундук не найден.', reply_markup=user_menu(message.from_user.id))
            return
        drops = (
            await session.execute(
                select(BcChestDrop.rarity_key, BcChestDrop.weight, BcChestDrop.min_count, BcChestDrop.max_count)
                .where(BcChestDrop.chest_key == chest.key)
                .order_by(BcChestDrop.weight.desc(), BcChestDrop.rarity_key.asc())
            )
        ).all()
    lines = [
        h('📦 Сундук'),
        f"Key: {chest.key}",
        f"Название: {chest.emoji} {chest.title}",
        f"Описание: {chest.description or '—'}",
        f"Цена coins: {chest.price_coins if chest.price_coins is not None else '-'}",
        f"Цена stars: {chest.price_stars if chest.price_stars is not None else '-'}",
        f"Открытий за раз: {chest.open_count}",
        f"Активен: {'да' if chest.is_active else 'нет'}",
        '',
        'Дроп:',
    ]
    if not drops:
        lines.append('• Таблица дропа пуста.')
    for rarity_key_row, weight, min_count, max_count in drops:
        lines.append(f"• {rarity_key_row}: weight={weight}, count={min_count}-{max_count}")
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='✏️ Редактировать', callback_data=f'act:admin:chest:edit:{chest.key}')],
            [InlineKeyboardButton(text='🎯 Дроп-таблица', callback_data=f'act:admin:chest:drops:edit:{chest.key}')],
            [InlineKeyboardButton(text='🗑 Удалить', callback_data=f'act:admin:chest:delete:{chest.key}')],
            [InlineKeyboardButton(text='🔙 К сундукам', callback_data='nav:admin:chests')],
        ]
    )
    await message.answer('\n'.join(lines), reply_markup=kb)


async def screen_admin_rp_category(message: Message, category_key: str) -> None:
    if message.from_user is None or not is_admin_id(message.from_user.id):
        await message.answer('Доступ запрещён.', reply_markup=user_menu(message.from_user.id if message.from_user else None))
        return
    async with SessionLocal() as session:
        category = await session.get(BcRPCategory, category_key)
        if category is None:
            await message.answer('Категория не найдена.', reply_markup=user_menu(message.from_user.id))
            return
        actions_count = int(await session.scalar(select(func.count()).select_from(BcRPAction).where(BcRPAction.category_key == category.key)) or 0)
    text = '\n'.join(
        [
            h('🎭 RP-категория'),
            f"Key: {category.key}",
            f"Название: {category.emoji} {category.title}",
            f"Сортировка: {category.sort}",
            f"Активна: {'да' if category.is_active else 'нет'}",
            f"Действий внутри: {actions_count}",
        ]
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='✏️ Редактировать', callback_data=f'act:admin:rp_category:edit:{category.key}')],
            [InlineKeyboardButton(text='🗑 Удалить', callback_data=f'act:admin:rp_category:delete:{category.key}')],
            [InlineKeyboardButton(text='🔙 К RP', callback_data='nav:admin:rp')],
        ]
    )
    await message.answer(text, reply_markup=kb)


async def screen_admin_rp_action(message: Message, action_key: str) -> None:
    if message.from_user is None or not is_admin_id(message.from_user.id):
        await message.answer('Доступ запрещён.', reply_markup=user_menu(message.from_user.id if message.from_user else None))
        return
    async with SessionLocal() as session:
        rp_action = await session.get(BcRPAction, action_key)
        if rp_action is None:
            await message.answer('RP-действие не найдено.', reply_markup=user_menu(message.from_user.id))
            return
    reward = dict(rp_action.reward or {})
    scopes = dict(rp_action.allowed_scopes or {})
    templates = list(rp_action.templates or [])
    lines = [
        h('🎭 RP-действие'),
        f"Key: {rp_action.key}",
        f"Название: {rp_action.emoji} {rp_action.title}",
        f"Категория: {rp_action.category_key}",
        f"Нужна цель: {'да' if rp_action.requires_target else 'нет'}",
        f"Cooldown: {rp_action.cooldown_seconds}с",
        f"Награда: coins={int(reward.get('coins') or 0)}, stars={int(reward.get('stars') or 0)}, points={int(reward.get('points') or 0)}",
        f"Scopes: private={int(bool(scopes.get('private')))}, group={int(bool(scopes.get('group')))}",
        f"Активно: {'да' if rp_action.is_active else 'нет'}",
        f"Сортировка: {rp_action.sort}",
        '',
        'Шаблоны:',
    ]
    if not templates:
        lines.append('• Шаблоны не заданы.')
    for template in templates[:5]:
        lines.append(f"• {template}")
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='✏️ Редактировать', callback_data=f'act:admin:rp_action:edit:{rp_action.key}')],
            [InlineKeyboardButton(text='🗑 Удалить', callback_data=f'act:admin:rp_action:delete:{rp_action.key}')],
            [InlineKeyboardButton(text='🔙 К RP', callback_data='nav:admin:rp')],
        ]
    )
    await message.answer('\n'.join(lines), reply_markup=kb)


async def screen_admin_section(message: Message, section: str) -> None:
    await message.answer(
        f"{h('🛠 Админ-панель')}\nРаздел `{section}` не найден.",
        parse_mode='Markdown',
        reply_markup=ik_admin_main(),
    )


def admin_parse_bool(raw: str) -> bool:
    value = raw.strip().lower()
    if value in {'1', 'true', 'yes', 'y', 'on', 'да'}:
        return True
    if value in {'0', 'false', 'no', 'n', 'off', 'нет'}:
        return False
    raise ValueError('bool')


def admin_parse_optional_int(raw: str) -> int | None:
    value = raw.strip()
    if value in {'', '-'}:
        return None
    return int(value)


def admin_parse_optional_datetime(raw: str) -> datetime | None:
    value = raw.strip()
    if value in {'', '-'}:
        return None
    normalized = value.replace(' ', 'T')
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def admin_parse_chest_drops(raw: str) -> list[tuple[str, float, int, int]]:
    drops: list[tuple[str, float, int, int]] = []
    for chunk in [item.strip() for item in raw.split(',') if item.strip()]:
        rarity_key, encoded = [part.strip() for part in chunk.split('=', maxsplit=1)]
        parts = [part.strip() for part in encoded.split(':')]
        weight = float(parts[0])
        min_count = int(parts[1]) if len(parts) > 1 and parts[1] else 1
        max_count = int(parts[2]) if len(parts) > 2 and parts[2] else min_count
        if min_count <= 0 or max_count <= 0 or max_count < min_count:
            raise ValueError('drops')
        drops.append((rarity_key, weight, min_count, max_count))
    if not drops:
        raise ValueError('drops')
    return drops


def admin_build_shop_payload(payload_type: str, payload_ref: str, payload_value: str) -> dict[str, object]:
    payload_type = payload_type.strip()
    payload_ref = payload_ref.strip()
    payload_value = payload_value.strip()
    if payload_type == 'booster':
        return {'type': 'booster', 'booster_key': payload_ref, 'amount': int(payload_value or 1)}
    if payload_type == 'activate_booster':
        return {'type': 'activate_booster', 'booster_key': payload_ref, 'stacks': int(payload_value or 1)}
    if payload_type == 'premium':
        return {'type': 'premium', 'days': int(payload_ref or payload_value or 30)}
    if payload_type == 'currency_exchange':
        frm, to = [part.strip() for part in payload_ref.split(':', maxsplit=1)]
        return {'type': 'currency_exchange', 'from': frm, 'to': to, 'amount': int(payload_value or 0)}
    if payload_type == 'custom':
        return {'type': 'custom', 'ref': payload_ref, 'value': payload_value}
    raise ValueError('payload')


async def screen_admin_shop_category(message: Message, category_key: str) -> None:
    if message.from_user is None or not is_admin_id(message.from_user.id):
        await message.answer('Доступ запрещён.', reply_markup=user_menu(message.from_user.id if message.from_user else None))
        return
    async with SessionLocal() as session:
        category = await session.get(BcShopCategory, category_key)
        if category is None:
            await message.answer('Категория магазина не найдена.', reply_markup=user_menu(message.from_user.id))
            return
        items_count = int(
            await session.scalar(select(func.count()).select_from(BcShopItem).where(BcShopItem.category_key == category.key)) or 0
        )
    text = '\n'.join(
        [
            h('🛒 Категория магазина'),
            f"Key: {category.key}",
            f"Название: {category.emoji} {category.title}",
            f"Сортировка: {category.sort}",
            f"Активна: {'да' if category.is_active else 'нет'}",
            f"Товаров внутри: {items_count}",
        ]
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='➕ Товар в категорию', callback_data=f'act:admin:shop_item:create:{category.key}')],
            [InlineKeyboardButton(text='✏️ Редактировать', callback_data=f'act:admin:shop_category:edit:{category.key}')],
            [InlineKeyboardButton(text='🗑 Удалить', callback_data=f'act:admin:shop_category:delete:{category.key}')],
            [InlineKeyboardButton(text='🔙 К магазину', callback_data='nav:admin:shop')],
        ]
    )
    await message.answer(text, reply_markup=kb)


async def screen_admin_shop_item(message: Message, item_id: int) -> None:
    if message.from_user is None or not is_admin_id(message.from_user.id):
        await message.answer('Доступ запрещён.', reply_markup=user_menu(message.from_user.id if message.from_user else None))
        return
    async with SessionLocal() as session:
        item = await session.get(BcShopItem, item_id)
        if item is None:
            await message.answer('Товар не найден.', reply_markup=user_menu(message.from_user.id))
            return
    payload = dict(item.payload or {})
    text = '\n'.join(
        [
            h('🛍 Товар магазина'),
            f"ID: {item.id}",
            f"Категория: {item.category_key}",
            f"Key: {item.key}",
            f"Название: {item.title}",
            f"Описание: {item.description or '—'}",
            f"Цена coins: {item.price_coins if item.price_coins is not None else '-'}",
            f"Цена stars: {item.price_stars if item.price_stars is not None else '-'}",
            f"Длительность: {item.duration_seconds if item.duration_seconds is not None else '-'}",
            f"Payload: {payload}",
            f"Активен: {'да' if item.is_active else 'нет'}",
            f"Сортировка: {item.sort}",
        ]
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='✏️ Редактировать', callback_data=f'act:admin:shop_item:edit:{item.id}')],
            [InlineKeyboardButton(text='🔴 Отключить' if item.is_active else '🟢 Включить', callback_data=f'act:admin:shop_item:toggle:{item.id}')],
            [InlineKeyboardButton(text='🗑 Удалить', callback_data=f'act:admin:shop_item:delete:{item.id}')],
            [InlineKeyboardButton(text='🔙 К магазину', callback_data='nav:admin:shop')],
        ]
    )
    await message.answer(text, reply_markup=kb)


async def screen_admin_task(message: Message, task_key: str) -> None:
    if message.from_user is None or not is_admin_id(message.from_user.id):
        await message.answer('Доступ запрещён.', reply_markup=user_menu(message.from_user.id if message.from_user else None))
        return
    async with SessionLocal() as session:
        task = await session.get(BcTask, task_key)
        if task is None:
            await message.answer('Задание не найдено.', reply_markup=user_menu(message.from_user.id))
            return
        active_users = int(await session.scalar(select(func.count()).select_from(User)) or 0)
    reward = dict(task.reward or {})
    config = dict(task.config or {})
    text = '\n'.join(
        [
            h('📜 Задание'),
            f"Key: {task.key}",
            f"Тип: {task.kind}",
            f"Название: {task.title}",
            f"Описание: {task.description or '—'}",
            f"Цель: {task.target}",
            f"Counter: {config.get('counter') or '-'}",
            f"Награда: coins={int(reward.get('coins') or 0)}, stars={int(reward.get('stars') or 0)}, points={int(reward.get('points') or 0)}",
            f"Активно: {'да' if task.is_active else 'нет'}",
            f"Сортировка: {task.sort}",
            f"Пользователей в системе: {active_users}",
        ]
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='✏️ Редактировать', callback_data=f'act:admin:task:edit:{task.key}')],
            [InlineKeyboardButton(text='🗑 Удалить', callback_data=f'act:admin:task:delete:{task.key}')],
            [InlineKeyboardButton(text='🔙 К заданиям', callback_data='nav:admin:tasks')],
        ]
    )
    await message.answer(text, reply_markup=kb)


async def screen_admin_event(message: Message, event_key: str) -> None:
    if message.from_user is None or not is_admin_id(message.from_user.id):
        await message.answer('Доступ запрещён.', reply_markup=user_menu(message.from_user.id if message.from_user else None))
        return
    async with SessionLocal() as session:
        event = await session.scalar(select(BcEvent).where(BcEvent.key == event_key))
        if event is None:
            await message.answer('Ивент не найден.', reply_markup=user_menu(message.from_user.id))
            return
        cards_count = int(await session.scalar(select(func.count()).select_from(BcCard).where(BcCard.event_id == event.id)) or 0)
    starts_at = event.starts_at.isoformat(timespec='minutes') if event.starts_at else '-'
    ends_at = event.ends_at.isoformat(timespec='minutes') if event.ends_at else '-'
    text = '\n'.join(
        [
            h('🎉 Ивент'),
            f"Key: {event.key}",
            f"Название: {event.title}",
            f"Описание: {event.description or '—'}",
            f"Старт: {starts_at}",
            f"Финиш: {ends_at}",
            f"Активен: {'да' if event.is_active else 'нет'}",
            f"Карточек привязано: {cards_count}",
        ]
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='✏️ Редактировать', callback_data=f'act:admin:event:edit:{event.key}')],
            [InlineKeyboardButton(text='🗑 Удалить', callback_data=f'act:admin:event:delete:{event.key}')],
            [InlineKeyboardButton(text='🔙 К ивентам', callback_data='nav:admin:events')],
        ]
    )
    await message.answer(text, reply_markup=kb)


async def screen_admin_role(message: Message, role_key: str) -> None:
    if message.from_user is None or not is_admin_id(message.from_user.id):
        await message.answer('Доступ запрещён.', reply_markup=user_menu(message.from_user.id if message.from_user else None))
        return
    async with SessionLocal() as session:
        role = await session.get(BcRole, role_key)
        if role is None:
            await message.answer('Роль не найдена.', reply_markup=user_menu(message.from_user.id))
            return
        user_ids = (
            await session.scalars(select(BcUserRole.user_id).where(BcUserRole.role_key == role.key).order_by(BcUserRole.granted_at.desc()).limit(8))
        ).all()
        permission_codes = (
            await session.scalars(
                select(BcRolePermission.permission_code).where(BcRolePermission.role_key == role.key).order_by(BcRolePermission.permission_code)
            )
        ).all()
    lines = [
        h('🔐 Роль'),
        f"Key: {role.key}",
        f"Название: {role.title}",
        f"Пользователей: {len(user_ids)}",
        f"Права: {len(permission_codes)}",
        '',
        'Последние user_id:',
    ]
    if not user_ids:
        lines.append('• Никому не выдана.')
    for user_id in user_ids:
        lines.append(f"• {user_id}")
    lines.append('')
    lines.append('Привязанные права:')
    if not permission_codes:
        lines.append('• Пока пусто.')
    for code in permission_codes[:10]:
        lines.append(f"• {code}")
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='✏️ Редактировать', callback_data=f'act:admin:role:edit:{role.key}')],
            [InlineKeyboardButton(text='👤 Выдать/снять у пользователя', callback_data='act:admin:role:grant:start')],
            [InlineKeyboardButton(text='🔗 Привязать/снять право', callback_data='act:admin:role:link_permission:start')],
            [InlineKeyboardButton(text='🗑 Удалить', callback_data=f'act:admin:role:delete:{role.key}')],
            [InlineKeyboardButton(text='🔙 К ролям и правам', callback_data='nav:admin:permissions')],
        ]
    )
    await message.answer('\n'.join(lines), reply_markup=kb)


async def screen_admin_permission(message: Message, permission_code: str) -> None:
    if message.from_user is None or not is_admin_id(message.from_user.id):
        await message.answer('Доступ запрещён.', reply_markup=user_menu(message.from_user.id if message.from_user else None))
        return
    async with SessionLocal() as session:
        permission = await session.get(BcPermission, permission_code)
        if permission is None:
            await message.answer('Право не найдено.', reply_markup=user_menu(message.from_user.id))
            return
        role_keys = (
            await session.scalars(
                select(BcRolePermission.role_key).where(BcRolePermission.permission_code == permission.code).order_by(BcRolePermission.role_key)
            )
        ).all()
    lines = [
        h('🔐 Право'),
        f"Code: {permission.code}",
        f"Название: {permission.title}",
        f"Ролей с доступом: {len(role_keys)}",
        '',
        'Роли:',
    ]
    if not role_keys:
        lines.append('• Ни одна роль не связана.')
    for role_key in role_keys[:12]:
        lines.append(f"• {role_key}")
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='✏️ Редактировать', callback_data=f'act:admin:permission:edit:{permission.code}')],
            [InlineKeyboardButton(text='🗑 Удалить', callback_data=f'act:admin:permission:delete:{permission.code}')],
            [InlineKeyboardButton(text='🔙 К ролям и правам', callback_data='nav:admin:permissions')],
        ]
    )
    await message.answer('\n'.join(lines), reply_markup=kb)


async def screen_admin_media(message: Message, media_id: int) -> None:
    if message.from_user is None or not is_admin_id(message.from_user.id):
        await message.answer('Доступ запрещён.', reply_markup=user_menu(message.from_user.id if message.from_user else None))
        return
    async with SessionLocal() as session:
        media = await session.get(BcMedia, media_id)
        if media is None:
            await message.answer('Медиа не найдено.', reply_markup=user_menu(message.from_user.id))
            return
    text = '\n'.join(
        [
            h('🖼 Медиа'),
            f"ID: {media.id}",
            f"Тип: {media.kind}",
            f"Название: {media.title or '—'}",
            f"File ID: {media.telegram_file_id or '-'}",
            f"URL: {media.url or '-'}",
            f"Активно: {'да' if media.is_active else 'нет'}",
            f"Meta: {dict(media.meta or {})}",
        ]
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='✏️ Редактировать', callback_data=f'act:admin:media:edit:{media.id}')],
            [InlineKeyboardButton(text='🖼 Загрузить файл', callback_data=f'act:admin:media:file:{media.id}')],
            [InlineKeyboardButton(text='🗑 Удалить', callback_data=f'act:admin:media:delete:{media.id}')],
            [InlineKeyboardButton(text='🔙 К медиа', callback_data='nav:admin:media')],
        ]
    )
    await message.answer(text, reply_markup=kb)


async def render_inventory_screen(message: Message) -> None:
    if message.from_user is None:
        return
    async with SessionLocal() as session:
        rows = (await session.execute(select(BcBooster.title, BcActiveBooster.stacks, BcActiveBooster.active_until).join(BcActiveBooster, BcActiveBooster.booster_key == BcBooster.key).where(BcActiveBooster.user_id == message.from_user.id).order_by(BcBooster.key))).all()
    if not rows:
        await message.answer(f"{h('\u26a1 \u0410\u043a\u0442\u0438\u0432\u043d\u044b\u0435 \u0431\u0443\u0441\u0442\u0435\u0440\u044b')}\n\u0410\u043a\u0442\u0438\u0432\u043d\u044b\u0445 \u0431\u0443\u0441\u0442\u0435\u0440\u043e\u0432 \u043f\u043e\u043a\u0430 \u043d\u0435\u0442.", reply_markup=ik_profile())
        return
    lines = [h('\u26a1 \u0410\u043a\u0442\u0438\u0432\u043d\u044b\u0435 \u0431\u0443\u0441\u0442\u0435\u0440\u044b'), '\u0417\u0434\u0435\u0441\u044c \u043f\u043e\u043a\u0430\u0437\u0430\u043d\u044b \u0432\u0430\u0448\u0438 \u0430\u043a\u0442\u0438\u0432\u043d\u044b\u0435 \u0431\u0443\u0441\u0442\u0435\u0440\u044b:']
    for title, stacks, active_until in rows:
        until = active_until.isoformat(timespec='minutes') if active_until else '\u0431\u0435\u0437 \u0442\u0430\u0439\u043c\u0435\u0440\u0430'
        lines.append(f"\u2022 {title} x{stacks} | {until}")
    await message.answer('\n'.join(lines), reply_markup=ik_profile())


async def render_profile_stats_screen(message: Message) -> None:
    if message.from_user is None:
        return
    async with SessionLocal() as session:
        user = await session.get(User, message.from_user.id)
        profile = await session.get(UserProfile, message.from_user.id)
        if user is None or profile is None:
            await message.answer(f"{h('\U0001f4c8 \u0421\u0442\u0430\u0442\u0438\u0441\u0442\u0438\u043a\u0430')}\n\u041f\u0440\u043e\u0444\u0438\u043b\u044c \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d.", reply_markup=ik_profile())
            return
        total_cards = await session.scalar(select(func.count()).select_from(BcCardInstance).where(BcCardInstance.user_id == user.id))
        unique_cards = await session.scalar(select(func.count(func.distinct(BcCardInstance.card_id))).where(BcCardInstance.user_id == user.id))
    text = (
        f"{h('\U0001f4c8 \u0421\u0442\u0430\u0442\u0438\u0441\u0442\u0438\u043a\u0430')}\n"
        f"\u041e\u0447\u043a\u0438: {user.total_points}\n"
        f"\u041c\u043e\u043d\u0435\u0442\u044b: {user.coins}\n"
        f"\u0417\u0432\u0451\u0437\u0434\u044b: {user.stars}\n"
        f"\u0412\u0441\u0435\u0433\u043e \u043a\u0430\u0440\u0442: {int(total_cards or 0)}\n"
        f"\u0423\u043d\u0438\u043a\u0430\u043b\u044c\u043d\u044b\u0445 \u043a\u0430\u0440\u0442: {int(unique_cards or 0)}\n"
        f"\u0418\u0433\u0440 \u0441\u044b\u0433\u0440\u0430\u043d\u043e: {profile.games_played}\n"
        f"\u041f\u043e\u0431\u0435\u0434: {profile.games_won}\n"
        f"\u041f\u0440\u043e\u0434\u0430\u043d\u043e \u043d\u0430 \u043c\u0430\u0440\u043a\u0435\u0442\u0435: {profile.market_sold}\n"
        f"\u041a\u0443\u043f\u043b\u0435\u043d\u043e \u043d\u0430 \u043c\u0430\u0440\u043a\u0435\u0442\u0435: {profile.market_bought}\n"
        f"\u0417\u0430\u0434\u0430\u043d\u0438\u0439 \u0432\u044b\u043f\u043e\u043b\u043d\u0435\u043d\u043e: {profile.tasks_done}"
    )
    await message.answer(text, reply_markup=ik_profile())


async def render_my_cards_screen(message: Message) -> None:
    if message.from_user is None:
        return
    async with SessionLocal() as session:
        rows = (await session.execute(select(BcCard.title, BcRarity.title, func.count(BcCardInstance.id)).join(BcCard, BcCard.id == BcCardInstance.card_id).join(BcRarity, BcRarity.key == BcCard.rarity_key).where(BcCardInstance.user_id == message.from_user.id).group_by(BcCard.title, BcRarity.title).order_by(func.count(BcCardInstance.id).desc(), BcCard.title.asc()).limit(20))).all()
    if not rows:
        await message.answer(f"{h('🖼 Мои карточки')}\nКоллекция пока пуста.", reply_markup=ik_profile())
        return
    lines = [h('🖼 Мои карточки'), 'Первые 20 карточек коллекции:']
    for title, rarity_title, count in rows:
        lines.append(f"• {title} | {rarity_title} | x{int(count)}")
    await message.answer('\n'.join(lines), reply_markup=ik_profile())

async def render_economy_screen(message: Message) -> None:
    if message.from_user is None:
        return
    async with SessionLocal() as session:
        service = BrawlCardsService(session)
        overview = await service.economy_overview(message.from_user.id)
    premium_until = overview["premium_until"]
    premium_text = premium_until.isoformat(timespec="minutes") if premium_until else "не активен"
    lines = [
        h("💼 Экономика"),
        "Здесь собрана сводка по валютам, карточкам, бустерам и активным кулдаунам.",
        "",
        f"🪙 Монеты: {overview['coins']}",
        f"⭐ Звёзды: {overview['stars']}",
        f"✨ Очки: {overview['points']}",
        f"🏅 Уровень: {overview['level']}",
        f"🃏 Карты: {overview['cards_total']} / уникальных {overview['cards_unique']}",
        f"⚡ Активные бустеры: {overview['boosters_active']}",
        f"🕒 Кулдаун карты: {seconds_to_hms(int(overview['card_cooldown']))}",
        f"🎁 Кулдаун бонуса: {seconds_to_hms(int(overview['bonus_cooldown']))}",
        f"💎 Premium: {premium_text}",
    ]
    await message.answer(
        "\n".join(lines),
        reply_markup=ik_list_nav([("shop", "🛒 В магазин"), ("premium", "💎 Premium"), ("top", "🏆 В топ")], prefix="nav", back_to="profile"),
    )


async def screen_shop_offers(message: Message) -> None:
    async with SessionLocal() as session:
        service = BrawlCardsService(session)
        items = await service.shop_offers(8)
    if not items:
        await message.answer(f"{h('🔥 Офферы')}\nПока нет активных предложений.", reply_markup=ik_shop_categories())
        return
    lines = [h("🔥 Офферы"), "Здесь собраны актуальные предложения, которые можно купить прямо сейчас:"]
    buttons: list[tuple[str, str]] = []
    for item in items:
        price_parts: list[str] = []
        if item.price_coins is not None:
            price_parts.append(f"{item.price_coins}🪙")
        if item.price_stars is not None:
            price_parts.append(f"{item.price_stars}⭐")
        price_text = " / ".join(price_parts) if price_parts else "бесплатно"
        lines.append(f"• {item.title} - {price_text}")
        buttons.append((item.key, item.title[:32]))
    await message.answer("\n".join(lines), reply_markup=ik_list_nav(buttons, prefix="nav:shop_item", back_to="shop"))


async def screen_events(message: Message) -> None:
    async with SessionLocal() as session:
        service = BrawlCardsService(session)
        events = await service.active_events()
        body = await template_text(session, message.from_user.id if message.from_user else None, 'screen.events', DEFAULT_TEXT_TEMPLATES['screen.events'])
    if not events:
        await message.answer(f"{h('🎉 Ивенты')}\nСейчас активных событий нет.", reply_markup=ik_shop_categories())
        return
    lines = [h("🎉 Ивенты"), body, "", f"Активных событий: {len(events)}", ""]
    for event in events[:10]:
        ends = event.ends_at.isoformat(timespec="minutes") if event.ends_at else "без срока"
        lines.append(f"• {event.title}\n{event.description[:120]}\nДо: {ends}")
    await message.answer(
        "\n".join(lines),
        reply_markup=ik_list_nav([("shop", "🛒 Магазин"), ("tasks", "📜 Задания"), ("bonus", "🎁 Бонус")], prefix="nav", back_to="main"),
    )


async def show_screen(message: Message, screen: str) -> None:
    is_admin = is_admin_id(message.from_user.id if message.from_user else 0)
    chat_type = chat_type_of(message)
    if screen != 'main' and (not feature_flag_enabled(screen, True) or not screen_visible_in_menu(screen, include_admin=is_admin)):
        await message.answer(
            f"{h('⛔ Раздел выключен')}\nЭтот раздел сейчас отключён в настройках бота.",
            reply_markup=user_menu(message.from_user.id if message.from_user else None, chat_type),
        )
        return
    if chat_type != 'private' and screen in PRIVATE_CHAT_SCREENS:
        await message.answer(
            f"{h('💬 Чатовый режим')}\nЭтот экран лучше открывать в личке. В чате оставлены быстрые действия: карта, бонусы, топы, RP и игры.",
            reply_markup=ik_nav('main'),
        )
        return
    if screen == 'main':
        await screen_main(message)
    elif screen == 'profile':
        await screen_profile(message)
    elif screen == 'inventory':
        await render_inventory_screen(message)
    elif screen == 'stats':
        await render_profile_stats_screen(message)
    elif screen == 'economy':
        await render_economy_screen(message)
    elif screen == 'my_cards':
        await render_my_cards_screen(message)
    elif screen == 'nick':
        await screen_nick(message)
    elif screen == 'get_card':
        await screen_get_card(message)
    elif screen == 'bonus':
        await screen_bonus(message)
    elif screen == 'top':
        await screen_top(message)
    elif screen == 'shop':
        await screen_shop(message)
    elif screen == 'shop_offers':
        await screen_shop_offers(message)
    elif screen == 'events':
        await screen_events(message)
    elif screen == 'chest':
        await screen_chest(message)
    elif screen == 'premium':
        await screen_premium(message)
    elif screen == 'tasks':
        await screen_tasks(message)
    elif screen == 'rp':
        await screen_rp(message)
    elif screen == 'quote':
        await screen_quote(message)
    elif screen == 'sticker':
        await screen_sticker(message)
    elif screen == 'games':
        await screen_games(message)
    elif screen == 'market':
        await screen_market(message)
    elif screen == 'marriage':
        await screen_marriage(message)
    elif screen == 'settings':
        await render_settings_screen(message)
    elif screen == 'admin':
        await screen_admin(message)
    else:
        await screen_main(message)


CARD_WIZARD_STEPS: dict[str, list[str]] = {
    'create': ['key', 'title', 'description', 'rarity_key', 'series', 'points', 'coins', 'drop_weight', 'is_limited', 'is_sellable', 'is_active', 'sort', 'photo'],
    'edit': ['title', 'description', 'rarity_key', 'series', 'points', 'coins', 'drop_weight', 'is_limited', 'is_sellable', 'is_active', 'sort', 'photo'],
}

CARD_WIZARD_DEFAULTS: dict[str, object] = {
    'series': 'Core',
    'points': 0,
    'coins': 0,
    'drop_weight': 1,
    'is_limited': 0,
    'is_sellable': 1,
    'is_active': 1,
    'sort': 100,
    'photo': '',
}


async def resolve_rarity_key(session, raw: str) -> str | None:
    value = raw.strip()
    if not value:
        return None
    rarity = await session.get(BcRarity, value)
    if rarity is not None:
        return rarity.key
    rows = (await session.scalars(select(BcRarity).where(func.lower(BcRarity.title) == value.lower()))).all()
    if rows:
        return rows[0].key
    return None


async def card_rarity_hint(session) -> str:
    rows = (await session.scalars(select(BcRarity).order_by(BcRarity.sort, BcRarity.key))).all()
    if not rows:
        return '\u0420\u0435\u0434\u043a\u043e\u0441\u0442\u0438 \u0435\u0449\u0451 \u043d\u0435 \u0441\u043e\u0437\u0434\u0430\u043d\u044b.'
    parts = [f"`{row.key}` ({row.emoji} {row.title})" for row in rows]
    return '\u0414\u043e\u0441\u0442\u0443\u043f\u043d\u044b\u0435 \u0440\u0435\u0434\u043a\u043e\u0441\u0442\u0438: ' + ', '.join(parts)


async def admin_card_wizard_markup(session, step: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if step == 'rarity_key':
        rarities = (await session.scalars(select(BcRarity).order_by(BcRarity.sort, BcRarity.key))).all()
        pair: list[InlineKeyboardButton] = []
        for rarity in rarities[:12]:
            pair.append(
                InlineKeyboardButton(
                    text=f"{rarity.emoji} {rarity.title}",
                    callback_data=f"act:admin:card:wizard:value:{rarity.key}",
                )
            )
            if len(pair) == 2:
                rows.append(pair)
                pair = []
        if pair:
            rows.append(pair)
    if step in {'is_limited', 'is_sellable', 'is_active'}:
        rows.append(
            [
                InlineKeyboardButton(text='✅ Да', callback_data='act:admin:card:wizard:value:1'),
                InlineKeyboardButton(text='❌ Нет', callback_data='act:admin:card:wizard:value:0'),
            ]
        )
    if step == 'photo':
        rows.append([InlineKeyboardButton(text='⏭ Пропустить фото', callback_data='act:admin:card:wizard:skip_photo')])
    rows.append([InlineKeyboardButton(text='❌ Отменить', callback_data='act:admin:card:wizard:cancel')])
    rows.append([InlineKeyboardButton(text='🔙 К карточкам', callback_data='nav:admin:cards')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def card_wizard_prompt(mode: str, step: str, data: dict) -> str:
    title = '\u2795 \u0414\u043e\u0431\u0430\u0432\u043b\u0435\u043d\u0438\u0435 \u043a\u0430\u0440\u0442\u043e\u0447\u043a\u0438' if mode == 'create' else '\u270f\ufe0f \u0420\u0435\u0434\u0430\u043a\u0442\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435 \u043a\u0430\u0440\u0442\u043e\u0447\u043a\u0438'
    labels = {
        'key': 'key \u043a\u0430\u0440\u0442\u043e\u0447\u043a\u0438',
        'title': '\u043d\u0430\u0437\u0432\u0430\u043d\u0438\u0435 \u043a\u0430\u0440\u0442\u043e\u0447\u043a\u0438',
        'description': '\u043e\u043f\u0438\u0441\u0430\u043d\u0438\u0435 \u043a\u0430\u0440\u0442\u043e\u0447\u043a\u0438',
        'rarity_key': '\u0440\u0435\u0434\u043a\u043e\u0441\u0442\u044c \u043a\u0430\u0440\u0442\u043e\u0447\u043a\u0438',
        'series': '\u0441\u0435\u0440\u0438\u044e \u043a\u0430\u0440\u0442\u043e\u0447\u043a\u0438',
        'points': '\u043e\u0447\u043a\u0438 \u0437\u0430 \u043a\u0430\u0440\u0442\u043e\u0447\u043a\u0443',
        'coins': '\u043c\u043e\u043d\u0435\u0442\u044b \u0437\u0430 \u043a\u0430\u0440\u0442\u043e\u0447\u043a\u0443',
        'drop_weight': '\u0432\u0435\u0441 \u043a\u0430\u0440\u0442\u044b \u0432\u043d\u0443\u0442\u0440\u0438 \u0440\u0435\u0434\u043a\u043e\u0441\u0442\u0438',
        'is_limited': '\u043b\u0438\u043c\u0438\u0442\u0438\u0440\u043e\u0432\u0430\u043d\u043d\u043e\u0441\u0442\u044c',
        'is_sellable': '\u0434\u043e\u0441\u0442\u0443\u043f\u043d\u043e\u0441\u0442\u044c \u043f\u0440\u043e\u0434\u0430\u0436\u0438',
        'is_active': '\u0430\u043a\u0442\u0438\u0432\u043d\u043e\u0441\u0442\u044c \u043a\u0430\u0440\u0442\u043e\u0447\u043a\u0438',
        'sort': '\u0441\u043e\u0440\u0442\u0438\u0440\u043e\u0432\u043a\u0443',
        'photo': '\u0444\u043e\u0442\u043e \u043a\u0430\u0440\u0442\u043e\u0447\u043a\u0438',
    }
    hints = {
        'key': '\u041f\u0440\u0438\u043c\u0435\u0440: `rustblade`',
        'title': '\u041f\u0440\u0438\u043c\u0435\u0440: `Rustblade`',
        'description': '\u041a\u043e\u0440\u043e\u0442\u043a\u043e\u0435 \u043e\u043f\u0438\u0441\u0430\u043d\u0438\u0435 \u043a\u0430\u0440\u0442\u043e\u0447\u043a\u0438.',
        'rarity_key': '\u0423\u043a\u0430\u0436\u0438\u0442\u0435 `key` \u0440\u0435\u0434\u043a\u043e\u0441\u0442\u0438.',
        'series': '\u041f\u0440\u0438\u043c\u0435\u0440: `Core`',
        'points': '\u0426\u0435\u043b\u043e\u0435 \u0447\u0438\u0441\u043b\u043e.',
        'coins': '\u0426\u0435\u043b\u043e\u0435 \u0447\u0438\u0441\u043b\u043e.',
        'drop_weight': '\u0427\u0438\u0441\u043b\u043e \u0432\u0435\u0441\u0430: `1` \u0438\u043b\u0438 `0.35`. \u042d\u0442\u043e \u043d\u0435 \u0448\u0430\u043d\u0441 \u0440\u0435\u0434\u043a\u043e\u0441\u0442\u0438.',
        'is_limited': '\u041d\u0430\u043f\u0438\u0448\u0438\u0442\u0435 `1`/`0` \u0438\u043b\u0438 `\u0434\u0430`/`\u043d\u0435\u0442`.',
        'is_sellable': '\u041d\u0430\u043f\u0438\u0448\u0438\u0442\u0435 `1`/`0` \u0438\u043b\u0438 `\u0434\u0430`/`\u043d\u0435\u0442`.',
        'is_active': '\u041d\u0430\u043f\u0438\u0448\u0438\u0442\u0435 `1`/`0` \u0438\u043b\u0438 `\u0434\u0430`/`\u043d\u0435\u0442`.',
        'sort': '\u0426\u0435\u043b\u043e\u0435 \u0447\u0438\u0441\u043b\u043e. \u041e\u0431\u044b\u0447\u043d\u043e `100`.',
        'photo': '\u041e\u0442\u043f\u0440\u0430\u0432\u044c\u0442\u0435 \u0444\u043e\u0442\u043e \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435\u043c \u0438\u043b\u0438 `-`, \u0447\u0442\u043e\u0431\u044b \u043f\u0440\u043e\u043f\u0443\u0441\u0442\u0438\u0442\u044c.',
    }
    steps = CARD_WIZARD_STEPS.get(mode, CARD_WIZARD_STEPS['create'])
    index = steps.index(step) + 1
    total = len(steps)
    current_value = data.get(step)
    current_line = ''
    if current_value not in (None, ''):
        current_line = f"\n\u0422\u0435\u043a\u0443\u0449\u0435\u0435 \u0437\u043d\u0430\u0447\u0435\u043d\u0438\u0435: `{current_value}`"
    summary_fields = (
        ('key', 'key'),
        ('title', 'название'),
        ('rarity_key', 'редкость'),
        ('series', 'серия'),
        ('points', 'очки'),
        ('coins', 'монеты'),
        ('drop_weight', 'вес'),
    )
    summary_lines = [f"• {label}: `{data[field]}`" for field, label in summary_fields if data.get(field) not in (None, '')]
    summary = f"\n\nУже заполнено:\n" + "\n".join(summary_lines) if summary_lines else ""
    return (
        f"{h(title)}\n"
        f"\u0428\u0430\u0433 {index}/{total}.\n"
        f"\u0412\u0432\u0435\u0434\u0438\u0442\u0435 {labels.get(step, step)}.\n"
        f"{hints.get(step, '')}{current_line}{summary}"
    )


async def save_card_wizard_payload(session, service: BrawlCardsService, user_id: int, payload: dict) -> tuple[bool, str, int | None]:
    mode = str(payload.get('mode') or 'create')
    data = dict(payload.get('data') or {})

    key = str(data.get('key') or '').strip().lower().replace(' ', '_')
    title = str(data.get('title') or '').strip()
    description = str(data.get('description') or '').strip()
    rarity_key = str(data.get('rarity_key') or '').strip()
    series = str(data.get('series') or 'Core').strip() or 'Core'
    photo = str(data.get('photo') or '').strip() or None

    if mode == 'create' and not key:
        return (False, '\u041d\u0443\u0436\u0435\u043d key \u043a\u0430\u0440\u0442\u043e\u0447\u043a\u0438.', None)
    if not title:
        return (False, '\u041e\u043f\u0438\u0441\u0430\u043d\u0438\u0435 \u043a\u0430\u0440\u0442\u043e\u0447\u043a\u0438 \u043e\u0431\u044f\u0437\u0430\u0442\u0435\u043b\u044c\u043d\u043e.', None)
    if not description:
        return (False, '\u041e\u043f\u0438\u0441\u0430\u043d\u0438\u0435 \u043a\u0430\u0440\u0442\u043e\u0447\u043a\u0438 \u043e\u0431\u044f\u0437\u0430\u0442\u0435\u043b\u044c\u043d\u043e.', None)
    if not rarity_key or await session.get(BcRarity, rarity_key) is None:
        return (False, '\u041a\u0430\u0440\u0442\u043e\u0447\u043a\u0430 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u0430.', None)

    try:
        points = int(data.get('points') or 0)
        coins = int(data.get('coins') or 0)
        drop_weight = float(data.get('drop_weight') or 1)
        is_limited = bool(int(data.get('is_limited') or 0))
        is_sellable = bool(int(data.get('is_sellable') or 0))
        is_active = bool(int(data.get('is_active') or 0))
        sort = int(data.get('sort') or 100)
    except (TypeError, ValueError):
        return (False, '\u041e\u0434\u043d\u0430 \u0438\u0437 \u043d\u0430\u0441\u0442\u0440\u043e\u0435\u043a \u043a\u0430\u0440\u0442\u043e\u0447\u043a\u0438 \u0437\u0430\u043f\u043e\u043b\u043d\u0435\u043d\u0430 \u043d\u0435\u0432\u0435\u0440\u043d\u043e.', None)

    if mode == 'create':
        if await session.scalar(select(BcCard.id).where(BcCard.key == key)) is not None:
            return (False, '\u041a\u0430\u0440\u0442\u043e\u0447\u043a\u0430 \u0441 \u0442\u0430\u043a\u0438\u043c key \u0443\u0436\u0435 \u0441\u0443\u0449\u0435\u0441\u0442\u0432\u0443\u0435\u0442.', None)
        card = BcCard(
            key=key,
            title=title,
            description=description,
            rarity_key=rarity_key,
            series=series,
            tags=[],
            base_points=points,
            base_coins=coins,
            drop_weight=drop_weight,
            is_limited=is_limited,
            limited_series_id=None,
            event_id=None,
            image_file_id=photo,
            image_url=None,
            media_id=None,
            is_sellable=is_sellable,
            is_active=is_active,
            sort=sort,
            meta={},
        )
        session.add(card)
        await session.flush()
        await service.clear_input_state(user_id)
        return (True, '\u041a\u0430\u0440\u0442\u043e\u0447\u043a\u0430 \u0441\u043e\u0437\u0434\u0430\u043d\u0430.', card.id)

    card_id = int(payload.get('id') or 0)
    card = await session.get(BcCard, card_id)
    if card is None:
        return (False, '\u041a\u0430\u0440\u0442\u043e\u0447\u043a\u0430 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u0430.', None)

    card.title = title
    card.description = description
    card.rarity_key = rarity_key
    card.series = series
    card.base_points = points
    card.base_coins = coins
    card.drop_weight = drop_weight
    card.is_limited = is_limited
    card.is_sellable = is_sellable
    card.is_active = is_active
    card.sort = sort
    if photo is not None:
        card.image_file_id = photo or None
    await session.flush()
    await service.clear_input_state(user_id)
    return (True, '\u041a\u0430\u0440\u0442\u043e\u0447\u043a\u0430 \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0430.', card.id)


async def consume_admin_card_wizard_input(session, service: BrawlCardsService, user_id: int, raw: str) -> dict:
    state = await service.get_input_state(user_id)
    if state is None or state.state != 'admin_card_wizard':
        return {'done': True, 'text': 'Конструктор карточки не активен.', 'reply_markup': main_menu()}

    payload = dict(state.payload or {})
    mode = str(payload.get('mode') or 'create')
    step = str(payload.get('step') or '')
    data = dict(payload.get('data') or {})
    steps = CARD_WIZARD_STEPS.get(mode, CARD_WIZARD_STEPS['create'])

    if raw.lower() in {'отмена', 'cancel', '/cancel'}:
        await service.clear_input_state(user_id)
        return {'done': True, 'text': f"{h('🃏 Конструктор карточки')}\nСоздание или редактирование карточки отменено.", 'reply_markup': main_menu()}

    if not step or step not in steps:
        return {'done': True, 'text': 'Состояние конструктора карточки повреждено.', 'reply_markup': main_menu()}

    if mode == 'edit' and raw == '-' and step != 'photo':
        value = data.get(step)
    elif mode == 'create' and raw == '-' and step in CARD_WIZARD_DEFAULTS:
        value = CARD_WIZARD_DEFAULTS[step]
    else:
        if step == 'key':
            value = raw.lower().replace(' ', '_')
            if not value:
                return {'done': True, 'text': 'Нужен key карточки.', 'reply_markup': await admin_card_wizard_markup(session, step)}
        elif step in {'title', 'description', 'series'}:
            value = raw
            if step in {'title', 'description'} and not value:
                return {'done': True, 'text': 'Это поле обязательно.', 'reply_markup': await admin_card_wizard_markup(session, step)}
        elif step == 'rarity_key':
            resolved = await resolve_rarity_key(session, raw)
            if resolved is None:
                hint = await card_rarity_hint(session)
                return {'done': True, 'text': f"Редкость не найдена.\n\n{hint}", 'reply_markup': await admin_card_wizard_markup(session, step), 'parse_mode': 'Markdown'}
            value = resolved
        elif step in {'points', 'coins', 'sort'}:
            try:
                value = int(raw)
            except ValueError:
                return {'done': True, 'text': 'Нужно целое число.', 'reply_markup': await admin_card_wizard_markup(session, step)}
        elif step == 'drop_weight':
            try:
                value = float(raw)
            except ValueError:
                return {'done': True, 'text': 'Нужно число. Пример: `1` или `0.35`.', 'reply_markup': await admin_card_wizard_markup(session, step), 'parse_mode': 'Markdown'}
        elif step in {'is_limited', 'is_sellable', 'is_active'}:
            normalized = raw.lower()
            if normalized not in {'0', '1', 'да', 'нет'}:
                return {'done': True, 'text': 'Нужно `1/0` или `да/нет`.', 'reply_markup': await admin_card_wizard_markup(session, step), 'parse_mode': 'Markdown'}
            value = 1 if normalized in {'1', 'да'} else 0
        elif step == 'photo':
            if raw != '-':
                return {'done': True, 'text': 'На этом шаге отправьте фото или `-`.', 'reply_markup': await admin_card_wizard_markup(session, step), 'parse_mode': 'Markdown'}
            value = data.get('photo') or ''
        else:
            value = raw

    if step == 'photo':
        data['photo'] = value
        payload['data'] = data
        ok, resp, card_id = await save_card_wizard_payload(session, service, user_id, payload)
        return {'done': True, 'text': resp, 'reply_markup': main_menu(), 'card_id': card_id if ok else None}

    data[step] = value
    next_index = steps.index(step) + 1
    next_step = steps[next_index]
    await service.set_input_state(user_id, 'admin_card_wizard', {'mode': mode, 'id': payload.get('id'), 'step': next_step, 'data': data})
    extra = ''
    if next_step == 'rarity_key':
        extra = f"\n\n{await card_rarity_hint(session)}"
    if mode == 'create' and next_step in CARD_WIZARD_DEFAULTS:
        extra += "\n\nМожно отправить `-`, чтобы взять значение по умолчанию."
    return {
        'done': False,
        'text': f"{card_wizard_prompt(mode, next_step, data)}{extra}",
        'reply_markup': await admin_card_wizard_markup(session, next_step),
        'parse_mode': 'Markdown',
    }

@router.message(CommandStart())
async def on_start(message: Message) -> None:
    await handle_start_command(message)

@router.message(Command(commands=['help', 'menu']))
async def on_help(message: Message) -> None:
    await render_help_screen(message)


@router.message(Command(commands=['admin']))
async def on_admin_command(message: Message) -> None:
    await ensure_user(message)
    await show_screen(message, 'admin')

@router.message(Command(commands=['profile']))
async def on_profile_command(message: Message) -> None:
    await ensure_user(message)
    await show_screen(message, 'profile')

@router.message(Command(commands=['card']))
async def on_card_command(message: Message) -> None:
    await ensure_user(message)
    await show_screen(message, 'get_card')

@router.message(Command(commands=['bonus']))
async def on_bonus_command(message: Message) -> None:
    await ensure_user(message)
    await show_screen(message, 'bonus')

@router.message(Command(commands=['shop']))
async def on_shop_command(message: Message) -> None:
    await ensure_user(message)
    await show_screen(message, 'shop')

@router.message(Command(commands=['games']))
async def on_games_command(message: Message) -> None:
    await ensure_user(message)
    await show_screen(message, 'games')

@router.message(Command(commands=['top']))
async def on_top_command(message: Message) -> None:
    await ensure_user(message)
    await show_screen(message, 'top')

@router.message(F.text.in_(MAIN_MENU_BUTTONS))
async def on_main_menu_button(message: Message) -> None:
    if message.text is None:
        return
    if message.from_user is not None:
        async with SessionLocal() as session:
            service = BrawlCardsService(session)
            state = await service.get_input_state(message.from_user.id)
            if state is not None:
                return
    await ensure_user(message)
    await show_screen(message, screen_by_main_menu_button(message.text) or 'main')

@router.message(F.text.in_(['🛠 Админ-панель', '🛠 Админ панель', 'Админ-панель', 'Админ панель']))
async def on_menu_alias(message: Message) -> None:
    if message.text is None:
        return
    if message.from_user is not None:
        async with SessionLocal() as session:
            service = BrawlCardsService(session)
            state = await service.get_input_state(message.from_user.id)
            if state is not None:
                return
    await ensure_user(message)
    await show_screen(message, 'admin')

@router.callback_query(F.data.startswith('nav:'))
async def on_nav(callback: CallbackQuery) -> None:
    if callback.message is None or callback.data is None:
        return
    await safe_callback_answer(callback)
    parts = callback.data.split(':')
    screen = parts[1] if len(parts) > 1 else 'main'
    arg = parts[2] if len(parts) > 2 else None
    msg = callback.message.model_copy(update={'from_user': callback.from_user})
    await ensure_user(msg)
    if screen == 'top' and arg:
        await screen_top_metric(msg, arg)
        return
    if screen == 'rp_cat' and arg:
        async with SessionLocal() as session:
            actions = await BrawlCardsService(session).rp_actions(arg)
        items = [(a.key, f"{a.emoji} {a.title}") for a in actions]
        await msg.answer(f"{h('🎭 RP')}\nВыберите действие.", reply_markup=ik_rp_actions(arg, items))
        return
    if screen == 'game' and arg:
        await render_game_detail(msg, arg)
        return
    if screen == 'shop' and arg:
        await screen_shop_category(msg, arg)
        return
    if screen == 'shop_item' and arg:
        await screen_shop_item(msg, arg)
        return
    if screen == 'chest' and arg:
        await screen_chest_detail(msg, arg)
        return
    if screen == 'task' and arg:
        await screen_task_detail(msg, arg)
        return
    if screen == 'admin' and arg:
        if await render_admin_section_v2(msg, arg):
            return
        await screen_admin_section(msg, arg)
        return
    if screen == 'admin_rarity' and arg:
        await screen_admin_rarity(msg, arg)
        return
    if screen == 'admin_booster' and arg:
        await screen_admin_booster(msg, arg)
        return
    if screen == 'admin_chest' and arg:
        await screen_admin_chest(msg, arg)
        return
    if screen == 'admin_card' and arg:
        await screen_admin_card(msg, int(arg))
        return
    if screen == 'admin_rpcat' and arg:
        await screen_admin_rp_category(msg, arg)
        return
    if screen == 'admin_rpact' and arg:
        await screen_admin_rp_action(msg, arg)
        return
    if screen == 'admin_shopcat' and arg:
        await screen_admin_shop_category(msg, arg)
        return
    if screen == 'admin_shopitem' and arg:
        await screen_admin_shop_item(msg, int(arg))
        return
    if screen == 'admin_task' and arg:
        await screen_admin_task(msg, arg)
        return
    if screen == 'admin_event' and arg:
        await screen_admin_event(msg, arg)
        return
    if screen == 'admin_role' and arg:
        await screen_admin_role(msg, arg)
        return
    if screen == 'admin_perm' and arg:
        await screen_admin_permission(msg, arg)
        return
    if screen == 'admin_media' and arg:
        await screen_admin_media(msg, int(arg))
        return
    if screen == 'market_buy':
        await render_market_list(msg, 'buy')
        return
    if screen == 'market_limited':
        await render_market_list(msg, 'limited')
        return
    if screen == 'market_my':
        await render_market_list(msg, 'my')
        return
    if screen == 'market_history':
        await render_market_list(msg, 'history')
        return
    if screen == 'market_lot' and arg:
        await render_market_lot(msg, int(arg))
        return
    if screen == 'marriage_pair':
        await render_marriage_pair(msg)
        return
    if screen == 'marriage_inbox':
        await render_marriage_inbox(msg)
        return
    await show_screen(msg, screen)

@router.callback_query(F.data.startswith('act:'))
async def on_action(callback: CallbackQuery) -> None:
    if callback.message is None or callback.data is None or callback.from_user is None:
        return
    await safe_callback_answer(callback)
    action = callback.data
    async with user_action_guard(callback.from_user.id):
        async with SessionLocal() as session:
            service = BrawlCardsService(session)
            await service.ensure_user(callback.from_user.id, callback.from_user.username, callback.from_user.first_name)
            await session.commit()

            async def respond(*args, **kwargs):
                reply_markup = kwargs.get('reply_markup')
                if reply_markup is None or isinstance(reply_markup, ReplyKeyboardMarkup):
                    kwargs['reply_markup'] = user_menu(
                        callback.from_user.id,
                        callback.message.chat.type if callback.message.chat else None,
                    )
                await session.commit()
                return await callback.message.answer(*args, **kwargs)

            if action == 'act:nick:enter':
                await service.set_input_state(callback.from_user.id, 'nick_wait', {})
                await respond(f"{h('✏️ Смена ника')}\nОтправьте новый ник одним сообщением.", reply_markup=main_menu())
                return
            if action == 'act:card:repeat_later':
                cd = await service.get_cooldown(callback.from_user.id, 'brawl_cards')
                await respond(f"{h('🃏 Получить карту')}\nОжидание: {seconds_to_hms(cd.seconds_left)}", reply_markup=main_menu())
                return
            if action == 'act:card:open_full':
                state = await session.get(BcUserState, callback.from_user.id)
                if state is None or state.last_card_id is None:
                    await respond(f"{h('🖼 Карточка')}\nНет последней карты.", reply_markup=main_menu())
                    return
                card = await session.get(BcCard, state.last_card_id)
                if card is None:
                    await respond(f"{h('🖼 Карточка')}\nКарта не найдена.", reply_markup=main_menu())
                    return
                text = f"{h('🖼 Карточка полностью')}\n*{card.title}*\n{card.description}"
                if card.image_file_id:
                    await callback.message.answer_photo(card.image_file_id, caption=text, parse_mode='Markdown')
                else:
                    await respond(text, parse_mode='Markdown')
                return
            if action == 'act:card:to_collection':
                await respond(f"{h('📂 Коллекция')}\nКарта уже добавлена в коллекцию автоматически.", reply_markup=main_menu())
                return
            if action.startswith('act:buy_xtr:'):
                item_key = action.split(':', maxsplit=2)[2]
                item = await service.shop_item(item_key)
                if item is None or item.price_stars is None:
                    await respond(f"{h('Telegram Stars')}\nТовар недоступен для оплаты Telegram Stars.", reply_markup=main_menu())
                    return
                await session.commit()
                await callback.message.answer_invoice(
                    title=item.title[:32],
                    description=(item.description or item.title)[:255],
                    payload=f"xtr_shop:{item.key}",
                    currency='XTR',
                    provider_token='',
                    prices=[LabeledPrice(label=item.title[:32], amount=int(item.price_stars))],
                    start_parameter=f"xtr-{item.key}",
                )
                return
            if action.startswith('act:buy:'):
                parts = action.split(':')
                if len(parts) == 4:
                    _, _, item_key, currency = parts
                    ok, resp = await service.buy_shop_item(callback.from_user.id, item_key, currency)
                    await respond(f"{h('🛒 Покупка')}\n{resp}", reply_markup=main_menu())
                    return
            if action.startswith('act:chest:open:'):
                chest_key = action.split(':', maxsplit=3)[3]
                result = await service.chest_open(callback.from_user.id, chest_key)
                if not result.get('ok'):
                    await respond(f"{h('📦 Сундук')}\n{result.get('error', 'Ошибка')}", reply_markup=main_menu())
                    return
                await service.inc_task_counter(callback.from_user.id, 'open_chest', 1)
                drops = result['drops']
                lines = [h(f"{result['chest']['emoji']} Сундук открыт"), f"Сундук: {result['chest']['title']}"]
                total_points = 0
                total_coins = 0
                for drop in drops:
                    lines.append(f"• {drop['rarity']} {drop['title']} (+{drop['points']}✨ +{drop['coins']}🪙)")
                    total_points += int(drop['points'])
                    total_coins += int(drop['coins'])
                lines.append(f"\nИтого: +{total_points}✨ +{total_coins}🪙")
                await respond('\n'.join(lines), reply_markup=main_menu())
                return
            if action.startswith('act:task:claim:'):
                task_key = action.split(':', maxsplit=3)[3]
                ok, resp = await service.claim_task_reward(callback.from_user.id, task_key)
                await respond(f"{h('📋 Задание')}\n{resp}", reply_markup=main_menu())
                return
            if action.startswith('act:bonus:open:'):
                task_key = action.split(':', maxsplit=3)[3]
                task = await session.get(BcBonusTask, task_key)
                if task is None or not task.is_active:
                    await respond(f"{h('🎁 Бонус')}\nЗадание не найдено.", reply_markup=main_menu())
                    return
                rows = []
                task_url = await service.resolve_bonus_url(task)
                if task_url:
                    rows.append([InlineKeyboardButton(text=f"{task.emoji} Открыть задание", url=task_url)])
                rows.append([InlineKeyboardButton(text='✅ Проверить выполнение', callback_data=f"act:bonus:mark:{task.key}")])
                rows.append([InlineKeyboardButton(text='🔙 Назад', callback_data='nav:bonus')])
                kb = InlineKeyboardMarkup(inline_keyboard=rows)
                await respond(f"{h('🎁 Бонусное задание')}\n{task.description}", reply_markup=kb)
                return
            if action.startswith('act:bonus:mark:'):
                task_key = action.split(':', maxsplit=3)[3]
                ok, resp = await service.verify_and_mark_bonus_task(callback.bot, callback.from_user.id, task_key)
                await respond(f"{h('🎁 Бонус')}\n{resp}", reply_markup=main_menu())
                return
            if action == 'act:bonus:check':
                ok, resp = await service.bonus_claim_if_ready(callback.from_user.id)
                await respond(f"{h('🎁 Бонус')}\n{resp}", reply_markup=main_menu())
                return
            if action.startswith('act:rp:do:'):
                action_key = action.split(':', maxsplit=3)[3]
                target_id = None
                if callback.message.reply_to_message and callback.message.reply_to_message.from_user:
                    target_id = callback.message.reply_to_message.from_user.id
                result = await service.perform_rp_action_payload(
                    callback.from_user.id,
                    action_key,
                    target_id,
                    callback.message.chat.type if callback.message.chat else None,
                    callback.message.chat.id if callback.message.chat else None,
                    callback.message.message_id,
                )
                if result.get('need_target'):
                    await service.set_input_state(callback.from_user.id, 'rp_target_wait', {'action_key': action_key})
                    await respond(f"{h('🎭 RP')}\n{result['message']}", reply_markup=main_menu())
                    return
                if not result.get('ok'):
                    await respond(f"{h('🎭 RP')}\n{result['message']}", reply_markup=main_menu())
                    return
                await session.commit()
                await send_rp_result(callback.message, f"{h('🎭 RP')}\n{result['text']}", result.get('media'))
                return
            if action.startswith('act:game:play:'):
                _, _, _, game_key, stake = action.split(':')
                stake_value = int(stake)
                if game_key in service.telegram_game_keys():
                    ok, resp = await service.prepare_telegram_game(callback.from_user.id, game_key, stake_value)
                    if not ok:
                        await respond(f"{h('🎮 Игра')}\n{resp}", reply_markup=main_menu())
                        return
                    await session.commit()
                    emoji = service.telegram_game_emoji(game_key)
                    try:
                        dice_message = await callback.message.answer_dice(emoji=emoji)
                    except Exception:
                        await service.rollback_telegram_game(callback.from_user.id, game_key, stake_value)
                        await session.commit()
                        await respond(f"{h('🎮 Игра')}\nНе удалось отправить Telegram-игру. Ставка возвращена.", reply_markup=main_menu())
                        return
                    value = dice_message.dice.value if dice_message.dice else 0
                    ok, resp = await service.finalize_telegram_game(callback.from_user.id, game_key, stake_value, value)
                    await respond(f"{h('🎮 Игра')}\n{resp}", reply_markup=main_menu())
                    return
                ok, resp = await service.game_play(callback.from_user.id, game_key, stake_value)
                await respond(f"{h('🎮 Игра')}\n{resp}", reply_markup=main_menu())
                return
            if action == 'act:market:sell:start':
                await service.set_input_state(callback.from_user.id, 'market_sell_wait', {})
                await respond(f"{h('💱 Маркет')}\nОтправьте строкой:\n`instance_id|coins_or_stars|price`\nПример: `15|coins|1200`", parse_mode='Markdown', reply_markup=main_menu())
                return
            if action == 'act:market:search:start':
                await respond(f"{h('💱 Маркет')}\nПоиск работает через список лотов и фильтры в карточках лотов.", reply_markup=ik_market_menu())
                return
            if action.startswith('act:market:buy:'):
                lot_id = int(action.split(':')[3])
                ok, resp = await service.market_buy_lot(callback.from_user.id, lot_id)
                await respond(f"{h('💱 Маркет')}\n{resp}", reply_markup=main_menu())
                return
            if action.startswith('act:market:cancel:'):
                lot_id = int(action.split(':')[3])
                ok, resp = await service.market_cancel_lot(callback.from_user.id, lot_id)
                await respond(f"{h('💱 Маркет')}\n{resp}", reply_markup=main_menu())
                return
            if action == 'act:marriage:propose:start':
                await service.set_input_state(callback.from_user.id, 'marriage_propose_wait', {})
                await respond(f"{h('💍 Брак')}\nОтправьте ID пользователя, @username или ссылку на профиль.", reply_markup=main_menu())
                return
            if action.startswith('act:marriage:accept:'):
                proposal_id = int(action.split(':')[3])
                ok, resp = await service.marriage_decide(callback.from_user.id, proposal_id, accept=True)
                await respond(f"{h('💍 Брак')}\n{resp}", reply_markup=main_menu())
                return
            if action.startswith('act:marriage:decline:'):
                proposal_id = int(action.split(':')[3])
                ok, resp = await service.marriage_decide(callback.from_user.id, proposal_id, accept=False)
                await respond(f"{h('💍 Брак')}\n{resp}", reply_markup=main_menu())
                return
            if action == 'act:quote:last_card':
                state = await session.get(BcUserState, callback.from_user.id)
                if state is None or state.last_card_id is None:
                    await respond(f"{h('💬 Цитата')}\nСначала получите карточку.", reply_markup=main_menu())
                    return
                card = await session.get(BcCard, state.last_card_id)
                if card is None:
                    await respond(f"{h('💬 Цитата')}\nКарта не найдена.", reply_markup=main_menu())
                    return
                await respond(f"{h('💬 Цитата')}\n«{card.title}»\n{card.description}", reply_markup=main_menu())
                return
            if action == 'act:quote:custom':
                await service.set_input_state(callback.from_user.id, 'quote_wait', {})
                await respond(f"{h('💬 Цитата')}\nОтправьте текст цитаты одним сообщением.", reply_markup=main_menu())
                return
            if action == 'act:sticker:last_card':
                await service.set_input_state(callback.from_user.id, 'sticker_last_wait', {})
                await respond(f"{h('🎨 Стикер')}\nОтправьте подпись для стикера по последней карте.", reply_markup=main_menu())
                return
            if action == 'act:sticker:template':
                await service.set_input_state(callback.from_user.id, 'sticker_template_wait', {})
                await respond(f"{h('🎨 Стикер')}\nОтправьте текст для шаблонного стикера.", reply_markup=main_menu())
                return
            if action.startswith('act:settings:toggle:'):
                key = action.split(':')[3]
                ok, resp = await service.toggle_setting(callback.from_user.id, key)
                await respond(f"{h('⚙️ Настройки')}\n{resp}", reply_markup=main_menu())
                return
            if action.startswith('act:settings:cycle:'):
                key = action.split(':')[3]
                ok, resp = await service.cycle_setting(callback.from_user.id, key)
                await respond(f"{h('⚙️ Настройки')}\n{resp}", reply_markup=main_menu())
                return
        if action == 'act:admin:card:create':
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            await service.set_input_state(callback.from_user.id, 'admin_card_wizard', {'mode': 'create', 'step': 'key', 'data': {}})
            rarity_hint = await card_rarity_hint(session)
            await respond(
                f"{card_wizard_prompt('create', 'key', {})}\n\n{rarity_hint}\n\nНа необязательных шагах можно отправить `-`, чтобы взять значение по умолчанию.",
                parse_mode='Markdown',
                reply_markup=await admin_card_wizard_markup(session, 'key'),
            )
            return
        if action.startswith('act:admin:card:edit:'):
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            card_id = int(action.split(':', maxsplit=4)[4])
            card = await session.get(BcCard, card_id)
            if card is None:
                await respond('Карточка не найдена.', reply_markup=main_menu())
                return
            data = {
                'title': card.title,
                'description': card.description,
                'rarity_key': card.rarity_key,
                'series': card.series,
                'points': card.base_points,
                'coins': card.base_coins,
                'drop_weight': card.drop_weight,
                'is_limited': int(card.is_limited),
                'is_sellable': int(card.is_sellable),
                'is_active': int(card.is_active),
                'sort': card.sort,
                'photo': card.image_file_id or '',
            }
            await service.set_input_state(callback.from_user.id, 'admin_card_wizard', {'mode': 'edit', 'id': card_id, 'step': 'title', 'data': data})
            await respond(
                f"{h('🃏 Редактор карточки')}\nПошаговое редактирование начато.\nНа любом текстовом шаге отправьте `-`, чтобы оставить текущее значение.\n\n{card_wizard_prompt('edit', 'title', data)}",
                parse_mode='Markdown',
                reply_markup=await admin_card_wizard_markup(session, 'title'),
            )
            return
        if action.startswith('act:admin:card:wizard:value:'):
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            raw = action.split(':', maxsplit=5)[5]
            result = await consume_admin_card_wizard_input(session, service, callback.from_user.id, raw)
            preview_text = None
            if result.get('done') and result.get('card_id'):
                card = await session.get(BcCard, int(result['card_id']))
                if card is not None:
                    preview_text = (
                        f"{h('🃏 Карточка сохранена')}\n"
                        f"Название: {card.title}\n"
                        f"Редкость: {card.rarity_key}\n"
                        f"Серия: {card.series}\n"
                        f"Фото: {'есть' if bool(card.image_file_id) else 'нет'}"
                    )
            await respond(
                result['text'],
                parse_mode=result.get('parse_mode'),
                reply_markup=result.get('reply_markup') or main_menu(),
            )
            if preview_text:
                await respond(preview_text, reply_markup=main_menu())
            return
        if action == 'act:admin:card:wizard:cancel':
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            await service.clear_input_state(callback.from_user.id)
            await respond(f"{h('🃏 Конструктор карточки')}\nСоздание или редактирование карточки отменено.", reply_markup=main_menu())
            return
        if action == 'act:admin:card:wizard:skip_photo':
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            state = await service.get_input_state(callback.from_user.id)
            if state is None or state.state != 'admin_card_wizard':
                await respond(f"{h('🃏 Конструктор карточки')}\nАктивный сценарий не найден.", reply_markup=main_menu())
                return
            payload = dict(state.payload or {})
            if str(payload.get('step') or '') != 'photo':
                await respond(f"{h('🃏 Конструктор карточки')}\nПропуск фото доступен только на шаге фото.", reply_markup=main_menu())
                return
            result = await consume_admin_card_wizard_input(session, service, callback.from_user.id, '-')
            preview_text = None
            if result.get('done') and result.get('card_id'):
                card = await session.get(BcCard, int(result['card_id']))
                if card is not None:
                    preview_text = (
                        f"{h('🃏 Карточка сохранена')}\n"
                        f"Название: {card.title}\n"
                        f"Редкость: {card.rarity_key}\n"
                        f"Серия: {card.series}\n"
                        f"Фото: {'есть' if bool(card.image_file_id) else 'нет'}"
                    )
            await respond(
                result['text'],
                parse_mode=result.get('parse_mode'),
                reply_markup=result.get('reply_markup') or main_menu(),
            )
            if preview_text:
                await respond(preview_text, reply_markup=main_menu())
            return
        if action.startswith('act:admin:card:duplicate:'):
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            card_id = int(action.split(':', maxsplit=4)[4])
            source_card = await session.get(BcCard, card_id)
            if source_card is None:
                await respond('Карточка не найдена.', reply_markup=main_menu())
                return
            base_key = f"{source_card.key}_copy"
            new_key = base_key
            suffix = 2
            while await session.scalar(select(BcCard.id).where(BcCard.key == new_key)) is not None:
                new_key = f"{base_key}_{suffix}"
                suffix += 1
            clone = BcCard(
                key=new_key,
                title=f"{source_card.title} COPY",
                description=source_card.description,
                rarity_key=source_card.rarity_key,
                series=source_card.series,
                tags=list(source_card.tags or []),
                base_points=source_card.base_points,
                base_coins=source_card.base_coins,
                drop_weight=source_card.drop_weight,
                is_limited=source_card.is_limited,
                limited_series_id=source_card.limited_series_id,
                event_id=source_card.event_id,
                image_file_id=source_card.image_file_id,
                image_url=source_card.image_url,
                media_id=source_card.media_id,
                is_sellable=source_card.is_sellable,
                is_active=False,
                sort=source_card.sort + 1,
                meta=dict(source_card.meta or {}),
            )
            session.add(clone)
            await session.flush()
            service.invalidate_catalog_cache()
            await respond(f"{h('🃏 Карточка')}\nСоздан дубликат: `{clone.key}`", parse_mode='Markdown', reply_markup=main_menu())
            await screen_admin_card(callback.message, clone.id)
            return
        if action.startswith('act:admin:card:photo:'):
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            card_id = int(action.split(':', maxsplit=4)[4])
            await service.set_input_state(callback.from_user.id, 'admin_card_photo', {'id': card_id})
            await respond(f"{h('🖼 Фото карточки')}\nОтправьте новое фото сообщением.", reply_markup=main_menu())
            return
        if action.startswith('act:admin:card:toggle_active:'):
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            card_id = int(action.split(':', maxsplit=5)[4])
            card = await session.get(BcCard, card_id)
            if card is None:
                await respond('Карточка не найдена.', reply_markup=main_menu())
                return
            card.is_active = not card.is_active
            service.invalidate_catalog_cache()
            await respond('Статус активности карточки обновлён.', reply_markup=main_menu())
            return
        if action.startswith('act:admin:card:toggle_sell:'):
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            card_id = int(action.split(':', maxsplit=5)[4])
            card = await session.get(BcCard, card_id)
            if card is None:
                await respond('Карточка не найдена.', reply_markup=main_menu())
                return
            card.is_sellable = not card.is_sellable
            service.invalidate_catalog_cache()
            await respond('Статус продажи карточки обновлён.', reply_markup=main_menu())
            return
        if action.startswith('act:admin:card:delete:'):
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            card_id = int(action.split(':', maxsplit=4)[4])
            card = await session.get(BcCard, card_id)
            if card is None:
                await respond('Карточка не найдена.', reply_markup=main_menu())
                return
            await session.delete(card)
            service.invalidate_catalog_cache()
            await respond('Карточка удалена.', reply_markup=main_menu())
            return
        if action == 'act:admin:rp_category:create':
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            await service.set_input_state(callback.from_user.id, 'admin_rp_category_form', {'mode': 'create'})
            await respond(
                f"{h('🎭 Категория RP')}\nОтправьте одной строкой:\n`key|Название|emoji|sort|active(0/1)`\n\nПример:\n`romance|Романтические|💘|20|1`",
                parse_mode='Markdown',
                reply_markup=main_menu(),
            )
            return
        if action.startswith('act:admin:rp_category:edit:'):
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            category_key = action.split(':', maxsplit=4)[4]
            await service.set_input_state(callback.from_user.id, 'admin_rp_category_form', {'mode': 'edit', 'key': category_key})
            await respond(
                f"{h('🎭 Категория RP')}\nКлюч: `{category_key}`\nОтправьте строкой:\n`Название|emoji|sort|active(0/1)`",
                parse_mode='Markdown',
                reply_markup=main_menu(),
            )
            return
        if action.startswith('act:admin:rp_category:delete:'):
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            category_key = action.split(':', maxsplit=4)[4]
            category = await session.get(BcRPCategory, category_key)
            if category is None:
                await respond('Категория не найдена.', reply_markup=main_menu())
                return
            await session.delete(category)
            service.invalidate_catalog_cache()
            await respond('Категория RP удалена.', reply_markup=main_menu())
            return
        if action == 'act:admin:rp_action:create':
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            await service.set_input_state(callback.from_user.id, 'admin_rp_action_form', {'mode': 'create'})
            await respond(
                f"{h('🎭 RP-действие')}\nОтправьте одной строкой:\n`key|category_key|Название|emoji|requires_target(0/1)|cooldown|coins|stars|points|media_id|private(0/1)|group(0/1)|sort|active(0/1)|template1;;template2`\n\nПример:\n`hug|friendly|Обнять|🤝|1|30|0|0|1||1|1|10|1|{{actor}} обнял {{target}};;{{actor}} крепко обнял {{target}}`",
                parse_mode='Markdown',
                reply_markup=main_menu(),
            )
            return
        if action.startswith('act:admin:rp_action:edit:'):
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            action_key = action.split(':', maxsplit=4)[4]
            await service.set_input_state(callback.from_user.id, 'admin_rp_action_form', {'mode': 'edit', 'key': action_key})
            await respond(
                f"{h('🎭 RP-действие')}\nКлюч: `{action_key}`\nОтправьте строкой:\n`category_key|Название|emoji|requires_target(0/1)|cooldown|coins|stars|points|media_id|private(0/1)|group(0/1)|sort|active(0/1)|template1;;template2`",
                parse_mode='Markdown',
                reply_markup=main_menu(),
            )
            return
        if action.startswith('act:admin:rp_action:delete:'):
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            action_key = action.split(':', maxsplit=4)[4]
            rp_action = await session.get(BcRPAction, action_key)
            if rp_action is None:
                await respond('RP-действие не найдено.', reply_markup=main_menu())
                return
            await session.delete(rp_action)
            service.invalidate_catalog_cache()
            await respond('RP-действие удалено.', reply_markup=main_menu())
            return
        if action == 'act:admin:rarity:create':
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            await service.set_input_state(callback.from_user.id, 'admin_rarity_form', {'mode': 'create'})
            await respond(f"{h('💎 Добавить редкость')}\nОтправьте одной строкой:\n`key|Название|эмодзи|шанс_редкости|цвет|points_mult|coins_mult|drop_mode|in_chests(0/1)|in_shop(0/1)`\nПример:\n`ultra|Ультра|🔶|0.2|#FFAA00|4.2|2.9|normal|1|1`", parse_mode='Markdown', reply_markup=main_menu())
            return
        if action.startswith('act:admin:rarity:edit:'):
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            rarity_key = action.split(':', maxsplit=4)[4]
            await service.set_input_state(callback.from_user.id, 'admin_rarity_form', {'mode': 'edit', 'key': rarity_key})
            await respond(f"{h('💎 Редактировать редкость')}\nКлюч: `{rarity_key}`\nОтправьте строкой:\n`Название|эмодзи|шанс_редкости|цвет|points_mult|coins_mult|drop_mode|in_chests(0/1)|in_shop(0/1)|active(0/1)`", parse_mode='Markdown', reply_markup=main_menu())
            return
        if action.startswith('act:admin:rarity:delete:'):
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            rarity_key = action.split(':', maxsplit=4)[4]
            r = await session.get(BcRarity, rarity_key)
            if r is None:
                await respond('Редкость не найдена.', reply_markup=main_menu())
                return
            await session.delete(r)
            service.invalidate_catalog_cache()
            await respond('Редкость удалена.', reply_markup=main_menu())
            return
        if action == 'act:admin:booster:create':
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            await service.set_input_state(callback.from_user.id, 'admin_booster_form', {'mode': 'create'})
            await respond(f"{h('⚡ Добавить бустер')}\nОтправьте одной строкой:\n`key|Название|эмодзи|effect_type|power|price_coins|price_stars|duration_seconds|max_stack|available(0/1)`\nПример:\n`luck2|Удача+|🍀|luck|0.5|600||0|10|1`", parse_mode='Markdown', reply_markup=main_menu())
            return
        if action.startswith('act:admin:booster:edit:'):
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            booster_key = action.split(':', maxsplit=4)[4]
            await service.set_input_state(callback.from_user.id, 'admin_booster_form', {'mode': 'edit', 'key': booster_key})
            await respond(f"{h('⚡ Редактировать бустер')}\nКлюч: `{booster_key}`\nОтправьте строкой:\n`Название|эмодзи|effect_type|power|price_coins|price_stars|duration_seconds|max_stack|available(0/1)`", parse_mode='Markdown', reply_markup=main_menu())
            return
        if action.startswith('act:admin:booster:delete:'):
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            booster_key = action.split(':', maxsplit=4)[4]
            b = await session.get(BcBooster, booster_key)
            if b is None:
                await respond('Бустер не найден.', reply_markup=main_menu())
                return
            await session.delete(b)
            service.invalidate_catalog_cache()
            await respond('Бустер удалён.', reply_markup=main_menu())
            return
        if action == 'act:admin:chest:create':
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            await service.set_input_state(callback.from_user.id, 'admin_chest_form', {'mode': 'create'})
            await respond(f"{h('📦 Добавить сундук')}\nОтправьте одной строкой:\n`key|Название|эмодзи|описание|price_coins|price_stars|open_count|drops`\nГде `drops` — список `rarity=weight,rarity=weight`.\nПример:\n`mini|Мини|📦|Быстрый сундук|150||1|common=90,rare=9,epic=1`", parse_mode='Markdown', reply_markup=main_menu())
            return
        if action.startswith('act:admin:chest:edit:'):
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            chest_key = action.split(':', maxsplit=4)[4]
            await service.set_input_state(callback.from_user.id, 'admin_chest_form', {'mode': 'edit', 'key': chest_key})
            await respond(f"{h('📦 Редактировать сундук')}\nКлюч: `{chest_key}`\nОтправьте строкой:\n`Название|эмодзи|описание|price_coins|price_stars|open_count|active(0/1)`", parse_mode='Markdown', reply_markup=main_menu())
            return
        if action.startswith('act:admin:chest:drops:edit:'):
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            chest_key = action.split(':', maxsplit=5)[5]
            await service.set_input_state(callback.from_user.id, 'admin_chest_drops_form', {'key': chest_key})
            await respond(
                f"{h('🎯 Дроп сундука')}\nКлюч: `{chest_key}`\nОтправьте строкой:\n`rarity=weight:min:max,rarity=weight:min:max`\n\nПример:\n`common=90:1:1,rare=9:1:1,epic=1:1:1`",
                parse_mode='Markdown',
                reply_markup=main_menu(),
            )
            return
        if action.startswith('act:admin:chest:delete:'):
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            chest_key = action.split(':', maxsplit=4)[4]
            c = await session.get(BcChest, chest_key)
            if c is None:
                await respond('Сундук не найден.', reply_markup=main_menu())
                return
            await session.delete(c)
            service.invalidate_catalog_cache()
            await respond('Сундук удалён.', reply_markup=main_menu())
            return
        if action == 'act:admin:shop_category:create':
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            await service.set_input_state(callback.from_user.id, 'admin_shop_category_form', {'mode': 'create'})
            await respond(
                f"{h('🛒 Категория магазина')}\nОтправьте строкой:\n`key|Название|эмодзи|sort|active(0/1)`\n\nПример:\n`seasonal|Сезонное|🧨|70|1`",
                parse_mode='Markdown',
                reply_markup=main_menu(),
            )
            return
        if action.startswith('act:admin:shop_category:edit:'):
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            category_key = action.split(':', maxsplit=4)[4]
            await service.set_input_state(callback.from_user.id, 'admin_shop_category_form', {'mode': 'edit', 'key': category_key})
            await respond(
                f"{h('🛒 Категория магазина')}\nКлюч: `{category_key}`\nОтправьте строкой:\n`Название|эмодзи|sort|active(0/1)`",
                parse_mode='Markdown',
                reply_markup=main_menu(),
            )
            return
        if action.startswith('act:admin:shop_category:delete:'):
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            category_key = action.split(':', maxsplit=4)[4]
            category = await session.get(BcShopCategory, category_key)
            if category is None:
                await respond('Категория не найдена.', reply_markup=main_menu())
                return
            await session.delete(category)
            service.invalidate_catalog_cache()
            await respond('Категория магазина удалена.', reply_markup=main_menu())
            return
        if action == 'act:admin:shop_item:create':
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            await service.set_input_state(callback.from_user.id, 'admin_shop_item_form', {'mode': 'create'})
            await respond(
                f"{h('🛍 Товар магазина')}\nОтправьте строкой:\n`category_key|key|Название|описание|price_coins|price_stars|duration_seconds|payload_type|payload_ref|payload_value|sort|active(0/1)`\n\nPayload types: `booster`, `activate_booster`, `premium`, `currency_exchange`, `custom`\nПример:\n`boosters|luck_pack|Удача|Бустер удачи|250||0|booster|luck|1|10|1`",
                parse_mode='Markdown',
                reply_markup=main_menu(),
            )
            return
        if action.startswith('act:admin:shop_item:create:'):
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            category_key = action.split(':', maxsplit=4)[4]
            await service.set_input_state(callback.from_user.id, 'admin_shop_item_form', {'mode': 'create', 'category_key': category_key})
            await respond(
                f"{h('🛍 Товар магазина')}\nКатегория: `{category_key}`\nОтправьте строкой:\n`key|Название|описание|price_coins|price_stars|duration_seconds|payload_type|payload_ref|payload_value|sort|active(0/1)`",
                parse_mode='Markdown',
                reply_markup=main_menu(),
            )
            return
        if action.startswith('act:admin:shop_item:edit:'):
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            item_id = int(action.split(':', maxsplit=4)[4])
            await service.set_input_state(callback.from_user.id, 'admin_shop_item_form', {'mode': 'edit', 'id': item_id})
            await respond(
                f"{h('🛍 Товар магазина')}\nID: `{item_id}`\nОтправьте строкой:\n`category_key|key|Название|описание|price_coins|price_stars|duration_seconds|payload_type|payload_ref|payload_value|sort|active(0/1)`",
                parse_mode='Markdown',
                reply_markup=main_menu(),
            )
            return
        if action.startswith('act:admin:shop_item:toggle:'):
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            item_id = int(action.split(':', maxsplit=5)[4])
            item = await session.get(BcShopItem, item_id)
            if item is None:
                await respond('Товар не найден.', reply_markup=main_menu())
                return
            item.is_active = not item.is_active
            service.invalidate_catalog_cache()
            await respond('Статус товара обновлён.', reply_markup=main_menu())
            return
        if action.startswith('act:admin:shop_item:delete:'):
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            item_id = int(action.split(':', maxsplit=4)[4])
            item = await session.get(BcShopItem, item_id)
            if item is None:
                await respond('Товар не найден.', reply_markup=main_menu())
                return
            await session.delete(item)
            service.invalidate_catalog_cache()
            await respond('Товар удалён.', reply_markup=main_menu())
            return
        if action == 'act:admin:task:create':
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            await service.set_input_state(callback.from_user.id, 'admin_task_form', {'mode': 'create'})
            await respond(
                f"{h('📜 Задание')}\nОтправьте строкой:\n`key|kind|Название|описание|target|coins|stars|points|counter|sort|active(0/1)`\n\nПример:\n`daily_cards|daily|Получи 5 карт|Собери карты сегодня|5|250|1|15|get_cards|10|1`",
                parse_mode='Markdown',
                reply_markup=main_menu(),
            )
            return
        if action.startswith('act:admin:task:edit:'):
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            task_key = action.split(':', maxsplit=4)[4]
            await service.set_input_state(callback.from_user.id, 'admin_task_form', {'mode': 'edit', 'key': task_key})
            await respond(
                f"{h('📜 Задание')}\nКлюч: `{task_key}`\nОтправьте строкой:\n`kind|Название|описание|target|coins|stars|points|counter|sort|active(0/1)`",
                parse_mode='Markdown',
                reply_markup=main_menu(),
            )
            return
        if action.startswith('act:admin:task:delete:'):
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            task_key = action.split(':', maxsplit=4)[4]
            task = await session.get(BcTask, task_key)
            if task is None:
                await respond('Задание не найдено.', reply_markup=main_menu())
                return
            await session.delete(task)
            service.invalidate_catalog_cache()
            await respond('Задание удалено.', reply_markup=main_menu())
            return
        if action == 'act:admin:event:create':
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            await service.set_input_state(callback.from_user.id, 'admin_event_form', {'mode': 'create'})
            await respond(
                f"{h('🎉 Ивент')}\nОтправьте строкой:\n`key|Название|описание|starts_at|ends_at|active(0/1)`\n\nИспользуйте ISO формат времени или `-`.\nПример:\n`spring|Весенний дроп|Карты и бонусы сезона|2026-04-10T12:00|2026-04-20T23:59|1`",
                parse_mode='Markdown',
                reply_markup=main_menu(),
            )
            return
        if action.startswith('act:admin:event:edit:'):
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            event_key = action.split(':', maxsplit=4)[4]
            await service.set_input_state(callback.from_user.id, 'admin_event_form', {'mode': 'edit', 'key': event_key})
            await respond(
                f"{h('🎉 Ивент')}\nКлюч: `{event_key}`\nОтправьте строкой:\n`Название|описание|starts_at|ends_at|active(0/1)`",
                parse_mode='Markdown',
                reply_markup=main_menu(),
            )
            return
        if action.startswith('act:admin:event:delete:'):
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            event_key = action.split(':', maxsplit=4)[4]
            event = await session.scalar(select(BcEvent).where(BcEvent.key == event_key))
            if event is None:
                await respond('Ивент не найден.', reply_markup=main_menu())
                return
            await session.delete(event)
            service.invalidate_catalog_cache()
            await respond('Ивент удалён.', reply_markup=main_menu())
            return
        if action == 'act:admin:role:create':
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            await service.set_input_state(callback.from_user.id, 'admin_role_form', {'mode': 'create'})
            await respond(f"{h('🔐 Роль')}\nОтправьте строкой:\n`key|Название`", parse_mode='Markdown', reply_markup=main_menu())
            return
        if action.startswith('act:admin:role:edit:'):
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            role_key = action.split(':', maxsplit=4)[4]
            await service.set_input_state(callback.from_user.id, 'admin_role_form', {'mode': 'edit', 'key': role_key})
            await respond(f"{h('🔐 Роль')}\nКлюч: `{role_key}`\nОтправьте новое название роли.", parse_mode='Markdown', reply_markup=main_menu())
            return
        if action.startswith('act:admin:role:delete:'):
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            role_key = action.split(':', maxsplit=4)[4]
            role = await session.get(BcRole, role_key)
            if role is None:
                await respond('Роль не найдена.', reply_markup=main_menu())
                return
            await session.delete(role)
            await respond('Роль удалена.', reply_markup=main_menu())
            return
        if action == 'act:admin:permission:create':
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            await service.set_input_state(callback.from_user.id, 'admin_permission_form', {'mode': 'create'})
            await respond(f"{h('🔐 Право')}\nОтправьте строкой:\n`code|Название`", parse_mode='Markdown', reply_markup=main_menu())
            return
        if action.startswith('act:admin:permission:edit:'):
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            permission_code = action.split(':', maxsplit=4)[4]
            await service.set_input_state(callback.from_user.id, 'admin_permission_form', {'mode': 'edit', 'code': permission_code})
            await respond(f"{h('🔐 Право')}\nКод: `{permission_code}`\nОтправьте новое название права.", parse_mode='Markdown', reply_markup=main_menu())
            return
        if action.startswith('act:admin:permission:delete:'):
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            permission_code = action.split(':', maxsplit=4)[4]
            permission = await session.get(BcPermission, permission_code)
            if permission is None:
                await respond('Право не найдено.', reply_markup=main_menu())
                return
            await session.delete(permission)
            await respond('Право удалено.', reply_markup=main_menu())
            return
        if action == 'act:admin:role:grant:start':
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            await service.set_input_state(callback.from_user.id, 'admin_role_grant_form', {})
            await respond(
                f"{h('👤 Выдача роли')}\nОтправьте строкой:\n`user_id|role_key|grant_or_revoke`\n\nПример:\n`123456789|moderator|grant`",
                parse_mode='Markdown',
                reply_markup=main_menu(),
            )
            return
        if action == 'act:admin:role:link_permission:start':
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            await service.set_input_state(callback.from_user.id, 'admin_role_permission_form', {})
            await respond(
                f"{h('🔗 Привязка права')}\nОтправьте строкой:\n`role_key|permission_code|grant_or_revoke`\n\nПример:\n`moderator|logs.view|grant`",
                parse_mode='Markdown',
                reply_markup=main_menu(),
            )
            return
        if action == 'act:admin:media:create':
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            await service.set_input_state(callback.from_user.id, 'admin_media_form', {'mode': 'create'})
            await respond(
                f"{h('🖼 Медиа')}\nОтправьте строкой:\n`kind|Название|url_or_-|active(0/1)`\n\nПосле создания можно отдельно загрузить Telegram file_id через кнопку.",
                parse_mode='Markdown',
                reply_markup=main_menu(),
            )
            return
        if action.startswith('act:admin:media:edit:'):
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            media_id = int(action.split(':', maxsplit=4)[4])
            await service.set_input_state(callback.from_user.id, 'admin_media_form', {'mode': 'edit', 'id': media_id})
            await respond(
                f"{h('🖼 Медиа')}\nID: `{media_id}`\nОтправьте строкой:\n`kind|Название|url_or_-|active(0/1)`",
                parse_mode='Markdown',
                reply_markup=main_menu(),
            )
            return
        if action.startswith('act:admin:media:file:'):
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            media_id = int(action.split(':', maxsplit=4)[4])
            await service.set_input_state(callback.from_user.id, 'admin_media_file_form', {'id': media_id})
            await respond(f"{h('🖼 Медиа')}\nОтправьте фото. Telegram file_id будет сохранён в запись #{media_id}.", reply_markup=main_menu())
            return
        if action.startswith('act:admin:media:delete:'):
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            media_id = int(action.split(':', maxsplit=4)[4])
            media = await session.get(BcMedia, media_id)
            if media is None:
                await respond('Медиа не найдено.', reply_markup=main_menu())
                return
            await session.delete(media)
            service.invalidate_catalog_cache()
            await respond('Медиа удалено.', reply_markup=main_menu())
            return
        if action == 'act:admin:user:manage:start':
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            await service.set_input_state(callback.from_user.id, 'admin_user_manage_form', {})
            await respond(
                f"{h('👥 Управление пользователем')}\nОтправьте одной строкой:\n`user_id|field|value`\n\nПоля:\n`coins`, `stars`, `points`, `level`, `exp`, `premium_days`, `nickname`, `cooldown:action`\n\nПримеры:\n`123456789|coins|5000`\n`123456789|cooldown:brawl_cards|0`",
                parse_mode='Markdown',
                reply_markup=main_menu(),
            )
            return
        if action.startswith('act:admin:sys:edit:'):
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            section = action.split(':', maxsplit=4)[4]
            await service.set_input_state(callback.from_user.id, 'admin_system_form', {'section': section})
            if section == 'cooldowns':
                current = await service.get_system_section('cooldowns')
                keys_text = ', '.join(f"`{key}`" for key in sorted(current))
                prompt = (
                    f"{h('⏱ Кулдауны')}\n"
                    "Отправьте строкой:\n"
                    "`key|seconds`\n\n"
                    "Ключи:\n"
                    f"{keys_text}\n\n"
                    "Для RP общий кулдаун не нужен: он меняется в самой RP-команде."
                )
            elif section == 'rewards':
                prompt = (
                    f"{h('🎁 Награды')}\n"
                    "Отправьте строкой:\n"
                    "`key|value`\n\n"
                    "Ключи:\n"
                    "`bonus_coins`, `bonus_stars`, `market_fee_percent`"
                )
            elif section == 'button_labels':
                prompt = (
                    f"{h('🔘 Подписи кнопок')}\n"
                    "Отправьте строкой:\n"
                    "`key|text`\n\n"
                    "Примеры ключей:\n"
                    "`main.profile`, `main.shop`, `main.admin`, `common.back`, `admin.broadcast`, `settings.notifications`"
                )
            elif section == 'input_placeholders':
                prompt = (
                    f"{h('⌨️ Placeholder')}\n"
                    "Отправьте строкой:\n"
                    "`key|text`\n\n"
                    "Ключи:\n"
                    "`main_menu`\n\n"
                    "Если нужен дефолт, отправьте `main_menu|-`."
                )
            elif section == 'main_menu_items':
                prompt = (
                    f"{h('🧭 Главное меню')}\n"
                    "Отправьте строкой:\n"
                    "`key|order|visible(0/1)|admin_only(0/1)`\n\n"
                    "Пример:\n"
                    "`main.premium|70|1|0`"
                )
            elif section == 'admin_menu_items':
                prompt = (
                    f"{h('🛠 Админ-меню')}\n"
                    "Отправьте строкой:\n"
                    "`key|order|visible(0/1)`\n\n"
                    "Пример:\n"
                    "`admin.broadcast|120|1`"
                )
            elif section == 'feature_flags':
                prompt = (
                    f"{h('🚦 Feature Flags')}\n"
                    "Отправьте строкой:\n"
                    "`screen|enabled(0/1)`\n\n"
                    "Пример:\n"
                    "`market|0`"
                )
            else:
                prompt = (
                    f"{h('🔗 Bonus-ссылки')}\n"
                    "Отправьте строкой:\n"
                    "`key|url`\n\n"
                    "Ключи:\n"
                    "`chat`, `subscribe`, `news`, `invite`, `partner`"
                )
            await respond(prompt, parse_mode='Markdown', reply_markup=main_menu())
            return
        if action == 'act:admin:template:pick':
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            await service.set_input_state(callback.from_user.id, 'admin_template_pick_form', {'locale': 'ru'})
            await respond(
                f"{h('🧾 Шаблон по ключу')}\nОтправьте строкой:\n`template_key|locale`\n\nПример:\n`screen.shop|ru`",
                parse_mode='Markdown',
                reply_markup=main_menu(),
            )
            return
        if action.startswith('act:admin:template:edit:'):
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            template_key = action.split(':', maxsplit=4)[4]
            await service.set_input_state(callback.from_user.id, 'admin_template_form', {'key': template_key, 'locale': 'ru'})
            current_text = await service.get_template_text(
                template_key,
                'ru',
                DEFAULT_TEXT_TEMPLATES.get(template_key, ''),
            )
            await respond(
                f"{h('📝 Редактор шаблона')}\nКлюч: {template_key}\n\nОтправьте новый текст одним сообщением.\n\nТекущее значение:\n{current_text}",
                reply_markup=main_menu(),
            )
            return
        if action == 'act:admin:broadcast:start':
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            await service.set_input_state(callback.from_user.id, 'admin_broadcast_form', {})
            await respond(
                f"{h('📢 Рассылка')}\nОтправьте текст рассылки одним сообщением.\n\nПосле отправки рассылка уйдёт в фон батчами.",
                reply_markup=main_menu(),
            )
            return
    await respond('Команда не распознана или уже недоступна.', reply_markup=main_menu())

@router.pre_checkout_query()
async def on_pre_checkout_query(pre_checkout_query: PreCheckoutQuery) -> None:
    payload = pre_checkout_query.invoice_payload or ""
    if not payload.startswith("xtr_shop:"):
        await pre_checkout_query.answer(ok=False, error_message="\u041d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u044b\u0439 \u043f\u043b\u0430\u0442\u0435\u0436.")
        return
    if pre_checkout_query.currency != "XTR":
        await pre_checkout_query.answer(ok=False, error_message="Оплата доступна только через Telegram Stars.")
        return
    item_key = payload.split(":", maxsplit=1)[1]
    async with SessionLocal() as session:
        service = BrawlCardsService(session)
        item = await service.shop_item(item_key)
    if item is None or item.price_stars is None:
        await pre_checkout_query.answer(ok=False, error_message="\u0422\u043e\u0432\u0430\u0440 \u0431\u043e\u043b\u044c\u0448\u0435 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u0435\u043d.")
        return
    if int(pre_checkout_query.total_amount) != int(item.price_stars):
        await pre_checkout_query.answer(ok=False, error_message="\u0421\u0443\u043c\u043c\u0430 \u043f\u043b\u0430\u0442\u0435\u0436\u0430 \u0443\u0441\u0442\u0430\u0440\u0435\u043b\u0430. \u041e\u0442\u043a\u0440\u043e\u0439\u0442\u0435 \u0442\u043e\u0432\u0430\u0440 \u0437\u0430\u043d\u043e\u0432\u043e.")
        return
    await pre_checkout_query.answer(ok=True)

@router.message(F.successful_payment)
async def on_successful_payment(message: Message) -> None:
    if message.from_user is None or message.successful_payment is None:
        return
    payload = message.successful_payment.invoice_payload or ""
    if not payload.startswith("xtr_shop:"):
        return
    item_key = payload.split(":", maxsplit=1)[1]
    async with SessionLocal() as session:
        service = BrawlCardsService(session)
        async with session.begin():
            await service.ensure_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
            ok, duplicate, resp = await service.process_stars_payment(
                user_id=message.from_user.id,
                item_key=item_key,
                charge_id=message.successful_payment.telegram_payment_charge_id,
                amount_paid=int(message.successful_payment.total_amount),
                invoice_payload=payload,
                provider_charge_id=message.successful_payment.provider_payment_charge_id or None,
            )
        if ok and duplicate:
            body = await service.get_template_text(
                'premium.payment_duplicate',
                'ru',
                DEFAULT_TEXT_TEMPLATES['premium.payment_duplicate'],
            )
            title = h("Платёж уже учтён")
        elif ok:
            body = await service.get_template_text(
                'premium.payment_success',
                'ru',
                DEFAULT_TEXT_TEMPLATES['premium.payment_success'],
            )
            title = h("Оплата успешна")
        else:
            body = await service.get_template_text(
                'premium.payment_error',
                'ru',
                DEFAULT_TEXT_TEMPLATES['premium.payment_error'],
            )
            title = h("Ошибка оплаты")
    charge_id = message.successful_payment.telegram_payment_charge_id
    await message.answer(
        f"{title}\n{body}\n\n{resp}\n\nСумма: {message.successful_payment.total_amount} XTR\nCharge ID: `{charge_id}`",
        reply_markup=user_menu(message.from_user.id, chat_type_of(message)),
        parse_mode="Markdown",
    )

@router.message(F.text)
async def on_state_text_input(message: Message) -> None:
    if message.from_user is None or not message.text:
        return
    async with SessionLocal() as session:
        service = BrawlCardsService(session)
        state = await service.get_input_state(message.from_user.id)
        if state is None:
            return

        raw = message.text.strip()
        menu = user_menu(message.from_user.id, chat_type_of(message))

        if state.state == 'nick_wait':
            async with session.begin():
                ok, resp = await service.change_nickname(message.from_user.id, raw)
                if ok:
                    await service.clear_input_state(message.from_user.id)
            await message.answer(resp, reply_markup=menu)
            return

        if state.state == 'rp_target_wait':
            payload = dict(state.payload or {})
            action_key = str(payload.get('action_key') or '')
            target = await service.resolve_user_reference(raw)
            if target is None:
                await message.answer(f"{h('\U0001f3ad RP')}\n\u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d. \u041e\u0442\u043f\u0440\u0430\u0432\u044c\u0442\u0435 ID, @username \u0438\u043b\u0438 \u0441\u0441\u044b\u043b\u043a\u0443 `https://t.me/...`.", parse_mode='Markdown', reply_markup=menu)
                return
            async with session.begin():
                result = await service.perform_rp_action_payload(
                    message.from_user.id,
                    action_key,
                    target.id,
                    message.chat.type if message.chat else None,
                    message.chat.id if message.chat else None,
                    message.message_id,
                )
                if result.get('ok'):
                    await service.clear_input_state(message.from_user.id)
            if not result.get('ok'):
                await message.answer(f"{h('\U0001f3ad RP')}\n{result.get('message', '\u041e\u0448\u0438\u0431\u043a\u0430 RP-\u0434\u0435\u0439\u0441\u0442\u0432\u0438\u044f.')}", reply_markup=menu)
                return
            await send_rp_result(message, f"{h('\U0001f3ad RP')}\n{result['text']}", result.get('media'))
            return

        if state.state == 'quote_wait':
            async with session.begin():
                await service.clear_input_state(message.from_user.id)
            await message.answer(f"{h('\U0001f4ac \u0426\u0438\u0442\u0430\u0442\u0430')}\n\xab{raw}\xbb", reply_markup=menu)
            return

        if state.state == 'sticker_last_wait':
            state_row = await session.get(BcUserState, message.from_user.id)
            card = await session.get(BcCard, state_row.last_card_id) if state_row and state_row.last_card_id else None
            if card is None:
                await message.answer(f"{h('\U0001f3a8 \u0421\u0442\u0438\u043a\u0435\u0440')}\n\u0421\u043d\u0430\u0447\u0430\u043b\u0430 \u043f\u043e\u043b\u0443\u0447\u0438\u0442\u0435 \u043a\u0430\u0440\u0442\u043e\u0447\u043a\u0443.", reply_markup=menu)
                return
            out_file = build_card_image(card.title, card.rarity_key, card.description, raw, Path('data/generated'))
            async with session.begin():
                await service.clear_input_state(message.from_user.id)
            await message.answer_photo(FSInputFile(out_file), caption=f"{h('\U0001f3a8 \u0421\u0442\u0438\u043a\u0435\u0440')}\n\u0421\u0442\u0438\u043a\u0435\u0440 \u043f\u043e \u043f\u043e\u0441\u043b\u0435\u0434\u043d\u0435\u0439 \u043a\u0430\u0440\u0442\u043e\u0447\u043a\u0435 \u0433\u043e\u0442\u043e\u0432.", reply_markup=menu)
            return

        if state.state == 'sticker_template_wait':
            out_file = build_card_image('Antonio', 'common', '\u0428\u0430\u0431\u043b\u043e\u043d\u043d\u044b\u0439 \u0441\u0442\u0438\u043a\u0435\u0440', raw, Path('data/generated'))
            async with session.begin():
                await service.clear_input_state(message.from_user.id)
            await message.answer_photo(FSInputFile(out_file), caption=f"{h('\U0001f3a8 \u0421\u0442\u0438\u043a\u0435\u0440')}\n\u0428\u0430\u0431\u043b\u043e\u043d\u043d\u044b\u0439 \u0441\u0442\u0438\u043a\u0435\u0440 \u0433\u043e\u0442\u043e\u0432.", reply_markup=menu)
            return


        if state.state == 'market_sell_wait':
            parts = [p.strip() for p in raw.split('|')]
            if len(parts) != 3:
                await message.answer(f"{h('💱 Маркет')}\nФормат: `instance_id|coins_or_stars|price`", parse_mode='Markdown', reply_markup=menu)
                return
            instance_id, currency, price = parts
            try:
                instance_id_int = int(instance_id)
                price_int = int(price)
            except ValueError:
                await message.answer(f"{h('💱 Маркет')}\n`instance_id` и `price` должны быть числами.", parse_mode='Markdown', reply_markup=menu)
                return
            async with session.begin():
                ok, resp = await service.market_sell_instance(message.from_user.id, instance_id_int, currency, price_int)
                if ok:
                    await service.clear_input_state(message.from_user.id)
            await message.answer(f"{h('💱 Маркет')}\n{resp}", reply_markup=menu)
            return

        if state.state == 'marriage_propose_wait':
            target = await service.resolve_user_reference(raw)
            if target is None:
                await message.answer(f"{h('💍 Брак')}\nПользователь не найден. Отправьте ID, @username или ссылку.", reply_markup=menu)
                return
            async with session.begin():
                ok, resp = await service.marriage_propose(message.from_user.id, target.id)
                if ok:
                    await service.clear_input_state(message.from_user.id)
            await message.answer(f"{h('💍 Брак')}\n{resp}", reply_markup=menu)
            return

        if state.state == 'admin_rp_category_form':
            if not is_admin_id(message.from_user.id):
                await message.answer('Доступ запрещён.', reply_markup=menu)
                return
            payload = dict(state.payload or {})
            mode = str(payload.get('mode') or 'create')
            parts = [part.strip() for part in raw.split('|')]
            try:
                if mode == 'create':
                    if len(parts) != 5:
                        raise ValueError('format')
                    key, title, emoji, sort_raw, active_raw = parts
                    category = BcRPCategory(key=key, title=title, emoji=emoji or '🎭', sort=int(sort_raw), is_active=admin_parse_bool(active_raw))
                    async with session.begin():
                        session.add(category)
                        await service.clear_input_state(message.from_user.id)
                else:
                    if len(parts) != 4:
                        raise ValueError('format')
                    category = await session.get(BcRPCategory, str(payload.get('key') or ''))
                    if category is None:
                        await message.answer('Категория не найдена.', reply_markup=menu)
                        return
                    async with session.begin():
                        category.title = parts[0]
                        category.emoji = parts[1] or '🎭'
                        category.sort = int(parts[2])
                        category.is_active = admin_parse_bool(parts[3])
                        await service.clear_input_state(message.from_user.id)
                service.invalidate_catalog_cache()
                await message.answer(f"{h('🎭 Категория RP')}\nСохранено.", reply_markup=menu)
                await screen_admin_rp_category(message, category.key)
            except (ValueError, TypeError):
                await message.answer('Формат категории RP неверный.', reply_markup=menu)
            return

        if state.state == 'admin_rp_action_form':
            if not is_admin_id(message.from_user.id):
                await message.answer('Доступ запрещён.', reply_markup=menu)
                return
            payload = dict(state.payload or {})
            mode = str(payload.get('mode') or 'create')
            parts = [part.strip() for part in raw.split('|')]
            try:
                if mode == 'create':
                    if len(parts) != 15:
                        raise ValueError('format')
                    key, category_key, title, emoji, requires_target_raw, cooldown_raw, coins_raw, stars_raw, points_raw, media_raw, private_raw, group_raw, sort_raw, active_raw, templates_raw = parts
                    if await session.get(BcRPCategory, category_key) is None:
                        raise ValueError('category')
                    rp_action = BcRPAction(
                        key=key,
                        category_key=category_key,
                        title=title,
                        emoji=emoji or '✨',
                        requires_target=admin_parse_bool(requires_target_raw),
                        cooldown_seconds=int(cooldown_raw),
                        reward={'coins': int(coins_raw or 0), 'stars': int(stars_raw or 0), 'points': int(points_raw or 0)},
                        templates=[item.strip() for item in templates_raw.split(';;') if item.strip()],
                        media_id=admin_parse_optional_int(media_raw),
                        restrictions={},
                        allowed_scopes={'private': admin_parse_bool(private_raw), 'group': admin_parse_bool(group_raw)},
                        is_active=admin_parse_bool(active_raw),
                        sort=int(sort_raw),
                    )
                    async with session.begin():
                        session.add(rp_action)
                        await service.clear_input_state(message.from_user.id)
                else:
                    if len(parts) != 14:
                        raise ValueError('format')
                    rp_action = await session.get(BcRPAction, str(payload.get('key') or ''))
                    if rp_action is None:
                        await message.answer('RP-действие не найдено.', reply_markup=menu)
                        return
                    if await session.get(BcRPCategory, parts[0]) is None:
                        raise ValueError('category')
                    async with session.begin():
                        rp_action.category_key = parts[0]
                        rp_action.title = parts[1]
                        rp_action.emoji = parts[2] or '✨'
                        rp_action.requires_target = admin_parse_bool(parts[3])
                        rp_action.cooldown_seconds = int(parts[4])
                        rp_action.reward = {'coins': int(parts[5] or 0), 'stars': int(parts[6] or 0), 'points': int(parts[7] or 0)}
                        rp_action.media_id = admin_parse_optional_int(parts[8])
                        rp_action.allowed_scopes = {'private': admin_parse_bool(parts[9]), 'group': admin_parse_bool(parts[10])}
                        rp_action.sort = int(parts[11])
                        rp_action.is_active = admin_parse_bool(parts[12])
                        rp_action.templates = [item.strip() for item in parts[13].split(';;') if item.strip()]
                        await service.clear_input_state(message.from_user.id)
                service.invalidate_catalog_cache()
                await message.answer(f"{h('🎭 RP-действие')}\nСохранено.", reply_markup=menu)
                await screen_admin_rp_action(message, rp_action.key)
            except (ValueError, TypeError):
                await message.answer('Формат RP-действия неверный.', reply_markup=menu)
            return

        if state.state == 'admin_rarity_form':
            if not is_admin_id(message.from_user.id):
                await message.answer('Доступ запрещён.', reply_markup=menu)
                return
            payload = dict(state.payload or {})
            mode = str(payload.get('mode') or 'create')
            parts = [part.strip() for part in raw.split('|')]
            try:
                if mode == 'create':
                    if len(parts) != 10:
                        raise ValueError('format')
                    key, title, emoji, chance_raw, color, points_mult_raw, coins_mult_raw, drop_mode, in_chests_raw, in_shop_raw = parts
                    rarity = BcRarity(key=key, title=title, emoji=emoji or '✨', chance=float(chance_raw), color=color or '#A0A0A0', points_mult=float(points_mult_raw), coins_mult=float(coins_mult_raw), available_in_chests=admin_parse_bool(in_chests_raw), available_in_shop=admin_parse_bool(in_shop_raw), drop_mode=drop_mode or 'normal', sort=100, meta={}, is_active=True)
                    async with session.begin():
                        session.add(rarity)
                        await service.clear_input_state(message.from_user.id)
                else:
                    if len(parts) != 10:
                        raise ValueError('format')
                    rarity = await session.get(BcRarity, str(payload.get('key') or ''))
                    if rarity is None:
                        await message.answer('Редкость не найдена.', reply_markup=menu)
                        return
                    async with session.begin():
                        rarity.title = parts[0]
                        rarity.emoji = parts[1] or '✨'
                        rarity.chance = float(parts[2])
                        rarity.color = parts[3] or '#A0A0A0'
                        rarity.points_mult = float(parts[4])
                        rarity.coins_mult = float(parts[5])
                        rarity.drop_mode = parts[6] or 'normal'
                        rarity.available_in_chests = admin_parse_bool(parts[7])
                        rarity.available_in_shop = admin_parse_bool(parts[8])
                        rarity.is_active = admin_parse_bool(parts[9])
                        await service.clear_input_state(message.from_user.id)
                service.invalidate_catalog_cache()
                await message.answer(f"{h('💎 Редкость')}\nСохранено.", reply_markup=menu)
                await screen_admin_rarity(message, rarity.key)
            except (ValueError, TypeError):
                await message.answer('Формат редкости неверный.', reply_markup=menu)
            return

        if state.state == 'admin_booster_form':
            if not is_admin_id(message.from_user.id):
                await message.answer('Доступ запрещён.', reply_markup=menu)
                return
            payload = dict(state.payload or {})
            mode = str(payload.get('mode') or 'create')
            parts = [part.strip() for part in raw.split('|')]
            try:
                if mode == 'create':
                    if len(parts) != 10:
                        raise ValueError('format')
                    key, title, emoji, effect_type, power_raw, price_coins_raw, price_stars_raw, duration_raw, max_stack_raw, available_raw = parts
                    booster = BcBooster(key=key, title=title, emoji=emoji or '⚡', effect_type=effect_type, effect_power=float(power_raw), price_coins=admin_parse_optional_int(price_coins_raw), price_stars=admin_parse_optional_int(price_stars_raw), duration_seconds=int(duration_raw or 0), stackable=True, max_stack=int(max_stack_raw or 1), purchase_limit=None, is_available=admin_parse_bool(available_raw), event_id=None, meta={})
                    async with session.begin():
                        session.add(booster)
                        await service.clear_input_state(message.from_user.id)
                else:
                    if len(parts) != 9:
                        raise ValueError('format')
                    booster = await session.get(BcBooster, str(payload.get('key') or ''))
                    if booster is None:
                        await message.answer('Бустер не найден.', reply_markup=menu)
                        return
                    async with session.begin():
                        booster.title = parts[0]
                        booster.emoji = parts[1] or '⚡'
                        booster.effect_type = parts[2]
                        booster.effect_power = float(parts[3])
                        booster.price_coins = admin_parse_optional_int(parts[4])
                        booster.price_stars = admin_parse_optional_int(parts[5])
                        booster.duration_seconds = int(parts[6] or 0)
                        booster.max_stack = int(parts[7] or 1)
                        booster.is_available = admin_parse_bool(parts[8])
                        await service.clear_input_state(message.from_user.id)
                service.invalidate_catalog_cache()
                await message.answer(f"{h('⚡ Бустер')}\nСохранено.", reply_markup=menu)
                await screen_admin_booster(message, booster.key)
            except (ValueError, TypeError):
                await message.answer('Формат бустера неверный.', reply_markup=menu)
            return

        if state.state == 'admin_chest_form':
            if not is_admin_id(message.from_user.id):
                await message.answer('Доступ запрещён.', reply_markup=menu)
                return
            payload = dict(state.payload or {})
            mode = str(payload.get('mode') or 'create')
            parts = [part.strip() for part in raw.split('|')]
            try:
                if mode == 'create':
                    if len(parts) != 8:
                        raise ValueError('format')
                    key, title, emoji, description, price_coins_raw, price_stars_raw, open_count_raw, drops_raw = parts
                    drops = admin_parse_chest_drops(drops_raw)
                    chest = BcChest(key=key, title=title, emoji=emoji or '📦', description=description, price_coins=admin_parse_optional_int(price_coins_raw), price_stars=admin_parse_optional_int(price_stars_raw), open_count=int(open_count_raw or 1), guarantees={}, limits={}, media_id=None, access={}, is_active=True, sort=100)
                    async with session.begin():
                        session.add(chest)
                        await session.flush()
                        for rarity_key, weight, min_count, max_count in drops:
                            session.add(BcChestDrop(chest_key=chest.key, rarity_key=rarity_key, weight=weight, min_count=min_count, max_count=max_count, meta={}))
                        await service.clear_input_state(message.from_user.id)
                else:
                    if len(parts) != 7:
                        raise ValueError('format')
                    chest = await session.get(BcChest, str(payload.get('key') or ''))
                    if chest is None:
                        await message.answer('Сундук не найден.', reply_markup=menu)
                        return
                    async with session.begin():
                        chest.title = parts[0]
                        chest.emoji = parts[1] or '📦'
                        chest.description = parts[2]
                        chest.price_coins = admin_parse_optional_int(parts[3])
                        chest.price_stars = admin_parse_optional_int(parts[4])
                        chest.open_count = int(parts[5] or 1)
                        chest.is_active = admin_parse_bool(parts[6])
                        await service.clear_input_state(message.from_user.id)
                service.invalidate_catalog_cache()
                await message.answer(f"{h('📦 Сундук')}\nСохранено.", reply_markup=menu)
                await screen_admin_chest(message, chest.key)
            except (ValueError, TypeError):
                await message.answer('Формат сундука неверный.', reply_markup=menu)
            return

        if state.state == 'admin_chest_drops_form':
            if not is_admin_id(message.from_user.id):
                await message.answer('Доступ запрещён.', reply_markup=menu)
                return
            payload = dict(state.payload or {})
            chest_key = str(payload.get('key') or '')
            chest = await session.get(BcChest, chest_key)
            if chest is None:
                await message.answer('Сундук не найден.', reply_markup=menu)
                return
            try:
                drops = admin_parse_chest_drops(raw)
                async with session.begin():
                    existing = (await session.scalars(select(BcChestDrop).where(BcChestDrop.chest_key == chest.key))).all()
                    for row in existing:
                        await session.delete(row)
                    for rarity_key, weight, min_count, max_count in drops:
                        session.add(BcChestDrop(chest_key=chest.key, rarity_key=rarity_key, weight=weight, min_count=min_count, max_count=max_count, meta={}))
                    await service.clear_input_state(message.from_user.id)
                service.invalidate_catalog_cache()
                await message.answer(f"{h('🎯 Дроп сундука')}\nТаблица обновлена.", reply_markup=menu)
                await screen_admin_chest(message, chest.key)
            except (ValueError, TypeError):
                await message.answer('Формат дропа неверный.', reply_markup=menu)
            return

        if state.state == 'admin_shop_category_form':
            if not is_admin_id(message.from_user.id):
                await message.answer('Доступ запрещён.', reply_markup=menu)
                return
            payload = dict(state.payload or {})
            mode = str(payload.get('mode') or 'create')
            parts = [part.strip() for part in raw.split('|')]
            try:
                if mode == 'create':
                    if len(parts) != 5:
                        raise ValueError('format')
                    key, title, emoji, sort_raw, active_raw = parts
                    category = BcShopCategory(key=key, title=title, emoji=emoji or '🛒', sort=int(sort_raw), is_active=admin_parse_bool(active_raw))
                    async with session.begin():
                        session.add(category)
                        await service.clear_input_state(message.from_user.id)
                else:
                    if len(parts) != 4:
                        raise ValueError('format')
                    category = await session.get(BcShopCategory, str(payload.get('key') or ''))
                    if category is None:
                        await message.answer('Категория не найдена.', reply_markup=menu)
                        return
                    async with session.begin():
                        category.title = parts[0]
                        category.emoji = parts[1] or '🛒'
                        category.sort = int(parts[2])
                        category.is_active = admin_parse_bool(parts[3])
                        await service.clear_input_state(message.from_user.id)
                service.invalidate_catalog_cache()
                await message.answer(f"{h('🛒 Категория магазина')}\nСохранено.", reply_markup=menu)
                await screen_admin_shop_category(message, category.key)
            except (ValueError, TypeError):
                await message.answer('Формат категории магазина неверный.', reply_markup=menu)
            return

        if state.state == 'admin_shop_item_form':
            if not is_admin_id(message.from_user.id):
                await message.answer('Доступ запрещён.', reply_markup=menu)
                return
            payload = dict(state.payload or {})
            mode = str(payload.get('mode') or 'create')
            parts = [part.strip() for part in raw.split('|')]
            try:
                preset_category = str(payload.get('category_key') or '').strip()
                if mode == 'create':
                    if preset_category:
                        if len(parts) != 11:
                            raise ValueError('format')
                        category_key = preset_category
                        key, title, description, price_coins_raw, price_stars_raw, duration_raw, payload_type, payload_ref, payload_value, sort_raw, active_raw = parts
                    else:
                        if len(parts) != 12:
                            raise ValueError('format')
                        category_key, key, title, description, price_coins_raw, price_stars_raw, duration_raw, payload_type, payload_ref, payload_value, sort_raw, active_raw = parts
                    if await session.get(BcShopCategory, category_key) is None:
                        raise ValueError('category')
                    item = BcShopItem(category_key=category_key, key=key, title=title, description=description, price_coins=admin_parse_optional_int(price_coins_raw), price_stars=admin_parse_optional_int(price_stars_raw), duration_seconds=admin_parse_optional_int(duration_raw), payload=admin_build_shop_payload(payload_type, payload_ref, payload_value), is_active=admin_parse_bool(active_raw), sort=int(sort_raw))
                    async with session.begin():
                        session.add(item)
                        await service.clear_input_state(message.from_user.id)
                else:
                    if len(parts) != 12:
                        raise ValueError('format')
                    item = await session.get(BcShopItem, int(payload.get('id') or 0))
                    if item is None:
                        await message.answer('Товар не найден.', reply_markup=menu)
                        return
                    category_key, key, title, description, price_coins_raw, price_stars_raw, duration_raw, payload_type, payload_ref, payload_value, sort_raw, active_raw = parts
                    if await session.get(BcShopCategory, category_key) is None:
                        raise ValueError('category')
                    async with session.begin():
                        item.category_key = category_key
                        item.key = key
                        item.title = title
                        item.description = description
                        item.price_coins = admin_parse_optional_int(price_coins_raw)
                        item.price_stars = admin_parse_optional_int(price_stars_raw)
                        item.duration_seconds = admin_parse_optional_int(duration_raw)
                        item.payload = admin_build_shop_payload(payload_type, payload_ref, payload_value)
                        item.sort = int(sort_raw)
                        item.is_active = admin_parse_bool(active_raw)
                        await service.clear_input_state(message.from_user.id)
                service.invalidate_catalog_cache()
                await message.answer(f"{h('🛍 Товар магазина')}\nСохранено.", reply_markup=menu)
                await screen_admin_shop_item(message, item.id)
            except (ValueError, TypeError):
                await message.answer('Формат товара магазина неверный.', reply_markup=menu)
            return

        if state.state == 'admin_task_form':
            if not is_admin_id(message.from_user.id):
                await message.answer('Доступ запрещён.', reply_markup=menu)
                return
            payload = dict(state.payload or {})
            mode = str(payload.get('mode') or 'create')
            parts = [part.strip() for part in raw.split('|')]
            try:
                if mode == 'create':
                    if len(parts) != 11:
                        raise ValueError('format')
                    key, kind, title, description, target_raw, coins_raw, stars_raw, points_raw, counter_key, sort_raw, active_raw = parts
                    task = BcTask(key=key, kind=kind, title=title, description=description, target=int(target_raw), reward={'coins': int(coins_raw or 0), 'stars': int(stars_raw or 0), 'points': int(points_raw or 0)}, expires_at=None, check_type='counter', config={'counter': counter_key}, is_active=admin_parse_bool(active_raw), sort=int(sort_raw))
                    async with session.begin():
                        session.add(task)
                        await service.clear_input_state(message.from_user.id)
                else:
                    if len(parts) != 10:
                        raise ValueError('format')
                    task = await session.get(BcTask, str(payload.get('key') or ''))
                    if task is None:
                        await message.answer('Задание не найдено.', reply_markup=menu)
                        return
                    async with session.begin():
                        task.kind = parts[0]
                        task.title = parts[1]
                        task.description = parts[2]
                        task.target = int(parts[3])
                        task.reward = {'coins': int(parts[4] or 0), 'stars': int(parts[5] or 0), 'points': int(parts[6] or 0)}
                        task.config = {'counter': parts[7]}
                        task.sort = int(parts[8])
                        task.is_active = admin_parse_bool(parts[9])
                        await service.clear_input_state(message.from_user.id)
                service.invalidate_catalog_cache()
                await message.answer(f"{h('📜 Задание')}\nСохранено.", reply_markup=menu)
                await screen_admin_task(message, task.key)
            except (ValueError, TypeError):
                await message.answer('Формат задания неверный.', reply_markup=menu)
            return

        if state.state == 'admin_event_form':
            if not is_admin_id(message.from_user.id):
                await message.answer('Доступ запрещён.', reply_markup=menu)
                return
            payload = dict(state.payload or {})
            mode = str(payload.get('mode') or 'create')
            parts = [part.strip() for part in raw.split('|')]
            try:
                if mode == 'create':
                    if len(parts) != 6:
                        raise ValueError('format')
                    key, title, description, starts_raw, ends_raw, active_raw = parts
                    event = BcEvent(key=key, title=title, description=description, starts_at=admin_parse_optional_datetime(starts_raw), ends_at=admin_parse_optional_datetime(ends_raw), config={}, is_active=admin_parse_bool(active_raw))
                    async with session.begin():
                        session.add(event)
                        await service.clear_input_state(message.from_user.id)
                else:
                    if len(parts) != 5:
                        raise ValueError('format')
                    event = await session.scalar(select(BcEvent).where(BcEvent.key == str(payload.get('key') or '')))
                    if event is None:
                        await message.answer('Ивент не найден.', reply_markup=menu)
                        return
                    async with session.begin():
                        event.title = parts[0]
                        event.description = parts[1]
                        event.starts_at = admin_parse_optional_datetime(parts[2])
                        event.ends_at = admin_parse_optional_datetime(parts[3])
                        event.is_active = admin_parse_bool(parts[4])
                        await service.clear_input_state(message.from_user.id)
                service.invalidate_catalog_cache()
                await message.answer(f"{h('🎉 Ивент')}\nСохранено.", reply_markup=menu)
                await screen_admin_event(message, event.key)
            except (ValueError, TypeError):
                await message.answer('Формат ивента неверный.', reply_markup=menu)
            return

        if state.state == 'admin_role_form':
            if not is_admin_id(message.from_user.id):
                await message.answer('Доступ запрещён.', reply_markup=menu)
                return
            payload = dict(state.payload or {})
            mode = str(payload.get('mode') or 'create')
            parts = [part.strip() for part in raw.split('|')]
            try:
                if mode == 'create':
                    if len(parts) != 2:
                        raise ValueError('format')
                    role = BcRole(key=parts[0], title=parts[1], meta={})
                    async with session.begin():
                        session.add(role)
                        await service.clear_input_state(message.from_user.id)
                else:
                    role = await session.get(BcRole, str(payload.get('key') or ''))
                    if role is None:
                        await message.answer('Роль не найдена.', reply_markup=menu)
                        return
                    async with session.begin():
                        role.title = raw
                        await service.clear_input_state(message.from_user.id)
                await message.answer(f"{h('🔐 Роль')}\nСохранено.", reply_markup=menu)
                await screen_admin_role(message, role.key)
            except (ValueError, TypeError):
                await message.answer('Формат роли неверный.', reply_markup=menu)
            return

        if state.state == 'admin_permission_form':
            if not is_admin_id(message.from_user.id):
                await message.answer('Доступ запрещён.', reply_markup=menu)
                return
            payload = dict(state.payload or {})
            mode = str(payload.get('mode') or 'create')
            parts = [part.strip() for part in raw.split('|')]
            try:
                if mode == 'create':
                    if len(parts) != 2:
                        raise ValueError('format')
                    permission = BcPermission(code=parts[0], title=parts[1])
                    async with session.begin():
                        session.add(permission)
                        await service.clear_input_state(message.from_user.id)
                else:
                    permission = await session.get(BcPermission, str(payload.get('code') or ''))
                    if permission is None:
                        await message.answer('Право не найдено.', reply_markup=menu)
                        return
                    async with session.begin():
                        permission.title = raw
                        await service.clear_input_state(message.from_user.id)
                await message.answer(f"{h('🔐 Право')}\nСохранено.", reply_markup=menu)
                await screen_admin_permission(message, permission.code)
            except (ValueError, TypeError):
                await message.answer('Формат права неверный.', reply_markup=menu)
            return

        if state.state == 'admin_role_grant_form':
            if not is_admin_id(message.from_user.id):
                await message.answer('Доступ запрещён.', reply_markup=menu)
                return
            parts = [part.strip() for part in raw.split('|')]
            if len(parts) != 3:
                await message.answer('Формат роли неверный: `user_id|role_key|grant_or_revoke`', parse_mode='Markdown', reply_markup=menu)
                return
            try:
                user_id = int(parts[0])
                role_key = parts[1]
                mode = parts[2].lower()
                if await session.get(BcRole, role_key) is None:
                    raise ValueError('role')
                async with session.begin():
                    row = await session.get(BcUserRole, {'user_id': user_id, 'role_key': role_key})
                    if mode == 'grant' and row is None:
                        session.add(BcUserRole(user_id=user_id, role_key=role_key))
                    elif mode == 'revoke' and row is not None:
                        await session.delete(row)
                    else:
                        raise ValueError('mode')
                    await service.clear_input_state(message.from_user.id)
                await message.answer(f"{h('👤 Выдача роли')}\nОперация выполнена.", reply_markup=menu)
                await screen_admin_role(message, role_key)
            except (ValueError, TypeError):
                await message.answer('Формат выдачи роли неверный.', reply_markup=menu)
            return

        if state.state == 'admin_role_permission_form':
            if not is_admin_id(message.from_user.id):
                await message.answer('Доступ запрещён.', reply_markup=menu)
                return
            parts = [part.strip() for part in raw.split('|')]
            if len(parts) != 3:
                await message.answer('Формат привязки неверный: `role_key|permission_code|grant_or_revoke`', parse_mode='Markdown', reply_markup=menu)
                return
            role_key, permission_code, mode = parts[0], parts[1], parts[2].lower()
            try:
                if await session.get(BcRole, role_key) is None or await session.get(BcPermission, permission_code) is None:
                    raise ValueError('link')
                async with session.begin():
                    row = await session.get(BcRolePermission, {'role_key': role_key, 'permission_code': permission_code})
                    if mode == 'grant' and row is None:
                        session.add(BcRolePermission(role_key=role_key, permission_code=permission_code))
                    elif mode == 'revoke' and row is not None:
                        await session.delete(row)
                    else:
                        raise ValueError('mode')
                    await service.clear_input_state(message.from_user.id)
                await message.answer(f"{h('🔗 Привязка права')}\nОперация выполнена.", reply_markup=menu)
                await screen_admin_role(message, role_key)
            except (ValueError, TypeError):
                await message.answer('Формат привязки права неверный.', reply_markup=menu)
            return

        if state.state == 'admin_media_form':
            if not is_admin_id(message.from_user.id):
                await message.answer('Доступ запрещён.', reply_markup=menu)
                return
            payload = dict(state.payload or {})
            mode = str(payload.get('mode') or 'create')
            parts = [part.strip() for part in raw.split('|')]
            try:
                if len(parts) != 4:
                    raise ValueError('format')
                kind, title, url_raw, active_raw = parts
                if mode == 'create':
                    media = BcMedia(kind=kind, telegram_file_id=None, url=None if url_raw == '-' else url_raw, title=title, meta={}, is_active=admin_parse_bool(active_raw))
                    async with session.begin():
                        session.add(media)
                        await session.flush()
                        await service.clear_input_state(message.from_user.id)
                else:
                    media = await session.get(BcMedia, int(payload.get('id') or 0))
                    if media is None:
                        await message.answer('Медиа не найдено.', reply_markup=menu)
                        return
                    async with session.begin():
                        media.kind = kind
                        media.title = title
                        media.url = None if url_raw == '-' else url_raw
                        media.is_active = admin_parse_bool(active_raw)
                        await service.clear_input_state(message.from_user.id)
                service.invalidate_catalog_cache()
                await message.answer(f"{h('🖼 Медиа')}\nСохранено.", reply_markup=menu)
                await screen_admin_media(message, media.id)
            except (ValueError, TypeError):
                await message.answer('Формат медиа неверный.', reply_markup=menu)
            return

        if state.state == 'admin_user_manage_form':
            if not is_admin_id(message.from_user.id):
                await message.answer('Доступ запрещён.', reply_markup=menu)
                return
            parts = [part.strip() for part in raw.split('|', maxsplit=2)]
            if len(parts) != 3:
                await message.answer(
                    f"{h('👥 Управление пользователем')}\nНужен формат: `user_id|field|value`",
                    parse_mode='Markdown',
                    reply_markup=menu,
                )
                return
            try:
                target_user_id = int(parts[0])
            except ValueError:
                await message.answer(
                    f"{h('👥 Управление пользователем')}\n`user_id` должен быть числом.",
                    parse_mode='Markdown',
                    reply_markup=menu,
                )
                return
            async with session.begin():
                ok, resp = await service.admin_update_user(target_user_id, parts[1], parts[2])
                if ok:
                    await service.clear_input_state(message.from_user.id)
            await message.answer(f"{h('👥 Управление пользователем')}\n{resp}", reply_markup=menu)
            return

        if state.state == 'admin_system_form':
            if not is_admin_id(message.from_user.id):
                await message.answer('Доступ запрещён.', reply_markup=menu)
                return
            payload = dict(state.payload or {})
            section = str(payload.get('section') or '').strip()
            maxsplit = 1
            if section == 'main_menu_items':
                maxsplit = 3
            elif section == 'admin_menu_items':
                maxsplit = 2
            parts = [part.strip() for part in raw.split('|', maxsplit=maxsplit)]
            if len(parts) < 2:
                await message.answer(
                    f"{h('⚙️ Системная настройка')}\nНеверный формат для выбранного раздела.",
                    parse_mode='Markdown',
                    reply_markup=menu,
                )
                return
            key = parts[0]
            if not key:
                await message.answer('Ключ не указан.', reply_markup=menu)
                return
            if section == 'button_labels' and key not in DEFAULT_BUTTON_LABELS:
                await message.answer(
                    f"{h('🔘 Подписи кнопок')}\nКлюч не поддерживается этим UI-контуром.",
                    reply_markup=menu,
                )
                return
            try:
                if section in {'cooldowns', 'rewards'}:
                    value_raw = parts[1]
                    value: object = int(value_raw)
                elif section == 'button_labels':
                    value_raw = parts[1]
                    value = DEFAULT_BUTTON_LABELS[key] if value_raw == '-' else value_raw
                    if not str(value).strip():
                        await message.answer('Текст кнопки не может быть пустым.', reply_markup=menu)
                        return
                elif section == 'input_placeholders':
                    if key not in DEFAULT_INPUT_PLACEHOLDERS:
                        await message.answer('Placeholder с таким ключом не поддерживается.', reply_markup=menu)
                        return
                    value_raw = parts[1]
                    value = DEFAULT_INPUT_PLACEHOLDERS[key] if value_raw == '-' else value_raw
                    if not str(value).strip():
                        await message.answer('Placeholder не может быть пустым.', reply_markup=menu)
                        return
                elif section == 'feature_flags':
                    current = await service.get_system_section(section)
                    if key not in current:
                        await message.answer('Feature flag не найден.', reply_markup=menu)
                        return
                    value = admin_parse_bool(parts[1])
                elif section == 'main_menu_items':
                    if key not in DEFAULT_MAIN_MENU_CONFIG:
                        await message.answer('Элемент главного меню не найден.', reply_markup=menu)
                        return
                    if len(parts) != 4:
                        await message.answer('Нужен формат: `key|order|visible(0/1)|admin_only(0/1)`', parse_mode='Markdown', reply_markup=menu)
                        return
                    current = await service.get_system_section(section)
                    value = {
                        'order': int(parts[1]),
                        'visible': admin_parse_bool(parts[2]),
                        'admin_only': admin_parse_bool(parts[3]),
                    }
                    current[key] = value
                    async with session.begin():
                        await service.set_system_section(section, current)
                        await service.clear_input_state(message.from_user.id)
                    await message.answer(
                        f"{h('⚙️ Настройки бота')}\nСохранено меню: {key}",
                        reply_markup=menu,
                    )
                    return
                elif section == 'admin_menu_items':
                    if key not in DEFAULT_ADMIN_MENU_CONFIG:
                        await message.answer('Элемент admin-меню не найден.', reply_markup=menu)
                        return
                    if len(parts) != 3:
                        await message.answer('Нужен формат: `key|order|visible(0/1)`', parse_mode='Markdown', reply_markup=menu)
                        return
                    current = await service.get_system_section(section)
                    value = {
                        'order': int(parts[1]),
                        'visible': admin_parse_bool(parts[2]),
                    }
                    current[key] = value
                    async with session.begin():
                        await service.set_system_section(section, current)
                        await service.clear_input_state(message.from_user.id)
                    await message.answer(
                        f"{h('⚙️ Настройки бота')}\nСохранено admin-меню: {key}",
                        reply_markup=menu,
                    )
                    return
                elif section == 'bonus_links':
                    value_raw = parts[1]
                    value = '' if value_raw == '-' else value_raw
                else:
                    await message.answer('Неизвестный раздел настроек.', reply_markup=menu)
                    return
            except ValueError:
                await message.answer('Значение имеет неверный формат.', reply_markup=menu)
                return
            async with session.begin():
                updated = await service.set_system_value(section, key, value)
                await service.clear_input_state(message.from_user.id)
            await message.answer(
                f"{h('⚙️ Настройки бота')}\nСохранено: {key} = {updated.get(key)}",
                reply_markup=menu,
            )
            return

        if state.state == 'admin_template_pick_form':
            if not is_admin_id(message.from_user.id):
                await message.answer('Доступ запрещён.', reply_markup=menu)
                return
            parts = [part.strip() for part in raw.split('|', maxsplit=1)]
            if len(parts) != 2:
                await message.answer('Нужен формат: `template_key|locale`', parse_mode='Markdown', reply_markup=menu)
                return
            template_key, locale = parts[0], parts[1] or 'ru'
            if not template_key:
                await message.answer('Ключ шаблона пустой.', reply_markup=menu)
                return
            current_text = await service.get_template_text(
                template_key,
                locale,
                DEFAULT_TEXT_TEMPLATES.get(template_key, ''),
            )
            async with session.begin():
                await service.set_input_state(message.from_user.id, 'admin_template_form', {'key': template_key, 'locale': locale})
            await message.answer(
                f"{h('📝 Редактор шаблона')}\nКлюч: {template_key}\nЛокаль: {locale}\n\nОтправьте новый текст одним сообщением.\n\nТекущее значение:\n{current_text}",
                reply_markup=menu,
            )
            return

        if state.state == 'admin_template_form':
            if not is_admin_id(message.from_user.id):
                await message.answer('Доступ запрещён.', reply_markup=menu)
                return
            payload = dict(state.payload or {})
            template_key = str(payload.get('key') or '').strip()
            locale = str(payload.get('locale') or 'ru').strip() or 'ru'
            if not template_key:
                await message.answer('Ключ шаблона не найден.', reply_markup=menu)
                return
            text_value = DEFAULT_TEXT_TEMPLATES.get(template_key, '') if raw == '-' else raw
            if not text_value.strip():
                await message.answer('Текст шаблона не может быть пустым.', reply_markup=menu)
                return
            async with session.begin():
                await service.upsert_template_text(template_key, locale, text_value)
                await service.clear_input_state(message.from_user.id)
            await message.answer(
                f"{h('📝 Редактор шаблона')}\nШаблон {template_key} обновлён.",
                reply_markup=menu,
            )
            return

        if state.state == 'admin_broadcast_form':
            if not is_admin_id(message.from_user.id):
                await message.answer('Доступ запрещён.', reply_markup=menu)
                return
            text_value = raw.strip()
            if not text_value:
                await message.answer('Текст рассылки пустой.', reply_markup=menu)
                return
            async with session.begin():
                await service.clear_input_state(message.from_user.id)
            asyncio.create_task(run_text_broadcast(message.bot, message.from_user.id, text_value))
            await message.answer(
                f"{h('📢 Рассылка')}\nЗадача запущена. Отчёт придёт отдельным сообщением.",
                reply_markup=menu,
            )
            return

        if state.state == 'admin_card_wizard':
            if not is_admin_id(message.from_user.id):
                await message.answer('Доступ запрещён.', reply_markup=menu)
                return
            result = await consume_admin_card_wizard_input(session, service, message.from_user.id, raw)
            await session.commit()
            if result.get('done'):
                service.invalidate_catalog_cache()
            await message.answer(
                result['text'],
                parse_mode=result.get('parse_mode'),
                reply_markup=result.get('reply_markup') or menu,
            )
            if result.get('done') and result.get('card_id'):
                await screen_admin_card(message, int(result['card_id']))
            return

@router.message(F.photo)
async def on_photo_input(message: Message) -> None:
    if message.from_user is None or not message.photo:
        return
    menu = user_menu(message.from_user.id, chat_type_of(message))
    async with SessionLocal() as session:
        service = BrawlCardsService(session)
        state = await service.get_input_state(message.from_user.id)
        if state is None or not is_admin_id(message.from_user.id):
            return
        file_id = message.photo[-1].file_id
        if state.state == 'admin_card_wizard':
            payload = dict(state.payload or {})
            if str(payload.get('step') or '') != 'photo':
                return
            data = dict(payload.get('data') or {})
            data['photo'] = file_id
            payload['data'] = data
            ok, resp, card_id = await save_card_wizard_payload(session, service, message.from_user.id, payload)
            await session.commit()
            if ok:
                service.invalidate_catalog_cache()
            await message.answer(resp, reply_markup=menu)
            if ok and card_id:
                await screen_admin_card(message, int(card_id))
            return
        if state.state == 'admin_card_photo':
            payload = dict(state.payload or {})
            card_id = int(payload.get('id') or 0)
            card = await session.get(BcCard, card_id)
            if card is None:
                await service.clear_input_state(message.from_user.id)
                await session.commit()
                await message.answer('Карточка не найдена.', reply_markup=menu)
                return
            card.image_file_id = file_id
            await service.clear_input_state(message.from_user.id)
            await session.commit()
            service.invalidate_catalog_cache()
            await message.answer('Фото карточки обновлено.', reply_markup=menu)
            await screen_admin_card(message, card_id)
            return
        if state.state == 'admin_media_file_form':
            payload = dict(state.payload or {})
            media_id = int(payload.get('id') or 0)
            media = await session.get(BcMedia, media_id)
            if media is None:
                await service.clear_input_state(message.from_user.id)
                await session.commit()
                await message.answer('Медиа не найдено.', reply_markup=menu)
                return
            media.kind = 'photo'
            media.telegram_file_id = file_id
            await service.clear_input_state(message.from_user.id)
            await session.commit()
            service.invalidate_catalog_cache()
            await message.answer('Медиа-файл обновлён.', reply_markup=menu)
            await screen_admin_media(message, media_id)
            return
