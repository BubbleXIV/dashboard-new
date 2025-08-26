import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import Modal, TextInput, Button, View
from datetime import datetime
from discord import TextStyle
import pytz
import json
import os
import shlex
import traceback
import logging
import asyncio
import inspect

# Set up logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("formcall")

# Disable loggers for libraries that are too verbose
logging.getLogger('discord').setLevel(logging.ERROR)
logging.getLogger('discord.http').setLevel(logging.ERROR)
logging.getLogger('discord.gateway').setLevel(logging.ERROR)

# Ensure the databases directory exists
if not os.path.exists("databases"):
    os.makedirs("databases")

FORMS_FILE = "databases/forms.json"


def load_forms():
    """Load forms from the JSON file"""
    if os.path.exists(FORMS_FILE):
        with open(FORMS_FILE, "r") as f:
            forms = json.load(f)
    else:
        forms = {}
    # Initialize 'button_locations' if it doesn't exist
    for guild_id in forms:
        for form_name in forms[guild_id]:
            if 'button_locations' not in forms[guild_id][form_name]:
                forms[guild_id][form_name]['button_locations'] = []
            if 'enable_approval' not in forms[guild_id][form_name]:
                forms[guild_id][form_name]['enable_approval'] = False
    return forms


def save_forms(forms):
    """Save forms to the JSON file"""
    try:
        # Ensure the directory exists
        os.makedirs(os.path.dirname(FORMS_FILE), exist_ok=True)

        # Save to a temporary file first
        temp_file = f"{FORMS_FILE}.temp"
        with open(temp_file, "w") as f:
            json.dump(forms, f, indent=4)

        # Validate the JSON by reading it back
        with open(temp_file, "r") as f:
            json.load(f)  # This will raise an exception if the JSON is invalid

        # Then rename to the actual file (atomic operation)
        import shutil
        shutil.move(temp_file, FORMS_FILE)

        print(f"Forms saved successfully to {FORMS_FILE}")
        return True
    except Exception as e:
        print(f"Error saving forms: {e}")
        import traceback
        traceback.print_exc()
        return False


def find_role_flexible(guild, role_input):
    """
    Find a role with flexible matching:
    1. Exact match (case-insensitive)
    2. Partial match in role name
    3. Check if input matches any word in role name
    """
    role_input = role_input.strip().lower()

    # First try exact match (case-insensitive)
    for role in guild.roles:
        if role.name.lower() == role_input:
            return role

    # Then try partial match - if input is contained in role name
    for role in guild.roles:
        if role_input in role.name.lower():
            return role

    # Finally try word matching - if input matches any word in role name
    for role in guild.roles:
        role_words = role.name.lower().replace('/', ' ').replace('-', ' ').split()
        if role_input in role_words:
            return role

    return None


def has_approval_permission(user, guild_id, form_name):
    """Check if user has permission to approve/deny submissions"""
    # Admin override
    if user.guild_permissions.manage_messages:
        return True

    # Check if user has any of the approval roles
    forms = load_forms()
    form_data = forms.get(guild_id, {}).get(form_name, {})
    approval_roles = form_data.get("approval_roles", [])

    if approval_roles:
        user_role_ids = [role.id for role in user.roles]
        return any(role_id in user_role_ids for role_id in approval_roles)

    return False


class ApprovalView(View):
    def __init__(self, form_name, submission_id):
        super().__init__(timeout=None)  # Set timeout to None for persistence
        self.form_name = form_name
        self.submission_id = submission_id
        # Remove the existing buttons so we can add our custom ones
        # This prevents duplicate buttons when we add our custom ones
        self.clear_items()
        # Add buttons with context-encoded custom_ids
        approve_button = Button(
            label="Approve",
            style=discord.ButtonStyle.green,
            custom_id=f"approve:{form_name}:{submission_id}"
        )
        approve_button.callback = self.approve_callback
        self.add_item(approve_button)
        deny_button = Button(
            label="Deny",
            style=discord.ButtonStyle.red,
            custom_id=f"deny:{form_name}:{submission_id}"
        )
        deny_button.callback = self.deny_callback
        self.add_item(deny_button)

    async def approve_callback(self, button_interaction: discord.Interaction):
        # Extract context from custom_id if needed
        if not hasattr(self, 'form_name') or not hasattr(self, 'submission_id'):
            custom_id_parts = button_interaction.data['custom_id'].split(':')
            if len(custom_id_parts) >= 3:
                self.form_name = custom_id_parts[1]
                self.submission_id = custom_id_parts[2]

        # Check if the user has permission to approve
        if not has_approval_permission(button_interaction.user, str(button_interaction.guild.id), self.form_name):
            # Check if the interaction has already been responded to
            if not button_interaction.response.is_done():
                await button_interaction.response.send_message(
                    "You don't have permission to approve submissions.",
                    ephemeral=True
                )
            else:
                await button_interaction.followup.send(
                    "You don't have permission to approve submissions.",
                    ephemeral=True
                )
            return

        # Create a modal for selecting roles
        class RoleSelectionModal(Modal):
            def __init__(self, form_name, submission_id, parent_view):
                super().__init__(title="Approved Roles")
                self.form_name = form_name
                self.submission_id = submission_id
                self.parent_view = parent_view  # Store reference to parent view
                self.roles = TextInput(
                    label="Roles to assign (comma separated)",
                    placeholder="e.g. Member, Verified, etc.",
                    required=False,
                    style=TextStyle.short
                )
                self.add_item(self.roles)

            async def on_submit(self, modal_interaction: discord.Interaction):
                try:
                    roles_text = self.roles.value.strip()
                    approved_roles = [role.strip() for role in roles_text.split(',')] if roles_text else []

                    # Get the submission message
                    channel = button_interaction.channel
                    parent_channel = channel
                    # If we're in a thread, get the parent channel
                    if isinstance(channel, discord.Thread):
                        parent_channel = channel.parent

                    try:
                        # Try to get the original message
                        submission_message = await parent_channel.fetch_message(int(self.submission_id))
                        # Get the user from the embed
                        embed = submission_message.embeds[0]
                        user_id = int(embed.footer.text.split(": ")[1])
                        user = button_interaction.guild.get_member(user_id)

                        # Add roles to the user with flexible matching
                        added_roles = []
                        failed_roles = []
                        if user and approved_roles:
                            for role_name in approved_roles:
                                role = find_role_flexible(button_interaction.guild, role_name)
                                if role:
                                    try:
                                        await user.add_roles(role, reason=f"Approved in {self.form_name} form")
                                        added_roles.append(role.name)
                                    except discord.Forbidden:
                                        failed_roles.append(f"{role.name} (missing permissions)")
                                    except Exception as e:
                                        failed_roles.append(f"{role.name} ({str(e)})")
                                else:
                                    # Provide suggestions for failed matches
                                    suggestions = []
                                    for guild_role in button_interaction.guild.roles:
                                        if (role_name.lower() in guild_role.name.lower() or
                                                guild_role.name.lower() in role_name.lower()):
                                            suggestions.append(guild_role.name)
                                    if suggestions:
                                        failed_roles.append(
                                            f"{role_name} (not found, did you mean: {', '.join(suggestions[:3])}?)")
                                    else:
                                        failed_roles.append(f"{role_name} (role not found)")

                        # Create a summary embed
                        summary_embed = discord.Embed(
                            title="Application Approved",
                            description=(
                                f"**Submission:** {user.name if user else 'Unknown User'} ({user_id})\n"
                                f"**Status:** Approved by {button_interaction.user.mention}\n"
                                f"**Timestamp:** {discord.utils.format_dt(datetime.now(), 'F')}"
                            ),
                            color=discord.Color.green()
                        )

                        # Add role information to the summary
                        if added_roles:
                            summary_embed.add_field(
                                name="Added Roles",
                                value=", ".join(added_roles),
                                inline=False
                            )
                        if failed_roles:
                            summary_embed.add_field(
                                name="Failed Roles",
                                value="\n".join(failed_roles),
                                inline=False
                            )

                        # Send summary embed only once - as a reply to the original message
                        await submission_message.reply(embed=summary_embed)

                        # Update the original submission
                        embed.color = discord.Color.green()
                        embed.add_field(
                            name="Status",
                            value=f"Approved by {button_interaction.user.mention} on {discord.utils.format_dt(datetime.now(), 'F')}",
                            inline=False
                        )
                        if added_roles:
                            embed.add_field(
                                name="Approved Roles",
                                value=", ".join(added_roles),
                                inline=False
                            )
                        if failed_roles:
                            embed.add_field(
                                name="Failed Roles",
                                value="\n".join(failed_roles),
                                inline=False
                            )
                        await submission_message.edit(embed=embed, view=None)

                        # Notify the user
                        if user:
                            roles_msg = ""
                            if added_roles:
                                roles_msg += f"\nYou have been approved for the following roles: {', '.join(added_roles)}"
                            try:
                                await user.send(
                                    f"Your {self.form_name} submission has been **approved**!{roles_msg}")
                            except:
                                await submission_message.reply("Note: Could not DM the user about the approval.")

                        # Respond to the modal interaction - check if already responded
                        if not modal_interaction.response.is_done():
                            await modal_interaction.response.send_message("Submission approved!", ephemeral=True)
                        else:
                            await modal_interaction.followup.send("Submission approved!", ephemeral=True)

                    except Exception as e:
                        print(f"Error in approval process: {e}")
                        import traceback
                        traceback.print_exc()
                        # Check if already responded before sending error message
                        if not modal_interaction.response.is_done():
                            await modal_interaction.response.send_message(
                                f"An error occurred during approval: {str(e)}", ephemeral=True
                            )
                        else:
                            await modal_interaction.followup.send(
                                f"An error occurred during approval: {str(e)}", ephemeral=True
                            )

                except Exception as e:
                    print(f"Error in role selection modal: {e}")
                    import traceback
                    traceback.print_exc()
                    # Check if already responded before sending error message
                    if not modal_interaction.response.is_done():
                        await modal_interaction.response.send_message(
                            f"An error occurred: {str(e)}", ephemeral=True
                        )
                    else:
                        await modal_interaction.followup.send(
                            f"An error occurred: {str(e)}", ephemeral=True
                        )

        await button_interaction.response.send_modal(
            RoleSelectionModal(self.form_name, self.submission_id, self)
        )

    async def deny_callback(self, button_interaction: discord.Interaction):
        # Extract context from custom_id if needed
        if not hasattr(self, 'form_name') or not hasattr(self, 'submission_id'):
            custom_id_parts = button_interaction.data['custom_id'].split(':')
            if len(custom_id_parts) >= 3:
                self.form_name = custom_id_parts[1]
                self.submission_id = custom_id_parts[2]

        # Check if the user has permission to deny
        if not button_interaction.user.guild_permissions.manage_messages:
            await button_interaction.response.send_message(
                "You don't have permission to deny submissions.",
                ephemeral=True
            )
            return

        class DenialReasonModal(Modal):
            def __init__(self, form_name, submission_id, parent_view):
                super().__init__(title="Denial Reason")
                self.form_name = form_name
                self.submission_id = submission_id
                self.parent_view = parent_view  # Store reference to parent view

                self.reason = TextInput(
                    label="Reason for Denial",
                    style=TextStyle.paragraph,
                    required=True
                )
                self.add_item(self.reason)

            async def on_submit(self, modal_interaction: discord.Interaction):
                try:
                    reason = self.reason.value

                    # Get the submission message
                    channel = button_interaction.channel
                    parent_channel = channel
                    # If we're in a thread, get the parent channel
                    if isinstance(channel, discord.Thread):
                        parent_channel = channel.parent

                    try:
                        # Try to get the original message
                        submission_message = await parent_channel.fetch_message(int(self.submission_id))

                        # Get the user from the embed
                        embed = submission_message.embeds[0]
                        user_id = int(embed.footer.text.split(": ")[1])
                        user = button_interaction.guild.get_member(user_id)

                        # Create a summary embed
                        summary_embed = discord.Embed(
                            title="Application Denied",
                            description=(
                                f"**Submission:** {user.name if user else 'Unknown User'} ({user_id})\n"
                                f"**Status:** Denied by {button_interaction.user.mention}\n"
                                f"**Reason:** {reason}\n"
                                f"**Timestamp:** {discord.utils.format_dt(datetime.now(), 'F')}"
                            ),
                            color=discord.Color.red()
                        )

                        # Send summary embed only once - as a reply to the original message
                        await submission_message.reply(embed=summary_embed)

                        # Update the original submission
                        embed.color = discord.Color.red()
                        embed.add_field(
                            name="Status",
                            value=f"Denied by {button_interaction.user.mention} on {discord.utils.format_dt(datetime.now(), 'F')}",
                            inline=False
                        )
                        embed.add_field(
                            name="Reason",
                            value=reason,
                            inline=False
                        )

                        await submission_message.edit(embed=embed, view=None)

                        # Notify the user
                        if user:
                            try:
                                await user.send(
                                    f"Your {self.form_name} submission has been **denied**.\n**Reason:** {reason}")
                            except:
                                await submission_message.reply("Note: Could not DM the user about the denial.")

                        await modal_interaction.response.send_message("Submission denied!", ephemeral=True)

                    except Exception as e:
                        print(f"Error in denial process: {e}")
                        import traceback
                        traceback.print_exc()
                        await modal_interaction.response.send_message(
                            f"An error occurred during denial: {str(e)}", ephemeral=True
                        )

                except Exception as e:
                    print(f"Error in denial reason modal: {e}")
                    import traceback
                    traceback.print_exc()
                    await modal_interaction.response.send_message(
                        f"An error occurred: {str(e)}", ephemeral=True
                    )

        # Send the modal with the necessary context
        await button_interaction.response.send_modal(
            DenialReasonModal(self.form_name, self.submission_id, self)
        )


class DynamicModal(Modal):
    # Store continue message IDs at the class level
    continue_message_ids = {}

    def __init__(self, title, questions, submission_channel_id, enable_approval, form_name, page=0,
                 previous_answers=None, user_id=None, display_title=None):
        super().__init__(title=f"{title} (Page {page + 1})")
        self.submission_channel_id = submission_channel_id
        self.enable_approval = enable_approval
        self.form_name = form_name
        self.display_title = display_title or title  # Store the display title
        self.all_questions = questions
        self.page = page
        self.previous_answers = previous_answers or []
        self.user_id = user_id or 0  # Will be set in on_submit if not provided

        # Calculate which questions to show on this page
        start = page * 5
        end = min(start + 5, len(questions))
        self.current_questions = questions[start:end]

        # Add text inputs for each question
        for idx, question in enumerate(self.current_questions):
            question_number = start + idx + 1
            self.add_item(self.create_text_input(idx, question_number, question))

    def create_text_input(self, idx, question_number, question):
        """Create a text input for a question"""
        if len(question) <= 45:
            # Short question: use it as the label
            return TextInput(
                label=question,
                placeholder="Your answer here...",
                required=True,
                style=TextStyle.short
            )
        else:
            # Long question: use a short label and put the full question in the placeholder
            truncated_question = self.format_long_question(question)
            return TextInput(
                label=f"Question {question_number}",
                placeholder=truncated_question,
                required=True,
                style=TextStyle.paragraph  # Use paragraph for longer inputs
            )

    def format_long_question(self, question):
        """Format a long question to fit within Discord's limits"""
        words = question.split()
        lines = []
        current_line = []
        for word in words:
            if len(' '.join(current_line + [word])) > 100:  # Discord's character limit for placeholders
                lines.append(' '.join(current_line))
                current_line = [word]
            else:
                current_line.append(word)
        if current_line:
            lines.append(' '.join(current_line))
        return '\n'.join(lines)

    async def on_submit(self, interaction: discord.Interaction):
        """Handle form submission"""
        try:
            logger.info(f"Form submitted for {self.form_name}, page {self.page + 1}")

            # Set user_id if not already set
            if not self.user_id:
                self.user_id = interaction.user.id

            # Delete previous continue messages for this user
            if self.user_id in DynamicModal.continue_message_ids:
                try:
                    channel = interaction.channel
                    for message_id in DynamicModal.continue_message_ids[self.user_id]:
                        try:
                            previous_message = await channel.fetch_message(message_id)
                            await previous_message.delete()
                            logger.info(f"Deleted previous continue message: {message_id}")
                        except discord.NotFound:
                            logger.info(f"Message {message_id} already deleted or not found")
                        except Exception as e:
                            logger.error(f"Failed to delete message {message_id}: {e}")

                    # Clear the list after attempting to delete all messages
                    DynamicModal.continue_message_ids[self.user_id] = []
                except Exception as e:
                    logger.error(f"Error deleting previous messages: {e}")

            # Collect answers from this page
            new_answers = [child.value for child in self.children]
            all_answers = self.previous_answers + new_answers
            logger.info(f"Current answers: {new_answers}")
            logger.info(f"All answers so far: {all_answers}")

            # Check if there are more pages
            if (self.page + 1) * 5 < len(self.all_questions):
                logger.info(f"More questions remaining. Preparing for next page.")

                # Send a new continue message
                continue_view = self.get_continue_view(all_answers)
                await interaction.response.send_message(
                    "Click 'Continue' to proceed to the next page.",
                    ephemeral=True,
                    view=continue_view
                )

                # Store the message ID for later deletion
                # We need to wait for the response to be sent before we can get the message ID
                await asyncio.sleep(0.5)  # Small delay to ensure the message is sent

                # Try to get the message ID from the response
                if hasattr(interaction, 'original_response'):
                    message = await interaction.original_response()

                    # Initialize the list for this user if it doesn't exist
                    if self.user_id not in DynamicModal.continue_message_ids:
                        DynamicModal.continue_message_ids[self.user_id] = []

                    # Add this message ID to the list
                    DynamicModal.continue_message_ids[self.user_id].append(message.id)
                    logger.info(f"Stored continue message ID: {message.id} for user {self.user_id}")
            else:
                logger.info("Processing final submission")
                await self.process_submission(interaction, all_answers)

                # Clear any stored message IDs for this user after final submission
                if self.user_id in DynamicModal.continue_message_ids:
                    DynamicModal.continue_message_ids[self.user_id] = []
        except Exception as e:
            logger.error(f"Error in on_submit: {e}\n{traceback.format_exc()}")
            await interaction.response.send_message(
                "An error occurred while processing your submission. Please try again.",
                ephemeral=True
            )

    def get_continue_view(self, all_answers):
        """Create a view with a continue button for multi-page forms"""

        class ContinueView(discord.ui.View):
            def __init__(self, modal):
                super().__init__()
                self.modal = modal

            @discord.ui.button(label="Continue", style=discord.ButtonStyle.primary)
            async def continue_button(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                # Create the next modal
                next_modal = DynamicModal(
                    self.modal.title.split('(')[0].strip(),
                    self.modal.all_questions,
                    self.modal.submission_channel_id,
                    self.modal.enable_approval,
                    self.modal.form_name,
                    self.modal.page + 1,
                    all_answers,
                    self.modal.user_id,  # Pass the user ID to the next modal
                    self.modal.display_title  # Pass the display title to the next modal
                )

                # Send the next modal
                await button_interaction.response.send_modal(next_modal)

        return ContinueView(self)

    async def process_submission(self, interaction: discord.Interaction, answers):
        """Process the final form submission"""
        try:
            # Format the answers with questions and add extra spacing
            formatted_answers = "\n\n".join([
                f"**Q{idx + 1}: {question}**\n{answer}"
                for idx, (question, answer) in enumerate(zip(self.all_questions, answers))
            ])

            # Use the display title for the submission
            form_title = self.display_title

            # Create the submission embed
            embed = discord.Embed(
                title=f"{interaction.user.name}'s {form_title} Submission",
                description=formatted_answers,
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )

            # Add user information
            embed.set_author(name=interaction.user.name, icon_url=interaction.user.display_avatar.url)
            embed.set_footer(text=f"User ID: {interaction.user.id}")

            # Get the submission channel
            channel = interaction.guild.get_channel(self.submission_channel_id)
            if not channel:
                await interaction.response.send_message("Submission channel not found.", ephemeral=True)
                return

            # Get form data for role pings
            guild_id = str(interaction.guild.id)
            forms = load_forms()
            form_data = forms.get(guild_id, {}).get(self.form_name, {})
            ping_roles = form_data.get("ping_roles", [])

            # Create role ping message
            ping_message = ""
            if ping_roles:
                role_mentions = [f"<@&{role_id}>" for role_id in ping_roles]
                ping_message = f"New form submission! {' '.join(role_mentions)}"

            # Send the submission with role pings if they exist
            if ping_message:
                submission_message = await channel.send(content=ping_message, embed=embed)
            else:
                submission_message = await channel.send(embed=embed)

            # Create a thread for discussion
            thread = await submission_message.create_thread(
                name=f"{interaction.user.name}'s {form_title} submission",
                auto_archive_duration=1440  # 24 hours
            )

            # Add approval buttons if enabled
            if self.enable_approval:
                # Create a persistent approval view with the submission message ID
                approval_view = ApprovalView(self.form_name, str(submission_message.id))
                # Send the approval view in the thread
                await thread.send("Please review this submission:", view=approval_view)
                # Also add the view to the original message
                await submission_message.edit(view=approval_view)

            # Notify the user that their submission was received
            await interaction.response.send_message(
                "Your submission has been recorded. Thank you!",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error in process_submission: {e}\n{traceback.format_exc()}")
            error_message = f"An error occurred while processing your submission. Please try again."
            if not interaction.response.is_done():
                await interaction.response.send_message(error_message, ephemeral=True)
            else:
                await interaction.followup.send(error_message, ephemeral=True)


class PersistentFormView(discord.ui.View):
    def __init__(self, form_name: str, enable_approval: bool, display_title: str = None):
        super().__init__(timeout=None)
        self.form_name = form_name
        self.enable_approval = enable_approval
        self.display_title = display_title or form_name  # Use the provided title or fall back to form_name

        # Clear existing items and add our custom button
        self.clear_items()
        open_button = discord.ui.Button(
            label="Open Form",
            style=discord.ButtonStyle.green,
            custom_id=f"open_form:{form_name}"
        )
        open_button.callback = self.open_form
        self.add_item(open_button)

    @classmethod
    def from_form_data(cls, form_name: str, form_data: dict):
        enable_approval = form_data.get('enable_approval', False)
        display_title = form_data.get('display_title', form_name)
        return cls(form_name, enable_approval, display_title)

    async def open_form(self, interaction: discord.Interaction):
        try:
            logger.info(f"Opening form: {self.form_name}")
            guild_id = str(interaction.guild.id)
            # Load the latest form data
            forms = load_forms()
            if guild_id not in forms or self.form_name not in forms[guild_id]:
                await interaction.response.send_message("Form not found. Please try again later.", ephemeral=True)
                return

            form_data = forms[guild_id][self.form_name]
            if "questions" not in form_data or "submission_channel" not in form_data:
                await interaction.response.send_message("Form data is incomplete. Please try again later.",
                                                        ephemeral=True)
                return

            # Fix: Properly extract the form data
            questions = form_data["questions"]
            submission_channel_id = form_data["submission_channel"]
            enable_approval = form_data.get("enable_approval", False)
            display_title = form_data.get("display_title", self.form_name)

            modal = DynamicModal(
                title=display_title,  # Use the display title
                questions=questions,
                submission_channel_id=submission_channel_id,
                enable_approval=enable_approval,
                form_name=self.form_name,  # Internal form name for reference
                display_title=display_title,  # Pass the display title
                page=0,
                previous_answers=[]
            )

            logger.info("Modal created, sending to user")
            await interaction.response.send_modal(modal)
            logger.info("Modal sent successfully")
        except Exception as e:
            logger.error(f"Error in open_form: {e}\n{traceback.format_exc()}")
            await interaction.response.send_message(
                "An error occurred while opening the form. Please try again.",
                ephemeral=True
            )


class BulkQuestionsModal(Modal):
    def __init__(self, form_name):
        super().__init__(title=f"Add Questions to {form_name}")
        self.form_name = form_name
        self.questions = TextInput(
            label="Enter questions (one per line)",
            style=TextStyle.paragraph,
            placeholder="Enter each question on a new line",
            required=True
        )
        self.add_item(self.questions)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Parse the questions from the text input
            questions_text = self.questions.value
            questions_list = [q.strip() for q in questions_text.split('\n') if q.strip()]
            if not questions_list:
                await interaction.response.send_message("No valid questions were provided.", ephemeral=True)
                return

            # Debug info
            print(f"Adding {len(questions_list)} questions to form '{self.form_name}'")
            print(f"Questions to add: {questions_list}")

            # Get the guild ID
            guild_id = str(interaction.guild.id)
            print(f"Guild ID: {guild_id}")

            # Load the current forms data directly from file to ensure we have the latest
            forms = load_forms()
            print(f"Forms loaded from file: {forms.get(guild_id, {}).get(self.form_name, {})}")

            # Check if the form exists
            if guild_id not in forms or self.form_name not in forms[guild_id]:
                await interaction.response.send_message(f"Form '{self.form_name}' not found.", ephemeral=True)
                return

            # Ensure the questions list exists
            if "questions" not in forms[guild_id][self.form_name]:
                forms[guild_id][self.form_name]["questions"] = []

            # Add the new questions
            current_questions = forms[guild_id][self.form_name]["questions"]
            print(f"Current questions before adding: {current_questions}")

            # Directly extend the questions list with the new questions
            forms[guild_id][self.form_name]["questions"].extend(questions_list)
            print(f"Updated questions: {forms[guild_id][self.form_name]['questions']}")

            # Save the updated forms data
            if save_forms(forms):
                print(f"Forms saved to file")

                # Update the bot's forms cache - this is critical
                # Get the bot instance from the interaction client
                bot = interaction.client

                # Update the bot's forms cache and the cog's forms cache
                if hasattr(bot, 'forms'):
                    bot.forms = forms
                    print("Updated bot's forms cache")

                # Find and update the Formcall cog's forms cache
                for cog_name, cog in bot.cogs.items():
                    if isinstance(cog, Formcall):
                        cog.forms = forms
                        print(f"Updated {cog_name} cog's forms cache")
            else:
                print("Failed to save forms")

            # Create a response embed
            embed = discord.Embed(
                title="Questions Added",
                description=f"Added {len(questions_list)} questions to form '{self.form_name}'",
                color=discord.Color.green()
            )

            # Add the first few questions as fields
            max_display = min(10, len(questions_list))
            for i in range(max_display):
                embed.add_field(
                    name=f"Question {len(current_questions) + i + 1}",
                    value=questions_list[i],
                    inline=False
                )

            if len(questions_list) > max_display:
                embed.add_field(
                    name="Note",
                    value=f"{len(questions_list) - max_display} more questions were added but not shown here.",
                    inline=False
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            print(f"Error in BulkQuestionsModal.on_submit: {e}")
            import traceback
            traceback.print_exc()
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"An error occurred while adding questions: {str(e)}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"An error occurred while adding questions: {str(e)}",
                    ephemeral=True
                )


class Formcall(commands.GroupCog, name="form"):
    """Cog for creating and managing application forms"""

    def __init__(self, bot):
        self.bot = bot
        self._default_permission = discord.Permissions(manage_guild=True)
        self.forms = load_forms()
        self.bot.forms = self.forms  # Make forms accessible from the bot
        self.bot.save_forms = lambda: save_forms(self.forms)  # Add save method to bot
        # Register persistent views for existing form buttons
        self.register_persistent_views()
        super().__init__()

    def register_persistent_views(self):
        """Register persistent views for all existing form buttons"""
        # Register form buttons
        for guild_id, guild_forms in self.forms.items():
            for form_name, form_data in guild_forms.items():
                enable_approval = form_data.get('enable_approval', False)
                view = PersistentFormView(form_name, enable_approval)
                self.bot.add_view(view)
                logger.info(f"Registered persistent view for form: {form_name}")

        # Register listeners for approval/denial buttons
        self.bot.add_view(View(timeout=None))  # Generic view to catch all persistent buttons
        logger.info("Registered persistent views for approval/denial buttons")

    @app_commands.command(name="create")
    @app_commands.describe(form_name="Name of the form to create")
    @app_commands.checks.has_permissions(administrator=True)
    async def create_form(self, interaction: discord.Interaction, form_name: str):
        """Creates a new form"""
        guild_id = str(interaction.guild.id)
        if guild_id not in self.forms:
            self.forms[guild_id] = {}
        if form_name in self.forms[guild_id]:
            await interaction.response.send_message(
                f"A form with the name '{form_name}' already exists.",
                ephemeral=True
            )
        else:
            self.forms[guild_id][form_name] = {
                "questions": [],
                "submission_channel": None,
                "enable_approval": False,
                "button_locations": []
            }
            save_forms(self.forms)
            embed = discord.Embed(
                title="Form Created",
                description=f"Form '{form_name}' created successfully.",
                color=discord.Color.green()
            )
            embed.add_field(
                name="Next Steps",
                value=(
                    "1. Add questions with `/form add_question` or `/form add_questions`\n"
                    "2. Set submission channel with `/form set_channel`\n"
                    "3. Deploy the form with `/form deploy`"
                )
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="add_question")
    @app_commands.describe(
        form_name="Name of the form to add a question to",
        question="The question to add"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def add_question(self, interaction: discord.Interaction, form_name: str, question: str):
        """Adds a question to the specified form"""
        guild_id = str(interaction.guild.id)
        if guild_id in self.forms and form_name in self.forms[guild_id]:
            self.forms[guild_id][form_name]["questions"].append(question)
            save_forms(self.forms)
            # Get the question count
            question_count = len(self.forms[guild_id][form_name]["questions"])
            embed = discord.Embed(
                title="Question Added",
                description=f"Added question #{question_count} to form '{form_name}':",
                color=discord.Color.green()
            )
            embed.add_field(name=f"Question {question_count}", value=question, inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(f"Form '{form_name}' not found.", ephemeral=True)

    @app_commands.command(name="add_questions")
    @app_commands.describe(form_name="Name of the form to add questions to")
    @app_commands.checks.has_permissions(administrator=True)
    async def add_questions(self, interaction: discord.Interaction, form_name: str):
        """Add multiple questions at once to a form"""
        try:
            guild_id = str(interaction.guild.id)
            # Check if the form exists
            if guild_id not in self.forms or form_name not in self.forms[guild_id]:
                await interaction.response.send_message(f"Form '{form_name}' not found.", ephemeral=True)
                return
            # Create and send the modal
            modal = BulkQuestionsModal(form_name)
            await interaction.response.send_modal(modal)
        except Exception as e:
            print(f"Error in add_questions command: {e}")
            import traceback
            traceback.print_exc()
            await interaction.response.send_message(
                f"An error occurred: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="view_questions")
    @app_commands.describe(form_name="Name of the form to view questions for")
    @app_commands.checks.has_permissions(administrator=True)
    async def view_questions(self, interaction: discord.Interaction, form_name: str):
        """Displays the current list of questions for the specified form"""
        guild_id = str(interaction.guild.id)
        if guild_id in self.forms and form_name in self.forms[guild_id]:
            questions = self.forms[guild_id][form_name].get("questions", [])
            if not questions:
                await interaction.response.send_message(
                    f"Form '{form_name}' has no questions yet.",
                    ephemeral=True
                )
                return

            # Create an embed to display the questions
            embed = discord.Embed(
                title=f"Questions for '{form_name}'",
                description=f"Total questions: {len(questions)}",
                color=discord.Color.blue()
            )

            # Add questions as fields, up to 25 (Discord's limit)
            for i, question in enumerate(questions[:25]):
                embed.add_field(
                    name=f"Question {i + 1}",
                    value=question,
                    inline=False
                )

            if len(questions) > 25:
                embed.set_footer(
                    text=f"Showing 25/{len(questions)} questions. Use /form view_more_questions to see more.")

            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(f"Form '{form_name}' not found.", ephemeral=True)

    @app_commands.command(name="view_more_questions")
    @app_commands.describe(
        form_name="Name of the form to view questions for",
        page="Page number to view (starts at 1)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def view_more_questions(self, interaction: discord.Interaction, form_name: str, page: int = 1):
        """Displays additional pages of questions for the specified form"""
        if page < 1:
            await interaction.response.send_message("Page number must be at least 1.", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)
        if guild_id in self.forms and form_name in self.forms[guild_id]:
            questions = self.forms[guild_id][form_name].get("questions", [])
            if not questions:
                await interaction.response.send_message(
                    f"Form '{form_name}' has no questions yet.",
                    ephemeral=True
                )
                return

            # Calculate pagination
            questions_per_page = 25
            total_pages = (len(questions) + questions_per_page - 1) // questions_per_page
            if page > total_pages:
                await interaction.response.send_message(
                    f"Invalid page number. Form '{form_name}' has {total_pages} pages of questions.",
                    ephemeral=True
                )
                return

            start_idx = (page - 1) * questions_per_page
            end_idx = min(start_idx + questions_per_page, len(questions))
            page_questions = questions[start_idx:end_idx]

            # Create an embed to display the questions
            embed = discord.Embed(
                title=f"Questions for '{form_name}' - Page {page}/{total_pages}",
                description=f"Total questions: {len(questions)}",
                color=discord.Color.blue()
            )

            # Add questions as fields
            for i, question in enumerate(page_questions):
                embed.add_field(
                    name=f"Question {start_idx + i + 1}",
                    value=question,
                    inline=False
                )

            embed.set_footer(text=f"Showing questions {start_idx + 1}-{end_idx} of {len(questions)}")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(f"Form '{form_name}' not found.", ephemeral=True)

    @app_commands.command(name="remove_question")
    @app_commands.describe(
        form_name="Name of the form to remove a question from",
        question_number="The number of the question to remove (starts at 1)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_question(self, interaction: discord.Interaction, form_name: str, question_number: int):
        """Removes a question from the specified form"""
        guild_id = str(interaction.guild.id)
        if guild_id in self.forms and form_name in self.forms[guild_id]:
            questions = self.forms[guild_id][form_name].get("questions", [])
            if not questions:
                await interaction.response.send_message(
                    f"Form '{form_name}' has no questions to remove.",
                    ephemeral=True
                )
                return

            if question_number < 1 or question_number > len(questions):
                await interaction.response.send_message(
                    f"Invalid question number. Form '{form_name}' has {len(questions)} questions.",
                    ephemeral=True
                )
                return

            # Remove the question
            removed_question = self.forms[guild_id][form_name]["questions"].pop(question_number - 1)
            save_forms(self.forms)

            embed = discord.Embed(
                title="Question Removed",
                description=f"Removed question #{question_number} from form '{form_name}':",
                color=discord.Color.red()
            )
            embed.add_field(name="Removed Question", value=removed_question, inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(f"Form '{form_name}' not found.", ephemeral=True)

    @app_commands.command(name="set_channel")
    @app_commands.describe(
        form_name="Name of the form to set the submission channel for",
        channel="The channel where form submissions will be sent"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def set_channel(self, interaction: discord.Interaction, form_name: str, channel: discord.TextChannel):
        """Sets the channel where form submissions will be sent"""
        guild_id = str(interaction.guild.id)
        if guild_id in self.forms and form_name in self.forms[guild_id]:
            self.forms[guild_id][form_name]["submission_channel"] = channel.id
            save_forms(self.forms)
            embed = discord.Embed(
                title="Submission Channel Set",
                description=f"Form submissions for '{form_name}' will now be sent to {channel.mention}.",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(f"Form '{form_name}' not found.", ephemeral=True)

    @app_commands.command(name="toggle_approval")
    @app_commands.describe(
        form_name="Name of the form to toggle approval for",
        enable="Whether to enable or disable the approval system"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def toggle_approval(self, interaction: discord.Interaction, form_name: str, enable: bool):
        """Enables or disables the approval system for a form"""
        guild_id = str(interaction.guild.id)
        if guild_id in self.forms and form_name in self.forms[guild_id]:
            self.forms[guild_id][form_name]["enable_approval"] = enable
            save_forms(self.forms)

            status = "enabled" if enable else "disabled"
            embed = discord.Embed(
                title="Approval System Updated",
                description=f"Approval system for '{form_name}' has been {status}.",
                color=discord.Color.green()
            )

            # Update any existing button views
            for location in self.forms[guild_id][form_name].get("button_locations", []):
                try:
                    channel_id, message_id = location
                    channel = interaction.guild.get_channel(channel_id)
                    if channel:
                        message = await channel.fetch_message(message_id)
                        if message:
                            view = PersistentFormView.from_form_data(form_name, self.forms[guild_id][form_name])
                            await message.edit(view=view)
                except Exception as e:
                    print(f"Error updating button view: {e}")

            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(f"Form '{form_name}' not found.", ephemeral=True)

    @app_commands.command(name="deploy")
    @app_commands.describe(
        form_name="Name of the form to deploy",
        channel="The channel where the form button will be placed",
        title="Title for the form message",
        description="Description for the form message"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def deploy_form(self, interaction: discord.Interaction, form_name: str, channel: discord.TextChannel,
                          title: str, description: str):
        """Deploys a form button to a channel"""
        guild_id = str(interaction.guild.id)
        # Reload forms from file to ensure we have the latest data
        self.forms = load_forms()
        if guild_id not in self.forms or form_name not in self.forms[guild_id]:
            await interaction.response.send_message(f"Form '{form_name}' not found.", ephemeral=True)
            return

        form_data = self.forms[guild_id][form_name]
        # Debug the form data to see what's happening
        print(f"Form data for {form_name}: {form_data}")

        # Check if questions exist and is a non-empty list
        if "questions" not in form_data or not isinstance(form_data["questions"], list) or len(
                form_data["questions"]) == 0:
            await interaction.response.send_message(
                f"Form '{form_name}' has no questions. Add questions before deploying.",
                ephemeral=True
            )
            return

        if form_data.get("submission_channel") is None:
            await interaction.response.send_message(
                f"Form '{form_name}' has no submission channel set. Set a channel before deploying.",
                ephemeral=True
            )
            return

        # Store the display title in the form data
        form_data["display_title"] = title

        # Create an embed for the form
        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Form: {form_name}")

        # Create a persistent view with the form button
        enable_approval = form_data.get('enable_approval', False)
        view = PersistentFormView(form_name, enable_approval, title)  # Pass the title

        # Send the message with the button
        form_message = await channel.send(embed=embed, view=view)

        # Store the button location
        if "button_locations" not in form_data:
            form_data["button_locations"] = []

        # Store as a tuple to maintain compatibility with existing data
        form_data["button_locations"].append((channel.id, form_message.id))
        save_forms(self.forms)

        await interaction.response.send_message(
            f"Form '{form_name}' has been deployed to {channel.mention}.",
            ephemeral=True
        )

    @app_commands.command(name="list")
    @app_commands.checks.has_permissions(administrator=True)
    async def list_forms(self, interaction: discord.Interaction):
        """Lists all forms for the current server"""
        guild_id = str(interaction.guild.id)
        if guild_id not in self.forms or not self.forms[guild_id]:
            await interaction.response.send_message("No forms have been created for this server.", ephemeral=True)
            return

        embed = discord.Embed(
            title="Forms for this server",
            description="Here are all the forms that have been created:",
            color=discord.Color.blue()
        )

        for form_name, form_data in self.forms[guild_id].items():
            # Get form details
            question_count = len(form_data.get("questions", []))
            submission_channel_id = form_data.get("submission_channel")
            submission_channel = (
                interaction.guild.get_channel(submission_channel_id).mention
                if submission_channel_id and interaction.guild.get_channel(submission_channel_id)
                else "Not set"
            )
            approval_status = "Enabled" if form_data.get("enable_approval", False) else "Disabled"
            button_count = len(form_data.get("button_locations", []))

            # Add form as a field
            embed.add_field(
                name=form_name,
                value=(
                    f"Questions: {question_count}\n"
                    f"Submission Channel: {submission_channel}\n"
                    f"Approval System: {approval_status}\n"
                    f"Button Deployments: {button_count}"
                ),
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="delete")
    @app_commands.describe(form_name="Name of the form to delete")
    @app_commands.checks.has_permissions(administrator=True)
    async def delete_form(self, interaction: discord.Interaction, form_name: str):
        """Deletes a form"""
        guild_id = str(interaction.guild.id)
        if guild_id in self.forms and form_name in self.forms[guild_id]:
            # Get button locations before deleting
            button_locations = self.forms[guild_id][form_name].get("button_locations", [])

            # Delete the form
            del self.forms[guild_id][form_name]
            save_forms(self.forms)

            # Try to remove buttons
            removed_buttons = 0
            for location in button_locations:
                try:
                    channel_id, message_id = location
                    channel = interaction.guild.get_channel(channel_id)
                    if channel:
                        message = await channel.fetch_message(message_id)
                        if message:
                            await message.edit(view=None)
                            removed_buttons += 1
                except Exception as e:
                    print(f"Error removing button: {e}")

            embed = discord.Embed(
                title="Form Deleted",
                description=f"Form '{form_name}' has been deleted.",
                color=discord.Color.red()
            )

            if button_locations:
                embed.add_field(
                    name="Button Cleanup",
                    value=f"Removed {removed_buttons}/{len(button_locations)} form buttons.",
                    inline=False
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(f"Form '{form_name}' not found.", ephemeral=True)

    @app_commands.command(name="debug_form")
    @app_commands.describe(form_name="Name of the form to debug")
    @app_commands.checks.has_permissions(administrator=True)
    async def debug_form(self, interaction: discord.Interaction, form_name: str):
        """Displays detailed debug information about a form"""
        guild_id = str(interaction.guild.id)

        # Reload forms from file
        fresh_forms = load_forms()

        # Check both in-memory and file versions
        memory_form = self.forms.get(guild_id, {}).get(form_name, {})
        file_form = fresh_forms.get(guild_id, {}).get(form_name, {})

        if not memory_form and not file_form:
            await interaction.response.send_message(f"Form '{form_name}' not found.", ephemeral=True)
            return

        # Create debug embed
        embed = discord.Embed(
            title=f"Debug Info for '{form_name}'",
            color=discord.Color.gold()
        )

        # Compare in-memory vs file data
        memory_questions = len(memory_form.get("questions", []))
        file_questions = len(file_form.get("questions", []))

        embed.add_field(
            name="Question Count",
            value=f"In-memory: {memory_questions}\nIn file: {file_questions}",
            inline=False
        )

        # Show other important form properties
        embed.add_field(
            name="Submission Channel",
            value=f"In-memory: {memory_form.get('submission_channel')}\nIn file: {file_form.get('submission_channel')}",
            inline=False
        )

        embed.add_field(
            name="Approval System",
            value=f"In-memory: {memory_form.get('enable_approval', False)}\nIn file: {file_form.get('enable_approval', False)}",
            inline=False
        )

        # Show button locations
        memory_buttons = len(memory_form.get("button_locations", []))
        file_buttons = len(file_form.get("button_locations", []))
        embed.add_field(
            name="Button Deployments",
            value=f"In-memory: {memory_buttons}\nIn file: {file_buttons}",
            inline=False
        )

        # If there's a discrepancy, offer to fix it
        if memory_form != file_form:
            embed.add_field(
                name="⚠️ Discrepancy Detected",
                value="The in-memory form data doesn't match the file data. Use `/form reload` to update.",
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="reload")
    @app_commands.checks.has_permissions(administrator=True)
    async def reload_forms(self, interaction: discord.Interaction):
        """Reloads all forms from the database file"""
        try:
            # Reload forms from file
            self.forms = load_forms()
            self.bot.forms = self.forms

            # Re-register persistent views
            self.register_persistent_views()

            await interaction.response.send_message(
                "Forms have been reloaded from the database file.",
                ephemeral=True
            )
        except Exception as e:
            print(f"Error reloading forms: {e}")
            import traceback
            traceback.print_exc()
            await interaction.response.send_message(
                f"An error occurred while reloading forms: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="set_role_ping")
    @app_commands.describe(
        form_name="Name of the form to set role pings for",
        roles="Roles to ping when a new form is submitted (comma separated)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def set_role_ping(self, interaction: discord.Interaction, form_name: str, roles: str):
        """Sets roles to ping when a new form is submitted"""
        guild_id = str(interaction.guild.id)

        if guild_id not in self.forms or form_name not in self.forms[guild_id]:
            await interaction.response.send_message(f"Form '{form_name}' not found.", ephemeral=True)
            return

        # Parse and validate roles
        role_names = [role.strip() for role in roles.split(',') if role.strip()]
        valid_roles = []
        invalid_roles = []

        for role_name in role_names:
            role = find_role_flexible(interaction.guild, role_name)
            if role:
                valid_roles.append(role.id)
            else:
                invalid_roles.append(role_name)

        if not valid_roles and role_names:
            await interaction.response.send_message(
                f"No valid roles found. Invalid roles: {', '.join(invalid_roles)}",
                ephemeral=True
            )
            return

        # Store role IDs in the form data
        self.forms[guild_id][form_name]["ping_roles"] = valid_roles
        save_forms(self.forms)

        embed = discord.Embed(
            title="Role Pings Set",
            description=f"Role pings for '{form_name}' have been updated.",
            color=discord.Color.green()
        )

        if valid_roles:
            role_mentions = [f"<@&{role_id}>" for role_id in valid_roles]
            embed.add_field(
                name="Roles to Ping",
                value=", ".join(role_mentions),
                inline=False
            )

        if invalid_roles:
            embed.add_field(
                name="Invalid Roles",
                value=", ".join(invalid_roles),
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="set_approval_roles")
    @app_commands.describe(
        form_name="Name of the form to set approval roles for",
        roles="Roles that can approve or deny submissions (comma separated)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def set_approval_roles(self, interaction: discord.Interaction, form_name: str, roles: str):
        """Sets which roles can approve or deny form submissions"""
        guild_id = str(interaction.guild.id)

        if guild_id not in self.forms or form_name not in self.forms[guild_id]:
            await interaction.response.send_message(f"Form '{form_name}' not found.", ephemeral=True)
            return

        # Parse and validate roles
        role_names = [role.strip() for role in roles.split(',') if role.strip()]
        valid_roles = []
        invalid_roles = []

        for role_name in role_names:
            role = find_role_flexible(interaction.guild, role_name)
            if role:
                valid_roles.append(role.id)
            else:
                invalid_roles.append(role_name)

        if not valid_roles and role_names:
            await interaction.response.send_message(
                f"No valid roles found. Invalid roles: {', '.join(invalid_roles)}",
                ephemeral=True
            )
            return

        # Store role IDs in the form data
        self.forms[guild_id][form_name]["approval_roles"] = valid_roles
        save_forms(self.forms)

        embed = discord.Embed(
            title="Approval Roles Set",
            description=f"Approval roles for '{form_name}' have been updated.",
            color=discord.Color.green()
        )

        if valid_roles:
            role_mentions = [f"<@&{role_id}>" for role_id in valid_roles]
            embed.add_field(
                name="Roles That Can Approve/Deny",
                value=", ".join(role_mentions),
                inline=False
            )

        if invalid_roles:
            embed.add_field(
                name="Invalid Roles",
                value=", ".join(invalid_roles),
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    # Check if we already have a cog instance
    existing_cog = bot.get_cog("Formcall")
    if existing_cog:
        # If we do, remove it first to prevent duplicate handlers
        await bot.remove_cog("Formcall")

    # Create a custom handler that we can reference later
    async def approval_button_handler(interaction):
        if interaction.type == discord.InteractionType.component:
            custom_id = interaction.data.get('custom_id', '')
            # Handle approval buttons
            if custom_id.startswith('approve:') or custom_id.startswith('deny:'):
                parts = custom_id.split(':')
                if len(parts) >= 3:
                    action = parts[0]  # 'approve' or 'deny'
                    form_name = parts[1]
                    submission_id = parts[2]
                    # Create a view with the extracted data
                    view = ApprovalView(form_name, submission_id)
                    # Call the appropriate callback
                    if action == 'approve':
                        await view.approve_callback(interaction)
                    else:
                        await view.deny_callback(interaction)
                    return

    # Store the handler on the bot for future reference
    if hasattr(bot, '_approval_handler'):
        # Remove the old handler if it exists
        bot.remove_listener(bot._approval_handler, 'on_interaction')

    # Add the new handler and store it
    bot.add_listener(approval_button_handler, 'on_interaction')
    bot._approval_handler = approval_button_handler

    # Now add the cog
    await bot.add_cog(Formcall(bot))
