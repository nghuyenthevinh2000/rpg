# Task 2 resource review

**Verdict: changes requested — one correctness blocker.**

Read-only source review against `remaining-mechanics.md` Task 2 and
`remaining-mechanics-spec.md` §1. No tests were rerun; the reported 17 focused
passes are implementation evidence, not independently reverified here. No
implementation, live state, archive, event, transaction, or map was edited.

## Blocker: aliased recipe capacity is checked against gross output, not final stock

- Both `world/lost-world/logic/resources.py:115-119` and
  `world/warhammer-40k/logic/resources.py:115-119` reject when
  `original_quantity + output > capacity`, before applying the same resource's
  input debit. This rejects valid atomic recipes whose final quantity fits.
- Concrete case: quantity/capacity 2, input 1, output 1 for the same ID. Original
  input sufficiency holds and final stock is 2, but the resolver checks 3 and
  rejects. Likewise quantity 9/capacity 10, input 5/output 6 should finish at 10,
  but is rejected as 15. This is not allowing outputs to fund insufficient
  inputs: sufficiency must still be checked against the original snapshot.
- The specification requires atomic consumption/production and outputs fitting
  capacity; it does not impose a temporary gross-output storage requirement.
  `tests/test_resources.py:99-111` explicitly expects rejection of the first
  valid case, and `remaining-task2-report.md:60-65` documents this extra restriction,
  so the green tests currently cement rather than detect the problem.
- Required correction: check original input sufficiency, aggregate input/output
  deltas by ID, then validate each final quantity for finiteness, nonnegativity,
  and applicable capacity before returning effects. Preserve one effect per
  changed stock and rejection when original inputs are insufficient. Adjust the
  alias regression to accept valid net-capacity cases and reject actual final
  overflow. No implementation changes were made by this review.

## Other reviewed invariants

No additional load-bearing defects found in the inspected paths:

- Finite/nonnegative stock and policy checks reject invalid baselines rather
  than clipping them; recipe amounts are positive and references must exist.
- Periodic order is capped production before consumption, stable by resource ID.
- Warhammer aggregates shortages per eligible character and reads the action
  overlay through the runner; it neither repeats retaliation nor damages dead,
  immortal, remote, or null-health targets.
- Both sanctuary flags prohibit nonzero shortage damage; Lost World's helper
  hard-disables starvation damage and retains named cold outcomes.
- Local resource schemas preserve the original optional field shapes, both
  contract/world resource references agree, and schema version remains 1.
  Live resource registries are empty, so loading does not activate new rates.
- Focused tests cover canonical loading, archive preservation, duplicate
  rejection, replay without helper execution, and interrupted-commit recovery.
  Their reported pass status was not rerun or expanded into a full-suite claim.
