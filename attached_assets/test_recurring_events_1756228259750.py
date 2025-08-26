import discord
from discord.ext import commands
import asyncio
import datetime
import pytz
from datetime import datetime, timedelta, timezone
import os
import json

# Accelerated time constant (3 minutes = 1 day)
ACCELERATED_TIME = True
ACCELERATION_FACTOR = 480  # 1 day = 3 minutes (180 seconds)


class TestRecurringEvents(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.attendance_cog = None
        self.test_channel_id = None
        self.test_guild_id = None
        self.test_event_id = None

    @commands.Cog.listener()
    async def on_ready(self):
        print("TestRecurringEvents cog is ready!")
        # Find the attendance cog
        self.attendance_cog = self.bot.get_cog("Attendance")
        if not self.attendance_cog:
            print("ERROR: Attendance cog not found!")
            return

    @commands.command()
    @commands.is_owner()
    async def setup_test(self, ctx):
        """Set up the test environment"""
        self.test_channel_id = ctx.channel.id
        self.test_guild_id = ctx.guild.id

        await ctx.send("Test environment set up. Channel and guild IDs recorded.")
        await ctx.send(f"Channel ID: {self.test_channel_id}, Guild ID: {self.test_guild_id}")

    @commands.command()
    @commands.is_owner()
    async def create_test_event(self, ctx):
        """Create a test recurring event"""
        if not self.attendance_cog:
            await ctx.send("Attendance cog not found!")
            return

        if not self.test_channel_id or not self.test_guild_id:
            await ctx.send("Please run !setup_test first!")
            return

        # Calculate event time (current time + 5 minutes in accelerated mode)
        now = datetime.now(timezone.utc)

        # In accelerated mode, 5 minutes = 40 hours (almost 2 days)
        if ACCELERATED_TIME:
            event_time = now + timedelta(minutes=5)
            await ctx.send("ACCELERATED MODE: Event will happen in 5 minutes (simulating ~40 hours)")
        else:
            event_time = now + timedelta(days=2)
            await ctx.send("Event will happen in 2 days")

        # Format the time string
        time_str = event_time.strftime("%Y-%m-%d %H:%M")

        # Create a unique event ID
        self.test_event_id = f"test_event_{now.strftime('%Y%m%d%H%M%S')}"

        # Create the event data
        event_data = {
            "id": self.test_event_id,
            "title": "Test Recurring Event",
            "description": "This is a test recurring event for cleanup and repost testing",
            "time": time_str,
            "location": "Test Location",
            "guild_id": self.test_guild_id,
            "channel_id": self.test_channel_id,
            "roles": {
                "role1": {
                    "name": "Attendee",
                    "users": [],
                    "limit": 10
                },
                "role2": {
                    "name": "Observer",
                    "users": []
                }
            },
            "recurring": True,
            "recurring_interval": 1,  # Weekly
            "event_role_users": []
        }

        # Add the event to the attendance cog
        self.attendance_cog.events[self.test_event_id] = event_data

        # Save the event
        await self.attendance_cog.save_events(self.test_guild_id)

        # Create and send the embed
        embed = await self.attendance_cog.create_event_embed(self.test_event_id)
        view = AttendanceView(self.attendance_cog, self.test_event_id)
        message = await ctx.send(embed=embed, view=view)

        # Update the event with the message ID
        self.attendance_cog.events[self.test_event_id]["message_id"] = message.id
        await self.attendance_cog.save_events(self.test_guild_id)

        # Schedule the cleanup and recurring tasks with accelerated time
        if ACCELERATED_TIME:
            self.bot.loop.create_task(self.accelerated_test(ctx))
        else:
            # Schedule normal tasks
            event_time_dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M").replace(tzinfo=pytz.UTC)
            time_diff = event_time_dt - datetime.now(pytz.UTC)

            # Schedule reminder (30 minutes before event)
            self.attendance_cog.reminder_tasks[self.test_event_id] = self.bot.loop.create_task(
                self.attendance_cog.send_reminder(self.test_event_id, time_diff)
            )

            # Schedule cleanup (2 days after event)
            cleanup_time = event_time_dt + timedelta(days=2)
            cleanup_diff = cleanup_time - datetime.now(pytz.UTC)
            self.attendance_cog.cleanup_tasks[self.test_event_id] = self.bot.loop.create_task(
                self.attendance_cog.cleanup_event(self.test_event_id, cleanup_diff)
            )

            # Schedule next occurrence
            self.attendance_cog.recurring_tasks[self.test_event_id] = self.bot.loop.create_task(
                self.attendance_cog.schedule_next_occurrence(self.test_event_id)
            )

        await ctx.send(f"Test event created with ID: {self.test_event_id}")
        await ctx.send("Event will be automatically cleaned up and reposted in accelerated time.")

    async def accelerated_test(self, ctx):
        """Run the test with accelerated time"""
        await ctx.send("Starting accelerated test...")

        # Get the event
        event = self.attendance_cog.events[self.test_event_id]
        event_time_str = event["time"]
        event_time = datetime.strptime(event_time_str, "%Y-%m-%d %H:%M").replace(tzinfo=pytz.UTC)

        # Calculate the real times for our test
        now = datetime.now(pytz.UTC)

        # 1. Reminder time (30 minutes before event)
        reminder_time = event_time - timedelta(minutes=30)
        reminder_diff = reminder_time - now

        # 2. Event time
        event_diff = event_time - now

        # 3. Cleanup time (2 days after event)
        cleanup_time = event_time + timedelta(days=2)
        cleanup_diff = cleanup_time - now

        # 4. Repost time (3 days before next event, which is 7 days after current event)
        next_event_time = event_time + timedelta(days=7)
        repost_time = next_event_time - timedelta(days=3)
        repost_diff = repost_time - now

        # Convert to accelerated time
        reminder_seconds = reminder_diff.total_seconds() / ACCELERATION_FACTOR
        event_seconds = event_diff.total_seconds() / ACCELERATION_FACTOR
        cleanup_seconds = cleanup_diff.total_seconds() / ACCELERATION_FACTOR
        repost_seconds = repost_diff.total_seconds() / ACCELERATION_FACTOR

        # Log the schedule
        await ctx.send(f"Accelerated test schedule:")
        await ctx.send(f"- Reminder: in {reminder_seconds:.1f} seconds (real: {reminder_diff})")
        await ctx.send(f"- Event: in {event_seconds:.1f} seconds (real: {event_diff})")
        await ctx.send(f"- Cleanup: in {cleanup_seconds:.1f} seconds (real: {cleanup_diff})")
        await ctx.send(f"- Repost: in {repost_seconds:.1f} seconds (real: {repost_diff})")

        # Schedule the reminder
        self.bot.loop.create_task(self.accelerated_reminder(ctx, reminder_seconds))

        # Schedule the event time notification
        self.bot.loop.create_task(self.accelerated_event_time(ctx, event_seconds))

        # Schedule the cleanup
        self.bot.loop.create_task(self.accelerated_cleanup(ctx, cleanup_seconds))

        # Schedule the repost
        self.bot.loop.create_task(self.accelerated_repost(ctx, repost_seconds))

    async def accelerated_reminder(self, ctx, seconds):
        """Simulate the reminder in accelerated time"""
        await asyncio.sleep(seconds)
        await ctx.send("ACCELERATED TEST: Reminder time reached (30 minutes before event)")

        # Manually trigger the reminder
        event = self.attendance_cog.events.get(self.test_event_id)
        if event:
            # Create a thread for discussion if it doesn't exist
            if not event.get("thread_id"):
                try:
                    channel = self.bot.get_channel(int(event["channel_id"]))
                    message = await channel.fetch_message(int(event["message_id"]))
                    thread = await message.create_thread(
                        name=f"Discussion: {event['title']}",
                        auto_archive_duration=1440  # 24 hours
                    )
                    event["thread_id"] = thread.id
                    await self.attendance_cog.save_events(event["guild_id"])

                    # Send reminder in thread
                    await thread.send("ACCELERATED TEST: This is the 30-minute reminder!")
                except Exception as e:
                    await ctx.send(f"Error creating thread: {e}")
            else:
                try:
                    channel = self.bot.get_channel(int(event["channel_id"]))
                    thread = channel.get_thread(event["thread_id"])
                    if thread:
                        await thread.send("ACCELERATED TEST: This is the 30-minute reminder!")
                except Exception as e:
                    await ctx.send(f"Error sending to thread: {e}")

    async def accelerated_event_time(self, ctx, seconds):
        """Simulate reaching the event time"""
        await asyncio.sleep(seconds)
        await ctx.send("ACCELERATED TEST: Event time reached!")

    async def accelerated_cleanup(self, ctx, seconds):
        """Simulate the cleanup in accelerated time"""
        await asyncio.sleep(seconds)
        await ctx.send("ACCELERATED TEST: Cleanup time reached (2 days after event)")

        # Manually trigger cleanup
        event = self.attendance_cog.events.get(self.test_event_id)
        if event:
            await ctx.send("Manually triggering cleanup_event...")
            await self.attendance_cog.cleanup_event(self.test_event_id, timedelta(seconds=1))

            # Check if event was cleaned up
            if self.test_event_id not in self.attendance_cog.events:
                await ctx.send("✅ Event was successfully cleaned up!")
            else:
                await ctx.send("❌ Event was NOT cleaned up properly!")
        else:
            await ctx.send("Event not found - it may have already been cleaned up")

    async def accelerated_repost(self, ctx, seconds):
        """Simulate the repost in accelerated time"""
        await asyncio.sleep(seconds)
        await ctx.send("ACCELERATED TEST: Repost time reached (3 days before next event)")

        # Check if a new event was created
        found_new_event = False
        original_title = "Test Recurring Event"

        for event_id, event in self.attendance_cog.events.items():
            if (event.get("title") == original_title and
                    event_id != self.test_event_id and
                    event.get("message_id")):
                found_new_event = True
                await ctx.send(f"✅ New recurring event was created with ID: {event_id}")
                break

        if not found_new_event:
            await ctx.send("❌ New recurring event was NOT created properly!")

            # Try to manually trigger the next occurrence
            await ctx.send("Attempting to manually trigger schedule_next_occurrence...")
            if self.test_event_id in self.attendance_cog.events:
                await self.attendance_cog.schedule_next_occurrence(self.test_event_id)
            else:
                # Create a new test event and try again
                await ctx.send("Original event not found, creating a new test event...")
                await self.create_test_event(ctx)


# AttendanceView class for the buttons
class AttendanceView(discord.ui.View):
    def __init__(self, cog, event_id):
        super().__init__(timeout=None)
        self.cog = cog
        self.event_id = event_id

        # Add buttons for each role
        event = cog.events.get(event_id)
        if event:
            for role_id, role_data in event.get("roles", {}).items():
                # Skip roles without names
                if not role_data.get("name"):
                    continue

                # Determine button style
                style = discord.ButtonStyle.primary
                if role_data.get("style") == "green":
                    style = discord.ButtonStyle.success
                elif role_data.get("style") == "red":
                    style = discord.ButtonStyle.danger
                elif role_data.get("style") == "gray":
                    style = discord.ButtonStyle.secondary

                # Create the button
                button = RoleButton(
                    cog=cog,
                    event_id=event_id,
                    role_id=role_id,
                    label=role_data.get("name", "Unknown"),
                    style=style
                )
                self.add_item(button)


# RoleButton class for the role buttons
class RoleButton(discord.ui.Button):
    def __init__(self, cog, event_id, role_id, label, style=discord.ButtonStyle.primary, disabled=False,
                 required_role_id=None):
        super().__init__(style=style, label=label, disabled=disabled,
                         custom_id=f"attendance:{event_id}:{role_id}:toggle")
        self.cog = cog
        self.event_id = event_id
        self.role_id = role_id
        self.required_role_id = required_role_id

    async def callback(self, interaction):
        await self.cog.toggle_role(interaction, self.event_id, self.role_id)


async def setup(bot):
    await bot.add_cog(TestRecurringEvents(bot))
