from __future__ import annotations

from datetime import datetime, timezone

import discord


def make_embed(
    title: str,
    description: str,
    color: discord.Color = discord.Color.blurple(),
    footer: str | None = None,
) -> discord.Embed:
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.now(timezone.utc),
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
