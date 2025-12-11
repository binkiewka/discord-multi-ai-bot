import discord
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
        
        # Row 0: Large Numbers (2 nums)
        # We need to know which are large/small but we only have game.numbers list.
        # However, we know typically first 2 are large in standard game, or we can just assume 
        # the list order is preserved from generation (large + small).
        # Let's just put first 2 in Row 0, and next 4 in Row 1.
        
        for i, num in enumerate(self.game.numbers[:2]):
            disabled = i in self.used_indices
            self.add_item(NumberButton(num, i, disabled, row=0))
            
        # Row 1: Small Numbers (4 nums)
        for i, num in enumerate(self.game.numbers[2:]):
            idx = i + 2
            disabled = idx in self.used_indices
            self.add_item(NumberButton(num, idx, disabled, row=1))

        # Row 2: Basic Operators + Open Paren
        ops_row2 = ["+", "-", "*", "/", "("]
        for op in ops_row2:
            self.add_item(OperatorButton(op, row=2))

        # Row 3: Close Paren, Controls, Submit
        self.add_item(OperatorButton(")", row=3))
        self.add_item(ActionButton("⌫", "backspace", discord.ButtonStyle.danger, row=3))
        self.add_item(ActionButton("CLR", "clear", discord.ButtonStyle.danger, row=3))
        self.add_item(ActionButton("SUBMIT", "submit", discord.ButtonStyle.success, row=3))

    async def update_view(self, interaction: discord.Interaction):
        self._init_buttons()
        # Ensure screen is always visible
        content = f"```fix\n{self.expression if self.expression else ' '}\n```"
        await interaction.response.edit_message(content=content, view=self)

class NumberButton(discord.ui.Button):
    def __init__(self, number, index, disabled=False, row=0):
        super().__init__(
            label=str(number), 
            style=discord.ButtonStyle.secondary, 
            disabled=disabled, 
            row=row
        )
        self.number = number
        self.index = index

    async def callback(self, interaction: discord.Interaction):
        view: CalculatorView = self.view
        if interaction.user.id != int(view.user_id):
            return await interaction.response.send_message("This isn't your game!", ephemeral=True)
            
        view.expression += str(self.number)
        view.used_indices.add(self.index)
        await view.update_view(interaction)

class OperatorButton(discord.ui.Button):
    def __init__(self, operator, row=0):
        super().__init__(
            label=operator, 
            style=discord.ButtonStyle.primary, 
            row=row
        )
        self.operator = operator

    async def callback(self, interaction: discord.Interaction):
        view: CalculatorView = self.view
        if interaction.user.id != int(view.user_id):
            return await interaction.response.send_message("This isn't your game!", ephemeral=True)
            
        # Add spacing for readability, except parentheses sometimes
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
        if interaction.user.id != int(view.user_id):
            return await interaction.response.send_message("This isn't your game!", ephemeral=True)

        if self.action == "clear":
            view.expression = ""
            view.used_indices.clear()
            await view.update_view(interaction)
            
        elif self.action == "backspace":
            # Simple backspace logic is tricky with tokens. 
            # We'll just reset for now or try to strip last char/token.
            # For robustness in this MVP, let's just clear. 
            # Or implementing a token stack would be better but complex.
            # Let's try simple string manipulation.
            if view.expression:
                view.expression = view.expression[:-1].strip()
                # Re-validating used indices is hard without parsing. 
                # So we simply Clear if they want to undo for safety.
                view.expression = ""
                view.used_indices.clear()
            await view.update_view(interaction)
            
        elif self.action == "submit":
            # Logic similar to original submit
            server_id = str(interaction.guild_id)
            channel_id = str(interaction.channel_id)
            user_id = str(interaction.user.id)
            
            try:
                submission = view.bot.countdown_game.submit_answer(
                    server_id, channel_id, user_id, view.expression
                )
                
                if submission.valid:
                    if submission.distance == 0:
                        response = f"🎯 **EXACT MATCH!** `{view.expression}` = {submission.result}"
                        color = discord.Color.gold()
                    else:
                        response = f"✅ **Submitted:** `{view.expression}` = {submission.result} ({submission.distance} away)"
                        color = discord.Color.green()
                    
                    # Send to main channel
                    embed = discord.Embed(description=response, color=color)
                    embed.set_footer(text=f"Submitted by {interaction.user.display_name}")
                    await interaction.channel.send(embed=embed)
                    await interaction.response.edit_message(content="Submitted!", view=None)

                else:
                    await interaction.response.send_message(f"❌ **Invalid:** {submission.error}", ephemeral=True)
                    
            except ValueError as e:
                await interaction.response.send_message(str(e), ephemeral=True)

class CountdownView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Play Now", style=discord.ButtonStyle.success, emoji="🎮")
    async def play_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        server_id = str(interaction.guild_id)
        channel_id = str(interaction.channel_id)

        game = self.bot.countdown_game.get_active_game(server_id, channel_id)
        if not game:
            await interaction.response.send_message("Game has ended!", ephemeral=True)
            return

        # Create ephemeral calculator for this user
        view = CalculatorView(self.bot, game, interaction.user.id)
        await interaction.response.send_message(
            content="```fix\n \n```",
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
        view = CountdownView(self.bot)

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

    async def setup_hook(self):
        """This is called when the bot is ready to start"""
        self.add_commands()

    async def has_permissions(self, ctx) -> bool:
        """Check if user has required permissions (admin, moderator, or bot owner)"""
        return (
            ctx.author.id == self.owner_id or
            (ctx.guild and (
                ctx.author.guild_permissions.administrator or
                ctx.author.guild_permissions.moderate_members
            ))
        )

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
            current_game = self.countdown_game.get_active_game(server_id, channel_id)
            if not current_game or current_game.status != "active":
                break

            time_left = current_game.time_remaining()
            if time_left <= 0:
                break

            # Update embed with current time
            try:
                embed = self._create_countdown_embed(current_game, interaction.user, time_left)
                view = CountdownView(self)
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
                    view = CountdownView(self)

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
        """Create the lobby settings embed."""
        rounds = rounds or lobby.rounds
        seconds_per_round = seconds_per_round or lobby.seconds_per_round

        embed = discord.Embed(
            title="NUMBERS GAME LOBBY",
            description="Configure your game and click **Start Game** when ready!",
            color=discord.Color.blue()
        )

        # Settings
        embed.add_field(
            name="Rounds",
            value=f"**{rounds}**",
            inline=True
        )

        embed.add_field(
            name="Time per Round",
            value=f"**{seconds_per_round}s**",
            inline=True
        )

        embed.add_field(name="\u200b", value="\u200b", inline=False)  # Spacer

        # Ready players
        ready_count = len(lobby.ready_players)
        if ready_count > 0:
            ready_list = []
            for player_id in lobby.ready_players:
                if player_id == lobby.host_id:
                    ready_list.append(f"<@{player_id}> (host)")
                else:
                    ready_list.append(f"<@{player_id}>")
            ready_text = "\n".join(ready_list)
        else:
            ready_text = "*No players ready yet*"

        embed.add_field(
            name=f"Ready Players ({ready_count})",
            value=ready_text,
            inline=False
        )

        embed.set_footer(text=f"Host: {host.display_name} • Host can start anytime!")

        return embed

    def _create_countdown_embed(self, game, started_by, time_left=None) -> discord.Embed:
        """Create the game board embed with live timer."""
        # Use time_left if provided, otherwise calculate from game state
        if time_left is None:
            time_left = game.time_remaining()

        # Round info for multi-round games
        if game.total_rounds > 1:
            title = f"NUMBERS GAME - Round {game.current_round}/{game.total_rounds}"
        else:
            title = "NUMBERS GAME"

        # Color based on time remaining
        if time_left > 20:
            color = discord.Color.green()
        elif time_left > 10:
            color = discord.Color.gold()
        else:
            color = discord.Color.red()

        embed = discord.Embed(
            title=title,
            description="\u200b",
            color=color
        )

        # Target
        embed.add_field(
            name="TARGET",
            value=f"```fix\n{game.target}\n```",
            inline=True
        )

        # Time with progress bar
        progress = int((time_left / game.round_duration) * 10)
        bar = "█" * progress + "░" * (10 - progress)
        time_display = f"**{int(time_left)}s** `{bar}`"

        embed.add_field(
            name="TIME LEFT",
            value=time_display,
            inline=True
        )

        embed.add_field(name="\u200b", value="\u200b", inline=False)

        # Numbers strip
        all_numbers = "  ".join([f"` {n} `" for n in game.numbers])
        embed.add_field(
            name="AVAILABLE NUMBERS",
            value=f"**{all_numbers}**",
            inline=False
        )

        embed.set_footer(text=f"Started by {started_by.display_name} • Click 'Play Now' to solve!")

        return embed

    def _create_results_embed(self, game, submissions: list, solver_result=None, points_earned=None) -> discord.Embed:
        """Create the game results embed."""
        winners = self.countdown_game.determine_winners(submissions)
        points_earned = points_earned or {}

        # Determine embed color and title based on results
        if not winners:
            color = discord.Color.dark_grey()
            title = "GAME OVER - No Valid Solutions!"
        elif winners[0].distance == 0:
            color = discord.Color.gold()
            title = "GAME OVER - PERFECT SOLUTION!"
        else:
            color = discord.Color.green()
            title = "GAME OVER - Results"

        embed = discord.Embed(title=title, color=color)

        # Recap the challenge
        embed.add_field(
            name="Target Was",
            value=f"**{game.target}**",
            inline=True
        )

        numbers_str = " ".join(map(str, game.numbers))
        embed.add_field(
            name="Numbers Were",
            value=numbers_str,
            inline=True
        )

        embed.add_field(name="\u200b", value="\u200b", inline=False)  # Spacer

        if winners:
            # Podium display
            medals = ["", "", ""]

            for i, sub in enumerate(winners[:3]):
                medal = medals[i] if i < 3 else ""
                user_mention = f"<@{sub.user_id}>"

                if sub.distance == 0:
                    status = "EXACT!"
                else:
                    status = f"{sub.distance} away"
                
                points_str = ""
                if sub.user_id in points_earned:
                    points_str = f" (+{points_earned[sub.user_id]} pts)"

                embed.add_field(
                    name=f"{medal} #{i+1}",
                    value=f"{user_mention}{points_str}\n`{sub.expression}` = {sub.result}\n({status})",
                    inline=True
                )

            # If more than 3 participants, show count
            if len(winners) > 3:
                embed.add_field(
                    name="Other Participants",
                    value=f"{len(winners) - 3} others submitted valid answers.",
                    inline=False
                )

        if solver_result:
            expr, val = solver_result
            if expr:
                embed.add_field(name="\u200b", value="\u200b", inline=False)
                val_str = f"{val}"
                if val == game.target:
                    title_str = "Best Possible Solution (Exact)"
                else:
                    title_str = f"Best Possible Solution ({abs(game.target - val)} away)"
                
                embed.add_field(
                    name=title_str,
                    value=f"```fix\n{expr} = {val}\n```",
                    inline=False
                )
        else:
            embed.add_field(
                name="No Winners",
                value="Nobody submitted a valid solution!",
                inline=False
            )

        # Stats
        total_submissions = len(submissions)
        valid_submissions = len([s for s in submissions if s.valid])

        embed.set_footer(
            text=f"Submissions: {valid_submissions}/{total_submissions} valid"
        )

        return embed

    def _create_round_results_embed(self, game, submissions: list, points_earned: dict, solver_result=None) -> discord.Embed:
        """Create embed showing round results (for multi-round games)."""
        winners = self.countdown_game.determine_winners(submissions)

        # Determine color based on results
        if not winners:
            color = discord.Color.dark_grey()
        elif winners[0].distance == 0:
            color = discord.Color.gold()
        else:
            color = discord.Color.green()

        embed = discord.Embed(
            title=f"Round {game.current_round} Complete!",
            color=color
        )

        # Challenge recap
        embed.add_field(
            name="Target",
            value=f"**{game.target}**",
            inline=True
        )

        numbers_str = " ".join(map(str, game.numbers))
        embed.add_field(
            name="Numbers",
            value=numbers_str,
            inline=True
        )

        embed.add_field(name="\u200b", value="\u200b", inline=False)

        # Round winners
        if winners:
            medals = ["🥇", "🥈", "🥉"]
            for i, sub in enumerate(winners[:3]):
                medal = medals[i] if i < 3 else f"#{i+1}"
                user_mention = f"<@{sub.user_id}>"

                if sub.distance == 0:
                    status = "EXACT!"
                else:
                    status = f"{sub.distance} away"

                points_str = ""
                if sub.user_id in points_earned:
                    points_str = f" (+{points_earned[sub.user_id]} pts)"

                embed.add_field(
                    name=f"{medal}",
                    value=f"{user_mention}{points_str}\n`{sub.expression}` = {sub.result}\n({status})",
                    inline=True
                )
        else:
            embed.add_field(
                name="No Winners",
                value="No valid submissions this round!",
                inline=False
            )

        # Solver result if no exact match
        if solver_result:
            expr, val = solver_result
            if expr:
                if val == game.target:
                    solver_text = f"Best: `{expr}` = {val} (exact)"
                else:
                    solver_text = f"Best: `{expr}` = {val} ({abs(game.target - val)} away)"
                embed.add_field(name="Solver", value=solver_text, inline=False)

        # Current standings
        if game.game_scores:
            # Add this round's points to display current standings
            current_scores = dict(game.game_scores)
            for user_id, pts in points_earned.items():
                current_scores[user_id] = current_scores.get(user_id, 0) + pts

            sorted_scores = sorted(current_scores.items(), key=lambda x: x[1], reverse=True)
            standings = " | ".join([f"<@{uid}>: {score}" for uid, score in sorted_scores[:5]])
            embed.add_field(name="Current Standings", value=standings, inline=False)

        embed.set_footer(text=f"Next round starting in 5 seconds...")

        return embed

    def _create_final_results_embed(self, game, solver_result=None) -> discord.Embed:
        """Create final results embed for multi-round games."""
        embed = discord.Embed(
            title="GAME OVER - Final Results",
            color=discord.Color.gold()
        )

        # Final standings
        if game.game_scores:
            sorted_scores = sorted(game.game_scores.items(), key=lambda x: x[1], reverse=True)
            medals = ["🥇", "🥈", "🥉"]

            standings_text = []
            for i, (user_id, score) in enumerate(sorted_scores):
                medal = medals[i] if i < 3 else f"#{i+1}"
                standings_text.append(f"**{medal}** <@{user_id}>: **{score}** points")

            embed.description = "\n".join(standings_text)
        else:
            embed.description = "No scores recorded!"

        embed.add_field(name="\u200b", value="\u200b", inline=False)

        # Game stats
        embed.add_field(
            name="Game Stats",
            value=f"Rounds: **{game.total_rounds}** | Time per round: **{game.round_duration}s**",
            inline=False
        )

        embed.set_footer(text="Thanks for playing! Use !numbers to play again.")

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
