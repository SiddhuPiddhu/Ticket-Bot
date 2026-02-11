from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class TicketCategory:
    id: str
    guild_id: int
    key: str
    display_name: str
    description: str
    channel_category_id: int | None
    support_role_ids: list[int] = field(default_factory=list)
    modal_questions: list[dict[str, Any]] = field(default_factory=list)
    template: dict[str, Any] = field(default_factory=dict)
    priority_default: str = "normal"
    tags_default: list[str] = field(default_factory=list)
    sla_minutes: int = 120
    is_enabled: bool = True


@dataclass(slots=True)
class TicketPanel:
    id: str
    panel_id: str
    guild_id: int
    channel_id: int
    message_id: int | None
    title: str
    description: str
    button_label: str
    button_emoji: str
    button_style: str
    category_map: dict[str, int] = field(default_factory=dict)
    support_role_ids: list[int] = field(default_factory=list)
    log_channel_id: int | None = None
    transcript_channel_id: int | None = None
    is_enabled: bool = True


@dataclass(slots=True)
class TicketRecord:
    id: str
    ticket_number: int
    guild_id: int
    channel_id: int
    opener_id: int
    opener_display: str
    panel_id: str | None
    category_key: str
    category_channel_id: int | None
    status: str
    priority: str
    tags: list[str] = field(default_factory=list)
    form_answers: dict[str, Any] = field(default_factory=dict)
    internal_notes: list[dict[str, Any]] = field(default_factory=list)
    claimed_by_id: int | None = None
    claimed_at: str | None = None
    first_response_at: str | None = None
    first_response_by_id: int | None = None
    response_due_at: str | None = None
    close_reason: str | None = None
    closed_by_id: int | None = None
    closed_at: str | None = None
    reopened_count: int = 0
    is_locked: bool = False
    is_anonymous: bool = False
    transcript_html_path: str | None = None
    transcript_txt_path: str | None = None
    soft_deleted: bool = False
    hard_deleted: bool = False
    escalation_level: int = 0
    department: str | None = None
    feedback_stars: int | None = None
    feedback_text: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
