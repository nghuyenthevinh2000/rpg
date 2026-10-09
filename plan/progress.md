# Execution ledger — plan: projects/rpg/plan/README.md

Scope: the plan's initial deliverable, with opt-in migration and no live gameplay or save cutover during development. User approved working in place on 2026-10-09. Existing RPG files are untracked; unrelated repository changes must remain untouched. No commits or pushes requested.

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

Task 2: in progress — world integration dispatch was interrupted by an incoming notification/progress question; resume the same implementer session, not a duplicate.

Operational guidance: updated `projects/rpg/AGENTS.md` to world-neutral gameplay roles, canonical proposals, and exactly one runner invocation. Retained 1–2 sub-agent gameplay mandate; excluded development/migration/tests. Original 79 world files are hashed and independently snapshotted in the approved temporary directory before any cutover.
