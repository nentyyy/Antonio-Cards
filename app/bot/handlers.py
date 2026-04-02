from __future__ import annotations
import asyncio
from pathlib import Path
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, Message, PreCheckoutQuery, ReplyKeyboardMarkup
from sqlalchemy import and_, func, select
from app.bot.context import display_name, ensure_user, h, is_admin_id, safe_callback_answer
from app.bot.keyboards import MAIN_MENU_BUTTONS, ik_admin_card_wizard, ik_admin_main, ik_bonus_tasks, ik_games_menu, ik_game_stakes, ik_get_card, ik_list_nav, ik_marriage_menu, ik_marriage_proposal, ik_market_lot_actions, ik_market_menu, ik_profile, ik_quote_menu, ik_rp_actions, ik_rp_categories, ik_shop_categories, ik_sticker_menu, ik_nav, main_menu, screen_by_main_menu_button
from app.bot.screens.core import handle_start_command, render_help_screen, screen_main, screen_nick, screen_profile
from app.bot.screens.leaderboards import screen_top, screen_top_metric
from app.bot.screens.settings import render_settings_screen
from app.bot.ui_defaults import DEFAULT_BUTTON_LABELS, DEFAULT_TEXT_TEMPLATES
from app.application.guards import user_action_guard
from app.config import get_settings
from app.db.models import BcActiveBooster, BcAuditLog, BcBonusTask, BcBooster, BcCard, BcCardInstance, BcChest, BcChestDrop, BcEvent, BcInputState, BcLimitedSeries, BcMarriageProposal, BcMedia, BcMarketLot, BcPermission, BcRole, BcRolePermission, BcRPAction, BcRPCategory, BcRarity, BcShopCategory, BcShopItem, BcTask, BcUserRole, BcUserState, BcUserSettings, Marriage, User, UserProfile
from app.db.session import SessionLocal
from app.services.brawl_cards_service import BrawlCardsService
from app.services.broadcast_service import run_text_broadcast
from app.utils.sticker import build_card_image
from app.utils.time import seconds_to_hms
router = Router(name='brawl_cards_user_bot')


def user_menu(user_id: int | None) -> ReplyKeyboardMarkup:
    return main_menu(is_admin=is_admin_id(user_id or 0))


async def send_rp_result(message: Message, text: str, media: BcMedia | None=None) -> None:
    reply_markup = user_menu(message.from_user.id if message.from_user else None)
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
        btns = [(t.key, f"{t.emoji} {t.title}") for t in tasks]
    text = f"{h('\U0001f381 \u0411\u043e\u043d\u0443\u0441')}\n\u0417\u0434\u0435\u0441\u044c \u0432\u044b \u043c\u043e\u0436\u0435\u0442\u0435 \u0432\u044b\u043f\u043e\u043b\u043d\u0438\u0442\u044c \u0431\u043e\u043d\u0443\u0441\u043d\u044b\u0435 \u0437\u0430\u0434\u0430\u043d\u0438\u044f \u0438 \u043f\u043e\u043b\u0443\u0447\u0438\u0442\u044c \u043d\u0430\u0433\u0440\u0430\u0434\u044b."
    await message.answer(text, reply_markup=ik_bonus_tasks(btns))

async def screen_shop(message: Message) -> None:
    if message.from_user is None:
        return
    await ensure_user(message)
    async with SessionLocal() as session:
        service = BrawlCardsService(session)
        categories = await service.shop_categories()
    lines = [
        h("\U0001f6d2 \u041c\u0430\u0433\u0430\u0437\u0438\u043d"),
        "\u0417\u0434\u0435\u0441\u044c \u0434\u043e\u0441\u0442\u0443\u043f\u043d\u044b \u043e\u0444\u0444\u0435\u0440\u044b, \u0441\u0443\u043d\u0434\u0443\u043a\u0438, \u0431\u0443\u0441\u0442\u0435\u0440\u044b, Premium \u0438 \u0432\u0430\u043b\u044e\u0442\u0430.",
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
        items = [(c.key, f"{c.emoji} {c.title}") for c in chests]
    text = f"{h('\U0001f4e6 \u0421\u0443\u043d\u0434\u0443\u043a\u0438')}\n\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0441\u0443\u043d\u0434\u0443\u043a \u0434\u043b\u044f \u043e\u0442\u043a\u0440\u044b\u0442\u0438\u044f."
    await message.answer(text, reply_markup=ik_list_nav(items, prefix='nav:chest', back_to='main'))

async def screen_premium(message: Message) -> None:
    text = (
        f"{h('\U0001f48e \u041f\u0440\u0435\u043c\u0438\u0443\u043c')}\n"
        "\u041f\u0440\u0435\u0438\u043c\u0443\u0449\u0435\u0441\u0442\u0432\u0430:\n"
        "\u2022 \u043c\u0435\u043d\u044c\u0448\u0435 \u043a\u0443\u043b\u0434\u0430\u0443\u043d \u043d\u0430 \u043f\u043e\u043b\u0443\u0447\u0435\u043d\u0438\u0435 \u043a\u0430\u0440\u0442\u043e\u0447\u0435\u043a\n"
        "\u2022 \u0432\u044b\u0448\u0435 \u0448\u0430\u043d\u0441 \u0440\u0435\u0434\u043a\u0438\u0445 \u043a\u0430\u0440\u0442\u043e\u0447\u0435\u043a\n"
        "\u2022 \u044d\u043c\u043e\u0434\u0437\u0438 \u0432 \u043d\u0438\u043a\u0435\n"
        "\u2022 \u0437\u043d\u0430\u0447\u043e\u043a \u0432 \u0442\u043e\u043f\u0430\u0445\n"
        "\u2022 \u0431\u043e\u043b\u044c\u0448\u0435 \u043c\u043e\u043d\u0435\u0442 \u0437\u0430 \u043a\u0430\u0440\u0442\u043e\u0447\u043a\u0438\n"
        "\u2022 \u043c\u0435\u043d\u044c\u0448\u0435 \u043a\u0443\u043b\u0434\u0430\u0443\u043d\u044b \u0432 \u0438\u0433\u0440\u0430\u0445\n"
        "\u2022 \u044d\u043a\u0441\u043a\u043b\u044e\u0437\u0438\u0432\u043d\u044b\u0435 RP-\u0432\u043e\u0437\u043c\u043e\u0436\u043d\u043e\u0441\u0442\u0438\n"
        "\u2022 \u0440\u0430\u043c\u043a\u0438 \u043f\u0440\u043e\u0444\u0438\u043b\u044f \u0438 \u043f\u0435\u0440\u0441\u043e\u043d\u0430\u043b\u0438\u0437\u0430\u0446\u0438\u044f\n\n"
        "\u041f\u043e\u043a\u0443\u043f\u043a\u0430 \u0434\u043e\u0441\u0442\u0443\u043f\u043d\u0430 \u0432 \u043c\u0430\u0433\u0430\u0437\u0438\u043d\u0435: \u00ab\U0001f48e \u041f\u0440\u0435\u043c\u0438\u0443\u043c\u00bb."
    )
    await message.answer(text, reply_markup=ik_shop_categories())

async def screen_tasks(message: Message) -> None:
    if message.from_user is None:
        return
    await ensure_user(message)
    async with SessionLocal() as session:
        service = BrawlCardsService(session)
        async with session.begin():
            tasks = await service.tasks()
            lines: list[str] = [h('\U0001f4dc \u0417\u0430\u0434\u0430\u043d\u0438\u044f'), '\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0437\u0430\u0434\u0430\u043d\u0438\u0435 \u0438 \u043f\u043e\u043b\u0443\u0447\u0438\u0442\u0435 \u043d\u0430\u0433\u0440\u0430\u0434\u0443:']
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
        items = [(c.key, f"{c.emoji} {c.title}") for c in categories]
    text = (
        f"{h('🎭 RP')}\n"
        "Выберите категорию RP-действий.\n"
        "Если действию нужна цель, используйте reply в чате или укажите ID/@username после выбора."
    )
    await message.answer(text, reply_markup=ik_rp_categories(items))

async def screen_quote(message: Message) -> None:
    text = (
        f"{h('💬 Цитата')}\n"
        "Выберите источник цитаты: последняя карточка или свой текст.\n"
        "После выбора бот сформирует готовую цитату отдельным сообщением."
    )
    await message.answer(text, reply_markup=ik_quote_menu())

async def screen_sticker(message: Message) -> None:
    text = (
        f"{h('🎨 Стикер')}\n"
        "Выберите сценарий генерации стикера.\n"
        "Можно собрать стикер по последней карточке или по своему текстовому шаблону."
    )
    await message.answer(text, reply_markup=ik_sticker_menu())

async def screen_games(message: Message) -> None:
    text = (
        f"{h('🎮 Игры')}\n"
        "Здесь доступны только реальные Telegram-игры.\n"
        "Результат берётся из фактического emoji-броска Telegram, а не из локального рандома.\n\n"
        "Доступно:\n"
        "• 🎲 Кости\n"
        "• 🎰 Слоты\n"
        "• 🎯 Дартс\n"
        "• ⚽ Футбол\n"
        "• 🏀 Баскетбол"
    )
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
    text = f"{h('\U0001f4b1 \u041c\u0430\u0440\u043a\u0435\u0442')}\n\u0422\u043e\u0440\u0433\u043e\u0432\u0430\u044f \u043f\u043b\u043e\u0449\u0430\u0434\u043a\u0430: \u043f\u043e\u043a\u0443\u043f\u043a\u0430, \u043f\u0440\u043e\u0434\u0430\u0436\u0430, \u043f\u043e\u0438\u0441\u043a \u0438 \u0438\u0441\u0442\u043e\u0440\u0438\u044f \u043b\u043e\u0442\u043e\u0432."
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
        rows = await service.market_lots(active_only=False, limit=100)
        target = next(((lot, card, seller) for lot, card, seller in rows if lot.id == lot_id), None)
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
    text = f"{h('\U0001f48d \u0411\u0440\u0430\u043a')}\n\u0417\u0434\u0435\u0441\u044c \u043c\u043e\u0436\u043d\u043e \u0441\u0434\u0435\u043b\u0430\u0442\u044c \u043f\u0440\u0435\u0434\u043b\u043e\u0436\u0435\u043d\u0438\u0435, \u043e\u0442\u043a\u0440\u044b\u0442\u044c \u043f\u0440\u043e\u0444\u0438\u043b\u044c \u043f\u0430\u0440\u044b \u0438 \u043f\u043e\u0441\u043c\u043e\u0442\u0440\u0435\u0442\u044c \u0432\u0445\u043e\u0434\u044f\u0449\u0438\u0435 \u0437\u0430\u044f\u0432\u043a\u0438."
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
            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
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
            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text='➕ Добавить карточку', callback_data='act:admin:card:create')],
                    *[[InlineKeyboardButton(text=title, callback_data=f"nav:admin_card:{key}")] for key, title in items],
                    [InlineKeyboardButton(text='🔙 Назад', callback_data='nav:admin')],
                ]
            )
            await message.answer(f"{h('🃏 Карточки')}\nВыберите карточку для просмотра или редактирования.", reply_markup=kb)
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
            lines = [h('🛒 Магазин'), 'Категории:']
            for cat in cats:
                lines.append(f"• {cat.emoji} {cat.title} | key={cat.key}")
            lines.append('')
            lines.append('Товары:')
            for item in items:
                lines.append(f"• {item.title} | key={item.key} | cat={item.category_key}")
            await message.answer('\n'.join(lines), reply_markup=ik_admin_main())
            return True
        if section == 'tasks':
            rows = (await session.scalars(select(BcTask).order_by(BcTask.sort).limit(20))).all()
            lines = [h('📜 Задания'), 'Задания системы:']
            for task in rows:
                lines.append(f"• {task.title} | {task.kind} | target={task.target} | active={int(task.is_active)}")
            await message.answer('\n'.join(lines), reply_markup=ik_admin_main())
            return True
        if section == 'rp':
            cats = (await session.scalars(select(BcRPCategory).order_by(BcRPCategory.sort))).all()
            acts = (await session.scalars(select(BcRPAction).order_by(BcRPAction.sort).limit(20))).all()
            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
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
            await message.answer(f"{h('🏆 Топы и сезоны')}\nПользователей: {users_total}\nВыданных карт: {cards_total}\nСезонные награды готовы к расширению.", reply_markup=ik_admin_main())
            return True
        if section == 'economy':
            lots_total = int(await session.scalar(select(func.count()).select_from(BcMarketLot)) or 0)
            await message.answer(f"{h('💰 Экономика')}\nЛотов на маркете: {lots_total}\nЭкономика управляется редкостями, бустерами, картами и товарами магазина.", reply_markup=ik_admin_main())
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
            lines = [h('🎉 Ивенты'), 'Список ивентов:']
            if not rows:
                lines.append('• Ивенты ещё не созданы.')
            for event in rows:
                lines.append(f"• {event.title} | key={event.key} | active={int(event.is_active)}")
            await message.answer('\n'.join(lines), reply_markup=ik_admin_main())
            return True
        if section == 'permissions':
            roles = (await session.scalars(select(BcRole).order_by(BcRole.key))).all()
            perms = (await session.scalars(select(BcPermission).order_by(BcPermission.code).limit(20))).all()
            lines = [h('🔐 Права'), 'Роли:']
            for role in roles:
                assigned = int(await session.scalar(select(func.count()).select_from(BcUserRole).where(BcUserRole.role_key == role.key)) or 0)
                lines.append(f"• {role.title} | key={role.key} | users={assigned}")
            lines.append('')
            lines.append('Права:')
            for perm in perms:
                linked = int(await session.scalar(select(func.count()).select_from(BcRolePermission).where(BcRolePermission.permission_code == perm.code)) or 0)
                lines.append(f"• {perm.code} | roles={linked}")
            await message.answer('\n'.join(lines), reply_markup=ik_admin_main())
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
            welcome_text = await service.get_template_text('screen.welcome', 'ru', DEFAULT_TEXT_TEMPLATES['screen.welcome'])
            help_text = await service.get_template_text('screen.help', 'ru', DEFAULT_TEXT_TEMPLATES['screen.help'])
            lines = [
                h('⚙️ Настройки бота'),
                'Здесь меняются таймеры, награды, бонусные ссылки, подписи кнопок и тексты интерфейса.',
                '',
                '⏱ Кулдауны:',
                f"• Карточка: {int(cooldowns.get('brawl_cards') or 0)}с",
                f"• Бонус: {int(cooldowns.get('bonus') or 0)}с",
                f"• Смена ника: {int(cooldowns.get('nick_change') or 0)}с",
                f"• Dice: {int(cooldowns.get('dice') or 0)}с",
                f"• Slot: {int(cooldowns.get('slot') or 0)}с",
                f"• Darts: {int(cooldowns.get('darts') or 0)}с",
                f"• Football: {int(cooldowns.get('football') or 0)}с",
                f"• Basketball: {int(cooldowns.get('basketball') or 0)}с",
                f"• Guess rarity: {int(cooldowns.get('guess_rarity') or 0)}с",
                f"• Coinflip: {int(cooldowns.get('coinflip') or 0)}с",
                f"• Card battle: {int(cooldowns.get('card_battle') or 0)}с",
                f"• Premium reduction: {int(cooldowns.get('premium_game_reduction') or 0)}с",
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
                    [InlineKeyboardButton(text='👋 Изменить приветствие', callback_data='act:admin:template:edit:screen.welcome')],
                    [InlineKeyboardButton(text='🧭 Изменить help-текст', callback_data='act:admin:template:edit:screen.help')],
                    [InlineKeyboardButton(text='📢 Рассылка', callback_data='nav:admin:broadcast')],
                    [InlineKeyboardButton(text='🔙 Назад', callback_data='nav:admin')],
                ]
            )
            await message.answer('\n'.join(lines), reply_markup=kb)
            return True
        if section == 'media':
            rows = (await session.scalars(select(BcMedia).order_by(BcMedia.created_at.desc()).limit(12))).all()
            lines = [h('🖼 Медиа'), 'Последние медиа-объекты:']
            if not rows:
                lines.append('• Медиа пока не загружены.')
            for media in rows:
                lines.append(f"• #{media.id} | {media.kind} | {media.title or 'без названия'} | active={int(media.is_active)}")
            await message.answer('\n'.join(lines), reply_markup=ik_admin_main())
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
                f"Шанс: {card.drop_weight}",
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
    if not events:
        await message.answer(f"{h('🎉 Ивенты')}\nСейчас активных событий нет.", reply_markup=ik_shop_categories())
        return
    lines = [h("🎉 Ивенты"), "Активные события и специальные режимы:"]
    for event in events[:10]:
        ends = event.ends_at.isoformat(timespec="minutes") if event.ends_at else "без срока"
        lines.append(f"• {event.title}\n{event.description[:120]}\nДо: {ends}")
    await message.answer(
        "\n".join(lines),
        reply_markup=ik_list_nav([("shop", "🛒 Магазин"), ("tasks", "📜 Задания"), ("bonus", "🎁 Бонус")], prefix="nav", back_to="main"),
    )


async def show_screen(message: Message, screen: str) -> None:
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
        'drop_weight': '\u0448\u0430\u043d\u0441 \u0432\u044b\u043f\u0430\u0434\u0435\u043d\u0438\u044f',
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
        'drop_weight': '\u0427\u0438\u0441\u043b\u043e: `1` \u0438\u043b\u0438 `0.35`.',
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
                    kwargs['reply_markup'] = user_menu(callback.from_user.id)
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
            await respond('RP-действие удалено.', reply_markup=main_menu())
            return
        if action == 'act:admin:rarity:create':
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            await service.set_input_state(callback.from_user.id, 'admin_rarity_form', {'mode': 'create'})
            await respond(f"{h('💎 Добавить редкость')}\nОтправьте одной строкой:\n`key|Название|эмодзи|шанс|цвет|points_mult|coins_mult|drop_mode|in_chests(0/1)|in_shop(0/1)`\nПример:\n`ultra|Ультра|🔶|0.2|#FFAA00|4.2|2.9|normal|1|1`", parse_mode='Markdown', reply_markup=main_menu())
            return
        if action.startswith('act:admin:rarity:edit:'):
            if not is_admin_id(callback.from_user.id):
                await respond('Доступ запрещён.', reply_markup=main_menu())
                return
            rarity_key = action.split(':', maxsplit=4)[4]
            await service.set_input_state(callback.from_user.id, 'admin_rarity_form', {'mode': 'edit', 'key': rarity_key})
            await respond(f"{h('💎 Редактировать редкость')}\nКлюч: `{rarity_key}`\nОтправьте строкой:\n`Название|эмодзи|шанс|цвет|points_mult|coins_mult|drop_mode|in_chests(0/1)|in_shop(0/1)|active(0/1)`", parse_mode='Markdown', reply_markup=main_menu())
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
            await respond(f"{h('📦 Редактировать сундук')}\nКлюч: `{chest_key}`\nОтправьте строкой:\n`Название|эмодзи|описание|price_coins|price_stars|open_count|active(0/1)`\nДроп-таблица редактируется отдельной кнопкой (будет добавлено).", parse_mode='Markdown', reply_markup=main_menu())
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
            await respond('Сундук удалён.', reply_markup=main_menu())
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
                prompt = (
                    f"{h('⏱ Кулдауны')}\n"
                    "Отправьте строкой:\n"
                    "`key|seconds`\n\n"
                    "Ключи:\n"
                    "`brawl_cards`, `bonus`, `nick_change`, `dice`, `slot`, `darts`, `football`, `basketball`, `guess_rarity`, `coinflip`, `card_battle`, `premium_game_reduction`"
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
    await respond('Действие пока не реализовано.', reply_markup=main_menu())

@router.pre_checkout_query()
async def on_pre_checkout_query(pre_checkout_query: PreCheckoutQuery) -> None:
    payload = pre_checkout_query.invoice_payload or ""
    if not payload.startswith("xtr_shop:"):
        await pre_checkout_query.answer(ok=False, error_message="\u041d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u044b\u0439 \u043f\u043b\u0430\u0442\u0435\u0436.")
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
            ok, resp = await service.grant_shop_item(
                message.from_user.id,
                item_key,
                source="telegram_stars",
                payment_charge_id=message.successful_payment.telegram_payment_charge_id,
                amount_paid=int(message.successful_payment.total_amount),
            )
    title = h("Оплата успешна") if ok else h("Ошибка оплаты")
    charge_id = message.successful_payment.telegram_payment_charge_id
    await message.answer(
        f"{title}\n{resp}\n\nСумма: {message.successful_payment.total_amount} XTR\nCharge ID: `{charge_id}`",
        reply_markup=main_menu(is_admin=is_admin_id(message.from_user.id)),
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

        if state.state == 'nick_wait':
            async with session.begin():
                ok, resp = await service.change_nickname(message.from_user.id, raw)
                if ok:
                    await service.clear_input_state(message.from_user.id)
            await message.answer(resp, reply_markup=main_menu(is_admin=is_admin_id(message.from_user.id)))
            return

        if state.state == 'rp_target_wait':
            payload = dict(state.payload or {})
            action_key = str(payload.get('action_key') or '')
            target = await service.resolve_user_reference(raw)
            if target is None:
                await message.answer(f"{h('\U0001f3ad RP')}\n\u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d. \u041e\u0442\u043f\u0440\u0430\u0432\u044c\u0442\u0435 ID, @username \u0438\u043b\u0438 \u0441\u0441\u044b\u043b\u043a\u0443 `https://t.me/...`.", parse_mode='Markdown', reply_markup=main_menu())
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
                await message.answer(f"{h('\U0001f3ad RP')}\n{result.get('message', '\u041e\u0448\u0438\u0431\u043a\u0430 RP-\u0434\u0435\u0439\u0441\u0442\u0432\u0438\u044f.')}", reply_markup=main_menu())
                return
            await send_rp_result(message, f"{h('\U0001f3ad RP')}\n{result['text']}", result.get('media'))
            return

        if state.state == 'quote_wait':
            async with session.begin():
                await service.clear_input_state(message.from_user.id)
            await message.answer(f"{h('\U0001f4ac \u0426\u0438\u0442\u0430\u0442\u0430')}\n\xab{raw}\xbb", reply_markup=main_menu())
            return

        if state.state == 'sticker_last_wait':
            state_row = await session.get(BcUserState, message.from_user.id)
            card = await session.get(BcCard, state_row.last_card_id) if state_row and state_row.last_card_id else None
            if card is None:
                await message.answer(f"{h('\U0001f3a8 \u0421\u0442\u0438\u043a\u0435\u0440')}\n\u0421\u043d\u0430\u0447\u0430\u043b\u0430 \u043f\u043e\u043b\u0443\u0447\u0438\u0442\u0435 \u043a\u0430\u0440\u0442\u043e\u0447\u043a\u0443.", reply_markup=main_menu())
                return
            out_file = build_card_image(card.title, card.rarity_key, card.description, raw, Path('data/generated'))
            async with session.begin():
                await service.clear_input_state(message.from_user.id)
            await message.answer_photo(FSInputFile(out_file), caption=f"{h('\U0001f3a8 \u0421\u0442\u0438\u043a\u0435\u0440')}\n\u0421\u0442\u0438\u043a\u0435\u0440 \u043f\u043e \u043f\u043e\u0441\u043b\u0435\u0434\u043d\u0435\u0439 \u043a\u0430\u0440\u0442\u043e\u0447\u043a\u0435 \u0433\u043e\u0442\u043e\u0432.", reply_markup=main_menu())
            return

        if state.state == 'sticker_template_wait':
            out_file = build_card_image('Antonio', 'common', '\u0428\u0430\u0431\u043b\u043e\u043d\u043d\u044b\u0439 \u0441\u0442\u0438\u043a\u0435\u0440', raw, Path('data/generated'))
            async with session.begin():
                await service.clear_input_state(message.from_user.id)
            await message.answer_photo(FSInputFile(out_file), caption=f"{h('\U0001f3a8 \u0421\u0442\u0438\u043a\u0435\u0440')}\n\u0428\u0430\u0431\u043b\u043e\u043d\u043d\u044b\u0439 \u0441\u0442\u0438\u043a\u0435\u0440 \u0433\u043e\u0442\u043e\u0432.", reply_markup=main_menu())
            return


        if state.state == 'market_sell_wait':
            parts = [p.strip() for p in raw.split('|')]
            if len(parts) != 3:
                await message.answer(f"{h('💱 Маркет')}\nФормат: `instance_id|coins_or_stars|price`", parse_mode='Markdown', reply_markup=main_menu())
                return
            instance_id, currency, price = parts
            try:
                instance_id_int = int(instance_id)
                price_int = int(price)
            except ValueError:
                await message.answer(f"{h('💱 Маркет')}\n`instance_id` и `price` должны быть числами.", parse_mode='Markdown', reply_markup=main_menu())
                return
            async with session.begin():
                ok, resp = await service.market_sell_instance(message.from_user.id, instance_id_int, currency, price_int)
                if ok:
                    await service.clear_input_state(message.from_user.id)
            await message.answer(f"{h('💱 Маркет')}\n{resp}", reply_markup=main_menu())
            return

        if state.state == 'marriage_propose_wait':
            target = await service.resolve_user_reference(raw)
            if target is None:
                await message.answer(f"{h('💍 Брак')}\nПользователь не найден. Отправьте ID, @username или ссылку.", reply_markup=main_menu())
                return
            async with session.begin():
                ok, resp = await service.marriage_propose(message.from_user.id, target.id)
                if ok:
                    await service.clear_input_state(message.from_user.id)
            await message.answer(f"{h('💍 Брак')}\n{resp}", reply_markup=main_menu())
            return

        if state.state == 'admin_user_manage_form':
            if not is_admin_id(message.from_user.id):
                await message.answer('Доступ запрещён.', reply_markup=main_menu())
                return
            parts = [part.strip() for part in raw.split('|', maxsplit=2)]
            if len(parts) != 3:
                await message.answer(
                    f"{h('👥 Управление пользователем')}\nНужен формат: `user_id|field|value`",
                    parse_mode='Markdown',
                    reply_markup=main_menu(is_admin=True),
                )
                return
            try:
                target_user_id = int(parts[0])
            except ValueError:
                await message.answer(
                    f"{h('👥 Управление пользователем')}\n`user_id` должен быть числом.",
                    parse_mode='Markdown',
                    reply_markup=main_menu(is_admin=True),
                )
                return
            async with session.begin():
                ok, resp = await service.admin_update_user(target_user_id, parts[1], parts[2])
                if ok:
                    await service.clear_input_state(message.from_user.id)
            await message.answer(f"{h('👥 Управление пользователем')}\n{resp}", reply_markup=main_menu(is_admin=True))
            return

        if state.state == 'admin_system_form':
            if not is_admin_id(message.from_user.id):
                await message.answer('Доступ запрещён.', reply_markup=main_menu())
                return
            payload = dict(state.payload or {})
            section = str(payload.get('section') or '').strip()
            parts = [part.strip() for part in raw.split('|', maxsplit=1)]
            if len(parts) != 2:
                await message.answer(
                    f"{h('⚙️ Системная настройка')}\nНужен формат: `key|value`",
                    parse_mode='Markdown',
                    reply_markup=main_menu(is_admin=True),
                )
                return
            key, value_raw = parts
            if not key:
                await message.answer('Ключ не указан.', reply_markup=main_menu(is_admin=True))
                return
            if section == 'button_labels' and key not in DEFAULT_BUTTON_LABELS:
                await message.answer(
                    f"{h('🔘 Подписи кнопок')}\nКлюч не поддерживается этим UI-контуром.",
                    reply_markup=main_menu(is_admin=True),
                )
                return
            try:
                if section in {'cooldowns', 'rewards'}:
                    value: object = int(value_raw)
                elif section == 'button_labels':
                    value = DEFAULT_BUTTON_LABELS[key] if value_raw == '-' else value_raw
                    if not str(value).strip():
                        await message.answer('Текст кнопки не может быть пустым.', reply_markup=main_menu(is_admin=True))
                        return
                elif section == 'bonus_links':
                    value = '' if value_raw == '-' else value_raw
                else:
                    await message.answer('Неизвестный раздел настроек.', reply_markup=main_menu(is_admin=True))
                    return
            except ValueError:
                await message.answer('Значение имеет неверный формат.', reply_markup=main_menu(is_admin=True))
                return
            async with session.begin():
                updated = await service.set_system_value(section, key, value)
                await service.clear_input_state(message.from_user.id)
            await message.answer(
                f"{h('⚙️ Настройки бота')}\nСохранено: {key} = {updated.get(key)}",
                reply_markup=main_menu(is_admin=True),
            )
            return

        if state.state == 'admin_template_form':
            if not is_admin_id(message.from_user.id):
                await message.answer('Доступ запрещён.', reply_markup=main_menu())
                return
            payload = dict(state.payload or {})
            template_key = str(payload.get('key') or '').strip()
            locale = str(payload.get('locale') or 'ru').strip() or 'ru'
            if not template_key:
                await message.answer('Ключ шаблона не найден.', reply_markup=main_menu(is_admin=True))
                return
            text_value = DEFAULT_TEXT_TEMPLATES.get(template_key, '') if raw == '-' else raw
            if not text_value.strip():
                await message.answer('Текст шаблона не может быть пустым.', reply_markup=main_menu(is_admin=True))
                return
            async with session.begin():
                await service.upsert_template_text(template_key, locale, text_value)
                await service.clear_input_state(message.from_user.id)
            await message.answer(
                f"{h('📝 Редактор шаблона')}\nШаблон {template_key} обновлён.",
                reply_markup=main_menu(is_admin=True),
            )
            return

        if state.state == 'admin_broadcast_form':
            if not is_admin_id(message.from_user.id):
                await message.answer('Доступ запрещён.', reply_markup=main_menu())
                return
            text_value = raw.strip()
            if not text_value:
                await message.answer('Текст рассылки пустой.', reply_markup=main_menu(is_admin=True))
                return
            async with session.begin():
                await service.clear_input_state(message.from_user.id)
            asyncio.create_task(run_text_broadcast(message.bot, message.from_user.id, text_value))
            await message.answer(
                f"{h('📢 Рассылка')}\nЗадача запущена. Отчёт придёт отдельным сообщением.",
                reply_markup=main_menu(is_admin=True),
            )
            return

        if state.state == 'admin_card_wizard':
            if not is_admin_id(message.from_user.id):
                await message.answer('Доступ запрещён.', reply_markup=main_menu())
                return
            result = await consume_admin_card_wizard_input(session, service, message.from_user.id, raw)
            await session.commit()
            await message.answer(
                result['text'],
                parse_mode=result.get('parse_mode'),
                reply_markup=result.get('reply_markup') or main_menu(),
            )
            if result.get('done') and result.get('card_id'):
                await screen_admin_card(message, int(result['card_id']))
            return

@router.message(F.photo)
async def on_photo_input(message: Message) -> None:
    if message.from_user is None or not message.photo:
        return
    menu = user_menu(message.from_user.id)
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
            await message.answer('Фото карточки обновлено.', reply_markup=menu)
            await screen_admin_card(message, card_id)
            return
