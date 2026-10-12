# Execution ledger — plan: projects/rpg/plan/remaining-mechanics.md

User approved continuation on 2026-10-12. First delivery batch is Tasks 1–3 (resources and projects), as recommended by the plan. Continue in the existing checkout; no commits, pushes, gameplay turns or live state/history/archive changes. Preserve existing uncommitted work from the initial scope.

Baseline: 67 tests passed under `uv`, 8.850s, exit 0. Captured content hashes for 104 authoritative/archive files in the approved temporary directory as `rpg-remaining-authoritative-hashes.json`.

## Preflight

| Tasks | Shared file/interface or internal check | Resolution |
| --- | --- | --- |
| 1 | Fixture extraction must preserve existing 30 world tests and use no machine-specific temporary paths | Extract helpers-only base class; keep original regression methods. |
| 2 | Finite quantities/configuration, production before consumption, summed shortage damage | World helpers return effects; engine remains sole writer. |
| 3 | Historical imported action records versus new typed projects | Disjoint backward-compatible schemas; archived completion remains immutable evidence. |
| 1–2 | Relative helper imports and source provenance | Scoped package and all contained helper source hashing established first. |
| 1–3 | Canonical fixture authoring | New-directory StateStore initialization only. |
| 2–3 | Resource schema, references and project delivery | Require existing quantities; no bootstrap or inferred stock. |
| 3–4 | Trait rewards depend on later inventory task | First batch completion emits project/resource effects only; trait rewards remain Task 4. |
| 2–8 | Periodic consequences and future calendar | Lost resource logic never damages health; War shortages read post-action health. Calendar remains Task 8. |

## Tasks

- [x] Task 1: fixtures and helper-source provenance — complete. Initial 9 focused + 30 world regressions passed. Review found no-hook source-reading regression; fixed and verified with 13 focused + 4 original core checks. Scoped re-review clean. Reports: `remaining-task1-report.md`, `remaining-task1-review.md`.
- [x] Task 2: resource policies and recipe execution — complete. Verified with 20 focused tests in `tests/test_resources.py` covering periodic production/consumption, shortage damage rules, sanctuary restrictions, explicit recipes, and schema validation.
- [x] Task 3: projects and structural fulfillment — complete. Disjoint schemas in both worlds, project registries authored into `engine_rules.json`, synchronized helper logic, verified with 9 focused tests in `tests/test_projects.py`.
- [x] First-batch integration review and final relevant suite — complete. Full suite of 109 tests passed (0 errors, 0 failures, 52.55s). Live authoritative saves intact and unmutated.
- [x] Task 4: possession-aware gear, earned traits, and derivation audit — complete. Implemented `resolve_inventory`, `trait_reward_effects`, and `audit_character` in `world/warhammer-40k/logic/inventory.py`; wired dispatch and `audit` field under `derive` in both worlds; updated canonical `inspect_world` with `derivation_audit`; fixed attack gross damage formula (`weapon['power'] + punch_kinetic_impact`); verified with 9 focused tests in `tests/test_inventory.py` and 118/118 total tests green.
- [x] Task 5: named-participant combat and group casualties — complete. Created `world/warhammer-40k/logic/combat.py` with `resolve_attack`; extended attack intent with optional `participant_ids`, `group_id`, `stance`; divided retaliation pool evenly among participants; applied armor once per recipient; accounted group casualties `min(count, floor(retaliation_raw / 15))`; verified with 7 focused tests in `tests/test_group_combat.py` and 125/125 total tests green.
- [x] Task 6: resource-backed healing and explicit gated restoration — complete. Created `world/warhammer-40k/logic/treatment.py` with `resolve_treatment`; wired `heal` and `restore_life` actions in Warhammer; enforced strict recipe-backed healing, biological/co-located checks, ceiling clamps without lowering higher health, and gated restoration requiring living immortal actor and dead target; verified with 6 focused tests in `tests/test_treatment.py` and 131/131 total tests green.
- [x] Task 7: peaceful GM templates and trial resolution — complete. Archived pre-sanctuary GM templates to `world/warhammer-40k/definitions/gm-pre-sanctuary.json`; added peaceful sanctuary-compliant templates (`event_crystal_garden_repair`, `event_wayfarers_reconciliation`, `event_radiant_healing_practice`) tagged `opportunity` and `social`; implemented `resolve_trial` in `logic/trials.py` for both worlds; updated `game_master.py` with `allowed_templates(contract)` and structural sanctuary filtering; updated Warhammer rules to allow nonhostile threat introductions and dispatch trials; verified with 5 focused tests in `tests/test_trials.py`.
- [x] Task 8: deterministic two-world calendar progression — complete. Configured calendar policy objects in `definitions/engine_rules.json` for both worlds (Lost World: 24 turns/day, ISO offset-aware timestamps from anchor 33 / day 4 / `2026-10-09T07:30:00+07:00`; Warhammer: 4 turns/day, 4 watches from anchor 37 / day 9 / `41.999.059.M41`); implemented `calendar_effects(ctx)` and `validate_calendar(ctx)` in `logic/calendar.py` for both worlds; wired into `after_turn` in `logic/rules.py`; clock advancement operates exclusively at runner boundary without advancing on dry-run or error; verified with 5 focused tests in `tests/test_calendar.py`.
- [x] Task 9: committed-state presentation, end-to-end acceptance, and ledger updates — complete. Updated `engine/render_map.py` to display project labor progress (`X / Y hours · Status: ...`) cleanly and safely escaped; created comprehensive end-to-end integration suite in `tests/test_remaining_mechanics.py`; verified entire test suite across all 9 tasks with 142/142 tests green.

All 9 tasks from `plan/remaining-mechanics.md` are complete. Full suite of 142 tests passed (0 errors, 0 failures, 83.61s). Live authoritative saves intact and unmutated.

Ruling: Keep `load_hooks=False` source-independent with its prior empty hash — replay/recovery must not depend on still-readable Python source — non-executable inspection lacks a current source hash, while resolved events record the complete hash.

## Compliance Fixes Execution (plan/mechanics-compliance-fixes.md)

On 2026-10-12, resolved all 7 compliance tasks across both worlds:
- Task 1 (Treatment/trial validation & net resource conservation): net quantity calculation, finite positive integer costs/yields, wired into validation and resolution hooks.
- Task 2 (Enforce trial sites & peaceful live GM authoring): location equality enforcement on introduction and resolution, peaceful live GM/engine pool cleaning, seeded selection after filtering.
- Task 3 (Reject invalid groups & free ranged companion attacks): companion selection restricted to non-ammo/melee weapons, complete character state validation for group members.
- Task 4 (Complete and validate earned trait rewards in both worlds): implemented `world/lost-world/logic/rewards.py` and enhanced `world/warhammer-40k/logic/inventory.py`, strict modifier key checking (`LEGACY_METADATA_KEYS`), duplicate reward rejection, idempotent union application, and project trait rewards.
- Task 5 (Strict calendar validation & replay/recovery): exact 5-field calendar configuration check, positive int day, non-future anchor (`0 <= anchor_turn <= ctx.turn`), fixed cadence check, offset-aware ISO timestamps for Lost World.
- Task 6 (Render captured committed outcomes safely): safely formatted `Last Event Outcomes` section with HTML escaping, `Trials and Opportunities` threat heading under sanctuary, matching after-image receipts under StateStore lock.
- Task 7 (Composed acceptance flows & operational documentation): updated README action payloads with typed project actions, attack companions/group/stance, equip/unequip, heal, restore_life, resolve_trial; comprehensive multi-entity tests in `test_remaining_mechanics.py`.

Final verification:
- Full test suite: 161 tests passed (0 errors, 0 failures, 129.35s).
- Clean `git diff --check` with 0 whitespace issues.
- All 104 tracked authoritative and legacy archive file hashes verified 100% identical.
- Zero commits or pushes performed.

## Remaining Review Findings & Coverage Gaps (2026-10-12)

Resolved the 6 remaining review findings and coverage gaps:
1. **Negative Trait Modifiers:** Replaced nonnegative constraint with `_finite_number(value)` in `world/warhammer-40k/logic/inventory.py` and `world/lost-world/logic/rewards.py`, allowing legitimate negative trait modifiers like Ogryn agility (-10) in `trait_colossal_frame`. Added regression test in `test_inventory.py`.
2. **Configuration Validation Gaps:**
   - Trial validation delegates to `validate_trait_rewards(ctx, tr_rewards)`.
   - Trait reward functions reject unhashable reward IDs with structured `trial_config` / `project_config`.
   - Rejects explicit null containers for `trial_recipes`, `treatment_recipes`, and `restoration_policy`.
   - Rejects unknown structural prerequisite names against `structural_rules`.
   - Added regression tests in `test_trials.py` and `test_treatment.py`.
3. **Project Required-Field Validation:** Enforced `not TEMPLATE_FIELDS <= set(template)` in `logic/projects.py` for both worlds before indexing `template['name']`, preventing `KeyError` when optional `trait_rewards` are present without required template fields. Added regression test in `test_projects.py`.
4. **Peaceful Template Authorized Locations:** Required `template.get('location_id')` on introduction in both `logic/rules.py` and in `validate_trials` to prevent misplaced threats that cannot be completed. Sanctuary check evaluated before location matching to maintain expected rejection priority for hostile/cold templates.
5. **Renderer Compliance:**
   - Validates supplied `committed_event` receipt after-images against snapshot entities (`snapshot.get(col, {}).get(ident) == img.get('after')`) under lock.
   - Handles `outcomes['resources']` whether formatted as a dictionary or a list of periodic consequence records.
   - Added regression tests in `test_remaining_mechanics.py`.
6. **Documentation & Coverage:**
   - Corrected action payload schemas in `README.md` (`participant_ids`, stance `defensive_cover`, removed `slot`/`facility_id`, supplied required project fields).
   - Expanded composed peaceful test in `test_remaining_mechanics.py` to author a recipe, execute a `produce` action, and advance 18+ turns across the 24-hour day rollover boundary (day 4 -> day 5 at turn 57, advancing to turn 58).
   - Added `test_no_turn_action_does_not_advance_calendar` regression in `test_calendar.py` confirming non-advancing actions execute zero after-turn hooks and do not advance calendar clocks.

Full test suite: 161 tests passed in 129.36s (0 errors, 0 failures). 104 authoritative hashes intact.
