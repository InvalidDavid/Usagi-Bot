
# this system is only managable under 100 server due to cache issue, might wanna add a db aiosqlite and settings

from collections import defaultdict, OrderedDict
from utils.imports import *

INSTAGRAM_REEL_PATTERN = re.compile(
    r'(https?://)(?:www\.|m\.)?instagram\.com(/reel/[a-zA-Z0-9_-]+)',
    re.IGNORECASE
)

INSTAGRAM_VIDEO_PATTERN = re.compile(
    r'(https?://)(?:www\.|m\.)?instagram\.com(/tv/[a-zA-Z0-9_-]+)',
    re.IGNORECASE
)

INSTAGRAM_PHOTO_PATTERN = re.compile(
    r'(https?://)(?:www\.|m\.)?instagram\.com(/p/[a-zA-Z0-9_-]+)',
    re.IGNORECASE
)

YOUTUBE_VIDEO_PATTERN = re.compile(
    r'(https?://)(?:www\.|m\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]+)',
    re.IGNORECASE
)

YOUTUBE_SHORTS_PATTERN = re.compile(
    r'(https?://)(?:www\.)?youtube\.com/shorts/([a-zA-Z0-9_-]+)',
    re.IGNORECASE
)

YOUTUBE_SHORT_PATTERN = re.compile(
    r'(https?://)youtu\.be/([a-zA-Z0-9_-]+)',
    re.IGNORECASE
)

TIKTOK_PATTERN = re.compile(
    r'(https?://)(?:www\.)?tiktok\.com/@[\w.-]+/video/(\d+)',
    re.IGNORECASE
)

REDDIT_POST_PATTERN = re.compile(
    r'(https?://)(?:www\.|old\.)?reddit\.com/(?:r/[\w\d_]+/)?comments/([a-z0-9]+)(?:/[^\s?#]*)?',
    re.IGNORECASE
)

REDDIT_SHORT_PATTERN = re.compile(
    r'(https?://)redd\.it/([a-z0-9]+)',
    re.IGNORECASE
)

REDDIT_SHARE_PATTERN = re.compile(
    r'(https?://)(?:www\.|old\.)?reddit\.com/s/([a-zA-Z0-9]+)',
    re.IGNORECASE
)

FACEBOOK_VIDEO_PATTERN = re.compile(
    r'(https?://)(?:www\.)?facebook\.com/(?:[^/\s]+/)?videos/(\d+)',
    re.IGNORECASE
)

FACEBOOK_REEL_PATTERN = re.compile(
    r'(https?://)(?:www\.)?facebook\.com/reel/([a-zA-Z0-9_-]+)/?',
    re.IGNORECASE
)

FACEBOOK_SHARE_REEL_PATTERN = re.compile(
    r'(https?://)(?:www\.)?facebook\.com/share/r/([a-zA-Z0-9_-]+)/?',
    re.IGNORECASE
)

FACEBOOK_SHARE_GENERIC_PATTERN = re.compile(
    r'(https?://)(?:www\.|m\.)?facebook\.com/share/(\d+)(?:[/?][^\s]*)?',
    re.IGNORECASE
)

FACEBOOK_WATCH_PATTERN = re.compile(
    r'(https?://)(?:www\.)?facebook\.com/watch/\?v=([a-zA-Z0-9_-]+)',
    re.IGNORECASE
)


class Autolink(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # duration per guild link block after it was sended
        self.cache_ttl_seconds = 300  # 5 Minuten

        # cache size max depends
        self.cache_size_per_guild = 500

        # guild_id -> OrderedDict[normalized_url, expires_at] never change that
        self.processed_links_by_guild: dict[int, OrderedDict[str, float]] = defaultdict(OrderedDict)

        self.patterns = [
            (INSTAGRAM_REEL_PATTERN, lambda m: f"{m.group(1)}kkinstagram.com{m.group(2)}"),
            (INSTAGRAM_VIDEO_PATTERN, lambda m: f"{m.group(1)}kkinstagram.com{m.group(2)}"),
            (INSTAGRAM_PHOTO_PATTERN, lambda m: f"{m.group(1)}kkinstagram.com{m.group(2)}"),
            (YOUTUBE_VIDEO_PATTERN, lambda m: f"https://koutube.com/watch?v={m.group(2)}"),
            (YOUTUBE_SHORTS_PATTERN, lambda m: f"https://koutube.com/watch?v={m.group(2)}"),
            (YOUTUBE_SHORT_PATTERN, lambda m: f"https://koutube.com/watch?v={m.group(2)}"),
            (TIKTOK_PATTERN, lambda m: f"https://vxtiktok.com/video/{m.group(2)}"),
            (REDDIT_POST_PATTERN, lambda m: f"https://rxddit.com/comments/{m.group(2)}"),
            (REDDIT_SHORT_PATTERN, lambda m: f"https://rxddit.com/comments/{m.group(2)}"),
            (REDDIT_SHARE_PATTERN, lambda m: f"https://rxddit.com/s/{m.group(2)}"),
            (FACEBOOK_VIDEO_PATTERN, lambda m: f"https://www.facebed.com/watch?v={m.group(2)}"),
            (FACEBOOK_REEL_PATTERN, lambda m: f"https://www.facebed.com/share/r/{m.group(2)}"),
            (FACEBOOK_WATCH_PATTERN, lambda m: f"https://www.facebed.com/watch?v={m.group(2)}"),
            (FACEBOOK_SHARE_REEL_PATTERN, lambda m: f"https://www.facebed.com/share/r/{m.group(2)}"),
            (FACEBOOK_SHARE_GENERIC_PATTERN, lambda m: f"https://www.facebed.com/watch?v={m.group(2)}"),
        ]

    def _get_guild_id(self, message: discord.Message) -> int:
        return message.guild.id if message.guild else 0

    def _normalize_url(self, url: str) -> str:
        return url.strip().lower().rstrip("/")

    def _cleanup_guild_cache(self, guild_id: int) -> None:
        now = time.time()
        guild_cache = self.processed_links_by_guild[guild_id]

        expired_keys = [key for key, expires_at in guild_cache.items() if expires_at <= now]
        for key in expired_keys:
            del guild_cache[key]

        while len(guild_cache) > self.cache_size_per_guild:
            guild_cache.popitem(last=False)

        if not guild_cache:
            self.processed_links_by_guild.pop(guild_id, None)

    def _is_already_processed(self, message: discord.Message, original_url: str) -> bool:
        guild_id = self._get_guild_id(message)
        self._cleanup_guild_cache(guild_id)

        guild_cache = self.processed_links_by_guild[guild_id]
        key = self._normalize_url(original_url)
        expires_at = guild_cache.get(key)

        if expires_at is None:
            return False

        if expires_at <= time.time():
            del guild_cache[key]
            if not guild_cache:
                self.processed_links_by_guild.pop(guild_id, None)
            return False

        guild_cache.move_to_end(key)
        return True

    def _mark_processed(self, message: discord.Message, original_url: str) -> None:
        guild_id = self._get_guild_id(message)
        guild_cache = self.processed_links_by_guild[guild_id]
        key = self._normalize_url(original_url)

        guild_cache[key] = time.time() + self.cache_ttl_seconds
        guild_cache.move_to_end(key)

        self._cleanup_guild_cache(guild_id)

    def _format_message(self, message: discord.Message, message_url: str, original_url: str) -> str:
        return f"\n-# ↪ [Original Link ↗](<{original_url}>) • [Message]({message_url})"

    def _find_first_supported_link(self, content: str):
        for pattern, builder in self.patterns:
            match = pattern.search(content)
            if match:
                original_url = match.group(0)
                mirror_url = builder(match)
                return original_url, mirror_url
        return None, None

    async def _send_mirror(
        self,
        message: discord.Message,
        mirror_url: str,
        original_url: str
    ) -> bool:
        try:
            footer = self._format_message(message, message.jump_url, original_url)
            await message.reply(f"{mirror_url}{footer}", mention_author=False)
            self._mark_processed(message, original_url)
            return True
        except discord.HTTPException as e:
            print(f"Failed to send mirror: {e}")
            return False
        except Exception as e:
            print(f"Unexpected error sending mirror: {e}")
            return False

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.content or message.reference:
            return

        original_url, mirror_url = self._find_first_supported_link(message.content)
        if not original_url:
            return

        if self._is_already_processed(message, original_url):
            return

        sent = await self._send_mirror(message, mirror_url, original_url)
        if not sent:
            return

        try:
            await message.edit(suppress=True)
        except discord.Forbidden:
            print(
                f"Missing 'manage_messages' permission to suppress embeds in "
                f"{message.guild.name if message.guild else 'DM'}"
            )
        except discord.HTTPException as e:
            print(f"Failed to suppress embed: {e}")
        except Exception as e:
            print(f"Unexpected error while suppressing embed: {e}")


def setup(bot: commands.Bot) -> None:
    bot.add_cog(Autolink(bot))
