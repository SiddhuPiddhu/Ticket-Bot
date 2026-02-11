from __future__ import annotations

from pathlib import Path

import pytest

from core.config import AppConfig, DiscordConfig
from database.base import Database
from database.migrations.runner import run_migrations
from database.repositories import (
    AnalyticsRepository,
    AuditRepository,
    BlacklistRepository,
    CategoryRepository,
    EventRepository,
    GuildRepository,
    PanelRepository,
    ParticipantRepository,
    StaffStatsRepository,
    TicketRepository,
)
from services.cache import MemoryCache
from services.ticket_service import TicketService, TicketServiceDeps

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "database" / "migrations"


@pytest.mark.asyncio
async def test_bootstrap_default_categories(tmp_path: Path) -> None:
    db_path = tmp_path / "tickets.db"
    db = Database(url=f"sqlite:///{db_path}")
    await db.connect()
    await run_migrations(db, MIGRATIONS_DIR)

    deps = TicketServiceDeps(
        guild_repo=GuildRepository(db),
        category_repo=CategoryRepository(db),
        panel_repo=PanelRepository(db),
        ticket_repo=TicketRepository(db),
        participant_repo=ParticipantRepository(db),
        event_repo=EventRepository(db),
        blacklist_repo=BlacklistRepository(db),
        staff_repo=StaffStatsRepository(db),
        audit_repo=AuditRepository(db),
        analytics_repo=AnalyticsRepository(db),
        cache=MemoryCache(),
    )
    service = TicketService(config=AppConfig(discord=DiscordConfig(token="x")), deps=deps)

    await service.bootstrap_default_categories(123)
    categories = await service.list_categories(123)
    assert len(categories) >= 3

    name = service.sanitize_channel_fragment("Hello World !!!")
    assert name == "hello-world"

    await db.close()
