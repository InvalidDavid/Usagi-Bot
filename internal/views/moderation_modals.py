from __future__ import annotations

import discord
from discord.ui import InputText, Modal

from internal.utils.ansi import GREEN, block


class AppealModal(Modal):
    def __init__(self, case_id: int, repository):
        super().__init__(title=f"Appeal for Case #{case_id}")
        self.case_id = case_id
        self.repository = repository
        self.add_item(
            InputText(
                label="Reason",
                placeholder="Why should this case be overturned?",
                style=discord.InputTextStyle.long,
                required=True,
                min_length=10,
                max_length=1000,
            )
        )

    async def callback(self, interaction: discord.Interaction):
        appeal_id = await self.repository.add_appeal(
            self.case_id,
            interaction.guild.id,
            interaction.user.id,
            self.children[0].value,
        )
        embed = discord.Embed(
            title="Appeal submitted",
            description=block(
                f"Your appeal for Case #{self.case_id} has been received.\nAppeal ID: #{appeal_id}\n\nWe'll take a look at it!",
                GREEN,
            ),
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
