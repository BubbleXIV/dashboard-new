import discord
from discord.ext import commands
import psutil
import platform
import time
import os
from datetime import datetime, timedelta


class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.start_time = time.time()

    def get_uptime(self):
        """Calculate bot uptime"""
        uptime_seconds = time.time() - self.start_time
        return str(timedelta(seconds=int(uptime_seconds)))

    def get_memory_usage(self):
        """Get memory usage in MB"""
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            return round(memory_info.rss / 1024 / 1024, 2)
        except:
            return "N/A"

    def get_cpu_usage(self):
        """Get CPU usage percentage"""
        try:
            return psutil.cpu_percent(interval=0.1)
        except:
            return "N/A"

    @commands.command(name='stats', aliases=['statistics', 'botinfo'])
    @commands.is_owner()
    async def show_stats(self, ctx):
        """Display comprehensive bot statistics (Owner only)"""
        # Calculate various statistics
        uptime = self.get_uptime()
        memory_usage = self.get_memory_usage()
        cpu_usage = self.get_cpu_usage()

        # Discord.py and Python versions
        dpy_version = discord.__version__
        python_version = platform.python_version()

        # Bot statistics
        total_guilds = len(self.bot.guilds)
        total_users = len(set(self.bot.get_all_members()))
        total_channels = len(list(self.bot.get_all_channels()))

        # Command counts
        prefix_commands = len(self.bot.commands)
        try:
            slash_commands = len(await self.bot.tree.fetch_commands())
        except:
            slash_commands = "N/A"

        # Latency
        latency = round(self.bot.latency * 1000, 2)

        # System info
        system = platform.system()
        system_version = platform.release()

        # Bot-specific stats
        loaded_cogs = len(self.bot.cogs)
        loaded_extensions = len(self.bot.extensions)
        forms_count = len(getattr(self.bot, 'forms', {}))

        # Create embed
        embed = discord.Embed(
            title="🤖 Bot Statistics",
            description=f"**{self.bot.user.name}** - Inhouse Bot by Don",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )

        # Bot Info
        embed.add_field(
            name="📊 Bot Information",
            value=f"**Uptime:** {uptime}\n"
                  f"**Latency:** {latency}ms\n"
                  f"**Synced:** {'✅' if getattr(self.bot, '_synced', False) else '❌'}",
            inline=True
        )

        # Server Stats
        embed.add_field(
            name="🌐 Server Statistics",
            value=f"**Guilds:** {total_guilds:,}\n"
                  f"**Users:** {total_users:,}\n"
                  f"**Channels:** {total_channels:,}",
            inline=True
        )

        # System Resources
        embed.add_field(
            name="💻 System Resources",
            value=f"**Memory:** {memory_usage} MB\n"
                  f"**CPU:** {cpu_usage}%\n"
                  f"**System:** {system} {system_version}",
            inline=True
        )

        # Commands & Extensions
        embed.add_field(
            name="⚙️ Commands & Extensions",
            value=f"**Prefix Commands:** {prefix_commands}\n"
                  f"**Slash Commands:** {slash_commands}\n"
                  f"**Loaded Cogs:** {loaded_cogs}",
            inline=True
        )

        # Versions
        embed.add_field(
            name="🔧 Versions",
            value=f"**Discord.py:** {dpy_version}\n"
                  f"**Python:** {python_version}",
            inline=True
        )

        # Bot-specific features
        embed.add_field(
            name="🎯 Bot Features",
            value=f"**Extensions:** {loaded_extensions}\n"
                  f"**Forms:** {forms_count}\n"
                  f"**Bot ID:** {self.bot.user.id}",
            inline=True
        )

        # Add bot avatar as thumbnail
        if self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)

        embed.set_footer(
            text=f"Requested by {ctx.author}",
            icon_url=ctx.author.avatar.url if ctx.author.avatar else None
        )

        await ctx.send(embed=embed)

    @commands.command(name='uptime')
    @commands.is_owner()
    async def show_uptime(self, ctx):
        """Display only bot uptime (Owner only)"""
        uptime = self.get_uptime()
        embed = discord.Embed(
            title="⏰ Bot Uptime",
            description=f"**{uptime}**",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        await ctx.send(embed=embed)

    @commands.command(name='ping')
    async def ping_command(self, ctx):
        """Check bot latency"""
        latency = round(self.bot.latency * 1000, 2)
        embed = discord.Embed(
            title="🏓 Pong!",
            description=f"Latency: **{latency}ms**",
            color=discord.Color.green() if latency < 100 else discord.Color.orange() if latency < 200 else discord.Color.red()
        )
        await ctx.send(embed=embed)

    @commands.command(name='extensions', aliases=['cogs'])
    @commands.is_owner()
    async def list_extensions(self, ctx):
        """List all loaded extensions and cogs"""
        embed = discord.Embed(
            title="📦 Loaded Extensions & Cogs",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )

        # List extensions
        extensions_list = "\n".join(self.bot.extensions.keys()) if self.bot.extensions else "None"
        embed.add_field(
            name=f"Extensions ({len(self.bot.extensions)})",
            value=f"```{extensions_list}```",
            inline=False
        )

        # List cogs
        cogs_list = "\n".join(self.bot.cogs.keys()) if self.bot.cogs else "None"
        embed.add_field(
            name=f"Cogs ({len(self.bot.cogs)})",
            value=f"```{cogs_list}```",
            inline=False
        )

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Stats(bot))
