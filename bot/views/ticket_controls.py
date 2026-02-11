from __future__ import annotations

from typing import TYPE_CHECKING, cast

import discord

from core.errors import ValidationError
from utils.embeds import error_embed, staff_embed, success_embed

if TYPE_CHECKING:
    from core.bot import TicketBot


def _is_staff(member: discord.Member) -> bool:
    if member.guild_permissions.administrator or member.guild_permissions.manage_channels:
        return True
    return any(role.name.lower() in {"support", "staff", "moderator", "admin"} for role in member.roles)


class CloseReasonModal(discord.ui.Modal, title="Close Ticket"):
    reason = discord.ui.TextInput(
        label="Close Reason",
        placeholder="Provide a concise close reason",
        style=discord.TextStyle.long,
        max_length=1024,
        required=True,
    )

    def __init__(self, controls_view: TicketControlsView) -> None:
        super().__init__(timeout=300)
        self.controls_view = controls_view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(embed=error_embed("Guild context is required."), ephemeral=True)
            return
        ticket = await self.controls_view.bot.ticket_service.get_ticket_for_channel(
            interaction.guild.id, cast(discord.TextChannel, interaction.channel).id
        )
        await self.controls_view.bot.ticket_service.close_ticket(
            ticket=ticket,
            actor_id=interaction.user.id,
            reason=str(self.reason).strip(),
        )
        channel = cast(discord.TextChannel, interaction.channel)
        artifacts = await self.controls_view.bot.transcript_service.generate(channel=channel, ticket_id=ticket.id)
        await self.controls_view.bot.ticket_repo.set_transcripts(
            ticket.id,
            str(artifacts.html_path) if artifacts.html_path else None,
            str(artifacts.txt_path) if artifacts.txt_path else None,
        )
        files: list[discord.File] = []
        if artifacts.html_path and artifacts.html_path.exists():
            files.append(discord.File(artifacts.html_path))
        if artifacts.txt_path and artifacts.txt_path.exists():
            files.append(discord.File(artifacts.txt_path))

        if files:
            panel = await self.controls_view.bot.panel_repo.get_by_panel_id(ticket.panel_id) if ticket.panel_id else None
            transcript_channel_id = panel.transcript_channel_id if panel else None
            if not transcript_channel_id:
                settings = await self.controls_view.bot.database.fetchone(
                    "SELECT transcript_channel_id FROM guild_settings WHERE guild_id = ?;",
                    [interaction.guild.id],
                )
                if settings:
                    transcript_channel_id = settings.get("transcript_channel_id")
            transcript_channel = interaction.guild.get_channel(transcript_channel_id) if transcript_channel_id else None
            if isinstance(transcript_channel, discord.TextChannel):
                await transcript_channel.send(
                    content=f"Transcript for ticket `{ticket.id}` (#{ticket.ticket_number})",
                    files=files,
                )

        await channel.set_permissions(interaction.guild.default_role, send_messages=False)
        await interaction.response.send_message(
            embed=success_embed("Ticket closed. Use reopen to resume this ticket."),
            ephemeral=False,
        )


class TicketControlsView(discord.ui.View):
    def __init__(self, bot: TicketBot, ticket_id: str) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.ticket_id = ticket_id

    @discord.ui.button(
        label="Claim",
        style=discord.ButtonStyle.primary,
        emoji="🛠️",
        custom_id="ticket:claim",
    )
    async def claim_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(embed=error_embed("Guild context is required."), ephemeral=True)
            return
        if not _is_staff(interaction.user):
            await interaction.response.send_message(
                embed=error_embed("You must be staff to claim tickets."), ephemeral=True
            )
            return
        ticket = await self.bot.ticket_service.get_ticket_for_channel(
            interaction.guild.id, cast(discord.TextChannel, interaction.channel).id
        )
        updated = await self.bot.ticket_service.claim_ticket(ticket, interaction.user)
        await interaction.response.send_message(
            embed=staff_embed("Ticket Claimed", f"Claimed by {interaction.user.mention}."),
            ephemeral=False,
        )
        if isinstance(interaction.channel, discord.TextChannel):
            await interaction.channel.edit(topic=f"ticket|{updated.ticket_number}|claimed:{interaction.user.id}")

    @discord.ui.button(
        label="Unclaim",
        style=discord.ButtonStyle.secondary,
        emoji="📤",
        custom_id="ticket:unclaim",
    )
    async def unclaim_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(embed=error_embed("Guild context is required."), ephemeral=True)
            return
        if not _is_staff(interaction.user):
            await interaction.response.send_message(
                embed=error_embed("You must be staff to unclaim tickets."), ephemeral=True
            )
            return
        ticket = await self.bot.ticket_service.get_ticket_for_channel(
            interaction.guild.id, cast(discord.TextChannel, interaction.channel).id
        )
        await self.bot.ticket_service.unclaim_ticket(ticket, interaction.user)
        await interaction.response.send_message(
            embed=success_embed("Ticket unclaimed."),
            ephemeral=False,
        )

    @discord.ui.button(
        label="Lock",
        style=discord.ButtonStyle.secondary,
        emoji="🔒",
        custom_id="ticket:lock",
    )
    async def lock_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(embed=error_embed("Guild context is required."), ephemeral=True)
            return
        if not _is_staff(interaction.user):
            await interaction.response.send_message(
                embed=error_embed("You must be staff to lock tickets."), ephemeral=True
            )
            return
        channel = cast(discord.TextChannel, interaction.channel)
        ticket = await self.bot.ticket_service.get_ticket_for_channel(interaction.guild.id, channel.id)
        await self.bot.ticket_service.lock_ticket(ticket=ticket, actor_id=interaction.user.id)
        opener = interaction.guild.get_member(ticket.opener_id)
        if opener:
            await channel.set_permissions(opener, send_messages=False)
        await interaction.response.send_message(embed=success_embed("Ticket locked."), ephemeral=False)

    @discord.ui.button(
        label="Unlock",
        style=discord.ButtonStyle.success,
        emoji="🔓",
        custom_id="ticket:unlock",
    )
    async def unlock_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(embed=error_embed("Guild context is required."), ephemeral=True)
            return
        if not _is_staff(interaction.user):
            await interaction.response.send_message(
                embed=error_embed("You must be staff to unlock tickets."), ephemeral=True
            )
            return
        channel = cast(discord.TextChannel, interaction.channel)
        ticket = await self.bot.ticket_service.get_ticket_for_channel(interaction.guild.id, channel.id)
        await self.bot.ticket_service.unlock_ticket(ticket=ticket, actor_id=interaction.user.id)
        opener = interaction.guild.get_member(ticket.opener_id)
        if opener:
            await channel.set_permissions(opener, send_messages=True)
        await interaction.response.send_message(embed=success_embed("Ticket unlocked."), ephemeral=False)

    @discord.ui.button(
        label="Close",
        style=discord.ButtonStyle.danger,
        emoji="🧾",
        custom_id="ticket:close",
    )
    async def close_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(embed=error_embed("Guild context is required."), ephemeral=True)
            return
        if not _is_staff(interaction.user):
            await interaction.response.send_message(
                embed=error_embed("You must be staff to close tickets."), ephemeral=True
            )
            return
        await interaction.response.send_modal(CloseReasonModal(self))

    @discord.ui.button(
        label="Reopen",
        style=discord.ButtonStyle.success,
        emoji="♻️",
        custom_id="ticket:reopen",
    )
    async def reopen_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(embed=error_embed("Guild context is required."), ephemeral=True)
            return
        if not _is_staff(interaction.user):
            await interaction.response.send_message(
                embed=error_embed("You must be staff to reopen tickets."), ephemeral=True
            )
            return
        channel = cast(discord.TextChannel, interaction.channel)
        ticket = await self.bot.ticket_service.get_ticket_for_channel(interaction.guild.id, channel.id)
        await self.bot.ticket_service.reopen_ticket(ticket=ticket, actor_id=interaction.user.id)
        opener = interaction.guild.get_member(ticket.opener_id)
        if opener:
            await channel.set_permissions(opener, send_messages=True)
        await interaction.response.send_message(
            embed=success_embed("Ticket reopened."),
            ephemeral=False,
        )

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item[discord.ui.View]) -> None:
        if isinstance(error, ValidationError):
            await interaction.response.send_message(embed=error_embed(error.user_message), ephemeral=True)
            return
        await interaction.response.send_message(
            embed=error_embed("Action failed due to an unexpected error."),
            ephemeral=True,
        )
