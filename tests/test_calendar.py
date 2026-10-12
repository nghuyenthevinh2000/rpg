"""Tests for deterministic two-world calendar progression."""
from engine.contracts import RuleError, WorldContract
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

    def test_no_turn_action_does_not_advance_calendar(self):
        from unittest.mock import patch
        world = self.make_world('warhammer-40k')
        contract = WorldContract(world)
        before_snap = read_snapshot(world)
        before_clock = before_snap['clock']['data']

        # Wrap contract.resolve to return advances_turn=False
        orig_resolve = contract.resolve
        def no_turn_resolve(ctx, event):
            res = orig_resolve(ctx, event)
            res.advances_turn = False
            return res

        with patch.object(contract, 'resolve', side_effect=no_turn_resolve):
            with patch.object(contract, 'after_turn') as mock_after_turn:
                # Need to use runner with our patched contract
                from engine.runner import run_event
                # Monkeypatch WorldContract inside runner
                with patch('engine.runner.WorldContract', return_value=contract):
                    report = run_event(world, self.event(world, {'type': 'wait', 'actor_id': 'player_vane'}, 'no_turn_wait'), render=False)
                    mock_after_turn.assert_not_called()
                    self.assertFalse(report['turn']['advances_turn'])
                    self.assertEqual(before_clock['turn'], report['turn']['before'])
                    self.assertEqual(before_clock['turn'], report['turn']['after'])
                    self.assertNotIn('clock', report['changes'])
                    after_clock = read_snapshot(world)['clock']['data']
                    self.assertEqual(before_clock, after_clock)

    def test_calendar_rejections_for_invalid_policy(self):
        from unittest.mock import patch
        from engine.runner import replay_event
        from engine.state_store import StateStore

        # 1. turns_per_day = True
        world = self.make_world('warhammer-40k')
        self.edit_rules(world, lambda r: r['calendar'].update(turns_per_day=True))
        before = read_snapshot(world)
        with self.assertRaises(RuleError) as err:
            run_event(world, self.event(world, {'type': 'wait', 'actor_id': 'player_vane'}), render=False)
        self.assertEqual('calendar_config', err.exception.code)
        self.assertEqual(before, read_snapshot(world))

        # 2. anchor_turn = current_turn + 1 (future anchor)
        self.tmp.cleanup(); self.setUp()
        world = self.make_world('warhammer-40k')
        cur_turn = read_snapshot(world)['clock']['data']['turn']
        self.edit_rules(world, lambda r: r['calendar'].update(anchor_turn=cur_turn + 1))
        before = read_snapshot(world)
        with self.assertRaises(RuleError) as err:
            run_event(world, self.event(world, {'type': 'wait', 'actor_id': 'player_vane'}), render=False)
        self.assertEqual('calendar_config', err.exception.code)
        self.assertEqual(before, read_snapshot(world))

        # 3. negative anchor_turn or boolean anchor_turn
        for bad_anchor in (-1, True, 'thirty-seven'):
            self.tmp.cleanup(); self.setUp()
            world = self.make_world('warhammer-40k')
            self.edit_rules(world, lambda r, a=bad_anchor: r['calendar'].update(anchor_turn=a))
            before = read_snapshot(world)
            with self.assertRaises(RuleError) as err:
                run_event(world, self.event(world, {'type': 'wait', 'actor_id': 'player_vane'}), render=False)
            self.assertEqual('calendar_config', err.exception.code)
            self.assertEqual(before, read_snapshot(world))

        # 4. negative anchor_day or boolean anchor_day
        for bad_day in (-1, True, 'nine'):
            self.tmp.cleanup(); self.setUp()
            world = self.make_world('warhammer-40k')
            self.edit_rules(world, lambda r, d=bad_day: r['calendar'].update(anchor_day=d))
            before = read_snapshot(world)
            with self.assertRaises(RuleError) as err:
                run_event(world, self.event(world, {'type': 'wait', 'actor_id': 'player_vane'}), render=False)
            self.assertEqual('calendar_config', err.exception.code)
            self.assertEqual(before, read_snapshot(world))

        # 5. wrong display_style
        self.tmp.cleanup(); self.setUp()
        world = self.make_world('warhammer-40k')
        self.edit_rules(world, lambda r: r['calendar'].update(display_style='iso_hours'))
        before = read_snapshot(world)
        with self.assertRaises(RuleError) as err:
            run_event(world, self.event(world, {'type': 'wait', 'actor_id': 'player_vane'}), render=False)
        self.assertEqual('calendar_config', err.exception.code)
        self.assertEqual(before, read_snapshot(world))

        # 6. unknown extra fields
        self.tmp.cleanup(); self.setUp()
        world = self.make_world('warhammer-40k')
        self.edit_rules(world, lambda r: r['calendar'].update(extra_field='invalid'))
        before = read_snapshot(world)
        with self.assertRaises(RuleError) as err:
            run_event(world, self.event(world, {'type': 'wait', 'actor_id': 'player_vane'}), render=False)
        self.assertEqual('calendar_config', err.exception.code)
        self.assertEqual(before, read_snapshot(world))

        # 7. Lost World timestamp with no UTC offset
        self.tmp.cleanup(); self.setUp()
        lw = self.make_world('lost-world')
        self.edit_rules(lw, lambda r: r['calendar'].update(anchor_timestamp='2026-10-09T07:30:00'))
        before_lw = read_snapshot(lw)
        with self.assertRaises(RuleError) as err:
            run_event(lw, self.event(lw, {'type': 'wait', 'actor_id': 'player_kael'}), render=False)
        self.assertEqual('calendar_config', err.exception.code)
        self.assertEqual(before_lw, read_snapshot(lw))

    def test_calendar_replay_and_interrupted_recovery(self):
        from unittest.mock import patch
        from engine.runner import replay_event
        from engine.state_store import StateStore

        # Exact replay into a fresh matching baseline
        world = self.make_world('warhammer-40k')
        twin = self.author_state(world, lambda s: None, 'twin')
        report = run_event(world, self.event(world, {'type': 'wait', 'actor_id': 'player_vane'}), render=False)
        replay_event(twin, report, render=False)
        self.assertEqual(read_snapshot(world)['clock'], read_snapshot(twin)['clock'])

        # Interrupted calendar commit recovery
        expected_snapshot = read_snapshot(world)
        expected = run_event(world, self.event(world, {'type': 'wait', 'actor_id': 'player_vane'}, 'ev_rec'), dry_run=True, render=False)
        expected_snapshot['clock'] = expected['changes']['clock']['after']

        with patch.object(StateStore, '_apply_images', side_effect=OSError('interrupted calendar')):
            with self.assertRaises(OSError):
                run_event(world, expected['event'], render=False)
        actual = read_snapshot(world)
        self.assertEqual(expected_snapshot['clock'], actual['clock'])
