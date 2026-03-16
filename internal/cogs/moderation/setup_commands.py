from __future__ import annotations

import discord
from discord.commands import Option

from internal.utils.ansi import BLUE, GREEN

from .groups import automod, badword, setup_group
from .helpers import action_embed


class SetupCommands:
    @setup_group.command(name="logchannel", description="Sets the log channel")
    async def setup_logchannel(self, ctx: discord.ApplicationContext, channel: discord.TextChannel):
        await self.db.set_mod_config(ctx.guild.id, log_channel_id=channel.id)
        embed = action_embed("Log channel set", discord.Color.green(), f"```ansi\n{GREEN}Logs will now go to {channel.mention}\u001b[0m```")
        await ctx.respond(embed=embed)

    @setup_group.command(name="quarantinerole", description="Sets the quarantine role")
    async def setup_quarantinerole(self, ctx: discord.ApplicationContext, role: discord.Role):
        await self.db.set_mod_config(ctx.guild.id, quarantine_role_id=role.id)
        embed = action_embed("Quarantine role set", discord.Color.green(), f"```ansi\n{GREEN}{role.name} is now the quarantine role\u001b[0m```")
        await ctx.respond(embed=embed)

    @setup_group.command(name="autopunish", description="Configures auto-punishment")
    async def setup_autopunish(self, ctx: discord.ApplicationContext, enabled: Option(bool, "On or off?", required=True), threshold: Option(int, "From how many warnings?", min_value=1, max_value=10, default=3)):
        await self.db.set_mod_config(ctx.guild.id, auto_punish=1 if enabled else 0, warn_threshold=threshold)
        status = "enabled" if enabled else "disabled"
        embed = action_embed(
            "Auto-punishment configured",
            discord.Color.green(),
            f"```ansi\n{GREEN}Auto-punishment is now {status}\nTriggers after {threshold} warnings\u001b[0m```",
        )
        await ctx.respond(embed=embed)

    @automod.command(name="configure", description="Sets up AutoMod")
    async def automod_configure(self, ctx: discord.ApplicationContext, spam: Option(bool, "Spam protection", required=False, default=False), links: Option(bool, "Link filter", required=False, default=False), invites: Option(bool, "Invite filter", required=False, default=False), caps: Option(bool, "Caps filter", required=False, default=False), action: Option(str, "What should happen?", choices=["warn", "kick"], default="warn")):
        await self.db.set_automod_config(
            ctx.guild.id,
            spam_enabled=1 if spam else 0,
            links_enabled=1 if links else 0,
            invites_enabled=1 if invites else 0,
            caps_enabled=1 if caps else 0,
            action_type=action,
        )
        features = [name for enabled, name in ((spam, "Spam Protection"), (links, "Link Filter"), (invites, "Invite Filter"), (caps, "Caps Filter")) if enabled]
        embed = discord.Embed(title="AutoMod configured", color=discord.Color.green())
        embed.add_field(name="Active Features", value=f"```ansi\n{GREEN}{', '.join(features) if features else 'Nothing active'}\u001b[0m```", inline=False)
        embed.add_field(name="Action on violation", value=f"```ansi\n{GREEN}{action}\u001b[0m```", inline=True)
        await ctx.respond(embed=embed)

    @automod.command(name="settings", description="Shows AutoMod settings")
    async def automod_settings(self, ctx: discord.ApplicationContext):
        config = await self.db.get_automod_config(ctx.guild.id)
        embed = discord.Embed(title="AutoMod Settings", color=discord.Color.blurple())
        if not config:
            embed.description = f"```ansi\n{BLUE}AutoMod is not set up yet\u001b[0m```"
            await ctx.respond(embed=embed)
            return

        settings = (
            ("Spam Protection", "On" if config.get("spam_enabled") else "Off"),
            ("Link Filter", "On" if config.get("links_enabled") else "Off"),
            ("Invite Filter", "On" if config.get("invites_enabled") else "Off"),
            ("Caps Filter", "On" if config.get("caps_enabled") else "Off"),
            ("Action", config.get("action_type") or "warn"),
            ("Spam Threshold", f"{config.get('spam_threshold') or 5} messages"),
        )
        for name, value in settings:
            embed.add_field(name=name, value=f"```ansi\n{BLUE}{value}\u001b[0m```", inline=True)
        await ctx.respond(embed=embed)

    @badword.command(name="add", description="Adds a banned word")
    async def badword_add(self, ctx: discord.ApplicationContext, word: Option(str, "Which word?", required=True), severity: Option(int, "How severe? (1-3)", min_value=1, max_value=3, default=1)):
        await self.db.add_badword(ctx.guild.id, word, severity)
        embed = action_embed("Word added to blacklist", discord.Color.green(), f"```ansi\n{GREEN}'{word}' is now banned\nSeverity: {severity}\u001b[0m```")
        await ctx.respond(embed=embed, ephemeral=True)

    @badword.command(name="remove", description="Removes a banned word")
    async def badword_remove(self, ctx: discord.ApplicationContext, word: Option(str, "Which word?", required=True)):
        await self.db.remove_badword(ctx.guild.id, word)
        embed = action_embed("Word removed from blacklist", discord.Color.green(), f"```ansi\n{GREEN}'{word}' is now allowed again\u001b[0m```")
        await ctx.respond(embed=embed, ephemeral=True)

    @badword.command(name="list", description="Shows all banned words")
    async def badword_list(self, ctx: discord.ApplicationContext):
        words = await self.db.get_badwords(ctx.guild.id)
        embed = discord.Embed(title="Banned Words", color=discord.Color.blurple())
        if words:
            lines = [f"{word['word']} (Severity: {word['severity']})" for word in words]
            embed.description = f"```ansi\n{BLUE}{chr(10).join(lines)}\u001b[0m```"
        else:
            embed.description = f"```ansi\n{BLUE}No words blocked\u001b[0m```"
        await ctx.respond(embed=embed, ephemeral=True)
