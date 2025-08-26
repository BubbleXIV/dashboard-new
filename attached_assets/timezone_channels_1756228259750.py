import discord
from discord.ext import commands, tasks
import pytz
from datetime import datetime
import json
import os
import asyncio
from typing import Dict, List, Optional, Union


class TimezoneChannels(commands.Cog):
    """
    A cog that manages voice channels displaying current time in different time zones.
    """

    # Define time zones with their display names
    TIMEZONES = {
        "PST": {"timezone": "America/Los_Angeles", "display": "Pacific"},
        "MST": {"timezone": "America/Denver", "display": "Mountain"},
        "CST": {"timezone": "America/Chicago", "display": "Central"},
        "EST": {"timezone": "America/New_York", "display": "Eastern"},
        "GMT": {"timezone": "Europe/London", "display": "GMT"},
        "IST": {"timezone": "Asia/Kolkata", "display": "Indian"},
        "ACST": {"timezone": "Australia/Adelaide", "display": "Australian Central"}
    }

    def __init__(self, bot):
        self.bot = bot
        self.config_file = "./databases/timezone_channels.json"
        self.config: Dict[str, Dict[str, int]] = {}
        self.update_interval = 5  # Default update interval in minutes
        self.load_config()
        self.update_channels.start()

    def cog_unload(self):
        self.update_channels.cancel()

    def load_config(self):
        """Load timezone channel configuration from file."""
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            if os.path.exists(self.config_file):
                with open(self.config_file, "r") as f:
                    self.config = json.load(f)
            else:
                self.config = {}
        except Exception as e:
            print(f"Error loading timezone channel config: {e}")
            self.config = {}

    def save_config(self):
        """Save timezone channel configuration to file."""
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, "w") as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print(f"Error saving timezone channel config: {e}")

    @tasks.loop(minutes=5)
    async def update_channels(self):
        """Update all configured timezone channels."""
        for guild_id, channels in self.config.items():
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                continue

            for tz_code, channel_id in channels.items():
                if tz_code not in self.TIMEZONES:
                    continue

                channel = guild.get_channel(channel_id)
                if not channel:
                    continue

                # Get the current time in the timezone
                tz_info = self.TIMEZONES[tz_code]
                timezone = pytz.timezone(tz_info["timezone"])
                current_time = datetime.now(timezone)

                # Format the time as "HH:MM AM/PM Timezone"
                time_str = current_time.strftime("%-I:%M %p")
                new_name = f"🕒 {time_str} {tz_info['display']}"

                # Only update if the name has changed
                if channel.name != new_name:
                    try:
                        # Use edit without reason to avoid audit log entries
                        await channel.edit(name=new_name)
                        # Add a small delay to avoid rate limits
                        await asyncio.sleep(1)
                    except Exception as e:
                        print(f"Error updating timezone channel {channel.id} in guild {guild.id}: {e}")

    @update_channels.before_loop
    async def before_update_channels(self):
        await self.bot.wait_until_ready()

    @commands.group(name="timezone", aliases=["tz"])
    @commands.has_permissions(administrator=True)
    async def timezone_group(self, ctx):
        """Commands to manage timezone channels."""
        if ctx.invoked_subcommand is None:
            await ctx.send("Please specify a subcommand. Use `!help timezone` for more information.")

    @timezone_group.command(name="set")
    async def set_timezone_channel(self, ctx, timezone_code: str, channel: discord.VoiceChannel):
        """
        Set a voice channel to display the time for a specific timezone.

        Example: !timezone set CST 123456789012345678
        """
        timezone_code = timezone_code.upper()
        if timezone_code not in self.TIMEZONES:
            available_timezones = ", ".join(self.TIMEZONES.keys())
            await ctx.send(f"Invalid timezone code. Available options: {available_timezones}")
            return

        guild_id = str(ctx.guild.id)
        if guild_id not in self.config:
            self.config[guild_id] = {}

        self.config[guild_id][timezone_code] = channel.id
        self.save_config()

        # Update the channel immediately
        tz_info = self.TIMEZONES[timezone_code]
        timezone = pytz.timezone(tz_info["timezone"])
        current_time = datetime.now(timezone)
        time_str = current_time.strftime("%-I:%M %p")
        new_name = f"🕒 {time_str} {tz_info['display']}"

        try:
            await channel.edit(name=new_name)
            await ctx.send(f"✅ Channel {channel.mention} has been set to display {timezone_code} time.")
        except Exception as e:
            await ctx.send(f"⚠️ Failed to update channel name: {e}")

    @timezone_group.command(name="remove", aliases=["delete", "unset"])
    async def remove_timezone_channel(self, ctx, timezone_code: str):
        """
        Remove a timezone channel configuration.

        Example: !timezone remove CST
        """
        timezone_code = timezone_code.upper()
        guild_id = str(ctx.guild.id)

        if guild_id not in self.config or timezone_code not in self.config[guild_id]:
            await ctx.send(f"No channel is configured for {timezone_code} in this server.")
            return

        channel_id = self.config[guild_id][timezone_code]
        channel = ctx.guild.get_channel(channel_id)

        del self.config[guild_id][timezone_code]
        if not self.config[guild_id]:
            del self.config[guild_id]

        self.save_config()

        if channel:
            channel_mention = channel.mention
        else:
            channel_mention = f"channel (ID: {channel_id})"

        await ctx.send(f"✅ Removed {timezone_code} configuration from {channel_mention}.")

    @timezone_group.command(name="list")
    async def list_timezone_channels(self, ctx):
        """List all configured timezone channels in this server."""
        guild_id = str(ctx.guild.id)

        if guild_id not in self.config or not self.config[guild_id]:
            await ctx.send("No timezone channels are configured in this server.")
            return

        embed = discord.Embed(
            title="Timezone Channels",
            description="List of configured timezone channels in this server:",
            color=discord.Color.blue()
        )

        for tz_code, channel_id in self.config[guild_id].items():
            channel = ctx.guild.get_channel(channel_id)
            if channel:
                channel_info = f"{channel.mention} ({channel.name})"
            else:
                channel_info = f"Channel not found (ID: {channel_id})"

            tz_info = self.TIMEZONES[tz_code]
            embed.add_field(
                name=f"{tz_code} - {tz_info['display']}",
                value=channel_info,
                inline=False
            )

        await ctx.send(embed=embed)

    @timezone_group.command(name="interval")
    async def set_update_interval(self, ctx, minutes: int):
        """
        Set how often the timezone channels should update (in minutes).

        Example: !timezone interval 10
        """
        if minutes < 5:
            await ctx.send("⚠️ Update interval cannot be less than 5 minutes to avoid rate limits.")
            minutes = 5

        self.update_channels.change_interval(minutes=minutes)
        self.update_interval = minutes
        await ctx.send(f"✅ Timezone channels will now update every {minutes} minutes.")


async def setup(bot):
    await bot.add_cog(TimezoneChannels(bot))
