import pytest
import pytest_asyncio
import os
from app.config.settings import settings
from app.database.connection import db_manager


@pytest_asyncio.fixture(autouse=True)
async def test_db():
    """Initializes a fresh in-memory mock database for each test session."""
    settings.USE_MOCK_DB = True
    db = await db_manager.connect(force_mock=True)
    # Clear collections before test
    collections = await db.list_collection_names()
    for col in collections:
        await db[col].delete_many({})
    yield db
    await db_manager.disconnect()
