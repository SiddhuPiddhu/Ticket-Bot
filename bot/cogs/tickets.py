from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast

import discord
from discord.ext import commands, tasks

from core.bot import TicketBot
from core.errors import TicketNotFound, ValidationError
from database.models import TicketRecord
from utils.embeds import error_embed, make_embed, staff_embed, success_embed
from views.ticket_controls import TicketControlsView
from views.ticket_panel import TicketPanelView

LOGGER = logging.getLogger(__name__)


def _is_staff(member: discord.Member) -> bool:
    if member.guild_permissions.administrator or member.guild_permissions.manage_channels:
        return True
    return any(role.name.lower() in {"support", "staff", "moderator", "admin"} for role in member.roles)


class TicketsCog(commands.Cog):
    def __init__(self, bot: TicketBot) -> None:
        self.bot = bot
        self._persistent_views_registered = False
        self.automation_worker.start()

    def cog_unload(self) -> None:
        self.automation_worker.cancel()

    async def cog_load(self) -> None:
        self.bot.add_view(TicketControlsView(bot=self.bot, ticket_id="*"))
        await self._register_panel_views()

    async def _register_panel_views(self) -> None:
        if self._persistent_views_registered:
            return
        if not self.bot.guilds:
            return
        for guild in self.bot.guilds:
            panels = await self.bot.panel_repo.list_by_guild(guild.id)
            for panel in panels:
                self.bot.add_view(TicketPanelView(self.bot, panel))
        self._persistent_views_registered = True

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        await self._register_panel_views()

    async def _current_ticket(
        self, ctx: commands.Context[TicketBot]
    ) -> tuple[discord.TextChannel, TicketRecord, discord.Member]:
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            raise ValidationError("Guild context is required.")
        channel = ctx.channel
        if not isinstance(channel, discord.TextChannel):
            raise ValidationError("Ticket commands require a text channel.")
        ticket = await self.bot.ticket_repo.get_by_channel(ctx.guild.id, channel.id)
        if not ticket:
            raise TicketNotFound()
        return channel, ticket, ctx.author

    async def _publish_transcript(
        self, channel: discord.TextChannel, ticket: TicketRecord
    ) -> list[discord.File]:
        artifacts = await self.bot.transcript_service.generate(channel=channel, ticket_id=ticket.id)
        files: list[discord.File] = []
        if artifacts.html_path and artifacts.html_path.exists():
            files.append(discord.File(artifacts.html_path))
        if artifacts.txt_path and artifacts.txt_path.exists():
            files.append(discord.File(artifacts.txt_path))

        await self.bot.ticket_repo.set_transcripts(
            ticket_id=ticket.id,
            html_path=str(artifacts.html_path) if artifacts.html_path else None,
            txt_path=str(artifacts.txt_path) if artifacts.txt_path else None,
        )
        return files

    async def _send_transcript_to_log_channel(
        self,
        guild: discord.Guild,
        ticket: TicketRecord,
        files: list[discord.File],
    ) -> None:
        if not files:
            return
        channel_id = None
        panel = await self.bot.panel_repo.get_by_panel_id(ticket.panel_id) if ticket.panel_id else None
        if panel and panel.transcript_channel_id:
            channel_id = panel.transcript_channel_id
        if not channel_id:
            settings = await self.bot.database.fetchone(
                "SELECT transcript_channel_id FROM guild_settings WHERE guild_id = ?;",
                [guild.id],
            )
            if settings:
                channel_id = settings.get("transcript_channel_id")
        log_channel = guild.get_channel(channel_id) if channel_id else None
        if isinstance(log_channel, discord.TextChannel):
            await log_channel.send(
                content=(
                    f"Transcript for ticket `{ticket.id}` (#{ticket.ticket_number}) "
                    f"closed by <@{ticket.closed_by_id}>."
                ),
                files=files,
            )

    @commands.hybrid_group(name="ticket", with_app_command=True, description="Ticket command group.")
    async def ticket(self, ctx: commands.Context[TicketBot]) -> None:
        if ctx.invoked_subcommand is None:
            await ctx.reply(
                embed=make_embed(
                    "Ticket Commands",
                    "`/ticket create <category>` to open\n"
                    "`/ticket close <reason>` to close\n"
                    "`/ticket claim` to claim\n"
                    "`/ticket info` for details",
                ),
                mention_author=False,
            )

    @ticket.command(name="create", description="Create a ticket via command without a panel.")
    async def ticket_create(self, ctx: commands.Context[TicketBot], category: str) -> None:
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            raise ValidationError("Guild context is required.")
        record = await self.bot.ticket_service.create_ticket(
            guild=ctx.guild,
            opener=ctx.author,
            panel=None,
            category_key=category.lower(),
            form_answers={"details": "Created through command."},
            anonymous=False,
        )
        channel = ctx.guild.get_channel(record.channel_id)
        if isinstance(channel, discord.TextChannel):
            await channel.send(
                embed=make_embed(
                    title=f"Ticket #{record.ticket_number}",
                    description=f"Category: `{record.category_key}`",
                    color=discord.Color.blurple(),
                ),
                view=TicketControlsView(bot=self.bot, ticket_id=record.id),
            )
        await ctx.reply(embed=success_embed(f"Ticket created: <#{record.channel_id}>"), mention_author=False)

    @ticket.command(name="claim", description="Claim current ticket.")
    async def ticket_claim(self, ctx: commands.Context[TicketBot]) -> None:
        channel, ticket, member = await self._current_ticket(ctx)
        if not _is_staff(member):
            raise ValidationError("Staff permission required.")
        updated = await self.bot.ticket_service.claim_ticket(ticket, member)
        await channel.send(embed=staff_embed("Ticket Claimed", f"{member.mention} claimed this ticket."))
        await channel.edit(topic=f"ticket|{updated.ticket_number}|claimed:{member.id}")

    @ticket.command(name="unclaim", description="Unclaim current ticket.")
    async def ticket_unclaim(self, ctx: commands.Context[TicketBot]) -> None:
        channel, ticket, member = await self._current_ticket(ctx)
        if not _is_staff(member):
            raise ValidationError("Staff permission required.")
        await self.bot.ticket_service.unclaim_ticket(ticket, member)
        await channel.send(embed=success_embed("Ticket unclaimed."))

    @ticket.command(name="lock", description="Lock current ticket.")
    async def ticket_lock(self, ctx: commands.Context[TicketBot]) -> None:
        channel, ticket, member = await self._current_ticket(ctx)
        if not _is_staff(member):
            raise ValidationError("Staff permission required.")
        await self.bot.ticket_service.lock_ticket(ticket, member.id)
        opener = ctx.guild.get_member(ticket.opener_id) if ctx.guild else None
        if opener:
            await channel.set_permissions(opener, send_messages=False)
        await channel.send(embed=success_embed("Ticket locked."))

    @ticket.command(name="unlock", description="Unlock current ticket.")
    async def ticket_unlock(self, ctx: commands.Context[TicketBot]) -> None:
        channel, ticket, member = await self._current_ticket(ctx)
        if not _is_staff(member):
            raise ValidationError("Staff permission required.")
        await self.bot.ticket_service.unlock_ticket(ticket, member.id)
        opener = ctx.guild.get_member(ticket.opener_id) if ctx.guild else None
        if opener:
            await channel.set_permissions(opener, send_messages=True)
        await channel.send(embed=success_embed("Ticket unlocked."))

    @ticket.command(name="close", description="Close current ticket.")
    async def ticket_close(self, ctx: commands.Context[TicketBot], *, reason: str) -> None:
        channel, ticket, member = await self._current_ticket(ctx)
        if not _is_staff(member):
            raise ValidationError("Staff permission required.")
        await self.bot.ticket_service.close_ticket(ticket=ticket, actor_id=member.id, reason=reason)
        files = await self._publish_transcript(channel, ticket)
        await self._send_transcript_to_log_channel(channel.guild, ticket, files)
        await channel.send(embed=success_embed(f"Ticket closed by {member.mention}. Reason: {reason}"))
        await channel.set_permissions(channel.guild.default_role, send_messages=False)

    @ticket.command(name="reopen", description="Reopen current ticket.")
    async def ticket_reopen(self, ctx: commands.Context[TicketBot]) -> None:
        channel, ticket, member = await self._current_ticket(ctx)
        if not _is_staff(member):
            raise ValidationError("Staff permission required.")
        await self.bot.ticket_service.reopen_ticket(ticket, member.id)
        opener = ctx.guild.get_member(ticket.opener_id) if ctx.guild else None
        if opener:
            await channel.set_permissions(opener, send_messages=True)
        await channel.send(embed=success_embed("Ticket reopened."))

    @ticket.command(name="rename", description="Rename current ticket channel.")
    async def ticket_rename(self, ctx: commands.Context[TicketBot], *, new_name: str) -> None:
        channel, ticket, member = await self._current_ticket(ctx)
        if not _is_staff(member):
            raise ValidationError("Staff permission required.")
        safe_name = self.bot.ticket_service.sanitize_channel_fragment(new_name)
        await channel.edit(name=safe_name)
        await self.bot.ticket_service.rename_ticket(ticket, member.id, channel.id, safe_name)
        await channel.send(embed=success_embed(f"Channel renamed to `{safe_name}`"))

    @ticket.command(name="transfer", description="Transfer ticket ownership.")
    async def ticket_transfer(self, ctx: commands.Context[TicketBot], member: discord.Member) -> None:
        channel, ticket, actor = await self._current_ticket(ctx)
        if not _is_staff(actor):
            raise ValidationError("Staff permission required.")
        await self.bot.ticket_service.transfer_ticket(ticket, actor.id, member)
        await channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True)
        await channel.send(embed=success_embed(f"Ticket ownership transferred to {member.mention}."))

    @ticket.command(name="adduser", description="Add user to ticket.")
    async def ticket_add_user(self, ctx: commands.Context[TicketBot], member: discord.Member) -> None:
        channel, ticket, actor = await self._current_ticket(ctx)
        if not _is_staff(actor):
            raise ValidationError("Staff permission required.")
        await self.bot.ticket_service.add_ticket_user(ticket, actor.id, member.id)
        await channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True)
        await channel.send(embed=success_embed(f"Added {member.mention} to this ticket."))

    @ticket.command(name="removeuser", description="Remove user from ticket.")
    async def ticket_remove_user(self, ctx: commands.Context[TicketBot], member: discord.Member) -> None:
        channel, ticket, actor = await self._current_ticket(ctx)
        if not _is_staff(actor):
            raise ValidationError("Staff permission required.")
        await self.bot.ticket_service.remove_ticket_user(ticket, actor.id, member.id)
        await channel.set_permissions(member, overwrite=None)
        await channel.send(embed=success_embed(f"Removed {member.mention} from this ticket."))

    @ticket.command(name="priority", description="Set ticket priority.")
    async def ticket_priority(self, ctx: commands.Context[TicketBot], level: str) -> None:
        channel, ticket, actor = await self._current_ticket(ctx)
        if not _is_staff(actor):
            raise ValidationError("Staff permission required.")
        await self.bot.ticket_service.set_priority(ticket, actor.id, level.lower())
        await channel.send(embed=success_embed(f"Priority updated to `{level.lower()}`"))

    @ticket.command(name="tags", description="Set ticket tags.")
    async def ticket_tags(self, ctx: commands.Context[TicketBot], *, tags: str) -> None:
        channel, ticket, actor = await self._current_ticket(ctx)
        if not _is_staff(actor):
            raise ValidationError("Staff permission required.")
        parsed = [tag.strip() for tag in tags.split(",") if tag.strip()]
        await self.bot.ticket_service.set_tags(ticket, actor.id, parsed)
        await channel.send(embed=success_embed(f"Tags updated: `{', '.join(parsed)}`"))

    @ticket.command(name="note", description="Add internal note.")
    async def ticket_note(self, ctx: commands.Context[TicketBot], *, note: str) -> None:
        _, ticket, actor = await self._current_ticket(ctx)
        if not _is_staff(actor):
            raise ValidationError("Staff permission required.")
        await self.bot.ticket_service.add_internal_note(ticket, actor.id, note)
        await ctx.reply(embed=staff_embed("Internal Note Added", note), mention_author=False)

    @ticket.command(name="escalate", description="Set escalation level.")
    async def ticket_escalate(self, ctx: commands.Context[TicketBot], level: int) -> None:
        channel, ticket, actor = await self._current_ticket(ctx)
        if not _is_staff(actor):
            raise ValidationError("Staff permission required.")
        await self.bot.ticket_service.escalate(ticket, actor.id, level)
        await channel.send(embed=staff_embed("Escalation Updated", f"Escalation level is now `{level}`."))

    @ticket.command(name="department", description="Set department routing.")
    async def ticket_department(self, ctx: commands.Context[TicketBot], *, department: str) -> None:
        channel, ticket, actor = await self._current_ticket(ctx)
        if not _is_staff(actor):
            raise ValidationError("Staff permission required.")
        await self.bot.ticket_service.set_department(ticket, actor.id, department)
        await channel.send(embed=success_embed(f"Department set to `{department}`"))

    @ticket.command(name="scheduleclose", description="Schedule auto-close.")
    async def ticket_schedule_close(self, ctx: commands.Context[TicketBot], minutes: int) -> None:
        channel, ticket, actor = await self._current_ticket(ctx)
        if not _is_staff(actor):
            raise ValidationError("Staff permission required.")
        if minutes < 1 or minutes > 10080:
            raise ValidationError("Minutes must be between 1 and 10080.")
        job_id = await self.bot.automation_service.schedule_auto_close(
            ticket_id=ticket.id, guild_id=ticket.guild_id, after_minutes=minutes
        )
        eta = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        await channel.send(
            embed=staff_embed(
                "Auto-Close Scheduled",
                f"Job `{job_id}` will close this ticket around {discord.utils.format_dt(eta, style='R')}.",
            )
        )

    @ticket.command(name="transcript", description="Generate transcript on-demand.")
    async def ticket_transcript(self, ctx: commands.Context[TicketBot]) -> None:
        channel, ticket, actor = await self._current_ticket(ctx)
        if actor.id != ticket.opener_id and not _is_staff(actor):
            raise ValidationError("Only ticket owner or staff can export transcript.")
        files = await self._publish_transcript(channel, ticket)
        if not files:
            raise ValidationError("No transcript output enabled.")
        await ctx.reply(content="Transcript generated:", files=files, mention_author=False)

    @ticket.command(name="softdelete", description="Soft delete current ticket metadata.")
    async def ticket_soft_delete(self, ctx: commands.Context[TicketBot]) -> None:
        channel, ticket, actor = await self._current_ticket(ctx)
        if not _is_staff(actor):
            raise ValidationError("Staff permission required.")
        await self.bot.ticket_repo.mark_soft_deleted(ticket.id)
        await channel.send(embed=staff_embed("Soft Deleted", "Ticket marked as soft-deleted in database."))

    @ticket.command(name="harddelete", description="Hard delete current ticket channel.")
    async def ticket_hard_delete(self, ctx: commands.Context[TicketBot]) -> None:
        channel, ticket, actor = await self._current_ticket(ctx)
        if not _is_staff(actor):
            raise ValidationError("Staff permission required.")
        await self.bot.ticket_repo.mark_hard_deleted(ticket.id)
        await channel.send(embed=staff_embed("Hard Delete", "Channel will be deleted in 5 seconds."))
        await asyncio.sleep(5)
        await channel.delete(reason=f"Hard delete ticket by {actor} ({actor.id})")

    @ticket.command(name="forceclose", description="Force close and optionally delete channel.")
    async def ticket_force_close(self, ctx: commands.Context[TicketBot], delete_channel: bool, *, reason: str) -> None:
        channel, ticket, actor = await self._current_ticket(ctx)
        if not _is_staff(actor):
            raise ValidationError("Staff permission required.")
        await self.bot.ticket_service.close_ticket(ticket, actor.id, reason)
        files = await self._publish_transcript(channel, ticket)
        await self._send_transcript_to_log_channel(channel.guild, ticket, files)
        if delete_channel:
            await channel.delete(reason=f"Force close by {actor} ({actor.id})")
        else:
            await channel.send(embed=success_embed("Ticket force-closed without deleting channel."))

    @ticket.command(name="feedback", description="Submit rating for the current ticket.")
    async def ticket_feedback(self, ctx: commands.Context[TicketBot], stars: int, *, message: str = "") -> None:
        _, ticket, actor = await self._current_ticket(ctx)
        if actor.id != ticket.opener_id and not _is_staff(actor):
            raise ValidationError("Only ticket owner or staff can submit feedback.")
        await self.bot.ticket_service.record_feedback(ticket, actor.id, stars, message or None)
        await ctx.reply(embed=success_embed("Feedback recorded. Thank you."), mention_author=False)

    @ticket.command(name="info", description="Show ticket info.")
    async def ticket_info(self, ctx: commands.Context[TicketBot]) -> None:
        _, ticket, _ = await self._current_ticket(ctx)
        embed = make_embed(
            title=f"Ticket #{ticket.ticket_number}",
            description=f"ID: `{ticket.id}`",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Status", value=ticket.status, inline=True)
        embed.add_field(name="Priority", value=ticket.priority, inline=True)
        embed.add_field(name="Category", value=ticket.category_key, inline=True)
        embed.add_field(name="Owner", value=f"<@{ticket.opener_id}>", inline=True)
        embed.add_field(name="Claimed By", value=f"<@{ticket.claimed_by_id}>" if ticket.claimed_by_id else "None", inline=True)
        embed.add_field(name="Escalation", value=str(ticket.escalation_level), inline=True)
        embed.add_field(name="Department", value=ticket.department or "None", inline=True)
        embed.add_field(name="Tags", value=", ".join(ticket.tags) if ticket.tags else "None", inline=False)
        if ticket.close_reason:
            embed.add_field(name="Close Reason", value=ticket.close_reason[:1000], inline=False)
        await ctx.reply(embed=embed, mention_author=False)

    @ticket.command(name="list", description="List open tickets in this guild.")
    async def ticket_list(self, ctx: commands.Context[TicketBot]) -> None:
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            raise ValidationError("Guild context is required.")
        if not _is_staff(ctx.author):
            raise ValidationError("Staff permission required.")
        tickets = await self.bot.ticket_service.list_open_tickets(ctx.guild.id, limit=25)
        if not tickets:
            await ctx.reply(embed=success_embed("No open tickets found."), mention_author=False)
            return
        lines = [
            f"`#{ticket.ticket_number}` <#{ticket.channel_id}> | {ticket.status} | {ticket.priority} | <@{ticket.opener_id}>"
            for ticket in tickets
        ]
        await ctx.reply(
            embed=make_embed("Open Tickets", "\n".join(lines[:25]), color=discord.Color.blurple()),
            mention_author=False,
        )

    @tasks.loop(seconds=30)
    async def automation_worker(self) -> None:
        await self.bot.wait_until_ready()
        jobs = await self.bot.automation_service.due_auto_close_jobs()
        for job in jobs:
            try:
                ticket = await self.bot.ticket_repo.get_by_id(job.ticket_id)
                if not ticket:
                    await self.bot.automation_service.mark_job_failed(job.id, "ticket_not_found")
                    continue
                if ticket.status == "closed":
                    await self.bot.automation_service.mark_job_done(job.id)
                    continue
                guild = self.bot.get_guild(ticket.guild_id)
                if not guild:
                    await self.bot.automation_service.mark_job_failed(job.id, "guild_not_found")
                    continue
                channel = guild.get_channel(ticket.channel_id)
                if not isinstance(channel, discord.TextChannel):
                    await self.bot.automation_service.mark_job_failed(job.id, "channel_not_found")
                    continue
                await self.bot.ticket_service.close_ticket(
                    ticket=ticket,
                    actor_id=self.bot.user.id if self.bot.user else 0,
                    reason="Scheduled auto-close",
                )
                files = await self._publish_transcript(channel, ticket)
                await self._send_transcript_to_log_channel(guild, ticket, files)
                await channel.send(
                    embed=success_embed("Ticket auto-closed by scheduled automation."),
                )
                await self.bot.automation_service.mark_job_done(job.id)
            except Exception as exc:  # pragma: no cover - runtime safety
                LOGGER.exception("Automation worker failed for job %s", job.id)
                await self.bot.automation_service.mark_job_failed(job.id, str(exc))

    @automation_worker.before_loop
    async def before_automation_worker(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: TicketBot) -> None:
    await bot.add_cog(TicketsCog(bot))
