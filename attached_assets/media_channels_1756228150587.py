import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import re
import asyncio
from typing import Optional, List, Dict, Any


class MediaChannels(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_file = './databases/media_channels.json'
        self.media_channels = self.load_database()

    def load_database(self) -> Dict[str, List[int]]:
        """Load media channels database from file"""
        try:
            if os.path.exists(self.db_file):
                with open(self.db_file, 'r') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            print(f"Error loading media channels database: {e}")
            return {}

    def save_database(self):
        """Save media channels database to file"""
        try:
            os.makedirs(os.path.dirname(self.db_file), exist_ok=True)
            with open(self.db_file, 'w') as f:
                json.dump(self.media_channels, f, indent=2)
        except Exception as e:
            print(f"Error saving media channels database: {e}")

    def is_media_channel(self, guild_id: int, channel_id: int) -> bool:
        """Check if a channel is set as a media channel"""
        guild_str = str(guild_id)
        return guild_str in self.media_channels and channel_id in self.media_channels[guild_str]

    def has_media_content(self, message: discord.Message) -> bool:
        """Check if message contains images, files, or links"""
        # Check for attachments (images, files, etc.)
        if message.attachments:
            return True

        # Check for embeds (usually from links)
        if message.embeds:
            return True

        # Check for URLs in message content
        url_pattern = re.compile(
            r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
        )
        if url_pattern.search(message.content):
            return True

        return False

    async def create_discussion_thread(self, message: discord.Message):
        """Create a discussion thread for a media post"""
        try:
            # Create thread title with user's display name
            thread_name = f"{message.author.display_name} screenshot discussion"

            # Create the thread with 3-day auto archive
            thread = await message.create_thread(
                name=thread_name,
                auto_archive_duration=4320  # 3 days in minutes (3 * 24 * 60 = 4320)
            )

            # Send a welcome message in the thread
            welcome_embed = discord.Embed(
                title="💬 Discussion Thread",
                description=(
                    f"This thread was created for discussing {message.author.display_name}'s post.\n\n"
                    "Feel free to:\n"
                    "• Ask questions about the content.\n"
                    "• Share your thoughts.\n"
                    "• Have conversations related to this post.\n\n"
                    "🕒 This thread will auto-archive after 3 days of inactivity."
                ),
                color=discord.Color.blue()
            )
            welcome_embed.set_footer(text="Keep media channel discussions organized!")

            await thread.send(embed=welcome_embed)

            print(f"Created discussion thread '{thread_name}' for {message.author} in {message.channel.name}")

        except discord.Forbidden:
            print(f"Cannot create thread in {message.channel.name} - missing permissions")
        except discord.HTTPException as e:
            print(f"Error creating thread: {e}")
        except Exception as e:
            print(f"Unexpected error creating thread: {e}")

    async def send_reminder(self, channel: discord.TextChannel, user: discord.Member):
        """Send a reminder message about media channel rules"""
        embed = discord.Embed(
            title="📸 Media Channel Reminder",
            description=(
                f"{user.mention}, this channel is for sharing **images, files, and links** only!\n\n"
                "**What you can post:**\n"
                "• Images and photos\n"
                "• Links to websites\n\n"
                "**For discussions:** Use the thread!"
            ),
            color=discord.Color.orange()
        )
        embed.set_footer(text="Your message was removed because it didn't contain media content.")

        # Send the reminder and delete it after 10 seconds
        try:
            reminder_msg = await channel.send(embed=embed, delete_after=10)
        except discord.Forbidden:
            print(f"Cannot send reminder in {channel.name} - missing permissions")
        except Exception as e:
            print(f"Error sending reminder: {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Monitor messages in media channels"""
        # Ignore bot messages
        if message.author.bot:
            return

        # Ignore DMs
        if not message.guild:
            return

        # Check if this is a media channel
        if not self.is_media_channel(message.guild.id, message.channel.id):
            return

        # Allow messages in threads
        if isinstance(message.channel, discord.Thread):
            return

        # Check if message has media content
        if self.has_media_content(message):
            # Message has media content - create a discussion thread
            await self.create_discussion_thread(message)
        else:
            # Message doesn't have media content - delete it and send reminder
            try:
                # Delete the message
                await message.delete()

                # Send reminder
                await self.send_reminder(message.channel, message.author)

                print(
                    f"Deleted non-media message from {message.author} in {message.channel.name} ({message.guild.name})")

            except discord.Forbidden:
                print(f"Cannot delete message in {message.channel.name} - missing permissions")
            except discord.NotFound:
                print(f"Message already deleted in {message.channel.name}")
            except Exception as e:
                print(f"Error handling non-media message: {e}")

    @app_commands.command(name="add_media_channel", description="Add a channel as a media-only channel")
    @app_commands.describe(channel="The channel to set as media-only")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def add_media_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Add a channel to the media channels list"""
        guild_str = str(interaction.guild.id)

        # Initialize guild in database if not exists
        if guild_str not in self.media_channels:
            self.media_channels[guild_str] = []

        # Check if channel is already a media channel
        if channel.id in self.media_channels[guild_str]:
            embed = discord.Embed(
                title="❌ Already Set",
                description=f"{channel.mention} is already configured as a media channel.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Add channel to media channels
        self.media_channels[guild_str].append(channel.id)
        self.save_database()

        embed = discord.Embed(
            title="✅ Media Channel Added",
            description=(
                f"{channel.mention} has been set as a media-only channel.\n\n"
                "**Rules now active:**\n"
                "• Only messages with images, files, or links are allowed\n"
                "• Messages without media content will be automatically deleted\n"
                "• Users will receive reminders about the channel rules\n"
                "• **Discussion threads will be automatically created** for each media post\n"
                "• Threads auto-archive after 3 days of inactivity\n\n"
                "🧵 **Thread Creation:** Every media post will get its own discussion thread titled "
                "\"[Username] screenshot discussion\" for organized conversations!"
            ),
            color=discord.Color.green()
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="remove_media_channel", description="Remove a channel from media-only mode")
    @app_commands.describe(channel="The channel to remove from media-only mode")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_media_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Remove a channel from the media channels list"""
        guild_str = str(interaction.guild.id)

        # Check if guild exists in database
        if guild_str not in self.media_channels:
            embed = discord.Embed(
                title="❌ Not Found",
                description="No media channels are configured for this server.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Check if channel is in media channels list
        if channel.id not in self.media_channels[guild_str]:
            embed = discord.Embed(
                title="❌ Not a Media Channel",
                description=f"{channel.mention} is not configured as a media channel.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Remove channel from media channels
        self.media_channels[guild_str].remove(channel.id)

        # Clean up empty guild entries
        if not self.media_channels[guild_str]:
            del self.media_channels[guild_str]

        self.save_database()

        embed = discord.Embed(
            title="✅ Media Channel Removed",
            description=(
                f"{channel.mention} is no longer a media-only channel.\n\n"
                "• All message types are now allowed\n"
                "• Automatic thread creation is disabled\n"
                "• No more automatic message deletion"
            ),
            color=discord.Color.green()
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="list_media_channels", description="List all media-only channels in this server")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def list_media_channels(self, interaction: discord.Interaction):
        """List all media channels for the current guild"""
        guild_str = str(interaction.guild.id)

        if guild_str not in self.media_channels or not self.media_channels[guild_str]:
            embed = discord.Embed(
                title="📸 Media Channels",
                description="No media channels are configured for this server.",
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Get channel mentions
        channel_mentions = []
        channels_to_remove = []

        for channel_id in self.media_channels[guild_str]:
            channel = interaction.guild.get_channel(channel_id)
            if channel:
                channel_mentions.append(channel.mention)
            else:
                # Channel no longer exists, mark for removal
                channels_to_remove.append(channel_id)

        # Clean up deleted channels
        if channels_to_remove:
            for channel_id in channels_to_remove:
                self.media_channels[guild_str].remove(channel_id)
            self.save_database()

        if not channel_mentions:
            embed = discord.Embed(
                title="📸 Media Channels",
                description="No valid media channels found. (Cleaned up deleted channels)",
                color=discord.Color.blue()
            )
        else:
            embed = discord.Embed(
                title="📸 Media Channels",
                description=f"**Active media-only channels:**\n" + "\n".join(channel_mentions),
                color=discord.Color.blue()
            )
            embed.add_field(
                name="Active Features",
                value="• Only images, files, and links allowed\n• Auto thread creation for discussions\n• 3-day thread auto-archive",
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(MediaChannels(bot))


