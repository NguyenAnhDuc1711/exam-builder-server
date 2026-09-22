"""Shared test fixtures.

`app.core.config` builds its `Settings()` singleton at import time and has
no defaults for the required variables, so the environment must be primed
*before* anything under `app.` is imported — hence the module-level
`os.environ` writes above the imports.

`DATABASE_URL` is force-set (not `setdefault`) to the test database so a
stray `.env` pointing at a dev database can never be dropped by these
tests. Override the target with `TEST_DATABASE_URL`.
"""

import os

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://exam_builder:exam_builder@localhost:5432/exam_builder_test",
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key")
os.environ.setdefault("CLOUDINARY_CLOUD_NAME", "test")
os.environ.setdefault("CLOUDINARY_API_KEY", "test")
os.environ.setdefault("CLOUDINARY_API_SECRET", "test")

import pytest_asyncio  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool  # noqa: E402

import app.models  # noqa: E402,F401  (registers tables)
from app.models.base import Base  # noqa: E402


@pytest_asyncio.fixture
async def db_engine():
    """A fresh schema per test, built from the ORM metadata."""
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def session(db_engine):
    maker = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as db_session:
        yield db_session
