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
        
        # Initialize AI clients
        self.ai_clients = {
            "claude": AnthropicClient(config.anthropic_api_key),
            "gpt4": OpenAIClient(config.openai_api_key),
            "gemini": GoogleAIClient(config.google_api_key),
        }
        # Keep image client separate for direct access
        self.image_client = ReplicateClient(config.replicate_api_token)

        # Register commands
        self.add_commands()

    async def has_permissions(self, ctx) -> bool:
        """Check if user has required permissions (admin or bot owner)"""
        return (
            ctx.author.id == self.owner_id or
            (ctx.guild and ctx.author.guild_permissions.administrator)
        )

    def add_commands(self):
        @self.command(name='setchan')
        async def set_channel(ctx):
            if not await self.has_permissions(ctx):
                await ctx.send("You need administrator permissions or need to be the bot owner to use this command.")
                return
            
            self.redis_client.set_allowed_channel(
                str(ctx.guild.id), 
                str(ctx.channel.id)
            )
            await ctx.send(f"AI bot will now respond in this channel only.")

        @self.command(name='setmodel')
        async def set_model(ctx, model: str):
            if not await self.has_permissions(ctx):
                await ctx.send("You need administrator permissions or need to be the bot owner to use this command.")
                return

            if model not in self.ai_clients:
                await ctx.send(f"Invalid model. Available models: {', '.join(self.ai_clients.keys())}")
                return
            
            self.redis_client.set_server_model(str(ctx.guild.id), model)
            await ctx.send(f"AI model set to {model}")

        @self.command(name='image')
        async def generate_image(ctx, *, prompt: str):
            """Generate an image from a text prompt using Replicate API"""
            try:
                async with ctx.typing():
                    # Generate the image
                    image_data = await self.image_client.generate_image(prompt)
                    if not image_data:
                        await ctx.send("Failed to generate image. Please try again.")
                        return

                    # Create Discord file object
                    file = discord.File(
                        io.BytesIO(image_data), 
                        filename="generated_image.png"
                    )
                    
                    # Send the image with the original prompt
                    await ctx.send(
                        f"Generated image for prompt: '{prompt}'",
                        file=file
                    )
            except Exception as e:
                await ctx.send(f"Error generating image: {str(e)}")

        @self.command(name='setrole')
        async def set_role(ctx, role: str):
            if not await self.has_permissions(ctx):
                await ctx.send("You need administrator permissions or need to be the bot owner to use this command.")
                return

            if role not in self.config.roles:
                await ctx.send(f"Invalid role. Available roles: {', '.join(self.config.roles.keys())}")
                return
            
            self.redis_client.set_server_role(str(ctx.guild.id), role)
            await ctx.send(f"AI role set to {role}")

        @self.command(name='listroles')
        async def list_roles(ctx):
            roles_info = "\n".join([
                f"**{role_id}**: {role.description}"
                for role_id, role in self.config.roles.items()
            ])
            await ctx.send(f"Available roles:\n{roles_info}")

        @self.command(name='listmodels')
        async def list_models(ctx):
            models_info = ", ".join(self.ai_clients.keys())
            await ctx.send(f"Available models: {models_info}")

        @self.command(name='status')
        async def status(ctx):
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

        @self.command(name='shutdown')
        async def shutdown(ctx):
            if ctx.author.id != self.owner_id:
                await ctx.send("Only the bot owner can use this command.")
                return
            
            await ctx.send("Shutting down...")
            await self.close()

        @self.command(name='listservers')
        async def list_servers(ctx):
            if ctx.author.id != self.owner_id:
                await ctx.send("Only the bot owner can use this command.")
                return
            
            servers = '\n'.join([f"{guild.name} (ID: {guild.id})" for guild in self.guilds])
            await ctx.send(f"Currently active in these servers:\n{servers}")

        @self.command(name='leaveserver')
        async def leave_server(ctx, server_id: str):
            if ctx.author.id != self.owner_id:
                await ctx.send("Only the bot owner can use this command.")
                return
            
            guild = self.get_guild(int(server_id))
            if guild:
                await guild.leave()
                await ctx.send(f"Left server: {guild.name}")
            else:
                await ctx.send("Server not found.")

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
                    timeout=60.0
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
