import asyncio
from pathlib import Path

from sqlalchemy import inspect

from app.core.config import get_settings
from app.db.session import engine


BASELINE_REVISION = "0001_baseline"
LEGACY_TABLES = {
    "users",
    "seller_profiles",
    "credit_wallets",
    "usage_ledgers",
    "email_otps",
    "personal_access_tokens",
    "categories",
    "cities",
    "listing_drafts",
    "listings",
    "listing_images",
    "ai_jobs",
    "favorites",
    "reports",
    "orders",
}


def _alembic_config():
    from alembic.config import Config

    backend_dir = Path(__file__).resolve().parents[2]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    config.set_main_option("sqlalchemy.url", get_settings().database_url)
    return config


async def _needs_legacy_stamp() -> bool:
    async with engine.begin() as connection:
        def _inspect(sync_connection) -> bool:
            tables = set(inspect(sync_connection).get_table_names())
            return "alembic_version" not in tables and bool(tables & LEGACY_TABLES)

        return await connection.run_sync(_inspect)


async def upgrade_database() -> None:
    from alembic import command

    config = _alembic_config()
    if await _needs_legacy_stamp():
        await asyncio.to_thread(command.stamp, config, BASELINE_REVISION)
    await asyncio.to_thread(command.upgrade, config, "head")
