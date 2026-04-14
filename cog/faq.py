
# small faq system which uses the new v2 components of discord buttons, dropdown menu
# if u dont rly understand how this all works maybe use this website as it shows ur it better: https://discord.builders/pycord-python-code-generator

from utils.imports import *

class FaqCategorySelect(discord.ui.DesignerView):
    def __init__(self, category: str):
        self.category = category

        if category == "general":
            self.faqs = {
                "faq_1": {
                    "number": 1,
                    "question": "Will there be an iOS version?",
                    "answer": "> No.",
                },
                "faq_2": {
                    "number": 2,
                    "question": "Will Usagi ever be on the Google Play Store?",
                    "answer": "> No.",
                },
                "faq_3": {
                    "number": 3,
                    "question": "Can Usagi read Light Novels?",
                    "answer": "> No.",
                },
                "faq_4": {
                    "number": 4,
                    "question": "Can Usagi stream Anime?",
                    "answer": "> No.",
                },
                "faq_5": {
                    "number": 5,
                    "question": "Can Usagi sync between devices?",
                    "answer": "> Yes.",
                },
                "faq_6": {
                    "number": 6,
                    "question": "Can I apply backups from Tachiyomi to Usagi?",
                    "answer": "> Possibly, but not officially.",
                },
            }
            title = "# General FAQ"

        elif category == "sources":
            self.faqs = {
                "faq_1": {
                    "number": 1,
                    "question": "What are some recommended sources? What source is the best? What is the replacement for source X? Where to read manga Y?",
                    "answer": "> No.",
                },
                "faq_2": {
                    "number": 2,
                    "question": "I'm having an issue with X source",
                    "answer": "> No. That's not our fault.",
                },
            }
            title = "# Sources FAQ"

        else:
            self.faqs = {
                "faq_1": {
                    "number": 1,
                    "question": "Why does Usagi no longer integrate sources like Kotatsu did before?",
                    "answer":
                        """I decided to remove the library that has built-in Online sources for the following reasons:
> 1. DMCA violation: This is a strong VIOLATION of copyrighted content, causing many applications to be forced to close like Tachiyomi, Kotatsu* before.
> 2. Disadvantage: Users always feel uncomfortable when frequently encountering reading source problems. They are forced to wait until the next app update is released so the problem can be fixed.
> 3. Development: Programmers / Contributors have always found it difficult to run Tests on previous applications, they did not have many options. Most of them follow previous testing methods such as running directly on the integrated library (cannot test all cases) OR they are forced to build test applications (like Kotatsu Dev) to be able to test content after implement.
> 4. Forced removal of reported content: According to #39 on the old integrated library, some content was forced to be taken down at the owner's request, making it impossible for users to continue accessing that content.
> 5. Privacy: In some cases, some content has been hidden / encrypted by the owner, and you are allowed to exploit it by the owner. But the old built-in library is an open source library based on the GPL-3.0 license, which requires the library's source code to be completely public. From there, passwords, hidden tokens, decryption methods, etc. will be forced to be made public on the source code, allowing others to exploit them.

-# *Kotatsu is said to be a branch of Tachiyomi based on document number 8 of Kakao Ent. (P. Cok)
                        """,
                },
                "faq_2": {
                    "number": 2,
                    "question": "Can Usagi work without a Plugin?",
                    "answer": "> Yes. Usagi works as an offline manga reader, able to read .CBZ files, manga image folders and even PDF* files\n>\n> *in the future, soon",
                },
                "faq_3": {
                    "number": 3,
                    "question": "Does Usagi have anything to do with other apps?",
                    "answer": "> Usagi is a standalone / another fork of Kotatsu, not relying on any other application. I got ideas from many applications, but it's not related to any application.",
                },
                "faq_4": {
                    "number": 4,
                    "question": "Who created Usagi? Which team / project does it belong to?",
                    "answer": "> <@954613690638929970>. Usagi is a product of the Yumemi™ project.",
                },
                "faq_5": {
                    "number": 5,
                    "question": "Does Usagi have anything to do with YakaTeam or any other organization?",
                    "answer": "> Usagi has nothing to do with YakaTeam, Redo or any other organization. Usagi itself can operate independently without involving any libraries / organizations outside of Usagi (except for open source libraries for Usagi development).",
                },
            }
            title = "# Other FAQ"

        options = [
            discord.SelectOption(
                label=faq["question"][:100],
                value=key,
                description=f"FAQ #{faq['number']}",
            )
            for key, faq in self.faqs.items()
        ]

        self.select = discord.ui.Select(
            custom_id=f"faq_select_{category}",
            placeholder="Select one or more FAQs",
            min_values=1,
            max_values=len(options),
            options=options,
        )
        self.select.callback = self.select_callback

        components = [
            discord.ui.Container(
                discord.ui.TextDisplay(content=title),
                discord.ui.ActionRow(self.select),
                color=discord.Color.embed_background(),
            )
        ]

        super().__init__(*components, timeout=None)

    async def select_callback(self, interaction: discord.Interaction):
        selected_values = self.select.values

        lines = []
        for key in selected_values:
            faq = self.faqs.get(key)
            if not faq:
                continue
            lines.append(f"**{faq['number']}. {faq['question']}**\n{faq['answer']}")

        message = "\n\n".join(lines) if lines else "No FAQ found."
        # py-cord bug which resets the dropdown without rly editing sth, dont change it unless it got fixxed
        await interaction.response.edit_message()
        await interaction.followup.send(message, ephemeral=True)


class FaqButtons(discord.ui.DesignerView):
    def __init__(self):
        self.general_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="General FAQ",
            custom_id="button_general",
        )
        self.general_button.callback = self.general_callback

        self.sources_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Sources FAQ",
            custom_id="button_sources",
        )
        self.sources_button.callback = self.sources_callback

        self.other_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Other FAQ",
            custom_id="button_other",
        )
        self.other_button.callback = self.other_callback

        components: list[discord.ui.Item[discord.ui.DesignerView]] = [
            discord.ui.Container(
                discord.ui.TextDisplay(content="# FAQ"),

                discord.ui.Separator(divider=True, spacing=discord.SeparatorSpacingSize.small,),
                discord.ui.TextDisplay(content="## General"),
                discord.ui.Section(
                    discord.ui.TextDisplay(content=
                    """
1. Will there be an iOS version?
2. Will Usagi ever be on the Google Play Store?
3. Can Usagi read Light Novels?
4. Can Usagi stream Anime?
5. Can Usagi sync between devices?
6. Can I apply backups from Tachiyomi to Usagi?
                    """
                    ),
                    accessory=self.general_button,
                ),

                discord.ui.Separator(divider=True, spacing=discord.SeparatorSpacingSize.small, ),
                discord.ui.TextDisplay(content="## Sources"),

                discord.ui.Section(
                    discord.ui.TextDisplay(content=
                    """
1. What are some recommended sources? What source is the best? What is the replacement for source X? Where to read manga Y?
2. I'm having an issue with X source
                    """),
                    accessory=self.sources_button,
                ),

                discord.ui.Separator(divider=True, spacing=discord.SeparatorSpacingSize.small,),
                discord.ui.TextDisplay(content="## Other"),

                discord.ui.Section(
                    discord.ui.TextDisplay(
                        content=
                        """
1. Why does Usagi no longer integrate sources like Kotatsu did before?
2. Can Usagi work without a Plugin?
3. Does Usagi have anything to do with other apps?
4. Who created Usagi? Which team / project does it belong to?
5. Does Usagi have anything to do with YakaTeam or any other organization?
                        """),
                    accessory=self.other_button,
                ),

                discord.ui.Separator(divider=True, spacing=discord.SeparatorSpacingSize.small,),
                discord.ui.TextDisplay(content="-# Press the buttons for the answers. ©️ Usagi"),
                color=discord.Color.embed_background(),
            ),
        ]
        super().__init__(*components, timeout=None)

    async def general_callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            view=FaqCategorySelect("general"),
            ephemeral=True,
        )

    async def sources_callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            view=FaqCategorySelect("sources"),
            ephemeral=True,
        )

    async def other_callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            view=FaqCategorySelect("other"),
            ephemeral=True,
        )


class FAQ(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._view_registered = False

    @commands.Cog.listener()
    async def on_ready(self):
        if not self._view_registered:
            self.bot.add_view(FaqButtons())
            self._view_registered = True


    @slash_command()
    @commands.is_owner()
    async def faq(self, ctx: discord.ApplicationContext) -> None:
        await ctx.respond("...", ephemeral=True)
        await ctx.channel.send(view=FaqButtons())


def setup(bot):
    bot.add_cog(FAQ(bot))
