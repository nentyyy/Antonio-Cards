from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.db.bootstrap import build_engine_kwargs, create_hot_path_indexes, register_sqlite_pragmas
from app.db.models import Base

settings = get_settings()
engine = create_async_engine(settings.database_url, **build_engine_kwargs(settings.database_url))
register_sqlite_pragmas(engine, settings.database_url)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    session = SessionLocal()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await create_hot_path_indexes(conn)
