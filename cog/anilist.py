import re
import requests
import discord
from discord.ext import commands
from datetime import datetime

class AniListCog(commands.Cog):
    ANIME_RE = re.compile(r"`[\\s\\S]*?`|\\{(.*?)\\}")
    MANGA_RE = re.compile(r"<.*?https?:\\/\\/.*?>|<a?:.+?:\\d*>|`[\\s\\S]*?`|<(.*?)>")

    def __init__(self, bot: commands.Bot, search_channels=None, search_enabled=True):
        self.bot = bot
        self.search_channels = search_channels or []
        self.search_enabled = search_enabled

    def extract_names(self, pattern, content):
        matches = pattern.findall(content)
        out = []
        for m in matches:
            if isinstance(m, tuple):
                name = m[0] or m[1]
            else:
                name = m
            if not name:
                continue
            name = name.strip("`<> {}")
            if name:
                out.append(name.strip())
        return out

    def search_anilist(self, name, media_type, allow_adult=False):
        query = """
        query ($search: String!, $type: MediaType, $isAdult: Boolean = false) {
          Page(page: 1, perPage: 1) {
            media(search: $search, type: $type, isAdult: $isAdult) {
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
        variables = {"search": name, "type": media_type, "isAdult": allow_adult}
        resp = requests.post("https://graphql.anilist.co", json={"query": query, "variables": variables}, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json().get("data", {}).get("Page", {}).get("media")
        if not data:
            return None
        m = data[0]
        title = m["title"]["english"] or m["title"]["romaji"] or m["title"]["native"]
        start_date = None
        sd = m.get("startDate", {})
        if sd.get("year"):
            start_date = f"{sd['year']}-{sd['month']:02d}-{sd['day']:02d}"
        cover_url = f"https://img.anili.st/media/{m['id']}"
        return {
            "id": m["id"],
            "title": title,
            "url": m["siteUrl"],
            "desc": m.get("description", ""),
            "genres": m.get("genres", []),
            "cover_url": cover_url,
            "format": m.get("format", ""),
            "color": m.get("coverImage", {}).get("color", "#2f3136"),
            "score": m.get("averageScore"),
            "start_date": start_date
        }

    def clean_description(self, desc):
        if not desc:
            return "No description available"
        desc = re.sub(r"(?i)<br\s*/?>", "\n", desc)
        desc = re.sub(r"(?i)</?i>", "", desc)
        desc = re.sub(r"<.*?>", "", desc)
        desc = re.sub(r"\n{2,}", "\n\n", desc.strip())
        return desc

    def truncate_description(self, desc, url, max_words=45):
        words = desc.split()
        if len(words) <= max_words:
            return desc
        truncated = " ".join(words[:max_words])
        return f"{truncated}... [Read more]({url})"


    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not self.search_enabled or message.author.bot:
            return
        if self.search_channels and message.channel.id not in self.search_channels:
            return

        for pattern, media_type in [(self.ANIME_RE, "ANIME"), (self.MANGA_RE, "MANGA")]:
            names = self.extract_names(pattern, message.content)
            if not names:
                continue
            allow_adult = getattr(message.channel, "nsfw", False)

            media = self.search_anilist(names[0], media_type, allow_adult)
            if not media:
                return

            if media.get("start_date"):
                try:
                    dt = datetime.strptime(media["start_date"], "%Y-%m-%d")
                    start_date_formatted = dt.strftime("%d %B, %Y")  # z.B. 26 December, 2019
                except Exception:
                    start_date_formatted = media["start_date"]
            else:
                start_date_formatted = "N/A"


            genres = ", ".join(media["genres"])
            desc = self.clean_description(media["desc"])
            desc_truncated = self.truncate_description(desc, media["url"], max_words=45)

            embed = discord.Embed(
                title=media["title"],
                url=media["url"],
                description=f"***{genres}***\n{desc_truncated}",
                color=int(media["color"].lstrip("#"), 16)
            )
            embed.set_image(url=media["cover_url"])

            embed.set_footer(
                text=f"AniList • {media['format']} • Release: {start_date_formatted}",
                icon_url=message.author.display_avatar.url
            )
            await message.channel.send(embed=embed, reference=message)
            return

def setup(bot):
    bot.add_cog(AniListCog(bot))
