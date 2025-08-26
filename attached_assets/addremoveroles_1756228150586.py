import discord
from discord.ext import commands
from discord import app_commands
import re


class RoleManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Register error handler for app commands
        self._app_command_error_handler = self.on_app_command_error

    async def cog_load(self) -> None:
        # This will run when the cog is loaded
        # We don't need to override the global error handler here
        pass

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        else:
            await interaction.response.send_message(f"An error occurred: {str(error)}", ephemeral=True)

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

    def get_role_objects(self, guild, role_input):
        # Split by spaces and commas, and clean up the result
        role_mentions = []
        for item in re.split(r'[,\s]+', role_input):
            if item:  # Skip empty strings
                role_mentions.append(item)
        roles = []
        for mention in role_mentions:
            # Try to extract role ID from mention format
            if mention.startswith('<@&') and mention.endswith('>'):
                try:
                    role_id = int(mention.strip('<@&>'))
                    role = guild.get_role(role_id)
                    if role:
                        roles.append(role)
                except ValueError:
                    continue
            # Try to extract role ID directly
            else:
                try:
                    role_id = int(mention)
                    role = guild.get_role(role_id)
                    if role:
                        roles.append(role)
                except ValueError:
                    # Try to find role by name
                    role = discord.utils.get(guild.roles, name=mention)
                    if role:
                        roles.append(role)
        return roles

    def get_member_objects(self, guild, member_input):
        # Split by spaces and commas, and clean up the result
        member_mentions = []
        for item in re.split(r'[,\s]+', member_input):
            if item:  # Skip empty strings
                member_mentions.append(item)
        members = []
        for mention in member_mentions:
            # Try to extract member ID from mention format
            if mention.startswith('<@') and mention.endswith('>'):
                try:
                    # Handle both <@ID> and <@!ID> formats
                    member_id = int(mention.strip('<@!>').strip('<@>'))
                    member = guild.get_member(member_id)
                    if member:
                        members.append(member)
                except ValueError:
                    continue
            # Try to extract member ID directly
            else:
                try:
                    member_id = int(mention)
                    member = guild.get_member(member_id)
                    if member:
                        members.append(member)
                except ValueError:
                    # Try to find member by name
                    member = discord.utils.get(guild.members, name=mention)
                    if member:
                        members.append(member)
        return members

    @app_commands.command(name='rolemanage', description='Add or remove roles from members')
    @app_commands.describe(
        action='Action to perform (add/remove)',
        roles='Roles to manage (mention, ID, or name, comma or space-separated)',
        members='Members to manage (mention, ID, or name, comma or space-separated)'
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Add roles to members", value="add"),
        app_commands.Choice(name="Remove roles from members", value="remove")
    ])
    @app_commands.default_permissions(manage_roles=True)
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_roles=True)  # Add this line to enforce permissions
    async def rolemanage_slash(self, interaction: discord.Interaction, action: str, roles: str, members: str):
        await interaction.response.defer(ephemeral=True)
        # Check that action is valid
        if action not in ['add', 'remove']:
            await interaction.followup.send('Invalid action. Use "add" or "remove".', ephemeral=True)
            return
        # Get role and member objects
        guild = interaction.guild
        role_objects = self.get_role_objects(guild, roles)
        member_objects = self.get_member_objects(guild, members)
        # Ensure roles and members are found
        if not role_objects:
            await interaction.followup.send('No valid roles found. Please check your input.', ephemeral=True)
            return
        if not member_objects:
            await interaction.followup.send('No valid members found. Please check your input.', ephemeral=True)
            return
        # Check bot permissions
        bot_member = guild.get_member(self.bot.user.id)
        bot_top_role = bot_member.top_role
        # Check if bot has manage_roles permission
        if not bot_member.guild_permissions.manage_roles:
            await interaction.followup.send('I don\'t have permission to manage roles in this server.', ephemeral=True)
            return
        # Prepare for role operations
        success_count = 0
        failure_count = 0
        success_messages = []
        failure_messages = []
        # Add or remove roles for each member
        for member in member_objects:
            for role in role_objects:
                # Check if bot's role is high enough to manage this role
                if role >= bot_top_role:
                    failure_messages.append(
                        f'Cannot manage role {role.mention} as it is higher than or equal to my highest role.')
                    failure_count += 1
                    continue
                # Check if the user has permission to manage this role
                if role >= interaction.user.top_role and interaction.user.id != guild.owner_id:
                    failure_messages.append(
                        f'You cannot manage role {role.mention} as it is higher than or equal to your highest role.')
                    failure_count += 1
                    continue
                if action == 'add':
                    if role not in member.roles:
                        try:
                            await member.add_roles(role, reason=f"Role added by {interaction.user.name}")
                            success_messages.append(f'Added role {role.mention} to {member.mention}.')
                            success_count += 1
                        except discord.Forbidden:
                            failure_messages.append(
                                f'Missing permissions to add role {role.mention} to {member.mention}.')
                            failure_count += 1
                        except Exception as e:
                            failure_messages.append(f'Failed to add role {role.mention} to {member.mention}: {str(e)}')
                            failure_count += 1
                elif action == 'remove':
                    if role in member.roles:
                        try:
                            await member.remove_roles(role, reason=f"Role removed by {interaction.user.name}")
                            success_messages.append(f'Removed role {role.mention} from {member.mention}.')
                            success_count += 1
                        except discord.Forbidden:
                            failure_messages.append(
                                f'Missing permissions to remove role {role.mention} from {member.mention}.')
                            failure_count += 1
                        except Exception as e:
                            failure_messages.append(
                                f'Failed to remove role {role.mention} from {member.mention}: {str(e)}')
                            failure_count += 1
        # Create an embed for the response
        embed = discord.Embed(
            title=f"Role Management Results - {action.capitalize()}",
            color=discord.Color.green() if success_count > 0 and failure_count == 0 else
            discord.Color.red() if success_count == 0 and failure_count > 0 else
            discord.Color.gold()
        )
        # Add summary field
        embed.add_field(
            name="Summary",
            value=f"✅ Successful operations: {success_count}\n❌ Failed operations: {failure_count}",
            inline=False
        )
        # Add success messages if any
        if success_messages:
            # Truncate if too many messages
            if len(success_messages) > 10:
                success_text = "\n".join(success_messages[:10]) + f"\n... and {len(success_messages) - 10} more."
            else:
                success_text = "\n".join(success_messages)
            embed.add_field(
                name="✅ Successful Operations",
                value=success_text,
                inline=False
            )
        # Add failure messages if any
        if failure_messages:
            # Truncate if too many messages
            if len(failure_messages) > 10:
                failure_text = "\n".join(failure_messages[:10]) + f"\n... and {len(failure_messages) - 10} more."
            else:
                failure_text = "\n".join(failure_messages)
            embed.add_field(
                name="❌ Failed Operations",
                value=failure_text,
                inline=False
            )
        # Send the response
        await interaction.followup.send(embed=embed, ephemeral=True)

    @rolemanage_slash.error
    async def rolemanage_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message("You don't have permission to manage roles.", ephemeral=True)
        else:
            await interaction.response.send_message(f"An error occurred: {str(error)}", ephemeral=True)

    # Traditional command version
    @commands.command(name="rolemanage")
    @commands.has_permissions(manage_roles=True)
    @commands.guild_only()
    async def rolemanage_command(self, ctx, action: str, roles: str, *, members: str):
        # Create a mock interaction
        class MockResponse:
            async def defer(self, ephemeral=False):
                pass

            def is_done(self):
                return False

        class MockFollowup:
            async def send(self, content=None, embed=None, ephemeral=False):
                if embed:
                    return await ctx.send(embed=embed)
                return await ctx.send(content)

        class MockInteraction:
            def __init__(self):
                self.response = MockResponse()
                self.followup = MockFollowup()
                self.guild = ctx.guild
                self.user = ctx.author

        # Call the slash command implementation with our mock
        interaction = MockInteraction()
        await self.rolemanage_slash(interaction, action, roles, members)


async def setup(bot):
    # Add the cog to the bot
    await bot.add_cog(RoleManager(bot))