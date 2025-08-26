import discord
from discord.ext import commands
from discord import app_commands


class CogTemplate(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Check if this cog is enabled for the current guild
    async def cog_check(self, ctx):
        # Skip check for DMs
        if ctx.guild is None:
            return True

        guild_id = str(ctx.guild.id)
        cog_toggle = self.bot.get_cog("CogToggle")

        if cog_toggle:
            disabled_cogs = cog_toggle.get_disabled_cogs_for_guild(guild_id)
            cog_name = self.__class__.__module__.split('.')[-1]  # Get the cog name from module
            if cog_name in disabled_cogs:
                return False
        return True

    # For slash commands, use this check
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Skip check for DMs
        if interaction.guild_id is None:
            return True

        guild_id = str(interaction.guild_id)
        cog_toggle = self.bot.get_cog("CogToggle")

        if cog_toggle:
            disabled_cogs = cog_toggle.get_disabled_cogs_for_guild(guild_id)
            cog_name = self.__class__.__module__.split('.')[-1]  # Get the cog name from module
            if cog_name in disabled_cogs:
                await interaction.response.send_message("This command is disabled in this server.", ephemeral=True)
                return False
        return True

    # Example prefix command
    @commands.command(name="example")
    @commands.guild_only()
    async def example_command(self, ctx):
        await ctx.send("This is an example command!")

    # Example slash command
    @app_commands.command(name="example_slash", description="An example slash command")
    @app_commands.guild_only()
    async def example_slash(self, interaction: discord.Interaction):
        await interaction.response.send_message("This is an example slash command!")


async def setup(bot):
    await bot.add_cog(CogTemplate(bot))
