import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import random
import math


class DeathrollManager:
    def __init__(self, bot):
        self.bot = bot
        self.data_file = "./databases/deathroll_data.json"
        self.authorized_roles = {}  # guild_id -> [role_ids]
        self.active_signups = {}  # guild_id -> signup_data
        self.active_tournaments = {}  # guild_id -> tournament_data
        self.load_data()

    def load_data(self):
        """Load persistent data from file"""
        try:
            os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r') as f:
                    data = json.load(f)
                    self.authorized_roles = data.get('authorized_roles', {})
                    # Don't load active signups/tournaments as they should reset on restart
        except Exception as e:
            print(f"Error loading deathroll data: {e}")

    def save_data(self):
        """Save persistent data to file"""
        try:
            data = {
                'authorized_roles': self.authorized_roles
            }
            with open(self.data_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving deathroll data: {e}")

    def has_permission(self, member: discord.Member) -> bool:
        """Check if member has permission to manage deathrolls"""
        # Administrators always have permission
        if member.guild_permissions.administrator:
            return True

        # Check authorized roles
        guild_id = str(member.guild.id)
        if guild_id in self.authorized_roles:
            member_role_ids = [role.id for role in member.roles]
            authorized_role_ids = self.authorized_roles[guild_id]
            return any(role_id in member_role_ids for role_id in authorized_role_ids)

        return False

    def create_bracket(self, participants: List[str]) -> List[List[Tuple[str, str]]]:
        """Create a tournament bracket from participants"""
        # Shuffle participants for random seeding
        shuffled = participants.copy()
        random.shuffle(shuffled)

        # Calculate next power of 2 to determine bracket size
        bracket_size = 2 ** math.ceil(math.log2(len(shuffled)))

        # Add byes if needed
        while len(shuffled) < bracket_size:
            shuffled.append("BYE")

        # Create bracket rounds
        bracket = []
        current_round = []

        # First round
        for i in range(0, len(shuffled), 2):
            current_round.append((shuffled[i], shuffled[i + 1]))
        bracket.append(current_round)

        # Subsequent rounds
        while len(current_round) > 1:
            next_round = []
            for i in range(0, len(current_round), 2):
                next_round.append(("TBD", "TBD"))
            bracket.append(next_round)
            current_round = next_round

        return bracket


class SignupView(discord.ui.View):
    def __init__(self, manager: DeathrollManager, guild_id: int):
        super().__init__(timeout=None)
        self.manager = manager
        self.guild_id = guild_id

    @discord.ui.button(label="Join Deathroll", style=discord.ButtonStyle.primary, emoji="⚔️")
    async def join_deathroll(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = str(self.guild_id)

        if guild_id not in self.manager.active_signups:
            await interaction.response.send_message("❌ No active deathroll signup found.", ephemeral=True)
            return

        signup_data = self.manager.active_signups[guild_id]

        # Check if signups are still open
        if datetime.now() > datetime.fromisoformat(signup_data['end_time']):
            await interaction.response.send_message("❌ Signups have closed for this deathroll.", ephemeral=True)
            return

        user_id = str(interaction.user.id)

        # Check if already signed up
        if user_id in signup_data['participants']:
            await interaction.response.send_message("❌ You're already signed up for this deathroll!", ephemeral=True)
            return

        # Add participant
        signup_data['participants'][user_id] = {
            'username': interaction.user.display_name,
            'joined_at': datetime.now().isoformat()
        }

        await interaction.response.send_message("✅ You've been added to the deathroll signup!", ephemeral=True)

        # Update the signup embed
        await self.update_signup_embed(interaction.guild)

    async def update_signup_embed(self, guild: discord.Guild):
        """Update the signup embed with current participants"""
        guild_id = str(guild.id)
        if guild_id not in self.manager.active_signups:
            return

        signup_data = self.manager.active_signups[guild_id]

        # Get the signup channel and message
        try:
            signup_channel = guild.get_channel(signup_data['signup_channel_id'])
            if not signup_channel:
                return

            signup_message = await signup_channel.fetch_message(signup_data['signup_message_id'])

            # Update signup embed
            embed = discord.Embed(
                title="⚔️ FFXIV Deathroll Signup",
                description=f"Click the button below to join the deathroll!\n\n**Signups close:** <t:{int(datetime.fromisoformat(signup_data['end_time']).timestamp())}:R>",
                color=discord.Color.red()
            )
            embed.add_field(
                name="Participants",
                value=f"{len(signup_data['participants'])} warriors ready to roll!",
                inline=False
            )

            await signup_message.edit(embed=embed, view=self)

            # Update the tracking channel
            if signup_data.get('tracking_channel_id'):
                await self.update_tracking_embed(guild)

        except Exception as e:
            print(f"Error updating signup embed: {e}")

    async def update_tracking_embed(self, guild: discord.Guild):
        """Update the tracking embed with participant list"""
        guild_id = str(guild.id)
        if guild_id not in self.manager.active_signups:
            return

        signup_data = self.manager.active_signups[guild_id]

        try:
            tracking_channel = guild.get_channel(signup_data['tracking_channel_id'])
            if not tracking_channel:
                return

            tracking_message = await tracking_channel.fetch_message(signup_data['tracking_message_id'])

            # Create participant list
            participants = list(signup_data['participants'].values())
            if participants:
                participant_list = "\n".join([f"• {p['username']}" for p in participants])
                if len(participant_list) > 1000:  # Discord embed field limit
                    participant_list = participant_list[:997] + "..."
            else:
                participant_list = "*No participants yet*"

            embed = discord.Embed(
                title="⚔️ Deathroll Participants",
                color=discord.Color.gold()
            )
            embed.add_field(
                name=f"Warriors ({len(participants)})",
                value=participant_list,
                inline=False
            )
            embed.add_field(
                name="Signup Status",
                value=f"Closes <t:{int(datetime.fromisoformat(signup_data['end_time']).timestamp())}:R>",
                inline=False
            )

            await tracking_message.edit(embed=embed)

        except Exception as e:
            print(f"Error updating tracking embed: {e}")


class BracketView(discord.ui.View):
    def __init__(self, manager: DeathrollManager, guild_id: int):
        super().__init__(timeout=None)
        self.manager = manager
        self.guild_id = guild_id

    @discord.ui.button(label="Update Match", style=discord.ButtonStyle.secondary, emoji="🏆")
    async def update_match(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check permissions
        if not self.manager.has_permission(interaction.user):
            await interaction.response.send_message("❌ You don't have permission to update matches.", ephemeral=True)
            return

        guild_id = str(self.guild_id)
        if guild_id not in self.manager.active_tournaments:
            await interaction.response.send_message("❌ No active tournament found.", ephemeral=True)
            return

        # Show match update modal
        modal = MatchUpdateModal(self.manager, guild_id)
        await interaction.response.send_modal(modal)


class MatchUpdateModal(discord.ui.Modal):
    def __init__(self, manager: DeathrollManager, guild_id: str):
        super().__init__(title="Update Match Result")
        self.manager = manager
        self.guild_id = guild_id

        self.round_input = discord.ui.TextInput(
            label="Round Number",
            placeholder="Enter round number (1, 2, 3, etc.)",
            max_length=2
        )

        self.match_input = discord.ui.TextInput(
            label="Match Number",
            placeholder="Enter match number in that round",
            max_length=2
        )

        self.winner_input = discord.ui.TextInput(
            label="Winner Name",
            placeholder="Enter the exact name of the winner",
            max_length=100
        )

        self.add_item(self.round_input)
        self.add_item(self.match_input)
        self.add_item(self.winner_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            round_num = int(self.round_input.value) - 1  # Convert to 0-based index
            match_num = int(self.match_input.value) - 1  # Convert to 0-based index
            winner_name = self.winner_input.value.strip()

            tournament_data = self.manager.active_tournaments[self.guild_id]
            bracket = tournament_data['bracket']

            # Validate round and match numbers
            if round_num < 0 or round_num >= len(bracket):
                await interaction.response.send_message(f"❌ Invalid round number. Must be between 1 and {len(bracket)}",
                                                        ephemeral=True)
                return

            if match_num < 0 or match_num >= len(bracket[round_num]):
                await interaction.response.send_message(
                    f"❌ Invalid match number. Must be between 1 and {len(bracket[round_num])}", ephemeral=True)
                return

            current_match = bracket[round_num][match_num]

            # Check if winner is valid
            if winner_name not in [current_match[0], current_match[1]]:
                await interaction.response.send_message(
                    f"❌ Winner must be either '{current_match[0]}' or '{current_match[1]}'", ephemeral=True)
                return

            # Update the bracket
            if round_num + 1 < len(bracket):  # Not the final
                next_round = bracket[round_num + 1]
                next_match_index = match_num // 2
                next_position = match_num % 2

                if next_position == 0:
                    next_round[next_match_index] = (winner_name, next_round[next_match_index][1])
                else:
                    next_round[next_match_index] = (next_round[next_match_index][0], winner_name)

            # Save the updated bracket
            tournament_data['bracket'] = bracket

            await interaction.response.send_message(f"✅ Match updated! {winner_name} advances to the next round.",
                                                    ephemeral=True)

            # Update the bracket display
            await self.update_bracket_display(interaction.guild)

        except ValueError:
            await interaction.response.send_message("❌ Round and match numbers must be valid integers.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error updating match: {str(e)}", ephemeral=True)

    async def update_bracket_display(self, guild: discord.Guild):
        """Update the bracket display embed"""
        tournament_data = self.manager.active_tournaments[self.guild_id]

        try:
            channel = guild.get_channel(tournament_data['bracket_channel_id'])
            if not channel:
                return

            message = await channel.fetch_message(tournament_data['bracket_message_id'])

            # Create bracket embed
            embed = discord.Embed(
                title="⚔️ FFXIV Deathroll Tournament Bracket",
                color=discord.Color.red()
            )

            bracket = tournament_data['bracket']
            for round_idx, round_matches in enumerate(bracket):
                round_name = f"Round {round_idx + 1}"
                if round_idx == len(bracket) - 1:
                    round_name = "Final"
                elif round_idx == len(bracket) - 2:
                    round_name = "Semi-Final"

                matches_text = []
                for match_idx, (p1, p2) in enumerate(round_matches):
                    if p1 == "BYE":
                        matches_text.append(f"{match_idx + 1}. {p2} (bye)")
                    elif p2 == "BYE":
                        matches_text.append(f"{match_idx + 1}. {p1} (bye)")
                    else:
                        matches_text.append(f"{match_idx + 1}. {p1} vs {p2}")

                embed.add_field(
                    name=round_name,
                    value="\n".join(matches_text) if matches_text else "TBD",
                    inline=True
                )

            # Check if tournament is complete
            final_match = bracket[-1][0]
            if final_match[0] != "TBD" and final_match[1] == "TBD":
                embed.add_field(
                    name="🏆 CHAMPION",
                    value=f"**{final_match[0]}**",
                    inline=False
                )
                embed.color = discord.Color.gold()

            view = BracketView(self.manager, int(self.guild_id))
            await message.edit(embed=embed, view=view)

        except Exception as e:
            print(f"Error updating bracket display: {e}")


class Deathroll(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.manager = DeathrollManager(bot)

        # Add persistent views
        self.bot.add_view(SignupView(self.manager, 0))  # Guild ID will be set when needed
        self.bot.add_view(BracketView(self.manager, 0))  # Guild ID will be set when needed

    @app_commands.command(name="deathroll_permissions", description="Manage deathroll command permissions")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        action="Add or remove role permissions",
        role="The role to add/remove permissions for"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Add Role", value="add"),
        app_commands.Choice(name="Remove Role", value="remove"),
        app_commands.Choice(name="List Roles", value="list")
    ])
    async def deathroll_permissions(self, interaction: discord.Interaction, action: str, role: discord.Role = None):
        # Check if user has administrator permissions
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ You need Administrator permissions to manage deathroll permissions.", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)

        if action == "add":
            if not role:
                await interaction.response.send_message("❌ You must specify a role to add.", ephemeral=True)
                return

            if guild_id not in self.manager.authorized_roles:
                self.manager.authorized_roles[guild_id] = []

            if role.id not in self.manager.authorized_roles[guild_id]:
                self.manager.authorized_roles[guild_id].append(role.id)
                self.manager.save_data()
                await interaction.response.send_message(f"✅ Added {role.mention} to deathroll managers.",
                                                        ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ {role.mention} already has deathroll permissions.",
                                                        ephemeral=True)

        elif action == "remove":
            if not role:
                await interaction.response.send_message("❌ You must specify a role to remove.", ephemeral=True)
                return

            if guild_id in self.manager.authorized_roles and role.id in self.manager.authorized_roles[guild_id]:
                self.manager.authorized_roles[guild_id].remove(role.id)
                self.manager.save_data()
                await interaction.response.send_message(f"✅ Removed {role.mention} from deathroll managers.",
                                                        ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ {role.mention} doesn't have deathroll permissions.",
                                                        ephemeral=True)

        elif action == "list":
            if guild_id not in self.manager.authorized_roles or not self.manager.authorized_roles[guild_id]:
                await interaction.response.send_message(
                    "❌ No roles have deathroll permissions. Only administrators can manage deathrolls.", ephemeral=True)
                return

            role_mentions = []
            for role_id in self.manager.authorized_roles[guild_id]:
                role_obj = interaction.guild.get_role(role_id)
                if role_obj:
                    role_mentions.append(role_obj.mention)

            if role_mentions:
                embed = discord.Embed(
                    title="⚔️ Deathroll Managers",
                    description="\n".join(role_mentions),
                    color=discord.Color.blue()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message("❌ No valid roles found with deathroll permissions.",
                                                        ephemeral=True)

    @app_commands.command(name="start_deathroll_signup", description="Start a new deathroll signup")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        signup_channel="Channel where the signup button will be posted",
        tracking_channel="Channel where participant names will be tracked",
        duration_minutes="How long signups will be open (in minutes)"
    )
    async def start_deathroll_signup(self, interaction: discord.Interaction,
                                     signup_channel: discord.TextChannel,
                                     tracking_channel: discord.TextChannel,
                                     duration_minutes: int):
        # Check permissions
        if not self.manager.has_permission(interaction.user):
            await interaction.response.send_message("❌ You don't have permission to start deathroll signups.",
                                                    ephemeral=True)
            return

        if duration_minutes < 1 or duration_minutes > 1440:  # Max 24 hours
            await interaction.response.send_message("❌ Duration must be between 1 and 1440 minutes (24 hours).",
                                                    ephemeral=True)
            return

        guild_id = str(interaction.guild.id)

        # Check if there's already an active signup
        if guild_id in self.manager.active_signups:
            await interaction.response.send_message("❌ There's already an active deathroll signup in this server.",
                                                    ephemeral=True)
            return

        # Calculate end time
        end_time = datetime.now() + timedelta(minutes=duration_minutes)

        # Create signup embed
        embed = discord.Embed(
            title="⚔️ FFXIV Deathroll Signup",
            description=f"Click the button below to join the deathroll!\n\n**Signups close:** <t:{int(end_time.timestamp())}:R>",
            color=discord.Color.red()
        )
        embed.add_field(
            name="Participants",
            value="0 warriors ready to roll!",
            inline=False
        )

        # Create view
        view = SignupView(self.manager, interaction.guild.id)

        # Send signup message
        signup_message = await signup_channel.send(embed=embed, view=view)

        # Create tracking embed
        tracking_embed = discord.Embed(
            title="⚔️ Deathroll Participants",
            color=discord.Color.gold()
        )
        tracking_embed.add_field(
            name="Warriors (0)",
            value="*No participants yet*",
            inline=False
        )
        tracking_embed.add_field(
            name="Signup Status",
            value=f"Closes <t:{int(end_time.timestamp())}:R>",
            inline=False
        )

        tracking_message = await tracking_channel.send(embed=tracking_embed)

        # Store signup data
        self.manager.active_signups[guild_id] = {
            'signup_channel_id': signup_channel.id,
            'signup_message_id': signup_message.id,
            'tracking_channel_id': tracking_channel.id,
            'tracking_message_id': tracking_message.id,
            'end_time': end_time.isoformat(),
            'participants': {},
            'created_by': interaction.user.id
        }

        await interaction.response.send_message(
            f"✅ Deathroll signup started! Signups will close <t:{int(end_time.timestamp())}:R>", ephemeral=True)

        # Schedule automatic closure
        await self.schedule_signup_closure(guild_id, duration_minutes * 60)

    async def schedule_signup_closure(self, guild_id: str, delay_seconds: int):
        """Schedule automatic signup closure"""
        await asyncio.sleep(delay_seconds)

        if guild_id in self.manager.active_signups:
            guild = self.bot.get_guild(int(guild_id))
            if guild:
                await self.close_signups_and_create_bracket(guild, guild_id)

    @app_commands.command(name="close_deathroll_signup",
                          description="Manually close deathroll signups and create bracket")
    @app_commands.default_permissions(administrator=True)
    async def close_deathroll_signup(self, interaction: discord.Interaction):
        # Check permissions
        if not self.manager.has_permission(interaction.user):
            await interaction.response.send_message("❌ You don't have permission to close deathroll signups.",
                                                    ephemeral=True)
            return

        guild_id = str(interaction.guild.id)

        if guild_id not in self.manager.active_signups:
            await interaction.response.send_message("❌ No active deathroll signup found.", ephemeral=True)
            return

        await interaction.response.defer()
        await self.close_signups_and_create_bracket(interaction.guild, guild_id)
        await interaction.followup.send("✅ Deathroll signups closed and bracket created!")

    async def close_signups_and_create_bracket(self, guild: discord.Guild, guild_id: str):
        """Close signups and create tournament bracket"""
        if guild_id not in self.manager.active_signups:
            return

        signup_data = self.manager.active_signups[guild_id]
        participants = list(signup_data['participants'].values())

        if len(participants) < 2:
            # Not enough participants
            try:
                signup_channel = guild.get_channel(signup_data['signup_channel_id'])
                if signup_channel:
                    embed = discord.Embed(
                        title="⚔️ Deathroll Cancelled",
                        description="Not enough participants to start the tournament. Need at least 2 warriors!",
                        color=discord.Color.orange()
                    )
                    await signup_channel.send(embed=embed)
            except Exception as e:
                print(f"Error sending cancellation message: {e}")

            # Clean up
            del self.manager.active_signups[guild_id]
            return

        # Create bracket
        participant_names = [p['username'] for p in participants]
        bracket = self.manager.create_bracket(participant_names)

        # Create bracket embed
        embed = discord.Embed(
            title="⚔️ FFXIV Deathroll Tournament Bracket",
            description=f"Tournament started with {len(participants)} participants!",
            color=discord.Color.red()
        )

        for round_idx, round_matches in enumerate(bracket):
            round_name = f"Round {round_idx + 1}"
            if round_idx == len(bracket) - 1:
                round_name = "Final"
            elif round_idx == len(bracket) - 2:
                round_name = "Semi-Final"

            matches_text = []
            for match_idx, (p1, p2) in enumerate(round_matches):
                if p1 == "BYE":
                    matches_text.append(f"{match_idx + 1}. {p2} (bye)")
                elif p2 == "BYE":
                    matches_text.append(f"{match_idx + 1}. {p1} (bye)")
                else:
                    matches_text.append(f"{match_idx + 1}. {p1} vs {p2}")

            embed.add_field(
                name=round_name,
                value="\n".join(matches_text) if matches_text else "TBD",
                inline=True
            )

        # Send bracket to tracking channel
        try:
            tracking_channel = guild.get_channel(signup_data['tracking_channel_id'])
            if tracking_channel:
                view = BracketView(self.manager, guild.id)
                bracket_message = await tracking_channel.send(embed=embed, view=view)

                # Store tournament data
                self.manager.active_tournaments[guild_id] = {
                    'bracket': bracket,
                    'bracket_channel_id': tracking_channel.id,
                    'bracket_message_id': bracket_message.id,
                    'participants': participant_names,
                    'created_at': datetime.now().isoformat()
                }
        except Exception as e:
            print(f"Error creating bracket: {e}")

        # Update signup message to show it's closed
        try:
            signup_channel = guild.get_channel(signup_data['signup_channel_id'])
            if signup_channel:
                signup_message = await signup_channel.fetch_message(signup_data['signup_message_id'])

                closed_embed = discord.Embed(
                    title="⚔️ FFXIV Deathroll Signup - CLOSED",
                    description="Signups are now closed. The tournament bracket has been created!",
                    color=discord.Color.orange()
                )
                closed_embed.add_field(
                    name="Final Participants",
                    value=f"{len(participants)} warriors entered the arena!",
                    inline=False
                )

                # Remove the button
                await signup_message.edit(embed=closed_embed, view=None)
        except Exception as e:
            print(f"Error updating signup message: {e}")

        # Clean up signup data
        del self.manager.active_signups[guild_id]

    @app_commands.command(name="cancel_deathroll", description="Cancel an active deathroll signup or tournament")
    @app_commands.default_permissions(administrator=True)
    async def cancel_deathroll(self, interaction: discord.Interaction):
        # Check permissions
        if not self.manager.has_permission(interaction.user):
            await interaction.response.send_message("❌ You don't have permission to cancel deathrolls.", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)

        # Check for active signup
        if guild_id in self.manager.active_signups:
            del self.manager.active_signups[guild_id]
            await interaction.response.send_message("✅ Active deathroll signup has been cancelled.", ephemeral=True)
            return

        # Check for active tournament
        if guild_id in self.manager.active_tournaments:
            del self.manager.active_tournaments[guild_id]
            await interaction.response.send_message("✅ Active deathroll tournament has been cancelled.", ephemeral=True)
            return

        await interaction.response.send_message("❌ No active deathroll signup or tournament found.", ephemeral=True)

    @app_commands.command(name="deathroll_status", description="Check the status of deathroll activities")
    async def deathroll_status(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)

        embed = discord.Embed(
            title="⚔️ Deathroll Status",
            color=discord.Color.blue()
        )

        # Check active signup
        if guild_id in self.manager.active_signups:
            signup_data = self.manager.active_signups[guild_id]
            end_time = datetime.fromisoformat(signup_data['end_time'])
            participant_count = len(signup_data['participants'])

            embed.add_field(
                name="📝 Active Signup",
                value=f"**Participants:** {participant_count}\n**Closes:** <t:{int(end_time.timestamp())}:R>",
                inline=False
            )

        # Check active tournament
        if guild_id in self.manager.active_tournaments:
            tournament_data = self.manager.active_tournaments[guild_id]
            participant_count = len(tournament_data['participants'])

            # Count completed matches
            bracket = tournament_data['bracket']
            total_matches = sum(len(round_matches) for round_matches in bracket)
            completed_matches = 0

            for round_matches in bracket[:-1]:  # Exclude final round for counting
                for match in round_matches:
                    if match[0] != "TBD" and match[1] != "TBD":
                        completed_matches += 1

            # Check if tournament is complete
            final_match = bracket[-1][0]
            tournament_complete = final_match[0] != "TBD" and final_match[1] == "TBD"

            if tournament_complete:
                embed.add_field(
                    name="🏆 Tournament Complete",
                    value=f"**Champion:** {final_match[0]}\n**Participants:** {participant_count}",
                    inline=False
                )
            else:
                embed.add_field(
                    name="⚔️ Active Tournament",
                    value=f"**Participants:** {participant_count}\n**Rounds:** {len(bracket)}\n**Status:** In Progress",
                    inline=False
                )

        # If nothing is active
        if guild_id not in self.manager.active_signups and guild_id not in self.manager.active_tournaments:
            embed.add_field(
                name="Status",
                value="No active deathroll activities",
                inline=False
            )

        # Show authorized roles
        if guild_id in self.manager.authorized_roles and self.manager.authorized_roles[guild_id]:
            role_mentions = []
            for role_id in self.manager.authorized_roles[guild_id]:
                role_obj = interaction.guild.get_role(role_id)
                if role_obj:
                    role_mentions.append(role_obj.mention)

            if role_mentions:
                embed.add_field(
                    name="🛡️ Authorized Managers",
                    value=", ".join(role_mentions),
                    inline=False
                )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="reset_deathroll_bracket", description="Reset the current tournament bracket")
    @app_commands.default_permissions(administrator=True)
    async def reset_deathroll_bracket(self, interaction: discord.Interaction):
        # Check permissions
        if not self.manager.has_permission(interaction.user):
            await interaction.response.send_message("❌ You don't have permission to reset tournament brackets.",
                                                    ephemeral=True)
            return

        guild_id = str(interaction.guild.id)

        if guild_id not in self.manager.active_tournaments:
            await interaction.response.send_message("❌ No active tournament found.", ephemeral=True)
            return

        tournament_data = self.manager.active_tournaments[guild_id]
        participants = tournament_data['participants']

        # Recreate bracket with same participants
        new_bracket = self.manager.create_bracket(participants)
        tournament_data['bracket'] = new_bracket

        # Update the bracket display
        try:
            channel = interaction.guild.get_channel(tournament_data['bracket_channel_id'])
            if channel:
                message = await channel.fetch_message(tournament_data['bracket_message_id'])

                # Create new bracket embed
                embed = discord.Embed(
                    title="⚔️ FFXIV Deathroll Tournament Bracket (RESET)",
                    description=f"Tournament bracket has been reset with {len(participants)} participants!",
                    color=discord.Color.red()
                )

                for round_idx, round_matches in enumerate(new_bracket):
                    round_name = f"Round {round_idx + 1}"
                    if round_idx == len(new_bracket) - 1:
                        round_name = "Final"
                    elif round_idx == len(new_bracket) - 2:
                        round_name = "Semi-Final"

                    matches_text = []
                    for match_idx, (p1, p2) in enumerate(round_matches):
                        if p1 == "BYE":
                            matches_text.append(f"{match_idx + 1}. {p2} (bye)")
                        elif p2 == "BYE":
                            matches_text.append(f"{match_idx + 1}. {p1} (bye)")
                        else:
                            matches_text.append(f"{match_idx + 1}. {p1} vs {p2}")

                    embed.add_field(
                        name=round_name,
                        value="\n".join(matches_text) if matches_text else "TBD",
                        inline=True
                    )

                view = BracketView(self.manager, interaction.guild.id)
                await message.edit(embed=embed, view=view)

                await interaction.response.send_message("✅ Tournament bracket has been reset with new matchups!",
                                                        ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(f"❌ Error resetting bracket: {str(e)}", ephemeral=True)

    @app_commands.command(name="advance_player", description="Manually advance a player to the next round")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        round_number="The round number (1, 2, 3, etc.)",
        match_number="The match number in that round",
        winner="The name of the winner"
    )
    async def advance_player(self, interaction: discord.Interaction, round_number: int, match_number: int, winner: str):
        # Check permissions
        if not self.manager.has_permission(interaction.user):
            await interaction.response.send_message("❌ You don't have permission to advance players.", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)

        if guild_id not in self.manager.active_tournaments:
            await interaction.response.send_message("❌ No active tournament found.", ephemeral=True)
            return

        tournament_data = self.manager.active_tournaments[guild_id]
        bracket = tournament_data['bracket']

        # Convert to 0-based indices
        round_idx = round_number - 1
        match_idx = match_number - 1

        # Validate inputs
        if round_idx < 0 or round_idx >= len(bracket):
            await interaction.response.send_message(f"❌ Invalid round number. Must be between 1 and {len(bracket)}",
                                                    ephemeral=True)
            return

        if match_idx < 0 or match_idx >= len(bracket[round_idx]):
            await interaction.response.send_message(
                f"❌ Invalid match number. Must be between 1 and {len(bracket[round_idx])}", ephemeral=True)
            return

        current_match = bracket[round_idx][match_idx]

        # Check if winner is valid
        if winner not in [current_match[0], current_match[1]]:
            await interaction.response.send_message(
                f"❌ Winner must be either '{current_match[0]}' or '{current_match[1]}'", ephemeral=True)
            return

        # Handle BYE advancement
        if current_match[0] == "BYE":
            winner = current_match[1]
        elif current_match[1] == "BYE":
            winner = current_match[0]

        # Update the bracket
        if round_idx + 1 < len(bracket):  # Not the final
            next_round = bracket[round_idx + 1]
            next_match_index = match_idx // 2
            next_position = match_idx % 2

            if next_position == 0:
                next_round[next_match_index] = (winner, next_round[next_match_index][1])
            else:
                next_round[next_match_index] = (next_round[next_match_index][0], winner)

        # Save the updated bracket
        tournament_data['bracket'] = bracket

        # Update the bracket display
        try:
            channel = interaction.guild.get_channel(tournament_data['bracket_channel_id'])
            if channel:
                message = await channel.fetch_message(tournament_data['bracket_message_id'])

                # Create updated bracket embed
                embed = discord.Embed(
                    title="⚔️ FFXIV Deathroll Tournament Bracket",
                    color=discord.Color.red()
                )

                for r_idx, round_matches in enumerate(bracket):
                    round_name = f"Round {r_idx + 1}"
                    if r_idx == len(bracket) - 1:
                        round_name = "Final"
                    elif r_idx == len(bracket) - 2:
                        round_name = "Semi-Final"

                    matches_text = []
                    for m_idx, (p1, p2) in enumerate(round_matches):
                        if p1 == "BYE":
                            matches_text.append(f"{m_idx + 1}. {p2} (bye)")
                        elif p2 == "BYE":
                            matches_text.append(f"{m_idx + 1}. {p1} (bye)")
                        else:
                            matches_text.append(f"{m_idx + 1}. {p1} vs {p2}")

                    embed.add_field(
                        name=round_name,
                        value="\n".join(matches_text) if matches_text else "TBD",
                        inline=True
                    )

                # Check if tournament is complete
                final_match = bracket[-1][0]
                if final_match[0] != "TBD" and final_match[1] == "TBD":
                    embed.add_field(
                        name="🏆 CHAMPION",
                        value=f"**{final_match[0]}**",
                        inline=False
                    )
                    embed.color = discord.Color.gold()

                view = BracketView(self.manager, interaction.guild.id)
                await message.edit(embed=embed, view=view)

        except Exception as e:
            print(f"Error updating bracket display: {e}")

        await interaction.response.send_message(f"✅ {winner} has been advanced to the next round!", ephemeral=True)

    @commands.Cog.listener()
    async def on_ready(self):
        """Set up persistent views when the bot is ready"""
        print("Deathroll cog loaded - Setting up persistent views...")

        # The views are already added in __init__, but we can do additional setup here if needed
        for guild_id in list(self.manager.active_signups.keys()):
            try:
                guild = self.bot.get_guild(int(guild_id))
                if guild:
                    # Re-add views for active signups
                    view = SignupView(self.manager, int(guild_id))
                    self.bot.add_view(view)
            except Exception as e:
                print(f"Error setting up signup view for guild {guild_id}: {e}")

        for guild_id in list(self.manager.active_tournaments.keys()):
            try:
                guild = self.bot.get_guild(int(guild_id))
                if guild:
                    # Re-add views for active tournaments
                    view = BracketView(self.manager, int(guild_id))
                    self.bot.add_view(view)
            except Exception as e:
                print(f"Error setting up bracket view for guild {guild_id}: {e}")


async def setup(bot):
    await bot.add_cog(Deathroll(bot))


