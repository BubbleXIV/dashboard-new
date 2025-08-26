import os
import discord
from discord.ext import commands
from discord import app_commands
import pickle

DISABLED_COGS_FILE = './databases/disabled_cogs.pkl'


# Function to save disabled cogs per server
def save_disabled_cogs(disabled_cogs):
    with open(DISABLED_COGS_FILE, 'wb') as f:
        pickle.dump(disabled_cogs, f)


# Helper function to load disabled cogs per server
def load_disabled_cogs():
    if os.path.exists(DISABLED_COGS_FILE):
        with open(DISABLED_COGS_FILE, 'rb') as f:
            return pickle.load(f)
    return {}


# Function to generate display names for cogs
def generate_cog_display_names(commands_dir):
    # List all Python files in the commands directory
    files = [f for f in os.listdir(commands_dir) if f.endswith('.py') and f != '__init__.py']
    # Generate display names with better formatting
    cog_display_names = {}
    for f in files:
        cog_name = f[:-3]  # Remove .py extension
        # Convert snake_case to Title Case with spaces
        display_name = ' '.join(word.capitalize() for word in cog_name.split('_'))
        # Special case handling for specific cogs (customize as needed)
        if cog_name.lower() == "formcall":
            display_name = "Form System"
        elif cog_name.lower() == "cog_toggle":
            display_name = "Cog Manager"
        # Add more special cases as needed
        cog_display_names[cog_name] = display_name
    return cog_display_names


class CogToggle(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.disabled_cogs = load_disabled_cogs()
        self.cog_display_names = generate_cog_display_names('./commands')  # Automatically generate display names

    async def unload_disabled_cogs_on_startup(self):
        for guild in self.bot.guilds:
            disabled_cogs = self.get_disabled_cogs_for_guild(guild.id)
            for cog_name in disabled_cogs:
                cog_path = f'commands.{cog_name}'
                try:
                    if cog_path in self.bot.extensions:
                        await self.bot.unload_extension(cog_path)
                        print(f"Disabled cog '{cog_name}' for guild {guild.name} on startup.")
                except Exception as e:
                    print(f"Failed to disable cog {cog_name} on startup for guild {guild.name}: {e}")

    def get_disabled_cogs_for_guild(self, guild_id):
        return self.disabled_cogs.get(str(guild_id), set())

    async def is_owner(self, interaction: discord.Interaction):
        application = await self.bot.application_info()
        if interaction.user.id != application.owner.id:
            await interaction.response.send_message("Only the bot owner can use this command.", ephemeral=True)
            return False
        return True

    @commands.Cog.listener()
    async def on_ready(self):
        await self.unload_disabled_cogs_on_startup()

    # Traditional command methods
    @commands.command(name="disable_cog")
    @commands.is_owner()  # This is a built-in check for traditional commands
    @commands.guild_only()
    async def disable_cog_command(self, ctx, cog_name: str):
        await self.disable_cog(ctx, cog_name)

    @commands.command(name="enable_cog")
    @commands.is_owner()  # This is a built-in check for traditional commands
    @commands.guild_only()
    async def enable_cog_command(self, ctx, cog_name: str):
        await self.enable_cog(ctx, cog_name)

    @commands.command(name="list_cogs")
    @commands.is_owner()  # This is a built-in check for traditional commands
    @commands.guild_only()
    async def list_cogs_command(self, ctx):
        await self.list_cogs(ctx)

    # Slash command implementations
    @app_commands.command(name="disable_cog", description="Disable a cog for this server")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def disable_cog_slash(self, interaction: discord.Interaction, cog_name: str):
        # Check if user is the bot owner
        if not await self.is_owner(interaction):
            return

        # Create a context-like object for compatibility with existing methods
        ctx = await self.bot.get_context(interaction)
        ctx.interaction = interaction
        # Check if the interaction is already responded to
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        await self.disable_cog(ctx, cog_name)

    @app_commands.command(name="enable_cog", description="Enable a cog for this server")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def enable_cog_slash(self, interaction: discord.Interaction, cog_name: str):
        # Check if user is the bot owner
        if not await self.is_owner(interaction):
            return

        # Create a context-like object for compatibility with existing methods
        ctx = await self.bot.get_context(interaction)
        ctx.interaction = interaction
        # Check if the interaction is already responded to
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        await self.enable_cog(ctx, cog_name)

    @app_commands.command(name="list_cogs", description="List all cogs and their status")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def list_cogs_slash(self, interaction: discord.Interaction):
        # Check if user is the bot owner
        if not await self.is_owner(interaction):
            return

        # Create a context-like object for compatibility with existing methods
        ctx = await self.bot.get_context(interaction)
        ctx.interaction = interaction
        # Check if the interaction is already responded to
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        await self.list_cogs(ctx)

    # Core implementation methods
    async def disable_cog(self, ctx, cog_name: str):
        guild_id = str(ctx.guild.id)
        cog_path = f'commands.{cog_name}'
        # Prevent disabling the CogToggle cog
        if cog_name.lower() == "cog_toggle":
            if hasattr(ctx, 'interaction') and not ctx.interaction.response.is_done():
                await ctx.interaction.followup.send(
                    "You cannot disable the Cog Manager as it's required for the bot to function properly.",
                    ephemeral=True)
            else:
                await ctx.send("You cannot disable the Cog Manager as it's required for the bot to function properly.")
            return
        if cog_name in self.get_disabled_cogs_for_guild(guild_id):
            if hasattr(ctx, 'interaction') and not ctx.interaction.response.is_done():
                await ctx.interaction.followup.send(
                    f'Cog **{self.cog_display_names.get(cog_name, cog_name)}** is already disabled for this server.',
                    ephemeral=True)
            else:
                await ctx.send(
                    f'Cog **{self.cog_display_names.get(cog_name, cog_name)}** is already disabled for this server.')
            return
        try:
            # Check if the cog exists
            if cog_path not in self.bot.extensions:
                if hasattr(ctx, 'interaction') and not ctx.interaction.response.is_done():
                    await ctx.interaction.followup.send(f'Cog **{cog_name}** does not exist.', ephemeral=True)
                else:
                    await ctx.send(f'Cog **{cog_name}** does not exist.')
                return
            await self.bot.unload_extension(cog_path)
            # Update disabled cogs
            if guild_id not in self.disabled_cogs:
                self.disabled_cogs[guild_id] = set()
            self.disabled_cogs[guild_id].add(cog_name)
            save_disabled_cogs(self.disabled_cogs)  # Save state
            display_name = self.cog_display_names.get(cog_name, cog_name)
            if hasattr(ctx, 'interaction') and not ctx.interaction.response.is_done():
                await ctx.interaction.followup.send(
                    f'Cog **{display_name}** (`{cog_name}`) disabled successfully for this server.', ephemeral=True)
            else:
                await ctx.send(f'Cog **{display_name}** (`{cog_name}`) disabled successfully for this server.')
        except Exception as e:
            if hasattr(ctx, 'interaction') and not ctx.interaction.response.is_done():
                await ctx.interaction.followup.send(f'Failed to disable cog **{cog_name}**: {e}', ephemeral=True)
            else:
                await ctx.send(f'Failed to disable cog **{cog_name}**: {e}')

    async def enable_cog(self, ctx, cog_name: str):
        guild_id = str(ctx.guild.id)
        cog_path = f'commands.{cog_name}'
        if cog_name not in self.get_disabled_cogs_for_guild(guild_id):
            if hasattr(ctx, 'interaction') and not ctx.interaction.response.is_done():
                await ctx.interaction.followup.send(
                    f'Cog **{self.cog_display_names.get(cog_name, cog_name)}** is already enabled for this server.',
                    ephemeral=True)
            else:
                await ctx.send(
                    f'Cog **{self.cog_display_names.get(cog_name, cog_name)}** is already enabled for this server.')
            return
        try:
            await self.bot.load_extension(cog_path)
            # Update disabled cogs
            if guild_id in self.disabled_cogs:
                self.disabled_cogs[guild_id].remove(cog_name)
                if not self.disabled_cogs[guild_id]:  # If empty, remove the guild entry
                    del self.disabled_cogs[guild_id]
            save_disabled_cogs(self.disabled_cogs)  # Save state
            display_name = self.cog_display_names.get(cog_name, cog_name)
            if hasattr(ctx, 'interaction') and not ctx.interaction.response.is_done():
                await ctx.interaction.followup.send(
                    f'Cog **{display_name}** (`{cog_name}`) enabled successfully for this server.', ephemeral=True)
            else:
                await ctx.send(f'Cog **{display_name}** (`{cog_name}`) enabled successfully for this server.')
        except Exception as e:
            if hasattr(ctx, 'interaction') and not ctx.interaction.response.is_done():
                await ctx.interaction.followup.send(f'Failed to enable cog **{cog_name}**: {e}', ephemeral=True)
            else:
                await ctx.send(f'Failed to enable cog **{cog_name}**: {e}')

    async def list_cogs(self, ctx):
        guild_id = str(ctx.guild.id)
        disabled_cogs = self.get_disabled_cogs_for_guild(guild_id)
        # Get all available cogs
        all_cogs = []
        for filename in os.listdir('./commands'):
            if filename.endswith('.py') and filename != '__init__.py':
                cog_name = filename[:-3]
                all_cogs.append(cog_name)
        # Sort cogs alphabetically by display name
        all_cogs.sort(key=lambda x: self.cog_display_names.get(x, x).lower())
        # Create lists of enabled and disabled cogs with their display names
        enabled_cogs = []
        disabled_cogs_list = []
        for cog_name in all_cogs:
            display_name = self.cog_display_names.get(cog_name, cog_name)
            if cog_name in disabled_cogs:
                disabled_cogs_list.append(f"**{display_name}** (`{cog_name}`)")
            else:
                enabled_cogs.append(f"**{display_name}** (`{cog_name}`)")
        # Create embed with better formatting
        embed = discord.Embed(
            title="Cog Status for this Server",
            description="Below is a list of all available cogs and their status in this server.",
            color=discord.Color.blue()
        )
        if enabled_cogs:
            embed.add_field(
                name=f"✅ Enabled Cogs ({len(enabled_cogs)})",
                value="\n".join(enabled_cogs),
                inline=False
            )
        else:
            embed.add_field(
                name="✅ Enabled Cogs (0)",
                value="No enabled cogs found.",
                inline=False
            )
        if disabled_cogs_list:
            embed.add_field(
                name=f"❌ Disabled Cogs ({len(disabled_cogs_list)})",
                value="\n".join(disabled_cogs_list),
                inline=False
            )
        else:
            embed.add_field(
                name="❌ Disabled Cogs (0)",
                value="No disabled cogs found.",
                inline=False
            )
        embed.set_footer(text="Use /enable_cog or /disable_cog to change cog status")
        if hasattr(ctx, 'interaction') and not ctx.interaction.response.is_done():
            await ctx.interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await ctx.send(embed=embed)

    # Autocomplete for cog names
    @disable_cog_slash.autocomplete('cog_name')
    @enable_cog_slash.autocomplete('cog_name')
    async def cog_autocomplete(self, interaction: discord.Interaction, current: str):
        # First check if the user is the bot owner
        application = await self.bot.application_info()
        if interaction.user.id != application.owner.id:
            return []  # Return empty list if not the owner

        guild_id = str(interaction.guild_id)
        disabled_cogs = self.get_disabled_cogs_for_guild(guild_id)
        # For disable command, show enabled cogs
        if interaction.command.name == "disable_cog":
            available_cogs = []
            for filename in os.listdir('./commands'):
                if filename.endswith('.py') and filename != '__init__.py':
                    cog_name = filename[:-3]
                    if cog_name not in disabled_cogs and cog_name.lower() != "cog_toggle":
                        display_name = self.cog_display_names.get(cog_name, cog_name)
                        available_cogs.append((cog_name, display_name))
            # Filter by current input (check both cog_name and display_name)
            filtered_cogs = [
                (cog, display) for cog, display in available_cogs
                if current.lower() in cog.lower() or current.lower() in display.lower()
            ]
            # Sort by display name
            filtered_cogs.sort(key=lambda x: x[1].lower())
            return [
                app_commands.Choice(name=f"{display} ({cog})", value=cog)
                for cog, display in filtered_cogs[:25]  # Discord limits to 25 choices
            ]
        # For enable command, show disabled cogs
        elif interaction.command.name == "enable_cog":
            available_cogs = []
            for filename in os.listdir('./commands'):
                if filename.endswith('.py') and filename != '__init__.py':
                    cog_name = filename[:-3]
                    if cog_name in disabled_cogs:
                        display_name = self.cog_display_names.get(cog_name, cog_name)
                        available_cogs.append((cog_name, display_name))
            # Filter by current input (check both cog_name and display_name)
            filtered_cogs = [
                (cog, display) for cog, display in available_cogs
                if current.lower() in cog.lower() or current.lower() in display.lower()
            ]
            # Sort by display name
            filtered_cogs.sort(key=lambda x: x[1].lower())
            return [
                app_commands.Choice(name=f"{display} ({cog})", value=cog)
                for cog, display in filtered_cogs[:25]  # Discord limits to 25 choices
            ]
        return []

async def setup(bot):
    # Ensure the database directory exists
    os.makedirs(os.path.dirname(DISABLED_COGS_FILE), exist_ok=True)
    await bot.add_cog(CogToggle(bot))

