from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException

from core.bot import TicketBot


def _auth(x_api_key: str | None, expected: str) -> None:
    if not expected:
        return
    if x_api_key != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


def create_api_app(bot: TicketBot) -> FastAPI:
    app = FastAPI(title="Ticket Bot API", version="1.0.0")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/guilds/{guild_id}/dashboard")
    async def dashboard(guild_id: int, x_api_key: str | None = Header(default=None)) -> dict[str, object]:
        _auth(x_api_key, bot.config.fastapi.jwt_secret)
        data = await bot.analytics_service.build_dashboard(guild_id)
        return {
            "total_tickets": data.total_tickets,
            "open_tickets": data.open_tickets,
            "closed_tickets": data.closed_tickets,
            "category_counts": data.category_counts,
            "staff_leaderboard": data.staff_leaderboard,
        }

    @app.get("/guilds/{guild_id}/tickets/open")
    async def open_tickets(guild_id: int, x_api_key: str | None = Header(default=None)) -> dict[str, object]:
        _auth(x_api_key, bot.config.fastapi.jwt_secret)
        rows = await bot.ticket_service.list_open_tickets(guild_id=guild_id, limit=200)
        return {
            "items": [
                {
                    "id": row.id,
                    "ticket_number": row.ticket_number,
                    "channel_id": row.channel_id,
                    "opener_id": row.opener_id,
                    "status": row.status,
                    "priority": row.priority,
                    "category_key": row.category_key,
                }
                for row in rows
            ]
        }

    return app
