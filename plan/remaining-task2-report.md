# Task 2 — stock policies and atomic production

Implemented only Task 2 of `remaining-mechanics.md` and the resource section of
`remaining-mechanics-spec.md`. No engine loader/persistence changes, dependencies,
commits, pushes, nested agents, gameplay turns, live save/archive/history writes,
proposal writes, or map writes were made by this task. Existing unrelated work
was left in place. Both live registries are deliberately empty: automatic rates
and penalties are not activated, and no recipe invents missing stock entities.

## Changed files

- Both `world/<id>/logic/resources.py`: fixed production, periodic stocks, and
  resource configuration validation.
- Both `logic/rules.py`: validation before any resolver proposal, `produce`
  dispatch, periodic composition, and final resource invariant validation.
- Both `schemas/resource.schema.json`, and resource references in both
  `world.json` and `contract.json`.
- Both `definitions/engine_rules.json`: empty `resource_policies` and
  `resource_recipes` registries.
- New `tests/test_resources.py` and this report.

## Interfaces and configuration types

All helpers accept the existing engine `RuleContext`; they read snapshots and
definitions, returning effects rather than writing state:

- `resolve_production(ctx, event) -> RuleResult`
- `periodic_resources(ctx) -> RuleResult`
- `validate_resources(ctx) -> list[dict]`, with `resource_config` violations.

Both registries are optional JSON objects and default to `{}`. Unknown fields
are rejected. Numbers exclude booleans, strings, NaN and infinities.

`resource_policies` is keyed by an existing resource ID:

| Field | Type / constraint |
| --- | --- |
| `capacity` | Required finite nonnegative number; current quantity cannot exceed it |
| `production_per_turn` | Optional finite nonnegative number, default 0 |
| `consumption_per_turn` | Optional finite nonnegative number, default 0 |
| `shortage_damage` | Optional finite nonnegative damage per unmet unit, default 0 |
| `location_id` | Optional existing authored location ID; required for positive damage |

Positive shortage damage is invalid in Lost World and in Warhammer when either
the rules sanctuary flag or structural sanctuary flag is enabled. Combat-enabled
Warhammer copies damage only living, mortal, numeric-health characters at the
policy's explicit location. All policies' penalties are summed before one
periodic health effect and one status effect per eligible character. Dead,
immortal, remote and null-health characters are unaffected.

`resource_recipes` is keyed by recipe ID. Each recipe requires exactly:

| Field | Type / constraint |
| --- | --- |
| `location_id` | Existing authored location ID |
| `inputs` | Nonempty object of existing resource IDs to finite positive numbers |
| `outputs` | Nonempty object of existing resource IDs to finite positive numbers |
| `health_cost` | Finite nonnegative fixed actor cost; 0 is allowed |

Outputs require explicit capacity from their resource policy, falling back to
the stock's optional `data.capacity`. Input sufficiency is checked against the
original snapshot; capacity is checked against final stock after combined input
and output deltas. Newly produced stock cannot fund inputs. Aliased input/output
IDs use a combined net delta, with exactly one
recipe quantity effect per changed resource, never silent map overwrite.

Intent is exactly `{"type":"produce","actor_id":"...","recipe_id":"..."}`:
all values are nonempty strings; caller quantities/effects are forbidden. A
living co-located actor is required. Mortal biological work whose cost would
reach zero health is rejected atomically; immortals and null-health entities do
not pay biological health costs. Successful production advances one engine turn.

Periodic stocks use `max(0, min(capacity, old + production) - consumption)` in
stable resource ID order. They emit one final quantity effect only when changed.
Outcomes use `resources` and `resource_shortages`; explicit recipe results use
`production`, preserving existing `cold` and combat outcome names. Warhammer
periodic effects read the resolver overlay and never repeat retaliation.

The local resource schemas require finite nonnegative `quantity`. All original
built-in resource fields remain accepted: `name`, `description`, `status`,
`location_id`, `metadata`, `amount`, `quantity`, `capacity`, and `unit`. Envelopes,
contracts and canonical saves remain `schema_version: 1`; no migration or archive
rewrite was introduced.

## Test-first evidence

Run from `projects/rpg/`:

```sh
uv run --no-project --with-requirements requirements.txt python -m unittest discover -s tests -p test_resources.py -v
```

- Initial RED: 13 tests, 8 failures and 9 errors (subtests count separately).
  The numeric regression failed as intended with `7 != 8`; production rejected
  as unsupported; negative/missing quantities and invalid configuration were not
  rejected. This run also exposed test setup issues: invalid JSON was rejected
  during event construction, two fixture IDs were nonexistent, and the helper
  did not yet exist. Those fixture issues were corrected without engine edits.
- First implementation run: 13 tests, 1 error. Recovery used a steady-state stock
  and therefore had no quantity change image. The fixture was corrected to
  consume 4 on that turn so recovery verifies a real resource change.
- Expanded integration run: 17 tests, 2 fixture errors from missing required
  threat metadata; authored threat envelopes were corrected.
- Final GREEN: **17 tests passed**, 10.830 seconds, exit 0. Focused suite only;
  the controller owns the once-per-batch final full suite and original 67-test
  regression confirmation.
- `git diff --check`: exit 0, no output.

Coverage includes 8 + 4 capped at 10, then consumption 3 -> 7; both worlds'
recipe debit/credit/cost behavior; insufficient stock atomicity; capacity and
alias checks; strict intent/config/schema rejection; lethal cost rejection and
immortal immunity; 5 + 7 shortages -> 12 with one periodic health effect per
actor; dead/null/immortal/remote exclusions; shortage mortality; sanctuary and
Lost World damage prohibition; Lost World cold outcome composition; Warhammer
killing-blow retaliation exactly once followed by shortage against post-action
health; helper-source hash changes; replay without helper execution; duplicates;
interrupted commit recovery matching the exact expected full snapshot; and
read-only loading/schema validation of both actual canonical worlds.

The actual-world read-only test compares content hashes before/after loading
(excluding bytecode/locks) and confirms the combined immutable migration archive
still contains **75 JSON files**. Temporary-world replay/recovery compares both
original live archives' hashes and the nonempty copied migration archive's hashes
before/after replay, duplicates and interrupted recovery. No tests execute events
on the actual worlds.

## Deliberate limits / integration notes

- No live policy activation, recipe bootstrap, scaling, generic rule language,
  authoring UI, resource creation or dependency additions.
- The two bounded ordinary Python helpers intentionally remain world-local;
  Lost World's shortage permission is a hard false, not caller authorization.
- Warhammer's existing canonical character schema excludes null health. Its
  synthetic shortage-immunity case uses the real periodic hook with a read-only
  context containing null health; no canonical schema was broadened.
- Engine source-independent replay remains unchanged. Full-suite/batch hash
  auditing must be completed by the controller, not inferred from focused tests.

## Review blocker correction — net-capacity aliases

Addressed `remaining-task2-review.md` with a minimal test-first correction in both
resource helpers. Original input sufficiency is still checked before outputs;
then input/output deltas are combined and every final quantity is checked for
finiteness, nonnegativity, and applicable capacity before any effects are returned.
The earlier report's gross-output-space restriction was incorrect and is corrected
above. No other mechanics, live policies, live files, or engine code were changed.

Replaced the incorrect alias-capacity rejection expectation and added regressions
for both worlds:

- Stock/capacity 2, input 1/output 1 succeeds with stock 2 and no quantity effect.
- Stock 9/capacity 10, input 5/output 6 succeeds with stock 10 and one effect.
- Stock 9/capacity 10, input 5/output 7 rejects true final overflow atomically.
- Empty stock, input 1/output 2 rejects with `insufficient_resources`, even though
  its mathematical net result would fit capacity; no bootstrapping is permitted.

RED and GREEN used the same focused command from `projects/rpg/`:

```sh
uv run --no-project --with-requirements requirements.txt python -m unittest discover -s tests -p test_resources.py -v
```

- RED before helper edits: 20 tests, 4 expected `resource_capacity` errors across
  the two valid alias cases in both worlds, 14.794 seconds, exit 1.
- GREEN after the minimal helper edits: **20 tests passed**, 14.747 seconds, exit 0.
- `git diff --check`: exit 0, no output.

Focused suite only; no full-suite run, commits, nested agents, or live writes.
Existing read-only canonical/archive and temporary replay/recovery checks remain
green. The controller retains ownership of the final batch full-suite check.
