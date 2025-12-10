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

class AnswerModal(discord.ui.Modal, title="Submit Answer"):
    expression = discord.ui.TextInput(
        label="Your Expression",
        placeholder="e.g. (25 + 10) * 3",
        required=True,
        style=discord.TextStyle.short
    )

    def __init__(self, bot, game_view):
        super().__init__()
        self.bot = bot
        self.game_view = game_view

    async def on_submit(self, interaction: discord.Interaction):
        # We need to defer or handle the response
        # We will reuse the bot's existing answer logic but routed through interaction
        server_id = str(interaction.guild_id)
        channel_id = str(interaction.channel_id)
        user_id = str(interaction.user.id)
        expression = self.expression.value

        try:
            # Get game
            game = self.bot.countdown_game.get_active_game(server_id, channel_id)
            if not game:
                await interaction.response.send_message("No active game!", ephemeral=True)
                return

            submission = self.bot.countdown_game.submit_answer(
                server_id, channel_id, user_id, expression
            )

            if submission.valid:
                if submission.distance == 0:
                    response = f"🎯 **EXACT MATCH!** `{expression}` = {submission.result}"
                    color = discord.Color.gold()
                else:
                    response = f"✅ **Submitted:** `{expression}` = {submission.result} ({submission.distance} away)"
                    color = discord.Color.green()
            else:
                response = f"❌ **Invalid:** {submission.error}"
                color = discord.Color.red()

            embed = discord.Embed(description=response, color=color)
            embed.set_footer(text=f"Submitted by {interaction.user.display_name}")
            
            await interaction.response.send_message(embed=embed)
            
        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)

class CountdownView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None) # Timeout handled by game timer
        self.bot = bot

    @discord.ui.button(label="Submit Answer", style=discord.ButtonStyle.primary, emoji="📝")
    async def submit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        server_id = str(interaction.guild_id)
        channel_id = str(interaction.channel_id)
        
        # Check if game is still active
        game = self.bot.countdown_game.get_active_game(server_id, channel_id)
        if not game:
            await interaction.response.send_message("Game has ended!", ephemeral=True)
            self.stop()
            return
            
        await interaction.response.send_modal(AnswerModal(self.bot, self))


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
            'solve': self._handle_answer  # alias
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
        Handle the countdown/numbers command - starts a new game.
        Usage: !countdown or !numbers
        """
        server_id = str(ctx.guild.id)
        channel_id = str(ctx.channel.id)
        user_id = str(ctx.author.id)

        try:
            game = self.countdown_game.create_game(server_id, channel_id, user_id)

            # Create and send game embed
            embed = self._create_countdown_embed(game, ctx.author)

            # Try to attach the banner image
            # Check for png first, then jpg
            banner_filename = 'countdown_banner.png'
            banner_path = os.path.join(self.assets_path, banner_filename)
            if not os.path.exists(banner_path):
                banner_filename = 'countdown_banner.jpg' 
                banner_path = os.path.join(self.assets_path, banner_filename)

            # Create the view with buttons
            view = CountdownView(self)

            if os.path.exists(banner_path):
                file = discord.File(banner_path, filename=banner_filename)
                embed.set_image(url=f"attachment://{banner_filename}")
                message = await ctx.send(file=file, embed=embed, view=view)
            else:
                message = await ctx.send(embed=embed, view=view)

            # Store message ID for potential updates
            game.message_id = str(message.id)
            self.countdown_game._save_game(server_id, channel_id, game)

            # Schedule game end
            asyncio.create_task(
                self._countdown_timer(ctx, server_id, channel_id, game.end_time)
            )

        except ValueError as e:
            await ctx.send(f"{str(e)}")

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
        """Background task to handle game timing."""
        import time

        # Wait until end time
        wait_time = end_time - time.time()
        if wait_time > 0:
            await asyncio.sleep(wait_time)

        # End the game
        try:
            game, submissions = self.countdown_game.end_game(server_id, channel_id)

            # Check if anyone found an exact solution
            exact_solution_found = any(s.valid and s.distance == 0 for s in submissions)
            
            solver_result = None
            if not exact_solution_found:
                # Run solver to show what was possible
                # This might take a moment, but since it's background task it's fine
                # To be safe regarding blocking, maybe run in executor if slow, but for 6 numbers it's fast.
                best_expr, best_val = self.solver.solve(game.target, game.numbers)
                solver_result = (best_expr, best_val)

            # Create results embed
            embed = self._create_results_embed(game, submissions, solver_result)
            
            # Send results - clearing the view (buttons) from the original message would be nice but difficult 
            # without keeping track of message object in memory securely or fetching it.
            # We'll just send a new message.
            await ctx.send(embed=embed)

        except ValueError:
            # Game was already ended or cancelled
            pass

    def _create_countdown_embed(self, game, started_by) -> discord.Embed:
        """Create the game board embed."""
        embed = discord.Embed(
            title="COUNTDOWN NUMBERS GAME",
            description="Reach the target number using the given numbers!",
            color=discord.Color.blue()
        )

        # Target number - big and prominent
        embed.add_field(
            name="TARGET",
            value=f"```fix\n{game.target}\n```",
            inline=False
        )

        # Available numbers - format nicely
        large_str = "  ".join([f"**{n}**" for n in game.large_numbers])
        small_str = "  ".join([f"**{n}**" for n in game.small_numbers])

        embed.add_field(
            name="Large Numbers",
            value=large_str,
            inline=True
        )
        embed.add_field(
            name="Small Numbers",
            value=small_str,
            inline=True
        )

        embed.add_field(name="\u200b", value="\u200b", inline=False)  # Spacer

        # Rules reminder
        embed.add_field(
            name="Rules",
            value=(
                "Use `+` `-` `*` `/` and parentheses `()`\n"
                "Each number can only be used **ONCE**\n"
                "Submit with: `!answer <expression>`"
            ),
            inline=False
        )

        # Time remaining
        embed.add_field(
            name="Time Limit",
            value="**30 seconds**",
            inline=True
        )

        embed.set_footer(text=f"Started by {started_by.display_name}")
        embed.timestamp = discord.utils.utcnow()

        return embed

    def _create_results_embed(self, game, submissions: list, solver_result=None) -> discord.Embed:
        """Create the game results embed."""
        winners = self.countdown_game.determine_winners(submissions)

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

                embed.add_field(
                    name=f"{medal} #{i+1}",
                    value=f"{user_mention}\n`{sub.expression}` = {sub.result}\n({status})",
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
