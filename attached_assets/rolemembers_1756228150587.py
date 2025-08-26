import discord
from discord import app_commands
from discord.ext import commands
import math
import asyncio
from typing import List, Optional, Dict, Union
import io
import csv
from collections import Counter


class RoleMembers(commands.Cog):
    """Commands for analyzing role distribution in the server"""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="list_role_members",
        description="List members with specific roles"
    )
    @app_commands.describe(
        role1="First role",
        role2="Second role (optional)",
        role3="Third role (optional)",
        role4="Fourth role (optional)",
        role5="Fifth role (optional)",
        show_usernames="Show full usernames in addition to nicknames",
        export_csv="Export results to a CSV file instead of showing embeds"
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def list_role_members(
            self,
            interaction: discord.Interaction,
            role1: discord.Role,
            role2: Optional[discord.Role] = None,
            role3: Optional[discord.Role] = None,
            role4: Optional[discord.Role] = None,
            role5: Optional[discord.Role] = None,
            show_usernames: Optional[bool] = False,
            export_csv: Optional[bool] = False
    ):
        """
        List members with up to five roles

        Parameters:
        -----------
        role1-role5: Roles to check
        show_usernames: Whether to show full usernames
        export_csv: Export results to a CSV file
        """
        # Defer the response to prevent timeouts
        await interaction.response.defer()

        # Create a list of roles including only those that are not None
        roles = [role for role in [role1, role2, role3, role4, role5] if role is not None]

        # Embed pagination limit
        members_per_page = 20

        try:
            if export_csv:
                # Export to CSV
                csv_data = io.StringIO()
                writer = csv.writer(csv_data)

                # Write header row
                header = ["Member ID", "Display Name", "Username", "Roles"]
                writer.writerow(header)

                # Process each role
                all_members = set()
                role_members = {}

                for role in roles:
                    role_members[role.id] = [member for member in role.members]
                    all_members.update(role_members[role.id])

                # Write data for each member
                for member in all_members:
                    member_roles = [role.name for role in roles if member in role_members[role.id]]
                    writer.writerow([
                        member.id,
                        member.display_name,
                        member.name,
                        ", ".join(member_roles)
                    ])

                # Create file
                csv_data.seek(0)
                file = discord.File(
                    fp=io.BytesIO(csv_data.getvalue().encode()),
                    filename="role_members.csv"
                )

                # Send the file
                await interaction.followup.send(
                    f"Here's the member data for {len(roles)} roles ({len(all_members)} unique members):",
                    file=file
                )

            else:
                # Send embeds
                for role in roles:
                    # Fetch members with the current role
                    members_with_role = [member for member in role.members]
                    total_members = len(members_with_role)

                    if total_members == 0:
                        await interaction.followup.send(f"No members have the {role.name} role.")
                        continue

                    total_pages = math.ceil(total_members / members_per_page)

                    # Create pagination buttons
                    class PaginationView(discord.ui.View):
                        def __init__(self, pages):
                            super().__init__(timeout=300)
                            self.pages = pages
                            self.current_page = 0

                        @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary)
                        async def previous_page(self, button_interaction: discord.Interaction,
                                                button: discord.ui.Button):
                            if button_interaction.user != interaction.user:
                                await button_interaction.response.send_message("You cannot use these controls.",
                                                                               ephemeral=True)
                                return

                            self.current_page = max(0, self.current_page - 1)
                            await button_interaction.response.edit_message(embed=self.pages[self.current_page])

                        @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary)
                        async def next_page(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                            if button_interaction.user != interaction.user:
                                await button_interaction.response.send_message("You cannot use these controls.",
                                                                               ephemeral=True)
                                return

                            self.current_page = min(len(self.pages) - 1, self.current_page + 1)
                            await button_interaction.response.edit_message(embed=self.pages[self.current_page])

                    # Create embeds for each page
                    embeds = []
                    for page in range(total_pages):
                        embed = discord.Embed(
                            title=f"Members with Role: {role.name}",
                            description=f"Total: {total_members} members",
                            color=role.color or discord.Color.blue()
                        )

                        # Get the members for the current page
                        start_idx = page * members_per_page
                        end_idx = min((page + 1) * members_per_page, total_members)
                        members_chunk = members_with_role[start_idx:end_idx]

                        # Format member list
                        member_list = []
                        for i, member in enumerate(members_chunk, start=start_idx + 1):
                            if show_usernames:
                                member_list.append(f"{i}. {member.mention} ({member.display_name} | {member.name})")
                            else:
                                member_list.append(f"{i}. {member.mention} ({member.display_name})")

                        # Add the members to the embed
                        embed.add_field(
                            name=f"Members {start_idx + 1}-{end_idx} of {total_members}",
                            value="\n".join(member_list) or "No members found",
                            inline=False
                        )

                        embed.set_footer(text=f"Page {page + 1}/{total_pages}")
                        embeds.append(embed)

                    # Send the first page with pagination
                    if embeds:
                        view = PaginationView(embeds)
                        await interaction.followup.send(embed=embeds[0], view=view)
                    else:
                        await interaction.followup.send(f"No members found with the {role.name} role.")

        except Exception as e:
            # Handle any errors that occur and send a message
            await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True)

    @app_commands.command(
        name="role_stats",
        description="Get statistics about role distribution in the server"
    )
    @app_commands.describe(
        include_bots="Whether to include bots in the statistics",
        export_csv="Export detailed results to a CSV file"
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def role_stats(
            self,
            interaction: discord.Interaction,
            include_bots: Optional[bool] = False,
            export_csv: Optional[bool] = False
    ):
        """
        Get statistics about role distribution in the server

        Parameters:
        -----------
        include_bots: Whether to include bots in the statistics
        export_csv: Export detailed results to a CSV file
        """
        await interaction.response.defer()

        try:
            # Get all roles in the server
            roles = interaction.guild.roles

            # Filter out the @everyone role and sort by position (highest first)
            roles = [role for role in roles if role.name != "@everyone"]
            roles.sort(key=lambda r: r.position, reverse=True)

            # Count members for each role
            role_counts = {}
            member_role_counts = Counter()

            for role in roles:
                # Filter members based on whether to include bots
                members = [m for m in role.members if include_bots or not m.bot]
                role_counts[role.id] = len(members)

                # Count how many roles each member has
                for member in members:
                    member_role_counts[member.id] += 1

            # Sort roles by member count
            sorted_roles = sorted(roles, key=lambda r: role_counts[r.id], reverse=True)

            # Calculate role distribution statistics
            total_members = len([m for m in interaction.guild.members if include_bots or not m.bot])
            avg_roles_per_member = sum(member_role_counts.values()) / max(1, len(member_role_counts))

            # Create the embed
            embed = discord.Embed(
                title=f"Role Statistics for {interaction.guild.name}",
                description=f"Total Members: {total_members} {'(excluding bots)' if not include_bots else ''}",
                color=discord.Color.blue()
            )

            # Add top 15 roles by member count
            top_roles = sorted_roles[:15]
            top_roles_text = "\n".join([
                f"{i + 1}. {role.mention}: **{role_counts[role.id]}** members ({role_counts[role.id] / max(1, total_members) * 100:.1f}%)"
                for i, role in enumerate(top_roles)
            ])

            embed.add_field(
                name="Top Roles by Member Count",
                value=top_roles_text or "No roles found",
                inline=False
            )

            # Add statistics
            embed.add_field(
                name="Statistics",
                value=(
                    f"**Total Roles:** {len(roles)}\n"
                    f"**Average Roles per Member:** {avg_roles_per_member:.2f}\n"
                    f"**Members with No Roles:** {sum(1 for m in interaction.guild.members if len(m.roles) == 1 and (include_bots or not m.bot))}\n"
                ),
                inline=False
            )

            # Add distribution of role counts
            role_count_distribution = Counter(member_role_counts.values())
            distribution_text = "\n".join([
                f"**{count} roles:** {freq} members"
                for count, freq in sorted(role_count_distribution.items())
            ])

            embed.add_field(
                name="Role Count Distribution",
                value=distribution_text or "No data",
                inline=False
            )

            # Send the embed
            await interaction.followup.send(embed=embed)

            # Export CSV if requested
            if export_csv:
                csv_data = io.StringIO()
                writer = csv.writer(csv_data)

                # Write header row
                writer.writerow(["Role ID", "Role Name", "Position", "Member Count", "Percentage"])

                # Write data for each role
                for role in sorted_roles:
                    writer.writerow([
                        role.id,
                        role.name,
                        role.position,
                        role_counts[role.id],
                        f"{role_counts[role.id] / max(1, total_members) * 100:.2f}%"
                    ])

                # Create file
                csv_data.seek(0)
                file = discord.File(
                    fp=io.BytesIO(csv_data.getvalue().encode()),
                    filename="role_statistics.csv"
                )

                # Send the file
                await interaction.followup.send(
                    "Here's the detailed role statistics data:",
                    file=file
                )

        except Exception as e:
            await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True)

    @app_commands.command(
        name="member_roles",
        description="List all roles for a specific member"
    )
    @app_commands.describe(
        member="The member to check roles for"
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def member_roles(
            self,
            interaction: discord.Interaction,
            member: discord.Member
    ):
        """
        List all roles for a specific member

        Parameters:
        -----------
        member: The member to check roles for
        """
        try:
            # Get all roles for the member (excluding @everyone)
            roles = [role for role in member.roles if role.name != "@everyone"]
            roles.sort(key=lambda r: r.position, reverse=True)

            if not roles:
                await interaction.response.send_message(f"{member.display_name} has no roles.")
                return

            # Create the embed
            embed = discord.Embed(
                title=f"Roles for {member.display_name}",
                description=f"User has {len(roles)} roles",
                color=member.color or discord.Color.blue()
            )

            embed.set_thumbnail(url=member.display_avatar.url)

            # Add roles to the embed
            roles_text = "\n".join([
                f"{i + 1}. {role.mention} (ID: {role.id})"
                for i, role in enumerate(roles)
            ])

            embed.add_field(
                name="Roles (Highest to Lowest)",
                value=roles_text,
                inline=False
            )

            # Add user info
            embed.add_field(
                name="User Info",
                value=(
                    f"**Username:** {member.name}\n"
                    f"**Display Name:** {member.display_name}\n"
                    f"**ID:** {member.id}\n"
                    f"**Joined:** {member.joined_at.strftime('%Y-%m-%d %H:%M:%S') if member.joined_at else 'Unknown'}\n"
                    f"**Account Created:** {member.created_at.strftime('%Y-%m-%d %H:%M:%S')}"
                ),
                inline=False
            )

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(RoleMembers(bot))
