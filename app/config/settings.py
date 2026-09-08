from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Discord Credentials
    DISCORD_TOKEN: str = "mock_discord_token"
    DISCORD_GUILD_ID: Optional[str] = None

    # Database Settings
    MONGO_URI: str = "mongodb://localhost:27017"
    MONGO_DB_NAME: str = "pirate_wars"
    USE_MOCK_DB: bool = False

    # AI Settings (Gemini & Gemma models)
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL_FAST: str = "gemini-3.5-flash-lite"
    GEMINI_MODEL_REASONING: str = "gemini-3.1-flash-lite"
    AI_FALLBACK_MODELS: list[str] = [
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemma-4-31b-it",
        "gemma-4-26b-a4b-it",
    ]

    # Simulation Parameters
    WORLD_TICK_INTERVAL_SECONDS: int = 60
    SIMULATION_POPULATION_AI_PIRATES: int = 50
    SIMULATION_POPULATION_AI_MARINES: int = 70
    SIMULATION_POPULATION_AI_MERCHANTS: int = 40
    SIMULATION_POPULATION_AI_CIVILIANS: int = 300

    # Operational Flags
    LOG_LEVEL: str = "INFO"
    DEBUG_MODE: bool = False


settings = Settings()
