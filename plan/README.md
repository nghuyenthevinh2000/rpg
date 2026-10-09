# Multi-world RPG engine plan

Status: initial-scope implementation in progress. Execution is tracked in `progress.md`.

## Execution decisions (2026-10-09)

- Work in place; do not touch unrelated projects or automatically commit changes.
- Define the canonical contract and adapt both current worlds to it. Preserve original saves and events in a migration archive, then cut over without advancing a gameplay turn.
- Treat stored current values as the migration baseline rather than attempting to reconstruct historical event applications. Derived modifiers are measured relative to the imported baseline so bonuses do not stack.
- Machine-readable death follows character health/status, not contradictory garrison prose. Replace immortal vitality `-99` with `capabilities.cannot_die` and configured nonnegative health.
- Preserve Warhammer's currently authored sanctuary: combat logic is proved in a test world where combat is enabled, not by reinstating hostile threats in the live save.
- Implement the initial scope below first. Unsupported historical action/resource systems remain archived metadata until their world rules are extracted.

## Goal

Keep live state split into small entity files, with one shared engine responsible for validating and committing changes. Each world supplies a contract defining its state schemas, definitions, and custom rule functions.

AI proposes events. World logic resolves mechanics. The engine owns persistence. The map reads committed state.

## Current findings

Paths below are relative to `local/rpg/`.

- `world_utils.py` already supports world selection, but progress storage differs between worlds.
- `change_world.py` runs event application, progress effects, stat enforcement, rendering, then GM mutation. `apply_event.py` also renders. The final map can be stale.
- `game_master.py` mutates state directly and hardcodes Lost World improvisation, ignoring Warhammer's configured improvisation templates.
- `enforce_progress_effects.py` hardcodes Warhammer resources, equipment, and troops.
- `enforce_char_stats.py` hardcodes stat names and treats vitality `-99` as immortality.
- `resolve-threat.py` hardcodes Warhammer combat and sample participants. Its report is separate from authoritative character/resource state.
- Characters use inconsistent location fields. Stored coordinates can disagree with location IDs.
- Events use several aliases. Event 030 in Warhammer nests character updates inside progress, where the dispatcher ignores them.
- There is no duplicate-event protection or recoverable multi-file commit. Reapplying events repeats deltas and decisions.
- Damage paths disagree about mortality: combat can turn immortal vitality into zero; survival floors can raise dead characters from zero to five.
- Structural rules and action-condition definitions are not enforced by the Python scripts.

## Architecture

```text
Definitions + committed state + player action
                       |
                       v
               AI / GM proposed event
                       |
                       v
             World resolve() function
                       |
                       v
           Shared effect reducer / overlay
                       |
                       v
            World after_turn() function
                       |
                       v
          Schema and invariant validation
                       |
                       v
          Recoverable split-state commit
                       |
                       v
                 Read-only map
```

Only the state store writes authoritative gameplay state. Rule functions return effects, not file mutations.

## Proposed directory structure

```text
local/rpg/
├── engine/
│   ├── contracts.py
│   ├── state_store.py
│   ├── runner.py
│   └── render_map.py
└── world/<world_id>/
    ├── world.json
    ├── definitions/
    │   ├── locations.json
    │   ├── stats.json
    │   ├── traits.json
    │   ├── equipment.json
    │   └── gm.json
    ├── schemas/
    │   ├── character.schema.json
    │   └── fleet.schema.json
    ├── logic/
    │   └── rules.py
    ├── state/
    │   ├── clock.json
    │   ├── characters/<character_id>.json
    │   ├── locations/<location_id>.json
    │   ├── resources/<stockpile_id>.json
    │   ├── threats/<threat_id>.json
    │   ├── actions/<action_id>.json
    │   ├── groups/<group_id>.json
    │   └── fleets/<fleet_id>.json
    ├── events/
    │   ├── proposed/
    │   └── committed/
    ├── transactions/
    └── map.html
```

Split state by independently changing entity, not by individual numeric field. Collections such as fleets are optional and world-specific. Reuse existing definition files during migration; moving directories is secondary to establishing contracts.

Static location descriptions and topology belong in definitions. Changing ownership, damage, and tension belong in location state.

## Ownership and write boundaries

| Component | Reads | Produces |
| --- | --- | --- |
| AI / narrative GM | Definitions and relevant state | Proposed events |
| World rules | Read-only context and events | Effects, outcomes, notes |
| Engine | Contracts, state, proposed effects | Validated state commits |
| Renderer | Committed state | Map |

Normal AI gameplay writes go to `events/proposed/`. Definition and rule-code changes are separate authoring operations.

Protect `state/`, committed events, and transactions from direct AI writes where harness permissions support it. Without filesystem enforcement, this is a workflow convention, not an access-control guarantee. Split files limit accidental damage but do not independently prevent it.

## World contract

Example `world.json` contract configuration:

```json
{
  "world_id": "warhammer-40k",
  "contract_version": 1,
  "state_schema_version": 1,
  "player_character_id": "player_vane",
  "collections": {
    "characters": {"schema": "schemas/character.schema.json"},
    "resources": {"schema": "engine:resource"},
    "threats": {"schema": "engine:threat"},
    "fleets": {"schema": "schemas/fleet.schema.json"}
  },
  "logic": {
    "resolve": "logic/rules.py:resolve",
    "after_turn": "logic/rules.py:after_turn",
    "derive": "logic/rules.py:derive",
    "validate": "logic/rules.py:validate"
  }
}
```

Paths resolve within the world directory; `engine:` references built-in contracts. Validate references and prevent entity identifiers from becoming arbitrary filesystem paths.

A world can define different character stats, add collections, omit combat, and supply custom Python behavior. The engine understands entities, references, effects, revisions, and transactions—not world lore.

Use JSON Schema for data shapes and custom validation for cross-entity invariants. Select a maintained schema validator during implementation rather than implementing a partial JSON Schema interpreter.

## State contract

Every entity uses a common envelope:

```json
{
  "id": "player_vane",
  "revision": 12,
  "schema_version": 1,
  "data": {
    "name": "Kathryn Vane",
    "location_id": "loc_shrine_aquila",
    "status": "alive",
    "stats": {
      "physical_vitality": 100,
      "clarity": 200
    },
    "capabilities": {"cannot_die": true},
    "traits": ["trait_immortal_awakened_yellow_energy"]
  }
}
```

Requirements:

- Stable IDs; engine-managed revisions and schema versions.
- Collection schemas validate entity data.
- References resolve to valid entities or definitions.
- Ordinary updates cannot change identity or engine metadata.
- Reject unknown mechanical fields; provide a designated narrative metadata field.
- Use one `location_id`; derive map coordinates from location definitions/state.
- Separate machine-readable status from narrative status text.
- Keep editable/base values distinct from derived effective stats.
- Define equipment and trait modifier order explicitly; recalculation must not stack bonuses.

World rules decide which stats exist, how damage and death work, and whether vitality exists at all. Replace the `-99` immortality sentinel with an explicit capability whose semantics are implemented consistently by that world.

The clock records turn/day and a world-specific display timestamp. Do not assume all fictional calendars use ISO timestamps.

## Custom logic function contract

Use ordinary Python functions. Only `resolve` is mandatory; other hooks have no-op defaults.

```python
def resolve(ctx, event) -> RuleResult:
    """Resolve the requested action into effects and mechanical outcomes."""


def after_turn(ctx, event, outcome) -> RuleResult:
    """Calculate periodic consequences against tentative post-action state."""


def derive(ctx, entity_ref) -> dict:
    """Calculate effective stats/display values without changing state."""


def validate(ctx) -> list[Violation]:
    """Check world invariants against the complete tentative state."""
```

Context exposes:

```python
class RuleContext:
    state: StateView
    definitions: DefinitionView
    rng: Random
    turn: int
```

State access:

```python
ctx.state.get("characters", "player_vane")
ctx.state.list("threats")
```

Views return immutable values or defensive copies and expose no save method. The context for `after_turn` and validation reads through the tentative state overlay.

Results contain effects, structured outcomes, and optional explanatory notes:

```python
RuleResult(
    effects=[...],
    outcomes={"damage_dealt": 42, "target_destroyed": False},
    notes=["Armor absorbed 12 damage."],
)
```

Rules must:

- Return effects rather than write files.
- Use engine-provided randomness.
- Avoid wall-clock time and external mutable inputs during resolution.
- Return stable ordering when iteration affects outcomes.
- Raise structured rule errors for invalid actions.
- Leave authoritative data unchanged during derivation.

Custom Python is trusted code. The context API prevents accidental mutation through that interface; it is not a Python sandbox. Untrusted scripts would require process-level isolation, outside the initial scope.

Use configuration for stat bounds, equipment parameters, resource thresholds, and explicit hazard tags. Use custom functions for genuinely different behavior. Do not introduce a custom rule language or plugin framework.

## Event contract

AI proposes intent; the world resolves mechanics:

```json
{
  "schema_version": 1,
  "event_id": "event_034",
  "world_id": "warhammer-40k",
  "expected_turn": 33,
  "action": {
    "type": "attack",
    "actor_id": "player_vane",
    "target_id": "threat_chaos_lord",
    "weapon_id": "item_void_relic_blade"
  },
  "narrative": "Vane advances toward the wounded lord."
}
```

Narrative does not independently authorize mechanical changes. Define explicit GM actions such as introducing a threat, moving a character, and completing a milestone. Validate those through world logic too.

Validate event identity, world, expected turn, action shape, entity references, and available resources. Engine-controlled turn advancement must have a defined policy, including whether an action consumes a turn. Entity revision checks handle stale non-turn-changing updates as needed.

## Effect contract

Example resolved effect:

```json
{
  "op": "increment",
  "collection": "threats",
  "entity_id": "threat_chaos_lord",
  "path": "/stats/vitality",
  "value": -42
}
```

Paths address fields within entity `data`, not arbitrary files or envelope metadata.

Initial operations:

- `create`: create a schema-valid entity.
- `set`: replace a permitted field.
- `increment`: change a numeric field.
- `remove`: remove an optional field or an explicitly permitted entity.

Define missing-field behavior, permitted paths, and ordered application precisely. Prefer ID-keyed collections over positional array edits. Reject ambiguous or invalid operations rather than silently skipping them.

AI does not receive an unrestricted raw-patch interface. Custom rules produce effects; the engine still validates their targets and final state.

## Turn execution and timing

1. Load the contract and proposed event.
2. Acquire the world write lock and recover pending transactions.
3. Validate identity, duplication, expected turn/revisions, schemas, and references.
4. Run `resolve()` against committed state.
5. Apply effects to an in-memory overlay.
6. Run `after_turn()` once if this action advances the turn.
7. Apply consequence effects.
8. Validate changed entities and complete world invariants.
9. Commit changed files as a recoverable transaction.
10. Render a consistent committed snapshot.

Run rendering under a consistent read boundary or use a captured snapshot so another turn cannot cause mixed-revision output. Rendering failure does not undo an already committed event; rendering can be retried without replaying gameplay.

Define whether newly introduced hazards activate immediately or next turn. Record activation timing explicitly. Combat owns its retaliation; periodic effects must not repeat it.

A dry run follows the same resolution and validation path but stops before persistence and shows entity-level changes.

## Recoverable split-state commits

Multiple file replacements are not one atomic transaction. Use a write-ahead journal and a world lock:

1. Record event identity, expected revisions, affected files, and before/after contents, including creates/removals.
2. Durably persist the prepared transaction before changing state.
3. Replace affected files via temporary files in the destination filesystem.
4. Durably mark the transaction committed.
5. Finalize the committed resolved-event archive idempotently.

Before reading or accepting another turn, recover incomplete prepared transactions using one documented policy—prefer deterministic roll-forward from recorded after-images. Include clock advancement and event application identity in recovery. An interrupted archive finalization must not permit the event to apply again.

Use flush/fsync and directory durability where required; atomic rename alone does not guarantee recovery after power loss. Readers must honor engine locking/recovery; external direct file readers do not receive a consistent-snapshot guarantee.

Committed events record exact effects and random outcomes. Replay applies those effects without rerunning world scripts or rerolling RNG. Record contract/rule version metadata for diagnosis.

## Migration mapping

| Existing file | Target responsibility |
| --- | --- |
| `change_world.py` | Thin CLI over shared runner |
| `apply_event.py` | Effect validation and in-memory reducer |
| `world_utils.py` | World discovery and split-state storage |
| `enforce_char_stats.py` | Shared stat helpers called by world rules |
| `enforce_progress_effects.py` | Warhammer periodic world logic |
| `resolve-threat.py` | Warhammer combat resolver |
| `game_master.py` | World-aware proposed-event generation |
| `render_map.py` | Read-only renderer of canonical state |

Preserve convenient CLI entry points during migration. Avoid keeping old commands as independent mutation paths.

## Implementation phases

### 1. Contracts and read-only inspection

- Define state, event, effect, and function contracts.
- Define timing, death, immortality, and modifier-order semantics.
- Add validators and inspection for both current worlds.
- Report legacy inconsistencies, including unsupported fields and references.

### 2. Import current saves

- Snapshot both worlds before migration.
- Import character/progress state into entity files.
- Normalize IDs, locations, equipment references, and machine-readable statuses.
- Preserve narrative metadata and archive original event files.
- Review derived/base stat separation where existing modifiers make automatic reconstruction ambiguous.
- Use current saves as migration baselines: old event history is not reliably replayable because of duplicate applications, ignored fields, and direct mutations.
- Keep one authoritative source after cutover; old files become archives or generated exports.

### 3. Shared execution and persistence

- Implement immutable/read-only views, the overlay, and effect reducer.
- Implement locking, duplicate detection, revisions, journaled commit, and recovery.
- Add dry-run output.
- Route all gameplay mutations through the runner.

### 4. Prove two different worlds

- Implement movement in both worlds using the same engine.
- Implement Lost World cold exposure through its custom logic.
- Implement Warhammer combat through its custom logic.
- Load the selected world's GM templates.
- Extract remaining resource, trait, equipment, and action mechanics incrementally.

### 5. Rendering and operational guidance

- Render canonical committed state and derived values.
- Use world-defined labels and hide absent systems.
- Escape narrative values in HTML.
- Update README and gameplay instructions.
- Make sub-agent roles world-neutral while preserving the existing mandate for gameplay turns.

## Acceptance checks

- The same runner processes both worlds with different rules.
- A world-specific collection works without changes to the persistence engine.
- Invalid, wrong-world, duplicate, and stale events do not mutate state.
- Custom rule failures leave no partial changes.
- Interrupted multi-file commits recover consistently, including creates and removals.
- All authoritative writes occur through the engine.
- Derived-stat calculation does not stack equipment bonuses.
- Death and immortality semantics are consistent across damage sources.
- Periodic effects and retaliation apply once at the intended timing.
- New committed events replay from the migration baseline without rerunning randomness.
- Rendering reflects one committed revision and can be retried independently.

## Initial scope

First deliver a split-state loader, validators, custom `resolve()` support, an effect reducer, and recoverable commits. Prove movement plus one different mechanic in each existing world before migrating every subsystem.

Defer a general plugin framework, custom expression language, untrusted-code sandbox, and additional storage backends until there is a concrete need.
