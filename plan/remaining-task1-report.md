# Task 1 execution report

**Review update:** The P1 correction appended below supersedes the initial
no-hook hashing behavior and its test expectations described in this report.
No-hook operations now preserve source-independent compatibility and the empty
SHA-256 convention.

Task 1 only is implemented in place, uncommitted. No resource/project mechanics,
world rule authoring, policy activation, schema changes, or live gameplay are
included. Existing unrelated and initial-engine work was preserved.

## Owned files

- `engine/contracts.py`: contained helper-source provenance and scoped imports.
- `tests/world_fixtures.py`: new helpers-only `TemporaryWorldCase`.
- `tests/test_worlds.py`: fixture extraction; all 30 existing tests remain in
  `WorldsTests`, with their test bodies unchanged.
- `tests/test_rule_sources.py`: nine focused regressions.
- `plan/remaining-task1-report.md`: this report.

## Fixture API

```python
TemporaryWorldCase.make_world(name='lost-world') -> Path
TemporaryWorldCase.author_state(world, transform, label) -> Path
TemporaryWorldCase.event(world, action, event_id='test_event') -> dict
TemporaryWorldCase.edit_rules(world, transform) -> None
```

- `make_world` copies the selected world's immutable `archive/legacy-baseline`
  into the case's temporary directory, overlays current logic/schema/contract
  authoring, then migrates that temporary copy. The former machine-specific
  temporary-snapshot fallback is removed; archives are required fixtures.
- `author_state` takes a detached snapshot, calls an in-place transformation,
  and copies world authoring into a fresh, safe-ID-named directory. It excludes
  state, events, transactions, archives, migration journals/staging, locks,
  Python bytecode, and engine temporary files. `StateStore.initialize_baseline`
  exclusively installs the authored canonical save. Its own
  `engine_baseline.json` is expected; prior committed gameplay is not copied.
- `event` captures the current turn and world ID without loading rules and
  accepts the planned `event_id` keyword.
- `edit_rules` applies an in-place transform to the copied rules definitions.
- Compatibility helpers `legacy`, `world`, and `edit_baseline` keep the original
  world tests unchanged. The base case contains no inherited tests. `hashes`
  excludes bytecode and lock files when checking copy/live content stability.
- Copy names and authored labels must be fresh; collisions fail instead of
  overwriting another fixture. These helpers are for temporary test worlds,
  not a live-authoring interface.

## Loader and provenance

The contract validates declared hook paths, gathers all contained `.py` sources
recursively under their parent directories, and hashes each unique source once
in world-relative path order. Hash input includes the relative path, a separator,
the source byte length, and exact source bytes. Hook files shared by several
hook references, or encountered through overlapping directories, are deduplicated.
Unused helpers also affect provenance. Non-Python files and bytecode do not.

`contained_path` checks candidates before source reads, rejecting symlinks and
escapes, including helper-directory symlinks. Hashing never imports or compiles
Python. `load_hooks=False` computes the same source provenance but does not
register packages or execute hook/helper modules.

Each hook directory gets a `ModuleType` namespace package with a contained
`__path__`. Its name includes directory identity and the **full** source hash.
Hook and helper modules are registered by Python's import machinery, retaining
standard dataclass/annotation support. Ordinary `.resources` imports and nested
helper packages work without modifying global `sys.path`.

A private, namespace-filtered finder/loader on `sys.meta_path` compiles only
captured source bytes. This bypasses stale timestamp/size-validated `.pyc` files,
including same-size edits with the original timestamp restored. Imports outside
registered rule namespaces use ordinary Python behavior; missing sources inside
those namespaces cannot fall through to unhashed filesystem imports. Captured
sources also support later imports from an already loaded hook.

## Red/green evidence

Commands ran from `projects/rpg/`, using `uv`, with no dependency additions.

### Focused red (once, before loader implementation)

```sh
uv run --no-project --with-requirements requirements.txt python -m unittest discover -s tests -p test_rule_sources.py -v
```

Result: **9 tests; FAILED (failures=5, errors=3)**, exit 1, 1.497 seconds.
The required helper edit regression failed with identical source hashes.
No-hook helper edits likewise left the empty hash unchanged; helper symlinks
were not rejected; relative imports failed with no known parent package.

The initial run also exposed two test-harness details, corrected before green:
`initialize_baseline` legitimately creates `engine_baseline.json`, and a failed
symlink subtest needed `finally` cleanup before its second target. The package
path assertion was normalized for macOS's `/var` versus `/private/var` alias.
The source-hash equality failure was observed before any production change.

### Focused green

The same focused command ran after implementation: **9/9 passed**, exit 0,
1.601 seconds. Coverage includes:

- changed contained helper provenance;
- no-hook hashing without execution;
- relative imports, dataclasses, and stale-bytecode same-size edits;
- nested and unused helper sources;
- location-independent provenance and bytecode exclusion;
- internal/external helper-file and helper-directory symlink rejection;
- archived event replay against an exact baseline despite raising helper/hook
  source, with exact resulting snapshot equality;
- fresh authored baselines, unchanged source copy, and fixture API keywords.

### Existing world regression suite (once)

```sh
uv run --no-project --with-requirements requirements.txt python -m unittest discover -s tests -p test_worlds.py -v
```

Result: **30/30 passed**, exit 0, 8.026 seconds. No inherited test duplication.
Existing migration/archive preservation and live-content checks passed.

```sh
git diff --check -- engine/contracts.py tests/test_worlds.py
```

Result: exit 0, no whitespace errors in the tracked implementation diff.

## Limits and controller handoff

- Task verification totals **39 passing tests** across the two scoped runs.
  The supplied 67-test baseline was not rerun; one final full relevant suite
  remains the controller's batch-level responsibility.
- The controller owns the authoritative 104-file pre-batch hash capture and
  its final comparison. This subagent did not recapture or replace that evidence
  and made no edits to live state, histories, archives, transactions, or proposals.
  Tests create and advance only temporary copies.
- Namespace modules and captured source maps remain process-local for the
  interpreter lifetime, as does the single scoped finder. There is no eviction
  or plugin API; long-lived bulk-authoring sessions may retain multiple versions.
- Trusted Python rules remain trusted: this is containment/provenance, not a
  sandbox. Standard-library/external imports are not recursively fingerprinted;
  no dependency scanner was added. Root hook directories are namespace packages;
  nested authored `__init__.py` files execute only when imported.
- Source hashes intentionally change format/coverage; archived events remain
  replayable because replay applies archived effects without executing rules.
  No historical record was rewritten.
- No commit, push, nested agent, or live-policy activation occurred.

## P1 review correction — source-independent no-hook operations

Read `plan/remaining-task1-review.md` and verified the source-availability
regression in `WorldContract`: source collection happened before the no-hook
return, preventing default StateStore construction and recovery when Python
authoring was absent or unreadable.

### Minimal production correction

Moved the `load_hooks=False` return immediately after declared hook-reference
validation, before source traversal, reads, hashing, or package registration.
Contract/config, collection schemas, definitions, and syntactic contained hook
references still validate. No-hook `rule_source_hash` again equals the historical
SHA-256 of empty input:

```text
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

Only normal executable `load_hooks=True` loading captures the real source
fingerprint. Its source containment, availability checks, relative imports,
namespace isolation, and bytecode-free compilation remain unchanged. There are
no changes to replay, runner metadata, snapshots, or journal implementation.

### Revised focused coverage

Replaced the extra no-hook current-hash expectation with the historical empty
hash/nonexecution expectation, including absence of new rule-module registrations.
Helper symlink checks now exercise executable loading, where source inspection
belongs. No production core regression tests were edited.

Added four tests (13 focused tests total):

- Exact-baseline snapshots and archived replay work with a deleted declared
  hook file or an absent whole logic directory; executable loading still rejects
  both with `invalid_hook`.
- A durable prepared transaction recovers through the ordinary `read_snapshot`
  API after its logic directory disappears. The snapshot and committed archive
  exactly match an uninterrupted temporary twin; another snapshot is stable.
- No-hook contract loading, replay, and snapshots work when Python source reads
  raise `PermissionError`; executable loading still rejects the read failure.
  The read-failure injection is limited to Python source bytes, not canonical
  state/config/schema/definition reads.
- No-hook loading still rejects traversal, absolute paths, backslash paths,
  non-Python hook suffixes, invalid function names, and malformed references.

### Red/green evidence (focused only)

```sh
uv run --no-project --with-requirements requirements.txt python -m unittest discover -s tests -p test_rule_sources.py -v
```

- **Red before correction:** 13 tests; **FAILED (failures=1, errors=4)**, exit 1,
  2.639 seconds. Failures showed the nonempty no-hook hash, attempted source read
  under `PermissionError`, missing-source snapshot failures for both variants,
  and missing-source failure before pending journal recovery.
- **Green after correction:** **13/13 passed**, exit 0, 2.888 seconds.

Unmodified core compatibility checks:

```sh
PYTHONPATH=tests uv run --no-project --with-requirements requirements.txt python -m unittest test_engine.EngineTests.test_replay_preserves_metadata_without_resolve_or_rng test_engine.EngineTests.test_snapshot_recovers_interrupted_create_remove_commit test_engine.EngineTests.test_recovery_when_archive_write_fails test_engine.EngineTests.test_contract_rejects_unsafe_paths_invalid_schemas_and_hooks -v
```

Result: **4/4 passed**, exit 0, 0.108 seconds.

```sh
git diff --check -- engine/contracts.py tests/test_worlds.py
```

Result: exit 0, no whitespace errors. This correction ran **17 passing scoped
checks**, not another full/world suite. Prior 30-world-test evidence remains as
recorded above. The fixture API is unchanged; controller-owned authoritative
hash verification and final batch verification remain with the controller.
All event/replay/recovery writes were in disposable temporary worlds. No live
writes, commits, pushes, or nested agents occurred.
