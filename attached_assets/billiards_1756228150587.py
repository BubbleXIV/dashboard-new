import discord
from discord.ext import commands
import asyncio
import random
import math
import time
from typing import Dict, List, Tuple, Optional, Union
import json
import os

# Add this constant near the top of the file
BILLIARDS_CONFIG_FILE = "./databases/billiards_config.json"


class Ball:
    def __init__(self, x: float, y: float, vx: float = 0, vy: float = 0, number: int = 0, pocketed: bool = False):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.number = number  # 0 for cue ball, 1-15 for other balls
        self.pocketed = pocketed

    def move(self, friction: float = 0.98):
        self.x += self.vx
        self.y += self.vy
        self.vx *= friction
        self.vy *= friction

        # Stop if velocity is very small
        if abs(self.vx) < 0.01 and abs(self.vy) < 0.01:
            self.vx = 0
            self.vy = 0

    def is_moving(self) -> bool:
        return abs(self.vx) > 0.01 or abs(self.vy) > 0.01

    def distance_to(self, other: 'Ball') -> float:
        return math.sqrt((self.x - other.x) ** 2 + (self.y - other.y) ** 2)

    def collide(self, other: 'Ball'):
        # Calculate collision physics
        dx = other.x - self.x
        dy = other.y - self.y
        distance = max(0.1, math.sqrt(dx * dx + dy * dy))  # Avoid division by zero

        # Normalize direction
        nx = dx / distance
        ny = dy / distance

        # Relative velocity
        dvx = self.vx - other.vx
        dvy = self.vy - other.vy

        # Velocity along collision normal
        velocity_along_normal = dvx * nx + dvy * ny

        # Don't collide if balls are moving away from each other
        if velocity_along_normal > 0:
            return

        # Collision impulse
        impulse = 2 * velocity_along_normal / 2  # Assuming equal mass

        # Apply impulse
        self.vx -= impulse * nx
        self.vy -= impulse * ny
        other.vx += impulse * nx
        other.vy += impulse * ny


class BilliardsTable:
    def __init__(self, width: int = 60, height: int = 30):
        self.width = width
        self.height = height
        self.balls: List[Ball] = []
        self.pockets = [
            (2, 2), (width // 2, 2), (width - 3, 2),
            (2, height - 3), (width // 2, height - 3), (width - 3, height - 3)
        ]
        self.reset()

    def reset(self):
        self.balls = []

        # Add cue ball
        self.balls.append(Ball(self.width // 4, self.height // 2, 0, 0, 0))

        # Add numbered balls in triangle formation
        row_starts = [self.width * 3 // 4, self.width * 3 // 4 - 2, self.width * 3 // 4 - 4,
                      self.width * 3 // 4 - 6, self.width * 3 // 4 - 8]
        ball_num = 1

        for i, row_start in enumerate(row_starts):
            for j in range(i + 1):
                y_offset = j * 2 - i
                self.balls.append(Ball(row_start, self.height // 2 + y_offset, 0, 0, ball_num))
                ball_num += 1
                if ball_num > 15:
                    break

    def shoot_cue_ball(self, angle: float, power: float):
        cue_ball = self.balls[0]
        if not cue_ball.pocketed and not cue_ball.is_moving():
            cue_ball.vx = power * math.cos(angle)
            cue_ball.vy = power * math.sin(angle)

    def update(self) -> bool:
        # Check if any balls are still moving
        any_moving = False

        # Move all balls
        for ball in self.balls:
            if not ball.pocketed:
                ball.move()
                if ball.is_moving():
                    any_moving = True

        # Check for collisions with walls
        for ball in self.balls:
            if not ball.pocketed:
                # Bounce off walls with some energy loss
                if ball.x <= 2 or ball.x >= self.width - 3:
                    ball.vx *= -0.9
                    # Ensure ball stays in bounds
                    if ball.x < 2:
                        ball.x = 2
                    if ball.x > self.width - 3:
                        ball.x = self.width - 3

                if ball.y <= 2 or ball.y >= self.height - 3:
                    ball.vy *= -0.9
                    # Ensure ball stays in bounds
                    if ball.y < 2:
                        ball.y = 2
                    if ball.y > self.height - 3:
                        ball.y = self.height - 3

        # Check for ball collisions
        for i in range(len(self.balls)):
            for j in range(i + 1, len(self.balls)):
                ball1 = self.balls[i]
                ball2 = self.balls[j]

                if not ball1.pocketed and not ball2.pocketed:
                    # Ball diameter is roughly 2 units
                    if ball1.distance_to(ball2) < 2:
                        ball1.collide(ball2)

        # Check for pocketing
        for ball in self.balls:
            if not ball.pocketed:
                for px, py in self.pockets:
                    if math.sqrt((ball.x - px) ** 2 + (ball.y - py) ** 2) < 2:
                        ball.pocketed = True
                        ball.vx = 0
                        ball.vy = 0
                        break

        # If cue ball is pocketed, respawn it
        if self.balls[0].pocketed:
            self.balls[0].pocketed = False
            self.balls[0].x = self.width // 4
            self.balls[0].y = self.height // 2
            self.balls[0].vx = 0
            self.balls[0].vy = 0

        return any_moving

    def render(self) -> str:
        # Create empty table
        table = [[' ' for _ in range(self.width)] for _ in range(self.height)]

        # Draw walls
        for x in range(self.width):
            table[0][x] = '═'
            table[self.height - 1][x] = '═'

        for y in range(self.height):
            table[y][0] = '║'
            table[y][self.width - 1] = '║'

        # Draw corners
        table[0][0] = '╔'
        table[0][self.width - 1] = '╗'
        table[self.height - 1][0] = '╚'
        table[self.height - 1][self.width - 1] = '╝'

        # Draw pockets
        for px, py in self.pockets:
            table[py][px] = 'O'

        # Draw balls
        for ball in self.balls:
            if not ball.pocketed:
                x, y = int(ball.x), int(ball.y)
                if 0 <= x < self.width and 0 <= y < self.height:
                    if ball.number == 0:
                        table[y][x] = '⚪'  # Cue ball
                    else:
                        # Use numbers for the balls
                        if ball.number < 10:
                            table[y][x] = str(ball.number)
                        else:
                            # For two-digit numbers, just use letters
                            table[y][x] = chr(ord('A') + ball.number - 10)

        # Convert to string
        return '\n'.join(''.join(row) for row in table)


class BilliardsGame:
    def __init__(self, channel_id: int, player1_id: int, player2_id: Optional[int] = None):
        self.channel_id = channel_id
        self.player1_id = player1_id
        self.player2_id = player2_id
        self.table = BilliardsTable()
        self.current_player_id = player1_id
        self.message: Optional[discord.Message] = None
        self.game_over = False
        self.last_interaction = time.time()

    async def update_display(self, bot):
        channel = bot.get_channel(self.channel_id)
        if not channel:
            return False

        # Render the table
        table_str = self.table.render()

        # Add game info
        player1 = await bot.fetch_user(self.player1_id)
        player1_name = player1.display_name if player1 else "Player 1"

        if self.player2_id:
            player2 = await bot.fetch_user(self.player2_id)
            player2_name = player2.display_name if player2 else "Player 2"
            current_player = player1_name if self.current_player_id == self.player1_id else player2_name
            game_info = f"🎱 Billiards: {player1_name} vs {player2_name}\nCurrent turn: {current_player}"
        else:
            game_info = f"🎱 Billiards: {player1_name} (Practice mode)"

        # Count pocketed balls
        pocketed_balls = [ball.number for ball in self.table.balls if ball.pocketed and ball.number > 0]
        pocketed_info = f"Pocketed balls: {', '.join(str(b) for b in sorted(pocketed_balls))}" if pocketed_balls else "No balls pocketed yet"

        # Add instructions
        instructions = "Type `!shoot <angle> <power>` to take a shot. Angle (0-360°), Power (1-10)"

        embed = discord.Embed(
            title="Billiards Game",
            description=f"```\n{table_str}\n```\n{game_info}\n{pocketed_info}\n\n{instructions}",
            color=0x00ff00
        )

        if self.message:
            try:
                await self.message.edit(embed=embed)
            except:
                self.message = await channel.send(embed=embed)
        else:
            self.message = await channel.send(embed=embed)

        return True

    def is_game_over(self) -> bool:
        # Game is over if all numbered balls are pocketed
        return all(ball.pocketed for ball in self.table.balls if ball.number > 0)

    def switch_player(self):
        if self.player2_id:  # Only switch if there are two players
            self.current_player_id = self.player2_id if self.current_player_id == self.player1_id else self.player1_id


class Billiards(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.games = {}  # channel_id -> game
        self.game_tasks = {}  # channel_id -> task
        self.cleanup_task = None
        self.config = self.load_config()

    def load_config(self):
        """Load billiards configuration from file"""
        default_config = {
            "enabled_channels": {},  # guild_id -> [channel_ids]
            "admin_roles": {}  # guild_id -> [role_ids]
        }

        if os.path.exists(BILLIARDS_CONFIG_FILE):
            try:
                with open(BILLIARDS_CONFIG_FILE, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading billiards config: {e}")
                return default_config
        else:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(BILLIARDS_CONFIG_FILE), exist_ok=True)
            # Save default config
            with open(BILLIARDS_CONFIG_FILE, 'w') as f:
                json.dump(default_config, f, indent=4)
            return default_config

    def save_config(self):
        """Save billiards configuration to file"""
        with open(BILLIARDS_CONFIG_FILE, 'w') as f:
            json.dump(self.config, f, indent=4)

    def is_channel_enabled(self, guild_id, channel_id):
        """Check if billiards is enabled in this channel"""
        guild_id_str = str(guild_id)
        channel_id_str = str(channel_id)

        # If no channels are configured for this guild, allow all channels
        if guild_id_str not in self.config["enabled_channels"] or not self.config["enabled_channels"][guild_id_str]:
            return True

        # Otherwise, check if this channel is in the enabled list
        return channel_id_str in self.config["enabled_channels"][guild_id_str]

    def has_admin_permission(self, ctx):
        """Check if user has permission to manage billiards settings"""
        # Server owner always has permission
        if ctx.author.id == ctx.guild.owner_id:
            return True

        # Check for administrator permission
        if ctx.author.guild_permissions.administrator:
            return True

        # Check for specific roles
        guild_id_str = str(ctx.guild.id)
        if guild_id_str in self.config["admin_roles"]:
            user_roles = [str(role.id) for role in ctx.author.roles]
            for role_id in self.config["admin_roles"][guild_id_str]:
                if role_id in user_roles:
                    return True

        return False

    async def cog_load(self):
        # Start the cleanup task when the cog is loaded
        self.cleanup_task = asyncio.create_task(self.cleanup_inactive_games())

    def cog_unload(self):
        # Cancel all running tasks when the cog is unloaded
        for task in self.game_tasks.values():
            task.cancel()
        if self.cleanup_task:
            self.cleanup_task.cancel()

    @commands.group(name="billiards", aliases=["pool"], invoke_without_command=True)
    async def billiards(self, ctx):
        """Play a game of billiards"""
        await ctx.send("Use `!billiards start` to start a new game, or `!billiards practice` to practice alone.")

    @billiards.command(name="start")
    async def start_game(self, ctx, opponent: discord.Member = None):
        """Start a new billiards game, optionally with an opponent"""
        # Check if billiards is enabled in this channel
        if not self.is_channel_enabled(ctx.guild.id, ctx.channel.id):
            enabled_channels = self.config["enabled_channels"].get(str(ctx.guild.id), [])
            if enabled_channels:
                channel_mentions = [f"<#{ch_id}>" for ch_id in enabled_channels]
                await ctx.send(f"Billiards games are only allowed in: {', '.join(channel_mentions)}")
            else:
                await ctx.send("Billiards games are not enabled in this channel.")
            return

        channel_id = ctx.channel.id

        # Check if there's already a game in this channel
        if channel_id in self.games:
            await ctx.send("There's already a billiards game in progress in this channel!")
            return

        player2_id = opponent.id if opponent else None

        # Create a new game
        game = BilliardsGame(channel_id, ctx.author.id, player2_id)
        self.games[channel_id] = game

        # Start the game task
        self.game_tasks[channel_id] = asyncio.create_task(self.run_game(channel_id))

        if opponent:
            await ctx.send(f"{ctx.author.mention} has started a billiards game with {opponent.mention}!")
        else:
            await ctx.send(
                f"{ctx.author.mention} has started a billiards game! Anyone can join with `!billiards join`.")

    @billiards.command(name="practice")
    async def practice_game(self, ctx):
        """Start a practice billiards game (single player)"""
        # Check if billiards is enabled in this channel
        if not self.is_channel_enabled(ctx.guild.id, ctx.channel.id):
            enabled_channels = self.config["enabled_channels"].get(str(ctx.guild.id), [])
            if enabled_channels:
                channel_mentions = [f"<#{ch_id}>" for ch_id in enabled_channels]
                await ctx.send(f"Billiards games are only allowed in: {', '.join(channel_mentions)}")
            else:
                await ctx.send("Billiards games are not enabled in this channel.")
            return

        channel_id = ctx.channel.id

        # Check if there's already a game in this channel
        if channel_id in self.games:
            await ctx.send("There's already a billiards game in progress in this channel!")
            return

        # Create a new game (single player)
        game = BilliardsGame(channel_id, ctx.author.id)
        self.games[channel_id] = game

        # Start the game task
        self.game_tasks[channel_id] = asyncio.create_task(self.run_game(channel_id))

        await ctx.send(f"{ctx.author.mention} has started a practice billiards game!")

    @billiards.command(name="join")
    async def join_game(self, ctx):
        """Join an ongoing billiards game"""
        # Check if billiards is enabled in this channel
        if not self.is_channel_enabled(ctx.guild.id, ctx.channel.id):
            return  # Silently ignore in disabled channels

        channel_id = ctx.channel.id

        if channel_id not in self.games:
            await ctx.send("There's no billiards game in progress in this channel!")
            return

        game = self.games[channel_id]

        if game.player2_id:
            await ctx.send("This game already has two players!")
            return

        if game.player1_id == ctx.author.id:
            await ctx.send("You can't play against yourself!")
            return

        # Add the player to the game
        game.player2_id = ctx.author.id
        await ctx.send(f"{ctx.author.mention} has joined the billiards game!")
        await game.update_display(self.bot)

    @billiards.command(name="end", aliases=["stop", "quit"])
    async def end_game(self, ctx):
        """End the current billiards game"""
        # Check if billiards is enabled in this channel
        if not self.is_channel_enabled(ctx.guild.id, ctx.channel.id):
            return  # Silently ignore in disabled channels

        channel_id = ctx.channel.id

        if channel_id not in self.games:
            await ctx.send("There's no billiards game in progress in this channel!")
            return

        game = self.games[channel_id]

        # Only the players or admins can end the game
        if ctx.author.id != game.player1_id and ctx.author.id != game.player2_id and not ctx.author.guild_permissions.administrator:
            await ctx.send("Only players or admins can end the game!")
            return

        # Cancel the game task
        if channel_id in self.game_tasks:
            self.game_tasks[channel_id].cancel()
            del self.game_tasks[channel_id]

        # Remove the game
        del self.games[channel_id]

        await ctx.send("The billiards game has been ended.")

    @billiards.group(name="config", invoke_without_command=True)
    async def billiards_config(self, ctx):
        """Configure billiards settings"""
        if not self.has_admin_permission(ctx):
            await ctx.send("You don't have permission to configure billiards settings.")
            return

        guild_id_str = str(ctx.guild.id)
        enabled_channels = self.config["enabled_channels"].get(guild_id_str, [])
        admin_roles = self.config["admin_roles"].get(guild_id_str, [])

        embed = discord.Embed(
            title="Billiards Configuration",
            description="Current billiards settings for this server",
            color=discord.Color.blue()
        )

        if enabled_channels:
            channel_mentions = [f"<#{ch_id}>" for ch_id in enabled_channels]
            embed.add_field(
                name="Enabled Channels",
                value=", ".join(channel_mentions),
                inline=False
            )
        else:
            embed.add_field(
                name="Enabled Channels",
                value="All channels (no restrictions)",
                inline=False
            )

        if admin_roles:
            role_mentions = [f"<@&{role_id}>" for role_id in admin_roles]
            embed.add_field(
                name="Admin Roles",
                value=", ".join(role_mentions),
                inline=False
            )
        else:
            embed.add_field(
                name="Admin Roles",
                value="Only server administrators",
                inline=False
            )

        embed.add_field(
            name="Commands",
            value=(
                "`!billiards config addchannel #channel` - Enable billiards in a channel\n"
                "`!billiards config removechannel #channel` - Disable billiards in a channel\n"
                "`!billiards config addrole @role` - Add an admin role\n"
                "`!billiards config removerole @role` - Remove an admin role\n"
                "`!billiards config reset` - Reset to default (all channels enabled)"
            ),
            inline=False
        )

        await ctx.send(embed=embed)

    @billiards_config.command(name="addchannel")
    async def add_channel(self, ctx, channel: discord.TextChannel):
        """Add a channel to the enabled channels list"""
        if not self.has_admin_permission(ctx):
            await ctx.send("You don't have permission to configure billiards settings.")
            return

        guild_id_str = str(ctx.guild.id)
        channel_id_str = str(channel.id)

        if guild_id_str not in self.config["enabled_channels"]:
            self.config["enabled_channels"][guild_id_str] = []

        if channel_id_str in self.config["enabled_channels"][guild_id_str]:
            await ctx.send(f"Billiards is already enabled in {channel.mention}!")
            return

        self.config["enabled_channels"][guild_id_str].append(channel_id_str)
        self.save_config()

        await ctx.send(f"Billiards is now enabled in {channel.mention}!")

    @billiards_config.command(name="removechannel")
    async def remove_channel(self, ctx, channel: discord.TextChannel):
        """Remove a channel from the enabled channels list"""
        if not self.has_admin_permission(ctx):
            await ctx.send("You don't have permission to configure billiards settings.")
            return

        guild_id_str = str(ctx.guild.id)
        channel_id_str = str(channel.id)

        if guild_id_str not in self.config["enabled_channels"] or channel_id_str not in self.config["enabled_channels"][
            guild_id_str]:
            await ctx.send(f"Billiards is not specifically enabled in {channel.mention}!")
            return

        self.config["enabled_channels"][guild_id_str].remove(channel_id_str)
        self.save_config()

        await ctx.send(f"Billiards is now disabled in {channel.mention}!")

    @billiards_config.command(name="addrole")
    async def add_role(self, ctx, role: discord.Role):
        """Add a role to the admin roles list"""
        if not self.has_admin_permission(ctx):
            await ctx.send("You don't have permission to configure billiards settings.")
            return

        guild_id_str = str(ctx.guild.id)
        role_id_str = str(role.id)

        if guild_id_str not in self.config["admin_roles"]:
            self.config["admin_roles"][guild_id_str] = []

        if role_id_str in self.config["admin_roles"][guild_id_str]:
            await ctx.send(f"{role.name} already has billiards admin permissions!")
            return

        self.config["admin_roles"][guild_id_str].append(role_id_str)
        self.save_config()

        await ctx.send(f"{role.name} can now manage billiards settings!")

    @billiards_config.command(name="removerole")
    async def remove_role(self, ctx, role: discord.Role):
        """Remove a role from the admin roles list"""
        if not self.has_admin_permission(ctx):
            await ctx.send("You don't have permission to configure billiards settings.")
            return

        guild_id_str = str(ctx.guild.id)
        role_id_str = str(role.id)

        if guild_id_str not in self.config["admin_roles"] or role_id_str not in self.config["admin_roles"][
            guild_id_str]:
            await ctx.send(f"{role.name} doesn't have billiards admin permissions!")
            return

        self.config["admin_roles"][guild_id_str].remove(role_id_str)
        self.save_config()

        await ctx.send(f"{role.name} can no longer manage billiards settings!")

    @billiards_config.command(name="reset")
    async def reset_config(self, ctx):
        """Reset billiards configuration to default (all channels enabled)"""
        if not self.has_admin_permission(ctx):
            await ctx.send("You don't have permission to configure billiards settings.")
            return

        guild_id_str = str(ctx.guild.id)

        if guild_id_str in self.config["enabled_channels"]:
            self.config["enabled_channels"][guild_id_str] = []

        self.save_config()

        await ctx.send("Billiards configuration has been reset. Billiards is now enabled in all channels.")

    @commands.command(name="shoot")
    async def shoot(self, ctx, angle: float, power: float):
        """Shoot the cue ball with the given angle and power"""
        # Check if billiards is enabled in this channel
        if not self.is_channel_enabled(ctx.guild.id, ctx.channel.id):
            return  # Silently ignore in disabled channels

        channel_id = ctx.channel.id

        if channel_id not in self.games:
            return  # Silently ignore if there's no game

        game = self.games[channel_id]

        # Check if it's the player's turn
        if ctx.author.id != game.current_player_id and game.player2_id is not None:
            await ctx.send("It's not your turn!")
            return

        # Validate input
        if not (0 <= angle <= 360):
            await ctx.send("Angle must be between 0 and 360 degrees!")
            return

        if not (1 <= power <= 10):
            await ctx.send("Power must be between 1 and 10!")
            return

        # Convert angle to radians
        angle_rad = math.radians(angle)

        # Shoot the cue ball
        game.table.shoot_cue_ball(angle_rad, power * 0.5)  # Scale power

        # Update the last interaction time
        game.last_interaction = time.time()

        # Delete the command message to keep the channel clean
        try:
            await ctx.message.delete()
        except:
            pass

    async def run_game(self, channel_id: int):
        """Run the billiards game simulation"""
        try:
            game = self.games[channel_id]

            # Initial display
            await game.update_display(self.bot)

            while channel_id in self.games and not game.game_over:
                # Wait a bit
                await asyncio.sleep(0.5)

                # Update the table physics
                balls_moving = game.table.update()

                # Only update the display if balls are moving or it's been a while
                if balls_moving:
                    await game.update_display(self.bot)

                # If balls stopped moving, switch player
                if balls_moving and not game.table.update():
                    game.switch_player()
                    await game.update_display(self.bot)

                # Check if game is over
                if game.is_game_over():
                    game.game_over = True
                    await self.end_game_with_winner(channel_id)

        except asyncio.CancelledError:
            # Task was cancelled, clean up
            if channel_id in self.games:
                del self.games[channel_id]
            if channel_id in self.game_tasks:
                del self.game_tasks[channel_id]
        except Exception as e:
            print(f"Error in billiards game: {e}")
            # Clean up on error
            if channel_id in self.games:
                del self.games[channel_id]
            if channel_id in self.game_tasks:
                del self.game_tasks[channel_id]

    async def end_game_with_winner(self, channel_id: int):
        """End the game and announce the winner"""
        if channel_id not in self.games:
            return

        game = self.games[channel_id]
        channel = self.bot.get_channel(channel_id)

        if not channel:
            return

        # Get player names
        player1 = await self.bot.fetch_user(game.player1_id)
        player1_name = player1.display_name if player1 else "Player 1"

        if game.player2_id:
            player2 = await self.bot.fetch_user(game.player2_id)
            player2_name = player2.display_name if player2 else "Player 2"

            # In a real game, we'd determine the winner based on rules
            # For simplicity, we'll say the current player wins
            winner = player1_name if game.current_player_id == game.player1_id else player2_name
            await channel.send(f"🎱 Game over! {winner} wins the billiards game!")
        else:
            await channel.send(f"🎱 Practice game complete! All balls have been pocketed.")

        # Clean up
        if channel_id in self.game_tasks:
            self.game_tasks[channel_id].cancel()
            del self.game_tasks[channel_id]

        del self.games[channel_id]

    async def cleanup_inactive_games(self):
        """Periodically clean up inactive games"""
        try:
            while True:
                await asyncio.sleep(300)  # Check every 5 minutes

                current_time = time.time()
                channels_to_cleanup = []

                for channel_id, game in list(self.games.items()):
                    # If no interaction for 15 minutes, end the game
                    if current_time - game.last_interaction > 900:  # 15 minutes
                        channels_to_cleanup.append(channel_id)

                for channel_id in channels_to_cleanup:
                    channel = self.bot.get_channel(channel_id)
                    if channel:
                        await channel.send("The billiards game has been ended due to inactivity.")

                    # Cancel the game task
                    if channel_id in self.game_tasks:
                        self.game_tasks[channel_id].cancel()
                        del self.game_tasks[channel_id]

                    # Remove the game
                    if channel_id in self.games:
                        del self.games[channel_id]

        except asyncio.CancelledError:
            pass  # Task was cancelled, just exit


async def setup(bot):
    await bot.add_cog(Billiards(bot))


