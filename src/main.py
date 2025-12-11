import asyncio
import os
import logging
import discord
from dotenv import load_dotenv
from bot import AIBot
from config.config import Config

async def main():
    # Load environment variables
    load_dotenv()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Set higher logging level for noisy libraries if needed
    # logging.getLogger('discord').setLevel(logging.DEBUG)

    try:
        print(f"Discord.py Version: {discord.__version__}", flush=True)
        config = Config()
        bot = AIBot(config)
        print("Starting bot...", flush=True)
        print(f"Token present: {bool(config.discord_token)}", flush=True)
        await bot.start(config.discord_token)
        print("Bot start returned (unexpected)", flush=True)
    except Exception as e:
        print(f"Error starting bot: {e}", flush=True)
        raise

if __name__ == "__main__":
    asyncio.run(main())
