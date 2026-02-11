from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.config import AppConfig, DiscordConfig
from database.models import TicketCategory, TicketPanel
from services.cache import MemoryCache
from services.ticket_service import TicketService, TicketServiceDeps


@pytest.mark.asyncio
async def test_create_ticket_with_mocked_discord_objects() -> None:
    cache = MemoryCache()
    deps = TicketServiceDeps(
        guild_repo=MagicMock(),
        category_repo=MagicMock(),
        panel_repo=MagicMock(),
        ticket_repo=MagicMock(),
        participant_repo=MagicMock(),
        event_repo=MagicMock(),
        blacklist_repo=MagicMock(),
        staff_repo=MagicMock(),
        audit_repo=MagicMock(),
        analytics_repo=MagicMock(),
        cache=cache,
    )
    deps.guild_repo.next_ticket_number = AsyncMock(return_value=101)
    deps.blacklist_repo.get_active = AsyncMock(return_value=None)
    deps.ticket_repo.list_open_by_user = AsyncMock(return_value=[])
    deps.category_repo.get = AsyncMock(
        return_value=TicketCategory(
            id="cat-1",
            guild_id=123,
            key="support",
            display_name="Support",
            description="Support requests",
            channel_category_id=None,
            support_role_ids=[],
            modal_questions=[],
            template={},
            priority_default="normal",
            tags_default=["support"],
            sla_minutes=60,
            is_enabled=True,
        )
    )
    deps.ticket_repo.create = AsyncMock()
    deps.participant_repo.add = AsyncMock()
    deps.event_repo.log = AsyncMock()
    deps.audit_repo.log = AsyncMock()

    service = TicketService(config=AppConfig(discord=DiscordConfig(token="x")), deps=deps)

    guild = MagicMock()
    guild.id = 123
    guild.default_role = object()
    guild.me = object()
    guild.get_role = MagicMock(return_value=None)
    guild.get_channel = MagicMock(return_value=None)
    guild.create_text_channel = AsyncMock(return_value=SimpleNamespace(id=987654321))

    opener = MagicMock()
    opener.id = 999
    opener.display_name = "Test User"

    panel = TicketPanel(
        id="p1",
        panel_id="support-main",
        guild_id=123,
        channel_id=321,
        message_id=None,
        title="Support",
        description="Open ticket",
        button_label="Create Ticket",
        button_emoji="🎫",
        button_style="primary",
        category_map={},
        support_role_ids=[],
        is_enabled=True,
    )

    ticket = await service.create_ticket(
        guild=guild,
        opener=opener,
        panel=panel,
        category_key="support",
        form_answers={"details": "help needed"},
    )

    assert ticket.ticket_number == 101
    assert ticket.guild_id == 123
    assert ticket.channel_id == 987654321
    deps.ticket_repo.create.assert_awaited()
