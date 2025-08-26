from discord.ext import commands


class BaseCog(commands.Cog):
    """Base class for all cogs with common functionality"""

    def __init__(self, bot):
        self.bot = bot

    async def cog_command_error(self, ctx, error):
        """Handle errors from commands in this cog"""
        if isinstance(error, commands.CheckFailure):
            # Ignore, as it's already handled
            pass
        else:
            # Log the error for debugging
            print(f"Error in {self.__cog_name__}: {error}")
            # Re-raise to allow global error handlers to process it
            raise error

    async def cog_before_invoke(self, ctx):
        """Check if the cog is enabled before running any command"""
        cog_toggle = self.bot.get_cog('CogToggle')
        if cog_toggle and not cog_toggle.is_cog_enabled(ctx.guild.id, self.__cog_name__):
            raise commands.CheckFailure(f"Cog `{self.__cog_name__}` is disabled.")


def setup_cog(cls):
    """Decorator to wrap a cog class with BaseCog functionality"""

    class WrappedCog(cls, BaseCog):
        def __init__(self, bot):
            BaseCog.__init__(self, bot)
            cls.__init__(self, bot)

    # Preserve the original class name and docstring
    WrappedCog.__name__ = cls.__name__
    WrappedCog.__doc__ = cls.__doc__

    return WrappedCog


# This setup function is required for all cog files
# but does nothing in this utility module
async def setup(bot):
    pass
