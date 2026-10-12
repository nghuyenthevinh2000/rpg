"""Paid projects in authored temporary baselines, never live gameplay."""
from copy import deepcopy

from world_fixtures import TemporaryWorldCase, ROOT, hashes
from engine.contracts import RuleError, WorldContract
from engine.runner import read_snapshot, run_event


class ProjectsTests(TemporaryWorldCase):
    def project_world(self, name='lost-world'):
        world = self.make_world(name)
        def author(state):
            state['actions'] = {}
            if name == 'lost-world':
                for identity in ('player_kael', 'npc_marcus_the_drifter'):
                    data = state['characters'][identity]['data']
                    data.update(status='alive', health=100, location_id='loc_monastery')
                state['characters']['player_kael']['data']['stats']['universal_dividend_balance'] = 949999
                for identity, quantity in (('raw_cedar_timber', 40), ('quarried_granite_slabs', 25)):
                    state['resources'][identity] = {'id': identity, 'revision': 0, 'schema_version': 1,
                        'data': {'name': identity, 'quantity': quantity, 'capacity': quantity}}
        return self.author_state(world, author, 'project_' + name)

    def act(self, world, kind, **fields):
        actor = 'player_kael' if WorldContract(world, load_hooks=False).config['world_id'] == 'lost-world' else 'player_vane'
        action = {'type': kind, 'actor_id': actor, 'project_id': 'hall_1', **fields}
        return run_event(world, self.event(world, action, 'turn_' + str(read_snapshot(world)['clock']['data']['turn'])), render=False)

    def start(self, world):
        lost = WorldContract(world, load_hooks=False).config['world_id'] == 'lost-world'
        return self.act(world, 'start_project', template_id='action_build_structure' if lost else 'action_resonant_pylon_repair',
            participant_ids=['player_kael', 'npc_marcus_the_drifter'] if lost else ['player_vane'])

    def reject(self, world, kind, **fields):
        before = read_snapshot(world)
        with self.assertRaises(RuleError):
            self.act(world, kind, **fields)
        self.assertEqual(before, read_snapshot(world))

    def test_start_project_charges_cost_once(self):
        world = self.project_world()
        self.start(world)
        state = read_snapshot(world)
        self.assertEqual(899999, state['characters']['player_kael']['data']['stats']['universal_dividend_balance'])
        self.assertEqual(0, state['actions']['hall_1']['data']['hours_committed'])
        self.assertEqual({'telemetry_severed': False, 'drones_rejected': False}, state['actions']['hall_1']['data']['conditions'])
        self.reject(world, 'start_project', template_id='action_build_structure', participant_ids=['player_kael'])

    def test_deliver_40_cedar_and_two_workers(self):
        world = self.project_world(); self.start(world)
        self.act(world, 'deliver_materials', resource_id='raw_cedar_timber', quantity=40)
        self.act(world, 'work_project')
        state = read_snapshot(world)
        self.assertEqual(0, state['resources']['raw_cedar_timber']['data']['quantity'])
        self.assertEqual(40, state['actions']['hall_1']['data']['materials_committed']['raw_cedar_timber'])
        self.assertEqual(2, state['actions']['hall_1']['data']['hours_committed'])

    def test_full_completion_exactly_once(self):
        world = self.project_world(); self.start(world)
        for identity, amount in (('raw_cedar_timber', 40), ('quarried_granite_slabs', 25)):
            self.act(world, 'deliver_materials', resource_id=identity, quantity=amount)
        for recipe in ('sever_telemetry', 'reject_drones'):
            self.act(world, 'prepare_project_site', recipe_id=recipe)
        for _ in range(60):
            self.act(world, 'work_project')
        self.act(world, 'complete_project')
        self.assertTrue(read_snapshot(world)['actions']['hall_1']['data']['completed'])
        self.reject(world, 'complete_project')

    def test_atomic_invalid_conditions_overdelivery_and_repeat_preparation(self):
        world = self.project_world(); self.start(world)
        self.reject(world, 'complete_project')
        self.reject(world, 'deliver_materials', resource_id='raw_cedar_timber', quantity=41)
        for quantity in (True, 0, -1, float('inf'), float('nan')):
            self.reject(world, 'deliver_materials', resource_id='raw_cedar_timber', quantity=quantity)
        self.reject(world, 'prepare_project_site', recipe_id='sever_telemetry', telemetry_severed=True)
        self.reject(world, 'prepare_project_site', recipe_id='arbitrary')
        self.act(world, 'prepare_project_site', recipe_id='sever_telemetry')
        self.reject(world, 'prepare_project_site', recipe_id='sever_telemetry')

    def test_dead_remote_and_duplicate_participants(self):
        for mode in ('dead', 'remote', 'duplicate'):
            world = self.project_world()
            if mode != 'duplicate':
                def author(state):
                    data = state['characters']['npc_marcus_the_drifter']['data']
                    if mode == 'dead': data.update(status='dead', health=0)
                    else: data['location_id'] = 'loc_glass_atrium'
                world = self.author_state(world, author, mode)
            self.reject(world, 'start_project', template_id='action_build_structure',
                participant_ids=['player_kael', 'npc_marcus_the_drifter'] + (['player_kael'] if mode == 'duplicate' else []))
            # Reuse the helper with a distinct directory on the next iteration.
            self.tmp.cleanup(); self.setUp()

    def test_template_hash_changes_reject_all_project_actions(self):
        world = self.project_world(); self.start(world)
        self.edit_rules(world, lambda rules: rules['project_templates']['action_build_structure'].update(hours_required=121))
        for kind, fields in (('work_project', {}), ('complete_project', {}),
                ('deliver_materials', {'resource_id':'raw_cedar_timber', 'quantity':1}),
                ('prepare_project_site', {'recipe_id':'sever_telemetry'}),
                ('start_project', {'template_id':'action_build_structure', 'participant_ids':['player_kael']})):
            self.reject(world, kind, **fields)

    def test_historical_completed_monastery_prevents_duplicate(self):
        world = self.project_world()
        def author(state):
            state['actions']['action_build_structure'] = {'id':'action_build_structure', 'revision':0, 'schema_version':1,
                'data':{'type':'action_build_structure', 'completed':True, 'location_id':'loc_monastery'}}
        world = self.author_state(world, author, 'historical')
        self.reject(world, 'start_project', template_id='action_build_structure', participant_ids=['player_kael'])

    def test_peaceful_pylon_repair(self):
        world = self.project_world('warhammer-40k'); self.start(world)
        before = read_snapshot(world)['characters']['player_vane']['data']['health']
        self.act(world, 'deliver_materials', resource_id='resonant_crystal_pylons', quantity=2)
        for _ in range(12): self.act(world, 'work_project')
        self.act(world, 'complete_project')
        state = read_snapshot(world)
        self.assertEqual(before, state['characters']['player_vane']['data']['health'])
        self.assertEqual(48, state['resources']['resonant_crystal_pylons']['data']['quantity'])

    def test_actual_worlds_load_without_mutation(self):
        for name in ('lost-world', 'warhammer-40k'):
            world = ROOT / 'world' / name
            before = hashes(world / 'state')
            WorldContract(world)
            read_snapshot(world)
            self.assertEqual(before, hashes(world / 'state'))

    def test_project_completion_grants_earned_trait_rewards_both_worlds(self):
        for world_id in ('warhammer-40k', 'lost-world'):
            self.tmp.cleanup(); self.setUp()
            world = self.project_world(world_id)
            lost = world_id == 'lost-world'
            actor = 'player_kael' if lost else 'player_vane'
            tpl_id = 'action_build_structure' if lost else 'action_resonant_pylon_repair'
            reward_trait = 'trait_unyielding_survival' if lost else 'trait_iron_discipline'

            # Edit template to add trait_rewards
            self.edit_rules(world, lambda rules, tid=tpl_id, tr=reward_trait: rules['project_templates'][tid].update({
                'trait_rewards': [tr]
            }))

            self.start(world)
            before_hp = read_snapshot(world)['characters'][actor]['data']['health']
            before_base = read_snapshot(world)['characters'][actor]['data']['baseline']

            if lost:
                for identity, amount in (('raw_cedar_timber', 40), ('quarried_granite_slabs', 25)):
                    self.act(world, 'deliver_materials', resource_id=identity, quantity=amount)
                for recipe in ('sever_telemetry', 'reject_drones'):
                    self.act(world, 'prepare_project_site', recipe_id=recipe)
                for _ in range(60):
                    self.act(world, 'work_project')
            else:
                self.act(world, 'deliver_materials', resource_id='resonant_crystal_pylons', quantity=2)
                for _ in range(12):
                    self.act(world, 'work_project')

            self.act(world, 'complete_project')
            s_after = read_snapshot(world)
            actor_data = s_after['characters'][actor]['data']
            self.assertIn(reward_trait, actor_data['traits'])
            self.assertEqual(before_hp, actor_data['health'])
            self.assertEqual(before_base, actor_data['baseline'])
            self.assertTrue(s_after['actions']['hall_1']['data']['completed'])
            # Repeat completion rejected
            self.reject(world, 'complete_project')

    def test_project_template_missing_required_fields_with_trait_rewards(self):
        # A template containing trait_rewards but missing required fields (e.g. 'name')
        # must produce a structured rejection (project_config) instead of KeyError
        for world_id in ('warhammer-40k', 'lost-world'):
            self.tmp.cleanup(); self.setUp()
            world = self.project_world(world_id)
            actor = 'player_kael' if world_id == 'lost-world' else 'player_vane'
            self.edit_rules(world, lambda rules: rules['project_templates'].update({
                'action_incomplete': {
                    'hours_required': 10,
                    'trait_rewards': ['trait_unyielding_survival'] if world_id == 'lost-world' else ['trait_iron_discipline']
                    # missing name, materials, etc.
                }
            }))
            before = read_snapshot(world)
            with self.assertRaises(RuleError) as err:
                run_event(world, self.event(world, {'type': 'wait', 'actor_id': actor}), render=False)
            self.assertEqual('project_config', err.exception.code)
            self.assertEqual(before, read_snapshot(world))
