"""Shared CLI boundaries; convenience names never own gameplay writes."""
import argparse
import json
import random
import sys
from engine.contracts import RuleContext, RuleError, StateView, WorldContract, load_json
from engine.runner import read_snapshot, replay_event, run_event
from world_utils import require_canonical, resolve_world_dir


def main(mode='run', argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('event', nargs='?')
    parser.add_argument('--world')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--no-render', action='store_true')
    parser.add_argument('--improvise', action='store_true')
    parser.add_argument('--force-gm', action='store_true')
    parser.add_argument('--replay', action='store_true')
    args = parser.parse_args(argv)
    try:
        world = resolve_world_dir(args.world, args.event)
        require_canonical(world)
        if mode == 'gm' or args.improvise or args.force_gm:
            if args.event:
                raise RuleError('proposal_only', 'GM flags only generate a separate proposal; omit the event argument')
            from game_master import propose_event
            result = propose_event(world, seed=args.seed, improvise=args.improvise)
        elif mode in ('stats', 'timing'):
            if args.event:
                raise RuleError('read_only', 'Inspection takes no event and never applies effects')
            snapshot = read_snapshot(world); contract = WorldContract(world)
            ctx = RuleContext(StateView(snapshot), contract.definition_view, random.Random(args.seed), snapshot['clock']['data']['turn'])
            if mode == 'stats':
                result = {'derived': {e['id']:contract.derive(ctx, 'characters/'+e['id']) for e in ctx.state.list('characters')}, 'violations':contract.validate(ctx), 'read_only':True}
            else:
                result = {'read_only':True, 'clock':snapshot['clock'], 'timing':'Actions then one periodic overlay pass; newly introduced hazards activate next turn; retaliation only in attack, even on killing blow. No enforcement write.'}
        elif mode == 'render':
            if args.event:
                raise RuleError('read_only', 'Rendering takes no event; it never replays gameplay')
            from engine.render_map import render_map
            result = {'map': str(render_map(world))}
        else:
            if not args.event:
                raise RuleError('missing_event', 'Supply a canonical proposed event JSON path')
            event = load_json(args.event)
            if 'action' not in event and not args.replay:
                raise RuleError('legacy_event', 'Legacy event aliases/patches are disabled; inspect/migrate the save, then propose canonical intent')
            if args.replay:
                if args.dry_run:
                    raise RuleError('unsupported_flag', 'Replay does not support --dry-run; use a temporary matching baseline')
                result = replay_event(world, event, render=not args.no_render)
            else:
                result = run_event(world, event, dry_run=args.dry_run, seed=args.seed, render=not args.no_render)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except RuleError as error:
        print(json.dumps({'error':error.to_dict()}, ensure_ascii=False), file=sys.stderr)
        return 2
    except OSError as error:
        print(json.dumps({'error':{'code':'filesystem_interruption', 'message':str(error), 'guidance':'Do not resubmit an uncertain turn. Read a snapshot to recover, or inspect migration journal and use documented --resume.'}}), file=sys.stderr)
        return 3
