import discord
from discord.ext import commands
import json
import os
import asyncio
import io
from datetime import datetime as dt, timedelta
import pytz
from pytz import timezone

# Constants
PASTEL_BLUE = 0x9DB2FF


class TestAttendanceView(discord.ui.View):
    def __init__(self, cog, event_id):
        super().__init__(timeout=None)
        self.cog = cog
        self.event_id = event_id
        # Add toggle buttons for each role
        for i, (role_id, role_data) in enumerate(cog.test_events[event_id]["roles"].items()):
            button = TestRoleButton(
                role_id=role_id,
                label=f"{role_data['name']}",
                style=discord.ButtonStyle.primary,
                custom_id=f"test_attendance:{event_id}:{role_id}:toggle",
                cog=cog,
                row=i // 5  # This puts up to 5 buttons per row
            )
            self.add_item(button)


class TestRoleButton(discord.ui.Button):
    def __init__(self, role_id, label, style, custom_id, cog, row=None):
        super().__init__(label=label, style=style, custom_id=custom_id, row=row)
        self.role_id = role_id
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        # Parse the custom_id to get event_id, role_id
        parts = self.custom_id.split(":")
        event_id = parts[1]
        role_id = parts[2]
        # Get the event and role data
        event = self.cog.test_events.get(event_id)
        if not event:
            await interaction.response.send_message("This test event no longer exists.", ephemeral=True)
            return
        role_data = event["roles"].get(role_id)
        if not role_data:
            await interaction.response.send_message("This role no longer exists.", ephemeral=True)
            return
        # Toggle user in/out of the role
        if interaction.user.id in role_data["users"]:
            # Remove the user from the role
            role_data["users"].remove(interaction.user.id)
            await interaction.response.send_message(
                f"You've been removed from {role_data['name']}.", ephemeral=True)
        else:
            # Add the user to the role
            role_data["users"].append(interaction.user.id)
            await interaction.response.send_message(
                f"You've signed up for {role_data['name']}!", ephemeral=True)
        # Update the event message
        await self.cog.update_test_event_message(event_id)
        # Save the events
        await self.cog.save_test_events(interaction.guild.id)


class TestAttendanceRegular(commands.Cog):
    """Cog for testing attendance events with accelerated time using regular commands"""

    def __init__(self, bot):
        self.bot = bot
        self.test_events = {}
        self.test_reminder_tasks = {}

    async def cog_load(self):
        """Load test events when the cog is loaded"""
        print("TestAttendanceRegular cog loaded")
        os.makedirs("test_data", exist_ok=True)

        # Load existing events
        for guild in self.bot.guilds:
            try:
                await self.load_test_events(guild.id)
            except:
                pass

    async def load_test_events(self, guild_id):
        """Load test events from file"""
        try:
            with open(f"test_data/test_attendance_events_{guild_id}.json", "r") as f:
                self.test_events.update(json.load(f))
                print(f"Loaded {len(self.test_events)} test events for guild {guild_id}")

                # Start accelerated checks for all events
                for event_id in self.test_events:
                    self.bot.loop.create_task(self.accelerated_check_reminders(event_id))
        except FileNotFoundError:
            print(f"No test events file found for guild {guild_id}")
        except Exception as e:
            print(f"Error loading test events: {e}")

    async def save_test_events(self, guild_id):
        """Save test events to file"""
        os.makedirs("test_data", exist_ok=True)
        with open(f"test_data/test_attendance_events_{guild_id}.json", "w") as f:
            json.dump(self.test_events, f, indent=4)

    async def update_test_event_message(self, event_id):
        """Update the test event message with current signups"""
        if event_id not in self.test_events:
            return
        event = self.test_events[event_id]
        # Create the embed
        embed = discord.Embed(
            title=event["title"],
            description=event["description"],
            color=PASTEL_BLUE
        )
        formatted_time = self.format_time_for_user(event["time"])
        embed.add_field(name="Time", value=formatted_time, inline=True)
        embed.add_field(name="Location", value=event["location"], inline=True)
        # Add test info
        embed.add_field(
            name="TEST MODE",
            value=f"Time acceleration: {event['acceleration']}x\n1 hour = {60 / event['acceleration']:.1f} minutes\n1 day = {24 / event['acceleration']:.1f} hours",
            inline=False
        )
        # Create a more compact role display
        roles_text = ""
        for role_id, role_data in event["roles"].items():
            roles_text += f"**{role_data['name']}**:\n"
            if not role_data["users"]:
                roles_text += "• No signups yet\n"
            else:
                for user_id in role_data["users"]:
                    user = self.bot.get_user(user_id)
                    if user:
                        roles_text += f"• {user.display_name}\n"
                    else:
                        roles_text += f"• Unknown User ({user_id})\n"
            roles_text += "\n"
        if roles_text:
            embed.add_field(name="Roles", value=roles_text, inline=False)
        # Add recurring info as footer if applicable
        if event.get("recurring"):
            if event["recurring_interval"] == 1:
                recurring_text = "Weekly"
            elif event["recurring_interval"] == 2:
                recurring_text = "Biweekly"
            else:
                recurring_text = f"Every {event['recurring_interval']} weeks"
            embed.set_footer(text=f"Recurring: {recurring_text}")
        # Update the message
        try:
            channel = self.bot.get_channel(event["channel_id"])
            message = await channel.fetch_message(event["message_id"])
            await message.edit(embed=embed)
        except Exception as e:
            print(f"Error updating test event message: {e}")

    def format_time_for_user(self, time_str):
        """Format the time string for display to users, using Discord's timestamp feature"""
        try:
            # Parse the stored UTC time
            event_time = dt.strptime(time_str, "%Y-%m-%d %H:%M")
            event_time = event_time.replace(tzinfo=pytz.UTC)
            # Convert to Unix timestamp (seconds since epoch)
            unix_timestamp = int(event_time.timestamp())
            # Use Discord's timestamp formatting
            formatted_time = f"<t:{unix_timestamp}:f> (<t:{unix_timestamp}:R>)"
            return formatted_time
        except Exception as e:
            print(f"Error formatting time: {e}")
            return time_str

    @commands.command(name="testcreate")
    @commands.has_permissions(administrator=True)
    async def create_test_event(self, ctx, hours_from_now: int = 2, acceleration: int = 60, recurring: bool = True,
                                interval: int = 2):
        """Create a test event with accelerated time

        Usage: !testcreate [hours_from_now] [acceleration] [recurring] [interval]
        Example: !testcreate 2 60 True 2
        """
        # Create a unique test event ID
        test_id = f"test_{dt.now().strftime('%Y%m%d%H%M%S')}"
        # Create event time
        now = dt.now(pytz.UTC)
        event_time = now + timedelta(hours=hours_from_now)
        # Create test event
        test_event = {
            "title": f"Test Event {test_id}",
            "description": f"This is a test event with {acceleration}x time acceleration",
            "time": event_time.strftime("%Y-%m-%d %H:%M"),
            "location": "Test Location",
            "roles": {
                "role_1": {
                    "name": "Test Role 1",
                    "restricted": False,
                    "users": []
                },
                "role_2": {
                    "name": "Test Role 2",
                    "restricted": False,
                    "users": []
                }
            },
            "recurring": recurring,
            "recurring_interval": interval,
            "acceleration": acceleration,
            "guild_id": ctx.guild.id,
            "channel_id": ctx.channel.id,
            "created_by": ctx.author.id,
            "created_at": now.strftime("%Y-%m-%d %H:%M:%S")
        }
        # Add the event to the dictionary BEFORE creating the view
        self.test_events[test_id] = test_event
        # Create embed
        embed = discord.Embed(
            title=test_event["title"],
            description=test_event["description"],
            color=PASTEL_BLUE
        )
        formatted_time = self.format_time_for_user(test_event["time"])
        embed.add_field(name="Time", value=formatted_time, inline=True)
        embed.add_field(name="Location", value=test_event["location"], inline=True)
        embed.add_field(name="Recurring", value="Yes" if test_event["recurring"] else "No", inline=True)
        if test_event["recurring"]:
            embed.add_field(name="Interval", value=f"{test_event['recurring_interval']} weeks", inline=True)
        # Add test info
        embed.add_field(
            name="TEST MODE",
            value=f"Time acceleration: {acceleration}x\n1 hour = {60 / acceleration:.1f} minutes\n1 day = {24 / acceleration:.1f} hours",
            inline=False
        )
        # Now create the view after the event is in the dictionary
        view = TestAttendanceView(self, test_id)
        # Send message
        message = await ctx.send(embed=embed, view=view)
        test_event["message_id"] = message.id
        # Save event
        await self.save_test_events(ctx.guild.id)
        # Start the accelerated time checker
        self.bot.loop.create_task(self.accelerated_check_reminders(test_id))
        await ctx.send(
            f"Created test event {test_id} that will occur in {hours_from_now} hours (accelerated {acceleration}x)\n"
            f"The event will behave as if time is passing {acceleration} times faster.\n"
            f"Watch for recurring behavior in the next few minutes!"
        )

    @commands.command(name="testlist")
    @commands.has_permissions(administrator=True)
    async def list_test_events(self, ctx):
        """List all active test events for this server"""
        # Filter events for this guild
        guild_events = {
            event_id: event_data
            for event_id, event_data in self.test_events.items()
            if event_data.get("guild_id") == ctx.guild.id
        }
        if not guild_events:
            await ctx.send("No active test events in this server.")
            return
        embed = discord.Embed(
            title="Active Test Events",
            color=PASTEL_BLUE
        )
        for event_id, event in guild_events.items():
            # Convert UTC time to EST for display
            try:
                event_time = dt.strptime(event["time"], "%Y-%m-%d %H:%M")
                event_time = event_time.replace(tzinfo=pytz.UTC)
                est = timezone('US/Eastern')
                est_time = event_time.astimezone(est)
                time_str = est_time.strftime("%Y-%m-%d %I:%M %p EST")
            except:
                time_str = event["time"]
            channel = self.bot.get_channel(event["channel_id"])
            channel_name = channel.mention if channel else "Unknown channel"
            embed.add_field(
                name=event["title"],
                value=f"Time: {time_str}\nLocation: {event['location']}\nChannel: {channel_name}\nAcceleration: {event['acceleration']}x\nID: `{event_id}`",
                inline=False
            )
        await ctx.send(embed=embed)

    @commands.command(name="testdelete")
    @commands.has_permissions(administrator=True)
    async def delete_test_event(self, ctx, event_id: str):
        """Delete a test event

        Usage: !testdelete [event_id]
        """
        if event_id not in self.test_events:
            await ctx.send("Test event not found. Use `!testlist` to see all test events.")
            return
        # Try to delete the message
        try:
            channel = self.bot.get_channel(self.test_events[event_id]["channel_id"])
            message = await channel.fetch_message(self.test_events[event_id]["message_id"])
            await message.delete()
        except:
            pass
        # Delete the event
        del self.test_events[event_id]
        await self.save_test_events(ctx.guild.id)
        await ctx.send(f"Test event {event_id} has been deleted.")

    @commands.command(name="testclearall")
    @commands.has_permissions(administrator=True)
    async def clear_all_test_events(self, ctx):
        """Delete all test events for this server"""
        # Filter events for this guild
        guild_events = {
            event_id: event_data
            for event_id, event_data in self.test_events.items()
            if event_data.get("guild_id") == ctx.guild.id
        }
        if not guild_events:
            await ctx.send("No active test events in this server.")
            return
        count = 0
        for event_id, event in guild_events.items():
            # Try to delete the message
            try:
                channel = self.bot.get_channel(event["channel_id"])
                message = await channel.fetch_message(event["message_id"])
                await message.delete()
            except:
                pass
            # Delete the event
            del self.test_events[event_id]
            count += 1
        await self.save_test_events(ctx.guild.id)
        await ctx.send(f"Deleted {count} test events.")

    async def accelerated_check_reminders(self, event_id):
        """Check for reminders with accelerated time"""
        if event_id not in self.test_events:
            return
        event = self.test_events[event_id]
        acceleration = event.get("acceleration", 1)
        # Parse the event time
        try:
            event_time = dt.strptime(event["time"], "%Y-%m-%d %H:%M")
            event_time = event_time.replace(tzinfo=pytz.UTC)
        except Exception as e:
            print(f"Error parsing event time: {e}")
            return
        # Calculate the real time to wait (accelerated)
        now = dt.now(pytz.UTC)
        time_until_event = (event_time - now).total_seconds()
        # If the event is in the past, handle recurring logic
        if time_until_event <= 0:
            if event.get("recurring", False):
                # Calculate the next occurrence
                interval_weeks = event.get("recurring_interval", 1)
                # Create the next event (1 week later in event time, but accelerated in real time)
                next_event_time = event_time + timedelta(weeks=interval_weeks)
                # Update the event time
                event["time"] = next_event_time.strftime("%Y-%m-%d %H:%M")
                # Save the events
                await self.save_test_events(event["guild_id"])
                # Announce the new event
                try:
                    channel = self.bot.get_channel(event["channel_id"])
                    # Create a thread for the old event if it doesn't exist
                    if not event.get("thread_id"):
                        try:
                            message = await channel.fetch_message(event["message_id"])
                            thread_name = f"{event['title']} Discussion"
                            thread = await message.create_thread(name=thread_name)
                            event["thread_id"] = thread.id
                            await thread.send("**TEST MODE**: Thread created for event discussion")
                        except Exception as e:
                            print(f"Error creating thread: {e}")
                    # Create a new attendance post for the next occurrence
                    new_embed = discord.Embed(
                        title=event["title"],
                        description=event["description"],
                        color=PASTEL_BLUE
                    )
                    formatted_time = self.format_time_for_user(event["time"])
                    new_embed.add_field(name="Time", value=formatted_time, inline=True)
                    new_embed.add_field(name="Location", value=event["location"], inline=True)
                    # Add test info
                    new_embed.add_field(
                        name="TEST MODE",
                        value=f"Time acceleration: {acceleration}x\n1 hour = {60 / acceleration:.1f} minutes\n1 day = {24 / acceleration:.1f} hours",
                        inline=False
                    )
                    if event.get("recurring"):
                        if event["recurring_interval"] == 1:
                            recurring_text = "Weekly"
                        elif event["recurring_interval"] == 2:
                            recurring_text = "Biweekly"
                        else:
                            recurring_text = f"Every {event['recurring_interval']} weeks"
                        new_embed.set_footer(text=f"Recurring: {recurring_text}")
                    # Clear the signups for the roles
                    for role_id in event["roles"]:
                        event["roles"][role_id]["users"] = []
                    # Delete the old message
                    try:
                        old_message = await channel.fetch_message(event["message_id"])
                        await old_message.delete()
                        await channel.send(
                            f"**TEST MODE**: The event '{event['title']}' has been rescheduled. Old attendance post deleted.",
                        )
                    except Exception as e:
                        print(f"Error deleting old message: {e}")
                    # Create new attendance post
                    view = TestAttendanceView(self, event_id)
                    new_message = await channel.send(
                        f"**TEST MODE**: New attendance post for the recurring event '{event['title']}'",
                        embed=new_embed,
                        view=view
                    )
                    # Update the event with the new message ID
                    event["message_id"] = new_message.id
                    # Save the updated event
                    await self.save_test_events(event["guild_id"])
                except Exception as e:
                    print(f"Error handling recurring event: {e}")
                # Start a new check for the next occurrence
                self.bot.loop.create_task(self.accelerated_check_reminders(event_id))
            else:
                # Non-recurring event in the past - clean it up
                try:
                    channel = self.bot.get_channel(event["channel_id"])
                    await channel.send(
                        f"**TEST MODE**: The event '{event['title']}' has ended and will be removed.",
                        reference=await channel.fetch_message(event["message_id"])
                    )
                    # Try to delete the message
                    message = await channel.fetch_message(event["message_id"])
                    await message.delete()
                except Exception as e:
                    print(f"Error cleaning up past event: {e}")
                # Remove the event
                del self.test_events[event_id]
                await self.save_test_events(event["guild_id"])
            return
        # Accelerate the time
        accelerated_wait = time_until_event / acceleration
        # Check if we need to send a reminder (30 minutes before)
        reminder_time = time_until_event - 1800  # 30 minutes before event
        if reminder_time > 0:
            # Wait until it's time to send the reminder (with acceleration)
            accelerated_reminder_wait = reminder_time / acceleration
            await asyncio.sleep(accelerated_reminder_wait)
            # Send the reminder
            try:
                channel = self.bot.get_channel(event["channel_id"])
                # Get all users who signed up
                all_users = set()
                for role_data in event["roles"].values():
                    all_users.update(role_data["users"])
                # Create the reminder message
                reminder = f"⏰ **TEST MODE: Event Reminder** ⏰\n\n"
                reminder += f"The event '{event['title']}' will start in 30 minutes!\n\n"
                # Send the reminder message
                reminder_message = await channel.send(reminder)
                # Create a thread for the event
                thread_name = f"{event['title']} Discussion"
                thread = await reminder_message.create_thread(name=thread_name, auto_archive_duration=1440)  # 24 hours
                event["thread_id"] = thread.id
                # Create a mention message for the thread
                if all_users:
                    mentions = "Hey everyone! The event is starting soon. "
                    for user_id in all_users:
                        mentions += f"<@{user_id}> "
                    # Send the mentions in the thread
                    await thread.send(mentions)
                    # Send additional information in the thread
                    await thread.send(f"**Event Details:**\n"
                                      f"Title: {event['title']}\n"
                                      f"Description: {event['description']}\n"
                                      f"Location: {event['location']}\n"
                                      f"Starting in: 30 minutes (accelerated)")
                # Save the updated event with thread ID
                await self.save_test_events(event["guild_id"])
            except Exception as e:
                print(f"Error sending reminder: {e}")
            # Calculate remaining time until event
            now = dt.now(pytz.UTC)
            time_until_event = (event_time - now).total_seconds()
            accelerated_wait = time_until_event / acceleration
        # Wait until the event (with acceleration)
        await asyncio.sleep(accelerated_wait)
        # Event is happening now
        try:
            channel = self.bot.get_channel(event["channel_id"])
            await channel.send(
                f"**TEST MODE**: The event '{event['title']}' is happening now!",
                reference=await channel.fetch_message(event["message_id"])
            )
            # If thread exists, send a message there too
            if event.get("thread_id"):
                try:
                    thread = await channel.fetch_thread(event["thread_id"])
                    await thread.send("**TEST MODE**: The event is starting now!")
                except Exception as e:
                    print(f"Error sending message to thread: {e}")
        except Exception as e:
            print(f"Error announcing event: {e}")
        # If recurring, schedule the next occurrence
        if event.get("recurring", False):
            # Calculate the next occurrence
            interval_weeks = event.get("recurring_interval", 1)
            # Create the next event (interval weeks later in event time)
            next_event_time = event_time + timedelta(weeks=interval_weeks)
            # Update the event time
            event["time"] = next_event_time.strftime("%Y-%m-%d %H:%M")
            # Create a new attendance post for the next occurrence
            try:
                channel = self.bot.get_channel(event["channel_id"])
                new_embed = discord.Embed(
                    title=event["title"],
                    description=event["description"],
                    color=PASTEL_BLUE
                )
                formatted_time = self.format_time_for_user(event["time"])
                new_embed.add_field(name="Time", value=formatted_time, inline=True)
                new_embed.add_field(name="Location", value=event["location"], inline=True)
                # Add test info
                new_embed.add_field(
                    name="TEST MODE",
                    value=f"Time acceleration: {acceleration}x\n1 hour = {60 / acceleration:.1f} minutes\n1 day = {24 / acceleration:.1f} hours",
                    inline=False
                )
                if event.get("recurring"):
                    if event["recurring_interval"] == 1:
                        recurring_text = "Weekly"
                    elif event["recurring_interval"] == 2:
                        recurring_text = "Biweekly"
                    else:
                        recurring_text = f"Every {event['recurring_interval']} weeks"
                    new_embed.set_footer(text=f"Recurring: {recurring_text}")
                # Clear the signups for the roles
                for role_id in event["roles"]:
                    event["roles"][role_id]["users"] = []
                # Delete the old message
                try:
                    old_message = await channel.fetch_message(event["message_id"])
                    await old_message.delete()
                    await channel.send(
                        f"**TEST MODE**: The event '{event['title']}' has been rescheduled. Old attendance post deleted.",
                    )
                except Exception as e:
                    print(f"Error deleting old message: {e}")
                # Create new attendance post
                view = TestAttendanceView(self, event_id)
                new_message = await channel.send(
                    f"**TEST MODE**: New attendance post for the recurring event '{event['title']}'",
                    embed=new_embed,
                    view=view
                )
                # Update the event with the new message ID
                event["message_id"] = new_message.id
                # Save the updated event
                await self.save_test_events(event["guild_id"])
            except Exception as e:
                print(f"Error creating new attendance post: {e}")
            # Start a new check for the next occurrence
            self.bot.loop.create_task(self.accelerated_check_reminders(event_id))
        else:
            # Non-recurring event - clean it up
            try:
                channel = self.bot.get_channel(event["channel_id"])
                await channel.send(
                    f"**TEST MODE**: The event '{event['title']}' has ended and will be removed.",
                    reference=await channel.fetch_message(event["message_id"])
                )
                # Try to delete the message
                message = await channel.fetch_message(event["message_id"])
                await message.delete()
            except Exception as e:
                print(f"Error cleaning up past event: {e}")
            # Remove the event
            del self.test_events[event_id]
            await self.save_test_events(event["guild_id"])

async def setup(bot):
    await bot.add_cog(TestAttendanceRegular(bot))

