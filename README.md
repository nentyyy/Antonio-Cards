# Antonio Cards

Antonio Cards is a Telegram card game built on `aiogram 3` and PostgreSQL.

## Runtime

- single bot entrypoint: `app/main_user.py`
- database layer: `app/db/*`
- user and admin transport: `app/bot/handlers.py`
- gameplay services: `app/services/*`
- cache, guards and membership verification: `app/application/*`, `app/domain/*`, `app/infra/*`

## Active Domains

- profile and settings
- cards, rarities, boosters and collections
- economy, premium and transactions
- bonus tasks and subscription checks
- shop, chests and market
- leaderboards, quotes, stickers and chat RP
- in-bot admin screens and runtime controls

## Project Structure

```text
app/
  application/
  bot/
  db/
  domain/
  infra/
  middlewares/
  services/
  utils/
  main_user.py
```

## Local Run

```bash
cp .env.example .env
docker compose up --build
```

or

```bash
python -m venv .venv
. .venv/Scripts/activate
pip install -r requirements.txt
python -m app.main_user
```

## Required Environment

- `BOT_TOKEN`
- `DATABASE_URL`
- `ADMIN_IDS`

## Deployment

Run the polling bot with:

```bash
python -m app.main_user
```
