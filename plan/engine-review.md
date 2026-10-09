# Task 1 engine review

## Verdict

**Changes required before integration: one Critical and one Important issue.**

The implementation substantially follows the approved initial engine design. The public rule interfaces, defensive views, ordered reducer, tentative hook contexts, net-change revisions, durable write sequence, roll-forward policy, retained duplicate receipts, and post-commit rendering boundary are clear and appropriately small. However, an ordinary accepted create can overwrite existing state on this workspace's filesystem, and replay does not establish the exact originally validated baseline on which its no-hook validation policy depends.

## Scope and evidence

- Inspected `engine/contracts.py`, `engine/state_store.py`, `engine/runner.py`, and all of `tests/test_engine.py` directly; no Git diff was used.
- Reviewed `plan/engine-brief.md`, `plan/README.md` (the approved design), `plan/semantics.md`, and `plan/engine-report.md`. The project-root `README.md` still describes the legacy engine; the applicable canonical design is in `plan/README.md`.
- The coordinator independently reported all 29 engine tests passing, exit 0. I did **not** rerun them.
- Ran two new, focused reproduction probes in disposable worlds under the approved OpenCode temporary directory using the designated virtualenv. Both findings below were reproduced. Neither probe used a live world or altered repository implementation/tests.
- No original world saves were inspected. Renderer implementation is explicitly the next task, not a finding. Trusted Python is not a sandbox; no sandbox requirement was imposed. Approved baseline migration and in-place development are not scope violations.

## Findings

### C1 — Case-distinct entity IDs can overwrite an existing entity and commit unreadable state

**Severity: Critical — accepted gameplay can destroy authoritative entity data.**

**Locations:** `engine/runner.py:86-95` (case-sensitive create identity check), `engine/state_store.py:72-81` (direct identifier-to-filename mapping), `engine/state_store.py:174-180` (after-image installation). Collection-name collision validation is also absent at `engine/contracts.py:188-191`.

`safe_id` permits both uppercase and lowercase identifiers. The reducer checks membership in a Python dictionary, which distinguishes `hero` from `HERO`. The backing case-insensitive filesystem does not distinguish `state/characters/hero.json` from `state/characters/HERO.json`. Consequently, creating `HERO` when `hero` exists passes all overlay and schema checks but replaces `hero`'s file at commit.

**Reproduction (confirmed on this workspace):**

1. Start with a valid world containing `characters/hero`, HP 10, and clock turn 0.
2. Have the trusted resolver return `{'op': 'create', 'collection': 'characters', 'entity_id': 'HERO', 'value': {'hp': 1}}`. Both entity data shapes satisfy the collection schema.
3. `run_event(..., render=False)` succeeds. Its changes contain only `characters/HERO` and `clock`; the existing hero is not recorded as an overwritten entity.
4. The original hero's file now contains envelope ID `HERO`. The next `read_snapshot()` raises `RuleError: Envelope ID differs from filename: characters/hero`.

Probe output:

```text
Filesystem case-insensitive: True
Create case alias committed; changes: ['characters/HERO', 'clock']
Subsequent snapshot error: RuleError Envelope ID differs from filename: characters/hero
```

This is not a concurrent external writer or malicious rule: it uses an allowed identifier and the ordinary supported create operation. A committed receipt will not roll the state back, and this transaction did not retain the original hero's before-image. Case-distinct collection names can likewise address the same directory. Remove/create pairs involving case aliases also need protection because sorted writes and removals can address the same file.

**Requested correction:** Define and enforce a filesystem-safe identity policy before preparing a transaction. The simplest portable policy is to reject case-fold collisions among collection names and entity IDs/transaction target references, including aliases across the before/after states. Validate existing layouts as well; do not silently rename or lowercase authored IDs. Preserve legitimate exact-ID remove/recreate behavior.

**Regression evidence needed:** On a case-insensitive filesystem, creating `HERO` alongside `hero` must reject without changing any state/history. Add coverage for case-alias collection declarations and remove/create aliases. If using a portable collision policy, the rejection tests can run on all filesystems.

### I1 — Replay can commit a state that violates the originally enforced world invariant

**Severity: Important — replay's baseline validation is incomplete.**

**Locations:** `engine/runner.py:220-237`, particularly the changed-entity-only before-image checks at lines 225-229. The report's exact-baseline justification is at `plan/engine-report.md:116`.

Replay deliberately does not execute `validate` or other world Python hooks, consistent with the approved no-rule replay requirement. That is safe only when the entire relevant baseline is the same as the state on which the archived result was validated. The implementation checks the clock, optional proposal revisions, and before-images of **changed** entities only. An unchanged entity used by `resolve` or `validate` is not covered unless the proposal author happened to supply its expected revision.

A valid non-turn event can change that entity without changing the replay's expected turn, leaving every recorded before-image equal. Replay then accepts effects originally validated against a different world state.

**Reproduction (confirmed):**

1. Start with hero HP 10, fleet fuel 3, turn 0. Define the world invariant `hero.hp <= fleet.fuel + 10`.
2. Produce a validated dry-run record for hero HP +2, advancing one turn. HP 12 is valid against fuel 3. Its changes contain hero and clock, not fleet. Validated dry-run records are explicitly supported replay inputs.
3. Commit another valid event at turn 0 that sets fleet fuel to 0 and does **not** advance the turn. HP 10 remains valid, and hero/clock envelopes are unchanged.
4. Replay the first record. It succeeds and commits HP 12 with fleet fuel 0. Calling the world's validator against the resulting snapshot returns `['cross-entity invariant']`.

Probe output:

```text
Replay accepted; current invariant violations: ['cross-entity invariant']
```

The same mismatch can arise when replaying a genuine committed record from a matching cloned baseline after applying the non-turn change to the target. No record forgery, RNG reroll, schema change, external filesystem mutation, or untrusted Python is needed.

**Requested correction:** Record an engine-generated full-baseline fingerprint (or equivalent complete snapshot identity, including entity membership and clock) with every resolved report and verify it before replay reduction/commit. Do not rely on optional caller-supplied revisions to capture rule dependencies. Retain the no-rule/no-RNG replay contract; rerunning world validation is not the requested fix.

**Regression evidence needed:** Replay must reject unchanged-effect-target records after an unrelated non-turn entity update when the original baseline differs, without writing state/history. Keep the existing successful exact-baseline replay test with unusable rule source.

## Other load-bearing checks

- Prepared journals are durably written before after-images; committed markers precede archive finalization. Recovery rolls forward prepared records and restores missing archives without reapplying committed historical state. Retained journal identity prevents reapplication after archive loss.
- The journal/archive image-agreement check and strict per-image envelopes are useful corruption guards. The existing tests exercise durable-write interruptions, creates/removals, archive loss, and repeated recovery; they do not cover the two counterexamples above.
- Contract, schema, definition, hook, state, journal, archive, and lock paths use containment/symlink checks. Schemas are checked with Draft 2020-12 and a contained local reference registry; external fetch is not enabled. JSON duplicate keys and nonfinite values are rejected.
- Reducer targets are data-only dictionary pointers, not envelope metadata or array positions. Clock advancement is engine-owned. Entity removal requires collection opt-in. Final normal-event validation sees the complete tentative overlay.
- `RuleContext`, `RuleResult`, `StateView`, `DefinitionView`, report shape, snapshot shape, and baseline initialization are sufficiently documented for world integration. Baseline receipts are explicitly distinguished from replayable gameplay records. Low-level store methods require the documented lock boundary.
- No additional Critical/Important issue was established in this review. This is not approval of renderer, world mechanics, migration content, or CLI cutover, which are outside Task 1.

## Scoped re-review — C1 and I1 corrections

**Verdict: C1 ADDRESSED; I1 ADDRESSED.** This supersedes the original changes-required verdict for these two findings only. No concrete remaining issue was found within the requested correction scope.

Reviewed the latest three engine modules, the added regression tests, and the appended correction report directly. No implementation edits, commands executing tests, commits, or subagents were used. Focused 10-test and full 37-test green results are reported by the coordinator/implementation report, not independently rerun here.

### C1 — ADDRESSED

- `contracts.py:33-40,195-202` rejects case-fold collection collisions, including reserved-clock aliases, without changing authored spelling. `contracts.py:299-315` also checks loaded/baseline collection and entity identities.
- `runner.py:76-102` retains entity identities throughout each reducer effect list, so removal does not permit a later case-alias create. `runner.py:131-132` checks the union of original and final IDs, covering aliases across primary and periodic reducers while allowing exact-ID remove/recreate.
- `state_store.py:85-104` checks existing directory spelling/filenames and transaction paths against that layout. The lock checks layout before recovery (`:28-30`). Journal validation checks target collisions and, for prepared journals, layout collisions (`:186-188`), before commit prepares a journal (`:246-248`) or recovery installs after-images (`:233-234`). Committed receipts appropriately do not compare historical targets against current entity spelling: they restore archives, not historical state.
- Baseline validation applies the entity collision guard before installation (`state_store.py:129-166`). Prepared baseline journals additionally pass the same target checks as gameplay.
- Added tests at `tests/test_engine.py:440-509` cover collection/reserved-clock aliases, create aliases, same-list and primary/periodic remove-create aliases, baseline aliases, existing layout aliases, direct-store targets, and prepared-journal recovery rejection. The existing exact-ID net-zero remove/recreate test remains present (`:429-438`).

These guards close the reproduced overwrite path and prevent aliasing before/after transaction targets from reaching durable writes.

### I1 — ADDRESSED

- `runner.py:160-163,199-202` computes and records SHA-256 over the full original committed snapshot using deterministic JSON serialization. All declared collection membership, envelopes, and the clock participate; formatting and dictionary insertion order do not.
- Replay requires the digest in strict metadata (`runner.py:220-226`) and compares it with the complete recovered current snapshot under the lock (`:236-240`), before reduction or commit. This closes the unchanged-target/non-turn-update counterexample without depending on optional proposal revisions.
- Replay still loads the contract without rule execution (`runner.py:219`) and applies recorded effects without RNG or world hooks. Successful replay preserves the recorded metadata (`:256-259`). Older records lacking the digest are rejected rather than silently using the insufficient changed-image-only fallback; this compatibility limit is documented in `engine-report.md:205`.
- Added tests at `tests/test_engine.py:511-564` reproduce the cross-entity invariant scenario and assert read-only stale-baseline rejection with rules/RNG unavailable. They also cover untouched data, revision, membership, clock changes, canonical serialization, and fingerprint completeness. Existing exact-baseline replay remains the success-path regression.

The fingerprint supplies the full-state baseline identity requested by I1. Definition/rule authoring compatibility and renderer integration remain outside this scoped re-review.
