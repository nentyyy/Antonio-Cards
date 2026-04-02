from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine


HOT_PATH_INDEXES: Sequence[str] = (
    "CREATE INDEX IF NOT EXISTS idx_users_last_active_at ON users (last_active_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_transactions_user_created ON transactions (user_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_bc_card_instances_user_obtained ON bc_card_instances (user_id, obtained_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_bc_card_instances_user_card ON bc_card_instances (user_id, card_id)",
    "CREATE INDEX IF NOT EXISTS idx_bc_active_boosters_user_key ON bc_active_boosters (user_id, booster_key)",
    "CREATE INDEX IF NOT EXISTS idx_bc_shop_categories_active_sort ON bc_shop_categories (is_active, sort)",
    "CREATE INDEX IF NOT EXISTS idx_bc_shop_items_category_active_sort ON bc_shop_items (category_key, is_active, sort)",
    "CREATE INDEX IF NOT EXISTS idx_bc_chests_active_sort ON bc_chests (is_active, sort)",
    "CREATE INDEX IF NOT EXISTS idx_bc_chest_drops_chest_rarity ON bc_chest_drops (chest_key, rarity_key)",
    "CREATE INDEX IF NOT EXISTS idx_bc_tasks_active_sort ON bc_tasks (is_active, sort)",
    "CREATE INDEX IF NOT EXISTS idx_bc_user_tasks_user_state ON bc_user_tasks (user_id, completed_at, claimed_at)",
    "CREATE INDEX IF NOT EXISTS idx_bc_bonus_tasks_active_sort ON bc_bonus_tasks (is_active, sort)",
    "CREATE INDEX IF NOT EXISTS idx_bc_user_bonus_tasks_user_state ON bc_user_bonus_tasks (user_id, completed_at, claimed_at)",
    "CREATE INDEX IF NOT EXISTS idx_bc_events_active_period ON bc_events (is_active, starts_at, ends_at)",
    "CREATE INDEX IF NOT EXISTS idx_bc_market_lots_status_created ON bc_market_lots (status, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_bc_market_lots_seller_status ON bc_market_lots (seller_id, status, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_bc_rp_actions_category_active_sort ON bc_rp_actions (category_key, is_active, sort)",
    "CREATE INDEX IF NOT EXISTS idx_bc_cards_rarity_active_sort ON bc_cards (rarity_key, is_active, sort)",
    "CREATE INDEX IF NOT EXISTS idx_bc_cards_series_active_sort ON bc_cards (series, is_active, sort)",
    "CREATE INDEX IF NOT EXISTS idx_bc_rp_logs_actor_created ON bc_rp_logs (actor_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_bc_marriage_proposals_target_status_created ON bc_marriage_proposals (target_id, status, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_bc_audit_logs_actor_created ON bc_audit_logs (actor_id, created_at DESC)",
)


def build_engine_kwargs(database_url: str) -> dict[str, object]:
    if database_url.startswith("sqlite"):
        return {
            "pool_pre_ping": True,
            "connect_args": {"timeout": 30},
        }
    return {
        "pool_pre_ping": True,
        "pool_size": 10,
        "max_overflow": 20,
        "pool_timeout": 10,
        "pool_recycle": 1800,
        "pool_use_lifo": True,
        "connect_args": {
            "command_timeout": 10,
            "server_settings": {"application_name": "antonio_cards"},
        },
    }


def register_sqlite_pragmas(engine: AsyncEngine, database_url: str) -> None:
    if not database_url.startswith("sqlite"):
        return

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()


async def create_hot_path_indexes(conn: AsyncConnection) -> None:
    for statement in HOT_PATH_INDEXES:
        await conn.execute(text(statement))
