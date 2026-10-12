"""End-to-end integration and acceptance tests across all remaining mechanics."""
import copy
from engine.contracts import RuleError
from engine.runner import read_snapshot, run_event
from engine.render_map import render_map
from world_fixtures import TemporaryWorldCase


class RemainingMechanicsIntegrationTests(TemporaryWorldCase):
    def test_project_display_uses_committed_fulfillment(self):
        # Authors or completes a project and verifies rendering
        world = self.make_world('lost-world')
        def author(state):
            state['actions'] = {}
            for identity in ('player_kael', 'npc_marcus_the_drifter'):
                data = state['characters'][identity]['data']
                data.update(status='alive', health=100, location_id='loc_monastery')
            state['characters']['player_kael']['data']['stats']['universal_dividend_balance'] = 949999
            for identity, quantity in (('raw_cedar_timber', 40), ('quarried_granite_slabs', 25)):
                state['resources'][identity] = {'id': identity, 'revision': 0, 'schema_version': 1,
                    'data': {'name': identity, 'quantity': quantity, 'capacity': quantity}}
        world = self.author_state(world, author, 'project_e2e')

        # Start project
        run_event(world, self.event(world, {
            'type': 'start_project', 'actor_id': 'player_kael',
            'template_id': 'action_build_structure', 'project_id': 'hall_1',
            'participant_ids': ['player_kael', 'npc_marcus_the_drifter']
        }, 'start_hall'), render=False)

        # Deliver materials
        run_event(world, self.event(world, {
            'type': 'deliver_materials', 'actor_id': 'player_kael',
            'project_id': 'hall_1', 'resource_id': 'raw_cedar_timber', 'quantity': 40
        }, 'deliv_1'), render=False)
        run_event(world, self.event(world, {
            'type': 'deliver_materials', 'actor_id': 'player_kael',
            'project_id': 'hall_1', 'resource_id': 'quarried_granite_slabs', 'quantity': 25
        }, 'deliv_2'), render=False)

        # Site preparations
        run_event(world, self.event(world, {
            'type': 'prepare_project_site', 'actor_id': 'player_kael',
            'project_id': 'hall_1', 'recipe_id': 'sever_telemetry'
        }, 'prep_1'), render=False)
        run_event(world, self.event(world, {
            'type': 'prepare_project_site', 'actor_id': 'player_kael',
            'project_id': 'hall_1', 'recipe_id': 'reject_drones'
        }, 'prep_2'), render=False)

        # Work project (60 turns * 2 workers = 120 hours)
        for i in range(60):
            run_event(world, self.event(world, {
                'type': 'work_project', 'actor_id': 'player_kael',
                'project_id': 'hall_1'
            }, f'work_{i}'), render=False)

        # Complete project
        run_event(world, self.event(world, {
            'type': 'complete_project', 'actor_id': 'player_kael',
            'project_id': 'hall_1'
        }, 'complete_hall'), render=False)

        render_map(world)
        html = (world / 'map.html').read_text()
        self.assertIn('120 / 120', html)
        self.assertIn('Completed', html)
        self.assertNotIn('<script>project</script>', html)

    def test_peaceful_sanctuary_end_to_end_flow(self):
        # Test full sanctuary cycle: peaceful opportunity introduction -> trial resolution -> calendar rollover
        world = self.make_world('warhammer-40k')
        start_clock = read_snapshot(world)['clock']['data']
        self.assertEqual(37, start_clock['turn'])
        self.assertEqual(9, start_clock['day'])

        # Introduce peaceful opportunity
        intro = self.event(world, {
            'type': 'introduce_threat',
            'template_id': 'event_crystal_garden_repair',
            'location_id': 'loc_hab_block_vermin'
        }, 'intro_e2e')
        res_intro = run_event(world, intro, render=False)
        trial_id = res_intro['outcomes']['threat_id']

        # Move to garden
        move = self.event(world, {
            'type': 'move',
            'actor_id': 'player_vane',
            'location_id': 'loc_hab_block_vermin'
        }, 'move_e2e')
        run_event(world, move, render=False)

        # Resolve trial
        res = self.event(world, {
            'type': 'resolve_trial',
            'actor_id': 'player_vane',
            'trial_id': trial_id,
            'recipe_id': 'recipe_crystal_garden_repair'
        }, 'resolve_e2e')
        run_event(world, res, render=False)

        final_snapshot = read_snapshot(world)
        final_clock = final_snapshot['clock']['data']
        # 3 turns elapsed: 37 -> 40
        self.assertEqual(40, final_clock['turn'])
        self.assertEqual(9, final_clock['day'])
        self.assertEqual('41.999.059.M41 · Day 9 · Watch 4', final_clock['display_timestamp'])
        self.assertFalse(final_snapshot['threats'][trial_id]['data']['active'])
        self.assertIn('trait_adaptable_spirit', final_snapshot['characters']['player_vane']['data']['traits'])
