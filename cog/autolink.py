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
    r'(https?://)(?:www\.)?facebook\.com/.*/videos/(\d+)',
    re.IGNORECASE
)

FACEBOOK_REEL_PATTERN = re.compile(
    r'(https?://)(?:www\.)?facebook\.com/reel/(\d+)',
    re.IGNORECASE
)

FACEBOOK_WATCH_PATTERN = re.compile(
    r'(https?://)(?:www\.)?facebook\.com/watch/\?v=(\d+)',
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

        ig_reel = INSTAGRAM_REEL_PATTERN.search(content)
        if ig_reel:
            original_url = ig_reel.group(0)
            mirror_url = f"{ig_reel.group(1)}kkinstagram.com{ig_reel.group(2)}"
            await self._send_mirror(message, mirror_url, original_url)
            await message.edit(suppress=True)
            return

        ig_video = INSTAGRAM_VIDEO_PATTERN.search(content)
        if ig_video:
            original_url = ig_video.group(0)
            mirror_url = f"{ig_video.group(1)}kkinstagram.com{ig_video.group(2)}"
            await self._send_mirror(message, mirror_url, original_url)
            await message.edit(suppress=True)
            return

        ig_photo = INSTAGRAM_PHOTO_PATTERN.search(content)
        if ig_photo:
            original_url = ig_photo.group(0)
            mirror_url = f"{ig_photo.group(1)}kkinstagram.com{ig_photo.group(2)}"
            await self._send_mirror(message, mirror_url, original_url)
            await message.edit(suppress=True)
            return

        yt_video = YOUTUBE_VIDEO_PATTERN.search(content)
        if yt_video:
            original_url = yt_video.group(0)
            video_id = yt_video.group(2)
            mirror_url = f"https://koutube.com/watch?v={video_id}"
            await self._send_mirror(message, mirror_url, original_url)
            await message.edit(suppress=True)
            return

        yt_shorts = YOUTUBE_SHORTS_PATTERN.search(content)
        if yt_shorts:
            original_url = yt_shorts.group(0)
            video_id = yt_shorts.group(2)
            mirror_url = f"https://koutube.com/watch?v={video_id}"
            await self._send_mirror(message, mirror_url, original_url)
            await message.edit(suppress=True)
            return

        yt_short = YOUTUBE_SHORT_PATTERN.search(content)
        if yt_short:
            original_url = yt_short.group(0)
            video_id = yt_short.group(2)
            mirror_url = f"https://koutube.com/watch?v={video_id}"
            await self._send_mirror(message, mirror_url, original_url)
            await message.edit(suppress=True)
            return

        tiktok = TIKTOK_PATTERN.search(content)
        if tiktok:
            original_url = tiktok.group(0)
            video_id = tiktok.group(2)
            mirror_url = f"https://vxtiktok.com/video/{video_id}"
            await self._send_mirror(message, mirror_url, original_url)
            await message.edit(suppress=True)
            return

        reddit = REDDIT_POST_PATTERN.search(content)
        if reddit:
            original_url = reddit.group(0)
            post_id = reddit.group(2)
            mirror_url = f"https://rxddit.com/comments/{post_id}"
            await self._send_mirror(message, mirror_url, original_url)
            await message.edit(suppress=True)
            return

        reddit_short = REDDIT_SHORT_PATTERN.search(content)
        if reddit_short:
            original_url = reddit_short.group(0)
            post_id = reddit_short.group(2)
            mirror_url = f"https://rxddit.com/comments/{post_id}"
            await self._send_mirror(message, mirror_url, original_url)
            await message.edit(suppress=True)
            return

        fb_video = FACEBOOK_VIDEO_PATTERN.search(content)
        if fb_video:
            original_url = fb_video.group(0)
            video_id = fb_video.group(2)
            mirror_url = f"https://facebed.com/watch?v={video_id}"
            await self._send_mirror(message, mirror_url, original_url)
            await message.edit(suppress=True)
            return

        fb_reel = FACEBOOK_REEL_PATTERN.search(content)
        if fb_reel:
            original_url = fb_reel.group(0)
            video_id = fb_reel.group(2)
            mirror_url = f"https://facebed.com/watch?v={video_id}"
            await self._send_mirror(message, mirror_url, original_url)
            await message.edit(suppress=True)
            return

def setup(bot: commands.Bot) -> None:
    bot.add_cog(Autolink(bot))
