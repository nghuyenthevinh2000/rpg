"""Contained helper provenance, imports and replay without rule execution."""
import json
import os
from pathlib import Path
import py_compile
import sys
from unittest.mock import patch

from world_fixtures import TemporaryWorldCase, hashes
from engine.contracts import RuleError, WorldContract
from engine.runner import read_snapshot, replay_event, run_event
from engine.state_store import StateStore


class RuleSourcesTests(TemporaryWorldCase):
    def test_helper_source_changes_provenance(self):
        world = self.make_world()
        helper = world / 'logic/custom_helper.py'
        helper.write_text('VALUE = 1\n')
        first = WorldContract(world).rule_source_hash
        helper.write_text('VALUE = 2\n')
        self.assertNotEqual(first, WorldContract(world).rule_source_hash)

    def test_no_hook_loading_keeps_empty_hash_without_execution(self):
        world = self.make_world()
        (world / 'logic/rules.py').write_text('raise RuntimeError("hook executed")\n')
        helper = world / 'logic/resources.py'
        helper.write_text('raise RuntimeError("helper executed")\n')
        empty_hash = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
        modules = {name for name in sys.modules if name.startswith('rpg_rules_')}
        self.assertEqual(empty_hash, WorldContract(world, load_hooks=False).rule_source_hash)
        helper.write_text('raise RuntimeError("helper changed")\n')
        self.assertEqual(empty_hash, WorldContract(world, load_hooks=False).rule_source_hash)
        self.assertEqual(modules, {name for name in sys.modules if name.startswith('rpg_rules_')})

    def test_relative_imports_dataclasses_and_same_size_edits(self):
        world = self.make_world()
        helper = world / 'logic/resources.py'
        helper.write_text('from __future__ import annotations\nfrom dataclasses import dataclass\n'
                          '@dataclass\nclass Stock:\n    value: int = 1\n')
        (world / 'logic/rules.py').write_text(
            'from .resources import Stock\n'
            'def resolve(*args): return Stock().value\n'
            'after_turn = derive = validate = resolve\n')
        paths = list(sys.path)
        first = WorldContract(world)
        self.assertEqual(1, first.resolve())
        timestamp = helper.stat().st_mtime_ns
        py_compile.compile(str(helper), doraise=True)
        helper.write_text(helper.read_text().replace('= 1', '= 2'))
        os.utime(helper, ns=(timestamp, timestamp))
        second = WorldContract(world)
        self.assertEqual(2, second.resolve())
        self.assertEqual(1, first.resolve())
        self.assertNotEqual(first.resolve.__module__, second.resolve.__module__)
        self.assertEqual(paths, sys.path)
        self.assertEqual([str((world / 'logic').resolve())],
                         sys.modules[second.resolve.__module__.rpartition('.')[0]].__path__)

    def test_nested_helpers_and_unimported_sources_are_hashed(self):
        world = self.make_world()
        directory = world / 'logic/nested'
        directory.mkdir()
        (directory / '__init__.py').write_text('from .values import VALUE\n')
        helper = directory / 'values.py'
        helper.write_text('VALUE = 3\n')
        (world / 'logic/rules.py').write_text(
            'from .nested import VALUE\n'
            'def resolve(*args): return VALUE\n'
            'after_turn = derive = validate = resolve\n')
        first = WorldContract(world)
        self.assertEqual(3, first.resolve())
        (directory / 'unused.py').write_text('raise RuntimeError("unused")\n')
        self.assertNotEqual(first.rule_source_hash, WorldContract(world).rule_source_hash)

    def test_source_hash_is_independent_of_copy_location_and_bytecode(self):
        world = self.make_world()
        twin = self.author_state(world, lambda state: None, 'twin')
        self.assertEqual(WorldContract(world).rule_source_hash,
                         WorldContract(twin).rule_source_hash)
        (world / 'logic/ignored.txt').write_text('not Python')
        before = WorldContract(world).rule_source_hash
        py_compile.compile(str(world / 'logic/rules.py'), doraise=True)
        self.assertEqual(before, WorldContract(world).rule_source_hash)

    def test_helper_symlinks_are_rejected_with_hooks(self):
        world = self.make_world()
        helper = world / 'logic/custom_helper.py'
        for target in (world / 'logic/rules.py', Path(self.tmp.name) / 'outside.py'):
            with self.subTest(target=target):
                if target.name == 'outside.py':
                    target.write_text('VALUE = 1\n')
                helper.symlink_to(target)
                try:
                    with self.assertRaises(RuleError) as error:
                        WorldContract(world)
                    self.assertEqual('unsafe_path', error.exception.code)
                finally:
                    helper.unlink()

    def test_helper_directory_symlink_is_rejected(self):
        world = self.make_world()
        directory = Path(self.tmp.name) / 'outside'
        directory.mkdir()
        (directory / 'helper.py').write_text('VALUE = 1\n')
        (world / 'logic/helpers').symlink_to(directory, target_is_directory=True)
        with self.assertRaises(RuleError) as error:
            WorldContract(world)
        self.assertEqual('unsafe_path', error.exception.code)

    def test_replay_archived_event_never_executes_hook_or_helper(self):
        world = self.make_world()
        twin = self.author_state(world, lambda state: None, 'replay_baseline')
        run_event(world, self.event(world, {'type': 'wait', 'actor_id': 'player_kael'}),
                  render=False)
        archived = json.loads((world / 'events/committed/test_event.json').read_text())
        (twin / 'logic/resources.py').write_text('raise RuntimeError("helper executed")\n')
        (twin / 'logic/rules.py').write_text(
            'from .resources import VALUE\nraise RuntimeError("hook executed")\n')
        replay_event(twin, archived, render=False)
        self.assertEqual(read_snapshot(world), read_snapshot(twin))

    def test_replay_and_snapshot_work_with_deleted_hook_or_missing_logic(self):
        world = self.make_world()
        twins = [self.author_state(world, lambda state: None, label)
                 for label in ('missing_hook', 'missing_logic')]
        baseline = read_snapshot(world)
        run_event(world, self.event(world, {'type': 'wait', 'actor_id': 'player_kael'}),
                  render=False)
        archived = json.loads((world / 'events/committed/test_event.json').read_text())
        expected = read_snapshot(world)
        for twin in twins:
            with self.subTest(world=twin.name):
                if twin.name == 'missing_hook':
                    (twin / 'logic/rules.py').unlink()
                else:
                    (twin / 'logic').rename(twin / 'unavailable_logic')
                self.assertEqual(baseline, read_snapshot(twin))
                replay_event(twin, archived, render=False)
                self.assertEqual(expected, read_snapshot(twin))
                with self.assertRaises(RuleError) as error:
                    WorldContract(twin)
                self.assertEqual('invalid_hook', error.exception.code)

    def test_snapshot_recovers_pending_transaction_without_logic(self):
        world = self.make_world()
        twin = self.author_state(world, lambda state: None, 'expected_recovery')
        event = self.event(world, {'type': 'wait', 'actor_id': 'player_kael'})
        run_event(twin, event, render=False)
        expected = read_snapshot(twin)
        with patch.object(StateStore, '_apply_images', side_effect=OSError('interrupted commit')):
            with self.assertRaises(OSError):
                run_event(world, event, render=False)
        journal_path = world / 'transactions/test_event.json'
        self.assertEqual('prepared', json.loads(journal_path.read_text())['status'])
        (world / 'logic').rename(world / 'unavailable_logic')
        self.assertEqual(expected, read_snapshot(world))
        self.assertEqual('committed', json.loads(journal_path.read_text())['status'])
        self.assertEqual(expected, read_snapshot(world))
        self.assertEqual(json.loads((twin / 'events/committed/test_event.json').read_text()),
                         json.loads((world / 'events/committed/test_event.json').read_text()))

    def test_no_hook_operations_ignore_unreadable_sources(self):
        world = self.make_world()
        twin = self.author_state(world, lambda state: None, 'unreadable_replay')
        run_event(world, self.event(world, {'type': 'wait', 'actor_id': 'player_kael'}),
                  render=False)
        archived = json.loads((world / 'events/committed/test_event.json').read_text())
        expected = read_snapshot(world)
        original = Path.read_bytes
        def unreadable(path):
            if path.suffix == '.py':
                raise PermissionError('unreadable rule source')
            return original(path)
        with patch.object(Path, 'read_bytes', unreadable):
            WorldContract(twin, load_hooks=False)
            replay_event(twin, archived, render=False)
            self.assertEqual(expected, read_snapshot(twin))
            with self.assertRaises(RuleError) as error:
                WorldContract(twin)
            self.assertEqual('invalid_hook', error.exception.code)

    def test_no_hook_loading_still_rejects_unsafe_or_invalid_hook_references(self):
        world = self.make_world()
        config_path = world / 'world.json'
        config = json.loads(config_path.read_text())
        variants = [('unsafe_path', '../outside.py:resolve'),
                    ('unsafe_path', '/outside.py:resolve'),
                    ('unsafe_path', 'logic\\rules.py:resolve'),
                    ('invalid_hook', 'logic/rules.txt:resolve'),
                    ('invalid_hook', 'logic/rules.py:not-valid'),
                    ('invalid_hook', 'logic/rules.py')]
        for code, reference in variants:
            with self.subTest(reference=reference):
                config['logic']['resolve'] = reference
                config_path.write_text(json.dumps(config))
                with self.assertRaises(RuleError) as error:
                    WorldContract(world, load_hooks=False)
                self.assertEqual(code, error.exception.code)

    def test_authored_state_is_fresh_and_source_is_unchanged(self):
        world = self.make_world()
        run_event(world, self.event(world, {'type': 'wait', 'actor_id': 'player_kael'}),
                  render=False)
        before = hashes(world)
        authored = self.author_state(world, lambda state: state['characters']['player_kael']
                                     ['data'].update(health=45), 'authored_health')
        self.assertEqual(before, hashes(world))
        self.assertEqual(45, read_snapshot(authored)['characters']['player_kael']['data']['health'])
        self.assertFalse((authored / '.migration.json').exists())
        self.assertFalse((authored / 'archive').exists())
        self.assertEqual(['engine_baseline.json'],
                         [p.name for p in (authored / 'events/committed').glob('*.json')])
        self.edit_rules(authored, lambda rules: rules.update(test_marker=True))
        self.assertTrue(json.loads((authored / 'definitions/engine_rules.json').read_text())['test_marker'])
        self.assertEqual('named_event', self.event(authored, {'type': 'wait'},
                                                event_id='named_event')['event_id'])
