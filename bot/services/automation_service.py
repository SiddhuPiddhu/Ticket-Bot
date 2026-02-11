from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from database.base import Database
from database.repositories import EventRepository, TicketRepository


@dataclass(slots=True)
class AutomationJob:
    id: str
    ticket_id: str
    guild_id: int
    job_type: str
    run_at: datetime
    payload: dict[str, Any]


class AutomationService:
    def __init__(self, db: Database, ticket_repo: TicketRepository, event_repo: EventRepository) -> None:
        self.db = db
        self.ticket_repo = ticket_repo
        self.event_repo = event_repo

    @staticmethod
    def _db_now() -> datetime:
        # Store/compare UTC as naive datetime for PostgreSQL TIMESTAMP compatibility.
        return datetime.now(UTC).replace(tzinfo=None)

    @staticmethod
    def _as_datetime(value: Any) -> datetime:
        if isinstance(value, datetime):
            if value.tzinfo is not None:
                return value.astimezone(UTC).replace(tzinfo=None)
            return value
        if isinstance(value, str):
            normalized = value.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is not None:
                return parsed.astimezone(UTC).replace(tzinfo=None)
            return parsed
        raise TypeError(f"Unsupported datetime value type: {type(value)!r}")

    async def schedule_auto_close(self, ticket_id: str, guild_id: int, after_minutes: int) -> str:
        job_id = str(uuid4())
        run_at = self._db_now() + timedelta(minutes=after_minutes)
        await self.db.execute(
            """
            INSERT INTO automation_jobs(id, ticket_id, guild_id, job_type, run_at, payload_json, status)
            VALUES (?, ?, ?, 'auto_close', ?, '{}', 'pending');
            """,
            [job_id, ticket_id, guild_id, run_at],
        )
        return job_id

    async def cancel_job(self, job_id: str) -> None:
        await self.db.execute(
            "UPDATE automation_jobs SET status = 'cancelled' WHERE id = ?;",
            [job_id],
        )

    async def due_auto_close_jobs(self) -> list[AutomationJob]:
        now = self._db_now()
        if self.db.driver == "sqlite":
            rows = await self.db.fetchall(
                """
                SELECT * FROM automation_jobs
                WHERE status = 'pending'
                  AND job_type = 'auto_close'
                  AND datetime(run_at) <= datetime(?);
                """,
                [now],
            )
        else:
            rows = await self.db.fetchall(
                """
                SELECT * FROM automation_jobs
                WHERE status = 'pending' AND job_type = 'auto_close' AND run_at <= ?;
                """,
                [now],
            )
        jobs: list[AutomationJob] = []
        for row in rows:
            jobs.append(
                AutomationJob(
                    id=row["id"],
                    ticket_id=row["ticket_id"],
                    guild_id=int(row["guild_id"]),
                    job_type=row["job_type"],
                    run_at=self._as_datetime(row["run_at"]),
                    payload={},
                )
            )
        return jobs

    async def mark_job_done(self, job_id: str) -> None:
        await self.db.execute(
            "UPDATE automation_jobs SET status = 'completed' WHERE id = ?;",
            [job_id],
        )

    async def mark_job_failed(self, job_id: str, reason: str) -> None:
        await self.db.execute(
            """
            UPDATE automation_jobs
            SET status = 'failed', payload_json = ?
            WHERE id = ?;
            """,
            [json.dumps({"error": reason[:200]}, ensure_ascii=True), job_id],
        )
