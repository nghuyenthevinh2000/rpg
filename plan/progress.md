# Execution ledger — plan: projects/rpg/plan/README.md

Scope: the plan's initial deliverable, with authorized baseline migration and no live gameplay turns. User approved working in place on 2026-10-09, then authorized defining the contract and adapting existing worlds. The user subsequently committed the project as a nested repository (`8dd76df`); retain those files and unrelated repository changes. No agent commits or pushes requested.

## Tasks

1. Shared contracts, read-only views, reducer, runner, journaled persistence, recovery, dry-run and replay; focused regression tests.
2. Legacy inspection/import, two world rule implementations, canonical renderer and safe CLI cutover; temporary-copy integration tests, followed by authorized live baseline migration.
3. Review integration, run final relevant suite, document operations and remaining incremental mechanics.

## Preflight interface review

| Tasks | Interface / consistency check | Decision |
| --- | --- | --- |
| 1 | Plan requires JSON Schema and custom hooks, not a partial validator | Use maintained `jsonschema`; isolated local Python environment for checks. |
| 2 | Migration must preserve baseline despite ambiguous stacked modifiers | Retain legacy metadata and report ambiguity; never guess base stats silently. |
| 3 | Initial scope versus later subsystem extraction | Clearly report unimplemented subsystems; do not claim full five-phase completion. |
| 1–2 | World contract, state envelope, effect reducer and rule hooks | Engine API established first, world integration consumes it. |
| 1–3 | Transaction and replay checks need end-to-end fixtures | Use temporary worlds and inject interrupted commits; no live save writes. |
| 2–3 | Legacy commands can bypass canonical ownership | Cutover-aware wrappers refuse unsupported mutation; rendering remains retryable. |

Ruling: Deliver initial scope before full subsystem migration — explicitly prescribed by the plan — remaining mechanics require incremental work.
Ruling: Keep live migration opt-in and develop against copied saves — avoids advancing or replacing user gameplay — saves remain legacy until the user runs migration.
Ruling: Work in place without creating commits — user requested in-place work and supplied an untracked project — changes remain uncommitted.

User steering: define the canonical contract and adjust existing worlds to it; migration-risk deliberation is not required. This authorizes baseline normalization and actual save cutover after tests, without executing a gameplay turn.
Ruling: Normalize to an explicit imported current-save baseline; snapshot legacy files and cut over both worlds after verification — user requested adapting existing worlds — the original save is recoverable from the archive if normalization is undesirable.

## Status

Task 1: complete — 37 focused engine tests passed. Independent review verified the casefold identity and full-baseline replay fixes; both findings addressed. Engine APIs/report: `engine-report.md`, scoped review: `engine-review.md`.

Task 2: implementation verified on 2026-10-12 — the cancelled worker left world integration which the user committed in nested repository `8dd76df`. Existing 30 world integration tests and 37 engine tests all pass under `uv`. Temporary-copy CLI migration/dry-run/commit/render succeeded for both worlds, live content hashes unchanged. No implementation was restarted or overwritten.

Task 3: complete — pre-cutover review clean (`worlds-review.md`); six additional temporary interrupted-directory-installation probes passed. Post-cutover full suite: 67 tests passed in 8.823s using `uv`; `git diff --check` passed. Both worlds remain at their original turns, with no gameplay events. Changes left uncommitted in place; no push or branch operation.

Live cutover completed on 2026-10-12. Lost World: turn 33/day 4, 27 original JSON archives hash-verified. Warhammer: turn 37/day 9, 48 original JSON archives hash-verified. Both custom validators pass, canonical maps rendered, snapshots unchanged by rendering, only non-gameplay `engine_baseline` receipts exist. Full pre-cutover backup: `/private/var/folders/nm/hp2tb73d0l75gl6jzvy6jfnm0000gn/T/opencode/rpg-pre-cutover-nw0p0fd5`. Durable original JSON archives reside inside each world under `archive/legacy-baseline/`.

Task 2: complete — both existing worlds now use canonical contracts, split-state baselines and world-specific rules. Shared CLI, read-only inspection and canonical rendering are operational. Earlier opt-in-only ruling was superseded by the user's normalization/cutover authorization. Unsupported historical construction, automated production/resource attrition, troop casualties and resurrection remain explicitly deferred; this completes the plan's initial scope, not every later extraction phase.

User instruction: use `uv` for Python package management. Verified command: `uv run --no-project --with-requirements requirements.txt python -m unittest discover -s tests -v` (67 tests, exit 0).

2026-10-12: previous temporary virtualenv/snapshot were not present after session resumption. Live source contents remain available and tests passed using those sources. Capture a fresh full backup immediately before cutover; original JSON bytes are also preserved by the migration archive.

Operational guidance: updated `projects/rpg/AGENTS.md` to world-neutral gameplay roles, canonical proposals, and exactly one runner invocation. Retained 1–2 sub-agent gameplay mandate; excluded development/migration/tests. Original 79 world files are hashed and independently snapshotted in the approved temporary directory before any cutover.
