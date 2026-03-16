from __future__ import annotations

from datetime import timedelta

import discord
from discord.commands import Option

from internal.utils.ansi import BLUE, GREEN, RED, YELLOW
from internal.utils.embeds import add_ansi_field

from .groups import mod
from .helpers import action_embed, add_member_field, ensure_manageable, safe_dm


class SanctionCommands:
    @mod.command(name="warn", description="Warns someone")
    async def warn(self, ctx: discord.ApplicationContext, member: discord.Member, reason: Option(str, "Reason?", required=False, default="No reason provided")):
        if not await ensure_manageable(ctx, member, "They're above you in hierarchy, can't do that."):
            return

        case_id = await self.db.add_case(ctx.guild.id, member.id, ctx.author.id, "warn", reason)
        await self.db.add_warning(ctx.guild.id, member.id, ctx.author.id, reason, case_id)
        warnings = await self.db.get_warnings(ctx.guild.id, member.id)

        embed = action_embed("Warning issued", discord.Color.orange())
        add_member_field(embed, "Offender", member, BLUE)
        add_member_field(embed, "Mod", ctx.author, BLUE, inline=True)
        add_ansi_field(embed, "Reason", reason, color=BLUE)
        add_ansi_field(embed, "Case ID", f"#{case_id}", color=BLUE, inline=True)
        add_ansi_field(embed, "Total Warnings", str(len(warnings)), color=YELLOW, inline=True)
        await ctx.respond(embed=embed)
        await self.log_action(ctx.guild, embed)
        await safe_dm(member, f"You received a warning on **{ctx.guild.name}**.\nReason: {reason}\nCase: #{case_id}")

        if not await self.should_auto_punish(ctx.guild.id, member.id):
            return
        config = await self.db.get_mod_config(ctx.guild.id)
        quarantine_role_id = None if not config else config.get("quarantine_role_id")
        quarantine_role = ctx.guild.get_role(quarantine_role_id) if quarantine_role_id else None
        if not quarantine_role:
            return
        try:
            await member.add_roles(quarantine_role, reason="Too many warnings collected")
        except (discord.Forbidden, discord.HTTPException):
            return
        auto_embed = action_embed(
            "Auto-punishment activated",
            discord.Color.red(),
            f"```ansi\n{RED}{member.mention} was automatically quarantined (too many warnings)\u001b[0m```",
        )
        await ctx.send(embed=auto_embed)

    @mod.command(name="kick", description="Kicks someone from the server")
    async def kick(self, ctx: discord.ApplicationContext, member: discord.Member, reason: Option(str, "Reason?", required=False, default="No reason provided")):
        if not await ensure_manageable(ctx, member, "They're above you, you can't kick them."):
            return

        case_id = await self.db.add_case(ctx.guild.id, member.id, ctx.author.id, "kick", reason)
        await safe_dm(member, f"You have been kicked from **{ctx.guild.name}**.\nReason: {reason}\nCase: #{case_id}\n\nBye!")
        try:
            await member.kick(reason=reason)
        except (discord.Forbidden, discord.HTTPException):
            await ctx.respond("Kick didn't work.", ephemeral=True)
            return

        embed = action_embed("User kicked", discord.Color.orange())
        add_member_field(embed, "Kicked", member, YELLOW)
        add_member_field(embed, "Mod", ctx.author, YELLOW, inline=True)
        add_ansi_field(embed, "Reason", reason, color=YELLOW)
        add_ansi_field(embed, "Case ID", f"#{case_id}", color=YELLOW, inline=True)
        await ctx.respond(embed=embed)
        await self.log_action(ctx.guild, embed)

    @mod.command(name="ban", description="Bans someone permanently")
    async def ban(self, ctx: discord.ApplicationContext, member: discord.Member, delete_days: Option(int, "Delete messages (days)", min_value=0, max_value=7, default=0), reason: Option(str, "Reason?", required=False, default="No reason provided")):
        if not await ensure_manageable(ctx, member, "Too powerful for you."):
            return

        case_id = await self.db.add_case(ctx.guild.id, member.id, ctx.author.id, "ban", reason)
        await safe_dm(member, f"You have been banned from **{ctx.guild.name}**.\nReason: {reason}\nCase: #{case_id}\n\nCya!")
        try:
            await member.ban(reason=reason, delete_message_days=delete_days)
        except (discord.Forbidden, discord.HTTPException):
            await ctx.respond("Ban didn't work.", ephemeral=True)
            return

        embed = action_embed("User banned", discord.Color.dark_red())
        add_member_field(embed, "Permanent ban issued", member, RED)
        add_member_field(embed, "Mod", ctx.author, RED, inline=True)
        add_ansi_field(embed, "Reason", reason, color=RED)
        add_ansi_field(embed, "Messages deleted", f"{delete_days} days", color=RED, inline=True)
        add_ansi_field(embed, "Case ID", f"#{case_id}", color=RED, inline=True)
        await ctx.respond(embed=embed)
        await self.log_action(ctx.guild, embed)

    @mod.command(name="unban", description="Unbans someone")
    async def unban(self, ctx: discord.ApplicationContext, user_id: Option(str, "User ID", required=True), reason: Option(str, "Reason?", required=False, default="Second chance")):
        try:
            user = await self.bot.fetch_user(int(user_id))
        except (ValueError, discord.NotFound, discord.HTTPException):
            await ctx.respond("Invalid user ID.", ephemeral=True)
            return

        try:
            await ctx.guild.unban(user, reason=reason)
        except (discord.Forbidden, discord.HTTPException):
            await ctx.respond("They're not banned or something went wrong.", ephemeral=True)
            return

        case_id = await self.db.add_case(ctx.guild.id, user.id, ctx.author.id, "unban", reason)
        embed = action_embed("Ban lifted", discord.Color.green())
        add_member_field(embed, "Welcome back", user, GREEN)
        add_member_field(embed, "Mod", ctx.author, GREEN, inline=True)
        add_ansi_field(embed, "Reason", reason, color=GREEN)
        add_ansi_field(embed, "Case ID", f"#{case_id}", color=GREEN, inline=True)
        await ctx.respond(embed=embed)
        await self.log_action(ctx.guild, embed)

    @mod.command(name="timeout", description="Times someone out")
    async def timeout(self, ctx: discord.ApplicationContext, member: discord.Member, duration: Option(int, "How long? (Minutes)", required=True), reason: Option(str, "Reason?", required=False, default="No reason provided")):
        if not await ensure_manageable(ctx, member, "Can't do that, they're above you."):
            return

        try:
            await member.timeout(timedelta(minutes=duration), reason=reason)
        except (discord.Forbidden, discord.HTTPException):
            await ctx.respond("Timeout didn't work.", ephemeral=True)
            return

        case_id = await self.db.add_case(ctx.guild.id, member.id, ctx.author.id, "timeout", reason, duration * 60)
        end_time = discord.utils.utcnow() + timedelta(minutes=duration)
        embed = action_embed("Timeout given", discord.Color.orange())
        add_member_field(embed, "Time out", member, YELLOW)
        add_member_field(embed, "Mod", ctx.author, YELLOW, inline=True)
        add_ansi_field(embed, "Duration", f"{duration} minutes", color=YELLOW, inline=True)
        embed.add_field(name="Ends", value=discord.utils.format_dt(end_time, "R"), inline=True)
        add_ansi_field(embed, "Reason", reason, color=YELLOW)
        add_ansi_field(embed, "Case ID", f"#{case_id}", color=YELLOW, inline=True)
        await ctx.respond(embed=embed)
        await self.log_action(ctx.guild, embed)
