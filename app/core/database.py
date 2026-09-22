"""Async SQLAlchemy engine + session factory.

The engine is created once at import time from `settings.DATABASE_URL`
(`postgresql+asyncpg://...`). `get_session` is the FastAPI dependency every
router/repository should depend on; it never commits on your behalf — the
use case owns the transaction boundary (see CRIT-1).
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)

# expire_on_commit=False: attributes stay readable after `commit()`, which
# matters because a response model is usually serialized after the commit.
AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
