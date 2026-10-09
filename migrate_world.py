"""Current-save normalization/cutover; --dry-run previews, --resume resumes ready installation."""
import argparse
import json
import sys
from engine.contracts import RuleError
from world_migration import migrate_world
from world_utils import resolve_world_dir

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--world', required=True)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--accept-baseline', action='store_true', help='Deprecated compatibility flag; baseline policy is already explicit')
    parser.add_argument('--resume', action='store_true', help='Resume a fully staged ready cutover; never restart or overwrite')
    args = parser.parse_args()
    try:
        print(json.dumps(migrate_world(resolve_world_dir(args.world), dry_run=args.dry_run, accept_baseline=args.accept_baseline, resume=args.resume), ensure_ascii=False, indent=2))
        return 0
    except RuleError as error:
        print(json.dumps({'error':error.to_dict()}), file=sys.stderr); return 2
    except OSError as error:
        print(json.dumps({'error':{'code':'migration_interruption','message':str(error),'guidance':'Keep original/archive/stage. Inspect .migration.json; ready phase supports --resume. Preparing phase refuses retry; restore into a fresh directory from verified original archive.'}}), file=sys.stderr); return 3

if __name__ == '__main__':
    raise SystemExit(main())
