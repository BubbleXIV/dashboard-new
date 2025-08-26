import discord
from discord.ext import commands
from discord.ui import Modal, TextInput, Button, View

# Create a bot instance with default intents
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

class TestModal(Modal):
    def __init__(self):
        super().__init__(title="Answer the Question")
        self.add_item(TextInput(label="Your Answer", placeholder="Type your answer here...", required=True))

    async def on_submit(self, interaction: discord.Interaction):
        print("Modal submitted!")  # Debug statement
        answer = self.children[0].value
        print(f"Received answer: {answer}")  # Debug statement

        try:
            # Respond to the interaction
            await interaction.response.send_message(f"Your answer has been recorded: {answer}", ephemeral=True)
        except Exception as e:
            print(f"Error in modal submission: {e}")
            await interaction.response.send_message("An error occurred. Please try again.", ephemeral=True)

class TestCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def test_modal(self, ctx):
        """Triggers a modal for the user to input an answer."""
        view = View()
        button = Button(label="Open Modal", style=discord.ButtonStyle.green)

        async def button_callback(interaction: discord.Interaction):
            print("Button clicked!")  # Debug statement
            modal = TestModal()
            await interaction.response.send_modal(modal)

        button.callback = button_callback
        view.add_item(button)

        await ctx.send("Click the button below to provide your answer:", view=view)

async def setup(bot):
    await bot.add_cog(TestCog(bot))