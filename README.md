# Multi-world RPG engine

AI proposes intent; selected-world rules resolve it; **only the shared runner and
StateStore write canonical gameplay state**. Narrative is metadata, not a patch.
Commands below run from `projects/rpg/`.

## Setup and verification

Python 3.10+ on a POSIX platform (`fcntl` world locks), plus JSON Schema:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
```

Development tests copy saves into temporary directories. They prefer each
world's `archive/legacy-baseline` after migration, otherwise the approved
original snapshot if available, otherwise the unmigrated save. They never
advance a live world and do not activate the gameplay sub-agent mandate.

## Inspect and migrate

Migration is available for **both** current worlds. The coordinator will cut
over both actual saves after implementation verification; implementation tests
do not perform that live cutover. Migration is not a turn.

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
  Armor/penetration/power are explicit config, not inferred from names. Resource
  consumption and damage commit together. Each attack retaliates **once, even on
  a killing blow**; periodic processing never retaliates. Current structural
  sanctuary rejects combat and hostile GM introductions. Combat tests disable
  sanctuary only in separately authored temporary copies.

## GM proposals and initial scope

```sh
python game_master.py --world lost-world --seed 7 --improvise
python game_master.py --world warhammer-40k --seed 7
```

GM reads the selected world's `disaster_pool`/`improvisation_templates`, uses seeded
selection, and exclusively creates a unique proposal. It never applies it. Lost
World has no improvisation pool: its configured disaster-pool fallback is disclosed
in the proposal. Warhammer's hostile pool is stale versus sanctuary: proposals
are marked inspection-only and rules refuse application. `change_world.py
--improvise`/`--force-gm` without an event also only generates a proposal; mixing
an event with these flags rejects rather than running a hidden mutation pipeline.

Construction fulfillment, automated resource consumption/production, troop
casualties, resurrection, narrative patching, GM relocation, and arbitrary
historical action mechanics are **not executable** in this initial scope. Imported
actions/resources/groups remain independently inspectable, with unsupported
details/history preserved under designated metadata and the exact archive.
Trusted ordinary Python rule functions are not a sandbox; filesystem write
boundaries are a workflow convention unless harness permissions enforce them.
