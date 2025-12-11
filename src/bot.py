import discord
print(">>> BOT.PY VERSION: 2024-12-11-v4-AUTO-CREATE <<<", flush=True)
from discord.ext import commands
from typing import Optional
import asyncio
import os
from config.config import Config, Role
from db.redis_client import RedisClient
from ai.anthropic_client import AnthropicClient
from ai.openai_client import OpenAIClient
from ai.google_client import GoogleAIClient
from ai.flux_client import FluxClient
from ai.fluxpro_client import FluxProClient
from ai.recraft_client import ReCraftClient
from games.countdown import CountdownGame
from games.solver import CountdownSolver
from utils.helpers import send_chunked_message
import io
import aiohttp
from aiohttp import web
import traceback
import json


class CalculatorView(discord.ui.View):
    def __init__(self, bot, game, user_id):
        super().__init__(timeout=180)
        self.bot = bot
        self.game = game
        self.user_id = user_id
        self.expression = ""
        self.used_indices = set()
        
        # Add buttons
        self._init_buttons()

    def _init_buttons(self):
        self.clear_items()

        # Row 0: Numbers 1-3
        for i in range(min(3, len(self.game.numbers))):
            num = self.game.numbers[i]
            used = i in self.used_indices
            self.add_item(NumberButton(num, i, used, row=0))

        # Row 1: Numbers 4-6
        for i in range(3, min(6, len(self.game.numbers))):
            num = self.game.numbers[i]
            used = i in self.used_indices
            self.add_item(NumberButton(num, i, used, row=1))

        # Row 2: Basic Operators
        operators = [("+", "+"), ("−", "-"), ("×", "*"), ("÷", "/")]
        for label, op in operators:
            self.add_item(OperatorButton(label, op, row=2))

        # Row 3: Parentheses and Clear
        self.add_item(OperatorButton("(", "(", row=3))
        self.add_item(OperatorButton(")", ")", row=3))
        self.add_item(ActionButton("CLR", "clear", discord.ButtonStyle.danger, row=3))

        # Row 4: Submit (Full width handled by Discord UI automatically if alone, but we'll see)
        self.add_item(ActionButton("✓  SUBMIT ANSWER", "submit", discord.ButtonStyle.success, row=4))

    async def update_view(self, interaction: discord.Interaction):
        self._init_buttons()
        # Update the embed to show current expression
        embed = self.bot._create_calculator_embed(self.game, self.expression)
        await interaction.response.edit_message(embed=embed, view=self)

class NumberButton(discord.ui.Button):
    def __init__(self, number, index, used=False, row=0):
        super().__init__(
            label=str(number),
            # Use secondary (gray) for numbers to look like keypad keys
            style=discord.ButtonStyle.secondary,
            disabled=used,
            row=row
        )
        self.number = number
        self.index = index

    async def callback(self, interaction: discord.Interaction):
        view: CalculatorView = self.view
        view.expression += str(self.number)
        view.used_indices.add(self.index)
        await view.update_view(interaction)


class OperatorButton(discord.ui.Button):
    def __init__(self, label, operator, row=0):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.primary, # Blurple for operators
            row=row
        )
        self.operator = operator

    async def callback(self, interaction: discord.Interaction):
        view: CalculatorView = self.view
        # Add spacing for readability, except parentheses
        if self.operator in "()":
            view.expression += self.operator
        else:
            view.expression += f" {self.operator} "
        await view.update_view(interaction)

class ActionButton(discord.ui.Button):
    def __init__(self, label, action, style, row=0):
        super().__init__(label=label, style=style, row=row)
        self.action = action

    async def callback(self, interaction: discord.Interaction):
        view: CalculatorView = self.view
        
        if self.action == "clear":
            view.expression = ""
            view.used_indices.clear()
            await view.update_view(interaction)

        elif self.action == "submit":
            server_id = str(interaction.guild_id)
            channel_id = str(interaction.channel_id)
            user_id = str(interaction.user.id)

            try:
                submission = view.bot.countdown_game.submit_answer(
                    server_id, channel_id, user_id, view.expression
                )

                if submission.valid:
                    if submission.distance == 0:
                        # Perfect match
                        embed = discord.Embed(
                            title="🎯  EXACT MATCH!",
                            description=f"You solved it! **{submission.result}**\n```{view.expression}```",
                            color=0xF1C40F  # Gold
                        )
                    else:
                        # Good submission
                        embed = discord.Embed(
                            title="✅  Answer Submitted",
                            description=f"Result: **{submission.result}** ({submission.distance} away)\n```{view.expression}```",
                            color=0x57F287  # Green
                        )
                    
                    # Update the private view to show success
                    await interaction.response.edit_message(embed=embed, view=None)

                else:
                    await interaction.response.send_message(f"❌ **Invalid:** {submission.error}", ephemeral=True)

            except ValueError as e:
                await interaction.response.send_message(str(e), ephemeral=True)

class CountdownView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="🎮  Play Now / Open Calculator", style=discord.ButtonStyle.success)
    async def play_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        server_id = str(interaction.guild_id)
        channel_id = str(interaction.channel_id)

        game = self.bot.countdown_game.get_active_game(server_id, channel_id)
        if not game:
            await interaction.response.send_message("Game has ended!", ephemeral=True)
            return

        # Create ephemeral unified calculator for this user
        view = CalculatorView(self.bot, game, interaction.user.id)
        embed = self.bot._create_calculator_embed(game, "")
        
        await interaction.response.send_message(
            embed=embed,
            view=view,
            ephemeral=True
        )


class RoundsSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="1 Round", value="1"),
            discord.SelectOption(label="2 Rounds", value="2"),
            discord.SelectOption(label="3 Rounds", value="3", default=True),
            discord.SelectOption(label="4 Rounds", value="4"),
            discord.SelectOption(label="5 Rounds", value="5"),
        ]
        super().__init__(placeholder="Select rounds...", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        view: CountdownSettingsView = self.view
        view.rounds = int(self.values[0])
        await view.update_lobby_embed(interaction)


class TimeSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="30 seconds", value="30"),
            discord.SelectOption(label="60 seconds", value="60", default=True),
            discord.SelectOption(label="120 seconds", value="120"),
        ]
        super().__init__(placeholder="Select time per round...", options=options, row=1)

    async def callback(self, interaction: discord.Interaction):
        view: CountdownSettingsView = self.view
        view.seconds_per_round = int(self.values[0])
        await view.update_lobby_embed(interaction)


class CountdownSettingsView(discord.ui.View):
    def __init__(self, bot, lobby, host):
        super().__init__(timeout=300)  # 5 minute timeout for lobby
        self.bot = bot
        self.lobby = lobby
        self.host = host
        self.rounds = lobby.rounds
        self.seconds_per_round = lobby.seconds_per_round

        # Add select menus
        self.add_item(RoundsSelect())
        self.add_item(TimeSelect())

    @discord.ui.button(label="Ready", style=discord.ButtonStyle.success, emoji="✅", row=2)
    async def ready_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        server_id = str(interaction.guild_id)
        channel_id = str(interaction.channel_id)
        user_id = str(interaction.user.id)

        try:
            self.lobby = self.bot.countdown_game.toggle_ready(server_id, channel_id, user_id)
            await self.update_lobby_embed(interaction)
        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)

    @discord.ui.button(label="Start Game", style=discord.ButtonStyle.primary, emoji="▶️", row=2)
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Only host can start
        if str(interaction.user.id) != self.lobby.host_id:
            await interaction.response.send_message("Only the host can start the game!", ephemeral=True)
            return

        server_id = str(interaction.guild_id)
        channel_id = str(interaction.channel_id)

        # Update lobby with current settings before starting
        self.lobby.rounds = self.rounds
        self.lobby.seconds_per_round = self.seconds_per_round
        self.bot.countdown_game.update_lobby(server_id, channel_id, self.lobby)

        # Create the game from lobby
        game = self.bot.countdown_game.create_game_from_lobby(self.lobby)

        # Create game embed
        embed = self.bot._create_countdown_embed(game, interaction.user)
        view = CountdownView(self.bot, server_id, channel_id)

        # Update the message with game board
        await interaction.response.edit_message(embed=embed, view=view)

        # Store message for timer updates
        message = await interaction.original_response()
        game.message_id = str(message.id)
        self.bot.countdown_game._save_game(server_id, channel_id, game)

        # Start the timer with live updates
        asyncio.create_task(
            self.bot._countdown_timer_with_updates(interaction, server_id, channel_id, message, game)
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, emoji="❌", row=2)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Only host can cancel
        if str(interaction.user.id) != self.lobby.host_id:
            await interaction.response.send_message("Only the host can cancel the lobby!", ephemeral=True)
            return

        server_id = str(interaction.guild_id)
        channel_id = str(interaction.channel_id)

        self.bot.countdown_game.delete_lobby(server_id, channel_id)
        await interaction.response.edit_message(
            content="Lobby cancelled.",
            embed=None,
            view=None
        )
        self.stop()

    async def update_lobby_embed(self, interaction: discord.Interaction):
        embed = self.bot._create_lobby_embed(self.lobby, self.host, self.rounds, self.seconds_per_round)
        await interaction.response.edit_message(embed=embed, view=self)


class AIBot(commands.Bot):
    def __init__(self, config: Config):
        # Set up intents explicitly
        intents = discord.Intents.default()
        intents.message_content = True  # Needed to read message content
        intents.members = True         # Needed for member-related features
        intents.guilds = True          # Needed for guild-related features
        intents.guild_messages = True  # Needed for messages in guilds

        super().__init__(command_prefix="!", intents=intents)
        print("Initializing AIBot...", flush=True)
        self.config = config
        self.redis_client = RedisClient(config.redis_host, config.redis_port)
        self.owner_id = int(config.owner_id)
        
        # Initialize AI clients
        self.ai_clients = {
            "claude": AnthropicClient(config.anthropic_api_key),
            "gpt4": OpenAIClient(config.openai_api_key),
            "gemini": GoogleAIClient(config.google_api_key),
            # Image generation clients
            "flux": FluxClient(config.replicate_api_token),
            "fluxpro": FluxProClient(config.replicate_api_token),
            "recraft": ReCraftClient(config.replicate_api_token)
        }

        # Initialize games
        self.countdown_game = CountdownGame(self.redis_client)
        self.solver = CountdownSolver()

        # Path to assets
        self.assets_path = os.path.join(os.path.dirname(__file__), 'assets')

        # Command handlers dictionary
        self.command_handlers = {
            'addchan': self._handle_add_channel,
            'mute': self._handle_mute_channel,
            'listchans': self._handle_list_channels,
            'clearchans': self._handle_clear_channels,
            'setmodel': self._handle_set_model,
            'setrole': self._handle_set_role,
            'setdefaultmodel': self._handle_set_default_model,
            'setdefaultrole': self._handle_set_default_role,
            'listroles': self._handle_list_roles,
            'listmodels': self._handle_list_models,
            'channelconfig': self._handle_channel_config,
            'clearchannelconfig': self._handle_clear_channel_config,
            'status': self._handle_status,
            'shutdown': self._handle_shutdown,
            'listservers': self._handle_list_servers,
            'leaveserver': self._handle_leave_server,
            # Image generation commands
            'flux': lambda ctx, prompt: self._handle_image_generation(ctx, prompt, "flux"),
            'fluxpro': lambda ctx, prompt: self._handle_image_generation(ctx, prompt, "fluxpro"),
            'recraft': lambda ctx, prompt: self._handle_image_generation(ctx, prompt, "recraft"),
            # Game commands
            'countdown': self._handle_countdown,
            'numbers': self._handle_countdown,  # alias
            'answer': self._handle_answer,
            'solve': self._handle_answer,  # alias
            'leaderboard': self._handle_leaderboard
        }
        print("AIBot initialization complete.", flush=True)

    async def setup_hook(self):
        """This is called when the bot is ready to start"""
        self._setup_hook_ran = True
        print("Executing setup_hook...", flush=True)
        self.add_commands()
        self._setup_slash_commands()
        
        # Custom sync to handle Type 4 Entry Point command
        print("Calling custom_sync from setup_hook...", flush=True)
        await self.custom_sync()
        
        # Start web server for Activity API
        print("Starting web server task from setup_hook...", flush=True)
        self.bg_task = asyncio.create_task(self.start_web_server())

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})", flush=True)
        print("------", flush=True)
        
        # Debug: Fetch current global commands to identify the conflict
        try:
             url = f"https://discord.com/api/v10/applications/{self.user.id}/commands"
             headers = {"Authorization": f"Bot {self.config.discord_token}"}
             async with aiohttp.ClientSession() as session:
                 async with session.get(url, headers=headers) as resp:
                     if resp.status == 200:
                         commands = await resp.json()
                         print("CURRENT GLOBAL COMMANDS:", flush=True)
                         for cmd in commands:
                             print(f"- {cmd['name']} (ID: {cmd['id']}) (Type: {cmd.get('type', 1)})", flush=True)
                     else:
                         print(f"Failed to fetch commands: {resp.status} {await resp.text()}", flush=True)
        except Exception as e:
             print(f"Error fetching commands: {e}", flush=True)

        # Fallback sync if setup_hook didn't run for some reason
        if not hasattr(self, '_setup_hook_ran'):
             print("Warning: setup_hook did not run! Syncing tree from on_ready...", flush=True)
             try:
                 await self.tree.sync()
                 print("Command tree synced from on_ready.", flush=True)
             except Exception as e:
                 print(f"Failed to sync tree from on_ready: {e}", flush=True)

        if not hasattr(self, '_custom_sync_ran'):
             print("Invoking custom_sync from on_ready (fallback)...", flush=True)
             await self.custom_sync()

        # Web server is started in setup_hook. No need to start it here again.
        if not hasattr(self, 'bg_task') or self.bg_task.done():
              print("Ensuring web server is running from on_ready...", flush=True)
              self.bg_task = asyncio.create_task(self.start_web_server())

    async def custom_sync(self):
        """Manual sync to include Type 4 Entry Point command"""
        self._custom_sync_ran = True
        print("Executing custom command sync...", flush=True)
        url = f"https://discord.com/api/v10/applications/{self.user.id}/commands"
        headers = {"Authorization": f"Bot {self.config.discord_token}"}
        
        # Hardcoded payload to match existing Entry Point command
        payload = [
          {
            "name": "launch",
            "description": "Launch an activity",
            "type": 4, # Primary Entry Point
            "contexts": [0, 1, 2],
            "integration_types": [0, 1],
            "handler": 2
          }
        ]
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.put(url, headers=headers, json=payload) as resp:
                    if resp.status in (200, 201):
                        print("Custom sync successful (Type 4 command registered).", flush=True)
                    else:
                        print(f"Custom sync failed: {resp.status} {await resp.text()}", flush=True)
        except Exception as e:
            print(f"Custom sync error: {e}", flush=True)

    async def on_interaction(self, interaction: discord.Interaction):
        """Handle interactions, specifically Type 4 Entry Point"""
        # Type 4 is NOT in discord.InteractionType enum usually, check raw value if needed
        # But discord.py might populate it as 'unknown' or value 4
        # We'll check if it's the launch command
        
        if interaction.type.value == 4 or (interaction.data and interaction.data.get('name') == 'launch'):
            print(f"Received Entry Point interaction: {interaction.data}", flush=True)
            await self._launch_game(interaction)
            return

        pass


    async def has_permissions(self, ctx) -> bool:
        """Check if user has required permissions (admin, moderator, or bot owner)"""
        return (
            ctx.author.id == self.owner_id or
            (ctx.guild and (
                ctx.author.guild_permissions.administrator or
                ctx.author.guild_permissions.moderate_members
            ))
        )

    def _setup_slash_commands(self):
        """Register slash commands - kept for local reference but not synced via tree"""
        # We don't really need to add it to tree if we handle it in on_interaction, 
        # but good to keep it for structure.
        pass

    async def _launch_game(self, interaction: discord.Interaction):
        """Reusable game launch logic - now just directs to Activity"""
        # Since we are moving lobby logic to the Activity itself, checking for active games here is less critical,
        # but we can still inform them if one is running.
        
        server_id = str(interaction.guild_id)
        # channel_id = str(interaction.channel_id)
        
        # We don't create a python-side lobby anymore.
        # We just want them to open the Activity.
        
        embed = discord.Embed(
            title="🔢 Numbers Game",
            description=(
                "**How to Play:**\n"
                "1. Click the **Rocketship 🚀** icon (Activities) in the chat bar.\n"
                "2. Select **Numbers Game**.\n"
                "3. Configure settings and start the game inside the activity!\n\n"
                "*All game setup is now handled directly in the game window.*"
            ),
            color=0x5865F2
        )
        await interaction.response.send_message(embed=embed)


    def add_commands(self):
        """Register commands using the command handlers dictionary"""
        for cmd_name, handler in self.command_handlers.items():
            @self.command(name=cmd_name)
            async def command_wrapper(ctx, *, arg=None, cmd=cmd_name, h=handler):
                if arg is None:
                    await h(ctx)
                else:
                    await h(ctx, arg)

    async def _handle_add_channel(self, ctx, channel_arg=None):
        """Handle the addchan command - adds channel to allowed channels"""
        if not await self.has_permissions(ctx):
            await ctx.send("You need administrator permissions or need to be the bot owner to use this command.")
            return

        server_id = str(ctx.guild.id)

        # Migrate old single-channel data if exists
        self.redis_client.migrate_single_to_multi_channel(server_id)

        # Determine which channel to add
        if channel_arg:
            # User specified a channel (format: #channel-name or channel_id)
            # Try to parse channel mention or ID
            channel_id = channel_arg.strip('<>#')
            try:
                # Check if it's a valid channel in the guild
                channel = ctx.guild.get_channel(int(channel_id))
                if not channel:
                    await ctx.send(f"Channel not found. Please provide a valid channel mention or ID.")
                    return
                channel_id = str(channel.id)
            except ValueError:
                await ctx.send(f"Invalid channel format. Use #channel-name or channel ID.")
                return
        else:
            # No argument provided, add current channel
            channel_id = str(ctx.channel.id)

        # Add channel to allowed channels
        self.redis_client.add_allowed_channel(server_id, channel_id)
        await ctx.send(f"AI bot will now respond in <#{channel_id}>.")

    async def _handle_mute_channel(self, ctx, channel_arg=None):
        """Handle the mute command - removes channel from allowed channels"""
        if not await self.has_permissions(ctx):
            await ctx.send("You need administrator permissions or need to be the bot owner to use this command.")
            return

        server_id = str(ctx.guild.id)

        # Migrate old single-channel data if exists
        self.redis_client.migrate_single_to_multi_channel(server_id)

        # Determine which channel to mute
        if channel_arg:
            # User specified a channel (format: #channel-name or channel_id)
            # Try to parse channel mention or ID
            channel_id = channel_arg.strip('<>#')
            try:
                # Check if it's a valid channel in the guild
                channel = ctx.guild.get_channel(int(channel_id))
                if not channel:
                    await ctx.send(f"Channel not found. Please provide a valid channel mention or ID.")
                    return
                channel_id = str(channel.id)
            except ValueError:
                await ctx.send(f"Invalid channel format. Use #channel-name or channel ID.")
                return
        else:
            # No argument provided, mute current channel
            channel_id = str(ctx.channel.id)

        # Remove channel from allowed channels
        self.redis_client.remove_allowed_channel(server_id, channel_id)
        await ctx.send(f"AI bot will no longer respond in <#{channel_id}>.")

    async def _handle_list_channels(self, ctx):
        """Handle the listchans command - lists all allowed channels"""
        if not await self.has_permissions(ctx):
            await ctx.send("You need administrator permissions or need to be the bot owner to use this command.")
            return

        server_id = str(ctx.guild.id)

        # Migrate old single-channel data if exists
        self.redis_client.migrate_single_to_multi_channel(server_id)

        allowed_channels = self.redis_client.get_allowed_channels(server_id)

        if not allowed_channels:
            await ctx.send("No channels are currently configured. Use !addchan to add channels.")
            return

        channel_mentions = [f"<#{channel_id}>" for channel_id in allowed_channels]
        await ctx.send(f"Allowed channels:\n" + "\n".join(f"- {mention}" for mention in channel_mentions))

    async def _handle_clear_channels(self, ctx):
        """Handle the clearchans command - removes all allowed channels"""
        if not await self.has_permissions(ctx):
            await ctx.send("You need administrator permissions or need to be the bot owner to use this command.")
            return

        server_id = str(ctx.guild.id)
        self.redis_client.clear_allowed_channels(server_id)
        await ctx.send("All allowed channels have been cleared. Bot will not respond in any channel until channels are added with !addchan.")

    async def _handle_set_model(self, ctx, args=None):
        """Handle the setmodel command - supports optional channel parameter
        Usage: !setmodel <model> [#channel]
        """
        if not await self.has_permissions(ctx):
            await ctx.send("You need administrator permissions or need to be the bot owner to use this command.")
            return

        if args is None:
            await ctx.send(f"Please specify a model. Available models: {', '.join(self.ai_clients.keys())}")
            return

        # Parse arguments: model and optional channel
        parts = args.split()
        if len(parts) == 0:
            await ctx.send(f"Please specify a model. Available models: {', '.join(self.ai_clients.keys())}")
            return

        model = parts[0]
        target_channel = None

        # Check if model is valid
        if model not in self.ai_clients:
            await ctx.send(f"Invalid model. Available models: {', '.join(self.ai_clients.keys())}")
            return

        # Check if channel was specified
        if len(parts) > 1:
            # User specified a channel (format: #channel-name or channel_id)
            channel_arg = parts[1].strip('<>#')
            try:
                # Check if it's a valid channel in the guild
                target_channel = ctx.guild.get_channel(int(channel_arg))
                if not target_channel:
                    await ctx.send(f"Channel not found. Please provide a valid channel mention or ID.")
                    return
            except ValueError:
                await ctx.send(f"Invalid channel format. Use #channel-name or channel ID.")
                return
        else:
            # No channel specified, use current channel
            target_channel = ctx.channel

        server_id = str(ctx.guild.id)
        channel_id = str(target_channel.id)

        # Set channel-specific model
        self.redis_client.set_channel_model(server_id, channel_id, model)
        await ctx.send(f"AI model set to **{model}** for <#{channel_id}>")

    async def _handle_set_role(self, ctx, args=None):
        """Handle the setrole command - supports optional channel parameter
        Usage: !setrole <role> [#channel]
        """
        if not await self.has_permissions(ctx):
            await ctx.send("You need administrator permissions or need to be the bot owner to use this command.")
            return

        if args is None:
            await ctx.send(f"Please specify a role. Available roles: {', '.join(self.config.roles.keys())}")
            return

        # Parse arguments: role and optional channel
        parts = args.split()
        if len(parts) == 0:
            await ctx.send(f"Please specify a role. Available roles: {', '.join(self.config.roles.keys())}")
            return

        role = parts[0]
        target_channel = None

        # Check if role is valid
        if role not in self.config.roles:
            await ctx.send(f"Invalid role. Available roles: {', '.join(self.config.roles.keys())}")
            return

        # Check if channel was specified
        if len(parts) > 1:
            # User specified a channel (format: #channel-name or channel_id)
            channel_arg = parts[1].strip('<>#')
            try:
                # Check if it's a valid channel in the guild
                target_channel = ctx.guild.get_channel(int(channel_arg))
                if not target_channel:
                    await ctx.send(f"Channel not found. Please provide a valid channel mention or ID.")
                    return
            except ValueError:
                await ctx.send(f"Invalid channel format. Use #channel-name or channel ID.")
                return
        else:
            # No channel specified, use current channel
            target_channel = ctx.channel

        server_id = str(ctx.guild.id)
        channel_id = str(target_channel.id)

        # Set channel-specific role
        self.redis_client.set_channel_role(server_id, channel_id, role)
        await ctx.send(f"AI role set to **{role}** for <#{channel_id}>")

    async def _handle_list_roles(self, ctx):
        """Handle the listroles command"""
        roles_info = "\n".join([
            f"**{role_id}**: {role.description}"
            for role_id, role in self.config.roles.items()
        ])
        await ctx.send(f"Available roles:\n{roles_info}")

    async def _handle_list_models(self, ctx):
        """Handle the listmodels command"""
        models_info = ", ".join(self.ai_clients.keys())
        await ctx.send(f"Available models: {models_info}")

    async def _handle_set_default_model(self, ctx, model=None):
        """Handle the setdefaultmodel command - sets server-wide default model
        Usage: !setdefaultmodel <model>
        """
        if not await self.has_permissions(ctx):
            await ctx.send("You need administrator, moderator, or bot owner permissions to use this command.")
            return

        if model is None:
            await ctx.send(f"Please specify a model. Available models: {', '.join(self.ai_clients.keys())}\nUsage: !setdefaultmodel <model>")
            return

        if model not in self.ai_clients:
            await ctx.send(f"Invalid model. Available models: {', '.join(self.ai_clients.keys())}")
            return

        server_id = str(ctx.guild.id)
        self.redis_client.set_default_model(server_id, model)
        await ctx.send(f"Server default AI model set to **{model}**. Channels without specific model settings will use this model.")

    async def _handle_set_default_role(self, ctx, role=None):
        """Handle the setdefaultrole command - sets server-wide default role
        Usage: !setdefaultrole <role>
        """
        if not await self.has_permissions(ctx):
            await ctx.send("You need administrator, moderator, or bot owner permissions to use this command.")
            return

        if role is None:
            await ctx.send(f"Please specify a role. Available roles: {', '.join(self.config.roles.keys())}\nUsage: !setdefaultrole <role>")
            return

        if role not in self.config.roles:
            await ctx.send(f"Invalid role. Available roles: {', '.join(self.config.roles.keys())}")
            return

        server_id = str(ctx.guild.id)
        self.redis_client.set_default_role(server_id, role)
        await ctx.send(f"Server default AI role set to **{role}**. Channels without specific role settings will use this role.")

    async def _handle_channel_config(self, ctx, args=None):
        """Handle the channelconfig command - show channel-specific configuration
        Usage: !channelconfig [#channel]
        """
        server_id = str(ctx.guild.id)
        target_channel = None

        # Parse optional channel argument
        if args:
            channel_arg = args.strip().split()[0].strip('<>#')
            try:
                target_channel = ctx.guild.get_channel(int(channel_arg))
                if not target_channel:
                    await ctx.send(f"Channel not found. Please provide a valid channel mention or ID.")
                    return
            except ValueError:
                await ctx.send(f"Invalid channel format. Use #channel-name or channel ID.")
                return
        else:
            # No channel specified, use current channel
            target_channel = ctx.channel

        channel_id = str(target_channel.id)

        # Get channel-specific and server-wide settings
        channel_role_raw = self.redis_client.redis.get(f"channel_role:{server_id}:{channel_id}")
        server_role_raw = self.redis_client.redis.get(f"role:{server_id}")
        effective_role = self.redis_client.get_channel_role(server_id, channel_id)

        channel_model_raw = self.redis_client.redis.get(f"channel_model:{server_id}:{channel_id}")
        server_model_raw = self.redis_client.redis.get(f"model:{server_id}")
        effective_model = self.redis_client.get_channel_model(server_id, channel_id)

        # Determine role source
        if channel_role_raw:
            role_source = "channel-specific"
        elif server_role_raw:
            role_source = "server-wide fallback"
        else:
            role_source = "default fallback"

        # Determine model source
        if channel_model_raw:
            model_source = "channel-specific"
        elif server_model_raw:
            model_source = "server-wide fallback"
        else:
            model_source = "default fallback"

        config_message = (
            f"**Configuration for <#{channel_id}>:**\n"
            f"• **Role:** {effective_role} ({role_source})\n"
            f"• **Model:** {effective_model} ({model_source})"
        )
        await ctx.send(config_message)

    async def _handle_clear_channel_config(self, ctx, args=None):
        """Handle the clearchannelconfig command - clear channel-specific settings
        Usage: !clearchannelconfig [#channel]
        """
        if not await self.has_permissions(ctx):
            await ctx.send("You need administrator permissions or need to be the bot owner to use this command.")
            return

        server_id = str(ctx.guild.id)
        target_channel = None

        # Parse optional channel argument
        if args:
            channel_arg = args.strip().split()[0].strip('<>#')
            try:
                target_channel = ctx.guild.get_channel(int(channel_arg))
                if not target_channel:
                    await ctx.send(f"Channel not found. Please provide a valid channel mention or ID.")
                    return
            except ValueError:
                await ctx.send(f"Invalid channel format. Use #channel-name or channel ID.")
                return
        else:
            # No channel specified, use current channel
            target_channel = ctx.channel

        channel_id = str(target_channel.id)

        # Clear channel-specific settings
        self.redis_client.clear_channel_role(server_id, channel_id)
        self.redis_client.clear_channel_model(server_id, channel_id)

        await ctx.send(f"Channel-specific settings cleared for <#{channel_id}>. Now using server-wide settings.")

    async def _handle_status(self, ctx):
        """Handle the status command - shows server defaults and per-channel settings"""
        if not await self.has_permissions(ctx):
            await ctx.send("You need administrator, moderator, or bot owner permissions to use this command.")
            return

        server_id = str(ctx.guild.id)

        # Migrate old single-channel data if exists
        self.redis_client.migrate_single_to_multi_channel(server_id)

        # Get server defaults
        default_model = self.redis_client.get_default_model(server_id)
        default_role = self.redis_client.get_default_role(server_id)

        # Get allowed channels
        allowed_channels = self.redis_client.get_allowed_channels(server_id)

        if not allowed_channels:
            status_message = (
                f"**Server Defaults:**\n"
                f"- Default Model: {default_model}\n"
                f"- Default Role: {default_role}\n\n"
                f"**Allowed Channels:** None (bot will not respond)\n"
                f"Use !addchan to add channels."
            )
        else:
            # Build channel settings list showing each channel's configuration
            channel_settings = []
            for channel_id in allowed_channels:
                role = self.redis_client.get_channel_role(server_id, channel_id)
                model = self.redis_client.get_channel_model(server_id, channel_id)
                channel_settings.append(f"  - <#{channel_id}>: Role=**{role}**, Model=**{model}**")

            status_message = (
                f"**Server Defaults:**\n"
                f"- Default Model: {default_model}\n"
                f"- Default Role: {default_role}\n\n"
                f"**Channel Settings:**\n" + "\n".join(channel_settings)
            )

        await ctx.send(status_message)

    async def _handle_shutdown(self, ctx):
        """Handle the shutdown command"""
        if ctx.author.id != self.owner_id:
            await ctx.send("Only the bot owner can use this command.")
            return
        
        await ctx.send("Shutting down...")
        await self.close()

    async def _handle_list_servers(self, ctx):
        """Handle the listservers command"""
        if ctx.author.id != self.owner_id:
            await ctx.send("Only the bot owner can use this command.")
            return
        
        servers = '\n'.join([f"{guild.name} (ID: {guild.id})" for guild in self.guilds])
        await ctx.send(f"Currently active in these servers:\n{servers}")

    async def _handle_leave_server(self, ctx, server_id=None):
        """Handle the leaveserver command"""
        if ctx.author.id != self.owner_id:
            await ctx.send("Only the bot owner can use this command.")
            return
        
        if server_id is None:
            await ctx.send("Please specify a server ID.")
            return

        try:
            guild = self.get_guild(int(server_id))
            if guild:
                await guild.leave()
                await ctx.send(f"Left server: {guild.name}")
            else:
                await ctx.send("Server not found.")
        except ValueError:
            await ctx.send("Invalid server ID format. Please provide a valid number.")

    async def _handle_image_generation(self, ctx, prompt: Optional[str], model: str):
        """
        Handle image generation commands for different models.
        
        Args:
            ctx: The Discord context
            prompt: The image generation prompt
            model: The model identifier to use for generation
        """
        if prompt is None:
            await ctx.send(f"Please provide a prompt for the {model} image generation.")
            return

        async with ctx.typing():
            try:
                # Get the appropriate image client
                image_client = self.ai_clients.get(model)
                if not image_client:
                    await ctx.send(f"The {model} image generation service is not properly configured.")
                    return

                # Generate the image
                image_data = await image_client.generate_image(prompt)
                
                if image_data:
                    # Create Discord file object from the image bytes
                    file = discord.File(
                        io.BytesIO(image_data), 
                        filename=f"{model}_generated.png"
                    )
                    await ctx.send(
                        "Here's your image:", 
                        file=file
                    )
                else:
                    await ctx.send(f"Failed to generate image with {model}.")
            except Exception as e:
                print(f"Error generating image with {model}: {str(e)}")  # Log the error
                await ctx.send(f"Error generating image with {model}: {str(e)}")

    # ==================== COUNTDOWN NUMBERS GAME ====================

    async def _handle_countdown(self, ctx, args=None):
        """
        Handle the countdown/numbers command - opens a game lobby.
        Usage: !countdown or !numbers
        """
        server_id = str(ctx.guild.id)
        channel_id = str(ctx.channel.id)
        user_id = str(ctx.author.id)

        try:
            # Create a lobby instead of starting game immediately
            lobby = self.countdown_game.create_lobby(server_id, channel_id, user_id)

            # Create lobby embed
            embed = self._create_lobby_embed(lobby, ctx.author)

            # Create the settings view
            view = CountdownSettingsView(self, lobby, ctx.author)
            message = await ctx.send(embed=embed, view=view)

            # Store message ID
            lobby.message_id = str(message.id)
            self.countdown_game.update_lobby(server_id, channel_id, lobby)

        except ValueError as e:
            await ctx.send(f"{str(e)}")
        except Exception as e:
            print(f"Error in _handle_countdown: {type(e).__name__}: {e}")
            await ctx.send(f"An error occurred: {str(e)}")

    async def _handle_leaderboard(self, ctx):
        """Show the server leaderboard."""
        server_id = str(ctx.guild.id)
        leaderboard = self.countdown_game.get_leaderboard(server_id)
        
        if not leaderboard:
            await ctx.send("No scores yet! Play some games with `!countdown`.")
            return
            
        embed = discord.Embed(
            title="🏆 Numbers Game Leaderboard",
            color=discord.Color.gold()
        )
        
        desc = []
        for i, (user_id, score) in enumerate(leaderboard):
            medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"#{i+1}"
            desc.append(f"**{medal}** <@{user_id}>: **{score}** pts")
            
        embed.description = "\n".join(desc)
        await ctx.send(embed=embed)

    async def _handle_answer(self, ctx, expression=None):
        """
        Handle the answer/solve command - submit an answer.
        Usage: !answer 25 * 4 + 7 or !solve (25 + 75) * 3
        """
        if expression is None:
            await ctx.send("Please provide an expression! Example: `!answer 25 * 4 + 7`", delete_after=5)
            return

        server_id = str(ctx.guild.id)
        channel_id = str(ctx.channel.id)
        user_id = str(ctx.author.id)

        try:
            # Get game to access target
            game = self.countdown_game.get_active_game(server_id, channel_id)
            if not game:
                await ctx.send("No active game in this channel! Start one with `!countdown`", delete_after=5)
                return

            submission = self.countdown_game.submit_answer(
                server_id, channel_id, user_id, expression
            )

            # Create confirmation embed
            if submission.valid:
                if submission.distance == 0:
                    embed = discord.Embed(
                        title="EXACT MATCH!",
                        description=f"`{expression}` = **{submission.result}**",
                        color=discord.Color.gold()
                    )
                    embed.add_field(
                        name="Target",
                        value=f"**{game.target}**",
                        inline=True
                    )
                else:
                    embed = discord.Embed(
                        title="Answer Submitted",
                        description=f"`{expression}` = **{submission.result}**",
                        color=discord.Color.green()
                    )
                    embed.add_field(
                        name="Distance from target",
                        value=f"**{submission.distance}** away from {game.target}",
                        inline=False
                    )
            else:
                embed = discord.Embed(
                    title="Invalid Answer",
                    description=f"{submission.error}",
                    color=discord.Color.red()
                )

            embed.set_footer(text=f"Submitted by {ctx.author.display_name}")
            await ctx.send(embed=embed, delete_after=10)

            # Delete the command message to reduce clutter
            try:
                await ctx.message.delete()
            except discord.errors.Forbidden:
                pass  # Bot doesn't have permission

        except ValueError as e:
            await ctx.send(f"{str(e)}", delete_after=5)

    async def _countdown_timer(self, ctx, server_id: str, channel_id: str, end_time: float):
        """Legacy background task - kept for compatibility."""
        import time

        wait_time = end_time - time.time()
        if wait_time > 0:
            await asyncio.sleep(wait_time)

        try:
            game, submissions = self.countdown_game.end_game(server_id, channel_id)
            points_earned = self.countdown_game.update_scores(server_id, submissions)
            exact_solution_found = any(s.valid and s.distance == 0 for s in submissions)

            solver_result = None
            if not exact_solution_found:
                best_expr, best_val = self.solver.solve(game.target, game.numbers)
                solver_result = (best_expr, best_val)

            embed = self._create_results_embed(game, submissions, solver_result, points_earned)
            await ctx.send(embed=embed)

        except ValueError:
            pass

    async def _countdown_timer_with_updates(self, interaction, server_id: str, channel_id: str,
                                            message: discord.Message, game):
        """Background task with live timer updates every 5 seconds."""
        import time

        while True:
            # Get fresh game state
            current_game = self.countdown_game.get_active_game(server_id, channel_id, auto_advance=False)
            if not current_game or current_game.status != "active":
                break

            time_left = current_game.time_remaining()
            if time_left <= 0:
                break

            # Update embed with current time
            # Update embed with current time
            try:
                embed = self._create_countdown_embed(current_game, interaction.user, time_left)
                view = CountdownView(self, server_id, channel_id)
                await message.edit(embed=embed, view=view)
            except discord.errors.NotFound:
                break  # Message was deleted
            except Exception:
                pass  # Ignore rate limit errors

            # Wait 5 seconds before next update
            await asyncio.sleep(5)

        # Handle round end
        await self._handle_round_end(interaction, server_id, channel_id, message)

    async def _handle_round_end(self, interaction, server_id: str, channel_id: str, message: discord.Message):
        """Handle the end of a round."""
        try:
            game, submissions = self.countdown_game.end_round(server_id, channel_id)
            points_earned = self.countdown_game.update_scores(server_id, submissions)

            # Check if anyone found an exact solution
            exact_solution_found = any(s.valid and s.distance == 0 for s in submissions)

            solver_result = None
            if not exact_solution_found:
                best_expr, best_val = self.solver.solve(game.target, game.numbers)
                solver_result = (best_expr, best_val)

            if game.is_final_round():
                # Update game scores one more time
                for user_id, pts in points_earned.items():
                    game.game_scores[user_id] = game.game_scores.get(user_id, 0) + pts

                # Show final results
                embed = self._create_final_results_embed(game, solver_result)
                await message.edit(embed=embed, view=None)

                # Clean up game
                self.countdown_game._delete_game(server_id, channel_id)
            else:
                # Show round results
                embed = self._create_round_results_embed(game, submissions, points_earned, solver_result)
                await message.edit(embed=embed, view=None)

                # Brief pause before next round
                await asyncio.sleep(5)

                # Advance to next round
                next_game = self.countdown_game.advance_round(server_id, channel_id, points_earned)
                if next_game:
                    # Create new game embed
                    embed = self._create_countdown_embed(next_game, interaction.user)
                    view = CountdownView(self, server_id, channel_id)

                    # Send new message for new round
                    new_message = await interaction.channel.send(embed=embed, view=view)
                    next_game.message_id = str(new_message.id)
                    self.countdown_game._save_game(server_id, channel_id, next_game)

                    # Start new timer
                    asyncio.create_task(
                        self._countdown_timer_with_updates(interaction, server_id, channel_id, new_message, next_game)
                    )

        except ValueError:
            pass

    def _create_lobby_embed(self, lobby, host, rounds=None, seconds_per_round=None) -> discord.Embed:
        """Create the lobby settings embed with modern design."""
        rounds = rounds or lobby.rounds
        seconds_per_round = seconds_per_round or lobby.seconds_per_round

        embed = discord.Embed(
            title="🎮  NUMBERS GAME LOBBY",
            description="Adjust settings below and press **Start Game** when ready.",
            color=0x2B2D31  # Dark theme
        )

        # Settings
        settings_text = f"**Rounds:** `{rounds}`\n**Time:** `{seconds_per_round}s`"
        embed.add_field(name="⚙️ Settings", value=settings_text, inline=True)

        # Players
        ready_count = len(lobby.ready_players)
        if ready_count > 0:
            players_text = "\n".join([f"• <@{pid}>" for pid in lobby.ready_players])
        else:
            players_text = "*Waiting for players...*"
        
        embed.add_field(name=f"👥 Players ({ready_count})", value=players_text, inline=True)
        
        embed.set_thumbnail(url="https://www.dropbox.com/scl/fi/848586887576/numbers_icon.png?rlkey=placeholder&raw=1") # Placeholder or generic icon
        embed.set_footer(text=f"Host: {host.display_name}")

        return embed

    def _create_calculator_embed(self, game, expression="") -> discord.Embed:
        """
        Create the PRIVATE unified game view embed.
        Contains Target, Numbers, and Current Expression.
        """
        # Modern Dark Theme Color (Midnight Blue/Dark Gray)
        color = 0x2F3136 

        # Header with Target Number (Large) if possible
        # Using a code block for the header to standout
        target_display = f"# 🎯 {game.target}"
        
        embed = discord.Embed(
            description=target_display,
            color=color
        )

        # Timer & Round Info
        time_left = game.time_remaining()
        round_info = f"Round {game.current_round}/{game.total_rounds} • ⏱️ {int(time_left)}s"
        embed.set_author(name=round_info, icon_url="https://cdn.discordapp.com/emojis/123456789.png") # Generic clock icon if available

        # Numbers Row (Visual representation of cards)
        # Using simple bold text with spacing
        numbers_display = "  ".join([f"［`{n}`］" for n in game.numbers])
        embed.add_field(name="AVAILABLE NUMBERS", value=numbers_display, inline=False)

        # Current Calculation Area (The "Screen")
        if expression:
            # Show current expression and dynamic result if strictly valid so far (optional, maybe just show expr)
            screen_content = f"```yaml\n{expression}\n```"
        else:
            screen_content = "```yaml\n \n```"  # Empty placeholder
        
        embed.add_field(name="CALCULATION", value=screen_content, inline=False)
        
        return embed

    def _create_countdown_embed(self, game, started_by, time_left=None) -> discord.Embed:
        """
        Create the PUBLIC status board embed.
        """
        if time_left is None:
            time_left = game.time_remaining()

        # Title
        title = "🔴  LIVE SESSION"

        # Color based on urgency
        if time_left > 20:
            color = 0x57F287  # Green
        elif time_left > 10:
            color = 0xFEE75C  # Yellow
        else:
            color = 0xED4245  # Red

        embed = discord.Embed(
            title=title,
            color=color
        )

        # Target and Numbers Summary
        summary = f"# 🎯 Target: {game.target}\n"
        summary += f"Numbers: " + " ".join([f"`{n}`" for n in game.numbers])
        embed.description = summary

        # Timer Progress
        progress = int((time_left / game.round_duration) * 10)
        bar = "▰" * progress + "▱" * (10 - progress)
        embed.add_field(name="⏳ Time Remaining", value=f"**{int(time_left)}s** `{bar}`", inline=False)

        # Active Players / Status
        # We can't easily see who is "typing" in their private view, so just show connected players from lobby or scores
        if game.game_scores:
            leaders = sorted(game.game_scores.items(), key=lambda x: x[1], reverse=True)[:3]
            leader_text = " • ".join([f"<@{uid}>: **{score}**" for uid, score in leaders])
            if leader_text:
                embed.add_field(name="🏆 Current Leaders", value=leader_text, inline=False)

        embed.set_footer(text=f"Round {game.current_round}/{game.total_rounds} • Started by {started_by.display_name}")

        return embed

    def _create_results_embed(self, game, submissions: list, solver_result=None, points_earned=None) -> discord.Embed:
        """Create the game results embed with modern design."""
        winners = self.countdown_game.determine_winners(submissions)
        points_earned = points_earned or {}

        # Determine embed color and title based on results
        if not winners:
            color = 0x99AAB5  # Gray
            title = "🏁  GAME OVER"
        elif winners[0].distance == 0:
            color = 0xF1C40F  # Gold
            title = "🏆  PERFECT SOLUTION!"
        else:
            color = 0x57F287  # Green
            title = "🏁  GAME OVER"

        # Challenge info
        numbers_str = "  ".join([f"`{n}`" for n in game.numbers])
        challenge_info = f"🎯 Target: **{game.target}**\n🔢 Numbers: {numbers_str}"

        embed = discord.Embed(
            title=title,
            description=f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{challenge_info}\n━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            color=color
        )

        if winners:
            medals = ["🥇", "🥈", "🥉"]
            results_text = []

            for i, sub in enumerate(winners[:3]):
                medal = medals[i] if i < 3 else f"#{i+1}"
                user_mention = f"<@{sub.user_id}>"

                if sub.distance == 0:
                    status = "**EXACT!**"
                else:
                    status = f"*{sub.distance} away*"

                points_str = ""
                if sub.user_id in points_earned:
                    points_str = f"  `+{points_earned[sub.user_id]} pts`"

                results_text.append(f"{medal} {user_mention} • **{sub.result}** {status}{points_str}")
                results_text.append(f"   └ `{sub.expression}`")

            embed.add_field(
                name="🏆  RESULTS",
                value="\n".join(results_text),
                inline=False
            )

            if len(winners) > 3:
                embed.add_field(
                    name="\u200b",
                    value=f"*+{len(winners) - 3} more participants*",
                    inline=False
                )

        if solver_result:
            expr, val = solver_result
            if expr:
                if val == game.target:
                    solver_text = f"💡 `{expr}` = {val} *(exact)*"
                else:
                    solver_text = f"💡 `{expr}` = {val} *({abs(game.target - val)} away)*"
                embed.add_field(name="Best Possible", value=solver_text, inline=False)
        elif not winners:
            embed.add_field(
                name="🏆  RESULTS",
                value="*No valid submissions*",
                inline=False
            )

        # Stats
        total_submissions = len(submissions)
        valid_submissions = len([s for s in submissions if s.valid])

        embed.set_footer(text=f"📊 {valid_submissions}/{total_submissions} valid submissions  •  Type !numbers to play again 🎮")

        return embed

    def _create_round_results_embed(self, game, submissions: list, points_earned: dict, solver_result=None) -> discord.Embed:
        """Create embed showing round results with modern design."""
        winners = self.countdown_game.determine_winners(submissions)

        # Determine color based on results
        if not winners:
            color = 0x99AAB5  # Gray
        elif winners[0].distance == 0:
            color = 0xF1C40F  # Gold
        else:
            color = 0x57F287  # Green

        # Challenge info
        numbers_str = "  ".join([f"`{n}`" for n in game.numbers])
        challenge_info = f"🎯 Target: **{game.target}**\n🔢 Numbers: {numbers_str}"

        embed = discord.Embed(
            title=f"🏁  ROUND {game.current_round} COMPLETE",
            description=f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{challenge_info}\n━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            color=color
        )

        # Round winners with better formatting
        if winners:
            medals = ["🥇", "🥈", "🥉"]
            results_text = []

            for i, sub in enumerate(winners[:3]):
                medal = medals[i] if i < 3 else f"#{i+1}"
                user_mention = f"<@{sub.user_id}>"

                if sub.distance == 0:
                    status = "**EXACT!**"
                else:
                    status = f"*{sub.distance} away*"

                points_str = ""
                if sub.user_id in points_earned:
                    points_str = f"  `+{points_earned[sub.user_id]} pts`"

                results_text.append(f"{medal} {user_mention} • **{sub.result}** {status}{points_str}")
                results_text.append(f"   └ `{sub.expression}`")

            embed.add_field(
                name="🏆  RESULTS",
                value="\n".join(results_text),
                inline=False
            )
        else:
            embed.add_field(
                name="🏆  RESULTS",
                value="*No valid submissions this round*",
                inline=False
            )

        # Solver result if no exact match
        if solver_result:
            expr, val = solver_result
            if expr:
                if val == game.target:
                    solver_text = f"💡 `{expr}` = {val} *(exact)*"
                else:
                    solver_text = f"💡 `{expr}` = {val} *({abs(game.target - val)} away)*"
                embed.add_field(name="Best Possible", value=solver_text, inline=False)

        # Current standings
        if game.game_scores or points_earned:
            current_scores = dict(game.game_scores)
            for user_id, pts in points_earned.items():
                current_scores[user_id] = current_scores.get(user_id, 0) + pts

            if current_scores:
                sorted_scores = sorted(current_scores.items(), key=lambda x: x[1], reverse=True)
                standings = "  │  ".join([f"<@{uid}>: **{score}**" for uid, score in sorted_scores[:5]])
                embed.add_field(name="📊  STANDINGS", value=standings, inline=False)

        embed.set_footer(text="⏳ Next round starting in 5 seconds...")

        return embed

    def _create_final_results_embed(self, game, solver_result=None) -> discord.Embed:
        """Create final results embed with modern celebratory design."""
        embed = discord.Embed(
            title="🏆  GAME OVER",
            description="━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            color=0xF1C40F  # Gold
        )

        # Final standings
        if game.game_scores:
            sorted_scores = sorted(game.game_scores.items(), key=lambda x: x[1], reverse=True)
            medals = ["🥇", "🥈", "🥉"]

            standings_text = []
            for i, (user_id, score) in enumerate(sorted_scores):
                medal = medals[i] if i < 3 else f"**#{i+1}**"
                standings_text.append(f"{medal}  <@{user_id}>  —  **{score} points**")

            embed.add_field(
                name="🎖️  FINAL STANDINGS",
                value="\n".join(standings_text),
                inline=False
            )
        else:
            embed.add_field(
                name="🎖️  FINAL STANDINGS",
                value="*No scores recorded*",
                inline=False
            )

        # Game stats
        embed.add_field(
            name="━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            value=f"📊  **{game.total_rounds}** rounds  •  **{game.round_duration}s** each",
            inline=False
        )

        embed.set_footer(text="Thanks for playing!  •  Type !numbers to play again 🎮")

        return embed

    # ==================== END COUNTDOWN GAME ====================

    async def get_ai_response(self,
                            server_id: str,
                            channel_id: str,
                            user_id: str,
                            message: str) -> Optional[str]:
        """Get AI response for a message"""
        # Migrate old single-channel data if exists
        self.redis_client.migrate_single_to_multi_channel(server_id)

        # Check if channel is allowed (multi-channel support)
        if not self.redis_client.is_channel_allowed(server_id, channel_id):
            return None

        channel = self.get_channel(int(channel_id))
        async with channel.typing():  # Show typing indicator while processing
            # Get current model and role (channel-specific with fallback)
            model = self.redis_client.get_channel_model(server_id, channel_id)
            role_id = self.redis_client.get_channel_role(server_id, channel_id)
            role: Role = self.config.roles[role_id]

            # Get conversation context
            context = self.redis_client.get_context(server_id, channel_id)

            try:
                # Generate response with timeout
                ai_client = self.ai_clients[model]
                response = await asyncio.wait_for(
                    ai_client.generate_response(
                        role.system_prompt,
                        context,
                        message
                    ),
                    timeout=120.0  # Extended timeout for image generation
                )

                # Save to context
                self.redis_client.add_to_context(
                    server_id,
                    channel_id,
                    user_id,
                    message,
                    response
                )

                return response
            except asyncio.TimeoutError:
                return "I apologize, but the response took too long. Please try again."
            except Exception as e:
                print(f"Error generating response: {str(e)}")  # Log the error
                return f"Error generating response: {str(e)}"

    async def on_ready(self):
        """Called when the bot is ready"""
        print(f"Bot is ready! Logged in as {self.user.name}")
        print(f"Bot ID: {self.user.id}")
        print(f"Connected to {len(self.guilds)} servers")

        # Set custom status
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="for mentions | !help"
            )
        )

    async def on_guild_join(self, guild):
        """Called when the bot joins a new guild"""
        print(f"Joined new guild: {guild.name} (ID: {guild.id})")

    async def on_message(self, message: discord.Message):
        """Called when a message is received"""
        # Process commands
        await self.process_commands(message)

        # Ignore messages from the bot itself
        if message.author == self.user:
            return

        # Only respond to mentions
        if self.user not in message.mentions:
            return

        # Remove the mention from the message
        content = message.content.replace(f'<@{self.user.id}>', '').strip()

        response = await self.get_ai_response(
            str(message.guild.id),
            str(message.channel.id),
            str(message.author.id),
            content
        )

        if response:
            await send_chunked_message(message.channel, response, reference=message)

    # ==================== WEB SERVER ====================
    async def start_web_server(self):
        """Start the aiohttp web server for the game dashboard."""
        print("Initializing web server...", flush=True)
        try:
            from aiohttp import web
            
            self.app = web.Application()

            # API (used by Discord Activity)
            # Define specific routes first to avoid dynamic pattern matching grabbing them
            self.app.router.add_post('/api/game/create', self.web_handle_create_game)
            self.app.router.add_post('/game/create', self.web_handle_create_game) # Alias

            self.app.router.add_get('/api/game/{game_id}', self.web_handle_game_api)
            self.app.router.add_get('/game/{game_id}', self.web_handle_game_api) # Alias
            
            self.app.router.add_post('/api/submit', self.web_handle_submit_api)
            self.app.router.add_post('/submit', self.web_handle_submit_api) # Alias
            
            self.app.router.add_post('/api/token', self.web_handle_token_exchange)
            self.app.router.add_post('/token', self.web_handle_token_exchange) # Alias for root access if needed
            self.app.router.add_get('/', self.web_handle_root) # Handle root for health checks

            runner = web.AppRunner(self.app)
            await runner.setup()
            site = web.TCPSite(runner, '0.0.0.0', 10010)
            await site.start()
            print("Web server started on port 10010", flush=True)
        except Exception as e:
            print(f"CRITICAL: Failed to start web server: {e}", flush=True)
            import traceback
            traceback.print_exc()

    async def web_handle_game_api(self, request):
        """Return game state JSON."""
        from aiohttp import web
        import urllib.parse
        game_id = request.match_info['game_id']
        
        try:
            # Handle encoded characters just in case
            game_id = urllib.parse.unquote(game_id).strip()
            
            if '_' in game_id:
                server_id, channel_id = game_id.split('_', 1)
                server_id = server_id.strip()
                channel_id = channel_id.strip()
            else:
                return web.json_response({"error": "Invalid Game ID format"}, status=400)
                
            print(f"API Request for Game ID: {server_id}_{channel_id}", flush=True)
            
            # Use the manager to get the game
            game = self.countdown_game.get_active_game(server_id, channel_id, allow_ended=True)
            
            if not game:
                # Return inactive status so frontend shows Lobby
                return web.json_response({"status": "inactive"}, status=200)

            # Return the game state as JSON
            # Safer: Load to dict first to ensure clean JSON
            import json
            response_data = json.loads(game.to_json())
            # Debug: Print what we are sending
            print(f"Sending Game JSON ({len(str(response_data))} chars): {str(response_data)[:100]}...", flush=True)
            return web.json_response(response_data)
            
        except Exception as e:
            print(f"Error handling request: {e}", flush=True)
            import traceback
            traceback.print_exc()
            return web.json_response({"error": str(e)}, status=500)

    async def web_handle_create_game(self, request):
        """Handle game creation from web lobby."""
        try:
            data = await request.json()
            server_id = str(data.get('server_id', '')).strip()
            channel_id = str(data.get('channel_id', '')).strip()
            started_by = data.get('started_by')
            rounds = int(data.get('rounds', 3))
            duration = int(data.get('duration', 60))

            if not all([server_id, channel_id, started_by]):
                return web.json_response({"error": "Missing required fields"}, status=400)

            print(f"Creating game via API: Server {server_id}, Channel {channel_id}, Rounds {rounds}", flush=True)

            # Create game
            # Note: create_game raises ValueError if game exists
            try:
                game = self.countdown_game.create_game(
                    server_id=server_id,
                    channel_id=channel_id,
                    started_by=started_by,
                    total_rounds=rounds,
                    round_duration=duration
                )
                import json
                return web.json_response(json.loads(game.to_json()))
            except ValueError as e:
                # If game exists, return it? Or error?
                # If it exists, they should join it.
                return web.json_response({"error": str(e)}, status=400)

        except Exception as e:
            print(f"Create Game Error: {e}", flush=True)
            traceback.print_exc()
            return web.json_response({"error": str(e)}, status=500)

    async def web_handle_submit_api(self, request):
        """Handle submission from web."""
        from aiohttp import web
        data = await request.json()
        game_id = str(data.get('game_id', '')).strip()
        user_id = data.get('user_id')
        expression = data.get('expression')
        
        if not game_id or not user_id or not expression:
             return web.json_response({"success": False, "error": "Missing data"}, status=400)

        server_id, channel_id = game_id.split("_", 1)
        server_id = server_id.strip()
        channel_id = channel_id.strip()
        
        try:
            submission = self.countdown_game.submit_answer(server_id, channel_id, user_id, expression)
            if submission.valid:
                return web.json_response({
                    "success": True,
                    "result": submission.result,
                    "distance": submission.distance
                })
            else:
                return web.json_response({
                    "success": False,
                    "error": submission.error
                })
        except ValueError as e:
            return web.json_response({"success": False, "error": str(e)})

    async def web_handle_token_exchange(self, request):
        """Exchange OAuth2 authorization code for access token (for Discord Activity)."""
        from aiohttp import web

        try:
            data = await request.json()
            code = data.get('code')

            if not code:
                return web.json_response({'error': 'Missing authorization code'}, status=400)

            client_id = os.getenv('DISCORD_CLIENT_ID')
            client_secret = os.getenv('DISCORD_CLIENT_SECRET')

            if not client_id or not client_secret:
                return web.json_response({'error': 'OAuth2 not configured'}, status=500)

            # Exchange code for token with Discord
            token_url = 'https://discord.com/api/oauth2/token'
            payload = {
                'client_id': client_id,
                'client_secret': client_secret,
                'grant_type': 'authorization_code',
                'code': code,
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(token_url, data=payload) as resp:
                    token_data = await resp.json()
                    print(f"Token exchange response: {resp.status} {token_data}", flush=True)

            if 'access_token' in token_data:
                return web.json_response({'access_token': token_data['access_token']})
            else:
                error_msg = token_data.get('error_description', token_data.get('error', 'Token exchange failed'))
                print(f"Token exchange failed: {error_msg}", flush=True)
                return web.json_response({'error': error_msg}, status=400)

        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def web_handle_root(self, request):
        """Handle root health checks."""
        from aiohttp import web
        return web.Response(text="Discord Activity Bot API is running")

class CountdownView(discord.ui.View):
    def __init__(self, bot, server_id, channel_id, base_url="http://localhost:10010"):
        super().__init__(timeout=None)
        self.bot = bot
        
        # Determine the public URL (should be configured, but using host IP request)
        # We will use the base_url passed in, or default.
        # Ideally this comes from config, but for now we hardcode/guess.
        # Actually, let's just use a relative path if we were in browser, but we are in Discord.
        # We need the user to set PUBLIC_URL. For now we use the requested port.
        
        game_id = f"{server_id}_{channel_id}"
        
        # Link Button!
        # Note: We need to know who the user is for the link?
        # No, the user will have to input it or we just use their session?
        # Actually easier: we can't easily pass user_id securely without auth.
        # BUT for a simple game, we can pass `?user=USER_ID` in the link. 
        # It's spoofable but low stakes.
        
        # We can't generate dynamic links properly in a persistent view unless we make it ephemeral per user.
        # But this is a persistent view on the board.
        # So we can keep "Play Now" as a button that GENERATES the ephemeral link!
        
        pass


    @discord.ui.button(label="🎮 Play in Discord", style=discord.ButtonStyle.success)
    async def launch_activity(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Launch the Numbers Game as a Discord Activity in voice channel."""
        # Check if user is in a voice channel
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message(
                "**Join a voice channel first!**\n"
                "Discord Activities require you to be in a voice channel to play.",
                ephemeral=True
            )
            return

        # Get the application ID for Activity launch
        app_id = os.getenv('DISCORD_CLIENT_ID') or os.getenv('DISCORD_APPLICATION_ID')
        if not app_id:
            await interaction.response.send_message(
                "Activity not configured. Please contact the bot administrator.",
                ephemeral=True
            )
            return

        try:
            # Create Activity invite for the voice channel
            voice_channel = interaction.user.voice.channel
            invite = await voice_channel.create_invite(
                max_age=86400,  # 24 hours
                max_uses=0,
                target_type=discord.InviteTarget.embedded_application,
                target_application_id=int(app_id)
            )

            await interaction.response.send_message(
                f"**[Click here to launch Numbers Game Activity]({invite.url})**\n"
                f"Playing in: {voice_channel.mention}",
                ephemeral=True
            )
        except discord.HTTPException as e:
            await interaction.response.send_message(
                f"Failed to create Activity invite: {e}",
                ephemeral=True
            )

