from __future__ import annotations

import logging

from discord.ext import commands

LOGGER = logging.getLogger(__name__)


async def load_extensions(bot: commands.Bot, extension_names: list[str]) -> None:
    for ext in extension_names:
        try:
            await bot.load_extension(ext)
            LOGGER.info("Loaded extension: %s", ext)
        except commands.ExtensionAlreadyLoaded:
            LOGGER.warning("Extension already loaded: %s", ext)
        except commands.ExtensionError:
            LOGGER.exception("Failed to load extension: %s", ext)


async def reload_extensions(bot: commands.Bot, extension_names: list[str]) -> None:
    for ext in extension_names:
        try:
            await bot.reload_extension(ext)
            LOGGER.info("Reloaded extension: %s", ext)
        except commands.ExtensionError:
            LOGGER.exception("Failed to reload extension: %s", ext)
