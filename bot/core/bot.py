from __future__ import annotations

import logging
from pathlib import Path

import discord
from discord.ext import commands

from core.config import AppConfig
from core.errors import handle_app_command_error, handle_prefix_command_error
from core.extensions import load_extensions
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
    SecurityRepository,
    StaffStatsRepository,
    TicketRepository,
)
from services.analytics_service import AnalyticsService
from services.automation_service import AutomationService
from services.cache import CacheBackend, build_cache
from services.security_service import SecurityService
from services.ticket_service import TicketService, TicketServiceDeps
from services.transcript_service import TranscriptService
from utils.i18n import I18N

LOGGER = logging.getLogger(__name__)


class TicketBot(commands.Bot):
    def __init__(self, config: AppConfig) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        intents.messages = True
        intents.message_content = True
        intents.reactions = True

        super().__init__(
            command_prefix=config.discord.prefix,
            intents=intents,
            application_id=config.discord.application_id,
            allowed_mentions=discord.AllowedMentions(
                everyone=config.discord.allowed_mentions_everyone,
                roles=True,
                users=True,
                replied_user=False,
            ),
            help_command=None,
        )
        self.config = config
        self.root_dir = Path(__file__).resolve().parent.parent
        self.database = Database(
            url=config.database.url,
            timeout_seconds=config.database.timeout_seconds,
            pool_min_size=config.database.pool_min_size,
            pool_max_size=config.database.pool_max_size,
        )
        self.cache: CacheBackend | None = None
        self.i18n = I18N(self.root_dir / "config" / "locales", config.i18n.default_locale)

        # Repositories and services are initialized during setup_hook.
        self.guild_repo: GuildRepository
        self.category_repo: CategoryRepository
        self.panel_repo: PanelRepository
        self.ticket_repo: TicketRepository
        self.participant_repo: ParticipantRepository
        self.event_repo: EventRepository
        self.blacklist_repo: BlacklistRepository
        self.staff_repo: StaffStatsRepository
        self.audit_repo: AuditRepository
        self.security_repo: SecurityRepository
        self.analytics_repo: AnalyticsRepository

        self.ticket_service: TicketService
        self.transcript_service: TranscriptService
        self.analytics_service: AnalyticsService
        self.security_service: SecurityService
        self.automation_service: AutomationService

    async def setup_hook(self) -> None:
        await self.database.connect()
        await run_migrations(self.database, self.root_dir / "database" / "migrations")
        self.cache = await build_cache(self.config.redis)

        self.guild_repo = GuildRepository(self.database)
        self.category_repo = CategoryRepository(self.database)
        self.panel_repo = PanelRepository(self.database)
        self.ticket_repo = TicketRepository(self.database)
        self.participant_repo = ParticipantRepository(self.database)
        self.event_repo = EventRepository(self.database)
        self.blacklist_repo = BlacklistRepository(self.database)
        self.staff_repo = StaffStatsRepository(self.database)
        self.audit_repo = AuditRepository(self.database)
        self.security_repo = SecurityRepository(self.database)
        self.analytics_repo = AnalyticsRepository(self.database)

        deps = TicketServiceDeps(
            guild_repo=self.guild_repo,
            category_repo=self.category_repo,
            panel_repo=self.panel_repo,
            ticket_repo=self.ticket_repo,
            participant_repo=self.participant_repo,
            event_repo=self.event_repo,
            blacklist_repo=self.blacklist_repo,
            staff_repo=self.staff_repo,
            audit_repo=self.audit_repo,
            analytics_repo=self.analytics_repo,
            cache=self.cache,
        )
        self.ticket_service = TicketService(self.config, deps)
        self.transcript_service = TranscriptService(self.config.transcripts)
        self.analytics_service = AnalyticsService(
            self.config.metrics, self.analytics_repo, self.ticket_repo, self.staff_repo
        )
        self.security_service = SecurityService(
            self.config,
            self.cache,
            self.security_repo,
            self.audit_repo,
        )
        self.automation_service = AutomationService(self.database, self.ticket_repo, self.event_repo)

        await self.ticket_service.bootstrap_panels_from_config()
        await load_extensions(self, self.config.enabled_extensions)

        if self.config.discord.sync_commands_on_start:
            synced = await self.tree.sync()
            LOGGER.info("Synced %s application commands", len(synced))

        self.tree.on_error = handle_app_command_error  # type: ignore[assignment]

    async def on_ready(self) -> None:
        LOGGER.info("Bot ready as %s (%s)", self.user, self.user.id if self.user else "n/a")
        activity_type = self.config.discord.activity_type.lower()
        if activity_type == "playing":
            activity = discord.Game(name=self.config.discord.status_text)
        elif activity_type == "listening":
            activity = discord.Activity(
                type=discord.ActivityType.listening, name=self.config.discord.status_text
            )
        else:
            activity = discord.Activity(
                type=discord.ActivityType.watching, name=self.config.discord.status_text
            )
        await self.change_presence(status=discord.Status.online, activity=activity)

    async def on_command_error(self, ctx: commands.Context[commands.Bot], error: commands.CommandError) -> None:
        if ctx.command and ctx.command.has_error_handler():
            return
        await handle_prefix_command_error(ctx, error)

    async def close(self) -> None:
        await super().close()
        await self.database.close()
        if self.cache:
            await self.cache.close()
