from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from app.config import get_settings
from app.db.session import SessionLocal
from app.services.game_service import GameService

router = Router(name="admin_bot")
settings = get_settings()


async def _is_admin(message: Message) -> bool:
    return message.from_user is not None and message.from_user.id in settings.admin_id_set()


async def _reject_if_not_admin(message: Message) -> bool:
    if not await _is_admin(message):
        await message.answer("Access denied")
        return True
    return False


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    if await _reject_if_not_admin(message):
        return
    await message.answer(
        "Admin bot ready. Commands: /setcooldown /setdrop /addcard /editcard /setprice /stats /broadcast_all /broadcast_segment"
    )


@router.message(Command("setcooldown"))
async def cmd_setcooldown(message: Message, command: CommandObject) -> None:
    if await _reject_if_not_admin(message):
        return

    args = (command.args or "").split()
    if len(args) != 2:
        await message.answer("Usage: /setcooldown <action> <seconds>")
        return

    action, seconds_raw = args
    seconds = int(seconds_raw)

    async with SessionLocal() as session:
        service = GameService(session)
        current = await service.get_setting("cooldowns", {})
        current[action] = seconds
        async with session.begin():
            await service.set_setting("cooldowns", current)

    await message.answer(f"Cooldown updated: {action}={seconds}s")


@router.message(Command("setdrop"))
async def cmd_setdrop(message: Message, command: CommandObject) -> None:
    if await _reject_if_not_admin(message):
        return

    args = (command.args or "").split()
    if len(args) not in {4, 5}:
        await message.answer("Usage: /setdrop <common> <rare> <mythic> <legendary> [limited]")
        return

    vals = [float(x) for x in args]
    if len(vals) == 4:
        vals.append(0.0)

    rates = {
        "common": vals[0],
        "rare": vals[1],
        "mythic": vals[2],
        "legendary": vals[3],
        "limited": vals[4],
    }

    async with SessionLocal() as session:
        service = GameService(session)
        async with session.begin():
            normalized = await service.set_drop_rates(rates)

    await message.answer(f"Drop rates updated: {normalized}")


@router.message(Command("addcard"))
async def cmd_addcard(message: Message, command: CommandObject) -> None:
    if await _reject_if_not_admin(message):
        return

    raw = (command.args or "").strip()
    parts = [x.strip() for x in raw.split("|")]
    if len(parts) < 5:
        await message.answer(
            "Usage: /addcard title|description|rarity|base_points|coin_reward|image_file_id(optional)"
        )
        return

    title, description, rarity, points_raw, coins_raw = parts[:5]
    image_file_id = parts[5] if len(parts) > 5 and parts[5] else None

    async with SessionLocal() as session:
        service = GameService(session)
        async with session.begin():
            card = await service.admin_add_card(
                title=title,
                description=description,
                rarity=rarity,
                base_points=int(points_raw),
                coin_reward=int(coins_raw),
                image_file_id=image_file_id,
            )

    await message.answer(f"Card added: id={card.card_id}, title={card.title}")


@router.message(Command("editcard"))
async def cmd_editcard(message: Message, command: CommandObject) -> None:
    if await _reject_if_not_admin(message):
        return

    args = (command.args or "").split(maxsplit=2)
    if len(args) != 3:
        await message.answer("Usage: /editcard <card_id> <field> <value>")
        return

    card_id = int(args[0])
    field = args[1]
    value = args[2]

    async with SessionLocal() as session:
        service = GameService(session)
        async with session.begin():
            result = await service.admin_edit_card(card_id, field, value)

    if not result["ok"]:
        await message.answer(result["error"])
    else:
        await message.answer(f"Card {card_id} updated")


@router.message(Command("setprice"))
async def cmd_setprice(message: Message, command: CommandObject) -> None:
    if await _reject_if_not_admin(message):
        return

    args = (command.args or "").split(maxsplit=1)
    if len(args) != 2:
        await message.answer("Usage: /setprice <key> <value>")
        return

    key, value_raw = args
    value: int | float | str
    try:
        value = int(value_raw)
    except ValueError:
        try:
            value = float(value_raw)
        except ValueError:
            value = value_raw

    async with SessionLocal() as session:
        service = GameService(session)
        async with session.begin():
            prices = await service.get_shop_prices()
            prices[key] = value
            await service.set_setting("shop_prices", prices)

    await message.answer(f"Price updated: {key}={value}")


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    if await _reject_if_not_admin(message):
        return

    async with SessionLocal() as session:
        service = GameService(session)
        data = await service.stats()

    await message.answer(
        f"Users: {data['users']}\nCards: {data['cards']}\nTransactions: {data['transactions']}\nPremium users: {data['premium_users']}"
    )


@router.message(Command("broadcast_all"))
async def cmd_broadcast_all(message: Message, command: CommandObject) -> None:
    if await _reject_if_not_admin(message):
        return

    text = (command.args or "").strip()
    if not text:
        await message.answer("Usage: /broadcast_all <text>")
        return

    async with SessionLocal() as session:
        service = GameService(session)
        users = await service.users_for_segment("all")

    sent = 0
    failed = 0
    for user in users:
        try:
            await message.bot.send_message(user.id, text)
            sent += 1
        except Exception:
            failed += 1

    await message.answer(f"Broadcast done. sent={sent}, failed={failed}")


@router.message(Command("broadcast_segment"))
async def cmd_broadcast_segment(message: Message, command: CommandObject) -> None:
    if await _reject_if_not_admin(message):
        return

    args = (command.args or "").split(maxsplit=1)
    if len(args) != 2:
        await message.answer("Usage: /broadcast_segment <premium|nonpremium|active7d> <text>")
        return

    segment, text = args

    async with SessionLocal() as session:
        service = GameService(session)
        users = await service.users_for_segment(segment)

    sent = 0
    failed = 0
    for user in users:
        try:
            await message.bot.send_message(user.id, text)
            sent += 1
        except Exception:
            failed += 1

    await message.answer(f"Segment broadcast ({segment}) done. sent={sent}, failed={failed}")
