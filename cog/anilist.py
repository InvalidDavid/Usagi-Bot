import re
import requests
import discord
from discord.ext import commands
from discord.commands import slash_command, Option, OptionChoice
from datetime import datetime


class AniListCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def search_anilist(self, name, media_type):

        query = """
        query ($search: String!, $type: MediaType) {
          Page(page: 1, perPage: 1) {
            media(search: $search, type: $type) {
              id
              siteUrl
              title { romaji english native }
              description(asHtml: true)
              genres
              coverImage { large color }
              format
              averageScore
              startDate { year month day }
            }
          }
        }
        """

        variables = {
            "search": name,
            "type": media_type
        }

        r = requests.post(
            "https://graphql.anilist.co",
            json={"query": query, "variables": variables},
            timeout=10
        )

        if r.status_code != 200:
            return None

        data = r.json().get("data", {}).get("Page", {}).get("media")

        if not data:
            return None

        m = data[0]

        title = (
            m["title"]["english"]
            or m["title"]["romaji"]
            or m["title"]["native"]
        )

        sd = m.get("startDate", {})

        year = sd.get("year")
        month = sd.get("month") or 1
        day = sd.get("day") or 1

        start_date = None
        if year:
            start_date = f"{year}-{month:02d}-{day:02d}"

        return {
            "id": m["id"],
            "title": title,
            "url": m["siteUrl"],
            "desc": m.get("description", ""),
            "genres": m.get("genres", []),
            "cover": f"https://img.anili.st/media/{m['id']}",
            "format": m.get("format"),
            "score": m.get("averageScore"),
            "color": m.get("coverImage", {}).get("color"),
            "start_date": start_date
        }


    def clean_description(self, text):

        if not text:
            return "No description available."

        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
        text = re.sub(r"</?i>", "", text, flags=re.I)
        text = re.sub(r"<[^>]+>", "", text)

        return text.strip()



    def truncate_description(self, text, url, max_words=45):

        words = text.split()

        if len(words) <= max_words:
            return text

        short = " ".join(words[:max_words])

        return f"{short}... [(more)]({url})"



    @slash_command(name="search", description="Search Anime or Manga on AniList")
    async def search(
        self,
        ctx: discord.ApplicationContext,

        media_type: Option(
            str,
            "Choose type",
            choices=[
                OptionChoice("Anime", "ANIME"),
                OptionChoice("Manga", "MANGA")
            ]
        ),

        title: Option(str, "Anime or Manga name"),

    ):

        await ctx.defer()

        media = self.search_anilist(title, media_type)

        if not media:
            await ctx.respond("No results found.")
            return



        if media["start_date"]:
            try:
                dt = datetime.strptime(media["start_date"], "%Y-%m-%d")
                date_text = dt.strftime("%d %B, %Y")
            except:
                date_text = media["start_date"]
        else:
            date_text = "Unknown"



        desc = self.clean_description(media["desc"])
        desc = self.truncate_description(desc, media["url"], 45)


        genres = ", ".join(media["genres"]) if media["genres"] else "Unknown"



        color_hex = media["color"] or "#2f3136"
        color = int(color_hex.lstrip("#"), 16)



        embed = discord.Embed(
            title=media["title"],
            url=media["url"],
            description=f"*{genres}*\n\n{desc}",
            color=color
        )

        embed.set_image(url=media["cover"])

        embed.set_footer(
            text=f"AniList • {media['format']} • {date_text}",
            icon_url="https://anilist.co/img/logo_al.png"
        )


        await ctx.respond(embed=embed)


def setup(bot):
    bot.add_cog(AniListCog(bot))
