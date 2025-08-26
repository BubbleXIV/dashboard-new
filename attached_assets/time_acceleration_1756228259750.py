import discord
from discord.ext import commands
import asyncio
import time
from datetime import datetime, timedelta
import pytz
import traceback


class TimeProvider:
    """A class that provides the current time, with optional acceleration"""

    def __init__(self):
        self.acceleration_enabled = False
        self.acceleration_start_real = None
        self.acceleration_start_simulated = None
        self.acceleration_factor = 1.0

    def enable_acceleration(self, factor=1.0):
        """Enable time acceleration with the given factor"""
        self.acceleration_enabled = True
        self.acceleration_start_real = time.time()
        self.acceleration_start_simulated = datetime.now(pytz.UTC)
        self.acceleration_factor = factor

    def disable_acceleration(self):
        """Disable time acceleration"""
        self.acceleration_enabled = False
        self.acceleration_start_real = None
        self.acceleration_start_simulated = None
        self.acceleration_factor = 1.0

    def now(self, tz=None):
        """Get the current time, accelerated if enabled"""
        if not self.acceleration_enabled:
            return datetime.now(tz)

        # Calculate how much real time has passed
        elapsed_real_seconds = time.time() - self.acceleration_start_real

        # Calculate how much simulated time has passed
        elapsed_simulated_seconds = elapsed_real_seconds * self.acceleration_factor

        # Add the simulated time to the start time
        simulated_now = self.acceleration_start_simulated + timedelta(seconds=elapsed_simulated_seconds)

        # Convert to the requested timezone if needed
        if tz is not None and simulated_now.tzinfo != tz:
            simulated_now = simulated_now.astimezone(tz)

        return simulated_now

    def simulate_days(self, days):
        """Simulate the passage of a specific number of days"""
        if not self.acceleration_enabled:
            return False

        # Calculate how many seconds to add to the simulated start time
        seconds_to_add = days * 24 * 60 * 60

        # Update the simulated start time
        self.acceleration_start_simulated += timedelta(seconds=seconds_to_add)

        return True


class TimeAcceleration(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.time_provider = TimeProvider()
        self.time_report_task = None

    def cog_unload(self):
        """Called when the cog is unloaded"""
        # Disable time acceleration
        self.time_provider.disable_acceleration()

        # Cancel the time reporting task if it's running
        if self.time_report_task and not self.time_report_task.done():
            self.time_report_task.cancel()

    @commands.command(name="accelerate_time")
    @commands.has_permissions(administrator=True)
    async def accelerate_time(self, ctx, enable: bool = True, minutes_per_day: int = 2):
        """
        Enable or disable time acceleration for testing.
        When enabled, each specified number of minutes (default 2) will simulate 1 day passing.
        """
        if enable:
            if not self.time_provider.acceleration_enabled:
                # Calculate the acceleration factor
                factor = 24 * 60 * 60 / (minutes_per_day * 60)  # Convert minutes to seconds

                # Enable time acceleration
                self.time_provider.enable_acceleration(factor)

                await ctx.send(f"Time acceleration enabled! {minutes_per_day} minutes now equals 1 day.")
                await ctx.send("⚠️ NOTE: This only affects time-based functionality that uses the time provider.")
                await ctx.send("Use `!accelerate_time False` to disable time acceleration.")

                # Start a task to periodically report the simulated time
                if not self.time_report_task or self.time_report_task.done():
                    self.time_report_task = asyncio.create_task(self._report_accelerated_time(ctx.channel))
            else:
                await ctx.send("Time acceleration is already enabled. Disable it first before changing settings.")
        else:
            if self.time_provider.acceleration_enabled:
                self.time_provider.disable_acceleration()

                # Cancel the time reporting task
                if self.time_report_task and not self.time_report_task.done():
                    self.time_report_task.cancel()

                await ctx.send("Time acceleration disabled.")
            else:
                await ctx.send("Time acceleration was not enabled.")

    async def _report_accelerated_time(self, channel):
        """Periodically report the accelerated time"""
        try:
            while True:
                now = self.time_provider.now(pytz.UTC)
                # Convert to Unix timestamp for Discord's timestamp formatting
                unix_timestamp = int(now.timestamp())

                # Discord timestamp format: <t:timestamp:format>
                # F = Full date and time (e.g., "Wednesday, December 31, 2020 7:00 PM")
                # f = Short date and time (e.g., "December 31, 2020 7:00 PM")
                # D = Full date (e.g., "December 31, 2020")
                # R = Relative time (e.g., "2 hours ago")

                await channel.send(f"⏰ Simulated time: <t:{unix_timestamp}:F> (<t:{unix_timestamp}:R>)")
                await asyncio.sleep(60)  # Report every minute
        except asyncio.CancelledError:
            # Task was cancelled, that's fine
            pass
        except Exception as e:
            print(f"Error in _report_accelerated_time: {e}")
            traceback.print_exc()

    @commands.command(name="check_time")
    async def check_time(self, ctx):
        """Check the current time (real or accelerated)"""
        now = self.time_provider.now(pytz.UTC)
        real_now = datetime.now(pytz.UTC)

        # Convert to Unix timestamps
        sim_timestamp = int(now.timestamp())
        real_timestamp = int(real_now.timestamp())

        if self.time_provider.acceleration_enabled:
            # Calculate days passed
            elapsed_real_seconds = time.time() - self.time_provider.acceleration_start_real
            elapsed_simulated_seconds = elapsed_real_seconds * self.time_provider.acceleration_factor
            days_passed = elapsed_simulated_seconds / (24 * 60 * 60)

            await ctx.send(f"⏰ Simulated time: <t:{sim_timestamp}:F>")
            await ctx.send(f"🕒 Real time: <t:{real_timestamp}:F>")
            await ctx.send(f"⏳ Simulated days passed: {days_passed:.2f} days")
        else:
            await ctx.send(f"🕒 Current time: <t:{real_timestamp}:F>")
            await ctx.send("Time acceleration is not enabled.")

    @commands.command(name="simulate_days")
    @commands.has_permissions(administrator=True)
    async def simulate_days(self, ctx, days: float = 1.0):
        """Simulate the passage of a specific number of days"""
        if not self.time_provider.acceleration_enabled:
            await ctx.send("Time acceleration is not enabled. Please enable it first with `!accelerate_time`.")
            return

        # Simulate days passing
        self.time_provider.simulate_days(days)

        now = self.time_provider.now(pytz.UTC)
        unix_timestamp = int(now.timestamp())

        await ctx.send(f"Simulated {days:.2f} days passing. New time: <t:{unix_timestamp}:F>")

        # Force a check of all events
        await ctx.send("Forcing a check of all events...")
        await self.force_check_events_impl(ctx)

    @commands.command(name="test_event_lifecycle")
    @commands.has_permissions(administrator=True)
    async def test_event_lifecycle(self, ctx, event_id=None):
        """Test the complete lifecycle of an event with accelerated time"""
        if not self.time_provider.acceleration_enabled:
            await ctx.send("Time acceleration is not enabled. Please enable it first with `!accelerate_time`.")
            return

        # Get the attendance cog
        attendance_cog = self.bot.get_cog("Attendance")
        if not attendance_cog:
            await ctx.send("Attendance cog not found.")
            return

        if not event_id:
            # List all events if no event_id is provided
            events_list = []
            for eid, event in attendance_cog.events.items():
                time_str = event.get("time", "Unknown")
                name = event.get("name", "Unnamed event")
                recurring = "🔄 Recurring" if event.get("recurring") else "⏱️ One-time"
                events_list.append(f"**{eid}**: {name} at {time_str} ({recurring})")

            if not events_list:
                await ctx.send("No events found.")
                return

            await ctx.send("Available events:\n" + "\n".join(events_list))
            return

        # Get the event
        event = attendance_cog.events.get(event_id)
        if not event:
            await ctx.send(f"Event {event_id} not found.")
            return

        # Get the event time
        event_time_str = event.get("time")
        if not event_time_str:
            await ctx.send(f"Event {event_id} has no time.")
            return

        # Parse the event time
        try:
            event_time = datetime.strptime(event_time_str, "%Y-%m-%d %H:%M")
            event_time = event_time.replace(tzinfo=pytz.UTC)
        except ValueError:
            await ctx.send(f"Could not parse time for event {event_id}.")
            return

        # Get current time
        now = self.time_provider.now(pytz.UTC)
        now_timestamp = int(now.timestamp())

        # Calculate time difference
        time_diff = event_time - now
        days_diff = time_diff.total_seconds() / (24 * 60 * 60)

        await ctx.send(f"Testing event lifecycle for event {event_id}...")

        # Convert event_time to timestamp if possible
        try:
            event_timestamp = int(event_time.timestamp())
            await ctx.send(f"Event time: <t:{event_timestamp}:F>")
        except:
            await ctx.send(f"Event time: {event_time_str}")

        await ctx.send(f"Current simulated time: <t:{now_timestamp}:F>")
        await ctx.send(f"Time until event: {days_diff:.2f} days")

        if days_diff > 0:
            await ctx.send(f"Event is in the future. Waiting for it to occur...")
        else:
            await ctx.send(f"Event is in the past. Checking if it needs cleanup...")

            if days_diff < -2:
                await ctx.send(
                    "Event is more than 2 days in the past. It should be cleaned up or have a new occurrence scheduled.")

                # Trigger cleanup/next occurrence manually
                if event.get("recurring"):
                    await ctx.send("This is a recurring event. Scheduling next occurrence...")
                    if hasattr(attendance_cog, 'schedule_next_occurrence'):
                        success = await attendance_cog.schedule_next_occurrence(event_id)
                        if success:
                            await ctx.send("Successfully scheduled next occurrence!")
                        else:
                            await ctx.send("Failed to schedule next occurrence.")
                    else:
                        await ctx.send("schedule_next_occurrence method not found in Attendance cog.")
                else:
                    await ctx.send("This is a one-time event. It should be cleaned up.")
                    if hasattr(attendance_cog, 'cleanup_event'):
                        success = await attendance_cog.cleanup_event(event_id)
                        if success:
                            await ctx.send("Successfully cleaned up event!")
                        else:
                            await ctx.send("Failed to clean up event.")
                    else:
                        await ctx.send("cleanup_event method not found in Attendance cog.")
            else:
                await ctx.send(f"Event occurred recently (within 2 days). It should still be visible.")

        # Force a check of all events
        await ctx.send("Forcing a check of all events...")
        await self.force_check_events_impl(ctx)

    @commands.command(name="force_check_events")
    @commands.has_permissions(administrator=True)
    async def force_check_events(self, ctx):
        """Force a check of all events"""
        await self.force_check_events_impl(ctx)

    async def force_check_events_impl(self, ctx):
        """Implementation of force_check_events"""
        attendance_cog = self.bot.get_cog("Attendance")
        if not attendance_cog:
            await ctx.send("Attendance cog not found.")
            return

        await ctx.send("Forcing a check of all events...")
        if hasattr(attendance_cog, 'check_events_impl'):
            await attendance_cog.check_events_impl()
        elif hasattr(attendance_cog, 'check_events'):
            if callable(getattr(attendance_cog.check_events, 'restart', None)):
                attendance_cog.check_events.restart()
            else:
                await ctx.send("check_events.restart method not found.")
        else:
            await ctx.send("No suitable check_events method found in Attendance cog.")
        await ctx.send("Check complete!")


async def setup(bot):
    await bot.add_cog(TimeAcceleration(bot))
