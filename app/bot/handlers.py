from __future__ import annotations
from pathlib import Path
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, FSInputFile, LabeledPrice, Message, PreCheckoutQuery
from sqlalchemy import and_, func, select
from app.bot.keyboards import BTN_ADMIN, BTN_BONUS, BTN_CHEST, BTN_GAMES, BTN_GET_CARD, BTN_MARRIAGE, BTN_MARKET, BTN_PREMIUM, BTN_PROFILE, BTN_QUOTE, BTN_RP, BTN_SETTINGS, BTN_SHOP, BTN_STICKER, BTN_TASKS, BTN_TOP, MAIN_MENU_BUTTONS, ik_admin_main, ik_bonus_tasks, ik_games_menu, ik_game_stakes, ik_get_card, ik_list_nav, ik_marriage_menu, ik_marriage_proposal, ik_market_lot_actions, ik_market_menu, ik_nick, ik_profile, ik_quote_menu, ik_rp_actions, ik_rp_categories, ik_shop_categories, ik_settings, ik_sticker_menu, ik_top_select, ik_nav, main_menu
from app.config import get_settings
from app.db.models import BcActiveBooster, BcAuditLog, BcBonusTask, BcBooster, BcCard, BcCardInstance, BcChest, BcChestDrop, BcEvent, BcInputState, BcLimitedSeries, BcMarriageProposal, BcMedia, BcMarketLot, BcPermission, BcRole, BcRolePermission, BcRPAction, BcRPCategory, BcRarity, BcShopCategory, BcShopItem, BcTask, BcUserRole, BcUserState, BcUserSettings, Marriage, User, UserProfile
from app.db.session import SessionLocal
from app.services.brawl_cards_service import BrawlCardsService
from app.utils.sticker import build_card_image
from app.utils.time import seconds_to_hms, utcnow
router = Router(name='brawl_cards_user_bot')
settings = get_settings()

def h(title: str) -> str:
    return f"{title}\n------------------"

def display_name(user: User) -> str:
    return user.nickname or user.first_name or str(user.id)


async def ensure_user(message: Message) -> User | None:
    if message.from_user is None:
        return None
    async with SessionLocal() as session:
        service = BrawlCardsService(session)
        async with session.begin():
            user = await service.ensure_user(user_id=message.from_user.id, username=message.from_user.username, first_name=message.from_user.first_name)
        return user


def is_admin_id(user_id: int) -> bool:
    return user_id in get_settings().admin_id_set()


async def template_text(session, user_id: int | None, key: str, fallback: str) -> str:
    service = BrawlCardsService(session)
    locale = 'ru'
    if user_id is not None:
        s = await service.ensure_settings(user_id)
        locale = s.locale
    return await service.get_template_text(key, locale, fallback)


def resolve_bonus_url(task: BcBonusTask) -> str:
    cfg = dict(task.config or {})
    url = str(cfg.get('url') or '').strip()
    if url:
        return url
    return get_settings().bonus_urls().get(task.key, '')


async def send_rp_result(message: Message, text: str, media: BcMedia | None=None) -> None:
    if media is None:
        await message.answer(text, reply_markup=main_menu(), parse_mode='Markdown')
        return
    file_id = media.telegram_file_id
    if media.kind == 'photo' and file_id:
        await message.answer_photo(file_id, caption=text, reply_markup=main_menu(), parse_mode='Markdown')
        return
    if media.kind == 'video' and file_id:
        await message.answer_video(file_id, caption=text, reply_markup=main_menu(), parse_mode='Markdown')
        return
    if media.kind == 'animation' and file_id:
        await message.answer_animation(file_id, caption=text, reply_markup=main_menu(), parse_mode='Markdown')
        return
    if media.kind == 'sticker' and file_id:
        await message.answer_sticker(file_id)
        await message.answer(text, reply_markup=main_menu(), parse_mode='Markdown')
        return
    await message.answer(text, reply_markup=main_menu(), parse_mode='Markdown')


async def send_start(message: Message) -> None:
    text = (
        f"{h('👑 Antonio')}\n"
        "Здесь ты собираешь карточки, усиливаешь аккаунт, выполняешь задания, получаешь бонусы, участвуешь в рейтингах, "
        "взаимодействуешь с другими игроками, торгуешь карточками, открываешь сундуки и используешь RP-функции.\n\n"
        "Нажимай кнопки меню снизу: почти все действия выполняются через них."
    )
    user_id = message.from_user.id if message.from_user else 0
    await message.answer(text, reply_markup=main_menu(is_admin=is_admin_id(user_id)))


async def screen_main(message: Message) -> None:
    await send_start(message)

async def screen_profile(message: Message) -> None:
    if message.from_user is None:
        return
    await ensure_user(message)
    async with SessionLocal() as session:
        service = BrawlCardsService(session)
        async with session.begin():
            user = await service.session.get(User, message.from_user.id)
            if user is None:
                await message.answer('Профиль не найден. Нажмите /start.')
                return
            prof = await service.session.get(UserProfile, message.from_user.id)
            if prof is None:
                prof = UserProfile(user_id=user.id)
                session.add(prof)
            state = await service.session.get(BcUserState, message.from_user.id)
        premium_active = bool(user.premium_until and user.premium_until > utcnow())
        premium_str = 'активен' if premium_active else 'не активен'
        premium_until = user.premium_until.isoformat(timespec='seconds') if user.premium_until else '—'
        cards_total = await session.scalar(select(func.count()).select_from(BcCardInstance).where(BcCardInstance.user_id == user.id))
        limited_count = await session.scalar(select(func.count()).select_from(BcCardInstance).join(BcCard, BcCard.id == BcCardInstance.card_id).where(and_(BcCardInstance.user_id == user.id, BcCard.is_limited.is_(True))))
        marriage = await session.scalar(select(Marriage).where((Marriage.user1_id == user.id) | (Marriage.user2_id == user.id)).limit(1))
        family_str = 'в браке' if marriage else 'не в браке'
        text = f"{h('👤 Профиль')}\n🆔 ID: `{user.id}`\n🏷 Ник: {display_name(user)}\n📅 Регистрация: {user.created_at.date().isoformat()}\n\n🏅 Уровень: {prof.level}\n📈 Опыт: {prof.exp}\n✨ Очки: {user.total_points}\n🪙 Монеты: {user.coins}\n⭐ Звёзды: {user.stars}\n\n🃏 Карточки: {user.cards_total} (legacy) | {cards_total or 0} (Antonio)\n🎟 Лимитки: {limited_count or 0}\n⚡ Активные бустеры: —\n💎 Premium: {premium_str} ({premium_until})\n\n🏆 Позиции в топах: —\n🎲 Игры: {prof.games_played} сыграно, {prof.games_won} побед\n💱 Маркет: {prof.market_sold} продано, {prof.market_bought} куплено\n💍 Семья: {family_str}\n✅ Заданий выполнено: {prof.tasks_done}\n⏱ Активность: {int(prof.activity_seconds // 3600)}ч"
        await message.answer(text, reply_markup=ik_profile(), parse_mode='Markdown')

async def screen_nick(message: Message) -> None:
    text = f"{h('✏️ Смена ника')}\nЗдесь вы можете поменять ник.\n\nПравила:\n• длина 3-24 символа\n• буквы/цифры/пробел и символы _-[]().,!?:+@#\n• эмодзи в нике — только с Premium\n• кулдаун смены: 24 часа\n• антиспам: слишком частые попытки блокируются\n\nНажмите «Ввести новый ник», затем отправьте ник одним сообщением."
    await message.answer(text, reply_markup=ik_nick())

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
                await message.answer(f"{h('🃏 Получить карту')}\nКулдаун: {seconds_to_hms(int(result['cooldown']))}\n\nПодсказка: Premium и бустеры могут сокращать ожидание.", reply_markup=ik_get_card())
                return
            await message.answer(f"{h('🃏 Получить карту')}\n{result.get('error', 'Ошибка')}", reply_markup=ik_get_card())
            return
        card = result['card']
        title = card['title']
        rarity = f"{card['rarity_emoji']} {card['rarity_title']}"
        series = card['series']
        is_limited = 'да' if card['is_limited'] else 'нет'
        obtained = card['obtained_at'].isoformat(timespec='seconds')
        text = f"{h('🃏 Карта получена')}\n🪪 Название: *{title}*\n📚 Серия: `{series}`\n💠 Редкость: {rarity}\n📝 Описание: {card['description']}\n\n✨ Очки: +{card['points']}\n🪙 Монеты: +{card['coins']}\n🎟 Лимитка: {is_limited}\n🗓 Дата: `{obtained}`"
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
    text = f"{h('🎁 Бонус')}\nЗдесь вы можете выполнить бонусные задания."
    await message.answer(text, reply_markup=ik_bonus_tasks(btns))

async def screen_top(message: Message) -> None:
    text = f"{h('🏆 Топ')}\nВыберите рейтинг."
    await message.answer(text, reply_markup=ik_top_select())

async def screen_top_metric(message: Message, metric: str) -> None:
    if message.from_user is None:
        return
    await ensure_user(message)
    async with SessionLocal() as session:
        if metric == 'points':
            rows = (await session.scalars(select(User).order_by(User.total_points.desc()).limit(10))).all()
            lines = [h('🏆 Топ по очкам')]
            for i, u in enumerate(rows, start=1):
                lines.append(f"{i}. {display_name(u)} — {u.total_points}✨")
        elif metric == 'coins':
            rows = (await session.scalars(select(User).order_by(User.coins.desc()).limit(10))).all()
            lines = [h('🏆 Топ по монетам')]
            for i, u in enumerate(rows, start=1):
                lines.append(f"{i}. {display_name(u)} — {u.coins}🪙")
        elif metric == 'cards':
            rows = (await session.execute(select(User.id, User.nickname, User.first_name, func.count(BcCardInstance.id).label('c')).join(BcCardInstance, BcCardInstance.user_id == User.id, isouter=True).group_by(User.id).order_by(func.count(BcCardInstance.id).desc()).limit(10))).all()
            lines = [h('🏆 Топ по картам')]
            for i, (uid, nick, first_name, c) in enumerate(rows, start=1):
                name = nick or first_name or str(uid)
                lines.append(f"{i}. {name} — {int(c or 0)}🃏")
        elif metric == 'level':
            rows = (await session.execute(select(User.id, User.nickname, User.first_name, UserProfile.level).join(UserProfile, UserProfile.user_id == User.id, isouter=True).order_by(UserProfile.level.desc().nullslast()).limit(10))).all()
            lines = [h('🏆 Топ по уровню')]
            for i, (uid, nick, first_name, lvl) in enumerate(rows, start=1):
                name = nick or first_name or str(uid)
                lines.append(f"{i}. {name} — {int(lvl or 1)}🏅")
        elif metric == 'rare':
            rows = (await session.execute(select(User.id, User.nickname, User.first_name, func.count(BcCardInstance.id).label('c')).join(BcCardInstance, BcCardInstance.user_id == User.id, isouter=True).join(BcCard, BcCard.id == BcCardInstance.card_id, isouter=True).where(BcCard.rarity_key.in_(['epic', 'mythic', 'legendary', 'exclusive', 'event', 'limited'])).group_by(User.id).order_by(func.count(BcCardInstance.id).desc()).limit(10))).all()
            lines = [h('🏆 Топ по редким')]
            for i, (uid, nick, first_name, c) in enumerate(rows, start=1):
                name = nick or first_name or str(uid)
                lines.append(f"{i}. {name} — {int(c or 0)}💎")
        else:
            await screen_top(message)
            return
    lines.append('\nНаграды сезона: настраиваются в админке (MVP).')
    await message.answer('\n'.join(lines), reply_markup=ik_top_select())

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
        price_lines.append(f"? {item.price_coins}\U0001fa99")
    if item.price_stars is not None:
        price_lines.append(f"? {item.price_stars}?")
    price_text = "\n".join(price_lines) if price_lines else "?"
    duration = seconds_to_hms(item.duration_seconds) if item.duration_seconds else "?"
    text = (
        f"{h('\U0001f6d2 \u0422\u043e\u0432\u0430\u0440')}\n"
        f"?? *{item.title}*\n"
        f"?? {item.description}\n\n"
        f"?? \u0426\u0435\u043d\u0430:\n{price_text}\n"
        f"? \u0421\u0440\u043e\u043a: {duration}"
    )
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    rows: list[list[InlineKeyboardButton]] = []
    if item.price_coins is not None:
        rows.append([InlineKeyboardButton(text="\u041a\u0443\u043f\u0438\u0442\u044c \u0437\u0430 \u043c\u043e\u043d\u0435\u0442\u044b", callback_data=f"act:buy:{item.key}:coins")])
    if item.price_stars is not None:
        rows.append([InlineKeyboardButton(text="\u041a\u0443\u043f\u0438\u0442\u044c \u0437\u0430 \u0437\u0432\u0435\u0437\u0434\u044b \u0431\u043e\u0442\u0430", callback_data=f"act:buy:{item.key}:stars")])
        rows.append([InlineKeyboardButton(text="? \u041e\u043f\u043b\u0430\u0442\u0438\u0442\u044c Telegram Stars", callback_data=f"act:buy_xtr:{item.key}")])
    rows.append([InlineKeyboardButton(text="? \u041d\u0430\u0437\u0430\u0434", callback_data=f"nav:shop:{item.category_key}")])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")

async def screen_chest_detail(message: Message, chest_key: str) -> None:
    if message.from_user is None:
        return
    await ensure_user(message)
    async with SessionLocal() as session:
        chest = await session.get(BcChest, chest_key)
        if chest is None or not chest.is_active:
            await message.answer(f"{h('📦 Сундук')}\nСундук не найден.", reply_markup=main_menu())
            return
    price_parts: list[str] = []
    if chest.price_coins is not None:
        price_parts.append(f"{chest.price_coins}🪙")
    if chest.price_stars is not None:
        price_parts.append(f"{chest.price_stars}⭐")
    price = ' / '.join(price_parts) if price_parts else '—'
    chest_title = f"{chest.emoji} {chest.title} ????????????"
    text = f"{h(chest_title)}\n{chest.description}\n\n???? ????????: {price}\n???? ????????????????: {chest.open_count}\n???? ?????????????? ??????????: ?????????????????????????? ?? ??????????????."
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='📦 Открыть', callback_data=f"act:chest:open:{chest.key}")], [InlineKeyboardButton(text='🔙 Назад', callback_data='nav:chest')]])
    await message.answer(text, reply_markup=kb)

async def screen_task_detail(message: Message, task_key: str) -> None:
    if message.from_user is None:
        return
    await ensure_user(message)
    async with SessionLocal() as session:
        service = BrawlCardsService(session)
        async with session.begin():
            task = await session.get(BcTask, task_key)
            if task is None or not task.is_active:
                await message.answer(f"{h('📜 Задания')}\nЗадание не найдено.", reply_markup=main_menu())
                return
            row = await service.get_user_task(message.from_user.id, task)
            await service.refresh_task_period(row, task)
    status = '✅ выполнено' if row.completed_at else '⬛ не выполнено'
    claimed = 'РґР°' if row.claimed_at else 'нет'
    reward = task.reward or {}
    text = f"{h('📜 Задание')}\n🏷 *{task.title}*\n📝 {task.description}\n\n📊 Прогресс: {row.progress}/{task.target}\n📌 Статус: {status}\n🎁 Награда: +{int(reward.get('coins') or 0)}🪙 +{int(reward.get('stars') or 0)}⭐ +{int(reward.get('points') or 0)}✨\n📥 Получено: {claimed}"
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='✅ Получить награду', callback_data=f"act:task:claim:{task.key}")], [InlineKeyboardButton(text='🔙 Назад', callback_data='nav:tasks')]])
    await message.answer(text, reply_markup=kb, parse_mode='Markdown')

async def screen_shop(message: Message) -> None:
    text = f"{h('\U0001f6d2 \u041c\u0430\u0433\u0430\u0437\u0438\u043d')}\n\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u043a\u0430\u0442\u0435\u0433\u043e\u0440\u0438\u044e, \u043e\u0442\u043a\u0440\u043e\u0439\u0442\u0435 \u043e\u0444\u0444\u0435\u0440\u044b \u0434\u043d\u044f \u0438\u043b\u0438 \u043f\u043e\u0441\u043c\u043e\u0442\u0440\u0438\u0442\u0435 \u0430\u043a\u0442\u0438\u0432\u043d\u044b\u0435 \u0438\u0432\u0435\u043d\u0442\u044b.\nTelegram Stars \u0434\u043b\u044f \u0446\u0438\u0444\u0440\u043e\u0432\u044b\u0445 \u043f\u043e\u043a\u0443\u043f\u043e\u043a \u0434\u043e\u0441\u0442\u0443\u043f\u043d\u044b \u043f\u0440\u044f\u043c\u043e \u0432\u043d\u0443\u0442\u0440\u0438 \u0431\u043e\u0442\u0430."
    await message.answer(text, reply_markup=ik_shop_categories())

async def screen_chest(message: Message) -> None:
    async with SessionLocal() as session:
        service = BrawlCardsService(session)
        chests = await service.chests()
        items = [(c.key, f"{c.emoji} {c.title}") for c in chests]
    text = f"{h('📦 Сундуки')}\nВыберите сундук для открытия."
    await message.answer(text, reply_markup=ik_list_nav(items, prefix='nav:chest', back_to='main'))

async def screen_premium(message: Message) -> None:
    text = f"{h('💎 Премиум')}\nПреимущества:\n• меньше кулдаун на получение карточек\n• выше шанс редких карточек\n• эмодзи в нике\n• значок в топах\n• больше монет за карточки\n• меньше кулдауны в играх\n• эксклюзивные RP-возможности\n• рамки профиля и персонализация\n\nПокупка доступна в магазине: «💎 Премиум»."
    await message.answer(text, reply_markup=ik_shop_categories())

async def screen_tasks(message: Message) -> None:
    if message.from_user is None:
        return
    await ensure_user(message)
    async with SessionLocal() as session:
        service = BrawlCardsService(session)
        async with session.begin():
            tasks = await service.tasks()
            lines: list[str] = [h('📜 Задания'), 'Выберите задание и получите награду:']
            buttons: list[tuple[str, str]] = []
            for t in tasks:
                row = await service.get_user_task(message.from_user.id, t)
                await service.refresh_task_period(row, t)
                status = '✅' if row.claimed_at else '🟩' if row.completed_at else 'в¬›'
                lines.append(f"{status} {t.title} — {row.progress}/{t.target}")
                buttons.append((t.key, f"{status} {t.title[:28]}"))
    await message.answer('\n'.join(lines), reply_markup=ik_list_nav(buttons, prefix='nav:task', back_to='main'))

async def screen_rp(message: Message) -> None:
    text = f"{h('🎭 RP')}\nВыберите действие.\nЕсли нужно указать цель — ответьте на сообщение пользователя и нажмите действие."
    await message.answer(text, reply_markup=ik_nav('main'))

async def screen_quote(message: Message) -> None:
    text = f"{h('💬 Цитата')}\nВведите текст цитаты сообщением (скоро будет выбор по карточке)."
    await message.answer(text, reply_markup=ik_nav('main'))

async def screen_sticker(message: Message) -> None:
    text = f"{h('🎨 Стикер')}\nВыберите карточку/шаблон (MVP: будет добавлено)."
    await message.answer(text, reply_markup=ik_nav('main'))

async def screen_games(message: Message) -> None:
    text = f"{h('СЂСџР‹Р† Р\xa0\x98Р\xa0С–РЎР‚РЎвЂ№')}\nВыберите мини-игру. Ставки и анти-абуз — в разработке (MVP)."
    items = [('dice', '🎲 Кости'), ('guess_rarity', '🎯 Угадай редкость'), ('coinflip', '🪙 Орёл/решка'), ('slot', '🎰 Слот')]
    await message.answer(text, reply_markup=ik_list_nav(items, prefix='act:game', back_to='main'))

async def screen_market(message: Message) -> None:
    text = f"{h('💱 Маркет')}\nТорговая площадка (MVP): скоро появятся лоты и поиск."
    await message.answer(text, reply_markup=ik_nav('main'))

async def screen_marriage(message: Message) -> None:
    text = f"{h('💍 Брак')}\nСистема предложений и профиля пары (MVP): скоро."
    await message.answer(text, reply_markup=ik_nav('main'))

async def screen_settings(message: Message) -> None:
    text = f"{h('⚙️ Настройки')}\nЗдесь вы можете настроить:\n• уведомления\n• язык\n• приватность\n• подтверждение покупок\n• стиль выдачи карточек\n• отображение медиа\n• безопасный режим"
    await message.answer(text, reply_markup=ik_nav('main'))

async def screen_admin(message: Message) -> None:
    if message.from_user is None:
        return
    if not is_admin_id(message.from_user.id):
        allowed = ', '.join((str(admin_id) for admin_id in sorted(get_settings().admin_id_set()))) or 'не заданы'
        await message.answer(f"{h('🛠 Админ-панель')}\nДоступ запрещён.\nВаш ID: `{message.from_user.id}`\nРазрешённые ID: `{allowed}`", reply_markup=ik_nav('main'), parse_mode='Markdown')
        return
    text = f"{h('🛠 Админ-панель')}\nВыберите раздел."
    await message.answer(text, reply_markup=ik_admin_main())

async def screen_admin_section(message: Message, section: str) -> None:
    if message.from_user is None:
        return
    if not is_admin_id(message.from_user.id):
        allowed = ', '.join((str(admin_id) for admin_id in sorted(get_settings().admin_id_set()))) or 'не заданы'
        await message.answer(f"{h('🛠 Админ-панель')}\nДоступ запрещён.\nВаш ID: `{message.from_user.id}`\nРазрешённые ID: `{allowed}`", reply_markup=main_menu(), parse_mode='Markdown')
        return
    async with SessionLocal() as session:
        if section == 'rarities':
            rows = (await session.scalars(select(BcRarity).order_by(BcRarity.sort))).all()
            items = [(r.key, f"{r.emoji} {r.title} ({r.chance:g})") for r in rows]
            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='➕ Добавить редкость', callback_data='act:admin:rarity:create')], *[[InlineKeyboardButton(text=title, callback_data=f"nav:admin_rarity:{key}")] for key, title in items], [InlineKeyboardButton(text='🔙 Назад', callback_data='nav:admin')]])
            await message.answer(f"{h('💎 Редкости')}\nВыберите редкость для просмотра или редактирования.", reply_markup=kb)
            return
        if section == 'boosters':
            rows = (await session.scalars(select(BcBooster).order_by(BcBooster.key))).all()
            items = [(b.key, f"{b.emoji} {b.title} ({b.effect_type} {b.effect_power:g})") for b in rows]
            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='➕ Добавить бустер', callback_data='act:admin:booster:create')], *[[InlineKeyboardButton(text=title, callback_data=f"nav:admin_booster:{key}")] for key, title in items], [InlineKeyboardButton(text='🔙 Назад', callback_data='nav:admin')]])
            await message.answer(f"{h('⚡ Бустеры')}\nВыберите бустер.", reply_markup=kb)
            return
        if section == 'bonus':
            rows = (await session.scalars(select(BcBonusTask).order_by(BcBonusTask.sort))).all()
            items = [(t.key, f"{t.emoji} {t.title}") for t in rows]
            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='➕ Добавить бонус-задание', callback_data='act:admin:bonus:create')], *[[InlineKeyboardButton(text=title, callback_data=f"nav:admin_bonus:{key}")] for key, title in items], [InlineKeyboardButton(text='🔙 Назад', callback_data='nav:admin')]])
            await message.answer(f"{h('🎁 Бонус-задания')}\nНастройка бонусных кнопок и условий.", reply_markup=kb)
            return
        if section == 'chests':
            rows = (await session.scalars(select(BcChest).order_by(BcChest.sort))).all()
            items = [(c.key, f"{c.emoji} {c.title}") for c in rows]
            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='➕ Добавить сундук', callback_data='act:admin:chest:create')], *[[InlineKeyboardButton(text=title, callback_data=f"nav:admin_chest:{key}")] for key, title in items], [InlineKeyboardButton(text='🔙 Назад', callback_data='nav:admin')]])
            await message.answer(f"{h('📦 Сундуки')}\nВыберите сундук.", reply_markup=kb)
            return
    await message.answer(f"{h('🛠 Админ-панель')}\nРаздел в разработке: {section}", reply_markup=ik_admin_main())

async def screen_admin_rarity(message: Message, rarity_key: str) -> None:
    if message.from_user is None:
        return
    if not is_admin_id(message.from_user.id):
        await message.answer(f"{h('🛠 Админ')}\nДоступ запрещён.", reply_markup=main_menu())
        return
    async with SessionLocal() as session:
        r = await session.get(BcRarity, rarity_key)
        if r is None:
            await message.answer(f"{h('💎 Редкости')}\nРедкость не найдена.", reply_markup=main_menu())
            return
    text = f"{h('💎 Редкость')}\nКлюч: `{r.key}`\nНазвание: {r.title}\nР\xadРјРѕРґР·Рё: {r.emoji}\nШанс: {r.chance:g}\nЦвет: {r.color}\nМножители: points x{r.points_mult:g}, coins x{r.coins_mult:g}\nР\xa0РµР¶РёРј: {r.drop_mode}\nАктивна: {('РґР°' if r.is_active else 'нет')}"
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='✏️ Редактировать', callback_data=f"act:admin:rarity:edit:{r.key}")], [InlineKeyboardButton(text='🗑 Удалить', callback_data=f"act:admin:rarity:delete:{r.key}")], [InlineKeyboardButton(text='🔙 Назад', callback_data='nav:admin:rarities')]])
    await message.answer(text, reply_markup=kb, parse_mode='Markdown')

async def screen_admin_booster(message: Message, booster_key: str) -> None:
    if message.from_user is None:
        return
    if not is_admin_id(message.from_user.id):
        await message.answer(f"{h('🛠 Админ')}\nДоступ запрещён.", reply_markup=main_menu())
        return
    async with SessionLocal() as session:
        b = await session.get(BcBooster, booster_key)
        if b is None:
            await message.answer(f"{h('⚡ Бустеры')}\nБустер не найден.", reply_markup=main_menu())
            return
    text = f"{h('⚡ Бустер')}\nКлюч: `{b.key}`\nНазвание: {b.title}\nР\xadРјРѕРґР·Рё: {b.emoji}\nЭффект: {b.effect_type} power={b.effect_power:g}\nР¦РµРЅР°: {b.price_coins or '—'}🪙 / {b.price_stars or '—'}⭐\nДлительность: {(seconds_to_hms(b.duration_seconds) if b.duration_seconds else 'одноразовый/пассив')}\nСтаки: {('РґР°' if b.stackable else 'нет')} (max {b.max_stack})\nДоступен: {('РґР°' if b.is_available else 'нет')}"
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='✏️ Редактировать', callback_data=f"act:admin:booster:edit:{b.key}")], [InlineKeyboardButton(text='🗑 Удалить', callback_data=f"act:admin:booster:delete:{b.key}")], [InlineKeyboardButton(text='🔙 Назад', callback_data='nav:admin:boosters')]])
    await message.answer(text, reply_markup=kb, parse_mode='Markdown')

async def screen_admin_chest(message: Message, chest_key: str) -> None:
    if message.from_user is None:
        return
    if not is_admin_id(message.from_user.id):
        await message.answer(f"{h('🛠 Админ')}\nДоступ запрещён.", reply_markup=main_menu())
        return
    async with SessionLocal() as session:
        c = await session.get(BcChest, chest_key)
        if c is None:
            await message.answer(f"{h('📦 Сундуки')}\nСундук не найден.", reply_markup=main_menu())
            return
        drops = (await session.scalars(select(BcChestDrop).where(BcChestDrop.chest_key == chest_key))).all()
    drop_lines = [f"• {d.rarity_key} ({d.weight:g})" for d in drops] or ['—']
    text = f"{h('?? ??????')}\n????: `{c.key}`\n????????: {c.emoji} {c.title}\n????????: {c.description}\n????: {c.price_coins or '?'}?? / {c.price_stars or '?'}?\n????????: {c.open_count}\n\n????:\n" + '\n'.join(drop_lines)
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='✏️ Редактировать', callback_data=f"act:admin:chest:edit:{c.key}")], [InlineKeyboardButton(text='🗑 Удалить', callback_data=f"act:admin:chest:delete:{c.key}")], [InlineKeyboardButton(text='🔙 Назад', callback_data='nav:admin:chests')]])
    await message.answer(text, reply_markup=kb, parse_mode='Markdown')

async def screen_admin_card(message: Message, card_id: int) -> None:
    if message.from_user is None:
        return
    if not is_admin_id(message.from_user.id):
        await message.answer(f"{h('🛠 Админ')}\nДоступ запрещён.", reply_markup=main_menu())
        return
    async with SessionLocal() as session:
        card = await session.get(BcCard, card_id)
        if card is None:
            await message.answer(f"{h('🃏 Карточки')}\nКарточка не найдена.", reply_markup=main_menu())
            return
        rarity = await session.get(BcRarity, card.rarity_key)
    rarity_title = f"{rarity.emoji} {rarity.title}" if rarity else card.rarity_key
    tags = ', '.join(card.tags or []) if card.tags else '—'
    text = f"{h('🃏 Карточка')}\nID: `{card.id}`\nКлюч: `{card.key}`\nНазвание: {card.title}\nОписание: {card.description}\nСерия: {card.series}\nРедкость: {rarity_title}\nОчки: {card.base_points}\nМонеты: {card.base_coins}\nШанс: {card.drop_weight:g}\nЛимитка: {('да' if card.is_limited else 'нет')}\nПродажа: {('да' if card.is_sellable else 'нет')}\nАктивна: {('да' if card.is_active else 'нет')}\nСортировка: {card.sort}\nТеги: {tags}\nФото: {('загружено' if card.image_file_id else 'нет')}\nImage file id: {card.image_file_id or '—'}"
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='✏️ Редактировать', callback_data=f"act:admin:card:edit:{card.id}")],
        [InlineKeyboardButton(text='🖼 Обновить фото', callback_data=f"act:admin:card:photo:{card.id}")],
        [
            InlineKeyboardButton(text=('🟢 Активна' if card.is_active else '⚪ Неактивна'), callback_data=f"act:admin:card:toggle_active:{card.id}"),
            InlineKeyboardButton(text=('💰 В продаже' if card.is_sellable else '🚫 Не продаётся'), callback_data=f"act:admin:card:toggle_sell:{card.id}"),
        ],
        [InlineKeyboardButton(text='🗑 Удалить', callback_data=f"act:admin:card:delete:{card.id}")],
        [InlineKeyboardButton(text='🔙 Назад', callback_data='nav:admin:cards')],
    ])
    if card.image_file_id:
        await message.answer_photo(card.image_file_id, caption=text, reply_markup=kb, parse_mode='Markdown')
    else:
        await message.answer(text, reply_markup=kb, parse_mode='Markdown')


async def screen_admin_rp_category(message: Message, category_key: str) -> None:
    if message.from_user is None or not is_admin_id(message.from_user.id):
        await message.answer(f"{h('🛠 Админ')}\nДоступ запрещён.", reply_markup=main_menu())
        return
    async with SessionLocal() as session:
        category = await session.get(BcRPCategory, category_key)
        if category is None:
            await message.answer(f"{h('🎭 RP')}\nКатегория не найдена.", reply_markup=main_menu())
            return
        actions = (await session.scalars(select(BcRPAction).where(BcRPAction.category_key == category.key).order_by(BcRPAction.sort))).all()
    lines = [
        h('🎭 RP-категория'),
        f"Ключ: `{category.key}`",
        f"Название: {category.emoji} {category.title}",
        f"Сортировка: {category.sort}",
        f"Активна: {"да" if category.is_active else "нет"}",
        f"Действий внутри: {len(actions)}",
    ]
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='✏️ Редактировать', callback_data=f"act:admin:rp_category:edit:{category.key}")],
        [InlineKeyboardButton(text='🗑 Удалить', callback_data=f"act:admin:rp_category:delete:{category.key}")],
        [InlineKeyboardButton(text='🔙 Назад', callback_data='nav:admin:rp')],
    ])
    await message.answer('\n'.join(lines), reply_markup=kb, parse_mode='Markdown')


async def screen_admin_rp_action(message: Message, action_key: str) -> None:
    if message.from_user is None or not is_admin_id(message.from_user.id):
        await message.answer(f"{h('🛠 Админ')}\nДоступ запрещён.", reply_markup=main_menu())
        return
    async with SessionLocal() as session:
        action = await session.get(BcRPAction, action_key)
        if action is None:
            await message.answer(f"{h('🎭 RP')}\nДействие не найдено.", reply_markup=main_menu())
            return
    reward = dict(action.reward or {})
    scopes = dict(action.allowed_scopes or {})
    lines = [
        h('🎭 RP-действие'),
        f"Ключ: `{action.key}`",
        f"Категория: `{action.category_key}`",
        f"Название: {action.emoji} {action.title}",
        f"Нужна цель: {"да" if action.requires_target else "нет"}",
        f"Кулдаун: {action.cooldown_seconds}с",
        f"Награда: +{int(reward.get("coins") or 0)}🪙 +{int(reward.get("stars") or 0)}⭐ +{int(reward.get("points") or 0)}✨",
        f"Media ID: {action.media_id or "—"}",
        f"Private: {"да" if scopes.get("private", True) else "нет"}",
        f"Group: {"да" if scopes.get("group", True) else "нет"}",
        f"Активно: {"да" if action.is_active else "нет"}",
    ]
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='✏️ Редактировать', callback_data=f"act:admin:rp_action:edit:{action.key}")],
        [InlineKeyboardButton(text='🗑 Удалить', callback_data=f"act:admin:rp_action:delete:{action.key}")],
        [InlineKeyboardButton(text='🔙 Назад', callback_data='nav:admin:rp')],
    ])
    await message.answer('\n'.join(lines), reply_markup=kb, parse_mode='Markdown')


CARD_WIZARD_STEPS: dict[str, list[str]] = {
    'create': ['key', 'title', 'description', 'rarity_key', 'series', 'points', 'coins', 'drop_weight', 'is_limited', 'is_sellable', 'is_active', 'sort', 'photo'],
    'edit': ['title', 'description', 'rarity_key', 'series', 'points', 'coins', 'drop_weight', 'is_limited', 'is_sellable', 'is_active', 'sort', 'photo'],
}


def card_wizard_prompt(mode: str, step: str, data: dict) -> str:
    title = '🃏 Конструктор карточки'
    current = data.get(step)
    current_line = ''
    if mode == 'edit' and current not in (None, ''):
        current_line = f"\nТекущее значение: `{current}`"
    if step == 'key':
        return f"{h(title)}\nШаг 1. Укажите `key` карточки.\nПример: `rustblade`"
    if step == 'title':
        return f"{h(title)}\nВведите название карточки.{current_line}"
    if step == 'description':
        return f"{h(title)}\nВведите описание карточки.{current_line}"
    if step == 'rarity_key':
        return f"{h(title)}\nВведите `rarity_key`.\nПример: `common`, `rare`, `legendary`.{current_line}"
    if step == 'series':
        return f"{h(title)}\nВведите серию карточки.{current_line}\nДля стандартной серии отправьте `Core`."
    if step == 'points':
        return f"{h(title)}\nВведите базовые очки.{current_line}"
    if step == 'coins':
        return f"{h(title)}\nВведите награду в монетах.{current_line}"
    if step == 'drop_weight':
        return f"{h(title)}\nВведите вес выпадения.\nПример: `1` или `0.35`.{current_line}"
    if step == 'is_limited':
        return f"{h(title)}\nЛимитированная карточка?\nОтправьте `1` или `0`.{current_line}"
    if step == 'is_sellable':
        return f"{h(title)}\nРазрешить продажу?\nОтправьте `1` или `0`.{current_line}"
    if step == 'is_active':
        return f"{h(title)}\nСделать карточку активной?\nОтправьте `1` или `0`.{current_line}"
    if step == 'sort':
        return f"{h(title)}\nВведите сортировку.{current_line}"
    return f"{h(title)}\nОтправьте фото карточки сообщением.\nЕсли фото не нужно, отправьте `-`."


async def save_card_wizard_payload(session, service: BrawlCardsService, user_id: int, payload: dict, *, photo_file_id: str | None=None) -> tuple[bool, str, int | None]:
    mode = str(payload.get('mode') or 'create')
    data = dict(payload.get('data') or {})
    if photo_file_id is not None:
        data['photo'] = photo_file_id
    rarity_key = str(data.get('rarity_key') or '').strip()
    if not rarity_key or await session.get(BcRarity, rarity_key) is None:
        return (False, 'Редкость не найдена.', None)
    image_file_id = str(data.get('photo') or '').strip() or None
    if mode == 'create':
        key = str(data.get('key') or '').strip()
        if not key:
            return (False, 'Нужен key карточки.', None)
        if await session.scalar(select(BcCard.id).where(BcCard.key == key)) is not None:
            return (False, 'Карточка с таким key уже существует.', None)
        card = BcCard(
            key=key,
            title=str(data.get('title') or '').strip(),
            description=str(data.get('description') or '').strip(),
            rarity_key=rarity_key,
            series=str(data.get('series') or 'Core').strip() or 'Core',
            tags=[],
            base_points=int(data.get('points') or 0),
            base_coins=int(data.get('coins') or 0),
            drop_weight=float(data.get('drop_weight') or 1),
            is_limited=bool(int(data.get('is_limited') or 0)),
            limited_series_id=None,
            event_id=None,
            image_file_id=image_file_id,
            image_url=None,
            media_id=None,
            is_sellable=bool(int(data.get('is_sellable') or 0)),
            is_active=bool(int(data.get('is_active') or 1)),
            sort=int(data.get('sort') or 100),
            meta={},
        )
        session.add(card)
        await session.flush()
        await service.clear_input_state(user_id)
        return (True, 'Карточка создана.', card.id)
    card_id = int(payload.get('id') or 0)
    card = await session.get(BcCard, card_id)
    if card is None:
        return (False, 'Карточка не найдена.', None)
    card.title = str(data.get('title') or '').strip()
    card.description = str(data.get('description') or '').strip()
    card.rarity_key = rarity_key
    card.series = str(data.get('series') or 'Core').strip() or 'Core'
    card.base_points = int(data.get('points') or 0)
    card.base_coins = int(data.get('coins') or 0)
    card.drop_weight = float(data.get('drop_weight') or 1)
    card.is_limited = bool(int(data.get('is_limited') or 0))
    card.is_sellable = bool(int(data.get('is_sellable') or 0))
    card.is_active = bool(int(data.get('is_active') or 1))
    card.sort = int(data.get('sort') or 100)
    card.image_file_id = image_file_id
    await session.flush()
    await service.clear_input_state(user_id)
    return (True, 'Карточка обновлена.', card.id)

async def render_rp_screen(message: Message) -> None:
    async with SessionLocal() as session:
        service = BrawlCardsService(session)
        categories = await service.rp_categories()
        body = await template_text(session, message.from_user.id if message.from_user else None, 'screen.rp', 'Выберите нужную категорию.\nЕсли действию нужна цель, ответьте на сообщение пользователя и нажмите кнопку действия.')
    items = [(c.key, f"{c.emoji} {c.title}") for c in categories]
    text = f"{h('🎭 RP')}\n{body}"
    await message.answer(text, reply_markup=ik_rp_categories(items))

async def render_quote_screen(message: Message) -> None:
    async with SessionLocal() as session:
        body = await template_text(session, message.from_user.id if message.from_user else None, 'screen.quote', 'Здесь вы можете создать цитату на основе последней карты или отправить свой текст.')
    text = f"{h('💬 Цитата')}\n{body}"
    await message.answer(text, reply_markup=ik_quote_menu())

async def render_sticker_screen(message: Message) -> None:
    async with SessionLocal() as session:
        body = await template_text(session, message.from_user.id if message.from_user else None, 'screen.sticker', 'Здесь вы можете сделать стикер по последней карте или по шаблону с вашим текстом.')
    text = f"{h('🎨 Стикер')}\n{body}"
    await message.answer(text, reply_markup=ik_sticker_menu())

async def render_games_screen(message: Message) -> None:
    async with SessionLocal() as session:
        body = await template_text(session, message.from_user.id if message.from_user else None, 'screen.games', 'Здесь вы можете выбрать мини-игру. У каждой игры есть ставки, награды и кулдаун.')
    text = f"{h('🎲 Игры')}\n{body}"
    await message.answer(text, reply_markup=ik_games_menu())

async def render_game_detail(message: Message, game_key: str) -> None:
    titles = {'dice': '🎲 Кости', 'guess_rarity': '🎯 Угадай редкость', 'coinflip': '🪙 Орёл/решка', 'card_battle': '🃏 Битва карточек', 'slot': '🎰 Слот'}
    title = titles.get(game_key)
    if title is None:
        await render_games_screen(message)
        return
    text = f"{h(title)}\nВыберите ставку. Система автоматически применяет антиабуз через кулдаун и проверку баланса."
    await message.answer(text, reply_markup=ik_game_stakes(game_key))

async def render_market_screen(message: Message) -> None:
    async with SessionLocal() as session:
        body = await template_text(session, message.from_user.id if message.from_user else None, 'screen.market', 'Здесь вы можете покупать карточки, выставлять свои лоты и смотреть историю торговли.')
    text = f"{h('💱 Маркет')}\n{body}"
    await message.answer(text, reply_markup=ik_market_menu())

async def render_market_list(message: Message, mode: str) -> None:
    if message.from_user is None:
        return
    async with SessionLocal() as session:
        service = BrawlCardsService(session)
        if mode == 'buy':
            rows = await service.market_lots(active_only=True, limit=12)
            title = '🛒 Купить карточку'
        elif mode == 'limited':
            rows = await service.market_lots(only_limited=True, active_only=True, limit=12)
            title = '⭐ Лимитированные'
        elif mode == 'my':
            rows = await service.market_lots(seller_id=message.from_user.id, active_only=False, limit=12)
            title = '📜 Мои лоты'
        else:
            rows = await service.market_lots(buyer_or_seller_id=message.from_user.id, active_only=False, limit=12)
            title = 'РІРЏВ± Р\xa0\x98РЎРѓРЎвЂљР\xa0С•РЎР‚Р\xa0С‘РЎРЏ'
    lines = [h(title), 'Выберите нужный лот.']
    buttons: list[list] = []
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    for lot, card, seller in rows:
        seller_name = seller.nickname or seller.first_name or str(seller.id)
        lines.append(f"#{lot.id} {card.title} | {lot.price} {lot.currency} | {seller_name}")
        buttons.append([InlineKeyboardButton(text=f"Лот #{lot.id}: {card.title}", callback_data=f"nav:market_lot:{lot.id}")])
    buttons.append([InlineKeyboardButton(text='🔙 Назад', callback_data='nav:market')])
    await message.answer('\n'.join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

async def render_market_lot(message: Message, lot_id: int) -> None:
    if message.from_user is None:
        return
    async with SessionLocal() as session:
        rows = await BrawlCardsService(session).market_lots(active_only=False, limit=200)
    found = next((row for row in rows if row[0].id == lot_id), None)
    if found is None:
        await message.answer(f"{h('💱 Маркет')}\nЛот не найден.", reply_markup=ik_market_menu())
        return
    lot, card, seller = found
    seller_name = seller.nickname or seller.first_name or str(seller.id)
    text = f"{h('💱 Лот')}\nID: `{lot.id}`\nКарта: *{card.title}*\nРедкость: {card.rarity_key}\nПродавец: {seller_name}\nР¦РµРЅР°: {lot.price} {lot.currency}\nКомиссия: {lot.fee_percent}%\nСтатус: {lot.status}"
    await message.answer(text, reply_markup=ik_market_lot_actions(lot.id, can_buy=lot.seller_id != message.from_user.id and lot.status == 'active', can_cancel=lot.seller_id == message.from_user.id and lot.status == 'active'), parse_mode='Markdown')

async def render_marriage_screen(message: Message) -> None:
    async with SessionLocal() as session:
        body = await template_text(session, message.from_user.id if message.from_user else None, 'screen.marriage', 'Здесь вы можете сделать предложение, проверить входящие и открыть экран вашей пары.')
    text = f"{h('💍 Брак')}\n{body}"
    await message.answer(text, reply_markup=ik_marriage_menu())

async def render_marriage_pair(message: Message) -> None:
    if message.from_user is None:
        return
    async with SessionLocal() as session:
        service = BrawlCardsService(session)
        pair = await service.marriage_of(message.from_user.id)
    if pair is None:
        await message.answer(f"{h('💍 Брак')}\nВы пока не состоите в браке.", reply_markup=ik_marriage_menu())
        return
    partner_id = pair.user2_id if pair.user1_id == message.from_user.id else pair.user1_id
    text = f"{h('💍 Пара')}\nВаш союз активен.\nПартнёр ID: `{partner_id}`\nДата: {pair.created_at.date().isoformat()}\nБонусы пары и совместный профиль уже готовы для дальнейшего расширения."
    await message.answer(text, reply_markup=ik_marriage_menu(), parse_mode='Markdown')

async def render_marriage_inbox(message: Message) -> None:
    if message.from_user is None:
        return
    async with SessionLocal() as session:
        service = BrawlCardsService(session)
        rows = await service.marriage_inbox(message.from_user.id)
    if not rows:
        await message.answer(f"{h('РЎР‚РЎСџРІР‚в„ўР\xa0РЉ Р\xa0\xa0РІР‚\x98Р\xa0РЋР\xa0вЂљР\xa0\xa0Р’В°Р\xa0\xa0РЎвЂќ')}\nВходящих предложений нет.", reply_markup=ik_marriage_menu())
        return
    for row in rows[:10]:
        text = f"{h('💍 Предложение')}\nID: `{row.id}`\nОт пользователя: `{row.proposer_id}`\nДата: {row.created_at.date().isoformat()}"
        await message.answer(text, reply_markup=ik_marriage_proposal(row.id), parse_mode='Markdown')

async def render_settings_screen(message: Message) -> None:
    if message.from_user is None:
        return
    async with SessionLocal() as session:
        service = BrawlCardsService(session)
        s = await service.user_settings(message.from_user.id)
        body = await template_text(session, message.from_user.id, 'screen.settings', 'Управляйте уведомлениями, языком, приватностью, стилем выдачи карт и безопасным режимом.')
    text = f"{h('⚙️ Настройки')}\n{body}\n\n🔔 Уведомления: {('вкл' if s.notifications else 'выкл')}\n🌐 Язык: {s.locale}\n🔐 Приватность: {('скрытая' if (s.privacy or {}).get('hidden') else 'обычная')}\n🧾 Подтверждение покупок: {('вкл' if s.confirm_purchases else 'выкл')}\n🃏 Стиль выдачи карт: {s.card_style}\n🖼 Отображение медиа: {('вкл' if s.show_media else 'выкл')}\n🛡 Безопасный режим: {('вкл' if s.safe_mode else 'выкл')}"
    await message.answer(text, reply_markup=ik_settings())

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
            await message.answer(f"{h('📢 Рассылка')}\nМассовые рассылки уже доступны через отдельный admin bot и готовы к переносу в кнопку-форму.", reply_markup=ik_admin_main())
            return True
        if section == 'events':
            rows = (await session.scalars(select(BcEvent).order_by(BcEvent.created_at.desc()).limit(10))).all()
            lines = [h('СЂСџР‹вЂ° Р\xa0\x98Р\xa0Р†Р\xa0ВµР\xa0Р…РЎвЂљРЎвЂ№'), 'Список ивентов:']
            if not rows:
                lines.append('РІР‚Сћ Р\xa0\x98Р\xa0Р†Р\xa0ВµР\xa0Р…РЎвЂљРЎвЂ№ Р\xa0ВµРЎвЂ°РЎвЂ\x98 Р\xa0Р…Р\xa0Вµ РЎРѓР\xa0С•Р\xa0В·Р\xa0Т‘Р\xa0В°Р\xa0Р…РЎвЂ№.')
            for event in rows:
                lines.append(f"• {event.title} | key={event.key} | active={int(event.is_active)}")
            await message.answer('\n'.join(lines), reply_markup=ik_admin_main())
            return True
        if section == 'permissions':
            roles = (await session.scalars(select(BcRole).order_by(BcRole.key))).all()
            perms = (await session.scalars(select(BcPermission).order_by(BcPermission.code).limit(20))).all()
            lines = [h('🔐 Права'), 'Р\xa0РѕР»Рё:']
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
            lines = [
                h('⚙️ Настройки бота'),
                'Здесь можно менять игровые таймеры, награды и bonus-ссылки.',
                '',
                '⏱ Кулдауны:',
                f"• Карта: {int(cooldowns.get("brawl_cards") or 0)}с",
                f"• Бонус: {int(cooldowns.get("bonus") or 0)}с",
                f"• Смена ника: {int(cooldowns.get("nick_change") or 0)}с",
                f"• Dice: {int(cooldowns.get("dice") or 0)}с",
                f"• Guess rarity: {int(cooldowns.get("guess_rarity") or 0)}с",
                f"• Coinflip: {int(cooldowns.get("coinflip") or 0)}с",
                f"• Card battle: {int(cooldowns.get("card_battle") or 0)}с",
                f"• Slot: {int(cooldowns.get("slot") or 0)}с",
                f"• Premium reduction: {int(cooldowns.get("premium_game_reduction") or 0)}с",
                '',
                '🎁 Награды:',
                f"• Bonus coins: {int(rewards.get("bonus_coins") or 0)}",
                f"• Bonus stars: {int(rewards.get("bonus_stars") or 0)}",
                f"• Market fee: {int(rewards.get("market_fee_percent") or 0)}%",
                '',
                '🔗 Bonus-ссылки:',
                f"• chat: {links.get("chat") or "—"}",
                f"• subscribe: {links.get("subscribe") or "—"}",
                f"• news: {links.get("news") or "—"}",
                f"• invite: {links.get("invite") or "—"}",
                f"• partner: {links.get("partner") or "—"}",
            ]
            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text='⏱ Изменить кулдауны', callback_data='act:admin:sys:edit:cooldowns')],
                    [InlineKeyboardButton(text='🎁 Изменить награды', callback_data='act:admin:sys:edit:rewards')],
                    [InlineKeyboardButton(text='🔗 Изменить bonus-ссылки', callback_data='act:admin:sys:edit:bonus_links')],
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

async def render_inventory_screen(message: Message) -> None:
    if message.from_user is None:
        return
    async with SessionLocal() as session:
        rows = (await session.execute(select(BcBooster.title, BcActiveBooster.stacks, BcActiveBooster.active_until).join(BcActiveBooster, BcActiveBooster.booster_key == BcBooster.key).where(BcActiveBooster.user_id == message.from_user.id).order_by(BcBooster.key))).all()
    if not rows:
        await message.answer(f"{h('СЂСџР‹вЂ™ Р\xa0\x98Р\xa0Р…Р\xa0Р†Р\xa0ВµР\xa0Р…РЎвЂљР\xa0В°РЎР‚РЎРЉ')}\nАктивных бустеров пока нет.", reply_markup=ik_profile())
        return
    lines = [h('СЂСџР‹вЂ™ Р\xa0\x98Р\xa0Р…Р\xa0Р†Р\xa0ВµР\xa0Р…РЎвЂљР\xa0В°РЎР‚РЎРЉ'), 'Здесь показаны ваши активные бустеры:']
    for title, stacks, active_until in rows:
        until = active_until.isoformat(timespec='minutes') if active_until else 'без таймера'
        lines.append(f"• {title} x{stacks} | {until}")
    await message.answer('\n'.join(lines), reply_markup=ik_profile())

async def render_profile_stats_screen(message: Message) -> None:
    if message.from_user is None:
        return
    async with SessionLocal() as session:
        user = await session.get(User, message.from_user.id)
        profile = await session.get(UserProfile, message.from_user.id)
        if user is None or profile is None:
            await message.answer(f"{h('📈 Статистика')}\nПрофиль не найден.", reply_markup=ik_profile())
            return
        total_cards = await session.scalar(select(func.count()).select_from(BcCardInstance).where(BcCardInstance.user_id == user.id))
        unique_cards = await session.scalar(select(func.count(func.distinct(BcCardInstance.card_id))).where(BcCardInstance.user_id == user.id))
    text = f"{h('📈 Статистика')}\nОчки: {user.total_points}\nМонеты: {user.coins}\nЗвёзды: {user.stars}\nВсего карт: {int(total_cards or 0)}\nУникальных карт: {int(unique_cards or 0)}\nР\xa0\x98Р\xa0С–РЎР‚ РЎРѓРЎвЂ№Р\xa0С–РЎР‚Р\xa0В°Р\xa0Р…Р\xa0С•: {profile.games_played}\nПобед: {profile.games_won}\nПродано на маркете: {profile.market_sold}\nКуплено на маркете: {profile.market_bought}\nЗаданий выполнено: {profile.tasks_done}"
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
    premium_text = premium_until.isoformat(timespec="minutes") if premium_until else "?? ???????"
    lines = [
        h("?? ?????????"),
        "????? ???????? ??? ??????, ???????? ? ?????????? ? ????????? ?????????.",
        "",
        f"?? ??????: {overview['coins']}",
        f"? ??????: {overview['stars']}",
        f"? ????: {overview['points']}",
        f"?? ???????: {overview['level']}",
        f"?? ?????: {overview['cards_total']} / ?????????? {overview['cards_unique']}",
        f"? ???????? ???????: {overview['boosters_active']}",
        f"?? ??????? ?????: {seconds_to_hms(int(overview['card_cooldown']))}",
        f"?? ??????? ??????: {seconds_to_hms(int(overview['bonus_cooldown']))}",
        f"?? Premium: {premium_text}",
    ]
    await message.answer(
        "\n".join(lines),
        reply_markup=ik_list_nav([("shop", "?? ? ???????"), ("premium", "?? Premium"), ("top", "?? ???")], prefix="nav", back_to="profile"),
    )


async def screen_shop_offers(message: Message) -> None:
    async with SessionLocal() as session:
        service = BrawlCardsService(session)
        items = await service.shop_offers(8)
    if not items:
        await message.answer(f"{h('?? ??????')}\n???? ??? ???????? ???????????.", reply_markup=ik_shop_categories())
        return
    lines = [h("?? ??????"), "??????? ???????????, ??????? ????? ??????? ? ???? ???:"]
    buttons: list[tuple[str, str]] = []
    for item in items:
        price_parts: list[str] = []
        if item.price_coins is not None:
            price_parts.append(f"{item.price_coins}??")
        if item.price_stars is not None:
            price_parts.append(f"{item.price_stars}?")
        price_text = " / ".join(price_parts) if price_parts else "?????????"
        lines.append(f"? {item.title} ? {price_text}")
        buttons.append((item.key, item.title[:32]))
    await message.answer("\n".join(lines), reply_markup=ik_list_nav(buttons, prefix="nav:shop_item", back_to="shop"))


async def screen_events(message: Message) -> None:
    async with SessionLocal() as session:
        service = BrawlCardsService(session)
        events = await service.active_events()
    if not events:
        await message.answer(f"{h('?? ??????')}\n?????? ???????? ??????? ???.", reply_markup=ik_shop_categories())
        return
    lines = [h("?? ??????"), "???????? ??????? ? ????????? ?????? ???????:"]
    for event in events[:10]:
        ends = event.ends_at.isoformat(timespec="minutes") if event.ends_at else "??? ?????"
        lines.append(f"? {event.title}\n{event.description[:120]}\n??: {ends}")
    await message.answer(
        "\n".join(lines),
        reply_markup=ik_list_nav([("shop", "?? ???????"), ("tasks", "?? ???????"), ("bonus", "?? ?????")], prefix="nav", back_to="main"),
    )


SCREEN_BY_BUTTON: dict[str, str] = {BTN_PROFILE: 'profile', BTN_GET_CARD: 'get_card', BTN_BONUS: 'bonus', BTN_TOP: 'top', BTN_SHOP: 'shop', BTN_CHEST: 'chest', BTN_PREMIUM: 'premium', BTN_TASKS: 'tasks', BTN_RP: 'rp', BTN_QUOTE: 'quote', BTN_STICKER: 'sticker', BTN_GAMES: 'games', BTN_MARKET: 'market', BTN_MARRIAGE: 'marriage', BTN_SETTINGS: 'settings', BTN_ADMIN: 'admin', '?? ?????-??????': 'admin', '?? ????? ??????': 'admin', '?????-??????': 'admin', '????? ??????': 'admin'}

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
        await render_rp_screen(message)
    elif screen == 'quote':
        await render_quote_screen(message)
    elif screen == 'sticker':
        await render_sticker_screen(message)
    elif screen == 'games':
        await render_games_screen(message)
    elif screen == 'market':
        await render_market_screen(message)
    elif screen == 'marriage':
        await render_marriage_screen(message)
    elif screen == 'settings':
        await render_settings_screen(message)
    elif screen == 'admin':
        await screen_admin(message)
    else:
        await screen_main(message)

@router.message(CommandStart())
async def on_start(message: Message) -> None:
    await ensure_user(message)
    await send_start(message)

@router.message(Command(commands=['help', 'помощь']))
async def on_help(message: Message) -> None:
    await message.answer(f"{h('ℹ️ Помощь')}\nЭтот бот почти не использует slash-команды.\nОткройте меню снизу и нажимайте кнопки.\n\nКоманды для входа:\n/start — главное меню")

@router.message(Command(commands=['admin']))
async def on_admin_command(message: Message) -> None:
    await ensure_user(message)
    await show_screen(message, 'admin')

@router.message(F.text.in_(MAIN_MENU_BUTTONS))
async def on_main_menu_button(message: Message) -> None:
    if message.text is None:
        return
    await ensure_user(message)
    await show_screen(message, SCREEN_BY_BUTTON.get(message.text, 'main'))

@router.message(F.text.in_(['🛠 Админ-панель', '🛠 Админ панель', 'Админ-панель', 'Админ панель']))
async def on_menu_alias(message: Message) -> None:
    if message.text is None:
        return
    await ensure_user(message)
    await show_screen(message, 'admin')

@router.callback_query(F.data.startswith('nav:'))
async def on_nav(callback: CallbackQuery) -> None:
    if callback.message is None or callback.data is None:
        return
    await callback.answer()
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
    await callback.answer()
    action = callback.data
    async with SessionLocal() as session:
        service = BrawlCardsService(session)
        async with session.begin():
            await service.ensure_user(callback.from_user.id, callback.from_user.username, callback.from_user.first_name)
            if action == 'act:nick:enter':
                await service.set_input_state(callback.from_user.id, 'nick_wait', {})
                await callback.message.answer(f"{h('✏️ Смена ника')}\nОтправьте новый ник одним сообщением.", reply_markup=main_menu())
                return
            if action == 'act:card:repeat_later':
                cd = await service.get_cooldown(callback.from_user.id, 'brawl_cards')
                await callback.message.answer(f"{h('🃏 Получить карту')}\nОжидание: {seconds_to_hms(cd.seconds_left)}", reply_markup=main_menu())
                return
            if action == 'act:card:open_full':
                state = await session.get(BcUserState, callback.from_user.id)
                if state is None or state.last_card_id is None:
                    await callback.message.answer(f"{h('🖼 Карточка')}\nНет последней карты.", reply_markup=main_menu())
                    return
                card = await session.get(BcCard, state.last_card_id)
                if card is None:
                    await callback.message.answer(f"{h('🖼 Карточка')}\nКарта не найдена.", reply_markup=main_menu())
                    return
                if card.image_file_id:
                    await callback.message.answer_photo(card.image_file_id, caption=f"{h('🖼 Карточка полностью')}\n*{card.title}*\n{card.description}", parse_mode='Markdown')
                else:
                    await callback.message.answer(f"{h('🖼 Карточка полностью')}\n*{card.title}*\n{card.description}", parse_mode='Markdown')
                return
            if action == 'act:card:to_collection':
                await callback.message.answer(f"{h('📂 Коллекция')}\nКарта уже добавлена в коллекцию автоматически.", reply_markup=main_menu())
                return
            if action.startswith('act:buy_xtr:'):
                item_key = action.split(':', maxsplit=2)[2]
                item = await service.shop_item(item_key)
                if item is None or item.price_stars is None:
                    await callback.message.answer(f"{h('Telegram Stars')}\n????? ?????????? ??? ?????? Telegram Stars.", reply_markup=main_menu())
                    return
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
                    await callback.message.answer(f"{h('🛒 Покупка')}\n{resp}", reply_markup=main_menu())
                    return
            if action.startswith('act:chest:open:'):
                chest_key = action.split(':', maxsplit=3)[3]
                result = await service.chest_open(callback.from_user.id, chest_key)
                if not result.get('ok'):
                    await callback.message.answer(f"{h('📦 Сундук')}\n{result.get('error', 'Ошибка')}", reply_markup=main_menu())
                    return
                await service.inc_task_counter(callback.from_user.id, 'open_chest', 1)
                drops = result['drops']
                lines = [h(f"{result['chest']['emoji']} Открытие сундука"), f"Сундук: {result['chest']['title']}"]
                total_points = 0
                total_coins = 0
                for d in drops:
                    lines.append(f"• {d['rarity']} — {d['title']} (+{d['points']}✨ +{d['coins']}🪙)")
                    total_points += int(d['points'])
                    total_coins += int(d['coins'])
                lines.append(f"\nР\xa0\x98РЎвЂљР\xa0С•Р\xa0С–Р\xa0С•: +{total_points}✨ +{total_coins}🪙")
                await callback.message.answer('\n'.join(lines), reply_markup=main_menu())
                return
            if action.startswith('act:task:claim:'):
                task_key = action.split(':', maxsplit=3)[3]
                ok, resp = await service.claim_task_reward(callback.from_user.id, task_key)
                await callback.message.answer(f"{h('📜 Задания')}\n{resp}", reply_markup=main_menu())
                return
            if action.startswith('act:bonus:open:'):
                task_key = action.split(':', maxsplit=3)[3]
                task = await session.get(BcBonusTask, task_key)
                if task is None or not task.is_active:
                    await callback.message.answer(f"{h('🎁 Бонус')}\nЗадание не найдено.", reply_markup=main_menu())
                    return
                from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
                rows = []
                task_url = await service.resolve_bonus_url(task)
                if task_url:
                    rows.append([InlineKeyboardButton(text=f"{task.emoji} Открыть ссылку", url=task_url)])
                rows.append([InlineKeyboardButton(text='✅ Отметить выполненным', callback_data=f"act:bonus:mark:{task.key}")])
                rows.append([InlineKeyboardButton(text='🔙 Назад', callback_data='nav:bonus')])
                kb = InlineKeyboardMarkup(inline_keyboard=rows)
                await callback.message.answer(f"{h('🎁 Задание')}\n{task.description}", reply_markup=kb)
                return
            if action.startswith('act:bonus:mark:'):
                task_key = action.split(':', maxsplit=3)[3]
                await service.mark_bonus_task_done(callback.from_user.id, task_key)
                await callback.message.answer(f"{h('🎁 Бонус')}\nЗадание отмечено как выполненное.", reply_markup=main_menu())
                return
            if action == 'act:bonus:check':
                ok, resp = await service.bonus_claim_if_ready(callback.from_user.id)
                await callback.message.answer(f"{h('🎁 Бонус')}\n{resp}", reply_markup=main_menu())
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
                    await callback.message.answer(f"{h('🎭 RP')}\n{result['message']}", reply_markup=main_menu())
                    return
                if not result.get('ok'):
                    await callback.message.answer(f"{h('🎭 RP')}\n{result['message']}", reply_markup=main_menu())
                    return
                await send_rp_result(callback.message, f"{h('🎭 RP')}\n{result['text']}", result.get('media'))
                return
            if action.startswith('act:game:play:'):
                _, _, _, game_key, stake = action.split(':')
                ok, resp = await service.game_play(callback.from_user.id, game_key, int(stake))
                await callback.message.answer(f"{h('🎲 Игры')}\n{resp}", reply_markup=main_menu())
                return
            if action == 'act:market:sell:start':
                await service.set_input_state(callback.from_user.id, 'market_sell_wait', {})
                await callback.message.answer(f"{h('💱 Маркет')}\nОтправьте строку в формате:\n`instance_id|coins_or_stars|price`\nПример: `15|coins|1200`", parse_mode='Markdown', reply_markup=main_menu())
                return
            if action == 'act:market:search:start':
                await callback.message.answer(f"{h('💱 Маркет')}\nПоиск и фильтры будут расширены отдельно. Пока используйте разделы покупки, лимиток и истории.", reply_markup=ik_market_menu())
                return
            if action.startswith('act:market:buy:'):
                lot_id = int(action.split(':')[3])
                ok, resp = await service.market_buy_lot(callback.from_user.id, lot_id)
                await callback.message.answer(f"{h('💱 Маркет')}\n{resp}", reply_markup=main_menu())
                return
            if action.startswith('act:market:cancel:'):
                lot_id = int(action.split(':')[3])
                ok, resp = await service.market_cancel_lot(callback.from_user.id, lot_id)
                await callback.message.answer(f"{h('💱 Маркет')}\n{resp}", reply_markup=main_menu())
                return
            if action == 'act:marriage:propose:start':
                await service.set_input_state(callback.from_user.id, 'marriage_propose_wait', {})
                await callback.message.answer(f"{h('РЎР‚РЎСџРІР‚в„ўР\xa0РЉ Р\xa0\xa0РІР‚\x98Р\xa0РЋР\xa0вЂљР\xa0\xa0Р’В°Р\xa0\xa0РЎвЂќ')}\nОтправьте ID пользователя, которому хотите сделать предложение.", reply_markup=main_menu())
                return
            if action.startswith('act:marriage:accept:'):
                proposal_id = int(action.split(':')[3])
                ok, resp = await service.marriage_decide(callback.from_user.id, proposal_id, accept=True)
                await callback.message.answer(f"{h('РЎР‚РЎСџРІР‚в„ўР\xa0РЉ Р\xa0\xa0РІР‚\x98Р\xa0РЋР\xa0вЂљР\xa0\xa0Р’В°Р\xa0\xa0РЎвЂќ')}\n{resp}", reply_markup=main_menu())
                return
            if action.startswith('act:marriage:decline:'):
                proposal_id = int(action.split(':')[3])
                ok, resp = await service.marriage_decide(callback.from_user.id, proposal_id, accept=False)
                await callback.message.answer(f"{h('РЎР‚РЎСџРІР‚в„ўР\xa0РЉ Р\xa0\xa0РІР‚\x98Р\xa0РЋР\xa0вЂљР\xa0\xa0Р’В°Р\xa0\xa0РЎвЂќ')}\n{resp}", reply_markup=main_menu())
                return
            if action == 'act:quote:last_card':
                state = await session.get(BcUserState, callback.from_user.id)
                if state is None or state.last_card_id is None:
                    await callback.message.answer(f"{h('💬 Цитата')}\nСначала получите карту.", reply_markup=main_menu())
                    return
                card = await session.get(BcCard, state.last_card_id)
                if card is None:
                    await callback.message.answer(f"{h('💬 Цитата')}\nКарта не найдена.", reply_markup=main_menu())
                    return
                await callback.message.answer(f"{h('💬 Цитата')}\nВ«{card.title}В»\n{card.description}", reply_markup=main_menu())
                return
            if action == 'act:quote:custom':
                await service.set_input_state(callback.from_user.id, 'quote_wait', {})
                await callback.message.answer(f"{h('💬 Цитата')}\nОтправьте текст цитаты одним сообщением.", reply_markup=main_menu())
                return
            if action == 'act:sticker:last_card':
                await service.set_input_state(callback.from_user.id, 'sticker_last_wait', {})
                await callback.message.answer(f"{h('🎨 Стикер')}\nОтправьте подпись для стикера по последней карте.", reply_markup=main_menu())
                return
            if action == 'act:sticker:template':
                await service.set_input_state(callback.from_user.id, 'sticker_template_wait', {})
                await callback.message.answer(f"{h('🎨 Стикер')}\nОтправьте текст для шаблонного стикера.", reply_markup=main_menu())
                return
            if action.startswith('act:settings:toggle:'):
                key = action.split(':')[3]
                ok, resp = await service.toggle_setting(callback.from_user.id, key)
                await callback.message.answer(f"{h('⚙️ Настройки')}\n{resp}", reply_markup=main_menu())
                return
            if action.startswith('act:settings:cycle:'):
                key = action.split(':')[3]
                ok, resp = await service.cycle_setting(callback.from_user.id, key)
                await callback.message.answer(f"{h('⚙️ Настройки')}\n{resp}", reply_markup=main_menu())
                return
            if action == 'act:admin:card:create':
                if not is_admin_id(callback.from_user.id):
                    await callback.message.answer('Access denied', reply_markup=main_menu())
                    return
                await service.set_input_state(callback.from_user.id, 'admin_card_wizard', {'mode': 'create', 'step': 'key', 'data': {}})
                await callback.message.answer(card_wizard_prompt('create', 'key', {}), parse_mode='Markdown', reply_markup=main_menu())
                return
            if action.startswith('act:admin:card:edit:'):
                if not is_admin_id(callback.from_user.id):
                    await callback.message.answer('Access denied', reply_markup=main_menu())
                    return
                card_id = int(action.split(':', maxsplit=4)[4])
                card = await session.get(BcCard, card_id)
                if card is None:
                    await callback.message.answer('Карточка не найдена.', reply_markup=main_menu())
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
                await callback.message.answer(
                    f"{h('🃏 Редактор карточки')}\nПошаговое редактирование начато.\nНа любом текстовом шаге отправьте `-`, чтобы оставить текущее значение.\n\n{card_wizard_prompt('edit', 'title', data)}",
                    parse_mode='Markdown',
                    reply_markup=main_menu(),
                )
                return
            if action.startswith('act:admin:card:photo:'):
                if not is_admin_id(callback.from_user.id):
                    await callback.message.answer('Access denied', reply_markup=main_menu())
                    return
                card_id = int(action.split(':', maxsplit=4)[4])
                await service.set_input_state(callback.from_user.id, 'admin_card_photo', {'id': card_id})
                await callback.message.answer(f"{h('🖼 Фото карточки')}\nОтправьте новое фото сообщением.", reply_markup=main_menu())
                return
            if action.startswith('act:admin:card:toggle_active:'):
                if not is_admin_id(callback.from_user.id):
                    await callback.message.answer('Access denied', reply_markup=main_menu())
                    return
                card_id = int(action.split(':', maxsplit=5)[4])
                card = await session.get(BcCard, card_id)
                if card is None:
                    await callback.message.answer('Карточка не найдена.', reply_markup=main_menu())
                    return
                card.is_active = not card.is_active
                await callback.message.answer('Статус активности карточки обновлён.', reply_markup=main_menu())
                return
            if action.startswith('act:admin:card:toggle_sell:'):
                if not is_admin_id(callback.from_user.id):
                    await callback.message.answer('Access denied', reply_markup=main_menu())
                    return
                card_id = int(action.split(':', maxsplit=5)[4])
                card = await session.get(BcCard, card_id)
                if card is None:
                    await callback.message.answer('Карточка не найдена.', reply_markup=main_menu())
                    return
                card.is_sellable = not card.is_sellable
                await callback.message.answer('Статус продажи карточки обновлён.', reply_markup=main_menu())
                return
            if action.startswith('act:admin:card:delete:'):
                if not is_admin_id(callback.from_user.id):
                    await callback.message.answer('Access denied', reply_markup=main_menu())
                    return
                card_id = int(action.split(':', maxsplit=4)[4])
                card = await session.get(BcCard, card_id)
                if card is None:
                    await callback.message.answer('Карточка не найдена.', reply_markup=main_menu())
                    return
                await session.delete(card)
                await callback.message.answer('Карточка удалена.', reply_markup=main_menu())
                return
            if action == 'act:admin:rp_category:create':
                if not is_admin_id(callback.from_user.id):
                    await callback.message.answer('Access denied', reply_markup=main_menu())
                    return
                await service.set_input_state(callback.from_user.id, 'admin_rp_category_form', {'mode': 'create'})
                await callback.message.answer(
                    f"{h('🎭 Категория RP')}\nОтправьте одной строкой:\n`key|Название|emoji|sort|active(0/1)`\n\nПример:\n`romance|Романтические|💘|20|1`",
                    parse_mode='Markdown',
                    reply_markup=main_menu(),
                )
                return
            if action.startswith('act:admin:rp_category:edit:'):
                if not is_admin_id(callback.from_user.id):
                    await callback.message.answer('Access denied', reply_markup=main_menu())
                    return
                category_key = action.split(':', maxsplit=4)[4]
                await service.set_input_state(callback.from_user.id, 'admin_rp_category_form', {'mode': 'edit', 'key': category_key})
                await callback.message.answer(
                    f"{h('🎭 Категория RP')}\nКлюч: `{category_key}`\nОтправьте строкой:\n`Название|emoji|sort|active(0/1)`",
                    parse_mode='Markdown',
                    reply_markup=main_menu(),
                )
                return
            if action.startswith('act:admin:rp_category:delete:'):
                if not is_admin_id(callback.from_user.id):
                    await callback.message.answer('Access denied', reply_markup=main_menu())
                    return
                category_key = action.split(':', maxsplit=4)[4]
                category = await session.get(BcRPCategory, category_key)
                if category is None:
                    await callback.message.answer('Категория не найдена.', reply_markup=main_menu())
                    return
                await session.delete(category)
                await callback.message.answer('Категория RP удалена.', reply_markup=main_menu())
                return
            if action == 'act:admin:rp_action:create':
                if not is_admin_id(callback.from_user.id):
                    await callback.message.answer('Access denied', reply_markup=main_menu())
                    return
                await service.set_input_state(callback.from_user.id, 'admin_rp_action_form', {'mode': 'create'})
                await callback.message.answer(
                    f"{h('🎭 RP-действие')}\nОтправьте одной строкой:\n`key|category_key|Название|emoji|requires_target(0/1)|cooldown|coins|stars|points|media_id|private(0/1)|group(0/1)|sort|active(0/1)|template1;;template2`\n\nПример:\n`hug|friendly|Обнять|🤝|1|30|0|0|1||1|1|10|1|{{actor}} обнял {{target}};;{{actor}} крепко обнял {{target}}`",
                    parse_mode='Markdown',
                    reply_markup=main_menu(),
                )
                return
            if action.startswith('act:admin:rp_action:edit:'):
                if not is_admin_id(callback.from_user.id):
                    await callback.message.answer('Access denied', reply_markup=main_menu())
                    return
                action_key = action.split(':', maxsplit=4)[4]
                await service.set_input_state(callback.from_user.id, 'admin_rp_action_form', {'mode': 'edit', 'key': action_key})
                await callback.message.answer(
                    f"{h('🎭 RP-действие')}\nКлюч: `{action_key}`\nОтправьте строкой:\n`category_key|Название|emoji|requires_target(0/1)|cooldown|coins|stars|points|media_id|private(0/1)|group(0/1)|sort|active(0/1)|template1;;template2`",
                    parse_mode='Markdown',
                    reply_markup=main_menu(),
                )
                return
            if action.startswith('act:admin:rp_action:delete:'):
                if not is_admin_id(callback.from_user.id):
                    await callback.message.answer('Access denied', reply_markup=main_menu())
                    return
                action_key = action.split(':', maxsplit=4)[4]
                rp_action = await session.get(BcRPAction, action_key)
                if rp_action is None:
                    await callback.message.answer('RP-действие не найдено.', reply_markup=main_menu())
                    return
                await session.delete(rp_action)
                await callback.message.answer('RP-действие удалено.', reply_markup=main_menu())
                return
            if action == 'act:admin:rarity:create':
                if not is_admin_id(callback.from_user.id):
                    await callback.message.answer('Access denied', reply_markup=main_menu())
                    return
                await service.set_input_state(callback.from_user.id, 'admin_rarity_form', {'mode': 'create'})
                await callback.message.answer(f"{h('💎 Добавить редкость')}\nОтправьте одной строкой:\n`key|Название|эмодзи|шанс|цвет|points_mult|coins_mult|drop_mode|in_chests(0/1)|in_shop(0/1)`\nПример:\n`ultra|Ультра|🔶|0.2|#FFAA00|4.2|2.9|normal|1|1`", parse_mode='Markdown', reply_markup=main_menu())
                return
            if action.startswith('act:admin:rarity:edit:'):
                if not is_admin_id(callback.from_user.id):
                    await callback.message.answer('Access denied', reply_markup=main_menu())
                    return
                rarity_key = action.split(':', maxsplit=4)[4]
                await service.set_input_state(callback.from_user.id, 'admin_rarity_form', {'mode': 'edit', 'key': rarity_key})
                await callback.message.answer(f"{h('💎 Редактировать редкость')}\nКлюч: `{rarity_key}`\nОтправьте строкой:\n`Название|эмодзи|шанс|цвет|points_mult|coins_mult|drop_mode|in_chests(0/1)|in_shop(0/1)|active(0/1)`", parse_mode='Markdown', reply_markup=main_menu())
                return
            if action.startswith('act:admin:rarity:delete:'):
                if not is_admin_id(callback.from_user.id):
                    await callback.message.answer('Access denied', reply_markup=main_menu())
                    return
                rarity_key = action.split(':', maxsplit=4)[4]
                r = await session.get(BcRarity, rarity_key)
                if r is None:
                    await callback.message.answer('Редкость не найдена.', reply_markup=main_menu())
                    return
                await session.delete(r)
                await callback.message.answer('Редкость удалена.', reply_markup=main_menu())
                return
            if action == 'act:admin:booster:create':
                if not is_admin_id(callback.from_user.id):
                    await callback.message.answer('Access denied', reply_markup=main_menu())
                    return
                await service.set_input_state(callback.from_user.id, 'admin_booster_form', {'mode': 'create'})
                await callback.message.answer(f"{h('⚡ Добавить бустер')}\nОтправьте одной строкой:\n`key|Название|эмодзи|effect_type|power|price_coins|price_stars|duration_seconds|max_stack|available(0/1)`\nПример:\n`luck2|Удача+|🍀|luck|0.5|600||0|10|1`", parse_mode='Markdown', reply_markup=main_menu())
                return
            if action.startswith('act:admin:booster:edit:'):
                if not is_admin_id(callback.from_user.id):
                    await callback.message.answer('Access denied', reply_markup=main_menu())
                    return
                booster_key = action.split(':', maxsplit=4)[4]
                await service.set_input_state(callback.from_user.id, 'admin_booster_form', {'mode': 'edit', 'key': booster_key})
                await callback.message.answer(f"{h('⚡ Редактировать бустер')}\nКлюч: `{booster_key}`\nОтправьте строкой:\n`Название|эмодзи|effect_type|power|price_coins|price_stars|duration_seconds|max_stack|available(0/1)`", parse_mode='Markdown', reply_markup=main_menu())
                return
            if action.startswith('act:admin:booster:delete:'):
                if not is_admin_id(callback.from_user.id):
                    await callback.message.answer('Access denied', reply_markup=main_menu())
                    return
                booster_key = action.split(':', maxsplit=4)[4]
                b = await session.get(BcBooster, booster_key)
                if b is None:
                    await callback.message.answer('Бустер не найден.', reply_markup=main_menu())
                    return
                await session.delete(b)
                await callback.message.answer('Бустер удалён.', reply_markup=main_menu())
                return
            if action == 'act:admin:chest:create':
                if not is_admin_id(callback.from_user.id):
                    await callback.message.answer('Access denied', reply_markup=main_menu())
                    return
                await service.set_input_state(callback.from_user.id, 'admin_chest_form', {'mode': 'create'})
                await callback.message.answer(f"{h('📦 Добавить сундук')}\nОтправьте одной строкой:\n`key|Название|эмодзи|описание|price_coins|price_stars|open_count|drops`\nГде `drops` — список `rarity=weight,rarity=weight`.\nПример:\n`mini|Мини|📦|Быстрый сундук|150||1|common=90,rare=9,epic=1`", parse_mode='Markdown', reply_markup=main_menu())
                return
            if action.startswith('act:admin:chest:edit:'):
                if not is_admin_id(callback.from_user.id):
                    await callback.message.answer('Access denied', reply_markup=main_menu())
                    return
                chest_key = action.split(':', maxsplit=4)[4]
                await service.set_input_state(callback.from_user.id, 'admin_chest_form', {'mode': 'edit', 'key': chest_key})
                await callback.message.answer(f"{h('📦 Редактировать сундук')}\nКлюч: `{chest_key}`\nОтправьте строкой:\n`Название|эмодзи|описание|price_coins|price_stars|open_count|active(0/1)`\nДроп-таблица редактируется отдельной кнопкой (будет добавлено).", parse_mode='Markdown', reply_markup=main_menu())
                return
            if action.startswith('act:admin:chest:delete:'):
                if not is_admin_id(callback.from_user.id):
                    await callback.message.answer('Access denied', reply_markup=main_menu())
                    return
                chest_key = action.split(':', maxsplit=4)[4]
                c = await session.get(BcChest, chest_key)
                if c is None:
                    await callback.message.answer('Сундук не найден.', reply_markup=main_menu())
                    return
                await session.delete(c)
                await callback.message.answer('Сундук удалён.', reply_markup=main_menu())
                return
            if action == 'act:admin:user:manage:start':
                if not is_admin_id(callback.from_user.id):
                    await callback.message.answer('Access denied', reply_markup=main_menu())
                    return
                await service.set_input_state(callback.from_user.id, 'admin_user_manage_form', {})
                await callback.message.answer(
                    f"{h('👥 Управление пользователем')}\nОтправьте одной строкой:\n`user_id|field|value`\n\nПоля:\n`coins`, `stars`, `points`, `level`, `exp`, `premium_days`, `nickname`, `cooldown:action`\n\nПримеры:\n`123456789|coins|5000`\n`123456789|cooldown:brawl_cards|0`",
                    parse_mode='Markdown',
                    reply_markup=main_menu(),
                )
                return
            if action.startswith('act:admin:sys:edit:'):
                if not is_admin_id(callback.from_user.id):
                    await callback.message.answer('Access denied', reply_markup=main_menu())
                    return
                section = action.split(':', maxsplit=4)[4]
                await service.set_input_state(callback.from_user.id, 'admin_system_form', {'section': section})
                if section == 'cooldowns':
                    prompt = (
                        f"{h('⏱ Кулдауны')}\n"
                        "Отправьте строкой:\n"
                        "`key|seconds`\n\n"
                        "Ключи:\n"
                        "`brawl_cards`, `bonus`, `nick_change`, `dice`, `guess_rarity`, `coinflip`, `card_battle`, `slot`, `premium_game_reduction`"
                    )
                elif section == 'rewards':
                    prompt = (
                        f"{h('🎁 Награды')}\n"
                        "Отправьте строкой:\n"
                        "`key|value`\n\n"
                        "Ключи:\n"
                        "`bonus_coins`, `bonus_stars`, `market_fee_percent`"
                    )
                else:
                    prompt = (
                        f"{h('🔗 Bonus-ссылки')}\n"
                        "Отправьте строкой:\n"
                        "`key|url`\n\n"
                        "Ключи:\n"
                        "`chat`, `subscribe`, `news`, `invite`, `partner`"
                    )
                await callback.message.answer(prompt, parse_mode='Markdown', reply_markup=main_menu())
                return
    await callback.message.answer('Действие пока не реализовано.', reply_markup=main_menu())

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
    title = h("?????? ?????????") if ok else h("?????? ????????")
    charge_id = message.successful_payment.telegram_payment_charge_id
    await message.answer(
        f"{title}\n{resp}\n\n?????: {message.successful_payment.total_amount} XTR\nCharge ID: `{charge_id}`",
        reply_markup=main_menu(is_admin=is_admin_id(message.from_user.id)),
        parse_mode="Markdown",
    )

@router.message(F.photo)
@router.message(F.photo)
@router.message(F.photo)
@router.message(F.photo)
async def on_photo_input(message: Message) -> None:
    if message.from_user is None or not message.photo:
        return
    async with SessionLocal() as session:
        service = BrawlCardsService(session)
        state = await service.get_input_state(message.from_user.id)
        if state is None:
            return
        if not is_admin_id(message.from_user.id):
            return
        file_id = message.photo[-1].file_id
        if state.state == 'admin_card_photo':
            payload = dict(state.payload or {})
            card_id = int(payload.get('id') or 0)
            async with session.begin():
                card = await session.get(BcCard, card_id)
                if card is None:
                    await service.clear_input_state(message.from_user.id)
                    await message.answer('Карточка не найдена.', reply_markup=main_menu())
                    return
                card.image_file_id = file_id
                await service.clear_input_state(message.from_user.id)
            await message.answer('Фото карточки обновлено.', reply_markup=main_menu())
            await screen_admin_card(message, card_id)
            return
        if state.state == 'admin_rp_category_form':
            if not is_admin_id(message.from_user.id):
                await message.answer('Access denied', reply_markup=main_menu())
                return
            payload = dict(state.payload or {})
            mode = payload.get('mode')
            parts = [p.strip() for p in message.text.split('|')]
            async with session.begin():
                if mode == 'create':
                    if len(parts) != 5:
                        await message.answer('???????? ??????. ?????? 5 ?????.', reply_markup=main_menu())
                        return
                    key, title, emoji, sort, active = parts
                    if await session.get(BcRPCategory, key) is not None:
                        await message.answer('????????? ? ????? key ??? ??????????.', reply_markup=main_menu())
                        return
                    session.add(BcRPCategory(key=key, title=title, emoji=emoji or '??', sort=int(sort or 100), is_active=bool(int(active))))
                    await service.clear_input_state(message.from_user.id)
                    await message.answer('????????? RP ???????.', reply_markup=main_menu())
                    await screen_admin_rp_category(message, key)
                    return
                if len(parts) != 4:
                    await message.answer('???????? ??????. ?????? 4 ????.', reply_markup=main_menu())
                    return
                title, emoji, sort, active = parts
                key = str(payload.get('key') or '')
                category = await session.get(BcRPCategory, key)
                if category is None:
                    await message.answer('????????? ?? ???????.', reply_markup=main_menu())
                    await service.clear_input_state(message.from_user.id)
                    return
                category.title = title
                category.emoji = emoji or '??'
                category.sort = int(sort or 100)
                category.is_active = bool(int(active))
                await service.clear_input_state(message.from_user.id)
                await message.answer('????????? RP ?????????.', reply_markup=main_menu())
                await screen_admin_rp_category(message, key)
                return
        if state.state == 'admin_rp_action_form':
            if not is_admin_id(message.from_user.id):
                await message.answer('Access denied', reply_markup=main_menu())
                return
            payload = dict(state.payload or {})
            mode = payload.get('mode')
            parts = [p.strip() for p in message.text.split('|')]
            async with session.begin():
                if mode == 'create':
                    if len(parts) != 15:
                        await message.answer('???????? ??????. ?????? 15 ?????.', reply_markup=main_menu())
                        return
                    key, category_key, title, emoji, requires_target, cooldown, coins, stars, points, media_id, private_scope, group_scope, sort, active, templates_raw = parts
                    if await session.get(BcRPAction, key) is not None:
                        await message.answer('RP-???????? ? ????? key ??? ??????????.', reply_markup=main_menu())
                        return
                else:
                    if len(parts) != 14:
                        await message.answer('???????? ??????. ?????? 14 ?????.', reply_markup=main_menu())
                        return
                    key = str(payload.get('key') or '')
                    category_key, title, emoji, requires_target, cooldown, coins, stars, points, media_id, private_scope, group_scope, sort, active, templates_raw = parts
                if await session.get(BcRPCategory, category_key) is None:
                    await message.answer('RP-????????? ?? ???????.', reply_markup=main_menu())
                    return
                media_value = int(media_id) if media_id else None
                templates = [item.strip() for item in templates_raw.split(';;') if item.strip()]
                if mode == 'create':
                    rp_action = BcRPAction(
                        key=key,
                        category_key=category_key,
                        title=title,
                        emoji=emoji or '?',
                        requires_target=bool(int(requires_target)),
                        cooldown_seconds=int(cooldown),
                        reward={'coins': int(coins or 0), 'stars': int(stars or 0), 'points': int(points or 0)},
                        templates=templates,
                        media_id=media_value,
                        restrictions={},
                        allowed_scopes={'private': bool(int(private_scope)), 'group': bool(int(group_scope))},
                        is_active=bool(int(active)),
                        sort=int(sort or 100),
                    )
                    session.add(rp_action)
                else:
                    rp_action = await session.get(BcRPAction, key)
                    if rp_action is None:
                        await message.answer('RP-???????? ?? ???????.', reply_markup=main_menu())
                        await service.clear_input_state(message.from_user.id)
                        return
                    rp_action.category_key = category_key
                    rp_action.title = title
                    rp_action.emoji = emoji or '?'
                    rp_action.requires_target = bool(int(requires_target))
                    rp_action.cooldown_seconds = int(cooldown)
                    rp_action.reward = {'coins': int(coins or 0), 'stars': int(stars or 0), 'points': int(points or 0)}
                    rp_action.templates = templates
                    rp_action.media_id = media_value
                    rp_action.allowed_scopes = {'private': bool(int(private_scope)), 'group': bool(int(group_scope))}
                    rp_action.is_active = bool(int(active))
                    rp_action.sort = int(sort or 100)
                await service.clear_input_state(message.from_user.id)
                await message.answer('RP-???????? ?????????.', reply_markup=main_menu())
                await screen_admin_rp_action(message, key)
                return
        if state.state == 'admin_card_wizard':
            payload = dict(state.payload or {})
            if str(payload.get('step') or '') != 'photo':
                return
            async with session.begin():
                ok, resp, card_id = await save_card_wizard_payload(session, service, message.from_user.id, payload, photo_file_id=file_id)
            await message.answer(resp, reply_markup=main_menu())
            if ok and card_id:
                await screen_admin_card(message, card_id)
            return


@router.message()
async def on_text_input(message: Message) -> None:
    if message.from_user is None or message.text is None:
        return
    await ensure_user(message)
    async with SessionLocal() as session:
        service = BrawlCardsService(session)
        state = await service.get_input_state(message.from_user.id)
        if state is None:
            return
        if state.state == 'nick_wait':
            async with session.begin():
                ok, resp = await service.set_nickname(message.from_user.id, message.text)
                await service.clear_input_state(message.from_user.id)
            await message.answer(resp, reply_markup=main_menu())
            if ok:
                await show_screen(message, 'profile')
            return
        if state.state == 'quote_wait':
            async with session.begin():
                await service.clear_input_state(message.from_user.id)
            await message.answer(f"{h('💬 Цитата')}\nВ«{message.text.strip()}В»", reply_markup=main_menu())
            return
        if state.state in {'sticker_last_wait', 'sticker_template_wait'}:
            async with session.begin():
                if state.state == 'sticker_last_wait':
                    user_state = await session.get(BcUserState, message.from_user.id)
                    if user_state is None or user_state.last_card_id is None:
                        await service.clear_input_state(message.from_user.id)
                        await message.answer(f"{h('🎨 Стикер')}\nСначала получите карту.", reply_markup=main_menu())
                        return
                    card = await session.get(BcCard, user_state.last_card_id)
                    if card is None:
                        await service.clear_input_state(message.from_user.id)
                        await message.answer(f"{h('🎨 Стикер')}\nКарта не найдена.", reply_markup=main_menu())
                        return
                    title = card.title
                    rarity = card.rarity_key
                    description = card.description
                else:
                    title = 'Antonio'
                    rarity = 'common'
                    description = 'Шаблонный стикер'
                out_path = build_card_image(title, rarity, description, message.text.strip(), Path('tmp'))
                await service.clear_input_state(message.from_user.id)
            await message.answer_photo(FSInputFile(str(out_path)), caption=f"{h('🎨 Стикер')}\nСтикер подготовлен.")
            return
        if state.state == 'market_sell_wait':
            parts = [p.strip() for p in message.text.split('|')]
            if len(parts) != 3:
                await message.answer(f"{h('💱 Маркет')}\nНужен формат: `instance_id|coins_or_stars|price`", parse_mode='Markdown')
                return
            instance_id, currency, price = parts
            async with session.begin():
                ok, resp = await service.market_sell_instance(message.from_user.id, int(instance_id), currency, int(price))
                await service.clear_input_state(message.from_user.id)
            await message.answer(f"{h('💱 Маркет')}\n{resp}", reply_markup=main_menu())
            return
        if state.state == 'marriage_propose_wait':
            target_id = int(message.text.strip())
            async with session.begin():
                ok, resp = await service.marriage_propose(message.from_user.id, target_id)
                await service.clear_input_state(message.from_user.id)
            await message.answer(f"{h('РЎР‚РЎСџРІР‚в„ўР\xa0РЉ Р\xa0\xa0РІР‚\x98Р\xa0РЋР\xa0вЂљР\xa0\xa0Р’В°Р\xa0\xa0РЎвЂќ')}\n{resp}", reply_markup=main_menu())
            return
        if state.state == 'rp_target_wait':
            payload = dict(state.payload or {})
            action_key = str(payload.get('action_key') or '')
            async with session.begin():
                target = await service.resolve_user_reference(message.text)
                if target is None:
                    await message.answer(f"{h('?? RP')}\n???????????? ?? ??????. ????????? ID, @username ??? ?????? `https://t.me/...`", parse_mode='Markdown', reply_markup=main_menu())
                    return
                result = await service.perform_rp_action_payload(
                    message.from_user.id,
                    action_key,
                    target.id,
                    message.chat.type if message.chat else None,
                    message.chat.id if message.chat else None,
                    message.message_id,
                )
                if not result.get('ok'):
                    await message.answer(f"{h('?? RP')}\n{result.get('message', '??????.')}", reply_markup=main_menu())
                    return
                await service.clear_input_state(message.from_user.id)
            await send_rp_result(message, f"{h('?? RP')}\n{result['text']}", result.get('media'))
            return
        if state.state == 'admin_user_manage_form':
            if not is_admin_id(message.from_user.id):
                await message.answer('Access denied', reply_markup=main_menu())
                return
            parts = [p.strip() for p in message.text.split('|', maxsplit=2)]
            if len(parts) != 3:
                await message.answer(
                    f"{h('\U0001f465 \u0423\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u0435 \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u0435\u043c')}\n\u041d\u0443\u0436\u0435\u043d \u0444\u043e\u0440\u043c\u0430\u0442: `user_id|field|value`",
                    parse_mode='Markdown',
                    reply_markup=main_menu(),
                )
                return
            target_user_id, field, value = parts
            async with session.begin():
                ok, resp = await service.admin_update_user(int(target_user_id), field, value)
                await service.clear_input_state(message.from_user.id)
            await message.answer(f"{h('\U0001f465 \u0423\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u0435 \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u0435\u043c')}\n{resp}", reply_markup=main_menu())
            return
        if state.state == 'admin_system_form':
            if not is_admin_id(message.from_user.id):
                await message.answer('Access denied', reply_markup=main_menu())
                return
            payload = dict(state.payload or {})
            section = str(payload.get('section') or '')
            parts = [p.strip() for p in message.text.split('|', maxsplit=1)]
            if len(parts) != 2:
                await message.answer(
                    f"{h('\u2699\ufe0f \u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438 \u0431\u043e\u0442\u0430')}\n\u041d\u0443\u0436\u0435\u043d \u0444\u043e\u0440\u043c\u0430\u0442: `key|value`",
                    parse_mode='Markdown',
                    reply_markup=main_menu(),
                )
                return
            key, raw_value = parts
            defaults = await service.get_system_section(section)
            if key not in defaults:
                await message.answer(
                    f"{h('\u2699\ufe0f \u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438 \u0431\u043e\u0442\u0430')}\n\u041d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u044b\u0439 \u043a\u043b\u044e\u0447: `{key}`",
                    parse_mode='Markdown',
                    reply_markup=main_menu(),
                )
                return
            if section in {'cooldowns', 'rewards'}:
                try:
                    value: object = int(raw_value)
                except ValueError:
                    await message.answer(
                        f"{h('\u2699\ufe0f \u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438 \u0431\u043e\u0442\u0430')}\n\u0414\u043b\u044f \u044d\u0442\u043e\u0433\u043e \u0440\u0430\u0437\u0434\u0435\u043b\u0430 \u043d\u0443\u0436\u043d\u043e \u0447\u0438\u0441\u043b\u043e.",
                        reply_markup=main_menu(),
                    )
                    return
            else:
                value = raw_value
            async with session.begin():
                await service.set_system_value(section, key, value)
                await service.clear_input_state(message.from_user.id)
            await message.answer(f"{h('\u2699\ufe0f \u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438 \u0431\u043e\u0442\u0430')}\n\u0421\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u043e: `{key}` = `{value}`", parse_mode='Markdown', reply_markup=main_menu())
            return
        if state.state == 'admin_card_wizard':
            if not is_admin_id(message.from_user.id):
                await message.answer('Access denied', reply_markup=main_menu())
                return
            payload = dict(state.payload or {})
            mode = str(payload.get('mode') or 'create')
            step = str(payload.get('step') or '')
            data = dict(payload.get('data') or {})
            steps = CARD_WIZARD_STEPS.get(mode, CARD_WIZARD_STEPS['create'])
            raw = message.text.strip()
            if not step or step not in steps:
                await message.answer('Состояние конструктора карточки повреждено.', reply_markup=main_menu())
                return
            if mode == 'edit' and raw == '-' and step != 'photo':
                value = data.get(step)
            else:
                if step in {'key', 'title', 'description', 'series'}:
                    value = raw
                elif step == 'rarity_key':
                    if await session.get(BcRarity, raw) is None:
                        await message.answer('Редкость не найдена. Введите существующий `rarity_key`.', parse_mode='Markdown', reply_markup=main_menu())
                        return
                    value = raw
                elif step in {'points', 'coins', 'sort'}:
                    try:
                        value = int(raw)
                    except ValueError:
                        await message.answer('Нужно целое число.', reply_markup=main_menu())
                        return
                elif step == 'drop_weight':
                    try:
                        value = float(raw)
                    except ValueError:
                        await message.answer('Нужно число. Пример: `1` или `0.35`.', parse_mode='Markdown', reply_markup=main_menu())
                        return
                elif step in {'is_limited', 'is_sellable', 'is_active'}:
                    if raw.lower() not in {'0', '1', 'да', 'нет'}:
                        await message.answer('Нужно `1` или `0`.', parse_mode='Markdown', reply_markup=main_menu())
                        return
                    value = 1 if raw.lower() in {'1', 'да'} else 0
                elif step == 'photo':
                    if raw != '-':
                        await message.answer('На этом шаге отправьте фото или `-`.', reply_markup=main_menu())
                        return
                    value = data.get('photo') or ''
                else:
                    value = raw
            if step == 'photo':
                payload['data'] = data
                async with session.begin():
                    ok, resp, card_id = await save_card_wizard_payload(session, service, message.from_user.id, payload)
                await message.answer(resp, reply_markup=main_menu())
                if ok and card_id:
                    await screen_admin_card(message, card_id)
                return
            data[step] = value
            next_index = steps.index(step) + 1
            next_step = steps[next_index]
            async with session.begin():
                await service.set_input_state(message.from_user.id, 'admin_card_wizard', {'mode': mode, 'id': payload.get('id'), 'step': next_step, 'data': data})
            await message.answer(card_wizard_prompt(mode, next_step, data), parse_mode='Markdown', reply_markup=main_menu())
            return
        if state.state == 'admin_card_form':
            if not is_admin_id(message.from_user.id):
                await message.answer('Access denied', reply_markup=main_menu())
                return
            payload = dict(state.payload or {})
            mode = payload.get('mode')
            raw = message.text.strip()
            async with session.begin():
                if mode == 'create':
                    parts = [p.strip() for p in raw.split('|')]
                    if len(parts) != 13:
                        await message.answer('Неверный формат. Ожидаю 13 полей через `|`.', parse_mode='Markdown')
                        return
                    key, title, description, rarity_key, series, points, coins, drop_weight, limited, sellable, active, sort, image_file_id = parts
                    if await session.scalar(select(BcCard.id).where(BcCard.key == key)) is not None:
                        await message.answer('Карточка с таким key уже существует.', reply_markup=main_menu())
                        return
                    if await session.get(BcRarity, rarity_key) is None:
                        await message.answer('Редкость не найдена.', reply_markup=main_menu())
                        return
                    card = BcCard(key=key, title=title, description=description, rarity_key=rarity_key, series=series or 'Core', tags=[], base_points=int(points), base_coins=int(coins), drop_weight=float(drop_weight), is_limited=bool(int(limited)), limited_series_id=None, event_id=None, image_file_id=image_file_id or None, image_url=None, media_id=None, is_sellable=bool(int(sellable)), is_active=bool(int(active)), sort=int(sort or 100), meta={})
                    session.add(card)
                    await session.flush()
                    await service.clear_input_state(message.from_user.id)
                    await message.answer('Карточка создана.', reply_markup=main_menu())
                    await screen_admin_card(message, card.id)
                    return
                if mode == 'edit':
                    card_id = int(payload.get('id'))
                    card = await session.get(BcCard, card_id)
                    if card is None:
                        await message.answer('Карточка не найдена.', reply_markup=main_menu())
                        await service.clear_input_state(message.from_user.id)
                        return
                    parts = [p.strip() for p in raw.split('|')]
                    if len(parts) != 12:
                        await message.answer('Неверный формат. Ожидаю 12 полей через `|`.', parse_mode='Markdown')
                        return
                    title, description, rarity_key, series, points, coins, drop_weight, limited, sellable, active, sort, image_file_id = parts
                    if await session.get(BcRarity, rarity_key) is None:
                        await message.answer('Редкость не найдена.', reply_markup=main_menu())
                        return
                    card.title = title
                    card.description = description
                    card.rarity_key = rarity_key
                    card.series = series or 'Core'
                    card.base_points = int(points)
                    card.base_coins = int(coins)
                    card.drop_weight = float(drop_weight)
                    card.is_limited = bool(int(limited))
                    card.is_sellable = bool(int(sellable))
                    card.is_active = bool(int(active))
                    card.sort = int(sort or 100)
                    card.image_file_id = image_file_id or None
                    await service.clear_input_state(message.from_user.id)
                    await message.answer('Карточка обновлена.', reply_markup=main_menu())
                    await screen_admin_card(message, card.id)
                    return
            await message.answer('Неизвестный режим формы.', reply_markup=main_menu())
            return
        if state.state == 'admin_rarity_form':
            if not is_admin_id(message.from_user.id):
                await message.answer('Access denied', reply_markup=main_menu())
                return
            payload = dict(state.payload or {})
            mode = payload.get('mode')
            raw = message.text.strip()
            async with session.begin():
                if mode == 'create':
                    parts = [p.strip() for p in raw.split('|')]
                    if len(parts) != 10:
                        await message.answer('Неверный формат. Ожидаю 10 полей через `|`.', parse_mode='Markdown')
                        return
                    key, title, emoji, chance, color, pm, cm, drop_mode, in_chests, in_shop = parts
                    if await session.get(BcRarity, key) is not None:
                        await message.answer('Редкость с таким key уже существует.', reply_markup=main_menu())
                        return
                    r = BcRarity(key=key, title=title, emoji=emoji, chance=float(chance), color=color, points_mult=float(pm), coins_mult=float(cm), available_in_chests=bool(int(in_chests)), available_in_shop=bool(int(in_shop)), drop_mode=drop_mode, sort=100, meta={}, is_active=True)
                    session.add(r)
                    await service.clear_input_state(message.from_user.id)
                    await message.answer('Редкость создана.', reply_markup=main_menu())
                    await screen_admin_rarity(message, r.key)
                    return
                if mode == 'edit':
                    key = str(payload.get('key'))
                    r = await session.get(BcRarity, key)
                    if r is None:
                        await message.answer('Редкость не найдена.', reply_markup=main_menu())
                        await service.clear_input_state(message.from_user.id)
                        return
                    parts = [p.strip() for p in raw.split('|')]
                    if len(parts) != 10:
                        await message.answer('Неверный формат. Ожидаю 10 полей через `|`.', parse_mode='Markdown')
                        return
                    title, emoji, chance, color, pm, cm, drop_mode, in_chests, in_shop, active = parts
                    r.title = title
                    r.emoji = emoji
                    r.chance = float(chance)
                    r.color = color
                    r.points_mult = float(pm)
                    r.coins_mult = float(cm)
                    r.drop_mode = drop_mode
                    r.available_in_chests = bool(int(in_chests))
                    r.available_in_shop = bool(int(in_shop))
                    r.is_active = bool(int(active))
                    await service.clear_input_state(message.from_user.id)
                    await message.answer('Редкость обновлена.', reply_markup=main_menu())
                    await screen_admin_rarity(message, r.key)
                    return
            await message.answer('Неизвестный режим формы.', reply_markup=main_menu())
            return
        if state.state == 'admin_booster_form':
            if not is_admin_id(message.from_user.id):
                await message.answer('Access denied', reply_markup=main_menu())
                return
            payload = dict(state.payload or {})
            mode = payload.get('mode')
            raw = message.text.strip()
            async with session.begin():
                if mode == 'create':
                    parts = [p.strip() for p in raw.split('|')]
                    if len(parts) != 10:
                        await message.answer('Неверный формат. Ожидаю 10 полей через `|`.', parse_mode='Markdown')
                        return
                    key, title, emoji, etype, power, pcoins, pstars, dur, max_stack, avail = parts
                    if await session.get(BcBooster, key) is not None:
                        await message.answer('Бустер с таким key уже существует.', reply_markup=main_menu())
                        return
                    b = BcBooster(key=key, title=title, emoji=emoji, effect_type=etype, effect_power=float(power), price_coins=int(pcoins) if pcoins else None, price_stars=int(pstars) if pstars else None, duration_seconds=int(dur or 0), stackable=True, max_stack=int(max_stack or 10), purchase_limit=None, is_available=bool(int(avail)), event_id=None, meta={})
                    session.add(b)
                    await service.clear_input_state(message.from_user.id)
                    await message.answer('Бустер создан.', reply_markup=main_menu())
                    await screen_admin_booster(message, b.key)
                    return
                if mode == 'edit':
                    key = str(payload.get('key'))
                    b = await session.get(BcBooster, key)
                    if b is None:
                        await message.answer('Бустер не найден.', reply_markup=main_menu())
                        await service.clear_input_state(message.from_user.id)
                        return
                    parts = [p.strip() for p in raw.split('|')]
                    if len(parts) != 9:
                        await message.answer('Неверный формат. Ожидаю 9 полей через `|`.', parse_mode='Markdown')
                        return
                    title, emoji, etype, power, pcoins, pstars, dur, max_stack, avail = parts
                    b.title = title
                    b.emoji = emoji
                    b.effect_type = etype
                    b.effect_power = float(power)
                    b.price_coins = int(pcoins) if pcoins else None
                    b.price_stars = int(pstars) if pstars else None
                    b.duration_seconds = int(dur or 0)
                    b.max_stack = int(max_stack or 10)
                    b.is_available = bool(int(avail))
                    await service.clear_input_state(message.from_user.id)
                    await message.answer('Бустер обновлён.', reply_markup=main_menu())
                    await screen_admin_booster(message, b.key)
                    return
            await message.answer('Неизвестный режим формы.', reply_markup=main_menu())
            return
        if state.state == 'admin_chest_form':
            if not is_admin_id(message.from_user.id):
                await message.answer('Access denied', reply_markup=main_menu())
                return
            payload = dict(state.payload or {})
            mode = payload.get('mode')
            raw = message.text.strip()
            async with session.begin():
                if mode == 'create':
                    parts = [p.strip() for p in raw.split('|')]
                    if len(parts) != 8:
                        await message.answer('Неверный формат. Ожидаю 8 полей через `|`.', parse_mode='Markdown')
                        return
                    key, title, emoji, desc, pcoins, pstars, open_count, drops_raw = parts
                    if await session.get(BcChest, key) is not None:
                        await message.answer('Сундук с таким key уже существует.', reply_markup=main_menu())
                        return
                    chest = BcChest(key=key, title=title, emoji=emoji, description=desc, price_coins=int(pcoins) if pcoins else None, price_stars=int(pstars) if pstars else None, open_count=int(open_count or 1), guarantees={}, limits={}, media_id=None, access={}, is_active=True, sort=100)
                    session.add(chest)
                    await session.flush()
                    for item in drops_raw.split(','):
                        item = item.strip()
                        if not item:
                            continue
                        rk, w = [x.strip() for x in item.split('=', maxsplit=1)]
                        session.add(BcChestDrop(chest_key=chest.key, rarity_key=rk, weight=float(w), min_count=1, max_count=1, meta={}))
                    await service.clear_input_state(message.from_user.id)
                    await message.answer('Сундук создан.', reply_markup=main_menu())
                    await screen_admin_chest(message, chest.key)
                    return
                if mode == 'edit':
                    key = str(payload.get('key'))
                    chest = await session.get(BcChest, key)
                    if chest is None:
                        await message.answer('Сундук не найден.', reply_markup=main_menu())
                        await service.clear_input_state(message.from_user.id)
                        return
                    parts = [p.strip() for p in raw.split('|')]
                    if len(parts) != 7:
                        await message.answer('Неверный формат. Ожидаю 7 полей через `|`.', parse_mode='Markdown')
                        return
                    title, emoji, desc, pcoins, pstars, open_count, active = parts
                    chest.title = title
                    chest.emoji = emoji
                    chest.description = desc
                    chest.price_coins = int(pcoins) if pcoins else None
                    chest.price_stars = int(pstars) if pstars else None
                    chest.open_count = int(open_count or 1)
                    chest.is_active = bool(int(active))
                    await service.clear_input_state(message.from_user.id)
                    await message.answer('Сундук обновлён.', reply_markup=main_menu())
                    await screen_admin_chest(message, chest.key)
                    return
            await message.answer('Неизвестный режим формы.', reply_markup=main_menu())
            return
