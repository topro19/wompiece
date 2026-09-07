import asyncio
from app.config.settings import settings
from app.discord.bot import bot
from app.services.logger import logger
from app.database.connection import db_manager


async def run_bot():
    """Starts the persistent world server and Discord bot."""
    if not settings.DISCORD_TOKEN or settings.DISCORD_TOKEN == "mock_discord_token":
        logger.warning(
            "DISCORD_TOKEN is not set or using mock token. Bot will initialize database and run health-check in standalone mode."
        )
        await db_manager.connect()
        logger.info(f"Database connected successfully (is_mock={db_manager.is_mock}). Engine is ready.")
        await db_manager.disconnect()
        return

    logger.info("Starting Pirate Wars Discord Client...")
    await bot.start(settings.DISCORD_TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("Server received interrupt signal. Shutting down gracefully.")
