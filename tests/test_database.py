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


@pytest.mark.asyncio
async def test_database_snapshot_persistence(test_db):
    """Verify that player data survives restart by saving and reloading disk snapshots."""
    # 1. Insert player data
    await db_manager.db.characters.insert_one({"_id": "persisted_char_1", "name": "Captain Black", "wealth": 500})
    
    # 2. Save snapshot to disk
    await db_manager.save_local_snapshot()

    # 3. Simulate process restart by clearing mock memory
    await db_manager.db.characters.delete_many({})
    assert await db_manager.db.characters.find_one({"_id": "persisted_char_1"}) is None

    # 4. Restore from snapshot
    await db_manager.load_local_snapshot()

    # 5. Verify restored
    restored = await db_manager.db.characters.find_one({"_id": "persisted_char_1"})
    assert restored is not None
    assert restored["name"] == "Captain Black"
    assert restored["wealth"] == 500
