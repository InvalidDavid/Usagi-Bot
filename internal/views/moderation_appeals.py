from __future__ import annotations

import discord
from discord.ui import Button, View

from internal.utils.ansi import GREEN, RED, block


class AppealReviewView(View):
    def __init__(self, appeal: dict, repository):
        super().__init__(timeout=None)
        self.appeal = appeal
        self.repository = repository

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def accept_appeal(self, button: Button, interaction: discord.Interaction):
        await self.repository.update_appeal(
            self.appeal["appeal_id"],
            "accepted",
            interaction.user.id,
            "Appeal was accepted",
        )
        await self.repository.close_case(self.appeal["case_id"], self.appeal["guild_id"])
        for child in self.children:
            child.disabled = True
        embed = discord.Embed(
            title="Appeal accepted",
            description=block(
                f"Appeal #{self.appeal['appeal_id']} has been accepted.\nCase #{self.appeal['case_id']} is now closed.",
                GREEN,
            ),
            color=discord.Color.green(),
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.danger)
    async def deny_appeal(self, button: Button, interaction: discord.Interaction):
        await self.repository.update_appeal(
            self.appeal["appeal_id"],
            "denied",
            interaction.user.id,
            "Appeal was denied",
        )
        for child in self.children:
            child.disabled = True
        embed = discord.Embed(
            title="Appeal denied",
            description=block(
                f"Appeal #{self.appeal['appeal_id']} was unfortunately not accepted.",
                RED,
            ),
            color=discord.Color.red(),
        )
        await interaction.response.edit_message(embed=embed, view=self)
