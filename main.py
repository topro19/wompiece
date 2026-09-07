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


import aiohttp
from app.game.simulation.scheduler_service import simulation_scheduler


async def keep_alive_loop():
    """
    Continuous background pulse executing every 5 seconds.
    Maintains CPU activity and self-pings the HTTP server so Render never sleeps or idles.
    """
    tick = 0
    external_url = os.environ.get("RENDER_EXTERNAL_URL")
    port = os.environ.get("PORT")

    logger.info("Keep-Alive pulse loop started (5-second cadence).")
    await asyncio.sleep(5)

    while True:
        try:
            tick += 1
            # 1. Background CPU activity: execute simulation high tick
            if db_manager.db:
                await simulation_scheduler.tick_high()

            # 2. Self-ping HTTP server every 60 seconds if hosted on Render to prevent idle spin-down
            if tick % 12 == 0:  # 12 * 5s = 60 seconds
                target_url = None
                if external_url:
                    target_url = f"{external_url.rstrip('/')}/healthz"
                elif port:
                    target_url = f"http://127.0.0.1:{port}/healthz"

                if target_url:
                    try:
                        async with aiohttp.ClientSession() as session:
                            async with session.get(target_url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                                if resp.status == 200:
                                    logger.debug(f"[KEEP-ALIVE] Pinged {target_url} successfully (HTTP 200).")
                    except Exception as e:
                        logger.debug(f"[KEEP-ALIVE] Ping attempt: {e}")

            if tick % 60 == 0:  # Every 5 minutes log health
                logger.info(f"[KEEP-ALIVE] Engine active. 5s pulses completed: {tick}. Bot: {bot.user}")

        except Exception as e:
            logger.warning(f"[KEEP-ALIVE] Pulse exception: {e}")

        await asyncio.sleep(5)


async def run_bot():
    """Starts the persistent world server, health server, keep-alive pulse, and Discord bot."""
    await start_web_server()
    asyncio.create_task(keep_alive_loop())

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
