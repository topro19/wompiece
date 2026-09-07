import pytest
from app.database.connection import db_manager
from app.game.economy.ledger import ledger, TransactionError
from app.game.models.character import Character, Faction


@pytest.mark.asyncio
async def test_ledger_mint_and_transfer(test_db):
    """Verify minting funds and double-entry player-to-player transfers."""
    db = db_manager.db

    # Create two characters
    p1 = Character(name="Pirate Jack", faction=Faction.PIRATE, wealth=100)
    p2 = Character(name="Merchant John", faction=Faction.MERCHANT, wealth=50)
    await db.characters.insert_one(p1.to_mongo())
    await db.characters.insert_one(p2.to_mongo())

    # Transfer 40 gold from p1 to p2
    tx = await ledger.transfer(
        sender_id=p1.character_id,
        receiver_id=p2.character_id,
        amount=40,
        reason="Purchase of navigation charts",
        idempotency_key="tx_test_001"
    )
    assert tx is not None

    # Check updated balances
    updated_p1 = await db.characters.find_one({"_id": p1.character_id})
    updated_p2 = await db.characters.find_one({"_id": p2.character_id})
    assert updated_p1["wealth"] == 60
    assert updated_p2["wealth"] == 90


@pytest.mark.asyncio
async def test_ledger_insufficient_funds(test_db):
    """Verify that ledger rejects transfers exceeding balance."""
    db = db_manager.db
    p1 = Character(name="Poor Sailor", faction=Faction.PIRATE, wealth=20)
    p2 = Character(name="Tavern Keeper", faction=Faction.MERCHANT, wealth=0)
    await db.characters.insert_one(p1.to_mongo())
    await db.characters.insert_one(p2.to_mongo())

    with pytest.raises(TransactionError, match="Insufficient funds"):
        await ledger.transfer(
            sender_id=p1.character_id,
            receiver_id=p2.character_id,
            amount=50,
            reason="Extravagant Rum Order",
            idempotency_key="tx_fail_002"
        )


@pytest.mark.asyncio
async def test_ledger_idempotency(test_db):
    """Verify duplicate transaction keys do not deduct multiple times."""
    db = db_manager.db
    p1 = Character(name="Captain Vance", faction=Faction.PIRATE, wealth=200)
    p2 = Character(name="Quartermaster", faction=Faction.PIRATE, wealth=0)
    await db.characters.insert_one(p1.to_mongo())
    await db.characters.insert_one(p2.to_mongo())

    key = "idempotent_tx_unique_99"
    # First attempt
    tx1 = await ledger.transfer(
        sender_id=p1.character_id,
        receiver_id=p2.character_id,
        amount=50,
        reason="Crew share",
        idempotency_key=key
    )

    # Second duplicate attempt
    tx2 = await ledger.transfer(
        sender_id=p1.character_id,
        receiver_id=p2.character_id,
        amount=50,
        reason="Crew share replay",
        idempotency_key=key
    )

    assert tx1.tx_id == tx2.tx_id
    # Ensure money was only deducted ONCE
    updated_p1 = await db.characters.find_one({"_id": p1.character_id})
    assert updated_p1["wealth"] == 150
