from utils.imports import *

class HelpView(View):
    def __init__(self, bot: discord.Bot, embeds, page_info=None):
        super().__init__(timeout=60)
        self.bot = bot
        self.embeds = embeds
        self.current_page = 0
        self.page_info = page_info or {}

        self.prev_button = Button(label="⬅️", style=discord.ButtonStyle.secondary)
        self.next_button = Button(label="➡️", style=discord.ButtonStyle.secondary)
        self.prev_button.callback = self.prev_page
        self.next_button.callback = self.next_page

        options = []
        # splits slash commands if in a cog has too many due to discord limitations
        for idx, embed in enumerate(embeds):
            if "📂" in embed.title:
                base_name = embed.title.split("📂 ")[1].split(" (Page")[0].split(" Commands")[0]
            else:
                base_name = embed.title[:50]

            if idx in self.page_info and self.page_info[idx]['total_pages'] > 1:
                label = f"{base_name} (Pg {self.page_info[idx]['page']}/{self.page_info[idx]['total_pages']})"
            else:
                label = base_name

            if len(label) > 100:
                label = label[:97] + "..."

            options.append(
                discord.SelectOption(
                    label=label,
                    value=str(idx),
                    description=f"{len(embed.fields)} Commands"
                )
            )

        self.select_menu = Select(
            placeholder="Select category...",
            options=options[:25]
        )
        self.select_menu.callback = self.select_category

        self.add_item(self.select_menu)
        self.add_item(self.prev_button)
        self.add_item(self.next_button)
        self.update_buttons()

    async def on_timeout(self):
        try:
            for item in self.children:
                item.disabled = True

            if hasattr(self, 'message'):
                await self.message.edit(view=self)
        except discord.NotFound:
            pass
        except Exception as e:
            print(f"Error on timeout: {e}")

    async def prev_page(self, interaction: discord.Interaction):
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    async def next_page(self, interaction: discord.Interaction):
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    async def select_category(self, interaction: discord.Interaction):
        self.current_page = int(self.select_menu.values[0])
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    def update_buttons(self):
        self.prev_button.disabled = self.current_page <= 0
        self.next_button.disabled = self.current_page >= len(self.embeds) - 1
        for option in self.select_menu.options:
            option.default = (option.value == str(self.current_page))


def is_owner_command(cmd):
    if getattr(cmd, "owner_only", False):
        return True
    if hasattr(cmd, "subcommands") and any(getattr(sub, "owner_only", False) for sub in cmd.subcommands):
        return True
    for check in getattr(cmd, "checks", []):
        if getattr(check, "__name__", "") == "predicate" and "is_owner" in repr(check):
            return True
    return False


def is_visible_command(cmd):
    if type(cmd).__name__ not in ("SlashCommand", "SlashCommandGroup"):
        return False
    if is_owner_command(cmd):
        return False
    return True


def gather_commands_recursive(cmd, prefix=""):
    cmds = []
    if not is_visible_command(cmd):
        return cmds

    current_name = f"{prefix}{cmd.name}"
    if hasattr(cmd, "subcommands") and cmd.subcommands:
        for sub in cmd.subcommands:
            cmds.extend(gather_commands_recursive(sub, prefix=current_name + " "))
    else:
        cmds.append((current_name.strip(), cmd.description or "No description"))
    return cmds

# ---------------------------------------

class User(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.MAX_FIELDS_PER_EMBED = 20
        self.start_time = datetime.now(timezone.utc)


    def format_timedelta(self, delta: timedelta) -> str:
        days = delta.days
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"🗓️ {days}d ⏰ {hours}h ⏳ {minutes}m ⏲️ {seconds}s"

    def time_ago(self, dt: datetime) -> str:
        if dt is None:
            return "Not available"
        if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        seconds = int(delta.total_seconds())

        if seconds < 60:
            return f"vor {seconds} seconds"
        elif seconds < 3600:
            return f"vor {seconds // 60} minutes"
        elif seconds < 86400:
            return f"vor {seconds // 3600} hours"
        elif seconds < 2592000:
            return f"vor {seconds // 86400} days"
        elif seconds < 31536000:
            return f"vor {seconds // 2592000} months"
        else:
            return f"vor {seconds // 31536000} years"


    @slash_command(name="about", description="Detailed stats about the bot.")
    async def about(self, ctx: discord.ApplicationContext):
        try:
            await ctx.defer()

            now = datetime.now(timezone.utc)
            uptime = now - self.start_time
            start = time.perf_counter()

            python_version = platform.python_version()
            discord_py_version = discord.__version__
            system_info = f"{platform.system()} {platform.release()}"

            cpu_percent = psutil.cpu_percent(interval=0.1)
            ram_percent = psutil.virtual_memory().percent

            created_at = self.bot.user.created_at if self.bot.user else None
            created_str = "Not available" if not created_at else f"{format_dt(created_at, 'F')} ({format_dt(created_at, 'R')})"

            ws_ping = round(self.bot.latency * 1000, 2)
            cmd_latency = round((time.perf_counter() - start) * 1000, 2)

            try:
                await self.bot.http.request(discord.http.Route("GET", "/gateway"))
                api_ping = round((time.perf_counter() - start) * 1000, 2)
            except Exception:
                api_ping = None

            embed = discord.Embed(
                title="🤖 Bot-Infos",
                description="# [GitHub](https://github.com/InvalidDavid/Y-K-Bot)",
                color=discord.Color.blurple(),
                timestamp=now
            )

            embed.add_field(name="🆔 Bot ID",
                            value=f"```{self.bot.user.id if self.bot.user else 'N/A'}```",
                            inline=True)
            embed.add_field(name="📛 Bot Name", value=f"```{self.bot.user}```", inline=True)

            embed.add_field(name="📅 Bot created", value=f"{created_str}", inline=False)

            embed.add_field(name="🕰️ Bot Uptime",
                            value=(f"```{self.format_timedelta(uptime)}```"
                                   f"Last restart: {format_dt(self.start_time, 'F')} ({format_dt(self.start_time, 'R')})"),
                            inline=False)

            embed.add_field(name="🏓 WebSocket Ping", value=f"```{ws_ping} ms```",
                            inline=True)
            embed.add_field(name="📡 API Ping",
                            value=f"```{api_ping if api_ping is not None else 'Fehler'} ms```",
                            inline=True)
            embed.add_field(name="⚡ Command-Reactiontime", value=f"```{cmd_latency} ms```", inline=True)


            embed.add_field(name="💻 CPU", value=f"```{cpu_percent:.1f}%```",
                            inline=True)
            embed.add_field(name="🧠 RAM", value=f"```{ram_percent:.2f}%```",
                            inline=True)
            embed.add_field(name="🖥️ Platform", value=f"```{system_info}```", inline=True)


            embed.add_field(name="🐍 Python Version", value=f"```{python_version}```",
                            inline=True)
            embed.add_field(name="📦 Py-cord Version", value=f"```{discord_py_version}```",
                            inline=True)

            embed.set_footer(text=f"Requested from {ctx.author}", icon_url=ctx.author.display_avatar.url)
            await ctx.respond(embed=embed)
        except Exception as e:
            await ctx.respond(f"Error: {e}", ephemeral=True)



    # ---------------------------------------



    @slash_command(name="help", description="Show all Slash commands, that u as a User can use.")
    async def help_command(self, ctx: discord.ApplicationContext):
        embeds = []
        page_info = {}
        embed_index = 0

        for cog_name, cog in self.bot.cogs.items():
            if cog_name in ["Jishaku", "Owner"]:
                continue

            commands_list = getattr(cog, "get_commands", lambda: [])()
            all_cmds = []

            for cmd in commands_list:
                if not is_visible_command(cmd):
                    continue
                all_cmds.extend(gather_commands_recursive(cmd))

            if not all_cmds:
                continue

            chunks = [all_cmds[i:i + self.MAX_FIELDS_PER_EMBED]
                      for i in range(0, len(all_cmds), self.MAX_FIELDS_PER_EMBED)]

            total_pages = len(chunks)

            for page_num, chunk in enumerate(chunks, 1):
                if total_pages > 1:
                    title = f"📂 {cog_name} Commands (Page {page_num}/{total_pages})"
                    description = f"Commands from `{cog_name}` - Page {page_num} of {total_pages}"
                else:
                    title = f"📂 {cog_name} Commands"
                    description = f"All commands from `{cog_name}`"

                embed = discord.Embed(
                    title=title,
                    description=description,
                    color=discord.Color.blurple()
                )

                page_info[embed_index] = {
                    'cog_name': cog_name,
                    'page': page_num,
                    'total_pages': total_pages
                }

                for name, desc in chunk:
                    if len(desc) > 100:
                        desc = desc[:97] + "..."

                    embed.add_field(
                        name=f"/{name}",
                        value=desc,
                        inline=False
                    )

                embeds.append(embed)
                embed_index += 1

        if not embeds:
            await ctx.respond("No visible commands found.", ephemeral=True)
            return

        if len(embeds) > 25:
            embeds, page_info = self._create_category_pages(embeds, page_info)

        view = HelpView(self.bot, embeds, page_info)
        msg = await ctx.respond(embed=embeds[0], view=view, ephemeral=True)
        view.message = await msg.original_response()

    def _create_category_pages(self, embeds, page_info):
        final_embeds = []
        final_page_info = {}
        new_index = 0

        for i in range(0, len(embeds), 25):
            chunk_embeds = embeds[i:i + 25]
            chunk_start = i + 1
            chunk_end = min(i + 25, len(embeds))

            overview_embed = discord.Embed(
                title=f"📚 Help Overview (Part {i // 25 + 1})",
                description=f"Categories {chunk_start}-{chunk_end} of {len(embeds)}\nUse the select menu below to navigate.",
                color=discord.Color.blurple()
            )

            field_count = 0
            for j, embed in enumerate(chunk_embeds):
                if field_count >= 25:
                    break

                if "📂" in embed.title:
                    category = embed.title.split("📂 ")[1]
                    if " (Page" in category:
                        category = category.split(" (Page")[0]
                else:
                    category = embed.title[:50]

                page_num = i + j + 1
                overview_embed.add_field(
                    name=f"Page {page_num}: {category[:250]}",
                    value=f"📄 {len(embed.fields)} commands",
                    inline=True
                )
                field_count += 1

            final_embeds.append(overview_embed)
            final_page_info[new_index] = {
                'cog_name': 'Overview',
                'page': i // 25 + 1,
                'total_pages': (len(embeds) + 24) // 25
            }
            new_index += 1

            for j, embed in enumerate(chunk_embeds):
                final_embeds.append(embed)
                original_index = i + j
                if original_index in page_info:
                    final_page_info[new_index] = page_info[original_index]
                new_index += 1

        return final_embeds, final_page_info



    # ---------------------------------------



def setup(bot):
    bot.add_cog(User(bot))
