import asyncio
import discord
from discord.ext import commands
import sqlite3
import random

DB_PATH = "Data/games.db"
CHOICES = ["Scissors", "Rock", "Paper"]
RANK_EMOJIS = ["🥇", "🥈", "🥉", "🎖️", "⭐"]


class GamesDatabase():
    def __init__(self, db_name: str = DB_PATH):
        self.conn = sqlite3.connect(db_name)
        self.conn.execute("PRAGMA foreign_keys = 1")
        self._init_db()

    def _init_db(self):
        cur = self.conn.cursor()
        cur.execute('''CREATE TABLE IF NOT EXISTS Rock_Paper_Scissors (
            user_id INTEGER PRIMARY KEY,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            draws INTEGER DEFAULT 0
        )''')
        cur.execute('''CREATE TABLE IF NOT EXISTS TicTacToe (
            user_id INTEGER PRIMARY KEY,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            draws INTEGER DEFAULT 0
        )''')
        self.conn.commit()

    def update_stats(self, user_id: int, result: str, game: str = "rps", bot_user_id: int = None):
        if user_id is None or user_id == bot_user_id:
            return
        table = "Rock_Paper_Scissors" if game.lower() == "rps" else "TicTacToe"
        cur = self.conn.cursor()
        cur.execute(f"INSERT OR IGNORE INTO {table} (user_id) VALUES (?)", (user_id,))
        if result == "win":
            cur.execute(f"UPDATE {table} SET wins = wins + 1 WHERE user_id=?", (user_id,))
        elif result == "loss":
            cur.execute(f"UPDATE {table} SET losses = losses + 1 WHERE user_id=?", (user_id,))
        else:
            cur.execute(f"UPDATE {table} SET draws = draws + 1 WHERE user_id=?", (user_id,))
        self.conn.commit()


def determine_result(p1_choice: str, p2_choice: str) -> str:
    if p1_choice == p2_choice:
        return "draw"
    wins = {"Scissors": "Paper", "Rock": "Scissors", "Paper": "Rock"}
    return "win" if wins[p1_choice] == p2_choice else "loss"


class RPSPlayView(discord.ui.View):
    def __init__(self, p1: discord.User, p2: discord.User, bot_user: discord.User, db: GamesDatabase):
        super().__init__(timeout=120)
        self.p1 = p1
        self.p2 = p2
        self.bot_user = bot_user
        self.db = db
        self.choices = {}
        self._lock = asyncio.Lock()
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id not in [self.p1.id, self.p2.id]:
            await interaction.response.send_message("❌ This is not your game!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="✂️  Scissors", style=discord.ButtonStyle.secondary)
    async def scissors_btn(self, button, interaction):
        await self.handle_choice(interaction, "Scissors")

    @discord.ui.button(label="🪨  Rock", style=discord.ButtonStyle.secondary)
    async def rock_btn(self, button, interaction):
        await self.handle_choice(interaction, "Rock")

    @discord.ui.button(label="📃  Paper", style=discord.ButtonStyle.secondary)
    async def paper_btn(self, button, interaction):
        await self.handle_choice(interaction, "Paper")

    async def handle_choice(self, interaction: discord.Interaction, choice: str):
        uid = interaction.user.id
        async with self._lock:
            if uid in self.choices:
                await interaction.response.send_message("You have already chosen!", ephemeral=True)
                return
            self.choices[uid] = choice

            if self.p2 == self.bot_user or self.p1 == self.bot_user:
                human = self.p1 if self.p1 != self.bot_user else self.p2
                bot_choice = random.choice(CHOICES)
                result = determine_result(choice, bot_choice)
                winner_text = {
                    "win": f"{human.mention} wins! 🎉",
                    "loss": f"{self.bot_user.mention} wins! 🤖",
                    "draw": "Draw! 😐"
                }[result]

                for child in self.children:
                    child.disabled = True
                await interaction.response.edit_message(
                    content=(f"**Result:** {winner_text}\n"
                             f"- {human.mention} chooses **{choice}**\n"
                             f"- Bot chooses **{bot_choice}**"),
                    view=self
                )
                self.stop()
                return

            if len(self.choices) == 2:
                p1_choice = self.choices[self.p1.id]
                p2_choice = self.choices[self.p2.id]
                p1_result = determine_result(p1_choice, p2_choice)
                p2_result = "draw" if p1_result == "draw" else ("loss" if p1_result == "win" else "win")

                self.db.update_stats(self.p1.id, p1_result, "rps")
                self.db.update_stats(self.p2.id, p2_result, "rps")

                winner_text = {
                    "win": f"{self.p1.mention} wins! 🎉",
                    "loss": f"{self.p2.mention} wins! 🎉",
                    "draw": "Draw! 😐"
                }[p1_result]

                for child in self.children:
                    child.disabled = True

                await interaction.response.edit_message(
                    content=(f"**{winner_text}**\n"
                             f"- {self.p1.mention} chooses **{p1_choice}**\n"
                             f"- {self.p2.mention} chooses **{p2_choice}**"),
                    view=self
                )
                self.stop()
            else:
                await interaction.response.send_message("Choice saved, waiting for opponent...", ephemeral=True)


class TicTacToeView(discord.ui.View):
    def __init__(self, p1, p2, bot_user, db: GamesDatabase, size=3, win_length=3):
        super().__init__(timeout=120)
        self.p1 = p1
        self.p2 = p2
        self.bot_user = bot_user
        self.db = db
        self.size = size
        self.win_length = win_length
        self.board = [" "] * (size * size)
        self.current = p1
        self.winner = None
        self.message = None
        self.is_bot_game = (p1 == bot_user or p2 == bot_user)

        for i in range(size * size):
            self.add_item(self.Cell(i, row=i // size))

    async def on_timeout(self):
        if self.message:
            for child in self.children:
                child.disabled = True
            embed = self.create_embed(
                title="⏰ Time ran out!",
                description=f"Last player to move: {self.current.mention}"
            )
            await self.message.edit(content=None, embed=embed, view=self)
        self.stop()

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user not in [self.p1, self.p2]:
            await interaction.response.send_message(
                "❌ You are not part of this game!", ephemeral=True
            )
            return False
        return True

    class Cell(discord.ui.Button):
        def __init__(self, idx, row):
            super().__init__(label="\u200b", style=discord.ButtonStyle.secondary, row=row)
            self.idx = idx

        async def callback(self, interaction: discord.Interaction):
            view: TicTacToeView = self.view
            bot_user_id = view.bot_user.id
            if interaction.user != view.current:
                await interaction.response.send_message("⏳ Not your turn!", ephemeral=True)
                return
            if view.board[self.idx] != " ":
                await interaction.response.send_message("❌ Cell already taken!", ephemeral=True)
                return

            mark = "❌" if view.current == view.p1 else "◯️"
            view.board[self.idx] = mark
            self.label = mark
            self.style = discord.ButtonStyle.primary if mark == "❌" else discord.ButtonStyle.danger
            self.disabled = True

            if view.check_winner(mark):
                view.winner = view.current
                for child in view.children:
                    child.disabled = True

                embed = discord.Embed(
                    title="🎉 Game Over!",
                    description=f"{view.winner.mention} wins!",
                    color=discord.Color.green()
                )
                await interaction.response.edit_message(content=None, embed=embed, view=view)

                if view.p1 != view.bot_user and view.p2 != view.bot_user:
                    loser = view.p2 if view.winner == view.p1 else view.p1
                    view.db.update_stats(view.winner.id, "win", game="ttt", bot_user_id=view.bot_user.id)
                    view.db.update_stats(loser.id, "loss", game="ttt", bot_user_id=view.bot_user.id)

                view.stop()
                return

            if all(s != " " for s in view.board):
                for child in view.children:
                    child.disabled = True
                embed = discord.Embed(
                    title="😐 Draw!",
                    description="The board is full!",
                    color=discord.Color.gold()
                )
                await interaction.response.edit_message(content=None, embed=embed, view=view)

                if view.p1 != view.bot_user and view.p2 != view.bot_user:
                    view.db.update_stats(view.p1.id, "draw", game="ttt", bot_user_id=view.bot_user.id)
                    view.db.update_stats(view.p2.id, "draw", game="ttt", bot_user_id=view.bot_user.id)

                view.stop()
                return
            view.current = view.p2 if view.current == view.p1 else view.p1
            embed = discord.Embed(
                title=f"TicTacToe {view.size}x{view.size}",
                description=f"Your turn: {view.current.mention}",
                color=discord.Color.blurple()
            )
            embed.add_field(
                name="Players",
                value=f"❌ {view.p1.mention}\n◯️ {view.p2.mention}",
                inline=False
            )
            await interaction.response.edit_message(content=None, embed=embed, view=view)

            if view.current == view.bot_user:
                await view.bot_move()

    async def bot_move(self):
        await asyncio.sleep(1)
        empty = [i for i, v in enumerate(self.board) if v == " "]
        if not empty:
            return

        bot_mark = "❌" if self.current == self.p1 else "◯️"
        player_mark = "◯️" if bot_mark == "❌" else "❌"


        def get_position_score(idx):
            n = self.size
            x, y = idx // n, idx % n
            center = n // 2

            if n == 5:
                if (x, y) == (2, 2):
                    return 100
                elif 1 <= x <= 3 and 1 <= y <= 3:
                    return 60
                elif x in [0, 4] and y in [0, 4]:
                    return 40
                elif x in [0, 4] or y in [0, 4]:
                    return 20
                else:
                    return 30
            else:
                if (x, y) == (1, 1):
                    return 100
                elif x in [0, 2] and y in [0, 2]:
                    return 40
                else:
                    return 20

        def check_immediate_win():
            for idx in empty:
                self.board[idx] = bot_mark
                if self.check_winner(bot_mark):
                    self.board[idx] = " "
                    return idx
                self.board[idx] = " "
            return None

        def check_block_player():
            for idx in empty:
                self.board[idx] = player_mark
                if self.check_winner(player_mark):
                    self.board[idx] = " "
                    return idx
                self.board[idx] = " "
            return None

        def check_fork_opportunities():
            fork_candidates = []
            for idx in empty:
                self.board[idx] = bot_mark
                win_count = 0
                for i in range(self.size * self.size):
                    if self.board[i] == bot_mark:
                        continue
                    self.board[i] = bot_mark
                    if self.check_winner(bot_mark):
                        win_count += 1
                    self.board[i] = " "
                if win_count >= 2:
                    fork_candidates.append((win_count, idx))
                self.board[idx] = " "

            if fork_candidates:
                return max(fork_candidates)[1]
            return None

        def check_block_fork():
            for idx in empty:
                self.board[idx] = player_mark
                fork_count = 0
                for test_idx in empty:
                    if test_idx == idx:
                        continue
                    self.board[test_idx] = player_mark
                    if self.check_winner(player_mark):
                        fork_count += 1
                    self.board[test_idx] = " "
                if fork_count >= 2:
                    self.board[idx] = " "
                    return idx
                self.board[idx] = " "
            return None

        def get_center_control():
            n = self.size
            center = n // 2
            center_idx = center * n + center
            if self.board[center_idx] == " ":
                return center_idx

            if n == 5:
                center_zone = [6, 7, 8, 11, 12, 13, 16, 17, 18]
                available = [c for c in center_zone if self.board[c] == " "]
                if available:
                    return random.choice(available)
            return None

        def check_multi_threat():
            n = self.size
            threats = []

            for idx in empty:
                threat_count = 0
                self.board[idx] = bot_mark

                x, y = idx // n, idx % n
                for dx, dy in [(0, 1), (1, 0), (1, 1), (1, -1)]:
                    count = 1
                    for step in range(1, self.win_length):
                        nx, ny = x + dx * step, y + dy * step
                        if 0 <= nx < n and 0 <= ny < n and self.board[nx * n + ny] == bot_mark:
                            count += 1
                        else:
                            break
                    for step in range(1, self.win_length):
                        nx, ny = x - dx * step, y - dy * step
                        if 0 <= nx < n and 0 <= ny < n and self.board[nx * n + ny] == bot_mark:
                            count += 1
                        else:
                            break

                    if count >= self.win_length - 1:
                        threat_count += 1

                if threat_count > 0:
                    threats.append((threat_count, idx))
                self.board[idx] = " "

            if threats:
                return max(threats)[1]
            return None

        def check_defensive_threat():
            n = self.size
            for idx in empty:
                self.board[idx] = player_mark
                threat = False

                x, y = idx // n, idx % n
                for dx, dy in [(0, 1), (1, 0), (1, 1), (1, -1)]:
                    count = 1
                    for step in range(1, self.win_length):
                        nx, ny = x + dx * step, y + dy * step
                        if 0 <= nx < n and 0 <= ny < n and self.board[nx * n + ny] == player_mark:
                            count += 1
                        else:
                            break
                    for step in range(1, self.win_length):
                        nx, ny = x - dx * step, y - dy * step
                        if 0 <= nx < n and 0 <= ny < n and self.board[nx * n + ny] == player_mark:
                            count += 1
                        else:
                            break

                    if count >= self.win_length - 1:
                        threat = True
                        break

                self.board[idx] = " "
                if threat:
                    return idx
            return None

        def get_corner_strategy():
            n = self.size
            if n == 5:
                corners = [0, 4, 20, 24]
            else:
                corners = [0, 2, 6, 8]

            player_corners = []
            for corner in corners:
                if self.board[corner] == player_mark:
                    player_corners.append(corner)

            if player_corners and n == 3:
                opposite_map = {0: 8, 2: 6, 6: 2, 8: 0}
                for pc in player_corners:
                    opposite = opposite_map.get(pc)
                    if opposite and self.board[opposite] == " ":
                        return opposite

            available = [c for c in corners if self.board[c] == " "]
            if available:
                return random.choice(available)
            return None

        def get_edge_strategy():
            n = self.size
            if n == 5:
                edges = {
                    1: 30, 2: 25, 3: 30,
                    5: 25, 9: 20, 10: 15, 14: 20, 15: 25,
                    19: 30, 21: 25, 22: 30, 23: 30
                }
                available = [(idx, priority) for idx, priority in edges.items()
                             if idx < len(self.board) and self.board[idx] == " "]
                if available:
                    return max(available, key=lambda x: x[1])[0]
            else:
                edges = [1, 3, 5, 7]
                available = [e for e in edges if self.board[e] == " "]
                if available:
                    return random.choice(available)
            return None

        def get_best_position():
            scored_positions = []
            for idx in empty:
                score = get_position_score(idx)

                n = self.size
                x, y = idx // n, idx % n
                connection_bonus = 0
                for dx, dy in [(0, 1), (1, 0), (1, 1), (1, -1)]:
                    count = 1
                    for step in range(1, self.win_length):
                        nx, ny = x + dx * step, y + dy * step
                        if 0 <= nx < n and 0 <= ny < n and self.board[nx * n + ny] == bot_mark:
                            count += 1
                        else:
                            break
                    for step in range(1, self.win_length):
                        nx, ny = x - dx * step, y - dy * step
                        if 0 <= nx < n and 0 <= ny < n and self.board[nx * n + ny] == bot_mark:
                            count += 1
                        else:
                            break
                    if count > 1:
                        connection_bonus += count * 10

                score += connection_bonus
                scored_positions.append((score, idx))

            if scored_positions:
                return max(scored_positions)[1]
            return None

        def random_move():
            return random.choice(empty)


        strategies = [
            check_immediate_win,
            check_block_player,
            check_fork_opportunities,
            check_block_fork,
            get_center_control,
            check_multi_threat,
            check_defensive_threat,
            get_corner_strategy,
            get_edge_strategy,
            get_best_position,
            random_move  
        ]

        if self.size == 5:
            strategies = [
                check_immediate_win,
                check_block_player,
                get_center_control,  
                check_fork_opportunities,
                check_block_fork,
                check_multi_threat,
                check_defensive_threat,
                get_corner_strategy,
                get_best_position,
                get_edge_strategy,
                random_move
            ]

        move = None
        for strategy in strategies:
            move = strategy()
            if move is not None:
                break

        if move is not None:
            btn = self.children[move]
            btn.label = bot_mark
            btn.style = discord.ButtonStyle.primary if bot_mark == "❌" else discord.ButtonStyle.danger
            btn.disabled = True
            self.board[move] = bot_mark

            if self.check_winner(bot_mark):
                self.winner = self.current
                for child in self.children:
                    child.disabled = True

                embed = discord.Embed(
                    title="🎉 Game Over!",
                    description=f"{self.winner.mention} wins!",
                    color=discord.Color.green()
                )
                await self.message.edit(embed=embed, view=self)

                if self.p1 != self.bot_user and self.p2 != self.bot_user:
                    loser = self.p2 if self.winner == self.p1 else self.p1
                    self.db.update_stats(self.winner.id, "win", "ttt", self.bot_user.id)
                    self.db.update_stats(loser.id, "loss", "ttt", self.bot_user.id)

                self.stop()

            elif all(cell != " " for cell in self.board):
                for child in self.children:
                    child.disabled = True

                embed = discord.Embed(
                    title="😐 Draw!",
                    description="The board is full!",
                    color=discord.Color.gold()
                )
                await self.message.edit(embed=embed, view=self)

                if self.p1 != self.bot_user and self.p2 != self.bot_user:
                    self.db.update_stats(self.p1.id, "draw", "ttt", self.bot_user.id)
                    self.db.update_stats(self.p2.id, "draw", "ttt", self.bot_user.id)

                self.stop()

            else:
                self.current = self.p2 if self.current == self.p1 else self.p1
                embed = discord.Embed(
                    title=f"TicTacToe {self.size}x{self.size}",
                    description=f"Your turn: {self.current.mention}",
                    color=discord.Color.blurple()
                )
                embed.add_field(
                    name="Players",
                    value=f"❌ {self.p1.mention}\n◯️ {self.p2.mention}",
                    inline=False
                )

                await self.message.edit(embed=embed, view=self)

    def check_winner(self, mark):
        n = self.size
        k = self.win_length
        board = self.board

        for i in range(n * n):
            if board[i] != mark:
                continue

            x, y = i // n, i % n

            for dx, dy in [(0, 1), (1, 0), (1, 1), (1, -1)]:
                count = 1
                for step in range(1, k):
                    nx, ny = x + dx * step, y + dy * step
                    ni = nx * n + ny

                    if 0 <= nx < n and 0 <= ny < n and board[ni] == mark:
                        count += 1
                    else:
                        break

                if count == k:
                    return True
        return False

    def create_embed(self, title: str, description: str) -> discord.Embed:
        color = discord.Color.blurple()
        if "win" in title.lower():
            color = discord.Color.green()
        elif "draw" in title.lower():
            color = discord.Color.gold()
        elif "time" in title.lower():
            color = discord.Color.red()
        embed = discord.Embed(title=title, description=f"{description}\n\n", color=color)
        return embed


class RPSInviteView(discord.ui.View):
    def __init__(self, challenger: discord.User, opponent: discord.User):
        super().__init__(timeout=60)
        self.challenger = challenger
        self.opponent = opponent
        self.accepted = None
        self.message = None

    @discord.ui.button(label="Accept ✅", style=discord.ButtonStyle.success)
    async def accept_button(self, button, interaction: discord.Interaction):
        if interaction.user != self.opponent:
            await interaction.response.send_message("❌ This invite is not for you.", ephemeral=True)
            return
        self.accepted = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content=f"{self.opponent.mention} accepted the challenge!", view=self)
        self.stop()

    @discord.ui.button(label="Decline ❌", style=discord.ButtonStyle.danger)
    async def decline_button(self, button, interaction: discord.Interaction):
        if interaction.user != self.opponent:
            await interaction.response.send_message("❌ This invite is not for you.", ephemeral=True)
            return
        self.accepted = False
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content=f"{self.opponent.mention} declined the challenge.", view=self)
        self.stop()



class TTTMatchView(discord.ui.View):
    def __init__(self, challenger: discord.User, opponent: discord.User):
        super().__init__(timeout=60)
        self.challenger = challenger
        self.opponent = opponent
        self.accepted = None
        self.message = None

    @discord.ui.button(label="Accept ✅", style=discord.ButtonStyle.success)
    async def accept_button(self, button, interaction: discord.Interaction):
        if interaction.user != self.opponent:
            await interaction.response.send_message("❌ This invite is not for you.", ephemeral=True)
            return
        self.accepted = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content=f"{self.opponent.mention} accepted the challenge!", view=self)
        self.stop()

    @discord.ui.button(label="Decline ❌", style=discord.ButtonStyle.danger)
    async def decline_button(self, button, interaction: discord.Interaction):
        if interaction.user != self.opponent:
            await interaction.response.send_message("❌ This invite is not for you.", ephemeral=True)
            return
        self.accepted = False
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content=f"{self.opponent.mention} declined the challenge.", view=self)
        self.stop()

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            await self.message.edit(content=f"⏰ Challenge expired! {self.opponent.mention} did not respond.", view=self)
        self.stop()



class Games(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot_user = bot.user
        self.db = GamesDatabase()

    games = discord.SlashCommandGroup("games", "Games and minigames")

    @games.command(name="rps", description="Play Rock-Paper-Scissors against bot or player")
    async def rps(self, ctx: discord.ApplicationContext, opponent: discord.User = None):
        opponent = opponent or self.bot.user

        if opponent == ctx.author:
            await ctx.respond("❌ You cannot play against yourself.", ephemeral=True)
            return

        if opponent == self.bot.user:
            view = RPSPlayView(ctx.author, self.bot.user, self.bot.user, db=self.db)
            await ctx.respond(">>> Choose your option against the bot:", view=view)
            view.message = await ctx.interaction.original_response()
            return

        invite_view = RPSInviteView(ctx.author, opponent)
        await ctx.respond(
            f"{ctx.author.mention} challenges {opponent.mention} to **Rock-Paper-Scissors**!",
            view=invite_view
        )
        invite_view.message = await ctx.interaction.original_response()

        await invite_view.wait()

        if invite_view.accepted is not True:
            if invite_view.accepted is False:
                await invite_view.message.edit(content=f"❌ {opponent.mention} declined.", view=None)
            return

        play_view = RPSPlayView(ctx.author, opponent, self.bot.user, db=self.db)
        await ctx.respond(
            f"{opponent.mention} accepted!\n>>> {ctx.author.mention} starts, choose your option:",
            view=play_view
        )
        play_view.message = await ctx.interaction.original_response()

    @games.command(name="tictactoe", description="Play TicTacToe in 3x3 or 5x5")
    async def tictactoe(
            self,
            ctx: discord.ApplicationContext,
            opponent: discord.User = None,
            mode: discord.Option(str, "Game mode", choices=["3x3", "5x5"]) = "3x3"
    ):
        opponent = opponent or self.bot.user
        size = 3 if mode == "3x3" else 5
        win_length = 3 if mode == "3x3" else 4

        if opponent == ctx.author:
            await ctx.respond("❌ You cannot play against yourself.", ephemeral=True)
            return

        if opponent.bot and opponent != self.bot.user:
            await ctx.respond("❌ You can only play against real players or your own bot.", ephemeral=True)
            return

        if opponent == self.bot.user:
            start_embed = discord.Embed(
                title=f"TicTacToe {size}x{size}",
                description=f"Your turn: {ctx.author.mention}",
                color=discord.Color.blurple()
            )
            start_embed.add_field(
                name="Players",
                value=f"❌ {ctx.author.mention}\n◯️ {opponent.mention}",
                inline=False
            )

            game_view = TicTacToeView(ctx.author, opponent, bot_user=self.bot.user, db=self.db, size=size,
                                      win_length=win_length)
            await ctx.respond(embed=start_embed, view=game_view)
            game_view.message = await ctx.interaction.original_response()
            return

        confirm_view = TTTMatchView(ctx.author, opponent)
        await ctx.respond(
            f"{ctx.author.mention} challenges {opponent.mention} to **TicTacToe {mode}**!",
            view=confirm_view
        )
        confirm_view.message = await ctx.interaction.original_response()

        await confirm_view.wait()

        if confirm_view.accepted is not True:
            if confirm_view.accepted is False:
                await confirm_view.message.edit(content=f"❌ {opponent.mention} declined.", view=None)
            return

        start_embed = discord.Embed(
            title=f"TicTacToe {size}x{size}",
            description=f"Your turn: {ctx.author.mention}",
            color=discord.Color.blurple()
        )
        start_embed.add_field(
            name="Players",
            value=f"❌ {ctx.author.mention}\n◯️ {opponent.mention}",
            inline=False
        )

        game_view = TicTacToeView(ctx.author, opponent, self.bot.user, db=self.db, size=size, win_length=win_length)

        await confirm_view.message.edit(content=None, embed=start_embed, view=game_view)
        game_view.message = confirm_view.message

    @games.command(name="stats", description="Show your RPS or TTT statistics")
    @discord.option("game", choices=["Rock-Paper-Scissors", "TicTacToe"], description="Choose the game", required=True)
    @discord.option("user", description="User whose stats are displayed", required=False)
    async def stats(self, ctx: discord.ApplicationContext, game: str, user: discord.User = None):
        target = user or ctx.author

        game_mapping = {
            "Rock-Paper-Scissors": "Rock_Paper_Scissors",
            "TicTacToe": "TicTacToe"
        }
        table = game_mapping.get(game)
        if not table:
            return await ctx.respond(f"Unknown game: {game}", ephemeral=True)

        try:
            with sqlite3.connect(DB_PATH) as conn:
                cur = conn.cursor()
                cur.execute(f"SELECT wins, losses, draws FROM {table} WHERE user_id=?", (target.id,))
                row = cur.fetchone()
        except sqlite3.Error as e:
            await ctx.respond(f"DB error: {e}", ephemeral=True)
            return

        if not row:
            return await ctx.respond(
                f"No {game} stats found for {target.mention} | {target.display_name} ({target.id}).",
                ephemeral=True)

        wins, losses, draws = row
        total = wins + losses + draws
        winrate = (wins / total * 100) if total else 0
        lossrate = (losses / total * 100) if total else 0
        drawrate = (draws / total * 100) if total else 0

        def make_bar(rate):
            filled = int(rate // 10)
            return "█" * filled + "░" * (10 - filled)

        if game == "Rock-Paper-Scissors":
            if winrate >= 70:
                rank_label = "🏆 Pro"
            elif winrate >= 50:
                rank_label = "⭐ Advanced"
            elif winrate >= 30:
                rank_label = "📈 Learning"
            else:
                rank_label = "🥱 Beginner"
        else:
            rank_label = "TicTacToe Player"

        embed = discord.Embed(
            title=f"📊 {game} - Statistics – {target.display_name}",
            description=f"Rank: **{rank_label}**",
            color=discord.Color.blurple()
        )

        embed.add_field(name="🏆 Wins", value=f"{wins}", inline=True)
        embed.add_field(name="💀 Losses", value=f"{losses}", inline=True)
        embed.add_field(name="🤝 Draws", value=f"{draws}", inline=True)
        embed.add_field(name="🎮 Total games", value=f"{total}", inline=False)
        embed.add_field(name="Winrate", value=f"{winrate:.1f}%\n{make_bar(winrate)}", inline=False)
        embed.add_field(name="Lossrate", value=f"{lossrate:.1f}%\n{make_bar(lossrate)}", inline=False)
        embed.add_field(name="Drawrate", value=f"{drawrate:.1f}%\n{make_bar(drawrate)}", inline=False)
        embed.set_footer(text=f"{game} • Statistics")

        return await ctx.respond(embed=embed)


def setup(bot):
    bot.add_cog(Games(bot))
