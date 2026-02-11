from __future__ import annotations

import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import discord
from discord.ext import commands

from core.bot import TicketBot
from core.extensions import reload_extensions
from database.models import TicketCategory, TicketPanel
from utils.embeds import error_embed, make_embed, staff_embed, success_embed
from views.setup_wizard import SetupWizardView
from views.ticket_panel import TicketPanelView


def _is_admin(member: discord.Member) -> bool:
    return member.guild_permissions.administrator


class AdminCog(commands.Cog):
    def __init__(self, bot: TicketBot) -> None:
        self.bot = bot

    async def _assert_admin(self, ctx: commands.Context[TicketBot]) -> None:
        if not ctx.guild or not isinstance(ctx.author, discord.Member) or not _is_admin(ctx.author):
            raise commands.CheckFailure("Administrator permission required.")

    @commands.hybrid_group(name="admin", with_app_command=True, description="Admin ticket operations.")
    async def admin(self, ctx: commands.Context[TicketBot]) -> None:
        if ctx.invoked_subcommand is None:
            await ctx.reply(
                embed=make_embed(
                    "Admin Commands",
                    "`/admin setup`\n"
                    "`/admin panel_create`\n"
                    "`/admin panel_deploy`\n"
                    "`/admin category_upsert`\n"
                    "`/admin blacklist_add`\n"
                    "`/admin reload`",
                ),
                mention_author=False,
            )

    @admin.command(name="setup", description="Launch interactive setup wizard.")
    async def admin_setup(self, ctx: commands.Context[TicketBot]) -> None:
        await self._assert_admin(ctx)
        await ctx.reply(
            "Open setup wizard:",
            view=SetupWizardView(self.bot),
            mention_author=False,
        )

    @admin.command(name="panel_create", description="Create or update a panel configuration.")
    async def panel_create(
        self,
        ctx: commands.Context[TicketBot],
        panel_id: str,
        channel: discord.TextChannel,
        *,
        title: str,
    ) -> None:
        await self._assert_admin(ctx)
        panel = TicketPanel(
            id=str(uuid4()),
            panel_id=panel_id.strip().lower(),
            guild_id=ctx.guild.id,  # type: ignore[union-attr]
            channel_id=channel.id,
            message_id=None,
            title=title[:100],
            description="Press the button to create a ticket.",
            button_label="Create Ticket",
            button_emoji="🎫",
            button_style="primary",
            category_map={},
            support_role_ids=[],
            log_channel_id=None,
            transcript_channel_id=None,
            is_enabled=True,
        )
        await self.bot.panel_repo.upsert(panel, created_by_id=ctx.author.id)
        await self.bot.ticket_service.bootstrap_default_categories(ctx.guild.id)  # type: ignore[union-attr]
        await ctx.reply(embed=success_embed(f"Panel `{panel.panel_id}` saved."), mention_author=False)

    @admin.command(name="panel_deploy", description="Deploy panel embed and interactive button.")
    async def panel_deploy(self, ctx: commands.Context[TicketBot], panel_id: str) -> None:
        await self._assert_admin(ctx)
        panel = await self.bot.panel_repo.get_by_panel_id(panel_id.strip().lower())
        if not panel or panel.guild_id != ctx.guild.id:  # type: ignore[union-attr]
            await ctx.reply(embed=error_embed("Panel not found."), mention_author=False)
            return
        channel = ctx.guild.get_channel(panel.channel_id)  # type: ignore[union-attr]
        if not isinstance(channel, discord.TextChannel):
            await ctx.reply(embed=error_embed("Panel channel is not a text channel."), mention_author=False)
            return
        embed = make_embed(panel.title, panel.description, color=discord.Color.blurple())
        message = await channel.send(embed=embed, view=TicketPanelView(self.bot, panel))
        await self.bot.panel_repo.update_message_id(panel.panel_id, message.id)
        self.bot.add_view(TicketPanelView(self.bot, panel))
        await ctx.reply(embed=success_embed(f"Panel deployed to {channel.mention}"), mention_author=False)

    @admin.command(name="panel_list", description="List configured ticket panels.")
    async def panel_list(self, ctx: commands.Context[TicketBot]) -> None:
        await self._assert_admin(ctx)
        panels = await self.bot.panel_repo.list_by_guild(ctx.guild.id)  # type: ignore[union-attr]
        if not panels:
            await ctx.reply(embed=success_embed("No panels configured."), mention_author=False)
            return
        lines = [
            f"`{panel.panel_id}` channel:<#{panel.channel_id}> message:{panel.message_id or 'n/a'} enabled:{panel.is_enabled}"
            for panel in panels
        ]
        await ctx.reply(embed=make_embed("Ticket Panels", "\n".join(lines)), mention_author=False)

    @admin.command(name="category_upsert", description="Create or update a ticket category.")
    async def category_upsert(
        self,
        ctx: commands.Context[TicketBot],
        key: str,
        display_name: str,
        sla_minutes: int = 120,
    ) -> None:
        await self._assert_admin(ctx)
        category = TicketCategory(
            id=str(uuid4()),
            guild_id=ctx.guild.id,  # type: ignore[union-attr]
            key=key.strip().lower(),
            display_name=display_name[:100],
            description=f"{display_name} requests",
            channel_category_id=None,
            support_role_ids=[],
            modal_questions=[
                {
                    "id": "subject",
                    "label": "Subject",
                    "placeholder": "Summarize the request",
                    "style": "short",
                    "required": True,
                    "max_length": 100,
                },
                {
                    "id": "details",
                    "label": "Details",
                    "placeholder": "Provide full context",
                    "style": "long",
                    "required": True,
                    "max_length": 1000,
                },
            ],
            template={"intro": f"Thanks for opening a {display_name} ticket."},
            priority_default="normal",
            tags_default=[key.strip().lower()],
            sla_minutes=max(10, min(sla_minutes, 1440)),
            is_enabled=True,
        )
        await self.bot.category_repo.upsert(category)
        await ctx.reply(embed=success_embed(f"Category `{category.key}` saved."), mention_author=False)

    @admin.command(name="category_list", description="List ticket categories.")
    async def category_list(self, ctx: commands.Context[TicketBot]) -> None:
        await self._assert_admin(ctx)
        categories = await self.bot.category_repo.list_by_guild(ctx.guild.id)  # type: ignore[union-attr]
        if not categories:
            await ctx.reply(embed=success_embed("No categories configured."), mention_author=False)
            return
        lines = [
            f"`{cat.key}` | {cat.display_name} | sla:{cat.sla_minutes}m | enabled:{cat.is_enabled}"
            for cat in categories
        ]
        await ctx.reply(embed=make_embed("Ticket Categories", "\n".join(lines)), mention_author=False)

    @admin.command(name="set_channels", description="Set log/transcript channels for guild defaults.")
    async def set_channels(
        self,
        ctx: commands.Context[TicketBot],
        transcript_channel: discord.TextChannel,
        log_channel: discord.TextChannel,
    ) -> None:
        await self._assert_admin(ctx)
        await self.bot.guild_repo.set_channels(ctx.guild.id, transcript_channel.id, log_channel.id)  # type: ignore[union-attr]
        await ctx.reply(embed=success_embed("Guild channels updated."), mention_author=False)

    @admin.command(name="blacklist_add", description="Blacklist a user from creating tickets.")
    async def blacklist_add(
        self, ctx: commands.Context[TicketBot], user: discord.User, hours: int, *, reason: str
    ) -> None:
        await self._assert_admin(ctx)
        until = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat() if hours > 0 else None
        await self.bot.ticket_service.blacklist_user(
            guild_id=ctx.guild.id,  # type: ignore[union-attr]
            actor_id=ctx.author.id,
            user_id=user.id,
            reason=reason,
            until_iso=until,
        )
        await ctx.reply(embed=success_embed(f"User <@{user.id}> blacklisted."), mention_author=False)

    @admin.command(name="blacklist_remove", description="Remove a user from blacklist.")
    async def blacklist_remove(self, ctx: commands.Context[TicketBot], user: discord.User) -> None:
        await self._assert_admin(ctx)
        await self.bot.ticket_service.unblacklist_user(
            guild_id=ctx.guild.id,  # type: ignore[union-attr]
            actor_id=ctx.author.id,
            user_id=user.id,
        )
        await ctx.reply(embed=success_embed(f"User <@{user.id}> removed from blacklist."), mention_author=False)

    @admin.command(name="reload", description="Reload all enabled extensions.")
    async def reload(self, ctx: commands.Context[TicketBot]) -> None:
        await self._assert_admin(ctx)
        await reload_extensions(self.bot, self.bot.config.enabled_extensions)
        await ctx.reply(embed=success_embed("Extensions reloaded."), mention_author=False)

    @admin.command(name="config_backup", description="Backup config file.")
    async def config_backup(self, ctx: commands.Context[TicketBot]) -> None:
        await self._assert_admin(ctx)
        source = self.bot.root_dir / "config" / "config.yaml"
        backup_dir = self.bot.root_dir / "config" / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        target = backup_dir / f"config_{stamp}.yaml"
        shutil.copyfile(source, target)
        await ctx.reply(embed=success_embed(f"Backup saved: `{target.name}`"), mention_author=False)

    @admin.command(name="config_restore", description="Restore config from backup filename.")
    async def config_restore(self, ctx: commands.Context[TicketBot], filename: str) -> None:
        await self._assert_admin(ctx)
        backup = self.bot.root_dir / "config" / "backups" / filename
        target = self.bot.root_dir / "config" / "config.yaml"
        if not backup.exists():
            await ctx.reply(embed=error_embed("Backup file not found."), mention_author=False)
            return
        shutil.copyfile(backup, target)
        await ctx.reply(
            embed=staff_embed(
                "Config Restored",
                "Config file restored. Run `/admin reload` to reload extensions and apply runtime changes.",
            ),
            mention_author=False,
        )

    @admin.command(name="staff_warn", description="Issue a staff warning.")
    async def staff_warn(self, ctx: commands.Context[TicketBot], member: discord.Member, *, reason: str) -> None:
        await self._assert_admin(ctx)
        warning_id = str(uuid4())
        await self.bot.database.execute(
            """
            INSERT INTO staff_warnings(id, guild_id, staff_id, moderator_id, reason)
            VALUES (?, ?, ?, ?, ?);
            """,
            [warning_id, ctx.guild.id, member.id, ctx.author.id, reason],  # type: ignore[union-attr]
        )
        await self.bot.database.execute(
            """
            INSERT INTO staff_stats(guild_id, staff_id)
            VALUES (?, ?)
            ON CONFLICT(guild_id, staff_id) DO NOTHING;
            """,
            [ctx.guild.id, member.id],  # type: ignore[union-attr]
        )
        await self.bot.database.execute(
            """
            UPDATE staff_stats
            SET warnings_count = warnings_count + 1, last_active_at = CURRENT_TIMESTAMP
            WHERE guild_id = ? AND staff_id = ?;
            """,
            [ctx.guild.id, member.id],  # type: ignore[union-attr]
        )
        await ctx.reply(
            embed=staff_embed("Staff Warning Issued", f"{member.mention} warned. Reason: {reason}"),
            mention_author=False,
        )


async def setup(bot: TicketBot) -> None:
    await bot.add_cog(AdminCog(bot))
