# Task 1 focused review

## Verdict

**Changes requested: one load-bearing compatibility blocker.** Task 1's fixture extraction, relative imports and helper-source provenance otherwise satisfy the scoped plan. Quality is acceptable apart from the new rule-source availability prerequisite on no-hook operations.

Reviewed `git diff -- engine/contracts.py tests/test_worlds.py`, new `tests/world_fixtures.py` and `tests/test_rule_sources.py`, Task 1 in `plan/remaining-mechanics.md`, and `plan/remaining-task1-report.md`. Compared the prior `HEAD:engine/contracts.py` implementation with the current replay/snapshot/recovery call paths. No implementation edits, test reruns, commits, nested agents or live writes were performed; this review document is the only write.

## Blocker

### P1 — Unavailable Python rule sources now block replay, snapshots and recovery

**Location:** `engine/contracts.py:284–304`, especially the required-hook-source check at lines 292–294 and the source reads at line 291, before the `load_hooks=False` return.

Previously, after validating each hook reference/path/suffix, `WorldContract(load_hooks=False)` skipped source loading entirely. A missing ordinary `logic/rules.py` or missing logic directory was therefore compatible with these operations, provided the contract, schemas, definitions and canonical save remained available. Unreadable rule source likewise was not consulted.

The new implementation always scans and reads Python sources and requires every declared hook source to be captured. Removing `logic/rules.py` now necessarily raises `RuleError('invalid_hook', 'Missing rule source: ...')` even with `load_hooks=False`; an unreadable captured helper can also raise `invalid_hook`. This is a source-inspection-confirmed behavioral regression, not a rule-execution concern:

- `replay_event` constructs the no-hook contract at `engine/runner.py:219`, before applying the archived effects. Its replay metadata validation checks the recorded hash's shape, not equality with current source (`runner.py:220–230`); current Python source is not needed to replay.
- `read_snapshot` delegates to `StateStore(world_dir).snapshot()` (`runner.py:264–265`), and `StateStore.__init__` constructs the same no-hook contract (`engine/state_store.py:17`). A readable canonical save is no longer inspectable when rule files are unavailable.
- Default `StateStore` construction fails before `locked()` can reach journal recovery (`state_store.py:22–30`, `221–234`). Thus durable prepared transactions cannot be recovered through the normal store/snapshot API until unrelated rule authoring is restored.

**Required correction:** preserve source-independent no-hook replay/snapshot/recovery while keeping complete, strict captured-source hashing and containment for executable hook loading. Do not weaken the existing hook-reference/path validation or normal execution's source checks. The newly added requirement that no-hook loading always produces a current source hash should not become a prerequisite for these operations.

**Regression coverage needed:** an exact-baseline archived replay with the declared hook file (or whole logic directory) absent, a snapshot read with absent rules, and normal journal recovery with absent rules. Where practical, cover a rule-source read failure as well. Confirm normal hook loading still rejects unavailable sources. The current raising-source replay test (`tests/test_rule_sources.py:106–116`) proves nonexecution but cannot detect this availability regression because all required files remain readable.

## Accepted aspects

- **Relative imports and hash accuracy:** contained `.py` files under declared hook directories are recursively captured, deduplicated by path and hashed in deterministic world-relative order. Path/separator/byte-length/source encoding is unambiguous. Unimported helpers and nested package sources affect provenance; copy location and bytecode do not.
- **Stale helper reuse:** namespace identity includes directory identity and the full captured source hash. Changed helper bytes select a new package; compiling captured bytes avoids timestamp/size-based stale bytecode. Existing loaded contracts retain their captured version. The finder prevents imports within registered namespaces from falling through to unhashed filesystem source.
- **Python compatibility:** ordinary relative imports and nested packages are supported without changing global `sys.path`; modules are registered by import machinery before execution, retaining dataclass/annotation support. No new dependency or plugin API is introduced.
- **Containment:** declared hooks and scanned candidates use `contained_path`; helper file/directory symlinks and escapes are rejected before source reads. The tests cover internal/external helper-file symlinks and a helper-directory symlink. The no-hook availability blocker does not justify bypassing existing path validation.
- **Fixture behavior:** the base class contains helpers only; the tracked diff preserves all 30 existing test bodies. Archive-backed copying intentionally removes the machine-specific fallback as planned. The public helper signatures match Task 1. Authored state is installed in a fresh safe-ID-named temporary directory exclusively through `StateStore.initialize_baseline`, excluding canonical history/state, migration artifacts, locks and bytecode. Compatibility aliases preserve the original world-test calls.
- **Reported evidence:** accepted the execution report's **9 focused + 30 original world tests passing** without rerunning them. Those results support the covered paths but do not establish compatibility when rule sources are unavailable. No additional speculative performance, plugin or unrelated mechanics findings are raised.

## Approval condition

Resolve the no-hook source-availability prerequisite and add targeted compatibility coverage. No other scoped blocker was identified.

## Scoped P1 re-review — addressed

**Verdict: P1 addressed; approved for the previously blocked compatibility scope.** This supersedes the initial changes-requested verdict above.

Inspected the revised `engine/contracts.py` diff, current focused tests, and the appended execution-report evidence. The no-hook return now occurs immediately after declared hook-reference/path/suffix validation and before source traversal, reads, required-source checks, hashing or package registration. It restores the historical empty-input hash and source independence for replay, default snapshot reads and journal recovery. Executable loading retains strict captured-source hashing, containment and availability checks.

The four added focused tests cover exact-baseline replay and snapshots with a deleted hook or absent logic directory; prepared-transaction recovery through `read_snapshot` without logic, including exact snapshot/archive comparison and repeat-read stability; unreadable Python-source injection for no-hook loading/replay/snapshots with executable-loading rejection; and preserved unsafe/invalid hook-reference rejection. The existing no-hook test now checks the historical empty hash and no module registration, rather than requiring source inspection.

Accepted the report's **13/13 focused tests and 4/4 unmodified core compatibility checks passing**, without rerunning tests or the full suite. Missing-source recovery and unreadable-source replay/snapshot coverage, together with the early-return placement, address the identified prerequisite across all three APIs. No remaining P1 blocker in this scoped re-review. No implementation edits, nested agents or live writes; only this verdict was appended.
