import pytest
from app.game.models.character import Faction, CharacterStatus
from app.services.character_service import character_service
from app.game.combat.combat_service import combat_service


@pytest.mark.asyncio
async def test_authoritative_combat_and_damage(test_db):
    """Verify combat attack rolls, damage application, and HP reduction."""
    attacker = await character_service.create_character(
        user_id="combatant_1",
        name="Swashbuckler",
        faction=Faction.PIRATE
    )
    defender = await character_service.create_character(
        user_id="combatant_2",
        name="Target Dummy",
        faction=Faction.INDEPENDENT
    )

    res = await combat_service.resolve_attack(
        attacker_id=attacker.character_id,
        defender_id=defender.character_id,
        is_lethal=False
    )

    assert "hit" in res
    if res["hit"]:
        assert res["damage"] > 0
        reloaded_def = await character_service.get_active_character_by_user("combatant_2")
        assert reloaded_def.health < 100


@pytest.mark.asyncio
async def test_lethal_combat_permadeath_and_wanted_escalation(test_db):
    """Verify lethal fatal blow triggers permadeath and escalates attacker wanted level & bounty."""
    pirate = await character_service.create_character(
        user_id="pirate_slayer_1",
        name="Captain Blood",
        faction=Faction.PIRATE
    )
    marine = await character_service.create_character(
        user_id="marine_victim_1",
        name="Patrol Officer",
        faction=Faction.MARINE
    )

    # Set victim to low HP (10) so next blow is guaranteed fatal
    await test_db.characters.update_one({"_id": marine.character_id}, {"$set": {"health": 10}})

    res = await combat_service.resolve_attack(
        attacker_id=pirate.character_id,
        defender_id=marine.character_id,
        is_lethal=True
    )

    if res["hit"]:
        assert res["permadeath"] is True
        # Verify Marine is DEAD permanently
        dead_doc = await test_db.characters.find_one({"_id": marine.character_id})
        assert dead_doc["status"] == CharacterStatus.DEAD.value

        # Verify Attacker Wanted Escalation
        reloaded_pirate = await character_service.get_active_character_by_user("pirate_slayer_1")
        assert reloaded_pirate.wanted_level >= 1
        assert reloaded_pirate.bounty >= 75000
