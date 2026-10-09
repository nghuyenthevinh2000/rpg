# Initial canonical-world semantics

These policies resolve the choices left open in the design. They apply to the initial two-world implementation, not to the world-neutral persistence engine.

## Identity and location

- Character IDs in current saves remain stable. File names are not identities.
- `location_id` is the only mechanical location. Coordinates come from location definitions and optional location state, never from character sheets.
- Legacy `connected_to` edges are undirected: an edge declared at either endpoint permits movement. Movement to an unconnected location is rejected.
- Narrative fields, historical decisions, and unresolved historical participants remain metadata; they do not create new mechanical entities.

## Health and derivation

- Current save values are the imported baseline. Historical modifiers and event history are not used to reconstruct an earlier character.
- Static effective values are derived from this baseline plus changes in configured modifiers relative to the baseline. Derivation is read-only and cannot stack bonuses.
- Current vitality is mutable health, separate from equipment-derived static bonuses. Adding armor does not resurrect or passively heal a character.
- Ordinary mortal health reaching zero means `status = dead`. No periodic floor can increase a character's current health. A dead character cannot move, attack, or receive periodic recovery.
- `capabilities.cannot_die = true` makes damage leave health unchanged. The old `-99` sentinel is archived; live health becomes a configured nonnegative value, and immortal kinetic scaling is an explicit separate parameter.
- A clear legacy KIA marker or mortal zero health imports as dead even when garrison narrative says peaceful rest. Any future resurrection requires a separately authored, validated world mechanic.

## Timing

- Supported movement, waiting, attacks, and GM introduction actions consume one turn. The engine advances the clock; narrative timestamps do not advance it.
- Action effects resolve first. Periodic effects read the resulting overlay and execute exactly once.
- Newly introduced hazards activate on the following action, not on their introduction action. Activation is stored explicitly.
- Combat retaliation occurs once in the attack resolver, including a final retaliation on a killing blow (the existing Warhammer law of retaliation). Periodic effects never repeat combat retaliation.
- Cold affects only living characters at the tagged hazard location. A successful survival floor is `min(current_health, max(floor, current_health - damage))`; failed survival can result in death. Seeded rolls and resolved effects are archived.

## Structural constraints

- Warhammer's current `transcendent_sanctuary` is authoritative: attacks and hostile template introductions are rejected. Tests prove its combat resolver in a separate authored combat-enabled world.
- The existing Warhammer GM pool remains available for author inspection, but does not override sanctuary rules. Lost World uses only its own configured templates.
- Unsupported historical construction/resource actions are rejected rather than accepted as unrestricted patches. Their save records remain visible as archived metadata until supported by world rules.

## Ownership

- Proposed-event generators may write only `events/proposed/`; they do not mutate gameplay.
- World rules return effects. Only the state store writes authoritative canonical state.
- Maps are escaped, read-only projections of one committed snapshot. A map failure never replays or undoes the event.
- Legacy saves are archived at cutover and are not a second writable state source.
