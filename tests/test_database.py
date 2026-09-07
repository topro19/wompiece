import pytest
from app.database.connection import db_manager


@pytest.mark.asyncio
async def test_database_connection(test_db):
    """Verify database connection is active and can perform CRUD."""
    assert db_manager.db is not None
    await db_manager.db.test_collection.insert_one({"test": "value"})
    result = await db_manager.db.test_collection.find_one({"test": "value"})
    assert result is not None
    assert result["test"] == "value"
