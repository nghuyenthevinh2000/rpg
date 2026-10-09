"""Inspect the selected legacy save without mutation."""
import argparse
import json
import sys
from engine.contracts import RuleError
from world_migration import inspect_world
from world_utils import resolve_world_dir

def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--world', required=True)
    args = parser.parse_args()
    try:
        report = inspect_world(resolve_world_dir(args.world))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2 if report.get('blocking') else 0
    except RuleError as error:
        print(json.dumps({'error':error.to_dict()}), file=sys.stderr); return 2

if __name__ == '__main__':
    raise SystemExit(main())
