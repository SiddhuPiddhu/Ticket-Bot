from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

import discord
from discord import app_commands
from discord.ext import commands

from core.errors import PermissionDenied, ValidationError

F = TypeVar("F", bound=Callable[..., Any])


def staff_only() -> Callable[[F], F]:
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return False
        if interaction.user.guild_permissions.administrator:
            return True
        has_support = any(role.name.lower() in {"support", "moderator", "admin"} for role in interaction.user.roles)
        if has_support:
            return True
        raise PermissionDenied()

    return app_commands.check(predicate)


def guild_admin_only() -> Callable[[F], F]:
    async def predicate(interaction: discord.Interaction) -> bool:
        member = interaction.user
        if not interaction.guild or not isinstance(member, discord.Member):
            return False
        if member.guild_permissions.administrator:
            return True
        raise PermissionDenied()

    return app_commands.check(predicate)


def hybrid_guild_only() -> Callable[[F], F]:
    return commands.guild_only()


def app_rate_limit(limit: int, window_seconds: int) -> Callable[[F], F]:
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild or not interaction.user:
            return False
        cache = getattr(interaction.client, "cache", None)
        if cache is None:
            return True
        key = f"decorator:rl:{interaction.guild.id}:{interaction.user.id}:{interaction.command.qualified_name if interaction.command else 'unknown'}"
        current = await cache.incr(key, ttl=window_seconds)
        if current > limit:
            raise ValidationError(f"Rate limited. Try again in {window_seconds} seconds.")
        return True

    return app_commands.check(predicate)
