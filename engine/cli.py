"""Unified module CLI dispatcher for engine."""
import argparse
import json
import random
import sys
from engine.contracts import RuleContext, RuleError, StateView, WorldContract, load_json
from engine.runner import read_snapshot, replay_event, run_event
from engine.world_utils import require_canonical, resolve_world_dir


def build_parser():
    parser = argparse.ArgumentParser(prog='python -m engine')
    subparsers = parser.add_subparsers(dest='command', required=True)

    # run EVENT [--world WORLD] [--dry-run] [--seed INT] [--no-render] [--replay]
    run_parser = subparsers.add_parser('run', help='Execute or replay a gameplay event')
    run_parser.add_argument('event', help='Canonical event JSON path')
    run_parser.add_argument('--world', help='World name or directory')
    run_parser.add_argument('--dry-run', action='store_true', help='Preview turn without committing state')
    run_parser.add_argument('--seed', type=int, default=0, help='RNG seed')
    run_parser.add_argument('--no-render', action='store_true', help='Skip map rendering')
    run_parser.add_argument('--replay', action='store_true', help='Replay an exact recorded event')

    # inspect --world WORLD
    inspect_parser = subparsers.add_parser('inspect', help='Inspect legacy or canonical world save')
    inspect_parser.add_argument('--world', required=True, help='World name or directory')

    # migrate --world WORLD [--dry-run] [--resume] [--accept-baseline]
    migrate_parser = subparsers.add_parser('migrate', help='Migrate world save to canonical schema')
    migrate_parser.add_argument('--world', required=True, help='World name or directory')
    migrate_parser.add_argument('--dry-run', action='store_true', help='Preview migration without writing')
    migrate_parser.add_argument('--resume', action='store_true', help='Resume a staged migration cutover')
    migrate_parser.add_argument('--accept-baseline', action='store_true', help='Deprecated compatibility flag')

    # render [--world WORLD]
    render_parser = subparsers.add_parser('render', help='Render world map projection')
    render_parser.add_argument('--world', help='World name or directory')

    # gm [--world WORLD] [--seed INT] [--improvise]
    gm_parser = subparsers.add_parser('gm', help='Generate seeded GM proposal')
    gm_parser.add_argument('--world', help='World name or directory')
    gm_parser.add_argument('--seed', type=int, default=0, help='RNG seed')
    gm_parser.add_argument('--improvise', action='store_true', help='Improvise proposal')

    # stats [--world WORLD] [--seed INT]
    stats_parser = subparsers.add_parser('stats', help='Inspect derived stats and invariant violations')
    stats_parser.add_argument('--world', help='World name or directory')
    stats_parser.add_argument('--seed', type=int, default=0, help='RNG seed')

    # timing [--world WORLD]
    timing_parser = subparsers.add_parser('timing', help='Inspect timing explanation and clock')
    timing_parser.add_argument('--world', help='World name or directory')

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == 'inspect':
            world = resolve_world_dir(args.world)
            from engine.migration import inspect_world
            report = inspect_world(world)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 2 if report.get('blocking') else 0

        elif args.command == 'migrate':
            world = resolve_world_dir(args.world)
            from engine.migration import migrate_world
            try:
                report = migrate_world(
                    world,
                    dry_run=args.dry_run,
                    accept_baseline=args.accept_baseline,
                    resume=args.resume
                )
                print(json.dumps(report, ensure_ascii=False, indent=2))
                return 0
            except OSError as error:
                print(json.dumps({'error': {
                    'code': 'migration_interruption',
                    'message': str(error),
                    'guidance': 'Keep original/archive/stage. Inspect .migration.json; ready phase supports --resume. Preparing phase refuses retry; restore into a fresh directory from verified original archive.'
                }}), file=sys.stderr)
                return 3

        elif args.command == 'run':
            world = resolve_world_dir(args.world, args.event)
            require_canonical(world)
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

        elif args.command == 'render':
            world = resolve_world_dir(args.world)
            require_canonical(world)
            from engine.render_map import render_map
            result = {'map': str(render_map(world))}
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        elif args.command == 'gm':
            world = resolve_world_dir(args.world)
            require_canonical(world)
            from engine.game_master import propose_event
            result = propose_event(world, seed=args.seed, improvise=args.improvise)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        elif args.command in ('stats', 'timing'):
            world = resolve_world_dir(args.world)
            require_canonical(world)
            snapshot = read_snapshot(world)
            contract = WorldContract(world)
            seed = getattr(args, 'seed', 0)
            ctx = RuleContext(StateView(snapshot), contract.definition_view, random.Random(seed), snapshot['clock']['data']['turn'])
            if args.command == 'stats':
                result = {
                    'derived': {e['id']: contract.derive(ctx, 'characters/' + e['id']) for e in ctx.state.list('characters')},
                    'violations': contract.validate(ctx),
                    'read_only': True
                }
            else:
                result = {
                    'read_only': True,
                    'clock': snapshot['clock'],
                    'timing': 'Actions then one periodic overlay pass; newly introduced hazards activate next turn; retaliation only in attack, even on killing blow. No enforcement write.'
                }
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        else:
            raise RuleError('unknown_command', f'Unknown command {args.command}')

    except RuleError as error:
        print(json.dumps({'error': error.to_dict()}, ensure_ascii=False), file=sys.stderr)
        return 2
    except OSError as error:
        print(json.dumps({'error': {
            'code': 'filesystem_interruption',
            'message': str(error),
            'guidance': 'Do not resubmit an uncertain turn. Read a snapshot to recover, or inspect migration journal and use documented --resume.'
        }}), file=sys.stderr)
        return 3
