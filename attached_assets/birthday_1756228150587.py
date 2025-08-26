import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta
import pytz
import pickle
import os
import calendar
import asyncio


class Birthday(commands.Cog):
    """Cog for managing user birthdays and sending birthday wishes"""

    def __init__(self, bot):
        self.bot = bot
        self.db_path = 'databases/birthday_db.pkl'
        self.cst_tz = pytz.timezone('America/Chicago')  # CST/CDT timezone
        self.ensure_db_directory()
        self.load_db()
        self.check_birthdays.start()  # Start the background task to check for birthdays

    def cog_unload(self):
        """Clean up when cog is unloaded"""
        self.check_birthdays.cancel()

    def ensure_db_directory(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    def save_db(self):
        with open(self.db_path, 'wb') as db_file:
            pickle.dump(self.birthday_db, db_file)

    def load_db(self):
        if os.path.exists(self.db_path):
            with open(self.db_path, 'rb') as db_file:
                self.birthday_db = pickle.load(db_file)
        else:
            self.birthday_db = {}

    def ordinal_suffix(self, number):
        if 10 <= number % 100 <= 20:
            suffix = 'th'
        else:
            suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(number % 10, 'th')
        return suffix

    def get_days_until_birthday(self, month, day):
        """Calculate days until next birthday using CST time"""
        now = datetime.now(self.cst_tz)  # Use CST instead of UTC
        this_year_birthday = self.cst_tz.localize(datetime(year=now.year, month=month, day=day))
        next_year_birthday = self.cst_tz.localize(datetime(year=now.year + 1, month=month, day=day))

        if now < this_year_birthday:
            return (this_year_birthday - now).days
        else:
            return (next_year_birthday - now).days

    async def staff_check(self, interaction: discord.Interaction) -> bool:
        """Check if the user has the Staff role"""
        staff_role = discord.utils.get(interaction.guild.roles, name="Staff")
        if not staff_role:
            # Use ephemeral=True to make the message only visible to the user
            await interaction.response.send_message("Staff role not found on this server.", ephemeral=True)
            return False
        if staff_role not in interaction.user.roles:
            await interaction.response.send_message("You need the Staff role to use this command.", ephemeral=True)
            return False
        return True

    @app_commands.command(name='setbirthday', description='Set your birthday')
    @app_commands.describe(
        month="Month (1-12)",
        day="Day (1-31)",
        year="Birth year (optional)"
    )
    async def set_birthday(self, interaction: discord.Interaction, month: int, day: int, year: int = None):
        # Important: Don't respond to the interaction in the check
        # Just check the role and return a boolean
        staff_role = discord.utils.get(interaction.guild.roles, name="Staff")
        if not staff_role or staff_role not in interaction.user.roles:
            await interaction.response.send_message("You need the Staff role to use this command.", ephemeral=True)
            return

        user_id = interaction.user.id
        guild_id = interaction.guild.id
        now = datetime.now(self.cst_tz)  # Use CST instead of UTC

        # Validate month
        if month < 1 or month > 12:
            await interaction.response.send_message("Invalid month. Please enter a number between 1 and 12.",
                                                    ephemeral=True)
            return

        # Validate day based on month
        max_days = calendar.monthrange(now.year, month)[1]
        if day < 1 or day > max_days:
            await interaction.response.send_message(
                f"Invalid day. {calendar.month_name[month]} has {max_days} days.",
                ephemeral=True
            )
            return

        # Validate year if provided
        if year and (year < 1900 or year > now.year):
            await interaction.response.send_message(
                f"Invalid year. Please enter a year between 1900 and {now.year}.",
                ephemeral=True
            )
            return

        # Set the birthday
        month_name = calendar.month_name[month]
        if year:
            birth_year = year
            age = now.year - year
            if (now.month < month) or (now.month == month and now.day < day):
                age -= 1  # Not had birthday yet this year
        else:
            birth_year = None
            age = None

        if guild_id not in self.birthday_db:
            self.birthday_db[guild_id] = {'birthdays': {}, 'channel_id': None}

        self.birthday_db[guild_id]['birthdays'][user_id] = {
            'month': month,
            'day': day,
            'year': birth_year
        }
        self.save_db()

        days_until_birthday = self.get_days_until_birthday(month, day)

        embed = discord.Embed(
            title="🎂 Birthday Set! 🎂",
            description=f"{interaction.user.mention}, your birthday has been set.",
            color=discord.Color.brand_green()
        )

        if birth_year:
            embed.add_field(
                name="Birthday",
                value=f"{month_name} {day}, {birth_year}",
                inline=False
            )
            age_str = f'{age}{self.ordinal_suffix(age)}' if age is not None else 'unknown age'
            embed.add_field(name="Current Age", value=age_str, inline=True)
        else:
            embed.add_field(
                name="Birthday",
                value=f"{month_name} {day}",
                inline=False
            )

        if days_until_birthday == 0:
            embed.add_field(name="Birthday Status", value="🎉 Today is your birthday! 🎉", inline=False)
        elif days_until_birthday == 1:
            embed.add_field(name="Birthday Status", value="Tomorrow is your birthday!", inline=False)
        else:
            embed.add_field(name="Days Until Birthday", value=f"{days_until_birthday} days", inline=False)

            # Calculate the exact next birthday date in CST
            current_year = now.year
            next_year = now.year + 1
            # Try this year's birthday
            this_year_bday = self.cst_tz.localize(datetime(year=current_year, month=month, day=day))
            # If this year's birthday has passed, use next year's
            if this_year_bday < now:
                next_birthday_date = self.cst_tz.localize(datetime(year=next_year, month=month, day=day))
            else:
                next_birthday_date = this_year_bday

            formatted_date = next_birthday_date.strftime("%A, %B %d, %Y")
            embed.add_field(name="Next Birthday", value=formatted_date, inline=False)

        channel_id = self.birthday_db[guild_id].get('channel_id')
        if channel_id:
            channel = self.bot.get_channel(channel_id)
            if channel:
                embed.set_footer(text=f"Birthday announcements will be sent in {channel.name}")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='removebirthday', description='Remove your birthday from the database')
    async def remove_birthday(self, interaction: discord.Interaction):
        if not await self.staff_check(interaction):
            return

        user_id = interaction.user.id
        guild_id = interaction.guild.id

        if guild_id in self.birthday_db and user_id in self.birthday_db[guild_id]['birthdays']:
            del self.birthday_db[guild_id]['birthdays'][user_id]
            self.save_db()
            embed = discord.Embed(
                title="Birthday Removed",
                description=f"{interaction.user.mention}, your birthday has been removed from the database.",
                color=discord.Color.brand_red()
            )
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message("You don't have a birthday set in the database.", ephemeral=True)

    @app_commands.command(name='mybirthday', description='View your currently set birthday')
    async def my_birthday(self, interaction: discord.Interaction):
        if not await self.staff_check(interaction):
            return

        user_id = interaction.user.id
        guild_id = interaction.guild.id

        if guild_id not in self.birthday_db or user_id not in self.birthday_db[guild_id]['birthdays']:
            await interaction.response.send_message("You don't have a birthday set in the database.", ephemeral=True)
            return

        info = self.birthday_db[guild_id]['birthdays'][user_id]
        month_name = calendar.month_name[info['month']]
        now = datetime.now(self.cst_tz)  # Use CST instead of UTC

        embed = discord.Embed(
            title="🎂 Your Birthday 🎂",
            description=f"Here's your birthday information, {interaction.user.mention}",
            color=discord.Color.brand_green()
        )

        if info['year']:
            embed.add_field(
                name="Birthday",
                value=f"{month_name} {info['day']}, {info['year']}",
                inline=False
            )
            age = now.year - info['year']
            if (now.month < info['month']) or (now.month == info['month'] and now.day < info['day']):
                age -= 1  # Not had birthday yet this year
            age_str = f'{age}{self.ordinal_suffix(age)}'
            embed.add_field(name="Current Age", value=age_str, inline=True)
        else:
            embed.add_field(
                name="Birthday",
                value=f"{month_name} {info['day']}",
                inline=False
            )

        days_until_birthday = self.get_days_until_birthday(info['month'], info['day'])
        if days_until_birthday == 0:
            embed.add_field(name="Birthday Status", value="🎉 Today is your birthday! 🎉", inline=False)
        elif days_until_birthday == 1:
            embed.add_field(name="Birthday Status", value="Tomorrow is your birthday!", inline=False)
        else:
            embed.add_field(name="Days Until Birthday", value=f"{days_until_birthday} days", inline=False)
            next_birthday_date = (now + timedelta(days=days_until_birthday)).strftime("%A, %B %d, %Y")
            embed.add_field(name="Next Birthday", value=next_birthday_date, inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name='listbirthdays', description='List all stored birthdays')
    @app_commands.default_permissions(administrator=True)
    async def list_birthdays(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id

        if guild_id not in self.birthday_db or not self.birthday_db[guild_id]['birthdays']:
            await interaction.response.send_message("No birthdays are currently stored.", ephemeral=True)
            return

        now = datetime.now(self.cst_tz)  # Use CST instead of UTC

        # Sort birthdays by upcoming date
        upcoming_birthdays = []
        for user_id, info in self.birthday_db[guild_id]['birthdays'].items():
            days_until = self.get_days_until_birthday(info['month'], info['day'])
            upcoming_birthdays.append((user_id, info, days_until))

        # Sort by days until birthday
        upcoming_birthdays.sort(key=lambda x: x[2])

        embed = discord.Embed(
            title="🎂 Upcoming Birthdays 🎂",
            description=f"There are {len(upcoming_birthdays)} birthdays registered in this server.",
            color=discord.Color.brand_green()
        )

        for user_id, info, days_until in upcoming_birthdays[:25]:  # Limit to 25 entries for embed
            user = interaction.guild.get_member(user_id)
            month_name = calendar.month_name[info['month']]

            if user:
                name = user.display_name
            else:
                name = f"Unknown User ({user_id})"

            if info['year']:
                age = now.year - info['year']
                if (now.month < info['month']) or (now.month == info['month'] and now.day < info['day']):
                    age -= 1
                next_age = age + 1
                birthday_text = f"{month_name} {info['day']} (turns {next_age})"
            else:
                birthday_text = f"{month_name} {info['day']}"

            if days_until == 0:
                value = f"🎉 **TODAY!** 🎉 {birthday_text}"
            elif days_until == 1:
                value = f"**Tomorrow!** {birthday_text}"
            else:
                value = f"In {days_until} days - {birthday_text}"

            embed.add_field(name=name, value=value, inline=False)

        channel_id = self.birthday_db[guild_id].get('channel_id')
        if channel_id:
            channel = self.bot.get_channel(channel_id)
            if channel:
                embed.set_footer(text=f"Birthday announcements are sent in #{channel.name}")
        else:
            embed.set_footer(text="No announcement channel set. Use /setbirthdaychannel to set one.")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='setbirthdaychannel', description="Set the channel for birthday messages")
    @app_commands.default_permissions(administrator=True)
    async def set_birthday_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        guild_id = interaction.guild.id

        if guild_id not in self.birthday_db:
            self.birthday_db[guild_id] = {'birthdays': {}, 'channel_id': None}

        self.birthday_db[guild_id]['channel_id'] = channel.id
        self.save_db()

        embed = discord.Embed(
            title="Birthday Channel Set",
            description=f"Birthday messages will now be sent to {channel.mention}.",
            color=discord.Color.brand_green()
        )

        # Count how many birthdays are registered
        if 'birthdays' in self.birthday_db[guild_id]:
            birthday_count = len(self.birthday_db[guild_id]['birthdays'])
            embed.set_footer(text=f"There are currently {birthday_count} birthdays registered in this server.")

        await interaction.response.send_message(embed=embed)

    @tasks.loop(hours=24)
    async def check_birthdays(self):
        now = datetime.now(self.cst_tz)  # Use CST instead of UTC
        print(f"[{now}] Checking for birthdays...")

        for guild_id, data in self.birthday_db.items():
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                continue

            channel_id = data.get('channel_id')
            public_channel = self.bot.get_channel(channel_id) if channel_id else None

            for user_id, info in data.get('birthdays', {}).items():
                if now.month == info['month'] and now.day == info['day']:
                    member = guild.get_member(int(user_id))
                    if not member:
                        continue

                    # Create birthday message
                    if info['year']:
                        age = now.year - info['year']
                        age_text = f" {age}{self.ordinal_suffix(age)}"
                    else:
                        age_text = ""

                    birthday_embed = discord.Embed(
                        title=f"🎉 Happy{age_text} Birthday, {member.display_name}! 🎉",
                        description=f"Everyone wish {member.mention} a happy birthday today!",
                        color=discord.Color.brand_green()
                    )

                    # Add a random birthday message
                    birthday_messages = [
                        "May your day be filled with joy and laughter!",
                        "Wishing you a fantastic birthday and a wonderful year ahead!",
                        "Hope your special day brings you all that your heart desires!",
                        "Another year older, another year wiser!",
                        "May your birthday be as amazing as you are!",
                        "Here's to celebrating you today!"
                    ]
                    import random
                    birthday_embed.add_field(
                        name="Birthday Wishes",
                        value=random.choice(birthday_messages),
                        inline=False
                    )

                    # Set a footer with the date in CST
                    birthday_embed.set_footer(
                        text=f"Birthday on {calendar.month_name[info['month']]} {info['day']} (CST)")

                    # Try to send DM to the user
                    try:
                        await member.send(embed=birthday_embed)
                    except Exception as e:
                        print(f"Failed to send birthday DM to {member.display_name}: {e}")

                    # Send to public channel if configured
                    if public_channel:
                        try:
                            await public_channel.send(embed=birthday_embed)
                        except Exception as e:
                            print(f"Failed to send birthday message to channel {channel_id}: {e}")

    @check_birthdays.before_loop
    async def before_check_birthdays(self):
        """Wait until the bot is ready before starting the birthday check loop"""
        await self.bot.wait_until_ready()
        # Calculate time until next check (next day at midnight CST)
        now = datetime.now(self.cst_tz)
        tomorrow = self.cst_tz.localize(datetime(now.year, now.month, now.day)) + timedelta(days=1)
        time_until_midnight = (tomorrow - now).total_seconds()
        print(f"Birthday checker will start in {time_until_midnight:.2f} seconds (waiting for CST midnight)")
        await asyncio.sleep(time_until_midnight)  # Wait until midnight CST

    @app_commands.command(name='checkbirthdays', description='Manually check for birthdays (admin only)')
    @app_commands.default_permissions(administrator=True)
    async def check_birthdays_command(self, interaction: discord.Interaction):
        """Manually trigger the birthday check"""
        await interaction.response.defer(ephemeral=True)

        # Store the current time in CST
        now = datetime.now(self.cst_tz)

        # Run the birthday check
        self.check_birthdays.restart()

        await interaction.followup.send(f"Birthday check manually triggered at {now.strftime('%H:%M:%S CST')}.")


async def setup(bot):
    await bot.add_cog(Birthday(bot))

