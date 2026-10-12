"""Named-participant combat and group casualties in authored combat fixtures."""
import json
from world_fixtures import TemporaryWorldCase, ROOT, hashes
from engine.contracts import RuleError, WorldContract, RuleContext, StateView
from engine.runner import read_snapshot, run_event


class GroupCombatTests(TemporaryWorldCase):
    def group_combat_world(self, sanctuary=False):
        world = self.make_world('warhammer-40k')
        if not sanctuary:
            self.edit_rules(world, lambda rules: rules.update(sanctuary=False))
            def edit_lore(state_dict):
                pass
            lore_path = world / 'definitions/world.json'
            lore = json.loads(lore_path.read_text())
            lore['structural_rules']['transcendent_sanctuary'] = False
            lore_path.write_text(json.dumps(lore, indent=2, allow_nan=False) + '\n')

        def author(state):
            # Two living co-located heroes at loc_shrine_aquila, 100 health each, zero armor
            # player_vane: mortal hp 100, remove armor and weapons except item_chainsword_mk7
            vane = state['characters']['player_vane']['data']
            vane['capabilities']['cannot_die'] = False
            vane['health'] = 100
            vane['equipment'] = ['item_chainsword_mk7']
            vane['inventory'] = ['item_chainsword_mk7']

            # npc_ogryn_bragg: living, health 100, remove armor, keep equipped melee item_power_fist
            bragg = state['characters']['npc_ogryn_bragg']['data']
            bragg['status'] = 'alive'
            bragg['health'] = 100
            bragg['location_id'] = 'loc_shrine_aquila'
            bragg['equipment'] = ['item_power_fist']

            # Squad group at loc_shrine_aquila with count 3, members vane and bragg
            state['groups']['squad'] = {
                'id': 'squad',
                'revision': 0,
                'schema_version': 1,
                'data': {
                    'name': 'Assault Squad',
                    'location_id': 'loc_shrine_aquila',
                    'count': 3,
                    'members': ['player_vane', 'npc_ogryn_bragg']
                }
            }

            # Enemy threat at loc_shrine_aquila with health 1000, retaliation 60, armor 0
            state['threats']['enemy'] = {
                'id': 'enemy',
                'revision': 0,
                'schema_version': 1,
                'data': {
                    'name': 'Enemy Threat',
                    'location_id': 'loc_shrine_aquila',
                    'active': True,
                    'activation_turn': 37,
                    'tags': ['hostile'],
                    'stats': {'health': 1000, 'armor': 0, 'retaliation': 60},
                    'metadata': {}
                }
            }

        return self.author_state(world, author, 'grp_combat')

    def group_attack(self, world, **extra):
        action = {
            'type': 'attack',
            'actor_id': 'player_vane',
            'target_id': 'enemy',
            'weapon_id': 'item_chainsword_mk7',
            'participant_ids': ['player_vane', 'npc_ogryn_bragg'],
            'group_id': 'squad',
            'stance': 'neutral',
            **extra
        }
        return self.event(world, action)

    def test_one_retaliation_pool_and_bounded_group_casualties(self):
        world = self.group_combat_world()
        report = run_event(world, self.group_attack(world), render=False)
        self.assertEqual(1, report['outcomes']['retaliations'])
        self.assertEqual(30, report['outcomes']['injuries']['player_vane']['damage'])
        self.assertEqual(30, report['outcomes']['injuries']['npc_ogryn_bragg']['damage'])
        self.assertEqual(0, read_snapshot(world)['groups']['squad']['data']['count'])
        self.assertEqual(3, report['outcomes']['casualties'])

    def test_killing_blow_still_retaliates_once(self):
        world = self.group_combat_world()
        # Set enemy health low so it dies in one attack
        def low_hp(state):
            state['threats']['enemy']['data']['stats']['health'] = 1
        world = self.author_state(world, low_hp, 'low_hp')
        report = run_event(world, self.group_attack(world), render=False)
        state = read_snapshot(world)
        self.assertFalse(state['threats']['enemy']['data']['active'])
        self.assertEqual(0, state['threats']['enemy']['data']['stats']['health'])
        self.assertEqual(1, report['outcomes']['retaliations'])
        self.assertEqual(70, state['characters']['player_vane']['data']['health'])

    def test_stances_defensive_and_aggressive_multipliers(self):
        # Defensive cover: outgoing * 0.8, incoming * 0.65
        world_def = self.group_combat_world()
        rep_def = run_event(world_def, self.group_attack(world_def, stance='defensive_cover'), render=False)
        # 60 pool / 2 = 30 * 0.65 = 19.5
        self.assertEqual(19.5, rep_def['outcomes']['injuries']['player_vane']['damage'])

        # Aggressive assault: outgoing * 1.15, incoming * 1.25
        self.tmp.cleanup(); self.setUp()
        world_agg = self.group_combat_world()
        rep_agg = run_event(world_agg, self.group_attack(world_agg, stance='aggressive_assault'), render=False)
        # 60 pool / 2 = 30 * 1.25 = 37.5
        self.assertEqual(37.5, rep_agg['outcomes']['injuries']['player_vane']['damage'])
        # Compare outgoing damage
        self.assertGreater(rep_agg['outcomes']['damage_dealt'], rep_def['outcomes']['damage_dealt'])

    def test_invalid_participants_and_caller_supplied_stats_rejected(self):
        world = self.group_combat_world()
        # Dead participant
        def dead_p(state):
            state['characters']['npc_ogryn_bragg']['data']['status'] = 'dead'
            state['characters']['npc_ogryn_bragg']['data']['health'] = 0
        w_dead = self.author_state(world, dead_p, 'dead_p')
        with self.assertRaises(RuleError):
            run_event(w_dead, self.group_attack(w_dead), render=False)

        # Remote participant
        def remote_p(state):
            state['characters']['npc_ogryn_bragg']['data']['location_id'] = 'loc_ancient_ruined_city'
        w_remote = self.author_state(world, remote_p, 'remote_p')
        with self.assertRaises(RuleError):
            run_event(w_remote, self.group_attack(w_remote), render=False)

        # Duplicate participant
        with self.assertRaises(RuleError):
            run_event(world, self.group_attack(world, participant_ids=['player_vane', 'player_vane']), render=False)

        # Actor not in participants
        with self.assertRaises(RuleError):
            run_event(world, self.group_attack(world, participant_ids=['npc_ogryn_bragg']), render=False)

        # Caller-supplied stats or damage in action payload rejected
        with self.assertRaises(RuleError):
            run_event(world, self.group_attack(world, damage=999), render=False)
        with self.assertRaises(RuleError):
            run_event(world, self.group_attack(world, armor=1.0), render=False)
        with self.assertRaises(RuleError):
            run_event(world, self.group_attack(world, casualties=0), render=False)

    def test_sanctuary_rejects_before_any_cost(self):
        world = self.group_combat_world(sanctuary=True)
        before = read_snapshot(world)
        with self.assertRaises(RuleError):
            run_event(world, self.group_attack(world), render=False)
        self.assertEqual(before, read_snapshot(world))

    def test_zero_count_or_depleted_group_rejected(self):
        world = self.group_combat_world()
        def zero_grp(state):
            state['groups']['squad']['data']['count'] = 0
        w_zero = self.author_state(world, zero_grp, 'zero_grp')
        with self.assertRaises(RuleError):
            run_event(w_zero, self.group_attack(w_zero), render=False)

    def test_immortal_immunity_in_group_combat(self):
        world = self.group_combat_world()
        def set_immortal(state):
            state['characters']['player_vane']['data']['capabilities']['cannot_die'] = True
        w_imm = self.author_state(world, set_immortal, 'immortal_grp')
        report = run_event(w_imm, self.group_attack(w_imm), render=False)
        state = read_snapshot(w_imm)
        self.assertEqual(100, state['characters']['player_vane']['data']['health'])
        self.assertEqual(70, state['characters']['npc_ogryn_bragg']['data']['health'])

    def test_companion_with_only_ranged_ammo_weapon_rejected(self):
        world = self.group_combat_world()
        def lasgun_companion(state):
            # Give bragg only item_lasgun_kantrael (ammo-backed ranged weapon)
            bragg = state['characters']['npc_ogryn_bragg']['data']
            bragg['equipment'] = ['item_lasgun_kantrael']
        w = self.author_state(world, lasgun_companion, 'lasgun_companion')
        before = read_snapshot(w)
        with self.assertRaises(RuleError) as err:
            run_event(w, self.group_attack(w), render=False)
        self.assertEqual('companion_weapon', err.exception.code)
        self.assertEqual(before, read_snapshot(w))

    def test_group_with_nonexistent_member_rejected(self):
        world = self.group_combat_world()
        def bad_group_member(state):
            state['groups']['squad']['data']['members'] = ['player_vane', 'nonexistent_character']
        w = self.author_state(world, bad_group_member, 'bad_group')
        before = read_snapshot(w)
        with self.assertRaises(RuleError) as err:
            run_event(w, self.group_attack(w), render=False)
        self.assertEqual('invalid_group', err.exception.code)
        self.assertEqual(before, read_snapshot(w))

    def test_actor_ranged_attack_debits_ammunition_once(self):
        world = self.group_combat_world()
        def actor_ranged(state):
            vane = state['characters']['player_vane']['data']
            vane['equipment'] = ['item_lasgun_kantrael']
            state['resources']['lasgun_charge_packs'] = {
                'id': 'lasgun_charge_packs',
                'revision': 0,
                'schema_version': 1,
                'data': {'name': 'Lasgun Charge Packs', 'quantity': 10}
            }
        w = self.author_state(world, actor_ranged, 'actor_ranged')
        # Actor attacks with lasgun and ammo
        event = self.event(w, {
            'type': 'attack',
            'actor_id': 'player_vane',
            'target_id': 'enemy',
            'weapon_id': 'item_lasgun_kantrael',
            'resource_id': 'lasgun_charge_packs',
            'participant_ids': ['player_vane', 'npc_ogryn_bragg'],
            'group_id': 'squad',
            'stance': 'neutral'
        })
        run_event(w, event, render=False)
        s = read_snapshot(w)
        # Ammunition debited once: 10 - 1 = 9
        self.assertEqual(9, s['resources']['lasgun_charge_packs']['data']['quantity'])
