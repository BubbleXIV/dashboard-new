import os
import json
import sqlite3
import discord
from discord.ext import commands
from discord import app_commands
import pickle

# Define the path to the database directory
DATABASE_DIR = './databases/'


class AdminCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def is_owner(self, interaction: discord.Interaction) -> bool:
        """Check if the user is the bot owner"""
        application = await self.bot.application_info()
        if interaction.user.id != application.owner.id:
            await interaction.response.send_message("Only the bot owner can use this command.", ephemeral=True)
            return False
        return True

    # Traditional commands
    @commands.command(name='cleardatabase', help='Clears the specified database file.')
    @commands.is_owner()
    async def clear_database(self, ctx, database_name: str):
        # Find the database file regardless of extension
        found_file = None
        for ext in ['.pkl', '.json', '.db']:
            test_file = os.path.join(DATABASE_DIR, f'{database_name}{ext}')
            if os.path.exists(test_file):
                found_file = test_file
                break

        if not found_file:
            await ctx.send(f"❌ No database found with the name `{database_name}`.")
            return

        # Clear the database based on its file type
        try:
            file_ext = os.path.splitext(found_file)[1].lower()
            if file_ext == '.pkl':
                await self._clear_pickle_db(found_file)
            elif file_ext == '.json':
                await self._clear_json_db(found_file)
            elif file_ext == '.db':
                await self._clear_sqlite_db(found_file)
            else:
                await ctx.send(f"❌ Unsupported file type: {file_ext}")
                return

            await ctx.send(f"✅ Successfully cleared database: `{database_name}{file_ext}`")
        except Exception as e:
            await ctx.send(f"❌ Error clearing database: {str(e)}")

    @commands.command(name='clearalldatabases', help='Clears all databases in the databases directory.')
    @commands.is_owner()
    async def clear_all_databases(self, ctx):
        if not os.path.exists(DATABASE_DIR):
            await ctx.send("❌ The databases directory does not exist.")
            return

        # Track results
        success = []
        errors = []

        # Process all database files
        for file_name in os.listdir(DATABASE_DIR):
            file_path = os.path.join(DATABASE_DIR, file_name)
            if not os.path.isfile(file_path):
                continue

            file_ext = os.path.splitext(file_name)[1].lower()
            db_name = os.path.splitext(file_name)[0]

            try:
                if file_ext == '.pkl':
                    await self._clear_pickle_db(file_path)
                elif file_ext == '.json':
                    await self._clear_json_db(file_path)
                elif file_ext == '.db':
                    await self._clear_sqlite_db(file_path)
                else:
                    # Skip non-database files
                    continue

                success.append(f"{db_name}{file_ext}")
            except Exception as e:
                errors.append(f"{db_name}{file_ext} ({str(e)})")

        # Send results
        message = []
        if success:
            message.append(f"✅ Successfully cleared {len(success)} databases: `{', '.join(success)}`")
        if errors:
            message.append(f"❌ Failed to clear {len(errors)} databases: `{', '.join(errors)}`")
        if not success and not errors:
            message.append("ℹ️ No database files found to clear.")

        await ctx.send("\n".join(message))

    @commands.command(name='listdatabases', help='Lists all databases in the databases directory.')
    @commands.is_owner()
    async def list_databases(self, ctx):
        if not os.path.exists(DATABASE_DIR):
            await ctx.send("❌ The databases directory does not exist.")
            return

        # Group files by type
        pkl_files = []
        json_files = []
        db_files = []
        other_files = []

        for file_name in os.listdir(DATABASE_DIR):
            file_path = os.path.join(DATABASE_DIR, file_name)
            if not os.path.isfile(file_path):
                continue

            file_ext = os.path.splitext(file_name)[1].lower()
            if file_ext == '.pkl':
                pkl_files.append(file_name)
            elif file_ext == '.json':
                json_files.append(file_name)
            elif file_ext == '.db':
                db_files.append(file_name)
            else:
                other_files.append(file_name)

        total_files = len(pkl_files) + len(json_files) + len(db_files) + len(other_files)
        if total_files == 0:
            await ctx.send("❌ No database files found.")
            return

        # Create an embed to display the databases
        embed = discord.Embed(
            title="📁 Database Files",
            description=f"Found {total_files} file(s) in the databases directory",
            color=discord.Color.blue()
        )

        # Add each type of database to the embed
        if pkl_files:
            embed.add_field(
                name=f"🗃️ Pickle Databases ({len(pkl_files)})",
                value="• " + "\n• ".join(pkl_files[:10]) +
                      ("\n• ..." if len(pkl_files) > 10 else ""),
                inline=False
            )

        if json_files:
            embed.add_field(
                name=f"📄 JSON Databases ({len(json_files)})",
                value="• " + "\n• ".join(json_files[:10]) +
                      ("\n• ..." if len(json_files) > 10 else ""),
                inline=False
            )

        if db_files:
            embed.add_field(
                name=f"💾 SQLite Databases ({len(db_files)})",
                value="• " + "\n• ".join(db_files[:10]) +
                      ("\n• ..." if len(db_files) > 10 else ""),
                inline=False
            )

        if other_files:
            embed.add_field(
                name=f"❓ Other Files ({len(other_files)})",
                value="• " + "\n• ".join(other_files[:10]) +
                      ("\n• ..." if len(other_files) > 10 else ""),
                inline=False
            )

        await ctx.send(embed=embed)

    @commands.command(name='inspectdatabase', help='Shows information about a specific database.')
    @commands.is_owner()
    async def inspect_database(self, ctx, database_name: str):
        # Find the database file regardless of extension
        found_file = None
        for ext in ['.pkl', '.json', '.db']:
            test_file = os.path.join(DATABASE_DIR, f'{database_name}{ext}')
            if os.path.exists(test_file):
                found_file = test_file
                break

        if not found_file:
            await ctx.send(f"❌ No database found with the name `{database_name}`.")
            return

        file_ext = os.path.splitext(found_file)[1].lower()
        file_size = os.path.getsize(found_file) / 1024  # Size in KB

        embed = discord.Embed(
            title=f"📊 Database: {database_name}{file_ext}",
            color=discord.Color.green()
        )

        embed.add_field(name="File Size", value=f"{file_size:.2f} KB", inline=True)
        embed.add_field(name="File Type", value=file_ext[1:].upper(), inline=True)

        try:
            if file_ext == '.pkl':
                with open(found_file, 'rb') as f:
                    data = pickle.load(f)
                await self._add_data_structure_to_embed(embed, data)
            elif file_ext == '.json':
                with open(found_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                await self._add_data_structure_to_embed(embed, data)
            elif file_ext == '.db':
                conn = sqlite3.connect(found_file)
                cursor = conn.cursor()

                # Get table count
                cursor.execute("SELECT count(*) FROM sqlite_master WHERE type='table';")
                table_count = cursor.fetchone()[0]
                embed.add_field(name="Tables", value=str(table_count), inline=True)

                # Get table names
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = cursor.fetchall()
                table_names = [table[0] for table in tables if table[0] != 'sqlite_sequence']

                if table_names:
                    embed.add_field(
                        name="Table Names",
                        value="`" + "`, `".join(table_names[:10]) + "`" +
                              (" (and more...)" if len(table_names) > 10 else ""),
                        inline=False
                    )

                # Get row counts for each table
                table_info = []
                for table in table_names[:5]:  # Limit to first 5 tables
                    cursor.execute(f"SELECT COUNT(*) FROM {table};")
                    row_count = cursor.fetchone()[0]
                    table_info.append(f"{table}: {row_count} rows")

                if table_info:
                    embed.add_field(
                        name="Table Statistics",
                        value="\n".join(table_info) +
                              ("\n..." if len(table_names) > 5 else ""),
                        inline=False
                    )

                conn.close()
        except Exception as e:
            embed.add_field(name="Error", value=f"Failed to inspect database content: {str(e)}", inline=False)

        await ctx.send(embed=embed)

    # Slash commands
    @app_commands.command(name="cleardatabase", description="Clears the specified database file")
    @app_commands.default_permissions(administrator=True)
    async def clear_database_slash(self, interaction: discord.Interaction, database_name: str):
        # Check if user is the bot owner
        if not await self.is_owner(interaction):
            return

        await interaction.response.defer(ephemeral=True)

        # Find the database file regardless of extension
        found_file = None
        for ext in ['.pkl', '.json', '.db']:
            test_file = os.path.join(DATABASE_DIR, f'{database_name}{ext}')
            if os.path.exists(test_file):
                found_file = test_file
                break

        if not found_file:
            await interaction.followup.send(f"❌ No database found with the name `{database_name}`.")
            return

        # Clear the database based on its file type
        try:
            file_ext = os.path.splitext(found_file)[1].lower()
            if file_ext == '.pkl':
                await self._clear_pickle_db(found_file)
            elif file_ext == '.json':
                await self._clear_json_db(found_file)
            elif file_ext == '.db':
                await self._clear_sqlite_db(found_file)
            else:
                await interaction.followup.send(f"❌ Unsupported file type: {file_ext}")
                return

            await interaction.followup.send(f"✅ Successfully cleared database: `{database_name}{file_ext}`")
        except Exception as e:
            await interaction.followup.send(f"❌ Error clearing database: {str(e)}")

    @app_commands.command(name="clearalldatabases", description="Clears all databases in the databases directory")
    @app_commands.default_permissions(administrator=True)
    async def clear_all_databases_slash(self, interaction: discord.Interaction):
        # Check if user is the bot owner
        if not await self.is_owner(interaction):
            return

        await interaction.response.defer(ephemeral=True)

        if not os.path.exists(DATABASE_DIR):
            await interaction.followup.send("❌ The databases directory does not exist.")
            return

        # Track results
        success = []
        errors = []

        # Process all database files
        for file_name in os.listdir(DATABASE_DIR):
            file_path = os.path.join(DATABASE_DIR, file_name)
            if not os.path.isfile(file_path):
                continue

            file_ext = os.path.splitext(file_name)[1].lower()
            db_name = os.path.splitext(file_name)[0]

            try:
                if file_ext == '.pkl':
                    await self._clear_pickle_db(file_path)
                elif file_ext == '.json':
                    await self._clear_json_db(file_path)
                elif file_ext == '.db':
                    await self._clear_sqlite_db(file_path)
                else:
                    # Skip non-database files
                    continue

                success.append(f"{db_name}{file_ext}")
            except Exception as e:
                errors.append(f"{db_name}{file_ext} ({str(e)})")

        # Send results
        message = []
        if success:
            message.append(f"✅ Successfully cleared {len(success)} databases: `{', '.join(success)}`")
        if errors:
            message.append(f"❌ Failed to clear {len(errors)} databases: `{', '.join(errors)}`")
        if not success and not errors:
            message.append("ℹ️ No database files found to clear.")

        await interaction.followup.send("\n".join(message))

    @app_commands.command(name="listdatabases", description="Lists all databases in the databases directory")
    @app_commands.default_permissions(administrator=True)
    async def list_databases_slash(self, interaction: discord.Interaction):
        # Check if user is the bot owner
        if not await self.is_owner(interaction):
            return

        await interaction.response.defer(ephemeral=True)

        if not os.path.exists(DATABASE_DIR):
            await interaction.followup.send("❌ The databases directory does not exist.")
            return

        # Group files by type
        pkl_files = []
        json_files = []
        db_files = []
        other_files = []

        for file_name in os.listdir(DATABASE_DIR):
            file_path = os.path.join(DATABASE_DIR, file_name)
            if not os.path.isfile(file_path):
                continue

            file_ext = os.path.splitext(file_name)[1].lower()
            if file_ext == '.pkl':
                pkl_files.append(file_name)
            elif file_ext == '.json':
                json_files.append(file_name)
            elif file_ext == '.db':
                db_files.append(file_name)
            else:
                other_files.append(file_name)

        total_files = len(pkl_files) + len(json_files) + len(db_files) + len(other_files)
        if total_files == 0:
            await interaction.followup.send("❌ No database files found.")
            return

        # Create an embed to display the databases
        embed = discord.Embed(
            title="📁 Database Files",
            description=f"Found {total_files} file(s) in the databases directory",
            color=discord.Color.blue()
        )

        # Add each type of database to the embed
        if pkl_files:
            embed.add_field(
                name=f"🗃️ Pickle Databases ({len(pkl_files)})",
                value="• " + "\n• ".join(pkl_files[:10]) +
                      ("\n• ..." if len(pkl_files) > 10 else ""),
                inline=False
            )

        if json_files:
            embed.add_field(
                name=f"📄 JSON Databases ({len(json_files)})",
                value="• " + "\n• ".join(json_files[:10]) +
                      ("\n• ..." if len(json_files) > 10 else ""),
                inline=False
            )

        if db_files:
            embed.add_field(
                name=f"💾 SQLite Databases ({len(db_files)})",
                value="• " + "\n• ".join(db_files[:10]) +
                      ("\n• ..." if len(db_files) > 10 else ""),
                inline=False
            )

        if other_files:
            embed.add_field(
                name=f"❓ Other Files ({len(other_files)})",
                value="• " + "\n• ".join(other_files[:10]) +
                      ("\n• ..." if len(other_files) > 10 else ""),
                inline=False
            )

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="inspectdatabase", description="Shows information about a specific database")
    @app_commands.default_permissions(administrator=True)
    async def inspect_database_slash(self, interaction: discord.Interaction, database_name: str):
        # Check if user is the bot owner
        if not await self.is_owner(interaction):
            return

        await interaction.response.defer(ephemeral=True)

        # Find the database file regardless of extension
        found_file = None
        for ext in ['.pkl', '.json', '.db']:
            test_file = os.path.join(DATABASE_DIR, f'{database_name}{ext}')
            if os.path.exists(test_file):
                found_file = test_file
                break

        if not found_file:
            await interaction.followup.send(f"❌ No database found with the name `{database_name}`.")
            return

        file_ext = os.path.splitext(found_file)[1].lower()
        file_size = os.path.getsize(found_file) / 1024  # Size in KB

        embed = discord.Embed(
            title=f"📊 Database: {database_name}{file_ext}",
            color=discord.Color.green()
        )

        embed.add_field(name="File Size", value=f"{file_size:.2f} KB", inline=True)
        embed.add_field(name="File Type", value=file_ext[1:].upper(), inline=True)

        try:
            if file_ext == '.pkl':
                with open(found_file, 'rb') as f:
                    data = pickle.load(f)
                await self._add_data_structure_to_embed(embed, data)
            elif file_ext == '.json':
                with open(found_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                await self._add_data_structure_to_embed(embed, data)
            elif file_ext == '.db':
                conn = sqlite3.connect(found_file)
                cursor = conn.cursor()

                # Get table count
                cursor.execute("SELECT count(*) FROM sqlite_master WHERE type='table';")
                table_count = cursor.fetchone()[0]
                embed.add_field(name="Tables", value=str(table_count), inline=True)

                # Get table names
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = cursor.fetchall()
                table_names = [table[0] for table in tables if table[0] != 'sqlite_sequence']

                if table_names:
                    embed.add_field(
                        name="Table Names",
                        value="`" + "`, `".join(table_names[:10]) + "`" +
                              (" (and more...)" if len(table_names) > 10 else ""),
                        inline=False
                    )

                # Get row counts for each table
                table_info = []
                for table in table_names[:5]:  # Limit to first 5 tables
                    cursor.execute(f"SELECT COUNT(*) FROM {table};")
                    row_count = cursor.fetchone()[0]
                    table_info.append(f"{table}: {row_count} rows")

                if table_info:
                    embed.add_field(
                        name="Table Statistics",
                        value="\n".join(table_info) +
                              ("\n..." if len(table_names) > 5 else ""),
                        inline=False
                    )

                conn.close()
        except Exception as e:
            embed.add_field(name="Error", value=f"Failed to inspect database content: {str(e)}", inline=False)

        await interaction.followup.send(embed=embed)

    # Helper methods for clearing different database types
    async def _clear_pickle_db(self, file_path):
        """Clear a pickle database while preserving structure"""
        try:
            with open(file_path, 'rb') as f:
                data = pickle.load(f)

            # Clear the data while preserving structure
            if isinstance(data, dict):
                data.clear()
            elif isinstance(data, list):
                data.clear()
            elif hasattr(data, '__dict__'):
                for attr in list(data.__dict__.keys()):
                    if isinstance(data.__dict__[attr], (dict, list)):
                        data.__dict__[attr].clear()
                    else:
                        data.__dict__[attr] = None
            else:
                data = {}

            # Save the cleared data
            with open(file_path, 'wb') as f:
                pickle.dump(data, f)
        except Exception:
            # If structure preservation fails, reset to empty dict
            with open(file_path, 'wb') as f:
                pickle.dump({}, f)

    async def _clear_json_db(self, file_path):
        """Clear a JSON database while preserving structure"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Clear the data while preserving structure
            if isinstance(data, dict):
                data.clear()
            elif isinstance(data, list):
                data.clear()
            else:
                data = {}

            # Save the cleared data
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception:
            # If structure preservation fails, reset to empty dict
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump({}, f, indent=2)

    async def _clear_sqlite_db(self, file_path):
        """Clear all tables in a SQLite database while preserving schema"""
        conn = None
        try:
            conn = sqlite3.connect(file_path)
            cursor = conn.cursor()

            # Get all tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()

            # Delete data from each table but keep the table structure
            for table in tables:
                table_name = table[0]
                if table_name != 'sqlite_sequence':  # Skip internal SQLite tables
                    cursor.execute(f"DELETE FROM {table_name};")

            conn.commit()
        except Exception as e:
            raise Exception(f"SQLite error: {str(e)}")
        finally:
            if conn:
                conn.close()

    async def _add_data_structure_to_embed(self, embed, data):
        """Add data structure information to an embed"""
        if isinstance(data, dict):
            embed.add_field(name="Structure", value="Dictionary", inline=True)
            embed.add_field(name="Entry Count", value=str(len(data)), inline=True)

            # Show some keys as examples
            if data:
                keys = list(data.keys())
                sample = keys[:5] if len(keys) > 5 else keys
                embed.add_field(
                    name="Sample Keys",
                    value="`" + "`, `".join(str(k)[:50] for k in sample) + "`" +
                          (" (and more...)" if len(keys) > 5 else ""),
                    inline=False
                )
        elif isinstance(data, list):
            embed.add_field(name="Structure", value="List", inline=True)
            embed.add_field(name="Item Count", value=str(len(data)), inline=True)

            # Show some items as examples
            if data:
                sample = data[:5] if len(data) > 5 else data
                sample_str = []
                for item in sample:
                    if isinstance(item, (dict, list)):
                        item_type = type(item).__name__
                        item_len = len(item)
                        sample_str.append(f"{item_type}({item_len})")
                    else:
                        sample_str.append(str(item)[:50])

                embed.add_field(
                    name="Sample Items",
                    value="`" + "`, `".join(sample_str) + "`" +
                          (" (and more...)" if len(data) > 5 else ""),
                    inline=False
                )
        elif hasattr(data, '__dict__'):
            embed.add_field(name="Structure", value="Object", inline=True)
            attrs = list(data.__dict__.keys())
            embed.add_field(name="Attribute Count", value=str(len(attrs)), inline=True)

            # Show attributes
            if attrs:
                embed.add_field(
                    name="Attributes",
                    value="`" + "`, `".join(attrs[:10]) + "`" +
                          (" (and more...)" if len(attrs) > 10 else ""),
                    inline=False
                )
        else:
            embed.add_field(name="Structure", value=f"Other ({type(data).__name__})", inline=True)


async def setup(bot):
    await bot.add_cog(AdminCommands(bot))

