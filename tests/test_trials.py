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

    def test_trial_rejections_premature_remote_wrong_recipe_insufficient_resource(self):
        world = self.make_world('warhammer-40k')
        intro_event = self.event(world, {
            'type': 'introduce_threat',
            'template_id': 'event_crystal_garden_repair',
            'location_id': 'loc_hab_block_vermin'
        }, 'event_intro')
        report_intro = run_event(world, intro_event, render=False)
        trial_id = report_intro['outcomes']['threat_id']

        # Premature resolution (turn 37 < activation_turn 38)
        premature_event = self.event(world, {
            'type': 'resolve_trial',
            'actor_id': 'player_vane',
            'trial_id': trial_id,
            'recipe_id': 'recipe_crystal_garden_repair'
        }, 'event_premature')
        with self.assertRaises(RuleError) as err:
            run_event(world, premature_event, render=False)
        self.assertIn(err.exception.code, ('trial_inactive', 'trial_location'))

        # Wait a turn (advance to 38)
        run_event(world, self.event(world, {'type': 'wait', 'actor_id': 'player_vane'}, 'wait_38'), render=False)

        # Actor is at loc_shrine_aquila, trial is at loc_hab_block_vermin -> trial_location error
        remote_event = self.event(world, {
            'type': 'resolve_trial',
            'actor_id': 'player_vane',
            'trial_id': trial_id,
            'recipe_id': 'recipe_crystal_garden_repair'
        }, 'event_remote')
        with self.assertRaises(RuleError) as err:
            run_event(world, remote_event, render=False)
        self.assertEqual('trial_location', err.exception.code)

        # Move to loc_hab_block_vermin
        run_event(world, self.event(world, {'type': 'move', 'actor_id': 'player_vane', 'location_id': 'loc_hab_block_vermin'}, 'move_to_hab'), render=False)

        # Wrong recipe
        wrong_recipe_event = self.event(world, {
            'type': 'resolve_trial',
            'actor_id': 'player_vane',
            'trial_id': trial_id,
            'recipe_id': 'recipe_wayfarers_reconciliation'
        }, 'event_wrong_recipe')
        with self.assertRaises(RuleError) as err:
            run_event(world, wrong_recipe_event, render=False)
        self.assertEqual('invalid_recipe', err.exception.code)

        # Empty stock / insufficient resources
        def drain_water(state):
            state['resources']['crystalline_spring_water']['data']['quantity'] = 0
        drained_world = self.author_state(world, drain_water, 'drained_water_world')
        insufficient_event = self.event(drained_world, {
            'type': 'resolve_trial',
            'actor_id': 'player_vane',
            'trial_id': trial_id,
            'recipe_id': 'recipe_crystal_garden_repair'
        }, 'event_insufficient')
        with self.assertRaises(RuleError) as err:
            run_event(drained_world, insufficient_event, render=False)
        self.assertEqual('insufficient_resources', err.exception.code)
