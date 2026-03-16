from __future__ import annotations

import discord
from discord.ui import Button, Select, View


class HelpView(View):
    def __init__(self, embeds: list[discord.Embed], page_info: dict[int, dict] | None = None):
        super().__init__(timeout=60)
        self.embeds = embeds
        self.current_page = 0
        self.page_info = page_info or {}
        self.prev_button = Button(label="⬅️", style=discord.ButtonStyle.secondary)
        self.next_button = Button(label="➡️", style=discord.ButtonStyle.secondary)
        self.prev_button.callback = self.prev_page
        self.next_button.callback = self.next_page
        self.select_menu = Select(
            placeholder="Select category...",
            options=self._build_options()[:25],
        )
        self.select_menu.callback = self.select_category
        self.add_item(self.select_menu)
        self.add_item(self.prev_button)
        self.add_item(self.next_button)
        self.update_buttons()

    def _build_options(self) -> list[discord.SelectOption]:
        options = []
        for index, embed in enumerate(self.embeds):
            title = embed.title or "Unknown"
            name = title.split("📂 ")[-1].split(" (Page")[0].split(" Commands")[0]
            page_meta = self.page_info.get(index)
            if page_meta and page_meta["total_pages"] > 1:
                name = f"{name} (Pg {page_meta['page']}/{page_meta['total_pages']})"
            label = f"{name[:97]}..." if len(name) > 100 else name
            options.append(
                discord.SelectOption(
                    label=label,
                    value=str(index),
                    description=f"{len(embed.fields)} Commands",
                )
            )
        return options

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if hasattr(self, "message"):
            await self.message.edit(view=self)

    async def prev_page(self, interaction: discord.Interaction):
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    async def next_page(self, interaction: discord.Interaction):
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    async def select_category(self, interaction: discord.Interaction):
        self.current_page = int(self.select_menu.values[0])
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    def update_buttons(self):
        self.prev_button.disabled = self.current_page <= 0
        self.next_button.disabled = self.current_page >= len(self.embeds) - 1
        for option in self.select_menu.options:
            option.default = option.value == str(self.current_page)
