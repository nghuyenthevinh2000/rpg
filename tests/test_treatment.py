"""Resource-backed healing and gated restoration tests in authored temporary baselines."""
import json
from world_fixtures import TemporaryWorldCase, ROOT, hashes
from engine.contracts import RuleError, WorldContract
from engine.runner import read_snapshot, run_event


class TreatmentTests(TemporaryWorldCase):
    def treatment_world(self, restoration_enabled=False):
        world = self.make_world('warhammer-40k')
        # Configure healing recipes in engine_rules.json
        def edit_rules(rules):
            rules['treatment_recipes'] = {
                'field_medication': {
                    'resource_id': 'med_supply',
                    'resource_cost': 1,
                    'heal_amount': 25,
                    'health_ceiling': 100
                }
            }
            if restoration_enabled:
                rules['restoration_policy'] = {
                    'enabled': True,
                    'resource_id': 'primordial_life_restoration',
                    'resource_cost': 1,
                    'restore_health': 100
                }
            else:
                rules['restoration_policy'] = {'enabled': False}
        self.edit_rules(world, edit_rules)

        def author(state):
            # Living co-located actor/target:
            # actor: player_vane at loc_shrine_aquila (living, immortal)
            # target: npc_ogryn_bragg at loc_shrine_aquila (living, mortal, health 40)
            bragg = state['characters']['npc_ogryn_bragg']['data']
            bragg['status'] = 'alive'
            bragg['health'] = 40
            bragg['location_id'] = 'loc_shrine_aquila'

            # Resource: med_supply quantity 1
            state['resources']['med_supply'] = {
                'id': 'med_supply',
                'revision': 0,
                'schema_version': 1,
                'data': {'name': 'Med Supply', 'quantity': 1}
            }

        return self.author_state(world, author, 'treat_world')

    def test_heal_consumes_stock_and_changes_health_atomically(self):
        world = self.treatment_world()
        run_event(world, self.event(world, {'type':'heal', 'actor_id':'player_vane',
            'target_id':'npc_ogryn_bragg', 'recipe_id':'field_medication'}), render=False)
        state = read_snapshot(world)
        self.assertEqual(65, state['characters']['npc_ogryn_bragg']['data']['health'])
        self.assertEqual(0, state['resources']['med_supply']['data']['quantity'])

    def test_heal_clamps_to_ceiling_without_lowering_higher_health(self):
        world = self.treatment_world()
        # Set bragg health to 90 (amount 25 would go to 115, clamp to 100)
        def set_90(state):
            state['characters']['npc_ogryn_bragg']['data']['health'] = 90
        w90 = self.author_state(world, set_90, 'hp_90')
        run_event(w90, self.event(w90, {'type':'heal', 'actor_id':'player_vane',
            'target_id':'npc_ogryn_bragg', 'recipe_id':'field_medication'}), render=False)
        s90 = read_snapshot(w90)
        self.assertEqual(100, s90['characters']['npc_ogryn_bragg']['data']['health'])
        self.assertEqual(0, s90['resources']['med_supply']['data']['quantity'])

        # If already higher than ceiling (e.g. 110), do not heal or lower health, reject as full-health/no-op
        self.tmp.cleanup(); self.setUp()
        world2 = self.treatment_world()
        def set_110(state):
            state['characters']['npc_ogryn_bragg']['data']['health'] = 110
        w110 = self.author_state(world2, set_110, 'hp_110')
        with self.assertRaises(RuleError):
            run_event(w110, self.event(w110, {'type':'heal', 'actor_id':'player_vane',
                'target_id':'npc_ogryn_bragg', 'recipe_id':'field_medication'}), render=False)

    def test_heal_rejects_missing_stock_dead_remote_null_health_and_immortal(self):
        world = self.treatment_world()
        # Missing stock (med_supply = 0)
        def no_stock(state):
            state['resources']['med_supply']['data']['quantity'] = 0
        w_nostock = self.author_state(world, no_stock, 'no_stock')
        with self.assertRaises(RuleError):
            run_event(w_nostock, self.event(w_nostock, {'type':'heal', 'actor_id':'player_vane',
                'target_id':'npc_ogryn_bragg', 'recipe_id':'field_medication'}), render=False)

        # Dead target
        def dead_target(state):
            d = state['characters']['npc_ogryn_bragg']['data']
            d['status'] = 'dead'
            d['health'] = 0
        w_dead = self.author_state(world, dead_target, 'dead_target')
        with self.assertRaises(RuleError):
            run_event(w_dead, self.event(w_dead, {'type':'heal', 'actor_id':'player_vane',
                'target_id':'npc_ogryn_bragg', 'recipe_id':'field_medication'}), render=False)

        # Remote target
        def remote_target(state):
            state['characters']['npc_ogryn_bragg']['data']['location_id'] = 'loc_ancient_ruined_city'
        w_remote = self.author_state(world, remote_target, 'remote_target')
        with self.assertRaises(RuleError):
            run_event(w_remote, self.event(w_remote, {'type':'heal', 'actor_id':'player_vane',
                'target_id':'npc_ogryn_bragg', 'recipe_id':'field_medication'}), render=False)

        # Full health target (health == ceiling 100)
        def full_hp(state):
            state['characters']['npc_ogryn_bragg']['data']['health'] = 100
        w_full = self.author_state(world, full_hp, 'full_hp')
        with self.assertRaises(RuleError):
            run_event(w_full, self.event(w_full, {'type':'heal', 'actor_id':'player_vane',
                'target_id':'npc_ogryn_bragg', 'recipe_id':'field_medication'}), render=False)

        # Immortal target (never treats immortal sentinel as a number or heals immortal)
        with self.assertRaises(RuleError):
            run_event(world, self.event(world, {'type':'heal', 'actor_id':'player_vane',
                'target_id':'player_vane', 'recipe_id':'field_medication'}), render=False)

    def test_restore_life_success_when_enabled(self):
        world = self.treatment_world(restoration_enabled=True)
        # Dead target co-located with living immortal actor player_vane
        def prep_dead(state):
            d = state['characters']['npc_ogryn_bragg']['data']
            d['status'] = 'dead'
            d['health'] = 0
            d['location_id'] = 'loc_shrine_aquila'
            # Ensure primordial_life_restoration resource exists with quantity 1
            state['resources']['primordial_life_restoration'] = {
                'id': 'primordial_life_restoration',
                'revision': 0,
                'schema_version': 1,
                'data': {'name': 'Primordial Life Restoration', 'quantity': 1}
            }
        w_dead = self.author_state(world, prep_dead, 'restore_dead')
        run_event(w_dead, self.event(w_dead, {'type':'restore_life', 'actor_id':'player_vane',
            'target_id':'npc_ogryn_bragg'}), render=False)
        state = read_snapshot(w_dead)
        bragg = state['characters']['npc_ogryn_bragg']['data']
        self.assertEqual('alive', bragg['status'])
        self.assertEqual(100, bragg['health'])
        # Retains existing capability: cannot_die is still False
        self.assertFalse(bragg['capabilities']['cannot_die'])
        # Consumes one primordial_life_restoration
        self.assertEqual(0, state['resources']['primordial_life_restoration']['data']['quantity'])

    def test_restore_life_rejected_when_disabled_or_wrong_actor_or_live_target(self):
        world = self.treatment_world(restoration_enabled=False)
        def prep_res(state):
            d = state['characters']['npc_ogryn_bragg']['data']
            d['status'] = 'dead'
            d['health'] = 0
            d['location_id'] = 'loc_shrine_aquila'
            state['resources']['primordial_life_restoration'] = {
                'id': 'primordial_life_restoration',
                'revision': 0,
                'schema_version': 1,
                'data': {'name': 'Primordial Life Restoration', 'quantity': 1}
            }
        w = self.author_state(world, prep_res, 'disabled_res')
        # Disabled policy rejects
        with self.assertRaises(RuleError):
            run_event(w, self.event(w, {'type':'restore_life', 'actor_id':'player_vane',
                'target_id':'npc_ogryn_bragg'}), render=False)

        # Enable policy, but mortal actor tries to restore
        self.tmp.cleanup(); self.setUp()
        world_en = self.treatment_world(restoration_enabled=True)
        def mortal_actor(state):
            prep_res(state)
            state['characters']['player_vane']['data']['capabilities']['cannot_die'] = False
        w_mortal = self.author_state(world_en, mortal_actor, 'mortal_actor')
        with self.assertRaises(RuleError):
            run_event(w_mortal, self.event(w_mortal, {'type':'restore_life', 'actor_id':'player_vane',
                'target_id':'npc_ogryn_bragg'}), render=False)

        # Already living target rejects
        self.tmp.cleanup(); self.setUp()
        world_live = self.treatment_world(restoration_enabled=True)
        def live_target(state):
            state['resources']['primordial_life_restoration'] = {
                'id': 'primordial_life_restoration',
                'revision': 0,
                'schema_version': 1,
                'data': {'name': 'Primordial Life Restoration', 'quantity': 1}
            }
        w_live = self.author_state(world_live, live_target, 'live_target')
        with self.assertRaises(RuleError):
            run_event(w_live, self.event(w_live, {'type':'restore_life', 'actor_id':'player_vane',
                'target_id':'npc_ogryn_bragg'}), render=False)

    def test_lost_world_rejects_treatment_and_restoration(self):
        world = self.make_world('lost-world')
        with self.assertRaises(RuleError):
            run_event(world, self.event(world, {'type':'heal', 'actor_id':'player_kael',
                'target_id':'npc_marcus_the_drifter', 'recipe_id':'med'}), render=False)
        with self.assertRaises(RuleError):
            run_event(world, self.event(world, {'type':'restore_life', 'actor_id':'player_kael',
                'target_id':'npc_marcus_the_drifter'}), render=False)
