import discord
from discord.ext import commands
import asyncio


class Purge(commands.Cog):
    """Commands for bulk message deletion"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=["clear"])
    @commands.has_permissions(administrator=True)
    async def purge(self, ctx, limit: int = None):
        """
        Delete a specified number of messages from the channel.
        Usage: !purge <number>
        """
        # Check for valid input
        if limit is None:
            # Use followup to make the message ephemeral
            await ctx.message.delete()
            await ctx.send("Please specify the number of messages to delete. Usage: `!purge <number>`", ephemeral=True)
            return

        if limit <= 0:
            await ctx.message.delete()
            await ctx.send("Please provide a positive number.", ephemeral=True)
            return

        if limit > 1000:
            await ctx.message.delete()
            await ctx.send("You can only delete up to 1000 messages at once.", ephemeral=True)
            return

        # Delete command message first
        await ctx.message.delete()

        # Delete messages in batches of 100 (Discord API limit)
        deleted_count = 0
        while limit > 0:
            batch_size = min(limit, 100)
            deleted = await ctx.channel.purge(limit=batch_size)
            deleted_count += len(deleted)
            limit -= batch_size

            # If we deleted fewer messages than requested in a batch, we've hit the end
            if len(deleted) < batch_size:
                break

        # Send ephemeral confirmation message
        await ctx.send(f"✅ Deleted {deleted_count} messages.", ephemeral=True)

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def purgeall(self, ctx):
        """
        Delete all messages in the channel (up to Discord's limit).
        Usage: !purgeall
        """

        # Create a confirmation view with buttons
        class ConfirmView(discord.ui.View):
            def __init__(self, cog):
                super().__init__(timeout=30)
                self.cog = cog
                self.confirmed = False

            @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
            async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != ctx.author.id:
                    await interaction.response.send_message("Only the command author can confirm this action.",
                                                            ephemeral=True)
                    return

                self.confirmed = True
                await interaction.response.defer()

                # Delete the command message
                await ctx.message.delete()

                # Purge the channel (Discord only allows purging messages newer than 14 days)
                deleted_count = 0
                batch_size = 100

                # Loop until no more messages can be deleted
                while True:
                    deleted = await ctx.channel.purge(limit=batch_size)
                    deleted_count += len(deleted)

                    # If we deleted fewer messages than the batch size, we've hit the end
                    if len(deleted) < batch_size:
                        break

                # Send ephemeral confirmation message
                await interaction.followup.send(f"✅ Deleted {deleted_count} messages.", ephemeral=True)
                self.stop()

            @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
            async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != ctx.author.id:
                    await interaction.response.send_message("Only the command author can cancel this action.",
                                                            ephemeral=True)
                    return

                await interaction.response.send_message("Purge cancelled.", ephemeral=True)
                await ctx.message.delete()
                self.stop()

        # Create and send the confirmation message with buttons
        view = ConfirmView(self)
        await ctx.send(
            "⚠️ Are you sure you want to delete ALL messages in this channel?",
            view=view,
            ephemeral=True
        )

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def purgeuser(self, ctx, user: discord.Member, limit: int = 100):
        """
        Delete a specified number of messages from a specific user.
        Usage: !purgeuser @user [number=100]
        """
        await ctx.message.delete()

        def check(message):
            return message.author == user

        deleted = await ctx.channel.purge(limit=limit, check=check)

        # Send ephemeral confirmation message
        await ctx.send(f"✅ Deleted {len(deleted)} messages from {user.mention}.", ephemeral=True)

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def purgebots(self, ctx, limit: int = 100):
        """
        Delete a specified number of messages from bots.
        Usage: !purgebots [number=100]
        """
        await ctx.message.delete()

        def check(message):
            return message.author.bot

        deleted = await ctx.channel.purge(limit=limit, check=check)

        # Send ephemeral confirmation message
        await ctx.send(f"✅ Deleted {len(deleted)} bot messages.", ephemeral=True)

    @purge.error
    @purgeall.error
    @purgeuser.error
    @purgebots.error
    async def purge_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You must be an Administrator to use this command.", ephemeral=True)
        elif isinstance(error, commands.BadArgument):
            await ctx.send("Invalid argument. Please provide a valid number or user.", ephemeral=True)
        else:
            await ctx.send(f"An error occurred: {str(error)}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Purge(bot))
