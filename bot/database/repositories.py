from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from database.base import Database
from database.models import TicketCategory, TicketPanel, TicketRecord


def _json_load(value: str | None, default: Any) -> Any:
    if value is None:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class GuildRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def ensure_guild(self, guild_id: int) -> None:
        await self.db.execute(
            """
            INSERT INTO guild_settings(guild_id)
            VALUES (?)
            ON CONFLICT(guild_id) DO NOTHING;
            """,
            [guild_id],
        )

    async def next_ticket_number(self, guild_id: int) -> int:
        await self.ensure_guild(guild_id)
        row = await self.db.fetchone(
            "SELECT ticket_counter FROM guild_settings WHERE guild_id = ?;",
            [guild_id],
        )
        current = int(row["ticket_counter"]) if row else 0
        nxt = current + 1
        await self.db.execute(
            """
            UPDATE guild_settings
            SET ticket_counter = ?, updated_at = CURRENT_TIMESTAMP
            WHERE guild_id = ?;
            """,
            [nxt, guild_id],
        )
        return nxt

    async def set_channels(
        self, guild_id: int, transcript_channel_id: int | None, log_channel_id: int | None
    ) -> None:
        await self.ensure_guild(guild_id)
        await self.db.execute(
            """
            UPDATE guild_settings
            SET transcript_channel_id = ?, log_channel_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE guild_id = ?;
            """,
            [transcript_channel_id, log_channel_id, guild_id],
        )


class CategoryRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def upsert(self, category: TicketCategory) -> None:
        await self.db.execute(
            """
            INSERT INTO ticket_categories (
                id, guild_id, key, display_name, description, channel_category_id,
                support_role_ids_json, modal_questions_json, template_json, priority_default,
                tags_default_json, sla_minutes, is_enabled, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(guild_id, key) DO UPDATE SET
                display_name = excluded.display_name,
                description = excluded.description,
                channel_category_id = excluded.channel_category_id,
                support_role_ids_json = excluded.support_role_ids_json,
                modal_questions_json = excluded.modal_questions_json,
                template_json = excluded.template_json,
                priority_default = excluded.priority_default,
                tags_default_json = excluded.tags_default_json,
                sla_minutes = excluded.sla_minutes,
                is_enabled = excluded.is_enabled,
                updated_at = CURRENT_TIMESTAMP;
            """,
            [
                category.id,
                category.guild_id,
                category.key,
                category.display_name,
                category.description,
                category.channel_category_id,
                _json_dump(category.support_role_ids),
                _json_dump(category.modal_questions),
                _json_dump(category.template),
                category.priority_default,
                _json_dump(category.tags_default),
                category.sla_minutes,
                category.is_enabled,
            ],
        )

    async def get(self, guild_id: int, key: str) -> TicketCategory | None:
        row = await self.db.fetchone(
            """
            SELECT * FROM ticket_categories
            WHERE guild_id = ? AND key = ?;
            """,
            [guild_id, key],
        )
        if not row:
            return None
        return TicketCategory(
            id=row["id"],
            guild_id=row["guild_id"],
            key=row["key"],
            display_name=row["display_name"],
            description=row["description"],
            channel_category_id=row["channel_category_id"],
            support_role_ids=[int(x) for x in _json_load(row["support_role_ids_json"], [])],
            modal_questions=list(_json_load(row["modal_questions_json"], [])),
            template=dict(_json_load(row["template_json"], {})),
            priority_default=row["priority_default"],
            tags_default=list(_json_load(row["tags_default_json"], [])),
            sla_minutes=int(row["sla_minutes"]),
            is_enabled=bool(row["is_enabled"]),
        )

    async def list_by_guild(self, guild_id: int) -> list[TicketCategory]:
        rows = await self.db.fetchall(
            """
            SELECT * FROM ticket_categories
            WHERE guild_id = ?
            ORDER BY key ASC;
            """,
            [guild_id],
        )
        result: list[TicketCategory] = []
        for row in rows:
            result.append(
                TicketCategory(
                    id=row["id"],
                    guild_id=row["guild_id"],
                    key=row["key"],
                    display_name=row["display_name"],
                    description=row["description"],
                    channel_category_id=row["channel_category_id"],
                    support_role_ids=[int(x) for x in _json_load(row["support_role_ids_json"], [])],
                    modal_questions=list(_json_load(row["modal_questions_json"], [])),
                    template=dict(_json_load(row["template_json"], {})),
                    priority_default=row["priority_default"],
                    tags_default=list(_json_load(row["tags_default_json"], [])),
                    sla_minutes=int(row["sla_minutes"]),
                    is_enabled=bool(row["is_enabled"]),
                )
            )
        return result


class PanelRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def upsert(self, panel: TicketPanel, created_by_id: int) -> None:
        await self.db.execute(
            """
            INSERT INTO ticket_panels(
                id, panel_id, guild_id, channel_id, message_id, title, description,
                button_label, button_emoji, button_style, category_map_json,
                support_role_ids_json, log_channel_id, transcript_channel_id,
                is_enabled, created_by_id, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(panel_id) DO UPDATE SET
                channel_id = excluded.channel_id,
                message_id = excluded.message_id,
                title = excluded.title,
                description = excluded.description,
                button_label = excluded.button_label,
                button_emoji = excluded.button_emoji,
                button_style = excluded.button_style,
                category_map_json = excluded.category_map_json,
                support_role_ids_json = excluded.support_role_ids_json,
                log_channel_id = excluded.log_channel_id,
                transcript_channel_id = excluded.transcript_channel_id,
                is_enabled = excluded.is_enabled,
                updated_at = CURRENT_TIMESTAMP;
            """,
            [
                panel.id,
                panel.panel_id,
                panel.guild_id,
                panel.channel_id,
                panel.message_id,
                panel.title,
                panel.description,
                panel.button_label,
                panel.button_emoji,
                panel.button_style,
                _json_dump(panel.category_map),
                _json_dump(panel.support_role_ids),
                panel.log_channel_id,
                panel.transcript_channel_id,
                panel.is_enabled,
                created_by_id,
            ],
        )

    async def update_message_id(self, panel_id: str, message_id: int) -> None:
        await self.db.execute(
            """
            UPDATE ticket_panels
            SET message_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE panel_id = ?;
            """,
            [message_id, panel_id],
        )

    async def get_by_panel_id(self, panel_id: str) -> TicketPanel | None:
        row = await self.db.fetchone(
            "SELECT * FROM ticket_panels WHERE panel_id = ?;",
            [panel_id],
        )
        if not row:
            return None
        return self._row_to_panel(row)

    async def get_by_message(self, guild_id: int, message_id: int) -> TicketPanel | None:
        row = await self.db.fetchone(
            """
            SELECT * FROM ticket_panels
            WHERE guild_id = ? AND message_id = ?;
            """,
            [guild_id, message_id],
        )
        if not row:
            return None
        return self._row_to_panel(row)

    async def list_by_guild(self, guild_id: int) -> list[TicketPanel]:
        rows = await self.db.fetchall(
            """
            SELECT * FROM ticket_panels
            WHERE guild_id = ?
            ORDER BY created_at DESC;
            """,
            [guild_id],
        )
        return [self._row_to_panel(row) for row in rows]

    def _row_to_panel(self, row: dict[str, Any]) -> TicketPanel:
        return TicketPanel(
            id=row["id"],
            panel_id=row["panel_id"],
            guild_id=row["guild_id"],
            channel_id=row["channel_id"],
            message_id=row["message_id"],
            title=row["title"],
            description=row["description"],
            button_label=row["button_label"],
            button_emoji=row["button_emoji"],
            button_style=row["button_style"],
            category_map={
                str(key): int(value)
                for key, value in dict(_json_load(row["category_map_json"], {})).items()
            },
            support_role_ids=[int(x) for x in _json_load(row["support_role_ids_json"], [])],
            log_channel_id=row["log_channel_id"],
            transcript_channel_id=row["transcript_channel_id"],
            is_enabled=bool(row["is_enabled"]),
        )


class TicketRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def create(self, ticket: TicketRecord) -> None:
        await self.db.execute(
            """
            INSERT INTO tickets(
                id, ticket_number, guild_id, channel_id, opener_id, opener_display,
                panel_id, category_key, category_channel_id, status, priority,
                tags_json, form_answers_json, internal_notes_json, claimed_by_id, claimed_at,
                first_response_at, first_response_by_id, response_due_at, close_reason,
                closed_by_id, closed_at, reopened_count, is_locked, is_anonymous,
                transcript_html_path, transcript_txt_path, soft_deleted, hard_deleted,
                escalation_level, department, feedback_stars, feedback_text
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?
            );
            """,
            [
                ticket.id,
                ticket.ticket_number,
                ticket.guild_id,
                ticket.channel_id,
                ticket.opener_id,
                ticket.opener_display,
                ticket.panel_id,
                ticket.category_key,
                ticket.category_channel_id,
                ticket.status,
                ticket.priority,
                _json_dump(ticket.tags),
                _json_dump(ticket.form_answers),
                _json_dump(ticket.internal_notes),
                ticket.claimed_by_id,
                ticket.claimed_at,
                ticket.first_response_at,
                ticket.first_response_by_id,
                ticket.response_due_at,
                ticket.close_reason,
                ticket.closed_by_id,
                ticket.closed_at,
                ticket.reopened_count,
                ticket.is_locked,
                ticket.is_anonymous,
                ticket.transcript_html_path,
                ticket.transcript_txt_path,
                ticket.soft_deleted,
                ticket.hard_deleted,
                ticket.escalation_level,
                ticket.department,
                ticket.feedback_stars,
                ticket.feedback_text,
            ],
        )

    async def get_by_channel(self, guild_id: int, channel_id: int) -> TicketRecord | None:
        row = await self.db.fetchone(
            "SELECT * FROM tickets WHERE guild_id = ? AND channel_id = ?;",
            [guild_id, channel_id],
        )
        if not row:
            return None
        return self._row_to_ticket(row)

    async def get_by_id(self, ticket_id: str) -> TicketRecord | None:
        row = await self.db.fetchone("SELECT * FROM tickets WHERE id = ?;", [ticket_id])
        if not row:
            return None
        return self._row_to_ticket(row)

    async def list_open_by_user(self, guild_id: int, opener_id: int) -> list[TicketRecord]:
        rows = await self.db.fetchall(
            """
            SELECT * FROM tickets
            WHERE guild_id = ? AND opener_id = ? AND status IN ('open', 'pending')
            ORDER BY created_at DESC;
            """,
            [guild_id, opener_id],
        )
        return [self._row_to_ticket(row) for row in rows]

    async def list_open(self, guild_id: int, limit: int = 100) -> list[TicketRecord]:
        rows = await self.db.fetchall(
            """
            SELECT * FROM tickets
            WHERE guild_id = ? AND status IN ('open', 'pending', 'locked')
            ORDER BY created_at DESC
            LIMIT ?;
            """,
            [guild_id, limit],
        )
        return [self._row_to_ticket(row) for row in rows]

    async def list_recent(self, guild_id: int, limit: int = 100) -> list[TicketRecord]:
        rows = await self.db.fetchall(
            """
            SELECT * FROM tickets
            WHERE guild_id = ?
            ORDER BY created_at DESC
            LIMIT ?;
            """,
            [guild_id, limit],
        )
        return [self._row_to_ticket(row) for row in rows]

    async def set_status(
        self,
        ticket_id: str,
        status: str,
        close_reason: str | None = None,
        closed_by_id: int | None = None,
    ) -> None:
        if status == "closed":
            await self.db.execute(
                """
                UPDATE tickets
                SET status = ?, close_reason = ?, closed_by_id = ?, closed_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?;
                """,
                [status, close_reason, closed_by_id, ticket_id],
            )
            return
        await self.db.execute(
            """
            UPDATE tickets
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?;
            """,
            [status, ticket_id],
        )

    async def set_locked(self, ticket_id: str, is_locked: bool) -> None:
        await self.db.execute(
            """
            UPDATE tickets
            SET is_locked = ?, status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?;
            """,
            [is_locked, "locked" if is_locked else "open", ticket_id],
        )

    async def set_claimed(self, ticket_id: str, staff_id: int | None) -> None:
        await self.db.execute(
            """
            UPDATE tickets
            SET claimed_by_id = ?, claimed_at = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?;
            """,
            [staff_id, _now_iso() if staff_id else None, ticket_id],
        )

    async def set_priority(self, ticket_id: str, priority: str) -> None:
        await self.db.execute(
            """
            UPDATE tickets
            SET priority = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?;
            """,
            [priority, ticket_id],
        )

    async def set_tags(self, ticket_id: str, tags: list[str]) -> None:
        await self.db.execute(
            """
            UPDATE tickets
            SET tags_json = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?;
            """,
            [_json_dump(tags), ticket_id],
        )

    async def append_internal_note(self, ticket_id: str, author_id: int, note: str) -> None:
        row = await self.db.fetchone("SELECT internal_notes_json FROM tickets WHERE id = ?;", [ticket_id])
        if not row:
            return
        notes = list(_json_load(row["internal_notes_json"], []))
        notes.append({"author_id": author_id, "note": note, "ts": _now_iso()})
        await self.db.execute(
            """
            UPDATE tickets
            SET internal_notes_json = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?;
            """,
            [_json_dump(notes), ticket_id],
        )

    async def transfer_owner(self, ticket_id: str, new_owner_id: int, new_display: str) -> None:
        await self.db.execute(
            """
            UPDATE tickets
            SET opener_id = ?, opener_display = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?;
            """,
            [new_owner_id, new_display, ticket_id],
        )

    async def update_channel(self, ticket_id: str, new_channel_id: int) -> None:
        await self.db.execute(
            """
            UPDATE tickets
            SET channel_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?;
            """,
            [new_channel_id, ticket_id],
        )

    async def set_transcripts(self, ticket_id: str, html_path: str | None, txt_path: str | None) -> None:
        await self.db.execute(
            """
            UPDATE tickets
            SET transcript_html_path = ?, transcript_txt_path = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?;
            """,
            [html_path, txt_path, ticket_id],
        )

    async def increment_reopened(self, ticket_id: str) -> None:
        await self.db.execute(
            """
            UPDATE tickets
            SET reopened_count = reopened_count + 1, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?;
            """,
            [ticket_id],
        )

    async def mark_soft_deleted(self, ticket_id: str) -> None:
        await self.db.execute(
            """
            UPDATE tickets
            SET soft_deleted = TRUE, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?;
            """,
            [ticket_id],
        )

    async def mark_hard_deleted(self, ticket_id: str) -> None:
        await self.db.execute(
            """
            UPDATE tickets
            SET hard_deleted = TRUE, status = 'deleted', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?;
            """,
            [ticket_id],
        )

    async def record_first_response(self, ticket_id: str, staff_id: int) -> None:
        await self.db.execute(
            """
            UPDATE tickets
            SET first_response_at = COALESCE(first_response_at, CURRENT_TIMESTAMP),
                first_response_by_id = COALESCE(first_response_by_id, ?),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?;
            """,
            [staff_id, ticket_id],
        )

    async def set_department(self, ticket_id: str, department: str) -> None:
        await self.db.execute(
            """
            UPDATE tickets
            SET department = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?;
            """,
            [department, ticket_id],
        )

    async def set_escalation_level(self, ticket_id: str, level: int) -> None:
        await self.db.execute(
            """
            UPDATE tickets
            SET escalation_level = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?;
            """,
            [level, ticket_id],
        )

    async def submit_feedback(
        self, ticket_id: str, stars: int, feedback: str | None, user_id: int, guild_id: int
    ) -> None:
        rating_id = str(uuid4())
        await self.db.execute(
            """
            INSERT INTO ticket_ratings(id, ticket_id, guild_id, user_id, stars, feedback)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticket_id) DO UPDATE SET stars = excluded.stars, feedback = excluded.feedback;
            """,
            [rating_id, ticket_id, guild_id, user_id, stars, feedback],
        )
        await self.db.execute(
            """
            UPDATE tickets
            SET feedback_stars = ?, feedback_text = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?;
            """,
            [stars, feedback, ticket_id],
        )

    def _row_to_ticket(self, row: dict[str, Any]) -> TicketRecord:
        return TicketRecord(
            id=row["id"],
            ticket_number=int(row["ticket_number"]),
            guild_id=int(row["guild_id"]),
            channel_id=int(row["channel_id"]),
            opener_id=int(row["opener_id"]),
            opener_display=row["opener_display"],
            panel_id=row["panel_id"],
            category_key=row["category_key"],
            category_channel_id=row["category_channel_id"],
            status=row["status"],
            priority=row["priority"],
            tags=list(_json_load(row["tags_json"], [])),
            form_answers=dict(_json_load(row["form_answers_json"], {})),
            internal_notes=list(_json_load(row["internal_notes_json"], [])),
            claimed_by_id=row["claimed_by_id"],
            claimed_at=row["claimed_at"],
            first_response_at=row["first_response_at"],
            first_response_by_id=row["first_response_by_id"],
            response_due_at=row["response_due_at"],
            close_reason=row["close_reason"],
            closed_by_id=row["closed_by_id"],
            closed_at=row["closed_at"],
            reopened_count=int(row["reopened_count"]),
            is_locked=bool(row["is_locked"]),
            is_anonymous=bool(row["is_anonymous"]),
            transcript_html_path=row["transcript_html_path"],
            transcript_txt_path=row["transcript_txt_path"],
            soft_deleted=bool(row["soft_deleted"]),
            hard_deleted=bool(row["hard_deleted"]),
            escalation_level=int(row["escalation_level"]),
            department=row["department"],
            feedback_stars=row["feedback_stars"],
            feedback_text=row["feedback_text"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class ParticipantRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def add(self, ticket_id: str, user_id: int, added_by_id: int) -> None:
        await self.db.execute(
            """
            INSERT INTO ticket_participants(ticket_id, user_id, added_by_id)
            VALUES (?, ?, ?)
            ON CONFLICT(ticket_id, user_id) DO NOTHING;
            """,
            [ticket_id, user_id, added_by_id],
        )

    async def remove(self, ticket_id: str, user_id: int) -> None:
        await self.db.execute(
            "DELETE FROM ticket_participants WHERE ticket_id = ? AND user_id = ?;",
            [ticket_id, user_id],
        )

    async def list_user_ids(self, ticket_id: str) -> list[int]:
        rows = await self.db.fetchall(
            "SELECT user_id FROM ticket_participants WHERE ticket_id = ?;",
            [ticket_id],
        )
        return [int(row["user_id"]) for row in rows]


class EventRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def log(
        self,
        ticket_id: str,
        guild_id: int,
        actor_id: int,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        await self.db.execute(
            """
            INSERT INTO ticket_events(id, ticket_id, guild_id, actor_id, event_type, payload_json)
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            [str(uuid4()), ticket_id, guild_id, actor_id, event_type, _json_dump(payload)],
        )

    async def list_recent(self, ticket_id: str, limit: int = 25) -> list[dict[str, Any]]:
        rows = await self.db.fetchall(
            """
            SELECT * FROM ticket_events
            WHERE ticket_id = ?
            ORDER BY created_at DESC
            LIMIT ?;
            """,
            [ticket_id, limit],
        )
        for row in rows:
            row["payload"] = _json_load(row.get("payload_json"), {})
        return rows


class BlacklistRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def add(
        self, guild_id: int, user_id: int, reason: str, created_by_id: int, until_at: str | None
    ) -> None:
        await self.db.execute(
            """
            INSERT INTO ticket_blacklist(guild_id, user_id, reason, until_at, created_by_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET
                reason = excluded.reason,
                until_at = excluded.until_at,
                created_by_id = excluded.created_by_id,
                created_at = CURRENT_TIMESTAMP;
            """,
            [guild_id, user_id, reason, until_at, created_by_id],
        )

    async def remove(self, guild_id: int, user_id: int) -> None:
        await self.db.execute(
            "DELETE FROM ticket_blacklist WHERE guild_id = ? AND user_id = ?;",
            [guild_id, user_id],
        )

    async def get_active(self, guild_id: int, user_id: int) -> dict[str, Any] | None:
        row = await self.db.fetchone(
            """
            SELECT * FROM ticket_blacklist
            WHERE guild_id = ? AND user_id = ?;
            """,
            [guild_id, user_id],
        )
        if not row:
            return None
        until_at = row.get("until_at")
        if until_at:
            try:
                expiry = datetime.fromisoformat(until_at.replace("Z", "+00:00"))
                if expiry <= datetime.now(UTC):
                    await self.remove(guild_id, user_id)
                    return None
            except ValueError:
                return row
        return row


class StaffStatsRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def _ensure(self, guild_id: int, staff_id: int) -> None:
        await self.db.execute(
            """
            INSERT INTO staff_stats(guild_id, staff_id)
            VALUES (?, ?)
            ON CONFLICT(guild_id, staff_id) DO NOTHING;
            """,
            [guild_id, staff_id],
        )

    async def increment_claimed(self, guild_id: int, staff_id: int) -> None:
        await self._ensure(guild_id, staff_id)
        await self.db.execute(
            """
            UPDATE staff_stats
            SET tickets_claimed = tickets_claimed + 1, last_active_at = CURRENT_TIMESTAMP
            WHERE guild_id = ? AND staff_id = ?;
            """,
            [guild_id, staff_id],
        )

    async def increment_closed(self, guild_id: int, staff_id: int) -> None:
        await self._ensure(guild_id, staff_id)
        await self.db.execute(
            """
            UPDATE staff_stats
            SET tickets_closed = tickets_closed + 1, last_active_at = CURRENT_TIMESTAMP
            WHERE guild_id = ? AND staff_id = ?;
            """,
            [guild_id, staff_id],
        )

    async def add_message(self, guild_id: int, staff_id: int) -> None:
        await self._ensure(guild_id, staff_id)
        await self.db.execute(
            """
            UPDATE staff_stats
            SET total_messages = total_messages + 1, last_active_at = CURRENT_TIMESTAMP
            WHERE guild_id = ? AND staff_id = ?;
            """,
            [guild_id, staff_id],
        )

    async def add_first_response(self, guild_id: int, staff_id: int, response_seconds: int) -> None:
        await self._ensure(guild_id, staff_id)
        await self.db.execute(
            """
            UPDATE staff_stats
            SET total_first_response_seconds = total_first_response_seconds + ?,
                first_response_count = first_response_count + 1,
                last_active_at = CURRENT_TIMESTAMP
            WHERE guild_id = ? AND staff_id = ?;
            """,
            [response_seconds, guild_id, staff_id],
        )

    async def leaderboard(self, guild_id: int, limit: int = 10) -> list[dict[str, Any]]:
        return await self.db.fetchall(
            """
            SELECT
                guild_id, staff_id, tickets_claimed, tickets_closed, total_messages,
                total_first_response_seconds, first_response_count,
                CASE
                    WHEN first_response_count = 0 THEN NULL
                    ELSE (total_first_response_seconds * 1.0 / first_response_count)
                END AS avg_first_response_seconds
            FROM staff_stats
            WHERE guild_id = ?
            ORDER BY tickets_closed DESC, tickets_claimed DESC
            LIMIT ?;
            """,
            [guild_id, limit],
        )


class AuditRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def log(
        self,
        guild_id: int,
        actor_id: int,
        action: str,
        target_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await self.db.execute(
            """
            INSERT INTO audit_logs(id, guild_id, actor_id, action, target_id, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            [str(uuid4()), guild_id, actor_id, action, target_id, _json_dump(metadata or {})],
        )


class SecurityRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def log(self, guild_id: int, event_type: str, severity: str, payload: dict[str, Any]) -> None:
        await self.db.execute(
            """
            INSERT INTO security_events(id, guild_id, event_type, severity, payload_json)
            VALUES (?, ?, ?, ?, ?);
            """,
            [str(uuid4()), guild_id, event_type, severity, _json_dump(payload)],
        )


class AnalyticsRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def ticket_status_counts(self, guild_id: int) -> list[dict[str, Any]]:
        return await self.db.fetchall(
            """
            SELECT status, COUNT(*) as count
            FROM tickets
            WHERE guild_id = ?
            GROUP BY status;
            """,
            [guild_id],
        )

    async def ticket_category_counts(self, guild_id: int) -> list[dict[str, Any]]:
        return await self.db.fetchall(
            """
            SELECT category_key, COUNT(*) as count
            FROM tickets
            WHERE guild_id = ?
            GROUP BY category_key
            ORDER BY count DESC;
            """,
            [guild_id],
        )

    async def daily_ticket_counts(self, guild_id: int, days: int = 30) -> list[dict[str, Any]]:
        if self.db.driver == "sqlite":
            query = """
                SELECT strftime('%Y-%m-%d', created_at) AS day, COUNT(*) AS count
                FROM tickets
                WHERE guild_id = ? AND created_at >= datetime('now', ?)
                GROUP BY day
                ORDER BY day ASC;
            """
            return await self.db.fetchall(query, [guild_id, f"-{days} day"])
        query = """
            SELECT to_char(created_at::date, 'YYYY-MM-DD') AS day, COUNT(*) AS count
            FROM tickets
            WHERE guild_id = ? AND created_at >= NOW() - (? || ' days')::interval
            GROUP BY created_at::date
            ORDER BY created_at::date ASC;
        """
        return await self.db.fetchall(query, [guild_id, days])

    async def response_time_distribution(self, guild_id: int) -> list[dict[str, Any]]:
        if self.db.driver == "sqlite":
            query = """
                SELECT
                    CAST((julianday(first_response_at) - julianday(created_at)) * 86400 AS INTEGER) AS seconds
                FROM tickets
                WHERE guild_id = ? AND first_response_at IS NOT NULL;
            """
            return await self.db.fetchall(query, [guild_id])
        query = """
            SELECT EXTRACT(EPOCH FROM (first_response_at - created_at))::INTEGER AS seconds
            FROM tickets
            WHERE guild_id = ? AND first_response_at IS NOT NULL;
        """
        return await self.db.fetchall(query, [guild_id])
