from __future__ import annotations

import logging
from pathlib import Path

from database.base import Database

LOGGER = logging.getLogger(__name__)


MIGRATION_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    id TEXT PRIMARY KEY,
    applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


async def run_migrations(database: Database, migrations_path: Path) -> None:
    await database.executescript(MIGRATION_TABLE_SQL)
    applied = await database.fetchall("SELECT id FROM schema_migrations;")
    applied_ids = {row["id"] for row in applied}

    migration_files = sorted(migrations_path.glob("*.sql"))
    for migration_file in migration_files:
        migration_id = migration_file.name
        if migration_id in applied_ids:
            continue
        sql = migration_file.read_text(encoding="utf-8")
        LOGGER.info("Applying migration %s", migration_id)
        await database.executescript(sql)
        await database.execute("INSERT INTO schema_migrations(id) VALUES (?);", [migration_id])
