"""Deterministic calendar progression for Lost World."""
from datetime import datetime, timedelta
from engine.contracts import RuleError

def _set(collection, identity, path, value):
    return {'op': 'set', 'collection': collection, 'entity_id': identity, 'path': path, 'value': value}

def validate_calendar(ctx):
    rules = ctx.definitions.get('rules')
    if not rules:
        return []
    policy = rules.get('calendar')
    if not policy:
        return []
    required = {'anchor_turn', 'anchor_day', 'anchor_timestamp', 'turns_per_day', 'display_style'}
    violations = []
    if not required.issubset(policy.keys()):
        violations.append({'id': 'calendar', 'code': 'calendar_config', 'message': f'Calendar requires {required}'})
    turns_per_day = policy.get('turns_per_day')
    if not isinstance(turns_per_day, int) or turns_per_day <= 0:
        violations.append({'id': 'calendar', 'code': 'calendar_config', 'message': 'turns_per_day must be positive integer'})
    anchor_turn = policy.get('anchor_turn')
    if isinstance(anchor_turn, int) and (ctx.turn + 1) < anchor_turn:
        violations.append({'id': 'calendar', 'code': 'calendar_config', 'message': 'Current turn before anchor turn'})
    try:
        datetime.fromisoformat(str(policy.get('anchor_timestamp', '')))
    except Exception:
        violations.append({'id': 'calendar', 'code': 'calendar_config', 'message': 'Invalid ISO anchor_timestamp'})
    return violations

def calendar_effects(ctx):
    rules = ctx.definitions.get('rules')
    if not rules:
        return []
    policy = rules.get('calendar')
    if not policy:
        return []

    violations = validate_calendar(ctx)
    if violations:
        raise RuleError('calendar_config', 'Invalid calendar configuration', violations)

    turns_per_day = policy['turns_per_day']
    next_turn = ctx.turn + 1
    anchor_turn = policy['anchor_turn']
    turn_delta = next_turn - anchor_turn
    new_day = policy['anchor_day'] + (turn_delta // turns_per_day)

    dt = datetime.fromisoformat(policy['anchor_timestamp'])
    new_dt = dt + timedelta(hours=turn_delta)
    display_timestamp = new_dt.isoformat()

    return [
        _set('clock', 'clock', '/day', new_day),
        _set('clock', 'clock', '/display_timestamp', display_timestamp)
    ]
