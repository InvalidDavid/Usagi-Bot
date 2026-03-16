from datetime import datetime

import discord
from discord.commands import Option, OptionChoice, slash_command
from discord.ext import commands

from internal.services.anilist import AniListMediaType, autocomplete_media_titles, search_media
from internal.utils.text import strip_html, truncate_words


async def anilist_title_autocomplete(ctx: discord.AutocompleteContext) -> list[OptionChoice]:
    media_type = ctx.options.get("media_type")
    suggestions = await autocomplete_media_titles(ctx.value or "", media_type)
    return [OptionChoice(item["label"], item["value"]) for item in suggestions]


class AniListCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @slash_command(name="search", description="Search Anime or Manga on AniList")
    async def search(
        self,
        ctx: discord.ApplicationContext,
        media_type: Option(AniListMediaType, "Choose type"),
        title: Option(
            str,
            "Anime or Manga name",
            autocomplete=anilist_title_autocomplete,
        ),
    ):
        await ctx.defer()
        media = await search_media(title, media_type)
        if not media:
            await ctx.respond("No results found.")
            return

        date_text = "Unknown"
        if media["start_date"]:
            try:
                date_text = datetime.strptime(media["start_date"], "%Y-%m-%d").strftime("%d %B, %Y")
            except ValueError:
                date_text = media["start_date"]

        description = truncate_words(strip_html(media["description"]), 45, media["url"])
        genres = ", ".join(media["genres"]) if media["genres"] else "Unknown"
        color = int((media["color"] or "#2f3136").lstrip("#"), 16)

        embed = discord.Embed(
            title=media["title"],
            url=media["url"],
            description=f"*{genres}*\n\n{description}",
            color=color,
        )
        if media["cover"]:
            embed.set_image(url=media["cover"])
        embed.set_footer(
            text=f"AniList • {media['format']} • {date_text}",
            icon_url="https://anilist.co/img/logo_al.png",
        )
        await ctx.respond(embed=embed)


def setup(bot):
    bot.add_cog(AniListCog(bot))
