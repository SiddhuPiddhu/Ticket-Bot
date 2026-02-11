from __future__ import annotations

import html
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import discord

from core.config import TranscriptConfig


@dataclass(slots=True)
class TranscriptArtifacts:
    html_path: Path | None
    txt_path: Path | None


class TranscriptService:
    def __init__(self, config: TranscriptConfig) -> None:
        self.config = config
        self.base_dir = Path(config.storage_directory)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def generate(
        self, channel: discord.TextChannel, ticket_id: str, limit: int | None = None
    ) -> TranscriptArtifacts:
        guild_dir = self.base_dir / str(channel.guild.id) / ticket_id
        guild_dir.mkdir(parents=True, exist_ok=True)

        messages: list[discord.Message] = []
        async for message in channel.history(limit=limit, oldest_first=True):
            messages.append(message)

        html_path: Path | None = None
        txt_path: Path | None = None

        if self.config.html_enabled:
            html_path = guild_dir / f"{channel.name}.html"
            html_path.write_text(self._build_html(channel, messages), encoding="utf-8")

        if self.config.txt_enabled:
            txt_path = guild_dir / f"{channel.name}.txt"
            txt_path.write_text(self._build_text(messages), encoding="utf-8")

        return TranscriptArtifacts(html_path=html_path, txt_path=txt_path)

    @staticmethod
    def _build_text(messages: Iterable[discord.Message]) -> str:
        lines: list[str] = []
        for msg in messages:
            author = f"{msg.author} ({msg.author.id})"
            created = msg.created_at.isoformat()
            content = msg.content or ""
            lines.append(f"[{created}] {author}: {content}")
            for attach in msg.attachments:
                lines.append(f"  attachment: {attach.url}")
        return "\n".join(lines)

    @staticmethod
    def _build_html(channel: discord.TextChannel, messages: Iterable[discord.Message]) -> str:
        rows: list[str] = []
        for msg in messages:
            escaped_content = html.escape(msg.content or "")
            attachment_html = ""
            if msg.attachments:
                links = "".join(
                    f'<li><a href="{html.escape(a.url)}">{html.escape(a.filename)}</a></li>'
                    for a in msg.attachments
                )
                attachment_html = f"<ul>{links}</ul>"
            rows.append(
                "<div class='msg'>"
                f"<div class='meta'>{html.escape(str(msg.author))} | {msg.created_at.isoformat()}</div>"
                f"<div class='content'>{escaped_content}</div>"
                f"{attachment_html}"
                "</div>"
            )

        return (
            "<!doctype html><html><head><meta charset='utf-8'>"
            "<style>"
            "body{font-family:Arial,sans-serif;background:#f5f7fb;color:#1f2937;padding:16px;}"
            ".msg{background:white;border:1px solid #e5e7eb;border-radius:8px;padding:10px;margin-bottom:8px;}"
            ".meta{font-size:12px;color:#6b7280;margin-bottom:6px;}"
            ".content{white-space:pre-wrap;}"
            "ul{margin-top:8px;}"
            "</style></head><body>"
            f"<h1>Transcript - #{html.escape(channel.name)}</h1>"
            + "".join(rows)
            + "</body></html>"
        )
