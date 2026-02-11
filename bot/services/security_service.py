from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import aiohttp

from core.config import AppConfig
from database.repositories import AuditRepository, SecurityRepository
from services.cache import CacheBackend
from utils.rate_limit import DistributedRateLimiter

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class SecurityEventResult:
    triggered: bool
    reason: str | None = None
    details: dict[str, Any] | None = None


class SecurityService:
    def __init__(
        self,
        config: AppConfig,
        cache: CacheBackend,
        security_repo: SecurityRepository,
        audit_repo: AuditRepository,
    ) -> None:
        self.config = config
        self.cache = cache
        self.security_repo = security_repo
        self.audit_repo = audit_repo
        self.rate_limiter = DistributedRateLimiter(cache)

    async def check_member_join_rate(self, guild_id: int) -> SecurityEventResult:
        key = f"security:joins:{guild_id}"
        result = await self.rate_limiter.hit(
            key=key,
            limit=self.config.security.anti_raid_join_threshold,
            window_seconds=self.config.security.anti_raid_window_seconds,
        )
        if result.allowed:
            return SecurityEventResult(triggered=False)
        payload = {
            "count": result.current,
            "limit": result.limit,
            "window_seconds": self.config.security.anti_raid_window_seconds,
        }
        await self.security_repo.log(guild_id, "anti_raid_triggered", "high", payload)
        return SecurityEventResult(triggered=True, reason="Anti-raid threshold exceeded", details=payload)

    async def check_user_message_spam(self, guild_id: int, user_id: int) -> SecurityEventResult:
        key = f"security:spam:{guild_id}:{user_id}"
        result = await self.rate_limiter.hit(
            key=key,
            limit=self.config.security.anti_spam_messages_per_10s,
            window_seconds=10,
        )
        if result.allowed:
            return SecurityEventResult(triggered=False)
        payload = {
            "count": result.current,
            "limit": result.limit,
            "window_seconds": 10,
            "user_id": user_id,
        }
        await self.security_repo.log(guild_id, "message_spam_detected", "medium", payload)
        return SecurityEventResult(triggered=True, reason="Message spam threshold exceeded", details=payload)

    async def send_webhook_log(self, title: str, payload: dict[str, Any]) -> None:
        if not self.config.webhook_log.enabled or not self.config.webhook_log.url:
            return
        try:
            async with aiohttp.ClientSession() as session:
                await session.post(
                    self.config.webhook_log.url,
                    json={
                        "content": None,
                        "embeds": [
                            {
                                "title": title,
                                "description": f"```json\n{json.dumps(payload, indent=2)[:3500]}\n```",
                                "timestamp": datetime.now(UTC).isoformat(),
                            }
                        ],
                    },
                    timeout=10,
                )
        except Exception:
            LOGGER.exception("Failed to send webhook security log")

    async def audit_action(
        self,
        guild_id: int,
        actor_id: int,
        action: str,
        target_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await self.audit_repo.log(guild_id, actor_id, action, target_id, metadata)

    async def ttl_ban_until(self, hours: int) -> str:
        return (datetime.now(UTC) + timedelta(hours=hours)).isoformat()
