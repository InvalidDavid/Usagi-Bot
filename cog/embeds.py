import json
from typing import Optional
from utils.imports import *
DB_PATH = "Data/embeds.db"

GUILD_IDS = GUILDS


async def check_permissions(ctx: discord.ApplicationContext):
    if GUILD_IDS and ctx.guild_id not in GUILD_IDS:
        await ctx.respond("This command can only be used in the configured server.", ephemeral=True)
        return False

    user_roles = [r.id for r in ctx.author.roles]
    if not any(r in MOD_ROLE_IDS + ADMIN_ROLE_IDS for r in user_roles):
        await ctx.respond("You need Mod or Admin role to use this command.", ephemeral=True)
        return False

    return True

def init_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS saved_embeds (
                guild_id INTEGER,
                name TEXT,
                data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, name)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_guild_id ON saved_embeds(guild_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_name ON saved_embeds(name)')
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        print(f"Database error: {e}")


init_db()


class DatabaseHelper:
    @staticmethod
    def get_templates(guild_id: int) -> list:
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM saved_embeds WHERE guild_id = ? ORDER BY name", (guild_id,))
            rows = cursor.fetchall()
            conn.close()
            return [row[0] for row in rows]
        except sqlite3.Error:
            return []

    @staticmethod
    def get_template(guild_id: int, name: str) -> Optional[dict]:
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT data FROM saved_embeds WHERE guild_id = ? AND name = ?", (guild_id, name))
            res = cursor.fetchone()
            conn.close()
            return json.loads(res[0]) if res else None
        except (sqlite3.Error, json.JSONDecodeError):
            return None

    @staticmethod
    def save_template(guild_id: int, name: str, data: dict) -> bool:
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO saved_embeds (guild_id, name, data, updated_at) VALUES (?,?,?, CURRENT_TIMESTAMP)",
                (guild_id, name, json.dumps(data))
            )
            conn.commit()
            conn.close()
            return True
        except sqlite3.Error:
            return False

    @staticmethod
    def delete_template(guild_id: int, name: str) -> bool:
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM saved_embeds WHERE guild_id = ? AND name = ?", (guild_id, name))
            conn.commit()
            conn.close()
            return True
        except sqlite3.Error:
            return False


class EmbedTitleModal(discord.ui.Modal):
    def __init__(self, view):
        super().__init__(title="Edit Title")
        self.view = view
        self.add_item(discord.ui.InputText(label="Title", value=view.embed.title or "", required=False, max_length=256))

    async def callback(self, interaction: discord.Interaction):
        self.view.embed.title = self.children[0].value or None
        await self.view.update_message(interaction)


class EmbedDescriptionModal(discord.ui.Modal):
    def __init__(self, view):
        super().__init__(title="Edit Description")
        self.view = view
        self.add_item(discord.ui.InputText(
            label="Description",
            value=view.embed.description or "",
            style=discord.InputTextStyle.paragraph,
            required=False,
            max_length=4000
        ))

    async def callback(self, interaction: discord.Interaction):
        self.view.embed.description = self.children[0].value or None
        await self.view.update_message(interaction)


class EmbedAuthorModal(discord.ui.Modal):
    def __init__(self, view):
        super().__init__(title="Edit Author")
        self.view = view
        author = view.embed.author
        self.add_item(discord.ui.InputText(label="Name", value=author.name if author else "", required=False))

    async def callback(self, interaction: discord.Interaction):
        name = self.children[0].value
        self.view.embed.set_author(name=name)
        await self.view.update_message(interaction)


class EmbedColorModal(discord.ui.Modal):
    def __init__(self, view):
        super().__init__(title="Edit Color")
        self.view = view
        self.add_item(discord.ui.InputText(label="Hex Color (e.g., 7289da)", required=False, max_length=6))

    async def callback(self, interaction: discord.Interaction):
        hex_color = self.children[0].value
        if hex_color:
            try:
                self.view.embed.color = int(hex_color, 16)
                await self.view.update_message(interaction)
            except ValueError:
                await interaction.response.send_message("❌ Invalid hex code!", ephemeral=True)


class EmbedFooterModal(discord.ui.Modal):
    def __init__(self, view):
        super().__init__(title="Edit Footer")
        self.view = view
        self.add_item(discord.ui.InputText(label="Text", value=view.embed.footer.text if view.embed.footer else "",
                                           required=False))

    async def callback(self, interaction: discord.Interaction):
        text = self.children[0].value
        self.view.embed.set_footer(text=text)
        await self.view.update_message(interaction)


class EmbedImageModal(discord.ui.Modal):
    def __init__(self, view):
        super().__init__(title="Edit Images")
        self.view = view
        self.add_item(
            discord.ui.InputText(label="Image URL", value=view.embed.image.url if view.embed.image else "",
                                 required=False))

    async def callback(self, interaction: discord.Interaction):
        self.view.embed.set_image(url=self.children[0].value or None)
        await self.view.update_message(interaction)


class EmbedFieldAddModal(discord.ui.Modal):
    def __init__(self, view):
        super().__init__(title="Add Field")
        self.view = view
        self.add_item(discord.ui.InputText(label="Name", required=True))
        self.add_item(discord.ui.InputText(label="Value", style=discord.InputTextStyle.paragraph, required=True))
        self.add_item(discord.ui.InputText(label="Inline (true/false)", value="true", required=False))

    async def callback(self, interaction: discord.Interaction):
        if len(self.view.embed.fields) >= 25:
            return await interaction.response.send_message("❌ Maximum 25 fields reached!", ephemeral=True)
        inline = self.children[2].value.lower() == "true"
        self.view.embed.add_field(name=self.children[0].value, value=self.children[1].value, inline=inline)
        await self.view.update_message(interaction)


class EmbedFieldRemoveModal(discord.ui.Modal):
    def __init__(self, view):
        super().__init__(title="Remove Field")
        self.view = view
        self.add_item(discord.ui.InputText(label="Field Index (0-based)", required=True))

    async def callback(self, interaction: discord.Interaction):
        try:
            idx = int(self.children[0].value)
            if 0 <= idx < len(self.view.embed.fields):
                self.view.embed.remove_field(idx)
                await self.view.update_message(interaction)
            else:
                await interaction.response.send_message(
                    f"❌ Invalid index! Available: 0-{len(self.view.embed.fields) - 1}", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("❌ Please enter a number!", ephemeral=True)


class ConfirmDeleteView(discord.ui.View):
    def __init__(self, template_name: str, guild_id: int, parent_view, timeout: int = 30):
        super().__init__(timeout=timeout)
        self.template_name = template_name
        self.guild_id = guild_id
        self.parent_view = parent_view
        self.message = None

    @discord.ui.button(label="✅ Confirm Delete", style=discord.ButtonStyle.danger, row=0)
    async def confirm(self, button: discord.ui.Button, interaction: discord.Interaction):

        success = DatabaseHelper.delete_template(self.guild_id, self.template_name)

        view = EmbedMainMenu(self.guild_id, timeout=120)

        if success:
            embed = discord.Embed(
                title="🎨 **Embed Builder**",
                description=f"✅ Template `{self.template_name}` deleted!\n\n"
                            "**Choose an option:**",
                color=discord.Color.green()
            )
        else:
            embed = discord.Embed(
                title="❌ Error",
                description="Failed to delete template!",
                color=discord.Color.red()
            )

        embed.set_footer(text="All changes are automatically saved")

        if interaction.guild.me.avatar:
            embed.set_thumbnail(url=interaction.guild.me.avatar.url)

        await interaction.response.edit_message(
            content=None,
            embed=embed,
            view=view
        )

        self.stop()

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary, row=0)
    async def cancel(self, button: discord.ui.Button, interaction: discord.Interaction):

        templates = DatabaseHelper.get_templates(self.guild_id)

        if templates:
            view = LoadTemplateView(self.guild_id, templates, timeout=60)

            embed = discord.Embed(
                title="📂 Load Template",
                description=f"Found **{len(templates)}** template(s). Select one from the dropdown:",
                color=discord.Color.blue()
            )

            await interaction.response.edit_message(embed=embed, view=view)
        else:
            await interaction.response.edit_message(
                content="❌ No templates found!",
                embed=None,
                view=None
            )

        self.stop()


    async def on_timeout(self):
        try:
            if hasattr(self, 'message') and self.message:
                await self.message.edit(view=None)
        except:
            pass


class ChannelSelectView(discord.ui.View):
    def __init__(self, embed: discord.Embed, timeout: int = 60):
        super().__init__(timeout=timeout)
        self.embed = embed
        self.used = False

    @discord.ui.channel_select(
        placeholder="Select a text channel",
        channel_types=[discord.ChannelType.text],
        min_values=1,
        max_values=1
    )
    async def channel_select(self, select: discord.ui.ChannelSelect, interaction: discord.Interaction):

        channel = select.values[0]

        try:
            await channel.send(embed=self.embed)

            await interaction.response.send_message(
                f"✅ Embed sent to {channel.mention}!",
                ephemeral=True
            )

            new_view = ChannelSelectView(self.embed, timeout=60)

            try:
                msg = await interaction.original_response()
                new_view.message = msg
            except:
                pass

            try:
                await interaction.message.edit(view=new_view)
            except:
                pass

        except discord.Forbidden:
            await interaction.response.send_message(
                f"❌ Missing permissions to send to {channel.mention}!",
                ephemeral=True
            )

        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error: {e}",
                ephemeral=True
            )

    async def on_timeout(self):
        try:
            if hasattr(self, 'message') and self.message:
                await self.message.edit(view=None)
        except:
            pass

class LoadTemplateView(discord.ui.View):
    def __init__(self, guild_id: int, templates: list, timeout: int = 60):
        super().__init__(timeout=timeout)
        self.guild_id = guild_id
        self.templates = templates
        self.current_page = 0
        self.items_per_page = 25
        self.message = None
        self.update_select_menu()

    def update_select_menu(self):
        start = self.current_page * self.items_per_page
        end = start + self.items_per_page
        page_templates = self.templates[start:end]

        options = [discord.SelectOption(label=t[:100], value=t) for t in page_templates]
        if not options:
            options = [discord.SelectOption(label="No templates found", value="none")]

        self.clear_items()

        select = discord.ui.Select(
            placeholder=f"Select template (Page {self.current_page + 1})",
            options=options,
            min_values=1,
            max_values=1,
            row=0
        )
        select.callback = self.select_callback
        self.add_item(select)

        exit_btn = discord.ui.Button(
            label="❌ Exit",
            style=discord.ButtonStyle.secondary,
            row=1
        )

        async def exit_callback(interaction: discord.Interaction):
            view = EmbedMainMenu(self.guild_id, timeout=120)

            embed = discord.Embed(
                title="🎨 Embed Builder",
                description="Returned to main menu.",
                color=discord.Color.blue()
            )

            await interaction.response.edit_message(
                embed=embed,
                view=view
            )

            self.stop()

        exit_btn.callback = exit_callback
        self.add_item(exit_btn)

        if len(self.templates) > self.items_per_page:

            if self.current_page > 0:
                prev_btn = discord.ui.Button(
                    label="◀ Previous",
                    style=discord.ButtonStyle.secondary,
                    row=2
                )
                prev_btn.callback = self.prev_page
                self.add_item(prev_btn)

            if end < len(self.templates):
                next_btn = discord.ui.Button(
                    label="Next ▶",
                    style=discord.ButtonStyle.secondary,
                    row=2
                )
                next_btn.callback = self.next_page
                self.add_item(next_btn)

    async def select_callback(self, interaction: discord.Interaction):
        selected = interaction.data["values"][0]

        if selected == "none":
            return await interaction.response.send_message("No templates available.", ephemeral=True)

        data = DatabaseHelper.get_template(self.guild_id, selected)

        if data:
            view = EmbedEditorView(
                discord.Embed.from_dict(data),
                timeout=300,
                template_name=selected,
                guild_id=self.guild_id
            )

            await interaction.response.edit_message(
                content=f"🔧 **Editing Template: {selected}**",
                embed=view.embed,
                view=view
            )

            if interaction.message:
                view.message = interaction.message
        else:
            await interaction.response.send_message("❌ Failed to load template!", ephemeral=True)

    async def prev_page(self, interaction: discord.Interaction):
        self.current_page -= 1
        self.update_select_menu()
        await interaction.response.edit_message(view=self)

    async def next_page(self, interaction: discord.Interaction):
        self.current_page += 1
        self.update_select_menu()
        await interaction.response.edit_message(view=self)

    async def on_timeout(self):
        try:
            if hasattr(self, 'message') and self.message:
                await self.message.edit(view=None)
        except:
            pass


class EmbedEditorView(discord.ui.View):
    def __init__(self, embed: Optional[discord.Embed] = None, timeout: int = 300, template_name: str = None,
                 guild_id: int = None):
        super().__init__(timeout=timeout)
        self.embed = embed or discord.Embed(
            title="New Embed",
            description="Select an option from the dropdown menu below.",
            color=discord.Color.blue()
        )
        self.message = None
        self.template_name = template_name
        self.guild_id = guild_id
        self.add_item(EmbedDropdown(self))

    async def update_message(self, interaction: discord.Interaction):
        try:
            await interaction.response.edit_message(embed=self.embed, view=self)
        except discord.NotFound:
            if self.message:
                await self.message.edit(embed=self.embed, view=self)

    async def on_timeout(self):
        try:
            if hasattr(self, 'message') and self.message:
                await self.message.edit(view=None)
        except:
            pass

    @discord.ui.button(label="💾 Save", style=discord.ButtonStyle.primary, row=1)
    async def btn_save(self, button: discord.ui.Button, interaction: discord.Interaction):
        modal = discord.ui.Modal(title="Save Template")
        modal.add_item(discord.ui.InputText(label="Template Name", required=True, max_length=100))

        async def cb(it: discord.Interaction):
            name = modal.children[0].value

            success = DatabaseHelper.save_template(it.guild.id, name, self.embed.to_dict())

            view = EmbedMainMenu(it.guild.id, timeout=120)

            if success:
                embed = discord.Embed(
                    title="🎨 **Embed Builder**",
                    description=f"✅ Saved as `{name}`!\n\n"
                                "**Choose an option:**",
                    color=discord.Color.green()
                )
            else:
                embed = discord.Embed(
                    title="❌ Error",
                    description="Failed to save template!",
                    color=discord.Color.red()
                )

            embed.set_footer(text="All changes are automatically saved")

            if it.guild.me.avatar:
                embed.set_thumbnail(url=it.guild.me.avatar.url)

            await it.response.edit_message(
                content=None,
                embed=embed,
                view=view
            )

        modal.callback = cb
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="📤 Send", style=discord.ButtonStyle.success, row=1)
    async def btn_send(self, button: discord.ui.Button, interaction: discord.Interaction):
        view = ChannelSelectView(self.embed, timeout=60)
        await interaction.response.send_message("Select a channel:", view=view, ephemeral=True)

    @discord.ui.button(label="🗑️ Exit", style=discord.ButtonStyle.secondary, row=1)
    async def btn_exit(self, button: discord.ui.Button, interaction: discord.Interaction):
        view = EmbedMainMenu(self.guild_id or interaction.guild.id, timeout=120)

        embed = discord.Embed(
            title="🎨 **Embed Builder**",
            description="Create beautiful custom embeds with this tool!\n\n"
                        "**Features:**\n"
                        "• 📝 Title & Description\n"
                        "• 👤 Author with Icon/URL\n"
                        "• 🎨 Color & Footer\n"
                        "• 🖼️ Images & Thumbnails\n"
                        "• ➕ Up to 25 fields\n"
                        "• 💾 Save/Load templates\n"
                        "• 📤 Send to any channel\n\n"
                        "**Choose an option:**",
            color=discord.Color.blue()
        )

        embed.set_footer(text="All changes are automatically saved")

        if interaction.guild.me.avatar:
            embed.set_thumbnail(url=interaction.guild.me.avatar.url)

        await interaction.response.edit_message(
            content=None,
            embed=embed,
            view=view
        )

        self.stop()

    @discord.ui.button(label="🗑️ Delete Template", style=discord.ButtonStyle.danger, row=1)
    async def btn_delete(self, button: discord.ui.Button, interaction: discord.Interaction):
        if not self.template_name or not self.guild_id:
            return await interaction.response.send_message("❌ This is not a loaded template!", ephemeral=True)

        confirm_view = ConfirmDeleteView(self.template_name, self.guild_id, self, timeout=30)

        embed = discord.Embed(
            title="⚠️ Confirm Deletion",
            description=f"Are you sure you want to delete template `{self.template_name}`?\nThis action cannot be undone!",
            color=discord.Color.orange()
        )

        await interaction.response.edit_message(
            embed=embed,
            view=confirm_view
        )


class EmbedDropdown(discord.ui.Select):
    def __init__(self, view):
        options = [
            discord.SelectOption(label="Title", value="title", emoji="📝"),
            discord.SelectOption(label="Description", value="description", emoji="📄"),
            discord.SelectOption(label="Author", value="author", emoji="👤"),
            discord.SelectOption(label="Color", value="color", emoji="🎨"),
            discord.SelectOption(label="Footer", value="footer", emoji="📌"),
            discord.SelectOption(label="Images", value="images", emoji="🖼️"),
            discord.SelectOption(label="Add Field", value="field_add", emoji="➕"),
            discord.SelectOption(label="Remove Field", value="field_remove", emoji="➖"),
            discord.SelectOption(label="Timestamp", value="timestamp", emoji="⏰"),
        ]
        super().__init__(placeholder="Select what you want to edit...", options=options, min_values=1, max_values=1)
        self.view = view

    async def callback(self, interaction: discord.Interaction):
        value = self.values[0]
        if value == "title":
            await interaction.response.send_modal(EmbedTitleModal(self.view))
        elif value == "description":
            await interaction.response.send_modal(EmbedDescriptionModal(self.view))
        elif value == "author":
            await interaction.response.send_modal(EmbedAuthorModal(self.view))
        elif value == "color":
            await interaction.response.send_modal(EmbedColorModal(self.view))
        elif value == "footer":
            await interaction.response.send_modal(EmbedFooterModal(self.view))
        elif value == "images":
            await interaction.response.send_modal(EmbedImageModal(self.view))
        elif value == "field_add":
            await interaction.response.send_modal(EmbedFieldAddModal(self.view))
        elif value == "field_remove":
            if len(self.view.embed.fields) == 0:
                await interaction.response.send_message("❌ No fields to remove!", ephemeral=True)
            else:
                await interaction.response.send_modal(EmbedFieldRemoveModal(self.view))
        elif value == "timestamp":
            if self.view.embed.timestamp:
                self.view.embed.timestamp = None
            else:
                self.view.embed.timestamp = datetime.utcnow()
            await self.view.update_message(interaction)


class EmbedMainMenu(discord.ui.View):
    def __init__(self, guild_id: int, timeout: int = 120):
        super().__init__(timeout=timeout)
        self.guild_id = guild_id
        self.message = None

    async def on_timeout(self):
        try:
            if hasattr(self, 'message') and self.message:
                await self.message.edit(view=None)
        except:
            pass


    @discord.ui.button(label="🆕 Create New Embed", style=discord.ButtonStyle.green, row=0)
    async def create_new(self, button: discord.ui.Button, interaction: discord.Interaction):
        view = EmbedEditorView(timeout=300)
        if self.message:
            view.message = self.message
        await interaction.response.edit_message(
            content="🔧 **Embed Builder**\nSelect an option from the dropdown menu.",
            embed=view.embed,
            view=view
        )

    @discord.ui.button(label="📂 Load Template", style=discord.ButtonStyle.blurple, row=0)
    async def load_template(self, button: discord.ui.Button, interaction: discord.Interaction):
        templates = DatabaseHelper.get_templates(self.guild_id)
        if not templates:
            return await interaction.response.send_message("❌ No templates found!", ephemeral=True)

        view = LoadTemplateView(self.guild_id, templates, timeout=60)
        embed = discord.Embed(
            title="📂 Load Template",
            description=f"Found **{len(templates)}** template(s). Select one from the dropdown:",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(content=None, embed=embed, view=view)
        if interaction.message:
            view.message = interaction.message


class EmbedCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @slash_command(name="embeds", description="Create and manage custom embeds")
    async def embeds(self, ctx: discord.ApplicationContext):
        if not await check_permissions(ctx):
            return

        view = EmbedMainMenu(ctx.guild.id, timeout=120)
        embed = discord.Embed(
            title="🎨 **Embed Builder**",
            description="Create professional embeds with this tool!\n\n"
                        "**Features:**\n"
                        "• 📝 Title & Description\n"
                        "• 👤 Author with Icon/URL\n"
                        "• 🎨 Color & Footer\n"
                        "• 🖼️ Images & Thumbnails\n"
                        "• ➕ Up to 25 fields\n"
                        "• 💾 Save/Load templates\n"
                        "• 📤 Send to any channel\n\n"
                        "**Choose an option:**",
            color=discord.Color.blue()
        )
        embed.set_footer(text="All changes are automatically saved")
        if ctx.bot.user.avatar:
            embed.set_thumbnail(url=ctx.bot.user.avatar.url)

        response = await ctx.respond(embed=embed, view=view, ephemeral=True)
        view.message = await response.original_response()


def setup(bot):
    bot.add_cog(EmbedCog(bot))
