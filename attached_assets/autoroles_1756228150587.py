import discord
from discord.ext import commands
from discord import app_commands
import pickle
import os

# Load or create databases
if not os.path.exists('databases'):
    os.makedirs('databases')

DATABASE_FILE = 'databases/role_buttons.pkl'


def load_database():
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, 'rb') as f:
            return pickle.load(f)
    return {}


def save_database(data):
    with open(DATABASE_FILE, 'wb') as f:
        pickle.dump(data, f)


class RoleButton(discord.ui.Button):
    def __init__(self, role_id: int, label: str, emoji: str, style: discord.ButtonStyle):
        super().__init__(label=label, emoji=emoji, style=style, custom_id=f"role_button_{role_id}")
        self.role_id = role_id

    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(self.role_id)
        if not role:
            await interaction.response.send_message("Role not found.", ephemeral=True)
            return

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"Removed {role.name} from you.", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"Added {role.name} to you.", ephemeral=True)


class PersistentRoleView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)


class RoleButtonCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._default_permission = discord.Permissions(manage_guild=True)

    async def cog_load(self):
        await self.load_persistent_views()

    async def load_persistent_views(self):
        database = load_database()
        for guild_id, guild_data in database.items():
            for message_id, message_data in guild_data.items():
                view = PersistentRoleView()
                for role_id, role_data in message_data['roles'].items():
                    # Try to get the role name from the guild
                    guild = self.bot.get_guild(int(guild_id))
                    role_name = f"Role {role_id}"  # Default fallback

                    if guild:
                        role = guild.get_role(int(role_id))
                        if role:
                            role_name = role.name

                    button = RoleButton(
                        int(role_id),
                        role_name,  # Use actual role name when available
                        role_data['emoji'],
                        self.get_button_color(role_data['color'])
                    )
                    view.add_item(button)

                self.bot.add_view(view, message_id=int(message_id))
                print(f"Loaded persistent view for message {message_id} in guild {guild_id}")

    @app_commands.command(name="reactrole", description="Send an embed with role buttons")
    @app_commands.describe(
        channel="Channel to send the role embed",
        emoji="Emoji for the button",
        role="Role to assign",
        color="Button color: red, green, blue",
        title="Title for the embed (optional)",
        description="Description for the embed (optional)"
    )
    async def reactrole(
            self,
            interaction: discord.Interaction,
            channel: discord.TextChannel,
            emoji: str,
            role: discord.Role,
            color: str,
            title: str = "Role Assignment",
            description: str = "Click a button to toggle roles"
    ):
        # Check permissions
        if not interaction.channel.permissions_for(interaction.guild.me).manage_roles:
            await interaction.response.send_message(
                "I don't have permission to manage roles in this server.",
                ephemeral=True
            )
            return

        if color not in ['red', 'green', 'blue']:
            await interaction.response.send_message(
                "Color must be 'red', 'green', or 'blue'.",
                ephemeral=True
            )
            return

        # Check if role is manageable
        if role.position >= interaction.guild.me.top_role.position:
            await interaction.response.send_message(
                f"I can't assign the {role.name} role because it's higher than or equal to my highest role.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color.blurple()
        )

        view = PersistentRoleView()
        button = RoleButton(role.id, role.name, emoji, self.get_button_color(color))
        view.add_item(button)

        message = await channel.send(embed=embed, view=view)

        # Store message, role, and guild info in the database
        database = load_database()
        guild_id = str(interaction.guild_id)

        if guild_id not in database:
            database[guild_id] = {}

        database[guild_id][str(message.id)] = {
            "roles": {str(role.id): {"emoji": emoji, "color": color}},
            "title": title,
            "description": description
        }

        save_database(database)
        self.bot.add_view(view, message_id=message.id)

        await interaction.response.send_message(
            f"Role button for {role.name} added in {channel.mention}.",
            ephemeral=True
        )

    @app_commands.command(name="addreactrole", description="Add more role buttons to an existing message")
    @app_commands.describe(
        channel="Channel where the message is located",
        message_id="ID of the message to add buttons to",
        emoji="Emoji for the button",
        role="Role to assign",
        color="Button color: red, green, blue"
    )
    async def addreactrole(
            self,
            interaction: discord.Interaction,
            channel: discord.TextChannel,
            message_id: str,
            emoji: str,
            role: discord.Role,
            color: str
    ):
        # Check permissions
        if not interaction.channel.permissions_for(interaction.guild.me).manage_roles:
            await interaction.response.send_message(
                "I don't have permission to manage roles in this server.",
                ephemeral=True
            )
            return

        if color not in ['red', 'green', 'blue']:
            await interaction.response.send_message(
                "Color must be 'red', 'green', or 'blue'.",
                ephemeral=True
            )
            return

        # Check if role is manageable
        if role.position >= interaction.guild.me.top_role.position:
            await interaction.response.send_message(
                f"I can't assign the {role.name} role because it's higher than or equal to my highest role.",
                ephemeral=True
            )
            return

        try:
            message = await channel.fetch_message(int(message_id))
        except (discord.NotFound, ValueError):
            await interaction.response.send_message(
                "Message not found. Please check the message ID.",
                ephemeral=True
            )
            return

        database = load_database()
        guild_id = str(interaction.guild_id)

        # Check if we're adding to an existing role message
        if guild_id not in database or str(message_id) not in database[guild_id]:
            await interaction.response.send_message(
                "This message is not set up for role buttons. Use /reactrole to create a new role button message.",
                ephemeral=True
            )
            return

        # Get existing data
        message_data = database[guild_id][str(message_id)]

        # Check if this role is already on the message
        if str(role.id) in message_data['roles']:
            await interaction.response.send_message(
                f"The role {role.name} is already on this message.",
                ephemeral=True
            )
            return

        # Create a new view with all existing buttons plus the new one
        view = PersistentRoleView()

        # Add existing buttons
        for role_id, role_data in message_data['roles'].items():
            existing_role = interaction.guild.get_role(int(role_id))
            if existing_role:
                existing_button = RoleButton(
                    int(role_id),
                    existing_role.name,
                    role_data['emoji'],
                    self.get_button_color(role_data['color'])
                )
                view.add_item(existing_button)

        # Add new button
        button = RoleButton(role.id, role.name, emoji, self.get_button_color(color))
        view.add_item(button)

        # Update the message
        await message.edit(view=view)

        # Update the database
        message_data['roles'][str(role.id)] = {"emoji": emoji, "color": color}
        save_database(database)

        # Register the view
        self.bot.add_view(view, message_id=int(message_id))

        await interaction.response.send_message(
            f"Added role button for {role.name} to the message.",
            ephemeral=True
        )

    @app_commands.command(name="removereactrole", description="Remove a role button from a message")
    @app_commands.describe(
        channel="Channel where the message is located",
        message_id="ID of the message",
        role="Role to remove from the message"
    )
    async def removereactrole(
            self,
            interaction: discord.Interaction,
            channel: discord.TextChannel,
            message_id: str,
            role: discord.Role
    ):
        try:
            message = await channel.fetch_message(int(message_id))
        except (discord.NotFound, ValueError):
            await interaction.response.send_message(
                "Message not found. Please check the message ID.",
                ephemeral=True
            )
            return

        database = load_database()
        guild_id = str(interaction.guild_id)

        if (guild_id not in database or
                str(message_id) not in database[guild_id] or
                str(role.id) not in database[guild_id][str(message_id)]['roles']):
            await interaction.response.send_message(
                f"The role {role.name} is not on this message.",
                ephemeral=True
            )
            return

        # Remove the role from the database
        message_data = database[guild_id][str(message_id)]
        del message_data['roles'][str(role.id)]

        # If no roles left, delete the entire message entry
        if not message_data['roles']:
            del database[guild_id][str(message_id)]
            await message.delete()
            save_database(database)
            await interaction.response.send_message(
                f"Removed the last role button. Message has been deleted.",
                ephemeral=True
            )
            return

        # Create a new view with remaining buttons
        view = PersistentRoleView()

        for role_id, role_data in message_data['roles'].items():
            existing_role = interaction.guild.get_role(int(role_id))
            if existing_role:
                existing_button = RoleButton(
                    int(role_id),
                    existing_role.name,
                    role_data['emoji'],
                    self.get_button_color(role_data['color'])
                )
                view.add_item(existing_button)

        # Update the message
        await message.edit(view=view)

        # Save the database
        save_database(database)

        # Register the view
        self.bot.add_view(view, message_id=int(message_id))

        await interaction.response.send_message(
            f"Removed role button for {role.name} from the message.",
            ephemeral=True
        )

    # Helper function to map color to discord button style
    def get_button_color(self, color: str):
        if color == 'red':
            return discord.ButtonStyle.danger
        elif color == 'green':
            return discord.ButtonStyle.success
        else:  # 'blue'
            return discord.ButtonStyle.primary


# Setup the cog
async def setup(bot):
    await bot.add_cog(RoleButtonCog(bot))
