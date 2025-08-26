import discord
from discord.ext import commands
from discord import app_commands
import os
import pickle
import asyncio
import logging
from typing import Dict, Tuple, List, Optional, Set

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('temp_channels')

# Path to the pickle file for storing permanent channel data
DATABASE_DIR = './databases/'
PERMANENT_CHANNELS_FILE = os.path.join(DATABASE_DIR, 'permanent_channels.pickle')


class TempChannels(commands.Cog):
    """Create temporary voice and text channels on demand"""

    def __init__(self, bot):
        self.bot = bot
        # Ensure database directory exists
        os.makedirs(DATABASE_DIR, exist_ok=True)
        # Dictionary to store permanent channel IDs
        self.permanent_channels = self.load_permanent_channels()
        # Dictionary to store temporary channels
        # Format: {voice_channel_id: (voice_channel_id, text_channel_id, creator_id)}
        self.temp_channels: Dict[int, Tuple[int, int, int]] = {}
        # Set to track channels being processed to prevent race conditions
        self.processing_channels: Set[int] = set()

    def load_permanent_channels(self) -> Dict[int, Dict[str, any]]:
        """Load permanent channel IDs and settings from a pickle file."""
        try:
            if os.path.exists(PERMANENT_CHANNELS_FILE):
                with open(PERMANENT_CHANNELS_FILE, 'rb') as f:
                    data = pickle.load(f)
                    # Handle legacy data format (when channels were stored as just IDs)
                    if data and isinstance(next(iter(data.values())), int):
                        # Convert old format to new format
                        converted_data = {}
                        for channel_id in data:
                            converted_data[channel_id] = {
                                'id': channel_id,
                                'name_format': "{user} voice channel",
                                'text_name_format': "{user} temporary chat",
                                'user_limit': 0,
                                'required_roles': [],
                                'welcome_message': "Welcome to your temporary channel! This channel will be deleted when everyone leaves the voice chat."
                            }
                        # Save the converted data
                        self.permanent_channels = converted_data
                        self.save_permanent_channels()
                        return converted_data
                    return data
        except Exception as e:
            logger.error(f"Error loading permanent channels: {e}")
        return {}

    def save_permanent_channels(self):
        """Save permanent channel IDs and settings to a pickle file."""
        try:
            with open(PERMANENT_CHANNELS_FILE, 'wb') as f:
                pickle.dump(self.permanent_channels, f)
        except Exception as e:
            logger.error(f"Error saving permanent channels: {e}")

    async def lock_channel(self, channel: discord.VoiceChannel):
        """Lock the permanent channel so that regular users cannot join it directly."""
        try:
            guild = channel.guild
            everyone_role = guild.default_role  # The @everyone role
            # Deny the `CONNECT` permission for the @everyone role in the permanent channel
            overwrites = channel.overwrites_for(everyone_role)
            overwrites.connect = False
            await channel.set_permissions(everyone_role, overwrite=overwrites)
            logger.info(f"Locked permanent channel: {channel.name} ({channel.id})")
        except Exception as e:
            logger.error(f"Error locking channel {channel.id}: {e}")

    def get_inherited_permissions(self, permanent_channel: discord.VoiceChannel, member: discord.Member) -> Dict[
        discord.abc.Snowflake, discord.PermissionOverwrite]:
        """Get permissions that should be inherited by temporary channels."""
        overwrites = {}

        # Start with the permanent channel's overwrites as a base
        for target, overwrite in permanent_channel.overwrites.items():
            # Skip @everyone role - we'll handle it separately
            if target == permanent_channel.guild.default_role:
                continue

            # For roles, check if they have connect permission in the permanent channel
            if isinstance(target, discord.Role):
                # If the role has explicit connect permission, inherit all permissions
                if overwrite.connect is True:
                    overwrites[target] = discord.PermissionOverwrite.from_pair(*overwrite.pair())
                # If connect is None (inherit), check the role's default permissions
                elif overwrite.connect is None:
                    # Check if the role would normally be able to connect
                    if target.permissions.connect:
                        overwrites[target] = discord.PermissionOverwrite.from_pair(*overwrite.pair())

            # For members, inherit their permissions if they can connect
            elif isinstance(target, discord.Member):
                if overwrite.connect is True or (overwrite.connect is None and target.guild_permissions.connect):
                    overwrites[target] = discord.PermissionOverwrite.from_pair(*overwrite.pair())

        # Add @everyone with view_channel and connect permissions based on roles that can access
        # This allows the temporary channels to be visible to users who have roles that can access them
        everyone_overwrite = discord.PermissionOverwrite()
        everyone_overwrite.view_channel = True
        everyone_overwrite.connect = True
        overwrites[permanent_channel.guild.default_role] = everyone_overwrite

        # Give the creator full control over their temporary channels
        overwrites[member] = discord.PermissionOverwrite(
            connect=True,
            view_channel=True,
            manage_channels=True,
            manage_permissions=True,
            move_members=True,
            send_messages=True,
            read_messages=True,
            read_message_history=True
        )

        return overwrites

    async def create_temp_channels(self, member: discord.Member, permanent_channel: discord.VoiceChannel):
        """Create temporary voice and text channels for a user."""
        try:
            # Get channel settings from permanent channel data
            channel_data = self.permanent_channels.get(permanent_channel.id, {})
            name_format = channel_data.get('name_format', "{user} voice channel")
            text_name_format = channel_data.get('text_name_format', "{user}'s temporary chat")
            user_limit = channel_data.get('user_limit', 0)  # 0 means no limit

            # Format channel names
            vc_name = name_format.format(user=member.display_name)
            text_name = text_name_format.format(user=member.display_name)

            # Get inherited permissions
            overwrites = self.get_inherited_permissions(permanent_channel, member)

            # Create a temporary voice channel with inherited permissions
            temp_vc = await member.guild.create_voice_channel(
                name=vc_name,
                category=permanent_channel.category,
                overwrites=overwrites,
                user_limit=user_limit,
                bitrate=permanent_channel.bitrate,
                rtc_region=permanent_channel.rtc_region
            )

            # Create a corresponding temporary text channel with inherited permissions
            temp_text = await member.guild.create_text_channel(
                name=text_name,
                category=permanent_channel.category,
                overwrites=overwrites,
                topic=f"Temporary chat for {member.display_name}'s voice channel"
            )

            # Store the temporary channels
            self.temp_channels[temp_vc.id] = (temp_vc.id, temp_text.id, member.id)

            # Move the member to the new voice channel
            await member.move_to(temp_vc)

            # Send welcome message
            welcome_message = channel_data.get('welcome_message',
                                               f"Welcome to your temporary channel, {member.mention}! "
                                               "This channel will be deleted when everyone leaves the voice chat."
                                               )
            await temp_text.send(welcome_message)

            logger.info(f"Created temp channels for {member.display_name}: VC {temp_vc.id}, Text {temp_text.id}")
            return temp_vc, temp_text

        except Exception as e:
            logger.error(f"Error creating temp channels for {member.id}: {e}")
            # If we failed to create both channels, clean up any that were created
            try:
                if 'temp_vc' in locals() and temp_vc:
                    await temp_vc.delete()
                if 'temp_text' in locals() and temp_text:
                    await temp_text.delete()
            except:
                pass
            return None, None

    async def cleanup_temp_channels(self, voice_channel_id: int):
        """Delete temporary voice and text channels when they're empty."""
        # Check if this channel is already being processed
        if voice_channel_id in self.processing_channels:
            return

        self.processing_channels.add(voice_channel_id)

        try:
            if voice_channel_id not in self.temp_channels:
                return

            vc_id, text_id, creator_id = self.temp_channels[voice_channel_id]

            # Get the channels
            voice_channel = self.bot.get_channel(vc_id)
            text_channel = self.bot.get_channel(text_id)

            # Check if the voice channel exists and is empty
            if voice_channel and len(voice_channel.members) == 0:
                # Add a small delay to prevent immediate deletion if someone is rejoining
                await asyncio.sleep(2)

                # Check again if it's still empty
                voice_channel = self.bot.get_channel(vc_id)
                if voice_channel and len(voice_channel.members) == 0:
                    # Remove from tracking BEFORE deleting to prevent race conditions
                    del self.temp_channels[voice_channel_id]

                    # Delete the channels
                    try:
                        if voice_channel:
                            await voice_channel.delete()
                    except Exception as e:
                        logger.error(f"Error deleting voice channel {vc_id}: {e}")

                    try:
                        if text_channel:
                            await text_channel.delete()
                    except Exception as e:
                        logger.error(f"Error deleting text channel {text_id}: {e}")

                    logger.info(f"Deleted temporary channels: VC {vc_id}, Text {text_id}")

        except Exception as e:
            logger.error(f"Error cleaning up temp channels {voice_channel_id}: {e}")
        finally:
            # Remove from processing set
            self.processing_channels.discard(voice_channel_id)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState,
                                    after: discord.VoiceState):
        """Handle voice channel join/leave events."""
        try:
            # When a user joins a permanent voice channel, create temporary channels
            if after.channel and after.channel.id in self.permanent_channels:
                # Check if user has required roles (if configured)
                channel_data = self.permanent_channels[after.channel.id]
                required_roles = channel_data.get('required_roles', [])

                if required_roles:
                    member_roles = [role.id for role in member.roles]
                    if not any(role_id in member_roles for role_id in required_roles):
                        # User doesn't have any of the required roles
                        # Move them back out if possible
                        try:
                            await member.move_to(None)
                        except:
                            pass
                        return

                # Create temporary channels for the user and move them automatically
                await self.create_temp_channels(member, after.channel)

            # Cleanup: Check if a user left a temporary voice channel
            if before.channel and before.channel.id in self.temp_channels:
                await self.cleanup_temp_channels(before.channel.id)

        except Exception as e:
            logger.error(f"Error in voice state update: {e}")

    @app_commands.command(
        name="add_permanent_channel",
        description="Add a voice channel as a 'Make Your Own' channel creator"
    )
    @app_commands.describe(
        channel="The voice channel to use as a creator channel",
        name_format="Format for temporary voice channels (use {user} for username)",
        text_name_format="Format for temporary text channels (use {user} for username)",
        user_limit="Maximum number of users in temporary voice channels (0 for no limit)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def add_permanent_channel(
            self,
            interaction: discord.Interaction,
            channel: discord.VoiceChannel,
            name_format: Optional[str] = "{user} voice channel",
            text_name_format: Optional[str] = "{user} temporary chat",
            user_limit: Optional[int] = 0
    ):
        """
        Add a voice channel as a 'Make Your Own' channel creator

        Parameters:
        -----------
        channel: The voice channel to use
        name_format: Format for temporary voice channels
        text_name_format: Format for temporary text channels
        user_limit: Maximum number of users in temporary voice channels
        """
        try:
            # Store channel settings
            self.permanent_channels[channel.id] = {
                'id': channel.id,
                'name_format': name_format,
                'text_name_format': text_name_format,
                'user_limit': user_limit,
                'required_roles': [],
                'welcome_message': f"Welcome to your temporary channel! This channel will be deleted when everyone leaves the voice chat."
            }

            self.save_permanent_channels()

            # Lock the permanent channel
            await self.lock_channel(channel)

            # Create embed response
            embed = discord.Embed(
                title="Channel Creator Added",
                description=f"**{channel.name}** is now a 'Make Your Own' channel creator!\n\n"
                            f"✅ **How it works**: When users join this channel, they will automatically be moved to a new temporary voice channel with a matching text channel.\n"
                            f"✅ **Automatic Role Inheritance**: Temporary channels will automatically inherit permissions from roles that can access the permanent channel.\n"
                            f"✅ **Auto-cleanup**: Channels are deleted when empty.",
                color=discord.Color.green()
            )
            embed.add_field(
                name="Voice Channel Format",
                value=f"`{name_format}`\nExample: `{name_format.format(user='JohnDoe')}`",
                inline=True
            )
            embed.add_field(
                name="Text Channel Format",
                value=f"`{text_name_format}`\nExample: `{text_name_format.format(user='JohnDoe')}`",
                inline=True
            )
            embed.add_field(
                name="User Limit",
                value=str(user_limit) if user_limit > 0 else "No limit",
                inline=True
            )

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            logger.error(f"Error adding permanent channel: {e}")
            await interaction.response.send_message(
                f"An error occurred: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(
        name="remove_permanent_channel",
        description="Remove a 'Make Your Own' channel creator"
    )
    @app_commands.describe(
        channel="The channel to remove as a creator channel"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_permanent_channel(
            self,
            interaction: discord.Interaction,
            channel: discord.VoiceChannel
    ):
        """
        Remove a 'Make Your Own' channel creator

        Parameters:
        -----------
        channel: The channel to remove
        """
        try:
            if channel.id in self.permanent_channels:
                del self.permanent_channels[channel.id]
                self.save_permanent_channels()

                # Unlock the channel
                guild = channel.guild
                everyone_role = guild.default_role
                overwrites = channel.overwrites_for(everyone_role)
                overwrites.connect = None  # Reset to default
                await channel.set_permissions(everyone_role, overwrite=overwrites)

                await interaction.response.send_message(
                    f"**{channel.name}** is no longer a 'Make Your Own' channel creator."
                )
            else:
                await interaction.response.send_message(
                    f"**{channel.name}** is not a 'Make Your Own' channel creator.",
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"Error removing permanent channel: {e}")
            await interaction.response.send_message(
                f"An error occurred: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(
        name="set_required_roles",
        description="Set roles required to create temporary channels"
    )
    @app_commands.describe(
        channel="The 'Make Your Own' channel to configure",
        role1="First required role",
        role2="Second required role (optional)",
        role3="Third required role (optional)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def set_required_roles(
            self,
            interaction: discord.Interaction,
            channel: discord.VoiceChannel,
            role1: discord.Role,
            role2: Optional[discord.Role] = None,
            role3: Optional[discord.Role] = None
    ):
        """
        Set roles required to create temporary channels

        Parameters:
        -----------
        channel: The 'Make Your Own' channel to configure
        role1-role3: Required roles (users must have at least one)
        """
        try:
            if channel.id not in self.permanent_channels:
                await interaction.response.send_message(
                    f"**{channel.name}** is not a 'Make Your Own' channel creator.",
                    ephemeral=True
                )
                return

            # Collect non-None roles
            roles = [role for role in [role1, role2, role3] if role is not None]
            role_ids = [role.id for role in roles]

            # Update channel settings
            self.permanent_channels[channel.id]['required_roles'] = role_ids
            self.save_permanent_channels()

            # Create response
            role_mentions = [role.mention for role in roles]
            if role_mentions:
                await interaction.response.send_message(
                    f"Users must have at least one of these roles to use **{channel.name}**:\n" +
                    ", ".join(role_mentions)
                )
            else:
                await interaction.response.send_message(
                    f"No roles are required to use **{channel.name}**."
                )

        except Exception as e:
            logger.error(f"Error setting required roles: {e}")
            await interaction.response.send_message(
                f"An error occurred: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(
        name="set_welcome_message",
        description="Set the welcome message for temporary channels"
    )
    @app_commands.describe(
        channel="The 'Make Your Own' channel to configure",
        message="The welcome message to display in new temporary text channels"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def set_welcome_message(
            self,
            interaction: discord.Interaction,
            channel: discord.VoiceChannel,
            message: str
    ):
        """
        Set the welcome message for temporary channels

        Parameters:
        -----------
        channel: The 'Make Your Own' channel to configure
        message: The welcome message to display
        """
        try:
            if channel.id not in self.permanent_channels:
                await interaction.response.send_message(
                    f"**{channel.name}** is not a 'Make Your Own' channel creator.",
                    ephemeral=True
                )
                return

            # Update channel settings
            self.permanent_channels[channel.id]['welcome_message'] = message
            self.save_permanent_channels()

            # Create embed to preview the message
            embed = discord.Embed(
                title="Welcome Message Updated",
                description=f"Welcome message for **{channel.name}** has been updated.",
                color=discord.Color.green()
            )
            embed.add_field(
                name="Preview",
                value=message,
                inline=False
            )

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            logger.error(f"Error setting welcome message: {e}")
            await interaction.response.send_message(
                f"An error occurred: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(
        name="list_channel_creators",
        description="List all 'Make Your Own' channel creators"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def list_channel_creators(self, interaction: discord.Interaction):
        """List all 'Make Your Own' channel creators in the server"""
        try:
            if not self.permanent_channels:
                await interaction.response.send_message(
                    "There are no 'Make Your Own' channel creators set up in this server.",
                    ephemeral=True
                )
                return

            # Create embed
            embed = discord.Embed(
                title="'Make Your Own' Channel Creators",
                description=f"This server has {len(self.permanent_channels)} channel creators configured.\n"
                            f"✅ All temporary channels automatically inherit permissions from roles that can access the permanent channel.\n"
                            f"✅ Users are automatically moved to new temporary channels when they join a creator channel.",
                color=discord.Color.blue()
            )

            # Add each channel to the embed
            for channel_id, settings in self.permanent_channels.items():
                channel = interaction.guild.get_channel(channel_id)
                if not channel:
                    continue

                # Get required roles
                required_role_ids = settings.get('required_roles', [])
                required_roles = []
                for role_id in required_role_ids:
                    role = interaction.guild.get_role(role_id)
                    if role:
                        required_roles.append(role.name)

                # Format field value
                field_value = (
                    f"**Voice Format:** `{settings.get('name_format', '{user} voice channel')}`\n"
                    f"**Text Format:** `{settings.get('text_name_format', '{user} temporary chat')}`\n"
                    f"**User Limit:** {settings.get('user_limit', 0) or 'No limit'}\n"
                    f"**Required Roles:** {', '.join(required_roles) if required_roles else 'None'}\n"
                    f"**Auto-Inherit Permissions:** ✅ Enabled"
                )

                embed.add_field(
                    name=channel.name,
                    value=field_value,
                    inline=False
                )

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            logger.error(f"Error listing channel creators: {e}")
            await interaction.response.send_message(
                f"An error occurred: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(
        name="list_temp_channels",
        description="List all active temporary channels"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def list_temp_channels(self, interaction: discord.Interaction):
        """List all active temporary channels in the server"""
        try:
            if not self.temp_channels:
                await interaction.response.send_message(
                    "There are no active temporary channels in this server.",
                    ephemeral=True
                )
                return

            # Create embed
            embed = discord.Embed(
                title="Active Temporary Channels",
                description=f"This server has {len(self.temp_channels)} active temporary channel pairs.",
                color=discord.Color.green()
            )

            # Add each channel pair to the embed
            for vc_id, (voice_id, text_id, creator_id) in self.temp_channels.items():
                voice_channel = interaction.guild.get_channel(voice_id)
                text_channel = interaction.guild.get_channel(text_id)
                creator = interaction.guild.get_member(creator_id)

                if not voice_channel or not text_channel:
                    continue

                # Count members in voice channel
                member_count = len(voice_channel.members)

                # Format field value
                field_value = (
                    f"**Voice Channel:** {voice_channel.mention} ({member_count} members)\n"
                    f"**Text Channel:** {text_channel.mention}\n"
                    f"**Created by:** {creator.mention if creator else 'Unknown'}\n"
                    f"**Created:** {voice_channel.created_at.strftime('%m/%d/%Y %H:%M')}"
                )

                embed.add_field(
                    name=voice_channel.name,
                    value=field_value,
                    inline=False
                )

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            logger.error(f"Error listing temp channels: {e}")
            await interaction.response.send_message(
                f"An error occurred: {str(e)}",
                ephemeral=True
            )

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        """Clean up if a permanent or temporary channel is deleted."""
        try:
            # If a permanent channel was deleted
            if channel.id in self.permanent_channels:
                del self.permanent_channels[channel.id]
                self.save_permanent_channels()
                logger.info(f"Permanent channel {channel.id} was deleted, removed from tracking")

            # If a temporary voice channel was deleted
            if channel.id in self.temp_channels:
                vc_id, text_id, creator_id = self.temp_channels[channel.id]
                # Try to delete the corresponding text channel if it exists
                text_channel = self.bot.get_channel(text_id)
                if text_channel:
                    await text_channel.delete()
                # Remove from tracking
                del self.temp_channels[channel.id]
                logger.info(f"Temporary voice channel {channel.id} was deleted, cleaned up text channel")

            # Check if a temporary text channel was deleted
            for vc_id, (voice_id, text_id, creator_id) in list(self.temp_channels.items()):
                if channel.id == text_id:
                    # Try to delete the corresponding voice channel if it exists and is empty
                    voice_channel = self.bot.get_channel(voice_id)
                    if voice_channel and len(voice_channel.members) == 0:
                        await voice_channel.delete()
                    # Remove from tracking
                    del self.temp_channels[vc_id]
                    logger.info(f"Temporary text channel {channel.id} was deleted, cleaned up voice channel")
                    break

        except Exception as e:
            logger.error(f"Error in on_guild_channel_delete: {e}")


async def setup(bot):
    await bot.add_cog(TempChannels(bot))

