import discord
import random
from discord import app_commands
from discord.ext import commands
from typing import List, Optional, Tuple


class RandomUser(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self) -> None:
        # This will run when the cog is loaded
        self.bot.tree.on_error = self.on_app_command_error

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        """Handle application command errors"""
        try:
            # Handle different types of errors
            if isinstance(error, app_commands.CheckFailure):
                error_message = "You don't have permission to use this command."
            else:
                error_message = f"An error occurred: {str(error)}"

            # Try to respond safely
            if not interaction.response.is_done():
                # Interaction hasn't been responded to yet
                await interaction.response.send_message(error_message, ephemeral=True)
            else:
                # Interaction has already been responded to, use followup
                await interaction.followup.send(error_message, ephemeral=True)

        except discord.errors.NotFound:
            # Interaction has expired, just log the error
            print(f"Could not respond to interaction error - interaction expired: {error}")
        except discord.errors.HTTPException as e:
            if e.code == 40060:  # Interaction already acknowledged
                print(f"Interaction already acknowledged when trying to send error: {error}")
            else:
                print(f"HTTP Exception in error handler: {e}")
        except Exception as e:
            print(f"Error in error handler: {e}")

    @app_commands.command(
        name="random_user",
        description="Pick a random user from a specified role"
    )
    @app_commands.describe(
        role="The role to pick a random user from"
    )
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_messages=True)
    async def random_user(self, interaction: discord.Interaction, role: discord.Role):
        """Pick a random user from the specified role."""
        # Get all members with the specified role
        members_with_role = [member for member in interaction.guild.members if role in member.roles]

        if not members_with_role:
            await interaction.response.send_message(f"No users found with the role {role.mention}.", ephemeral=True)
            return

        # Pick a random member
        random_member = random.choice(members_with_role)

        # Create an embed to display the result
        embed = discord.Embed(
            title="Member Roulette",
            description=f"Random member selection!!",
            color=discord.Color.blue()
        )
        embed.add_field(name="Selected User", value=random_member.mention, inline=False)
        embed.set_thumbnail(url=random_member.display_avatar.url)

        await interaction.response.send_message(embed=embed)

    @random_user.error
    async def random_user_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message("You need the 'Manage Messages' permission to use this command.",
                                                    ephemeral=True)
        else:
            await interaction.response.send_message(f"An error occurred: {str(error)}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(RandomUser(bot))
