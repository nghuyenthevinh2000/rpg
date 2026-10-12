"""Temporary-save integration checks; never advance a live world."""
import copy
import json
from pathlib import Path
import random
import shutil
import subprocess
import sys
from unittest.mock import patch

from world_fixtures import ROOT, TemporaryWorldCase, hashes
from engine.contracts import RuleContext, RuleError, StateView, WorldContract
from engine.runner import read_snapshot, replay_event, run_event


class WorldsTests(TemporaryWorldCase):
    def test_inspection_read_only_both_saves(self):
        from engine.migration import inspect_world
        for name in ('lost-world', 'warhammer-40k'):
            w = self.legacy(name)
            before = hashes(w)
            report = inspect_world(w)
            self.assertEqual(before, hashes(w))
            self.assertTrue(report['issues'])
            self.assertFalse(report['blocking'])
            codes = {i['code'] for i in report['issues']}
            self.assertIn('baseline_modifiers', codes)
            self.assertIn('legacy_event_shape', codes)
            if name == 'warhammer-40k':
                self.assertIn('ignored_nested_event_030_updates', codes)

    def test_character_schema_rejects_arbitrary_baseline_modifier(self):
        w = self.world()
        s = read_snapshot(w)
        s['characters']['player_kael']['data']['baseline']['modifiers']['raw_patch_power'] = 99
        with self.assertRaises(RuleError):
            self.edit_baseline(w, lambda state: state.update(s))

    def test_import_baseline_archive_and_no_live_mutation(self):
        from engine.migration import migrate_world
        for name, turn, day in [('lost-world', 33, 4), ('warhammer-40k', 37, 9)]:
            live_before = hashes(ROOT / 'world' / name)
            w = self.legacy(name)
            originals = {p: h for p,h in hashes(w).items() if p.endswith('.json') and not p.startswith(('logic/', 'schemas/', 'definitions/engine_rules', 'definitions/gm-pre-sanctuary')) and p != 'contract.json'}
            self.assertTrue(migrate_world(w, dry_run=True)['preview'])
            self.assertFalse((w / 'archive').exists())
            migrate_world(w)
            s = read_snapshot(w)
            self.assertEqual((turn, day), (s['clock']['data']['turn'], s['clock']['data']['day']))
            archive = hashes(w / 'archive/legacy-baseline')
            for p,h in originals.items():
                self.assertEqual(h, archive[p])
            self.assertEqual(live_before, hashes(ROOT / 'world' / name))
            with self.assertRaises(RuleError):
                migrate_world(w)

    def test_mortality_and_sentinel(self):
        s = read_snapshot(self.world('warhammer-40k'))
        self.assertTrue(s['characters']['player_vane']['data']['capabilities']['cannot_die'])
        self.assertGreaterEqual(s['characters']['player_vane']['data']['health'], 0)
        for key, e in s['characters'].items():
            if key != 'player_vane':
                self.assertEqual('dead', e['data']['status'])

    def test_move_undirected_both_worlds_and_strict_actions(self):
        for name in ('lost-world', 'warhammer-40k'):
            w = self.world(name)
            contract = WorldContract(w)
            player = contract.config['player_character_id']
            current = read_snapshot(w)['characters'][player]['data']['location_id']
            locations = {l['id']: l for l in contract.definitions['locations']['locations']}
            target = next(l['id'] for l in locations.values() if current in l.get('connected_to', []) or l['id'] in locations[current].get('connected_to', []))
            event = self.event(w, {'type': 'move', 'actor_id': player, 'location_id': target})
            run_event(w, event, render=False)
            self.assertEqual(target, read_snapshot(w)['characters'][player]['data']['location_id'])
            with self.assertRaises(RuleError):
                run_event(w, self.event(w, {'type': 'wait', 'actor_id': player, 'patch': {}}), render=False)

    def test_derivation_idempotent_baseline_relative(self):
        w = self.world('warhammer-40k')
        s = read_snapshot(w)
        c = WorldContract(w)
        ctx = RuleContext(StateView(s), c.definition_view, random.Random(0), 37)
        before = copy.deepcopy(s)
        first = c.derive(ctx, 'characters/player_vane')
        self.assertEqual(first, c.derive(ctx, 'characters/player_vane'))
        self.assertEqual(200, first['stats']['strength'])
        self.assertEqual(before, s)

    def cold(self, health=10, immortal=False, trait=True):
        w = self.world()
        def edit(s):
            d = s['characters']['player_kael']['data']
            d['health'] = health
            d['capabilities']['cannot_die'] = immortal
            d['traits'] = ['trait_unyielding_survival'] if trait else []
            s['threats']['cold'] = {'id': 'cold', 'revision': 0, 'schema_version': 1, 'data': {'name': 'Cold', 'location_id': 'loc_monastery', 'active': True, 'activation_turn': 33, 'tags': ['cold'], 'stats': {'health': 100, 'armor': 0, 'retaliation': 0}, 'metadata': {}}}
        return self.edit_baseline(w, edit)

    def test_cold_floor_never_heals_dead_and_remote_untouched(self):
        w = self.cold()
        event = self.event(w, {'type': 'wait', 'actor_id': 'player_kael'})
        r = run_event(w, event, seed=0, render=False)
        s = read_snapshot(w)
        self.assertEqual(10, s['characters']['player_kael']['data']['health'])
        self.assertEqual(70, s['characters']['npc_lyra_orator']['data']['health'])
        self.assertIsNone(s['characters']['entity_mirror_ghost']['data']['health'])
        self.assertEqual(4, len(r['outcomes']['cold']))

    def test_cold_failure_death_and_immortal(self):
        w = self.cold(trait=False)
        run_event(w, self.event(w, {'type': 'wait', 'actor_id': 'player_kael'}), render=False)
        self.assertEqual('dead', read_snapshot(w)['characters']['player_kael']['data']['status'])
        with self.assertRaises(RuleError):
            run_event(w, self.event(w, {'type': 'wait', 'actor_id': 'player_kael'}, 'dead_wait'), render=False)
        self.tmp.cleanup()
        self.setUp()
        w = self.cold(immortal=True)
        run_event(w, self.event(w, {'type': 'wait', 'actor_id': 'player_kael'}), render=False)
        self.assertEqual(10, read_snapshot(w)['characters']['player_kael']['data']['health'])

    def test_seeded_replay_exact(self):
        w = self.cold(health=100)
        twin = Path(self.tmp.name) / 'twin'
        shutil.copytree(w, twin)
        event = self.event(w, {'type': 'wait', 'actor_id': 'player_kael'})
        r = run_event(w, event, seed=42, render=False)
        replay_event(twin, r, render=False)
        self.assertEqual(read_snapshot(w), read_snapshot(twin))

    def combat(self, immortal=False, hp=100, target_hp=1):
        w = self.world('warhammer-40k')
        rules = json.loads((w / 'definitions/engine_rules.json').read_text())
        rules['sanctuary'] = False
        (w / 'definitions/engine_rules.json').write_text(json.dumps(rules))
        lore = json.loads((w / 'definitions/world.json').read_text())
        lore['structural_rules']['transcendent_sanctuary'] = False
        (w / 'definitions/world.json').write_text(json.dumps(lore))
        def edit(s):
            d = s['characters']['player_vane']['data']
            d['health'] = hp
            d['capabilities']['cannot_die'] = immortal
            s['threats']['enemy'] = {'id': 'enemy', 'revision': 0, 'schema_version': 1, 'data': {'name': 'Enemy', 'location_id': d['location_id'], 'active': True, 'activation_turn': 37, 'tags': ['hostile'], 'stats': {'health': target_hp, 'armor': 0, 'retaliation': 80}, 'metadata': {}}}
        return self.edit_baseline(w, edit)

    def test_combat_killing_blow_retaliates_once_mortal_and_immortal(self):
        w = self.combat(hp=10)
        r = run_event(w, self.event(w, {'type': 'attack', 'actor_id': 'player_vane', 'target_id': 'enemy', 'weapon_id': 'item_void_relic_blade'}), render=False)
        s = read_snapshot(w)
        self.assertFalse(s['threats']['enemy']['data']['active'])
        self.assertEqual('dead', s['characters']['player_vane']['data']['status'])
        self.assertEqual(1, r['outcomes']['retaliations'])

    def test_combat_immortality_and_resource_failure_atomic(self):
        w = self.combat(immortal=True)
        event = self.event(w, {'type': 'attack', 'actor_id': 'player_vane', 'target_id': 'enemy', 'weapon_id': 'item_storm_bolter', 'resource_id': 'wrong'})
        before = read_snapshot(w)
        with self.assertRaises(RuleError):
            run_event(w, event, render=False)
        self.assertEqual(before, read_snapshot(w))
        run_event(w, self.event(w, {'type': 'attack', 'actor_id': 'player_vane', 'target_id': 'enemy', 'weapon_id': 'item_void_relic_blade'}), render=False)
        self.assertEqual(100, read_snapshot(w)['characters']['player_vane']['data']['health'])

    def test_sanctuary_rejects_combat_and_gm(self):
        w = self.world('warhammer-40k')
        gm_pre = json.loads((w / 'definitions/gm-pre-sanctuary.json').read_text())
        (w / 'game_master.json').write_text(json.dumps(gm_pre))
        rules_path = w / 'definitions/engine_rules.json'
        rules = json.loads(rules_path.read_text())
        rules['templates']['event_sump_mutant_breach'] = {'tags': ['hostile'], 'stats': {'health': 120, 'armor': 0.2, 'retaliation': 25}}
        rules_path.write_text(json.dumps(rules))
        for action in ({'type':'attack', 'actor_id':'player_vane', 'target_id':'enemy', 'weapon_id':'item_void_relic_blade'}, {'type':'introduce_threat', 'template_id':'event_sump_mutant_breach', 'location_id':'loc_shrine_aquila'}):
            with self.assertRaises(RuleError) as error:
                run_event(w, self.event(w, action), render=False)
            self.assertEqual('sanctuary', error.exception.code)

    def test_gm_selected_world_proposal_only_and_activation(self):
        from engine.game_master import propose_event
        w = self.world()
        before = read_snapshot(w)
        proposal = propose_event(w, seed=1, improvise=True)
        self.assertEqual(before, read_snapshot(w))
        self.assertEqual('lost-world', proposal['world_id'])
        self.assertEqual({'clock': 0}, proposal['expected_revisions'])
        self.assertEqual(1, len(list((w / 'events/proposed').glob('*.json'))))
        r = run_event(w, proposal, render=False)
        self.assertEqual(34, read_snapshot(w)['threats'][r['outcomes']['threat_id']]['data']['activation_turn'])

    def test_renderer_escaping_and_stale_snapshot_guard(self):
        from engine.render_map import render_map
        w = self.world()
        s = read_snapshot(w)
        s['characters']['player_kael']['data']['name'] = '<script>bad</script>'
        authored = self.edit_baseline(w, lambda state: state.update(s))
        captured = read_snapshot(authored)
        render_map(authored, captured)
        text = (authored / 'map.html').read_text()
        self.assertIn('&lt;script&gt;bad&lt;/script&gt;', text)
        self.assertNotIn('<script>bad</script>', text)
        run_event(authored, self.event(authored, {'type':'wait', 'actor_id':'player_kael'}), render=True)
        current = (authored / 'map.html').read_text()
        self.assertIn('Turn 34', current)
        with self.assertRaises(RuleError):
            render_map(authored, captured)
        self.assertEqual(current, (authored / 'map.html').read_text())

    def test_legacy_writer_disabled_and_path_inference(self):
        from engine.world_utils import resolve_world_dir, save_progress
        w = self.legacy('lost-world')
        with self.assertRaises(RuleError):
            save_progress(w, {})
        self.assertEqual(w.resolve(), resolve_world_dir(event_path=w / 'events/proposed/one.json'))
        with self.assertRaises(RuleError):
            resolve_world_dir('definitely-unknown')
        for subcmd in ('stats', 'timing', 'render'):
            r = subprocess.run([sys.executable, '-m', 'engine', subcmd, '--world', str(w)], capture_output=True, text=True)
            self.assertNotEqual(0, r.returncode)


    def test_interrupted_migration_refuses_retry_retains_legacy_authority(self):
        import engine.migration
        w = self.legacy('lost-world')
        original = (w / 'world.json').read_bytes()
        with patch.object(engine.migration, '_cutover', side_effect=OSError('interruption')):
            with self.assertRaises(OSError):
                engine.migration.migrate_world(w)
        self.assertEqual(original, (w / 'world.json').read_bytes())
        archive = hashes(w / 'archive/legacy-baseline')
        with self.assertRaises(RuleError):
            engine.migration.migrate_world(w)
        self.assertEqual(archive, hashes(w / 'archive/legacy-baseline'))
        self.assertFalse(engine.migration.migrate_world(w, resume=True)['preview'])
        self.assertEqual(33, read_snapshot(w)['clock']['data']['turn'])

    def test_bad_character_reference_blocks_import(self):
        from engine.migration import inspect_world, migrate_world
        w = self.legacy('lost-world')
        p = w / 'char/main_char.json'
        d = json.loads(p.read_text()); d['current_location'] = 'unknown'; p.write_text(json.dumps(d))
        self.assertTrue(inspect_world(w)['blocking'])
        with self.assertRaises(RuleError):
            migrate_world(w)

    def test_inspect_blocks_active_action_location_reference(self):
        from engine.migration import inspect_world, migrate_world
        w = self.legacy('lost-world')
        p = w / 'progress.json'; d = json.loads(p.read_text())
        d['active_actions'][0]['location'] = 'missing_location'
        p.write_text(json.dumps(d))
        self.assertTrue(inspect_world(w)['blocking'])
        with self.assertRaises(RuleError):
            migrate_world(w)
        self.assertFalse((w / 'archive').exists())

    def test_resume_checks_installed_baseline_before_contract(self):
        import engine.migration
        w = self.legacy('lost-world')
        real_atomic = engine.migration._atomic
        def interrupt(path, value):
            if Path(path).resolve() == (w / 'world.json').resolve():
                raise OSError('before contract')
            return real_atomic(path, value)
        with patch.object(engine.migration, '_atomic', side_effect=interrupt):
            with self.assertRaises(OSError):
                engine.migration.migrate_world(w)
        p = w / 'state/characters/player_kael.json'
        d = json.loads(p.read_text()); d['data']['health'] = 9; p.write_text(json.dumps(d))
        with self.assertRaises(RuleError):
            engine.migration.migrate_world(w, resume=True)
        self.assertNotIn('contract_version', json.loads((w / 'world.json').read_text()))

    def test_cold_movement_overlay_dead_and_failed_survival(self):
        w = self.cold()
        # Author a fresh source, because authored copy names are intentionally unique.
        s = read_snapshot(w)
        s['characters']['npc_dr_harlan']['data']['status'] = 'dead'
        s['characters']['npc_dr_harlan']['data']['health'] = 0
        from engine.state_store import StateStore
        destination = Path(self.tmp.name) / 'dead_cold'
        shutil.copytree(w, destination, ignore=shutil.ignore_patterns('state','transactions','events','.engine.lock'))
        StateStore(destination).initialize_baseline(s)
        r = run_event(destination, self.event(destination, {'type':'move','actor_id':'player_kael','location_id':'loc_echo_plaza'}), seed=4, render=False)
        self.assertEqual(0, read_snapshot(destination)['characters']['npc_dr_harlan']['data']['health'])
        self.assertNotIn('player_kael', [o['actor_id'] for o in r['outcomes']['cold']])
        self.assertTrue(any(o['result'] == 'survival_failed' for o in r['outcomes']['cold']))

    def test_combat_ammunition_debits_and_insufficient_rejects(self):
        w = self.combat(immortal=True, target_hp=10000)
        s = read_snapshot(w)
        s['resources']['bolter_rounds'] = {'id':'bolter_rounds','revision':0,'schema_version':1,'data':{'name':'Ammo','quantity':3}}
        from engine.state_store import StateStore
        destination = Path(self.tmp.name) / 'ammo_combat'
        shutil.copytree(w, destination, ignore=shutil.ignore_patterns('state','transactions','events','.engine.lock'))
        StateStore(destination).initialize_baseline(s)
        action = {'type':'attack','actor_id':'player_vane','target_id':'enemy','weapon_id':'item_storm_bolter','resource_id':'bolter_rounds'}
        run_event(destination, self.event(destination, action), render=False)
        before = read_snapshot(destination)
        self.assertEqual(1, before['resources']['bolter_rounds']['data']['quantity'])
        with self.assertRaises(RuleError):
            run_event(destination, self.event(destination, action, 'no_ammo'), render=False)
        self.assertEqual(before, read_snapshot(destination))

    def test_derivation_equipment_offset_no_health_change(self):
        w = self.world('warhammer-40k'); c = WorldContract(w); s = read_snapshot(w)
        before = copy.deepcopy(s)
        s['characters']['player_vane']['data']['equipment'].remove('item_void_relic_blade')
        ctx = RuleContext(StateView(s), c.definition_view, random.Random(0), 37)
        effective = c.derive(ctx, 'characters/player_vane')
        self.assertEqual(150, effective['stats']['strength'])
        self.assertEqual(before['characters']['player_vane']['data']['health'], effective['health'])
        self.assertEqual(effective, c.derive(ctx, 'characters/player_vane'))

    def test_new_cold_hazard_does_not_act_on_introduction(self):
        w = self.world()
        r = run_event(w, self.event(w, {'type':'introduce_threat','template_id':'event_famine_of_salt','location_id':'loc_monastery'}), render=False)
        self.assertEqual([], r['outcomes']['cold'])
        next_report = run_event(w, self.event(w, {'type':'wait','actor_id':'player_kael'}, 'next_turn'), render=False)
        self.assertEqual(4, len(next_report['outcomes']['cold']))

    def test_unknown_equipment_id_and_casefold_block(self):
        from engine.migration import inspect_world, migrate_world
        w = self.legacy('warhammer-40k'); p = w / 'char/main_char.json'
        d = json.loads(p.read_text()); d['equipment']['armor'] = 'item_not_real'; p.write_text(json.dumps(d))
        self.assertTrue(inspect_world(w)['blocking'])
        with self.assertRaises(RuleError):
            migrate_world(w)
        alias = copy.deepcopy(d); alias['id'] = 'PLAYER_VANE'
        (w / 'char/alias.json').write_text(json.dumps(alias))
        with self.assertRaises(RuleError) as error:
            inspect_world(w)
        self.assertEqual('casefold_collision', error.exception.code)

    def test_canonical_inspection_commands_do_not_write(self):
        w = self.world()
        before = hashes(w)
        for subcmd in ('stats', 'timing'):
            result = subprocess.run([sys.executable, '-m', 'engine', subcmd, '--world', str(w)], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(before, hashes(w))
        p = w / 'legacy_event.json'; p.write_text(json.dumps({'character_updates':{}}))
        result = subprocess.run([sys.executable, '-m', 'engine', 'run', str(p), '--world', str(w)], capture_output=True, text=True)
        self.assertEqual(2, result.returncode)
        self.assertIn('legacy_event', result.stderr)


    def test_warhammer_gm_pool_no_application(self):
        from engine.game_master import propose_event
        w = self.world('warhammer-40k'); before = read_snapshot(w)
        # Authored hostile GM pool copy retains stale hostile template narrative
        gm_pre = json.loads((w / 'definitions/gm-pre-sanctuary.json').read_text())
        (w / 'game_master.json').write_text(json.dumps(gm_pre))
        with self.assertRaises(RuleError) as err:
            propose_event(w, seed=2, improvise=True)
        self.assertEqual('no_templates', err.exception.code)
        self.assertEqual(before, read_snapshot(w))

    def test_import_unsupported_fields_metadata_not_executable(self):
        w = self.world(); s = read_snapshot(w)
        record = s['actions']['action_build_structure']['data']
        self.assertFalse(record['metadata']['executable'])
        self.assertIn('seeker_surgeon', record['metadata']['legacy']['assigned_participants'])
        self.assertNotIn('seeker_surgeon', s['characters'])
        self.assertNotIn('cold', s['threats']['event_sudden_unregulated_squall']['data']['tags'])

    def test_migration_partial_stage_refuses_and_archive_never_overwritten(self):
        import engine.migration
        from engine.state_store import StateStore
        w = self.legacy('lost-world')
        with patch.object(StateStore, 'initialize_baseline', side_effect=OSError('baseline interruption')):
            with self.assertRaises(OSError):
                engine.migration.migrate_world(w)
        archive = hashes(w / 'archive/legacy-baseline')
        for resume in (False,True):
            with self.assertRaises(RuleError):
                engine.migration.migrate_world(w,resume=resume)
        self.assertEqual(archive, hashes(w / 'archive/legacy-baseline'))

    def test_move_rejects_disconnected_and_dry_run_no_writes(self):
        w = self.world(); before = hashes(w)
        event = self.event(w, {'type':'move','actor_id':'player_kael','location_id':'loc_echo_plaza'})
        run_event(w,event,dry_run=True,render=True)
        self.assertEqual(before,hashes(w))
        with self.assertRaises(RuleError):
            run_event(w,self.event(w,{'type':'move','actor_id':'player_kael','location_id':'loc_mirror_apex'}),render=False)
        self.assertEqual(before,hashes(w))

    def test_contract_installed_journal_pending_refuses_gameplay_until_resume(self):
        import engine.migration
        from engine.world_utils import require_canonical
        w = self.legacy('lost-world')
        atomic = engine.migration._atomic
        def interrupt(path, value):
            if Path(path).name == '.migration.json' and value['phase'] == 'complete':
                raise OSError('journal finalization')
            return atomic(path,value)
        with patch.object(engine.migration,'_atomic',side_effect=interrupt):
            with self.assertRaises(OSError):
                engine.migration.migrate_world(w)
        self.assertEqual(1,json.loads((w/'world.json').read_text())['contract_version'])
        with self.assertRaises(RuleError):
            require_canonical(w)
        engine.migration.migrate_world(w,resume=True)
        require_canonical(w)
