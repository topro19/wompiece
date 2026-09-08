import os
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from bson import json_util
from app.config.settings import settings
from app.services.logger import logger

try:
    from mongomock_motor import AsyncMongoMockClient
except ImportError:
    AsyncMongoMockClient = None

SNAPSHOT_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "local_db_snapshot.json"
)


class DatabaseManager:
    """Manages asynchronous MongoDB connection lifecycle and collection access with persistent disk snapshot fallback."""

    def __init__(self):
        self._client: Optional[AsyncIOMotorClient] = None
        self._db: Optional[AsyncIOMotorDatabase] = None
        self._is_mock: bool = False

    async def connect(self, force_mock: bool = False) -> AsyncIOMotorDatabase:
        """Connects to MongoDB or initializes a disk-persisted mock client."""
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
            if not force_mock:
                await self.load_local_snapshot()
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
            logger.warning(f"Could not connect to MongoDB ({e}). Falling back to disk-persisted AsyncMongoMockClient.")
            if AsyncMongoMockClient is not None:
                self._client = AsyncMongoMockClient()
                self._db = self._client[settings.MONGO_DB_NAME]
                self._is_mock = True
                if not force_mock:
                    await self.load_local_snapshot()
            else:
                raise e

        return self._db

    async def load_local_snapshot(self):
        """Restores database collections from disk snapshot if running in local fallback mode."""
        if not self._is_mock or self._db is None or not os.path.exists(SNAPSHOT_FILE):
            return
        try:
            with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
                raw = f.read().strip()
                if not raw:
                    return
                data = json_util.loads(raw)
            total_docs = 0
            for col_name, docs in data.items():
                if docs:
                    await self._db[col_name].delete_many({})
                    await self._db[col_name].insert_many(docs)
                    total_docs += len(docs)
            logger.info(f"[DB PERSISTENCE] Loaded {len(data)} collections ({total_docs} records) from local disk snapshot ({SNAPSHOT_FILE}).")
        except Exception as e:
            logger.warning(f"[DB PERSISTENCE] Failed to load local disk snapshot: {e}")

    async def save_local_snapshot(self):
        """Serializes current mock database state to local disk so player data survives process restarts."""
        if not self._is_mock or self._db is None:
            return
        try:
            os.makedirs(os.path.dirname(SNAPSHOT_FILE), exist_ok=True)
            col_names = await self._db.list_collection_names()
            if not col_names:
                return

            data = {}
            for col in col_names:
                cursor = self._db[col].find({})
                docs = await cursor.to_list(length=10000)
                data[col] = docs

            raw = json_util.dumps(data, indent=2)
            tmp_file = f"{SNAPSHOT_FILE}.tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                f.write(raw)
            if os.path.exists(SNAPSHOT_FILE):
                os.replace(tmp_file, SNAPSHOT_FILE)
            else:
                os.rename(tmp_file, SNAPSHOT_FILE)
            logger.debug(f"[DB PERSISTENCE] Saved local snapshot with {len(col_names)} collections to {SNAPSHOT_FILE}.")
        except Exception as e:
            logger.warning(f"[DB PERSISTENCE] Failed to save local disk snapshot: {e}")

    async def disconnect(self):
        """Saves disk snapshot and closes MongoDB connection."""
        if self._is_mock:
            await self.save_local_snapshot()
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
