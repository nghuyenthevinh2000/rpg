"""Resource policies and recipes exercise only authored temporary baselines."""
import copy
import json
import random
from unittest.mock import patch

from world_fixtures import ROOT, TemporaryWorldCase, hashes
from engine.contracts import RuleContext, RuleError, StateView, WorldContract
from engine.runner import read_snapshot, replay_event, run_event
from engine.state_store import StateStore


class ResourceTests(TemporaryWorldCase):
    def resource_world(self, name='warhammer-40k', quantity=8, capacity=10,
                       production=4, consumption=3, damage=0, sanctuary=False):
        source = self.make_world(name)
        actor_id = 'player_vane' if name == 'warhammer-40k' else 'player_kael'
        location = read_snapshot(source)['characters'][actor_id]['data']['location_id']
        self.edit_rules(source, lambda r: r.update(
            sanctuary=sanctuary, resource_recipes={}, resource_policies={
                'test_water': {'capacity': capacity, 'production_per_turn': production,
                               'consumption_per_turn': consumption,
                               'shortage_damage': damage, 'location_id': location}}))
        if name == 'warhammer-40k':
            path = source / 'definitions/world.json'
            data = json.loads(path.read_text())
            data['structural_rules']['transcendent_sanctuary'] = sanctuary
            path.write_text(json.dumps(data))
        def author(state):
            state['resources']['test_water'] = self.stock('test_water', quantity)
            actor = state['characters'][actor_id]['data']
            actor.update(health=100, status='alive')
            actor['capabilities']['cannot_die'] = False
        return self.author_state(source, author, 'resources_' + name)

    @staticmethod
    def stock(identity, quantity):
        return {'id': identity, 'revision': 0, 'schema_version': 1,
                'data': {'name': identity, 'quantity': quantity}}

    def wait(self, world, event_id='test_event'):
        return self.event(world, {'type': 'wait', 'actor_id':
            WorldContract(world, load_hooks=False).config['player_character_id']}, event_id)

    def recipe_world(self, name='warhammer-40k'):
        world = self.resource_world(name, quantity=4, production=0, consumption=0)
        location = read_snapshot(world)['characters'][
            WorldContract(world, load_hooks=False).config['player_character_id']]['data']['location_id']
        def configure(r):
            r['resource_policies']['warming_supply'] = {'capacity': 2}
            r['resource_recipes']['warming'] = {'location_id': location,
                'inputs': {'twigs': 5, 'test_water': 2},
                'outputs': {'warming_supply': 1}, 'health_cost': 3}
        # Stocks precede references: initialize the new authored baseline first.
        def author(state):
            state['resources']['twigs'] = self.stock('twigs', 5)
            state['resources']['warming_supply'] = self.stock('warming_supply', 0)
        world = self.author_state(world, author, 'recipe_' + name)
        self.edit_rules(world, configure)
        return world

    def produce(self, world, **extra):
        action = {'type': 'produce', 'actor_id':
            WorldContract(world, load_hooks=False).config['player_character_id'], 'recipe_id': 'warming'}
        action.update(extra)
        return self.event(world, action)

    def assert_rejected_unchanged(self, world, event):
        before = hashes(world)
        with self.assertRaises(RuleError):
            run_event(world, event, render=False)
        self.assertEqual(before, hashes(world))

    def test_production_precedes_consumption_once(self):
        world = self.resource_world()
        report = run_event(world, self.wait(world), render=False)
        self.assertEqual(7, read_snapshot(world)['resources']['test_water']['data']['quantity'])
        self.assertEqual(1, len(report['outcomes']['resources']))

    def test_recipe_debits_inputs_credits_output_and_cost_once_both_worlds(self):
        for name in ('lost-world', 'warhammer-40k'):
            with self.subTest(name=name):
                world = self.recipe_world(name)
                report = run_event(world, self.produce(world), render=False)
                state = read_snapshot(world)
                self.assertEqual(0, state['resources']['twigs']['data']['quantity'])
                self.assertEqual(2, state['resources']['test_water']['data']['quantity'])
                self.assertEqual(1, state['resources']['warming_supply']['data']['quantity'])
                actor = WorldContract(world).config['player_character_id']
                self.assertEqual(97, state['characters'][actor]['data']['health'])
                self.assertEqual(1, report['turn']['after'] - report['turn']['before'])
                self.assert_rejected_unchanged(world, report['event'])

    def test_recipe_insufficient_stock_is_atomic(self):
        world = self.recipe_world()
        world = self.author_state(world, lambda s: s['resources']['twigs']['data'].update(quantity=4), 'short_input')
        self.assert_rejected_unchanged(world, self.produce(world))

    def test_recipe_capacity_checks_alias_net_delta(self):
        for name in ('lost-world', 'warhammer-40k'):
            with self.subTest(name=name):
                world = self.recipe_world(name)
                self.edit_rules(world, lambda r: r['resource_recipes']['warming'].update(
                    inputs={'test_water': 2}, outputs={'test_water': 3}))
                report = run_event(world, self.produce(world), render=False)
                self.assertEqual(5, read_snapshot(world)['resources']['test_water']['data']['quantity'])
                effects = [e for e in report['effects'] if e['collection'] == 'resources']
                self.assertEqual(1, len(effects))
                world = self.author_state(world, lambda s: s['resources']['warming_supply']['data'].update(quantity=2), 'full_output_' + name)
                self.edit_rules(world, lambda r: r['resource_recipes']['warming'].update(
                    inputs={'warming_supply': 1}, outputs={'warming_supply': 1}))
                # A full stock remains valid when its atomic net change is zero.
                report = run_event(world, self.produce(world), render=False)
                self.assertEqual(2, read_snapshot(world)['resources']['warming_supply']['data']['quantity'])
                self.assertFalse(any(e['collection'] == 'resources' for e in report['effects']))

    def test_same_id_recipe_final_quantity_fits_capacity(self):
        for name in ('lost-world', 'warhammer-40k'):
            with self.subTest(name=name):
                world = self.recipe_world(name)
                world = self.author_state(world, lambda s: s['resources']['test_water']['data'].update(quantity=9), 'net_capacity_' + name)
                self.edit_rules(world, lambda r: r['resource_recipes']['warming'].update(
                    inputs={'test_water': 5}, outputs={'test_water': 6}))
                report = run_event(world, self.produce(world), render=False)
                self.assertEqual(10, read_snapshot(world)['resources']['test_water']['data']['quantity'])
                effects = [e for e in report['effects'] if e['collection'] == 'resources']
                self.assertEqual(1, len(effects))
                self.assertEqual(10, effects[0]['value'])

    def test_same_id_recipe_actual_net_overflow_rejects_atomically(self):
        for name in ('lost-world', 'warhammer-40k'):
            with self.subTest(name=name):
                world = self.recipe_world(name)
                world = self.author_state(world, lambda s: s['resources']['test_water']['data'].update(quantity=9), 'net_overflow_' + name)
                self.edit_rules(world, lambda r: r['resource_recipes']['warming'].update(
                    inputs={'test_water': 5}, outputs={'test_water': 7}))
                self.assert_rejected_unchanged(world, self.produce(world))

    def test_same_id_recipe_empty_stock_cannot_bootstrap_inputs(self):
        for name in ('lost-world', 'warhammer-40k'):
            with self.subTest(name=name):
                world = self.recipe_world(name)
                world = self.author_state(world, lambda s: s['resources']['test_water']['data'].update(quantity=0), 'empty_alias_' + name)
                self.edit_rules(world, lambda r: r['resource_recipes']['warming'].update(
                    inputs={'test_water': 1}, outputs={'test_water': 2}))
                event = self.produce(world)
                self.assert_rejected_unchanged(world, event)
                with self.assertRaises(RuleError) as error:
                    run_event(world, event, render=False)
                self.assertEqual('insufficient_resources', error.exception.code)

    def test_recipe_strict_intent_actor_location_and_lethal_cost(self):
        world = self.recipe_world()
        for extra in ({'quantity': 2}, {'recipe_id': 1}, {'recipe_id': 'missing'}, {'actor_id': 'missing'}):
            with self.subTest(extra=extra):
                self.assert_rejected_unchanged(world, self.produce(world, **extra))
        self.edit_rules(world, lambda r: r['resource_recipes']['warming'].update(health_cost=100))
        self.assert_rejected_unchanged(world, self.produce(world))
        world = self.author_state(world, lambda s: s['characters']['player_vane']['data']['capabilities'].update(cannot_die=True), 'immortal_work')
        run_event(world, self.produce(world), render=False)
        self.assertEqual(100, read_snapshot(world)['characters']['player_vane']['data']['health'])

    def test_recipe_remote_dead_actor_and_output_cannot_fund_inputs(self):
        world = self.recipe_world()
        self.edit_rules(world, lambda r: r['resource_recipes']['warming'].update(
            inputs={'test_water': 5}, outputs={'test_water': 5}))
        self.assert_rejected_unchanged(world, self.produce(world))
        self.edit_rules(world, lambda r: r['resource_recipes']['warming'].update(inputs={'test_water': 2}))
        self.edit_rules(world, lambda r: r['resource_recipes']['warming'].update(
            location_id=next(l['id'] for l in WorldContract(world).definitions['locations']['locations']
                if l['id'] != r['resource_recipes']['warming']['location_id'])))
        self.assert_rejected_unchanged(world, self.produce(world))
        dead = self.author_state(world, lambda s: s['characters']['player_vane']['data'].update(health=0, status='dead'), 'dead_worker')
        self.assert_rejected_unchanged(dead, self.produce(dead))

    def test_bad_policy_configuration_rejected_before_resolver_effects(self):
        world = self.resource_world(production=0, consumption=0)
        original = json.loads((world / 'definitions/engine_rules.json').read_text())
        event = self.wait(world)
        cases = [{'capacity': -1}, {'capacity': 7}, {'production_per_turn': -1},
                 {'consumption_per_turn': True}, {'shortage_damage': '5'},
                 {'unknown': 1}, {'location_id': 'missing'}, {'location_id': []}, {'production_per_turn': float('inf')},
                 {'consumption_per_turn': float('nan')}]
        for change in cases:
            with self.subTest(change=change):
                rules = copy.deepcopy(original)
                rules['resource_policies']['test_water'].update(change)
                (world / 'definitions/engine_rules.json').write_text(json.dumps(rules))
                self.assert_rejected_unchanged(world, event)
        (world / 'definitions/engine_rules.json').write_text(json.dumps(original))
        self.edit_rules(world, lambda r: r['resource_policies'].update(missing={'capacity': 10}))
        self.assert_rejected_unchanged(world, self.wait(world))

    def test_bad_recipe_configuration_rejected_even_for_wait(self):
        world = self.recipe_world()
        original = json.loads((world / 'definitions/engine_rules.json').read_text())
        event = self.wait(world)
        for change in ({'inputs': {'twigs': 0}}, {'outputs': {'warming_supply': -1}},
                       {'inputs': {'twigs': True}}, {'health_cost': -1},
                       {'health_cost': float('inf')}, {'location_id': 'missing'},
                       {'inputs': {'missing': 1}}, {'outputs': {'missing': 1}},
                       {'outputs': []}, {'outputs': {'twigs': 1}}, {'unknown': 1}):
            with self.subTest(change=change):
                rules = copy.deepcopy(original)
                rules['resource_recipes']['warming'].update(change)
                (world / 'definitions/engine_rules.json').write_text(json.dumps(rules))
                self.assert_rejected_unchanged(world, event)

    def test_shortages_sum_once_and_skip_dead_null_immortal_remote(self):
        world = self.resource_world(quantity=0, production=0, consumption=1, damage=5)
        location = read_snapshot(world)['characters']['player_vane']['data']['location_id']
        remote = next(l['id'] for l in WorldContract(world).definitions['locations']['locations'] if l['id'] != location)
        def author(s):
            s['resources']['test_food'] = self.stock('test_food', 0)
            for identity, health, dead, immune in (
                ('npc_ogryn_bragg', 100, False, False),
                ('npc_trooper_jax', 0, True, False),
                ('npc_enginseer_kroll', 100, False, True)):
                d = s['characters'][identity]['data']
                d.update(location_id=location, health=health, status='dead' if dead else 'alive')
                d['capabilities']['cannot_die'] = immune
            d = s['characters']['npc_confessor_malachi']['data']
            d.update(location_id=remote, health=100, status='alive')
            d['capabilities']['cannot_die'] = False
        world = self.author_state(world, author, 'two_shortages')
        self.edit_rules(world, lambda r: r['resource_policies'].update(test_food={
            'capacity': 10, 'consumption_per_turn': 1, 'shortage_damage': 7, 'location_id': location}))
        report = run_event(world, self.wait(world), render=False)
        state = read_snapshot(world)
        for identity in ('player_vane', 'npc_ogryn_bragg'):
            self.assertEqual(88, state['characters'][identity]['data']['health'])
            self.assertEqual(1, len([e for e in report['effects'] if e['entity_id'] == identity and e.get('path') == '/health']))
        self.assertEqual(0, state['characters']['npc_trooper_jax']['data']['health'])
        self.assertEqual(100, state['characters']['npc_enginseer_kroll']['data']['health'])
        self.assertEqual(100, state['characters']['npc_confessor_malachi']['data']['health'])
        # Warhammer's canonical schema currently excludes null health. Exercise
        # synthetic immunity through the helper's read-only context instead.
        state['characters']['player_vane']['data']['health'] = None
        contract = WorldContract(world)
        ctx = RuleContext(StateView(state), contract.definition_view, random.Random(0), state['clock']['data']['turn'])
        periodic = contract.after_turn(ctx, self.wait(world), {})
        self.assertFalse(any(e['entity_id'] == 'player_vane' for e in periodic.effects))

    def test_shortage_mortal_death_does_not_heal_or_revive(self):
        world = self.resource_world(quantity=0, production=0, consumption=1, damage=5)
        world = self.author_state(world, lambda s: s['characters']['player_vane']['data'].update(health=4), 'lethal_shortage')
        run_event(world, self.wait(world), render=False)
        data = read_snapshot(world)['characters']['player_vane']['data']
        self.assertEqual((0, 'dead'), (data['health'], data['status']))

    def test_warhammer_shortage_uses_post_attack_health_no_repeat_retaliation(self):
        world = self.resource_world(quantity=0, production=0, consumption=1, damage=5)
        def author(s):
            location = s['characters']['player_vane']['data']['location_id']
            s['threats']['enemy'] = {'id': 'enemy', 'revision': 0, 'schema_version': 1,
                'data': {'name': 'Enemy', 'location_id': location, 'active': True,
                         'activation_turn': 0, 'tags': ['hostile'], 'metadata': {},
                         'stats': {'health': 1, 'armor': 0, 'retaliation': 30}}}
        world = self.author_state(world, author, 'attack_shortage')
        event = self.event(world, {'type': 'attack', 'actor_id': 'player_vane',
            'target_id': 'enemy', 'weapon_id': 'item_void_relic_blade'})
        report = run_event(world, event, render=False)
        self.assertEqual(1, report['outcomes']['retaliations'])
        self.assertEqual(0, report['outcomes']['remaining_health'])
        self.assertEqual(100 - report['outcomes']['retaliation_damage'] - 5,
                         read_snapshot(world)['characters']['player_vane']['data']['health'])

    def test_lost_world_resources_preserve_cold_outcomes(self):
        world = self.resource_world('lost-world')
        def author(s):
            location = s['characters']['player_kael']['data']['location_id']
            s['threats']['cold_hazard'] = {'id': 'cold_hazard', 'revision': 0, 'schema_version': 1,
                'data': {'name': 'Cold', 'location_id': location, 'active': True,
                         'activation_turn': 0, 'tags': ['cold'], 'metadata': {},
                         'stats': {'health': 0, 'armor': 0, 'retaliation': 0}}}
        world = self.author_state(world, author, 'cold_resources')
        report = run_event(world, self.wait(world), seed=4, render=False)
        self.assertTrue(report['outcomes']['cold'])
        self.assertEqual(1, len(report['outcomes']['resources']))
        self.assertEqual([], report['outcomes']['resource_shortages'])
        self.assertEqual(7, read_snapshot(world)['resources']['test_water']['data']['quantity'])

    def test_sanctuary_and_lost_world_refuse_shortage_damage(self):
        for name, sanctuary in (('warhammer-40k', True), ('lost-world', False)):
            with self.subTest(name=name):
                world = self.resource_world(name, quantity=0, production=0, consumption=1, damage=5, sanctuary=sanctuary)
                self.assert_rejected_unchanged(world, self.wait(world))

    def test_resource_schema_requires_nonnegative_quantity_keeps_builtin_fields(self):
        world = self.resource_world()
        contract = WorldContract(world)
        for quantity in (-1, True, '2', float('inf'), float('nan'), None):
            with self.subTest(quantity=quantity), self.assertRaises(RuleError):
                contract.validate_envelope('resources', 'stock', self.stock('stock', quantity))
        missing = self.stock('stock', 1)
        del missing['data']['quantity']
        with self.assertRaises(RuleError):
            contract.validate_envelope('resources', 'stock', missing)
        valid = self.stock('stock', 1)
        valid['data'].update(amount=3, capacity=10, unit='litres', description='water',
                             status='ready', location_id='loc_test', metadata={})
        contract.validate_envelope('resources', 'stock', valid)

    def test_final_world_validation_reports_resource_configuration(self):
        world = self.resource_world()
        self.edit_rules(world, lambda r: r['resource_policies']['test_water'].update(capacity=1))
        contract = WorldContract(world)
        state = read_snapshot(world)
        ctx = RuleContext(StateView(state), contract.definition_view, random.Random(0), state['clock']['data']['turn'])
        self.assertTrue(any(v['code'] == 'resource_config' for v in contract.validate(ctx)))

    def test_replay_helper_hash_duplicate_and_recovery_exact(self):
        world = self.resource_world()
        twin = self.author_state(world, lambda s: None, 'replay_twin')
        archive_roots = [ROOT / 'world' / name / 'archive/legacy-baseline'
                         for name in ('lost-world', 'warhammer-40k')]
        archive_before = [hashes(root) for root in archive_roots]
        copied_archive = world.parent / 'warhammer-40k/archive/legacy-baseline'
        copied_before = hashes(copied_archive)
        self.assertTrue(copied_before)
        report = run_event(world, self.wait(world), render=False)
        helper = twin / 'logic/resources.py'
        first_hash = WorldContract(twin).rule_source_hash
        helper.write_text(helper.read_text() + '\n# authored source revision\n')
        self.assertNotEqual(first_hash, WorldContract(twin).rule_source_hash)
        helper.write_text(helper.read_text() + '\nraise RuntimeError("replay must not import")\n')
        replay_event(twin, report, render=False)
        self.assertEqual(read_snapshot(world), read_snapshot(twin))
        self.assertEqual(first_hash, report['metadata']['rule_source_hash'])
        self.assert_rejected_unchanged(world, report['event'])
        self.assertEqual(archive_before, [hashes(root) for root in archive_roots])
        self.assertEqual(copied_before, hashes(copied_archive))
        # 7 is the first policy's steady state. Change the authored consumption
        # to ensure the interrupted second turn actually changes a quantity.
        self.edit_rules(world, lambda r: r['resource_policies']['test_water'].update(consumption_per_turn=4))
        expected_snapshot = read_snapshot(world)
        expected = run_event(world, self.wait(world, 'recover_event'), dry_run=True, render=False)
        for reference, images in expected['changes'].items():
            if reference == 'clock':
                expected_snapshot['clock'] = images['after']
            else:
                collection, identity = reference.split('/')
                expected_snapshot[collection][identity] = images['after']
        with patch.object(StateStore, '_apply_images', side_effect=OSError('interrupted install')):
            with self.assertRaises(OSError):
                run_event(world, expected['event'], render=False)
        actual = read_snapshot(world)
        self.assertEqual(expected_snapshot, actual)
        self.assertEqual(expected['changes']['resources/test_water']['after'], actual['resources']['test_water'])
        self.assertEqual(expected['turn']['after'], actual['clock']['data']['turn'])
        self.assert_rejected_unchanged(world, expected['event'])
        self.assertEqual(archive_before, [hashes(root) for root in archive_roots])
        self.assertEqual(copied_before, hashes(copied_archive))

    def test_actual_canonical_worlds_load_read_only_and_archives_unchanged(self):
        archive_json_count = 0
        for name in ('lost-world', 'warhammer-40k'):
            world = ROOT / 'world' / name
            before = hashes(world)
            contract = WorldContract(world)
            state = read_snapshot(world)
            contract.validate_state(state)
            self.assertEqual(1, contract.config['state_schema_version'])
            self.assertEqual(before, hashes(world))
            archive_json_count += len(list((world / 'archive/legacy-baseline').rglob('*.json')))
        self.assertEqual(75, archive_json_count)
