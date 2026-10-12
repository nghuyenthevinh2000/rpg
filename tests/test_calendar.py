"""Tests for deterministic two-world calendar progression."""
from engine.contracts import RuleError
from engine.runner import read_snapshot, run_event
from world_fixtures import TemporaryWorldCase


class CalendarTests(TemporaryWorldCase):
    def test_lost_world_hour_advance_is_in_same_commit(self):
        world = self.make_world('lost-world')
        report = run_event(world, self.event(world, {'type': 'wait', 'actor_id': 'player_kael'}), render=False)
        clock = read_snapshot(world)['clock']['data']
        self.assertEqual(34, clock['turn'])
        self.assertEqual(4, clock['day'])
        self.assertEqual('2026-10-09T08:30:00+07:00', clock['display_timestamp'])
        self.assertIn('clock', report['changes'])

    def test_lost_world_24_hour_rollover(self):
        world = self.make_world('lost-world')
        # Starting at turn 33, day 4, 07:30.
        # Advancing 24 turns: turn 33 -> 57 (delta = 24 turns = 1 day -> day 5, 07:30)
        for i in range(24):
            run_event(world, self.event(world, {'type': 'wait', 'actor_id': 'player_kael'}, f'wait_{i}'), render=False)
        clock = read_snapshot(world)['clock']['data']
        self.assertEqual(57, clock['turn'])
        self.assertEqual(5, clock['day'])
        self.assertEqual('2026-10-10T07:30:00+07:00', clock['display_timestamp'])

    def test_warhammer_watches_progression_and_day_rollover(self):
        world = self.make_world('warhammer-40k')
        # Starting at turn 37, day 9, anchor 37, 4 watches/day.
        # Next turn (38): delta = 1 -> day = 9 + 0 = 9, watch = 1 + (1 % 4) = 2.
        run_event(world, self.event(world, {'type': 'wait', 'actor_id': 'player_vane'}, 'wait_38'), render=False)
        clock = read_snapshot(world)['clock']['data']
        self.assertEqual(38, clock['turn'])
        self.assertEqual(9, clock['day'])
        self.assertEqual('41.999.059.M41 · Day 9 · Watch 2', clock['display_timestamp'])

        # Turn 39 (delta = 2): day 9, watch 3
        run_event(world, self.event(world, {'type': 'wait', 'actor_id': 'player_vane'}, 'wait_39'), render=False)
        clock = read_snapshot(world)['clock']['data']
        self.assertEqual(39, clock['turn'])
        self.assertEqual(9, clock['day'])
        self.assertEqual('41.999.059.M41 · Day 9 · Watch 3', clock['display_timestamp'])

        # Turn 40 (delta = 3): day 9, watch 4
        run_event(world, self.event(world, {'type': 'wait', 'actor_id': 'player_vane'}, 'wait_40'), render=False)
        clock = read_snapshot(world)['clock']['data']
        self.assertEqual(40, clock['turn'])
        self.assertEqual(9, clock['day'])
        self.assertEqual('41.999.059.M41 · Day 9 · Watch 4', clock['display_timestamp'])

        # Turn 41 (delta = 4): day 10, watch 1
        run_event(world, self.event(world, {'type': 'wait', 'actor_id': 'player_vane'}, 'wait_41'), render=False)
        clock = read_snapshot(world)['clock']['data']
        self.assertEqual(41, clock['turn'])
        self.assertEqual(10, clock['day'])
        self.assertEqual('41.999.059.M41 · Day 10 · Watch 1', clock['display_timestamp'])

    def test_calendar_dry_run_and_failed_action_clock_stability(self):
        world = self.make_world('warhammer-40k')
        before = read_snapshot(world)['clock']['data']
        # Dry run does not advance clock
        run_event(world, self.event(world, {'type': 'wait', 'actor_id': 'player_vane'}), dry_run=True, render=False)
        self.assertEqual(before, read_snapshot(world)['clock']['data'])

        # Failed action does not advance clock (unconnected movement)
        with self.assertRaises(RuleError):
            run_event(world, self.event(world, {'type': 'move', 'actor_id': 'player_vane', 'location_id': 'loc_charnel_trench'}), render=False)
        self.assertEqual(before, read_snapshot(world)['clock']['data'])

    def test_calendar_rejections_for_invalid_policy(self):
        world = self.make_world('warhammer-40k')
        # Invalid turns_per_day
        self.edit_rules(world, lambda r: r['calendar'].update(turns_per_day=0))
        with self.assertRaises(RuleError) as err:
            run_event(world, self.event(world, {'type': 'wait', 'actor_id': 'player_vane'}), render=False)
        self.assertEqual('calendar_config', err.exception.code)
