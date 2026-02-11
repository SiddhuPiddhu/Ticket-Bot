from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import discord

from database.models import TicketPanel
from utils.embeds import error_embed, success_embed
from views.ticket_panel import TicketPanelView

if TYPE_CHECKING:
    from core.bot import TicketBot


class SetupWizardModal(discord.ui.Modal, title="Ticket Panel Setup"):
    panel_id = discord.ui.TextInput(
        label="Panel ID",
        placeholder="support-main",
        required=True,
        max_length=64,
    )
    channel_id = discord.ui.TextInput(
        label="Panel Channel ID",
        placeholder="123456789012345678",
        required=True,
        max_length=20,
    )
    title_input = discord.ui.TextInput(
        label="Panel Title",
        placeholder="Support Center",
        required=True,
        max_length=100,
    )
    description_input = discord.ui.TextInput(
        label="Panel Description",
        placeholder="Create a ticket using the button below.",
        style=discord.TextStyle.long,
        required=True,
        max_length=1000,
    )

    def __init__(self, bot: TicketBot) -> None:
        super().__init__(timeout=600)
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(embed=error_embed("Guild context is required."), ephemeral=True)
            return
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(embed=error_embed("Admin permission required."), ephemeral=True)
            return

        try:
            channel_id = int(str(self.channel_id).strip())
        except ValueError:
            await interaction.response.send_message(embed=error_embed("Invalid channel ID."), ephemeral=True)
            return

        channel = interaction.guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(embed=error_embed("Channel must be a text channel."), ephemeral=True)
            return

        panel = TicketPanel(
            id=str(uuid4()),
            panel_id=str(self.panel_id).strip().lower(),
            guild_id=interaction.guild.id,
            channel_id=channel.id,
            message_id=None,
            title=str(self.title_input).strip(),
            description=str(self.description_input).strip(),
            button_label="Create Ticket",
            button_emoji="🎫",
            button_style="primary",
            category_map={},
            support_role_ids=[],
            log_channel_id=None,
            transcript_channel_id=None,
            is_enabled=True,
        )
        await self.bot.panel_repo.upsert(panel, created_by_id=interaction.user.id)
        await self.bot.ticket_service.bootstrap_default_categories(interaction.guild.id)

        embed = discord.Embed(title=panel.title, description=panel.description, color=discord.Color.blurple())
        msg = await channel.send(embed=embed, view=TicketPanelView(self.bot, panel))
        await self.bot.panel_repo.update_message_id(panel.panel_id, msg.id)
        await interaction.response.send_message(
            embed=success_embed(f"Panel deployed in {channel.mention}"),
            ephemeral=True,
        )


class SetupWizardView(discord.ui.View):
    def __init__(self, bot: TicketBot) -> None:
        super().__init__(timeout=300)
        self.bot = bot

    @discord.ui.button(label="Launch Setup Wizard", style=discord.ButtonStyle.primary, emoji="⚙️")
    async def launch(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(SetupWizardModal(self.bot))
