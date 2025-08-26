import os
import json
import asyncio
import datetime
import aiohttp
import discord
from discord.ext import commands, tasks
from typing import Dict, List, Optional, Set
from aiohttp import ClientTimeout, TCPConnector


class TwitchNotifications(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.twitch_client_id = os.getenv('TWITCH_CLIENT_ID')
        self.twitch_client_secret = os.getenv('TWITCH_CLIENT_SECRET')
        self.access_token = None
        self.token_expires_at = 0
        self.streamers_file = './databases/twitch_streamers.json'
        self.notification_channels_file = './databases/twitch_notification_channels.json'
        self.active_streams = {}  # {guild_id: {username: message_id}}
        self.streamers = {}  # {guild_id: [username1, username2, ...]}
        self.notification_channels = {}  # {guild_id: channel_id}

        # Create a persistent session that will be reused
        self.timeout = ClientTimeout(total=30, connect=10)
        self.connector = TCPConnector(
            limit=100,
            limit_per_host=30,
            ttl_dns_cache=300,
            use_dns_cache=True,
        )
        self.session = None  # Will be initialized when needed

        self.load_streamers()
        self.load_notification_channels()
        self.check_streams.start()

    async def get_session(self):
        """Get or create the aiohttp session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                timeout=self.timeout,
                connector=self.connector
            )
        return self.session

    def cog_unload(self):
        self.check_streams.cancel()
        # Clean up session and connector
        if self.session and not self.session.closed:
            asyncio.create_task(self.session.close())
        if hasattr(self, 'connector') and not self.connector.closed:
            asyncio.create_task(self.connector.close())

    def load_streamers(self):
        """Load streamers from file"""
        try:
            if os.path.exists(self.streamers_file):
                with open(self.streamers_file, 'r') as f:
                    self.streamers = json.load(f)
            else:
                self.streamers = {}
            print("Twitch streamers loaded successfully")
        except Exception as e:
            print(f"Error loading Twitch streamers: {e}")
            self.streamers = {}

    def save_streamers(self):
        """Save streamers to file"""
        try:
            os.makedirs(os.path.dirname(self.streamers_file), exist_ok=True)
            with open(self.streamers_file, 'w') as f:
                json.dump(self.streamers, f)
        except Exception as e:
            print(f"Error saving Twitch streamers: {e}")

    def load_notification_channels(self):
        """Load notification channels from file"""
        try:
            if os.path.exists(self.notification_channels_file):
                with open(self.notification_channels_file, 'r') as f:
                    self.notification_channels = json.load(f)
            else:
                self.notification_channels = {}
            print("Twitch notification channels loaded successfully")
        except Exception as e:
            print(f"Error loading Twitch notification channels: {e}")
            self.notification_channels = {}

    def save_notification_channels(self):
        """Save notification channels to file"""
        try:
            os.makedirs(os.path.dirname(self.notification_channels_file), exist_ok=True)
            with open(self.notification_channels_file, 'w') as f:
                json.dump(self.notification_channels, f)
        except Exception as e:
            print(f"Error saving Twitch notification channels: {e}")

    async def make_request_with_retry(self, method, url, max_retries=3, **kwargs):
        """Make HTTP request with retry logic for DNS and connection issues"""
        retry_delay = 5

        for attempt in range(max_retries):
            try:
                session = await self.get_session()
                async with session.request(method, url, **kwargs) as response:
                    return response.status, await response.json()

            except aiohttp.ClientConnectorError as e:
                error_msg = str(e).lower()
                if "temporary failure in name resolution" in error_msg or "cannot connect to host" in error_msg:
                    print(f"DNS/Connection issue for {url}, attempt {attempt + 1}/{max_retries}: {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay * (attempt + 1))
                        continue
                print(f"Connection error after {max_retries} attempts: {e}")
                return None, None

            except aiohttp.ClientError as e:
                if "session is closed" in str(e).lower():
                    print(f"Session closed error for {url}, attempt {attempt + 1}/{max_retries}, recreating session")
                    # Force recreation of session
                    if self.session and not self.session.closed:
                        await self.session.close()
                    self.session = None
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                        continue
                else:
                    print(f"Client error for {url}, attempt {attempt + 1}/{max_retries}: {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                        continue
                return None, None

            except asyncio.TimeoutError:
                print(f"Timeout for {url}, attempt {attempt + 1}/{max_retries}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    continue
                print(f"Request timed out after {max_retries} attempts")
                return None, None

            except Exception as e:
                print(f"Unexpected error for {url}, attempt {attempt + 1}/{max_retries}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    continue
                return None, None

        return None, None

    async def get_access_token(self):
        """Get Twitch API access token with improved error handling"""
        if not self.twitch_client_id or not self.twitch_client_secret:
            print("Twitch API credentials not set")
            return None

        current_time = datetime.datetime.now().timestamp()
        if self.access_token and current_time < self.token_expires_at:
            return self.access_token

        try:
            url = "https://id.twitch.tv/oauth2/token"
            params = {
                "client_id": self.twitch_client_id,
                "client_secret": self.twitch_client_secret,
                "grant_type": "client_credentials"
            }

            status, data = await self.make_request_with_retry("POST", url, params=params)

            if status == 200 and data:
                self.access_token = data["access_token"]
                self.token_expires_at = current_time + data["expires_in"] - 300  # Refresh 5 minutes early
                print("Successfully obtained Twitch access token")
                return self.access_token
            else:
                print(f"Failed to get Twitch access token: {status}")
                return None

        except Exception as e:
            print(f"Error getting Twitch access token: {e}")
            return None

    async def get_streams(self, usernames):
        """Get stream information for a list of usernames with improved error handling"""
        if not usernames:
            return []

        token = await self.get_access_token()
        if not token:
            return []

        try:
            url = "https://api.twitch.tv/helix/streams"
            headers = {
                "Client-ID": self.twitch_client_id,
                "Authorization": f"Bearer {token}"
            }
            params = {"user_login": usernames}

            status, data = await self.make_request_with_retry("GET", url, headers=headers, params=params)

            if status == 200 and data:
                return data.get("data", [])
            else:
                print(f"Failed to get streams: {status}")
                return []

        except Exception as e:
            print(f"Error getting streams: {e}")
            return []

    async def get_users(self, usernames):
        """Get user information for a list of usernames with improved error handling"""
        if not usernames:
            return []

        token = await self.get_access_token()
        if not token:
            return []

        try:
            url = "https://api.twitch.tv/helix/users"
            headers = {
                "Client-ID": self.twitch_client_id,
                "Authorization": f"Bearer {token}"
            }
            params = {"login": usernames}

            status, data = await self.make_request_with_retry("GET", url, headers=headers, params=params)

            if status == 200 and data:
                return data.get("data", [])
            else:
                print(f"Failed to get users: {status}")
                return []

        except Exception as e:
            print(f"Error getting users: {e}")
            return []

    @tasks.loop(minutes=2)
    async def check_streams(self):
        """Check if streamers are live and send notifications"""
        if not self.streamers:
            return

        for guild_id, streamers in self.streamers.items():
            if not streamers:
                continue

            guild_id_str = str(guild_id)
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                continue

            # Get notification channel
            notification_channel_id = self.notification_channels.get(guild_id_str)
            if not notification_channel_id:
                continue  # Skip if no notification channel is set

            channel = guild.get_channel(int(notification_channel_id))
            if not channel:
                continue  # Skip if channel doesn't exist

            # Initialize active streams for this guild if not exists
            if guild_id_str not in self.active_streams:
                self.active_streams[guild_id_str] = {}

            # Get stream data for all streamers in this guild
            stream_data = await self.get_streams(streamers)

            # If we couldn't get stream data due to connection issues, skip this iteration
            if stream_data is None:
                print(f"Skipping stream check for {guild.name} due to connection issues")
                continue

            # Track which streamers are currently live
            live_streamers = {stream['user_login'].lower() for stream in stream_data}

            # Check for streams that have ended
            ended_streams = []
            for username in list(self.active_streams[guild_id_str].keys()):
                if username.lower() not in live_streamers:
                    # Stream ended, delete the notification
                    message_id = self.active_streams[guild_id_str][username]
                    ended_streams.append((username, message_id))

            # Delete notifications for ended streams
            for username, message_id in ended_streams:
                try:
                    try:
                        message = await channel.fetch_message(message_id)
                        await message.delete()
                        print(f"Deleted notification for {username} in {guild.name}")
                    except discord.NotFound:
                        pass  # Message already deleted
                    except Exception as e:
                        print(f"Error deleting message: {e}")
                    # Remove from active streams
                    del self.active_streams[guild_id_str][username]
                except Exception as e:
                    print(f"Error handling ended stream for {username}: {e}")

            # Process live streams
            for stream in stream_data:
                username = stream['user_login'].lower()
                # Skip if we already have an active notification for this stream
                if username in self.active_streams[guild_id_str]:
                    continue

                # Get user data for profile image
                user_data = await self.get_users([username])
                if not user_data:
                    continue

                user = user_data[0]

                # Create and send notification
                try:
                    embed = discord.Embed(
                        title=f"{stream['user_name']} has started streaming!",
                        description=stream['title'],
                        color=discord.Color.purple(),
                        url=f"https://twitch.tv/{username}"
                    )
                    embed.add_field(name="Game", value=stream['game_name'] or "No game specified", inline=True)
                    embed.add_field(name="Viewers", value=str(stream['viewer_count']), inline=True)
                    embed.set_thumbnail(url=user['profile_image_url'])
                    embed.set_image(url=stream['thumbnail_url'].replace('{width}', '440').replace('{height}', '248'))
                    embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
                    embed.set_footer(text="Started streaming")

                    message = await channel.send(embed=embed)
                    self.active_streams[guild_id_str][username] = message.id
                    print(f"Sent notification for {username} in {guild.name}")
                except Exception as e:
                    print(f"Error sending notification for {username}: {e}")

    @check_streams.before_loop
    async def before_check_streams(self):
        await self.bot.wait_until_ready()

    @commands.group(name="twitch", invoke_without_command=True)
    async def twitch(self, ctx):
        """Twitch notification commands"""
        commands_list = [
            "`!twitch add <username>` - Add a Twitch streamer to the notification list",
            "`!twitch remove <username>` - Remove a Twitch streamer from the notification list",
            "`!twitch list` - List all Twitch streamers in the notification list",
            "`!twitch setchannel [#channel]` - Set the channel for Twitch notifications (defaults to current channel)",
            "`!twitch showchannel` - Show the current notification channel"
        ]
        embed = discord.Embed(
            title="Twitch Notification Commands",
            description="\n".join(commands_list),
            color=discord.Color.purple()
        )
        await ctx.send(embed=embed)

    @twitch.command(name="add")
    @commands.has_permissions(administrator=True)
    async def add_streamer(self, ctx, username: str):
        """Add a Twitch streamer to the notification list"""
        guild_id = str(ctx.guild.id)
        # Check if notification channel is set
        if guild_id not in self.notification_channels:
            await ctx.send("⚠️ No notification channel set! Please set one with `!twitch setchannel #channel` first.")
            return

        # Initialize streamers for this guild if not exists
        if guild_id not in self.streamers:
            self.streamers[guild_id] = []

        username = username.lower()
        # Check if streamer already exists
        if username in self.streamers[guild_id]:
            await ctx.send(f"Streamer `{username}` is already in the notification list.")
            return

        # Verify the username exists on Twitch
        user_data = await self.get_users([username])
        if not user_data:
            await ctx.send(f"Streamer `{username}` not found on Twitch or connection issue occurred.")
            return

        # Add streamer
        self.streamers[guild_id].append(username)
        self.save_streamers()
        await ctx.send(f"✅ Added `{username}` to the Twitch notification list.")

    @twitch.command(name="remove")
    @commands.has_permissions(administrator=True)
    async def remove_streamer(self, ctx, username: str):
        """Remove a Twitch streamer from the notification list"""
        guild_id = str(ctx.guild.id)
        if guild_id not in self.streamers:
            await ctx.send("No streamers are set up for this server.")
            return

        username = username.lower()
        if username not in self.streamers[guild_id]:
            await ctx.send(f"Streamer `{username}` is not in the notification list.")
            return

        # Remove streamer
        self.streamers[guild_id].remove(username)
        self.save_streamers()

        # Remove from active streams if exists
        if guild_id in self.active_streams and username in self.active_streams[guild_id]:
            del self.active_streams[guild_id][username]

        await ctx.send(f"✅ Removed `{username}` from the Twitch notification list.")

    @twitch.command(name="list")
    async def list_streamers(self, ctx):
        """List all Twitch streamers in the notification list"""
        guild_id = str(ctx.guild.id)
        if guild_id not in self.streamers or not self.streamers[guild_id]:
            await ctx.send("No streamers are set up for this server.")
            return

        streamers = self.streamers[guild_id]
        embed = discord.Embed(
            title="Twitch Streamers",
            description="List of Twitch streamers for notifications",
            color=discord.Color.purple()
        )
        for i, username in enumerate(streamers, 1):
            embed.add_field(name=f"{i}. {username}", value=f"https://twitch.tv/{username}", inline=False)

        # Add notification channel info
        if guild_id in self.notification_channels:
            channel_id = self.notification_channels[guild_id]
            channel = ctx.guild.get_channel(int(channel_id))
            if channel:
                embed.set_footer(text=f"Notifications are sent to #{channel.name}")

        await ctx.send(embed=embed)

    @twitch.command(name="setchannel")
    @commands.has_permissions(administrator=True)
    async def set_channel(self, ctx, channel: discord.TextChannel = None):
        """Set the channel for Twitch notifications"""
        if channel is None:
            channel = ctx.channel

        guild_id = str(ctx.guild.id)
        self.notification_channels[guild_id] = channel.id
        self.save_notification_channels()
        await ctx.send(f"✅ Twitch notifications will be sent to {channel.mention}.")

    @twitch.command(name="showchannel")
    async def show_channel(self, ctx):
        """Show the current notification channel"""
        guild_id = str(ctx.guild.id)
        if guild_id not in self.notification_channels:
            await ctx.send("⚠️ No notification channel has been set for this server.")
            return

        channel_id = self.notification_channels[guild_id]
        channel = ctx.guild.get_channel(int(channel_id))
        if channel:
            await ctx.send(f"Twitch notifications are currently sent to {channel.mention}.")
        else:
            await ctx.send("⚠️ The configured notification channel no longer exists. Please set a new one.")
            # Remove invalid channel
            del self.notification_channels[guild_id]
            self.save_notification_channels()

    @add_streamer.error
    async def add_streamer_error(self, ctx, error):
        """Handle errors in add_streamer command"""
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("⚠️ You need administrator permissions to use this command.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("⚠️ Please specify a Twitch username to add. Example: `!twitch add ninja`")
        else:
            await ctx.send(f"⚠️ An error occurred: {str(error)}")
            print(f"Error in add_streamer command: {error}")

    @remove_streamer.error
    async def remove_streamer_error(self, ctx, error):
        """Handle errors in remove_streamer command"""
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("⚠️ You need administrator permissions to use this command.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("⚠️ Please specify a Twitch username to remove. Example: `!twitch remove ninja`")
        else:
            await ctx.send(f"⚠️ An error occurred: {str(error)}")
            print(f"Error in remove_streamer command: {error}")

    @set_channel.error
    async def set_channel_error(self, ctx, error):
        """Handle errors in set_channel command"""
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("⚠️ You need administrator permissions to use this command.")
        else:
            await ctx.send(f"⚠️ An error occurred: {str(error)}")
            print(f"Error in set_channel command: {error}")

async def setup(bot):
    await bot.add_cog(TwitchNotifications(bot))

