# Architecture Review: Usagi-Bot

**Repository:** InvalidDavid/Usabi-Bot (Usagi-Bot)  
**Review Date:** 2026-04-20  
**Reviewer:** Architecture Review Agent  
**Files Reviewed:** main.py, utils/secrets.py, utils/imports.py, cog/*.py (10 cogs)

---

## 1. Overall Architecture Assessment

### Structure Summary

```
Usagi-Bot/
├── main.py              # Entry point, logging, bot initialization
├── utils/
│   ├── secrets.py       # Environment configuration (20 lines)
│   └── imports.py       # Star-import barrel file (62 lines)
└── cog/
    ├── user.py          # Help system + about command (362 lines)
    ├── owner.py         # Cog management (209 lines)
    ├── mod.py           # Moderation + forum tools (251 lines)
    ├── games.py         # Games + SQLite persistence (878 lines)
    ├── reminder.py      # Reminder system + APScheduler (829 lines)
    ├── faq.py           # FAQ system (261 lines)
    ├── errorhandler.py  # Global error handling (288 lines)
    ├── autolink.py      # URL mirroring (224 lines)
    └── anilist.py       # AniList API integration (155 lines)
```

### Architecture Classification

**Tier:** Monolithic single-file-per-cog module  
**Pattern:** Canonical Py-cord cog pattern withslash command groups  
**State Model:** Mixed — in-memory caches, SQLite files, APScheduler background workers  
**Concurrency Model:** Asyncio with APScheduler for scheduled tasks, sqlite3 for DB (synchronous)

### Overall Score: **5/10** — Functional but fragile

| Dimension | Score | Notes |
|-----------|-------|-------|
| Code Organization | 6/10 | Clear separation by domain, but oversized files |
| Dependency Management | 4/10 | Star-import barrel obscures real dependencies |
| State Management | 5/10 | Mixed in-memory/SQL, no transactions, no cleanup |
| Scalability | 3/10 | Global caches unbounded, no sharding, O(n) operations |
| Error Handling | 6/10 | Centralized handler, but caching strategy has issues |
| Testability | 2/10 | Hardcoded paths, global state, no DI |
| Operational Robustness | 5/10 | Logging present, but crash logs on disk only |

---

## 2. Design Pattern Usage Analysis

### Patterns Identified

| Pattern | Usage | Assessment |
|---------|-------|------------|
| **Cog Pattern** | All 10 modules use `commands.Cog` base | ✅ Correct, standard Py-cord pattern |
| **Slash Command Groups** | `owner`, `mod`, `forum`, `games`, `reminder` groups | ✅ Good organization |
| **Star Import Barrel** | `utils.imports` re-exports ~40 symbols | ⚠️ Code smell — hides actual dependencies |
| **Repository Pattern** | `GamesDatabase`, `Reminder` both contain raw sqlite3 calls | ⚠️ Not abstracted — logic buried in cog |
| **Strategy Pattern** | `bot_move()` in TicTacToe has 11 named strategies | ✅ Well-implemented, clean separation |
| **View Pattern** | All UI use `discord.ui.View/DesignerView` subclasses | ✅ Good |
| **Singleton (implicit)** | `GamesDatabase()` creates one connection per cog load | ⚠️ Process-level singleton via module global |
| **Worker Loop Pattern** | `Reminder.worker_loop()` busy-polls DB | ⚠️ No sleep optimization, always spinning |

### Star Import Pattern — Critical Issue

**`utils/imports.py`** (62 lines) re-exports ~40 symbols via `from X import *`. Every cog file begins with:

```python
from utils.imports import *
```

**Problems:**
1. **Hides real dependencies** — impossible to know what a cog actually needs without reading it
2. **Import order problems** — circular dependencies are masked; if A imports B and B imports A via the barrel, debugging is nightmarish
3. **Namespace pollution** — `Button` (discord.ui) and `UIButton` (discord.ui) both exist; collisions likely
4. **Static analysis failure** — linters and type checkers cannot resolve what's actually used
5. **Refactoring hazard** — renaming a symbol in `imports.py` silently breaks every cog

**Specific collision observed:**
```python
from discord.ui import Button, Select
from discord.ui import Button as UIButton  # Line 41 — same name, aliased
```
This should never be necessary if imports were explicit.

**Recommendation:** Replace `from utils.imports import *` with explicit imports per file. Use `utils/imports.py` only as a backward-compatibility shim during migration.

---

## 3. Separation of Concerns Evaluation

### Layer Analysis

| Layer | Location | Issues |
|-------|----------|--------|
| **Configuration** | `utils/secrets.py` | ✅ Single responsibility, loads from `.env` |
| **Runtime Bootstrap** | `main.py` lines 1-53, 164-174 | ✅ Logging setup is clean; monkey-patch is concerning |
| **Discord Gateway** | `main.py` lines 56-95 | ⚠️ Monkey-patching `discord.gateway.DiscordWebSocket.identify` — fragile, version-dependent |
| **Cog Domain Logic** | Respective cog files | ✅ Commands grouped by domain |
| **Data Access** | `games.py`, `reminder.py` | ❌ DB logic embedded in cog, not abstracted |
| **Background Jobs** | `reminder.py` APScheduler | ⚠️ Coupled to cog lifecycle |
| **Error Handling** | `errorhandler.py` | ⚠️ Also handles `_slash_error_cache` — persistence concern |

### Cross-Cutting Concerns

**Logging:**
- ✅ Centralized in `main.py` (logger setup)
- ✅ `logger = logging.getLogger("bot.reminder")` in reminder.py
- ❌ `print()` calls throughout — no structured logging in autolink.py, games.py

**Database:**
- ❌ Two separate SQLite DBs (`Data/games.db`, `Data/reminders.db`) — no unified transaction boundary
- ❌ `games.py` uses sync `sqlite3` in async context — no lock mechanism for `GamesDatabase.conn`
- ❌ `reminder.py` opens a new connection per operation (not pooled)
- ❌ No migrations — `CREATE TABLE IF NOT EXISTS` only

**Scheduler:**
- ⚠️ `AsyncIOScheduler` in reminder.py — scheduler lifecycle not managed at bot level
- ⚠️ 5 separate `bot.loop.create_task()` calls in `Reminder.__init__` — initialization scatter

### Biggest Violations

1. **Games cog (878 lines)** — This is a 3-in-1 violation: UI (views), game logic (strategies), and data access (database) all in one file. Should be split.
2. **Reminder cog (829 lines)** — Worker loop, scheduler, database, parsing, and UI all in one file. Hard to test and maintain.
3. **FAQ cog (261 lines)** — Hardcoded FAQ data inside the class. Should be external JSON/YAML.

---

## 4. Module Interaction Analysis

### Interaction Map

```
main.py
├── loads all cogs dynamically
├── bot.run(TOKEN)
│
├── user.py (HelpView ←→ bot.cogs)
├── owner.py (cog management ←→ bot.extensions)
├── mod.py (no cross-cog deps)
├── games.py (GamesDatabase ←→ sqlite3)
├── reminder.py
│   ├── worker_loop ←→ sqlite3
│   ├── scheduler ←→ APScheduler
│   └── on_member_remove listener ←→ bot
├── faq.py (FaqButtons ←→ bot.add_view)
├── errorhandler.py
│   ├── WebhookLogger ←→ aiohttp
│   └── listener ←→ bot
├── autolink.py (on_message listener ←→ message.content)
└── anilist.py (search_anilist ←→ requests.post)
```

### Key Observations

**1. Shared State via `bot` reference**
All cogs receive `self.bot` but there's no interface contract. Cogs access `bot.extensions`, `bot.cogs`, `bot.user`, `bot.http`, `bot.loop` — all implicit dependencies.

**2. No Dependency Injection**
Cogs are tightly coupled to `discord.Bot`. `GamesDatabase` is instantiated directly in `Games.__init__`, not injected. This makes mocking impossible for tests.

**3. Cross-cog Communication**
- `user.py` accesses `self.bot.cogs` to build help (line 238) — fragile if cog names change
- `owner.py` manages extensions dynamically
- No pub/sub or event bus — direct method calls only

**4. Autolink ↔ Other Cogs**
Autolink processes `on_message` events and suppresses embeds. This is orthogonal to other cogs — good separation.

**5. ErrorHandler ↔ All Cogs**
ErrorHandler registers a global listener via `bot.add_listener(self.on_global_error)` — correct pattern, but the cog must be loaded first (protected cog).

---

## 5. Scalability Concerns and Recommendations

### Critical Scalability Issues

#### Issue 1: Unbounded In-Memory Cache (Autolink)
**File:** `cog/autolink.py` line 94
```python
self.processed_links_by_guild: dict[int, OrderedDict[str, float]] = defaultdict(OrderedDict)
```
- Grows per guild without limit
- `cache_size_per_guild = 500` only enforced during cleanup (on access)
- No TTL expiration enforcement between accesses
- Under high load, this will OOM on large servers

**Fix:** Use `cachetools.TTLCache` or implement periodic background cleanup task.

#### Issue 2: Reminder Worker Loop Busy-Spin
**File:** `cog/reminder.py` lines 643-805
```python
while not self.bot.is_closed():
    # ... process one reminder at a time ...
    if next_run is None:
        await asyncio.sleep(1.0)  # 1 second granularity
        continue
    delay = max(0.05, min(1.0, next_run - time.time()))
    await asyncio.sleep(delay)
```
- Processes **one reminder per database round-trip**
- If 1000 reminders are pending, that's 1000 separate SQLite transactions
- No batching — each reminder: `UPDATE → SELECT → send → UPDATE`

**Fix:** Batch-fetch up to N pending reminders per loop iteration, process in memory, then commit.

#### Issue 3: Sync SQLite in Async Context (Games)
**File:** `cog/games.py` line 11
```python
self.conn = sqlite3.connect(db_name)
```
- `GamesDatabase.conn` is a **shared synchronous connection** across all game commands
- Multiple concurrent slash commands will hit the connection simultaneously
- No `threading.Lock` — only `asyncio.Lock` in `RPSPlayView` which is per-game, not per-cog

**Fix:** Use `aiosqlite` for async DB operations, or use a connection pool.

#### Issue 4: Error Cache Memory Leak
**File:** `cog/errorhandler.py` line 133
```python
self._slash_error_cache = {}
```
- Cache key: `(user_id, command_name, error_type)` — grows unbounded
- Only cleaned on cleanup task (300s intervals)
- Under attack (many users triggering errors), grows without bound

**Fix:** Add max cache size with LRU eviction.

#### Issue 5: Mod Cog Commented-Out Code
**File:** `cog/mod.py` lines 24-70
- 47 lines of commented-out `on_thread_create` handler
- Dead code indicates planned features that may conflict with current implementation
- Should be removed or implemented

### Scalability Recommendations (Priority Order)

| Priority | Recommendation | Impact |
|----------|---------------|--------|
| P0 | Replace `utils.imports` star import with explicit imports | Maintainability |
| P0 | Replace sync sqlite3 with aiosqlite in games.py and reminder.py | Correctness under concurrency |
| P1 | Add max size to `_slash_error_cache` | Memory safety |
| P1 | Implement TTL-based cache for autolink instead of manual OrderedDict | Memory safety |
| P1 | Batch reminder processing (fetch N, process, commit) | Performance |
| P2 | Split games.py into: game_logic.py, game_views.py, game_db.py | Maintainability |
| P2 | Split reminder.py into: reminder_db.py, reminder_scheduler.py, reminder_cog.py | Maintainability |
| P2 | Move FAQ data to external JSON/YAML | Maintainability |
| P3 | Add health check endpoint / status command with all system metrics | Observability |
| P3 | Remove monkey-patch or isolate it in a dedicated compatibility module | Version safety |

---

## 6. Specific File-Level Architectural Issues

### main.py

| Line | Issue | Severity |
|------|-------|----------|
| 1 | `from utils.imports import *` — hides all imports | Medium |
| 5 | `os.makedirs` at module level — I/O on every import | Low |
| 59-93 | Monkey-patch `discord.gateway.DiscordWebSocket.identify` — Discord TOS, version-dependent, no version guard | **High** |
| 98-105 | `commands.Bot` init with `intents=discord.Intents.all()` — too permissive, requests all intents unnecessarily | Medium |
| 164-174 | Dynamic cog loading via `os.listdir("cog")` — no loading order guarantee, hidden coupling | Medium |

### utils/imports.py

| Line | Issue | Severity |
|------|-------|----------|
| 1-62 | `from X import *` barrel file — all issues described in §2 | **High** |
| 29-30 | `requests` and `aiohttp` both imported — sync/async HTTP confusion | Medium |

### utils/secrets.py

| Line | Issue | Severity |
|------|-------|----------|
| 11 | `int(os.getenv("FORUM_ID"))` — no default, crashes if missing | Medium |
| 6-14 | All values loaded at module import time — no reloading support | Low |

### cog/user.py

| Line | Issue | Severity |
|------|-------|----------|
| 85-93 | `is_owner_command()` inspects function objects via `repr()` — extremely fragile | **High** |
| 238 | `self.bot.cogs.items()` iteration — depends on cog name strings | Medium |
| 51-61 | `on_timeout` uses bare `except Exception` with `print()` | Medium |
| 142-151 | `time_ago()` has hardcoded German string "vor" — not locale-aware | Low |

### cog/owner.py

| Line | Issue | Severity |
|------|-------|----------|
| 119 | `traceback.print_exc()` — should use logger | Medium |
| 68-202 | All commands use `@commands.is_owner()` decorator manually — no shared guard | Low |

### cog/mod.py

| Line | Issue | Severity |
|------|-------|----------|
| 24-70 | 47 lines of commented-out code — technical debt | Medium |
| 162 | Bare `print(e)` — should use logger | Medium |
| 208 | `thread.send()` before `thread.edit()` — race condition on lock | Medium |

### cog/games.py ⚠️ LARGEST FILE

| Line | Issue | Severity |
|------|-------|----------|
| 4 | `DB_PATH = "Data/games.db"` — hardcoded relative path, not configurable | **High** |
| 11 | `self.conn = sqlite3.connect(db_name)` — sync connection, shared across async commands, no lock | **High** |
| 36 | `f"INSERT OR IGNORE INTO {table} (user_id) VALUES (?)"` — f-string SQL, vulnerable to injection via `table` parameter (though constrained to "Rock_Paper_Scissors"/"TicTacToe") | Medium |
| 53-138 | `RPSPlayView` has `_lock` but parent `GamesDatabase` has no lock — games can race | **High** |
| 177-627 | `TicTacToeView.Cell` is a nested class 450 lines into the file — hard to find | Medium |

### cog/reminder.py ⚠️ SECOND LARGEST

| Line | Issue | Severity |
|------|-------|----------|
| 8 | `MAX_RETRIES = 5` — never used (retry logic is hardcoded in worker_loop) | Low |
| 339-370 | DB initialization inline in cog — no migration system | Medium |
| 385-428 | `_cleanup_orphan_users()` fetches all reminders on startup — O(n) with network calls | **High** |
| 643-805 | Worker loop: 1 reminder per iteration, no batching | **High** |
| 651-667 | `lock_token` approach for distributed locking — race condition between UPDATE and SELECT | Medium |
| 799 | `delay = max(0.05, min(1.0, next_run - time.time()))` — if `next_run` is 1000s in future, still polls every 1s | Medium |

### cog/faq.py

| Line | Issue | Severity |
|------|-------|----------|
| 12-98 | Hardcoded FAQ data dict — should be external JSON | Medium |
| 246-250 | `on_ready` registers view every restart — no persistence check | Medium |
| 253-257 | `@commands.is_owner()` on FAQ command — but owner can only send to channel, not trigger ephemeral response properly | Low |

### cog/errorhandler.py

| Line | Issue | Severity |
|------|-------|----------|
| 54 | `_error_cache` grows unbounded — memory leak under load | **High** |
| 115 | `print()` instead of logger | Medium |
| 169-186 | `on_global_error` — logs to webhook but also `traceback.print_exception` to stdout (double logging) | Medium |

### cog/autolink.py

| Line | Issue | Severity |
|------|-------|----------|
| 94 | `defaultdict(OrderedDict)` — unbounded per-guild cache | **High** |
| 88-89 | `cache_ttl_seconds=300`, `cache_size_per_guild=500` — not configurable | Medium |
| 188-191, 213-220 | `print()` for errors — no structured logging | Medium |

### cog/anilist.py

| Line | Issue | Severity |
|------|-------|----------|
| 32 | `requests.post()` — **synchronous blocking call in async context** | **High** |
| 124 | Bare `except:` — catches everything including keyboard interrupts | Medium |

### cog/v2 errorhandler.py (duplicate file, space in name)

| Line | Issue | Severity |
|------|-------|----------|
| 1-276 | File name contains space (`v2 errorhandler.py`) — this file will be loaded as `cog.v2_errorhandler` if at all | **High** |
| 182 | `traceback.print_exception()` only in v2 version, not in main errorhandler — behavior divergence | Medium |

---

## 7. Review Checklist

### Must Fix (P0)
- [ ] Replace `from utils.imports import *` with explicit imports in all cog files
- [ ] Replace sync `requests` call in `anilist.py` with `aiohttp`
- [ ] Replace sync `sqlite3` with `aiosqlite` or add proper connection locking in `games.py`
- [ ] Add max size limit to `_slash_error_cache` in `errorhandler.py`
- [ ] Rename `cog/v2 errorhandler.py` — spaces in Python filenames cause import failures

### Should Fix (P1)
- [ ] Add TTL enforcement to autolink cache (`_cleanup_guild_cache` only runs on access)
- [ ] Batch reminder processing — fetch N pending reminders per loop iteration
- [ ] Remove or formalize the Discord gateway monkey-patch (or add version guard)
- [ ] Use `logging` instead of `print()` throughout
- [ ] Make `FORUM_ID` default to `None` to prevent startup crash
- [ ] Add `__all__` to prevent star-import issues

### Could Fix (P2)
- [ ] Split `games.py` (878 lines) into logical submodules
- [ ] Split `reminder.py` (829 lines) into DB layer + scheduler layer + cog
- [ ] Externalize FAQ data to JSON/YAML
- [ ] Implement proper data access objects instead of raw SQL in cogs
- [ ] Add database migration system (even basic version tracking)
- [ ] Remove commented-out code from `mod.py`

### Nice to Have (P3)
- [ ] Add health check / status command showing all system states
- [ ] Implement DI container for testability
- [ ] Add per-command rate limiting that survives restarts (Redis)
- [ ] Locale-aware time formatting instead of hardcoded "vor"
- [ ] Document the star-import pattern as technical debt

---

## 8. Verification Strategy

### Code Quality Verification
1. Run `flake8` / `ruff` on entire codebase — expect star-import violations
2. Run `mypy --strict` — expect type errors in games.py and reminder.py
3. Check that `cog/v2 errorhandler.py` is loaded or skipped by the cog loader

### Runtime Verification
1. Start bot with empty `.env` — expect `int(os.getenv("FORUM_ID"))` crash
2. Send 100 concurrent `/games rps` commands — verify no sqlite3 connection errors
3. Send 1000 reminders via reminder system — observe worker loop behavior
4. Monitor memory growth on autolink cache under sustained URL traffic
5. Verify error handler receives webhook payloads for critical errors

### Architecture Conformance
1. No `from utils.imports import *` in any new or modified cog files
2. All DB operations use async drivers (`aiosqlite`)
3. All HTTP calls are non-blocking (`aiohttp` or `httpx`)
4. All logging goes through `logging.getLogger()` hierarchy

---

## 9. Key Risks and Fallbacks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Memory exhaustion via unbounded caches | Medium | High | Add max size + TTL to all cache implementations |
| Race condition in games DB | Medium | High | Replace sync sqlite3 with aiosqlite |
| Bot crashes on missing env vars | High | Medium | Add defaults or validate at startup |
| Monkey-patch breaks on Pycord update | Medium | High | Version check or remove the patch |
| Cog loading fails due to space in filename | High | High | Rename `v2 errorhandler.py` immediately |
| Sync HTTP blocks event loop in anilist | High | Medium | Replace with aiohttp |
| Worker loop starvation under load | Medium | Medium | Batch processing in reminder worker |

---

## 10. Summary

**Architecture Type:** Monolithic cog-based Discord bot with background workers  
**Technology Stack:** Py-cord, APScheduler, sqlite3 (sync), requests (sync)  
**Overall Assessment:** 5/10 — Functional but fragile

The codebase works for small-scale deployment but has significant structural issues that will cause problems at scale or under adversarial conditions. The star-import pattern, synchronous database access, unbounded caches, and synchronous HTTP calls are the five most critical issues to address.

**Immediate Action Items:**
1. Rename `cog/v2 errorhandler.py` 
2. Replace sync `requests` in `anilist.py` with `aiohttp`
3. Replace `from utils.imports import *` with explicit imports
4. Add bounds to `_slash_error_cache`

*End of Review*