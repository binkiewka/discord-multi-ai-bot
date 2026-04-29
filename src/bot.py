import discord
print(">>> BOT.PY VERSION: 2024-12-11-v4-AUTO-CREATE <<<", flush=True)
import io
from collections import deque
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

from utils.helpers import send_chunked_message



class AIBot(commands.Bot):
    def __init__(self, config: Config):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True
        intents.guild_messages = True

        super().__init__(command_prefix="!", intents=intents)
        print("Initializing AIBot...", flush=True)
        self.config = config
        self.redis_client = RedisClient(config.redis_host, config.redis_port)
        self.owner_id = int(config.owner_id)

        # Message deduplication buffer
        self.processed_messages = deque(maxlen=100)

        # Initialize AI clients
        # Keys are the model identifiers used in !setmodel / !setdefaultmodel commands
        self.ai_clients = {
            "claude": AnthropicClient(config.anthropic_api_key),    # claude-haiku-4-5
            "gpt4mini": OpenAIClient(config.openai_api_key),        # gpt-4.1-mini
            "gemini": GoogleAIClient(config.google_api_key),        # gemini-3.1-flash-lite-preview
            # Image generation clients
            "flux": FluxClient(config.replicate_api_token),
            "fluxpro": FluxProClient(config.replicate_api_token),
            "recraft": ReCraftClient(config.replicate_api_token)
        }

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
        }
        print("AIBot initialization complete.", flush=True)

    async def setup_hook(self):
        self._setup_hook_ran = True
        print("Executing setup_hook...", flush=True)
        self.add_commands()

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})", flush=True)
        print("------", flush=True)

        if not hasattr(self, '_setup_hook_ran'):
            print("Warning: setup_hook did not run! Syncing tree from on_ready...", flush=True)
            try:
                await self.tree.sync()
                print("Command tree synced from on_ready.", flush=True)
            except Exception as e:
                print(f"Failed to sync tree from on_ready: {e}", flush=True)

        if not hasattr(self, '_custom_sync_ran'):
            pass

        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="for mentions | !help"
            )
        )

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
        print(f"DEBUG: add_commands called, registering {len(self.command_handlers)} commands", flush=True)

        for cmd_name, handler in self.command_handlers.items():
            print(f"DEBUG: Registering command: {cmd_name}", flush=True)

            def make_callback(h):
                async def callback(ctx, *, arg=None):
                    print(f"DEBUG: Command callback invoked by {ctx.author}", flush=True)
                    if arg is None:
                        await h(ctx)
                    else:
                        await h(ctx, arg)
                return callback

            cmd = commands.Command(make_callback(handler), name=cmd_name)
            self.add_command(cmd)

        print(f"DEBUG: Total commands registered: {len(self.commands)}", flush=True)
        for c in self.commands:
            print(f"DEBUG: - {c}", flush=True)

    async def _handle_add_channel(self, ctx, channel_arg=None):
        """Handle the addchan command - adds channel to allowed channels"""
        if not await self.has_permissions(ctx):
            await ctx.send("You need administrator permissions or need to be the bot owner to use this command.")
            return

        server_id = str(ctx.guild.id)
        self.redis_client.migrate_single_to_multi_channel(server_id)

        if channel_arg:
            channel_id = channel_arg.strip('<>#')
            try:
                channel = ctx.guild.get_channel(int(channel_id))
                if not channel:
                    await ctx.send(f"Channel not found. Please provide a valid channel mention or ID.")
                    return
                channel_id = str(channel.id)
            except ValueError:
                await ctx.send(f"Invalid channel format. Use #channel-name or channel ID.")
                return
        else:
            channel_id = str(ctx.channel.id)

        self.redis_client.add_allowed_channel(server_id, channel_id)
        await ctx.send(f"AI bot will now respond in <#{channel_id}>.")

    async def _handle_mute_channel(self, ctx, channel_arg=None):
        """Handle the mute command - removes channel from allowed channels"""
        if not await self.has_permissions(ctx):
            await ctx.send("You need administrator permissions or need to be the bot owner to use this command.")
            return

        server_id = str(ctx.guild.id)
        self.redis_client.migrate_single_to_multi_channel(server_id)

        if channel_arg:
            channel_id = channel_arg.strip('<>#')
            try:
                channel = ctx.guild.get_channel(int(channel_id))
                if not channel:
                    await ctx.send(f"Channel not found. Please provide a valid channel mention or ID.")
                    return
                channel_id = str(channel.id)
            except ValueError:
                await ctx.send(f"Invalid channel format. Use #channel-name or channel ID.")
                return
        else:
            channel_id = str(ctx.channel.id)

        self.redis_client.remove_allowed_channel(server_id, channel_id)
        await ctx.send(f"AI bot will no longer respond in <#{channel_id}>.")

    async def _handle_list_channels(self, ctx):
        """Handle the listchans command - lists all allowed channels"""
        if not await self.has_permissions(ctx):
            await ctx.send("You need administrator permissions or need to be the bot owner to use this command.")
            return

        server_id = str(ctx.guild.id)
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

        parts = args.split()
        if len(parts) == 0:
            await ctx.send(f"Please specify a model. Available models: {', '.join(self.ai_clients.keys())}")
            return

        model = parts[0]
        target_channel = None

        if model not in self.ai_clients:
            await ctx.send(f"Invalid model. Available models: {', '.join(self.ai_clients.keys())}")
            return

        if len(parts) > 1:
            channel_arg = parts[1].strip('<>#')
            try:
                target_channel = ctx.guild.get_channel(int(channel_arg))
                if not target_channel:
                    await ctx.send(f"Channel not found. Please provide a valid channel mention or ID.")
                    return
            except ValueError:
                await ctx.send(f"Invalid channel format. Use #channel-name or channel ID.")
                return
        else:
            target_channel = ctx.channel

        server_id = str(ctx.guild.id)
        channel_id = str(target_channel.id)
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

        parts = args.split()
        if len(parts) == 0:
            await ctx.send(f"Please specify a role. Available roles: {', '.join(self.config.roles.keys())}")
            return

        role = parts[0]
        target_channel = None

        if role not in self.config.roles:
            await ctx.send(f"Invalid role. Available roles: {', '.join(self.config.roles.keys())}")
            return

        if len(parts) > 1:
            channel_arg = parts[1].strip('<>#')
            try:
                target_channel = ctx.guild.get_channel(int(channel_arg))
                if not target_channel:
                    await ctx.send(f"Channel not found. Please provide a valid channel mention or ID.")
                    return
            except ValueError:
                await ctx.send(f"Invalid channel format. Use #channel-name or channel ID.")
                return
        else:
            target_channel = ctx.channel

        server_id = str(ctx.guild.id)
        channel_id = str(target_channel.id)
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
        model_descriptions = {
            "claude":   "Claude Haiku 4.5 (Anthropic) — fast & efficient",
            "gpt4mini": "GPT-4.1 Mini (OpenAI) — smart & cost-effective",
            "gemini":   "Gemini 3.1 Flash-Lite Preview (Google) — lightweight & quick",
        }
        lines = [f"**{key}** — {desc}" for key, desc in model_descriptions.items()
                 if key in self.ai_clients and key not in ("flux", "fluxpro", "recraft")]
        await ctx.send("Available models:\n" + "\n".join(lines))

    async def _handle_set_default_model(self, ctx, model=None):
        """Handle the setdefaultmodel command - sets server-wide default model"""
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
        """Handle the setdefaultrole command - sets server-wide default role"""
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
        """Handle the channelconfig command"""
        server_id = str(ctx.guild.id)
        target_channel = None

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
            target_channel = ctx.channel

        channel_id = str(target_channel.id)

        channel_role_raw = self.redis_client.redis.get(f"channel_role:{server_id}:{channel_id}")
        server_role_raw = self.redis_client.redis.get(f"role:{server_id}")
        effective_role = self.redis_client.get_channel_role(server_id, channel_id)

        channel_model_raw = self.redis_client.redis.get(f"channel_model:{server_id}:{channel_id}")
        server_model_raw = self.redis_client.redis.get(f"model:{server_id}")
        effective_model = self.redis_client.get_channel_model(server_id, channel_id)

        role_source = "channel-specific" if channel_role_raw else ("server-wide fallback" if server_role_raw else "default fallback")
        model_source = "channel-specific" if channel_model_raw else ("server-wide fallback" if server_model_raw else "default fallback")

        config_message = (
            f"**Configuration for <#{channel_id}>:**\n"
            f"• **Role:** {effective_role} ({role_source})\n"
            f"• **Model:** {effective_model} ({model_source})"
        )
        await ctx.send(config_message)

    async def _handle_clear_channel_config(self, ctx, args=None):
        """Handle the clearchannelconfig command"""
        if not await self.has_permissions(ctx):
            await ctx.send("You need administrator permissions or need to be the bot owner to use this command.")
            return

        server_id = str(ctx.guild.id)
        target_channel = None

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
            target_channel = ctx.channel

        channel_id = str(target_channel.id)
        self.redis_client.clear_channel_role(server_id, channel_id)
        self.redis_client.clear_channel_model(server_id, channel_id)
        await ctx.send(f"Channel-specific settings cleared for <#{channel_id}>. Now using server-wide settings.")

    async def _handle_status(self, ctx):
        """Handle the status command"""
        if not await self.has_permissions(ctx):
            await ctx.send("You need administrator, moderator, or bot owner permissions to use this command.")
            return

        server_id = str(ctx.guild.id)
        self.redis_client.migrate_single_to_multi_channel(server_id)

        default_model = self.redis_client.get_default_model(server_id)
        default_role = self.redis_client.get_default_role(server_id)
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
        """Handle image generation commands"""
        if prompt is None:
            await ctx.send(f"Please provide a prompt for the {model} image generation.")
            return

        async with ctx.typing():
            try:
                image_client = self.ai_clients.get(model)
                if not image_client:
                    await ctx.send(f"The {model} image generation service is not properly configured.")
                    return

                image_data = await image_client.generate_image(prompt)

                if image_data:
                    file = discord.File(
                        io.BytesIO(image_data),
                        filename=f"{model}_generated.png"
                    )
                    await ctx.send("Here's your image:", file=file)
                else:
                    await ctx.send(f"Failed to generate image with {model}.")
            except Exception as e:
                print(f"Error generating image with {model}: {str(e)}")
                await ctx.send(f"Error generating image with {model}: {str(e)}")

    async def get_ai_response(self,
                              server_id: str,
                              channel_id: str,
                              user_id: str,
                              message: str) -> Optional[str]:
        """Get AI response for a message"""
        self.redis_client.migrate_single_to_multi_channel(server_id)

        if not self.redis_client.is_channel_allowed(server_id, channel_id):
            return None

        channel = self.get_channel(int(channel_id))
        async with channel.typing():
            model = self.redis_client.get_channel_model(server_id, channel_id)
            role_id = self.redis_client.get_channel_role(server_id, channel_id)
            role: Role = self.config.roles[role_id]
            context = self.redis_client.get_context(server_id, channel_id)

            try:
                ai_client = self.ai_clients[model]
                response = await asyncio.wait_for(
                    ai_client.generate_response(
                        role.system_prompt,
                        context,
                        message
                    ),
                    timeout=120.0
                )

                self.redis_client.add_to_context(
                    server_id, channel_id, user_id, message, response
                )

                return response
            except asyncio.TimeoutError:
                return "I apologize, but the response took too long. Please try again."
            except Exception as e:
                print(f"Error generating response: {str(e)}")
                return f"Error generating response: {str(e)}"

    async def on_guild_join(self, guild):
        print(f"Joined new guild: {guild.name} (ID: {guild.id})")

    async def on_message(self, message: discord.Message):
        print(f"DEBUG: on_message called for msg_id={message.id} from {message.author}: {message.content[:50]}", flush=True)

        if message.author == self.user:
            return

        if message.id in self.processed_messages:
            return
        self.processed_messages.append(message.id)

        await self.process_commands(message)

        if self.user not in message.mentions:
            return

        print(f"DEBUG: Bot mentioned by {message.author}. content={message.content}", flush=True)

        content = message.content.replace(f'<@{self.user.id}>', '').strip()

        print(f"DEBUG: Requesting AI response for: {content}", flush=True)
        response = await self.get_ai_response(
            str(message.guild.id),
            str(message.channel.id),
            str(message.author.id),
            content
        )
        print(f"DEBUG: AI Response received: {bool(response)}", flush=True)

        if response:
            await send_chunked_message(message.channel, response, reference=message)
