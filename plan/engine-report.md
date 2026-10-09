# Task 1 — shared engine report

## Outcome

Implemented the initial shared engine in place, without commits, delegation, live-world edits, or existing-script edits. Final focused engine suite: **29 tests passed** in 0.571 seconds. Added the coordinator-requested durable baseline initialization API.

Owned files:

- `engine/__init__.py`
- `engine/contracts.py`
- `engine/state_store.py`
- `engine/runner.py`
- `tests/test_engine.py`
- `requirements.txt`
- `plan/engine-report.md`

Dependency: `jsonschema>=4.18,<5`; its `referencing` dependency supplies the local schema registry. No new test framework; tests use `unittest`, disposable directories, and mocked durable-write boundaries.

## Public API and integration contracts

### Contracts

```python
from engine.contracts import (
    WorldContract, RuleResult, RuleError,
    StateView, DefinitionView, RuleContext,
)

contract = WorldContract(world_dir)
```

`WorldContract` exposes `config`, `collections`, `schemas`, `validators`, loaded JSON `definitions`, defensive `definition_view`, and callable `resolve`, `after_turn`, `derive`, and `validate` attributes. `resolve` is mandatory. Defaults: `after_turn` returns an empty `RuleResult`, `derive` returns `{}`, and `validate` returns `[]`. `rule_source_hash` is SHA-256 over the referenced rule filenames and source bytes in stable order, with each module hashed once.

`WorldContract(world_dir, load_hooks=False)` validates contract and schemas and loads definitions, but does not read/execute Python rule source. Snapshot, baseline installation, and replay use this mode. It still checks the syntax and containment of configured hook paths.

`RuleResult(effects=[], outcomes={}, notes=[], advances_turn=True)` uses independent default containers. Hooks must return this type; effects and notes are lists, outcomes is an object, notes contain strings, and `advances_turn` is a boolean. Results must contain finite JSON values. Primary `resolve` owns turn policy; an `after_turn` result does not override it. Periodic outcomes merge into primary outcomes, with periodic values winning on duplicate keys; effects and notes concatenate in order.

`RuleError(code, message, details=None)` exposes these attributes and `.to_dict()`. Rule exceptions become `RuleError('rule_failure', ...)`; contract/schema/event/reducer/replay errors use structured codes. Filesystem interruptions remain filesystem exceptions so callers can distinguish uncertain durable commits from rejected resolution. Following such an interruption, recover through a store snapshot rather than blindly resubmitting the event.

`StateView(state)` captures a deep copy. `.get(collection, entity_id)` returns an envelope or `None`; `.list(collection)` returns envelopes sorted by ID. Returned objects are defensive copies. The clock is accessible through `get('clock', 'clock')` and `list('clock')`. Unknown collections return no entities.

`DefinitionView(definitions).get(name)` returns defensive JSON or `None`.

`RuleContext(state, definitions, rng, turn)` is a frozen dataclass. Context state/definitions use the views above; RNG is an engine-provided `random.Random`. `after_turn` sees the tentative post-primary-action overlay with the original turn; final `validate` sees the complete overlay, finalized revisions, and advanced turn. Custom `validate` must return a JSON-serializable list of violations; an empty list passes.

### Canonical snapshot shape

```python
snapshot = {
    'clock': {
        'id': 'clock', 'revision': 0, 'schema_version': 1,
        'data': {'turn': 0, 'day': 1, 'display_timestamp': 'Dawn'},
    },
    'characters': {
        'hero': {
            'id': 'hero', 'revision': 0, 'schema_version': 1,
            'data': {'hp': 10, 'location_id': 'home'},
        },
    },
    'fleets': {},  # Every declared collection is present, even when empty.
}
```

Collection files are `state/<collection>/<id>.json`; clock is `state/clock.json`. Only declared collections are loaded. Every envelope has exactly `id`, `revision`, `schema_version`, and object-valued `data`; filenames and IDs must agree. Revisions are nonnegative integers, and initial schema version is 1. Clock requires nonnegative integer turn/day and string display timestamp. Custom collection schemas validate data, including unknown-field policy.

### Persistence and baseline migration

```python
from engine.state_store import StateStore

store = StateStore(staged_world_dir)
receipt = store.initialize_baseline(snapshot)
snapshot = store.snapshot()

# Low-level methods load/recover/commit are intended for use under this boundary:
with store.locked():
    snapshot = store.load()
```

`initialize_baseline(snapshot)` is the authorized migration write boundary for an **empty staged canonical world**. It:

1. Requires exactly clock plus the declared collection maps; validates safe IDs, strict envelopes, collection schemas, and canonical location references.
2. Acquires the world lock and performs recovery.
3. Refuses any existing state files, symlinks, transaction history, or committed-event history. Empty state directories are allowed.
4. Installs all envelopes via a prepared journal, durable after-images, committed marker, and archive finalization. Supplied revisions are preserved.
5. Returns a JSON receipt with `kind: 'baseline'` and `event_id: 'engine_baseline'`.

The baseline receipt is retained at `transactions/engine_baseline.json` and `events/committed/engine_baseline.json`. It is **not a gameplay record and is not replayable**. History tools should exclude `kind == 'baseline'` from gameplay replay. After an interrupted baseline installation, `snapshot()`/`read_snapshot()` roll it forward; calling initialization again refuses the now-existing baseline. Baseline loading intentionally does not execute custom rule hooks; migration code must establish world-specific mechanical invariants before installation.

All durable JSON writes use a same-filesystem temporary file, flush/fsync, `os.replace`, and parent-directory fsync. Directory creation and file removals also fsync their parent. `.engine.lock` uses `fcntl.flock` and is the only normal clean-read/dry-run artifact.

Prepared transactions record exact before/after envelopes (including null creates/removals), expected revisions, and exact resolved-event archive. Recovery deterministically rolls prepared journals forward, marks them committed, and finalizes archives. Committed journals are retained as duplicate-identity receipts: losing an archive does not permit reapplication, and subsequent locked reads restore the archive. Committed historical state images are **not** reapplied when restoring missing archives.

### Runner, report, replay, renderer

```python
from engine.runner import run_event, replay_event, read_snapshot

report = run_event(world_dir, event_or_path,
                   dry_run=False, seed=0, render=False)
report = replay_event(world_dir, committed_report_or_path, render=False)
snapshot = read_snapshot(world_dir)

# Renderer callback receives one captured snapshot, after gameplay commit:
report = run_event(world_dir, event, render=lambda snapshot: render_snapshot(snapshot))
```

Events accept an object or JSON path. Strict top-level fields are `schema_version`, `event_id`, `world_id`, `expected_turn`, `action`, optional `expected_revisions`, and optional string `narrative`. Action is an object with a nonempty string `type`; world rules validate action-specific properties. Proposed top-level effects are rejected. The test world's action contains fixture effects only because its trusted resolver explicitly returns them.

`expected_revisions` is a flat mapping such as `{'characters/hero': 12, 'clock': 3}`. Checks run for both turn and non-turn actions. References must address declared collections and existing entities. IDs permit ASCII alphanumeric start, then alphanumeric/underscore/hyphen, maximum length 128.

Reports contain `event_id`, `world_id`, original `event`, `dry_run`, exact ordered `effects`, `outcomes`, `notes`, `changes`, `turn`, and `metadata`. Changes are keyed by `collection/id`, with special key `clock`, and contain exact `before`/`after` envelopes or null. Turn contains `before`, `after`, and `advances_turn`. Metadata contains seed, contract version, state schema version, and rule source hash. Existing net-changed entities advance revision once; new entities start at revision 0; net-zero edits preserve original envelopes and revisions. Non-turn actions skip periodic processing and clock advancement.

A clean dry run resolves, reduces, and validates normally but does not write state, transactions, committed events, proposals, or maps, and never invokes rendering. Recovery of an already pending transaction is still performed before resolution.

`replay_event` accepts a resolved report/archive (also a validated dry-run report for replay into its matching baseline). It executes **no rule module and no RNG**, checks event/world/turn/revisions and exact before-images, applies recorded effects and deterministic turn advancement, validates schemas/references, and verifies derived changes match recorded images. Outcomes, notes, effects, and source metadata are preserved. `dry_run` becomes false in the committed archive. Replay does not rerun world-specific `validate`: it relies on the originally validated record and the exact baseline, while enforcing current structural/reference contracts.

`read_snapshot` locks, recovers, validates, and returns defensive state for a renderer. Rendering runs outside the lock with a deep-copy snapshot captured at the commit boundary. Render failure adds `render_error` to the returned report, never replays or undoes gameplay. The immutable committed archive excludes post-commit renderer errors.

`render=True` lazily imports `engine.render_map.render_map(world_dir, snapshot)`. **That renderer is not part of this task and is not implemented here**; until integration provides it, pass `render=False` or a callable. Its absence is reported as a render error after the successful commit.

## Reducer and schema details

- Effects have strict keys `op`, `collection`, `entity_id`, with operation-specific `path`/`value`.
- `create` takes raw entity data in `value`, requires a missing ID, and validates its schema immediately. It cannot supply envelope metadata.
- `set` and `increment` require existing dictionary fields. Intermediate dictionaries are not created. Increment rejects booleans, non-numeric operands, and nonfinite results.
- Paths are JSON pointers into **data only**, with `~0`/`~1` decoding, no envelope access, root replacement, or positional array edits. Dictionary keys that happen to be numeric remain dictionary keys.
- Field `remove` requires an existing field; final schemas reject removal of required fields. Entity removal omits `path` and requires collection configuration `allow_remove: true`.
- Calendar effects may address `collection: 'clock'`, `entity_id: 'clock'`, paths `/day` and `/display_timestamp`. Clock turn remains engine-owned.
- Final validation covers every entity, canonical `location_id`, and the complete custom world invariant hook.
- Location IDs resolve against declared location entities or the `locations` definition payload. Definition locations may be ID-keyed, an array of objects with `id`, or wrapped under a `locations` key.
- Built-ins are `engine:resource`, `engine:threat`, `engine:location`, `engine:action`, and `engine:group`. They reject unknown top-level data fields and allow designated object-valued `metadata`. Common fields are name, description, status, and location_id. World-specific mechanics should use custom schemas rather than inventing fields outside a built-in schema.
- JSON Schema uses Draft 2020-12, checks each schema at load, and registers only contained local schema files. Fragment references and relative local file references work. No network retrieval is configured or permitted. Paths and symlinks are checked for contracts, schemas, definitions, logic, state, locks, transactions, and archives. Duplicate JSON keys and nonfinite JSON values are rejected.

## Test-first evidence

All commands ran from `projects/rpg` with:

```sh
PY=/private/var/folders/nm/hp2tb73d0l75gl6jzvy6jfnm0000gn/T/opencode/rpg-engine-venv/bin/python
$PY -m unittest discover -s tests -p test_engine.py -v
```

Recorded sequence:

1. Initial RED: 16 tests, 1 public-contract assertion failure and 32 missing-engine import errors/subtest errors, before production files existed.
2. First implementation run: 16 tests, 14 passed, 2 recovery-test failures. Root cause: fault-boundary comparisons used macOS `/var` fixture paths while production correctly resolved `/private/var`. Normalizing the disposable fixture path fixed the injection target.
3. Baseline RED: 18 tests, existing 16 passed, 2 new errors because `initialize_baseline` did not exist. Implemented baseline installation afterward.
4. Expanded validation run: 25 tests, 24 passed, 1 malformed replay metadata error (`list` had no `.get`). Added strict replay metadata validation. Focused GREEN: `... -k replay -v`, 2 tests passed.
5. Prepared journal image consistency RED: `... -k journal_archive -v`, 1 assertion failure. Added archive/image agreement validation before recovery writes.
6. Standard module/dataclass RED: `... -k dataclass -v`, 1 error because the dynamic rule module was absent from `sys.modules`. Registered source-specific module identities without producing rule bytecode files.
7. Immediate create validation RED: `... -k create_must -v`, 1 assertion failure. Added immediate create-envelope/schema validation, including creates subsequently removed.
8. Net-zero remove/recreate RED: `... -k identical_entity -v`, 1 failure (captured revision incorrectly reset from 7 to 0). Preserved the original envelope for net-zero changes.
9. Final GREEN, exact full command above: **29 tests passed**, exit 0, 0.571 seconds.

Recovery tests inject interruptions after every durable transaction write boundary, before clock installation, and during archive finalization. They also cover creates/removals, idempotent repeated recovery, missing committed archives, baseline installation interruption, and corruption detection. These are real filesystem tests with mocked interruption boundaries, not physical power-loss testing.

## Deliberate limits and integration concerns

- Trusted Python only: defensive views are not a sandbox. Rules must not directly mutate files, consult wall time, or use external randomness. Directly referenced rule source is hashed; imported helper/dependency source is not part of that hash.
- No live-world migration or mechanic/renderer integration performed. Existing scripts remain unchanged and must not remain alternate gameplay mutation paths after coordinator cutover.
- Custom references other than canonical location IDs belong to the world `validate` hook. The engine does not invent actor, equipment, group membership, mortality, or resource semantics.
- Schemas must be object documents. `$id` must be omitted or equal the contained file URI; nested `$id` is unsupported. Remote logical schema IDs and external references are rejected conservatively. Extend only for an actual world-schema need.
- Retained journal receipts make duplicate identity durable but cause locked recovery scans proportional to event history. Initial scope favors straightforward correctness; compaction would require preserving identity receipts and migration/version policy.
- One exclusive lock per world; external readers that bypass engine snapshots have no consistent multi-file-read guarantee. Low-level store methods require the documented lock boundary.
- Engine-owned revision policy is based on net committed differences, not number of individual effects. New envelopes begin at revision 0.
- Contract/state schema version 1 only; schema migrations and historical-schema upgrades are not implemented.
- Custom baseline invariants and world-specific replay validation are intentionally not executed as Python hooks; baseline authoring and archived validated records provide those guarantees.
- Default renderer integration remains outstanding; pass a callback or `render=False` until provided.

## Review corrections — C1 and I1

Addressed both verified findings in `plan/engine-review.md`, with failing regressions before implementation. This section supersedes the earlier changed-image-only replay baseline justification. No public method signatures changed; no live worlds, existing scripts, commits, or subagents were involved.

### C1: portable casefold identity safety

Authored identifiers retain their exact spelling. A shared collision guard raises `RuleError('casefold_collision', ...)` when different names have the same `.casefold()` value; it never lowercases or silently renames IDs.

Guards cover:

- Collection declarations, including aliases of the reserved `clock` collection.
- Baseline and loaded-state entity membership, scoped per collection.
- Existing state directory spelling and entity filenames, checked before recovery can write.
- Reducer targets, retaining identities removed earlier in the same ordered effect list.
- The union of before/after entity IDs, including removal in primary resolution followed by a case-alias create in `after_turn`.
- Journal target aliases, and prepared transaction targets against the existing filesystem layout, before preparing/installing state. Direct `StateStore.commit` and pending-journal recovery use the same guard.

Exact-ID removal/recreation remains valid, including the existing revision-preserving net-zero regression. Uppercase identifiers remain valid when they do not alias another identity. Read-only rejection assertions compare state, history, definitions, and rule bytes; the existing lock artifact is excluded as documented above.

Existing-layout tests inject directory enumeration containing case aliases so they run on both case-sensitive and case-insensitive filesystems; assertions require the collision error code rather than accepting an unrelated missing-file error.

### I1: full-state replay baseline metadata

Every gameplay report/archive now includes required **`metadata.baseline_sha256`**, a lowercase 64-character SHA-256 hex digest of the complete committed snapshot before resolution. The canonical byte encoding is:

```python
json.dumps(snapshot, sort_keys=True, separators=(',', ':'),
           ensure_ascii=False, allow_nan=False).encode('utf-8')
```

It covers all declared collection membership (including empty collections), every envelope's identity/revision/schema version/data, and the complete clock envelope. File whitespace and dictionary insertion order do not affect the fingerprint. Gameplay history, filesystem paths, definitions, and rule source are not part of this state fingerprint; existing contract/schema/source metadata remain separate.

Replay validates the digest's format and compares it with the entire recovered current snapshot before effect reduction or commit. A mismatch raises **`RuleError('stale_baseline', ...)`**, even if changed-entity before-images, optional caller revisions, and expected turn still match. Original metadata, including the fingerprint, is preserved on successful exact-baseline replay. No rule module, world validation hook, or RNG is executed.

**Compatibility:** older gameplay records lacking `baseline_sha256` are rejected for replay because changed-only images cannot reconstruct the missing proof. Existing committed receipts still recover normally; baseline installation receipts remain non-gameplay/non-replayable and retain their existing metadata shape.

### Regression evidence

Working directory: `projects/rpg`. Interpreter remains the approved brief virtualenv:

```sh
PY=/private/var/folders/nm/hp2tb73d0l75gl6jzvy6jfnm0000gn/T/opencode/rpg-engine-venv/bin/python
```

RED, before production fixes:

```sh
$PY -m unittest discover -s tests -p test_engine.py -k casefold -v
# 6 tests; 7 assertion failures including subtests, proving absent alias guards.
$PY -m unittest discover -s tests -p test_engine.py -k full_baseline -v
# 2 tests; 2 assertion failures: missing digest and accepted unrelated non-turn change.
```

Focused GREEN after the fixes:

```sh
$PY -m unittest discover -s tests -p test_engine.py -k casefold -v
# 6 passed.
$PY -m unittest discover -s tests -p test_engine.py -k full_baseline -v
# 2 passed.
$PY -m unittest discover -s tests -p test_engine.py -k casefold -k full_baseline -k replay -v
# 10 passed, exit 0, 0.260 seconds; includes existing exact-baseline replay.
```

The cross-entity reproduction uses `hero.hp <= fleet.fuel + 10`, records hero HP +2, then commits a valid non-turn fleet fuel change. Replay rejects without writing any state/history. Fingerprint tests also cover untouched data, revision, membership, clock changes, and formatting-insensitive identity. Both rejected and successful replay tests block `random.Random` construction and make the rule source unusable.

Final engine suite was run **once after focused regressions**:

```sh
$PY -m unittest discover -s tests -p test_engine.py -v
# 37 tests passed, exit 0, 0.764 seconds.
```
