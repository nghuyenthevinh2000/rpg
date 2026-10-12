"""Tests for engine package CLI and supporting module relocation."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tests.world_fixtures import ROOT, TemporaryWorldCase, hashes


class PackageWorldUtilsTests(TemporaryWorldCase):
    def test_package_world_root_is_rpg_root(self):
        from engine.world_utils import RPG_DIR, resolve_world_dir
        self.assertEqual(ROOT, RPG_DIR)
        self.assertEqual((ROOT / 'world/lost-world').resolve(),
                         resolve_world_dir('lost-world'))

    def test_known_world_name_not_shadowed_by_cwd(self):
        from engine.world_utils import resolve_world_dir
        with tempfile.TemporaryDirectory() as temp_dir:
            orig_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                # Create a local directory named 'lost-world' in temp_dir with dummy world.json
                fake_local = Path(temp_dir) / 'lost-world'
                fake_local.mkdir()
                (fake_local / 'world.json').write_text('{"id": "fake"}')

                # Known name without path separators must resolve to repository world
                self.assertEqual((ROOT / 'world/lost-world').resolve(),
                                 resolve_world_dir('lost-world'))

                # Explicit relative path must resolve to the local working directory path
                self.assertEqual(fake_local.resolve(),
                                 resolve_world_dir('./lost-world'))
            finally:
                os.chdir(orig_cwd)

    def test_subprocess_import_from_unrelated_cwd(self):
        with tempfile.TemporaryDirectory() as empty_dir:
            script = (
                "import sys, os\n"
                "import engine.world_utils\n"
                "def fail_loader(*args, **kwargs):\n"
                "    raise RuntimeError('world load triggered on import')\n"
                "engine.world_utils.require_canonical = fail_loader\n"
                "import engine.cli\n"
                "import engine.migration\n"
                "import engine.game_master\n"
                "import engine.world_utils\n"
            )
            cmd = [sys.executable, '-c', script]
            env = os.environ.copy()
            env['PYTHONPATH'] = str(ROOT)
            proc = subprocess.run(cmd, cwd=empty_dir, env=env, capture_output=True, text=True)
            self.assertEqual(0, proc.returncode, f"Subprocess failed:\nstdout: {proc.stdout}\nstderr: {proc.stderr}")
            self.assertEqual("", proc.stdout)
            self.assertEqual("", proc.stderr)

    def test_no_hook_replay_cli_isolation(self):
        # API replay with deleted/unusable world Python source using the existing no-hook regression;
        # importing the unified CLI must not force replay to execute rules.
        import engine.cli
        from engine.runner import run_event, replay_event, read_snapshot
        world = self.make_world('lost-world')
        twin = self.author_state(world, lambda state: None, 'replay_baseline_cli')
        run_event(world, self.event(world, {'type': 'wait', 'actor_id': 'player_kael'}), render=False)
        archived = json.loads((world / 'events/committed/test_event.json').read_text())
        (twin / 'logic/resources.py').write_text('raise RuntimeError("helper executed")\n')
        (twin / 'logic/rules.py').write_text('from .resources import VALUE\nraise RuntimeError("hook executed")\n')
        # Replaying event into twin must not execute hook or helper
        replay_event(twin, archived, render=False)
        self.assertEqual(read_snapshot(world), read_snapshot(twin))

    def test_explicit_temporary_paths_and_event_inference(self):
        from engine.world_utils import resolve_world_dir
        world = self.legacy('lost-world')
        # Explicit path to world directory
        self.assertEqual(world.resolve(), resolve_world_dir(str(world)))
        # Inferred from event/
        event_dir = world / 'event'
        event_dir.mkdir(parents=True, exist_ok=True)
        event_file = event_dir / 'event_001.json'
        event_file.write_text('{}')
        self.assertEqual(world.resolve(), resolve_world_dir(event_path=str(event_file)))
        # Inferred from events/proposed/
        proposed_dir = world / 'events/proposed'
        proposed_dir.mkdir(parents=True, exist_ok=True)
        prop_file = proposed_dir / 'prop_001.json'
        prop_file.write_text('{}')
        self.assertEqual(world.resolve(), resolve_world_dir(event_path=str(prop_file)))
        # Inferred from events/committed/
        committed_dir = world / 'events/committed'
        committed_dir.mkdir(parents=True, exist_ok=True)
        comm_file = committed_dir / 'comm_001.json'
        comm_file.write_text('{}')
        self.assertEqual(world.resolve(), resolve_world_dir(event_path=str(comm_file)))

    def test_package_layout_removed_wrappers_do_not_exist(self):
        retired_wrappers = [
            'change_world.py',
            'apply_event.py',
            'resolve-threat.py',
            'enforce_char_stats.py',
            'enforce_progress_effects.py',
            'render_map.py',
            'inspect_world.py',
            'migrate_world.py',
        ]
        existing = [name for name in retired_wrappers if (ROOT / name).exists()]
        self.assertEqual([], existing, f"Retired root wrappers must not exist: {existing}")



class EngineCLITests(TemporaryWorldCase):
    def invoke(self, *args):
        return subprocess.run([sys.executable, '-m', 'engine', *args],
                              cwd=ROOT, capture_output=True, text=True)

    def test_help_world_independent(self):
        res = self.invoke('--help')
        self.assertEqual(0, res.returncode, res.stderr)
        self.assertIn('run', res.stdout)
        self.assertIn('inspect', res.stdout)
        self.assertIn('migrate', res.stdout)
        self.assertIn('render', res.stdout)
        self.assertIn('gm', res.stdout)
        self.assertIn('stats', res.stdout)
        self.assertIn('timing', res.stdout)

    def test_subcommand_helps_world_independent(self):
        for subcmd in ('run', 'inspect', 'migrate', 'render', 'gm', 'stats', 'timing'):
            res = self.invoke(subcmd, '--help')
            self.assertEqual(0, res.returncode, f"{subcmd} --help failed: {res.stderr}")
            self.assertIn('usage:', res.stdout.lower())

    def test_inspect_emits_json_without_mutation(self):
        world = self.make_world('lost-world')
        before = hashes(world)
        result = self.invoke('inspect', '--world', str(world))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIsInstance(json.loads(result.stdout), dict)
        self.assertEqual(before, hashes(world))

    def test_legacy_world_refusal_by_canonical_commands(self):
        world = self.legacy('lost-world')
        for cmd in (['stats', '--world', str(world)],
                    ['timing', '--world', str(world)],
                    ['render', '--world', str(world)],
                    ['gm', '--world', str(world)]):
            res = self.invoke(*cmd)
            self.assertEqual(2, res.returncode, f"{cmd} should reject legacy world, got {res.returncode}")
            data = json.loads(res.stderr)
            self.assertIn('error', data)

    def _create_event_file(self, world, action, event_id='test_event', filename=None):
        event_dict = self.event(world, action, event_id=event_id)
        if filename is None:
            filename = f'{event_id}.json'
        p = world / 'events/proposed' / filename
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(event_dict))
        return p

    def cold(self, health=10, immortal=False, trait=True):
        w = self.world()
        def edit(s):
            d = s['characters']['player_kael']['data']
            d['health'] = health
            d['capabilities']['cannot_die'] = immortal
            d['traits'] = ['trait_unyielding_survival'] if trait else []
            s['threats']['cold'] = {'id': 'cold', 'revision': 0, 'schema_version': 1, 'data': {'name': 'Cold', 'location_id': 'loc_monastery', 'active': True, 'activation_turn': 33, 'tags': ['cold'], 'stats': {'health': 100, 'armor': 0, 'retaliation': 0}, 'metadata': {}}}
        return self.edit_baseline(w, edit)

    def test_run_dry_run_leaves_hashes_unchanged(self):
        world = self.world()
        event_path = self._create_event_file(world, {'type': 'wait', 'actor_id': 'player_kael'})
        before = hashes(world)
        res = self.invoke('run', str(event_path), '--world', str(world), '--dry-run')
        self.assertEqual(0, res.returncode, res.stderr)
        data = json.loads(res.stdout)
        self.assertTrue(data.get('dry_run'))
        self.assertEqual(before, hashes(world))

    def test_run_commit_advances_once_and_duplicate_rejects(self):
        world = self.world()
        event_path = self._create_event_file(world, {'type': 'wait', 'actor_id': 'player_kael'})
        before_turn = json.loads((world / 'state/clock.json').read_text())['data']['turn']

        # First run: advances once
        res = self.invoke('run', str(event_path), '--world', str(world))
        self.assertEqual(0, res.returncode, res.stderr)
        after_turn = json.loads((world / 'state/clock.json').read_text())['data']['turn']
        self.assertEqual(before_turn + 1, after_turn)

        # Duplicate run: rejected
        res2 = self.invoke('run', str(event_path), '--world', str(world))
        self.assertEqual(2, res2.returncode, "Duplicate event submission should be rejected")
        err = json.loads(res2.stderr)
        self.assertIn('error', err)

    def test_run_with_inferred_world_from_event_path(self):
        world = self.world()
        event_path = self._create_event_file(world, {'type': 'wait', 'actor_id': 'player_kael'})
        abs_event_path = str(event_path.resolve())
        # Omit --world; world should be inferred from event path
        res = self.invoke('run', abs_event_path, '--dry-run')
        self.assertEqual(0, res.returncode, res.stderr)
        data = json.loads(res.stdout)
        self.assertTrue(data.get('dry_run'))

    def test_replay_succeeds_only_into_exact_fresh_baseline(self):
        import shutil
        world = self.cold(health=100)
        twin = Path(self.tmp.name) / 'twin_replay'
        shutil.copytree(world, twin)

        event_path = self._create_event_file(world, {'type': 'wait', 'actor_id': 'player_kael'})
        res = self.invoke('run', str(event_path), '--world', str(world), '--seed', '42', '--no-render')
        self.assertEqual(0, res.returncode, res.stderr)

        committed_events = [p for p in (world / 'events/committed').glob('*.json') if p.name != 'engine_baseline.json']
        self.assertEqual(1, len(committed_events))
        committed_file = committed_events[0]

        # Replay into fresh twin baseline
        res_rep = self.invoke('run', str(committed_file), '--world', str(twin), '--replay', '--no-render')
        self.assertEqual(0, res_rep.returncode, res_rep.stderr)
        self.assertEqual(
            json.loads((world / 'state/clock.json').read_text()),
            json.loads((twin / 'state/clock.json').read_text())
        )

        # Replaying again into non-matching or advanced state must fail
        res_rep2 = self.invoke('run', str(committed_file), '--world', str(twin), '--replay', '--no-render')
        self.assertEqual(2, res_rep2.returncode)

    def test_stats_and_timing_are_read_only(self):
        world = self.world()
        before = hashes(world)

        res_stats = self.invoke('stats', '--world', str(world))
        self.assertEqual(0, res_stats.returncode, res_stats.stderr)
        data_stats = json.loads(res_stats.stdout)
        self.assertTrue(data_stats.get('read_only'))
        self.assertIn('derived', data_stats)
        self.assertEqual(before, hashes(world))

        res_timing = self.invoke('timing', '--world', str(world))
        self.assertEqual(0, res_timing.returncode, res_timing.stderr)
        data_timing = json.loads(res_timing.stdout)
        self.assertTrue(data_timing.get('read_only'))
        self.assertIn('clock', data_timing)
        self.assertEqual(before, hashes(world))

    def test_gm_writes_only_one_proposal(self):
        world = self.world()
        proposed_dir = world / 'events/proposed'
        existing_proposals = list(proposed_dir.glob('*.json'))
        before_state = hashes(world / 'state')

        res = self.invoke('gm', '--world', str(world), '--seed', '1', '--improvise')
        self.assertEqual(0, res.returncode, res.stderr)
        proposal = json.loads(res.stdout)
        self.assertEqual('lost-world', proposal['world_id'])

        new_proposals = list(proposed_dir.glob('*.json'))
        self.assertEqual(len(existing_proposals) + 1, len(new_proposals))
        # state must not be modified
        self.assertEqual(before_state, hashes(world / 'state'))

    def test_render_changes_only_projection(self):
        world = self.world()
        state_before = hashes(world / 'state')
        res = self.invoke('render', '--world', str(world))
        self.assertEqual(0, res.returncode, res.stderr)
        self.assertTrue((world / 'map.html').exists())
        self.assertEqual(state_before, hashes(world / 'state'))

    def test_migration_dry_run_is_read_only(self):
        world = self.legacy('lost-world')
        before = hashes(world)
        res = self.invoke('migrate', '--world', str(world), '--dry-run')
        self.assertEqual(0, res.returncode, res.stderr)
        report = json.loads(res.stdout)
        self.assertTrue(report.get('preview'))
        self.assertEqual(before, hashes(world))

    def test_staged_migration_and_resume_behavior(self):
        from unittest.mock import patch
        import engine.migration
        world = self.legacy('lost-world')
        # Simulate interruption during migration cutover
        real_atomic = engine.migration._atomic

        def interrupt(path, value):
            if Path(path).resolve() == (world / 'world.json').resolve():
                raise OSError('simulated interruption before world.json')
            return real_atomic(path, value)

        # Test within current process to allow unittest.mock.patch
        with patch.object(engine.migration, '_atomic', side_effect=interrupt):
            from engine.cli import main
            ret = main(['migrate', '--world', str(world)])
            self.assertEqual(3, ret)

        # Now resume the staged migration via invoke
        res_resume = self.invoke('migrate', '--world', str(world), '--resume')
        self.assertEqual(0, res_resume.returncode, res_resume.stderr)
        report = json.loads(res_resume.stdout)
        self.assertFalse(report.get('preview'))
        journal = json.loads((world / '.migration.json').read_text())
        self.assertEqual('complete', journal.get('phase'))
        self.assertTrue((world / 'world.json').exists())

    def test_usage_and_error_handling(self):
        world = self.world()

        # Missing subcommand
        res = self.invoke()
        self.assertEqual(2, res.returncode)

        # Unknown subcommand
        res = self.invoke('unknown_cmd')
        self.assertEqual(2, res.returncode)

        # Unknown flags
        res = self.invoke('run', '--bogus')
        self.assertEqual(2, res.returncode)

        # Missing required --world for inspect / migrate
        res = self.invoke('inspect')
        self.assertEqual(2, res.returncode)
        res = self.invoke('migrate')
        self.assertEqual(2, res.returncode)

        # Missing event for run
        res = self.invoke('run', '--world', str(world))
        self.assertEqual(2, res.returncode)

        # Event passed to GM or inspection (argparse positional error since gm/inspect accept no positional args)
        res = self.invoke('gm', 'some_event.json', '--world', str(world))
        self.assertEqual(2, res.returncode)
        res = self.invoke('inspect', 'some_event.json', '--world', str(world))
        self.assertEqual(2, res.returncode)

        # run with removed GM flags: --improvise / --force-gm
        res = self.invoke('run', 'dummy.json', '--improvise')
        self.assertEqual(2, res.returncode)
        res = self.invoke('run', 'dummy.json', '--force-gm')
        self.assertEqual(2, res.returncode)

        # run with --replay and --dry-run combined
        event_path = self._create_event_file(world, {'type': 'wait', 'actor_id': 'player_kael'})
        res = self.invoke('run', str(event_path), '--world', str(world), '--replay', '--dry-run')
        self.assertEqual(2, res.returncode)
        err = json.loads(res.stderr)
        self.assertEqual('unsupported_flag', err['error']['code'])

    def test_inspect_blocking_exit_code(self):
        world = self.legacy('lost-world')
        p = world / 'progress.json'
        d = json.loads(p.read_text())
        d['active_actions'][0]['location'] = 'missing_location'
        p.write_text(json.dumps(d))

        res = self.invoke('inspect', '--world', str(world))
        # Blocking inspection must exit 2 while printing valid JSON to stdout
        self.assertEqual(2, res.returncode)
        report = json.loads(res.stdout)
        self.assertTrue(report.get('blocking'))

    def test_oserror_filesystem_interruption_guidance(self):
        from unittest.mock import patch
        import engine.cli
        from engine.cli import main
        world = self.world()
        event_path = self._create_event_file(world, {'type': 'wait', 'actor_id': 'player_kael'})

        with patch.object(engine.cli, 'run_event', side_effect=OSError('disk failure')):
            import io
            captured_err = io.StringIO()
            old_stderr = sys.stderr
            try:
                sys.stderr = captured_err
                code = main(['run', str(event_path), '--world', str(world)])
            finally:
                sys.stderr = old_stderr

            self.assertEqual(3, code)
            err = json.loads(captured_err.getvalue())
            self.assertEqual('filesystem_interruption', err['error']['code'])
            self.assertIn('Do not resubmit an uncertain turn', err['error']['guidance'])




