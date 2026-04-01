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
    r'(https?://)(?:www\.)?reddit\.com/r/[\w\d_]+/comments/([a-z0-9]+)',
    re.IGNORECASE
)

REDDIT_SHORT_PATTERN = re.compile(
    r'(https?://)redd\.it/([a-z0-9]+)',
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

FACEBOOK_WATCH_PATTERN = re.compile(
    r'(https?://)(?:www\.)?facebook\.com/watch/\?v=([a-zA-Z0-9_-]+)',
    re.IGNORECASE
)

class Autolink(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.processed_links = set()
        self.cache_size = 100

    def _is_already_processed(self, content: str, author_id: int) -> bool:
        key = f"{author_id}:{hash(content)}"
        return key in self.processed_links

    def _mark_processed(self, content: str, author_id: int) -> None:
        key = f"{author_id}:{hash(content)}"
        self.processed_links.add(key)

        if len(self.processed_links) > self.cache_size:
            self.processed_links.clear()

    def _format_message(self, message, message_url: str, original_url: str) -> str:
        return f"\n-# ↪ [Original Link ↗](<{original_url}>) • [Message]({message_url})"

    async def _send_mirror(self, message: discord.Message, mirror_url: str, original_url: str) -> bool:
        try:
            footer = self._format_message(message, message.jump_url, original_url)
            await message.reply(f"{mirror_url}{footer}", mention_author=False)
            self._mark_processed(message.content, message.author.id)
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

        if self._is_already_processed(message.content, message.author.id):
            return

        content = message.content

        patterns = [
            (INSTAGRAM_REEL_PATTERN, lambda m: f"{m.group(1)}kkinstagram.com{m.group(2)}"),
            (INSTAGRAM_VIDEO_PATTERN, lambda m: f"{m.group(1)}kkinstagram.com{m.group(2)}"),
            (INSTAGRAM_PHOTO_PATTERN, lambda m: f"{m.group(1)}kkinstagram.com{m.group(2)}"),
            (YOUTUBE_VIDEO_PATTERN, lambda m: f"https://www.koutube.com/watch?v={m.group(2)}"),
            (YOUTUBE_SHORTS_PATTERN, lambda m: f"https://www.koutube.com/watch?v={m.group(2)}"),
            (YOUTUBE_SHORT_PATTERN, lambda m: f"https://www.koutube.com/watch?v={m.group(2)}"),
            (TIKTOK_PATTERN, lambda m: f"https://vxtiktok.com/video/{m.group(2)}"),
            (REDDIT_POST_PATTERN, lambda m: f"https://rxddit.com/comments/{m.group(2)}"),
            (REDDIT_SHORT_PATTERN, lambda m: f"https://rxddit.com/comments/{m.group(2)}"),
            (FACEBOOK_VIDEO_PATTERN, lambda m: f"https://www.facebed.com/watch?v={m.group(2)}"),
            (FACEBOOK_REEL_PATTERN, lambda m: f"https://www.facebed.com/share/r/{m.group(2)}"),
            (FACEBOOK_WATCH_PATTERN, lambda m: f"https://www.facebed.com/watch?v={m.group(2)}"),
            (FACEBOOK_SHARE_REEL_PATTERN, lambda m: f"https://www.facebed.com/share/r/{m.group(2)}"),
        ]

        for pattern, builder in patterns:
            match = pattern.search(content)
            if match:
                original_url = match.group(0)
                mirror_url = builder(match)

                await self._send_mirror(message, mirror_url, original_url)

                try:
                    await message.edit(suppress=True)
                except discord.Forbidden:
                    print(f"Missing 'manage_messages' permission to edit {message.author.name}'s message")
                except discord.HTTPException as e:
                    print(f"Failed to suppress embed: {e}")
                except Exception as e:
                    print(f"Unexpected error while suppressing embed: {e}")

                return

def setup(bot: commands.Bot) -> None:
    bot.add_cog(Autolink(bot))
