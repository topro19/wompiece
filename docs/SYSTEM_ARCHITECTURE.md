# PIRATE WARS — System Architecture & World Specification

## 1. Executive Summary & Design Invariants

**PIRATE WARS** is a persistent, multiplayer simulation world set in an age of sail, piracy, colonial commerce, and naval justice. The world is inhabited simultaneously by human players and autonomous AI-controlled agents.

```
                    ┌──────────────────────────┐
                    │   DETERMINISTIC ENGINE   │
                    │   Authoritative Truth    │
                    └────────────┬─────────────┘
                                 │
           ┌─────────────────────┼─────────────────────┐
           │                     │                     │
           ▼                     ▼                     ▼
     MONGODB CLUSTER       GOOGLE GEMINI        DISCORD BOT TREE
     Long-Term State     Reasoner/Narrator     Command Interface
```

### Core Invariants:
1. **Server-Authoritative Determinism**: The game engine owns 100% of state mutation. The AI never mutates state directly. It reasons, proposes, and narrates within strict Pydantic schemas.
2. **True One-Life Permadeath**: Characters possess exactly one life. Upon reaching 0 HP via lethal combat or execution, an immutable `DEATH_EVENT` is recorded, and the character is archived.
3. **Double-Entry Economic Ledger**: Every gold piece and doubloon is tracked via double-entry transactions with idempotency keys. Balances cannot drop below zero.
4. **Information Visibility Firewalls**: Strict firewalls prevent metagaming (`PUBLIC`, `CREW_ONLY`, `FACTION_ONLY`, `CASE_RESTRICTED`, `SECRET`).
5. **Prompt Injection Defense**: Untrusted player input is quarantined within `<untrusted_player_action>` delimiters before being evaluated by LLMs.

---

## 2. World Geography & Location Graph

The world map consists of interconnected island locations, secret coves, and open sea lanes:

- **Azure Island**:
  - `port_azure_docks`: Grand harbor, shipyard, cargo wharf. Connects to `port_azure_market`, `the_crimson_parrot`, `marine_headquarters`, and `azure_sea_lane`.
  - `port_azure_market`: Central bazaar, colonial bank, trade exchange.
  - `marine_headquarters`: Marine 16th Division fortress, holding cells, warrant office.
  - `the_crimson_parrot`: Outlaw tavern, high-low gambling den, rumor mill.
  - `smugglers_cove` (Dead Man's Cove): Hidden sea cavern, fence, black market docks.
  - `governors_mansion`: Grand colonial estate, commercial licensing office.
- **Azure Sea (Maritime Zone)**:
  - `azure_sea_lane`: Open ocean highway connecting Azure Island, Isla de la Muerte, and Verdant Atoll. Accessible only via vessels.
- **Isla de la Muerte**:
  - `skull_rock_anchorage`: Treacherous reef harbor, pirate shipyard, black market.
  - `skull_rock_tavern`: The Black Skull Tavern, crew recruiting, mutineers' retreat.
- **Verdant Atoll**:
  - `coral_bay_wharf`: Crystal lagoon trade port, merchant shipyard.
  - `coral_bay_market`: Spice bazaar, foreign colonial bank.

---

## 3. Naval & Ship System (`app/game/ships/`)

### Vessel Classes & Base Attributes

| Class | Base Cost | Max Hull | Armor | Cannons | Speed | Cargo Hold | Crew Max |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Sloop** | 500g | 100 HP | 5 | 4 | 12 kts | 50 units | 6 sailors |
| **Caravel** | 1,500g | 220 HP | 10 | 10 | 10 kts | 160 units | 20 sailors |
| **Frigate** | 4,000g | 400 HP | 20 | 24 | 8 kts | 350 units | 50 sailors |
| **Galleon** | 10,000g | 750 HP | 30 | 44 | 6 kts | 800 units | 120 sailors |

### Naval Mechanics:
- **Broadside Combat**: Server-authoritative gunnery simulation factoring cannon count, armor penetration, critical powder keg hits (1.5x damage), and retaliatory broadsides.
- **Vessel Sinking**: Hulls reaching 0 HP transition to `SUNK`, losing all loaded cargo to the depths.
- **Shipyard Repairs**: Damaged hulls can be repaired at port shipyards for 2 gold per HP.
- **Dynamic Sea Encounters**: Voyages roll for storms, Marine frigate customs inspections, pirate raider ambushes, and merchant convoys.

---

## 4. Background Simulation Scheduler (`app/game/simulation/`)

The simulation engine executes tiered ticks to maintain a living, breathing world:

1. **HIGH Priority Tick**:
   - Rapid checks: combat timers, transient conditions, acute health states.
2. **MEDIUM Priority Tick**:
   - Advances world clock and shifts weather (Dense Fog, Tropical Squall, Fair Winds).
   - Commercial operations: passive daily commerce across all player and NPC businesses.
   - Crew dynamics: recalculates mutiny risk for all active pirate crews based on officer dissatisfaction and treasury reserves. Automatically triggers mutiny events when risk exceeds 75%.
   - Autonomous NPC progression: *Captain Redhook* plans shipping raids; *Inspector Vance* reviews active cases and prepares warrants.
3. **LOW Priority Tick**:
   - Long-horizon cycles: daily market adjustments, statutory case reviews, wanted level bounty inflation.

---

## 5. Detective, Law & Justice System (`app/game/investigations/`)

- **Statutory Laws**: Statutory penal codes governing Smuggling, Illegal Gambling, Falsified Identity, Bribery, Piracy, and Murder.
- **Evidence Dossier**: Timestamped chains of custody, including physical contraband, financial ledger anomalies, witness transcripts, and surveillance logs.
- **AI Marine Commander Warrants**: Gemini acts as the Marine Commander, analyzing evidence against statutory legal thresholds to `APPROVE` or `DENY` search and arrest warrants.
- **Bribery & Corruption**: Secret bribery mechanics allowing suspects to attempt corrupting officers, counter-balanced by undercover Marine sting operations and Internal Affairs oversight.

---

## 6. Complete Discord Slash Command Registry

1. `/start` — Create character and enter persistent world (One-Life).
2. `/profile` — View vitals, faction, rank, purse, wanted level, and stats.
3. `/inventory` — Inspect personal weapons, tools, documents, and contraband.
4. `/location` — View current location, local facilities, and travel buttons.
5. `/crew [info|join|leave|deposit]` — Mixed AI/player crew management and treasury deposits.
6. `/business [info|operate|smuggle]` — Commercial business operations and black market runs.
7. `/alias [forge|list]` — Forged civilian identities and shell ownership.
8. `/case [open|view|evidence|interrogate|warrant]` — Marine criminal investigation docket.
9. `/act` — Freeform player actions interpreted by AI context engine.
10. `/bribe` — Attempt secret bribery of officials or initiate undercover stings.
11. `/gamble [dice]` — High-low dice wagering with loaded dice detection.
12. `/combat [attack]` — Server-authoritative player combat and permadeath escalation.
13. `/ship [buy|info|sail|attack|repair]` — Naval vessel outfitting, sailing, and broadside cannon battles.
14. `/admin [simulate_tick|advance_time|spawn_npc|inspect_character|list_ships]` — Developer simulation tools.
15. `/status` — Persistent world engine health check and latency ping.
