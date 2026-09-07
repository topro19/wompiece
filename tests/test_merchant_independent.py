import pytest
from app.database.connection import db_manager
from app.game.models.character import Character, Faction
from app.services.character_service import character_service
from app.game.economy.ledger import ledger
from app.game.economy.trade_service import trade_service
from app.game.economy.trade_models import CommodityType
from app.game.economy.banking_service import banking_service
from app.game.protection.protection_service import protection_service
from app.game.protection.protection_models import ProtectedEntityType
from app.game.information.intel_service import intel_service
from app.game.information.intel_models import IntelCategory
from app.game.contracts.contract_service import contract_service
from app.game.contracts.contract_models import ContractType
from app.game.salvage.salvage_service import salvage_service


@pytest.mark.asyncio
async def test_trade_commodity_arbitrage_and_ledger():
    """Verify buying commodity low at one island and selling high for profit."""
    db = db_manager.db
    await db.characters.delete_many({})
    await db.transactions.delete_many({})

    # 1. Create merchant at Coral Bay (where Spices are cheap: buy mult 0.7 = 42g)
    merchant = await character_service.create_character(
        user_id="user_trader_1",
        name="Merchant Silvio",
        faction=Faction.MERCHANT,
        starting_location_id="coral_bay_market"
    )
    # Mint 500g capital
    await ledger.transfer(
        receiver_id=merchant.character_id,
        amount=500,
        reason="Initial trade capital",
        idempotency_key="seed_silvio_1"
    )

    # 2. Buy 5x Rare Spices at Coral Bay
    buy_res = await trade_service.buy_commodity(
        character_id=merchant.character_id,
        commodity_id=CommodityType.RARE_SPICES.value,
        quantity=5
    )
    assert buy_res["quantity"] == 5
    assert buy_res["unit_price"] == 42
    assert buy_res["total_cost"] == 210

    # 3. Simulate traveling to Port Azure Market (where Spices are prized: sell mult 1.35 = 81g)
    await db.characters.update_one(
        {"_id": merchant.character_id},
        {"$set": {"location_id": "port_azure_market"}}
    )

    # 4. Sell 5x Rare Spices at Port Azure Market
    sell_res = await trade_service.sell_commodity(
        character_id=merchant.character_id,
        commodity_id=CommodityType.RARE_SPICES.value,
        quantity=5
    )
    assert sell_res["quantity"] == 5
    assert sell_res["unit_price"] == 81
    assert sell_res["total_payout"] == 405

    # Net profit: 405 - 210 = +195g
    updated_char = await db.characters.find_one({"_id": merchant.character_id})
    assert updated_char["wealth"] == 350 + 500 - 210 + 405  # starter 350 + 500 minted + profit
    assert updated_char["reputation_merchant"] > 0


@pytest.mark.asyncio
async def test_contraband_customs_seizure_at_naval_port():
    """Verify selling illegal contraband at Port Azure risks dock seizure and Marine case."""
    db = db_manager.db

    smuggler = await character_service.create_character(
        user_id="user_smuggler_9",
        name="Shady Jack",
        faction=Faction.PIRATE,
        starting_location_id="port_azure_market"
    )
    # Give contraband opium to smuggler
    await character_service.add_item(smuggler.character_id, {
        "item_id": CommodityType.CONTRABAND_OPIUM.value,
        "name": "Smuggled Medicinal Opium",
        "type": "commodity",
        "quantity": 2,
        "is_contraband": True
    })

    # Sell at Port Azure Market (high security): detection roll triggers exception or seizure
    # Let's test until seizure or sale succeeds, asserting valid mechanics
    try:
        res = await trade_service.sell_commodity(
            character_id=smuggler.character_id,
            commodity_id=CommodityType.CONTRABAND_OPIUM.value,
            quantity=1
        )
        assert res["action"] == "SELL"
    except ValueError as ve:
        # Seizure occurred
        assert "CUSTOMS SEIZURE" in str(ve)
        updated = await db.characters.find_one({"_id": smuggler.character_id})
        assert updated["wanted_level"] >= 2


@pytest.mark.asyncio
async def test_merchant_banking_and_loan_repayment():
    """Verify merchant issuing loans with interest and borrower repayment via ledger."""
    db = db_manager.db

    banker = await character_service.create_character(
        user_id="user_banker_1",
        name="Lord Sterling",
        faction=Faction.MERCHANT,
        starting_location_id="port_azure_market"
    )
    borrower = await character_service.create_character(
        user_id="user_borrower_1",
        name="Ned the Carpenter",
        faction=Faction.INDEPENDENT,
        starting_location_id="port_azure_market"
    )

    # Give banker 2000g capital
    await ledger.transfer(
        receiver_id=banker.character_id,
        amount=2000,
        reason="Bank vaults",
        idempotency_key="banker_vault_01"
    )

    # 1. Issue 500g loan at 20% interest (Total due: 600g)
    loan = await banking_service.issue_loan(
        banker_character_id=banker.character_id,
        borrower_character_id=borrower.character_id,
        principal_amount=500,
        interest_rate_percent=20,
        duration_days=7
    )
    assert loan.principal_amount == 500
    assert loan.total_due == 600

    # Borrower received the 500g
    borrower_doc = await db.characters.find_one({"_id": borrower.character_id})
    assert borrower_doc["wealth"] == 120 + 500  # starter 120 + 500

    # 2. Borrower repays loan
    repay_res = await banking_service.repay_loan(
        loan_id=loan.loan_id,
        borrower_character_id=borrower.character_id
    )
    assert repay_res["status"] == "REPAID"
    assert repay_res["amount_paid"] == 600


@pytest.mark.asyncio
async def test_faction_protection_contract_and_retaliation():
    """Verify attacking a protected merchant triggers severe faction retaliation."""
    db = db_manager.db

    merchant = await character_service.create_character(
        user_id="user_prot_merch",
        name="Giles the Brewer",
        faction=Faction.MERCHANT,
        starting_location_id="port_azure_docks"
    )
    attacker = await character_service.create_character(
        user_id="user_aggressor",
        name="Ruthless Pete",
        faction=Faction.INDEPENDENT,
        starting_location_id="port_azure_docks"
    )

    # Give merchant funds for retainer
    await ledger.transfer(
        receiver_id=merchant.character_id,
        amount=500,
        reason="Protection dues",
        idempotency_key="prot_dues_01"
    )

    # 1. Merchant hires The Black Tide (Pirates) to protect his warehouse/self
    contract = await protection_service.create_contract(
        merchant_character_id=merchant.character_id,
        entity_type=ProtectedEntityType.INDIVIDUAL,
        entity_id=merchant.character_id,
        protector_faction=Faction.PIRATE,
        protector_id="crew_black_tide",
        protector_name="The Black Tide",
        weekly_dues=150
    )
    assert contract.status == "ACTIVE"

    # 2. Aggressor commits hostile action against protected merchant
    consequences = await protection_service.check_hostile_action(
        attacker_id=attacker.character_id,
        victim_entity_id=merchant.character_id
    )
    assert consequences is not None
    assert consequences["is_protected"] is True
    assert consequences["protector_faction"] == "PIRATE"

    # Verify attacker suffered pirate underworld penalties
    updated_attacker = await db.characters.find_one({"_id": attacker.character_id})
    assert updated_attacker["reputation_pirate"] == -50
    assert updated_attacker["bounty"] >= 250


@pytest.mark.asyncio
async def test_information_brokerage_and_intel_sale():
    """Verify informant gathering intelligence and selling it to a buyer via ledger."""
    db = db_manager.db

    informant = await character_service.create_character(
        user_id="user_informant_1",
        name="Whispering Sal",
        faction=Faction.INDEPENDENT,
        starting_location_id="the_crimson_parrot"
    )
    buyer = await character_service.create_character(
        user_id="user_intel_buyer",
        name="Captain Vane",
        faction=Faction.PIRATE,
        starting_location_id="the_crimson_parrot"
    )
    await ledger.transfer(
        receiver_id=buyer.character_id,
        amount=500,
        reason="Intel budget",
        idempotency_key="buyer_budget_01"
    )

    # 1. Gather intelligence
    intel = await intel_service.gather_intel(
        character_id=informant.character_id,
        category=IntelCategory.MARINE_PATROL
    )
    assert intel.intel_id.startswith("intel_")
    assert intel.reliability > 0.8

    # 2. Sell intelligence to Captain Vane
    sale_res = await intel_service.sell_intel(
        intel_id=intel.intel_id,
        seller_character_id=informant.character_id,
        buyer_character_id=buyer.character_id,
        negotiated_price=120
    )
    assert sale_res["price_paid"] == 120
    assert sale_res["buyer"] == "Captain Vane"


@pytest.mark.asyncio
async def test_contract_board_escrow_and_completion():
    """Verify dynamic contract posting with escrow lock, acceptance, and completion payout."""
    db = db_manager.db

    issuer = await character_service.create_character(
        user_id="user_issuer_guild",
        name="Guildmaster Thorne",
        faction=Faction.MERCHANT,
        starting_location_id="port_azure_market"
    )
    hunter = await character_service.create_character(
        user_id="user_hunter_merc",
        name="Grimm the Hunter",
        faction=Faction.INDEPENDENT,
        starting_location_id="port_azure_market"
    )

    await ledger.transfer(
        receiver_id=issuer.character_id,
        amount=1000,
        reason="Contract budget",
        idempotency_key="contract_fund_01"
    )

    # 1. Post Delivery Contract (Reward: 400g locked in escrow)
    contract = await contract_service.post_contract(
        issuer_character_id=issuer.character_id,
        contract_type=ContractType.DELIVERY,
        title="Deliver 2x Seasoned Oak Timber",
        reward_amount=400,
        description="Urgent repairs needed on warehouse wharf.",
        required_item_id="timber",
        required_quantity=2
    )
    assert contract.status == "OPEN"
    assert contract.reward_amount == 400

    # 2. Hunter accepts contract
    accepted = await contract_service.accept_contract(
        contract_id=contract.contract_id,
        contractor_character_id=hunter.character_id
    )
    assert accepted.status == "ACCEPTED"
    assert accepted.assigned_contractor_id == hunter.character_id

    # 3. Hunter acquires the required timber
    await character_service.add_item(hunter.character_id, {
        "item_id": "timber",
        "name": "Seasoned Oak Timber",
        "quantity": 2,
        "type": "commodity"
    })

    # 4. Complete contract -> releases 400g escrow to hunter
    complete_res = await contract_service.complete_contract(
        contract_id=contract.contract_id,
        contractor_character_id=hunter.character_id
    )
    assert complete_res["reward_amount"] == 400

    # Verify hunter wallet received the 400g
    hunter_doc = await db.characters.find_one({"_id": hunter.character_id})
    assert hunter_doc["wealth"] == 120 + 400  # starter 120 + 400 reward


@pytest.mark.asyncio
async def test_salvage_exploration_and_moral_choices():
    """Verify discovering marine wreckage and choosing between honorable return or piracy."""
    db = db_manager.db

    explorer = await character_service.create_character(
        user_id="user_explorer_1",
        name="Diver Barnaby",
        faction=Faction.INDEPENDENT,
        starting_location_id="azure_sea_lane"
    )

    # 1. Force discovery of a salvage site
    site = await salvage_service.explore_for_salvage(
        character_id=explorer.character_id,
        location_id="azure_sea_lane"
    )
    if not site:
        # Procedural fallback creates one if random didn't hit
        from app.game.salvage.salvage_models import SalvageSite, SalvageType
        site = SalvageSite(
            name="Wreck of the Golden Siren",
            location_id="azure_sea_lane",
            salvage_type=SalvageType.SUNKEN_SHIPWRECK,
            original_owner_name="Azure Merchant Consortium",
            loot_gold=400
        )
        await db.salvage_sites.insert_one(site.to_mongo())

    # 2. Return to rightful owner for legal reward
    claim_res = await salvage_service.claim_salvage(
        character_id=explorer.character_id,
        site_id=site.site_id,
        choice="return_to_owner"
    )
    assert claim_res["choice"] == "return_to_owner"
    assert claim_res["reward_gold"] > 0
    assert "+15 Merchant" in claim_res["reputation_change"]
