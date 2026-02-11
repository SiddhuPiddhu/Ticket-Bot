from __future__ import annotations

import logging

import discord
from discord.ext import commands

from core.bot import TicketBot

LOGGER = logging.getLogger(__name__)


class EventsCog(commands.Cog):
    def __init__(self, bot: TicketBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        for guild in self.bot.guilds:
            await self.bot.guild_repo.ensure_guild(guild.id)
            await self.bot.ticket_service.bootstrap_default_categories(guild.id)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        await self.bot.guild_repo.ensure_guild(guild.id)
        await self.bot.ticket_service.bootstrap_default_categories(guild.id)
        LOGGER.info("Bootstrapped defaults for new guild %s", guild.id)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild or not isinstance(message.channel, discord.TextChannel):
            return

        ticket = await self.bot.ticket_repo.get_by_channel(message.guild.id, message.channel.id)
        if not ticket:
            return
        member = message.author if isinstance(message.author, discord.Member) else None
        if not member:
            return
        await self.bot.ticket_service.register_staff_message(ticket=ticket, member=member)


async def setup(bot: TicketBot) -> None:
    await bot.add_cog(EventsCog(bot))
