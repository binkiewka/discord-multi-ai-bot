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
        print("Starting bot...")
        await bot.start(config.discord_token)
    except Exception as e:
        print(f"Error starting bot: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
