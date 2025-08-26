import asyncio
import csv
import discord
import io
import json
import os
import pytz
import shutil
import re
import datetime
import copy
import glob
import logging
import time
import gspread
from google.oauth2.service_account import Credentials
from dateutil.rrule import rrulestr
from datetime import datetime, timedelta
from discord import app_commands
from discord.ext import commands, tasks
from pytz import timezone
from discord.ui import Button, View
from typing import Dict, List, Optional, Union
import sqlite3

# Constants
PASTEL_BLUE = 0x9DB2FF
PASTEL_RED = 0xFF9D9D
PASTEL_GREEN = 0x9DFFB2
DATA_FOLDER = "data"

logger = logging.getLogger(__name__)


class AttendanceTracker:
    def __init__(self):
        # Existing JSON-based storage
        self.data_file = os.path.join("data", "attendance_records.json")
        os.makedirs(os.path.dirname(self.data_file), exist_ok=True)

        self.attendance_data = {
            "records": [],
            "last_id": 0
        }

        # Load existing data
        self.load_data()

        # Google Sheets setup
        self.sheets_cache = {}  # Cache sheets by guild_id
        self.gc = None
        self.sheets_enabled = False
        self.setup_google_auth()

    def setup_google_auth(self):
        """Set up Google authentication (one time)"""
        try:
            scope = [
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive"
            ]

            creds_file = "google_credentials.json"

            if os.path.exists(creds_file):
                creds = Credentials.from_service_account_file(creds_file, scopes=scope)
                self.gc = gspread.authorize(creds)
                self.sheets_enabled = True
                print("Google Sheets authentication successful")
            else:
                print(f"Google credentials file '{creds_file}' not found. Google Sheets integration disabled.")
                self.sheets_enabled = False

        except Exception as e:
            print(f"Error setting up Google Sheets authentication: {e}")
            self.sheets_enabled = False

    def get_sheet_name(self, guild_id, guild_name):
        """Generate sheet name for a specific guild"""
        # Clean guild name for use in sheet title
        clean_name = "".join(c for c in guild_name if c.isalnum() or c in (' ', '-', '_')).strip()
        return f"Attendance - {clean_name} ({guild_id})"

    async def get_or_create_sheet(self, guild_id, guild_name):
        """Get or create a sheet for a specific guild"""
        if not self.sheets_enabled:
            return None

        # Check cache first
        if guild_id in self.sheets_cache:
            return self.sheets_cache[guild_id]

        try:
            sheet_name = self.get_sheet_name(guild_id, guild_name)

            try:
                # Try to open existing sheet
                sheet = self.gc.open(sheet_name).sheet1
                print(f"Found existing sheet for guild {guild_name}: {sheet_name}")

            except gspread.SpreadsheetNotFound:
                # Create new sheet
                print(f"Creating new sheet for guild {guild_name}: {sheet_name}")
                spreadsheet = self.gc.create(sheet_name)
                sheet = spreadsheet.sheet1

                # Set up headers
                headers = [
                    "Timestamp", "User ID", "Username", "Event ID",
                    "Event Title", "Role ID", "Role Name", "Action", "Guild ID", "Guild Name"
                ]
                sheet.insert_row(headers, 1)

                # Format the header row
                sheet.format('A1:J1', {
                    "backgroundColor": {"red": 0.2, "green": 0.6, "blue": 1.0},
                    "textFormat": {"bold": True, "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}}
                })

                print(f"Created new sheet: {sheet_name}")
                print(f"Sheet URL: {spreadsheet.url}")

            # Cache the sheet
            self.sheets_cache[guild_id] = sheet
            return sheet

        except Exception as e:
            print(f"Error getting/creating sheet for guild {guild_id}: {e}")
            return None

    async def log_to_google_sheets(self, user_id, username, event_id, event_title, role_id, role_name, action, guild_id,
                                   guild_name):
        print(f"🔍 log_to_google_sheets called for {username} in {guild_name}")  # ADD THIS

        if not self.sheets_enabled:
            print("❌ Sheets not enabled")  # ADD THIS
            return False

        try:
            # Get the sheet for this guild
            sheet = await self.get_or_create_sheet(guild_id, guild_name)
            if not sheet:
                return False

            # Get current timestamp in EST
            est = pytz.timezone('US/Eastern')
            timestamp = datetime.now(est).strftime("%Y-%m-%d %H:%M:%S EST")

            # Prepare row data
            row_data = [
                timestamp,
                str(user_id),
                username,
                str(event_id),
                event_title,
                str(role_id),
                role_name,
                action,  # "joined" or "left"
                str(guild_id),
                guild_name
            ]

            # Insert the row (at row 2, after headers)
            sheet.insert_row(row_data, 2)
            print(f"✅ Successfully logged to sheets for {username}")
            return True
        except Exception as e:
            print(f"❌ Error logging to sheets: {e}")  # ADD THIS
            return False

    def get_sheet_url(self, guild_id):
        """Get the URL for a guild's sheet"""
        if guild_id in self.sheets_cache:
            return self.sheets_cache[guild_id].spreadsheet.url
        return None

    def clear_cache(self):
        """Clear the sheets cache (useful for testing)"""
        self.sheets_cache.clear()

    def load_data(self):
        """Load attendance data from file"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r') as f:
                    loaded_data = json.load(f)

                    # Ensure the loaded data has the required structure
                    if isinstance(loaded_data, dict) and "records" in loaded_data and "last_id" in loaded_data:
                        self.attendance_data = loaded_data
                    else:
                        # Convert old format to new format if needed
                        if isinstance(loaded_data, list):
                            # Old format was just a list of records
                            self.attendance_data = {
                                "records": loaded_data,
                                "last_id": len(loaded_data)
                            }
                        else:
                            # Initialize with default structure
                            self.attendance_data = {
                                "records": [],
                                "last_id": 0
                            }
                        print("Converted attendance data to new format")
                        self.save_data()
        except Exception as e:
            print(f"Error loading attendance data: {e}")
            # Initialize with empty structure
            self.attendance_data = {
                "records": [],
                "last_id": 0
            }
            self.save_data()

    def save_data(self):
        """Save attendance data to file"""
        try:
            with open(self.data_file, 'w') as f:
                json.dump(self.attendance_data, f, indent=4)
            return True
        except Exception as e:
            print(f"Error saving attendance data: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def record_attendance(self, guild_id, user_id, event_id, event_title, event_time, role_id, role_name):
        """Record a user's attendance for an event"""
        try:
            # Check if this attendance record already exists
            for record in self.attendance_data["records"]:
                if (record["guild_id"] == str(guild_id) and
                        record["user_id"] == str(user_id) and
                        record["event_id"] == str(event_id) and
                        record["role_id"] == str(role_id)):
                    # Already exists, update it
                    record["role_name"] = role_name
                    record["event_title"] = event_title
                    record["event_time"] = event_time
                    record["timestamp"] = datetime.now().isoformat()
                    self.save_data()
                    return True

            # Create a new record
            record = {
                "id": self.attendance_data["last_id"] + 1,
                "guild_id": str(guild_id),
                "user_id": str(user_id),
                "event_id": str(event_id),
                "event_title": event_title,
                "event_time": event_time,
                "role_id": str(role_id),
                "role_name": role_name,
                "timestamp": datetime.now().isoformat()
            }

            # Add to records and update last_id
            self.attendance_data["records"].append(record)
            self.attendance_data["last_id"] += 1

            # Save to file
            self.save_data()
            return True
        except Exception as e:
            print(f"Error recording attendance: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def delete_attendance(self, guild_id, user_id, event_id, role_id):
        """Delete a user's attendance record"""
        try:
            # Find the record to delete
            for i, record in enumerate(self.attendance_data["records"]):
                if (record["guild_id"] == str(guild_id) and
                        record["user_id"] == str(user_id) and
                        record["event_id"] == str(event_id) and
                        record["role_id"] == str(role_id)):
                    # Remove the record
                    self.attendance_data["records"].pop(i)
                    self.save_data()
                    return True
            return False
        except Exception as e:
            print(f"Error deleting attendance: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def update_attendance(self, guild_id, event_id, user_id, role_id, role_name, event_title, event_time,
                                old_role_id=None):
        """Update a user's attendance record"""
        try:
            # First delete the old record
            if old_role_id:
                await self.delete_attendance(guild_id, user_id, event_id, old_role_id)
            else:
                await self.delete_attendance(guild_id, user_id, event_id, role_id)

            # Then create a new one
            return await self.record_attendance(
                guild_id=guild_id,
                user_id=user_id,
                event_id=event_id,
                event_title=event_title,
                event_time=event_time,
                role_id=role_id,
                role_name=role_name
            )
        except Exception as e:
            print(f"Error updating attendance: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def get_user_attendance(self, guild_id, user_id):
        """Get all attendance records for a user in a guild"""
        try:
            records = []
            for record in self.attendance_data["records"]:
                if record["guild_id"] == str(guild_id) and record["user_id"] == str(user_id):
                    records.append(record)
            return records
        except Exception as e:
            print(f"Error getting user attendance: {e}")
            import traceback
            traceback.print_exc()
            return []

    async def get_event_attendance(self, guild_id, event_id):
        """Get all attendance records for an event"""
        try:
            records = []
            for record in self.attendance_data["records"]:
                if record["guild_id"] == str(guild_id) and record["event_id"] == str(event_id):
                    records.append(record)
            return records
        except Exception as e:
            print(f"Error getting event attendance: {e}")
            import traceback
            traceback.print_exc()
            return []

    def get_guild_attendance_stats(self, guild_id, days=30):
        """Get attendance statistics for a guild"""
        try:
            # Convert to string
            guild_id = str(guild_id)

            # Calculate the date threshold
            threshold_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

            # Find all records for this guild within the time period
            guild_records = [
                record for record in self.attendance_data["records"]
                if record["guild_id"] == guild_id and
                   record.get("event_time", "").split(" ")[0] >= threshold_date
            ]

            # Get unique events and users
            unique_events = set()
            unique_users = set()
            event_attendance = {}  # event_id -> list of user_ids
            user_attendance = {}  # user_id -> list of event_ids

            for record in guild_records:
                event_id = record.get("event_id")
                user_id = record.get("user_id")
                event_title = record.get("event_title", "Unknown")

                if event_id and user_id:
                    unique_events.add(event_id)
                    unique_users.add(user_id)

                    # Track which users attended which events
                    if event_id not in event_attendance:
                        event_attendance[event_id] = {
                            "title": event_title,
                            "users": set()
                        }
                    event_attendance[event_id]["users"].add(user_id)

                    # Track which events each user attended
                    if user_id not in user_attendance:
                        user_attendance[user_id] = set()
                    user_attendance[user_id].add(event_id)

            # Get most active users
            most_active_users = sorted(
                [{"user_id": user_id, "event_count": len(events)}
                 for user_id, events in user_attendance.items()],
                key=lambda x: x["event_count"],
                reverse=True
            )[:5]

            # Get most popular events
            most_popular_events = sorted(
                [{"event_id": event_id, "event_title": data["title"], "user_count": len(data["users"])}
                 for event_id, data in event_attendance.items()],
                key=lambda x: x["user_count"],
                reverse=True
            )[:5]

            # Format the statistics
            stats = {
                "total_events": len(unique_events),
                "total_attendees": len(unique_users),
                "most_active_users": most_active_users,
                "most_popular_events": most_popular_events
            }

            return stats
        except Exception as e:
            print(f"Error getting guild attendance stats: {e}")
            import traceback
            traceback.print_exc()
            return {
                "total_events": 0,
                "total_attendees": 0,
                "most_active_users": [],
                "most_popular_events": []
            }


class DeleteConfirmationView(discord.ui.View):
    def __init__(self, cog, guild_id):
        super().__init__(timeout=60)  # 60 seconds timeout
        self.cog = cog
        self.guild_id = guild_id

    @discord.ui.button(label="Yes, delete ALL events", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Delete all events
        deleted_count = await self.cog.delete_all_events(self.guild_id)

        # Disable all buttons
        for item in self.children:
            item.disabled = True

        # Update the message
        await interaction.response.edit_message(
            content=f"✅ Successfully deleted {deleted_count} events from this server.",
            view=self
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Disable all buttons
        for item in self.children:
            item.disabled = True

        # Update the message
        await interaction.response.edit_message(
            content="Operation cancelled. No events were deleted.",
            view=self
        )

    async def on_timeout(self):
        # Disable all buttons when the view times out
        for item in self.children:
            item.disabled = True


class RoleButton(discord.ui.Button):
    # Class variable to track button cooldowns
    _cooldowns = {}

    def __init__(self, cog, event_id, role_id, label, style, disabled=False, required_role_id=None):
        # Create a custom_id that uniquely identifies this button
        custom_id = f"attendance:{event_id}:{role_id}:toggle"
        super().__init__(
            style=style,
            label=label,
            disabled=disabled,
            custom_id=custom_id
        )
        self.cog = cog
        self.event_id = event_id
        self.role_id = role_id
        self.required_role_id = required_role_id

    async def callback(self, interaction: discord.Interaction):
        """Handle button click with debounce protection"""
        # Create a unique key for this user, event, and role
        user_id = str(interaction.user.id)
        cooldown_key = f"{user_id}:{self.event_id}:{self.role_id}"

        # Check if the button is on cooldown (1 second cooldown)
        current_time = datetime.now().timestamp()
        if cooldown_key in RoleButton._cooldowns:
            last_click = RoleButton._cooldowns[cooldown_key]
            if current_time - last_click < 1.0:  # 1 second cooldown
                # Button was clicked too recently, ignore this click
                try:
                    if not interaction.response.is_done():
                        await interaction.response.defer(ephemeral=True)
                except Exception as e:
                    print(f"Error deferring interaction during cooldown: {e}")
                return

        # Update the cooldown timestamp
        RoleButton._cooldowns[cooldown_key] = current_time

        # Defer the response immediately
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception as e:
            print(f"Error deferring interaction in button callback: {e}")

        try:
            # Call the handler in the cog
            await self.cog.toggle_role(interaction, self.event_id, self.role_id)
        except Exception as e:
            print(f"Error in RoleButton callback: {e}")
            import traceback
            traceback.print_exc()
            try:
                await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True)
            except Exception as follow_up_error:
                print(f"Error sending followup: {follow_up_error}")

class AttendanceView(discord.ui.View):
    def __init__(self, cog, event_id):
        super().__init__(timeout=None)  # Make the view persistent
        self.cog = cog
        self.event_id = event_id

        # Clear any existing items
        self.clear_items()

        # Add buttons for each role if event_id in self.cog.events
        if event_id in self.cog.events:
            event = self.cog.events[event_id]
            for role_id, role_data in event["roles"].items():
                if role_data.get("name"):  # Only add buttons for roles with names
                    # Determine button style
                    style = discord.ButtonStyle.primary  # Default is blue

                    # If the role is restricted, make it red
                    if role_data.get("restricted", False):
                        style = discord.ButtonStyle.danger  # Red
                    # Otherwise use the specified style if available
                    elif role_data.get("style") == "green":
                        style = discord.ButtonStyle.success
                    elif role_data.get("style") == "red":
                        style = discord.ButtonStyle.danger
                    elif role_data.get("style") == "gray":
                        style = discord.ButtonStyle.secondary

                    # Create the button using RoleButton class
                    button = RoleButton(
                        cog=self.cog,
                        event_id=event_id,
                        role_id=role_id,
                        label=role_data["name"],
                        style=style,
                        disabled=role_data.get("disabled", False),
                        required_role_id=role_data.get("required_role_id")
                    )
                    self.add_item(button)


class Attendance(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.events = {}
        self.reminder_tasks = {}
        self.cleanup_tasks = {}
        self.pending_tasks = {}
        self.recurring_tasks = {}
        self.data_dir = "data"

        # Set up all data storage
        self.setup_data_storage()

        # We'll load events when the bot is ready
        self.bot.loop.create_task(self.load_all_events_when_ready())

        # Start the check_events task
        self.check_events.start()

        # Load guild email configurations
        self.load_guild_emails()

    def cog_load(self):
        """Called when the cog is loaded"""
        # Only start the task if it's not already running
        if not self.check_events.is_running():
            self.check_events.start()

        # Clean up old events
        asyncio.create_task(self.cleanup_old_events())

    def cog_unload(self):
        """Called when the cog is unloaded"""
        # Stop the task if it's running
        if self.check_events.is_running():
            self.check_events.cancel()

    def get_time_provider(self):
        """Get the time provider from the TimeAcceleration cog, or use the default"""
        time_accel_cog = self.bot.get_cog("TimeAcceleration")
        if time_accel_cog and hasattr(time_accel_cog, 'time_provider'):
            return time_accel_cog.time_provider

        # Return a default time provider that just uses the real time
        class DefaultTimeProvider:
            def now(self, tz=None):
                return datetime.now(tz)

        return DefaultTimeProvider()

    async def setup_recurring_events(self):
        """Set up recurring events after bot restart"""
        print("Setting up recurring events...")
        # Load all events
        await self.load_events()
        # Get all recurring events
        recurring_events = {event_id: event for event_id, event in self.events.items()
                            if event.get("recurring")}
        print(f"Found {len(recurring_events)} recurring events")
        # Schedule next occurrences for each recurring event
        for event_id, event in recurring_events.items():
            # Only schedule if the event hasn't happened yet
            event_time_str = event.get("time")
            if event_time_str:
                try:
                    event_time = datetime.strptime(event_time_str, "%Y-%m-%d %H:%M")
                    event_time = event_time.replace(tzinfo=pytz.UTC)
                    now = self.get_time_provider().now(pytz.UTC)

                    # Calculate time difference
                    time_diff = event_time - now
                    # Check if this event already has a message
                    if event.get("message_id"):
                        print(f"Event {event_id} already has a message posted")
                        # Store the last reminder time to prevent duplicate reminders on restart
                        last_reminder_key = f"last_reminder_{event_id}"
                        last_reminder_time = self.events.get(event_id, {}).get(last_reminder_key)
                        # If the event is in the future, schedule its next occurrence
                        if time_diff.total_seconds() > 0:
                            print(f"Scheduling next occurrence for future event {event_id}")
                            self.recurring_tasks[event_id] = self.bot.loop.create_task(
                                self.schedule_next_occurrence(event_id)
                            )
                        # If the event is in the past but less than 2 days ago, wait until 2 days have passed
                        elif time_diff.total_seconds() > -2 * 24 * 60 * 60:
                            print(f"Event {event_id} happened less than 2 days ago, waiting until 2 days have passed")
                            # Check if we've already sent a reminder since the event
                            if last_reminder_time:
                                last_reminder = datetime.strptime(last_reminder_time, "%Y-%m-%d %H:%M")
                                last_reminder = last_reminder.replace(tzinfo=pytz.UTC)
                                # If we've already sent a reminder after the event, don't send another one
                                if last_reminder > event_time:
                                    print(f"Already sent a reminder for event {event_id} after it occurred")
                                    continue

                            wait_time = (2 * 24 * 60 * 60) + time_diff.total_seconds()

                            # Create a task that waits and then schedules the next occurrence
                            async def wait_and_schedule(event_id, wait_time):
                                await asyncio.sleep(wait_time)
                                # Record that we sent a reminder
                                self.events[event_id][f"last_reminder_{event_id}"] = datetime.now(pytz.UTC).strftime(
                                    "%Y-%m-%d %H:%M")
                                await self.save_events(
                                    self.events[event_id].get("guild_id"))  # Save to persist this information
                                await self.schedule_next_occurrence(event_id)

                            # Create and store the task
                            task = asyncio.create_task(wait_and_schedule(event_id, wait_time))
                            self.pending_tasks[event_id] = task
                except Exception as e:
                    print(f"Error scheduling next occurrence for event {event_id}: {e}")
                    import traceback
                    traceback.print_exc()

    def calculate_next_occurrence(self, recurrence_rule, last_occurrence):
        """Calculate the next occurrence based on the recurrence rule."""
        try:
            # Parse the recurrence rule
            rrule_obj = rrulestr(recurrence_rule, dtstart=last_occurrence)

            # Get the next occurrence after now
            now = self.get_time_provider().now(pytz.UTC)

            next_occurrence = rrule_obj.after(now, inc=False)

            return next_occurrence
        except Exception as e:
            print(f"Error calculating next occurrence: {e}")
            import traceback
            traceback.print_exc()
            return None


    async def safe_respond(self, interaction, message, ephemeral=True):
        """Safely respond to an interaction, handling cases where the interaction might have timed out"""
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(message, ephemeral=ephemeral)
            else:
                await interaction.followup.send(message, ephemeral=ephemeral)
        except discord.errors.NotFound:
            # Interaction has expired or webhook is invalid
            print(f"Could not respond to interaction - it may have expired")
        except discord.errors.HTTPException as e:
            print(f"HTTP Exception when responding to interaction: {e}")
        except Exception as e:
            print(f"Error responding to interaction: {e}")

    async def get_event(self, guild_id, event_id):
        """Safely get an event after ensuring events are loaded"""
        await self.load_events(guild_id)
        return self.events.get(event_id)

    def setup_data_storage(self):
        """Set up all necessary data directories and storage"""
        try:
            # Create the main data directory
            os.makedirs(self.data_dir, exist_ok=True)

            # Create the attendance data directory
            attendance_dir = os.path.join(self.data_dir, "attendance")
            os.makedirs(attendance_dir, exist_ok=True)

            # Create the events directory
            events_dir = os.path.join(self.data_dir, "events")
            os.makedirs(events_dir, exist_ok=True)

            # Initialize the attendance tracker
            self.attendance_tracker = AttendanceTracker()

            print("Data storage system initialized successfully")
        except Exception as e:
            print(f"Error setting up data storage: {e}")
            import traceback
            traceback.print_exc()

    def can_join_restricted_role(self, user, role_data):
        """Check if a user can join a restricted role"""
        # If the role isn't restricted, anyone can join
        if not role_data.get("restricted", False):
            return True

        # Check if the role has a required role
        required_role_id = role_data.get("required_role_id")
        if not required_role_id:
            return False

        # Check if the user has the required role
        for role in user.roles:
            if str(role.id) == str(required_role_id):
                return True

        return False

    def get_toggle_lock_key(self, user_id, event_id):
        return f"{user_id}:{event_id}"

    # Helper function for consistent datetime handling
    async def parse_event_time(self, time_str):
        try:
            # Parse the input time string
            naive_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
            # Convert EST to UTC for storage
            est = timezone('US/Eastern')
            est_time = est.localize(naive_time)
            utc_time = est_time.astimezone(pytz.UTC)
            # Return both the datetime object and formatted string
            return utc_time, utc_time.strftime("%Y-%m-%d %H:%M")
        except ValueError as e:
            raise ValueError(f"Invalid time format: {e}")

    async def on_interaction(self, interaction):
        """Handle button interactions for attendance"""
        if not interaction.data or not interaction.data.get("custom_id"):
            return

        custom_id = interaction.data["custom_id"]
        if custom_id.startswith("attendance:"):
            # Parse the custom ID to get event_id and role_id
            parts = custom_id.split(":")
            if len(parts) >= 4 and parts[3] == "toggle":
                event_id = parts[1]
                role_id = parts[2]

                # Handle the role toggle directly
                await self.toggle_role(interaction, event_id, role_id)

    async def cancel_task_safely(self, task_dict, event_id):
        """Safely cancel a task if it exists"""
        if event_id in task_dict:
            task = task_dict[event_id]
            if not task.done() and not task.cancelled():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            del task_dict[event_id]

    def parse_time_input(self, time_str):
        """Parse a time string input and convert to UTC"""
        # Parse the input time string
        naive_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
        # Convert EST to UTC for storage
        est = timezone('US/Eastern')
        est_time = est.localize(naive_time)
        utc_time = est_time.astimezone(pytz.UTC)
        return utc_time

    def format_time_for_display(self, utc_time_str):
        """Format a UTC time string for display using Discord's timestamp feature"""
        try:
            # Parse the UTC time
            utc_time = datetime.strptime(utc_time_str, "%Y-%m-%d %H:%M").replace(tzinfo=pytz.UTC)

            # Get Unix timestamp for Discord's timestamp feature
            unix_timestamp = int(utc_time.timestamp())

            # Format with Discord timestamp (shows in user's local time)
            discord_timestamp = f"<t:{unix_timestamp}:F>"  # F = Full date and time

            # Also add relative time
            relative_time = f"<t:{unix_timestamp}:R>"  # R = Relative time

            return f"{discord_timestamp}\n({relative_time})"
        except Exception as e:
            print(f"Error formatting time: {e}")
            # Fallback to EST formatting
            utc_time = datetime.strptime(utc_time_str, "%Y-%m-%d %H:%M").replace(tzinfo=pytz.UTC)
            est = timezone('US/Eastern')
            est_time = utc_time.astimezone(est)
            return est_time.strftime("%Y-%m-%d %I:%M %p EST")

    async def load_all_events_when_ready(self):
        """Wait until the bot is ready, then load events for all guilds"""
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            try:
                await self.load_events(guild.id)
            except Exception as e:
                print(f"Error loading events for guild {guild.id}: {e}")

        # Check for missing message IDs
        missing_count, total_count = await self.check_event_message_ids()

        # Fix missing message IDs if needed
        if missing_count > 0:
            await self.fix_missing_message_ids()

        # Fix recurring events with missing message IDs
        await self.fix_recurring_events()

        # Start any necessary tasks for loaded events
        if hasattr(self, 'start_tasks_for_loaded_events'):
            await self.start_tasks_for_loaded_events()

    async def check_event_message_ids(self):
        """Check all events for missing message IDs"""
        print("Checking all events for missing message IDs...")
        missing_count = 0
        total_count = 0

        for event_id, event in self.events.items():
            total_count += 1
            if 'message_id' not in event or not event['message_id']:
                missing_count += 1
                print(f"Event {event_id} is missing message_id")
                # Print other event details to help debug
                print(f"  Title: {event.get('title')}")
                print(f"  Guild ID: {event.get('guild_id')}")
                print(f"  Channel ID: {event.get('channel_id')}")

        print(f"Found {missing_count} events with missing message IDs out of {total_count} total events")
        return missing_count, total_count

    async def fix_recurring_events(self):
        """Fix recurring events that are missing message IDs"""
        print("Checking for recurring events with missing message IDs...")
        return 0
        fixed_count = 0
        now = self.get_time_provider().now(pytz.UTC)

        for event_id, event in list(self.events.items()):
            if event.get("recurring", False) and ('message_id' not in event or not event['message_id']):
                print(f"Found recurring event {event_id} with missing message_id")

                if event.get("message_id"):
                    print(f"Event {event_id} already has message_id, skipping fix")
                    continue

                # Check if this event should already be posted (less than 3 days away)
                if event.get("time"):
                    try:
                        event_time = datetime.strptime(event["time"], "%Y-%m-%d %H:%M").replace(tzinfo=pytz.UTC)
                        days_until_event = (event_time - now).days

                        if days_until_event > 3:
                            print(
                                f"Recurring event {event_id} is {days_until_event} days away, scheduling instead of posting now")
                            await self.schedule_event_posting(event_id)
                            continue
                    except Exception as e:
                        print(f"Error parsing time for recurring event {event_id}: {e}")

                # Only create message if event should already be posted
                if 'channel_id' in event and event['channel_id']:
                    try:
                        channel = self.bot.get_channel(int(event['channel_id']))
                        if not channel:
                            print(f"Channel {event['channel_id']} not found for event {event_id}")
                            continue

                        embed = await self.create_event_embed(event_id)
                        view = AttendanceView(self, event_id)
                        message = await channel.send(embed=embed, view=view)

                        event['message_id'] = str(message.id)
                        print(f"Fixed recurring event {event_id} with new message_id: {event['message_id']}")

                        await self.save_events(event['guild_id'])
                        fixed_count += 1
                    except Exception as e:
                        print(f"Error fixing recurring event {event_id}: {e}")
                        import traceback
                        traceback.print_exc()

        print(f"Fixed {fixed_count} recurring events with missing message IDs")
        return fixed_count

    async def fix_missing_message_ids(self):
        """Fix any events with missing message IDs - but only for events that should already be posted"""
        print("Checking for events with missing message IDs...")
        return 0
        fixed_count = 0
        now = self.get_time_provider().now(pytz.UTC)

        for event_id, event in list(self.events.items()):
            if 'message_id' not in event or not event['message_id']:
                print(f"Found event {event_id} with missing message_id")

                if event.get("message_id"):
                    print(f"Event {event_id} already has message_id, skipping fix")
                    continue

                # Check if this event should already be posted (less than 3 days away)
                if event.get("time"):
                    try:
                        event_time = datetime.strptime(event["time"], "%Y-%m-%d %H:%M").replace(tzinfo=pytz.UTC)
                        days_until_event = (event_time - now).days

                        if days_until_event > 3:
                            print(
                                f"Event {event_id} is {days_until_event} days away, scheduling instead of posting now")
                            await self.schedule_event_posting(event_id)
                            continue
                    except Exception as e:
                        print(f"Error parsing time for event {event_id}: {e}")

                # Only create message if event should already be posted
                if 'channel_id' in event and event['channel_id']:
                    try:
                        channel = self.bot.get_channel(int(event['channel_id']))
                        if not channel:
                            print(f"Channel {event['channel_id']} not found for event {event_id}")
                            continue

                        embed = await self.create_event_embed(event_id)
                        view = AttendanceView(self, event_id)
                        message = await channel.send(embed=embed, view=view)

                        event['message_id'] = str(message.id)
                        print(f"Fixed event {event_id} with new message_id: {event['message_id']}")

                        await self.save_events(event['guild_id'])
                        fixed_count += 1
                    except Exception as e:
                        print(f"Error fixing event {event_id}: {e}")
                        import traceback
                        traceback.print_exc()
                else:
                    print(f"Cannot fix event {event_id} - missing channel_id")

        print(f"Fixed {fixed_count} events with missing message IDs")
        return fixed_count

    async def start_tasks_for_loaded_events(self):
        """Start tasks for all loaded events - but don't post messages immediately"""
        now = self.get_time_provider().now(pytz.UTC)

        for event_id, event in self.events.items():
            try:
                # Parse the event time
                event_time_str = event["time"]
                event_time = datetime.strptime(event_time_str, "%Y-%m-%d %H:%M").replace(tzinfo=pytz.UTC)
                time_diff = event_time - now

                # Only schedule tasks, don't post messages
                if event.get("message_id"):
                    # Event already has a message, just schedule remaining tasks
                    if time_diff.total_seconds() > 1800:  # More than 30 minutes away
                        self.reminder_tasks[event_id] = self.bot.loop.create_task(
                            self.send_reminder(event_id, time_diff)
                        )

                    # Schedule cleanup for all events (2 days after event time)
                    cleanup_time = event_time + timedelta(days=2)
                    cleanup_diff = cleanup_time - now
                    if cleanup_diff.total_seconds() > 0:
                        self.cleanup_tasks[event_id] = self.bot.loop.create_task(
                            self.cleanup_event(event_id, cleanup_diff)
                        )
                else:
                    # Event doesn't have a message, schedule it properly
                    await self.schedule_event_posting(event_id)

            except Exception as e:
                print(f"Error processing event {event_id}: {e}")
                import traceback
                traceback.print_exc()

    async def assign_event_role(self, event_id, user_id):
        """Safely assign an event role to a user"""
        event = self.events.get(event_id)
        if not event or not event.get("event_role_id"):
            return False

        guild = self.bot.get_guild(event["guild_id"])
        if not guild:
            return False

        member = guild.get_member(int(user_id))
        if not member:
            return False

        role = guild.get_role(event["event_role_id"])
        if not role:
            return False

        try:
            await member.add_roles(role, reason=f"Signed up for event: {event['title']}")
            if str(user_id) not in event["event_role_users"]:
                event["event_role_users"].append(str(user_id))
            return True
        except Exception as e:
            print(f"Error assigning role: {e}")
            return False

    def cog_unload(self):
        # Cancel all tasks when the cog is unloaded
        self.check_events.cancel()
        for task in self.reminder_tasks.values():
            task.cancel()
        for task in self.cleanup_tasks.values():
            task.cancel()
        for task in self.recurring_tasks.values():
            task.cancel()

    @tasks.loop(minutes=30)
    async def check_events(self):
        """Periodically check all events to ensure they're being handled"""
        try:
            now = self.get_time_provider().now(pytz.UTC)
            print(f"Checking events at {now}")

            for event_id, event in list(self.events.items()):
                try:
                    # Skip events that don't have a time
                    if not event.get("time"):
                        continue

                    # Parse the event time
                    event_time_str = event.get("time")
                    event_time = datetime.strptime(event_time_str, "%Y-%m-%d %H:%M")
                    event_time = event_time.replace(tzinfo=pytz.UTC)

                    # Calculate time difference
                    time_diff = event_time - now

                    # If this is a recurring event
                    if event.get("recurring"):
                        # If the event is more than 2 days in the past and doesn't have a task
                        if time_diff.total_seconds() < -2 * 24 * 60 * 60 and event_id not in self.recurring_tasks:
                            print(f"Event {event_id} is more than 2 days in the past, scheduling next occurrence")
                            self.recurring_tasks[event_id] = self.bot.loop.create_task(
                                self.schedule_next_occurrence(event_id)
                            )
                        # If the event is in the future but doesn't have role removal scheduled
                        elif time_diff.total_seconds() > 0 and f"role_{event_id}" not in self.pending_tasks:
                            # Schedule role removal for 4 hours after the event
                            role_removal_time = event_time + timedelta(hours=4)
                            role_diff = (role_removal_time - now).total_seconds()

                            if role_diff > 0:
                                print(f"Scheduling role removal for event {event_id}")
                                self.pending_tasks[f"role_{event_id}"] = self.bot.loop.create_task(
                                    self.remove_role_after_delay(event_id, role_diff)
                                )

                except Exception as e:
                    print(f"Error checking event {event_id}: {e}")
                    import traceback
                    traceback.print_exc()

        except Exception as e:
            print(f"Error in check_events: {e}")
            import traceback
            traceback.print_exc()

    @check_events.before_loop
    async def before_check_events(self):
        await self.bot.wait_until_ready()

    async def schedule_next_occurrence(self, event_id):
        """Schedule the next occurrence of a recurring event"""
        try:
            print(f"Scheduling next occurrence for event {event_id}")

            # Check if event still exists (it might have been deleted already)
            if event_id not in self.events:
                print(f"Event {event_id} not found in events dictionary, skipping next occurrence")
                return False

            event = self.events[event_id].copy()  # Make a copy before potential deletion

            if not event.get("recurring"):
                print(f"Event {event_id} is not recurring")
                return False

            # Get event details
            event_time_str = event.get("time")
            if not event_time_str:
                print(f"Event {event_id} has no time")
                return False

            event_time = datetime.strptime(event_time_str, "%Y-%m-%d %H:%M").replace(tzinfo=pytz.UTC)
            now = datetime.now(pytz.UTC)

            # Only proceed if event is in the past
            if (event_time - now).total_seconds() >= 0:
                print(f"Event {event_id} is still in the future")
                return False

            # Calculate next occurrence using your rrule method
            recurrence_rule = event.get("recurrence_rule", "FREQ=WEEKLY")
            from dateutil.rrule import rrulestr
            try:
                rrule_str = f"DTSTART:{event_time.strftime('%Y%m%dT%H%M%SZ')}\nRRULE:{recurrence_rule}"
                rule = rrulestr(rrule_str, dtstart=event_time)
                next_occurrence = rule.after(now, inc=False)

                if not next_occurrence:
                    print(f"No future occurrences for event {event_id}")
                    await self.delete_event(event_id)
                    return False

                print(f"Next occurrence for event {event_id}: {next_occurrence}")

                # Store data we need before cleanup
                guild_id = event.get("guild_id")

                # Cancel any running tasks for the old event
                await self.cancel_task_safely(self.reminder_tasks, event_id)
                await self.cancel_task_safely(self.cleanup_tasks, event_id)
                await self.cancel_task_safely(self.recurring_tasks, event_id)
                await self.cancel_task_safely(self.pending_tasks, event_id)

                # Remove Discord roles if applicable
                await self.remove_event_roles(event_id)

                # Delete the Discord message if it exists
                if event.get("message_id") and event.get("channel_id"):
                    try:
                        channel = self.bot.get_channel(int(event["channel_id"]))
                        if channel:
                            message = await channel.fetch_message(int(event["message_id"]))
                            await message.delete()
                            print(f"Deleted message for event {event_id}")
                    except discord.NotFound:
                        print(f"Message for event {event_id} already deleted")
                    except Exception as e:
                        print(f"Error deleting message for event {event_id}: {e}")

                # Delete the Discord thread AND its starter message if it exists
                if event.get("thread_id") and event.get("channel_id"):
                    try:
                        channel = self.bot.get_channel(int(event["channel_id"]))
                        if channel:
                            thread = channel.get_thread(int(event["thread_id"]))
                            if not thread:
                                # Try to fetch the thread if it's not in cache
                                try:
                                    thread = await channel.fetch_thread(int(event["thread_id"]))
                                except:
                                    pass
                            if thread:
                                # Delete the thread first
                                await thread.delete()
                                print(f"Deleted thread for event {event_id}")

                                # Delete the thread starter message if we have its ID
                                if event.get("thread_starter_message_id"):
                                    try:
                                        starter_message = await channel.fetch_message(
                                            int(event["thread_starter_message_id"]))
                                        await starter_message.delete()
                                        print(
                                            f"Deleted thread starter message {event['thread_starter_message_id']} for event {event_id}")
                                    except discord.NotFound:
                                        print(
                                            f"Thread starter message {event['thread_starter_message_id']} already deleted for event {event_id}")
                                    except Exception as e:
                                        print(f"Error deleting thread starter message for event {event_id}: {e}")
                                else:
                                    print(f"No thread starter message ID saved for event {event_id}")
                    except discord.NotFound:
                        print(f"Thread for event {event_id} already deleted")
                    except Exception as e:
                        print(f"Error deleting thread for event {event_id}: {e}")

                # Create new event for next occurrence
                new_event = copy.deepcopy(event)

                new_event["time"] = next_occurrence.strftime("%Y-%m-%d %H:%M")

                # MOVE DUPLICATE CHECK HERE - BEFORE adding to self.events
                print(
                    f"DEBUG: Looking for duplicates of time '{next_occurrence.strftime('%Y-%m-%d %H:%M')}' and title '{event['title']}'")
                print(f"DEBUG: Current events in memory: {list(self.events.keys())}")

                # Check for existing events with the same time
                existing_event_with_same_time = None
                for existing_id, existing_event in self.events.items():
                    print(
                        f"DEBUG: Checking event {existing_id}: time='{existing_event.get('time')}', title='{existing_event.get('title')}'")

                    if (existing_id != event_id and  # Don't compare with the old event we're replacing
                            existing_event.get("time") == next_occurrence.strftime("%Y-%m-%d %H:%M") and
                            existing_event.get("title") == event["title"]):
                        existing_event_with_same_time = existing_id
                        print(f"DEBUG: FOUND DUPLICATE! {existing_event_with_same_time}")
                        break
                    else:
                        print(
                            f"DEBUG: Not a duplicate - time match: {existing_event.get('time') == next_occurrence.strftime('%Y-%m-%d %H:%M')}, title match: {existing_event.get('title') == event['title']}")

                if existing_event_with_same_time:
                    print(f"DEBUG: Event with same time already exists: {existing_event_with_same_time}")
                    print(f"DEBUG: Will remove old event: {event_id}")

                    # Remove the old event from dictionary
                    if event_id in self.events:
                        print(f"DEBUG: Removing old event {event_id} from events dictionary")
                        del self.events[event_id]

                    # Save the changes
                    print(f"DEBUG: Saving events to file...")
                    await self.save_events(guild_id)
                    print(f"DEBUG: Duplicate prevented, not creating new event")
                    return True

                print(f"DEBUG: No duplicate found, proceeding with normal event creation")

                # Generate new ID using your method
                new_id = f"{event['title']}_{len(self.events) + 1}_{new_event['time'].replace(' ', '_').replace(':', '-')}"

                # IMPORTANT: Remove message_id so it doesn't get posted immediately
                if "message_id" in new_event:
                    del new_event["message_id"]
                if "thread_id" in new_event:
                    del new_event["thread_id"]

                # Reset user lists
                for role_id in new_event["roles"]:
                    new_event["roles"][role_id]["users"] = []
                new_event["event_role_users"] = []

                # Check if next occurrence already exists (using your new ID)
                if new_id in self.events:
                    print(f"Next occurrence {new_id} already exists, not creating duplicate")
                    # Remove the old event from dictionary
                    if event_id in self.events:
                        print(f"Removing old event {event_id} from events dictionary")
                        del self.events[event_id]
                    return True


                # Remove the old event from dictionary
                if event_id in self.events:
                    print(f"Removing old event {event_id} from events dictionary")
                    del self.events[event_id]

                # Add the new event to the dictionary
                self.events[new_id] = new_event
                print(f"Creating new event {new_id}")

                # Save the events
                await self.save_events(guild_id)

                # Schedule the new event
                await self.schedule_event_posting(new_id)

                return True


            except Exception as e:
                print(f"Error calculating next occurrence: {e}")
                import traceback
                traceback.print_exc()
                return False

        except Exception as e:
            print(f"Error in schedule_next_occurrence for {event_id}: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def remove_event_roles(self, event_id):
        """Remove all Discord roles associated with an event"""
        try:
            print(f"Removing roles for event {event_id}")

            # Check if the event exists
            if event_id not in self.events:
                print(f"Event {event_id} not found")
                return False

            event = self.events[event_id]
            guild_id = event.get("guild_id")

            if not guild_id:
                print(f"Event {event_id} has no guild_id")
                return False

            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                print(f"Guild {guild_id} not found")
                return False

            # Remove event role from all users if it exists
            if event.get("event_role_id") and event.get("event_role_users"):
                event_role = guild.get_role(int(event.get("event_role_id")))
                if event_role:
                    print(f"Removing event role {event_role.name} from {len(event.get('event_role_users', []))} users")
                    for user_id in event.get("event_role_users", []):
                        try:
                            member = guild.get_member(int(user_id))
                            if member:
                                await member.remove_roles(event_role, reason=f"Event {event['title']} cleanup")
                                print(f"Removed event role from {member.display_name}")
                        except Exception as e:
                            print(f"Error removing event role from user {user_id}: {e}")
                else:
                    print(f"Event role {event.get('event_role_id')} not found")

            # Remove role-specific Discord roles if they exist
            for role_id, role_data in event.get("roles", {}).items():
                if role_data.get("discord_role_id") and role_data.get("users"):
                    discord_role = guild.get_role(int(role_data.get("discord_role_id")))
                    if discord_role:
                        print(f"Removing role {discord_role.name} from {len(role_data.get('users', []))} users")
                        for user_id in role_data.get("users", []):
                            try:
                                member = guild.get_member(int(user_id))
                                if member:
                                    await member.remove_roles(discord_role, reason=f"Event {event['title']} cleanup")
                                    print(f"Removed role {discord_role.name} from {member.display_name}")
                            except Exception as e:
                                print(f"Error removing role from user {user_id}: {e}")
                    else:
                        print(f"Discord role {role_data.get('discord_role_id')} not found")

            return True
        except Exception as e:
            print(f"Error removing event roles: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def remove_role_after_delay(self, event_id, delay):
        """Remove the pingable role after a delay"""
        try:
            await asyncio.sleep(delay)
            event = self.events.get(event_id)
            if not event:
                return

            guild_id = event.get("guild_id")
            role_id = event.get("role_id")  # This seems to be for a pingable role

            if not guild_id or not role_id:
                return

            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                return

            role = guild.get_role(int(role_id))
            if not role:
                return

            # Make the role not mentionable
            await role.edit(mentionable=False)
            print(f"Made role {role.name} not mentionable for event {event_id}")

        except asyncio.CancelledError:
            # Task was cancelled, that's fine
            pass
        except Exception as e:
            print(f"Error removing role for event {event_id}: {e}")
            import traceback
            traceback.print_exc()

    async def delete_embed_after_delay(self, event_id, delay):
        """Delete the event embed after a delay"""
        try:
            await asyncio.sleep(delay)

            event = self.events.get(event_id)
            if not event:
                return

            guild_id = event.get("guild_id")
            channel_id = event.get("channel_id")
            message_id = event.get("message_id")

            if not guild_id or not channel_id or not message_id:
                return

            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                return

            channel = guild.get_channel(int(channel_id))
            if not channel:
                return

            # Remove all Discord roles associated with the event before deleting
            await self.remove_event_roles(event_id)

            try:
                message = await channel.fetch_message(int(message_id))
                await message.delete()
                print(f"Deleted event embed for event {event_id}")
            except discord.NotFound:
                print(f"Event embed for event {event_id} already deleted")

            # DELETE THREAD IF IT EXISTS
            if event.get("thread_id"):
                try:
                    thread = channel.get_thread(int(event["thread_id"]))
                    if not thread:
                        thread = await channel.fetch_thread(int(event["thread_id"]))
                    if thread:
                        await thread.delete()
                        print(f"Deleted thread for event {event_id}")
                except Exception as e:
                    print(f"Error deleting thread for event {event_id}: {e}")

            # If this is a recurring event, schedule the next occurrence
            if event.get("recurring"):
                await self.schedule_next_occurrence(event_id)
            else:
                # If not recurring, remove the event from storage
                del self.events[event_id]
                await self.save_events(guild_id)

        except asyncio.CancelledError:
            # Task was cancelled, that's fine
            pass
        except Exception as e:
            print(f"Error deleting embed for event {event_id}: {e}")
            import traceback
            traceback.print_exc()

    async def post_event_message_now(self, event_id):
        """Post an event message immediately"""
        try:
            if event_id not in self.events:
                print(f"Event {event_id} not found when trying to post message")
                return

            event = self.events[event_id]

            # STRENGTHEN THIS CHECK:
            if event.get("message_id"):
                print(f"Event {event_id} already has message_id {event['message_id']}, skipping post")
                return

            # ADD IMMEDIATE LOCK TO PREVENT DOUBLE POSTING:
            if hasattr(self, '_posting_events'):
                if event_id in self._posting_events:
                    print(f"Event {event_id} is already being posted, skipping")
                    return
            else:
                self._posting_events = set()

            self._posting_events.add(event_id)

            try:
                # Get the channel
                channel_id = event.get("channel_id")
                if not channel_id:
                    print(f"Event {event_id} has no channel_id")
                    return

                channel = self.bot.get_channel(int(channel_id))
                if not channel:
                    print(f"Channel {channel_id} not found for event {event_id}")
                    return

                # Create the embed and view
                embed = await self.create_event_embed(event_id)
                view = AttendanceView(self, event_id)

                # Check for staff ping
                content = None
                if event.get("staff_ping_role_id"):
                    # Use channel.guild instead of getting guild separately
                    role = channel.guild.get_role(int(event["staff_ping_role_id"]))
                    if role:
                        content = role.mention
                        print(f"Adding staff ping for event {event_id}: {role.name}")
                    else:
                        print(f"Staff ping role {event['staff_ping_role_id']} not found for event {event_id}")

                # Send the message (MOVED OUT OF THE IF BLOCK)
                message = await channel.send(content=content, embed=embed, view=view)

                # Update the event with message ID only
                self.events[event_id]["message_id"] = str(message.id)
                await self.save_events(event.get("guild_id"))

                print(f"Posted message for event {event_id}: {message.id}")

                # Schedule reminder and cleanup
                await self.schedule_event_tasks(event_id)

            finally:
                # Remove from posting set
                self._posting_events.discard(event_id)

        except Exception as e:
            print(f"Error posting event message for {event_id}: {e}")
            import traceback
            traceback.print_exc()
            # Make sure to clean up the lock
            if hasattr(self, '_posting_events'):
                self._posting_events.discard(event_id)

    async def post_recurring_event(self, event_id, time_diff):
        """Post a recurring event when it's time"""
        try:
            # Get the event
            event = self.events.get(event_id)
            if not event:
                print(f"Event {event_id} not found")
                return

            # Get the event time
            event_time_str = event.get("time")
            if not event_time_str:
                print(f"Event {event_id} has no time")
                return

            # Parse the event time
            event_time = datetime.strptime(event_time_str, "%Y-%m-%d %H:%M")
            event_time = event_time.replace(tzinfo=pytz.UTC)

            # Calculate when to post (3 days before the event)
            now = self.get_time_provider().now(pytz.UTC)

            time_to_event = event_time - now

            # Wait until it's time to post the event (3 days before the event date)
            posting_delay = time_to_event.total_seconds() - (3 * 24 * 60 * 60)  # 3 days in seconds
            if posting_delay > 0:
                print(f"Waiting {posting_delay} seconds to post event {event_id} (3 days before it occurs)")
                await asyncio.sleep(posting_delay)

            # Check if the event still exists
            if event_id not in self.events:
                return
            event = self.events[event_id]

            # Check if the message has already been posted
            if event.get("message_id"):
                print(f"Event {event_id} already has a message, skipping post")
                return

            # Check if a similar event already exists
            event_time_str = event["time"]
            event_title = event["title"]
            duplicate_found = False
            for existing_id, existing_event in self.events.items():
                if existing_id != event_id and existing_event.get("title") == event_title and existing_event.get(
                        "time") == event_time_str:
                    print(f"Found duplicate event {existing_id} with same title and time, skipping creation")
                    duplicate_found = True
                    break

            if duplicate_found:
                # Delete this duplicate event
                del self.events[event_id]
                await self.save_events(event["guild_id"])
                return

            # Create the embed and view
            embed = await self.create_event_embed(event_id)
            view = AttendanceView(self, event_id)

            # Send the message
            channel = self.bot.get_channel(int(event["channel_id"]))
            if not channel:
                print(f"Channel {event['channel_id']} not found for recurring event {event_id}")
                return

            try:
                # Check for staff ping
                content = None
                if event.get("staff_ping_role_id"):
                    guild = self.bot.get_guild(int(event["guild_id"]))
                    if guild:
                        role = guild.get_role(int(event["staff_ping_role_id"]))
                        if role:
                            content = role.mention

                message = await channel.send(content=content, embed=embed, view=view)
                event["message_id"] = message.id
                # Save the updated event
                await self.save_events(event["guild_id"], update_message=False)

                # Schedule reminder and cleanup for the new event
                event_time_str = event["time"]
                event_time = datetime.strptime(event_time_str, "%Y-%m-%d %H:%M").replace(tzinfo=pytz.UTC)
                reminder_diff = event_time - datetime.now(pytz.UTC)
                if reminder_diff.total_seconds() > 1800:  # Only schedule if more than 30 minutes away
                    self.reminder_tasks[event_id] = self.bot.loop.create_task(
                        self.send_reminder(event_id, reminder_diff)
                    )

                # Clean up 2 days after the event
                cleanup_time = event_time + timedelta(days=2)
                cleanup_diff = cleanup_time - datetime.now(pytz.UTC)
                self.cleanup_tasks[event_id] = self.bot.loop.create_task(
                    self.cleanup_event(event_id, cleanup_diff)
                )

                # Schedule the next occurrence
                await self.schedule_next_occurrence(event_id)
            except Exception as e:
                print(f"Error posting recurring event {event_id}: {e}")
                import traceback
                traceback.print_exc()
        except Exception as e:
            print(f"Error in post_recurring_event for {event_id}: {e}")
            import traceback
            traceback.print_exc()

    async def send_reminder(self, event_id, time_diff):
        """Send a reminder for an event"""
        try:
            # Wait until 30 minutes before the event
            reminder_time = time_diff.total_seconds() - 1800  # 30 minutes in seconds
            print(f"Scheduling reminder for event {event_id} in {reminder_time} seconds")
            if reminder_time > 0:
                await asyncio.sleep(reminder_time)

            print(f"Sending reminder for event {event_id}")

            # Check if the event still exists
            event = self.events.get(event_id)
            if not event:
                print(f"Event {event_id} no longer exists")
                return

            # Check if we've already sent a reminder for this event
            last_reminder_key = f"last_reminder_{event_id}"
            if last_reminder_key in event:
                try:
                    event_time = datetime.strptime(event.get("time"), "%Y-%m-%d %H:%M").replace(tzinfo=pytz.UTC)
                    last_reminder_time = datetime.strptime(event[last_reminder_key], "%Y-%m-%d %H:%M")
                    last_reminder_time = last_reminder_time.replace(tzinfo=pytz.UTC)
                    # If we've already sent a reminder after the event was created, don't send another one
                    if last_reminder_time > event_time - timedelta(hours=1):  # Within 1 hour of event time
                        print(f"Already sent a reminder for event {event_id} recently")
                        return
                except Exception as e:
                    print(f"Error checking last reminder time: {e}")
                    # Continue with sending the reminder

            # Get the guild and channel
            guild = self.bot.get_guild(int(event["guild_id"]))
            if not guild:
                print(f"Guild {event['guild_id']} not found for event {event_id}")
                return

            channel = guild.get_channel(int(event["channel_id"]))
            if not channel:
                print(f"Channel {event['channel_id']} not found for event {event_id}")
                return

            # Get the message
            try:
                message = await channel.fetch_message(int(event["message_id"]))
                print(f"Found message for event {event_id}")
            except Exception as e:
                print(f"Error fetching message for event {event_id}: {e}")
                return

            # Always create a NEW thread for each event occurrence
            thread = None
            try:
                print(f"Creating new thread for event {event_id}")
                thread = await message.create_thread(
                    name=f"Discussion: {event['title']} - {event.get('time', '')}",
                    auto_archive_duration=1440  # 24 hours
                )
                # Save the thread ID to the event data
                self.events[event_id]["thread_id"] = str(thread.id)  # Convert to string for consistency
                await self.save_events(int(event["guild_id"]))
                print(f"Thread created for event {event_id}: {thread.id}")
            except Exception as e:
                print(f"Error creating thread for event {event_id}: {e}")
                return

            # Format the reminder message
            title = event.get('title', 'Untitled Event')
            location = event.get('location', 'Not specified')

            # Parse the event time
            event_time_str = event.get('time', '')
            try:
                event_time = datetime.strptime(event_time_str, "%Y-%m-%d %H:%M").replace(tzinfo=pytz.UTC)
                # Format as Discord timestamp for local time conversion
                # This will show the time in each user's local timezone
                discord_timestamp = f"<t:{int(event_time.timestamp())}:F>"
                start_time = discord_timestamp
            except ValueError:
                start_time = event_time_str

            # Build the reminder message
            reminder_message = "Look alive! We start in 30 minutes!\n\n"
            reminder_message += f"{title}\n"
            reminder_message += f"Location: {location}\n"
            reminder_message += f"Start time: {start_time}\n\n"

            # Add pings section
            pings = []

            # First add the pingable role if it exists
            if event.get("event_role_id"):
                role = guild.get_role(int(event["event_role_id"]))
                if role:
                    pings.append(role.mention)

            # Then add individual user pings
            for role_id, role_data in event["roles"].items():
                for user_id in role_data.get("users", []):
                    pings.append(f"<@{user_id}>")

            # Add the pings to the message if there are any
            if pings:
                reminder_message += " ".join(pings)

            # Send the reminder in the thread
            try:
                await thread.send(reminder_message)
                print(f"Sent reminder for event {event_id} in thread")

                # Record that we sent a reminder
                self.events[event_id][f"last_reminder_{event_id}"] = datetime.now(pytz.UTC).strftime("%Y-%m-%d %H:%M")
                await self.save_events(int(event["guild_id"]))

            except Exception as e:
                print(f"Error sending reminder in thread for event {event_id}: {e}")

        except asyncio.CancelledError:
            # Task was cancelled, that's fine
            print(f"Reminder task for event {event_id} was cancelled")
        except Exception as e:
            print(f"Unexpected error in send_reminder for event {event_id}: {e}")
            import traceback
            traceback.print_exc()

    async def cleanup_event(self, event_id, time_diff):
        """Clean up an event after it's over"""
        try:
            # The time_diff already includes the 2-day delay from schedule_event_tasks
            cleanup_delay = time_diff.total_seconds()
            if cleanup_delay > 0:
                print(f"Scheduling cleanup for event {event_id} in {cleanup_delay} seconds")
                await asyncio.sleep(cleanup_delay)

            print(f"🧹 Starting cleanup for event {event_id}")

            # Check if the event still exists
            if event_id not in self.events:
                print(f"Event {event_id} no longer exists, skipping cleanup.")
                return

            event = self.events[event_id]

            # Remove all Discord roles associated with the event
            await self.remove_event_roles(event_id)

            # Delete the event message if it exists
            if "message_id" in event and "channel_id" in event:
                try:
                    channel = self.bot.get_channel(int(event.get("channel_id")))
                    if channel:
                        try:
                            message = await channel.fetch_message(int(event.get("message_id")))
                            await message.delete()
                            print(f"Deleted message for event {event_id}")
                        except discord.NotFound:
                            print(f"Message for event {event_id} already deleted")
                except Exception as e:
                    print(f"Error deleting message for event {event_id}: {e}")

            # Delete the thread if it exists
            if "thread_id" in event and "channel_id" in event:
                try:
                    channel = self.bot.get_channel(int(event.get("channel_id")))
                    if channel:
                        thread = channel.get_thread(int(event.get("thread_id")))
                        if thread:
                            await thread.delete()
                            print(f"Deleted thread for event {event_id}")
                except Exception as e:
                    print(f"Error deleting thread for event {event_id}: {e}")

            # Handle recurring vs non-recurring events
            if event.get("recurring"):
                print(f"Event {event_id} is recurring, scheduling next occurrence")
                # For recurring events, schedule the next occurrence
                await self.schedule_next_occurrence(event_id)
            else:
                print(f"Event {event_id} is not recurring, removing from storage")
                # For non-recurring events, just delete
                del self.events[event_id]
                await self.save_events(event.get("guild_id"))

            # Clean up the cleanup task
            if event_id in self.cleanup_tasks:
                del self.cleanup_tasks[event_id]

            print(f"✅ Cleanup completed for event {event_id}")

        except asyncio.CancelledError:
            print(f"Cleanup task for event {event_id} was cancelled")
        except Exception as e:
            print(f"Error during cleanup of event {event_id}: {e}")
            import traceback
            traceback.print_exc()

    async def cleanup_old_events(self):
        """Clean up old events on startup"""
        try:
            now = self.get_time_provider().now(pytz.UTC)
            print(f"Cleaning up old events at {now}")
            cleanup_count = 0
            next_occurrence_count = 0

            # Create a copy of the events list to avoid modification during iteration
            events_to_process = list(self.events.items())

            for event_id, event in events_to_process:
                try:
                    # Double-check the event still exists (in case another process deleted it)
                    if event_id not in self.events:
                        print(f"Event {event_id} was already deleted, skipping")
                        continue

                    # Skip events that don't have a time
                    if not event.get("time"):
                        continue

                    # Parse the event time
                    event_time_str = event.get("time")
                    event_time = datetime.strptime(event_time_str, "%Y-%m-%d %H:%M")
                    event_time = event_time.replace(tzinfo=pytz.UTC)

                    # Calculate time difference
                    time_diff = event_time - now

                    # If this is a non-recurring event that's more than 2 days old
                    if not event.get("recurring") and time_diff.total_seconds() < -2 * 24 * 60 * 60:
                        print(f"Cleaning up old non-recurring event: {event_id}")
                        if await self.delete_event(event_id):
                            cleanup_count += 1

                    # If this is a recurring event that's more than 2 days old
                    elif event.get("recurring") and time_diff.total_seconds() < -2 * 24 * 60 * 60:
                        print(f"Scheduling next occurrence for old recurring event: {event_id}")
                        await self.schedule_next_occurrence(event_id)
                        next_occurrence_count += 1

                    # If this is a future event, schedule its cleanup
                    elif time_diff.total_seconds() > 0:
                        cleanup_time = event_time + timedelta(days=2)
                        cleanup_diff = cleanup_time - now
                        if cleanup_diff.total_seconds() > 0:
                            print(f"Scheduling cleanup for future event {event_id}")
                            self.cleanup_tasks[event_id] = self.bot.loop.create_task(
                                self.cleanup_event(event_id, time_diff)
                            )

                except Exception as e:
                    print(f"Error processing event {event_id} during cleanup: {e}")
                    import traceback
                    traceback.print_exc()

            print(
                f"Cleanup completed: {cleanup_count} events cleaned up, {next_occurrence_count} recurring events scheduled")

        except Exception as e:
            print(f"Error during cleanup_old_events: {e}")
            import traceback
            traceback.print_exc()

    async def cleanup_old_events_on_startup(self):
        """Clean up old events for all guilds on bot startup"""
        print("Running automatic cleanup on startup...")

        try:
            # Get all guild IDs that have events loaded
            guild_ids = set()

            # Get guild IDs from currently loaded events
            for event_id, event in self.events.items():
                guild_id = event.get("guild_id")
                if guild_id:
                    guild_ids.add(guild_id)

            # Check the correct events directory structure
            events_dir = os.path.join("data", "events")
            if os.path.exists(events_dir):
                print(f"Checking events directory: {events_dir}")
                for filename in os.listdir(events_dir):
                    if filename.startswith("events_") and filename.endswith(".json"):
                        guild_id_str = filename.replace("events_", "").replace(".json", "")
                        try:
                            guild_id = int(guild_id_str)
                            guild_ids.add(guild_id)
                            print(f"Found event file for guild {guild_id}: {filename}")
                        except ValueError:
                            print(f"Could not parse guild ID from filename: {filename}")
                            continue
            else:
                print(f"Events directory does not exist: {events_dir}")

            # Also check data directory (legacy location)
            data_dir = "data"
            if os.path.exists(data_dir):
                print(f"Checking data directory: {data_dir}")
                for filename in os.listdir(data_dir):
                    if filename.startswith("events_") and filename.endswith(".json"):
                        guild_id_str = filename.replace("events_", "").replace(".json", "")
                        try:
                            guild_id = int(guild_id_str)
                            guild_ids.add(guild_id)
                            print(f"Found event file for guild {guild_id}: {filename}")
                        except ValueError:
                            print(f"Could not parse guild ID from filename: {filename}")
                            continue

            print(f"Found event files for {len(guild_ids)} guilds: {guild_ids}")

            # Get current time for debugging
            now = self.get_time_provider().now(pytz.UTC)
            print(f"Current time: {now}")
            print(f"Looking for events older than: {now - timedelta(days=2)}")

            total_cleaned = 0
            for guild_id in guild_ids:
                try:
                    print(f"Cleaning up events for guild {guild_id}")

                    # Load events for this guild
                    await self.load_events(guild_id)

                    events_to_cleanup = []

                    # Find old events for this guild
                    for event_id, event in list(self.events.items()):
                        if event.get("guild_id") != guild_id:
                            continue

                        try:
                            if not event.get("time"):
                                print(f"Event {event_id} has no time, skipping")
                                continue

                            event_time_str = event.get("time")
                            event_time = datetime.strptime(event_time_str, "%Y-%m-%d %H:%M")
                            event_time = event_time.replace(tzinfo=pytz.UTC)
                            time_since_event = now - event_time

                            print(
                                f"Event {event_id}: time={event_time}, age={time_since_event.total_seconds() / 3600:.1f} hours")

                            # Clean up events older than 2 days (172800 seconds)
                            if time_since_event.total_seconds() > 2 * 24 * 60 * 60:
                                print(f"Event {event_id} is old enough for cleanup")
                                events_to_cleanup.append(event_id)
                            else:
                                print(f"Event {event_id} is not old enough yet")

                        except Exception as e:
                            print(f"Error analyzing event {event_id}: {e}")

                    print(f"Found {len(events_to_cleanup)} events to cleanup for guild {guild_id}")

                    # Clean up the old events
                    cleaned_count = 0
                    for event_id in events_to_cleanup:
                        try:
                            if event_id in self.events:
                                event = self.events[event_id]

                                print(f"Cleaning up old event: {event.get('title', event_id)}")

                                # Remove roles
                                await self.remove_event_roles(event_id)

                                # Delete message if it exists
                                if "message_id" in event and "channel_id" in event:
                                    try:
                                        guild = self.bot.get_guild(guild_id)
                                        if guild:
                                            channel = guild.get_channel(int(event.get("channel_id")))
                                            if channel:
                                                try:
                                                    message = await channel.fetch_message(int(event.get("message_id")))
                                                    await message.delete()
                                                    print(f"Deleted message for event {event_id}")
                                                except discord.NotFound:
                                                    print(f"Message already deleted for event {event_id}")
                                    except Exception as e:
                                        print(f"Error deleting message for event {event_id}: {e}")

                                # Handle based on type
                                if event.get("recurring"):
                                    print(f"Scheduling next occurrence for recurring event {event_id}")
                                    await self.schedule_next_occurrence(event_id)
                                else:
                                    print(f"Deleting non-recurring event {event_id}")
                                    del self.events[event_id]

                                cleaned_count += 1

                        except Exception as e:
                            print(f"Error cleaning up event {event_id}: {e}")

                    if cleaned_count > 0:
                        await self.save_events(guild_id)
                        total_cleaned += cleaned_count
                        print(f"Cleaned up {cleaned_count} events for guild {guild_id}")

                except Exception as e:
                    print(f"Error cleaning up guild {guild_id}: {e}")

            print(f"Startup cleanup completed. Total events cleaned: {total_cleaned}")

        except Exception as e:
            print(f"Error in startup cleanup: {e}")
            import traceback
            traceback.print_exc()

    async def save_events(self, guild_id, update_message=False):
        """Save events to the data directory"""
        try:
            guild_id = str(guild_id)
            # Find all events for this guild
            guild_events = {}
            event_count = 0

            for event_id, event in self.events.items():
                if str(event.get("guild_id")) == guild_id:
                    guild_events[event_id] = event
                    event_count += 1

                    # Debug output for message_id
                    if "message_id" in event:
                        print(
                            f"Event {event.get('title', event_id)} has message_id: {event['message_id']} before saving")
                    else:
                        print(f"WARNING: Event {event.get('title', event_id)} is missing message_id before saving")

            print(f"Saving {event_count} events for guild {guild_id}")

            # Ensure the events directory exists
            os.makedirs(os.path.join(self.data_dir, "events"), exist_ok=True)

            # Save the events to a file
            events_file = os.path.join(self.data_dir, "events", f"events_{guild_id}.json")

            # Create a backup of the existing file if it exists
            if os.path.exists(events_file):
                backup_file = os.path.join(self.data_dir, "events", f"events_{guild_id}_backup.json")
                try:
                    shutil.copy2(events_file, backup_file)
                    print(f"Created backup at: {backup_file}")
                except Exception as e:
                    print(f"Error creating backup: {e}")

            # Save the events
            with open(events_file, "w") as f:
                json.dump(guild_events, f, indent=4)

            print(f"Successfully saved events for guild {guild_id}")

            # Verify the file was saved correctly
            if os.path.exists(events_file):
                file_size = os.path.getsize(events_file)
                print(f"Verified file exists with size: {file_size} bytes")

                # Verify message_ids were saved correctly
                for event_id, event in guild_events.items():
                    if "message_id" in event:
                        print(
                            f"Verified saved event {event.get('title', event_id)} has message_id: {event['message_id']}")
                    else:
                        print(f"WARNING: Event {event.get('title', event_id)} is missing message_id after saving")

            # Update event messages if requested (but this should rarely be used)
            if update_message:
                for event_id, event in guild_events.items():
                    await self.update_event_message(event_id)

            return True
        except Exception as e:
            print(f"Error saving events: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def repair_events_file(self, guild_id):
        """Repair the events file if it's corrupted or empty"""
        events_file = os.path.join(self.data_dir, "events", f"events_{guild_id}.json")

        # Check if file exists but is empty or corrupted
        if os.path.exists(events_file):
            try:
                with open(events_file, "r") as f:
                    content = f.read().strip()

                    # FIXED: Only repair if truly empty or whitespace
                    if not content:
                        # File is completely empty
                        with open(events_file, "w") as f:
                            json.dump({}, f)
                        print(f"Repaired empty events file for guild {guild_id}")
                    else:
                        # Try to parse the JSON
                        try:
                            data = json.loads(content)
                            # ADDED: Check if it's actually empty JSON
                            if data == {}:
                                print(f"File data/events/events_{guild_id}.json contains empty JSON object")
                            else:
                                print(f"File data/events/events_{guild_id}.json contains {len(data)} events")
                        except json.JSONDecodeError:
                            # File is corrupted, create a new one
                            print(f"JSON decode error in events file for guild {guild_id}, repairing...")
                            with open(events_file, "w") as f:
                                json.dump({}, f)
                            print(f"Repaired corrupted events file for guild {guild_id}")
            except Exception as e:
                print(f"Error checking events file for guild {guild_id}: {e}")
        else:
            # Create the directory if it doesn't exist
            os.makedirs(os.path.dirname(events_file), exist_ok=True)
            # Create a new file
            with open(events_file, "w") as f:
                json.dump({}, f)
            print(f"Created new events file for guild {guild_id}")

    async def delete_event(self, event_id):
        """Delete an event safely"""
        try:
            # Check if the event exists before trying to delete it
            if event_id not in self.events:
                print(f"Event {event_id} not found in events dictionary, skipping deletion")
                return True  # Return True since the event is already gone

            event = self.events[event_id]

            # Cancel any running tasks for this event
            await self.cancel_task_safely(self.reminder_tasks, event_id)
            await self.cancel_task_safely(self.cleanup_tasks, event_id)
            await self.cancel_task_safely(self.recurring_tasks, event_id)
            await self.cancel_task_safely(self.pending_tasks, event_id)

            # Remove Discord roles if applicable
            await self.remove_event_roles(event_id)

            # Delete the message if it exists
            if event.get("message_id") and event.get("channel_id"):
                try:
                    channel = self.bot.get_channel(int(event["channel_id"]))
                    if channel:
                        message = await channel.fetch_message(int(event["message_id"]))
                        await message.delete()
                        print(f"Deleted message for event {event_id}")
                except discord.NotFound:
                    print(f"Message for event {event_id} already deleted")
                except Exception as e:
                    print(f"Error deleting message for event {event_id}: {e}")

            # Delete the thread if it exists
            if event.get("thread_id") and event.get("channel_id"):
                try:
                    channel = self.bot.get_channel(int(event["channel_id"]))
                    if channel:
                        thread = channel.get_thread(int(event["thread_id"]))
                        if thread:
                            await thread.delete()
                            print(f"Deleted thread for event {event_id}")
                except Exception as e:
                    print(f"Error deleting thread for event {event_id}: {e}")

            # Finally, remove from events dictionary (with another safety check)
            if event_id in self.events:
                del self.events[event_id]
                print(f"Removed event {event_id} from events dictionary")

            # Save the updated events
            await self.save_events(event.get("guild_id"))

            return True

        except Exception as e:
            print(f"Error deleting event {event_id}: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def load_events(self, guild_id=None):
        """Load events from the data directory"""
        try:
            if guild_id is None:
                print("Loading all events in attendance cog...")
                self.events = {}
                total_events = 0
                # Ensure the events directory exists
                os.makedirs(os.path.join(self.data_dir, "events"), exist_ok=True)
                # Get all event files
                event_files = glob.glob(os.path.join(self.data_dir, "events", "events_*.json"))
                for event_file in event_files:
                    try:
                        # Extract guild ID from filename
                        match = re.search(r"events_(\d+)\.json", os.path.basename(event_file))
                        if match:
                            file_guild_id = match.group(1)
                            # Repair this file if needed
                            #await self.repair_events_file(file_guild_id)

                            # Load events for this guild
                            with open(event_file, "r") as f:
                                file_content = f.read().strip()
                                if not file_content or file_content == "{}":
                                    print(f"File {event_file} contains empty JSON object")
                                    continue
                                guild_events = json.loads(file_content)
                            # Check if guild_events is empty
                            if not guild_events:
                                print(f"No events found in {event_file}")
                                continue
                            # Add events to the main events dictionary
                            for event_id, event_data in guild_events.items():
                                self.events[event_id] = event_data
                                total_events += 1
                            print(f"Loaded {len(guild_events)} events for guild {file_guild_id}")
                    except Exception as e:
                        print(f"Error loading events from {event_file}: {e}")
                        import traceback
                        traceback.print_exc()
                print(f"Loaded a total of {total_events} events")
                print("Events loaded successfully")
                return True
            else:
                # Load events for a specific guild
                guild_id = str(guild_id)

                # Repair the events file if needed
                await self.repair_events_file(guild_id)

                events_file = os.path.join(self.data_dir, "events", f"events_{guild_id}.json")
                if os.path.exists(events_file):
                    try:
                        with open(events_file, "r") as f:
                            file_content = f.read().strip()
                            if not file_content or file_content == "{}":
                                print(f"File {events_file} contains empty JSON object")
                                return True
                            guild_events = json.loads(file_content)
                        # Check if guild_events is empty
                        if not guild_events:
                            print(f"No events found in {events_file}")
                            return True
                        # Add events to the main events dictionary
                        for event_id, event_data in guild_events.items():
                            self.events[event_id] = event_data
                        print(f"Loaded {len(guild_events)} events for guild {guild_id}")
                        return True
                    except Exception as e:
                        print(f"Error loading events for guild {guild_id}: {e}")
                        import traceback
                        traceback.print_exc()
                        return False
                else:
                    print(f"No events file found for guild {guild_id}")
                    return True  # Return True since this isn't an error
        except Exception as e:
            print(f"Error loading events: {e}")
            import traceback
            traceback.print_exc()
            return False

    def format_time_for_user(self, time_str):
        """Format a UTC time string to a user-friendly format with Discord timestamp"""
        try:
            # Parse the UTC time
            utc_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M").replace(tzinfo=pytz.UTC)
            # Get Unix timestamp for Discord's timestamp feature
            unix_timestamp = int(utc_time.timestamp())
            # Format with Discord timestamp (shows in user's local time)
            discord_timestamp = f"<t:{unix_timestamp}:F>"  # F = Full date and time
            # Also add relative time
            relative_time = f"<t:{unix_timestamp}:R>"  # R = Relative time
            return f"{discord_timestamp}\n({relative_time})"
        except Exception as e:
            print(f"Error formatting time: {e}")
            return time_str

    async def create_event_embed(self, event_id):
        """Create an embed for an event"""
        event = self.events[event_id]

        # Get the event time string
        event_time_str = event.get("time", "Unknown")

        # Format the time using Discord's timestamp feature for local time display
        try:
            event_time = datetime.strptime(event_time_str, "%Y-%m-%d %H:%M").replace(tzinfo=pytz.UTC)
            # Get Unix timestamp for Discord's timestamp feature
            unix_timestamp = int(event_time.timestamp())
            # Format with Discord timestamp (shows in user's local time)
            time_str = f"<t:{unix_timestamp}:F>\n(<t:{unix_timestamp}:R>)"  # F = Full date and time, R = Relative time
        except ValueError:
            time_str = "Unknown Time"

        embed = discord.Embed(
            title=event["title"],
            description=event["description"],
            color=0x87CEEB  # Pastel blue color
        )

        embed.add_field(name="Time", value=time_str, inline=True)
        embed.add_field(name="Location", value=event["location"], inline=True)

        # Add fields for each role
        for role_id, role_data in event.get("roles", {}).items():
            role_name = role_data.get("name")
            if not role_name:  # Skip roles with no name
                continue

            # Get the users in this role
            users = role_data.get("users", [])
            user_count = len(users)

            # Create a list of user mentions
            user_list = []
            for user_id in users:
                try:
                    guild = self.bot.get_guild(int(event["guild_id"]))
                    if guild:
                        member = guild.get_member(int(user_id))
                        if member:
                            user_list.append(member.mention)
                        else:
                            user_list.append(f"<@{user_id}>")  # Fallback to mention format
                    else:
                        user_list.append(f"<@{user_id}>")  # Fallback to mention format
                except Exception as e:
                    print(f"Error getting member {user_id}: {e}")
                    user_list.append(f"<@{user_id}>")  # Fallback to mention format

            # Format the field value
            if user_list:
                # Join the user mentions with newlines, limit to 10 users to avoid hitting embed limits
                displayed_users = user_list[:10]
                remaining = user_count - 10 if user_count > 10 else 0

                value = "\n".join(displayed_users)
                if remaining > 0:
                    value += f"\n*...and {remaining} more*"
            else:
                value = "*No users*"

            # Add role limit if applicable
            if "limit" in role_data and role_data["limit"] > 0:
                field_name = f"{role_name} ({user_count}/{role_data['limit']})"
            else:
                field_name = f"{role_name} ({user_count})"

            # Add restricted indicator if applicable
            if role_data.get("restricted", False):
                field_name += " 🔒"

            embed.add_field(name=field_name, value=value, inline=False)

        # Add footer with event ID for reference
        # Build footer text
        footer_parts = []

        # Add creator (get the actual username instead of mention)
        if event.get("created_by"):
            try:
                user = self.bot.get_user(int(event["created_by"]))
                if user:
                    footer_parts.append(f"Created by: {user.display_name}")
                else:
                    footer_parts.append(f"Created by: User ID {event['created_by']}")
            except:
                footer_parts.append(f"Created by: User ID {event['created_by']}")

        # Add recurring info
        if event.get("recurring", False):
            interval = event.get("recurring_interval", 1)
            if interval == 1:
                footer_parts.append("Recurring: Weekly")
            elif interval == 2:
                footer_parts.append("Recurring: Biweekly")
            elif interval == 4:
                footer_parts.append("Recurring: Monthly")
            else:
                footer_parts.append(f"Recurring: Every {interval} weeks")
        else:
            footer_parts.append("Recurring: No")

        # Join all parts with " | "
        footer_text = " | ".join(footer_parts)
        embed.set_footer(text=footer_text)

        return embed

    async def setup_persistent_views(self):
        """Set up persistent views for all events"""
        try:
            print("Setting up persistent views for attendance...")
            # Load events first
            await self.load_events()

            # Create a view for each event
            view_count = 0
            for event_id, event in list(self.events.items()):
                try:
                    # Check if the event has a message_id and channel_id
                    if "message_id" in event and "channel_id" in event and event["message_id"]:
                        # Only set up view for existing messages, don't create new ones
                        view = AttendanceView(self, event_id)
                        self.bot.add_view(view, message_id=int(event["message_id"]))
                        view_count += 1
                        print(f"Set up persistent view for event {event_id} with message {event['message_id']}")
                    else:
                        # For events without message_id, schedule them properly instead of posting immediately
                        await self.schedule_event_posting(event_id)

                except Exception as e:
                    print(f"Error setting up view for event {event_id}: {e}")

            print(f"Attendance views set up successfully: {view_count} views")
            print("Running startup cleanup of old events...")
            await self.cleanup_old_events_on_startup()

        except Exception as e:
            print(f"Error setting up persistent views: {e}")
            import traceback
            traceback.print_exc()

    async def schedule_event_posting(self, event_id):
        """Schedule an event to be posted 3 days before it occurs"""
        try:
            if event_id not in self.events:
                return

            event = self.events[event_id]

            # Skip if event already has a message
            if event.get("message_id"):
                print(f"Event {event_id} already has message_id {event['message_id']}, skipping scheduling")
                return

            # Parse event time
            event_time_str = event.get("time")
            if not event_time_str:
                print(f"Event {event_id} has no time")
                return

            event_time = datetime.strptime(event_time_str, "%Y-%m-%d %H:%M").replace(tzinfo=pytz.UTC)
            now = self.get_time_provider().now(pytz.UTC)

            # Calculate when to post (3 days before event)
            post_time = event_time - timedelta(days=3)
            time_until_post = post_time - now

            if time_until_post.total_seconds() > 0:
                # Schedule posting for 3 days before
                print(
                    f"Scheduling event {event_id} to post in {time_until_post.total_seconds()} seconds (3 days before event)")
                self.recurring_tasks[event_id] = self.bot.loop.create_task(
                    self.post_event_after_delay(event_id, time_until_post.total_seconds())
                )
            elif (event_time - now).total_seconds() > 0:
                # Event is less than 3 days away but still in future - post now
                print(f"Event {event_id} is less than 3 days away, posting immediately")
                await self.post_event_message_now(event_id)
            else:
                # Event is in the past - handle cleanup or next occurrence
                print(f"Event {event_id} is in the past")
                if event.get("recurring"):
                    await self.schedule_next_occurrence(event_id)

        except Exception as e:
            print(f"Error scheduling event posting for {event_id}: {e}")
            import traceback
            traceback.print_exc()

    async def post_event_after_delay(self, event_id, delay_seconds):
        """Post an event after a specific delay"""
        try:
            await asyncio.sleep(delay_seconds)
            await self.post_event_message_now(event_id)
        except asyncio.CancelledError:
            print(f"Event posting cancelled for {event_id}")
        except Exception as e:
            print(f"Error in post_event_after_delay for {event_id}: {e}")

    async def schedule_event_tasks(self, event_id):
        """Schedule reminder and cleanup tasks for an event"""
        try:
            if event_id not in self.events:
                return

            event = self.events[event_id]
            event_time_str = event["time"]
            event_time = datetime.strptime(event_time_str, "%Y-%m-%d %H:%M").replace(tzinfo=pytz.UTC)
            now = self.get_time_provider().now(pytz.UTC)

            # Schedule reminder if event is more than 30 minutes away
            reminder_diff = event_time - now
            if reminder_diff.total_seconds() > 1800:  # More than 30 minutes
                self.reminder_tasks[event_id] = self.bot.loop.create_task(
                    self.send_reminder(event_id, reminder_diff)
                )

            # Schedule cleanup (2 days after event)
            cleanup_time = event_time + timedelta(days=2)
            cleanup_diff = cleanup_time - now
            if cleanup_diff.total_seconds() > 0:
                self.cleanup_tasks[event_id] = self.bot.loop.create_task(
                    self.cleanup_event(event_id, cleanup_diff)
                )

        except Exception as e:
            print(f"Error scheduling tasks for event {event_id}: {e}")

    async def delete_all_events(self, guild_id):
        """Delete all events for a guild"""
        guild_id = str(guild_id)
        # Find all events for this guild
        events_to_delete = [event_id for event_id, event in self.events.items()
                            if str(event.get("guild_id")) == guild_id]

        # Delete each event
        deleted_count = 0
        for event_id in events_to_delete:
            if await self.delete_event(event_id):
                deleted_count += 1

        return deleted_count

    def can_bypass_signup_restrictions(self, member, guild):
        """Check if a member can bypass signup restrictions"""
        # Check if the bot has signup_bypass_roles attribute
        if not hasattr(self.bot, 'signup_bypass_roles'):
            return False
        # Get the bypass roles for this guild
        guild_id = str(guild.id)
        bypass_role_ids = self.bot.signup_bypass_roles.get(guild_id, [])
        # Check if the member has any of the bypass roles
        for role in member.roles:
            if str(role.id) in bypass_role_ids:
                return True
        return False

    async def update_event_message(self, event_id):
        """Update the event message with the latest information"""
        try:
            if event_id not in self.events:
                print(f"Event {event_id} not found in self.events")
                return False

            event = self.events[event_id]
            guild_id = event.get("guild_id")
            channel_id = event.get("channel_id")
            message_id = event.get("message_id")

            # If message_id is missing, try to create a new message
            if not message_id:
                print(f"Event {event_id} is missing message_id, attempting to create a new message")
                if channel_id:
                    try:
                        channel = self.bot.get_channel(int(channel_id))
                        if channel:
                            embed = await self.create_event_embed(event_id)
                            view = AttendanceView(self, event_id)
                            message = await channel.send(embed=embed, view=view)
                            self.events[event_id]["message_id"] = str(message.id)
                            await self.save_events(guild_id)
                            print(f"Created new message for event {event_id}: {message.id}")
                            return True
                    except Exception as e:
                        print(f"Error creating new message: {e}")
                return False

            if not all([guild_id, channel_id, message_id]):
                print(
                    f"Missing required data for event {event_id}: guild_id={guild_id}, channel_id={channel_id}, message_id={message_id}")
                return False

            # Get the guild, channel, and message
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                print(f"Guild {guild_id} not found")
                return False

            channel = guild.get_channel(int(channel_id))
            if not channel:
                print(f"Channel {channel_id} not found in guild {guild_id}")
                return False

            try:
                message = await channel.fetch_message(int(message_id))
            except discord.NotFound:
                print(f"Message {message_id} not found in channel {channel_id}, creating new message")
                try:
                    embed = await self.create_event_embed(event_id)
                    view = AttendanceView(self, event_id)
                    message = await channel.send(embed=embed, view=view)
                    self.events[event_id]["message_id"] = str(message.id)
                    await self.save_events(guild_id)
                    print(f"Created new message for event {event_id}: {message.id}")
                    return True
                except Exception as e:
                    print(f"Error creating new message: {e}")
                    return False
            except Exception as e:
                print(f"Error fetching message: {e}")
                return False

            # Create the updated embed
            embed = await self.create_event_embed(event_id)

            # Update the message
            view = AttendanceView(self, event_id)
            await message.edit(embed=embed, view=view)
            print(f"Successfully updated message for event {event_id}")
            return True
        except Exception as e:
            print(f"Error updating event message: {e}")
            import traceback
            traceback.print_exc()
            return False

    def create_event_view(self, event_id):
        """Create a view for an event with role buttons"""
        event = self.events.get(event_id)
        if not event:
            return None

        view = discord.ui.View(timeout=None)

        # Add buttons for each role
        for role_id, role_data in event.get("roles", {}).items():
            # Skip roles without names
            if not role_data.get("name"):
                continue

            # Determine button style
            style = discord.ButtonStyle.primary  # Default is blue

            # If the role is restricted, make it red
            if role_data.get("restricted", False):
                style = discord.ButtonStyle.danger  # Red
            # Otherwise use the specified style if available
            elif role_data.get("style") == "green":
                style = discord.ButtonStyle.success
            elif role_data.get("style") == "red":
                style = discord.ButtonStyle.danger
            elif role_data.get("style") == "gray":
                style = discord.ButtonStyle.secondary

            # Create the button
            button = RoleButton(
                cog=self,
                event_id=event_id,
                role_id=role_id,
                label=role_data.get("name", "Unknown"),
                style=style,
                disabled=role_data.get("disabled", False),
                required_role_id=role_data.get("required_role_id")
            )
            view.add_item(button)

        return view

    async def toggle_role(self, interaction, event_id, role_id):
        """Toggle a user's role for an event with locking to prevent concurrent toggles"""
        try:
            print(f"Toggle role called for event_id: {event_id}, role_id: {role_id}")

            # Create a unique lock key for this user and event
            user_id = str(interaction.user.id)

            # Initialize toggle_locks if it doesn't exist
            if not hasattr(self, 'toggle_locks'):
                self.toggle_locks = {}

            lock_key = f"{user_id}:{event_id}"

            # Check if there's already a toggle in progress for this user and event
            if lock_key in self.toggle_locks:
                # Already processing a toggle for this user and event
                try:
                    # Try to respond to the interaction
                    await self.safe_respond(interaction,
                                            "Please wait, your previous request is still processing.",
                                            ephemeral=True
                                            )
                except Exception as e:
                    print(f"Error responding to interaction: {e}")
                return

            # Set the lock
            self.toggle_locks[lock_key] = True

            # Acknowledge the interaction immediately if not already done
            try:
                if not interaction.response.is_done():
                    await interaction.response.defer(ephemeral=True)
            except Exception as e:
                print(f"Error deferring interaction: {e}")

            try:
                # Get the guild ID and user ID
                guild_id = str(interaction.guild.id)
                member = interaction.guild.get_member(int(user_id))

                # Check if the event exists
                if event_id not in self.events:
                    print(f"Event {event_id} not found in self.events")
                    print(f"Available events: {list(self.events.keys())}")
                    await self.safe_respond(interaction, "Event not found. Please contact an administrator.")
                    return

                # Get the event - make a copy to avoid race conditions
                event = copy.deepcopy(self.events[event_id])

                # Check if the role exists
                if role_id not in event.get("roles", {}):
                    await self.safe_respond(interaction, "Role not found.")
                    return

                # Get the role data
                role_data = event["roles"][role_id]
                role_name = role_data.get('name', 'Unknown Role')

                # Check if the user can bypass restrictions
                can_bypass = member and self.can_bypass_signup_restrictions(member, interaction.guild)

                # Check if the role is restricted
                if role_data.get("restricted", False) and not can_bypass:
                    if not self.can_join_restricted_role(interaction.user, role_data):
                        required_role_id = role_data.get("required_role_id")
                        required_role = interaction.guild.get_role(int(required_role_id)) if required_role_id else None
                        role_name = required_role.name if required_role else "required role"
                        await self.safe_respond(
                            interaction,
                            f"You don't have the {role_name} role required to sign up for this position."
                        )
                        return

                # Initialize the users list if it doesn't exist
                if "users" not in role_data:
                    role_data["users"] = []

                # Check current state to determine action
                currently_in_role = user_id in role_data["users"]

                # Prepare response message
                response_message = ""

                # Initialize event_role_users if it doesn't exist
                if "event_role_users" not in event:
                    event["event_role_users"] = []

                # First, check if user is in any other role and remove them
                current_role_id = None
                for other_role_id, other_role_data in event["roles"].items():
                    if other_role_id != role_id and user_id in other_role_data.get("users", []):
                        # Found user in another role, remove them
                        current_role_id = other_role_id
                        other_role_data["users"].remove(user_id)
                        # LOG THE "LEFT" ACTION FOR THE PREVIOUS ROLE
                        try:
                            await self.attendance_tracker.log_to_google_sheets(
                                user_id=user_id,
                                username=interaction.user.display_name,  # ✅ FIXED
                                event_id=event_id,
                                event_title=event["title"],
                                role_id=other_role_id,
                                role_name=other_role_data.get('name', 'Unknown Role'),
                                action="left",
                                guild_id=interaction.guild.id,  # ✅ FIXED
                                guild_name=interaction.guild.name  # ✅ FIXED
                            )
                        except Exception as sheets_error:
                            print(f"Error logging role switch (left) to Google Sheets: {sheets_error}")

                        # Update attendance record for the removed role
                        await self.attendance_tracker.delete_attendance(
                            guild_id=event["guild_id"],
                            user_id=user_id,
                            event_id=event_id,
                            role_id=other_role_id
                        )

                        # Handle Discord role removal if applicable
                        if "discord_role_id" in other_role_data and other_role_data["discord_role_id"]:
                            try:
                                discord_role = interaction.guild.get_role(int(other_role_data["discord_role_id"]))
                                if discord_role and member:
                                    await member.remove_roles(discord_role,
                                                              reason=f"Removed from {event['title']} event role")
                            except Exception as e:
                                print(f"Error removing Discord role: {e}")

                        # Handle Discord role removal if applicable
                        if "discord_role_id" in other_role_data and other_role_data["discord_role_id"]:
                            try:
                                discord_role = interaction.guild.get_role(int(other_role_data["discord_role_id"]))
                                if discord_role and member:
                                    await member.remove_roles(discord_role,
                                                              reason=f"Removed from {event['title']} event role")
                            except Exception as e:
                                print(f"Error removing Discord role: {e}")

                if currently_in_role:
                    # REMOVE USER FROM ROLE (they clicked the same role again)
                    role_data["users"].remove(user_id)
                    response_message = f"You have left the {role_name} role."

                    try:
                        await self.attendance_tracker.log_to_google_sheets(
                            user_id=user_id,
                            username=interaction.user.display_name,
                            event_id=event_id,
                            event_title=event["title"],
                            role_id=role_id,
                            role_name=role_data["name"],
                            action="left",
                            guild_id=interaction.guild.id,
                            guild_name=interaction.guild.name
                        )
                    except Exception as sheets_error:
                        print(f"Error logging role leave to Google Sheets: {sheets_error}")

                    # Update attendance record
                    await self.attendance_tracker.delete_attendance(
                        guild_id=event["guild_id"],
                        user_id=user_id,
                        event_id=event_id,
                        role_id=role_id
                    )

                    # Handle Discord role removal if applicable
                    if "discord_role_id" in role_data and role_data["discord_role_id"]:
                        try:
                            discord_role = interaction.guild.get_role(int(role_data["discord_role_id"]))
                            if discord_role and member:
                                await member.remove_roles(discord_role,
                                                          reason=f"Removed from {event['title']} event role")
                        except Exception as e:
                            print(f"Error removing Discord role: {e}")

                    # Check if user is in any other roles for this event
                    user_in_other_roles = False
                    for other_role_id, other_role_data in event["roles"].items():
                        if other_role_id != role_id and user_id in other_role_data.get("users", []):
                            user_in_other_roles = True
                            break

                    # If not in any other roles, remove event role if it exists
                    if not user_in_other_roles and event.get("event_role_id") and user_id in event.get(
                            "event_role_users", []):
                        try:
                            event_role = interaction.guild.get_role(int(event["event_role_id"]))
                            if event_role and member:
                                await member.remove_roles(event_role,
                                                          reason=f"Left all roles in event: {event['title']}")
                                if user_id in event["event_role_users"]:
                                    event["event_role_users"].remove(user_id)
                        except Exception as e:
                            print(f"Error removing event role: {e}")

                else:
                    # ADD USER TO ROLE
                    # Check if the role has a limit
                    if "limit" in role_data and role_data["limit"] > 0:
                        # Check if the role is full
                        if len(role_data["users"]) >= role_data["limit"] and not can_bypass:
                            await self.safe_respond(interaction, f"The {role_name} role is full.")
                            return

                    # Add the user to the role
                    role_data["users"].append(user_id)

                    # Update attendance record
                    await self.attendance_tracker.record_attendance(
                        guild_id=event["guild_id"],
                        user_id=user_id,
                        event_id=event_id,
                        event_title=event["title"],
                        event_time=event["time"],
                        role_id=role_id,
                        role_name=role_data["name"]
                    )

                    try:
                        await self.attendance_tracker.log_to_google_sheets(
                            user_id=user_id,
                            username=interaction.user.display_name,
                            event_id=event_id,
                            event_title=event["title"],
                            role_id=role_id,
                            role_name=role_data["name"],
                            action="joined",
                            guild_id=interaction.guild.id,
                            guild_name=interaction.guild.name
                        )
                    except Exception as sheets_error:
                        print(f"Error logging role join to Google Sheets: {sheets_error}")

                    if current_role_id:
                        previous_role_name = event["roles"][current_role_id].get('name', 'Unknown Role')
                        response_message = f"You have switched from {previous_role_name} to {role_name}."
                    else:
                        response_message = f"You have joined the {role_name} role."

                    # Add Discord role if applicable
                    if "discord_role_id" in role_data and role_data["discord_role_id"]:
                        try:
                            discord_role = interaction.guild.get_role(int(role_data["discord_role_id"]))
                            if discord_role and member:
                                await member.add_roles(discord_role, reason=f"Joined {event['title']} event role")
                        except Exception as e:
                            print(f"Error adding Discord role: {e}")

                    # Add event role if it exists and user isn't already in it
                    if event.get("event_role_id") and user_id not in event.get("event_role_users", []):
                        try:
                            event_role = interaction.guild.get_role(int(event["event_role_id"]))
                            if event_role and member:
                                await member.add_roles(event_role, reason=f"Joined role in event: {event['title']}")
                                if "event_role_users" not in event:
                                    event["event_role_users"] = []
                                event["event_role_users"].append(user_id)
                        except Exception as e:
                            print(f"Error adding event role: {e}")

                # Update the event in the dictionary
                self.events[event_id] = event

                # Save the events
                await self.save_events(guild_id, update_message=False)

                # Update the message
                await self.update_event_message(event_id)

                # Respond to the interaction
                await self.safe_respond(interaction, response_message)

            finally:
                # Always release the lock
                if hasattr(self, 'toggle_locks') and lock_key in self.toggle_locks:
                    del self.toggle_locks[lock_key]

        except Exception as e:
            print(f"Error toggling role: {e}")
            import traceback
            traceback.print_exc()
            await self.safe_respond(interaction, "An error occurred. Please try again.")

    @app_commands.command(name="create", description="Create a new attendance event")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def create_attendance(self, interaction: discord.Interaction):
        """Create a new attendance event"""
        # Load events for this guild if not already loaded
        await self.load_events(interaction.guild.id)
        await interaction.response.send_message("Let's create a new attendance event. I'll ask you some questions.",
                                                ephemeral=True)
        # Ask for title
        await interaction.followup.send("What's the title of the event?", ephemeral=True)

        # We need to wait for a message in the channel from this user
        def check(m):
            return m.author == interaction.user and m.channel == interaction.channel

        try:
            title_msg = await self.bot.wait_for("message", check=check, timeout=300)
            title = title_msg.content
            # Delete the user's message to keep the channel clean
            try:
                await title_msg.delete()
            except:
                pass
        except asyncio.TimeoutError:
            return await interaction.followup.send("Timed out. Please try again.", ephemeral=True)

        # Ask for description
        await interaction.followup.send("Please provide a description for the event:", ephemeral=True)
        try:
            desc_msg = await self.bot.wait_for("message", check=check, timeout=300)
            description = desc_msg.content
            try:
                await desc_msg.delete()
            except:
                pass
        except asyncio.TimeoutError:
            return await interaction.followup.send("Timed out. Please try again.", ephemeral=True)

        # Ask for time
        await interaction.followup.send("When will the event take place? (Format: YYYY-MM-DD HH:MM in EST timezone)",
                                        ephemeral=True)
        while True:
            try:
                time_msg = await self.bot.wait_for("message", check=check, timeout=300)
                event_time_str = time_msg.content
                # Validate time format
                try:
                    # Parse the input time string
                    naive_time = datetime.strptime(event_time_str, "%Y-%m-%d %H:%M")
                    # Convert EST to UTC for storage
                    est = timezone('US/Eastern')
                    est_time = est.localize(naive_time)
                    utc_time = est_time.astimezone(pytz.UTC)
                    # Store in UTC format
                    event_time = utc_time.strftime("%Y-%m-%d %H:%M")
                    try:
                        await time_msg.delete()
                    except:
                        pass
                    break
                except ValueError as e:
                    print(f"Time parsing error: {e}")
                    await interaction.followup.send("Invalid time format. Please use YYYY-MM-DD HH:MM", ephemeral=True)
                    try:
                        await time_msg.delete()
                    except:
                        pass
            except asyncio.TimeoutError:
                return await interaction.followup.send("Timed out. Please try again.", ephemeral=True)

        # Ask for location
        await interaction.followup.send("Where will the event take place?", ephemeral=True)
        try:
            location_msg = await self.bot.wait_for("message", check=check, timeout=300)
            location = location_msg.content
            try:
                await location_msg.delete()
            except:
                pass
        except asyncio.TimeoutError:
            return await interaction.followup.send("Timed out. Please try again.", ephemeral=True)

        # Ask for embed ping
        await interaction.followup.send(
            "Would you like to add a staff ping when this event is posted? This will ping staff members every time the event goes out (including recurring events). (yes/no)",
            ephemeral=True
        )
        try:
            staff_ping_msg = await self.bot.wait_for("message", check=check, timeout=300)
            wants_staff_ping = staff_ping_msg.content.lower() in ["yes", "y", "true"]
            try:
                await staff_ping_msg.delete()
            except:
                pass
        except asyncio.TimeoutError:
            return await interaction.followup.send("Timed out. Please try again.", ephemeral=True)

        staff_ping_role_id = None
        if wants_staff_ping:
            await interaction.followup.send(
                "Please mention the role to ping, enter its ID, or name:",
                ephemeral=True
            )
            try:
                ping_role_msg = await self.bot.wait_for("message", check=check, timeout=300)
                # Check for role mentions first
                if ping_role_msg.role_mentions:
                    role = ping_role_msg.role_mentions[0]
                    staff_ping_role_id = role.id
                    await interaction.followup.send(f"Staff ping role set to: {role.name}", ephemeral=True)
                else:
                    # Try to find the role by ID
                    try:
                        role_id = int(ping_role_msg.content.strip())
                        role = interaction.guild.get_role(role_id)
                    except ValueError:
                        # If not an ID, try to find by name
                        role_name = ping_role_msg.content.strip()
                        role = discord.utils.get(interaction.guild.roles, name=role_name)

                    if role:
                        staff_ping_role_id = role.id
                        await interaction.followup.send(f"Staff ping role set to: {role.name}", ephemeral=True)
                    else:
                        await interaction.followup.send("Role not found. No staff ping will be added.", ephemeral=True)
                        staff_ping_role_id = None

                try:
                    await ping_role_msg.delete()
                except:
                    pass
            except asyncio.TimeoutError:
                return await interaction.followup.send("Timed out. Please try again.", ephemeral=True)

        # Ask for channel
        await interaction.followup.send(
            f"Which channel should the event be posted in? Please enter the channel name, ID, or mention a channel.",
            ephemeral=True)
        while True:
            try:
                channel_msg = await self.bot.wait_for("message", check=check, timeout=300)
                # Check for channel mentions first
                if channel_msg.channel_mentions:
                    target_channel = channel_msg.channel_mentions[0]
                    try:
                        await channel_msg.delete()
                    except:
                        pass
                    break
                # Try to find the channel by ID
                try:
                    channel_id = int(channel_msg.content.strip())
                    target_channel = interaction.guild.get_channel(channel_id)
                except ValueError:
                    # If not an ID, try to find by name
                    channel_name = channel_msg.content.strip().lower()
                    target_channel = discord.utils.get(interaction.guild.text_channels, name=channel_name)
                if target_channel:
                    try:
                        await channel_msg.delete()
                    except:
                        pass
                    break
                else:
                    await interaction.followup.send(f"Channel not found in {interaction.guild.name}. Please try again.",
                                                    ephemeral=True)
                    try:
                        await channel_msg.delete()
                    except:
                        pass
            except asyncio.TimeoutError:
                return await interaction.followup.send("Timed out. Please try again.", ephemeral=True)

        # Ask for recurring
        await interaction.followup.send("Should this event repeat? (yes/no)", ephemeral=True)
        try:
            recurring_msg = await self.bot.wait_for("message", check=check, timeout=300)
            recurring = recurring_msg.content.lower() in ["yes", "y", "true"]
            try:
                await recurring_msg.delete()
            except:
                pass
        except asyncio.TimeoutError:
            return await interaction.followup.send("Timed out. Please try again.", ephemeral=True)

        recurring_interval = 0
        if recurring:
            # Ask for recurring interval
            await interaction.followup.send(
                "How often should it repeat? (Enter number of weeks: 1 for weekly, 2 for biweekly, etc.)",
                ephemeral=True)
            while True:
                try:
                    interval_msg = await self.bot.wait_for("message", check=check, timeout=300)
                    recurring_interval = int(interval_msg.content)
                    if recurring_interval <= 0:
                        await interaction.followup.send("Please enter a positive number.", ephemeral=True)
                        try:
                            await interval_msg.delete()
                        except:
                            pass
                    else:
                        try:
                            await interval_msg.delete()
                        except:
                            pass
                        break
                except ValueError:
                    await interaction.followup.send("Please enter a valid number.", ephemeral=True)
                    try:
                        await interval_msg.delete()
                    except:
                        pass
                except asyncio.TimeoutError:
                    return await interaction.followup.send("Timed out. Please try again.", ephemeral=True)

        # Now set up the roles
        roles = {}
        # Get the restricted role IDs
        restricted_role_ids = []
        for i in range(4):  # Changed to 4 restricted roles as per requirements
            await interaction.followup.send(
                f"For restricted role #{i + 1}, please mention the role, enter its ID, or name (or type 'skip' to skip this restricted role):",
                ephemeral=True)
            try:
                role_msg = await self.bot.wait_for("message", check=check, timeout=300)
                if role_msg.content.lower() == "skip":
                    restricted_role_ids.append(None)
                    try:
                        await role_msg.delete()
                    except:
                        pass
                    continue
                # Check for role mentions first
                if role_msg.role_mentions:
                    role = role_msg.role_mentions[0]
                    restricted_role_ids.append(role.id)
                    await interaction.followup.send(f"Found role: {role.name}", ephemeral=True)
                else:
                    # Try to find the role by ID
                    try:
                        role_id = int(role_msg.content.strip())
                        role = interaction.guild.get_role(role_id)
                    except ValueError:
                        # If not an ID, try to find by name
                        role_name = role_msg.content.strip()
                        role = discord.utils.get(interaction.guild.roles, name=role_name)
                    if role:
                        restricted_role_ids.append(role.id)
                        await interaction.followup.send(f"Found role: {role.name}", ephemeral=True)
                    else:
                        await interaction.followup.send("Role not found. Skipping this restricted role.",
                                                        ephemeral=True)
                        restricted_role_ids.append(None)
                # Delete the user's message to keep the channel clean
                try:
                    await role_msg.delete()
                except:
                    pass
            except asyncio.TimeoutError:
                return await interaction.followup.send("Timed out. Please try again.", ephemeral=True)

        # Create roles (up to 10, with skippable options)
        max_roles = 10
        role_count = 0
        # First handle restricted roles
        for i in range(4):  # Changed to 4 restricted roles
            # Skip if no required role was specified
            if i >= len(restricted_role_ids) or restricted_role_ids[i] is None:
                role_id = f"role_{i + 1}"
                roles[role_id] = {
                    "name": None,  # No name means this role is skipped
                    "restricted": True,
                    "users": [],
                    "required_role_id": None
                }
                continue
            await interaction.followup.send(f"Name for restricted role #{i + 1}:", ephemeral=True)
            try:
                role_name_msg = await self.bot.wait_for("message", check=check, timeout=300)
                role_name = role_name_msg.content
                try:
                    await role_name_msg.delete()
                except:
                    pass
            except asyncio.TimeoutError:
                return await interaction.followup.send("Timed out. Please try again.", ephemeral=True)
            role_id = f"role_{i + 1}"
            roles[role_id] = {
                "name": role_name,
                "restricted": True,
                "users": [],
                "required_role_id": restricted_role_ids[i]
            }
            role_count += 1

        # Now handle open roles (6 open roles as per requirements)
        for i in range(4, 4 + 6):  # 4 restricted + 6 open = 10 total
            await interaction.followup.send(
                f"Name for open role #{i + 1 - 4} (or type 'skip' to skip, or 'done' if you're finished adding roles):",
                ephemeral=True)
            try:
                role_name_msg = await self.bot.wait_for("message", check=check, timeout=300)
                role_name = role_name_msg.content
                try:
                    await role_name_msg.delete()
                except:
                    pass
                if role_name.lower() == "done":
                    break
                if role_name.lower() == "skip":
                    role_id = f"role_{i + 1}"
                    roles[role_id] = {
                        "name": None,  # No name means this role is skipped
                        "restricted": False,
                        "users": [],
                        "required_role_id": None
                    }
                    continue
                role_id = f"role_{i + 1}"
                roles[role_id] = {
                    "name": role_name,
                    "restricted": False,
                    "users": [],
                    "required_role_id": None
                }
                role_count += 1
            except asyncio.TimeoutError:
                return await interaction.followup.send("Timed out. Please try again.", ephemeral=True)

        # NEW: Ask if a pingable role should be assigned to participants
        await interaction.followup.send(
            "Would you like to assign a pingable role to everyone who signs up for this event? (yes/no)",
            ephemeral=True
        )
        try:
            pingable_msg = await self.bot.wait_for("message", check=check, timeout=300)
            assign_pingable_role = pingable_msg.content.lower() in ["yes", "y", "true"]
            try:
                await pingable_msg.delete()
            except:
                pass
        except asyncio.TimeoutError:
            return await interaction.followup.send("Timed out. Please try again.", ephemeral=True)

        event_role_id = None
        if assign_pingable_role:
            # Ask if they want to create a new role or use an existing one
            await interaction.followup.send(
                "Would you like to create a new role or use an existing one? (new/existing)",
                ephemeral=True
            )
            try:
                role_choice_msg = await self.bot.wait_for("message", check=check, timeout=300)
                create_new_role = role_choice_msg.content.lower() in ["new", "n", "create"]
                try:
                    await role_choice_msg.delete()
                except:
                    pass
                if create_new_role:
                    # Create a new role
                    role_name = f"Event: {title}"
                    new_role = await interaction.guild.create_role(
                        name=role_name,
                        mentionable=True,
                        reason=f"Created for event: {title}"
                    )
                    event_role_id = new_role.id
                    await interaction.followup.send(f"Created new role: {new_role.name}", ephemeral=True)
                else:
                    # Use an existing role
                    await interaction.followup.send(
                        "Please mention the role, enter its ID, or name:",
                        ephemeral=True
                    )
                    try:
                        existing_role_msg = await self.bot.wait_for("message", check=check, timeout=300)
                        # Check for role mentions first
                        if existing_role_msg.role_mentions:
                            role = existing_role_msg.role_mentions[0]
                            event_role_id = role.id
                            await interaction.followup.send(f"Using role: {role.name}", ephemeral=True)
                        else:
                            # Try to find the role by ID
                            try:
                                role_id = int(existing_role_msg.content.strip())
                                role = interaction.guild.get_role(role_id)
                            except ValueError:
                                # If not an ID, try to find by name
                                role_name = existing_role_msg.content.strip()
                                role = discord.utils.get(interaction.guild.roles, name=role_name)
                            if role:
                                event_role_id = role.id
                                await interaction.followup.send(f"Using role: {role.name}", ephemeral=True)
                            else:
                                await interaction.followup.send("Role not found. No pingable role will be assigned.",
                                                                ephemeral=True)
                                event_role_id = None
                        try:
                            await existing_role_msg.delete()
                        except:
                            pass
                    except asyncio.TimeoutError:
                        return await interaction.followup.send("Timed out. Please try again.", ephemeral=True)
            except asyncio.TimeoutError:
                return await interaction.followup.send("Timed out. Please try again.", ephemeral=True)

        # Create a unique event ID based on title and date
        event_id = f"{title.replace(' ', '_')}_{naive_time.strftime('%Y-%m-%d_%H-%M')}"

        # Create the event dictionary
        event = {
            "id": event_id,
            "title": title,
            "description": description,
            "time": event_time,
            "location": location,
            "guild_id": interaction.guild.id,
            "channel_id": target_channel.id,
            "message_id": None,  # Will be updated after sending the message
            "roles": roles,
            "recurring": recurring,
            "recurring_interval": recurring_interval,
            "event_role_id": event_role_id,
            "staff_ping_role_id": staff_ping_role_id,
            "created_by": interaction.user.id,
            "created_at": datetime.now(pytz.UTC).strftime("%Y-%m-%d %H:%M")
        }

        # Save the event to the dictionary BEFORE creating the view
        self.events[event_id] = event

        # Create the embed
        embed = await self.create_event_embed(event_id)

        # Debug output before saving
        print(f"Creating event with ID: {event_id}")
        print(f"Event data: {event}")
        print(f"Current events dict has {len(self.events)} events")
        print(f"Guild ID in event: {event['guild_id']}, Type: {type(event['guild_id'])}")

        # Send the message with the view
        view = AttendanceView(self, event_id)

        # Check for staff ping
        content = None
        if event.get("staff_ping_role_id"):
            role = interaction.guild.get_role(int(event["staff_ping_role_id"]))
            if role:
                content = role.mention

        message = await target_channel.send(content=content, embed=embed, view=view)

        # Debug the message ID
        print(f"Message sent with ID: {message.id}")

        # Update the event with the message ID
        self.events[event_id]["message_id"] = message.id
        print(f"Updated event {event_id} with message_id: {self.events[event_id]['message_id']}")

        # Make a copy of the event to verify it's saved correctly
        event_copy = self.events[event_id].copy()

        # Save the events
        await self.save_events(interaction.guild.id)
        print(f"Saved events for guild {interaction.guild.id}")

        # Verify the message ID was saved by checking the actual saved data
        # This is a critical step to ensure the message ID is persisted
        events_file = os.path.join(self.data_dir, "events", f"events_{interaction.guild.id}.json")
        if os.path.exists(events_file):
            try:
                with open(events_file, "r") as f:
                    saved_events = json.load(f)
                    if event_id in saved_events and 'message_id' in saved_events[event_id]:
                        print(f"Verified saved message_id: {saved_events[event_id]['message_id']}")
                    else:
                        print(f"WARNING: message_id not found in saved event data!")
                        # Try to fix it by saving again
                        self.events[event_id] = event_copy  # Restore from our copy
                        await self.save_events(interaction.guild.id)
                        print(f"Attempted to fix by saving again")
            except Exception as e:
                print(f"Error verifying saved data: {e}")

        # Schedule the reminder
        event_time_dt = datetime.strptime(event_time, "%Y-%m-%d %H:%M")
        event_time_dt = event_time_dt.replace(tzinfo=pytz.UTC)
        time_diff = event_time_dt - datetime.now(pytz.UTC)

        if time_diff.total_seconds() > 1800:  # Only schedule if more than 30 minutes away
            self.reminder_tasks[event_id] = self.bot.loop.create_task(
                self.send_reminder(event_id, time_diff)
            )

        # Schedule cleanup
        event_time_dt = datetime.strptime(event_time, "%Y-%m-%d %H:%M")
        event_time_dt = event_time_dt.replace(tzinfo=pytz.UTC)
        # Keep this structure but pass the right parameter:
        time_until_event = event_time_dt - datetime.now(pytz.UTC)
        self.cleanup_tasks[event_id] = self.bot.loop.create_task(
            self.cleanup_event(event_id, time_until_event)
        )

        # If recurring, schedule the next occurrence
        if recurring:
            self.recurring_tasks[event_id] = self.bot.loop.create_task(
                self.schedule_next_occurrence(event_id)
            )

        # Confirm to the user
        await interaction.followup.send(
            f"Event created successfully! Check {target_channel.mention} to see your event.",
            ephemeral=True
        )

    @app_commands.command(name="list", description="List all events")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def list_events(self, interaction: discord.Interaction):
        """List all events"""
        try:
            # Load events first
            await self.load_events(interaction.guild.id)

            # Filter events for this guild - fix the type comparison
            guild_events = {
                event_id: event for event_id, event in self.events.items()
                if event.get("guild_id") == interaction.guild.id and not event.get("cleaned_up", False)
            }

            print(f"Found {len(guild_events)} events for guild {interaction.guild.id}")

            if not guild_events:
                embed = discord.Embed(
                    title="📅 Upcoming Events",
                    description="No active events found.",
                    color=0x87CEEB
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            # Create the main embed
            embed = discord.Embed(
                title="📅 Upcoming Events",
                description="Here are all the upcoming events:",
                color=0x87CEEB,
                timestamp=datetime.utcnow()
            )

            # Sort events by time
            sorted_events = sorted(
                guild_events.items(),
                key=lambda x: x[1].get("time", "9999-12-31 23:59")
            )

            # Add events to embed
            for event_id, event in sorted_events:
                try:
                    title = event.get("title", "Untitled Event")
                    description = event.get("description", "No description provided")
                    location = event.get("location", "Not specified")

                    # Format the time
                    event_time_str = event.get("time")
                    if event_time_str:
                        try:
                            event_time = datetime.strptime(event_time_str, "%Y-%m-%d %H:%M").replace(tzinfo=pytz.UTC)
                            local_time = event_time.astimezone(timezone('US/Eastern'))

                            # Calculate time difference
                            now = datetime.now(timezone('US/Eastern'))
                            time_diff = event_time.astimezone(timezone('US/Eastern')) - now

                            if time_diff.days > 0:
                                time_ago = f"in {time_diff.days} days"
                            elif time_diff.days < 0:
                                time_ago = f"{abs(time_diff.days)} days ago"
                            elif time_diff.total_seconds() > 0:
                                hours = int(time_diff.total_seconds() // 3600)
                                if hours > 0:
                                    time_ago = f"in {hours} hours"
                                else:
                                    minutes = int(time_diff.total_seconds() // 60)
                                    time_ago = f"in {minutes} minutes"
                            else:
                                hours_ago = int(abs(time_diff.total_seconds()) // 3600)
                                time_ago = f"{hours_ago} hours ago"

                            formatted_time = local_time.strftime("%A, %B %d, %Y %I:%M %p")
                            time_display = f"{formatted_time} ({time_ago})"
                        except Exception as e:
                            print(f"Error parsing time for event {event_id}: {e}")
                            time_display = event_time_str
                    else:
                        time_display = "Not specified"

                    # Count signups
                    signup_count = 0
                    if "signups" in event:
                        for role_signups in event["signups"].values():
                            signup_count += len(role_signups)

                    # Check if recurring and calculate next occurrence
                    recurring_info = ""
                    next_occurrence = ""
                    if event.get("recurring"):
                        recurring_type = event.get("recurring_type", "weekly")
                        recurring_info = f"Recurring: {recurring_type.title()}"

                        # Calculate next occurrence for recurring events
                        if event_time_str:
                            try:
                                base_time = datetime.strptime(event_time_str, "%Y-%m-%d %H:%M").replace(tzinfo=pytz.UTC)
                                now = datetime.now(pytz.UTC)

                                if recurring_type.lower() == "weekly":
                                    # Find next weekly occurrence
                                    days_ahead = 7
                                    next_time = base_time
                                    while next_time <= now:
                                        next_time += timedelta(days=7)
                                elif recurring_type.lower() == "daily":
                                    days_ahead = 1
                                    next_time = base_time
                                    while next_time <= now:
                                        next_time += timedelta(days=1)
                                else:
                                    next_time = base_time

                                if next_time != base_time:
                                    next_local = next_time.astimezone(timezone('US/Eastern'))
                                    next_formatted = next_local.strftime("%A, %B %d, %Y %I:%M %p")

                                    # Calculate time until next occurrence
                                    time_until = next_time - now
                                    if time_until.days > 0:
                                        time_until_str = f"in {time_until.days} days"
                                    else:
                                        hours_until = int(time_until.total_seconds() // 3600)
                                        time_until_str = f"in {hours_until} hours"

                                    next_occurrence = f"Next Occurrence: {next_formatted} ({time_until_str})"
                            except Exception as e:
                                print(f"Error calculating next occurrence: {e}")

                    # Check if message exists
                    message_status = ""
                    if not event.get("message_id"):
                        message_status = " ⚠️"

                    # Build the field value
                    field_value = f"**Description:** {description}\n"
                    field_value += f"**Time:** {time_display}\n"
                    field_value += f"**Location:** {location}\n"
                    field_value += f"**Signups:** {signup_count}\n"

                    if recurring_info:
                        field_value += f"**{recurring_info}**\n"
                    if next_occurrence:
                        field_value += f"**{next_occurrence}**\n"

                    field_value += f"**ID:** `{event_id}`"

                    # Add field for this event
                    embed.add_field(
                        name=f"{title}{message_status}",
                        value=field_value,
                        inline=False
                    )

                except Exception as e:
                    print(f"Error processing event {event_id}: {e}")
                    embed.add_field(
                        name=f"{event.get('title', 'Error Event')} ❌",
                        value=f"Error processing event data\n**ID:** `{event_id}`",
                        inline=False
                    )

            # Add footer with helpful info
            embed.set_footer(
                text=f"Total Events: {len(guild_events)} | ⚠️ = Missing message",
                icon_url=interaction.guild.icon.url if interaction.guild.icon else None
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            print(f"Error in list_events: {e}")
            import traceback
            traceback.print_exc()
            try:
                error_embed = discord.Embed(
                    title="❌ Error",
                    description=f"An error occurred while loading events:\n```{str(e)}```",
                    color=0xFF0000
                )
                await interaction.response.send_message(embed=error_embed, ephemeral=True)
            except:
                print("Could not send error response")

    @app_commands.command(name="delete", description="Delete an attendance event")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def delete_event_command(self, interaction: discord.Interaction, event_id: str):
        """Delete an attendance event"""
        await self.load_events(interaction.guild.id)

        event = self.events.get(event_id)
        if not event:
            return await interaction.response.send_message("Event not found.", ephemeral=True)

        if event["guild_id"] != interaction.guild.id:
            return await interaction.response.send_message("Event not found in this guild.", ephemeral=True)

        # Try to delete the message
        try:
            channel = interaction.guild.get_channel(event["channel_id"])
            if channel:
                message = await channel.fetch_message(event["message_id"])
                await message.delete()
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass

        # Delete the event
        await self.delete_event(event_id)

        await interaction.response.send_message(f"Event '{event['title']}' has been deleted.", ephemeral=True)

    @app_commands.command(name="delete_all", description="Delete all attendance events in this guild")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def delete_all_events_command(self, interaction: discord.Interaction):
        """Delete all attendance events in this guild"""
        # Defer the response as this might take some time
        await interaction.response.defer(ephemeral=True)

        # Load events for this guild
        await self.load_events(interaction.guild.id)

        # Filter events that belong to this guild
        guild_events = {event_id: event for event_id, event in self.events.items()
                        if event.get("guild_id") == interaction.guild.id}

        if not guild_events:
            return await interaction.followup.send("No events found in this guild.", ephemeral=True)

        deleted_count = 0
        for event_id, event in guild_events.items():
            # Try to delete the message
            try:
                channel = interaction.guild.get_channel(event.get("channel_id"))
                if channel and event.get("message_id"):
                    try:
                        message = await channel.fetch_message(event["message_id"])
                        await message.delete()
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
                        print(f"Could not delete message for event {event_id}: {e}")
            except Exception as e:
                print(f"Error processing channel/message for event {event_id}: {e}")

            # Cancel any scheduled tasks
            if event_id in self.reminder_tasks:
                self.reminder_tasks[event_id].cancel()
                del self.reminder_tasks[event_id]

            if event_id in self.cleanup_tasks:
                self.cleanup_tasks[event_id].cancel()
                del self.cleanup_tasks[event_id]

            if event_id in self.recurring_tasks:
                self.recurring_tasks[event_id].cancel()
                del self.recurring_tasks[event_id]

            # Delete the event from our dictionary
            if event_id in self.events:
                del self.events[event_id]
                deleted_count += 1

        # Save the updated events
        await self.save_events(interaction.guild.id)

        await interaction.followup.send(f"Deleted {deleted_count} events from this guild.", ephemeral=True)

    @app_commands.command(name="attendance", description="View or export attendance data")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.choices(
        view_type=[
            app_commands.Choice(name="User Attendance", value="user"),
            app_commands.Choice(name="Role Attendance", value="role"),
            app_commands.Choice(name="Date Attendance", value="date"),
            app_commands.Choice(name="All Attendance", value="all")
        ],
        output_format=[
            app_commands.Choice(name="Discord Message", value="discord"),
            app_commands.Choice(name="CSV File", value="csv")
        ]
    )
    async def view_attendance(self, interaction: discord.Interaction, view_type: str, output_format: str,
                              user: discord.Member = None, role_name: str = None, date: str = None):
        """
        View or export attendance data

        Parameters:
        -----------
        view_type: str
            Type of view: 'user', 'role', 'date', or 'all'
        output_format: str
            Format to display results: 'discord' or 'csv'
        user: discord.Member
            User to view attendance for (required for 'user' view type)
        role_name: str
            Role name to view attendance for (required for 'role' view type)
        date: str
            Date to view attendance for in YYYY-MM-DD format (required for 'date' view type)
        """
        await self.load_events(interaction.guild.id)

        # Filter events for this guild
        guild_events = {
            event_id: event for event_id, event in self.events.items()
            if event["guild_id"] == interaction.guild.id  # Both should be integers
        }

        if not guild_events:
            return await interaction.response.send_message("No events found for this guild.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        # Validate parameters based on view type
        if view_type == "user" and not user:
            return await interaction.followup.send("Please provide a user to view attendance for.", ephemeral=True)

        if view_type == "role" and not role_name:
            return await interaction.followup.send("Please provide a role name to view attendance for.", ephemeral=True)

        if view_type == "date" and not date:
            return await interaction.followup.send("Please provide a date to view attendance for (YYYY-MM-DD).",
                                                   ephemeral=True)

        # Validate date format if provided
        if date:
            try:
                filter_date = datetime.strptime(date, "%Y-%m-%d").date()
            except ValueError:
                return await interaction.followup.send("Invalid date format. Please use YYYY-MM-DD.", ephemeral=True)

        # Process the data based on view type
        if view_type == "user":
            # Get user attendance data
            user_data = []
            for event_id, event in guild_events.items():
                event_time_str = event.get("time", "Unknown")
                try:
                    event_time = datetime.strptime(event_time_str, "%Y-%m-%d %H:%M")
                    event_date = event_time.strftime("%Y-%m-%d")
                except ValueError:
                    event_date = "Unknown"

                # Check if user was in any role
                user_found = False
                for role_id, role_data in event.get("roles", {}).items():
                    if str(user.id) in role_data.get("users", []):
                        user_data.append({
                            "event_title": event.get("title", "Unknown Event"),
                            "event_date": event_date,
                            "role": role_data.get("name", "Unknown Role"),
                            "attended": "Yes"
                        })
                        user_found = True
                        break

                if not user_found:
                    user_data.append({
                        "event_title": event.get("title", "Unknown Event"),
                        "event_date": event_date,
                        "role": "N/A",
                        "attended": "No"
                    })

            # Output the data
            if output_format == "discord":
                if not user_data:
                    await interaction.followup.send(f"No attendance data found for {user.display_name}.",
                                                    ephemeral=True)
                    return

                # Create an embed to display the data
                embed = discord.Embed(
                    title=f"Attendance for {user.display_name}",
                    color=discord.Color.blue()
                )

                # Add fields for each event (up to 25 fields max)
                for i, entry in enumerate(user_data[:25]):
                    embed.add_field(
                        name=f"{entry['event_title']} ({entry['event_date']})",
                        value=f"Role: {entry['role']}\nAttended: {entry['attended']}",
                        inline=True
                    )

                if len(user_data) > 25:
                    embed.set_footer(text=f"Showing 25 of {len(user_data)} events. Use CSV export to see all.")

                await interaction.followup.send(embed=embed, ephemeral=True)
            else:  # CSV
                csv_data = io.StringIO()
                writer = csv.writer(csv_data)
                writer.writerow(["Event Title", "Event Date", "Role", "Attended"])

                for entry in user_data:
                    writer.writerow([
                        entry["event_title"],
                        entry["event_date"],
                        entry["role"],
                        entry["attended"]
                    ])

                csv_data.seek(0)
                file = discord.File(
                    fp=io.BytesIO(csv_data.getvalue().encode()),
                    filename=f"user_{user.id}_attendance.csv"
                )
                await interaction.followup.send(
                    f"Here's the attendance data for {user.display_name}:",
                    file=file,
                    ephemeral=True
                )

        elif view_type == "role":
            # Get role attendance data
            role_data = []
            for event_id, event in guild_events.items():
                event_time_str = event.get("time", "Unknown")
                try:
                    event_time = datetime.strptime(event_time_str, "%Y-%m-%d %H:%M")
                    event_date = event_time.strftime("%Y-%m-%d")
                except ValueError:
                    event_date = "Unknown"

                # Find the role that matches the filter
                for role_id, role_data_item in event.get("roles", {}).items():
                    if role_data_item.get("name", "").lower() == role_name.lower():
                        # Add each user in this role
                        for user_id in role_data_item.get("users", []):
                            member = interaction.guild.get_member(int(user_id))
                            user_name = member.display_name if member else f"Unknown User ({user_id})"
                            role_data.append({
                                "event_title": event.get("title", "Unknown Event"),
                                "event_date": event_date,
                                "user_name": user_name,
                                "user_id": user_id
                            })

            # Output the data
            if output_format == "discord":
                if not role_data:
                    await interaction.followup.send(
                        f"No attendance data found for role '{role_name}'.",
                        ephemeral=True
                    )
                    return

                # Group by event
                events_dict = {}
                for entry in role_data:
                    event_key = f"{entry['event_title']} ({entry['event_date']})"
                    if event_key not in events_dict:
                        events_dict[event_key] = []
                    events_dict[event_key].append(entry['user_name'])

                # Create an embed to display the data
                embed = discord.Embed(
                    title=f"Attendance for Role '{role_name}'",
                    color=discord.Color.blue()
                )

                # Add fields for each event (up to 25 fields max)
                for i, (event_name, users) in enumerate(list(events_dict.items())[:25]):
                    embed.add_field(
                        name=event_name,
                        value="\n".join(users[:10]) + (f"\n...and {len(users) - 10} more" if len(users) > 10 else ""),
                        inline=True
                    )

                if len(events_dict) > 25:
                    embed.set_footer(text=f"Showing 25 of {len(events_dict)} events. Use CSV export to see all.")

                await interaction.followup.send(embed=embed, ephemeral=True)
            else:  # CSV
                csv_data = io.StringIO()
                writer = csv.writer(csv_data)
                writer.writerow(["Event Title", "Event Date", "User", "User ID"])

                for entry in role_data:
                    writer.writerow([
                        entry["event_title"],
                        entry["event_date"],
                        entry["user_name"],
                        entry["user_id"]
                    ])

                csv_data.seek(0)
                file = discord.File(
                    fp=io.BytesIO(csv_data.getvalue().encode()),
                    filename=f"role_{role_name}_attendance.csv"
                )
                await interaction.followup.send(
                    f"Here's the attendance data for role '{role_name}':",
                    file=file,
                    ephemeral=True
                )

        elif view_type == "date":
            # Get date attendance data
            date_data = []
            for event_id, event in guild_events.items():
                event_time_str = event.get("time", "Unknown")
                try:
                    event_time = datetime.strptime(event_time_str, "%Y-%m-%d %H:%M")
                    event_date = event_time.strftime("%Y-%m-%d")
                except ValueError:
                    event_date = "Unknown"

                # Check if event matches the filter date
                if event_date == date:  # Compare string to string
                    for role_id, role_data_item in event.get("roles", {}).items():
                        if role_data_item.get("name"):
                            for user_id in role_data_item.get("users", []):
                                member = interaction.guild.get_member(int(user_id))
                                user_name = member.display_name if member else f"Unknown User ({user_id})"
                                date_data.append({
                                    "event_title": event.get("title", "Unknown Event"),
                                    "role": role_data_item.get("name", "Unknown Role"),
                                    "user_name": user_name,
                                    "user_id": user_id
                                })

            # Output the data
            if output_format == "discord":
                if not date_data:
                    await interaction.followup.send(
                        f"No attendance data found for date '{date}'.",
                        ephemeral=True
                    )
                    return

                # Group by event and role
                events_dict = {}
                for entry in date_data:
                    event_key = entry['event_title']
                    role_key = entry['role']

                    if event_key not in events_dict:
                        events_dict[event_key] = {}

                    if role_key not in events_dict[event_key]:
                        events_dict[event_key][role_key] = []

                    events_dict[event_key][role_key].append(entry['user_name'])

                # Create an embed to display the data
                embed = discord.Embed(
                    title=f"Attendance for Date '{date}'",
                    color=discord.Color.blue()
                )

                # Add fields for each event and role
                for event_name, roles in events_dict.items():
                    for role_name, users in roles.items():
                        embed.add_field(
                            name=f"{event_name} - {role_name} ({len(users)})",
                            value="\n".join(users[:10]) + (
                                f"\n...and {len(users) - 10} more" if len(users) > 10 else ""),
                            inline=True
                        )

                await interaction.followup.send(embed=embed, ephemeral=True)
            else:  # CSV
                csv_data = io.StringIO()
                writer = csv.writer(csv_data)
                writer.writerow(["Event Title", "Role", "User", "User ID"])

                for entry in date_data:
                    writer.writerow([
                        entry["event_title"],
                        entry["role"],
                        entry["user_name"],
                        entry["user_id"]
                    ])

                csv_data.seek(0)
                file = discord.File(
                    fp=io.BytesIO(csv_data.getvalue().encode()),
                    filename=f"date_{date}_attendance.csv"
                )
                await interaction.followup.send(
                    f"Here's the attendance data for date '{date}':",
                    file=file,
                    ephemeral=True
                )

        elif view_type == "all":
            # Get all attendance data
            all_data = []
            for event_id, event in guild_events.items():
                event_time_str = event.get("time", "Unknown")
                try:
                    event_time = datetime.strptime(event_time_str, "%Y-%m-%d %H:%M")
                    event_date = event_time.strftime("%Y-%m-%d")
                except ValueError:
                    event_date = "Unknown"

                for role_id, role_data_item in event.get("roles", {}).items():
                    if role_data_item.get("name"):
                        for user_id in role_data_item.get("users", []):
                            member = interaction.guild.get_member(int(user_id))
                            user_name = member.display_name if member else f"Unknown User ({user_id})"
                            all_data.append({
                                "event_title": event.get("title", "Unknown Event"),
                                "event_date": event_date,
                                "role": role_data_item.get("name", "Unknown Role"),
                                "user_name": user_name,
                                "user_id": user_id
                            })

            # Output the data
            if output_format == "discord":
                if not all_data:
                    await interaction.followup.send("No attendance data found.", ephemeral=True)
                    return

                # For "all" data, it's usually too much for Discord embeds
                # So we'll summarize by event
                events_summary = {}
                for entry in all_data:
                    event_key = f"{entry['event_title']} ({entry['event_date']})"
                    if event_key not in events_summary:
                        events_summary[event_key] = {"total": 0, "roles": {}}

                    events_summary[event_key]["total"] += 1

                    role_name = entry["role"]
                    if role_name not in events_summary[event_key]["roles"]:
                        events_summary[event_key]["roles"][role_name] = 0

                    events_summary[event_key]["roles"][role_name] += 1

                # Create an embed to display the summary
                embed = discord.Embed(
                    title="Attendance Summary",
                    description=f"Total Events: {len(events_summary)}",
                    color=discord.Color.blue()
                )

                # Add fields for each event (up to 25 fields max)
                for i, (event_name, data) in enumerate(list(events_summary.items())[:25]):
                    role_summary = "\n".join([f"{role}: {count}" for role, count in data["roles"].items()])
                    embed.add_field(
                        name=f"{event_name} (Total: {data['total']})",
                        value=role_summary or "No roles",
                        inline=True
                    )

                if len(events_summary) > 25:
                    embed.set_footer(text=f"Showing 25 of {len(events_summary)} events. Use CSV export to see all.")

                await interaction.followup.send(embed=embed, ephemeral=True)
            else:  # CSV
                csv_data = io.StringIO()
                writer = csv.writer(csv_data)
                writer.writerow(["Event Title", "Event Date", "Role", "User", "User ID"])

                for entry in all_data:
                    writer.writerow([
                        entry["event_title"],
                        entry["event_date"],
                        entry["role"],
                        entry["user_name"],
                        entry["user_id"]
                    ])

                csv_data.seek(0)
                file = discord.File(
                    fp=io.BytesIO(csv_data.getvalue().encode()),
                    filename="all_attendance.csv"
                )
                await interaction.followup.send(
                    "Here's all attendance data:",
                    file=file,
                    ephemeral=True
                )

        else:
            await interaction.followup.send(
                "Invalid view type. Please use 'user', 'role', 'date', or 'all'.",
                ephemeral=True
            )

    @app_commands.command(name="edit", description="Edit an existing attendance event")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def edit_event(self, interaction: discord.Interaction, event_id: str, field: str, value: str):
        """Edit an existing attendance event"""
        await self.load_events(interaction.guild.id)
        event = self.events.get(event_id)
        if not event:
            return await interaction.response.send_message("Event not found.", ephemeral=True)
        if event["guild_id"] != interaction.guild.id:
            return await interaction.response.send_message("Event not found in this guild.", ephemeral=True)

        # Update the field
        if field.lower() == "title":
            event["title"] = value
        elif field.lower() == "description":
            event["description"] = value
        elif field.lower() == "time":
            # Validate time format
            try:
                # Parse the input time string
                naive_time = datetime.strptime(value, "%Y-%m-%d %H:%M")
                # Convert EST to UTC for storage
                est = timezone('US/Eastern')
                est_time = est.localize(naive_time)
                utc_time = est_time.astimezone(pytz.UTC)
                # Store in UTC format
                event["time"] = utc_time.strftime("%Y-%m-%d %H:%M")
                # Reschedule reminders and cleanup
                event_time_dt = utc_time
                time_diff = event_time_dt - datetime.now(pytz.UTC)
                # Cancel existing tasks
                await self.cancel_task_safely(self.reminder_tasks, event_id)
                await self.cancel_task_safely(self.cleanup_tasks, event_id)
                # Schedule new tasks
                if time_diff.total_seconds() > 1800:  # Only schedule if more than 30 minutes away
                    self.reminder_tasks[event_id] = self.bot.loop.create_task(
                        self.send_reminder(event_id, time_diff)
                    )
                cleanup_time = event_time_dt + timedelta(days=1)
                cleanup_diff = cleanup_time - datetime.now(pytz.UTC)
                self.cleanup_tasks[event_id] = self.bot.loop.create_task(
                    self.cleanup_event(event_id, cleanup_diff)
                )
            except ValueError:
                return await interaction.response.send_message(
                    "Invalid time format. Please use YYYY-MM-DD HH:MM",
                    ephemeral=True
                )
        elif field.lower() == "location":
            event["location"] = value
        else:
            return await interaction.response.send_message(
                "Invalid field. Please use 'title', 'description', 'time', or 'location'.",
                ephemeral=True
            )

        # Update the event message
        await self.update_event_message(event_id)
        # Save the updated event data
        await self.save_events(event["guild_id"])
        await interaction.response.send_message(f"Event '{event['title']}' has been updated.", ephemeral=True)

    @app_commands.command(name="cleanup_events", description="Manually clean up old events")
    @app_commands.describe(
        force="Force cleanup of all past events regardless of age",
        dry_run="Show what would be cleaned up without actually doing it")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def cleanup_events(
            self,
            interaction: discord.Interaction,
            force: bool = False,
            dry_run: bool = False):
        """Manually trigger cleanup of old events"""
        try:
            # Check permissions
            if not interaction.user.guild_permissions.manage_events:
                await interaction.response.send_message(
                    "❌ You don't have permission to use this command.",
                    ephemeral=True
                )
                return

            # Send initial response
            action = "Simulating" if dry_run else "Starting"
            await interaction.response.send_message(f"{action} cleanup of old events...", ephemeral=True)

            # CHANGE THIS LINE - use 'Attendance' instead of 'EventManager'
            event_manager = self.bot.get_cog('Attendance')
            if not event_manager:
                await interaction.followup.send("❌ Attendance cog not found.", ephemeral=True)
                return

            # OR EVEN BETTER - just use self since this command is inside the Attendance cog
            # Remove the event_manager lookup entirely and use self:

            # Load events for this guild
            await self.load_events(interaction.guild.id)

            # Get current time
            now = self.get_time_provider().now(pytz.UTC)
            events_to_cleanup = []
            recurring_events = []

            # Analyze events - use self.events instead of event_manager.events
            for event_id, event in self.events.items():
                try:
                    # Only process events for this guild
                    if event.get("guild_id") != str(interaction.guild.id):
                        continue

                    if not event.get("time"):
                        continue

                    event_time_str = event.get("time")
                    event_time = datetime.strptime(event_time_str, "%Y-%m-%d %H:%M")
                    event_time = event_time.replace(tzinfo=pytz.UTC)
                    time_since_event = now - event_time

                    # Check cleanup criteria
                    should_cleanup = False
                    if force and time_since_event.total_seconds() > 0:  # Any past event if force
                        should_cleanup = True
                    elif time_since_event.total_seconds() > 2 * 24 * 60 * 60:  # More than 2 days
                        should_cleanup = True

                    if should_cleanup:
                        events_to_cleanup.append({
                            'id': event_id,
                            'title': event.get('title', 'Untitled'),
                            'time': event_time_str,
                            'recurring': event.get('recurring', False),
                            'days_old': time_since_event.days
                        })
                        if event.get('recurring'):
                            recurring_events.append(event_id)

                except Exception as e:
                    print(f"Error analyzing event {event_id}: {e}")

            # Create summary message
            if not events_to_cleanup:
                await interaction.followup.send(
                    "✅ No old events found that need cleanup!",
                    ephemeral=True
                )
                return

            # Build detailed message
            message_parts = []
            if dry_run:
                message_parts.append(f"🔍 **DRY RUN** - Found {len(events_to_cleanup)} events that would be cleaned up:")
            else:
                message_parts.append(f"🧹 Found {len(events_to_cleanup)} events to clean up:")

            # Group events by type
            non_recurring = [e for e in events_to_cleanup if not e['recurring']]
            recurring = [e for e in events_to_cleanup if e['recurring']]

            if non_recurring:
                message_parts.append(f"\n**Non-recurring events to delete ({len(non_recurring)}):**")
                for event in non_recurring[:5]:  # Show first 5
                    message_parts.append(f"• {event['title']} ({event['days_old']} days old)")
                if len(non_recurring) > 5:
                    message_parts.append(f"• ... and {len(non_recurring) - 5} more")

            if recurring:
                message_parts.append(f"\n**Recurring events to update ({len(recurring)}):**")
                for event in recurring[:5]:  # Show first 5
                    message_parts.append(f"• {event['title']} (will schedule next occurrence)")
                if len(recurring) > 5:
                    message_parts.append(f"• ... and {len(recurring) - 5} more")

            # Send summary
            summary_message = "\n".join(message_parts)
            await interaction.followup.send(summary_message, ephemeral=True)

            # Actually perform cleanup if not dry run
            if not dry_run:
                cleaned_count = 0
                errors = 0

                for event_info in events_to_cleanup:
                    try:
                        event_id = event_info['id']
                        # Use self instead of event_manager
                        if event_id in self.events:
                            event = self.events[event_id]

                            # Remove roles
                            await self.remove_event_roles(event_id)

                            # Delete message
                            if "message_id" in event and "channel_id" in event:
                                try:
                                    channel = interaction.guild.get_channel(int(event.get("channel_id")))
                                    if channel:
                                        try:
                                            message = await channel.fetch_message(int(event.get("message_id")))
                                            await message.delete()
                                        except discord.NotFound:
                                            pass  # Already deleted
                                except Exception as e:
                                    print(f"Error deleting message for event {event_id}: {e}")

                            # Handle based on type
                            if event.get("recurring"):
                                await self.schedule_next_occurrence(event_id)
                            else:
                                del self.events[event_id]
                                await self.save_events(interaction.guild.id)

                            cleaned_count += 1

                    except Exception as e:
                        print(f"Error cleaning up event {event_info['id']}: {e}")
                        errors += 1

                # Send final results
                result_message = f"✅ **Cleanup completed!**\n"
                result_message += f"• Successfully processed: {cleaned_count} events\n"
                if errors > 0:
                    result_message += f"• Errors encountered: {errors} events\n"

                # Count remaining events for this guild
                remaining_events = len([e for e in self.events.values()
                                        if e.get("guild_id") == str(interaction.guild.id)])
                result_message += f"• Remaining events: {remaining_events}"

                await interaction.followup.send(result_message, ephemeral=True)

        except Exception as e:
            print(f"Error in cleanup_events command: {e}")
            import traceback
            traceback.print_exc()
            error_message = f"❌ An error occurred during cleanup: {str(e)}"
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(error_message, ephemeral=True)
                else:
                    await interaction.followup.send(error_message, ephemeral=True)
            except:
                pass

    @app_commands.command(name="test_sheets", description="Test Google Sheets integration for this server")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def test_sheets(self, interaction: discord.Interaction):
        """Test Google Sheets integration for this specific server"""
        await interaction.response.defer(ephemeral=True)
        try:
            if not self.attendance_tracker.sheets_enabled:
                await interaction.followup.send(
                    "❌ Google Sheets integration is disabled.\n"
                    "Check your `google_credentials.json` file.",
                    ephemeral=True
                )
                return

            # Test writing to the sheet for this guild
            test_result = await self.attendance_tracker.log_to_google_sheets(
                user_id=interaction.user.id,
                username=f"TEST - {interaction.user.display_name}",
                event_id="test_event_123",
                event_title="Test Event",
                role_id="test_role_456",
                role_name="Test Role",
                action="test",
                guild_id=interaction.guild.id,
                guild_name=interaction.guild.name
            )

            if test_result:
                sheet_name = self.attendance_tracker.get_sheet_name(
                    str(interaction.guild.id),
                    interaction.guild.name
                )
                sheet_url = self.attendance_tracker.get_sheet_url(str(interaction.guild.id))

                embed = discord.Embed(
                    title="✅ Google Sheets Test Successful!",
                    color=0x00ff00,
                    description=f"Successfully logged test data for **{interaction.guild.name}**"
                )
                embed.add_field(name="Sheet Name", value=sheet_name, inline=False)
                embed.add_field(name="Guild", value=f"{interaction.guild.name} ({interaction.guild.id})", inline=True)
                embed.add_field(name="Test User", value=interaction.user.display_name, inline=True)

                if sheet_url:
                    embed.add_field(name="Sheet URL", value=f"[Open Sheet]({sheet_url})", inline=False)

                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(
                    "❌ Failed to write to Google Sheets. Check the console for error details.",
                    ephemeral=True
                )
        except Exception as e:
            await interaction.followup.send(
                f"❌ Error testing Google Sheets:\n```{str(e)}```",
                ephemeral=True
            )

    @app_commands.command(name="sheets_info", description="Get Google Sheets info for this server")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def sheets_info(self, interaction: discord.Interaction):
        """Get Google Sheets information for this server"""
        await interaction.response.defer(ephemeral=True)

        if not self.attendance_tracker.sheets_enabled:
            await interaction.followup.send(
                "❌ Google Sheets integration is disabled.",
                ephemeral=True
            )
            return

        try:
            guild_id = str(interaction.guild.id)
            sheet_name = self.attendance_tracker.get_sheet_name(guild_id, interaction.guild.name)

            embed = discord.Embed(
                title="📊 Google Sheets Info",
                color=0x4285f4,
                description=f"Information for **{interaction.guild.name}**"
            )

            embed.add_field(name="Sheet Name", value=sheet_name, inline=False)
            embed.add_field(name="Guild ID", value=guild_id, inline=True)
            embed.add_field(
                name="Status",
                value="✅ Enabled" if self.attendance_tracker.sheets_enabled else "❌ Disabled",
                inline=True
            )

            # Try to actually access the sheet instead of just checking cache
            try:
                sheet = self.attendance_tracker.gc.open(sheet_name)
                embed.add_field(name="Sheet Status", value="✅ Sheet exists and accessible", inline=False)
                embed.add_field(name="Sheet URL", value=f"[Open Sheet]({sheet.url})", inline=False)

                # Get record count
                try:
                    worksheet = sheet.sheet1
                    records = worksheet.get_all_records()
                    embed.add_field(name="Total Records", value=str(len(records)), inline=True)

                    if records:
                        # Most recent entry (assuming newest are at the top)
                        last_entry = records[0] if records else None
                        if last_entry and 'Timestamp' in last_entry:
                            embed.add_field(name="Last Entry", value=last_entry['Timestamp'], inline=True)
                        else:
                            embed.add_field(name="Last Entry", value="No timestamp found", inline=True)
                    else:
                        embed.add_field(name="Last Entry", value="No records yet", inline=True)

                    # Add to cache now that we've accessed it
                    self.attendance_tracker.sheets_cache[guild_id] = worksheet

                except Exception as records_error:
                    embed.add_field(name="Records", value=f"Error reading records: {str(records_error)}", inline=True)

            except Exception as sheet_error:
                if "not found" in str(sheet_error).lower():
                    embed.add_field(
                        name="Sheet Status",
                        value="❌ Sheet not found (will be created on first use)",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="Sheet Status",
                        value=f"❌ Error accessing sheet: {str(sheet_error)}",
                        inline=False
                    )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            await interaction.followup.send(
                f"❌ Error getting sheet info:\n```{str(e)}```",
                ephemeral=True
            )

    @app_commands.command(name="set_sheets_email", description="Set email to receive attendance sheets for this server")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(email="Email address to share attendance sheets with")
    async def set_sheets_email(self, interaction: discord.Interaction, email: str):
        """Set email to receive attendance sheets for this server"""
        # Check if user has manage server permissions
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "❌ You need 'Manage Server' permission to use this command.",
                ephemeral=True
            )
            return

        # Validate email format (basic check)
        import re
        if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            await interaction.response.send_message(
                "❌ Please provide a valid email address.",
                ephemeral=True
            )
            return

        # Save email for this guild
        guild_id = str(interaction.guild.id)
        if not hasattr(self, 'guild_sheet_emails'):
            self.guild_sheet_emails = {}

        self.guild_sheet_emails[guild_id] = email

        # Save to file
        self.save_guild_emails()

        await interaction.response.send_message(
            f"✅ Attendance sheets for this server will be shared with: `{email}`",
            ephemeral=True
        )

    def save_guild_emails(self):
        """Save guild email configurations"""
        try:
            os.makedirs('./databases', exist_ok=True)
            with open('./databases/guild_sheet_emails.json', 'w') as f:
                json.dump(getattr(self, 'guild_sheet_emails', {}), f)
        except Exception as e:
            print(f"Error saving guild emails: {e}")

    def load_guild_emails(self):
        """Load guild email configurations"""
        try:
            if os.path.exists('./databases/guild_sheet_emails.json'):
                with open('./databases/guild_sheet_emails.json', 'r') as f:
                    self.guild_sheet_emails = json.load(f)
            else:
                self.guild_sheet_emails = {}
        except Exception as e:
            print(f"Error loading guild emails: {e}")
            self.guild_sheet_emails = {}

    @app_commands.command(name="debug_sheets", description="Debug Google Sheets integration")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def debug_sheets(self, interaction: discord.Interaction):
        """Debug Google Sheets integration"""
        await interaction.response.defer(ephemeral=True)

        debug_info = []

        # Check basic setup
        debug_info.append(f"**Basic Setup:**")
        debug_info.append(f"• Sheets enabled: {self.attendance_tracker.sheets_enabled}")
        debug_info.append(f"• Has credentials: {hasattr(self.attendance_tracker, 'gc')}")

        # Check guild-specific info
        guild_id = str(interaction.guild.id)
        debug_info.append(f"\n**Guild Info:**")
        debug_info.append(f"• Guild ID: {guild_id}")
        debug_info.append(f"• Guild name: {interaction.guild.name}")

        # Check sheet cache
        debug_info.append(f"\n**Sheet Cache:**")
        if hasattr(self.attendance_tracker, 'sheets_cache'):
            debug_info.append(f"• Cache exists: Yes")
            debug_info.append(f"• Guilds in cache: {list(self.attendance_tracker.sheets_cache.keys())}")
            debug_info.append(f"• This guild in cache: {guild_id in self.attendance_tracker.sheets_cache}")
        else:
            debug_info.append(f"• Cache exists: No")

        # Check email setup
        debug_info.append(f"\n**Email Setup:**")
        if hasattr(self, 'guild_sheet_emails'):
            debug_info.append(f"• Email config exists: Yes")
            debug_info.append(f"• Email for this guild: {self.guild_sheet_emails.get(guild_id, 'Not set')}")
        else:
            debug_info.append(f"• Email config exists: No")

        # Try to manually create/access sheet
        debug_info.append(f"\n**Manual Sheet Test:**")
        try:
            sheet_name = self.attendance_tracker.get_sheet_name(guild_id, interaction.guild.name)
            debug_info.append(f"• Generated sheet name: {sheet_name}")

            # Try to open or create the sheet
            if hasattr(self.attendance_tracker, 'gc'):
                try:
                    sheet = self.attendance_tracker.gc.open(sheet_name)
                    debug_info.append(f"• Sheet exists: Yes")
                    debug_info.append(f"• Sheet URL: {sheet.url}")

                    # Check if email is set for sharing
                    email = self.guild_sheet_emails.get(guild_id) if hasattr(self, 'guild_sheet_emails') else None
                    if email:
                        debug_info.append(f"• Will share with: {email}")
                    else:
                        debug_info.append(f"• No email set for sharing")

                except Exception as e:
                    debug_info.append(f"• Sheet exists: No ({str(e)})")
                    debug_info.append(f"• Attempting to create...")

                    try:
                        # Try to create the sheet
                        sheet = self.attendance_tracker.gc.create(sheet_name)
                        debug_info.append(f"• Sheet created: Yes")
                        debug_info.append(f"• New sheet URL: {sheet.url}")

                        # Try to share it
                        email = self.guild_sheet_emails.get(guild_id) if hasattr(self, 'guild_sheet_emails') else None
                        if email:
                            sheet.share(email, perm_type='user', role='writer')
                            debug_info.append(f"• Shared with {email}: Success")
                        else:
                            debug_info.append(f"• No email to share with")

                    except Exception as create_error:
                        debug_info.append(f"• Sheet creation failed: {str(create_error)}")
            else:
                debug_info.append(f"• No Google client available")

        except Exception as e:
            debug_info.append(f"• Manual test failed: {str(e)}")

        # Send debug info
        debug_message = "\n".join(debug_info)
        if len(debug_message) > 2000:
            # Split into multiple messages if too long
            chunks = [debug_message[i:i + 2000] for i in range(0, len(debug_message), 2000)]
            for i, chunk in enumerate(chunks):
                if i == 0:
                    await interaction.followup.send(f"```\n{chunk}\n```", ephemeral=True)
                else:
                    await interaction.followup.send(f"```\n{chunk}\n```", ephemeral=True)
        else:
            await interaction.followup.send(f"```\n{debug_message}\n```", ephemeral=True)

    @app_commands.command(name="share_sheet",
                          description="Manually share the attendance sheet with the configured email")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def share_sheet(self, interaction: discord.Interaction):
        """Manually share the attendance sheet with the configured email"""
        await interaction.response.defer(ephemeral=True)

        guild_id = str(interaction.guild.id)

        # Check if email is configured
        if not hasattr(self, 'guild_sheet_emails') or guild_id not in self.guild_sheet_emails:
            await interaction.followup.send(
                "❌ No email configured for this server. Use `/set_sheets_email` first.",
                ephemeral=True
            )
            return

        email = self.guild_sheet_emails[guild_id]

        try:
            # Get the sheet
            sheet_name = self.attendance_tracker.get_sheet_name(guild_id, interaction.guild.name)
            sheet = self.attendance_tracker.gc.open(sheet_name)

            # Try to share it
            await interaction.followup.send(f"🔄 Attempting to share sheet with {email}...", ephemeral=True)

            # Share with different permission levels to see what works
            try:
                sheet.share(email, perm_type='user', role='writer', notify=True)
                await interaction.followup.send(f"✅ Successfully shared sheet with {email} as writer!", ephemeral=True)
            except Exception as writer_error:
                try:
                    sheet.share(email, perm_type='user', role='reader', notify=True)
                    await interaction.followup.send(f"✅ Successfully shared sheet with {email} as reader!",
                                                    ephemeral=True)
                except Exception as reader_error:
                    await interaction.followup.send(
                        f"❌ Failed to share sheet:\n"
                        f"Writer error: {str(writer_error)}\n"
                        f"Reader error: {str(reader_error)}",
                        ephemeral=True
                    )

        except Exception as e:
            await interaction.followup.send(
                f"❌ Error sharing sheet: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="test_manual_log", description="Manually test logging to Google Sheets")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def test_manual_log(self, interaction: discord.Interaction):
        """Manually test the Google Sheets logging function"""
        await interaction.response.defer(ephemeral=True)

        try:
            # Call the actual logging function that should be called when clicking roles
            result = await self.attendance_tracker.log_to_google_sheets(
                user_id=interaction.user.id,
                username=interaction.user.display_name,
                event_id="manual_test_123",
                event_title="Manual Test Event",
                role_id="manual_role_456",
                role_name="Manual Test Role",
                action="joined",
                guild_id=interaction.guild.id,
                guild_name=interaction.guild.name
            )

            if result:
                await interaction.followup.send("✅ Manual logging test successful!", ephemeral=True)
            else:
                await interaction.followup.send("❌ Manual logging test failed!", ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"❌ Error in manual test: {str(e)}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Attendance(bot))



