"""Compatibility entry point for the same canonical runner."""
from engine.runner import run_event as apply_event
from world_cli import main

if __name__ == '__main__':
    raise SystemExit(main())
