# Remaining RPG Mechanics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` or `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Follow repository budget-first rules; do not add repeated approval/review gates or automatic commits.

**Goal:** Complete resources, projects, equipment/traits, group combat/treatment, peaceful GM trials, and fictional calendar progression on the existing canonical engine.

**Architecture:** Retain the engine's validated event/effect/transaction pipeline. Add typed per-world policies and small ordinary Python rule helpers; no new rule language. Deliver independently testable stages, with resources and construction as the first execution batch.

**Tech Stack:** Python 3.10+, JSON Schema through the existing `jsonschema` dependency, `unittest`, POSIX locks, and `uv` package management; no additional dependencies.

**Spec:** `projects/rpg/plan/remaining-mechanics-spec.md` (proposed authoritative requirements); preserve engine constraints in `projects/rpg/plan/README.md` and `projects/rpg/plan/semantics.md`.

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

All paths below are relative to `projects/rpg/`. Run commands from that directory. Status: proposed; implementation has not begun.

## Delivery order and checkpoints

| Stage | Tasks | Depends on | Independently usable result |
| --- | --- | --- | --- |
| A: resource mechanics | 1–2 | Existing engine | Typed stock policies and atomic recipe production |
| B: project fulfillment | 3 | A | Material delivery, paid labor, exactly-once completion |
| C: equipment/traits | 4 | Existing engine; B for project rewards | Possession-aware gear changes and stable derivation |
| D: combat/treatment | 5–6 | A, C | Group attacks, casualty accounting, healing and gated restoration |
| E: peaceful GM | 7 | A, B, C | Playable sanctuary opportunities and earned rewards |
| F: calendars/operations | 8–9 | Prior action semantics | Deterministic calendars and documented end-to-end checks |

Start with A–B. Later stages are separate execution batches, not reasons to redesign completed work. No live gameplay or activation is included in these checkpoints.

## File map

- `tests/world_fixtures.py`: extract reusable temporary-world helpers from `tests/test_worlds.py`, including archive-backed initial saves, authored snapshots and event construction; no inherited test duplication.
- `world/<id>/logic/resources.py`, `projects.py`, `inventory.py`: world-specific resource, project and gear behavior respectively. Define each only when its task needs it.
- `world/warhammer-40k/logic/combat.py`, `treatment.py`: expanded combat and treatment, reusing the existing resolver rather than a second mutation command.
- `world/<id>/logic/trials.py`, `calendar.py`: validated trial rewards and fictional calendar calculations.
- `world/<id>/logic/rules.py`: retain mandatory hook entry points; route typed actions and compose consequences in documented order.
- `world/<id>/definitions/engine_rules.json`: explicit policy registries, rates and calendar configuration; no mechanical values inferred from prose.
- `world/<id>/schemas/{resource,action}.schema.json`: stricter resource shape and backward-compatible historical/project action branches.
- `world/<id>/{world,contract}.json`: update schema/definition references together, not state files; keep the current schemas/version supported.
- `game_master.py`, `engine/render_map.py`, `inspect_world.py`, `README.md`: proposal filtering, committed-state presentation, audits and operations.

`engine/state_store.py` and journal/replay machinery need no rewrite. Task 1 adds a per-world, source-hash-namespaced Python package for the declared hook directory, allowing ordinary relative imports such as `from .resources import periodic_resources`. Give the package a contained `__path__`, register package/hook modules in `sys.modules`, and retain standard dataclass support; do not alter `sys.path` globally or create a new plugin interface. Hash contained helper source before executing the package. Replay still must not execute helpers.

## Verification commands

Baseline and final relevant suite:

```sh
uv run --no-project --with-requirements requirements.txt python -m unittest discover -s tests -v
```

Each task's focused command uses its exact new test filename. Run red once, implement, then green; investigate failures with focused tests. Run the final relevant suite once per delivered batch, not after every edit. Tests must use temporary copies and compare live content hashes excluding Python bytecode/lock files. Do not generate live diagnostic proposals or replay live events.

### Task 1: Reusable fixtures and helper-source provenance

**Files:** Modify `tests/test_worlds.py`, `engine/contracts.py`; create `tests/world_fixtures.py`, `tests/test_rule_sources.py`.

**Interfaces:** Produce `TemporaryWorldCase.make_world(name='lost-world') -> Path`, `author_state(world, transform, label) -> Path`, `event(world, action, event_id='test_event') -> dict`, and `edit_rules(world, transform) -> None`. Helper state is installed exclusively through `StateStore.initialize_baseline` into a new directory. No live file is edited by fixtures.

- [ ] Extract existing legacy-copy/migration/edit/event helper behavior into a base case containing helpers only; keep all existing 30 world tests in `WorldsTests`. Prefer `archive/legacy-baseline` fixtures, never depend on a specific machine's temporary snapshot. Implement `author_state` in a fresh named directory, copying definitions/logic/schemas but excluding `state`, `events`, `transactions`, migration journals/staging and lock files, then call `StateStore.initialize_baseline`.
- [ ] Add a failing regression proving a changed contained helper changes the recorded source hash:

```python
def test_helper_source_changes_provenance(self):
    world = self.make_world()
    helper = world / 'logic/resources.py'
    helper.write_text('VALUE = 1\n')
    first = WorldContract(world).rule_source_hash
    helper.write_text('VALUE = 2\n')
    self.assertNotEqual(first, WorldContract(world).rule_source_hash)
```

- [ ] Run `uv run --no-project --with-requirements requirements.txt python -m unittest discover -s tests -p test_rule_sources.py -v`; expect hash equality to fail before the fix.
- [ ] Conservatively hash contained `.py` files in the declared hook directories, ordered by relative path, including hook files once. Reject helper symlinks/escapes with existing `contained_path`; do not import helper source for hashing. Add a scoped package namespace using `ModuleType`, `__path__` and registered hook names so `from .resources import VALUE` works without global path changes. Include the full contained source hash in namespace identity to avoid stale helper reuse after authoring changes. Keep `WorldContract(load_hooks=False)` and replay free of rule execution. No dynamic dependency scanner or package framework.
- [ ] Add a no-hook replay regression where helper source raises at import, and verify existing archived replay succeeds from an exact baseline. Run focused tests green and existing world tests after the fixture extraction. Leave changes uncommitted unless requested.

### Task 2: Stock policies and atomic production recipes

**Files:** Create `world/lost-world/logic/resources.py`, `world/warhammer-40k/logic/resources.py`, both `schemas/resource.schema.json`, `tests/test_resources.py`; modify both rule entry points, rules definitions, `world.json` and `contract.json` schema references.

**Interfaces:** `resolve_production(ctx, event) -> RuleResult`; `periodic_resources(ctx) -> RuleResult`; `validate_resources(ctx) -> list[dict]`. Read `resource_policies` and `resource_recipes`; return resource effects and, only for permitted Warhammer shortages, health/status effects. Lost World's resource helper never emits starvation health effects.

- [ ] Write the numeric periodic regression using a combat-enabled Warhammer temporary world and resource `test_water`:

```python
def test_production_precedes_consumption_once(self):
    world = self.resource_world(quantity=8, capacity=10,
                                production=4, consumption=3)
    report = run_event(world, self.event(world, {
        'type': 'wait', 'actor_id': 'player_vane'}), render=False)
    self.assertEqual(7, read_snapshot(world)['resources']['test_water']['data']['quantity'])
    self.assertEqual(1, len(report['outcomes']['resources']))
```

`resource_world` is a local fixture built with Task 1 helpers: author the resource envelope with quantity 8 and configure capacity 10, production 4, consumption 3, damage 0; disable sanctuary only in that copy.

- [ ] Run `uv run --no-project --with-requirements requirements.txt python -m unittest discover -s tests -p test_resources.py -v`; expect unchanged quantity 8 before implementing periodic policies.
- [ ] Implement `final = max(0, min(capacity, old + production) - consumption)` and unmet consumption from the capped pre-consumption value. Do not silently clip an already invalid baseline exceeding an authored capacity; reject configuration. Emit one final effect per changed quantity; periodic resource updates have stable ID order.
- [ ] Add schema/config rejection tests for negative/nonfinite rates, zero/nonfinite recipe costs where positive costs are required, missing policy target, over-capacity output, unknown action fields and a sanctuary shortage policy with damage. Verify dead/immortal/null-health targets are not damaged and shortage damage never heals. Sum damage across resource policies before emitting one final health/status effect per character; test two shortages of 5 and 7 produce exactly 12 damage, not just the last penalty.
- [ ] Add a production recipe fixture consuming 5 twigs and 2 water to output one warming supply. Reject insufficient inputs atomically; successful production debits both and credits output once. Existing live policies remain absent or zero-rate; do not mint missing input/output entities.
- [ ] Compose `periodic_resources` with existing hooks: Lost World quantities then existing cold (no resource health overlap); Warhammer resource consequences read post-attack health, with no repeated retaliation. Merge named outcomes rather than overwriting cold/combat outcomes.
- [ ] Add recovery/replay/duplicate tests proving quantity effects apply once and original 75 JSON archive hashes remain unchanged. Run focused tests green.

### Task 3: Paid, reference-safe projects

**Files:** Create both worlds' `logic/projects.py`, both `schemas/action.schema.json`, `tests/test_projects.py`; modify hook dispatch/validation, definitions and both contract schema references.

**Interfaces:** `resolve_project(ctx, event) -> RuleResult`, `validate_projects(ctx) -> list[dict]`; consume Task 2 resources and spec `project_templates`. New project IDs identify instances, not template IDs.

- [ ] Create a local `project_world` fixture: living Kael plus Marcus at `loc_monastery`, empty historical action table for this authored construction scenario, stock quantities 40 cedar/25 granite, actor credits 949999, and valid structural facts. Add:

```python
def test_start_project_charges_cost_once(self):
    world = self.project_world()
    event = self.event(world, {'type': 'start_project', 'actor_id': 'player_kael',
        'template_id': 'action_build_structure', 'project_id': 'hall_1',
        'participant_ids': ['player_kael', 'npc_marcus_the_drifter']})
    run_event(world, event, render=False)
    state = read_snapshot(world)
    self.assertEqual(899999, state['characters']['player_kael']['data']['stats']['universal_dividend_balance'])
    self.assertEqual(0, state['actions']['hall_1']['data']['hours_committed'])
```

- [ ] Run `uv run --no-project --with-requirements requirements.txt python -m unittest discover -s tests -p test_projects.py -v`; expect unsupported action before dispatch exists.
- [ ] Define historical/new-project disjoint schemas and typed start/deliver/work/prepare/complete action schemas. Permit non-string values only in these validated typed actions: participant list and finite positive delivery quantity. Preserve existing strict string-only movement dispatch; Task 5 explicitly extends attack's participant list. Register manual-work sites through typed `project_sites` definitions, not narrative inference.
- [ ] Implement starting costs once, participants and co-location checks, template fingerprint, material transfers and one-hour-per-participant labor. Use engine-managed create/revisions, not direct file writes. Reject dead workers, insufficient credits, illegal structural facts, over-delivery and missing resource IDs.
- [ ] Add exact examples: deliver 40 cedar -> stock 0/project 40; work with two living participants -> +2 hours; full project completion -> completed once; insufficient granite -> entire event unchanged; dead participant -> rejection; template hash change -> rejection; historical completed monastery record -> duplicate construction rejected without replaying costs.
- [ ] Add a peaceful Warhammer repair fixture requiring 12 hours and 2 crystal pylons. Keep sanctuary enabled and verify no health drain, bloody tithes or combat is introduced by repair. Translate only the selected templates; unsupported legacy actions still reject.
- [ ] Implement the fixed `sever_telemetry` and `reject_drones` site-preparation recipes, which set only their existing condition fields and consume one turn. Reject other sites, unknown recipes, caller-supplied booleans and duplicate preparation. Completion returns configured project/resource effects only after all requirements hold; test missing conditions and repeated completion. Earned trait effects are added in Task 4, not assumed here. Run focused tests green.

### Task 4: Possession-aware gear, earned traits, and derivation audit

**Files:** Create `world/warhammer-40k/logic/inventory.py`, `tests/test_inventory.py`; modify Warhammer rule dispatch/derive/validate, `world_migration.py` canonical inspection, `inspect_world.py`, `README.md`. Lost World continues rejecting mechanical equip until its registry is authored; add its reward validation in `logic/rules.py`.

**Interfaces:** `resolve_inventory(ctx, event) -> RuleResult`; `trait_reward_effects(ctx, actor_id, trait_ids) -> list[dict]` in each world's inventory/reward helper, used by project/trial completion; read-only `audit_character(ctx, actor_id) -> dict` showing static, baseline modifier totals, current totals, effective values and health. Include its result under `derive(...)["audit"]`, so canonical inspection can expose it through the existing derive hook without a new contract hook or circular helper imports.

- [ ] Author a fixture where Vane owns `item_relic_blade_macragge` in inventory and has no currently equipped melee weapon; preserve frozen baseline modifier totals. Add:

```python
def test_equip_transfers_possession_without_healing(self):
    world = self.gear_world()
    before = read_snapshot(world)['characters']['player_vane']['data']['health']
    run_event(world, self.event(world, {'type':'equip', 'actor_id':'player_vane',
                                     'item_id':'item_relic_blade_macragge'}), render=False)
    data = read_snapshot(world)['characters']['player_vane']['data']
    self.assertIn('item_relic_blade_macragge', data['equipment'])
    self.assertNotIn('item_relic_blade_macragge', data['inventory'])
    self.assertEqual(before, data['health'])
```

- [ ] Run `uv run --no-project --with-requirements requirements.txt python -m unittest discover -s tests -p test_inventory.py -v`; expect unsupported equip before implementation.
- [ ] Implement equip/unequip as recognized-ID list transfers, explicit occupied-slot rejection, no possession fabrication, no duplicates; one turn each. Keep worn gear as legitimate existing ownership without changing baselines.
- [ ] Add tests for wrong possession, unknown item, occupied slot, unequip twice, dead actors and a repeated equip/unequip cycle returning original derived stats without bonus stacking or vitality changes. Do not force historical narrative clothes into equipment state.
- [ ] Add validated earned trait rewards to project completion, reject unknown/unsupported modifier keys and prove a repeated completion cannot add another reward. Do not expose unrestricted trait grants.
- [ ] Correct and document Warhammer attack multiplier order: kinetic includes configured trait/equipment multipliers once; gross attack = configured weapon power + that kinetic value. Add a fixed numeric regression that distinguishes this from multiplying the weapon a second time.
- [ ] Extend read-only canonical inspection with the derivation audit; compare state hashes before/after audit. Run focused tests green. Manual baseline recalibration remains an explicit authoring operation, not an automatic migration.

### Task 5: Named-participant combat and group casualties

**Files:** Create `world/warhammer-40k/logic/combat.py`, `tests/test_group_combat.py`; modify Warhammer resolve/validation, `definitions/engine_rules.json`, and custom group schema/reference if required. Preserve current single-actor attack behavior apart from Task 4's documented multiplier correction.

**Interfaces:** `resolve_attack(ctx, event) -> RuleResult`; optional intent fields `participant_ids`, `group_id`, `stance`. Group validation requires `count` and location for casualty-enabled deployments; historical member-only garrison remains valid but cannot be treated as a combat troop count.

- [ ] Create a combat-enabled fixture with two living co-located heroes, 100 health each, zero armor, threat retaliation 60, sufficient configured ammunition, and a group count 3. Add:

```python
def test_one_retaliation_pool_and_bounded_group_casualties(self):
    world = self.group_combat_world()
    report = run_event(world, self.group_attack(world), render=False)
    self.assertEqual(1, report['outcomes']['retaliations'])
    self.assertEqual(30, report['outcomes']['injuries']['player_vane']['damage'])
    self.assertEqual(30, report['outcomes']['injuries']['npc_ogryn_bragg']['damage'])
    self.assertEqual(0, read_snapshot(world)['groups']['squad']['data']['count'])
```

`group_attack` supplies actor Vane, target enemy, recognized equipped melee weapon, those two participant IDs, `group_id: squad`, and neutral stance. It is a test fixture, not a live event.

- [ ] Run `uv run --no-project --with-requirements requirements.txt python -m unittest discover -s tests -p test_group_combat.py -v`; expect strict action rejection before extension.
- [ ] Validate unique living/co-located participants, actor membership, configured companion weapon mechanics, group count/deployment and exact stance allowlist. Reject participant stats, damage, armor or casualty numbers supplied by the caller.
- [ ] Compute outgoing attacks deterministically by ID, one retaliation pool, armor once per recipient and group casualties `min(count, floor(raw_retaliation / 15))`. Apply group, ammo, threat and character effects in one RuleResult; never in periodic processing.
- [ ] Test final retaliation on killing blow, defensive/aggressive multipliers, dead/remote/duplicate participants, zero-count groups, immortal immunity, depletion/replay and sanctuary rejection before any cost. Run focused tests green.

### Task 6: Resource-backed healing and explicit gated restoration

**Files:** Create `world/warhammer-40k/logic/treatment.py`, `tests/test_treatment.py`; modify both worlds' dispatch to clearly reject/handle their allowed treatment actions, Warhammer policies and README.

**Interfaces:** `resolve_treatment(ctx, event) -> RuleResult`; `heal` includes `actor_id`, `target_id`, `recipe_id`; `restore_life` includes only actor and target. Restoration policy defaults disabled. No engine metadata or capabilities are implicitly changed by treatment.

- [ ] Author a fixture with living co-located actor/target, target health 40, one med-supply, treatment amount 25, ceiling 100 and resource cost 1. Add:

```python
def test_heal_consumes_stock_and_changes_health_atomically(self):
    world = self.treatment_world()
    run_event(world, self.event(world, {'type':'heal', 'actor_id':'player_vane',
        'target_id':'npc_ogryn_bragg', 'recipe_id':'field_medication'}), render=False)
    state = read_snapshot(world)
    self.assertEqual(65, state['characters']['npc_ogryn_bragg']['data']['health'])
    self.assertEqual(0, state['resources']['med_supply']['data']['quantity'])
```

- [ ] Run `uv run --no-project --with-requirements requirements.txt python -m unittest discover -s tests -p test_treatment.py -v`; expect unsupported treatment before implementation.
- [ ] Implement strict recipe-backed healing and reject missing stock, remote/full-health/dead/null-health targets. Clamp only to configured ceiling; do not lower health already exceeding it or charge for a no-op.
- [ ] In a separately authored sanctuary fixture, enable restoration and test living immortal actor, co-located dead target, one `primordial_life_restoration` consumed, status alive/health 100, existing capability retained. Disabled policy, wrong actor, empty stock, already-live target and Lost World restoration all reject atomically.
- [ ] Confirm no existing live companion is revived during tests or configuration loading; tests author fixture states through StateStore only. Run focused tests green.

### Task 7: Peaceful GM templates and exactly-once trial rewards

**Files:** Modify `game_master.py`, both rule dispatchers, Warhammer `game_master.json` and both rules definition registries; create both `logic/trials.py`, `tests/test_trials.py`; preserve old authoring in `world/warhammer-40k/definitions/gm-pre-sanctuary.json` without editing `archive/legacy-baseline`.

**Interfaces:** `resolve_trial(ctx, event) -> RuleResult`; `allowed_templates(contract) -> list[dict]` in `game_master.py`; `introduce_threat` retains its canonical name. Consume Task 2 resource recipes and Task 4 trait reward validation.

- [ ] Add a sanctuary proposal regression:

```python
def test_sanctuary_proposal_is_playable_and_state_is_unchanged(self):
    world = self.make_world('warhammer-40k')
    before = read_snapshot(world)
    proposal = propose_event(world, seed=7)
    self.assertEqual(before, read_snapshot(world))
    report = run_event(world, proposal, dry_run=True, render=False)
    self.assertIn('threat_id', report['outcomes'])
    self.assertEqual(before, read_snapshot(world))
```

- [ ] Run `uv run --no-project --with-requirements requirements.txt python -m unittest discover -s tests -p test_trials.py -v`; expect sanctuary rejection with the current hostile pool.
- [ ] Archive active old GM authoring once, then author the three named peaceful templates from the spec and matching typed recipes; expose correct labels `Trials and Opportunities` through world rules definitions. No resource or health rewards supplied in proposal JSON.
- [ ] Change sanctuary introduction validation from unconditional rejection to forbidden-tag rejection; retain attack prohibition. Filter GM pools by structural constraints before seeded selection, return a structured `no_templates` when none are allowed, and keep exclusive proposal creation/proposal-only writes.
- [ ] Resolve active eligible trials through strict completion recipes, fixed prerequisites/resource costs and recognized once-only rewards. Mark inactive only in the same transaction. Reject premature next-turn activation, wrong location, unknown recipe and repeated resolution. Use existing sequential-turn expected/revision checks.
- [ ] Update old tests deliberately: sanctuary hostile introductions still reject; peaceful proposals now dry-run successfully rather than containing an inspection-only stale-template marker. Keep Lost World pools isolated and cold activation unchanged. Run focused tests green.

### Task 8: Deterministic two-world calendar progression

**Files:** Create both `logic/calendar.py`, `tests/test_calendar.py`; modify both `after_turn` composition and rules definitions. No change to engine-owned `/turn` behavior.

**Interfaces:** `calendar_effects(ctx) -> list[dict]`, addressing only clock `/day` and `/display_timestamp`. Compute the completing turn as `ctx.turn + 1`; calendar policies are anchored definitions, not wall-clock inputs.

- [ ] Use a Lost World fixture anchored to turn 33/day 4/timestamp `2026-10-09T07:30:00+07:00`, 24 turns/day. Add:

```python
def test_lost_world_hour_advance_is_in_same_commit(self):
    world = self.calendar_world('lost-world')
    report = run_event(world, self.event(world, {
        'type':'wait', 'actor_id':'player_kael'}), render=False)
    clock = read_snapshot(world)['clock']['data']
    self.assertEqual(34, clock['turn'])
    self.assertEqual(4, clock['day'])
    self.assertEqual('2026-10-09T08:30:00+07:00', clock['display_timestamp'])
    self.assertIn('clock', report['changes'])
```

- [ ] Run `uv run --no-project --with-requirements requirements.txt python -m unittest discover -s tests -p test_calendar.py -v`; expect unchanged timestamp before calendar effects.
- [ ] Implement Lost World offset-aware hourly progression. Define day from elapsed completed turns relative to the anchor, not midnight parsing: every 24 turns increments the gameplay day. Preserve the authored UTC offset.
- [ ] Implement Warhammer four watches/day, string formatter `<anchor_timestamp> · Day <day> · Watch <1..4>`; never run `datetime.fromisoformat` on a fictional timestamp. After one turn from anchor 37/day 9, expect `41.999.059.M41 · Day 9 · Watch 2`; after four turns expect day 10/watch 1.
- [ ] Test turn/day rollover, zero/invalid turns-per-day, anchor greater than current turn, dry-run/no-turn/failed-action clock stability, commit interruption recovery and exact replay. Loading policy must not change the current clock. All currently added actions cost exactly one turn; labor hours never bypass this rule.
- [ ] Compose calendar effects after resource/cold consequences, preserving once-only execution. Run focused tests green. Anchor live policies only during a separately authorized authoring step; do not apply clock effects to live saves in verification.

### Task 9: Committed-state presentation and end-to-end acceptance

**Files:** Modify `engine/render_map.py`, `inspect_world.py`, `README.md`, `plan/progress.md`; create `tests/test_remaining_mechanics.py`.

**Interfaces:** Continue `render_map(world_dir, snapshot=None)` and existing CLI commands. Display helpers consume captured envelopes and derived values only; no state writes or additional gameplay calls.

- [ ] Add a temporary-world scenario covering recipe production -> project start/material delivery/work/completion -> earned reward -> peaceful GM introduction/resolution -> calendar rollover. A separate combat-enabled fixture covers gear change -> group attack -> heal/restore. Use different event IDs and exact expected turns; do not fabricate a live gameplay history.
- [ ] Add a captured-render regression:

```python
def test_project_display_uses_committed_fulfillment(self):
    world = self.completed_project_world()
    render_map(world)
    html = (world / 'map.html').read_text()
    self.assertIn('120 / 120', html)
    self.assertIn('Completed', html)
    self.assertNotIn('<script>project</script>', html)
```

`completed_project_world` authors a project with the exact canonical fields and an HTML-bearing display name in a temporary baseline, or executes the Task 3 sequence; never inserts required project fields into live records.

- [ ] Run `uv run --no-project --with-requirements requirements.txt python -m unittest discover -s tests -p test_remaining_mechanics.py -v`; expect missing fulfillment presentation before extending the renderer.
- [ ] Render resource quantities/units, project hours/materials/completion, calendar display and structured last-event outcomes without re-reading legacy files. Read any resolved-event display data inside the same locked snapshot boundary, or capture it with the snapshot; no unlocked history read during rendering. Keep stale-render comparison, HTML escaping and independent retries.
- [ ] Update README action payloads, supported world policies, explicit restoration activation, audit behavior and `uv` commands. Keep archive/recovery/no-direct-writes instructions and gameplay sub-agent mandate. Update old initial-scope limitations only for actually implemented mechanics.
- [ ] Run the full relevant suite once using the verification command above; expect all original 67 regressions plus new tests passing. Run `git diff --check`; verify authoritative live `state/`, `events/committed/`, `transactions/` and immutable `archive/legacy-baseline/` hashes match the pre-batch capture. Code and authored definition/contract changes are reviewed separately, not mistaken for gameplay mutations. Record exact counts, commands, scope and any intentionally disabled policies in the execution ledger.
- [ ] Leave work in place without a commit/push or live gameplay execution. Ask for a separate live-policy/gameplay activation only if requested, not at every implementation step.

## Completion criteria and deliberate deferrals

All six mechanics areas have implemented, tested hooks and documented typed intent. Existing worlds remain loadable and their archives/baselines are unchanged by verification. Sanctuary opportunities are playable, while hostile combat and resurrection remain controlled by world policy. Every action's cost, clock effects and outcomes replay exactly once.

Do not build generic authoring UIs, arbitrary GM field patches/teleports, a general trait expression interpreter, untrusted-code execution, multiple storage backends, real-time schedulers, or automatic baseline rebase. Manual balance tuning and additional action templates are authoring work after these mechanisms exist, not excuses to broaden a task.

## Plan self-review

| Requirement area | Tasks |
| --- | --- |
| Resources, supply strain, production | 2 |
| Structural/action prerequisites, labor/material fulfillment | 3 |
| Equipment/trait order, possession, baseline audit | 4 |
| Companions, tactical combat, casualties | 5 |
| Healing and deliberate restoration | 6 |
| World-aware playable GM events | 7 |
| World-specific turn/day/display calendars | 8 |
| Recovery/replay, no partial writes, rendering, operations | 1–9 |

Cross-task interfaces share fixed IDs and signatures; configuration/schema references are updated in both `world.json` and `contract.json`. Resource health consequences cannot collide with Lost World cold because its resource policy never damages health. Warhammer shortages read the action overlay; they do not perform combat retaliation. Templates are fingerprinted so changed authoring cannot silently change an active project's requirements. Current baselines and historical archives remain immutable during verification.
