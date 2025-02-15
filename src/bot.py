import discord
from discord.ext import commands
from typing import Optional
import asyncio
from config.config import Config, Role
from db.redis_client import RedisClient
from ai.anthropic_client import AnthropicClient
from ai.openai_client import OpenAIClient
from ai.google_client import GoogleAIClient
from ai.replicate_client import ReplicateClient
from utils.helpers import send_chunked_message
import io

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
        
        self.ai_clients = {
            "claude": AnthropicClient(config.anthropic_api_key),
            "gpt4": OpenAIClient(config.openai_api_key),
            "gemini": GoogleAIClient(config.google_api_key),
            "image": ReplicateClient(config.replicate_api_token)
        }

        # Command handlers dictionary
        self.command_handlers = {
            'setchan': self._handle_set_channel,
            'setmodel': self._handle_set_model,
            'setrole': self._handle_set_role,
            'listroles': self._handle_list_roles,
            'listmodels': self._handle_list_models,
            'status': self._handle_status,
            'shutdown': self._handle_shutdown,
            'listservers': self._handle_list_servers,
            'leaveserver': self._handle_leave_server,
            'image': self._handle_image
        }

    async def setup_hook(self):
        """This is called when the bot is ready to start"""
        self.add_commands()

    async def has_permissions(self, ctx) -> bool:
        """Check if user has required permissions (admin or bot owner)"""
        return (
            ctx.author.id == self.owner_id or
            (ctx.guild and ctx.author.guild_permissions.administrator)
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

    async def _handle_set_channel(self, ctx, *args):
        """Handle the setchan command"""
        if not await self.has_permissions(ctx):
            await ctx.send("You need administrator permissions or need to be the bot owner to use this command.")
            return
        
        self.redis_client.set_allowed_channel(
            str(ctx.guild.id), 
            str(ctx.channel.id)
        )
        await ctx.send(f"AI bot will now respond in this channel only.")

    async def _handle_set_model(self, ctx, model=None):
        """Handle the setmodel command"""
        if not await self.has_permissions(ctx):
            await ctx.send("You need administrator permissions or need to be the bot owner to use this command.")
            return

        if model is None:
            await ctx.send(f"Please specify a model. Available models: {', '.join(self.ai_clients.keys())}")
            return

        if model not in self.ai_clients:
            await ctx.send(f"Invalid model. Available models: {', '.join(self.ai_clients.keys())}")
            return
        
        self.redis_client.set_server_model(str(ctx.guild.id), model)
        await ctx.send(f"AI model set to {model}")

    async def _handle_set_role(self, ctx, role=None):
        """Handle the setrole command"""
        if not await self.has_permissions(ctx):
            await ctx.send("You need administrator permissions or need to be the bot owner to use this command.")
            return

        if role is None:
            await ctx.send(f"Please specify a role. Available roles: {', '.join(self.config.roles.keys())}")
            return

        if role not in self.config.roles:
            await ctx.send(f"Invalid role. Available roles: {', '.join(self.config.roles.keys())}")
            return
        
        self.redis_client.set_server_role(str(ctx.guild.id), role)
        await ctx.send(f"AI role set to {role}")

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

    async def _handle_status(self, ctx):
        """Handle the status command"""
        if not await self.has_permissions(ctx):
            await ctx.send("You need administrator permissions or need to be the bot owner to use this command.")
            return

        server_id = str(ctx.guild.id)
        current_channel = self.redis_client.get_allowed_channel(server_id)
        current_model = self.redis_client.get_server_model(server_id)
        current_role = self.redis_client.get_server_role(server_id)

        status_message = (
            f"Current configuration:\n"
            f"- Allowed Channel: <#{current_channel}>\n"
            f"- AI Model: {current_model}\n"
            f"- Role: {current_role}"
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

    async def _handle_image(self, ctx, prompt=None):
        """
        Handle the image command by generating and sending an AI-generated image.
        
        Args:
            ctx: The Discord context
            prompt: The image generation prompt
        """
        if prompt is None:
            await ctx.send("Please provide a prompt for the image generation.")
            return

        async with ctx.typing():
            try:
                # Use the image client directly
                image_client = self.ai_clients["image"]
                image_data = await image_client.generate_image(prompt)
                
                if image_data:
                    # Create Discord file object from the image bytes
                    file = discord.File(
                        io.BytesIO(image_data), 
                        filename="generated_image.png"
                    )
                    await ctx.send(
                        "Here's your image:", 
                        file=file
                    )
                else:
                    await ctx.send("Failed to generate image.")
            except Exception as e:
                print(f"Error generating image: {str(e)}")  # Log the error
                await ctx.send(f"Error generating image: {str(e)}")

    async def get_ai_response(self, 
                            server_id: str, 
                            channel_id: str,
                            user_id: str, 
                            message: str) -> Optional[str]:
        # Check if channel is allowed
        allowed_channel = self.redis_client.get_allowed_channel(server_id)
        if not allowed_channel or allowed_channel != channel_id:
            return None

        channel = self.get_channel(int(channel_id))
        async with channel.typing():  # Show typing indicator while processing
            # Get current model and role
            model = self.redis_client.get_server_model(server_id)
            role_id = self.redis_client.get_server_role(server_id)
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
        print(f"Joined new guild: {guild.name} (ID: {guild.id})")
        # You could send a welcome message to the first available channel
        # or implement other onboarding logic here

    async def on_message(self, message: discord.Message):
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
