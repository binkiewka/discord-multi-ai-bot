import asyncio
import os
from dotenv import load_dotenv
from bot import AIBot
from config.config import Config

async def main():
    # Load environment variables
    load_dotenv()
    
    try:
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
