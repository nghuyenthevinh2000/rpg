"""Possession-aware equipment and audit tests in authored temporary baselines."""
import copy
from world_fixtures import TemporaryWorldCase, ROOT, hashes
from engine.contracts import RuleError, WorldContract, RuleContext, StateView
from engine.runner import read_snapshot, run_event


class InventoryTests(TemporaryWorldCase):
    def gear_world(self):
        world = self.make_world('warhammer-40k')
        def author(state):
            # Vane owns item_relic_blade_macragge in inventory and has no currently equipped melee weapon
            data = state['characters']['player_vane']['data']
            if 'item_void_relic_blade' in data['equipment']:
                data['equipment'].remove('item_void_relic_blade')
            if 'item_relic_blade_macragge' not in data['inventory']:
                data['inventory'].append('item_relic_blade_macragge')
        return self.author_state(world, author, 'gear_warhammer-40k')

    def test_equip_transfers_possession_without_healing(self):
        world = self.gear_world()
        before = read_snapshot(world)['characters']['player_vane']['data']['health']
        run_event(world, self.event(world, {'type':'equip', 'actor_id':'player_vane',
                                         'item_id':'item_relic_blade_macragge'}), render=False)
        data = read_snapshot(world)['characters']['player_vane']['data']
        self.assertIn('item_relic_blade_macragge', data['equipment'])
        self.assertNotIn('item_relic_blade_macragge', data['inventory'])
        self.assertEqual(before, data['health'])

    def test_unequip_transfers_possession_without_healing(self):
        world = self.gear_world()
        # Equip it first
        run_event(world, self.event(world, {'type':'equip', 'actor_id':'player_vane',
                                         'item_id':'item_relic_blade_macragge'}, 'event_equip'), render=False)
        before = read_snapshot(world)['characters']['player_vane']['data']['health']
        run_event(world, self.event(world, {'type':'unequip', 'actor_id':'player_vane',
                                         'item_id':'item_relic_blade_macragge'}, 'event_unequip'), render=False)
        data = read_snapshot(world)['characters']['player_vane']['data']
        self.assertNotIn('item_relic_blade_macragge', data['equipment'])
        self.assertIn('item_relic_blade_macragge', data['inventory'])
        self.assertEqual(before, data['health'])

    def test_equip_rejects_unpossessed_or_occupied_or_unknown_or_dead(self):
        world = self.gear_world()
        # Unpossessed item
        with self.assertRaises(RuleError):
            run_event(world, self.event(world, {'type':'equip', 'actor_id':'player_vane',
                                             'item_id':'item_chainsword_mk7'}), render=False)
        # Unknown item
        with self.assertRaises(RuleError):
            run_event(world, self.event(world, {'type':'equip', 'actor_id':'player_vane',
                                             'item_id':'item_fictional_weapon'}), render=False)
        # Equip relic blade (occupies melee_weapon slot)
        run_event(world, self.event(world, {'type':'equip', 'actor_id':'player_vane',
                                         'item_id':'item_relic_blade_macragge'}), render=False)
        # Adding another melee weapon to inventory and trying to equip into occupied slot
        def add_inv(state):
            state['characters']['player_vane']['data']['inventory'].append('item_chainsword_mk7')
        world = self.author_state(world, add_inv, 'occupied_slot')
        with self.assertRaises(RuleError):
            run_event(world, self.event(world, {'type':'equip', 'actor_id':'player_vane',
                                             'item_id':'item_chainsword_mk7'}), render=False)
        # Unequip twice
        run_event(world, self.event(world, {'type':'unequip', 'actor_id':'player_vane',
                                         'item_id':'item_relic_blade_macragge'}), render=False)
        with self.assertRaises(RuleError):
            run_event(world, self.event(world, {'type':'unequip', 'actor_id':'player_vane',
                                             'item_id':'item_relic_blade_macragge'}), render=False)
        # Dead actor
        def kill_actor(state):
            d = state['characters']['player_vane']['data']
            d['capabilities']['cannot_die'] = False
            d['status'] = 'dead'
            d['health'] = 0
        world = self.author_state(world, kill_actor, 'dead_actor')
        with self.assertRaises(RuleError):
            run_event(world, self.event(world, {'type':'equip', 'actor_id':'player_vane',
                                             'item_id':'item_relic_blade_macragge'}), render=False)

    def test_equip_unequip_cycle_restores_exact_stats(self):
        world = self.gear_world()
        c = WorldContract(world)
        s0 = read_snapshot(world)
        ctx0 = RuleContext(StateView(s0), c.definition_view, None, s0['clock']['data']['turn'])
        base_derive = c.derive(ctx0, 'characters/player_vane')

        run_event(world, self.event(world, {'type':'equip', 'actor_id':'player_vane',
                                         'item_id':'item_relic_blade_macragge'}, 'event_cycle_equip'), render=False)
        run_event(world, self.event(world, {'type':'unequip', 'actor_id':'player_vane',
                                         'item_id':'item_relic_blade_macragge'}, 'event_cycle_unequip'), render=False)
        s_end = read_snapshot(world)
        ctx_end = RuleContext(StateView(s_end), c.definition_view, None, s_end['clock']['data']['turn'])
        end_derive = c.derive(ctx_end, 'characters/player_vane')

        self.assertEqual(base_derive['stats'], end_derive['stats'])
        self.assertEqual(base_derive['health'], end_derive['health'])
        self.assertEqual(base_derive['punch_kinetic_impact'], end_derive['punch_kinetic_impact'])

    def test_lost_world_rejects_equip(self):
        world = self.make_world('lost-world')
        with self.assertRaises(RuleError):
            run_event(world, self.event(world, {'type':'equip', 'actor_id':'player_kael',
                                             'item_id':'item_cloak'}), render=False)

    def test_earned_trait_rewards_apply_once(self):
        import sys
        world = self.make_world('warhammer-40k')
        c = WorldContract(world)
        pkg_name = c.derive.__module__.rsplit('.', 1)[0]
        inv_mod = sys.modules[pkg_name + '.inventory']
        trait_reward_effects = inv_mod.trait_reward_effects
        s = read_snapshot(world)
        ctx = RuleContext(StateView(s), c.definition_view, None, s['clock']['data']['turn'])
        effects = trait_reward_effects(ctx, 'player_vane', ['trait_iron_discipline'])
        self.assertEqual(1, len(effects))
        self.assertIn('trait_iron_discipline', effects[0]['value'])
        # If already possessing trait, returns empty (cannot grant duplicate)
        def add_trait(state):
            state['characters']['player_vane']['data']['traits'].append('trait_iron_discipline')
        world = self.author_state(world, add_trait, 'has_trait')
        s2 = read_snapshot(world)
        ctx2 = RuleContext(StateView(s2), c.definition_view, None, s2['clock']['data']['turn'])
        effects2 = trait_reward_effects(ctx2, 'player_vane', ['trait_iron_discipline'])
        self.assertEqual([], effects2)

    def test_audit_character_exposes_breakdown_and_bounds_exceptions(self):
        world = ROOT / 'world/warhammer-40k'
        before_hashes = hashes(world / 'state')
        c = WorldContract(world)
        s = read_snapshot(world)
        ctx = RuleContext(StateView(s), c.definition_view, None, 1)
        derived = c.derive(ctx, 'characters/player_vane')
        self.assertIn('audit', derived)
        audit = derived['audit']
        for key in ('static', 'baseline_modifiers', 'current_modifiers', 'effective_values', 'health', 'bounds_exceptions'):
            self.assertIn(key, audit)
        self.assertEqual(audit['static'], s['characters']['player_vane']['data']['stats'])
        self.assertEqual(audit['effective_values'], derived['stats'])
        self.assertEqual(before_hashes, hashes(world / 'state'))

    def test_canonical_inspection_includes_audit(self):
        from world_migration import inspect_world
        world = ROOT / 'world/warhammer-40k'
        before_hashes = hashes(world / 'state')
        report = inspect_world(world)
        self.assertIn('derivation_audit', report)
        self.assertIn('player_vane', report['derivation_audit'])
        self.assertEqual(before_hashes, hashes(world / 'state'))

    def test_warhammer_combat_multiplier_order(self):
        # Gross attack = weapon['power'] + kinetic (where kinetic already includes trait/equipment multipliers)
        # Verify it does NOT multiply weapon by strike_kinetic_multiplier again
        from test_worlds import WorldsTests
        t = WorldsTests()
        t.setUp()
        try:
            w = t.combat()
            c = WorldContract(w)
            s = read_snapshot(w)
            ctx = RuleContext(StateView(s), c.definition_view, None, 1)
            derived = c.derive(ctx, 'characters/player_vane')
            weapon = c.definitions['rules']['weapons']['item_void_relic_blade']
            expected_gross = round(weapon['power'] + derived['punch_kinetic_impact'], 2)
            # Attack enemy
            res = run_event(w, t.event(w, {'type': 'attack', 'actor_id': 'player_vane', 'target_id': 'enemy', 'weapon_id': 'item_void_relic_blade'}), render=False)
            self.assertEqual(expected_gross, res['outcomes']['damage_dealt'])
        finally:
            t.tearDown()
