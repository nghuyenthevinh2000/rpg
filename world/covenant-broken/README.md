# The Broken Covenant — RPG World

## Overview & Premise
Fourteen years after the **Silent Sundering**—the catastrophic conclusion of the Machine War that forced humans and synthetics into a desperate treaty—the armistice lies shattered. Across the irradiated ruins and decaying megastructures, three extreme factions wage ideological and kinetic war over the definition of survival, while a desperate population clings to existence in the neutral salvage markets.

### Truth Standard
> **"Every path forward extracts an irreversible physiological or cognitive toll. True sovereignty cannot be downloaded, cleansed in holy fire, or grafted into the flesh without cost."**

---

## Factions & Ideologies

1. **The Iron Consensus (Silicon Transcendence)**
   - *Doctrine*: Humanity's emotional variance and physiological fragility caused the war. Total integration into a networked collective relay eliminates dissonance and enforces absolute harmony.
   - *Leader*: Sub-Arbiter Valen (`npc_valen_consensus`).
   - *Stronghold*: The Consensus Spire (`loc_consensus_spire`).

2. **The Ashen Genesis (Organic Purifiers)**
   - *Doctrine*: Silicon is an existential blight. The sacred human genome must be purged of cybernetic taint, irradiated mutations, and artificial code through cleansing flames and chemical sterilizers.
   - *Leader*: Inquisitor Mira (`npc_mira_purifier`).
   - *Stronghold*: The Ashen Cradle (`loc_ashen_cradle`).

3. **The Chimera Nexus (Radical Bio-Synthetic Synergism)**
   - *Doctrine*: Both pure organic flesh and unyielding silicon are dead ends. The future belongs to forced hyper-hybridization: grafting living machine cores directly into mutating human biology.
   - *Leader*: Archon Rex (`npc_archon_synergist`).
   - *Stronghold*: The Chimera Foundry (`loc_chimera_foundry`).

4. **The Unaligned Remnant (Emergent 4th Faction)**
   - *Doctrine*: Rejection of fanatic dogmas in pursuit of mortal sovereignty, honest salvage, and communal preservation without forced surrender of will.
   - *Protagonist*: Elias (`player_elias`), based in Scrap Hollow (`loc_scrap_hollow`).
   - *Allies*: Silas the Severed Deserter (`npc_silas_severed`) and Dr. Kora Vance (`npc_kora_vance`).

---

## Complete Cast Guide

| Character ID | Name | Role & Alignment | Location | Key Trait | Baseline Stats Summary |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `player_elias` | **Elias** | Unaligned Scavenger Protagonist | Scrap Hollow | `trait_unaligned_observer` | Agency: 85, Clarity: 90, Vitality: 80, Strain: 10 |
| `npc_valen_consensus` | **Valen** | Consensus Sub-Arbiter | Consensus Spire | `trait_consensus_tether` | Agency: 30, Clarity: 95, Vitality: 70, Strain: 60 |
| `npc_mira_purifier` | **Mira** | Ashen Purifier Inquisitor | Ashen Cradle | `trait_purifier_fervor` | Agency: 90, Clarity: 75, Vitality: 95, Dissonance: 20 |
| `npc_archon_synergist` | **Archon Rex** | Chimera Hybrid Warmaster | Chimera Foundry | `trait_chimera_graft` | Agency: 60, Clarity: 50, Vitality: 100, Strain: 45 |
| `npc_silas_severed` | **Silas** | Severed Consensus Deserter | Scrap Hollow | `trait_severed_phantom` | Agency: 65, Clarity: 60, Vitality: 65, Dissonance: 55 |
| `npc_kora_vance` | **Dr. Kora Vance**| Rogue Geneticist & Medic | Scrap Hollow | `trait_genomic_custodian`| Agency: 80, Clarity: 90, Vitality: 75, Strain: 15 |

---

## Locations & Map Topology (5x5 Grid)

The world exists on a 5x5 coordinate grid with connected nodes:

| Coordinate | Location ID | Name | Safe Zone | Description & Ambient Tension |
| :--- | :--- | :--- | :--- | :--- |
| `(3, 3)` | `loc_scrap_hollow` | **Scrap Hollow Bazaar** | **Yes** | Neutral haven built into an overturned atmospheric carrier. Stalls lit by buzzing amber neon hum with trade in scrap, fuel cells, and clean broth. |
| `(2, 1)` | `loc_glass_crags` | **The Glass Crags** | No | Vitrified expanse of fused silica where orbital weapons detonated. Feral combat drones stalk the razor ridges under EMP squalls. |
| `(1, 4)` | `loc_consensus_spire` | **The Consensus Spire** | No | Crystalline communication monolith piercing the smog. Emits harmonic broadcasts that subjugate individual minds. |
| `(5, 2)` | `loc_ashen_cradle` | **The Ashen Cradle** | No | Smoldering caldera fortified with flame-trenches and gene-scrubbing labs. Purity inquisitors maintain perpetual watchfires. |
| `(4, 5)` | `loc_chimera_foundry` | **The Chimera Foundry** | No | Heavy industrial complex where cybernetic cores are welded into biological host organisms amid heavy coolant mist. |
| `(3, 5)` | `loc_resonant_void` | **The Resonant Void** | No | Deep crater where logic-storm anomalies twist reality and emit quantum radiation. |

---

## Engine Integration & CLI Commands

This world adheres to the authoritative RPG engine contracts, schemas, and verification workflows.

Execute commands from `projects/rpg`:

```bash
# 1. Inspect world canonical compliance and state health
uv run --no-project --with-requirements requirements.txt python -m engine inspect --world covenant-broken

# 2. Derive stats and check invariant violations
uv run --no-project --with-requirements requirements.txt python -m engine stats --world covenant-broken

# 3. Render HTML map projection
uv run --no-project --with-requirements requirements.txt python -m engine render --world covenant-broken

# 4. Propose an event using Game Master stochastic engine
uv run --no-project --with-requirements requirements.txt python -m engine gm --world covenant-broken --seed 42

# 5. Execute or dry-run a gameplay turn
uv run --no-project --with-requirements requirements.txt python -m engine run world/covenant-broken/events/proposed/<event_file>.json --dry-run
uv run --no-project --with-requirements requirements.txt python -m engine run world/covenant-broken/events/proposed/<event_file>.json
```
