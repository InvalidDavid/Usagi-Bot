import html

from utils.imports import *

logger = logging.getLogger("bot.anilist")


class AniList(commands.Cog):
    ANILIST_API_URL = "https://graphql.anilist.co"
    ANILIST_LOGO_URL = "https://anilist.co/img/logo_al.png"
    DEFAULT_EMBED_COLOR = discord.Color.embed_background()

    REQUEST_TIMEOUT_SECONDS = 10
    MAX_DESCRIPTION_WORDS = 45

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._session: Optional[aiohttp.ClientSession] = None

    async def cog_load(self) -> None:
        await self._get_session()

    def cog_unload(self) -> None:
        if self._session is not None and not self._session.closed:
            asyncio.create_task(self._session.close())

        self._session = None

    async def _close_session(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()

        self._session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.REQUEST_TIMEOUT_SECONDS)
            self._session = aiohttp.ClientSession(timeout=timeout)

        return self._session

    async def search_anilist(self, name: str, media_type: str) -> dict | None:
        query = """
        query ($search: String!, $type: MediaType) {
            Page(page: 1, perPage: 10) {
                media(search: $search, type: $type, sort: POPULARITY_DESC) {
                    id
                    siteUrl
                    title {
                        romaji
                        english
                        native
                    }
                    description(asHtml: true)
                    genres
                    coverImage {
                        large
                        color
                    }
                    format
                    averageScore
                    startDate {
                        year
                        month
                        day
                    }
                }
            }
        }
        """

        payload = {
            "query": query,
            "variables": {
                "search": name,
                "type": media_type,
            },
        }

        try:
            session = await self._get_session()

            async with session.post(self.ANILIST_API_URL, json=payload) as response:
                if response.status != 200:
                    logger.warning(
                        "AniList request failed | status=%s | media_type=%s | search=%s",
                        response.status,
                        media_type,
                        name,
                    )
                    return None

                body = await response.json(content_type=None)

        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            logger.exception(
                "AniList request crashed | media_type=%s | search=%s",
                media_type,
                name,
            )
            return None

        if not isinstance(body, dict):
            return None

        media_items = body.get("data", {}).get("Page", {}).get("media")
        if not isinstance(media_items, list) or not media_items:
            return None

        media = media_items[0]
        if not isinstance(media, dict):
            return None

        title_data = media.get("title")
        if not isinstance(title_data, dict):
            title_data = {}

        title = (
            title_data.get("english")
            or title_data.get("romaji")
            or title_data.get("native")
            or "Unknown Title"
        )

        start_date_data = media.get("startDate")
        if not isinstance(start_date_data, dict):
            start_date_data = {}

        year = start_date_data.get("year")
        month = start_date_data.get("month") or 1
        day = start_date_data.get("day") or 1

        start_date = None
        if year:
            start_date = f"{year}-{month:02d}-{day:02d}"

        cover_image = media.get("coverImage")
        if not isinstance(cover_image, dict):
            cover_image = {}

        media_id = media.get("id")
        cover_url = f"https://img.anili.st/media/{media_id}"

        genres = media.get("genres")
        if not isinstance(genres, list):
            genres = []

        return {
            "id": media_id,
            "title": title,
            "url": media.get("siteUrl"),
            "desc": media.get("description") or "",
            "genres": genres,
            "cover": cover_url,
            "format": media.get("format") or "Unknown",
            "score": media.get("averageScore"),
            "color": cover_image.get("color"),
            "start_date": start_date,
        }

    @staticmethod
    def clean_description(text: str) -> str:
        if not text:
            return "No description available."

        text = html.unescape(text)

        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"</p>\s*<p>", "\n\n", text, flags=re.IGNORECASE)
        text = re.sub(r"</?p>", "", text, flags=re.IGNORECASE)
        text = re.sub(r"</?i>", "", text, flags=re.IGNORECASE)
        text = re.sub(r"</?b>", "", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text)

        text = re.sub(r"\n{3,}", "\n\n", text)
        cleaned = text.strip()

        return cleaned or "No description available."

    @staticmethod
    def truncate_description(text: str, url: str | None, max_words: int = 45) -> str:
        words = text.split()
        if len(words) <= max_words:
            return text

        short = " ".join(words[:max_words])
        if url:
            return f"{short}... [(more)]({url})"

        return f"{short}..."

    @staticmethod
    def format_start_date(start_date: str | None) -> str:
        if not start_date:
            return "Unknown"

        try:
            dt = datetime.strptime(start_date, "%Y-%m-%d")
            return dt.strftime("%d %B, %Y")
        except ValueError:
            return start_date

    @staticmethod
    def parse_embed_color(color_hex: str | None) -> discord.Color:
        if not color_hex:
            return AniList.DEFAULT_EMBED_COLOR

        try:
            return discord.Color(int(color_hex.lstrip("#"), 16))
        except ValueError:
            return AniList.DEFAULT_EMBED_COLOR

    def build_embed(self, media: dict) -> discord.Embed:
        date_text = self.format_start_date(media.get("start_date"))

        desc = self.clean_description(media.get("desc", ""))
        desc = self.truncate_description(
            desc,
            media.get("url"),
            self.MAX_DESCRIPTION_WORDS,
        )

        genres = ", ".join(media.get("genres", [])) if media.get("genres") else "Unknown"
        color = self.parse_embed_color(media.get("color"))

        description_parts = [f"*{genres}*"]

        if media.get("score") is not None:
            description_parts.append(f"**Score:** {media['score']}/100")

        description_parts.append(desc)

        embed = discord.Embed(
            title=media.get("title", "Unknown Title"),
            url=media.get("url"),
            description="\n\n".join(description_parts),
            color=color,
        )

        if media.get("cover"):
            embed.set_image(url=media["cover"])

        embed.set_footer(
            text=f"AniList • {media.get('format', 'Unknown')} • {date_text}",
            icon_url=self.ANILIST_LOGO_URL,
        )

        return embed

    @slash_command(name="search", description="Search anime or manga on AniList")
    async def search(
        self,
        ctx: discord.ApplicationContext,
        media_type: Option(
            str,
            "Choose type",
            choices=[
                OptionChoice("Anime", "ANIME"),
                OptionChoice("Manga", "MANGA"),
            ],
        ),
        title: Option(str, "Anime or manga name"),
    ) -> None:
        await ctx.defer()

        media = await self.search_anilist(title, media_type)
        if not media:
            await ctx.followup.send("No results found.")
            return

        embed = self.build_embed(media)
        await ctx.followup.send(embed=embed)


def setup(bot: commands.Bot) -> None:
    bot.add_cog(AniList(bot))
