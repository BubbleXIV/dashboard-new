import discord
from discord.ext import commands
from discord import app_commands
import datetime
import json
import os

# Ensure the databases directory exists
if not os.path.exists("databases"):
    os.makedirs("databases")


# Database handler for member events
class DatabaseHandler:
    def __init__(self):
        self.db_file = "databases/member_events.json"
        self.data = self.load_data()

    def load_data(self):
        if os.path.exists(self.db_file):
            with open(self.db_file, "r") as f:
                return json.load(f)
        return {}

    def save_data(self):
        with open(self.db_file, "w") as f:
            json.dump(self.data, f, indent=4)

    def _ensure_guild_exists(self, guild_id):
        guild_id = str(guild_id)  # Convert to string for JSON compatibility
        if guild_id not in self.data:
            self.data[guild_id] = {
                "log_channel": None,
                "special_roles": []
            }

    def set_log_channel(self, guild_id, channel_id):
        guild_id = str(guild_id)
        self._ensure_guild_exists(guild_id)
        self.data[guild_id]["log_channel"] = channel_id
        self.save_data()

    def get_log_channel(self, guild_id):
        guild_id = str(guild_id)
        self._ensure_guild_exists(guild_id)
        return self.data[guild_id]["log_channel"]

    def add_special_role(self, guild_id, role_id):
        guild_id = str(guild_id)
        self._ensure_guild_exists(guild_id)
        if role_id not in self.data[guild_id]["special_roles"]:
            self.data[guild_id]["special_roles"].append(role_id)
            self.save_data()

    def remove_special_role(self, guild_id, role_id):
        guild_id = str(guild_id)
        self._ensure_guild_exists(guild_id)
        if role_id in self.data[guild_id]["special_roles"]:
            self.data[guild_id]["special_roles"].remove(role_id)
            self.save_data()

    def get_special_roles(self, guild_id):
        guild_id = str(guild_id)
        self._ensure_guild_exists(guild_id)
        return self.data[guild_id]["special_roles"]


class MemberEvents(commands.Cog):
    """Track member join, leave, kick, and ban events"""

    def __init__(self, bot):
        self.bot = bot
        self.db = DatabaseHandler()
        self.recent_kicks = {}

    @app_commands.command(name="set_log_channel", description="Set the channel for join/leave/kick/ban logs")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_log_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Set the channel where member events will be logged"""
        self.db.set_log_channel(interaction.guild_id, channel.id)

        embed = discord.Embed(
            title="Log Channel Set",
            description=f"Member events will now be logged in {channel.mention}",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="add_special_roles",
        description="Add roles that trigger extra info on leave/kick/ban"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def add_special_roles(self, interaction: discord.Interaction, roles: str):
        """Add roles that will be highlighted when a member with them leaves"""
        added_roles = []
        for role_mention in roles.split():
            try:
                role_id = int(role_mention.strip('<@&>'))
                role = interaction.guild.get_role(role_id)
                if role:
                    self.db.add_special_role(interaction.guild_id, role.id)
                    added_roles.append(role.name)
            except ValueError:
                pass

        if added_roles:
            embed = discord.Embed(
                title="Special Roles Added",
                description=f"Added the following roles to special roles:\n• {', '.join(added_roles)}",
                color=discord.Color.green()
            )
        else:
            embed = discord.Embed(
                title="No Roles Added",
                description="No valid roles were provided. Please mention roles with @Role or use role IDs.",
                color=discord.Color.red()
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="remove_special_roles",
        description="Remove roles from triggering extra info on leave/kick/ban"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_special_roles(self, interaction: discord.Interaction, roles: str):
        """Remove roles from the special roles list"""
        removed_roles = []
        for role_mention in roles.split():
            try:
                role_id = int(role_mention.strip('<@&>'))
                role = interaction.guild.get_role(role_id)
                if role:
                    self.db.remove_special_role(interaction.guild_id, role.id)
                    removed_roles.append(role.name)
            except ValueError:
                pass

        if removed_roles:
            embed = discord.Embed(
                title="Special Roles Removed",
                description=f"Removed the following roles from special roles:\n• {', '.join(removed_roles)}",
                color=discord.Color.green()
            )
        else:
            embed = discord.Embed(
                title="No Roles Removed",
                description="No valid roles were provided. Please mention roles with @Role or use role IDs.",
                color=discord.Color.red()
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="list_special_roles",
        description="List all roles that trigger extra info on leave/kick/ban"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def list_special_roles(self, interaction: discord.Interaction):
        """List all special roles currently configured"""
        special_role_ids = self.db.get_special_roles(interaction.guild_id)

        if not special_role_ids:
            embed = discord.Embed(
                title="Special Roles",
                description="No special roles have been configured.",
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        special_roles = []
        for role_id in special_role_ids:
            role = interaction.guild.get_role(role_id)
            if role:
                special_roles.append(f"• {role.mention} ({role.name})")

        embed = discord.Embed(
            title="Special Roles",
            description="The following roles are configured as special roles:\n" + "\n".join(special_roles),
            color=discord.Color.blue()
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Log when a member joins the server"""
        log_channel_id = self.db.get_log_channel(member.guild.id)
        if not log_channel_id:
            return

        channel = self.bot.get_channel(log_channel_id)
        if not channel:
            return

        # Get join timestamp
        join_time = int(member.joined_at.replace(tzinfo=datetime.timezone.utc).timestamp())

        # Get account creation timestamp
        created_time = int(member.created_at.replace(tzinfo=datetime.timezone.utc).timestamp())

        # Calculate account age
        account_age = (member.joined_at - member.created_at).days

        embed = discord.Embed(
            title="Member Joined",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now()
        )
        embed.add_field(name="Member", value=f"{member.mention} ({member})", inline=False)
        embed.add_field(name="Joined At", value=f"<t:{join_time}:F>", inline=True)
        embed.add_field(name="Account Created", value=f"<t:{created_time}:F>", inline=True)
        embed.add_field(name="Account Age", value=f"{account_age} days", inline=True)

        # Add warning for new accounts (less than 7 days old)
        if account_age < 7:
            embed.add_field(
                name="⚠️ New Account Warning",
                value=f"This account was created only {account_age} days ago",
                inline=False
            )

        embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
        embed.set_footer(text=f"Member ID: {member.id}")

        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        """Log when a member leaves the server"""
        guild_id = member.guild.id
        member_id = member.id

        # Check if this was a kick
        if guild_id in self.recent_kicks and member_id in self.recent_kicks[guild_id]:
            await self.log_member_leave(member, "Kicked")
            del self.recent_kicks[guild_id][member_id]
        else:
            await self.log_member_leave(member, "Left")

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        """Log when a member is banned from the server"""
        member = guild.get_member(user.id)
        if member:
            await self.log_member_leave(member, "Banned")
        else:
            # Handle case where the user was banned without being a member
            log_channel_id = self.db.get_log_channel(guild.id)
            if not log_channel_id:
                return

            channel = self.bot.get_channel(log_channel_id)
            if not channel:
                return

            ban_time = int(datetime.datetime.now(datetime.timezone.utc).timestamp())

            embed = discord.Embed(
                title="User Banned",
                color=discord.Color.dark_red(),
                timestamp=datetime.datetime.now()
            )
            embed.add_field(name="User", value=f"{user.mention} ({user})", inline=False)
            embed.add_field(name="Banned At", value=f"<t:{ban_time}:F>", inline=False)

            embed.set_thumbnail(url=user.avatar.url if user.avatar else user.default_avatar.url)
            embed.set_footer(text=f"User ID: {user.id}")

            await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_audit_log_entry_create(self, entry):
        """Track kick events through audit logs"""
        if entry.action == discord.AuditLogAction.kick:
            guild_id = entry.guild.id
            member_id = entry.target.id

            if guild_id not in self.recent_kicks:
                self.recent_kicks[guild_id] = {}

            self.recent_kicks[guild_id][member_id] = entry.created_at

            # Clean up old entries
            current_time = datetime.datetime.now(datetime.timezone.utc)
            self.recent_kicks[guild_id] = {
                k: v for k, v in self.recent_kicks[guild_id].items()
                if (current_time - v).total_seconds() < 5
            }

    async def log_member_leave(self, member: discord.Member, action: str):
        """Log member leave events (left, kicked, banned)"""
        log_channel_id = self.db.get_log_channel(member.guild.id)
        if not log_channel_id:
            return

        channel = self.bot.get_channel(log_channel_id)
        if not channel:
            return

        # Set color based on action
        color_map = {
            "Left": discord.Color.orange(),
            "Kicked": discord.Color.red(),
            "Banned": discord.Color.dark_red()
        }
        color = color_map.get(action, discord.Color.red())

        # Get timestamps
        leave_time = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
        join_time = int(member.joined_at.replace(tzinfo=datetime.timezone.utc).timestamp())

        # Calculate time in server
        time_in_server = (datetime.datetime.now(datetime.timezone.utc) - member.joined_at).days

        embed = discord.Embed(
            title=f"Member {action}",
            color=color,
            timestamp=datetime.datetime.now()
        )
        embed.add_field(name="Member", value=f"{member.mention} ({member})", inline=False)

        if member.nick:
            embed.add_field(name="Nickname", value=member.nick, inline=True)

        embed.add_field(name=f"{action} At", value=f"<t:{leave_time}:F>", inline=False)
        embed.add_field(name="Joined At", value=f"<t:{join_time}:F>", inline=True)
        embed.add_field(name="Time in Server", value=f"{time_in_server} days", inline=True)

        # Add special roles if any
        special_role_ids = self.db.get_special_roles(member.guild.id)
        member_special_roles = [role.name for role in member.roles if role.id in special_role_ids]

        if member_special_roles:
            embed.add_field(
                name="⚠️ Special Roles",
                value=", ".join(member_special_roles),
                inline=False
            )

        # Add all roles
        all_roles = [role.name for role in member.roles if role.name != "@everyone"]
        if all_roles:
            embed.add_field(
                name="All Roles",
                value=", ".join(all_roles),
                inline=False
            )

        embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
        embed.set_footer(text=f"Member ID: {member.id}")

        await channel.send(embed=embed)


async def setup(bot):
    await bot.add_cog(MemberEvents(bot))
