# Multi-World RPG Gameplay Sub-Agent Mandate

## Mandatory Directive

Whenever executing narrative turns, character choices, combat rounds, or world-altering events in this RPG project (`projects/rpg/`, including its worlds):

1. **Always Invoke 1–2 Sub-Agents**:
   - Before drafting the final world event or applying state changes, use the harness's sub-agent tool to spawn **1 to 2 concurrent sub-agents** to deliberate or take active roles in the round.
   - Engine development, migration, inspection, rendering, and temporary-world regression tests are not narrative gameplay turns and do not activate this mandate.

2. **Sub-Agent Role Options**:
   - **Role Option A — Active Threat / Adversary / Boss Encounter**:
     - *Archetype*: An active antagonist, boss, or emerging threat permitted by the selected world's current rules.
     - *Responsibility*: Pursue the antagonist's goals and propose counter-actions or dialogue. World logic, not the sub-agent, determines authoritative damage and retaliation. Do not introduce hostility in a world whose current contract prohibits it.
   - **Role Option B — Companion / Garrison NPC**:
     - *Archetype*: A living active companion, local NPC, emissary, or witness from the selected world.
     - *Responsibility*: Provide authentic in-character reactions, proposed actions, or philosophical input. Do not revive a dead character through narrative prose.
   - **Role Option C — Game Master / World Entropy & Systemic Hazards**:
     - *Archetype*: The selected world's Game Master or systemic-hazard perspective.
     - *Responsibility*: Assess environmental hazards, unexpected consequences, supply strain, or emergent reactions using that world's definitions and templates.

3. **Synthesis & Engine Execution**:
   - Incorporate the sub-agents' proposed intent and dialogue into canonical event files under `world/<world_id>/events/proposed/`. Narrative never independently authorizes mechanical changes.
   - Dry-run the proposed event, then execute it once through `change_world.py`. The shared runner resolves mechanics, applies periodic effects once, validates, commits, and renders.
   - Never directly edit `state/`, `events/committed/`, or `transactions/`. Definition and rule authoring are separate from gameplay.
   - Do not separately run stat or progress enforcement to apply another round of consequences. Rendering can be retried without replaying the event.
   - Before save cutover, legacy gameplay mutation is disabled; inspect and migrate the world first. These write boundaries are a workflow convention unless harness filesystem permissions enforce them.
