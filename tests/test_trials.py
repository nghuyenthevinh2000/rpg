"""Tests for peaceful GM templates and trial resolution."""
import copy
import json
from pathlib import Path
from engine.contracts import RuleError, WorldContract
from engine.runner import read_snapshot, run_event
from game_master import propose_event, allowed_templates
from world_fixtures import TemporaryWorldCase, hashes


class TrialsTests(TemporaryWorldCase):
    def test_sanctuary_proposal_is_playable_and_state_is_unchanged(self):
        world = self.make_world('warhammer-40k')
        before = read_snapshot(world)
        proposal = propose_event(world, seed=7)
        self.assertEqual(before, read_snapshot(world))
        report = run_event(world, proposal, dry_run=True, render=False)
        self.assertIn('threat_id', report['outcomes'])
        self.assertEqual(before, read_snapshot(world))

    def test_sanctuary_filters_hostile_templates_and_allows_peaceful(self):
        world = self.make_world('warhammer-40k')
        contract = WorldContract(world, load_hooks=False)
        allowed = allowed_templates(contract)
        self.assertTrue(len(allowed) > 0)
        for t in allowed:
            spec = contract.definitions['rules']['templates'][t['id']]
            self.assertTrue(any(tag in ('opportunity', 'social') for tag in spec['tags']))
            self.assertFalse(any(tag in ('hostile', 'cold') for tag in spec['tags']))

    def test_trial_resolution_flow_and_rewards(self):
        world = self.make_world('warhammer-40k')
        # Introduce a trial
        intro_event = self.event(world, {
            'type': 'introduce_threat',
            'template_id': 'event_crystal_garden_repair',
            'location_id': 'loc_hab_block_vermin'
        }, 'event_intro_trial')
        report_intro = run_event(world, intro_event, render=False)
        trial_id = report_intro['outcomes']['threat_id']
        threat_data = read_snapshot(world)['threats'][trial_id]['data']
        self.assertTrue(threat_data['active'])
        self.assertEqual(38, threat_data['activation_turn'])

        # Moving player to loc_hab_block_vermin on turn 38
        move_event = self.event(world, {
            'type': 'move',
            'actor_id': 'player_vane',
            'location_id': 'loc_hab_block_vermin'
        }, 'event_move')
        run_event(world, move_event, render=False)

        # Before resolving trial, check stock: crystalline_spring_water and golden_harvest_fruits
        s_before = read_snapshot(world)
        water_before = s_before['resources']['crystalline_spring_water']['data']['quantity']
        fruits_before = s_before['resources']['golden_harvest_fruits']['data']['quantity']

        resolve_event = self.event(world, {
            'type': 'resolve_trial',
            'actor_id': 'player_vane',
            'trial_id': trial_id,
            'recipe_id': 'recipe_crystal_garden_repair'
        }, 'event_resolve_trial')
        report_res = run_event(world, resolve_event, render=False)
        self.assertEqual(trial_id, report_res['outcomes']['trial_id'])

        s_after = read_snapshot(world)
        # Trial marked inactive
        self.assertFalse(s_after['threats'][trial_id]['data']['active'])
        # Resources updated: -5 water, +10 fruits
        self.assertEqual(water_before - 5, s_after['resources']['crystalline_spring_water']['data']['quantity'])
        self.assertEqual(fruits_before + 10, s_after['resources']['golden_harvest_fruits']['data']['quantity'])
        # Trait granted: trait_adaptable_spirit
        self.assertIn('trait_adaptable_spirit', s_after['characters']['player_vane']['data']['traits'])

        # Duplicate / repeated resolution rejected
        repeat_event = self.event(world, {
            'type': 'resolve_trial',
            'actor_id': 'player_vane',
            'trial_id': trial_id,
            'recipe_id': 'recipe_crystal_garden_repair'
        }, 'event_repeat_resolve')
        with self.assertRaises(RuleError) as err:
            run_event(world, repeat_event, render=False)
        self.assertEqual('invalid_trial', err.exception.code)

    def test_introduction_location_mismatch_rejected(self):
        world = self.make_world('warhammer-40k')
        before = read_snapshot(world)
        # Template declares loc_hab_block_vermin; try introducing at loc_shrine_aquila
        bad_intro = self.event(world, {
            'type': 'introduce_threat',
            'template_id': 'event_crystal_garden_repair',
            'location_id': 'loc_shrine_aquila'
        }, 'event_bad_intro')
        with self.assertRaises(RuleError) as err:
            run_event(world, bad_intro, render=False)
        self.assertEqual('invalid_location', err.exception.code)
        self.assertEqual(before, read_snapshot(world))

    def test_misplaced_trial_resolution_rejected(self):
        world = self.make_world('warhammer-40k')
        # Author trial at loc_shrine_aquila when recipe requires loc_hab_block_vermin
        def author_misplaced(state):
            state['threats']['trial_misplaced'] = {
                'id': 'trial_misplaced',
                'revision': 0,
                'schema_version': 1,
                'data': {
                    'name': 'Misplaced Trial',
                    'location_id': 'loc_shrine_aquila',
                    'active': True,
                    'activation_turn': 37,
                    'tags': ['opportunity'],
                    'stats': {'health': 0, 'armor': 0, 'retaliation': 0},
                    'metadata': {'template_id': 'event_crystal_garden_repair'}
                }
            }
        w = self.author_state(world, author_misplaced, 'misplaced_trial')
        before = read_snapshot(w)
        # Actor is at loc_shrine_aquila, trial is at loc_shrine_aquila, but recipe requires loc_hab_block_vermin
        event = self.event(w, {
            'type': 'resolve_trial',
            'actor_id': 'player_vane',
            'trial_id': 'trial_misplaced',
            'recipe_id': 'recipe_crystal_garden_repair'
        })
        with self.assertRaises(RuleError) as err:
            run_event(w, event, render=False)
        self.assertEqual('trial_location', err.exception.code)
        self.assertEqual(before, read_snapshot(w))

    def test_premature_activation_and_subsequent_eligibility(self):
        world = self.make_world('warhammer-40k')
        # Move player to loc_hab_block_vermin first
        run_event(world, self.event(world, {'type':'move', 'actor_id':'player_vane', 'location_id':'loc_hab_block_vermin'}, 'mv'), render=False)
        current_turn = read_snapshot(world)['clock']['data']['turn']

        # Author a co-located trial with activation_turn = current_turn + 1
        def author_trial(state):
            state['threats']['trial_future'] = {
                'id': 'trial_future',
                'revision': 0,
                'schema_version': 1,
                'data': {
                    'name': 'Future Trial',
                    'location_id': 'loc_hab_block_vermin',
                    'active': True,
                    'activation_turn': current_turn + 1,
                    'tags': ['opportunity'],
                    'stats': {'health': 0, 'armor': 0, 'retaliation': 0},
                    'metadata': {'template_id': 'event_crystal_garden_repair'}
                }
            }
        w = self.author_state(world, author_trial, 'fut_trial')
        before = read_snapshot(w)

        # Attempt resolving prematurely: must fail with trial_inactive and leave snapshot untouched
        premature = self.event(w, {
            'type': 'resolve_trial',
            'actor_id': 'player_vane',
            'trial_id': 'trial_future',
            'recipe_id': 'recipe_crystal_garden_repair'
        }, 'premature')
        with self.assertRaises(RuleError) as err:
            run_event(w, premature, render=False)
        self.assertEqual('trial_inactive', err.exception.code)
        self.assertEqual(before, read_snapshot(w))

        # Wait a turn to advance to current_turn + 1
        run_event(w, self.event(w, {'type':'wait', 'actor_id':'player_vane'}, 'wait_advance'), render=False)

        # Now resolve on the following turn: eligible and succeeds
        res_event = self.event(w, {
            'type': 'resolve_trial',
            'actor_id': 'player_vane',
            'trial_id': 'trial_future',
            'recipe_id': 'recipe_crystal_garden_repair'
        }, 'now_eligible')
        report = run_event(w, res_event, render=False)
        self.assertEqual('trial_future', report['outcomes']['trial_id'])

    def test_trial_configuration_rejections_runner_level(self):
        for bad_cost in [-5, True, 'ten']:
            self.tmp.cleanup(); self.setUp()
            world = self.make_world('warhammer-40k')
            self.edit_rules(world, lambda rules: rules['trial_recipes']['recipe_crystal_garden_repair']['resource_costs'].update({'crystalline_spring_water': bad_cost}))
            before = read_snapshot(world)
            with self.assertRaises(RuleError) as err:
                run_event(world, self.event(world, {'type':'wait', 'actor_id':'player_vane'}), render=False)
            self.assertEqual('trial_config', err.exception.code)
            self.assertEqual(before, read_snapshot(world))

        for bad_reward in [-10, True, 'five']:
            self.tmp.cleanup(); self.setUp()
            world = self.make_world('warhammer-40k')
            self.edit_rules(world, lambda rules: rules['trial_recipes']['recipe_crystal_garden_repair']['resource_rewards'].update({'golden_harvest_fruits': bad_reward}))
            before = read_snapshot(world)
            with self.assertRaises(RuleError) as err:
                run_event(world, self.event(world, {'type':'wait', 'actor_id':'player_vane'}), render=False)
            self.assertEqual('trial_config', err.exception.code)
            self.assertEqual(before, read_snapshot(world))

        # Explicit null trial_recipes container
        self.tmp.cleanup(); self.setUp()
        world_null = self.make_world('warhammer-40k')
        self.edit_rules(world_null, lambda rules: rules.update(trial_recipes=None))
        before_null = read_snapshot(world_null)
        with self.assertRaises(RuleError) as err:
            run_event(world_null, self.event(world_null, {'type':'wait', 'actor_id':'player_vane'}), render=False)
        self.assertEqual('trial_config', err.exception.code)
        self.assertEqual(before_null, read_snapshot(world_null))

        # Unhashable trait_rewards element (e.g. dict inside list)
        self.tmp.cleanup(); self.setUp()
        world_unhash = self.make_world('warhammer-40k')
        self.edit_rules(world_unhash, lambda rules: rules['trial_recipes']['recipe_crystal_garden_repair'].update(trait_rewards=[{'unhashable': True}]))
        before_unhash = read_snapshot(world_unhash)
        with self.assertRaises(RuleError) as err:
            run_event(world_unhash, self.event(world_unhash, {'type':'wait', 'actor_id':'player_vane'}), render=False)
        self.assertEqual('trial_config', err.exception.code)
        self.assertEqual(before_unhash, read_snapshot(world_unhash))

        # Unknown structural prerequisite name
        self.tmp.cleanup(); self.setUp()
        world_struct = self.make_world('warhammer-40k')
        self.edit_rules(world_struct, lambda rules: rules['trial_recipes']['recipe_crystal_garden_repair'].update(structural_requirements={'unknown_condition_flag': True}))
        before_struct = read_snapshot(world_struct)
        with self.assertRaises(RuleError) as err:
            run_event(world_struct, self.event(world_struct, {'type':'wait', 'actor_id':'player_vane'}), render=False)
        self.assertEqual('trial_config', err.exception.code)
        self.assertEqual(before_struct, read_snapshot(world_struct))

    def test_trial_net_quantity_conservation_both_worlds(self):
        # Cases:
        # 1. old 8000 / cost 5 / reward 10 -> 8005 and one resource effect
        # 2. old 0 / cost 5 / reward 10 -> unchanged rejection (insufficient_resources)
        # 3. old at capacity / cost 5 / reward 5 -> accepted net-zero stock
        # 4. actual net overflow -> unchanged rejection (resource_capacity)
        for world_id in ['warhammer-40k', 'lost-world']:
            self.tmp.cleanup(); self.setUp()
            world = self.make_world(world_id)

            actor_id = 'player_vane' if world_id == 'warhammer-40k' else 'player_kael'
            loc_id = 'loc_hab_block_vermin' if world_id == 'warhammer-40k' else 'loc_monastery'
            tpl_id = 'event_crystal_garden_repair' if world_id == 'warhammer-40k' else 'event_sudden_unregulated_squall'
            rec_id = 'recipe_crystal_garden_repair' if world_id == 'warhammer-40k' else 'recipe_sudden_unregulated_squall'
            res_id = 'crystalline_spring_water' if world_id == 'warhammer-40k' else 'raw_cedar_timber'

            # 1. old 8000 / cost 5 / reward 10 -> 8005
            def setup_8000(state):
                state['characters'][actor_id]['data']['location_id'] = loc_id
                state['resources'][res_id] = {
                    'id': res_id, 'revision': 0, 'schema_version': 1,
                    'data': {'name': 'Test Res', 'quantity': 8000, 'capacity': 10000}
                }
                state['threats']['t_net'] = {
                    'id': 't_net', 'revision': 0, 'schema_version': 1,
                    'data': {
                        'name': 'Net Trial', 'location_id': loc_id, 'active': True,
                        'activation_turn': 0, 'tags': ['opportunity'],
                        'stats': {'health': 0, 'armor': 0, 'retaliation': 0},
                        'metadata': {'template_id': tpl_id}
                    }
                }
            w1 = self.author_state(world, setup_8000, 'net_8000')
            self.edit_rules(w1, lambda rules: rules['trial_recipes'][rec_id].update({
                'location_id': loc_id,
                'resource_costs': {res_id: 5},
                'resource_rewards': {res_id: 10},
                'structural_requirements': {}
            }))
            report = run_event(w1, self.event(w1, {
                'type': 'resolve_trial', 'actor_id': actor_id, 'trial_id': 't_net', 'recipe_id': rec_id
            }), render=False)
            s1 = read_snapshot(w1)
            self.assertEqual(8005, s1['resources'][res_id]['data']['quantity'])

            # 2. old 0 / cost 5 / reward 10 -> unchanged rejection
            self.tmp.cleanup(); self.setUp()
            world2 = self.make_world(world_id)
            def setup_0(state):
                setup_8000(state)
                state['resources'][res_id]['data']['quantity'] = 0
            w2 = self.author_state(world2, setup_0, 'net_0')
            self.edit_rules(w2, lambda rules: rules['trial_recipes'][rec_id].update({
                'location_id': loc_id,
                'resource_costs': {res_id: 5},
                'resource_rewards': {res_id: 10},
                'structural_requirements': {}
            }))
            before2 = read_snapshot(w2)
            with self.assertRaises(RuleError) as err:
                run_event(w2, self.event(w2, {
                    'type': 'resolve_trial', 'actor_id': actor_id, 'trial_id': 't_net', 'recipe_id': rec_id
                }), render=False)
            self.assertEqual('insufficient_resources', err.exception.code)
            self.assertEqual(before2, read_snapshot(w2))

            # 3. old at capacity / cost 5 / reward 5 -> accepted net-zero stock
            self.tmp.cleanup(); self.setUp()
            world3 = self.make_world(world_id)
            def setup_cap(state):
                setup_8000(state)
                state['resources'][res_id]['data']['quantity'] = 1000
                state['resources'][res_id]['data']['capacity'] = 1000
            w3 = self.author_state(world3, setup_cap, 'net_cap')
            self.edit_rules(w3, lambda rules: rules['trial_recipes'][rec_id].update({
                'location_id': loc_id,
                'resource_costs': {res_id: 5},
                'resource_rewards': {res_id: 5},
                'structural_requirements': {}
            }))
            run_event(w3, self.event(w3, {
                'type': 'resolve_trial', 'actor_id': actor_id, 'trial_id': 't_net', 'recipe_id': rec_id
            }), render=False)
            s3 = read_snapshot(w3)
            self.assertEqual(1000, s3['resources'][res_id]['data']['quantity'])

            # 4. actual net overflow -> unchanged rejection
            self.tmp.cleanup(); self.setUp()
            world4 = self.make_world(world_id)
            w4 = self.author_state(world4, setup_cap, 'net_over')
            self.edit_rules(w4, lambda rules: rules['trial_recipes'][rec_id].update({
                'location_id': loc_id,
                'resource_costs': {res_id: 5},
                'resource_rewards': {res_id: 10},
                'structural_requirements': {}
            }))
            before4 = read_snapshot(w4)
            with self.assertRaises(RuleError) as err:
                run_event(w4, self.event(w4, {
                    'type': 'resolve_trial', 'actor_id': actor_id, 'trial_id': 't_net', 'recipe_id': rec_id
                }), render=False)
            self.assertEqual('resource_capacity', err.exception.code)
            self.assertEqual(before4, read_snapshot(w4))

    def test_lost_world_trial_earned_trait_rewards(self):
        world = self.make_world('lost-world')
        # Setup trial with trait reward
        def author_lw_trial(state):
            # Remove trait_unyielding_survival if player already has it
            kael = state['characters']['player_kael']['data']
            if 'trait_unyielding_survival' in kael['traits']:
                kael['traits'].remove('trait_unyielding_survival')
            kael['location_id'] = 'loc_monastery'
            state['threats']['trial_squall'] = {
                'id': 'trial_squall', 'revision': 0, 'schema_version': 1,
                'data': {
                    'name': 'Squall Trial', 'location_id': 'loc_monastery', 'active': True,
                    'activation_turn': 0, 'tags': ['weather'],
                    'stats': {'health': 0, 'armor': 0, 'retaliation': 0},
                    'metadata': {'template_id': 'event_sudden_unregulated_squall'}
                }
            }
        w = self.author_state(world, author_lw_trial, 'lw_trial')
        self.edit_rules(w, lambda rules: rules['trial_recipes']['recipe_sudden_unregulated_squall'].update({
            'trait_rewards': ['trait_unyielding_survival']
        }))
        before_hp = read_snapshot(w)['characters']['player_kael']['data']['health']
        before_base = read_snapshot(w)['characters']['player_kael']['data']['baseline']

        event = self.event(w, {
            'type': 'resolve_trial', 'actor_id': 'player_kael',
            'trial_id': 'trial_squall', 'recipe_id': 'recipe_sudden_unregulated_squall'
        })
        run_event(w, event, render=False)

        s_after = read_snapshot(w)
        kael_data = s_after['characters']['player_kael']['data']
        self.assertIn('trait_unyielding_survival', kael_data['traits'])
        self.assertEqual(before_hp, kael_data['health'])
        self.assertEqual(before_base, kael_data['baseline'])
        self.assertFalse(s_after['threats']['trial_squall']['data']['active'])

        # Repeat resolution rejected
        repeat_event = self.event(w, {
            'type': 'resolve_trial', 'actor_id': 'player_kael',
            'trial_id': 'trial_squall', 'recipe_id': 'recipe_sudden_unregulated_squall'
        }, 'repeat_resolve')
        with self.assertRaises(RuleError) as err:
            run_event(w, repeat_event, render=False)
        self.assertEqual('invalid_trial', err.exception.code)
