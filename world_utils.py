"""World selection and read-only compatibility helpers."""
from pathlib import Path
from engine.contracts import RuleError, load_json

RPG_DIR = Path(__file__).resolve().parent


def resolve_world_dir(world_arg=None, event_path=None):
    if world_arg:
        candidate = Path(world_arg).expanduser()
        if not candidate.is_dir():
            candidate = RPG_DIR / 'world' / world_arg
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
        raise RuleError('migration_incomplete', 'Migration is pending; inspect .migration.json and use migrate_world.py --resume only for ready staging')
    if config.get('contract_version') != 1:
        raise RuleError('legacy_world', 'Gameplay is disabled: run inspect_world.py then migrate_world.py --world WORLD')
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
    raise RuleError('legacy_writer_disabled', 'Direct save mutation is disabled; propose a canonical event and use change_world.py')
