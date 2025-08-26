import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta
import sqlite3
import os
import asyncio
import logging
import asyncio
from io import BytesIO
from typing import List, Optional, Dict, Union

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('role_info')

# Define the path to the database directory
DATABASE_DIR = './databases/'
ACTIVITY_DB = os.path.join(DATABASE_DIR, 'activity.db')


class RoleInfo(commands.Cog):
    """Track user activity and manage roles based on activity levels"""

    def __init__(self, bot):
        self.bot = bot
        # Ensure the database directory exists
        os.makedirs(DATABASE_DIR, exist_ok=True)
        # Connect to the database
        self.db = sqlite3.connect(ACTIVITY_DB)
        self.cursor = self.db.cursor()
        # Create tables if they don't exist
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS activity (
                user_id INTEGER,
                guild_id INTEGER,
                last_message TEXT,
                last_reaction TEXT,
                last_voice TEXT,
                last_activity TEXT,
                PRIMARY KEY (user_id, guild_id)
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS inactivity_settings (
                guild_id INTEGER PRIMARY KEY,
                warning_days INTEGER DEFAULT 30,
                removal_days INTEGER DEFAULT 60,
                warning_role_id INTEGER,
                notification_channel_id INTEGER
            )
        ''')
        self.db.commit()
        # Check and update schema if needed
        self.check_and_update_schema()

    def get_inactivity_settings(self, guild_id: int) -> Dict:
        """Get inactivity settings for a guild"""
        self.cursor.execute('''
            SELECT warning_days, removal_days, warning_role_id, notification_channel_id
            FROM inactivity_settings
            WHERE guild_id = ?
        ''', (guild_id,))

        result = self.cursor.fetchone()
        if result:
            return {
                'warning_days': result[0],
                'removal_days': result[1],
                'warning_role_id': result[2],
                'notification_channel_id': result[3]
            }
        else:
            # Return default settings if none exist
            return {
                'warning_days': 30,
                'removal_days': 60,
                'warning_role_id': None,
                'notification_channel_id': None
            }

    def cog_unload(self):
        """Close the database connection when the cog is unloaded"""
        self.db.close()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Track user activity when they send a message"""
        # Skip if not in a guild or if the author is a bot
        if not message.guild or message.author.bot:
            return

        try:
            # Update the activity record
            self.cursor.execute('''
                INSERT OR REPLACE INTO activity 
                (user_id, guild_id, last_message, last_activity)
                VALUES (?, ?, ?, ?)
            ''', (
                message.author.id,
                message.guild.id,
                datetime.now().isoformat(),
                datetime.now().isoformat()
            ))
            self.db.commit()
        except Exception as e:
            logger.error(f"Error tracking message activity: {e}")

    def check_and_update_schema(self):
        """Check if the database schema is up to date and update it if needed"""
        try:
            # Check if the last_message column exists in the activity table
            self.cursor.execute("PRAGMA table_info(activity)")
            columns = [column[1] for column in self.cursor.fetchall()]

            # Add any missing columns
            if 'last_message' not in columns:
                self.cursor.execute('ALTER TABLE activity ADD COLUMN last_message TEXT')
                logger.info("Added missing column 'last_message' to activity table")
            if 'last_reaction' not in columns:
                self.cursor.execute('ALTER TABLE activity ADD COLUMN last_reaction TEXT')
                logger.info("Added missing column 'last_reaction' to activity table")
            if 'last_voice' not in columns:
                self.cursor.execute('ALTER TABLE activity ADD COLUMN last_voice TEXT')
                logger.info("Added missing column 'last_voice' to activity table")
            if 'last_activity' not in columns:
                self.cursor.execute('ALTER TABLE activity ADD COLUMN last_activity TEXT')
                logger.info("Added missing column 'last_activity' to activity table")

            self.db.commit()
        except Exception as e:
            logger.error(f"Error checking/updating database schema: {e}")

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        """Track user activity when they add a reaction"""
        # Skip if not in a guild or if the user is a bot
        if not reaction.message.guild or user.bot:
            return

        try:
            # Update the activity record
            self.cursor.execute('''
                INSERT INTO activity 
                (user_id, guild_id, last_reaction, last_activity)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, guild_id) DO UPDATE SET
                last_reaction = excluded.last_reaction,
                last_activity = excluded.last_activity
            ''', (
                user.id,
                reaction.message.guild.id,
                datetime.now().isoformat(),
                datetime.now().isoformat()
            ))
            self.db.commit()
        except Exception as e:
            logger.error(f"Error tracking reaction activity: {e}")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState,
                                    after: discord.VoiceState):
        """Track user activity when they join or leave a voice channel"""
        # Skip if the member is a bot
        if member.bot:
            return

        try:
            # Only track when joining a voice channel (not leaving)
            if after.channel and (not before.channel or before.channel != after.channel):
                self.cursor.execute('''
                    INSERT INTO activity 
                    (user_id, guild_id, last_voice, last_activity)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id, guild_id) DO UPDATE SET
                    last_voice = excluded.last_voice,
                    last_activity = excluded.last_activity
                ''', (
                    member.id,
                    member.guild.id,
                    datetime.now().isoformat(),
                    datetime.now().isoformat()
                ))
                self.db.commit()
        except Exception as e:
            logger.error(f"Error tracking voice activity: {e}")

    @app_commands.command(
        name="inactive_users",
        description="List all inactive users across the server"
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def inactive_users(self, interaction: discord.Interaction, days: Optional[int] = None):
        """
        List all users who have been inactive for a specified number of days
        Parameters:
        -----------
        days: Number of days of inactivity to check for (uses server settings if not specified)
        """
        await interaction.response.defer()

        try:
            # Import asyncio at the top of the file if not already imported
            import asyncio
            from io import BytesIO

            # Get inactivity settings for this guild
            settings = self.get_inactivity_settings(interaction.guild.id)

            # Use provided days or fall back to server settings
            if days is None:
                days = settings['warning_days']

            # Calculate the cutoff date
            cutoff_date = datetime.now() - timedelta(days=days)

            # Get all members in the guild
            all_members = interaction.guild.members

            # Get activity data for all members
            member_ids = [member.id for member in all_members if not member.bot]

            if not member_ids:
                await interaction.followup.send("No members found in this server.")
                return

            # Query activity data
            placeholders = ','.join(['?'] * len(member_ids))
            query = f'''
                SELECT user_id, last_activity 
                FROM activity 
                WHERE user_id IN ({placeholders}) AND guild_id = ?
            '''
            self.cursor.execute(query, member_ids + [interaction.guild.id])
            activity_data = {row[0]: row[1] for row in self.cursor.fetchall()}

            # Process member data
            inactive_members = []
            now = datetime.now()

            for member in all_members:
                if member.bot:
                    continue

                last_activity_str = activity_data.get(member.id)

                if last_activity_str:
                    try:
                        last_activity = datetime.fromisoformat(last_activity_str)
                        days_inactive = (now - last_activity).days
                        last_activity_time = last_activity.strftime("%m/%d/%Y %H:%M")
                    except ValueError:
                        # Handle invalid date format
                        days_inactive = 999
                        last_activity_time = "Invalid date"
                else:
                    # No activity record = never been active
                    days_inactive = 999
                    last_activity_time = "Never"

                # Check if user is inactive based on the threshold
                if days_inactive >= days:
                    inactive_members.append({
                        'member': member,
                        'last_activity': last_activity_time,
                        'days_inactive': days_inactive
                    })

            if not inactive_members:
                await interaction.followup.send(f"✅ No users have been inactive for {days}+ days!")
                return

            # Sort by inactivity (most inactive first)
            inactive_members.sort(key=lambda x: x['days_inactive'], reverse=True)

            # Create paginated embeds (10 members per page)
            embeds = []
            chunks = [inactive_members[i:i + 10] for i in range(0, len(inactive_members), 10)]

            for i, chunk in enumerate(chunks):
                embed = discord.Embed(
                    title=f"Inactive Users ({days}+ days)",
                    description=f"Total: {len(inactive_members)} inactive members\nUsing threshold: {days} days",
                    color=discord.Color.orange()
                )

                for data in chunk:
                    member = data['member']
                    roles = ", ".join([role.name for role in member.roles if role.name != "@everyone"])

                    # Add warning indicators
                    warning = ""
                    if data['days_inactive'] >= settings['removal_days']:
                        warning = " 🔴"
                    elif data['days_inactive'] >= settings['warning_days']:
                        warning = " ⚠️"

                    embed.add_field(
                        name=f"{member.display_name} ({member.name}){warning}",
                        value=f"Last activity: {data['last_activity']}\nInactive for: {data['days_inactive']} days\nRoles: {roles or 'None'}",
                        inline=False
                    )

                embed.set_footer(
                    text=f"Page {i + 1}/{len(chunks)} • 🔴 = {settings['removal_days']}+ days, ⚠️ = {settings['warning_days']}+ days")
                embeds.append(embed)

            # Create pagination view with ALL buttons
            class PaginationView(discord.ui.View):
                def __init__(self, embeds, inactive_members_data, days_threshold):
                    super().__init__(timeout=300)
                    self.embeds = embeds
                    self.inactive_members_data = inactive_members_data
                    self.days_threshold = days_threshold
                    self.current_page = 0

                @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary)
                async def previous_page(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                    if button_interaction.user != interaction.user:
                        await button_interaction.response.send_message("You cannot use these controls.", ephemeral=True)
                        return
                    self.current_page = max(0, self.current_page - 1)
                    await button_interaction.response.edit_message(embed=self.embeds[self.current_page])

                @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary)
                async def next_page(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                    if button_interaction.user != interaction.user:
                        await button_interaction.response.send_message("You cannot use these controls.", ephemeral=True)
                        return
                    self.current_page = min(len(self.embeds) - 1, self.current_page + 1)
                    await button_interaction.response.edit_message(embed=self.embeds[self.current_page])

                @discord.ui.button(label="Export CSV", style=discord.ButtonStyle.primary)
                async def export_csv(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                    if button_interaction.user != interaction.user:
                        await button_interaction.response.send_message("You cannot use these controls.", ephemeral=True)
                        return

                    try:
                        # Defer the response immediately to prevent timeout
                        await button_interaction.response.defer(ephemeral=True)

                        # Generate CSV content
                        csv_content = "Username,Display Name,User ID,Last Activity,Days Inactive,Roles\n"
                        for data in self.inactive_members_data:
                            member = data['member']
                            roles = "|".join([role.name for role in member.roles if role.name != "@everyone"])
                            # Escape quotes in CSV data
                            username = member.name.replace('"', '""')
                            display_name = member.display_name.replace('"', '""')
                            last_activity = str(data["last_activity"]).replace('"', '""')
                            roles_escaped = roles.replace('"', '""')

                            csv_content += f'"{username}","{display_name}",{member.id},"{last_activity}",{data["days_inactive"]},"{roles_escaped}"\n'

                        # Create file with BytesIO
                        csv_bytes = BytesIO(csv_content.encode('utf-8'))

                        # Create Discord file
                        file = discord.File(
                            fp=csv_bytes,
                            filename=f"inactive_users_{self.days_threshold}_days.csv"
                        )

                        await button_interaction.followup.send(
                            f"📊 Here's the data for {len(self.inactive_members_data)} users inactive for {self.days_threshold}+ days:",
                            file=file,
                            ephemeral=True
                        )

                    except Exception as e:
                        logger.error(f"Error exporting CSV: {e}", exc_info=True)
                        try:
                            await button_interaction.followup.send(
                                "❌ Failed to export CSV. Please try again.",
                                ephemeral=True
                            )
                        except:
                            pass

                @discord.ui.button(label="Notify Users", style=discord.ButtonStyle.danger)
                async def notify_users(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                    if button_interaction.user != interaction.user:
                        await button_interaction.response.send_message("You cannot use these controls.", ephemeral=True)
                        return

                    # Create confirmation view
                    class ConfirmView(discord.ui.View):
                        def __init__(self):
                            super().__init__(timeout=60)
                            self.confirmed = False

                        @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
                        async def confirm(self, confirm_interaction: discord.Interaction,
                                          confirm_button: discord.ui.Button):
                            if confirm_interaction.user != interaction.user:
                                await confirm_interaction.response.send_message("You cannot use these controls.",
                                                                                ephemeral=True)
                                return
                            self.confirmed = True
                            await confirm_interaction.response.defer()
                            self.stop()

                        @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
                        async def cancel(self, cancel_interaction: discord.Interaction,
                                         cancel_button: discord.ui.Button):
                            if cancel_interaction.user != interaction.user:
                                await cancel_interaction.response.send_message("You cannot use these controls.",
                                                                               ephemeral=True)
                                return
                            await cancel_interaction.response.send_message("Operation cancelled.", ephemeral=True)
                            self.stop()

                    confirm_view = ConfirmView()
                    await button_interaction.response.send_message(
                        f"⚠️ Are you sure you want to DM all {len(self.inactive_members_data)} inactive users? This cannot be undone.",
                        view=confirm_view,
                        ephemeral=True
                    )

                    # Wait for confirmation
                    await confirm_view.wait()
                    if confirm_view.confirmed:
                        # Send DMs to inactive users
                        success_count = 0
                        failed_count = 0

                        for data in self.inactive_members_data:
                            member = data['member']
                            try:
                                embed = discord.Embed(
                                    title=f"Inactivity Notice from {interaction.guild.name}",
                                    description=(
                                        f"Hello {member.mention},\n\n"
                                        f"We noticed you haven't been active in **{interaction.guild.name}** "
                                        f"for **{data['days_inactive']} days** (last activity: {data['last_activity']}). We miss you!\n\n"
                                        f"If you'd like to remain a member, please send a message in any channel "
                                        f"to let us know you're still interested in being part of our community.\n\n"
                                        f"Thank you!"
                                    ),
                                    color=discord.Color.orange()
                                )
                                embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
                                await member.send(embed=embed)
                                success_count += 1
                                # Add a small delay to avoid rate limits
                                await asyncio.sleep(1)
                            except Exception as e:
                                logger.error(f"Failed to DM {member}: {e}")
                                failed_count += 1

                        # Send summary
                        await button_interaction.followup.send(
                            f"✅ DM sent to {success_count} users\n❌ Failed to DM {failed_count} users",
                            ephemeral=True
                        )

            # Send the first page with pagination (pass days parameter too)
            view = PaginationView(embeds, inactive_members, days)
            await interaction.followup.send(embed=embeds[0], view=view)

        except Exception as e:
            logger.error(f"Error in inactive_users command: {e}", exc_info=True)
            await interaction.followup.send("An error occurred while processing the command.")


    @app_commands.command(
        name="check_settings",
        description="View current inactivity settings for this server"
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def check_settings(self, interaction: discord.Interaction):
        """Check current inactivity settings"""
        try:
            settings = self.get_inactivity_settings(interaction.guild.id)

            embed = discord.Embed(
                title="Inactivity Settings",
                description=f"Current settings for {interaction.guild.name}",
                color=discord.Color.blue()
            )

            embed.add_field(
                name="Warning Threshold",
                value=f"{settings['warning_days']} days",
                inline=True
            )

            embed.add_field(
                name="Removal Threshold",
                value=f"{settings['removal_days']} days",
                inline=True
            )

            # Get warning role if set
            warning_role = None
            if settings['warning_role_id']:
                warning_role = interaction.guild.get_role(settings['warning_role_id'])

            embed.add_field(
                name="Warning Role",
                value=warning_role.mention if warning_role else "Not set",
                inline=True
            )

            # Get notification channel if set
            notification_channel = None
            if settings['notification_channel_id']:
                notification_channel = interaction.guild.get_channel(settings['notification_channel_id'])

            embed.add_field(
                name="Notification Channel",
                value=notification_channel.mention if notification_channel else "Not set",
                inline=True
            )

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            logger.error(f"Error in check_settings command: {e}", exc_info=True)
            await interaction.response.send_message("An error occurred while fetching settings.", ephemeral=True)

    @app_commands.command(
        name="roleinfo",
        description="List members with a specific role and their last activity"
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def roleinfo(self, interaction: discord.Interaction, role: discord.Role,
                       inactive_days: Optional[int] = None,
                       sort_by: Optional[str] = "name"):
        """
        List members with a specific role and their last activity
        Parameters:
        -----------
        role: The role to check
        inactive_days: Only show members inactive for this many days (optional)
        sort_by: Sort by "name" or "activity" (optional)
        """
        await interaction.response.defer()

        try:
            from io import BytesIO

            # Get inactivity settings if no specific days provided
            if inactive_days is None:
                settings = self.get_inactivity_settings(interaction.guild.id)
                default_days = settings['warning_days']
            else:
                default_days = inactive_days

            # Get all members with the role
            members_with_role = [member for member in interaction.guild.members if role in member.roles]

            if not members_with_role:
                await interaction.followup.send(f"No members have the {role.name} role.")
                return

            # Get activity data for all members at once
            member_ids = [member.id for member in members_with_role]
            placeholders = ','.join(['?'] * len(member_ids))
            query = f'''
                SELECT user_id, last_activity 
                FROM activity 
                WHERE user_id IN ({placeholders}) AND guild_id = ?
            '''
            self.cursor.execute(query, member_ids + [interaction.guild.id])
            activity_data = {row[0]: row[1] for row in self.cursor.fetchall()}

            # Process member data
            member_data = []
            now = datetime.now()

            for member in members_with_role:
                last_activity_str = activity_data.get(member.id)

                if last_activity_str:
                    try:
                        last_activity = datetime.fromisoformat(last_activity_str)
                        days_inactive = (now - last_activity).days
                        last_activity_time = last_activity.strftime("%m/%d/%Y %H:%M")
                    except ValueError:
                        days_inactive = 999  # High number for sorting
                        last_activity_time = "Invalid date"
                else:
                    days_inactive = 999  # High number for sorting
                    last_activity_time = "Never"

                # Skip if we're filtering by inactive days and this member doesn't match
                if inactive_days is not None and days_inactive < inactive_days:
                    continue

                member_data.append({
                    'member': member,
                    'last_activity': last_activity_time,
                    'days_inactive': days_inactive
                })

            # Sort the data
            if sort_by.lower() == "activity":
                member_data.sort(key=lambda x: x['days_inactive'], reverse=True)
            else:  # Default to name
                member_data.sort(key=lambda x: x['member'].display_name.lower())

            # Create paginated embeds (10 members per page)
            embeds = []
            chunks = [member_data[i:i + 10] for i in range(0, len(member_data), 10)]

            for i, chunk in enumerate(chunks):
                embed = discord.Embed(
                    title=f"Members with {role.name}",
                    description=f"Total: {len(member_data)} members" +
                                (f" inactive for {inactive_days}+ days" if inactive_days else ""),
                    color=role.color or discord.Color.blue()
                )

                for data in chunk:
                    member = data['member']
                    value = f"Last activity: {data['last_activity']}"
                    if data['days_inactive'] >= 60:
                        value += f" ({data['days_inactive']} days ago) 🔴"
                    elif data['days_inactive'] >= 30:
                        value += f" ({data['days_inactive']} days ago) ⚠️"
                    elif data['days_inactive'] >= 14:
                        value += f" ({data['days_inactive']} days ago) ⚠"

                    embed.add_field(
                        name=f"{member.display_name} ({member.name})",
                        value=value,
                        inline=False
                    )

                embed.set_footer(text=f"Page {i + 1}/{len(chunks)} • Sorted by {sort_by}")
                embeds.append(embed)

            if not embeds:
                await interaction.followup.send(f"No members with the {role.name} role match your criteria.")
                return

            # Create pagination buttons with FIXED CSV export
            class PaginationView(discord.ui.View):
                def __init__(self, embeds, member_data, role_name):
                    super().__init__(timeout=300)
                    self.embeds = embeds
                    self.member_data = member_data
                    self.role_name = role_name
                    self.current_page = 0

                @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary)
                async def previous_page(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                    if button_interaction.user != interaction.user:
                        await button_interaction.response.send_message("You cannot use these controls.", ephemeral=True)
                        return
                    self.current_page = max(0, self.current_page - 1)
                    await button_interaction.response.edit_message(embed=self.embeds[self.current_page])

                @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary)
                async def next_page(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                    if button_interaction.user != interaction.user:
                        await button_interaction.response.send_message("You cannot use these controls.", ephemeral=True)
                        return
                    self.current_page = min(len(self.embeds) - 1, self.current_page + 1)
                    await button_interaction.response.edit_message(embed=self.embeds[self.current_page])

                @discord.ui.button(label="Export CSV", style=discord.ButtonStyle.primary)
                async def export_csv(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                    if button_interaction.user != interaction.user:
                        await button_interaction.response.send_message("You cannot use these controls.", ephemeral=True)
                        return

                    try:
                        # Defer the response immediately to prevent timeout
                        await button_interaction.response.defer(ephemeral=True)

                        # Generate CSV content
                        csv_content = "Username,Display Name,User ID,Last Activity,Days Inactive\n"
                        for data in self.member_data:
                            member = data['member']
                            # Escape quotes in CSV data
                            username = member.name.replace('"', '""')
                            display_name = member.display_name.replace('"', '""')
                            last_activity = str(data["last_activity"]).replace('"', '""')

                            csv_content += f'"{username}","{display_name}",{member.id},"{last_activity}",{data["days_inactive"]}\n'

                        # Create file with BytesIO
                        csv_bytes = BytesIO(csv_content.encode('utf-8'))

                        # Create Discord file
                        file = discord.File(
                            fp=csv_bytes,
                            filename=f"{self.role_name}_activity.csv"
                        )

                        await button_interaction.followup.send(
                            f"📊 Here's the activity data for members with the {self.role_name} role:",
                            file=file,
                            ephemeral=True
                        )

                    except Exception as e:
                        logger.error(f"Error exporting CSV: {e}", exc_info=True)
                        try:
                            await button_interaction.followup.send(
                                "❌ Failed to export CSV. Please try again.",
                                ephemeral=True
                            )
                        except:
                            pass

            # Send the first page with pagination
            view = PaginationView(embeds, member_data, role.name)
            await interaction.followup.send(embed=embeds[0], view=view)

        except Exception as e:
            logger.error(f"Error in roleinfo command: {e}", exc_info=True)
            await interaction.followup.send("An error occurred while processing the command.")

    @app_commands.command(
        name="setup_inactivity",
        description="Configure inactivity tracking settings"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_inactivity(self, interaction: discord.Interaction,
                               warning_days: int = 30,
                               removal_days: int = 60,
                               warning_role: Optional[discord.Role] = None,
                               notification_channel: Optional[discord.TextChannel] = None):
        """
        Configure inactivity tracking settings for the server
        Parameters:
        -----------
        warning_days: Days of inactivity before a warning is issued
        removal_days: Days of inactivity before role removal is suggested
        warning_role: Role to assign to inactive users (optional)
        notification_channel: Channel to send notifications to (optional)
        """
        try:
            # Update or insert settings
            self.cursor.execute('''
                INSERT OR REPLACE INTO inactivity_settings
                (guild_id, warning_days, removal_days, warning_role_id, notification_channel_id)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                interaction.guild.id,
                warning_days,
                removal_days,
                warning_role.id if warning_role else None,
                notification_channel.id if notification_channel else None
            ))
            self.db.commit()

            # Create confirmation embed
            embed = discord.Embed(
                title="Inactivity Tracking Configured",
                description="Your inactivity tracking settings have been updated.",
                color=discord.Color.green()
            )
            embed.add_field(
                name="Warning Threshold",
                value=f"{warning_days} days",
                inline=True
            )
            embed.add_field(
                name="Removal Threshold",
                value=f"{removal_days} days",
                inline=True
            )
            embed.add_field(
                name="Warning Role",
                value=warning_role.mention if warning_role else "Not set",
                inline=True
            )
            embed.add_field(
                name="Notification Channel",
                value=notification_channel.mention if notification_channel else "Not set",
                inline=True
            )

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            logger.error(f"Error in setup_inactivity command: {e}", exc_info=True)
            await interaction.response.send_message("An error occurred while saving your settings.", ephemeral=True)

    @app_commands.command(
        name="user_activity",
        description="Check a specific user's activity"
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def user_activity(self, interaction: discord.Interaction, user: discord.Member):
        """
        Check a specific user's activity details
        Parameters:
        -----------
        user: The user to check
        """
        try:
            # Get user's activity data
            self.cursor.execute('''
                SELECT last_message, last_reaction, last_voice, last_activity
                FROM activity
                WHERE user_id = ? AND guild_id = ?
            ''', (user.id, interaction.guild.id))

            result = self.cursor.fetchone()

            if not result:
                await interaction.response.send_message(f"No activity data found for {user.mention}.")
                return

            last_message, last_reaction, last_voice, last_activity = result
            now = datetime.now()

            # Get server settings for warning indicators
            settings = self.get_inactivity_settings(interaction.guild.id)

            # Create the embed
            embed = discord.Embed(
                title=f"Activity for {user.display_name}",
                color=user.color or discord.Color.blue()
            )
            embed.set_thumbnail(url=user.display_avatar.url)

            # Add user info
            embed.add_field(
                name="User Info",
                value=(
                    f"**Username:** {user.name}\n"
                    f"**Display Name:** {user.display_name}\n"
                    f"**ID:** {user.id}\n"
                    f"**Joined Server:** {user.joined_at.strftime('%m/%d/%Y %H:%M') if user.joined_at else 'Unknown'}\n"
                    f"**Account Created:** {user.created_at.strftime('%m/%d/%Y %H:%M')}"
                ),
                inline=False
            )

            # Add activity data
            activity_info = []

            if last_message:
                try:
                    last_message_dt = datetime.fromisoformat(last_message)
                    days_since_message = (now - last_message_dt).days
                    activity_info.append(
                        f"**Last Message:** {last_message_dt.strftime('%m/%d/%Y %H:%M')} ({days_since_message} days ago)")
                except ValueError:
                    activity_info.append(f"**Last Message:** Invalid date format")

            if last_reaction:
                try:
                    last_reaction_dt = datetime.fromisoformat(last_reaction)
                    days_since_reaction = (now - last_reaction_dt).days
                    activity_info.append(
                        f"**Last Reaction:** {last_reaction_dt.strftime('%m/%d/%Y %H:%M')} ({days_since_reaction} days ago)")
                except ValueError:
                    activity_info.append(f"**Last Reaction:** Invalid date format")

            if last_voice:
                try:
                    last_voice_dt = datetime.fromisoformat(last_voice)
                    days_since_voice = (now - last_voice_dt).days
                    activity_info.append(
                        f"**Last Voice Activity:** {last_voice_dt.strftime('%m/%d/%Y %H:%M')} ({days_since_voice} days ago)")
                except ValueError:
                    activity_info.append(f"**Last Voice Activity:** Invalid date format")

            if last_activity:
                try:
                    last_activity_dt = datetime.fromisoformat(last_activity)
                    days_since_activity = (now - last_activity_dt).days
                    activity_info.append(
                        f"**Last Activity:** {last_activity_dt.strftime('%m/%d/%Y %H:%M')} ({days_since_activity} days ago)")

                    # Add warning indicators based on server settings
                    if days_since_activity >= settings['removal_days']:
                        activity_info.append("🔴 **Exceeds removal threshold** 🔴")
                    elif days_since_activity >= settings['warning_days']:
                        activity_info.append("⚠️ **Exceeds warning threshold** ⚠️")
                    elif days_since_activity >= 14:
                        activity_info.append("⚠ **Moderately inactive**")
                except ValueError:
                    activity_info.append(f"**Last Activity:** Invalid date format")

            embed.add_field(
                name="Activity Data",
                value="\n".join(activity_info) or "No activity data available",
                inline=False
            )

            # Add roles
            roles = [role.mention for role in user.roles if role.name != "@everyone"]
            embed.add_field(
                name=f"Roles ({len(roles)})",
                value=" ".join(roles) or "No roles",
                inline=False
            )

            # Add server settings info
            embed.add_field(
                name="Server Thresholds",
                value=f"Warning: {settings['warning_days']} days\nRemoval: {settings['removal_days']} days",
                inline=True
            )

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            logger.error(f"Error in user_activity command: {e}", exc_info=True)
            await interaction.response.send_message("An error occurred while fetching user activity data.",
                                                    ephemeral=True)

    @app_commands.command(
        name="activity_summary",
        description="Get a summary of server activity statistics"
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def activity_summary(self, interaction: discord.Interaction):
        """Get a summary of server activity statistics"""
        await interaction.response.defer()

        try:
            settings = self.get_inactivity_settings(interaction.guild.id)

            # Get all non-bot members
            all_members = [member for member in interaction.guild.members if not member.bot]
            total_members = len(all_members)

            if total_members == 0:
                await interaction.followup.send("No members found in this server.")
                return

            # Get activity data for all members
            member_ids = [member.id for member in all_members]
            placeholders = ','.join(['?'] * len(member_ids))
            query = f'''
                SELECT user_id, last_activity 
                FROM activity 
                WHERE user_id IN ({placeholders}) AND guild_id = ?
            '''
            self.cursor.execute(query, member_ids + [interaction.guild.id])
            activity_data = {row[0]: row[1] for row in self.cursor.fetchall()}

            # Categorize members by activity
            now = datetime.now()
            active_members = 0
            warning_members = 0
            removal_members = 0
            never_active = 0

            for member in all_members:
                last_activity_str = activity_data.get(member.id)

                if last_activity_str:
                    try:
                        last_activity = datetime.fromisoformat(last_activity_str)
                        days_inactive = (now - last_activity).days

                        if days_inactive >= settings['removal_days']:
                            removal_members += 1
                        elif days_inactive >= settings['warning_days']:
                            warning_members += 1
                        else:
                            active_members += 1
                    except ValueError:
                        never_active += 1
                else:
                    never_active += 1

            # Create summary embed
            embed = discord.Embed(
                title=f"Activity Summary for {interaction.guild.name}",
                description=f"Analysis of {total_members} members",
                color=discord.Color.blue()
            )

            # Add statistics
            embed.add_field(
                name="🟢 Active Members",
                value=f"{active_members} ({active_members / total_members * 100:.1f}%)\nLess than {settings['warning_days']} days inactive",
                inline=True
            )

            embed.add_field(
                name="⚠️ Warning Level",
                value=f"{warning_members} ({warning_members / total_members * 100:.1f}%)\n{settings['warning_days']}-{settings['removal_days'] - 1} days inactive",
                inline=True
            )

            embed.add_field(
                name="🔴 Removal Level",
                value=f"{removal_members} ({removal_members / total_members * 100:.1f}%)\n{settings['removal_days']}+ days inactive",
                inline=True
            )

            embed.add_field(
                name="❓ Never Active",
                value=f"{never_active} ({never_active / total_members * 100:.1f}%)\nNo recorded activity",
                inline=True
            )

            embed.add_field(
                name="Server Settings",
                value=f"Warning threshold: {settings['warning_days']} days\nRemoval threshold: {settings['removal_days']} days",
                inline=True
            )

            # Add recommendations
            recommendations = []
            if warning_members > 0:
                recommendations.append(f"• Consider messaging {warning_members} members at warning level")
            if removal_members > 0:
                recommendations.append(f"• Review {removal_members} members for potential role removal")
            if never_active > total_members * 0.2:  # More than 20% never active
                recommendations.append(f"• High number of never-active members - consider cleanup")

            if recommendations:
                embed.add_field(
                    name="📋 Recommendations",
                    value="\n".join(recommendations),
                    inline=False
                )

            embed.set_footer(text="Use /inactive_users to see detailed lists")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Error in activity_summary command: {e}", exc_info=True)
            await interaction.followup.send("An error occurred while generating the activity summary.")

    @app_commands.command(
        name="reset_activity",
        description="Reset activity data for a user (admin only)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_activity(self, interaction: discord.Interaction, user: discord.Member):
        """Reset activity data for a specific user"""
        try:
            # Delete the user's activity record
            self.cursor.execute('''
                DELETE FROM activity 
                WHERE user_id = ? AND guild_id = ?
            ''', (user.id, interaction.guild.id))

            rows_affected = self.cursor.rowcount
            self.db.commit()

            if rows_affected > 0:
                await interaction.response.send_message(f"✅ Reset activity data for {user.mention}.")
            else:
                await interaction.response.send_message(f"No activity data found for {user.mention} to reset.")

        except Exception as e:
            logger.error(f"Error in reset_activity command: {e}", exc_info=True)
            await interaction.response.send_message("An error occurred while resetting activity data.", ephemeral=True)

    @app_commands.command(
        name="bulk_reset_activity",
        description="Reset activity data for multiple users (admin only)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def bulk_reset_activity(self, interaction: discord.Interaction, role: Optional[discord.Role] = None):
        """Reset activity data for all users or users with a specific role"""
        await interaction.response.defer()

        try:
            if role:
                # Reset for specific role
                members_to_reset = [member for member in interaction.guild.members if
                                    role in member.roles and not member.bot]
                description = f"all members with the {role.name} role"
            else:
                # Reset for all members
                members_to_reset = [member for member in interaction.guild.members if not member.bot]
                description = "all members"

            if not members_to_reset:
                await interaction.followup.send("No members found to reset activity data for.")
                return

            # Create confirmation
            class ConfirmView(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=60)
                    self.confirmed = False

                @discord.ui.button(label="Confirm Reset", style=discord.ButtonStyle.danger)
                async def confirm(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                    if button_interaction.user != interaction.user:
                        await button_interaction.response.send_message("You cannot use these controls.", ephemeral=True)
                        return
                    self.confirmed = True
                    await button_interaction.response.defer()
                    self.stop()

                @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
                async def cancel(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                    if button_interaction.user != interaction.user:
                        await button_interaction.response.send_message("You cannot use these controls.", ephemeral=True)
                        return
                    await button_interaction.response.send_message("Operation cancelled.", ephemeral=True)
                    self.stop()

            confirm_view = ConfirmView()
            await interaction.followup.send(
                f"⚠️ **WARNING**: This will reset activity data for {len(members_to_reset)} members ({description}).\n\n"
                f"This action cannot be undone. Are you sure?",
                view=confirm_view
            )

            await confirm_view.wait()

            if confirm_view.confirmed:
                # Perform the reset
                member_ids = [member.id for member in members_to_reset]
                placeholders = ','.join(['?'] * len(member_ids))

                self.cursor.execute(f'''
                    DELETE FROM activity 
                    WHERE user_id IN ({placeholders}) AND guild_id = ?
                ''', member_ids + [interaction.guild.id])

                rows_affected = self.cursor.rowcount
                self.db.commit()

                await interaction.followup.send(
                    f"✅ Reset activity data for {rows_affected} members ({description})."
                )

        except Exception as e:
            logger.error(f"Error in bulk_reset_activity command: {e}", exc_info=True)
            await interaction.followup.send("An error occurred while resetting activity data.")


async def setup(bot):
    await bot.add_cog(RoleInfo(bot))


