from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.config.settings import settings
from app.services.logger import logger

try:
    from mongomock_motor import AsyncMongoMockClient
except ImportError:
    AsyncMongoMockClient = None


class DatabaseManager:
    """Manages asynchronous MongoDB connection lifecycle and collection access."""

    def __init__(self):
        self._client: Optional[AsyncIOMotorClient] = None
        self._db: Optional[AsyncIOMotorDatabase] = None
        self._is_mock: bool = False

    async def connect(self, force_mock: bool = False) -> AsyncIOMotorDatabase:
        """Connects to MongoDB or initializes an in-memory mock client."""
        if self._db is not None:
            return self._db

        use_mock = force_mock or settings.USE_MOCK_DB

        if use_mock:
            if AsyncMongoMockClient is None:
                raise RuntimeError("mongomock-motor is required for mock database mode.")
            logger.info("Initializing in-memory MongoMock database for testing/simulation.")
            self._client = AsyncMongoMockClient()
            self._db = self._client[settings.MONGO_DB_NAME]
            self._is_mock = True
            return self._db

        try:
            logger.info(f"Connecting to MongoDB at {settings.MONGO_URI} [DB: {settings.MONGO_DB_NAME}]...")
            self._client = AsyncIOMotorClient(
                settings.MONGO_URI,
                serverSelectionTimeoutMS=2000,
                uuidRepresentation="standard"
            )
            self._db = self._client[settings.MONGO_DB_NAME]
            # Ping database to verify connection
            await self._client.admin.command("ping")
            logger.info("Successfully established connection to MongoDB.")
            self._is_mock = False
        except Exception as e:
            logger.warning(f"Could not connect to MongoDB ({e}). Falling back to AsyncMongoMockClient.")
            if AsyncMongoMockClient is not None:
                self._client = AsyncMongoMockClient()
                self._db = self._client[settings.MONGO_DB_NAME]
                self._is_mock = True
            else:
                raise e

        return self._db

    async def disconnect(self):
        """Closes MongoDB connection."""
        if self._client:
            self._client.close()
            self._client = None
            self._db = None
            logger.info("Disconnected from MongoDB.")

    @property
    def db(self) -> AsyncIOMotorDatabase:
        if self._db is None:
            raise RuntimeError("Database is not connected. Call `await db_manager.connect()` first.")
        return self._db

    @property
    def is_mock(self) -> bool:
        return self._is_mock


db_manager = DatabaseManager()
