from __future__ import annotations

import statistics

import discord
from discord.ext import commands

from core.bot import TicketBot
from utils.embeds import make_embed, success_embed


def _is_staff(member: discord.Member) -> bool:
    return member.guild_permissions.administrator or member.guild_permissions.manage_guild


class AnalyticsCog(commands.Cog):
    def __init__(self, bot: TicketBot) -> None:
        self.bot = bot

    @commands.hybrid_group(
        name="analytics",
        with_app_command=True,
        description="Ticket analytics and exports.",
    )
    async def analytics(self, ctx: commands.Context[TicketBot]) -> None:
        if ctx.invoked_subcommand is None:
            await ctx.reply(
                embed=make_embed(
                    "Analytics Commands",
                    "`/analytics dashboard`\n"
                    "`/analytics leaderboard`\n"
                    "`/analytics export`\n"
                    "`/analytics graph`\n"
                    "`/analytics response_times`",
                ),
                mention_author=False,
            )

    @analytics.command(name="dashboard", description="Show dashboard metrics.")
    async def analytics_dashboard(self, ctx: commands.Context[TicketBot]) -> None:
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return
        if not _is_staff(ctx.author):
            await ctx.reply("Staff permission required.", mention_author=False)
            return
        metrics = await self.bot.analytics_service.build_dashboard(ctx.guild.id)
        embed = make_embed("Ticket Dashboard", f"Guild: **{ctx.guild.name}**", color=discord.Color.blurple())
        embed.add_field(name="Total Tickets", value=str(metrics.total_tickets), inline=True)
        embed.add_field(name="Open Tickets", value=str(metrics.open_tickets), inline=True)
        embed.add_field(name="Closed Tickets", value=str(metrics.closed_tickets), inline=True)

        category_lines = [
            f"`{row['category_key']}`: {row['count']}" for row in metrics.category_counts[:10]
        ] or ["No data"]
        embed.add_field(name="Top Categories", value="\n".join(category_lines), inline=False)

        staff_lines = [
            f"<@{row['staff_id']}> closed:{row['tickets_closed']} claimed:{row['tickets_claimed']}"
            for row in metrics.staff_leaderboard[:10]
        ] or ["No data"]
        embed.add_field(name="Staff Leaderboard", value="\n".join(staff_lines), inline=False)
        await ctx.reply(embed=embed, mention_author=False)

    @analytics.command(name="leaderboard", description="Show staff leaderboard.")
    async def analytics_leaderboard(self, ctx: commands.Context[TicketBot]) -> None:
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return
        if not _is_staff(ctx.author):
            await ctx.reply("Staff permission required.", mention_author=False)
            return
        rows = await self.bot.staff_repo.leaderboard(ctx.guild.id, limit=20)
        if not rows:
            await ctx.reply(embed=success_embed("No staff data yet."), mention_author=False)
            return
        lines = [
            f"`{idx+1:02}` <@{row['staff_id']}> | closed:{row['tickets_closed']} "
            f"| claimed:{row['tickets_claimed']} | avg_first_response:{(row.get('avg_first_response_seconds') or 0):.1f}s"
            for idx, row in enumerate(rows)
        ]
        await ctx.reply(embed=make_embed("Staff Leaderboard", "\n".join(lines)), mention_author=False)

    @analytics.command(name="export", description="Export ticket records to CSV.")
    async def analytics_export(self, ctx: commands.Context[TicketBot]) -> None:
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return
        if not _is_staff(ctx.author):
            await ctx.reply("Staff permission required.", mention_author=False)
            return
        csv_file = await self.bot.analytics_service.export_tickets_csv(ctx.guild.id)
        await ctx.reply(
            content="Ticket export generated.",
            file=discord.File(csv_file),
            mention_author=False,
        )

    @analytics.command(name="graph", description="Generate ticket volume graph.")
    async def analytics_graph(self, ctx: commands.Context[TicketBot]) -> None:
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return
        if not _is_staff(ctx.author):
            await ctx.reply("Staff permission required.", mention_author=False)
            return
        output = await self.bot.analytics_service.generate_graph(ctx.guild.id)
        if not output:
            await ctx.reply("Graph generation unavailable.", mention_author=False)
            return
        await ctx.reply(content="Ticket volume graph:", file=discord.File(output), mention_author=False)

    @analytics.command(name="response_times", description="Show response-time statistics.")
    async def analytics_response_times(self, ctx: commands.Context[TicketBot]) -> None:
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return
        if not _is_staff(ctx.author):
            await ctx.reply("Staff permission required.", mention_author=False)
            return
        rows = await self.bot.analytics_repo.response_time_distribution(ctx.guild.id)
        values = [int(row["seconds"]) for row in rows if row.get("seconds") is not None and int(row["seconds"]) >= 0]
        if not values:
            await ctx.reply(embed=success_embed("No response-time data available."), mention_author=False)
            return
        avg = statistics.mean(values)
        median = statistics.median(values)
        p95 = sorted(values)[int(len(values) * 0.95) - 1] if len(values) > 1 else values[0]
        embed = make_embed(
            "Response Time Metrics",
            f"Samples: **{len(values)}**",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Average", value=f"{avg:.1f}s", inline=True)
        embed.add_field(name="Median", value=f"{median:.1f}s", inline=True)
        embed.add_field(name="P95", value=f"{p95:.1f}s", inline=True)
        await ctx.reply(embed=embed, mention_author=False)


async def setup(bot: TicketBot) -> None:
    await bot.add_cog(AnalyticsCog(bot))
