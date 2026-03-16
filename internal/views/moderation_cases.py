from __future__ import annotations

from datetime import datetime, timezone

import discord
from discord.ui import Button, View

from internal.utils.ansi import BLUE, block


class CaseView(View):
    PAGE_SIZE = 5

    def __init__(self, cases: list[dict], current_page: int = 0):
        super().__init__(timeout=180)
        self.cases = cases
        self.current_page = current_page
        self.max_pages = (len(cases) - 1) // self.PAGE_SIZE if cases else 0
        self._update_buttons()

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="Case Overview",
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc),
        )
        if not self.cases:
            embed.description = "No cases yet, everything's chill here."
            return embed

        start_index = self.current_page * self.PAGE_SIZE
        current_cases = self.cases[start_index:start_index + self.PAGE_SIZE]
        for case in current_cases:
            created_at = datetime.fromtimestamp(case["timestamp"], tz=timezone.utc)
            status = "Active" if case["active"] else "Closed"
            value = (
                f"User: {case['user_id']}\n"
                f"Mod: {case['moderator_id']}\n"
                f"Reason: {case['reason']}\n"
                f"Status: {status}\n"
                f"Date: {created_at.strftime('%d.%m.%Y %H:%M')}"
            )
            embed.add_field(
                name=f"Case #{case['case_id']} - {case['action_type'].upper()}",
                value=block(value, BLUE),
                inline=False,
            )
        embed.set_footer(text=f"Page {self.current_page + 1} of {self.max_pages + 1}")
        return embed

    def _update_buttons(self):
        self.previous_page.disabled = self.current_page == 0
        self.next_page.disabled = self.current_page >= self.max_pages

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous_page(self, button: Button, interaction: discord.Interaction):
        self.current_page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_page(self, button: Button, interaction: discord.Interaction):
        self.current_page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)
