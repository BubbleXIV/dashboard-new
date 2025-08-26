import discord
import json
import asyncio
import random
import os
import pytz
from datetime import datetime, timedelta
from discord.ext import commands, tasks
from discord import app_commands
from typing import Dict, List, Optional, Union


class GiveawayView(discord.ui.View):
    def __init__(self, giveaway_id: str):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id

        # Add the enter/leave button
        self.add_item(GiveawayButton(giveaway_id))


class GiveawayButton(discord.ui.Button):
    def __init__(self, giveaway_id: str):
        super().__init__(
            style=discord.ButtonStyle.primary,
            label="Enter Giveaway",
            custom_id=f"giveaway:{giveaway_id}"
        )
        self.giveaway_id = giveaway_id

    async def callback(self, interaction: discord.Interaction):
        # Get the giveaway cog
        giveaway_cog = interaction.client.get_cog("Giveaway")
        if not giveaway_cog:
            await interaction.response.send_message("Giveaway system is currently unavailable.", ephemeral=True)
            return

        # Toggle the user's entry
        await giveaway_cog.toggle_entry(interaction, self.giveaway_id)


class Giveaway(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.giveaways = {}
        self.giveaway_file = "./databases/giveaways.json"
        self.load_giveaways()
        self.check_giveaways.start()

    def cog_unload(self):
        self.check_giveaways.cancel()

    def load_giveaways(self):
        """Load giveaways from file"""
        os.makedirs(os.path.dirname(self.giveaway_file), exist_ok=True)
        try:
            if os.path.exists(self.giveaway_file):
                with open(self.giveaway_file, 'r') as f:
                    self.giveaways = json.load(f)
                print(f"Loaded {len(self.giveaways)} giveaways from file")
        except Exception as e:
            print(f"Error loading giveaways: {e}")
            self.giveaways = {}

    def save_giveaways(self):
        """Save giveaways to file"""
        try:
            with open(self.giveaway_file, 'w') as f:
                json.dump(self.giveaways, f, indent=4)
        except Exception as e:
            print(f"Error saving giveaways: {e}")

    @tasks.loop(seconds=30)
    async def check_giveaways(self):
        """Check for ended giveaways and draw winners"""
        current_time = datetime.now(pytz.UTC).timestamp()  # Use UTC timezone
        ended_giveaways = []

        for giveaway_id, giveaway in self.giveaways.items():
            if giveaway["end_time"] <= current_time and not giveaway.get("ended", False):
                ended_giveaways.append(giveaway_id)

        for giveaway_id in ended_giveaways:
            await self.end_giveaway(giveaway_id)

    @check_giveaways.before_loop
    async def before_check_giveaways(self):
        await self.bot.wait_until_ready()

    async def setup_persistent_views(self):
        """Set up persistent views for all active giveaways"""
        for giveaway_id in self.giveaways:
            self.bot.add_view(GiveawayView(giveaway_id))
        print(f"Set up persistent views for {len(self.giveaways)} giveaways")

    async def create_giveaway_embed(self, giveaway_id: str) -> discord.Embed:
        """Create an embed for a giveaway"""
        giveaway = self.giveaways[giveaway_id]

        # Calculate time remaining
        end_time = giveaway["end_time"]
        current_time = datetime.now(pytz.UTC).timestamp()  # Use UTC timezone
        time_remaining = max(0, end_time - current_time)

        # Format time remaining
        if time_remaining > 0:
            days, remainder = divmod(time_remaining, 86400)
            hours, remainder = divmod(remainder, 3600)
            minutes, seconds = divmod(remainder, 60)
            time_str = ""
            if days > 0:
                time_str += f"{int(days)} days, "
            if hours > 0 or days > 0:
                time_str += f"{int(hours)} hours, "
            if minutes > 0 or hours > 0 or days > 0:
                time_str += f"{int(minutes)} minutes"
            else:
                time_str += f"{int(seconds)} seconds"
            footer_text = f"Ends in: {time_str} | Giveaway ID: {giveaway_id}"
        else:
            footer_text = f"Giveaway has ended | Giveaway ID: {giveaway_id}"

        # Create embed
        embed = discord.Embed(
            title=giveaway["title"],
            description=giveaway["description"],
            color=discord.Color.blue()
        )

        # Add prize field
        embed.add_field(
            name="Prize",
            value=giveaway["prize"],
            inline=False
        )

        # Add entries field
        entries_count = len(giveaway["entries"])
        embed.add_field(
            name="Entries",
            value=f"{entries_count} {'entry' if entries_count == 1 else 'entries'}",
            inline=True
        )

        # Add winners field
        embed.add_field(
            name="Winners",
            value=f"{giveaway['winner_count']} {'winner' if giveaway['winner_count'] == 1 else 'winners'}",
            inline=True
        )

        # Add host field
        host_id = giveaway["host_id"]
        embed.add_field(
            name="Hosted by",
            value=f"<@{host_id}>",
            inline=True
        )

        # Add local time field
        embed.add_field(
            name="End Time",
            value=f"<t:{int(end_time)}:F>",
            inline=False
        )

        # Add countdown field
        if time_remaining > 0:
            embed.add_field(
                name="Time Remaining",
                value=f"<t:{int(end_time)}:R>",
                inline=False
            )

        # Set footer with creation time
        created_time = giveaway.get("created_time", datetime.now(pytz.UTC).timestamp())
        embed.set_footer(text=f"Created: <t:{int(created_time)}:F> | Giveaway ID: {giveaway_id}")

        # Set timestamp to end time as UTC datetime
        end_time_dt = datetime.fromtimestamp(end_time, tz=pytz.UTC)
        embed.timestamp = end_time_dt

        return embed

    async def update_giveaway_message(self, giveaway_id: str):
        """Update the giveaway message with current information"""
        giveaway = self.giveaways[giveaway_id]

        try:
            channel_id = giveaway["channel_id"]
            message_id = giveaway["message_id"]

            channel = self.bot.get_channel(int(channel_id))
            if not channel:
                print(f"Channel {channel_id} not found for giveaway {giveaway_id}")
                return

            try:
                message = await channel.fetch_message(int(message_id))
                embed = await self.create_giveaway_embed(giveaway_id)

                # Only update the view if the giveaway is still active
                if not giveaway.get("ended", False):
                    await message.edit(embed=embed)
                else:
                    await message.edit(embed=embed, view=None)
            except discord.NotFound:
                print(f"Message {message_id} not found for giveaway {giveaway_id}")
            except Exception as e:
                print(f"Error updating giveaway message: {e}")
        except Exception as e:
            print(f"Error in update_giveaway_message: {e}")

    async def toggle_entry(self, interaction: discord.Interaction, giveaway_id: str):
        """Toggle a user's entry in a giveaway"""
        if giveaway_id not in self.giveaways:
            await interaction.response.send_message("This giveaway no longer exists.", ephemeral=True)
            return

        giveaway = self.giveaways[giveaway_id]
        user_id = str(interaction.user.id)

        # Check if giveaway has ended
        if giveaway.get("ended", False):
            await interaction.response.send_message("This giveaway has already ended.", ephemeral=True)
            return

        # Toggle entry
        if user_id in giveaway["entries"]:
            giveaway["entries"].remove(user_id)
            await interaction.response.send_message("You have withdrawn from the giveaway.", ephemeral=True)
        else:
            giveaway["entries"].append(user_id)
            await interaction.response.send_message("You have entered the giveaway! Good luck!", ephemeral=True)

        # Save and update
        self.save_giveaways()
        await self.update_giveaway_message(giveaway_id)

    async def end_giveaway(self, giveaway_id: str):
        """End a giveaway and select winners"""
        if giveaway_id not in self.giveaways:
            return

        giveaway = self.giveaways[giveaway_id]

        # Mark as ended
        giveaway["ended"] = True

        # Get channel and message
        channel_id = giveaway["channel_id"]
        channel = self.bot.get_channel(int(channel_id))

        if not channel:
            print(f"Channel {channel_id} not found for giveaway {giveaway_id}")
            return

        # Select winners
        entries = giveaway["entries"]
        winner_count = min(giveaway["winner_count"], len(entries))
        winners = []

        if entries and winner_count > 0:
            # Copy entries to avoid modifying the original list during selection
            entry_pool = entries.copy()

            for _ in range(winner_count):
                if not entry_pool:
                    break

                winner = random.choice(entry_pool)
                winners.append(winner)
                entry_pool.remove(winner)

        # Store winners
        giveaway["winners"] = winners

        # Update the giveaway message
        await self.update_giveaway_message(giveaway_id)

        # Send winner announcement
        if winners:
            winner_mentions = [f"<@{winner}>" for winner in winners]
            winners_text = ", ".join(winner_mentions)

            embed = discord.Embed(
                title="🎉 Giveaway Ended!",
                description=f"**{giveaway['title']}**\n\n**Prize:** {giveaway['prize']}\n\n**Winner{'s' if len(winners) > 1 else ''}:** {winners_text}",
                color=discord.Color.green()
            )

            await channel.send(
                content=f"Congratulations {winners_text}! You won the giveaway!",
                embed=embed
            )
        else:
            embed = discord.Embed(
                title="🎉 Giveaway Ended",
                description=f"**{giveaway['title']}**\n\nNo valid entries were found for this giveaway.",
                color=discord.Color.red()
            )

            await channel.send(embed=embed)

        # Save changes
        self.save_giveaways()

    @app_commands.command(name="giveaway", description="Create a new giveaway")
    @app_commands.describe(
        prize="The prize for the giveaway",
        winners="Number of winners (default: 1)",
        duration="Duration in minutes (default: 60)",
        title="Title for the giveaway (default: 'Giveaway!')",
        description="Description for the giveaway"
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def create_giveaway(
            self,
            interaction: discord.Interaction,
            prize: str,
            winners: int = 1,
            duration: int = 60,
            title: str = "Giveaway!",
            description: str = "React with the button below to enter!"
    ):
        """Create a new giveaway"""
        # Validate inputs
        if winners < 1:
            await interaction.response.send_message("Number of winners must be at least 1.", ephemeral=True)
            return
        if duration < 1:
            await interaction.response.send_message("Duration must be at least 1 minute.", ephemeral=True)
            return

        # Defer response since this might take a moment
        await interaction.response.defer(ephemeral=True)

        # Create giveaway data with proper UTC timestamps
        current_time = datetime.now(pytz.UTC)
        giveaway_id = f"{interaction.guild_id}-{int(current_time.timestamp())}"
        end_time = current_time + timedelta(minutes=duration)

        giveaway = {
            "title": title,
            "description": description,
            "prize": prize,
            "winner_count": winners,
            "host_id": str(interaction.user.id),
            "guild_id": str(interaction.guild_id),
            "channel_id": str(interaction.channel_id),
            "end_time": end_time.timestamp(),
            "created_time": current_time.timestamp(),
            "entries": [],
            "ended": False,
            "winners": []
        }

        # Create embed and view
        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Prize",
            value=prize,
            inline=False
        )
        embed.add_field(
            name="Entries",
            value="0 entries",
            inline=True
        )
        embed.add_field(
            name="Winners",
            value=f"{winners} {'winner' if winners == 1 else 'winners'}",
            inline=True
        )
        embed.add_field(
            name="Hosted by",
            value=f"<@{interaction.user.id}>",
            inline=True
        )
        embed.add_field(
            name="End Time",
            value=f"<t:{int(end_time.timestamp())}:F>",
            inline=False
        )
        embed.add_field(
            name="Time Remaining",
            value=f"<t:{int(end_time.timestamp())}:R>",
            inline=False
        )

        # Calculate time remaining for footer
        days, remainder = divmod(duration * 60, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        time_str = ""
        if days > 0:
            time_str += f"{int(days)} days, "
        if hours > 0 or days > 0:
            time_str += f"{int(hours)} hours, "
        time_str += f"{int(minutes)} minutes"

        embed.set_footer(text=f"Ends in: {time_str} | Giveaway ID: {giveaway_id}")
        embed.timestamp = end_time

        # Create view with button
        view = GiveawayView(giveaway_id)

        # Send the giveaway message
        giveaway_message = await interaction.channel.send(embed=embed, view=view)

        # Store message ID in giveaway data
        giveaway["message_id"] = str(giveaway_message.id)

        # Save giveaway
        self.giveaways[giveaway_id] = giveaway
        self.save_giveaways()

        # Register the view for persistence
        self.bot.add_view(view)

        # Confirm to the user
        await interaction.followup.send(f"Giveaway created successfully! It will end in {time_str}.", ephemeral=True)

    @app_commands.command(name="giveaway_end", description="End a giveaway early")
    @app_commands.describe(giveaway_id="The ID of the giveaway to end")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def end_giveaway_command(self, interaction: discord.Interaction, giveaway_id: str):
        """End a giveaway early"""
        # Check if the giveaway exists
        if giveaway_id not in self.giveaways:
            await interaction.response.send_message("Giveaway not found. Please check the ID and try again.",
                                                    ephemeral=True)
            return

        giveaway = self.giveaways[giveaway_id]

        # Check if user is the host or has manage messages permission
        is_host = str(interaction.user.id) == giveaway["host_id"]
        has_permission = interaction.channel.permissions_for(interaction.user).manage_messages

        if not (is_host or has_permission):
            await interaction.response.send_message("You don't have permission to end this giveaway.", ephemeral=True)
            return

        # Check if already ended
        if giveaway.get("ended", False):
            await interaction.response.send_message("This giveaway has already ended.", ephemeral=True)
            return

        # Defer response
        await interaction.response.defer(ephemeral=True)

        # End the giveaway
        await self.end_giveaway(giveaway_id)

        # Confirm to the user
        await interaction.followup.send("Giveaway ended successfully!", ephemeral=True)

    @app_commands.command(name="giveaway_reroll", description="Reroll a winner for a giveaway")
    @app_commands.describe(
        giveaway_id="The ID of the giveaway to reroll",
        winner_count="Number of winners to reroll (default: 1)"
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def reroll_giveaway(self, interaction: discord.Interaction, giveaway_id: str, winner_count: int = 1):
        """Reroll winners for a giveaway"""
        # Check if the giveaway exists
        if giveaway_id not in self.giveaways:
            await interaction.response.send_message("Giveaway not found. Please check the ID and try again.",
                                                    ephemeral=True)
            return

        giveaway = self.giveaways[giveaway_id]

        # Check if user is the host or has manage messages permission
        is_host = str(interaction.user.id) == giveaway["host_id"]
        has_permission = interaction.channel.permissions_for(interaction.user).manage_messages

        if not (is_host or has_permission):
            await interaction.response.send_message("You don't have permission to reroll this giveaway.",
                                                    ephemeral=True)
            return

        # Check if the giveaway has ended
        if not giveaway.get("ended", False):
            await interaction.response.send_message("This giveaway hasn't ended yet.", ephemeral=True)
            return

        # Validate winner count
        if winner_count < 1:
            await interaction.response.send_message("Number of winners must be at least 1.", ephemeral=True)
            return

        # Defer response
        await interaction.response.defer(ephemeral=True)

        # Get entries excluding previous winners
        entries = [entry for entry in giveaway["entries"] if entry not in giveaway.get("winners", [])]

        if not entries:
            await interaction.followup.send("No eligible entries found for reroll.", ephemeral=True)
            return

        # Select new winners
        new_winner_count = min(winner_count, len(entries))
        new_winners = random.sample(entries, new_winner_count)

        # Add to winners list
        giveaway["winners"].extend(new_winners)
        self.save_giveaways()

        # Send winner announcement
        if new_winners:
            winner_mentions = [f"<@{winner}>" for winner in new_winners]
            winners_text = ", ".join(winner_mentions)

            embed = discord.Embed(
                title="🎉 Giveaway Reroll!",
                description=f"**{giveaway['title']}**\n\n**Prize:** {giveaway['prize']}\n\n**New Winner{'s' if len(new_winners) > 1 else ''}:** {winners_text}",
                color=discord.Color.green()
            )

            await interaction.channel.send(
                content=f"Congratulations {winners_text}! You won the rerolled giveaway!",
                embed=embed
            )

            await interaction.followup.send(f"Successfully rerolled {new_winner_count} winner(s)!", ephemeral=True)
        else:
            await interaction.followup.send("No new winners were selected.", ephemeral=True)

    @app_commands.command(name="giveaway_list", description="List all active giveaways")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def list_giveaways(self, interaction: discord.Interaction):
        """List all active giveaways in the server"""
        guild_id = str(interaction.guild_id)

        # Filter giveaways for this guild that haven't ended
        active_giveaways = {
            gid: giveaway for gid, giveaway in self.giveaways.items()
            if giveaway["guild_id"] == guild_id and not giveaway.get("ended", False)
        }

        if not active_giveaways:
            await interaction.response.send_message("There are no active giveaways in this server.", ephemeral=True)
            return

        # Create embed
        embed = discord.Embed(
            title="Active Giveaways",
            description=f"There are {len(active_giveaways)} active giveaways in this server.",
            color=discord.Color.blue()
        )

        # Add fields for each giveaway
        for giveaway_id, giveaway in active_giveaways.items():
            # Calculate time remaining
            end_time = giveaway["end_time"]
            current_time = datetime.now(pytz.UTC).timestamp()  # Use UTC timezone
            time_remaining = max(0, end_time - current_time)

            days, remainder = divmod(time_remaining, 86400)
            hours, remainder = divmod(remainder, 3600)
            minutes, seconds = divmod(remainder, 60)

            time_str = ""
            if days > 0:
                time_str += f"{int(days)}d "
            if hours > 0 or days > 0:
                time_str += f"{int(hours)}h "
            time_str += f"{int(minutes)}m"

            # Create field
            channel = self.bot.get_channel(int(giveaway["channel_id"]))
            channel_name = channel.name if channel else "Unknown Channel"

            embed.add_field(
                name=f"{giveaway['title']} - {giveaway['prize']}",
                value=f"ID: `{giveaway_id}`\nChannel: {channel_name}\nEntries: {len(giveaway['entries'])}\nEnds in: {time_str}\n[Jump to Giveaway](https://discord.com/channels/{interaction.guild_id}/{giveaway['channel_id']}/{giveaway['message_id']})",
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="giveaway_info", description="Get information about a specific giveaway")
    @app_commands.describe(giveaway_id="The ID of the giveaway")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def giveaway_info(self, interaction: discord.Interaction, giveaway_id: str):
        """Get detailed information about a giveaway"""
        # Check if the giveaway exists
        if giveaway_id not in self.giveaways:
            await interaction.response.send_message("Giveaway not found. Please check the ID and try again.",
                                                    ephemeral=True)
            return

        giveaway = self.giveaways[giveaway_id]

        # Check if the giveaway is in this guild
        if giveaway["guild_id"] != str(interaction.guild_id):
            await interaction.response.send_message("Giveaway not found in this server.", ephemeral=True)
            return

        # Create embed
        embed = discord.Embed(
            title=f"Giveaway Info: {giveaway['title']}",
            description=giveaway['description'],
            color=discord.Color.blue()
        )

        # Add basic info
        embed.add_field(name="Prize", value=giveaway["prize"], inline=False)
        embed.add_field(name="Host", value=f"<@{giveaway['host_id']}>", inline=True)
        embed.add_field(name="Winners", value=str(giveaway["winner_count"]), inline=True)
        embed.add_field(name="Entries", value=str(len(giveaway["entries"])), inline=True)

        # Add status info
        if giveaway.get("ended", False):
            embed.add_field(name="Status", value="Ended", inline=True)

            # Add winners if any
            winners = giveaway.get("winners", [])
            if winners:
                winner_mentions = [f"<@{winner}>" for winner in winners]
                embed.add_field(
                    name="Winner(s)",
                    value=", ".join(winner_mentions),
                    inline=False
                )
            else:
                embed.add_field(name="Winner(s)", value="No winners", inline=False)
        else:
            # Calculate time remaining
            end_time = giveaway["end_time"]
            current_time = datetime.now(pytz.UTC).timestamp()  # Use UTC timezone
            time_remaining = max(0, end_time - current_time)

            days, remainder = divmod(time_remaining, 86400)
            hours, remainder = divmod(remainder, 3600)
            minutes, seconds = divmod(remainder, 60)

            time_str = ""
            if days > 0:
                time_str += f"{int(days)} days, "
            if hours > 0 or days > 0:
                time_str += f"{int(hours)} hours, "
            time_str += f"{int(minutes)} minutes"

            embed.add_field(name="Status", value=f"Active - Ends in {time_str}", inline=False)

        # Add link to giveaway
        embed.add_field(
            name="Link",
            value=f"[Jump to Giveaway](https://discord.com/channels/{interaction.guild_id}/{giveaway['channel_id']}/{giveaway['message_id']})",
            inline=False
        )

        # Set footer with ID
        embed.set_footer(text=f"Giveaway ID: {giveaway_id}")

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    giveaway_cog = Giveaway(bot)
    await bot.add_cog(giveaway_cog)
    # Set up persistent views for existing giveaways
    await giveaway_cog.setup_persistent_views()

