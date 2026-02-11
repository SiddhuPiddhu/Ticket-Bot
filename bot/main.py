from __future__ import annotations

import asyncio
from pathlib import Path

import uvicorn

from core.api import create_api_app
from core.bot import TicketBot
from core.config import AppConfig, load_config
from core.logging import configure_logging


async def _run_bot(config: AppConfig) -> None:
    bot = TicketBot(config=config)
    async with bot:
        api_task: asyncio.Task[None] | None = None
        if config.fastapi.enabled:
            api = create_api_app(bot)
            server = uvicorn.Server(
                uvicorn.Config(
                    app=api,
                    host=config.fastapi.host,
                    port=config.fastapi.port,
                    log_level=config.logging.level.lower(),
                )
            )
            api_task = asyncio.create_task(server.serve())
        try:
            await bot.start(config.discord.token)
        finally:
            if api_task:
                api_task.cancel()


def main() -> None:
    root = Path(__file__).resolve().parent
    config = load_config(root / "config" / "config.yaml")
    configure_logging(config.logging)
    asyncio.run(_run_bot(config))


if __name__ == "__main__":
    main()
