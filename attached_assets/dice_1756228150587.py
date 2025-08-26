import random
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, List


class DiceRoller(commands.Cog):
    """A cog for rolling various types of dice"""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="roll", description="Roll a d100 die")
    async def roll(self, interaction: discord.Interaction):
        """Simple command to roll a d100"""
        # Roll a d100
        result = random.randint(1, 100)

        # Create the response
        embed = discord.Embed(
            title="🎲 d100 Roll",
            description=f"**{result}**",
            color=0x3498db
        )

        # Set the footer with some flavor text
        footer_texts = [
            "May the odds be ever in your favor!",
            "Roll for initiative!",
            "Critical hit?",
            "Natural 100!",
            "Snake eyes!",
            "The dice never lie...",
            "Fortune favors the bold!",
            "Let chaos decide!",
            "The dice have spoken.",
            "What will fate decide?"
        ]
        embed.set_footer(text=random.choice(footer_texts))

        # Send the response
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="rolladvanced", description="Roll a die of your choice")
    @app_commands.describe(
        dice_type="Type of die to roll (default: d100)",
        number="Number of dice to roll (default: 1)",
        modifier="Modifier to add to the total (default: 0)"
    )
    @app_commands.choices(dice_type=[
        app_commands.Choice(name="d2", value="d2"),
        app_commands.Choice(name="d4", value="d4"),
        app_commands.Choice(name="d6", value="d6"),
        app_commands.Choice(name="d8", value="d8"),
        app_commands.Choice(name="d10", value="d10"),
        app_commands.Choice(name="d20", value="d20"),
        app_commands.Choice(name="d100", value="d100"),
        app_commands.Choice(name="d1000", value="d1000")
    ])
    async def rolladvanced(
            self,
            interaction: discord.Interaction,
            dice_type: Optional[str] = "d100",
            number: Optional[int] = 1,
            modifier: Optional[int] = 0
    ):
        """Roll dice of the specified type"""
        # Validate inputs
        if number <= 0:
            await interaction.response.send_message("You must roll at least 1 die.", ephemeral=True)
            return

        if number > 100:
            await interaction.response.send_message("You can roll a maximum of 100 dice at once.", ephemeral=True)
            return

        # Get the die size from the dice type
        die_size = int(dice_type.replace('d', ''))

        # Roll the dice
        rolls = [random.randint(1, die_size) for _ in range(number)]
        total = sum(rolls) + modifier

        # Create the response
        embed = discord.Embed(
            title=f"🎲 Dice Roll: {number}{dice_type} + {modifier}",
            color=0x3498db
        )

        # Add the total
        embed.add_field(
            name="Total",
            value=f"**{total}**",
            inline=False
        )

        # Add individual rolls if there are multiple dice
        if number > 1:
            # Format the rolls in a readable way
            if number <= 20:  # Show all rolls if 20 or fewer
                rolls_str = ", ".join(str(r) for r in rolls)
            else:  # Show summary for more than 20 rolls
                rolls_str = f"{len(rolls)} dice rolled"

            embed.add_field(
                name="Individual Rolls",
                value=rolls_str,
                inline=False
            )

            # Add some statistics
            embed.add_field(name="Highest", value=str(max(rolls)), inline=True)
            embed.add_field(name="Lowest", value=str(min(rolls)), inline=True)
            embed.add_field(name="Average", value=f"{sum(rolls) / len(rolls):.2f}", inline=True)

        # Add the modifier information if there is one
        if modifier != 0:
            embed.add_field(
                name="Modifier",
                value=f"{'+' if modifier > 0 else ''}{modifier}",
                inline=True
            )

        # Set the footer with some flavor text
        footer_texts = [
            "May the odds be ever in your favor!",
            "Roll for initiative!",
            "Critical hit?",
            "Natural 20!",
            "Snake eyes!",
            "The dice never lie...",
            "Fortune favors the bold!",
            "Let chaos decide!",
            "The dice have spoken.",
            "What will fate decide?"
        ]
        embed.set_footer(text=random.choice(footer_texts))

        # Send the response
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="rolldice", description="Roll custom dice notation (e.g., 2d6+3)")
    @app_commands.describe(
        dice_notation="Dice notation to roll (e.g., 2d6+3, 1d20-2, 3d8)"
    )
    async def rolldice(self, interaction: discord.Interaction, dice_notation: str):
        """Roll dice using standard dice notation"""
        try:
            # Parse the dice notation
            import re

            # Match patterns like "2d6+3", "1d20-2", "d8", etc.
            pattern = r'^(\d+)?d(\d+)([+-]\d+)?$'
            match = re.match(pattern, dice_notation.lower().replace(" ", ""))

            if not match:
                await interaction.response.send_message(
                    "Invalid dice notation. Use format like '2d6+3', '1d20-2', or 'd8'.",
                    ephemeral=True
                )
                return

            # Extract the components
            num_dice = int(match.group(1)) if match.group(1) else 1
            die_size = int(match.group(2))
            modifier = int(match.group(3)) if match.group(3) else 0

            # Validate inputs
            if num_dice <= 0:
                await interaction.response.send_message("You must roll at least 1 die.", ephemeral=True)
                return

            if num_dice > 100:
                await interaction.response.send_message("You can roll a maximum of 100 dice at once.", ephemeral=True)
                return

            if die_size <= 0:
                await interaction.response.send_message("Die size must be at least 1.", ephemeral=True)
                return

            # Roll the dice
            rolls = [random.randint(1, die_size) for _ in range(num_dice)]
            total = sum(rolls) + modifier

            # Create the response
            embed = discord.Embed(
                title=f"🎲 Dice Roll: {dice_notation}",
                color=0x3498db
            )

            # Add the total
            embed.add_field(
                name="Total",
                value=f"**{total}**",
                inline=False
            )

            # Add individual rolls if there are multiple dice
            if num_dice > 1:
                # Format the rolls in a readable way
                if num_dice <= 20:  # Show all rolls if 20 or fewer
                    rolls_str = ", ".join(str(r) for r in rolls)
                else:  # Show summary for more than 20 rolls
                    rolls_str = f"{len(rolls)} dice rolled"

                embed.add_field(
                    name="Individual Rolls",
                    value=rolls_str,
                    inline=False
                )

                # Add some statistics
                embed.add_field(name="Highest", value=str(max(rolls)), inline=True)
                embed.add_field(name="Lowest", value=str(min(rolls)), inline=True)
                embed.add_field(name="Average", value=f"{sum(rolls) / len(rolls):.2f}", inline=True)

            # Add the modifier information if there is one
            if modifier != 0:
                embed.add_field(
                    name="Modifier",
                    value=f"{'+' if modifier > 0 else ''}{modifier}",
                    inline=True
                )

            # Set the footer with some flavor text
            footer_texts = [
                "May the odds be ever in your favor!",
                "Roll for initiative!",
                "Critical hit?",
                "Natural 20!",
                "Snake eyes!",
                "The dice never lie...",
                "Fortune favors the bold!",
                "Let chaos decide!",
                "The dice have spoken.",
                "What will fate decide?"
            ]
            embed.set_footer(text=random.choice(footer_texts))

            # Send the response
            await interaction.response.send_message(embed=embed)

        except Exception as e:
            await interaction.response.send_message(
                f"Error processing dice roll: {str(e)}",
                ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(DiceRoller(bot))
