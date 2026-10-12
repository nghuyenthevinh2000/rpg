# Remaining world mechanics — proposed design

Status: proposed on 2026-10-12; planning only. No additional mechanics or gameplay events are authorized by this document alone.

## Goal and baseline

Finish the six remaining world-mechanics areas without replacing the working engine. The initial implementation has 67 passing tests. Lost World is migrated at turn 33/day 4; Warhammer is migrated at turn 37/day 9. Their original JSON files remain in `world/<id>/archive/legacy-baseline/`.

The current public interfaces are `RuleContext`, `RuleResult`, `WorldContract`, `run_event`, `replay_event`, and `StateStore`. World state uses envelopes; characters have mutable `health`, baseline-relative `stats`, ID lists for equipment/traits/inventory, and `capabilities.cannot_die`. Events contain intent, not effects. There is no need for another persistence backend, plugin framework, expression language, or rule sandbox.

## Binding constraints

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

## Delivery boundaries

Each stage is a working deliverable and can stop after its focused tests and relevant suite pass:

1. Resource policies and recipe execution.
2. Construction/project fulfillment.
3. Inventory, equipment, and earned traits.
4. Group combat, healing, and explicit restoration.
5. Sanctuary-aware GM proposals and trial resolution.
6. Calendar progression and final operational guidance.

Do not enable automatic penalties, production, or resurrection merely because code exists. Live policy defaults remain conservative; test fixtures explicitly enable new rates and hazards. Resource/project work is the first execution batch; later stages can be executed separately.

## 1. Resources

Policies live in a new optional `resource_policies` object in each world's `definitions/engine_rules.json`, keyed by resource ID. A policy contains `capacity`, `production_per_turn`, `consumption_per_turn`, optional `location_id`, and `shortage_damage`. Values are finite nonnegative numbers; absent rates mean zero. Referenced resources must already exist for periodic processing; a missing policy target is a rule/configuration error, never an invented stockpile.

Periodic order per resource: produce up to capacity, consume at most available quantity, calculate unmet consumption, then emit one final quantity effect. Newly introduced policies do not infer rates from archived prose or `days_reserve`. Stable ID ordering makes outcomes deterministic. Existing Warhammer stocks default to zero rates and no shortage damage; Lost World has no automatic starvation damage. In a combat-enabled Warhammer fixture, a shortage policy can damage living biological characters at its configured location once. Sum all eligible shortages per character before emitting a single health/status update; do not let successive set effects overwrite earlier damage. Sanctuary rejects a nonzero shortage-damage policy rather than applying it.

Explicit production uses `{"type":"produce","actor_id":"...","recipe_id":"..."}`. A recipe in `resource_recipes` defines its location, input resource quantities, output resource quantities, and fixed actor health cost. Inputs must exist and be sufficient; outputs must exist and fit capacity. Recipes consume inputs and produce outputs atomically, cannot be scaled by caller-supplied effects or quantities, and consume one turn. No free resource bootstrap or invented starting stock is part of this stage.

Both worlds adopt a local `schemas/resource.schema.json` requiring finite nonnegative `quantity`, while retaining the other existing `engine:resource` fields as optional shape-compatible fields. Built-in engine schemas and persistence remain lore-neutral.

## 2. Construction and projects

Author a small, typed `project_templates` registry in each world's rules definitions. It translates selected existing `action_conditions.json` entries into executable numeric requirements; it is not a generic interpreter of narrative text.

Actions:

- `start_project`: `actor_id`, `template_id`, `project_id`, `participant_ids`.
- `deliver_materials`: `actor_id`, `project_id`, `resource_id`, `quantity`.
- `work_project`: `actor_id`, `project_id`.
- `prepare_project_site`: `actor_id`, `project_id`, `recipe_id`.
- `complete_project`: `actor_id`, `project_id`.

All consume one turn. Participants must be unique, living, co-located character IDs; the actor must be included and authorized as the project's actor. Starting creates a project at the actor's location and charges configured irreversible starting costs once. Delivering transfers a finite positive quantity from an existing stockpile into the project's ID-keyed committed-material map; it cannot exceed the requirement. Working contributes exactly one labor hour per eligible participant per turn, capped at hours remaining, and applies configured fatigue without reviving or silently killing a participant before they can be validated. Reject work whose configured cost would reduce a mortal worker to zero; no labor is obtained from dead actors.

Completion requires hours, all material amounts, and every named structural condition; it produces configured outcomes once and marks the record completed. Runtime `conditions` is a strict named boolean map, initialized false and established by approved site-preparation recipes, not assertions supplied in a completion event. A site recipe has fixed resource costs and fixed condition names/values; it cannot set arbitrary fields. Initial Lost World preparations are `sever_telemetry` and `reject_drones`, each taking one turn, no stock cost, and only permitted at author-defined manual-work sites. Project rules also verify current `project_sites` definitions and world structural restrictions; flags cannot authorize a site prohibited by definitions. First Lost World template: `action_build_structure`, 120 labor hours, 40 cedar logs, 25 granite slabs, 50,000 dividend credits, and telemetry/drone-severance conditions. First Warhammer template: peaceful `action_resonant_pylon_repair`, 12 labor hours and 2 existing `resonant_crystal_pylons`; no bloody tithe or newly hostile lore.

Project schema uses disjoint branches: existing imported `engine:action`-compatible records remain read-only historical records; new records require `kind: project`, `template_id`, `actor_id`, `participant_ids`, `status`, `completed`, `hours_committed`, `materials_committed`, and `conditions`. Requirements come from immutable definitions, not editable request payloads. Active templates cannot change underneath a project: record a template SHA-256 at creation and reject project actions if its definition changes. Preserve historical completion at the same template/location as evidence preventing accidental duplicate construction; rebuilding requires a different explicit template.

## 3. Equipment and traits

Keep existing list-based storage, avoiding an unrelated save-format rewrite. `equip` and `unequip` take `actor_id` and `item_id`, consume one turn, and move the recognized ID between that character's inventory and equipment. Equipping requires possession, a valid registry entry and slot, and no occupied slot; require explicit unequip first. Existing worn gear already implies possession and need not be added to inventory by a migration. Historical narrative attire is not mechanical gear.

Trait changes are earned from world-defined trial/project rewards, not an unrestricted `grant_trait` event. Rewards have recognized IDs and apply once. Recalculation uses stored baseline offsets, adding/removing current configured modifiers without editing frozen baseline totals. Reject unsupported trait modifier keys. Make equipment multipliers contribute once to attack damage: the current Warhammer resolver multiplies a kinetic value that already contains equipment multipliers by the weapon multiplier again; preserve a regression for the corrected explicitly documented calculation.

Do not automatically rebase imported static values. Provide a read-only audit showing baseline/static/current modifiers/effective values/bounds exceptions, leaving any manual rebase to a separate reviewed authoring operation. Lost World equipment support only activates when a typed equipment registry is explicitly authored; no fake conversion of prose clothing.

## 4. Group combat, healing, and restoration

Extend attack intent with optional `participant_ids`, `group_id`, and `stance`; existing single-actor attack payloads stay valid. Default stance is neutral. `defensive_cover` multiplies outgoing and incoming damage by 0.8 and 0.65; `aggressive_assault` uses 1.15 and 1.25. Participants are unique living co-located characters including the actor; selected weapon must belong to the actor. Companions use configured equipped melee/default weapon mechanics, not caller-provided stats. Divide the hostile pool evenly among participants, then apply each character's configured armor once. One final retaliation occurs on every attack, including a killing blow; periodic rules never repeat it.

A selected group must have explicit nonnegative `count`, co-located deployment, valid member references, and positive available count; no count is inferred from narrative garrison prose. Group casualty policy is configured per combat-enabled world and yields `min(count, floor(retaliation_raw / 15))`; decrement once alongside ammo and named-character effects. No automatic casualty conversion of current sanctuary specialists.

`heal` takes `actor_id`, `target_id`, and `recipe_id`; recognized co-located living biological targets only. Definition gives resource/cost/amount/health ceiling. Reject dead targets, null-health synthetic entities, full-health no-op treatments, and missing stock; health and stock change atomically. Healing consumes one turn and never treats an immortality sentinel as a number.

`restore_life` is a separate Warhammer-only action with `actor_id` and `target_id`. Proposed restoration recipe: same location, living immortal actor, dead target, cost one existing `primordial_life_restoration`, restore health to 100/status alive; retain target's existing capability and do not grant immortality. The policy is disabled by default until separately activated as world authoring. Lost World rejects restoration. Implementation and tests must not resurrect existing dead live companions.

## 5. GM and trials

Archive the old hostile Warhammer GM authoring file separately from the immutable migration archive before replacing the active GM pool. New templates are `event_crystal_garden_repair`, `event_wayfarers_reconciliation`, and `event_radiant_healing_practice`, tagged `opportunity` or `social`, never hostile, with zero health/armor/retaliation. Match them with explicit configured completion recipes and locations. Keep hostile templates available only in authored combat-enabled fixtures.

Retain the canonical `introduce_threat` operation for trial/opportunity entities to avoid renaming existing events. Sanctuary rejects templates tagged `hostile` or `cold`, not all introductions. Neutral/peaceful templates are validated and allowed; no caller can supply custom tags or reward effects. Threats with `active: true`, zero health and nonhostile tags are trials, not attackable combatants. GM proposals select only templates allowed by current structural rules, retain seeded selection, and never write state.

`resolve_trial` takes `actor_id`, `trial_id`, and `recipe_id`. Validate location, activation, allowed completion recipe, resources, and prerequisites; apply predetermined resource/trait outcomes, then mark the trial inactive. Reject repeated completion. New trials remain inactive mechanically until the following action, preserving current activation timing. Do not re-run catastrophe logic after proposing or rendering.

## 6. Calendar

Calendar policy lives under `calendar` in each world's rules definitions: `anchor_turn`, `anchor_day`, `anchor_timestamp`, `turns_per_day`, and `display_style`. Lost World uses 24 turns/day and one hour per turn, anchored to the current committed timestamp; use offset-aware Python `datetime` only because this world's authored timestamp is ISO. Warhammer uses four watches/day and a fictional timestamp formatted as `<anchor_timestamp> · Day <day> · Watch <1..4>`; never parse it as an ISO date.

Compute time from completed-turn distance to the anchor, not machine time. Each current supported action, including new project/GM/gear/treatment actions, consumes exactly one turn; labor hours are effort, not arbitrary elapsed-time increments. `after_turn` emits clock `/day` and `/display_timestamp` effects against the soon-to-complete turn `ctx.turn + 1`. Engine alone increments `/turn`. Clock advancement participates in the same transaction and replay; dry runs and failed actions advance nothing. A calendar policy activates without changing the current clock merely by loading the policy. Audit anchor equality before authoring live policy; a changed live turn requires a freshly reviewed anchor.

## Acceptance

- Both existing worlds load without rewriting their baselines.
- Every added action has a strict shape, explicit mechanical authorization, atomic rejection and exactly-once behavior.
- Resource/project costs and combat/treatment outcomes conserve quantities and do not duplicate on retry/recovery/replay.
- New rules compose with existing cold, mortality, immortality and sanctuary behavior.
- GM can propose and complete a genuinely playable peaceful sanctuary opportunity.
- Day/timestamp progression is deterministic, world-specific and replayable.
- Renderer exposes project fulfillment and treatment/combat/resource outcomes from committed state, escapes prose, and remains independently retryable.
- Existing 67 tests plus new subsystem and end-to-end regressions pass using `uv`; live-save content hashes remain unchanged during tests.
