# tiktok got removed due mirror site got taken down
from collections import defaultdict
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse
from utils.imports import *

logger = logging.getLogger("bot.autolink")

MAX_MESSAGE_LENGTH = 1900
URL_RE = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)

YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$", re.ASCII)
REDDIT_ID_RE = re.compile(r"^[a-z0-9]+$", re.ASCII)


@dataclass(frozen=True, slots=True)
class LinkMatch:
    original_url: str
    mirror_url: str
    dedup_key: str


class Autolink(commands.Cog):
    CACHE_TTL_SECONDS = 300.0
    CACHE_SIZE_PER_GUILD = 500

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.processed_links_by_guild: dict[int, dict[str, float]] = defaultdict(dict)
        self.guild_locks: dict[int, asyncio.Lock] = {}
        self.cleanup_cache.start()

    def cog_unload(self) -> None:
        self.cleanup_cache.cancel()

    @tasks.loop(minutes=2)
    async def cleanup_cache(self) -> None:
        now = time.monotonic()
        for guild_id in list(self.processed_links_by_guild.keys()):
            self._prune_guild_cache(guild_id, now)

    @cleanup_cache.before_loop
    async def before_cleanup_cache(self) -> None:
        await self.bot.wait_until_ready()

    def _get_guild_lock(self, guild_id: int) -> asyncio.Lock:
        lock = self.guild_locks.get(guild_id)
        if lock is None:
            lock = asyncio.Lock()
            self.guild_locks[guild_id] = lock
        return lock

    def _prune_guild_cache(self, guild_id: int, now: float) -> None:
        guild_cache = self.processed_links_by_guild.get(guild_id)
        if not guild_cache:
            self.processed_links_by_guild.pop(guild_id, None)
            self.guild_locks.pop(guild_id, None)
            return

        expired_keys = [key for key, expires_at in guild_cache.items() if expires_at <= now]
        for key in expired_keys:
            guild_cache.pop(key, None)

        if len(guild_cache) > self.CACHE_SIZE_PER_GUILD:
            overflow = len(guild_cache) - self.CACHE_SIZE_PER_GUILD
            oldest_items = sorted(guild_cache.items(), key=lambda item: item[1])[:overflow]
            for key, _ in oldest_items:
                guild_cache.pop(key, None)

        if not guild_cache:
            self.processed_links_by_guild.pop(guild_id, None)
            self.guild_locks.pop(guild_id, None)

    def _is_processed(self, guild_id: int, dedup_key: str, now: float) -> bool:
        guild_cache = self.processed_links_by_guild.get(guild_id)
        if not guild_cache:
            return False

        expires_at = guild_cache.get(dedup_key)
        if expires_at is None:
            return False

        if expires_at <= now:
            guild_cache.pop(dedup_key, None)
            if not guild_cache:
                self.processed_links_by_guild.pop(guild_id, None)
                self.guild_locks.pop(guild_id, None)
            return False

        return True

    def _mark_processed(self, guild_id: int, dedup_key: str, now: float) -> None:
        self.processed_links_by_guild[guild_id][dedup_key] = now + self.CACHE_TTL_SECONDS

    def _clean_url_candidate(self, raw_url: str) -> str:
        cleaned = raw_url.rstrip(".,!?:;)]}>\"'")
        return cleaned.strip()

    def _extract_urls(self, content: str) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()

        for match in URL_RE.finditer(content):
            cleaned = self._clean_url_candidate(match.group(0))
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                urls.append(cleaned)

        return urls

    def _normalize_host(self, host: str) -> str:
        host = host.lower().strip(".")
        prefixes = ("www.", "m.", "old.", "mobile.")
        changed = True
        while changed:
            changed = False
            for prefix in prefixes:
                if host.startswith(prefix):
                    host = host[len(prefix):]
                    changed = True
        return host

    def _format_footer(self, original_url: str, message_url: str) -> str:
        return f"\n-# ↪ [Original Link ↗](<{original_url}>) • [Message]({message_url})"

    def _chunk_links_with_single_footer(
        self,
        links: list[LinkMatch],
        message_url: str,
    ) -> list[str]:
        chunks: list[str] = []
        current_links: list[LinkMatch] = []

        for link in links:
            candidate_links = current_links + [link]
            footer = self._format_footer(candidate_links[0].original_url, message_url)
            candidate_text = "\n".join(item.mirror_url for item in candidate_links) + footer

            if len(candidate_text) > MAX_MESSAGE_LENGTH:
                if not current_links:
                    logger.warning("Mirror entry too large, skipped: %s", link.mirror_url)
                    continue

                footer = self._format_footer(current_links[0].original_url, message_url)
                chunks.append("\n".join(item.mirror_url for item in current_links) + footer)
                current_links = [link]
            else:
                current_links = candidate_links

        if current_links:
            footer = self._format_footer(current_links[0].original_url, message_url)
            chunks.append("\n".join(item.mirror_url for item in current_links) + footer)

        return chunks

    def _extract_supported_links(self, content: str) -> list[LinkMatch]:
        matches_by_key: dict[str, LinkMatch] = {}

        for url in self._extract_urls(content):
            parsed = urlparse(url)
            match = self._build_link_match(url, parsed)
            if match is not None:
                matches_by_key.setdefault(match.dedup_key, match)

        return list(matches_by_key.values())

    def _build_link_match(self, original_url: str, parsed) -> LinkMatch | None:
        host = self._normalize_host(parsed.netloc)
        path = parsed.path or "/"
        path_parts = [part for part in path.split("/") if part]
        query = parse_qs(parsed.query, keep_blank_values=False)

        # Instagram direct post/reel URLs.
        if host == "instagram.com":
            return self._parse_instagram(original_url, path_parts)

        # YouTube direct video/live/post URLs.
        if host in {"youtube.com", "youtu.be"}:
            return self._parse_youtube(original_url, host, path_parts, query)

        # Reddit post/share/gallery URLs.
        if host in {"reddit.com", "redd.it"}:
            return self._parse_reddit(original_url, host, path_parts)

        # Facebook video/reel/watch URLs.
        if host in {"facebook.com", "fb.watch"}:
            return self._parse_facebook(original_url, host, path_parts, query)

        return None

    def _parse_instagram(self, original_url: str, path_parts: list[str]) -> LinkMatch | None:
        if len(path_parts) < 2:
            return None

        kind = path_parts[0].lower()
        shortcode = path_parts[1].strip()

        # Support common direct Instagram content routes.
        if kind == "reels":
            kind = "reel"

        if kind not in {"p", "reel", "tv"}:
            return None

        if not shortcode:
            return None

        canonical_path = f"/{kind}/{shortcode}"
        return LinkMatch(
            original_url=original_url,
            mirror_url=f"https://kkinstagram.com{canonical_path}",
            dedup_key=f"instagram:{canonical_path.lower()}",
        )

    def _parse_youtube(
        self,
        original_url: str,
        host: str,
        path_parts: list[str],
        query: dict[str, list[str]],
    ) -> LinkMatch | None:
        target: str | None = None
        target_type: str | None = None

        if host == "youtu.be":
            if path_parts:
                candidate = path_parts[0].strip()
                if YOUTUBE_ID_RE.fullmatch(candidate):
                    target = candidate
                    target_type = "video"

        elif host == "youtube.com":
            first = path_parts[0].lower() if path_parts else ""

            # Standard watch page.
            if first == "watch":
                candidate = query.get("v", [None])[0]
                if candidate and YOUTUBE_ID_RE.fullmatch(candidate):
                    target = candidate
                    target_type = "video"

            # Shorts route.
            elif first == "shorts" and len(path_parts) >= 2:
                candidate = path_parts[1].strip()
                if YOUTUBE_ID_RE.fullmatch(candidate):
                    target = candidate
                    target_type = "video"

            # Embed route.
            elif first == "embed" and len(path_parts) >= 2:
                candidate = path_parts[1].strip()
                if YOUTUBE_ID_RE.fullmatch(candidate):
                    target = candidate
                    target_type = "video"

            # Legacy /v/<id> route.
            elif first == "v" and len(path_parts) >= 2:
                candidate = path_parts[1].strip()
                if YOUTUBE_ID_RE.fullmatch(candidate):
                    target = candidate
                    target_type = "video"

            # Live route.
            elif first == "live" and len(path_parts) >= 2:
                candidate = path_parts[1].strip()
                if YOUTUBE_ID_RE.fullmatch(candidate):
                    target = candidate
                    target_type = "video"

        if target is None or target_type is None:
            return None

        if target_type == "video":
            return LinkMatch(
                original_url=original_url,
                mirror_url=f"https://koutube.com/watch?v={target}",
                dedup_key=f"youtube:{target.lower()}",
            )

        return LinkMatch(
            original_url=original_url,
            mirror_url=f"https://koutube.com/post/{target}",
            dedup_key=f"youtube-post:{target.lower()}",
        )

    def _parse_reddit(self, original_url: str, host: str, path_parts: list[str]) -> LinkMatch | None:
        if host == "redd.it":
            if not path_parts:
                return None

            post_id = path_parts[0].lower().strip()
            if not REDDIT_ID_RE.fullmatch(post_id):
                return None

            return LinkMatch(
                original_url=original_url,
                mirror_url=f"https://rxddit.com/comments/{post_id}",
                dedup_key=f"reddit:{post_id}",
            )

        # Shared short Reddit URL: /s/<id>
        if len(path_parts) >= 2 and path_parts[0].lower() == "s":
            share_id = path_parts[1].strip()
            if not share_id:
                return None

            return LinkMatch(
                original_url=original_url,
                mirror_url=f"https://rxddit.com/s/{share_id}",
                dedup_key=f"reddit-share:{share_id.lower()}",
            )

        # Gallery posts still map back to the post id.
        if len(path_parts) >= 2 and path_parts[0].lower() == "gallery":
            post_id = path_parts[1].lower().strip()
            if not REDDIT_ID_RE.fullmatch(post_id):
                return None

            return LinkMatch(
                original_url=original_url,
                mirror_url=f"https://rxddit.com/comments/{post_id}",
                dedup_key=f"reddit:{post_id}",
            )

        comments_index: int | None = None
        for i, part in enumerate(path_parts):
            if part.lower() == "comments":
                comments_index = i
                break

        if comments_index is None or comments_index + 1 >= len(path_parts):
            return None

        post_id = path_parts[comments_index + 1].lower().strip()
        if not REDDIT_ID_RE.fullmatch(post_id):
            return None

        return LinkMatch(
            original_url=original_url,
            mirror_url=f"https://rxddit.com/comments/{post_id}",
            dedup_key=f"reddit:{post_id}",
        )

    def _parse_facebook(
        self,
        original_url: str,
        host: str,
        path_parts: list[str],
        query: dict[str, list[str]],
    ) -> LinkMatch | None:
        if host == "fb.watch":
            if not path_parts:
                return None

            watch_id = path_parts[0].strip()
            if not watch_id:
                return None

            return LinkMatch(
                original_url=original_url,
                mirror_url=f"https://www.facebed.com/share/v/{watch_id}",
                dedup_key=f"facebook-watch:{watch_id.lower()}",
            )

        if not path_parts:
            return None

        first = path_parts[0].lower()

        # /watch/?v=<id> and /watch/live/?v=<id>
        if first == "watch":
            video_id = query.get("v", [None])[0]
            if video_id:
                return LinkMatch(
                    original_url=original_url,
                    mirror_url=f"https://www.facebed.com/watch?v={video_id}",
                    dedup_key=f"facebook:{video_id.lower()}",
                )
            return None

        # /reel/<id>
        if first == "reel" and len(path_parts) >= 2:
            reel_id = path_parts[1].strip()
            if reel_id:
                return LinkMatch(
                    original_url=original_url,
                    mirror_url=f"https://www.facebed.com/share/r/{reel_id}",
                    dedup_key=f"facebook-reel:{reel_id.lower()}",
                )

        # /videos/<id>
        if first == "videos" and len(path_parts) >= 2:
            video_id = path_parts[1].strip()
            if video_id:
                return LinkMatch(
                    original_url=original_url,
                    mirror_url=f"https://www.facebed.com/watch?v={video_id}",
                    dedup_key=f"facebook:{video_id.lower()}",
                )

        # /share/r/<id>
        if first == "share" and len(path_parts) >= 3 and path_parts[1].lower() == "r":
            reel_id = path_parts[2].strip()
            if reel_id:
                return LinkMatch(
                    original_url=original_url,
                    mirror_url=f"https://www.facebed.com/share/r/{reel_id}",
                    dedup_key=f"facebook-reel:{reel_id.lower()}",
                )

        # /share/v/<id>
        if first == "share" and len(path_parts) >= 3 and path_parts[1].lower() == "v":
            video_id = path_parts[2].strip()
            if video_id:
                return LinkMatch(
                    original_url=original_url,
                    mirror_url=f"https://www.facebed.com/share/v/{video_id}",
                    dedup_key=f"facebook-watch:{video_id.lower()}",
                )

        # /share/<id>
        if first == "share" and len(path_parts) >= 2 and path_parts[1].lower() not in {"r", "v"}:
            share_id = path_parts[1].strip()
            if share_id:
                return LinkMatch(
                    original_url=original_url,
                    mirror_url=f"https://www.facebed.com/watch?v={share_id}",
                    dedup_key=f"facebook:{share_id.lower()}",
                )

        # /<user>/videos/<id>
        if len(path_parts) >= 3 and path_parts[-2].lower() == "videos":
            video_id = path_parts[-1].strip()
            if video_id:
                return LinkMatch(
                    original_url=original_url,
                    mirror_url=f"https://www.facebed.com/watch?v={video_id}",
                    dedup_key=f"facebook:{video_id.lower()}",
                )

        return None

    async def _send_mirrors(self, message: discord.Message, links: Iterable[LinkMatch]) -> bool:
        links = list(links)
        if not links:
            return False

        chunks = self._chunk_links_with_single_footer(links, message.jump_url)
        if not chunks:
            return False

        try:
            for chunk in chunks:
                await message.reply(chunk, mention_author=False)
            return True

        except discord.Forbidden:
            logger.warning(
                "Missing permission to reply in guild=%s channel=%s",
                getattr(message.guild, "id", None),
                getattr(message.channel, "id", None),
            )
            return False

        except discord.HTTPException:
            logger.exception("Failed to send mirror reply")
            return False

    async def _suppress_embeds_if_possible(self, message: discord.Message, can_manage_messages: bool) -> None:
        if not can_manage_messages:
            return

        try:
            await message.edit(suppress=True)
        except discord.Forbidden:
            logger.warning(
                "Missing manage_messages permission in guild=%s channel=%s",
                getattr(message.guild, "id", None),
                getattr(message.channel, "id", None),
            )
        except discord.HTTPException:
            logger.exception("Failed to suppress embeds for message %s", message.id)

    def _get_me(self, guild: discord.Guild) -> discord.Member | None:
        if self.bot.user is None:
            return None

        me = guild.get_member(self.bot.user.id)
        if me is not None:
            return me

        return getattr(guild, "me", None)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        # Ignore bots and webhooks.
        if message.author.bot or message.webhook_id is not None:
            return

        if message.guild is None:
            return

        # Ignore non-user text messages.
        if not message.content or message.type != discord.MessageType.default:
            return

        me = self._get_me(message.guild)
        if me is None:
            return

        perms = message.channel.permissions_for(me)
        if not perms.send_messages:
            return

        links = self._extract_supported_links(message.content)
        if not links:
            return

        guild_id = message.guild.id
        lock = self._get_guild_lock(guild_id)
        now = time.monotonic()

        # Keep cache mutation inside the guild lock to avoid duplicate processing.
        async with lock:
            self._prune_guild_cache(guild_id, now)

            fresh_links = [
                link for link in links
                if not self._is_processed(guild_id, link.dedup_key, now)
            ]

            # Mark links before sending to reduce duplicate replies under concurrency.
            for link in fresh_links:
                self._mark_processed(guild_id, link.dedup_key, now)

        if not fresh_links:
            return

        sent = await self._send_mirrors(message, fresh_links)
        if not sent:
            # Rollback is intentionally skipped. A short-lived false dedupe is preferable
            # to duplicate mirror replies caused by concurrent sends.
            return

        await self._suppress_embeds_if_possible(message, perms.manage_messages)


def setup(bot: commands.Bot) -> None:
    bot.add_cog(Autolink(bot))
