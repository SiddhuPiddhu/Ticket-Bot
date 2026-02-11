from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.config import MetricsConfig
from database.repositories import AnalyticsRepository, StaffStatsRepository, TicketRepository

try:
    import matplotlib.pyplot as plt
except ImportError:  # pragma: no cover - optional graph dependency
    plt = None


@dataclass(slots=True)
class DashboardMetrics:
    total_tickets: int
    open_tickets: int
    closed_tickets: int
    category_counts: list[dict[str, Any]]
    staff_leaderboard: list[dict[str, Any]]


class AnalyticsService:
    def __init__(
        self,
        metrics_config: MetricsConfig,
        analytics_repo: AnalyticsRepository,
        ticket_repo: TicketRepository,
        staff_repo: StaffStatsRepository,
    ) -> None:
        self.metrics_config = metrics_config
        self.analytics_repo = analytics_repo
        self.ticket_repo = ticket_repo
        self.staff_repo = staff_repo
        self.export_dir = Path(metrics_config.export_directory)
        self.export_dir.mkdir(parents=True, exist_ok=True)

    async def build_dashboard(self, guild_id: int) -> DashboardMetrics:
        recent = await self.ticket_repo.list_recent(guild_id, limit=10_000)
        total = len(recent)
        open_count = len([item for item in recent if item.status in {"open", "pending", "locked"}])
        closed_count = len([item for item in recent if item.status == "closed"])
        category_counts = await self.analytics_repo.ticket_category_counts(guild_id)
        leaderboard = await self.staff_repo.leaderboard(
            guild_id=guild_id, limit=self.metrics_config.leaderboard_size
        )
        return DashboardMetrics(
            total_tickets=total,
            open_tickets=open_count,
            closed_tickets=closed_count,
            category_counts=category_counts,
            staff_leaderboard=leaderboard,
        )

    async def export_tickets_csv(self, guild_id: int) -> Path:
        rows = await self.ticket_repo.list_recent(guild_id, limit=10_000)
        output = self.export_dir / f"tickets_{guild_id}.csv"
        with output.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "ticket_id",
                    "number",
                    "status",
                    "priority",
                    "category",
                    "opener_id",
                    "claimed_by_id",
                    "created_at",
                    "closed_at",
                    "feedback_stars",
                ]
            )
            for row in rows:
                writer.writerow(
                    [
                        row.id,
                        row.ticket_number,
                        row.status,
                        row.priority,
                        row.category_key,
                        row.opener_id,
                        row.claimed_by_id,
                        row.created_at,
                        row.closed_at,
                        row.feedback_stars,
                    ]
                )
        return output

    async def generate_graph(self, guild_id: int) -> Path | None:
        if not self.metrics_config.enable_graphs or plt is None:
            return None
        points = await self.analytics_repo.daily_ticket_counts(guild_id, days=30)
        if not points:
            return None
        days = [str(item["day"]) for item in points]
        counts = [int(item["count"]) for item in points]

        output = self.export_dir / f"ticket_volume_{guild_id}.png"
        plt.figure(figsize=(12, 5))
        plt.plot(days, counts, marker="o", linewidth=2)
        plt.xticks(rotation=45, ha="right")
        plt.ylabel("Ticket Count")
        plt.title("Ticket Volume (Last 30 Days)")
        plt.tight_layout()
        plt.savefig(output)
        plt.close()
        return output
