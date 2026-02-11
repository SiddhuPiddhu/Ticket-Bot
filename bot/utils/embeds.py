from __future__ import annotations

from datetime import UTC, datetime

import discord


def make_embed(
    title: str,
    description: str,
    color: discord.Color | None = None,
    footer: str | None = None,
) -> discord.Embed:
    resolved_color = color if color is not None else discord.Color.blurple()
    embed = discord.Embed(
        title=title,
        description=description,
        color=resolved_color,
        timestamp=datetime.now(UTC),
    )
    if footer:
        embed.set_footer(text=footer)
    return embed


def staff_embed(title: str, description: str) -> discord.Embed:
    return make_embed(title=title, description=description, color=discord.Color.gold())


def success_embed(message: str) -> discord.Embed:
    return make_embed(title="Success", description=message, color=discord.Color.green())


def error_embed(message: str) -> discord.Embed:
    return make_embed(title="Error", description=message, color=discord.Color.red())
