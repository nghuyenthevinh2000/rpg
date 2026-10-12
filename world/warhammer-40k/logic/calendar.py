"""Deterministic calendar progression for Warhammer 40k."""
from engine.contracts import RuleError

CALENDAR_FIELDS = {'anchor_turn', 'anchor_day', 'anchor_timestamp', 'turns_per_day', 'display_style'}


def _set(collection, identity, path, value):
    return {'op': 'set', 'collection': collection, 'entity_id': identity, 'path': path, 'value': value}


def validate_calendar(ctx):
    rules = ctx.definitions.get('rules')
    if not rules:
        return []
    policy = rules.get('calendar')
    if policy is None:
        return []
    if not isinstance(policy, dict):
        return [{'id': 'calendar', 'code': 'calendar_config', 'message': 'calendar policy must be an object'}]

    violations = []

    def bad(message):
        violations.append({'id': 'calendar', 'code': 'calendar_config', 'message': message})

    if set(policy) != CALENDAR_FIELDS:
        bad(f'Calendar policy requires exact fields: {sorted(CALENDAR_FIELDS)}')
        return violations

    anchor_turn = policy.get('anchor_turn')
    if type(anchor_turn) is not int or not (0 <= anchor_turn <= ctx.turn):
        bad('anchor_turn must be an integer between 0 and current turn')

    anchor_day = policy.get('anchor_day')
    if type(anchor_day) is not int or anchor_day < 0:
        bad('anchor_day must be a nonnegative integer')

    turns_per_day = policy.get('turns_per_day')
    if type(turns_per_day) is not int or turns_per_day != 4:
        bad('turns_per_day must be integer 4')

    if policy.get('display_style') != 'watches':
        bad("display_style must be 'watches'")

    ts = policy.get('anchor_timestamp')
    if not isinstance(ts, str) or not ts:
        bad('anchor_timestamp must be a nonempty string')

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

    watch = 1 + (turn_delta % turns_per_day)
    display_timestamp = f"{policy['anchor_timestamp']} · Day {new_day} · Watch {watch}"

    return [
        _set('clock', 'clock', '/day', new_day),
        _set('clock', 'clock', '/display_timestamp', display_timestamp)
    ]
