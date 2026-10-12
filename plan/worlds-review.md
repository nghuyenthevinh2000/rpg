# World integration pre-cutover review

Reviewed nested-repository commit `8dd76df` against the overriding user steering in
`plan/worlds-brief.md`, `plan/semantics.md`, and the initial scope in
`plan/README.md`. Engine-core C1/I1 were already independently reviewed and were
not re-reviewed here. No implementation changes, reversions, commits, delegation,
live migration, or gameplay were performed.

## Verdict

**Spec: PASS for the initial cutover scope. Quality: no verified critical or
important cutover blockers found.** Both existing worlds can proceed through the
documented migration command without a gameplay turn. This is not approval of
every historical subsystem or a general security audit.

- **Critical blockers: none found.**
- **Important blockers: none found.**

## Reviewed boundaries

- **Baseline and data preservation:** `world_migration.py:99–275` imports current
  save values rather than replaying events. Static values and configured modifier
  totals are frozen separately; health remains mutable and authoritative.
  Death/KIA and `-99` normalization follow the chosen policies. Original character
  records, progress, unresolved historical participants, and unsupported fields
  remain metadata; exact source save/definition/history JSON bytes and SHA-256s
  are retained (`:59–75`, `:339–345`). Unsupported mechanics are not silently made
  executable.
- **Archive and contract-last safety:** existing archive/state/history/staging
  destinations are refused (`world_migration.py:333–335`); source/archive hashes
  are checked before installation and on resume (`:322–325`, `:363–364`). A staged
  baseline is authored only through `StateStore.initialize_baseline` (`:362`).
  State/history directories install before `world.json`, and the installed full
  baseline fingerprint is verified before that final replacement (`:286–306`).
  A preparing journal refuses retries; ready journals allow explicit resume.
  CLI gameplay remains disabled while journal finalization is pending
  (`world_utils.py:28–35`).
- **References and write ownership:** import blocks invalid active locations,
  character aliases/identities, and equipped ID references; historical unresolved
  participants remain non-executable metadata. Root gameplay entry points route
  to the same runner. Stat/progress inspection does not apply effects, direct
  `save_progress` refuses writes, and GM generation exclusively creates proposals
  (`world_cli.py:23–55`, `world_utils.py:54–55`, `game_master.py:37–49`).
- **Mortality and timing:** both worlds require living actors and undirected
  connected movement. Lost World cold uses explicit tags/location/activation,
  reads post-movement state, exposes each living biological character once, keeps
  immortals immune, and cannot heal via a survival floor
  (`world/lost-world/logic/rules.py:47–89`). Warhammer sanctuary rejects attacks
  and hostile introductions; combat checks target/weapon/ammunition, returns one
  final retaliation even on a killing blow, and has no periodic retaliation
  (`world/warhammer-40k/logic/rules.py:21–84`). New introductions use `ctx.turn + 1`,
  consistent with the documented original-turn periodic context.
- **Snapshot rendering:** `engine/render_map.py` consumes one defensive canonical
  snapshot and definitions, never standalone legacy character/progress files.
  Display values are escaped, the player is marked at canonical coordinates, and
  empty collections are hidden. Full-snapshot comparison and atomic replacement
  occur under the engine lock (`:62–78`), rejecting older captured renders.
  Documented rendering retries do not replay gameplay.

## Verification evidence

- Coordinator supplied: **67 passing tests** from
  `uv run --no-project --with-requirements requirements.txt python -m unittest discover -s tests -v`.
  Coordinator also supplied successful migration/dry-run/temporary commit/render
  smoke checks for both worlds and unchanged live hashes. These were not rerun.
- Reviewed the relevant `tests/test_worlds.py` coverage, including source/archive
  preservation, baseline-relative derivation, mortality, cold activation/overlay,
  sanctuary, ammunition rejection/debit, retaliation, proposal-only GM, disabled
  legacy writers, escaped/stale rendering, and migration refusal/resume.
- Independently ran **six focused temporary-world fault reproductions** through
  `uv run --no-project --with-requirements requirements.txt python`: interruption
  immediately after each `state`, `transactions`, and `events` directory rename,
  for each world. All six retained original legacy `world.json`, left a ready
  journal, refused pending gameplay, resumed successfully, preserved archive
  hashes, and retained initial turn 33/37. Temporary directories used the approved
  OpenCode temporary root. No full suite or live writes were performed.

## Scope limits

Construction, automatic resources/production, troop casualties, resurrection,
arbitrary narrative patches, and other unextracted historical systems remain
unsupported as authorized. Trusted Python rules and filesystem write ownership
are workflow conventions, not sandbox guarantees. No additional approval gate
or speculative subsystem expansion is needed before this initial cutover.
