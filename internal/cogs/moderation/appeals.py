from __future__ import annotations

from datetime import datetime, timezone

import discord
from discord.commands import Option
from discord.ext import commands

from internal.utils.ansi import BLUE
from internal.views.moderation_appeals import AppealReviewView
from internal.views.moderation_modals import AppealModal

from .groups import appeal


class AppealCommands:
    @appeal.command(name="submit", description="Submits an appeal")
    async def appeal_submit(self, ctx: discord.ApplicationContext, case_id: Option(int, "Case ID", required=True)):
        case = await self.db.get_case_by_id(case_id, ctx.guild.id)
        if not case:
            await ctx.respond("Case not found.", ephemeral=True)
            return
        if case["user_id"] != ctx.author.id:
            await ctx.respond("That's not your case.", ephemeral=True)
            return
        if not case["active"]:
            await ctx.respond("The case is already closed.", ephemeral=True)
            return
        await ctx.send_modal(AppealModal(case_id, self.db))

    @appeal.command(name="review", description="Shows pending appeals")
    @commands.has_permissions(moderate_members=True)
    async def appeal_review(self, ctx: discord.ApplicationContext):
        appeals = await self.db.get_appeals(ctx.guild.id, "pending")
        if not appeals:
            await ctx.respond("No pending appeals.", ephemeral=True)
            return
        embed = discord.Embed(title="Pending Appeals", color=discord.Color.blurple())
        for item in appeals[:5]:
            created_at = datetime.fromtimestamp(item["timestamp"], tz=timezone.utc)
            preview = f"{item['reason'][:50]}..." if len(item["reason"]) > 50 else item["reason"]
            embed.add_field(
                name=f"Appeal #{item['appeal_id']} - Case #{item['case_id']}",
                value=f"```ansi\n{BLUE}User: {item['user_id']}\nReason: {preview}\nDate: {created_at.strftime('%d.%m.%Y')}\u001b[0m```",
                inline=False,
            )
        await ctx.respond(embed=embed, view=AppealReviewView(appeals[0], self.db))

    @appeal.command(name="list", description="Shows all appeals")
    @commands.has_permissions(moderate_members=True)
    async def appeal_list(self, ctx: discord.ApplicationContext, status: Option(str, "Status", choices=["pending", "accepted", "denied"], required=False)):
        appeals = await self.db.get_appeals(ctx.guild.id, status)
        embed = discord.Embed(title=f"Appeals {f'({status})' if status else ''}", color=discord.Color.blurple())
        if not appeals:
            embed.description = f"```ansi\n{BLUE}No appeals found\u001b[0m```"
            await ctx.respond(embed=embed)
            return

        for item in appeals[:10]:
            created_at = datetime.fromtimestamp(item["timestamp"], tz=timezone.utc)
            embed.add_field(
                name=f"Appeal #{item['appeal_id']}",
                value=f"```ansi\n{BLUE}Case: #{item['case_id']}\nUser: {item['user_id']}\nStatus: {item['status']}\nDate: {created_at.strftime('%d.%m.%Y')}\u001b[0m```",
                inline=True,
            )
        await ctx.respond(embed=embed)
