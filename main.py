import os
import asyncio
from aiohttp import web
from app.config.settings import settings
from app.discord.bot import bot
from app.services.logger import logger
from app.database.connection import db_manager


async def health_check_handler(request: web.Request) -> web.Response:
    """HTTP Health-check endpoint for Render cloud hosting."""
    return web.json_response({
        "status": "online",
        "service": "Pirate Wars Persistent Simulation Engine",
        "bot": str(bot.user) if bot.user else "connecting..."
    })


async def start_web_server():
    """Starts a lightweight health-check web server if PORT is provided by Render."""
    port_str = os.environ.get("PORT")
    if port_str:
        try:
            port = int(port_str)
            app = web.Application()
            app.router.add_get("/", health_check_handler)
            app.router.add_get("/healthz", health_check_handler)
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, "0.0.0.0", port)
            await site.start()
            logger.info(f"Render HTTP health-check listener active on port {port}.")
        except Exception as e:
            logger.warning(f"Could not start Render health-check web server: {e}")


async def run_bot():
    """Starts the persistent world server, health server, and Discord bot."""
    await start_web_server()

    if not settings.DISCORD_TOKEN or settings.DISCORD_TOKEN == "mock_discord_token":
        logger.warning(
            "DISCORD_TOKEN is not set or using mock token. Bot will initialize database and run health-check in standalone mode."
        )
        await db_manager.connect()
        logger.info(f"Database connected successfully (is_mock={db_manager.is_mock}). Engine is ready.")
        if os.environ.get("PORT"):
            while True:
                await asyncio.sleep(3600)
        await db_manager.disconnect()
        return

    logger.info("Starting Pirate Wars Discord Client...")
    await bot.start(settings.DISCORD_TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("Server received interrupt signal. Shutting down gracefully.")
