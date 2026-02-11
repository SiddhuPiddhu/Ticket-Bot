from __future__ import annotations

import logging
from datetime import timedelta

import discord
from discord.ext import commands

from core.bot import TicketBot
from utils.embeds import make_embed, staff_embed, success_embed

LOGGER = logging.getLogger(__name__)


def _is_admin(member: discord.Member) -> bool:
    return member.guild_permissions.administrator


class SecurityCog(commands.Cog):
    def __init__(self, bot: TicketBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        result = await self.bot.security_service.check_member_join_rate(member.guild.id)
        if not result.triggered:
            return

        await self.bot.security_service.send_webhook_log(
            "Anti-Raid Triggered",
            {"guild_id": member.guild.id, "member_id": member.id, **(result.details or {})},
        )
        settings = await self.bot.database.fetchone(
            "SELECT log_channel_id FROM guild_settings WHERE guild_id = ?;",
            [member.guild.id],
        )
        log_channel = member.guild.get_channel(settings["log_channel_id"]) if settings and settings.get("log_channel_id") else None
        if isinstance(log_channel, discord.TextChannel):
            await log_channel.send(
                embed=staff_embed(
                    "Anti-Raid Triggered",
                    (
                        f"Join threshold exceeded. Recent join count: `{result.details.get('count')}`.\n"
                        "Review recent joins and enable verification/lockdown if needed."
                    ),
                )
            )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot:
            return
        if not isinstance(message.author, discord.Member):
            return
        result = await self.bot.security_service.check_user_message_spam(
            guild_id=message.guild.id,
            user_id=message.author.id,
        )
        if not result.triggered:
            return
        try:
            await message.delete()
        except discord.HTTPException:
            pass
        if message.author.guild_permissions.manage_messages:
            return
        try:
            await message.author.timeout(timedelta(minutes=1), reason="Automated anti-spam action")
        except discord.HTTPException:
            LOGGER.warning("Failed to timeout spammer user_id=%s", message.author.id)

    @commands.hybrid_group(name="security", with_app_command=True, description="Security controls.")
    async def security(self, ctx: commands.Context[TicketBot]) -> None:
        if ctx.invoked_subcommand is None:
            await ctx.reply(
                embed=make_embed(
                    "Security Commands",
                    "`/security status`\n"
                    "`/security events`\n"
                    "`/security lockdown`\n"
                    "`/security unlockdown`",
                ),
                mention_author=False,
            )

    @security.command(name="status", description="Show active security thresholds.")
    async def security_status(self, ctx: commands.Context[TicketBot]) -> None:
        if not ctx.guild or not isinstance(ctx.author, discord.Member) or not _is_admin(ctx.author):
            return
        cfg = self.bot.config.security
        embed = make_embed("Security Status", "Current anti-abuse configuration.", color=discord.Color.orange())
        embed.add_field(
            name="Anti-Raid",
            value=f"{cfg.anti_raid_join_threshold} joins / {cfg.anti_raid_window_seconds}s",
            inline=False,
        )
        embed.add_field(
            name="Anti-Spam",
            value=f"{cfg.anti_spam_messages_per_10s} messages / 10s per user",
            inline=False,
        )
        embed.add_field(
            name="Ticket Cooldown",
            value=f"{cfg.ticket_creation_cooldown_seconds}s",
            inline=True,
        )
        embed.add_field(
            name="Ticket Max per Hour",
            value=str(cfg.ticket_creation_max_per_hour),
            inline=True,
        )
        await ctx.reply(embed=embed, mention_author=False)

    @security.command(name="events", description="Show recent security events.")
    async def security_events(self, ctx: commands.Context[TicketBot]) -> None:
        if not ctx.guild or not isinstance(ctx.author, discord.Member) or not _is_admin(ctx.author):
            return
        rows = await self.bot.database.fetchall(
            """
            SELECT event_type, severity, payload_json, created_at
            FROM security_events
            WHERE guild_id = ?
            ORDER BY created_at DESC
            LIMIT 20;
            """,
            [ctx.guild.id],
        )
        if not rows:
            await ctx.reply(embed=success_embed("No security events recorded."), mention_author=False)
            return
        lines = [
            f"`{row['created_at']}` {row['severity'].upper()} `{row['event_type']}` {row['payload_json'][:80]}"
            for row in rows
        ]
        await ctx.reply(embed=make_embed("Recent Security Events", "\n".join(lines)), mention_author=False)

    @security.command(name="lockdown", description="Lock all ticket channels from @everyone send.")
    async def security_lockdown(self, ctx: commands.Context[TicketBot]) -> None:
        if not ctx.guild or not isinstance(ctx.author, discord.Member) or not _is_admin(ctx.author):
            return
        tickets = await self.bot.ticket_service.list_open_tickets(ctx.guild.id, limit=200)
        changed = 0
        for ticket in tickets:
            channel = ctx.guild.get_channel(ticket.channel_id)
            if isinstance(channel, discord.TextChannel):
                await channel.set_permissions(ctx.guild.default_role, send_messages=False)
                changed += 1
        await ctx.reply(embed=staff_embed("Lockdown Enabled", f"Updated {changed} ticket channels."), mention_author=False)

    @security.command(name="unlockdown", description="Re-enable @everyone send in open tickets.")
    async def security_unlockdown(self, ctx: commands.Context[TicketBot]) -> None:
        if not ctx.guild or not isinstance(ctx.author, discord.Member) or not _is_admin(ctx.author):
            return
        tickets = await self.bot.ticket_service.list_open_tickets(ctx.guild.id, limit=200)
        changed = 0
        for ticket in tickets:
            channel = ctx.guild.get_channel(ticket.channel_id)
            opener = ctx.guild.get_member(ticket.opener_id)
            if isinstance(channel, discord.TextChannel) and opener:
                await channel.set_permissions(opener, send_messages=True, view_channel=True)
                changed += 1
        await ctx.reply(embed=success_embed(f"Lockdown removed in {changed} ticket channels."), mention_author=False)


async def setup(bot: TicketBot) -> None:
    await bot.add_cog(SecurityCog(bot))
