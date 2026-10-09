"""Read-only derived-stat and invariant inspection; never enforce by writing."""
from world_cli import main

if __name__ == '__main__':
    raise SystemExit(main('stats'))
