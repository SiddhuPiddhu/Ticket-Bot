from __future__ import annotations

import logging
from dataclasses import dataclass

import discord
from discord import app_commands
from discord.ext import commands

LOGGER = logging.getLogger(__name__)


class BotError(RuntimeError):
    user_message: str = "An unexpected error occurred."


@dataclass(slots=True)
class PermissionDeniedError(BotError):
    user_message: str = "You do not have permission to run this action."


@dataclass(slots=True)
class TicketLimitReachedError(BotError):
    user_message: str = "You reached the maximum open ticket limit."


@dataclass(slots=True)
class TicketNotFoundError(BotError):
    user_message: str = "The requested ticket could not be found."


@dataclass(slots=True)
class TicketStateError(BotError):
    user_message: str = "The ticket is not in a valid state for this action."


@dataclass(slots=True)
class ValidationError(BotError):
    user_message: str = "The provided input is not valid."


# Backward-compatible aliases used across the codebase.
PermissionDenied = PermissionDeniedError
TicketLimitReached = TicketLimitReachedError
TicketNotFound = TicketNotFoundError


async def send_error_response(
    target: commands.Context[commands.Bot] | discord.Interaction[commands.Bot], message: str
) -> None:
    embed = discord.Embed(title="Error", description=message, color=discord.Color.red())
    if isinstance(target, commands.Context):
        await target.reply(embed=embed, mention_author=False)
        return
    if target.response.is_done():
        await target.followup.send(embed=embed, ephemeral=True)
    else:
        await target.response.send_message(embed=embed, ephemeral=True)


def _humanize_command_error(error: Exception) -> str:
    if isinstance(error, BotError):
        return error.user_message
    if isinstance(error, commands.CommandOnCooldown):
        return f"Cooldown active. Retry in {error.retry_after:.1f} seconds."
    if isinstance(error, commands.MissingPermissions):
        return "You are missing required Discord permissions."
    if isinstance(error, commands.CheckFailure):
        return "You are not authorized for this command."
    if isinstance(error, commands.BadArgument):
        return "Command argument was invalid."
    return "An unexpected command error occurred."


async def handle_prefix_command_error(
    ctx: commands.Context[commands.Bot], error: commands.CommandError
) -> None:
    message = _humanize_command_error(error)
    LOGGER.exception(
        "Prefix command failed. command=%s guild=%s user=%s",
        getattr(ctx.command, "qualified_name", None),
        getattr(ctx.guild, "id", None),
        ctx.author.id,
        exc_info=error,
    )
    await send_error_response(ctx, message)


async def handle_app_command_error(
    interaction: discord.Interaction[commands.Bot], error: app_commands.AppCommandError
) -> None:
    message = "An unexpected slash-command error occurred."
    if isinstance(error, app_commands.CheckFailure):
        message = "You are not authorized for this command."
    elif isinstance(error, app_commands.CommandOnCooldown):
        message = f"Cooldown active. Retry in {error.retry_after:.1f} seconds."
    elif isinstance(error, BotError):
        message = error.user_message

    LOGGER.exception(
        "Slash command failed. command=%s guild=%s user=%s",
        getattr(interaction.command, "qualified_name", None),
        getattr(interaction.guild, "id", None),
        interaction.user.id if interaction.user else None,
        exc_info=error,
    )
    await send_error_response(interaction, message)
