# Engine Package and Unified CLI Implementation Plan

> **For agentic workers:** Use `executing-plans` or `subagent-driven-development` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. Follow repository budget-first rules; no automatic commits or repeated approval gates.

**Goal:** Consolidate shared RPG Python code under `engine/`, expose `python -m engine`, and remove redundant root scripts without changing gameplay or saves.

**Architecture:** Move existing support modules into the existing engine package using relative imports. Add one small `__main__.py` entry point and an `argparse` subcommand dispatcher that calls the existing runner, migration, GM, renderer, and inspection APIs. World-specific hooks stay in `world/<id>/logic/`; tests stay in `tests/`.

**Tech Stack:** Python 3.10+, standard-library `argparse`/`unittest`, existing `jsonschema`, and `uv`; no new dependencies or packaging framework.

**Spec:** The design contract below defines this refactor. Preserve mechanics/persistence constraints in `remaining-mechanics-spec.md`; this plan supersedes older documents only where they require root-level command filenames.

## Global Constraints

- Use `uv` for Python package management.
- Only StateStore writes authoritative canonical state; world functions return effects.
- Preserve `resolve -> overlay -> after_turn once -> validation -> journaled commit -> render`.
- Replay applies archived effects without rules or RNG.
- Keep `schema_version: 1`, baseline-relative derivation, mortality, immortality, sanctuary, and activation timing unchanged.
- Do not advance or rewrite live saves during implementation verification.
- Tests execute events, migration, GM generation, and rendering only in temporary copies.
- Keep immutable legacy archives and historical resolved receipts unchanged, including old command strings in archived content.
- Work in place; preserve existing uncommitted work. Do not commit, push, reset, or discard unrelated changes unless requested.
- Do not combine this refactor with outstanding mechanics corrections or balance changes.

## Design contract

### Package layout

```text
engine/
  __init__.py
  __main__.py       # calls cli.main(); no other behavior
  cli.py            # subcommands, JSON output, error/exit boundaries
  world_utils.py    # selection, canonical checks, disabled legacy writer
  migration.py      # existing inspection and staged migration implementation
  game_master.py    # existing seeded proposal generation only
  contracts.py
  runner.py
  state_store.py
  render_map.py
tests/
world/<id>/logic/
```

Retain public function names and signatures in moved modules: `resolve_world_dir`, `require_canonical`, `load_progress`, `save_progress`, `inspect_world`, `migrate_world`, `allowed_templates`, and `propose_event`. Imports become `engine.<module>` for external consumers and relative imports for package-internal code. Do not re-export everything through `engine/__init__.py` or add compatibility modules indefinitely.

`RPG_DIR` becomes `Path(__file__).resolve().parents[1]` in `engine/world_utils.py`. World lookup is anchored to the repository RPG directory, not the invocation directory. Explicit relative `--world` paths continue to resolve relative to the caller's working directory; known names continue to resolve under `RPG_DIR / 'world'`.

### CLI grammar

Commands are invoked from `projects/rpg/`, where Python can discover `engine`. Do not promise invocation from arbitrary directories without installing the package or explicitly setting `PYTHONPATH`; no installation work is needed for this refactor.

| Command | Arguments | Existing implementation |
| --- | --- | --- |
| `python -m engine run EVENT` | `--world`, `--dry-run`, `--seed INT` default 0, `--no-render`, `--replay` | `run_event` or `replay_event` |
| `python -m engine inspect` | required `--world` | `inspect_world` |
| `python -m engine migrate` | required `--world`, `--dry-run`, `--resume`, deprecated `--accept-baseline` | `migrate_world` |
| `python -m engine render` | `--world` | `render_map` |
| `python -m engine gm` | `--world`, `--seed INT` default 0, `--improvise` | `propose_event` |
| `python -m engine stats` | `--world`, `--seed INT` default 0 | existing read-only derive/validation report |
| `python -m engine timing` | `--world` | existing read-only clock/timing report |

Only `run` accepts an event path. Retain event-path world inference for `event/`, `events/proposed/`, and `events/committed/`, strict legacy-event rejection, and exact replay semantics. Replay plus dry-run remains an explicit error. GM flags no longer belong to `run`: use the distinct `gm` command instead of `--force-gm` or an implicit proposal branch. State this intentional command-line compatibility break in documentation; do not silently reinterpret old invocations.

Keep existing default-world selection where `--world` is optional. Inspection/migration may operate on legacy worlds; gameplay/stats/timing/render/GM require canonical worlds. GM still only writes proposals. Stats and timing never write state. Rendering retries without rerunning a turn.

Successful commands print JSON to stdout. Structured `RuleError` prints `{"error": ...}` to stderr and exits 2; filesystem interruptions exit 3 with existing recovery guidance. Inspection reports with `blocking: true` exit 2 while still printing their inspection JSON. `argparse` handles help/usage errors normally. Importing `engine`, `engine.cli`, or moved modules must not select a world, invoke rules, or write files.

### Compatibility and removal

This is a coordinated repository-local command/import update, not a public API compatibility layer. Update all active consumers before removing root scripts. Existing world contract hook paths and source hashing must not change; move no world logic and rewrite no stored effects or fingerprints.

Historical plans/reports may retain old filenames as historical evidence. Update active README/AGENTS/world documentation and add a supersession link to older architecture guidance where necessary; do not mass-edit every old mention or immutable archived content.

## Verification strategy

Use the helpers in `tests/world_fixtures.py` for temporary worlds. Capture fresh content hashes for both worlds' `state/`, `events/committed/`, `transactions/`, and `archive/legacy-baseline/` before executing tests; compare afterward. Capture initial Git status to distinguish user work from refactor changes.

Focused test command:

```sh
uv run --no-project --with-requirements requirements.txt python -m unittest discover -s tests -p test_cli.py -v
```

Final full suite, with a harness timeout of at least 300 seconds:

```sh
uv run --no-project --with-requirements requirements.txt python -m unittest discover -s tests -v
```

The last independently reviewed baseline was 161 passing tests, not a promised future count. Record fresh counts. Run focused regressions during work, then one final full suite; do not repeatedly rerun full suites after routine edits.

### Task 1: Relocate supporting modules and repair imports/root discovery

**Files:** Move `world_utils.py` -> `engine/world_utils.py`, `world_migration.py` -> `engine/migration.py`, `game_master.py` -> `engine/game_master.py`; modify `engine/render_map.py`, temporary remaining root entry-point imports, `tests/world_fixtures.py`, `tests/test_worlds.py`, `tests/test_inventory.py`, `tests/test_trials.py`; create `tests/test_cli.py`.

**Interfaces:** Preserve every moved public function's signature. `engine.world_utils.RPG_DIR` points to `projects/rpg`, not `projects/rpg/engine`. Keep lazy imports where they avoid cycles, especially `load_progress -> runner` and future `cli -> game_master`.

- [ ] Capture current status and authoritative hashes. Add failing import/root-location tests:

```python
def test_package_world_root_is_rpg_root(self):
    from engine.world_utils import RPG_DIR, resolve_world_dir
    self.assertEqual(ROOT, RPG_DIR)
    self.assertEqual((ROOT / 'world/lost-world').resolve(),
                     resolve_world_dir('lost-world'))
```

`ROOT` comes from `world_fixtures`; this lookup test performs no gameplay.

- [ ] Run the focused CLI suite red; expect the new package import to be missing.
- [ ] Move the three modules, retaining contents except package imports, root anchoring, and removed script entry-point code. Examples:

```python
# engine/world_utils.py
from .contracts import RuleError, load_json
RPG_DIR = Path(__file__).resolve().parents[1]

# engine/migration.py
from .contracts import RuleContext, RuleError, StateView, WorldContract
from .state_store import StateStore
from .world_utils import load_progress
```

Retain the migration module's other imported contract helpers. `engine/game_master.py` does not import the CLI or run it at the bottom; `engine/render_map.py` imports `.world_utils`.

- [ ] Update all imports and patch targets, including `patch.object(engine.migration, '_cutover'/'_atomic')` patterns. Preserve the module object used by fault injection; do not create duplicate implementations. Temporarily retained wrappers import the moved modules until Task 3 deletes them.
- [ ] Add subprocess coverage for importing the package modules from an unrelated temporary cwd with `PYTHONPATH` explicitly set to `ROOT`; assert known-name lookup still reaches the RPG world folder. Verify explicit temporary paths and event-path inference retain their existing behavior.
- [ ] Run focused CLI tests and affected world/migration inspection regressions green. Do not run live migration, rendering, or GM generation as a smoke check.

### Task 2: Add one explicit module CLI

**Files:** Move/refactor `world_cli.py` -> `engine/cli.py`; create `engine/__main__.py`; modify `tests/test_cli.py`; temporarily update `change_world.py`, `apply_event.py`, `resolve-threat.py`, `enforce_char_stats.py`, `enforce_progress_effects.py`, and root `render_map.py` before their Task 3 removal.

**Interfaces:** `engine.cli.main(argv=None) -> int`; existing API dispatch functions remain unchanged. `engine.__main__` calls `main()` only when executed as a module.

- [ ] Add failing subprocess tests for `python -m engine --help`, each subcommand's help, `inspect --world <temporary-world>`, and legacy-world refusal by canonical commands. Use subprocess arguments, not shell strings:

```python
def invoke(self, *args):
    return subprocess.run([sys.executable, '-m', 'engine', *args],
                          cwd=ROOT, capture_output=True, text=True)

def test_inspect_emits_json_without_mutation(self):
    world = self.make_world('lost-world')
    before = hashes(world)
    result = self.invoke('inspect', '--world', str(world))
    self.assertEqual(0, result.returncode, result.stderr)
    self.assertIsInstance(json.loads(result.stdout), dict)
    self.assertEqual(before, hashes(world))
```

Use `TemporaryWorldCase` as the test base and import `hashes`/`ROOT` from `world_fixtures`.

- [ ] Run the focused CLI suite red; expect missing `engine.__main__` or subcommands.
- [ ] Implement the small entry point:

```python
from .cli import main

if __name__ == '__main__':
    raise SystemExit(main())
```

- [ ] Use `parser.add_subparsers(dest='command', required=True)` and define each command's exact grammar from the table. Reuse current dispatch/output code rather than a command-registration framework. Parse arguments before loading any world so all help paths are world-independent. Preserve structured error codes and interruption guidance; adjust their command names to the new CLI.
- [ ] Redirect the six temporarily remaining CLI wrappers directly to the package dispatcher, prepending `run`, `stats`, `timing`, or `render` as mapped in Task 3. This keeps the intermediate checkout functional without retaining a root `world_cli` shim:

```python
import sys
from engine.cli import main

if __name__ == '__main__':
    raise SystemExit(main(['run', *sys.argv[1:]]))
```

The stats/timing/render wrappers substitute their mapped command for `run`; all are deleted in Task 3. The inspection/migration wrappers already use the moved APIs from Task 1 and are also deleted in Task 3.
- [ ] Add temporary subprocess checks: run dry-run leaves hashes unchanged; one commit advances once; duplicate rejects; replay succeeds only into an exact fresh baseline; `stats`/`timing` are read-only; GM writes only one proposal; `render` changes only its projection/allowed lock artifacts; migration dry-run is read-only; staged migration/resume retains existing refusal/recovery behavior. Use an absolute temporary event path for inference coverage.
- [ ] Add usage/error tests: missing command/event/world where required, unknown commands/flags, event passed to GM/inspection, `run --improvise`/`--force-gm` rejected, and `run --replay --dry-run` rejected. Verify `inspect` blocking exit code and `RuleError`/`OSError` behavior with focused mocks or invalid temporary fixtures; never inject faults into live worlds.
- [ ] Run CLI focused tests green. Keep inspection and migration usable before canonical cutover; do not put `require_canonical` above their branches.

### Task 3: Remove root wrappers and update every active consumer

**Files:** Delete root `change_world.py`, `apply_event.py`, `resolve-threat.py`, `enforce_char_stats.py`, `enforce_progress_effects.py`, `render_map.py`, `inspect_world.py`, `migrate_world.py` after inspecting their current diffs; root support modules have already moved. Modify `tests/test_worlds.py`, `README.md`, `AGENTS.md`, `world/lost-world/README.md`, `world/warhammer-40k/README.md` if it contains old active guidance, and actionable runtime error strings. Add a link in `plan/README.md` to this superseding package/CLI plan.

**Interfaces:** All executable repository commands use `python -m engine <subcommand>`; all Python imports use `engine.*`. No top-level Python files remain in the RPG directory, apart from any newly discovered user file that must be investigated rather than automatically deleted.

- [ ] Add a package-layout regression asserting the enumerated old paths no longer exist and package modules import without side effects. Run the focused suite red while wrappers remain.
- [ ] Replace subprocess tests that iterate old scripts with actual module invocations. Map convenience names:

| Previous entry | Replacement |
| --- | --- |
| `change_world.py`, `apply_event.py`, `resolve-threat.py` | `python -m engine run EVENT` |
| `enforce_char_stats.py` | `python -m engine stats` |
| `enforce_progress_effects.py` | `python -m engine timing` |
| `render_map.py` | `python -m engine render` |
| `inspect_world.py` | `python -m engine inspect` |
| `migrate_world.py` | `python -m engine migrate` |
| `game_master.py`, implicit `--force-gm` branch | `python -m engine gm` |

- [ ] Update `require_canonical`, disabled legacy-writer guidance, and stale-render/recovery messages to direct users to commands that actually exist. Preserve old strings inside archived events; replay must retain their exact metadata.
- [ ] Update active docs to show the invocation directory and `uv`-based examples, including migration resume, dry-run then one commit, independent render, stats/timing inspection, proposal-only GM, and exact-baseline replay. Remove stale Lost World instructions promising mutating enforcement or GM flags combined with gameplay. Do not change world lore, definitions, hook references, or saves.
- [ ] Delete only the enumerated redundant wrappers after confirming no unique user changes would be lost. No permanent shims or duplicate CLIs. Document retired command/import names and replacements in the main README.
- [ ] Search Python imports and active shell/docs/config references for old filenames. Distinguish world `game_master.json` authoring from the removed Python script; never rename the JSON files merely because their names match. Historical plans/reports may retain old names with a supersession note.
- [ ] Run focused CLI/world tests green; verify instructions in `AGENTS.md` still require gameplay agents and dry-run/commit once, now through `python -m engine run`.

### Task 4: Final package isolation and non-mutation acceptance

**Files:** `tests/test_cli.py`, `plan/remaining-progress.md` (append a separate refactor section), any remaining affected test imports/documentation only.

**Interfaces:** Existing engine APIs and world hook paths remain callable; no code in `engine/` imports a removed root module. Nothing in this task adds another persistence mechanism or compatibility command.

- [ ] Verify the dependency closure by searching Python imports for `world_cli`, `world_migration`, root `game_master`, and root `world_utils`. Keep tests' existing root-path bootstrapping only for discovering `engine`, not making removed modules importable.
- [ ] Add an import-side-effect subprocess test that imports `engine.cli`, `engine.migration`, `engine.game_master`, and `engine.world_utils` from an empty temporary cwd with `PYTHONPATH=ROOT`; it must succeed without reading gameplay state or producing output/proposals. Patch world-loading functions to raise if called during the imports, or compare content hashes and captured stdout/stderr where the existing subprocess setup permits.
- [ ] Test API replay with deleted/unusable world Python source using the existing no-hook regression; importing the unified CLI must not force replay to execute rules. Check world rule source hashes and schema references remain identical for a fixed authored world before/after relocation.
- [ ] Run the final full suite once using the command above and a 300-second-or-longer timeout. Run `git diff --check`; compare authoritative/history/archive hashes against the fresh pre-refactor capture. Do not render live maps or generate live proposals during verification.
- [ ] Append actual command/test counts, hash results, retired commands, and any intentional CLI compatibility breaks to the execution ledger. Record outstanding mechanics review findings separately; passing relocation tests does not claim to fix them.
- [ ] Review the final diff for user-work preservation and scope. Report completion with evidence; leave changes in place without committing/pushing or applying a live gameplay event.

## Acceptance checklist

- [ ] Shared support Python modules reside under `engine/`; redundant root entry points are removed.
- [ ] All seven explicit subcommands work, including help without a world.
- [ ] World-name/path/event inference survives relocation and does not depend on cwd for known world names.
- [ ] Inspection/migration legacy paths, interrupted migration resume, exact replay, canonical refusal, and JSON/exit boundaries retain their behavior.
- [ ] Stats/timing remain read-only; GM remains proposal-only; rendering is independently retryable; successful gameplay commits once.
- [ ] World definitions/hooks/saves/schema versions are unchanged by package relocation.
- [ ] Active docs/tests/runtime guidance refer to existing module commands; historical archives remain byte-identical.
- [ ] Focused and full-suite tests pass; live authoritative/history/archive hashes are unchanged; no commits or pushes made.
