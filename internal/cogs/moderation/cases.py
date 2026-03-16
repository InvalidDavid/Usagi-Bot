from datetime import datetime, timezone

import discord
from discord.commands import Option

from internal.utils.ansi import BLUE, GREEN, YELLOW
from internal.utils.embeds import add_ansi_field
from internal.views.moderation_cases import CaseView

from .groups import mod
from .helpers import action_embed, add_member_field


class CaseCommands:
    @mod.command(name="clear", description="Deletes messages")
    async def clear(self, ctx: discord.ApplicationContext, amount: Option(int, "How many?", min_value=1, max_value=100, required=True), member: Option(discord.Member, "Only from this user", required=False, default=None)):
        await ctx.defer(ephemeral=True)
        deleted = await ctx.channel.purge(limit=amount, check=(lambda message: member is None or message.author == member))
        embed = action_embed("Messages deleted", discord.Color.blue(), f"```ansi\n{BLUE}{len(deleted)} messages were cleaned up\u001b[0m```")
        if member:
            add_member_field(embed, "From user", member, BLUE)
        await ctx.respond(embed=embed, ephemeral=True)
        await self.log_action(ctx.guild, embed)

    @mod.command(name="warnings", description="Shows all warnings of someone")
    async def warnings(self, ctx: discord.ApplicationContext, member: discord.Member):
        warnings = await self.db.get_warnings(ctx.guild.id, member.id)
        embed = action_embed(f"Warnings for {member.display_name}", discord.Color.orange())
        add_ansi_field(embed, "Count", str(len(warnings)), color=YELLOW, inline=True)
        if warnings:
            for index, warning in enumerate(warnings[:10], start=1):
                created_at = datetime.fromtimestamp(warning["timestamp"], tz=timezone.utc)
                add_ansi_field(embed, f"Warning #{index}", f"Reason: {warning['reason']}\nDate: {created_at.strftime('%d.%m.%Y %H:%M')}", color=YELLOW)
        else:
            embed.description = f"```ansi\n{BLUE}Clean record, no warnings\u001b[0m```"
        await ctx.respond(embed=embed)

    @mod.command(name="clearwarnings", description="Deletes all warnings from someone")
    async def clearwarnings(self, ctx: discord.ApplicationContext, member: discord.Member):
        warnings = await self.db.get_warnings(ctx.guild.id, member.id)
        if not warnings:
            await ctx.respond("They don't have any warnings anyway.", ephemeral=True)
            return
        await self.db.clear_warnings(ctx.guild.id, member.id)
        embed = action_embed(
            "Warnings cleared",
            discord.Color.green(),
            f"```ansi\n{GREEN}All warnings from {member.mention} have been removed\u001b[0m```",
        )
        add_ansi_field(embed, "Cleared", f"{len(warnings)} total", color=GREEN)
        await ctx.respond(embed=embed)
        await self.log_action(ctx.guild, embed)

    @mod.command(name="case", description="Shows details of a case")
    async def case(self, ctx: discord.ApplicationContext, case_id: Option(int, "Case ID", required=True)):
        case = await self.db.get_case_by_id(case_id, ctx.guild.id)
        if not case:
            await ctx.respond("Case not found.", ephemeral=True)
            return

        created_at = datetime.fromtimestamp(case["timestamp"], tz=timezone.utc)
        embed = discord.Embed(title=f"Case #{case_id}", color=discord.Color.blurple(), timestamp=created_at)
        add_ansi_field(embed, "Action", case["action_type"].upper(), color=BLUE, inline=True)
        add_ansi_field(embed, "Status", "Active" if case["active"] else "Closed", color=BLUE, inline=True)
        add_ansi_field(embed, "User", f"ID: {case['user_id']}", color=BLUE)
        add_ansi_field(embed, "Mod", f"ID: {case['moderator_id']}", color=BLUE, inline=True)
        add_ansi_field(embed, "Reason", case["reason"], color=BLUE)
        if case["duration"]:
            add_ansi_field(embed, "Duration", f"{case['duration'] // 60} minutes", color=BLUE, inline=True)
        await ctx.respond(embed=embed)

    @mod.command(name="cases", description="Shows all cases")
    async def cases(self, ctx: discord.ApplicationContext, member: Option(discord.Member, "From which user?", required=False, default=None), active_only: Option(bool, "Only active cases", required=False, default=False)):
        await ctx.defer()
        cases = await self.db.get_cases(ctx.guild.id, member.id if member else None, active_only)
        if not cases:
            await ctx.respond("No cases found.", ephemeral=True)
            return
        view = CaseView(cases)
        await ctx.respond(embed=view.build_embed(), view=view)

    @mod.command(name="closecase", description="Closes a case")
    async def closecase(self, ctx: discord.ApplicationContext, case_id: Option(int, "Case ID", required=True)):
        case = await self.db.get_case_by_id(case_id, ctx.guild.id)
        if not case:
            await ctx.respond("Case not found.", ephemeral=True)
            return
        if not case["active"]:
            await ctx.respond("It's already closed.", ephemeral=True)
            return
        await self.db.close_case(case_id, ctx.guild.id)
        embed = action_embed("Case closed", discord.Color.green(), f"```ansi\n{GREEN}Case #{case_id} is now closed\u001b[0m```")
        await ctx.respond(embed=embed)
        await self.log_action(ctx.guild, embed)

    @mod.command(name="quarantine", description="Quarantines someone")
    async def quarantine(self, ctx: discord.ApplicationContext, member: discord.Member, reason: Option(str, "Reason?", required=False, default="Suspicious")):
        config = await self.db.get_mod_config(ctx.guild.id)
        quarantine_role_id = None if not config else config.get("quarantine_role_id")
        quarantine_role = ctx.guild.get_role(quarantine_role_id) if quarantine_role_id else None
        if not quarantine_role:
            await ctx.respond("No quarantine role set up.", ephemeral=True)
            return
        try:
            await member.add_roles(quarantine_role, reason=reason)
        except (discord.Forbidden, discord.HTTPException):
            await ctx.respond("Couldn't assign role.", ephemeral=True)
            return
        embed = action_embed("Quarantined", discord.Color.dark_orange())
        add_member_field(embed, "Isolated", member, YELLOW)
        add_member_field(embed, "Mod", ctx.author, YELLOW, inline=True)
        add_ansi_field(embed, "Reason", reason, color=YELLOW)
        await ctx.respond(embed=embed)
        await self.log_action(ctx.guild, embed)

    @mod.command(name="unquarantine", description="Removes someone from quarantine")
    async def unquarantine(self, ctx: discord.ApplicationContext, member: discord.Member):
        config = await self.db.get_mod_config(ctx.guild.id)
        quarantine_role_id = None if not config else config.get("quarantine_role_id")
        quarantine_role = ctx.guild.get_role(quarantine_role_id) if quarantine_role_id else None
        if not quarantine_role:
            await ctx.respond("No quarantine role configured.", ephemeral=True)
            return
        if quarantine_role not in member.roles:
            await ctx.respond("They're not in quarantine.", ephemeral=True)
            return
        try:
            await member.remove_roles(quarantine_role)
        except (discord.Forbidden, discord.HTTPException):
            await ctx.respond("Couldn't remove role.", ephemeral=True)
            return
        embed = action_embed(
            "Quarantine lifted",
            discord.Color.green(),
            f"```ansi\n{GREEN}{member.mention} is free again\u001b[0m```",
        )
        await ctx.respond(embed=embed)
        await self.log_action(ctx.guild, embed)
