from __future__ import annotations

import random
from typing import TYPE_CHECKING

import discord

from utils.embeds import error_embed, make_embed, success_embed
from views.ticket_controls import TicketControlsView

if TYPE_CHECKING:
    from core.bot import TicketBot
    from database.models import TicketCategory, TicketPanel


def _button_style_from_name(style_name: str) -> discord.ButtonStyle:
    mapping = {
        "primary": discord.ButtonStyle.primary,
        "secondary": discord.ButtonStyle.secondary,
        "success": discord.ButtonStyle.success,
        "danger": discord.ButtonStyle.danger,
    }
    return mapping.get(style_name.lower(), discord.ButtonStyle.primary)


class CaptchaModal(discord.ui.Modal):
    response = discord.ui.TextInput(
        label="Enter the code",
        placeholder="Type the exact verification code",
        required=True,
        max_length=10,
    )

    def __init__(
        self,
        expected: str,
        bot: TicketBot,
        panel: TicketPanel,
        categories: list[TicketCategory],
    ) -> None:
        super().__init__(title=f"Captcha: {expected}", timeout=180)
        self.expected = expected
        self.bot = bot
        self.panel = panel
        self.categories = categories

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if str(self.response).strip() != self.expected:
            await interaction.response.send_message(
                embed=error_embed("Captcha verification failed."),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            "Select a category to continue:",
            view=TicketCategoryView(self.bot, self.panel, self.categories),
            ephemeral=True,
        )


class DynamicTicketModal(discord.ui.Modal):
    def __init__(
        self,
        bot: TicketBot,
        panel: TicketPanel,
        category: TicketCategory,
        opener: discord.Member,
        anonymous: bool = False,
    ) -> None:
        super().__init__(title=f"{category.display_name} Ticket", timeout=600)
        self.bot = bot
        self.panel = panel
        self.category = category
        self.opener = opener
        self.anonymous = anonymous
        self._inputs: list[tuple[str, discord.ui.TextInput]] = []

        questions = category.modal_questions[:5]
        if not questions:
            questions = [
                {
                    "id": "details",
                    "label": "Details",
                    "placeholder": "Describe your issue",
                    "style": "long",
                    "required": True,
                    "max_length": 1000,
                }
            ]

        for question in questions:
            style = discord.TextStyle.long if question.get("style") == "long" else discord.TextStyle.short
            text_input = discord.ui.TextInput(
                label=str(question.get("label", "Question"))[:45],
                placeholder=str(question.get("placeholder", ""))[:100],
                style=style,
                required=bool(question.get("required", True)),
                max_length=int(question.get("max_length", 1000)),
            )
            self._inputs.append((str(question.get("id", f"q{len(self._inputs)+1}")), text_input))
            self.add_item(text_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message(
                embed=error_embed("Guild context is required."),
                ephemeral=True,
            )
            return

        answers = {qid: str(inp.value).strip() for qid, inp in self._inputs}
        ticket = await self.bot.ticket_service.create_ticket(
            guild=interaction.guild,
            opener=self.opener,
            panel=self.panel,
            category_key=self.category.key,
            form_answers=answers,
            anonymous=self.anonymous,
        )

        channel = interaction.guild.get_channel(ticket.channel_id)
        if isinstance(channel, discord.TextChannel):
            body = "\n".join([f"**{key}**: {value}" for key, value in answers.items()]) or "No details"
            embed = make_embed(
                title=f"Ticket #{ticket.ticket_number} | {self.category.display_name}",
                description=body,
                color=discord.Color.blurple(),
                footer=f"Ticket ID: {ticket.id}",
            )
            if not ticket.is_anonymous:
                embed.add_field(name="Opened By", value=self.opener.mention, inline=False)
            embed.add_field(name="Priority", value=ticket.priority.title(), inline=True)
            embed.add_field(name="Category", value=self.category.display_name, inline=True)
            await channel.send(
                content="@here New ticket created.",
                embed=embed,
                view=TicketControlsView(bot=self.bot, ticket_id=ticket.id),
            )

        await interaction.response.send_message(
            embed=success_embed(f"Ticket created: <#{ticket.channel_id}>"),
            ephemeral=True,
        )


class TicketCategorySelect(discord.ui.Select):
    def __init__(self, bot: TicketBot, panel: TicketPanel, categories: list[TicketCategory]) -> None:
        options = [
            discord.SelectOption(label=cat.display_name[:100], value=cat.key, description=cat.description[:100])
            for cat in categories[:25]
        ]
        super().__init__(
            placeholder="Select ticket category",
            options=options,
            min_values=1,
            max_values=1,
            custom_id=f"ticket:category:{panel.panel_id}",
        )
        self.bot = bot
        self.panel = panel
        self.categories = {c.key: c for c in categories}

    async def callback(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                embed=error_embed("Guild context is required."),
                ephemeral=True,
            )
            return
        selected_key = self.values[0]
        category = self.categories.get(selected_key)
        if not category:
            await interaction.response.send_message(
                embed=error_embed("Invalid category selected."),
                ephemeral=True,
            )
            return

        anonymous = False
        if self.bot.config.security.allow_anonymous_tickets:
            anonymous = selected_key in {"bug", "suggestion"}

        modal = DynamicTicketModal(
            bot=self.bot,
            panel=self.panel,
            category=category,
            opener=interaction.user,
            anonymous=anonymous,
        )
        await interaction.response.send_modal(modal)


class TicketCategoryView(discord.ui.View):
    def __init__(self, bot: TicketBot, panel: TicketPanel, categories: list[TicketCategory]) -> None:
        super().__init__(timeout=300)
        self.add_item(TicketCategorySelect(bot, panel, categories))


class TicketCreateButton(discord.ui.Button["TicketPanelView"]):
    def __init__(self, bot: TicketBot, panel: TicketPanel) -> None:
        super().__init__(
            label=panel.button_label,
            emoji=panel.button_emoji,
            style=_button_style_from_name(panel.button_style),
            custom_id=f"ticket:create:{panel.panel_id}",
        )
        self.bot = bot
        self.panel = panel

    async def callback(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                embed=error_embed("Guild context is required."),
                ephemeral=True,
            )
            return

        categories = await self.bot.ticket_service.list_categories(interaction.guild.id)
        if not categories:
            await interaction.response.send_message(
                embed=error_embed("No ticket categories are configured."),
                ephemeral=True,
            )
            return

        if self.bot.config.security.enable_captcha:
            code = str(random.randint(10000, 99999))
            await interaction.response.send_modal(CaptchaModal(code, self.bot, self.panel, categories))
            return

        await interaction.response.send_message(
            "Select a category to continue:",
            view=TicketCategoryView(self.bot, self.panel, categories),
            ephemeral=True,
        )


class TicketPanelView(discord.ui.View):
    def __init__(self, bot: TicketBot, panel: TicketPanel) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.panel = panel
        self.add_item(TicketCreateButton(bot, panel))
