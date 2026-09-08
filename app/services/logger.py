import logging
import sys
from app.config.settings import settings


def setup_logger(name: str = "pirate_wars") -> logging.Logger:
    """Configures and returns a structured logger for the game engine."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
        logger.setLevel(log_level)

        # Also configure discord logger to send warnings/errors to stdout
        discord_logger = logging.getLogger("discord")
        if not discord_logger.handlers:
            discord_logger.addHandler(handler)
            discord_logger.setLevel(logging.WARNING)

    return logger


logger = setup_logger()

