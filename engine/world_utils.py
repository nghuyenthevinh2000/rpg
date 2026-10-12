"""World selection and read-only compatibility helpers."""
from pathlib import Path
from .contracts import RuleError, load_json

RPG_DIR = Path(__file__).resolve().parents[1]


def resolve_world_dir(world_arg=None, event_path=None):
    if world_arg:
        # Check if world_arg matches a known world name in the repository first
        repo_world = RPG_DIR / 'world' / world_arg
        if repo_world.is_dir() and (repo_world / 'world.json').is_file() and not Path(world_arg).is_absolute() and not any(sep in world_arg for sep in ('/', '\\', '.')):
            candidate = repo_world
        else:
            candidate = Path(world_arg).expanduser()
            if not candidate.is_dir():
                candidate = repo_world
    elif event_path:
        event = Path(event_path).resolve()
        if event.parent.name == 'event':
            candidate = event.parent.parent
        elif event.parent.name in ('proposed', 'committed') and event.parent.parent.name == 'events':
            candidate = event.parent.parent.parent
        else:
            raise RuleError('unknown_world', 'Use --world or an event/ or events/proposed/ path')
    else:
        candidate = RPG_DIR / 'world/lost-world'
    if not candidate.is_dir() or not (candidate / 'world.json').is_file():
        raise RuleError('unknown_world', f'Unknown world: {candidate}')
    return candidate.resolve()


def require_canonical(world_dir):
    config = load_json(Path(world_dir) / 'world.json')
    journal = Path(world_dir) / '.migration.json'
    if journal.exists() and load_json(journal).get('phase') != 'complete':
        raise RuleError('migration_incomplete', 'Migration is pending; inspect .migration.json and use python -m engine migrate --resume only for ready staging')
    if config.get('contract_version') != 1:
        raise RuleError('legacy_world', 'Gameplay is disabled: run python -m engine inspect then python -m engine migrate --world WORLD')
    return config



def load_progress(world_dir):
    """Legacy inspection only; canonical consumers use read_snapshot."""
    world = Path(world_dir)
    if load_json(world / 'world.json').get('contract_version'):
        from engine.runner import read_snapshot
        return read_snapshot(world)
    if (world / 'progress.json').exists():
        return load_json(world / 'progress.json')
    progress = {}
    for filename in ('world-changing.json', 'resources.json', 'threats.json'):
        path = world / 'progress' / filename
        if path.exists():
            progress.update(load_json(path))
    return progress


def save_progress(world_dir, progress):
    raise RuleError('legacy_writer_disabled', 'Direct save mutation is disabled; propose a canonical event and use python -m engine run EVENT')
