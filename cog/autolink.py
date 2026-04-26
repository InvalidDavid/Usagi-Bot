from dataclasses import dataclass
from utils.imports import *

logger = logging.getLogger("bot.autolink")

MAX_MESSAGE_LENGTH = 1900
URL_RE = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)

YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$", re.ASCII)
REDDIT_ID_RE = re.compile(r"^[a-z0-9]+$", re.ASCII)
INSTAGRAM_SHORTCODE_RE = re.compile(r"^[A-Za-z0-9_-]+$", re.ASCII)

PlatformParser: TypeAlias = Callable[
    [str, str, list[str], dict[str, list[str]]],
    "LinkMatch | None",
]


@dataclass(frozen=True, slots=True)
class LinkMatch:
    original_url: str
    mirror_url: str
    dedup_key: str

class Autolink(commands.Cog):
    CACHE_TTL_SECONDS = 300.0
    CACHE_SIZE_PER_GUILD = 500
    MAX_FACEBOOK_ID_LENGTH = 20

    MIRROR_DOMAINS = {
        "instagram": "kkinstagram.com",
        "youtube": "koutube.com",
        "youtube_short": "koutu.be",
        "reddit": "rxddit.com",
        "facebook": "www.facebed.com",
    }

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.processed_links_by_guild: dict[int, dict[str, float]] = defaultdict(dict)
        self.guild_locks: dict[int, asyncio.Lock] = {}

    async def cog_load(self) -> None:
        if not self.cleanup_cache.is_running():
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
            oldest_keys = [
                key
                for key, _ in heapq.nsmallest(
                    overflow,
                    guild_cache.items(),
                    key=lambda item: item[1],
                )
            ]
            for key in oldest_keys:
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
        cleaned = raw_url.strip()

        if cleaned.startswith("<"):
            cleaned = cleaned[1:]

        cleaned = cleaned.rstrip(".,!?:;)]}>\"'")
        cleaned = cleaned.rstrip(">")
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
            if not link.mirror_url:
                logger.warning("Empty mirror URL for original: %s", link.original_url)
                continue

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
            try:
                parsed = urlparse(url)
                match = self._build_link_match(url, parsed)
            except Exception:
                logger.debug("Failed to parse candidate URL: %s", url, exc_info=True)
                continue

            if match is not None:
                matches_by_key.setdefault(match.dedup_key, match)

        if matches_by_key:
            logger.debug("Extracted %d supported link(s) from content", len(matches_by_key))

        return list(matches_by_key.values())

    def _build_link_match(self, original_url: str, parsed: ParseResult) -> LinkMatch | None:
        host = self._normalize_host(parsed.netloc)
        if not host:
            return None

        path = parsed.path or "/"
        path_parts = [part for part in path.split("/") if part]
        query = parse_qs(parsed.query, keep_blank_values=False)

        parser = self._get_platform_parser(host)
        if parser is None:
            return None

        return parser(original_url, host, path_parts, query)

    def _get_platform_parser(self, host: str) -> PlatformParser | None:
        parsers: dict[str, PlatformParser] = {
            "instagram.com": lambda url, _host, parts, _query: self._parse_instagram(url, parts),
            "youtube.com": self._parse_youtube,
            "youtu.be": self._parse_youtube,
            "reddit.com": lambda url, host_name, parts, _query: self._parse_reddit(url, host_name, parts),
            "redd.it": lambda url, host_name, parts, _query: self._parse_reddit(url, host_name, parts),
            "facebook.com": self._parse_facebook,
            "fb.watch": self._parse_facebook,
        }
        return parsers.get(host)

    def _make_link_match(self, original_url: str, mirror_url: str, dedup_key: str) -> LinkMatch:
        return LinkMatch(
            original_url=original_url,
            mirror_url=mirror_url,
            dedup_key=dedup_key,
        )

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

        if not shortcode or not INSTAGRAM_SHORTCODE_RE.fullmatch(shortcode):
            logger.debug("Invalid Instagram shortcode: %s", shortcode)
            return None

        canonical_path = f"/{kind}/{shortcode}"
        return self._make_link_match(
            original_url=original_url,
            mirror_url=f"https://{self.MIRROR_DOMAINS['instagram']}{canonical_path}",
            dedup_key=f"instagram:{canonical_path.lower()}",
        )

    def _parse_youtube(
        self,
        original_url: str,
        host: str,
        path_parts: list[str],
        query: dict[str, list[str]],
    ) -> LinkMatch | None:
        parsed_target = self._extract_youtube_target(host, path_parts, query)
        if parsed_target is None:
            return None

        video_id, is_shorts, prefer_short_domain = parsed_target

        if prefer_short_domain:
            mirror_url = f"https://{self.MIRROR_DOMAINS['youtube_short']}/watch?v={video_id}"
            if is_shorts:
                mirror_url += "?shorts"
        else:
            mirror_url = f"https://{self.MIRROR_DOMAINS['youtube']}/watch?v={video_id}"
            if is_shorts:
                mirror_url += "&shorts"

        return self._make_link_match(
            original_url=original_url,
            mirror_url=mirror_url,
            dedup_key=f"youtube:{video_id.lower()}",
        )

    def _extract_youtube_target(
        self,
        host: str,
        path_parts: list[str],
        query: dict[str, list[str]],
    ) -> tuple[str, bool, bool] | None:
        if host == "youtu.be":
            if not path_parts:
                return None

            candidate = path_parts[0].strip()
            if YOUTUBE_ID_RE.fullmatch(candidate):
                return candidate, False, True
            return None

        if host != "youtube.com":
            return None

        first = path_parts[0].lower() if path_parts else ""

        extractors: dict[str, Callable[[], tuple[str, bool, bool] | None]] = {
            "watch": lambda: self._youtube_watch_target(query),
            "shorts": lambda: self._youtube_shorts_target(path_parts),
            "embed": lambda: self._youtube_path_target(path_parts, 1),
            "v": lambda: self._youtube_path_target(path_parts, 1),
            "live": lambda: self._youtube_path_target(path_parts, 1),
        }

        extractor = extractors.get(first)
        if extractor is None:
            if first:
                logger.debug("Unknown YouTube path: /%s", first)
            return None

        return extractor()

    def _youtube_watch_target(self, query: dict[str, list[str]]) -> tuple[str, bool, bool] | None:
        video_id = self._validated_youtube_id(query.get("v", [None])[0])
        if video_id is None:
            return None

        # this is for the mirror website ?shorts, YouTube itself doenst have it.
        shorts_list = query.get("shorts", [])
        is_shorts = bool(shorts_list) and shorts_list[0].lower() not in {"0", "false", "no"}
        return video_id, is_shorts, False

    def _youtube_shorts_target(self, path_parts: list[str]) -> tuple[str, bool, bool] | None:
        video_id = self._path_part_youtube_id(path_parts, 1)
        if video_id is None:
            return None

        return video_id, True, False

    def _youtube_path_target(self, path_parts: list[str], index: int) -> tuple[str, bool, bool] | None:
        video_id = self._path_part_youtube_id(path_parts, index)
        if video_id is None:
            return None

        return video_id, False, False

    def _validated_youtube_id(self, candidate: str | None) -> str | None:
        if candidate and YOUTUBE_ID_RE.fullmatch(candidate):
            return candidate
        return None

    def _path_part_youtube_id(self, path_parts: list[str], index: int) -> str | None:
        if len(path_parts) <= index:
            return None
        return self._validated_youtube_id(path_parts[index].strip())

    def _valid_facebook_id(self, candidate: str | None) -> bool:
        return bool(candidate) and len(candidate) <= self.MAX_FACEBOOK_ID_LENGTH

    def _parse_reddit(self, original_url: str, host: str, path_parts: list[str]) -> LinkMatch | None:
        if host == "redd.it":
            if not path_parts:
                return None

            post_id = path_parts[0].lower().strip()
            if not REDDIT_ID_RE.fullmatch(post_id):
                return None

            return self._make_link_match(
                original_url=original_url,
                mirror_url=f"https://{self.MIRROR_DOMAINS['reddit']}/comments/{post_id}",
                dedup_key=f"reddit:{post_id}",
            )

        # Shared short Reddit URL: /s/<id>
        if len(path_parts) >= 2 and path_parts[0].lower() == "s":
            share_id = path_parts[1].strip()
            if not share_id:
                return None

            return self._make_link_match(
                original_url=original_url,
                mirror_url=f"https://{self.MIRROR_DOMAINS['reddit']}/s/{share_id}",
                dedup_key=f"reddit-share:{share_id.lower()}",
            )

        # Shared subreddit/user short URL:
        # /r/<subreddit>/s/<id>
        # /u/<user>/s/<id>
        # /user/<user>/s/<id>
        if (
            len(path_parts) >= 4
            and path_parts[0].lower() in {"r", "u", "user"}
            and path_parts[2].lower() == "s"
        ):
            share_id = path_parts[3].strip()
            if not share_id:
                return None

            return self._make_link_match(
                original_url=original_url,
                mirror_url=f"https://{self.MIRROR_DOMAINS['reddit']}/s/{share_id}",
                dedup_key=f"reddit-share:{share_id.lower()}",
            )

        # Gallery posts still map back to the post id.
        if len(path_parts) >= 2 and path_parts[0].lower() == "gallery":
            post_id = path_parts[1].lower().strip()
            if not REDDIT_ID_RE.fullmatch(post_id):
                return None

            return self._make_link_match(
                original_url=original_url,
                mirror_url=f"https://{self.MIRROR_DOMAINS['reddit']}/comments/{post_id}",
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

        return self._make_link_match(
            original_url=original_url,
            mirror_url=f"https://{self.MIRROR_DOMAINS['reddit']}/comments/{post_id}",
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
            if not self._valid_facebook_id(watch_id):
                return None

            return self._make_link_match(
                original_url=original_url,
                mirror_url=f"https://{self.MIRROR_DOMAINS['facebook']}/share/v/{watch_id}",
                dedup_key=f"facebook-watch:{watch_id.lower()}",
            )

        if not path_parts:
            return None

        first = path_parts[0].lower()

        handlers: dict[str, Callable[[], LinkMatch | None]] = {
            "watch": lambda: self._facebook_watch_query_match(original_url, query),
            "reel": lambda: self._facebook_reel_match(original_url, path_parts),
            "videos": lambda: self._facebook_videos_match(original_url, path_parts),
            "share": lambda: self._facebook_share_match(original_url, path_parts),
        }

        handler = handlers.get(first)
        if handler is not None:
            match = handler()
            if match is not None:
                return match

        # /<user>/videos/<id>
        if len(path_parts) >= 3 and path_parts[-2].lower() == "videos":
            video_id = path_parts[-1].strip()
            if self._valid_facebook_id(video_id):
                return self._make_link_match(
                    original_url=original_url,
                    mirror_url=f"https://{self.MIRROR_DOMAINS['facebook']}/watch?v={video_id}",
                    dedup_key=f"facebook:{video_id.lower()}",
                )

        return None

    def _facebook_watch_query_match(
        self,
        original_url: str,
        query: dict[str, list[str]],
    ) -> LinkMatch | None:
        video_id = query.get("v", [None])[0]
        if not self._valid_facebook_id(video_id):
            return None

        return self._make_link_match(
            original_url=original_url,
            mirror_url=f"https://{self.MIRROR_DOMAINS['facebook']}/watch?v={video_id}",
            dedup_key=f"facebook:{video_id.lower()}",
        )

    def _facebook_reel_match(self, original_url: str, path_parts: list[str]) -> LinkMatch | None:
        if len(path_parts) < 2:
            return None

        reel_id = path_parts[1].strip()
        if not self._valid_facebook_id(reel_id):
            return None

        return self._make_link_match(
            original_url=original_url,
            mirror_url=f"https://{self.MIRROR_DOMAINS['facebook']}/share/r/{reel_id}",
            dedup_key=f"facebook-reel:{reel_id.lower()}",
        )

    def _facebook_videos_match(self, original_url: str, path_parts: list[str]) -> LinkMatch | None:
        if len(path_parts) < 2:
            return None

        video_id = path_parts[1].strip()
        if not self._valid_facebook_id(video_id):
            return None

        return self._make_link_match(
            original_url=original_url,
            mirror_url=f"https://{self.MIRROR_DOMAINS['facebook']}/watch?v={video_id}",
            dedup_key=f"facebook:{video_id.lower()}",
        )

    def _facebook_share_match(self, original_url: str, path_parts: list[str]) -> LinkMatch | None:
        # /share/r/<id>
        if len(path_parts) >= 3 and path_parts[1].lower() == "r":
            reel_id = path_parts[2].strip()
            if self._valid_facebook_id(reel_id):
                return self._make_link_match(
                    original_url=original_url,
                    mirror_url=f"https://{self.MIRROR_DOMAINS['facebook']}/share/r/{reel_id}",
                    dedup_key=f"facebook-reel:{reel_id.lower()}",
                )

        # /share/v/<id>
        if len(path_parts) >= 3 and path_parts[1].lower() == "v":
            video_id = path_parts[2].strip()
            if self._valid_facebook_id(video_id):
                return self._make_link_match(
                    original_url=original_url,
                    mirror_url=f"https://{self.MIRROR_DOMAINS['facebook']}/share/v/{video_id}",
                    dedup_key=f"facebook-watch:{video_id.lower()}",
                )

        # /share/<id>
        if len(path_parts) >= 2 and path_parts[1].lower() not in {"r", "v"}:
            share_id = path_parts[1].strip()
            if self._valid_facebook_id(share_id):
                return self._make_link_match(
                    original_url=original_url,
                    mirror_url=f"https://{self.MIRROR_DOMAINS['facebook']}/watch?v={share_id}",
                    dedup_key=f"facebook:{share_id.lower()}",
                )

        return None

    async def _send_mirrors(self, message: discord.Message, links: Iterable[LinkMatch]) -> bool:
        links = list(links)
        if not links:
            return False

        chunks = self._chunk_links_with_single_footer(links, message.jump_url)
        if not chunks:
            logger.debug("No mirror chunks generated for message %s", message.id)
            return False

        logger.debug(
            "Sending %d mirror chunk(s) for message=%s guild=%s",
            len(chunks),
            message.id,
            getattr(message.guild, "id", None),
        )

        for chunk in chunks:
            try:
                reference = message.to_reference(fail_if_not_exists=False)
                await message.channel.send(
                    chunk,
                    reference=reference,
                    mention_author=False,
                )

            except discord.Forbidden:
                logger.warning(
                    "Missing permission to send mirror in guild=%s channel=%s",
                    getattr(message.guild, "id", None),
                    getattr(message.channel, "id", None),
                )
                return False

            except discord.NotFound:
                logger.warning(
                    "Channel or message vanished while sending mirror for message=%s",
                    message.id,
                )
                return False

            except discord.HTTPException:
                try:
                    await message.channel.send(chunk)
                except discord.Forbidden:
                    logger.warning(
                        "Missing permission to send fallback mirror in guild=%s channel=%s",
                        getattr(message.guild, "id", None),
                        getattr(message.channel, "id", None),
                    )
                    return False
                except discord.NotFound:
                    logger.warning(
                        "Channel vanished while sending fallback mirror for message=%s",
                        message.id,
                    )
                    return False
                except discord.HTTPException:
                    logger.exception("Failed to send mirror message for message %s", message.id)
                    return False

        return True

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
        except discord.NotFound:
            logger.debug("Message %s was deleted before embeds could be suppressed", message.id)
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

            if not fresh_links:
                logger.debug(
                    "All %d link(s) already processed in guild=%s within TTL",
                    len(links),
                    guild_id,
                )
                return

            # Mark links before sending to reduce duplicate replies under concurrency.
            for link in fresh_links:
                self._mark_processed(guild_id, link.dedup_key, now)

        sent = await self._send_mirrors(message, fresh_links)
        if not sent:
            # Rollback is intentionally skipped. A short-lived false dedupe is preferable
            # to duplicate mirror replies caused by concurrent sends.
            return

        await self._suppress_embeds_if_possible(message, perms.manage_messages)


def setup(bot: commands.Bot) -> None:
    bot.add_cog(Autolink(bot))


# pytest tests in same file
# run with: pytest -q cog/autolink.py
# you need to install pytest + pytest-asyncio
# this code is to test each function of the cache if its works properly or got any issues

# try:
#     import pytest
#     from types import SimpleNamespace
#     from unittest.mock import AsyncMock, Mock, patch
# except ImportError:
#     pytest = None
#
#
# if pytest is not None:
#     @pytest.fixture
#     def cog():
#         fake_bot = SimpleNamespace(
#             user=SimpleNamespace(id=12345),
#             wait_until_ready=AsyncMock(),
#         )
#
#         instance = Autolink(fake_bot)
#         return instance
#
#
#     def test_mark_and_is_processed_until_expiry(cog):
#         guild_id = 1
#         key = "youtube:abc123"
#         now = 100.0
#
#         assert cog._is_processed(guild_id, key, now) is False
#
#         cog._mark_processed(guild_id, key, now)
#
#         assert cog._is_processed(guild_id, key, now + 1.0) is True
#         assert cog._is_processed(guild_id, key, now + 299.999) is True
#         assert cog._is_processed(guild_id, key, now + cog.CACHE_TTL_SECONDS) is False
#         assert guild_id not in cog.processed_links_by_guild
#
#
#     def test_prune_guild_cache_removes_expired_entries_and_lock(cog):
#         guild_id = 42
#         now = 500.0
#
#         cog._get_guild_lock(guild_id)
#
#         cog.processed_links_by_guild[guild_id] = {
#             "a": now - 1,
#             "b": now - 10,
#         }
#
#         cog._prune_guild_cache(guild_id, now)
#
#         assert guild_id not in cog.processed_links_by_guild
#         assert guild_id not in cog.guild_locks
#
#
#     def test_prune_guild_cache_keeps_size_limit_and_removes_oldest(cog):
#         guild_id = 99
#         old_limit = cog.CACHE_SIZE_PER_GUILD
#         cog.CACHE_SIZE_PER_GUILD = 3
#
#         try:
#             cog.processed_links_by_guild[guild_id] = {
#                 "k1": 10.0,
#                 "k2": 20.0,
#                 "k3": 30.0,
#                 "k4": 40.0,
#                 "k5": 50.0,
#             }
#
#             cog._prune_guild_cache(guild_id, now=0.0)
#
#             remaining = cog.processed_links_by_guild[guild_id]
#             assert set(remaining.keys()) == {"k3", "k4", "k5"}
#         finally:
#             cog.CACHE_SIZE_PER_GUILD = old_limit
#
#
#     def test_is_processed_removes_expired_entry_but_keeps_other_entries(cog):
#         guild_id = 7
#         now = 1000.0
#
#         cog.processed_links_by_guild[guild_id] = {
#             "expired": now - 1,
#             "alive": now + 100,
#         }
#
#         assert cog._is_processed(guild_id, "expired", now) is False
#         assert cog._is_processed(guild_id, "alive", now) is True
#         assert "alive" in cog.processed_links_by_guild[guild_id]
#
#
#     def make_message(
#         *,
#         guild_id=1,
#         content="https://youtu.be/dQw4w9WgXcQ",
#         manage_messages=False,
#     ):
#         perms = SimpleNamespace(send_messages=True, manage_messages=manage_messages)
#         me = object()
#
#         guild = SimpleNamespace(
#             id=guild_id,
#             get_member=lambda _user_id: me,
#             me=me,
#         )
#
#         channel = SimpleNamespace(
#             id=555,
#             permissions_for=lambda _member: perms,
#         )
#
#         author = SimpleNamespace(bot=False)
#
#         return SimpleNamespace(
#             id=999,
#             author=author,
#             webhook_id=None,
#             guild=guild,
#             channel=channel,
#             content=content,
#             type=discord.MessageType.default,
#             jump_url="https://discord.com/channels/1/555/999",
#         )
#
#
#     @pytest.mark.asyncio
#     async def test_cog_load_starts_cleanup_loop(cog):
#         with patch.object(cog.cleanup_cache, "start", return_value=None) as start_mock:
#             await cog.cog_load()
#             start_mock.assert_called_once()
#
#
#     @pytest.mark.asyncio
#     async def test_on_message_failed_send_still_marks_processed(cog):
#         msg = make_message()
#
#         link = LinkMatch(
#             original_url="https://youtu.be/dQw4w9WgXcQ",
#             mirror_url="https://koutu.be/watch?v=dQw4w9WgXcQ",
#             dedup_key="youtube:dqw4w9wgxcq",
#         )
#
#         cog._extract_supported_links = Mock(return_value=[link])
#         cog._send_mirrors = AsyncMock(return_value=False)
#         cog._suppress_embeds_if_possible = AsyncMock()
#
#         await cog.on_message(msg)
#         await cog.on_message(msg)
#
#         cog._send_mirrors.assert_awaited_once()
#         cog._suppress_embeds_if_possible.assert_not_awaited()
#
#
#     @pytest.mark.asyncio
#     async def test_on_message_concurrent_calls_only_send_once(cog):
#         msg1 = make_message(guild_id=123)
#         msg2 = make_message(guild_id=123)
#
#         link = LinkMatch(
#             original_url="https://youtu.be/dQw4w9WgXcQ",
#             mirror_url="https://koutu.be/watch?v=dQw4w9WgXcQ",
#             dedup_key="youtube:dqw4w9wgxcq",
#         )
#
#         cog._extract_supported_links = Mock(return_value=[link])
#         cog._send_mirrors = AsyncMock(return_value=True)
#         cog._suppress_embeds_if_possible = AsyncMock()
#
#         await asyncio.gather(cog.on_message(msg1), cog.on_message(msg2))
#
#         cog._send_mirrors.assert_awaited_once()
#
#
#     @pytest.mark.asyncio
#     async def test_on_message_ignores_bots_and_dms(cog):
#         bot_msg = make_message()
#         bot_msg.author.bot = True
#
#         dm_msg = make_message()
#         dm_msg.guild = None
#
#         cog._extract_supported_links = Mock()
#         cog._send_mirrors = AsyncMock()
#
#         await cog.on_message(bot_msg)
#         await cog.on_message(dm_msg)
#
#         cog._extract_supported_links.assert_not_called()
#         cog._send_mirrors.assert_not_awaited()
