"""Helpers-only temporary worlds; canonical saves are installed by StateStore."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.contracts import WorldContract, contained_path, safe_id
from engine.runner import read_snapshot
from engine.state_store import StateStore


def hashes(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()
            and p.suffix != '.pyc' and '__pycache__' not in p.parts
            and not p.name.endswith('.lock')}


class TemporaryWorldCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def legacy(self, name):
        live = contained_path(ROOT / 'world', name)
        source = live / 'archive/legacy-baseline'
        dest = Path(self.tmp.name) / name
        shutil.copytree(source, dest)
        for part in ('logic', 'schemas', 'contract.json', 'game_master.json', 'definitions/engine_rules.json', 'definitions/gm-pre-sanctuary.json'):
            src, target = live / part, dest / part
            target.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, target, dirs_exist_ok=True,
                                ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            elif src.exists():
                shutil.copy2(src, target)
        return dest

    def make_world(self, name='lost-world'):
        from engine.migration import migrate_world
        world = self.legacy(name)
        migrate_world(world)
        return world

    def author_state(self, world, transform, label):
        safe_id(label)
        state = read_snapshot(world)
        transform(state)
        destination = Path(self.tmp.name) / label
        shutil.copytree(world, destination, ignore=shutil.ignore_patterns(
            'state', 'events', 'transactions', 'archive', '.migration*',
            '*.lock', '__pycache__', '*.pyc', '.engine-*.tmp'))
        StateStore(destination).initialize_baseline(state)
        return destination

    def event(self, world, action, event_id='test_event'):
        state = read_snapshot(world)
        return {'schema_version': 1, 'event_id': event_id,
                'world_id': WorldContract(world, load_hooks=False).config['world_id'],
                'expected_turn': state['clock']['data']['turn'], 'action': action}

    def edit_rules(self, world, transform):
        path = contained_path(world, 'definitions/engine_rules.json')
        rules = json.loads(path.read_text())
        transform(rules)
        path.write_text(json.dumps(rules, indent=2, allow_nan=False) + '\n')

    # Compatibility aliases keep the original world regressions unchanged.
    def world(self, name='lost-world'):
        return self.make_world(name)

    def edit_baseline(self, world, transform):
        return self.author_state(world, transform, 'authored_' + world.name)
