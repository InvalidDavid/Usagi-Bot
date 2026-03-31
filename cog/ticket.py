from discord import Embed
from discord.commands import option
from typing import List, Tuple, Optional
import json
from utils.imports import *

DB_PATH = "Data/ticket.db"


class TicketDatabase:
    def __init__(self, db_name: str = DB_PATH):
        self.conn = sqlite3.connect(db_name)
        self._create_tables()

    def _create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            thread_id INTEGER NOT NULL,
            creator_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            category TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            closed_at TIMESTAMP NULL,
            closed_by INTEGER NULL
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS ticket_settings (
            guild_id INTEGER PRIMARY KEY,
            support_role_id INTEGER NULL,
            transcript_channel_id INTEGER NULL,
            ticket_channel_id INTEGER NULL,
            log_channel_id INTEGER NULL
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS ticket_categories (
            guild_id INTEGER NOT NULL,
            category_name TEXT NOT NULL,
            description TEXT NOT NULL,
            PRIMARY KEY (guild_id, category_name)
        )
        """)


        cursor.execute("""
        CREATE TABLE IF NOT EXISTS ticket_panels (
            guild_id INTEGER PRIMARY KEY,
            embed_json TEXT NOT NULL,
            message_id INTEGER NULL
        )
        """)

        self.conn.commit()

    def create_ticket(self, guild_id: int, thread_id: int, creator_id: int, category: str) -> int:
        cursor = self.conn.cursor()
        cursor.execute("""
        INSERT INTO tickets (guild_id, thread_id, creator_id, category)
        VALUES (?, ?, ?, ?)
        """, (guild_id, thread_id, creator_id, category))
        self.conn.commit()
        return cursor.lastrowid

    def close_ticket(self, ticket_id: int, closed_by: int):
        cursor = self.conn.cursor()
        cursor.execute("""
        UPDATE tickets 
        SET status = 'closed', 
            closed_at = CURRENT_TIMESTAMP,
            closed_by = ?
        WHERE ticket_id = ?
        """, (closed_by, ticket_id))
        self.conn.commit()

    def get_ticket(self, thread_id: int) -> Optional[Tuple]:
        cursor = self.conn.cursor()
        cursor.execute("""
        SELECT * FROM tickets 
        WHERE thread_id = ? AND status = 'open'
        """, (thread_id,))
        return cursor.fetchone()

    def get_user_tickets(self, guild_id: int, user_id: int) -> List[Tuple]:
        cursor = self.conn.cursor()
        cursor.execute("""
        SELECT * FROM tickets 
        WHERE guild_id = ? AND creator_id = ? AND status = 'open'
        """, (guild_id, user_id))
        return cursor.fetchall()

    def update_settings(self, guild_id: int, support_role_id: int = None,
                           transcript_channel_id: int = None, ticket_channel_id: int = None,
                           log_channel_id: int = None):
        cursor = self.conn.cursor()
        cursor.execute("""
        INSERT OR REPLACE INTO ticket_settings 
        (guild_id, support_role_id, transcript_channel_id, ticket_channel_id, log_channel_id)
        VALUES (?, ?, ?, ?, ?)
        """, (guild_id, support_role_id, transcript_channel_id, ticket_channel_id, log_channel_id))
        self.conn.commit()

    def get_settings(self, guild_id: int) -> Optional[Tuple]:
        cursor = self.conn.cursor()
        cursor.execute("""
        SELECT * FROM ticket_settings 
        WHERE guild_id = ?
        """, (guild_id,))
        return cursor.fetchone()

    def add_category(self, guild_id: int, name: str, description: str):
        cursor = self.conn.cursor()
        cursor.execute("""
        INSERT OR REPLACE INTO ticket_categories 
        (guild_id, category_name, description)
        VALUES (?, ?, ?)
        """, (guild_id, name, description))
        self.conn.commit()

    def remove_category(self, guild_id: int, name: str):
        cursor = self.conn.cursor()
        cursor.execute("""
        DELETE FROM ticket_categories 
        WHERE guild_id = ? AND category_name = ?
        """, (guild_id, name))
        self.conn.commit()

    def get_categories(self, guild_id: int) -> List[Tuple]:
        cursor = self.conn.cursor()
        cursor.execute("""
        SELECT * FROM ticket_categories 
        WHERE guild_id = ?
        """, (guild_id,))
        return cursor.fetchall()


        self.conn.commit()

    def save_panel(self, guild_id: int, embed: discord.Embed, message_id: int = None):
        try:
            embed_dict = embed.to_dict()
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO ticket_panels 
                (guild_id, embed_json, message_id)
                VALUES (?, ?, ?)
            """, (guild_id, json.dumps(embed_dict), message_id))
            self.conn.commit()
        except Exception as e:
            print(f"Error saving embed: {e}")

    def load_panel(self, guild_id: int) -> Optional[Tuple]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT embed_json, message_id FROM ticket_panels WHERE guild_id = ?", (guild_id,))
        result = cursor.fetchone()
        if result:
            try:
                embed_dict = json.loads(result[0])
                return discord.Embed.from_dict(embed_dict), result[1]
            except Exception as e:
                print(f"[Error loading embed] {e}")
        return None, None


    def close(self):
        self.conn.close()

async def autocomplete_category_list(self, ctx: discord.AutocompleteContext):
    guild_id = ctx.interaction.guild_id
    query = ctx.value.lower()

    categories = self.db.get_categories(guild_id)
    return [
               name for _, name, _ in categories
               if query in name.lower()
           ][:25]



class TicketCategoryView(discord.ui.View):
    def __init__(self, db, settings, categories, create_ticket_callback):
        super().__init__(timeout=None)
        self.db = db
        self.settings = settings
        self.categories = categories
        self.create_ticket_callback = create_ticket_callback

        self.add_item(TicketCategorySelect(db, settings, categories, create_ticket_callback))



class TicketCategorySelect(discord.ui.Select):
    def __init__(self, db, settings, categories, create_ticket_callback):
        options = [
            discord.SelectOption(
                label=category[1],
                description=category[2],
                value=category[1]
            ) for category in categories
        ]
        super().__init__(
            placeholder="Choose a category",
            options=options,
            min_values=1,
            max_values=1
        )
        self.db = db
        self.settings = settings
        self.create_ticket_callback = create_ticket_callback

    async def callback(self, interaction: discord.Interaction):
        await self.create_ticket_callback(interaction, self.settings, self.values[0])
        self.view.clear_items()
        message = await interaction.original_response()
        await message.edit(view=self.view, delete_after=10)





class TicketCreateView(discord.ui.View):
    def __init__(self, bot, db):
        super().__init__(timeout=None)
        self.bot = bot
        self.db = db

        button = discord.ui.Button(
            label="Create Ticket",
            style=discord.ButtonStyle.primary,
            custom_id="ticket_create_button",
            emoji="🎫"
        )
        button.callback = self.button_callback
        self.add_item(button)

    async def button_callback(self, interaction: discord.Interaction):
        try:
            if not interaction.guild:
                return await interaction.response.send_message(
                    "❌ This command can only be used in a server.",
                    ephemeral=True
                )


            settings = self.db.get_settings(interaction.guild.id)
            if not settings:
                return await interaction.response.send_message(
                    "❌ The ticket system has not been set up on this server yet.",
                    ephemeral=True
                )


            categories = self.db.get_categories(interaction.guild.id)
            if not categories:
                return await interaction.response.send_message(
                    "❌ No ticket categories are configured.",
                    ephemeral=True
                )

            else:
                view = TicketCategoryView(self.db, settings, categories, self._create_ticket)
                await interaction.response.send_message(
                    "Please choose a category:",
                    view=view,
                    ephemeral=True
                )

        except Exception as e:
            print(f"Error in button callback: {e}")
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(
                        "❌ An error occurred. Please try again later.",
                        ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        "❌ An error occurred. Please try again later.",
                        ephemeral=True
                    )
            except Exception as e2:
                print(f"Error handling error: {e2}")


    async def _create_ticket(self, interaction: discord.Interaction, settings: Tuple, category_name: str):
        try:
            await interaction.response.defer(ephemeral=True)

            guild = interaction.guild
            member = interaction.user

            existing_tickets = self.db.get_user_tickets(guild.id, member.id)
            if existing_tickets:
                await interaction.followup.send(
                    f"❌ You already have an open ticket: <#{existing_tickets[0][2]}>",
                    ephemeral=True
                )
                return

            ticket_channel = guild.get_channel(settings[3])
            if not ticket_channel:
                await interaction.followup.send("❌ Ticket channel not found!", ephemeral=True)
                return



            thread = await ticket_channel.create_thread(
                name=f"Ticket-{member.display_name}",
                type=discord.ChannelType.private_thread,
                invitable=False
            )

            await thread.add_user(member)
            support_role = guild.get_role(settings[1])
            if support_role:
                for support_member in support_role.members:
                    try:
                        await thread.add_user(support_member)
                    except discord.HTTPException:
                        continue

            ticket_id = self.db.create_ticket(guild.id, thread.id, member.id, category_name)

            embed = discord.Embed(
                title=f"Ticket #{ticket_id} - {category_name}",
                description=(
                    f"Hello {member.mention},\n"
                    f"Your private ticket has been created. Please describe your issue as precisely as possible.\n"
                    f"The support team will get back to you soon.\n"
                    f"**Category:** {category_name}\n"
                    f"**Created at:** {discord.utils.format_dt(datetime.now(), 'f')}"
                ),
                color=discord.Color.blue()
            )

            await thread.send(
                content=f"{member.mention} {support_role.mention if support_role else ''}",
                embed=embed,
                view=TicketManagementView(self.bot, self.db)
            )

            await interaction.followup.send(
                f"✅ Your private ticket has been created: {thread.mention}",
                ephemeral=True
            )

            log_channel = guild.get_channel(settings[4]) if settings[4] else None
            if log_channel:
                log_embed = discord.Embed(
                    title="📥 New ticket created",
                    color=discord.Color.green(),
                    description=(
                        f"**Ticket ID:** #{ticket_id}\n"
                        f"**User:** {member.mention} ({member.id})\n"
                        f"**Category:** {category_name}\n"
                        f"**Thread:** {thread.mention}"
                    )
                )
                await log_channel.send(embed=log_embed)
            else:
                return
        except Exception as e:
            print(f"Error creating ticket: {e}")
            try:
                await interaction.followup.send("❌ Error while creating the ticket.", ephemeral=True)
            except Exception as e2:
                print(f"Error sending error message: {e2}")




class TicketManagementView(discord.ui.View):
    def __init__(self, bot, db):
        super().__init__(timeout=None)
        self.bot = bot
        self.db = db

        button = discord.ui.Button(
            label="Close",
            style=discord.ButtonStyle.red,
            custom_id="ticket_close_button",
            emoji="🔒"
        )
        button.callback = self.close_ticket
        self.add_item(button)

    async def close_ticket(self, interaction: discord.Interaction):
        ticket = self.db.get_ticket(interaction.channel.id)
        if not ticket:
            await interaction.response.send_message("❌ This is not a valid ticket.", ephemeral=True)
            return

        settings = self.db.get_settings(interaction.guild.id)
        member = interaction.guild.get_member(ticket[3])

        if not (interaction.user.guild_permissions.administrator or
                (settings and interaction.user.get_role(settings[1])) or
                interaction.user.id == ticket[3]):
            await interaction.response.send_message(
                "❌ You do not have permission to close this ticket.",
                ephemeral=True
            )
            return

        confirm_view = discord.ui.View()
        confirm_button = discord.ui.Button(
            style=discord.ButtonStyle.green,
            label="Confirm",
            custom_id=f"confirm_close_{interaction.channel.id}"
        )
        cancel_button = discord.ui.Button(
            style=discord.ButtonStyle.red,
            label="Cancel",
            custom_id=f"cancel_close_{interaction.channel.id}"
        )
        confirm_view.add_item(confirm_button)
        confirm_view.add_item(cancel_button)

        embed = discord.Embed(
            title="Really close ticket?",
            description="Do you really want to close this ticket?",
            color=discord.Color.orange()
        )

        await interaction.response.send_message(
            embed=embed,
            view=confirm_view,
            ephemeral=True
        )

        message = await interaction.original_response()

        def check(i: discord.Interaction):
            return i.user == interaction.user and i.message.id == message.id

        try:
            confirm_interaction = await self.bot.wait_for(
                "interaction",
                check=check,
                timeout=30.0
            )

            for child in confirm_view.children:
                child.disabled = True

            try:
                await message.edit(view=None)
                await message.delete(delay=5.0)
            except discord.NotFound:
                pass

            if f"confirm_close_{interaction.channel.id}" in confirm_interaction.data["custom_id"]:
                await self._finalize_close(interaction, ticket, settings, member)
            else:
                await confirm_interaction.response.send_message(
                    "✅ Ticket closing cancelled.",
                    ephemeral=True
                )

        except asyncio.TimeoutError:
            for child in confirm_view.children:
                child.disabled = True
            try:
                await message.edit(view=confirm_view)
                await message.delete(delay=5.0)
            except discord.NotFound:
                pass

            await interaction.followup.send(
                "❌ Timeout. Ticket was not closed.",
                ephemeral=True
            )

    async def _finalize_close(self, interaction, ticket, settings, member):
        messages = []
        async for message in interaction.channel.history(limit=None, oldest_first=True):
            messages.append(f"{message.author.display_name} ({message.author.id}): {message.content}")

        transcript = "\n".join(messages)

        transcript_file = discord.File(
            io.BytesIO(transcript.encode("utf-8")),
            filename=f"transcript-{ticket[0]}.txt"
        )

        # transcript_channel = interaction.guild.get_channel(settings[2]) if settings else None
        #if transcript_channel:
         #   await transcript_channel.send(
          #      content=f"📄 Transcript for ticket #{ticket[0]} ({ticket[4]})",
            #    file=transcript_file
           # )

        self.db.close_ticket(ticket[0], interaction.user.id)

        thread = interaction.channel
        await thread.edit(
            name=f"closed-{thread.name}",
            archived=True,
            locked=True
        )

        try:
            created_at = discord.utils.format_dt(datetime.fromisoformat(ticket[6]), 'f')
        except (ValueError, IndexError):
            created_at = "Unknown"


        embed = discord.Embed(
            title=f"Ticket #{ticket[0]} closed",
            description=(
                f"The ticket was closed by {interaction.user.mention}.\n"
                f"**Creator:** {member.mention if member else 'Unknown'}\n"
                f"**Created at:** {created_at}\n"
                f"**Closed at:** {discord.utils.format_dt(datetime.now(), 'f')}"
            ),
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed, file=transcript_file)

        self.stop()

        if settings[4]:
            log_channel = interaction.guild.get_channel(settings[4])
            if log_channel:
                log_embed = discord.Embed(
                    title="Ticket closed",
                    color=discord.Color.red(),
                    description=(
                        f"**Ticket ID:** #{ticket[0]}\n"
                        f"**Closed by:** {interaction.user.mention} ({interaction.user.id})\n"
                        f"**Creator:** {member.mention if member else 'Unknown'} ({ticket[3]})\n"
                        f"**Thread:** {interaction.channel.mention}"
                    )
                )
                await log_channel.send(embed=log_embed, file=transcript_file)




class TicketSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = TicketDatabase()
        self.bot.loop.create_task(self.initialize_views())

    async def initialize_views(self):
        await self.bot.wait_until_ready()
        self.bot.add_view(TicketCreateView(self.bot, self.db))
        self.bot.add_view(TicketManagementView(self.bot, self.db))

    ticket = SlashCommandGroup("ticket", "Ticket system commands")
    category = ticket.create_subgroup("category", description="Ticket category")

    @ticket.command(name="settings", description="Changes the ticket system settings")
    @commands.has_permissions(administrator=True)
    async def ticket_settings(self, ctx):
        settings = self.db.get_settings(ctx.guild.id)
        if not settings:
            return await ctx.respond(
                "❌ The ticket system has not been set up yet! Please use `/ticket setup` first.",
                ephemeral=True
            )

        embed = discord.Embed(
            title="🎛️ Ticket Settings",
            description="Choose below what you want to edit.",
            color=discord.Color.blurple()
        )
        embed.add_field(
            name="Current Settings",
            value=(
                f"**Support Role:** {f'<@&{settings[1]}>' if settings[1] else '❌ Not set'}\n"
                f"**Transcript Channel:** {f'<#{settings[2]}>' if settings[2] else '❌ Not set'}\n"
                f"**Ticket Channel:** {f'<#{settings[3]}>' if settings[3] else '❌ Not set'}\n"
                f"**Log Channel:** {f'<#{settings[4]}>' if settings[4] else '❌ Not set'}"
            ),
            inline=False
        )

        view = SettingsSelectionView(self.db, ctx.guild.id, ctx.user, self.bot)
        msg = await ctx.respond(embed=embed, view=view, ephemeral=True)
        view.message = await msg.original_response()

    @ticket.command(name="setup", description="Sets up the ticket system")
    @commands.has_permissions(administrator=True)
    async def setup_ticket(
            self,
            ctx,
            support_role: Option(discord.Role, "Role for support members"),
            transcript_channel: Option(discord.TextChannel, "Channel for transcripts"),
            ticket_channel: Option(discord.TextChannel, "Channel for ticket threads"),
            log_channel: Option(discord.TextChannel, "Channel for logs", required=False)
    ):
        self.db.update_settings(
            ctx.guild.id,
            support_role.id,
            transcript_channel.id,
            ticket_channel.id,
            log_channel.id if log_channel else None
        )

        embed = Embed(
            title="✅ Ticket system set up successfully",
            color=discord.Color.green(),
            description=f"""
            **Support Role:** {support_role.mention}
            **Transcript Channel:** {transcript_channel.mention}
            **Ticket Channel:** {ticket_channel.mention}
            **Log Channel:** {log_channel.mention if log_channel else 'None'}
            """
        )
        await ctx.respond(embed=embed, ephemeral=True)

    @ticket.command(name="message", description="Sends the current ticket panel")
    @commands.has_permissions(administrator=True)
    async def send_panel(self, ctx):
        settings = self.db.get_settings(ctx.guild.id)
        if not settings or not settings[3]:
            return await ctx.respond("❌ Configure it first with `/ticket setup`!", ephemeral=True)

        channel = ctx.guild.get_channel(settings[3])
        if not channel:
            return await ctx.respond("❌ Configure it first with `/ticket setup`!", ephemeral=True)

        embed, message_id = self.db.load_panel(ctx.guild.id)
        if not embed:
            embed = discord.Embed(
                title="🎫 Ticket System",
                description="Click below to create a ticket",
                color=discord.Color.blue()
            )

        view = TicketCreateView(self.bot, self.db)
        msg = await channel.send(embed=embed, view=view)
        self.db.save_panel(ctx.guild.id, embed, msg.id)
        self.bot.add_view(view, message_id=msg.id)

        return await ctx.respond(f"✅ Panel was sent to {channel.mention}!", ephemeral=True)

    @ticket.command(name="embed", description="Edits the ticket panel embed")
    @commands.has_permissions(administrator=True)
    async def edit_embed(self, ctx):

        embed_data = self.db.load_panel(ctx.guild.id)

        embed = embed_data[0] if embed_data and embed_data[0] else None

        if embed is None:
            embed = discord.Embed(
                title="🎫 Ticket System",
                description="Click below to create a ticket",
                color=discord.Color.blue()
            )

        view = EmbedBuilderView(self.db, ctx.guild.id)
        await ctx.respond("✍️ Edit the ticket panel:", embed=embed, view=view, ephemeral=True)

    @category.command(name="add", description="Adds a ticket category")
    @commands.has_permissions(administrator=True)
    async def add_category(
        self,
        ctx,
        name: Option(str, "Name of the category"),
        description: Option(str, "Description of the category")
    ):
        categories = self.db.get_categories(ctx.guild.id)

        if len(categories) >= 7:
            await ctx.respond("❌ A maximum of **7 categories** may exist.", ephemeral=True)
            return

        if any(k[1].lower() == name.lower() for k in categories):
            await ctx.respond(f"⚠️ Category **{name}** already exists.", ephemeral=True)
            return

        self.db.add_category(ctx.guild.id, name, description)
        await ctx.respond(f"✅ Category **{name}** was added.", ephemeral=True)


    @category.command(name="remove", description="Removes a ticket category")
    @option("name", description="Name of the category", autocomplete=autocomplete_category_list)
    @commands.has_permissions(administrator=True)
    async def remove_category(self, ctx, name: str):
        categories = [k[1] for k in self.db.get_categories(ctx.guild.id)]
        if name not in categories:
            await ctx.respond(f"❌ Category **{name}** does not exist.", ephemeral=True)
            return

        self.db.remove_category(ctx.guild.id, name)
        await ctx.respond(f"🗑️ Category **{name}** was removed.", ephemeral=True)



    @category.command(name="list", description="Shows all ticket categories")
    @commands.has_permissions(administrator=True)
    async def list_categories(self, ctx):
        categories = self.db.get_categories(ctx.guild.id)
        if not categories:
            await ctx.respond("⚠️ No categories available.", ephemeral=True)
            return

        msg = "\n".join([f"• **{name}** – {description}" for _, name, description in categories])
        await ctx.respond(f"📋 **Ticket Categories:**\n{msg}", ephemeral=True)




def setup(bot):
    bot.add_cog(TicketSystem(bot))


class TicketCreateButton(discord.ui.Button):
    def __init__(self, bot, db):
        super().__init__(
            style=discord.ButtonStyle.primary,
            label="Create Ticket",
            custom_id="persistent:ticket_create",
            emoji="🎫"
        )
        self.bot = bot
        self.db = db

    async def callback(self, interaction: discord.Interaction):
        settings = self.db.get_settings(interaction.guild.id)
        if not settings:
            return await interaction.response.send_message(
                "❌ Ticket system has not been set up yet!",
                ephemeral=True
            )

        ticket_channel = interaction.guild.get_channel(settings[3])
        if not ticket_channel:
            return await interaction.response.send_message(
                "❌ Ticket channel not found!",
                ephemeral=True
            )

        categories = self.db.get_categories(interaction.guild.id)
        if not categories:
            return await interaction.response.send_message(
                "❌ No categories available!",
                ephemeral=True
            )

        thread = await ticket_channel.create_thread(
            name=f"Ticket-{interaction.user.display_name}",
            type=discord.ChannelType.private_thread
        )

        await thread.add_user(interaction.user)
        support_role = interaction.guild.get_role(settings[1])
        if support_role:
            for member in support_role.members:
                try:
                    await thread.add_user(member)
                except:
                    continue

        ticket_id = self.db.create_ticket(
            interaction.guild.id,
            thread.id,
            interaction.user.id,
            "General"
        )

        embed = discord.Embed(
            title=f"Ticket #{ticket_id}",
            description=f"Hello {interaction.user.mention},\n\n"
                        "Please describe your issue.\n"
                        "The support team will get back to you soon.",
            color=discord.Color.blue()
        )

        view = EmbedBuilderView(self.db, interaction.guild.id)
        await thread.send(
            content=f"{interaction.user.mention} {support_role.mention if support_role else ''}",
            embed=embed,
            view=view
        )

        return await interaction.response.send_message(
            f"✅ Ticket was created: {thread.mention}",
            ephemeral=True
        )


class CreateEmbedBuilderButton(discord.ui.Button):
    def __init__(self, db, guild_id):
        super().__init__(label="Create Embed", style=discord.ButtonStyle.green, emoji="🖋️")
        self.db = db
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Default Title", description="Default Description", color=discord.Color.blue())
        builder_view = EmbedBuilderView(self.db, self.guild_id, embed)
        await interaction.response.send_message("✍️ Edit your embed below:", embed=embed, view=builder_view, ephemeral=True)


class SaveEmbedButton(discord.ui.Button):
    def __init__(self, db, guild_id):
        super().__init__(style=discord.ButtonStyle.green, label="Save")
        self.db = db
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        embed = interaction.message.embeds[0]
        self.db.save_panel(self.guild_id, embed)

        await interaction.response.edit_message(
            content="✅ Embed was saved!",
            embed=embed,
            view=None
        )




class EmbedBuilderView(discord.ui.View):
    def __init__(self, db, guild_id: int, has_saved_embed: bool = False):
        super().__init__(timeout=600)
        self.db = db
        self.guild_id = guild_id
        self.add_item(Dropdown())
        self.add_item(SaveEmbedButton(db, guild_id))
        self.add_item(ResetEmbedButton())


    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.guild_permissions.administrator

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item):
        await interaction.response.send_message(
            "❌ An error occurred. Please try again.",
            ephemeral=True
        )
        print(f"Error in {item}: {error}")

class SendEmbedButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.green,
            label="Send",
            custom_id="send_embed_button",
            emoji="📨"
        )

    async def callback(self, interaction: discord.Interaction):
        settings = self.view.db.get_settings(interaction.guild.id)
        if not settings:
            return await interaction.response.send_message(
                "❌ Ticket system not set up!",
                ephemeral=True
            )

        support_role = interaction.guild.get_role(settings[1])
        if not (interaction.user.guild_permissions.administrator or
                (support_role and support_role in interaction.user.roles)):
            return await interaction.response.send_message(
                "❌ Only support members can send embeds!",
                ephemeral=True
            )

        embed = interaction.message.embeds[0]
        await interaction.channel.send(embed=embed)

        return await interaction.response.send_message(
            "✅ Embed was sent!",
            ephemeral=True
        )




class Send(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Send",
            style=discord.enums.ButtonStyle.green,
            custom_id="interaction:send",
            emoji="✉️"
        )

    async def callback(self, interaction: discord.Interaction):
        message = interaction.message
        channel = interaction.channel
        if len(message.embeds) == 0 and not message.content:
            return await interaction.response.send_message("What exactly do you want to send?", ephemeral=True)
        if len(message.embeds) == 0:
            await channel.send(content=message.content)
        else:
            embed = message.embeds[0]
            final = embed.copy()

            if message.content:
                await channel.send(embed=embed,content=message.content)
            else:
                await channel.send(embed=embed)
        return await interaction.response.send_message("Sent", ephemeral=True)


async def check_embed(embed, checker):
    list = embed.to_dict()
    list_fields = len(list['fields'])
    if checker == "":
        if list_fields <= 0:
            if len(list) < 4:
                return False
    return True

class ResetEmbedButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.danger,
            label="Reset",
            emoji="🗑️"
        )

    async def callback(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎫 Ticket System",
            description="Click below to create a ticket",
            color=discord.Color.blue()
        )
        view = EmbedBuilderView(self.view.db, self.view.guild_id)
        await interaction.response.edit_message(embed=embed, view=view)


class content(discord.ui.Modal):
    def __init__(self, label, placeholder, value, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.label = label
        self.placeholder = placeholder
        self.value = value

        self.add_item(discord.ui.InputText(
            required=False,
            max_length=1999,
            label=label,
            placeholder=placeholder,
            value=value,
            style=discord.InputTextStyle.long
        ))

    async def callback(self, interaction: discord.Interaction):
        message = interaction.message
        await interaction.response.edit_message(content=self.children[0].value)

class author(discord.ui.Modal):
    def __init__(self, label, placeholder, value, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.label = label
        self.placeholder = placeholder
        self.value = value

        self.add_item(discord.ui.InputText(
            required=False,
            max_length=200,
            label=label,
            placeholder=placeholder,
            value=value,
            style=discord.InputTextStyle.short
        ))
        self.add_item(discord.ui.InputText(
            required=True,
            max_length=200,
            label="Author Icon",
            placeholder="Author Icon Here...",
            value=value,
            style=discord.InputTextStyle.short
        ))
        self.add_item(discord.ui.InputText(
            required=True,
            max_length=200,
            label="Author URL",
            placeholder="Author URL Here...",
            value=value,
            style=discord.InputTextStyle.short
        ))

    async def callback(self, interaction: discord.Interaction):
        message = interaction.message
        embed = message.embeds[0]
        check = await check_embed(embed, self.children[0].value)
        if check is False:
            return await interaction.response.send_message("At least one field must be present")

        # embed.set_author(name=self.children[0].value,url=self.children[2].value,icon_url=self.children[1].value)

        embeds = []
        if not len(message.embeds) == 2 or len(message.embeds[1].fields) == 0:
            embeds.append(embed)
            embed2 = discord.Embed(description=f"Settings", color=discord.Color.yellow())
            if self.children[0].value == "":
                embed2.add_field(name="Author", value="default author")
            else:
                embed2.add_field(name="Author", value=self.children[0].value)

            link_aiu = self.children[1].value
            if link_aiu.find('http://') == 0 or link_aiu.find('https://') == 0:
                embed2.add_field(name="Author Icon URL", value=self.children[1].value)

            else:
                embed2.add_field(name="Author Icon URL", value="https://www.pleaseenteravaildurladress.com/")

            link_au = self.children[2].value
            if link_au.find('http://') == 0 or link_au.find('https://') == 0:
                embed2.add_field(name="Author URL", value=self.children[2].value)
            else:
                embed2.add_field(name="Author URL", value="https://www.pleaseenteravaildurladress.com/")
            embeds.append(embed2)
        else:
            embeds.append(embed)
            embed2 = message.embeds[1]
            current_fields = embed2.fields.copy()
            field_list = []
            for field in current_fields:
                field_list.append(field.name)
                if field.name == "Author":
                    embed2.remove_field(embed2.fields.index(field))
                    if not self.children[0].value == "":
                        embed2.add_field(name="Author", value=self.children[0].value)
                elif field.name == "Author Icon URL":
                    embed2.remove_field(embed2.fields.index(field))
                    if not self.children[0].value == "":
                        link_aiu2 = self.children[1].value
                        if link_aiu2.find('http://') == 0 or link_aiu2.find('https://') == 0:
                            embed2.add_field(name="Author Icon URL", value=self.children[1].value)
                        else:
                            embed2.add_field(name="Author Icon URL",
                                             value="https://www.pleaseenteravaildurladress.com/")
                elif field.name == "Author URL":
                    embed2.remove_field(embed2.fields.index(field))
                    if not self.children[0].value == "":
                        link_au2 = self.children[2].value
                        if link_au2.find('http://') == 0 or link_au2.find('https://') == 0:
                            embed2.add_field(name="Author URL", value=self.children[2].value)
                        else:
                            embed2.add_field(name="Author URL", value="https://www.pleaseenteravaildurladress.com/")

            if not "Author" in field_list or not "Author URL" in field_list or not "Author Icon URL" in field_list:
                if self.children[0].value == "":
                    embed2.add_field(name="Author", value="default author")
                else:
                    embed2.add_field(name="Author", value=self.children[0].value)

                link_aiut = self.children[1].value
                if link_aiut.find('http://') == 0 or link_aiut.find('https://') == 0:
                    embed2.add_field(name="Author Icon URL", value=self.children[1].value)
                else:
                    embed2.add_field(name="Author Icon URL", value="https://www.pleaseenteravaildurladress.com/")

                link_aut = self.children[2].value
                if link_aut.find('http://') == 0 or link_aut.find('https://') == 0:
                    embed2.add_field(name="Author URL", value=self.children[2].value)
                else:
                    embed2.add_field(name="Author URL", value="https://www.pleaseenteravaildurladress.com/")

            embeds.append(embed2)

        return await interaction.response.edit_message(embeds=embeds)


class title(discord.ui.Modal):
    def __init__(self, label, placeholder, value, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.label = label
        self.placeholder = placeholder
        self.value = value

        self.add_item(discord.ui.InputText(
            required=False,
            max_length=50,
            label=label,
            placeholder=placeholder,
            value=value,
            style=discord.InputTextStyle.short
        ))

    async def callback(self, interaction: discord.Interaction):
        message = interaction.message

        embed = message.embeds[0]
        check = await check_embed(embed, self.children[0].value)
        if check is False:
            return await interaction.response.send_message("At least one field must be present")
        try:

            embed.title = self.children[0].value
        except:
            pass

        embeds = []
        if len(message.embeds) == 2:
            embeds.append(embed)
            embeds.append(message.embeds[1])
        else:
            embeds.append(embed)

        return await interaction.response.edit_message(embeds=embeds)


class description(discord.ui.Modal):
    def __init__(self, label, placeholder, value, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.label = label
        self.placeholder = placeholder
        self.value = value

        self.add_item(discord.ui.InputText(
            required=False,
            max_length=500,
            label=label,
            placeholder=placeholder,
            value=value,
            style=discord.InputTextStyle.long
        ))

    async def callback(self, interaction: discord.Interaction):
        # variables = ["UserID","UserTag","Username","UserAvatarURL","UserBannerURL","UserCreateAT","UserJoined","Members","GuildID","Guildname","GuildIcon","GuildBannert"]
        # variable_set = set(variables)
        text = self.children[0].value
        # for variable in re.findall(r'{(.*?)}', text):
        #     if variable not in variable_set:
        #         text = text.replace("{" + variable + "}", "#####")
        message = interaction.message
        embed = message.embeds[0]
        check = await check_embed(embed, text)
        if check is False:
            return await interaction.response.send_message("At least one field must be present")
        try:
            embed.description = text
        except:
            pass

        embeds = []
        if len(message.embeds) == 2:
            embeds.append(embed)
            embeds.append(message.embeds[1])
        else:
            embeds.append(embed)

        return await interaction.response.edit_message(embeds=embeds)



class footer(discord.ui.Modal):
    def __init__(self, label, placeholder, value, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.label = label
        self.placeholder = placeholder
        self.value = value

        self.add_item(discord.ui.InputText(
            required=False,
            max_length=50,
            label=label,
            placeholder=placeholder,
            value=value,
            style=discord.InputTextStyle.short
        ))

    async def callback(self, interaction: discord.Interaction):
        message = interaction.message
        embed = message.embeds[0]
        check = await check_embed(embed, self.children[0].value)
        if check is False:
            return await interaction.response.send_message("At least one field must be present")
        try:
            embed.set_footer(text=self.children[0].value)
        except:
            pass

        embeds = []
        if len(message.embeds) == 2:
            embeds.append(embed)
            embeds.append(message.embeds[1])
        else:
            embeds.append(embed)

        return interaction.response.edit_message(embeds=embeds)


class color(discord.ui.Modal):
    def __init__(self, label, placeholder, value, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.label = label
        self.placeholder = placeholder
        self.value = value

        self.add_item(discord.ui.InputText(
            required=False,
            max_length=6,
            min_length=6,
            label=label,
            placeholder=placeholder,
            value=value,
            style=discord.InputTextStyle.short
        ))

    async def callback(self, interaction: discord.Interaction):
        message = interaction.message
        embed = message.embeds[0]
        check = await check_embed(embed, self.children[0].value)
        if check is False:
            return await interaction.response.send_message("At least one field must be present")
        try:
            color = f"0x{self.children[0].value}"
            embed.colour = discord.Colour(int(color, 16))
        except:
            pass

        embeds = []
        if len(message.embeds) == 2:
            embeds.append(embed)
            embeds.append(message.embeds[1])
        else:
            embeds.append(embed)

        return await interaction.response.edit_message(embeds=embeds)


class field_add(discord.ui.Modal):
    def __init__(self, dropdown, label, placeholder, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dropdown = dropdown
        self.label = label
        self.placeholder = placeholder

        self.add_item(discord.ui.InputText(
            required=True,
            max_length=2000,
            label=label,
            placeholder=placeholder,
            style=discord.InputTextStyle.short
        ))

        self.add_item(discord.ui.InputText(
            required=True,
            max_length=2000,
            label="Field Value",
            placeholder="Field Value Here...",
            style=discord.InputTextStyle.long
        ))

        self.add_item(discord.ui.InputText(
            required=True,
            max_length=2000,
            min_length=4,
            label="Field Inline",
            placeholder="Field Inline Here... (true or false)",
            value="false",
            style=discord.InputTextStyle.short
        ))

    async def callback(self, interaction: discord.Interaction):
        message = interaction.message
        embed = message.embeds[0]

        if self.children[2].value == "true" or "false":
            if len(embed.fields) == 24:
                return await interaction.response.send_message(
                    "You cannot add more than 25 fields to your embed", ephemeral=True)
            else:
                embed.add_field(name=self.children[0].value, value=self.children[1].value,
                                inline=self.children[2].value)
        else:
            embed.add_field(name=self.children[0].value, value=self.children[1].value)

        embeds = []
        if len(message.embeds) == 2:
            embeds.append(embed)
            embeds.append(message.embeds[1])
        else:
            embeds.append(embed)

        return await interaction.response.edit_message(embeds=embeds)


class field_remove(discord.ui.Modal):
    def __init__(self, label, placeholder, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.label = label
        self.placeholder = placeholder

        self.add_item(discord.ui.InputText(
            required=True,
            max_length=2,
            label=label,
            placeholder=placeholder,
            style=discord.InputTextStyle.short
        ))

    async def callback(self, interaction: discord.Interaction):
        message = interaction.message
        embed = message.embeds[0]
        if len(embed.fields) == 0:
            return await interaction.response.send_message("You cannot remove fields because there are no fields", ephemeral=True)
        else:
            if len(embed.fields) == 0:
                return await interaction.response.send_message(
                    "You cannot remove more fields because there are none", ephemeral=True)
            if len(embed.fields) > int(self.children[0].value):
                embed.fields.pop(int(self.children[0].value))
            else:
                return await interaction.response.send_message(
                    "Please note that field numbering starts at 0, so 0, 1, 2, ...", ephemeral=True)

        embeds = []
        if len(message.embeds) == 2:
            embeds.append(embed)
            embeds.append(message.embeds[1])
        else:
            embeds.append(embed)

        return await interaction.response.edit_message(embeds=embeds)


options = [
            discord.SelectOption(label="Content",  emoji="✍️", value="content"),
            discord.SelectOption(label="Author",  emoji="🗣️", value="author"),
            discord.SelectOption(label="Title",  emoji="📣", value="title"),
            discord.SelectOption(label="Description",  emoji="📜",
                                 value="description"),
            discord.SelectOption(label="Footer", emoji="📓", value="footer"),
            discord.SelectOption(label="Color", emoji="🎨", value="color"),
            discord.SelectOption(label="Timestamp",  emoji="⏰", value="timestamp"),
            discord.SelectOption(label="Add Embed",  emoji="➕", value="field_add"),
            discord.SelectOption(label="Remove Embed",  emoji="➖",
                                 value="field_remove"),
        ]

class Dropdown(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Select field",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="interaction:Dropdown",
        )

    async def callback(self, interaction: discord.Interaction):
        not_embed = "You need to add an embed to use this function!"
        if "content" in interaction.data['values']:
            message = interaction.message
            modal = content(label="Content", placeholder="Content here...", value=message.content,
                            title="New Embed: Content")
            return await interaction.response.send_modal(modal)
        elif "author" in interaction.data['values']:
            message = interaction.message
            if not message.embeds:
                return await interaction.response.send_message(not_embed, ephemeral=True)
            embed = message.embeds[0]
            if embed.author is None:
                modal = author(label="Author", placeholder="Author here...", value="", title="New Embed: Author")
            else:
                modal = author(label="Author", placeholder="Author here...", value=embed.author.name,
                               title="New Embed: Author")
            return await interaction.response.send_modal(modal)

        elif "title" in interaction.data['values']:
            message = interaction.message
            if not message.embeds:
                return await interaction.response.send_message(not_embed, ephemeral=True)
            embed = message.embeds[0]

            if embed.title is None:
                modal = title(label="Title", placeholder="Title here...", value="", title="New Embed: Title")
            else:
                modal = title(label="Title", placeholder="Title here...", value=embed.title, title="New Embed: Title")
            await interaction.response.send_modal(modal)

        elif "description" in interaction.data['values']:
            message = interaction.message
            if not message.embeds:
                return await interaction.response.send_message(not_embed, ephemeral=True)
            embed = message.embeds[0]

            if embed.description is None:
                modal = description(label="Description", placeholder="Description here...", value="",
                                    title="New Embed: Description")
            else:
                modal = description(label="Description", placeholder="Description here...", value=embed.description,
                                    title="New Embed: Description")
            return await interaction.response.send_modal(modal)

        elif "footer" in interaction.data['values']:
            message = interaction.message
            if not message.embeds:
                return await interaction.response.send_message(not_embed, ephemeral=True)
            embed = message.embeds[0]
            if embed.footer is None:
                modal = footer(label="Footer", placeholder="Footer here...", value="", title="New Embed: Footer")
            else:
                modal = footer(label="Footer", placeholder="Footer here...", value=embed.footer.text,
                               title="New Embed: Footer")
            return await interaction.response.send_modal(modal)

        elif "color" in interaction.data['values']:
            message = interaction.message
            if not message.embeds:
                return await interaction.response.send_message(not_embed, ephemeral=True)
            embed = message.embeds[0]
            if embed.colour is None:
                modal = color(label="Color", placeholder="Color (HEX) here...", value="", title="New Embed: Color")
            else:
                rgb = embed.colour.to_rgb()
                hex_code = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
                modal = color(label="Color", placeholder="Color (HEX) here...", value=hex_code[1:],
                              title="New Embed: Color")
            return await interaction.response.send_modal(modal)

        elif "timestamp" in interaction.data['values']:
            message = interaction.message
            if not message.embeds:
                return await interaction.response.send_message(not_embed, ephemeral=True)
            embed = message.embeds[0]

            if embed.timestamp:
                embed.timestamp = None
            else:
                embed.timestamp = datetime.now()

            embeds = []
            if len(message.embeds) == 2:
                embeds.append(embed)
                embeds.append(message.embeds[1])
            else:
                embeds.append(embed)

            return await interaction.response.edit_message(embeds=embeds)

        elif "field_add" in interaction.data['values']:
            message = interaction.message
            if not message.embeds:
                return await interaction.response.send_message(not_embed, ephemeral=True)
            embed = message.embeds[0]
            modal = field_add(self, label="Field Name", placeholder="Field name here...", title="New Embed: Add Field")
            return await interaction.response.send_modal(modal)

        elif "field_remove" in interaction.data['values']:
            message = interaction.message
            if not message.embeds:
                return await interaction.response.send_message(not_embed, ephemeral=True)
            embed = message.embeds[0]
            if len(embed.fields) == 1:
                embed.fields.pop(0)
                embeds = []
                if len(message.embeds) == 2:
                    embeds.append(embed)
                    embeds.append(message.embeds[1])
                else:
                    embeds.append(embed)

                return await interaction.response.edit_message(embeds=embeds)
            modal = field_remove(label="Field number (count starts at 0)", placeholder="Field number here...",
                                 title="New Embed: Remove Field")
            return await interaction.response.send_modal(modal)
        elif not interaction.response.is_done():
            view = discord.ui.View()
            view.add_item(Dropdown())
            message = interaction.message

            if message:
                await interaction.response.edit_message(view=view)
            else:
                await interaction.response.send_message(view=view)


class SettingsSelectionView(discord.ui.View):
    def __init__(self, db, guild_id, user, bot):
        super().__init__(timeout=60)
        self.db = db
        self.guild_id = guild_id
        self.user = user
        self.bot = bot
        self.add_item(SettingsDropdown(db, guild_id, user, bot))
        self.add_item(DoneButton(user))
        self.add_item(CancelButton(user))

    async def on_timeout(self):
        try:
            for item in self.children:
                item.disabled = True
            await self.message.edit(content="⏰ Time expired.", view=self)
        except:
            pass

class SettingsDropdown(discord.ui.Select):
    def __init__(self, db, guild_id, user, bot):
        self.db = db
        self.guild_id = guild_id
        self.user = user
        self.bot = bot

        options = [
            discord.SelectOption(label="Support Role", value="support", emoji="🛠️"),
            discord.SelectOption(label="Transcript Channel", value="transcript", emoji="📄"),
            discord.SelectOption(label="Ticket Channel", value="ticket", emoji="🎫"),
            discord.SelectOption(label="Log Channel", value="log", emoji="📋")
        ]
        super().__init__(
            placeholder="Choose a setting...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.user:
            return await interaction.response.send_message("Not your menu.", ephemeral=True)

        value = self.values[0]
        if value == "support":
            button = SupportRoleButton(self.db, self.guild_id)
        elif value == "transcript":
            button = TranscriptChannelButton(self.db, self.guild_id)
        elif value == "ticket":
            button = TicketChannelButton(self.db, self.guild_id)
        elif value == "log":
            button = LogChannelButton(self.db, self.guild_id)
        else:
            return await interaction.response.send_message("Invalid selection.", ephemeral=True)

        return await button.callback(interaction)

class DoneButton(discord.ui.Button):
    def __init__(self, user):
        super().__init__(label="Done", style=discord.ButtonStyle.green, row=1)
        self.user = user

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.user:
            return await interaction.response.send_message("Only the original user can complete this.", ephemeral=True)

        return await interaction.response.edit_message(content="✅ Settings completed.", view=None)


class SupportRoleButton(discord.ui.Button):
    def __init__(self, db, guild_id):
        super().__init__(
            style=discord.ButtonStyle.primary,
            label="Support Role",
            custom_id=f"settings_support_{guild_id}",
            row=0
        )
        self.db = db
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        class RoleSelect(discord.ui.Select):
            def __init__(self, db, guild_id, user, roles):
                self.db = db
                self.guild_id = guild_id
                self.user = user
                options = [
                    discord.SelectOption(label=role.name, value=str(role.id))
                    for role in roles if not role.is_default()
                ][:25]
                super().__init__(
                    placeholder="Choose a support role",
                    options=options,
                    min_values=1,
                    max_values=1
                )

            async def callback(self, select_interaction: discord.Interaction):
                if select_interaction.user != self.user:
                    return await select_interaction.response.send_message(
                        "Only the original user can make this selection.",
                        ephemeral=True
                    )

                role_id = int(self.values[0])
                current = self.db.get_settings(self.guild_id)
                self.db.update_settings(
                    self.guild_id,
                    role_id,
                    current[2],
                    current[3],
                    current[4]
                )

                return await select_interaction.response.edit_message(
                    content=f"✅ Support role was set to <@&{role_id}>.",
                    view=None
                )

        view = discord.ui.View(timeout=60)
        view.add_item(RoleSelect(self.db, self.guild_id, interaction.user, interaction.guild.roles))
        await interaction.followup.send("Choose a support role:", view=view, ephemeral=True)


class TranscriptChannelButton(discord.ui.Button):
    def __init__(self, db, guild_id):
        super().__init__(
            style=discord.ButtonStyle.primary,
            label="Transcript Channel",
            custom_id=f"settings_transcript_{guild_id}",
            row=0
        )
        self.db = db
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        class TranscriptSelect(discord.ui.Select):
            def __init__(self, db, guild_id, user, channels):
                self.db = db
                self.guild_id = guild_id
                self.user = user
                options = [
                    discord.SelectOption(label=channel.name, value=str(channel.id))
                    for channel in channels
                ][:25]
                super().__init__(
                    placeholder="Choose a transcript channel",
                    options=options,
                    min_values=1,
                    max_values=1
                )

            async def callback(self, select_interaction: discord.Interaction):
                if select_interaction.user != self.user:
                    return await select_interaction.response.send_message(
                        "Only the original user can make this selection.",
                        ephemeral=True
                    )

                channel_id = int(self.values[0])
                current = self.db.get_settings(self.guild_id)
                self.db.update_settings(
                    self.guild_id,
                    current[1],
                    channel_id,
                    current[3],
                    current[4]
                )

                return await select_interaction.response.edit_message(
                    content=f"✅ Transcript channel was set to <#{channel_id}>.",
                    view=None
                )

        view = discord.ui.View(timeout=60)
        view.add_item(TranscriptSelect(self.db, self.guild_id, interaction.user, interaction.guild.text_channels))
        await interaction.followup.send("Choose a transcript channel:", view=view, ephemeral=True)



class TicketChannelButton(discord.ui.Button):
    def __init__(self, db, guild_id):
        super().__init__(
            style=discord.ButtonStyle.primary,
            label="Ticket Channel",
            custom_id=f"settings_ticket_{guild_id}",
            row=1
        )
        self.db = db
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        class TicketSelect(discord.ui.Select):
            def __init__(self, db, guild_id, user, channels):
                self.db = db
                self.guild_id = guild_id
                self.user = user
                options = [
                    discord.SelectOption(label=channel.name, value=str(channel.id))
                    for channel in channels
                ][:25]
                super().__init__(
                    placeholder="Choose a ticket channel",
                    options=options,
                    min_values=1,
                    max_values=1
                )

            async def callback(self, select_interaction: discord.Interaction):
                if select_interaction.user != self.user:
                    return await select_interaction.response.send_message(
                        "Only the original user can make this selection.",
                        ephemeral=True
                    )

                channel_id = int(self.values[0])
                current = self.db.get_settings(self.guild_id)
                self.db.update_settings(
                    self.guild_id,
                    current[1],
                    current[2],
                    channel_id,
                    current[4]
                )

                return await select_interaction.response.edit_message(
                    content=f"✅ Ticket channel was set to <#{channel_id}>.",
                    view=None
                )

        view = discord.ui.View(timeout=60)
        view.add_item(TicketSelect(self.db, self.guild_id, interaction.user, interaction.guild.text_channels))
        await interaction.followup.send("Choose a ticket channel:", view=view, ephemeral=True)



class LogChannelButton(discord.ui.Button):
    def __init__(self, db, guild_id):
        super().__init__(
            style=discord.ButtonStyle.primary,
            label="Log Channel",
            custom_id=f"settings_log_{guild_id}",
            row=1
        )
        self.db = db
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        class ChannelSelect(discord.ui.Select):
            def __init__(self, db, guild_id, user, channels):
                self.db = db
                self.guild_id = guild_id
                self.user = user

                options = [
                    discord.SelectOption(label=channel.name, value=str(channel.id))
                    for channel in channels
                ][:25]

                super().__init__(
                    placeholder="Choose a log channel",
                    options=options,
                    min_values=1,
                    max_values=1
                )

            async def callback(self, select_interaction: discord.Interaction):
                if select_interaction.user != self.user:
                    return await select_interaction.response.send_message(
                        "Only the original user can make this selection.",
                        ephemeral=True
                    )

                channel_id = int(self.values[0])
                current = self.db.get_settings(self.guild_id)
                self.db.update_settings(
                    self.guild_id,
                    current[1],  # support role
                    current[2],  # transcript channel
                    current[3],  # ticket channel
                    channel_id
                )

                return await select_interaction.response.edit_message(
                    content=f"✅ Log channel was set to <#{channel_id}>.",
                    view=None
                )

        view = discord.ui.View(timeout=60)
        view.add_item(ChannelSelect(self.db, self.guild_id, interaction.user, interaction.guild.text_channels))
        await interaction.followup.send("Choose a log channel:", view=view, ephemeral=True)



class CancelButton(discord.ui.Button):
    def __init__(self, user):
        super().__init__(label="Cancel", style=discord.ButtonStyle.red, row=1)
        self.user = user

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.user:
            return await interaction.response.send_message("Not your process.", ephemeral=True)

        return await interaction.response.edit_message(content="❌ Settings cancelled.", view=None)
