from __future__ import annotations

TICKET_STATUS_OPEN = "open"
TICKET_STATUS_PENDING = "pending"
TICKET_STATUS_LOCKED = "locked"
TICKET_STATUS_CLOSED = "closed"
TICKET_STATUS_DELETED = "deleted"

PRIORITY_LEVELS = ("low", "normal", "high", "urgent", "critical")

DEFAULT_CATEGORY_QUESTIONS = [
    {
        "id": "subject",
        "label": "Subject",
        "placeholder": "Summarize your request",
        "style": "short",
        "required": True,
        "max_length": 100,
    },
    {
        "id": "details",
        "label": "Details",
        "placeholder": "Provide detailed context",
        "style": "long",
        "required": True,
        "max_length": 1000,
    },
]

AUDIT_ACTIONS = {
    "ticket_create",
    "ticket_close",
    "ticket_reopen",
    "ticket_claim",
    "ticket_unclaim",
    "ticket_lock",
    "ticket_unlock",
    "ticket_rename",
    "ticket_transfer",
    "ticket_add_user",
    "ticket_remove_user",
    "ticket_priority",
    "ticket_tags",
    "ticket_note",
    "ticket_delete",
    "config_update",
    "blacklist_add",
    "blacklist_remove",
}
