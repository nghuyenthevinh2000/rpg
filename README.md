# Multi-world RPG engine

AI proposes intent; selected-world rules resolve it; **only the shared runner and
StateStore write canonical gameplay state**. Narrative is metadata, not a patch.
Commands below run from `projects/rpg/`.

## Setup and verification

Python 3.10+ on a POSIX platform (`fcntl` world locks), with `uv` for package management:

```sh
uv venv
uv pip install --python .venv/bin/python -r requirements.txt
source .venv/bin/activate
python -m unittest discover -s tests -v
```

Without a persistent environment, run checks directly with:

```sh
uv run --no-project --with-requirements requirements.txt python -m unittest discover -s tests -v
```

Development tests copy saves into temporary directories. They prefer each
world's `archive/legacy-baseline` after migration, otherwise the approved
original snapshot if available, otherwise the unmigrated save. They never
advance a live world and do not activate the gameplay sub-agent mandate.

## Inspect and migrate

Both current worlds use canonical split state. Original saves are preserved in
each world's `archive/legacy-baseline/`; implementation tests never advance the
live worlds. Migration of another legacy copy is not a turn:

```sh
python inspect_world.py --world lost-world
python migrate_world.py --world lost-world --dry-run
python migrate_world.py --world lost-world
python migrate_world.py --world warhammer-40k --dry-run
python migrate_world.py --world warhammer-40k
```

`--dry-run` is read-only preview. Default migration installs the explicitly
chosen **current-save baseline**, without an ambiguity approval gate;
`--accept-baseline` remains a deprecated compatibility no-op. Invalid identities,
casefold aliases, equipped ID references, and active location references block
import. Historical unresolved participants such as `seeker_surgeon` remain
narrative metadata, never invented characters.

- Exact original save, condition/GM/action-definition and event JSON bytes are
  preserved once in `archive/legacy-baseline/`. Source SHA-256s, inspection issues,
  and normalization choices are in `archive/migration-report.json`.
- `.migration.json` is a durable journal and `.migration-stage/` holds the
  candidate. The candidate baseline is installed **only** by
  `StateStore.initialize_baseline`, never by migration's own state-file writer.
- Complete state/history directories are installed before replacing `world.json`
  with `contract.json`. Original lore/topology becomes `definitions/world.json`.
  Until that final replacement, gameplay commands reject the legacy world.
- Existing archives/state/history are never overwritten. Old `char/`, `progress*`
  and `event/` files remain frozen compatibility material, not a writable second
  authority. Canonical consumers use `state/` and engine snapshots only.
- Initial clocks remain Lost World **turn 33/day 4**, Warhammer **turn 37/day 9**,
  with each save's display timestamp. Historical event files are never replayed.

### Interrupted migration / uncertain turn

Do not blindly rerun a failed command. Retain the archive, stage, and journal.
`phase: ready` can finish an interrupted installation explicitly:

```sh
python migrate_world.py --world lost-world --resume
```

Resume verifies exact original source/archive hashes and the installed full
baseline fingerprint before contract cutover. A `preparing` journal refuses
automatic retry: it may contain incomplete archival/staging work. Restore verified
originals into a **fresh directory**, copy the authored `contract.json`, `logic/`,
`schemas/`, and `definitions/engine_rules.json` there, then migrate that copy.
Never delete/overwrite uncertain evidence or an existing live canonical state.
For uncertain gameplay persistence, `engine.runner.read_snapshot(world)` recovers
the engine journal; inspect `events/committed/` before submitting anything again.

## Canonical proposed events

Use a unique safe event ID, current `expected_turn`, and optional current revisions.
Put intent under `events/proposed/`; the runner owns `events/committed/`,
`transactions/`, `state/`, clock advancement, and revisions.

Lost World movement example (initial baseline):

```json
{
  "schema_version": 1,
  "event_id": "kael_departure_034",
  "world_id": "lost-world",
  "expected_turn": 33,
  "expected_revisions": {"clock": 0, "characters/player_kael": 0},
  "action": {"type": "move", "actor_id": "player_kael", "location_id": "loc_echo_plaza"},
  "narrative": "Kael walks from the monastery to the forum."
}
```

Warhammer sanctuary example (initial baseline):

```json
{
  "schema_version": 1,
  "event_id": "vane_observation_038",
  "world_id": "warhammer-40k",
  "expected_turn": 37,
  "action": {"type": "wait", "actor_id": "player_vane"},
  "narrative": "Vane observes the Golden Haven in peace."
}
```

For actual gameplay follow `AGENTS.md`: invoke 1–2 gameplay sub-agents, synthesize
their proposed intent, dry-run, then commit **once**:

```sh
python change_world.py world/lost-world/events/proposed/kael_departure_034.json --dry-run --seed 42
python change_world.py world/lost-world/events/proposed/kael_departure_034.json --seed 42
python render_map.py --world lost-world
python enforce_char_stats.py --world lost-world
python enforce_progress_effects.py --world warhammer-40k
```

`apply_event.py` and `resolve-threat.py` are the same runner boundary, not separate
mutation systems. `--world` accepts a known world name or existing world directory;
event paths under `event/`, `events/proposed/`, or `events/committed/` infer the
world. Legacy aliases/raw patches/report-only combat specs are explicitly rejected.
`--no-render` omits map generation. Stat/progress commands are read-only inspection,
never an extra consequence pass. A map failure does not undo or replay a commit;
retry rendering independently. Maps escape display text and reject stale snapshots
while holding the engine lock through atomic map replacement.

Replay a committed gameplay report **only into an exact matching baseline copy**:

```sh
python change_world.py path/to/resolved-event.json --world path/to/baseline-copy --replay --no-render
```

Replay applies recorded effects/outcomes without rules or RNG and checks the
engine's complete baseline fingerprint. `engine_baseline` receipts are migration
records, not replayable gameplay events. Never replay into the already advanced
live save.

## World rules and baseline derivation

- `location_id` alone determines mechanical position; coordinates come from
  authored locations. Legacy topology is explicitly **undirected**. Movement
  follows one connected edge; no GM teleport is implemented. Move/wait/attack/
  introduction consume one turn. Unknown action types or fields reject atomically.
- Imported current numeric static values are frozen baselines, not reconstructed
  pre-bonus values. Effective stats = stored baseline/static value + current
  configured trait/equipment totals − frozen imported configured totals. Bounds
  apply afterward, expanded only enough to retain already out-of-bound baselines;
  inspection reports every exception. This never adds original bonuses twice.
  Trait/equipment modifier totals and original applied modifiers remain available
  for review. Derivation does not mutate the snapshot.
- `health` is separate mutable vitality. Equipment/traits never passively heal it.
  `punch_kinetic_impact` is freshly derived from explicit world formulas; archived
  historic punch values do not pretend to be reproducible current damage. The
  non-biological synthetic twin has `health: null` and no cold exposure.
- Mortal zero health or a clear current KIA marker imports `status: dead`, regardless
  of peaceful garrison prose. Dead actors cannot act. Legacy `-99` becomes
  `capabilities.cannot_die: true`, health **100**, with explicit kinetic vitality
  scaling (**500** for Warhammer). Damage leaves immortal health unchanged.
- Lost World cold uses explicit template tags, location and activation turn. The
  current atmospheric squall is **weather, not cold**. A new cold introduction
  activates on the following action. Periodic cold reads movement's overlay once
  and exposes living biological actors once even with multiple local hazards.
  Seeded miracle probability comes from the GM registry (0.01); ordinary damage
  is 15, failed survival damage 18; successful survival floor 25 uses
  `min(old_health, max(25, old_health - 15))`, so it cannot heal or revive.
- Warhammer attacks require a living co-located active threat, recognized equipped
  configured weapon, and sufficient exact ammunition resource when required.
  Armor/penetration/power are explicit config, not inferred from names. Gross attack damage
  is `weapon['power'] + punch_kinetic_impact` (where punch impact already contains trait and
  equipment kinetic multipliers once, without multiplying weapon power a second time). Resource
  consumption and damage commit together. Each attack retaliates **once, even on
  a killing blow**; periodic processing never retaliates. Companions (`participants`) can join attacks
  using melee or non-ammunition weapons without consuming companion ammunition, while invalid group
  members reject atomically. Current structural sanctuary rejects combat and hostile GM introductions.
  Combat tests disable sanctuary only in separately authored temporary copies.

  Attack action payload example:
  ```json
  {
    "type": "attack",
    "actor_id": "player_vane",
    "target_id": "threat_stalker",
    "weapon_id": "item_void_relic_blade",
    "participant_ids": ["npc_trooper_jax"],
    "group_id": "Garrison",
    "stance": "defensive_cover"
  }
  ```

- Equipment actions (`equip`, `unequip`) require possession, living actors, and recognized
  slots, ensuring items cannot be fabricated or duplicated across slots without explicit unequip.
  Character derivation exposes a read-only `audit` entry detailing static values, baseline
  modifiers, current modifiers, effective values, health, and any bounds baseline exceptions.

  Equip and unequip payload examples:
  ```json
  {"type": "equip", "actor_id": "player_vane", "item_id": "item_relic_blade_macragge"}
  {"type": "unequip", "actor_id": "player_vane", "item_id": "item_relic_blade_macragge"}
  ```

- Treatment actions (`heal`, `restore_life`): `heal` requires living co-located biological targets,
  valid recipe references, and sufficient stock, clamping to configured ceiling without lowering higher health
  or charging for full-health no-ops. `restore_life` is disabled by default and requires an explicit authored
  restoration policy, living immortal actor, co-located dead target, and consumes configured stock restoring
  status alive with health 100 while preserving existing capabilities. Lost World strictly rejects treatment
  and restoration.

  Heal and restore_life payload examples:
  ```json
  {"type": "heal", "actor_id": "player_vane", "target_id": "npc_trooper_jax", "recipe_id": "recipe_field_dressing"}
  {"type": "restore_life", "actor_id": "player_vane", "target_id": "npc_trooper_jax"}
  ```

- Trial actions (`resolve_trial`) resolve noncombat challenges, social trials, and sanctuary opportunities against
  configured difficulty checks, actor skills, and success/failure outcome stakes without violating sanctuary.
  Trials must take place at their authored `location_id`.

  Trial resolution payload example:
  ```json
  {"type": "resolve_trial", "actor_id": "player_vane", "trial_id": "trial_monastery_dispute", "recipe_id": "recipe_peace_talks"}
  ```

- Production actions (`produce`) convert registered recipe inputs into outputs at actor's location:
  ```json
  {"type": "produce", "actor_id": "player_kael", "recipe_id": "recipe_bread"}
  ```

- Typed project actions: project progression uses five discrete, validated action types rather than a generic contribution command.
  Projects require site authorization, material delivery matching bill of materials, site preparation, and authorized labor work:
  ```json
  {"type": "start_project", "actor_id": "player_kael", "project_id": "proj_active_distillery", "template_id": "proj_solar_distillery", "participant_ids": ["player_kael", "npc_worker_1"]}
  {"type": "deliver_materials", "actor_id": "player_kael", "project_id": "proj_active_distillery", "resource_id": "timber", "quantity": 20}
  {"type": "prepare_project_site", "actor_id": "player_kael", "project_id": "proj_active_distillery", "recipe_id": "prep_site_grading"}
  {"type": "work_project", "actor_id": "player_kael", "project_id": "proj_active_distillery"}
  {"type": "complete_project", "actor_id": "player_kael", "project_id": "proj_active_distillery"}
  ```
  Completed projects can grant resource rewards and earned trait rewards (applied once without passive healing),
  and map presentation reflects committed labor hours, materials, and completion state.

- Deterministic calendar progression: Lost World advances 24 turns/day with ISO offset-aware timestamps from
  anchor turn 33 / day 4 / `2026-10-09T07:30:00+07:00`; Warhammer advances 4 turns/day across 4 imperial watches
  from anchor turn 37 / day 9 / `41.999.059.M41`. The runner advances turn count atomically; dry runs and failures
  never advance clock state.

## GM proposals and sanctuary handling

```sh
python game_master.py --world lost-world --seed 7 --improvise
python game_master.py --world warhammer-40k --seed 7
```

GM reads the selected world's `disaster_pool`/`improvisation_templates`, uses seeded
selection, and exclusively creates a unique proposal. It never applies it. Lost
World has no improvisation pool: its configured disaster-pool fallback is disclosed
in the proposal. Under sanctuary, hostile and cold templates are filtered out;
Warhammer draws from authored peaceful opportunity and social templates
(pre-sanctuary combat templates remain archived in `definitions/gm-pre-sanctuary.json`).
`change_world.py --improvise`/`--force-gm` without an event also only generates a proposal;
mixing an event with these flags rejects rather than running a hidden mutation pipeline.

Arbitrary historical freeform action mechanics remain strictly constrained to typed,
validated schemas and recipes. Imported baseline records remain independently inspectable,
with unmigrated details and original state preserved under designated metadata and the exact archive.
Trusted ordinary Python rule functions are not a sandbox; filesystem write
boundaries are a workflow convention unless harness permissions enforce them.

