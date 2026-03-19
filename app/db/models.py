from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Float,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Rarity(StrEnum):
    COMMON = "common"
    RARE = "rare"
    MYTHIC = "mythic"
    LEGENDARY = "legendary"
    LIMITED = "limited"


class MarketCurrency(StrEnum):
    COINS = "coins"
    STARS = "stars"


class MarketStatus(StrEnum):
    ACTIVE = "active"
    SOLD = "sold"
    CANCELLED = "cancelled"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str] = mapped_column(String(255), nullable=False)
    nickname: Mapped[str | None] = mapped_column(String(64), nullable=True)
    coins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stars: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cards_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cards_unique: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    premium_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    cards: Mapped[list["UserCard"]] = relationship(back_populates="user")


class CardCatalog(Base):
    __tablename__ = "cards_catalog"

    card_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    image_file_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    rarity: Mapped[str] = mapped_column(String(32), nullable=False)
    base_points: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    coin_reward: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        CheckConstraint("rarity in ('common','rare','mythic','legendary','limited')", name="ck_card_rarity"),
    )


class UserCard(Base):
    __tablename__ = "user_cards"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    card_id: Mapped[int] = mapped_column(
        ForeignKey("cards_catalog.card_id", ondelete="CASCADE"), primary_key=True
    )
    amount: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    first_drop_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_drop_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="cards")


class Cooldown(Base):
    __tablename__ = "cooldowns"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    action: Mapped[str] = mapped_column(String(64), primary_key=True)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    currency: Mapped[str] = mapped_column(String(32), nullable=False)
    amount_spent: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class UserBooster(Base):
    __tablename__ = "user_boosters"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    luck_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    timewarp_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class UserState(Base):
    __tablename__ = "user_state"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    last_card_id: Mapped[int | None] = mapped_column(
        ForeignKey("cards_catalog.card_id", ondelete="SET NULL"), nullable=True
    )
    last_card_got_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Marriage(Base):
    __tablename__ = "marriages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user1_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    user2_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("user1_id", "user2_id", name="uq_marriage_pair"),)


class MarketListing(Base):
    __tablename__ = "market_listings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards_catalog.card_id", ondelete="CASCADE"), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(16), nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=MarketStatus.ACTIVE.value, nullable=False)
    buyer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    bought_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("currency in ('coins','stars')", name="ck_market_currency"),
        CheckConstraint("status in ('active','sold','cancelled')", name="ck_market_status"),
    )


# ============================
# Brawl CARDS (new schema)
# ============================


class AdminRole(StrEnum):
    OWNER = "owner"
    HEAD_ADMIN = "head_admin"
    ADMIN = "admin"
    MODERATOR = "moderator"
    CONTENT_MANAGER = "content_manager"
    EVENT_MANAGER = "event_manager"


class PermissionCode(StrEnum):
    ADMIN_PANEL = "admin.panel"
    USERS_VIEW = "users.view"
    USERS_EDIT = "users.edit"
    CATALOG_EDIT = "catalog.edit"
    RARITIES_EDIT = "rarities.edit"
    BOOSTERS_EDIT = "boosters.edit"
    SHOP_EDIT = "shop.edit"
    CHESTS_EDIT = "chests.edit"
    TASKS_EDIT = "tasks.edit"
    RP_EDIT = "rp.edit"
    EVENTS_EDIT = "events.edit"
    BROADCAST = "broadcast"
    ECONOMY_EDIT = "economy.edit"
    LOGS_VIEW = "logs.view"
    MEDIA_EDIT = "media.edit"


class UserProfile(Base):
    __tablename__ = "bc_profiles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    exp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    activity_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tasks_done: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    games_played: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    games_won: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    market_sold: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    market_bought: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class BcUserSettings(Base):
    __tablename__ = "bc_user_settings"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    locale: Mapped[str] = mapped_column(String(16), default="ru", nullable=False)
    notifications: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    privacy: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    confirm_purchases: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    card_style: Mapped[str] = mapped_column(String(32), default="full", nullable=False)
    show_media: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    safe_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class BcTextTemplate(Base):
    __tablename__ = "bc_text_templates"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    locale: Mapped[str] = mapped_column(String(16), primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class BcMedia(Base):
    __tablename__ = "bc_media"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # photo/video/animation/sticker
    telegram_file_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    meta: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BcEvent(Base):
    __tablename__ = "bc_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BcRarity(Base):
    __tablename__ = "bc_rarities"

    key: Mapped[str] = mapped_column(String(32), primary_key=True)
    title: Mapped[str] = mapped_column(String(64), nullable=False)
    emoji: Mapped[str] = mapped_column(String(16), default="✨", nullable=False)
    chance: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)  # weights, normalized in service
    color: Mapped[str] = mapped_column(String(16), default="#A0A0A0", nullable=False)
    points_mult: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    coins_mult: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    available_in_chests: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    available_in_shop: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    drop_mode: Mapped[str] = mapped_column(String(16), default="normal", nullable=False)  # normal/event/manual
    sort: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    meta: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class BcLimitedSeries(Base):
    __tablename__ = "bc_limited_series"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    banner_media_id: Mapped[int | None] = mapped_column(ForeignKey("bc_media.id", ondelete="SET NULL"), nullable=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    project_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    per_user_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_coins: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_stars: Mapped[int | None] = mapped_column(Integer, nullable=True)
    conditions: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    can_manual_grant: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_released: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BcCard(Base):
    __tablename__ = "bc_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    rarity_key: Mapped[str] = mapped_column(ForeignKey("bc_rarities.key", ondelete="RESTRICT"), nullable=False)
    series: Mapped[str] = mapped_column(String(64), default="Core", nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    base_points: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    base_coins: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    drop_weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    is_limited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    limited_series_id: Mapped[int | None] = mapped_column(
        ForeignKey("bc_limited_series.id", ondelete="SET NULL"), nullable=True
    )
    event_id: Mapped[int | None] = mapped_column(ForeignKey("bc_events.id", ondelete="SET NULL"), nullable=True)

    image_file_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_id: Mapped[int | None] = mapped_column(ForeignKey("bc_media.id", ondelete="SET NULL"), nullable=True)

    is_sellable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    meta: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    rarity: Mapped["BcRarity"] = relationship()


class BcCardInstance(Base):
    __tablename__ = "bc_card_instances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("bc_cards.id", ondelete="CASCADE"), nullable=False, index=True)
    obtained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    source: Mapped[str] = mapped_column(String(32), default="brawl", nullable=False)

    points_awarded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    coins_awarded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    is_limited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    limited_series_id: Mapped[int | None] = mapped_column(
        ForeignKey("bc_limited_series.id", ondelete="SET NULL"), nullable=True
    )
    serial: Mapped[int | None] = mapped_column(Integer, nullable=True)


class BcBooster(Base):
    __tablename__ = "bc_boosters"

    key: Mapped[str] = mapped_column(String(48), primary_key=True)
    title: Mapped[str] = mapped_column(String(80), nullable=False)
    emoji: Mapped[str] = mapped_column(String(16), default="⚡", nullable=False)
    effect_type: Mapped[str] = mapped_column(String(32), nullable=False)  # luck/time/coins_mult/points_mult/limited
    effect_power: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    price_coins: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_stars: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0 = instant/one-shot
    stackable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_stack: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    purchase_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("bc_events.id", ondelete="SET NULL"), nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class BcActiveBooster(Base):
    __tablename__ = "bc_active_boosters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    booster_key: Mapped[str] = mapped_column(ForeignKey("bc_boosters.key", ondelete="CASCADE"), nullable=False)
    stacks: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    active_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BcShopCategory(Base):
    __tablename__ = "bc_shop_categories"

    key: Mapped[str] = mapped_column(String(48), primary_key=True)
    title: Mapped[str] = mapped_column(String(80), nullable=False)
    emoji: Mapped[str] = mapped_column(String(16), default="🛒", nullable=False)
    sort: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class BcShopItem(Base):
    __tablename__ = "bc_shop_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category_key: Mapped[str] = mapped_column(
        ForeignKey("bc_shop_categories.key", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    price_coins: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_stars: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort: Mapped[int] = mapped_column(Integer, default=100, nullable=False)


class BcChest(Base):
    __tablename__ = "bc_chests"

    key: Mapped[str] = mapped_column(String(48), primary_key=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    emoji: Mapped[str] = mapped_column(String(16), default="📦", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    price_coins: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_stars: Mapped[int | None] = mapped_column(Integer, nullable=True)
    open_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    guarantees: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    limits: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    media_id: Mapped[int | None] = mapped_column(ForeignKey("bc_media.id", ondelete="SET NULL"), nullable=True)
    access: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort: Mapped[int] = mapped_column(Integer, default=100, nullable=False)


class BcChestDrop(Base):
    __tablename__ = "bc_chest_drops"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chest_key: Mapped[str] = mapped_column(ForeignKey("bc_chests.key", ondelete="CASCADE"), nullable=False, index=True)
    rarity_key: Mapped[str] = mapped_column(ForeignKey("bc_rarities.key", ondelete="RESTRICT"), nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    min_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    meta: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class BcTask(Base):
    __tablename__ = "bc_tasks"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # daily/weekly/oneoff/hidden/event
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    target: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    reward: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    check_type: Mapped[str] = mapped_column(String(32), default="counter", nullable=False)
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort: Mapped[int] = mapped_column(Integer, default=100, nullable=False)


class BcUserTask(Base):
    __tablename__ = "bc_user_tasks"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    task_key: Mapped[str] = mapped_column(ForeignKey("bc_tasks.key", ondelete="CASCADE"), primary_key=True)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    state: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class BcBonusTask(Base):
    __tablename__ = "bc_bonus_tasks"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    emoji: Mapped[str] = mapped_column(String(16), default="🎁", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)  # subscribe/channel/chat/link/invite/custom
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    sort: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class BcUserBonusTask(Base):
    __tablename__ = "bc_user_bonus_tasks"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    task_key: Mapped[str] = mapped_column(ForeignKey("bc_bonus_tasks.key", ondelete="CASCADE"), primary_key=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    state: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class BcRPCategory(Base):
    __tablename__ = "bc_rp_categories"

    key: Mapped[str] = mapped_column(String(48), primary_key=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    emoji: Mapped[str] = mapped_column(String(16), default="🎭", nullable=False)
    sort: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class BcRPAction(Base):
    __tablename__ = "bc_rp_actions"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    category_key: Mapped[str] = mapped_column(
        ForeignKey("bc_rp_categories.key", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    emoji: Mapped[str] = mapped_column(String(16), default="✨", nullable=False)
    requires_target: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    reward: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    templates: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    media_id: Mapped[int | None] = mapped_column(ForeignKey("bc_media.id", ondelete="SET NULL"), nullable=True)
    restrictions: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    allowed_scopes: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)  # {"private":true,"group":true}
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort: Mapped[int] = mapped_column(Integer, default=100, nullable=False)


class BcRPLog(Base):
    __tablename__ = "bc_rp_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    target_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action_key: Mapped[str] = mapped_column(ForeignKey("bc_rp_actions.key", ondelete="SET NULL"), nullable=True)
    chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BcMarketLot(Base):
    __tablename__ = "bc_market_lots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    card_instance_id: Mapped[int] = mapped_column(
        ForeignKey("bc_card_instances.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    currency: Mapped[str] = mapped_column(String(16), nullable=False)  # coins/stars
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    fee_percent: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)  # active/sold/cancelled
    buyer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    bought_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("currency in ('coins','stars')", name="ck_bc_market_currency"),
        CheckConstraint("status in ('active','sold','cancelled')", name="ck_bc_market_status"),
    )


class BcMarriageProposal(Base):
    __tablename__ = "bc_marriage_proposals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    proposer_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    target_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)  # pending/accepted/declined
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("proposer_id", "target_id", name="uq_bc_marriage_proposal_pair"),)


class BcRole(Base):
    __tablename__ = "bc_roles"

    key: Mapped[str] = mapped_column(String(48), primary_key=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    meta: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class BcPermission(Base):
    __tablename__ = "bc_permissions"

    code: Mapped[str] = mapped_column(String(80), primary_key=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)


class BcRolePermission(Base):
    __tablename__ = "bc_role_permissions"

    role_key: Mapped[str] = mapped_column(ForeignKey("bc_roles.key", ondelete="CASCADE"), primary_key=True)
    permission_code: Mapped[str] = mapped_column(ForeignKey("bc_permissions.code", ondelete="CASCADE"), primary_key=True)


class BcUserRole(Base):
    __tablename__ = "bc_user_roles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_key: Mapped[str] = mapped_column(ForeignKey("bc_roles.key", ondelete="CASCADE"), primary_key=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BcAuditLog(Base):
    __tablename__ = "bc_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BcInputState(Base):
    __tablename__ = "bc_input_state"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    state: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class BcUserState(Base):
    __tablename__ = "bc_user_state"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    last_card_instance_id: Mapped[int | None] = mapped_column(
        ForeignKey("bc_card_instances.id", ondelete="SET NULL"), nullable=True
    )
    last_card_id: Mapped[int | None] = mapped_column(ForeignKey("bc_cards.id", ondelete="SET NULL"), nullable=True)
    last_card_got_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
