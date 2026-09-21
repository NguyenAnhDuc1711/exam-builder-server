"""Migration sanity: `upgrade head` builds the schema, `downgrade base`
removes it cleanly.

These tests are synchronous on purpose: `alembic/env.py` calls
`asyncio.run()` itself, which would explode inside an already-running event
loop.

NOTE (T002): written without a Python/Docker runtime available in the
authoring environment — unexecuted, see the T002 handoff.
"""

import asyncio
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from tests.conftest import TEST_DATABASE_URL
from tests.unit.test_schema_invariants import EXPECTED_TABLES

ROOT = Path(__file__).resolve().parents[2]


def _alembic_config() -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    return config


async def _fetch(sql: str) -> set[str]:
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            rows = await conn.execute(text(sql))
            return {row[0] for row in rows}
    finally:
        await engine.dispose()


async def _reset_schema() -> None:
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
    finally:
        await engine.dispose()


def _public_tables() -> set[str]:
    return asyncio.run(
        _fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public'"
        )
    )


@pytest.fixture
def empty_database():
    asyncio.run(_reset_schema())
    yield
    asyncio.run(_reset_schema())


def test_upgrade_head_creates_every_table(empty_database):
    command.upgrade(_alembic_config(), "head")

    tables = _public_tables()
    missing = EXPECTED_TABLES - tables
    assert not missing, f"migration did not create: {sorted(missing)}"


def test_downgrade_base_rolls_back_cleanly(empty_database):
    config = _alembic_config()
    command.upgrade(config, "head")
    command.downgrade(config, "base")

    tables = _public_tables()
    assert not (EXPECTED_TABLES & tables)


def test_migrated_schema_has_no_multi_tenant_columns(empty_database):
    """NFR-3 verified against the real, migrated database."""
    command.upgrade(_alembic_config(), "head")

    columns = asyncio.run(
        _fetch(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public'"
        )
    )
    assert not [c for c in columns if "organization" in c or "tenant" in c]
