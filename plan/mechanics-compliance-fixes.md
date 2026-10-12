# RPG Mechanics Compliance Fixes Implementation Plan

> **For agentic workers:** Use `executing-plans` or `subagent-driven-development` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. Repository budget-first rules override repeated review gates and automatic commits.

**Goal:** Fix every confirmed mismatch from the remaining-mechanics review without rewriting the working engine or advancing live saves.

**Architecture:** Repair the existing world resolvers and validators, reuse finite-number/resource helpers, and add focused regressions for each failure. Keep canonical effects, journaled commits, replay, and baseline-relative derivation intact. Extend rendering with an optional captured committed receipt rather than storing duplicate outcome state.

**Tech Stack:** Python 3.10+, existing `jsonschema`, `unittest`, standard library, and `uv`; no new dependencies.

**Spec:** `remaining-mechanics-spec.md`, with task-level acceptance details in `remaining-mechanics.md`. This document addresses review findings, not a new mechanics expansion.

## Global Constraints

- Use `uv` for Python package management.
- Only StateStore writes authoritative canonical state; world functions return effects.
- Preserve `resolve -> overlay -> after_turn once -> validation -> journaled commit -> render`.
- Custom rules use engine RNG; replay applies archived effects without rules or RNG.
- Reject unknown action fields, invalid references, insufficient resources, and stale events without partial writes.
- Keep equipment bonuses baseline-relative; derivation is read-only and never passively changes health.
- Damage cannot reduce immortal health; mortal zero health means dead. Survival floors never heal or revive.
- Preserve Lost World's no-global-scarcity/no-violent-apocalypse constraints and Warhammer's current sanctuary. Combat-enabled worlds are temporary authored test copies.
- Archived historical records are not executable projects or a replayable history. Do not retroactively charge their costs or reapply their rewards.
- Schema additions must accept existing canonical baselines and existing committed records. Do not change `schema_version: 1` to 2 without a separate versioned migration design.
- Development tests use temporary world copies, never live gameplay turns. Actual gameplay retains the 1–2 sub-agent mandate in `AGENTS.md`.
- Do not advance or rewrite live saves during implementation verification. Any live initialization or gameplay activation is an explicit later operation.
- Do not commit, push, or discard unrelated work unless requested.

## Baseline, scope, and execution order

Review baseline: commit `72f1aba`; 142 tests passed; hashes for 104 authoritative/history/archive files remained unchanged. Capture fresh hashes when implementation begins rather than assuming this count is permanent.

All file paths and commands below are relative to `projects/rpg/`. This is planning only. Do not execute corrective changes merely by loading this document.

Deliver Tasks 1–3 first (conservation and mechanical authorization), then Tasks 4–6 (remaining compliance), then Task 7 (integration and operational guidance). Run focused red/green tests for each task and one final relevant full suite. No persistence rewrite, new rule language, general equipment framework, baseline rebasing, or live policy activation is included.

## File responsibilities

| Files | Responsibility |
| --- | --- |
| Both `logic/trials.py`; Warhammer `logic/treatment.py` | Validate fixed recipes and conserve stock atomically |
| Both `logic/rules.py` | Compose configuration validators, enforce introduction sites, and keep existing hooks |
| Warhammer `logic/combat.py` | Validate deployed member references and prevent free companion ammunition |
| Warhammer `logic/inventory.py`; new Lost World `logic/rewards.py` | Strict, idempotent earned trait effects |
| Both `logic/projects.py` | Support trait outcomes in fingerprinted project definitions |
| Both `logic/calendar.py` | Validate anchor types, world cadence, and offset-aware time |
| Warhammer `game_master.json`, `definitions/engine_rules.json`; `game_master.py` | Peaceful live pools and consistent proposal filtering |
| `engine/render_map.py`, `engine/runner.py`, `engine/state_store.py` only if a receipt capture helper is needed | Render a snapshot-matched committed receipt without another gameplay pass |
| Existing subsystem tests; `tests/test_remaining_mechanics.py` | Regression and composed-flow coverage |
| `README.md`, `plan/remaining-progress.md` | Correct intent examples and actual verification evidence |

### Task 1: Validate treatment/trial policies and conserve trial resources

**Files:** Both `world/<id>/logic/trials.py`, Warhammer `logic/treatment.py`, both `logic/rules.py`, `tests/test_trials.py`, `tests/test_treatment.py`.

**Interfaces:** Add `validate_trials(ctx) -> list[dict]` in each trial module and `validate_treatment(ctx) -> list[dict]` in Warhammer treatment. Invoke them in pre-resolution configuration validation and final world validation. Reuse `resources._number(value, positive=False)` and `_capacity(ctx, resource_id)`; retain `resolve_trial(ctx, event)` and `resolve_treatment(ctx, event)`.

- [x] Add runner-level rejection cases for negative, boolean, nonnumeric, and nonfinite recipe costs/rewards/healing values. Compare complete pre/post snapshots on rejection; do not merely call a helper. Configure invalid policies in temporary copies with `edit_rules`; nonfinite JSON cases use in-memory definitions or assert existing strict JSON loading rejects them before resolution.
- [x] Run the focused suites red:
  `uv run --no-project --with-requirements requirements.txt python -m unittest discover -s tests -p test_treatment.py -v`
  and the same command with `-p test_trials.py`.
- [x] Validate exact recipe field names and container shapes. Trial costs/rewards are ID-keyed maps of finite nonnegative numbers; zero is a harmless authored no-op. Treatment `resource_cost`, `heal_amount`, and `health_ceiling` must be finite positive numbers. Validate existing resource/template/location references and boolean structural requirements. Restoration `enabled` must be a boolean; when enabled require the specified `primordial_life_restoration` resource, cost 1, and restored health 100. Keep absent/disabled restoration inert. Return structured configuration errors rather than raw arithmetic/lookup exceptions.
- [x] Replace independent cost/reward setters with one net quantity effect per resource, ordered by ID. Require original stock to cover the cost before allowing rewards; capacity applies to final stock:

```python
for resource_id in sorted(set(costs) | set(rewards)):
    old = ctx.state.get('resources', resource_id)['data']['quantity']
    cost = costs.get(resource_id, 0)
    reward = rewards.get(resource_id, 0)
    if old < cost:
        raise RuleError('insufficient_resources', resource_id)
    final = old - cost + reward
    capacity = _capacity(ctx, resource_id)
    if capacity is not None and final > capacity:
        raise RuleError('resource_capacity', resource_id)
    if final != old:
        effects.append(_set('resources', resource_id, '/quantity', final))
```

- [x] Assert the exact cases: old 8000/cost 5/reward 10 -> 8005 and one resource effect; old 0/cost 5/reward 10 -> unchanged rejection; old at capacity/cost 5/reward 5 -> accepted net-zero stock; actual net overflow -> unchanged rejection. Cover both worlds.
- [x] Run both focused suites green; retain existing healing ceiling, immortal immunity, dead-target, and restoration capability tests. Leave live treatment/resource registries conservative.

### Task 2: Enforce trial sites and replace hostile live GM authoring

**Files:** Both `logic/rules.py` and `logic/trials.py`, Warhammer `game_master.json` and `definitions/engine_rules.json`, `game_master.py`, `tests/test_trials.py`, affected `tests/test_worlds.py` fixture setup.

**Interfaces:** Retain `allowed_templates(contract)` and `propose_event(world_dir, *, seed=0, improvise=False)`. Both introduction and completion consume the authored template/recipe `location_id`; new peaceful trials require an explicit site. No arbitrary location event or reward fields are added.

- [x] Add a regression introducing crystal-garden repair at `loc_shrine_aquila` rather than `loc_hab_block_vermin`; assert exact location error and unchanged snapshot. Add a separately authored misplaced trial proving resolution also rejects it.
- [x] Run `uv run --no-project --with-requirements requirements.txt python -m unittest discover -s tests -p test_trials.py -v` red.
- [x] Require explicit template-site equality when a template declares a location. Keep old location-less combat templates usable only in combat fixtures. Require recipe site, trial site, and actor site to agree on completion:

```python
site = recipe['location_id']
if actor['data']['location_id'] != site or threat['data']['location_id'] != site:
    raise RuleError('trial_location', 'Configured trial site required')
```

- [x] Preserve and verify existing `definitions/gm-pre-sanctuary.json`; never overwrite it or the immutable migration archive. Remove hostile entries from active Warhammer disaster/improvisation pools and active mechanical template registry. Give improvisation a peaceful pool, or an empty pool using the existing explicitly disclosed disaster fallback. Combat tests copy hostile authoring from the separate archive into their temporary definitions, not the live pool.
- [x] Use the same allowed-template filtering semantics in ordinary and improvisation proposal generation; seed selection after filtering. Missing/forbidden templates cannot be selected. Empty eligible pools return structured `no_templates`; proposal generation remains the only write and occurs only in temporary copies during tests.
- [x] Replace the misleading premature-activation test. Author a co-located temporary trial with `activation_turn = current_turn + 1`, assert exactly `trial_inactive`, then confirm eligibility on the following action. Introduction at turn 37 commits turn 38 and is legitimately eligible for the next action at turn 38; do not add an extra waiting turn.
- [x] Run trial and affected world focused suites green. Check normal and improvisation sanctuary proposals dry-run successfully, while explicitly injected hostile fixtures still reject under sanctuary.

### Task 3: Reject invalid groups and free ranged companion attacks

**Files:** `world/warhammer-40k/logic/combat.py`, `logic/rules.py` if a shared reference check is needed, `tests/test_group_combat.py`.

**Interfaces:** Keep `resolve_attack(ctx, event, derive_fn)` and the current typed attack fields. For this repair, companions use recognized equipped melee weapons or an explicitly authored non-ammunition default weapon. Do not silently select a ranged weapon with an unpaid ammunition requirement. Named actor ranged attacks retain their existing exact resource/ammunition checks.

- [x] Add two failing cases: a companion equipped only with an ammo-backed lasgun and no stock, and a deployed count-3 group with a nonexistent member ID. Assert unchanged health, ammo, group, threat, and clock.
- [x] Run `uv run --no-project --with-requirements requirements.txt python -m unittest discover -s tests -p test_group_combat.py -v` red.
- [x] Remove the arbitrary any-weapon companion fallback. Select an authored melee/default non-ammo weapon deterministically; otherwise raise `companion_weapon`. A default cannot be fabricated from caller-supplied power or an unrecognized ID. Supporting ranged companions with aggregate per-participant ammo expenditure is a separate expansion, not necessary to satisfy the existing melee/default specification.
- [x] Validate every selected group's stored member reference against `ctx.state.get('characters', member_id)` before proposing effects; reject missing references with `invalid_group`. Preserve imported historical groups without inferring a troop count or changing their baselines. Count/deployment remain required for casualty-enabled selection.
- [x] Retain positive count, unique/co-located living participants, stance multipliers, killing-blow retaliation, and immortality tests. Add a successful valid group/melee-companion case and an actor ranged attack proving ammo still debits once. Run the focused suite green.

### Task 4: Complete and validate earned trait rewards in both worlds

**Files:** Warhammer `logic/inventory.py`, new Lost World `logic/rewards.py`, both `logic/projects.py`, both `logic/trials.py`, both `logic/rules.py`/audit where needed; `tests/test_inventory.py`, `tests/test_projects.py`, `tests/test_trials.py`.

**Interfaces:** Warhammer retains `trait_reward_effects(ctx, actor_id, trait_ids) -> list[dict]`; Lost World's reward module exposes that exact signature without enabling equipment actions. Add `validate_trait_rewards(ctx, trait_ids) -> list[dict]` in those modules for project/trial configuration validation. `trait_rewards` is an optional unique ID list on project templates and trial recipes.

- [x] Add runner-level project reward tests in both worlds and a Lost World trial reward test using a recognized previously unowned trait. Assert trait granted once, health unchanged, frozen baseline unchanged, and repeat completion/resolution rejected. The existing direct-helper test alone is insufficient.
- [x] Add strict cases for unknown IDs, a string instead of a list, duplicate reward IDs, and malformed `max_max_strength` modifier keys. Run inventory, project, and trial focused suites red.
- [x] Replace `key.replace('max_', '')` with exact supported-key validation. Numeric runtime modifiers must target the world's supported stats with finite values. Inventory legacy `physical_vitality` and known `max_*` declarations must be explicitly identified as legacy non-runtime vitality/cap metadata, not inferred by prefix stripping; expose this classification in audit rather than silently pretending they affect stats. They never heal health or change caps in this correction. Keep existing archived declarations loadable; reject malformed/unknown keys on newly awarded traits.
- [x] Implement idempotent effects using the existing set-union pattern:

```python
current = actor['data']['traits']
new_traits = sorted(set(current) | set(trait_ids))
if new_traits == sorted(current):
    return []
return [_set('characters', actor_id, '/traits', new_traits)]
```

Validate actor/reward definitions before this calculation; do not return success for invalid IDs or missing actors.

- [x] Extend project template validation to allow optional `trait_rewards`; it naturally participates in the existing full-template fingerprint. Completion composes trait effects, existing resource rewards, and the completed marker into one `RuleResult`. Trial recipes use the same world-specific helper. Reject bad rewards before any stock debit or completion marker.
- [x] Do not add live rewards to existing templates or rewrite in-flight fingerprints just to exercise the feature; author rewarded copies in tests. Confirm both live worlds still load and their existing baselines derive identically. Run affected focused suites green.

### Task 5: Make calendar validation strict and cover replay/recovery

**Files:** Both `logic/calendar.py`, `tests/test_calendar.py`.

**Interfaces:** Retain `validate_calendar(ctx) -> list[dict]` and `calendar_effects(ctx) -> list[dict]`. Absent calendar remains optional. Authored calendar policy has exactly the five specified fields; retain the existing `display_style` spellings `iso_hours` for Lost World and `watches` for Warhammer. Do not change live anchors.

- [x] Add failing cases for `turns_per_day=True`, `anchor_turn=current_turn+1`, negative/noninteger/boolean anchors and days, wrong style, unknown fields, and a Lost World timestamp with no UTC offset. Assert structured `calendar_config` rejection and unchanged snapshot.
- [x] Run `uv run --no-project --with-requirements requirements.txt python -m unittest discover -s tests -p test_calendar.py -v` red.
- [x] Reject boolean integer aliases, future anchors relative to the current snapshot turn, and malformed policy containers. Preserve the specified fixed cadence: Lost World 24 turns/day and one hour/turn; Warhammer 4 watches/day. Validate timestamp as a nonempty string; for Lost World require `datetime.fromisoformat(...).utcoffset() is not None`; Warhammer never ISO-parses its timestamp:

```python
valid_anchor = type(anchor_turn) is int and 0 <= anchor_turn <= ctx.turn
valid_day = type(anchor_day) is int and anchor_day >= 0
valid_rate = type(turns_per_day) is int and turns_per_day == required_rate
```

- [x] Keep completing-turn calculation `ctx.turn + 1`. Add exact replay into a fresh matching baseline, interrupted calendar commit recovery using the existing fault-injection pattern, and a no-turn action fixture proving no periodic clock updates. Avoid editing the live anchors; loading remains read-only.
- [x] Run the calendar focused suite green, including existing offset-preserving rollover, dry-run, and failure checks.

### Task 6: Render captured committed outcomes safely

**Files:** `engine/render_map.py`, `engine/runner.py`, `engine/state_store.py` only for a small read helper if needed; `tests/test_remaining_mechanics.py`, renderer-focused regressions in `tests/test_worlds.py`/`tests/test_engine.py` when interfaces change.

**Interfaces:** Preserve compatibility with `render_map(world_dir, snapshot=None)` by adding optional keyword-only `committed_event=None`. The runner passes its captured committed report alongside its captured snapshot. Independent rendering captures both current state and its latest matching gameplay receipt under one StateStore lock. No state schema additions or gameplay replay.

- [x] Add failing render assertions for structured combat injuries/casualties, healing amount, resource outcomes, and escaped outcome/narrative text from a committed temporary event. Verify independently retried rendering displays the same receipt. Add baseline-only rendering with no gameplay receipt and a stale-snapshot case.
- [x] Run `uv run --no-project --with-requirements requirements.txt python -m unittest discover -s tests -p test_remaining_mechanics.py -v` red.
- [x] Render a `Last Event Outcomes` section from `committed_event['outcomes']` using the existing HTML escaping. Capture the receipt inside the same locked state/history boundary; validate that its `changes` after-images and turn match the snapshot. For independent render, select the latest matching gameplay receipt by committed turn, excluding `engine_baseline`, not filesystem mtime. Initial baselines show no fabricated outcomes. Keep journal recovery and history reads locked; do not duplicate outcomes into canonical state.
- [x] Retain fingerprint comparison and atomic map replacement. A runner rendering an older captured snapshot must fail `stale_render`, not silently substitute a newer event. Renderer retry never calls resolution, RNG, periodic processing, or replay.
- [x] Label peaceful sanctuary threats `Trials and Opportunities` using authored world labels, rather than an engine-wide rename. Retain project hours/materials/completion and resource units from captured envelopes. Run focused render regressions green.

### Task 7: Composed acceptance flows and accurate operational documentation

**Files:** `tests/test_remaining_mechanics.py`, `README.md`, `plan/remaining-progress.md`.

**Interfaces:** Use existing `TemporaryWorldCase.make_world`, `author_state`, `event`, and `edit_rules`; run all gameplay effects through `run_event`, and exact replay through `replay_event` on fresh baselines. Do not inherit whole test cases to reuse fixture methods.

- [x] Add one temporary flow: configured production -> project start -> materials -> site preparation -> labor -> completion/earned trait -> peaceful introduction -> trial completion -> calendar rollover. Choose small authored requirements where needed to keep it focused. Assert numeric stock conservation, final project completion, one trait instance, unchanged baseline/health except explicit rules, and clock advancement once per successful action.
- [x] Add a separate combat-enabled temporary flow: possession-aware equip -> valid participant/group attack -> resource-backed heal -> explicitly enabled restoration. Check ammo, bounded casualties, final health/status, preserved capabilities, and rejection of duplicate/repeated operations.
- [x] Exercise archived effects and interrupted recovery on representative corrected multi-entity actions, using fresh exact baselines and existing StateStore injection patterns. Do not resolve rules again during replay. Add the HTML-bearing project name to the rendering fixture so its escaping assertion is meaningful rather than checking for a string never inserted.
- [x] Run `uv run --no-project --with-requirements requirements.txt python -m unittest discover -s tests -p test_remaining_mechanics.py -v` and address only failures introduced/revealed by these requirements.
- [x] Replace unsupported README names `trial` and `contribute_project`. Document exact payload examples for `produce`, all five project actions, `equip`/`unequip`, optional attack participants/group/stance, `heal`, `restore_life`, and `resolve_trial`. Explain recipe/site authorization, melee/default companion boundary, restoration disabled by default, empty live resource registries, and separately authorized live activation. Keep `uv`, archive/recovery, inspection-only commands, and gameplay-agent instructions.
- [x] Run the final suite once:
  `uv run --no-project --with-requirements requirements.txt python -m unittest discover -s tests -v`.
  Run `git diff --check` and compare pre/post content hashes for both worlds' `state/`, `events/committed/`, `transactions/`, and `archive/legacy-baseline/`. Record actual counts/commands/results in the ledger, plus intentionally inactive policies. No promised fixed test count: the 142-test review baseline is not a substitute for new regressions.
- [x] Review the diff for scope: no live authoritative edits, archive overwrites, automatic rebases, new dependencies, commits, or pushes. Report any blocked criterion explicitly instead of marking the original Tasks 1–9 complete by inference.

## Coverage and acceptance checklist

| Review finding | Fix task |
| --- | --- |
| Negative/invalid treatment and trial costs | 1 |
| Same-resource trial costs overwritten by rewards | 1 |
| Caller-relocated trials | 2 |
| Hostile active live pools and unusable improvisation | 2 |
| Misleading premature-activation regression | 2 |
| Free companion ranged ammunition | 3 |
| Nonexistent combat group members | 3 |
| Missing project/Lost World earned traits | 4 |
| Unsupported trait modifier keys | 4 |
| Boolean rates, future anchors, missing timestamp offsets | 5 |
| Missing structured committed outcome rendering | 6 |
| Missing combined acceptance flows and incorrect action docs | 7 |

Completion requires every focused rejection to be atomic, corrected effects to conserve resources, traits to be earned exactly once without passive healing, and clocks/outcomes to survive replay/recovery. Both live worlds must remain readable at their existing committed clocks; verification must not alter live state/history/archives. Implementation changes remain in place and uncommitted unless the user separately asks otherwise.
