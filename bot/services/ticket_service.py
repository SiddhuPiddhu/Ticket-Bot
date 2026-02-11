from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import timedelta
from uuid import uuid4

import discord

from core.config import AppConfig
from core.errors import TicketLimitReached, TicketNotFound, TicketStateError, ValidationError
from database.models import TicketCategory, TicketPanel, TicketRecord
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
from services.cache import CacheBackend
from utils.constants import PRIORITY_LEVELS
from utils.rate_limit import DistributedRateLimiter
from utils.time import to_iso, utc_now

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class TicketServiceDeps:
    guild_repo: GuildRepository
    category_repo: CategoryRepository
    panel_repo: PanelRepository
    ticket_repo: TicketRepository
    participant_repo: ParticipantRepository
    event_repo: EventRepository
    blacklist_repo: BlacklistRepository
    staff_repo: StaffStatsRepository
    audit_repo: AuditRepository
    analytics_repo: AnalyticsRepository
    cache: CacheBackend


class TicketService:
    def __init__(self, config: AppConfig, deps: TicketServiceDeps) -> None:
        self.config = config
        self.deps = deps
        self.rate_limiter = DistributedRateLimiter(deps.cache)

    async def bootstrap_default_categories(self, guild_id: int) -> None:
        existing = await self.deps.category_repo.list_by_guild(guild_id)
        if existing:
            return
        defaults = [
            TicketCategory(
                id=str(uuid4()),
                guild_id=guild_id,
                key="support",
                display_name="General Support",
                description="Account, setup, and technical support.",
                channel_category_id=None,
                support_role_ids=[],
                modal_questions=[
                    {
                        "id": "subject",
                        "label": "Subject",
                        "placeholder": "Summarize your issue",
                        "style": "short",
                        "required": True,
                        "max_length": 100,
                    },
                    {
                        "id": "details",
                        "label": "Details",
                        "placeholder": "Describe the issue with relevant details",
                        "style": "long",
                        "required": True,
                        "max_length": 1000,
                    },
                ],
                priority_default="normal",
                tags_default=["support"],
                sla_minutes=120,
            ),
            TicketCategory(
                id=str(uuid4()),
                guild_id=guild_id,
                key="billing",
                display_name="Billing",
                description="Payment and invoice requests.",
                channel_category_id=None,
                support_role_ids=[],
                modal_questions=[
                    {
                        "id": "invoice_id",
                        "label": "Invoice ID",
                        "placeholder": "Invoice identifier",
                        "style": "short",
                        "required": True,
                        "max_length": 80,
                    },
                    {
                        "id": "summary",
                        "label": "Issue Summary",
                        "placeholder": "Describe the billing issue",
                        "style": "long",
                        "required": True,
                        "max_length": 1000,
                    },
                ],
                priority_default="high",
                tags_default=["billing"],
                sla_minutes=60,
            ),
            TicketCategory(
                id=str(uuid4()),
                guild_id=guild_id,
                key="bug",
                display_name="Bug Report",
                description="Report product bugs and regressions.",
                channel_category_id=None,
                support_role_ids=[],
                modal_questions=[
                    {
                        "id": "environment",
                        "label": "Environment",
                        "placeholder": "Version / platform",
                        "style": "short",
                        "required": True,
                        "max_length": 120,
                    },
                    {
                        "id": "repro_steps",
                        "label": "Reproduction Steps",
                        "placeholder": "List deterministic reproduction steps",
                        "style": "long",
                        "required": True,
                        "max_length": 1000,
                    },
                ],
                priority_default="high",
                tags_default=["bug"],
                sla_minutes=45,
            ),
            TicketCategory(
                id=str(uuid4()),
                guild_id=guild_id,
                key="suggestion",
                display_name="Suggestion",
                description="Share ideas and feature proposals.",
                channel_category_id=None,
                support_role_ids=[],
                modal_questions=[
                    {
                        "id": "idea",
                        "label": "Suggestion",
                        "placeholder": "Describe your idea",
                        "style": "long",
                        "required": True,
                        "max_length": 1000,
                    }
                ],
                priority_default="low",
                tags_default=["suggestion"],
                sla_minutes=240,
            ),
            TicketCategory(
                id=str(uuid4()),
                guild_id=guild_id,
                key="payment-proof",
                display_name="Payment Proof",
                description="Submit payment screenshots/proofs.",
                channel_category_id=None,
                support_role_ids=[],
                modal_questions=[
                    {
                        "id": "order_id",
                        "label": "Order ID",
                        "placeholder": "Order identifier",
                        "style": "short",
                        "required": True,
                        "max_length": 80,
                    },
                    {
                        "id": "context",
                        "label": "Context",
                        "placeholder": "Any additional context",
                        "style": "long",
                        "required": False,
                        "max_length": 1000,
                    },
                ],
                priority_default="normal",
                tags_default=["payment"],
                sla_minutes=120,
            ),
        ]
        for category in defaults:
            await self.deps.category_repo.upsert(category)

    async def bootstrap_panels_from_config(self) -> None:
        for panel_cfg in self.config.ticket_panels:
            panel = TicketPanel(
                id=str(uuid4()),
                panel_id=panel_cfg.panel_id,
                guild_id=panel_cfg.guild_id,
                channel_id=panel_cfg.channel_id,
                message_id=None,
                title=panel_cfg.title,
                description=panel_cfg.description,
                button_label=panel_cfg.button_label,
                button_emoji=panel_cfg.button_emoji,
                button_style=panel_cfg.button_style,
                category_map=panel_cfg.category_map,
                support_role_ids=panel_cfg.support_role_ids,
                log_channel_id=panel_cfg.log_channel_id,
                transcript_channel_id=panel_cfg.transcript_channel_id,
                is_enabled=True,
            )
            await self.deps.panel_repo.upsert(panel=panel, created_by_id=0)
            await self.deps.guild_repo.ensure_guild(panel.guild_id)
            await self.bootstrap_default_categories(panel.guild_id)

    async def is_user_blacklisted(self, guild_id: int, user_id: int) -> bool:
        row = await self.deps.blacklist_repo.get_active(guild_id=guild_id, user_id=user_id)
        return row is not None

    async def check_ticket_open_limits(self, guild_id: int, user_id: int) -> None:
        if await self.is_user_blacklisted(guild_id, user_id):
            raise ValidationError("You are blacklisted from creating tickets.")

        user_open = await self.deps.ticket_repo.list_open_by_user(guild_id, user_id)
        if len(user_open) >= self.config.security.max_open_tickets_per_user:
            raise TicketLimitReached()

        cooldown_key = f"ticket:cooldown:{guild_id}:{user_id}"
        cooldown_hit = await self.rate_limiter.hit(
            cooldown_key,
            limit=1,
            window_seconds=self.config.security.ticket_creation_cooldown_seconds,
        )
        if not cooldown_hit.allowed:
            raise ValidationError(
                f"Ticket creation cooldown active ({self.config.security.ticket_creation_cooldown_seconds}s)."
            )

        hourly_key = f"ticket:hourly:{guild_id}:{user_id}"
        hour_hit = await self.rate_limiter.hit(
            hourly_key,
            limit=self.config.security.ticket_creation_max_per_hour,
            window_seconds=3600,
        )
        if not hour_hit.allowed:
            raise ValidationError("Hourly ticket creation limit exceeded.")

    async def get_panel(self, panel_id: str) -> TicketPanel | None:
        return await self.deps.panel_repo.get_by_panel_id(panel_id)

    async def get_panel_by_message(self, guild_id: int, message_id: int) -> TicketPanel | None:
        return await self.deps.panel_repo.get_by_message(guild_id, message_id)

    async def list_categories(self, guild_id: int) -> list[TicketCategory]:
        categories = await self.deps.category_repo.list_by_guild(guild_id)
        return [c for c in categories if c.is_enabled]

    async def resolve_category(self, guild_id: int, key: str) -> TicketCategory:
        category = await self.deps.category_repo.get(guild_id=guild_id, key=key)
        if not category:
            raise ValidationError(f"Unknown ticket category: {key}")
        if not category.is_enabled:
            raise ValidationError(f"Ticket category `{key}` is disabled.")
        return category

    @staticmethod
    def sanitize_channel_fragment(name: str) -> str:
        name = name.strip().lower()
        name = re.sub(r"[^a-z0-9-]+", "-", name)
        name = re.sub(r"-{2,}", "-", name).strip("-")
        return name[:32] or "user"

    async def build_ticket_name(
        self,
        guild_id: int,
        category_key: str,
        opener_name: str,
    ) -> tuple[str, int]:
        number = await self.deps.guild_repo.next_ticket_number(guild_id)
        clean_name = self.sanitize_channel_fragment(opener_name)
        return f"ticket-{number}-{category_key}-{clean_name}"[:95], number

    async def create_ticket(
        self,
        guild: discord.Guild,
        opener: discord.Member,
        panel: TicketPanel | None,
        category_key: str,
        form_answers: dict[str, str],
        anonymous: bool = False,
    ) -> TicketRecord:
        await self.check_ticket_open_limits(guild.id, opener.id)
        category = await self.resolve_category(guild.id, category_key)

        overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            opener: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
                add_reactions=True,
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
                manage_messages=True,
            ),
        }

        support_role_ids = set(category.support_role_ids)
        if panel:
            support_role_ids.update(panel.support_role_ids)
        for role_id in support_role_ids:
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_messages=True,
                    attach_files=True,
                    embed_links=True,
                )

        channel_category = guild.get_channel(category.channel_category_id) if category.channel_category_id else None
        if channel_category and not isinstance(channel_category, discord.CategoryChannel):
            channel_category = None

        channel_name, ticket_number = await self.build_ticket_name(
            guild_id=guild.id,
            category_key=category.key,
            opener_name=opener.display_name,
        )
        channel = await guild.create_text_channel(
            name=channel_name,
            category=channel_category,
            overwrites=overwrites,
            reason=f"Ticket created by {opener} ({opener.id})",
            topic=f"ticket|{ticket_number}|opener:{opener.id}|category:{category.key}",
        )

        ticket_id = str(uuid4())
        created_at = utc_now()
        response_due_at = created_at + timedelta(minutes=category.sla_minutes)
        record = TicketRecord(
            id=ticket_id,
            ticket_number=ticket_number,
            guild_id=guild.id,
            channel_id=channel.id,
            opener_id=opener.id,
            opener_display=(opener.display_name if not anonymous else "Anonymous User"),
            panel_id=panel.panel_id if panel else None,
            category_key=category.key,
            category_channel_id=category.channel_category_id,
            status="open",
            priority=category.priority_default if category.priority_default in PRIORITY_LEVELS else "normal",
            tags=category.tags_default,
            form_answers=form_answers,
            internal_notes=[],
            is_anonymous=anonymous and self.config.security.allow_anonymous_tickets,
            response_due_at=to_iso(response_due_at),
            department=category.display_name,
            created_at=to_iso(created_at),
            updated_at=to_iso(created_at),
        )

        await self.deps.ticket_repo.create(record)
        await self.deps.participant_repo.add(ticket_id=ticket_id, user_id=opener.id, added_by_id=opener.id)
        await self.deps.event_repo.log(
            ticket_id=ticket_id,
            guild_id=guild.id,
            actor_id=opener.id,
            event_type="create",
            payload={
                "category": category.key,
                "answers": form_answers,
                "anonymous": record.is_anonymous,
                "channel_id": channel.id,
            },
        )
        await self.deps.audit_repo.log(
            guild_id=guild.id,
            actor_id=opener.id,
            action="ticket_create",
            target_id=ticket_id,
            metadata={"channel_id": channel.id, "category": category.key},
        )
        return record

    async def get_ticket_for_channel(self, guild_id: int, channel_id: int) -> TicketRecord:
        ticket = await self.deps.ticket_repo.get_by_channel(guild_id=guild_id, channel_id=channel_id)
        if not ticket:
            raise TicketNotFound()
        return ticket

    async def claim_ticket(self, ticket: TicketRecord, staff_member: discord.Member) -> TicketRecord:
        if ticket.status not in {"open", "pending", "locked"}:
            raise TicketStateError("Ticket cannot be claimed in its current state.")
        await self.deps.ticket_repo.set_claimed(ticket.id, staff_member.id)
        await self.deps.staff_repo.increment_claimed(ticket.guild_id, staff_member.id)
        await self.deps.event_repo.log(
            ticket_id=ticket.id,
            guild_id=ticket.guild_id,
            actor_id=staff_member.id,
            event_type="claim",
            payload={"staff_id": staff_member.id},
        )
        await self.deps.audit_repo.log(
            guild_id=ticket.guild_id,
            actor_id=staff_member.id,
            action="ticket_claim",
            target_id=ticket.id,
        )
        refreshed = await self.deps.ticket_repo.get_by_id(ticket.id)
        if not refreshed:
            raise TicketNotFound()
        return refreshed

    async def unclaim_ticket(self, ticket: TicketRecord, staff_member: discord.Member) -> TicketRecord:
        await self.deps.ticket_repo.set_claimed(ticket.id, None)
        await self.deps.event_repo.log(
            ticket_id=ticket.id,
            guild_id=ticket.guild_id,
            actor_id=staff_member.id,
            event_type="unclaim",
            payload={"staff_id": staff_member.id},
        )
        await self.deps.audit_repo.log(
            guild_id=ticket.guild_id,
            actor_id=staff_member.id,
            action="ticket_unclaim",
            target_id=ticket.id,
        )
        refreshed = await self.deps.ticket_repo.get_by_id(ticket.id)
        if not refreshed:
            raise TicketNotFound()
        return refreshed

    async def lock_ticket(self, ticket: TicketRecord, actor_id: int) -> None:
        await self.deps.ticket_repo.set_locked(ticket.id, True)
        await self.deps.event_repo.log(
            ticket_id=ticket.id,
            guild_id=ticket.guild_id,
            actor_id=actor_id,
            event_type="lock",
            payload={},
        )
        await self.deps.audit_repo.log(
            guild_id=ticket.guild_id,
            actor_id=actor_id,
            action="ticket_lock",
            target_id=ticket.id,
        )

    async def unlock_ticket(self, ticket: TicketRecord, actor_id: int) -> None:
        await self.deps.ticket_repo.set_locked(ticket.id, False)
        await self.deps.event_repo.log(
            ticket_id=ticket.id,
            guild_id=ticket.guild_id,
            actor_id=actor_id,
            event_type="unlock",
            payload={},
        )
        await self.deps.audit_repo.log(
            guild_id=ticket.guild_id,
            actor_id=actor_id,
            action="ticket_unlock",
            target_id=ticket.id,
        )

    async def close_ticket(self, ticket: TicketRecord, actor_id: int, reason: str) -> None:
        if self.config.security.require_ticket_close_reason and not reason.strip():
            raise ValidationError("Close reason is required.")
        await self.deps.ticket_repo.set_status(
            ticket_id=ticket.id,
            status="closed",
            close_reason=reason,
            closed_by_id=actor_id,
        )
        await self.deps.staff_repo.increment_closed(ticket.guild_id, actor_id)
        await self.deps.event_repo.log(
            ticket_id=ticket.id,
            guild_id=ticket.guild_id,
            actor_id=actor_id,
            event_type="close",
            payload={"reason": reason},
        )
        await self.deps.audit_repo.log(
            guild_id=ticket.guild_id,
            actor_id=actor_id,
            action="ticket_close",
            target_id=ticket.id,
            metadata={"reason": reason},
        )

    async def reopen_ticket(self, ticket: TicketRecord, actor_id: int) -> None:
        await self.deps.ticket_repo.set_status(ticket.id, "open")
        await self.deps.ticket_repo.increment_reopened(ticket.id)
        await self.deps.event_repo.log(
            ticket_id=ticket.id,
            guild_id=ticket.guild_id,
            actor_id=actor_id,
            event_type="reopen",
            payload={},
        )
        await self.deps.audit_repo.log(
            guild_id=ticket.guild_id,
            actor_id=actor_id,
            action="ticket_reopen",
            target_id=ticket.id,
        )

    async def rename_ticket(self, ticket: TicketRecord, actor_id: int, new_channel_id: int, new_name: str) -> None:
        await self.deps.ticket_repo.update_channel(ticket.id, new_channel_id)
        await self.deps.event_repo.log(
            ticket_id=ticket.id,
            guild_id=ticket.guild_id,
            actor_id=actor_id,
            event_type="rename",
            payload={"name": new_name},
        )
        await self.deps.audit_repo.log(
            guild_id=ticket.guild_id,
            actor_id=actor_id,
            action="ticket_rename",
            target_id=ticket.id,
            metadata={"name": new_name},
        )

    async def transfer_ticket(self, ticket: TicketRecord, actor_id: int, new_owner: discord.Member) -> None:
        await self.deps.ticket_repo.transfer_owner(ticket.id, new_owner.id, new_owner.display_name)
        await self.deps.participant_repo.add(ticket.id, new_owner.id, actor_id)
        await self.deps.event_repo.log(
            ticket_id=ticket.id,
            guild_id=ticket.guild_id,
            actor_id=actor_id,
            event_type="transfer",
            payload={"new_owner_id": new_owner.id},
        )
        await self.deps.audit_repo.log(
            guild_id=ticket.guild_id,
            actor_id=actor_id,
            action="ticket_transfer",
            target_id=ticket.id,
            metadata={"new_owner_id": new_owner.id},
        )

    async def add_ticket_user(self, ticket: TicketRecord, actor_id: int, user_id: int) -> None:
        await self.deps.participant_repo.add(ticket.id, user_id, actor_id)
        await self.deps.event_repo.log(
            ticket_id=ticket.id,
            guild_id=ticket.guild_id,
            actor_id=actor_id,
            event_type="add_user",
            payload={"user_id": user_id},
        )
        await self.deps.audit_repo.log(
            guild_id=ticket.guild_id,
            actor_id=actor_id,
            action="ticket_add_user",
            target_id=ticket.id,
            metadata={"user_id": user_id},
        )

    async def remove_ticket_user(self, ticket: TicketRecord, actor_id: int, user_id: int) -> None:
        await self.deps.participant_repo.remove(ticket.id, user_id)
        await self.deps.event_repo.log(
            ticket_id=ticket.id,
            guild_id=ticket.guild_id,
            actor_id=actor_id,
            event_type="remove_user",
            payload={"user_id": user_id},
        )
        await self.deps.audit_repo.log(
            guild_id=ticket.guild_id,
            actor_id=actor_id,
            action="ticket_remove_user",
            target_id=ticket.id,
            metadata={"user_id": user_id},
        )

    async def set_priority(self, ticket: TicketRecord, actor_id: int, priority: str) -> None:
        if priority not in PRIORITY_LEVELS:
            raise ValidationError(f"Invalid priority value. Use: {', '.join(PRIORITY_LEVELS)}")
        await self.deps.ticket_repo.set_priority(ticket.id, priority)
        await self.deps.event_repo.log(
            ticket_id=ticket.id,
            guild_id=ticket.guild_id,
            actor_id=actor_id,
            event_type="priority",
            payload={"priority": priority},
        )
        await self.deps.audit_repo.log(
            guild_id=ticket.guild_id,
            actor_id=actor_id,
            action="ticket_priority",
            target_id=ticket.id,
            metadata={"priority": priority},
        )

    async def set_tags(self, ticket: TicketRecord, actor_id: int, tags: list[str]) -> None:
        clean_tags = sorted({tag.strip().lower() for tag in tags if tag.strip()})
        await self.deps.ticket_repo.set_tags(ticket.id, clean_tags)
        await self.deps.event_repo.log(
            ticket_id=ticket.id,
            guild_id=ticket.guild_id,
            actor_id=actor_id,
            event_type="tags",
            payload={"tags": clean_tags},
        )
        await self.deps.audit_repo.log(
            guild_id=ticket.guild_id,
            actor_id=actor_id,
            action="ticket_tags",
            target_id=ticket.id,
            metadata={"tags": clean_tags},
        )

    async def add_internal_note(self, ticket: TicketRecord, actor_id: int, note: str) -> None:
        if not note.strip():
            raise ValidationError("Internal note cannot be empty.")
        await self.deps.ticket_repo.append_internal_note(ticket.id, actor_id, note.strip())
        await self.deps.event_repo.log(
            ticket_id=ticket.id,
            guild_id=ticket.guild_id,
            actor_id=actor_id,
            event_type="note",
            payload={"note": note.strip()},
        )
        await self.deps.audit_repo.log(
            guild_id=ticket.guild_id,
            actor_id=actor_id,
            action="ticket_note",
            target_id=ticket.id,
        )

    async def set_department(self, ticket: TicketRecord, actor_id: int, department: str) -> None:
        await self.deps.ticket_repo.set_department(ticket.id, department=department)
        await self.deps.event_repo.log(
            ticket_id=ticket.id,
            guild_id=ticket.guild_id,
            actor_id=actor_id,
            event_type="department",
            payload={"department": department},
        )

    async def escalate(self, ticket: TicketRecord, actor_id: int, level: int) -> None:
        if level < 0 or level > 10:
            raise ValidationError("Escalation level must be between 0 and 10.")
        await self.deps.ticket_repo.set_escalation_level(ticket.id, level=level)
        await self.deps.event_repo.log(
            ticket_id=ticket.id,
            guild_id=ticket.guild_id,
            actor_id=actor_id,
            event_type="escalate",
            payload={"level": level},
        )

    async def record_feedback(
        self, ticket: TicketRecord, user_id: int, stars: int, feedback: str | None = None
    ) -> None:
        if stars < 1 or stars > 5:
            raise ValidationError("Star rating must be between 1 and 5.")
        await self.deps.ticket_repo.submit_feedback(
            ticket_id=ticket.id,
            stars=stars,
            feedback=feedback,
            user_id=user_id,
            guild_id=ticket.guild_id,
        )
        await self.deps.event_repo.log(
            ticket_id=ticket.id,
            guild_id=ticket.guild_id,
            actor_id=user_id,
            event_type="feedback",
            payload={"stars": stars, "feedback": feedback},
        )

    async def blacklist_user(
        self,
        guild_id: int,
        actor_id: int,
        user_id: int,
        reason: str,
        until_iso: str | None = None,
    ) -> None:
        await self.deps.blacklist_repo.add(
            guild_id=guild_id,
            user_id=user_id,
            reason=reason.strip() or "No reason provided",
            created_by_id=actor_id,
            until_at=until_iso,
        )
        await self.deps.audit_repo.log(
            guild_id=guild_id,
            actor_id=actor_id,
            action="blacklist_add",
            target_id=str(user_id),
            metadata={"reason": reason, "until": until_iso},
        )

    async def unblacklist_user(self, guild_id: int, actor_id: int, user_id: int) -> None:
        await self.deps.blacklist_repo.remove(guild_id=guild_id, user_id=user_id)
        await self.deps.audit_repo.log(
            guild_id=guild_id,
            actor_id=actor_id,
            action="blacklist_remove",
            target_id=str(user_id),
        )

    async def register_staff_message(self, ticket: TicketRecord, member: discord.Member) -> None:
        if member.bot:
            return
        await self.deps.staff_repo.add_message(ticket.guild_id, member.id)
        if ticket.first_response_at is None:
            if ticket.created_at:
                try:
                    created_at = discord.utils.parse_time(ticket.created_at)
                    if created_at:
                        delta = utc_now() - created_at
                        await self.deps.staff_repo.add_first_response(
                            ticket.guild_id, member.id, int(delta.total_seconds())
                        )
                except Exception:
                    LOGGER.debug("Failed to parse ticket created_at for first response metrics")
            await self.deps.ticket_repo.record_first_response(ticket.id, member.id)

    async def list_open_tickets(self, guild_id: int, limit: int = 100) -> list[TicketRecord]:
        return await self.deps.ticket_repo.list_open(guild_id=guild_id, limit=limit)

    async def list_recent_tickets(self, guild_id: int, limit: int = 100) -> list[TicketRecord]:
        return await self.deps.ticket_repo.list_recent(guild_id=guild_id, limit=limit)
