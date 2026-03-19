# Cards Arena

Cards Arena is a Telegram collectible card game built with Python, aiogram 3, and PostgreSQL.

Architecture:
- User bot (`app/main_user.py`) for gameplay.
- Admin bot (`app/main_admin.py`) for runtime management.
- PostgreSQL for persistent state.
- Docker and docker-compose for local deployment.
- Long polling for both bots.

## Implemented Features

User bot:
- `/start` user registration + menu.
- `/profile` nickname, premium, points, coins, stars, cards stats.
- `/name` nickname setup (emoji/non-ascii only for premium).
- `/brawl` rarity roll + premium/luck booster modifiers + cooldown.
- `/bonus` periodic reward with channel task check (`getChatMember`) + `Check tasks` button.
- `/shop` sections: Boosters, Coins, Chests, Premium.
- Luck booster: one-time +35% rare+ probabilities.
- Timewarp booster: one-time `-1 hour` brawl cooldown.
- `/premium` activates premium for 30 days using stars.
- Premium bonuses: reduced cooldowns, better mythic/legendary chance, +30% coin rewards, emoji nickname, top badge, reduced dice cooldown.
- `/top [points|cards|coins]` top 10.
- `/quote <text>` quote with last card.
- `/sticker <text>` generated card image with caption.
- `/diceplay` Telegram dice game with coin rewards and cooldown.
- `/chest <rarity>` buy chest and receive 5 cards of selected tier.
- `/roleplay [action]` safe RP action, only as reply.
- `/marriage` marriage registration, only as reply.
- `/market` marketplace for limited cards (sell, buy, cancel), supports coins/stars and fee.

Admin bot:
- `/setcooldown <action> <seconds>`
- `/setdrop <common> <rare> <mythic> <legendary> [limited]`
- `/addcard title|description|rarity|base_points|coin_reward|image_file_id(optional)`
- `/editcard <card_id> <field> <value>`
- `/setprice <key> <value>`
- `/stats`
- `/broadcast_all <text>`
- `/broadcast_segment <premium|nonpremium|active7d> <text>`

Core requirements covered:
- Required tables: `users`, `cards_catalog`, `user_cards`, `cooldowns`, `transactions`.
- Additional tables for gameplay systems (`settings`, `user_boosters`, `user_state`, `marriages`, `market_listings`).
- Coin/card operations use DB transactions.
- Anti-flood middleware.
- Logging via standard `logging`.

## Project Structure

```text
app/
  admin/handlers.py
  bot/handlers.py
  bot/keyboards.py
  db/models.py
  db/session.py
  db/seed.py
  services/game_service.py
  middlewares/antiflood.py
  utils/sticker.py
  main_user.py
  main_admin.py
```

## Local Run (Docker)

1. Copy env file:

```bash
cp .env.example .env
```

2. Fill `BOT_TOKEN`, `ADMIN_BOT_TOKEN`, `ADMIN_IDS`.

3. Start services:

```bash
docker compose up --build
```

Services:
- `postgres` on `localhost:5432`
- `user-bot` long polling
- `admin-bot` long polling

## Local Run (without Docker)

1. Create venv and install:

```bash
python -m venv .venv
. .venv/Scripts/activate  # Windows PowerShell: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. Ensure PostgreSQL is running and `DATABASE_URL` points to it.

3. Run bots in separate terminals:

```bash
python -m app.main_user
python -m app.main_admin
```

## Render Deployment

Render does not run `docker-compose` directly for one service stack. Use separate services:

1. Create a PostgreSQL instance in Render.
2. Create **Background Worker** `cards-arena-user-bot`.
3. Create **Background Worker** `cards-arena-admin-bot`.
4. Connect both workers to same repo.
5. Set environment variables for both:
   - `DATABASE_URL` (Render external DB URL in asyncpg format)
   - `BOT_TOKEN`
   - `ADMIN_BOT_TOKEN`
   - `ADMIN_IDS`
   - Other optional vars from `.env.example`
6. Worker start commands:
   - User bot: `python -m app.main_user`
   - Admin bot: `python -m app.main_admin`

Notes for Render `DATABASE_URL`:
- Render may provide sync URL like `postgres://...`.
- Convert to async SQLAlchemy URL: `postgresql+asyncpg://...`

## Important Notes

- Seed cards are added automatically if catalog is empty.
- Drop rates defaults are `common 70 / rare 20 / mythic 8 / legendary 2`.
- Limited cards default drop rate is `0`, intended for admin events/market economy.
- Marketplace fee is controlled by `shop_prices.market_fee_percent`.
# Antonio

This repository now contains the expanded Antonio implementation: a Telegram collectible card game with button-first navigation, modular gameplay services, DB-backed rarities/boosters/chests/tasks/RP actions, marketplace flow, marriage flow, settings and an in-bot admin panel.
# Antonio update

This project now runs as one Telegram bot. Player screens and admin-panel screens work through the same `BOT_TOKEN`, and admin access is limited to the first two values in `ADMIN_IDS`.
