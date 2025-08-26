import os
import discord
import logging
import asyncio
import pickle
import json
import shutil
from dotenv import load_dotenv
from discord.ext import commands
from discord import app_commands
from commands.formcall import Formcall, PersistentFormView
from datetime import datetime, timedelta
from discord import TextStyle

# Load environment variables
load_dotenv()
token = os.getenv('TOKEN')
application_id = os.getenv('APPLICATION_ID')

GOOGLE_SHEETS_ENABLED = os.path.exists('google_credentials.json')
if GOOGLE_SHEETS_ENABLED:
    print("✅ Google Sheets credentials found - Sheets integration enabled")
else:
    print("⚠️  Google Sheets credentials not found - Sheets integration disabled")
    print("   Place your google_credentials.json file in the root directory to enable Google Sheets")

if application_id is None:
    raise ValueError("APPLICATION_ID is not set in the environment variables.")
application_id = int(application_id)

# Define your bot with intents and application_id
intents = discord.Intents.all()
intents.members = True
intents.presences = True

# Add your owner role ID here
OWNER_ROLE_ID = 412341987048423427  # Replace with your actual role ID

signup_bypass_roles = {
    "702437656604180634": [  # This is your Guild/Server ID
        "739999454517657761",  # These are Role IDs in that server
        "1269338172459057255",
        "1033814716386136134",
        "1269500228919103508"
    ]
}

_handled_attendance_interactions = set()

# Set up a logger for attendance tracking
attendance_logger = logging.getLogger('attendance')
attendance_logger.setLevel(logging.DEBUG)
attendance_handler = logging.FileHandler(filename='attendance.log', encoding='utf-8', mode='w')
attendance_handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s: %(message)s'))
attendance_logger.addHandler(attendance_handler)


class CommandTree(app_commands.CommandTree):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Define permission mappings based on command patterns
        self.permission_patterns = {
            # Administrator permissions
            'administrator': [
                'admin', 'sync', 'reload', 'debug', 'load', 'unload', 'toggle',
                'disable', 'enable', 'config', 'set', 'cleardatabase', 'clearalldatabases',
                'disable_cog', 'enable_cog', 'shutdown', 'restart'
            ],
            # Manage roles permissions
            'manage_roles': [
                'role', 'rank', 'promote', 'demote', 'rolemanage', 'addrole',
                'removerole', 'createrole', 'deleterole'
            ],
            # Manage messages permissions
            'manage_messages': [
                'purge', 'clear', 'delete', 'clean', 'prune', 'remove'
            ],
            # Manage channels permissions
            'manage_channels': [
                'channel', 'createchannel', 'deletechannel', 'movechannel'
            ],
            # Ban members permissions
            'ban_members': [
                'ban', 'unban', 'banlist'
            ],
            # Kick members permissions
            'kick_members': [
                'kick', 'remove'
            ],
            # Manage nicknames permissions
            'manage_nicknames': [
                'nick', 'nickname', 'rename'
            ],
            # Mute/timeout permissions
            'moderate_members': [
                'mute', 'unmute', 'timeout', 'untimeout', 'silence'
            ]
        }

    def get_required_permission(self, command_name: str) -> str:
        """Automatically detect what permission a command needs based on its name"""
        command_lower = command_name.lower()

        # Check each permission category
        for permission, keywords in self.permission_patterns.items():
            if any(keyword in command_lower for keyword in keywords):
                return permission

        # Default to no special permissions (public command)
        return None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check if user can run this command before it executes"""
        if not interaction.command:
            return True

        command_name = interaction.command.name
        required_permission = self.get_required_permission(command_name)

        # If no special permission required, allow everyone
        if not required_permission:
            return True

        # Always allow bot owners
        if await interaction.client.is_owner(interaction.user):
            return True

        # Check if user has the required permission
        user_permissions = interaction.user.guild_permissions

        if required_permission == 'administrator':
            return user_permissions.administrator
        elif required_permission == 'manage_roles':
            return user_permissions.manage_roles or user_permissions.administrator
        elif required_permission == 'manage_messages':
            return user_permissions.manage_messages or user_permissions.administrator
        elif required_permission == 'manage_channels':
            return user_permissions.manage_channels or user_permissions.administrator
        elif required_permission == 'ban_members':
            return user_permissions.ban_members or user_permissions.administrator
        elif required_permission == 'kick_members':
            return user_permissions.kick_members or user_permissions.administrator
        elif required_permission == 'manage_nicknames':
            return user_permissions.manage_nicknames or user_permissions.administrator
        elif required_permission == 'moderate_members':
            return user_permissions.moderate_members or user_permissions.administrator

        return False

    async def sync(self, *, guild=None):
        """Override sync with automatic permission detection and permission setting"""
        print("🔄 Syncing commands with automatic permission detection...")
        # Do the normal sync first
        commands = await super().sync(guild=guild)

        # Set permissions for each command
        if guild:
            guilds_to_process = [guild]
        else:
            guilds_to_process = self.client.guilds

        for guild_obj in guilds_to_process:
            try:
                # Get all synced commands for this guild
                guild_commands = await self.fetch_commands(guild=guild_obj)
                for command in guild_commands:
                    required_permission = self.get_required_permission(command.name)
                    if required_permission:
                        # Create permission overrides using the simpler approach
                        perms = {}

                        if required_permission == 'administrator':
                            # Deny @everyone first
                            perms[guild_obj.default_role.id] = False
                            # Allow administrators
                            admin_roles = [role for role in guild_obj.roles if role.permissions.administrator]
                            for role in admin_roles:
                                perms[role.id] = True
                        else:
                            # For other permissions, deny @everyone first
                            perms[guild_obj.default_role.id] = False
                            # Allow roles with the required permission
                            for role in guild_obj.roles:
                                role_perms = role.permissions
                                should_allow = False
                                if required_permission == 'manage_roles' and (
                                        role_perms.manage_roles or role_perms.administrator):
                                    should_allow = True
                                elif required_permission == 'manage_messages' and (
                                        role_perms.manage_messages or role_perms.administrator):
                                    should_allow = True
                                elif required_permission == 'manage_channels' and (
                                        role_perms.manage_channels or role_perms.administrator):
                                    should_allow = True
                                elif required_permission == 'ban_members' and (
                                        role_perms.ban_members or role_perms.administrator):
                                    should_allow = True
                                elif required_permission == 'kick_members' and (
                                        role_perms.kick_members or role_perms.administrator):
                                    should_allow = True
                                elif required_permission == 'manage_nicknames' and (
                                        role_perms.manage_nicknames or role_perms.administrator):
                                    should_allow = True
                                elif required_permission == 'moderate_members' and (
                                        role_perms.moderate_members or role_perms.administrator):
                                    should_allow = True

                                if should_allow:
                                    perms[role.id] = True

                        # Always allow bot owners
                        for owner_id in self.client.owner_ids:
                            perms[owner_id] = True

                        # Apply permissions for this command
                        if perms:
                            try:
                                await command.edit_permissions(guild=guild_obj, permissions=perms)
                                print(f"✅ Set permissions for command '{command.name}' in {guild_obj.name}")
                            except discord.Forbidden:
                                print(
                                    f"⚠️  Missing permissions to set command permissions for '{command.name}' in {guild_obj.name}")
                            except discord.HTTPException as e:
                                if e.status == 400:
                                    print(f"⚠️  Invalid permissions for command '{command.name}' in {guild_obj.name}")
                                else:
                                    print(
                                        f"⚠️  HTTP error setting permissions for '{command.name}' in {guild_obj.name}: {e}")
                            except Exception as e:
                                print(
                                    f"⚠️  Error setting permissions for command '{command.name}' in {guild_obj.name}: {e}")
            except Exception as e:
                print(f"⚠️  Error processing permissions for guild {guild_obj.name}: {e}")
                import traceback
                traceback.print_exc()

        print(f"✅ Commands synced with permission restrictions applied!")
        return commands

    async def on_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        if isinstance(error, app_commands.CheckFailure):
            command_name = interaction.command.name if interaction.command else "Unknown"
            required_perm = self.get_required_permission(command_name)

            if required_perm:
                perm_name = required_perm.replace('_', ' ').title()
                await interaction.response.send_message(
                    f"❌ You need **{perm_name}** permission to use this command.",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "❌ You don't have permission to use this command.",
                    ephemeral=True
                )
        else:
            print(f"Command error: {error}")
            import traceback
            traceback.print_exc()

            if not interaction.response.is_done():
                try:
                    await interaction.response.send_message(
                        f"An error occurred: {str(error)}",
                        ephemeral=True
                    )
                except:
                    try:
                        await interaction.followup.send(
                            f"An error occurred: {str(error)}",
                            ephemeral=True
                        )
                    except:
                        print("Could not send error message to user")


async def load_attendance_cogs(bot):
    """Load attendance cogs with proper async compatibility"""
    try:
        print("Loading attendance cog...")
        # Add the bypass roles to the bot so extensions can access it
        bot.signup_bypass_roles = signup_bypass_roles
        # ADD THIS - Make Google Sheets status available to attendance cog
        bot.google_sheets_enabled = GOOGLE_SHEETS_ENABLED

        # Load the attendance cog
        await bot.load_extension('commands.attendance')
        print('Loaded cog: attendance')
        print("Successfully loaded attendance cog")

        # Print Google Sheets status
        if GOOGLE_SHEETS_ENABLED:
            print("📊 Google Sheets integration is enabled for attendance tracking")
        else:
            print("📊 Google Sheets integration is disabled - only local JSON storage will be used")

        return True
    except Exception as e:
        print(f"Error loading attendance cog: {e}")
        import traceback
        traceback.print_exc()
        return False


class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=commands.when_mentioned_or('!', '-'),
                         description='Inhouse Bot by Don',
                         intents=intents,
                         application_id=application_id,
                         tree_cls=CommandTree,
                         owner_ids={412341987048423427})  # Set of user IDs
        self.forms = {}
        self._synced = False
        self.google_sheets_enabled = GOOGLE_SHEETS_ENABLED

    async def is_owner(self, user):
        """Override is_owner to include role-based ownership"""
        # Check default owner first (including owner_ids)
        if await super().is_owner(user):
            return True

        # Check for role in all mutual guilds
        for guild in self.guilds:
            member = guild.get_member(user.id)
            if member and any(role.id == OWNER_ROLE_ID for role in member.roles):
                return True

        return False

    async def setup_hook(self):
        # Load extensions first
        await self.load_commands()
        # Then load forms and recreate buttons
        await self.load_forms()
        await self.recreate_form_buttons()
        # Sync commands only once during startup
        if not self._synced:
            print("Syncing commands during setup...")
            await self.tree.sync()
            self._synced = True
            print("Commands synced during setup")

    async def load_commands(self):
        # First load the cog_toggle.py to manage other cogs
        try:
            await self.load_extension('commands.cog_toggle')
            print('Loaded cog: cog_toggle')
        except Exception as e:
            print(f'Failed to load cog_toggle: {e}')

        # Load event cleanup cog
        try:
            await self.load_extension('commands.event_cleanup')
            print('Loaded cog: event_cleanup')
        except Exception as e:
            print(f'Failed to load event_cleanup: {e}')

        # Use the special loader for attendance cogs
        await load_attendance_cogs(self)

        # Then load all other cogs (except the attendance cogs we already loaded)
        attendance_cogs = ['attendance_tracker', 'attendance_signup']
        for filename in os.listdir('./commands'):
            if filename.endswith('.py') and filename != '__init__.py' and filename != 'cog_toggle.py':
                cog_name = filename[:-3]
                # Skip attendance cogs as they're already loaded
                if cog_name in attendance_cogs:
                    continue
                try:
                    await self.load_extension(f'commands.{cog_name}')
                    print(f'Loaded cog: {cog_name}')
                except Exception as e:
                    print(f'Failed to load cog {cog_name}: {e}')

    async def load_forms(self):
        try:
            # Ensure the directory exists
            os.makedirs(os.path.dirname(FORMS_FILE), exist_ok=True)
            if os.path.exists(FORMS_FILE):
                with open(FORMS_FILE, "r") as f:
                    self.forms = json.load(f)
            else:
                self.forms = {}
            print("Forms loaded successfully")
        except Exception as e:
            print(f"Error loading forms: {e}")
            self.forms = {}

    async def recreate_form_buttons(self):
        try:
            for guild_id, guild_forms in self.forms.items():
                for form_name, form_data in guild_forms.items():
                    # Pass form_name and form_data (not guild_id)
                    view = PersistentFormView.from_form_data(form_name, form_data)
                    self.add_view(view)
                    # Track locations to remove if they're invalid
                    locations_to_remove = []
                    for i, location in enumerate(form_data.get('button_locations', [])):
                        # Check if location is a tuple/list or a dictionary
                        if isinstance(location, (list, tuple)) and len(location) >= 2:
                            # It's a tuple/list format: [channel_id, message_id]
                            channel_id, message_id = location
                        elif isinstance(location, dict) and 'channel_id' in location and 'message_id' in location:
                            # It's a dictionary format: {'channel_id': channel_id, 'message_id': message_id}
                            channel_id = location['channel_id']
                            message_id = location['message_id']
                        else:
                            print(f"Invalid location format: {location}")
                            locations_to_remove.append(location)
                            continue

                        channel = self.get_channel(int(channel_id))
                        if channel:
                            try:
                                message = await channel.fetch_message(int(message_id))
                                embed = discord.Embed(
                                    title=form_name,
                                    description=form_data.get('description',
                                                              f"Click the button below to open the {form_name} form."),
                                    color=discord.Color.blue()
                                )
                                await message.edit(embed=embed, view=view)
                            except discord.NotFound:
                                # Message was deleted, mark this location for removal
                                locations_to_remove.append(location)
                            except Exception as e:
                                print(f"Error recreating button for {form_name}: {e}")
                                locations_to_remove.append(location)
                        else:
                            # Channel not found, mark this location for removal
                            locations_to_remove.append(location)

                    # Remove invalid locations
                    for loc in locations_to_remove:
                        if loc in form_data.get('button_locations', []):
                            form_data['button_locations'].remove(loc)

                    # Save if we removed any locations
                    if locations_to_remove:
                        self.save_forms()
            print("All form buttons have been recreated.")
        except Exception as e:
            print(f"Error recreating form buttons: {e}")

    def save_forms(self):
        try:
            # Ensure the directory exists
            os.makedirs(os.path.dirname(FORMS_FILE), exist_ok=True)
            with open(FORMS_FILE, "w") as f:
                json.dump(self.forms, f)
        except Exception as e:
            print(f"Error saving forms: {e}")


bot = MyBot()
# Setup logging
logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

# File to store disabled cogs
DISABLED_COGS_FILE = './databases/disabled_cogs.pkl'
FORMS_FILE = "./databases/forms.json"


# Function to load disabled cogs from file
def load_disabled_cogs():
    if os.path.exists(DISABLED_COGS_FILE):
        with open(DISABLED_COGS_FILE, 'rb') as f:
            return pickle.load(f)
    return set()


# Function to save disabled cogs to file
def save_disabled_cogs(disabled_cogs):
    # Ensure the directory exists
    os.makedirs(os.path.dirname(DISABLED_COGS_FILE), exist_ok=True)
    with open(DISABLED_COGS_FILE, 'wb') as f:
        pickle.dump(disabled_cogs, f)


# Initialize disabled cogs set
disabled_cogs = load_disabled_cogs()


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} ({bot.user.id})')
    # Print guild information
    print(f"Bot is in {len(bot.guilds)} guilds:")
    for guild in bot.guilds:
        print(f"- {guild.name} (ID: {guild.id})")

    # Print Google Sheets status
    print(f"📊 Google Sheets Integration: {'✅ Enabled' if bot.google_sheets_enabled else '❌ Disabled'}")

    # Set activity
    activity = discord.Game(name="boom boom.")
    await bot.change_presence(activity=activity)

    # Print all loaded cogs with their exact class names
    print("All loaded cogs with their exact class names:")
    for cog_name, cog in bot.cogs.items():
        print(f"- {cog_name} (Class: {cog.__class__.__name__})")
    print(f"Loaded extensions: {list(bot.extensions.keys())}")

    # Check if attendance cog is loaded, if not, load it
    if 'commands.attendance' not in bot.extensions:
        print("Attendance cog not loaded, loading now...")
        # Add the bypass roles to the bot so extensions can access it
        bot.signup_bypass_roles = signup_bypass_roles
        bot.google_sheets_enabled = GOOGLE_SHEETS_ENABLED
        try:
            await bot.load_extension('commands.attendance')
            print('Loaded cog: attendance')
        except Exception as e:
            print(f"Error loading attendance cog: {e}")
            import traceback
            traceback.print_exc()

    # Try to find the attendance cog by class name
    attendance_cog = None
    for cog_name, cog in bot.cogs.items():
        if cog.__class__.__name__ == "Attendance":
            attendance_cog = cog
            print(f"Found Attendance cog as '{cog_name}'")
            break

    if attendance_cog:
        print("Loading events in attendance cog...")
        try:
            # Load events for all guilds
            for guild in bot.guilds:
                await attendance_cog.load_events(str(guild.id))
            print("Events loaded successfully")
        except Exception as e:
            print(f"Error loading events in attendance cog: {e}")
            import traceback
            traceback.print_exc()

        # Set up persistent views for attendance
        print("Setting up persistent views for attendance...")
        try:
            await attendance_cog.setup_persistent_views()
            print("Attendance views set up successfully")
        except Exception as e:
            print(f"Error setting up attendance views: {e}")
            import traceback
            traceback.print_exc()

        # Show Google Sheets status for attendance
        if hasattr(attendance_cog, 'attendance_tracker'):
            sheets_status = getattr(attendance_cog.attendance_tracker, 'sheets_enabled', False)
            print(f"📊 Attendance Google Sheets: {'✅ Ready' if sheets_status else '❌ Not Ready'}")

    else:
        print("Attendance cog not found! Available cogs:")
        for cog_name in bot.cogs:
            print(f"- {cog_name}")


@bot.event
async def on_interaction(interaction):
    # Handle attendance button interactions
    if interaction.type == discord.InteractionType.component:
        custom_id = interaction.data.get("custom_id", "")
        if custom_id.startswith("attendance:"):
            # Find the attendance cog
            attendance_cog = bot.get_cog("Attendance")
            if attendance_cog:
                # Generate a unique ID for this interaction to prevent double-processing
                interaction_id = f"{interaction.id}:{custom_id}"
                if interaction_id not in _handled_attendance_interactions:
                    _handled_attendance_interactions.add(interaction_id)
                    # Parse the custom ID to get event_id and role_id
                    parts = custom_id.split(":")
                    if len(parts) >= 4 and parts[3] == "toggle":
                        event_id = parts[1]
                        role_id = parts[2]
                        # Handle the role toggle
                        await attendance_cog.toggle_role(interaction, event_id, role_id)
                    # Clean up old interaction IDs (keep the set from growing too large)
                    if len(_handled_attendance_interactions) > 1000:
                        _handled_attendance_interactions.clear()


# Global sync flag to prevent multiple syncs
_is_syncing = False


@bot.command(name="sync")
@commands.is_owner()  # This will now work with your role!
async def sync_commands(ctx):
    global _is_syncing
    if _is_syncing:
        await ctx.send("Already syncing commands, please wait...")
        return
    try:
        _is_syncing = True
        await ctx.send("Syncing commands...")
        # Sync commands globally
        synced = await bot.tree.sync()
        await ctx.send(f"Synced {len(synced)} command(s) successfully!")
        bot._synced = True
    except Exception as e:
        await ctx.send(f"Error syncing commands: {e}")
        import traceback
        traceback.print_exc()
    finally:
        _is_syncing = False


@bot.command(name="load_time_acceleration")
@commands.is_owner()
async def load_time_acceleration(ctx):
    """Load the time acceleration testing cog"""
    try:
        await bot.load_extension('commands.time_acceleration')
        await ctx.send("Time acceleration testing cog loaded!")
    except Exception as e:
        await ctx.send(f"Error loading time acceleration testing cog: {e}")


@bot.command(name="sync_guild")
@commands.is_owner()
async def sync_guild_commands(ctx):
    global _is_syncing
    if _is_syncing:
        await ctx.send("Already syncing commands, please wait...")
        return
    try:
        _is_syncing = True
        await ctx.send(f"Syncing commands to guild {ctx.guild.id}...")
        # Sync commands to the current guild
        bot.tree.copy_global_to(guild=ctx.guild)
        synced = await bot.tree.sync(guild=ctx.guild)
        await ctx.send(f"Synced {len(synced)} command(s) to this guild successfully!")
    except Exception as e:
        await ctx.send(f"Error syncing commands: {e}")
        import traceback
        traceback.print_exc()
    finally:
        _is_syncing = False


@bot.command(name="clear_commands")
@commands.is_owner()
async def clear_commands(ctx):
    global _is_syncing
    if _is_syncing:
        await ctx.send("Already syncing commands, please wait...")
        return
    try:
        _is_syncing = True
        await ctx.send("Clearing all commands...")
        # Clear all commands
        bot.tree.clear_commands(guild=None)
        await bot.tree.sync()
        await ctx.send("All commands have been cleared!")
    except Exception as e:
        await ctx.send(f"Error clearing commands: {e}")
        import traceback
        traceback.print_exc()
    finally:
        _is_syncing = False


@bot.command(name="reload")
@commands.is_owner()
async def reload_cogs(ctx, cog_name=None):
    """Reload all cogs or a specific cog"""
    if cog_name:
        try:
            await bot.reload_extension(f"commands.{cog_name}")
            await ctx.send(f"Reloaded cog: {cog_name}")
        except Exception as e:
            await ctx.send(f"Error reloading cog {cog_name}: {e}")
    else:
        # Reload all cogs
        success = []
        failed = []
        for extension in list(bot.extensions.keys()):
            try:
                await bot.reload_extension(extension)
                success.append(extension)
            except Exception as e:
                failed.append(f"{extension}: {e}")

        message = f"Reloaded {len(success)} cogs successfully."
        if failed:
            message += f"\nFailed to reload {len(failed)} cogs:\n" + "\n".join(failed)
        await ctx.send(message)


@bot.command(name="debug")
@commands.is_owner()
async def debug_info(ctx):
    """Show debug information about the bot"""
    embed = discord.Embed(title="Bot Debug Information", color=discord.Color.blue())

    # Bot info
    embed.add_field(
        name="Bot Info",
        value=f"Name: {bot.user.name}\nID: {bot.user.id}\nLatency: {round(bot.latency * 1000)}ms",
        inline=False
    )

    # Loaded cogs
    cogs_list = "\n".join(list(bot.extensions.keys())) or "None"
    embed.add_field(name="Loaded Extensions", value=f"```{cogs_list}```", inline=False)

    # Command count
    global_commands = len(await bot.tree.fetch_commands())
    embed.add_field(name="Global Commands", value=str(global_commands), inline=True)

    # Guild count
    embed.add_field(name="Guilds", value=str(len(bot.guilds)), inline=True)

    # Sync status
    embed.add_field(name="Commands Synced", value=str(bot._synced), inline=True)

    await ctx.send(embed=embed)


@bot.command(name="sheets_status")
@commands.is_owner()
async def sheets_status(ctx):
    """Check Google Sheets integration status"""
    embed = discord.Embed(title="📊 Google Sheets Status", color=discord.Color.blue())

    # Check if credentials file exists
    creds_exist = os.path.exists('google_credentials.json')
    embed.add_field(
        name="Credentials File",
        value="✅ Found" if creds_exist else "❌ Missing",
        inline=True
    )

    # Check bot attribute
    embed.add_field(
        name="Bot Integration",
        value="✅ Enabled" if bot.google_sheets_enabled else "❌ Disabled",
        inline=True
    )

    # Check attendance cog
    attendance_cog = bot.get_cog("Attendance")
    if attendance_cog and hasattr(attendance_cog, 'attendance_tracker'):
        sheets_enabled = getattr(attendance_cog.attendance_tracker, 'sheets_enabled', False)
        embed.add_field(
            name="Attendance Tracker",
            value="✅ Ready" if sheets_enabled else "❌ Not Ready",
            inline=True
        )

        # Show cache info if available
        if hasattr(attendance_cog.attendance_tracker, 'sheets_cache'):
            cache_count = len(attendance_cog.attendance_tracker.sheets_cache)
            embed.add_field(
                name="Cached Sheets",
                value=str(cache_count),
                inline=True
            )
    else:
        embed.add_field(
            name="Attendance Tracker",
            value="❌ Not Found",
            inline=True
        )

    # Instructions
    if not creds_exist:
        embed.add_field(
            name="Setup Instructions",
            value="1. Create a Google Service Account\n"
                  "2. Download the JSON credentials\n"
                  "3. Rename to `google_credentials.json`\n"
                  "4. Place in bot root directory\n"
                  "5. Restart the bot",
            inline=False
        )

    await ctx.send(embed=embed)


@bot.command(name="check_permissions")
@commands.is_owner()
async def check_permissions(ctx, *, command_name: str = None):
    """Check what permission a command requires"""
    if command_name:
        required_perm = bot.tree.get_required_permission(command_name)
        if required_perm:
            await ctx.send(f"Command `{command_name}` requires: **{required_perm.replace('_', ' ').title()}**")
        else:
            await ctx.send(f"Command `{command_name}` is **public** (no special permissions required)")
    else:
        # Show all commands and their permissions
        commands = await bot.tree.fetch_commands()

        categorized = {
            'Public': [],
            'Administrator': [],
            'Manage Roles': [],
            'Manage Messages': [],
            'Manage Channels': [],
            'Ban Members': [],
            'Kick Members': [],
            'Manage Nicknames': [],
            'Moderate Members': []
        }

        for command in commands:
            required_perm = bot.tree.get_required_permission(command.name)
            if not required_perm:
                categorized['Public'].append(command.name)
            else:
                perm_name = required_perm.replace('_', ' ').title()
                if perm_name in categorized:
                    categorized[perm_name].append(command.name)

        embed = discord.Embed(title="Command Permissions Overview", color=discord.Color.blue())

        for category, commands_list in categorized.items():
            if commands_list:
                # Limit to first 10 commands to avoid embed limits
                display_commands = commands_list[:10]
                if len(commands_list) > 10:
                    display_commands.append(f"... and {len(commands_list) - 10} more")

                embed.add_field(
                    name=f"{category} ({len(commands_list)})",
                    value=", ".join(display_commands) if display_commands else "None",
                    inline=False
                )

        await ctx.send(embed=embed)


@bot.command(name="add_permission_pattern")
@commands.is_owner()
async def add_permission_pattern(ctx, permission: str, *, keywords: str):
    """Add new keywords to a permission category"""
    keywords_list = [k.strip() for k in keywords.split(',')]

    if permission in bot.tree.permission_patterns:
        bot.tree.permission_patterns[permission].extend(keywords_list)
        await ctx.send(f"✅ Added keywords `{', '.join(keywords_list)}` to **{permission}** category")
    else:
        await ctx.send(
            f"❌ Permission category `{permission}` not found. Available: {', '.join(bot.tree.permission_patterns.keys())}")


async def main():
    # Ensure directories exist
    os.makedirs('./databases', exist_ok=True)
    async with bot:
        await bot.start(token, reconnect=True)


if __name__ == '__main__':
    asyncio.run(main())

