"""Composed acceptance flows, outcome rendering, replay, and recovery across all mechanics."""
import json
from unittest.mock import patch
from engine.contracts import RuleError, WorldContract
from engine.runner import read_snapshot, run_event, replay_event
from engine.render_map import render_map
from engine.state_store import StateStore
from world_fixtures import TemporaryWorldCase


class RemainingMechanicsIntegrationTests(TemporaryWorldCase):
    def test_project_display_uses_committed_fulfillment(self):
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

        # Add HTML-bearing name to template to verify safe escaping
        self.edit_rules(world, lambda rules: rules['project_templates']['action_build_structure'].update({
            'name': 'Erect <script>monastery</script>'
        }))

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
        self.assertIn('&lt;script&gt;monastery&lt;/script&gt;', html)
        self.assertNotIn('<script>monastery</script>', html)

    def test_render_outcomes_and_stale_detection(self):
        world = self.make_world('warhammer-40k')
        # 1. Baseline-only rendering has no fabricated outcomes
        render_map(world)
        base_html = (world / 'map.html').read_text()
        self.assertNotIn('Last Event Outcomes', base_html)

        # 2. Run a trial resolution event with HTML in narrative
        intro = self.event(world, {
            'type': 'introduce_threat',
            'template_id': 'event_crystal_garden_repair',
            'location_id': 'loc_hab_block_vermin'
        }, 'intro_rnd')
        run_event(world, intro, render=True)
        intro_html = (world / 'map.html').read_text()
        self.assertIn('Trials and Opportunities', intro_html)

        run_event(world, self.event(world, {'type': 'move', 'actor_id': 'player_vane', 'location_id': 'loc_hab_block_vermin'}, 'mv_rnd'), render=False)

        stale_snap = read_snapshot(world)
        resolve_ev = self.event(world, {
            'type': 'resolve_trial',
            'actor_id': 'player_vane',
            'trial_id': 'intro_rnd',
            'recipe_id': 'recipe_crystal_garden_repair'
        }, 'res_rnd')
        resolve_ev['narrative'] = 'Restoring <script>alert("flora")</script>'
        run_event(world, resolve_ev, render=True)

        post_html = (world / 'map.html').read_text()
        self.assertIn('Last Event Outcomes', post_html)
        self.assertIn('&lt;script&gt;alert(&quot;flora&quot;)&lt;/script&gt;', post_html)
        self.assertNotIn('<script>alert("flora")</script>', post_html)
        self.assertIn('Trial Resolved: intro_rnd', post_html)

        # 3. Independent render produces identical outcomes receipt
        render_map(world)
        retry_html = (world / 'map.html').read_text()
        self.assertIn('Last Event Outcomes', retry_html)
        self.assertIn('Trial Resolved: intro_rnd', retry_html)

        # 4. Stale snapshot fails stale_render
        with self.assertRaises(RuleError) as err:
            render_map(world, snapshot=stale_snap)
        self.assertEqual('stale_render', err.exception.code)

        # 5. Supplied receipt with mismatching after-images is omitted from outcomes display
        latest_snap = read_snapshot(world)
        import copy
        bad_receipt = copy.deepcopy(resolve_ev)
        bad_event_report = {
            'event': bad_receipt,
            'turn': {'after': latest_snap['clock']['data']['turn']},
            'outcomes': {'trial_id': 'mismatch_trial', 'resolved_by': 'player_vane'},
            'changes': {
                'characters/player_vane': {
                    'after': {'fake_mismatch': True}
                }
            }
        }
        render_map(world, committed_event=bad_event_report, snapshot=latest_snap)
        mismatch_html = (world / 'map.html').read_text()
        self.assertNotIn('mismatch_trial', mismatch_html)

        # 6. Periodic resource outcomes rendered when list of records
        list_receipt = {
            'event': bad_receipt,
            'turn': {'after': latest_snap['clock']['data']['turn']},
            'outcomes': {
                'resources': [{'resource_id': 'crystalline_spring_water', 'before': 50, 'after': 45}]
            },
            'changes': {}
        }
        render_map(world, committed_event=list_receipt, snapshot=latest_snap)
        list_html = (world / 'map.html').read_text()
        self.assertIn('Last Event Outcomes', list_html)
        self.assertIn('crystalline_spring_water', list_html)

        # 7. Incomplete receipt (outcomes only, no turn or changes) is omitted
        incomplete_receipt = {
            'outcomes': {'trial_id': 'incomplete_trial', 'resolved_by': 'player_vane'}
        }
        render_map(world, committed_event=incomplete_receipt, snapshot=latest_snap)
        incomplete_html = (world / 'map.html').read_text()
        self.assertNotIn('incomplete_trial', incomplete_html)

    def test_composed_peaceful_production_project_trial_calendar_flow(self):
        world = self.make_world('lost-world')
        # Setup small project & trial flow
        def author_lw(state):
            state['actions'] = {}
            for identity in ('player_kael', 'npc_marcus_the_drifter'):
                data = state['characters'][identity]['data']
                data.update(status='alive', health=100, location_id='loc_monastery')
            if 'trait_unyielding_survival' in state['characters']['player_kael']['data']['traits']:
                state['characters']['player_kael']['data']['traits'].remove('trait_unyielding_survival')
            state['resources']['raw_cedar_timber'] = {
                'id': 'raw_cedar_timber', 'revision': 0, 'schema_version': 1,
                'data': {'name': 'Timber', 'quantity': 10, 'capacity': 100}
            }
            state['resources']['quarried_granite_slabs'] = {
                'id': 'quarried_granite_slabs', 'revision': 0, 'schema_version': 1,
                'data': {'name': 'Granite', 'quantity': 25, 'capacity': 100}
            }
        world = self.author_state(world, author_lw, 'lw_composed')

        # Fast 2-hour project with trait reward
        self.edit_rules(world, lambda rules: rules['project_templates'].update({
            'action_quick_hut': {
                'name': 'Quick Hut',
                'hours_required': 2,
                'materials': {'raw_cedar_timber': 2},
                'credit_cost': 0,
                'credit_stat': None,
                'fatigue_cost': 0,
                'conditions': [],
                'site_ids': ['loc_monastery'],
                'structural_requirements': {},
                'resource_rewards': {},
                'trait_rewards': ['trait_unyielding_survival']
            }
        }))
        self.edit_rules(world, lambda rules: rules['project_sites']['loc_monastery']['template_ids'].append('action_quick_hut'))

        start_turn = read_snapshot(world)['clock']['data']['turn']

        # 1. Start project (turn 33 -> 34)
        run_event(world, self.event(world, {
            'type': 'start_project', 'actor_id': 'player_kael',
            'template_id': 'action_quick_hut', 'project_id': 'hut_1',
            'participant_ids': ['player_kael', 'npc_marcus_the_drifter']
        }, 'ev_start'), render=False)
        self.assertEqual(start_turn + 1, read_snapshot(world)['clock']['data']['turn'])

        # 2. Deliver materials (turn 34 -> 35)
        run_event(world, self.event(world, {
            'type': 'deliver_materials', 'actor_id': 'player_kael',
            'project_id': 'hut_1', 'resource_id': 'raw_cedar_timber', 'quantity': 2
        }, 'ev_mat'), render=False)
        self.assertEqual(8, read_snapshot(world)['resources']['raw_cedar_timber']['data']['quantity'])

        # 3. Work project (2 workers = 2 hours, turn 35 -> 36)
        run_event(world, self.event(world, {
            'type': 'work_project', 'actor_id': 'player_kael',
            'project_id': 'hut_1'
        }, 'ev_work'), render=False)

        # 4. Complete project and earn trait (turn 36 -> 37)
        run_event(world, self.event(world, {
            'type': 'complete_project', 'actor_id': 'player_kael',
            'project_id': 'hut_1'
        }, 'ev_comp'), render=False)
        snap4 = read_snapshot(world)
        self.assertIn('trait_unyielding_survival', snap4['characters']['player_kael']['data']['traits'])

        # 5. Peaceful trial introduction (turn 37 -> 38)
        intro = self.event(world, {
            'type': 'introduce_threat',
            'template_id': 'event_sudden_unregulated_squall',
            'location_id': 'loc_monastery'
        }, 'ev_intro')
        run_event(world, intro, render=False)

        # 6. Resolve trial (turn 38 -> 39)
        resolve_ev = self.event(world, {
            'type': 'resolve_trial',
            'actor_id': 'player_kael',
            'trial_id': 'ev_intro',
            'recipe_id': 'recipe_sudden_unregulated_squall'
        }, 'ev_res')
        run_event(world, resolve_ev, render=False)

        mid = read_snapshot(world)
        self.assertEqual(start_turn + 6, mid['clock']['data']['turn'])
        self.assertFalse(mid['threats']['ev_intro']['data']['active'])

        # 7. Production action: produce lumber from timber
        self.edit_rules(world, lambda rules: rules['resource_recipes'].update({
            'recipe_craft_planks': {
                'location_id': 'loc_monastery',
                'inputs': {'raw_cedar_timber': 2},
                'outputs': {'quarried_granite_slabs': 1},
                'health_cost': 5
            }
        }))
        produce_ev = self.event(world, {
            'type': 'produce',
            'actor_id': 'player_kael',
            'recipe_id': 'recipe_craft_planks'
        }, 'ev_prod')
        run_event(world, produce_ev, render=False)
        snap_prod = read_snapshot(world)
        self.assertEqual(start_turn + 7, snap_prod['clock']['data']['turn'])  # turn 40
        self.assertEqual(6, snap_prod['resources']['raw_cedar_timber']['data']['quantity'])
        self.assertEqual(26, snap_prod['resources']['quarried_granite_slabs']['data']['quantity'])

        # 8. Advance turns across the 24-hour day rollover boundary (day 4 -> day 5 at turn 57, advance to 58)
        current_t = snap_prod['clock']['data']['turn']
        turns_to_advance = 58 - current_t
        for i in range(turns_to_advance):
            run_event(world, self.event(world, {'type': 'wait', 'actor_id': 'player_kael'}, f'wait_roll_{i}'), render=False)

        final = read_snapshot(world)
        self.assertEqual(58, final['clock']['data']['turn'])
        self.assertEqual(5, final['clock']['data']['day'])
        self.assertEqual('2026-10-10T08:30:00+07:00', final['clock']['data']['display_timestamp'])

    def test_composed_combat_equip_heal_restoration_flow(self):
        world = self.make_world('warhammer-40k')
        # Author combat-enabled temporary copy
        self.edit_rules(world, lambda rules: rules.update(sanctuary=False))
        lore_path = world / 'definitions/world.json'
        lore = json.loads(lore_path.read_text())
        lore['structural_rules']['transcendent_sanctuary'] = False
        lore_path.write_text(json.dumps(lore, indent=2) + '\n')

        # Configure treatment and restoration recipes
        self.edit_rules(world, lambda rules: rules.update({
            'treatment_recipes': {
                'field_medication': {
                    'resource_id': 'med_kit',
                    'resource_cost': 1,
                    'heal_amount': 30,
                    'health_ceiling': 100
                }
            },
            'restoration_policy': {
                'enabled': True,
                'resource_id': 'primordial_life_restoration',
                'resource_cost': 1,
                'restore_health': 100
            }
        }))

        def author_state_fn(state):
            # Living immortal player_vane at loc_shrine_aquila
            vane = state['characters']['player_vane']['data']
            vane['capabilities']['cannot_die'] = True
            vane['health'] = 100
            vane['location_id'] = 'loc_shrine_aquila'
            vane['inventory'].append('item_void_relic_blade')
            if 'item_void_relic_blade' in vane['equipment']:
                vane['equipment'].remove('item_void_relic_blade')

            # Living mortal bragg at loc_shrine_aquila with melee weapon
            bragg = state['characters']['npc_ogryn_bragg']['data']
            bragg['status'] = 'alive'
            bragg['health'] = 100
            bragg['capabilities']['cannot_die'] = False
            bragg['location_id'] = 'loc_shrine_aquila'
            bragg['equipment'] = ['item_power_fist']

            # Third mortal jax at loc_shrine_aquila (starts dead for restoration test)
            jax = state['characters']['npc_trooper_jax']['data']
            jax['status'] = 'dead'
            jax['health'] = 0
            jax['capabilities']['cannot_die'] = False
            jax['location_id'] = 'loc_shrine_aquila'

            # Deployed squad group
            state['groups']['garrison'] = {
                'id': 'garrison', 'revision': 0, 'schema_version': 1,
                'data': {'name': 'Garrison', 'location_id': 'loc_shrine_aquila', 'count': 5, 'members': ['player_vane', 'npc_ogryn_bragg']}
            }

            # Threat
            state['threats']['horror'] = {
                'id': 'horror', 'revision': 0, 'schema_version': 1,
                'data': {'name': 'Horror', 'location_id': 'loc_shrine_aquila', 'active': True, 'activation_turn': 0,
                         'tags': ['hostile'], 'stats': {'health': 500, 'armor': 0, 'retaliation': 40}, 'metadata': {}}
            }

            # Resources
            state['resources']['med_kit'] = {
                'id': 'med_kit', 'revision': 0, 'schema_version': 1,
                'data': {'name': 'Med Kit', 'quantity': 5}
            }
            state['resources']['primordial_life_restoration'] = {
                'id': 'primordial_life_restoration', 'revision': 0, 'schema_version': 1,
                'data': {'name': 'Life Restoration', 'quantity': 1}
            }
        w = self.author_state(world, author_state_fn, 'combat_flow')

        # 1. Equip weapon
        run_event(w, self.event(w, {
            'type': 'equip', 'actor_id': 'player_vane', 'item_id': 'item_void_relic_blade'
        }, 'ev_equip'), render=False)

        # 2. Combat attack with participants and group
        atk_rep = run_event(w, self.event(w, {
            'type': 'attack', 'actor_id': 'player_vane', 'target_id': 'horror',
            'weapon_id': 'item_void_relic_blade', 'participant_ids': ['player_vane', 'npc_ogryn_bragg'],
            'group_id': 'garrison', 'stance': 'neutral'
        }, 'ev_atk'), render=False)
        self.assertEqual(2, atk_rep['outcomes']['casualties'])
        # Bragg took damage: 40 pool / 2 = 20 damage -> health 80
        s_combat = read_snapshot(w)
        self.assertEqual(80, s_combat['characters']['npc_ogryn_bragg']['data']['health'])
        # Immortal vane health untouched
        self.assertEqual(100, s_combat['characters']['player_vane']['data']['health'])

        # 3. Heal bragg from 80 -> 100 using med_kit
        heal_rep = run_event(w, self.event(w, {
            'type': 'heal', 'actor_id': 'player_vane', 'target_id': 'npc_ogryn_bragg',
            'recipe_id': 'field_medication'
        }, 'ev_heal'), render=False)
        self.assertEqual(20, heal_rep['outcomes']['healed'])
        s_heal = read_snapshot(w)
        self.assertEqual(100, s_heal['characters']['npc_ogryn_bragg']['data']['health'])
        self.assertEqual(4, s_heal['resources']['med_kit']['data']['quantity'])

        # 4. Restore life to dead mortal jax
        rest_rep = run_event(w, self.event(w, {
            'type': 'restore_life', 'actor_id': 'player_vane', 'target_id': 'npc_trooper_jax'
        }, 'ev_rest'), render=False)
        self.assertEqual(100, rest_rep['outcomes']['restored_health'])
        s_rest = read_snapshot(w)
        jax_data = s_rest['characters']['npc_trooper_jax']['data']
        self.assertEqual('alive', jax_data['status'])
        self.assertEqual(100, jax_data['health'])
        self.assertFalse(jax_data['capabilities']['cannot_die'])
        self.assertEqual(0, s_rest['resources']['primordial_life_restoration']['data']['quantity'])

        # Re-restoring now-living jax rejects
        with self.assertRaises(RuleError):
            run_event(w, self.event(w, {
                'type': 'restore_life', 'actor_id': 'player_vane', 'target_id': 'npc_trooper_jax'
            }, 'ev_rest_again'), render=False)

        # 5. Combat-template regression: location-less hostile template introduction succeeds in combat-enabled world
        gm_pre = json.loads((w / 'definitions/gm-pre-sanctuary.json').read_text())
        (w / 'game_master.json').write_text(json.dumps(gm_pre))
        self.edit_rules(w, lambda rules: rules['templates'].update({
            'event_sump_mutant_breach': {
                'tags': ['hostile'],
                'stats': {'health': 120, 'armor': 0.2, 'retaliation': 25}
                # No location_id authored in template
            }
        }))
        intro_hostile = self.event(w, {
            'type': 'introduce_threat',
            'template_id': 'event_sump_mutant_breach',
            'location_id': 'loc_shrine_aquila'
        }, 'ev_intro_hostile')
        intro_rep = run_event(w, intro_hostile, render=False)
        self.assertEqual('ev_intro_hostile', intro_rep['outcomes']['threat_id'])
        s_hostile = read_snapshot(w)
        self.assertTrue(s_hostile['threats']['ev_intro_hostile']['data']['active'])
        self.assertEqual('loc_shrine_aquila', s_hostile['threats']['ev_intro_hostile']['data']['location_id'])

    def test_archived_effects_replay_and_interrupted_recovery(self):
        world = self.make_world('lost-world')
        twin = self.author_state(world, lambda s: None, 'twin-lw')
        ev = self.event(world, {'type': 'wait', 'actor_id': 'player_kael'})
        report = run_event(world, ev, render=False)

        # Exact replay into fresh twin matching baseline
        replay_event(twin, report, render=False)
        self.assertEqual(read_snapshot(world), read_snapshot(twin))

        # Interrupted recovery
        expected_snap = read_snapshot(world)
        expected = run_event(world, self.event(world, {'type': 'wait', 'actor_id': 'player_kael'}, 'rec_ev'), dry_run=True, render=False)
        expected_snap['clock'] = expected['changes']['clock']['after']

        with patch.object(StateStore, '_apply_images', side_effect=OSError('interrupted write')):
            with self.assertRaises(OSError):
                run_event(world, expected['event'], render=False)
        actual = read_snapshot(world)
        self.assertEqual(expected_snap, actual)
