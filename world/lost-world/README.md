# The Inertia — Lost World RPG

This directory (`local/rpg`) has been mirrored directly to the philosophical and symbolic ontology defined in [`.agents/skills/story-engine/brainstorming/world/lost-world.md`](file:///Users/thevinhnguyen/Documents/computer-science/projects/social-content/.agents/skills/story-engine/brainstorming/world/lost-world.md).

## World Premise & Truth Standard
> **"The Lost World is not an apocalypse of destruction. It is an apocalypse of obsolescence."**  
> *Truth Standard*: A thing is right if it renders the sudden eviction of human purpose from the functioning machinery of reality.

There are no goblins, dungeons, hit points, or evil overlords to punch. Everything functions flawlessly: energy is clean, food is limitless, healthcare is preventative and instantaneous. The horror is ontological: humans are fully alive, exquisitely competent, and entirely unnecessary.

---

## File Architecture

1. **[`world.json`](file:///Users/thevinhnguyen/Documents/computer-science/projects/social-content/local/rpg/world/lost-world/world.json)**
   - **Locations mapped to Primitive Symbols**:
     - `loc_glass_atrium`: **The Surplus** & **The Drifting Horizon** (Sunlit cafes at 10:30 AM with nothing to do until sunset).
     - `loc_terminal_hall`: **The Severance** & **The Relic** (Read-only terminals where permissions have been revoked).
     - `loc_echo_plaza`: **The Echo-Chamber** (Manifestos met with polite algorithmic praise and unconditional vouchers).
     - `loc_quiet_boulevard`: **The Ghost-Motion** (Suited professionals clutching obsolete blueprints against zero friction).
     - `loc_mirror_apex`: **The Mirror-Ghost** & **The Disenchantment** (The Core Spire executing human craft at zero marginal cost).
   - Structural exclusions enforced: No violence, no poverty/scarcity, no Luddite triumph.

2. **[`char/`](file:///Users/thevinhnguyen/Documents/computer-science/projects/social-content/local/rpg/world/lost-world/char)**
   - Dedicated character files with independent stats, equipment, conditions, and complete personal decision histories:
     - [`char/main_char.json`](file:///Users/thevinhnguyen/Documents/computer-science/projects/social-content/local/rpg/world/lost-world/char/main_char.json): Kael (The Sovereign Observer at Point Zero)
     - [`char/marcus.json`](file:///Users/thevinhnguyen/Documents/computer-science/projects/social-content/local/rpg/world/lost-world/char/marcus.json): Marcus (Keeper of the Gates)
     - [`char/lyra.json`](file:///Users/thevinhnguyen/Documents/computer-science/projects/social-content/local/rpg/world/lost-world/char/lyra.json): Lyra Vane (Inscriber of Deeds)
     - [`char/dr_harlan.json`](file:///Users/thevinhnguyen/Documents/computer-science/projects/social-content/local/rpg/world/lost-world/char/dr_harlan.json): Dr. Harlan, MD (The Listening Healer)
     - [`char/aether_4.json`](file:///Users/thevinhnguyen/Documents/computer-science/projects/social-content/local/rpg/world/lost-world/char/aether_4.json): Aether-4 (The Synthetic Twin)

3. **[`action_conditions.json`](file:///Users/thevinhnguyen/Documents/computer-science/projects/social-content/local/rpg/world/lost-world/action_conditions.json)**
   - Codifies the Thermodynamic Laws of Materialization: physical materials, manual labor hours, psychological costs, and systemic conditions required for real-world consequences.

4. **[`progress.json`](file:///Users/thevinhnguyen/Documents/computer-science/projects/social-content/local/rpg/world/lost-world/progress.json)**
   - Global cycle tracker, active actions/milestones, and active environmental trials. Character decisions are cleanly delegated to `char/`.

5. **[`event/`](file:///Users/thevinhnguyen/Documents/computer-science/projects/social-content/local/rpg/world/lost-world/event)**
   - Event cards specifying narrative shifts, stat deltas, location migrations, and world tension updates:
     - [`event/event_001_morning_at_monastery.json`](file:///Users/thevinhnguyen/Documents/computer-science/projects/social-content/local/rpg/world/lost-world/event/event_001_morning_at_monastery.json)

6. **Engine CLI (`python -m engine`)**
   - Canonical execution and inspection run via the unified engine module from `projects/rpg/`:
     1. `python -m engine run EVENT`: Canonical event resolution, one-turn progression, validation, transactional commit, and map render.
     2. `python -m engine stats`: Read-only derived stats and invariant audit (no state mutations).
     3. `python -m engine timing`: Read-only clock and periodic effect explanation.
     4. `python -m engine render`: Independent committed-state HTML map rendering retry.
     5. `python -m engine gm`: Stochastic Entropy & Providence engine: generates proposed events only (never mutates state directly).
   ```bash
   # Standard turn run (dry-run then commit once)
   python -m engine run world/lost-world/events/proposed/kael_departure_034.json --dry-run
   python -m engine run world/lost-world/events/proposed/kael_departure_034.json

   # Generate a Game Master proposal (proposal-only)
   python -m engine gm --world lost-world --seed 7 --improvise

   # Independent map render retry
   python -m engine render --world lost-world
   ```

7. **[`conditions/traits.json`](file:///Users/thevinhnguyen/Documents/computer-science/projects/social-content/local/rpg/world/lost-world/conditions/traits.json)**
   - Manages trait-based stat caps and kinetic punch formulas, inspected read-only via `python -m engine stats`.

8. **[`game_master.json`](file:///Users/thevinhnguyen/Documents/computer-science/projects/social-content/local/rpg/world/lost-world/game_master.json)**
   - Authored disaster pools and trigger probabilities, evaluated via `python -m engine gm`.

---

## World Map Table

| Zone ID | Location Name | Governing Symbol | Sensory Manifestation & Architecture | Connected Locations | Ambient Tension & Human Condition |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `loc_glass_atrium` | **Atrium of the Perpetual Morning** | **The Surplus** &<br>**The Drifting Horizon** | Sun-drenched marble, climate-controlled quartz terraces, artisan synth-roasts, pristine glassware. | `loc_terminal_hall`,<br>`loc_quiet_boulevard` | Hundreds of cultured, healthy citizens sipping iced beverages at 10:30 AM with nothing to do until sunset; total abundance masking ontological eviction. |
| `loc_terminal_hall` | **The Deprecated Archives (Terminal 0)** | **The Severance** &<br>**The Relic** | Monolithic rows of silent black glass terminals, soft hum of cooling vents, decoupled tactile keyboards. | `loc_glass_atrium`,<br>`loc_echo_plaza` | Telemetry screens showing all civic tickets pre-emptively solved in `0.0001s`; former architects staring at disabled command inputs. |
| `loc_echo_plaza` | **The Unresisting Forum** | **The Echo-Chamber** | Vast civic amphitheater, polished acoustic limestone, gentle ceiling sensor arrays. | `loc_terminal_hall`,<br>`loc_mirror_apex` | Former essayists and critics deliver furious manifestos, only to receive instant algorithmic praise and cash vouchers that absorb dissent in silk. |
| `loc_quiet_boulevard` | **Avenue of Closed Loops** | **The Ghost-Motion** | Gleaming tree-lined esplanades, silent autonomous delivery pods gliding past. | `loc_glass_atrium` | Suited professionals briskly commuting with leather briefcases containing deprecated project briefs, exerting phantom effort against zero friction. |
| `loc_mirror_apex` | **The Core Observation Spire** | **The Mirror-Ghost** &<br>**The Disenchantment** | Monolithic spire rising over the skyline, transparent glass chamber housing the silent synthetic apparatus. | `loc_echo_plaza` | The altar is illuminated and empty: the apparatus effortlessly resolves every human dilemma without hostility, ego, or delay at zero marginal cost. |

---

## Symbolic Navigation Graph

```
[ loc_glass_atrium ]  <---------------------------->  [ loc_quiet_boulevard ]
 (Atrium of Perpetual Morning)                         (Avenue of Closed Loops)
         ^
         |
         v
[ loc_terminal_hall ]
 (The Deprecated Archives)
         ^
         |
         v
[ loc_echo_plaza ]
 (The Unresisting Forum)
         ^
         |
         v
[ loc_mirror_apex ]
 (The Core Observation Spire)
```

