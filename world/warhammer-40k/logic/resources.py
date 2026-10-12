"""Fixed stock policies and atomic, unscaled production recipes."""
import math

from engine.contracts import RuleError, RuleResult

SHORTAGE_ALLOWED = True
POLICY_FIELDS = {'capacity', 'production_per_turn', 'consumption_per_turn',
                 'location_id', 'shortage_damage'}
RECIPE_FIELDS = {'location_id', 'inputs', 'outputs', 'health_cost'}


def _number(value, positive=False):
    try:
        return type(value) in (int, float) and math.isfinite(value) and (value > 0 if positive else value >= 0)
    except OverflowError:
        return False


def _capacity(ctx, identity):
    policy = ctx.definitions.get('rules').get('resource_policies', {}).get(identity, {})
    return policy.get('capacity', ctx.state.get('resources', identity)['data'].get('capacity'))


def validate_resources(ctx):
    """Return violations without proposing effects or altering the snapshot."""
    rules = ctx.definitions.get('rules')
    locations = {l['id'] for l in ctx.definitions.get('locations')['locations']}
    policies, recipes = rules.get('resource_policies', {}), rules.get('resource_recipes', {})
    violations = []
    def bad(identity, message):
        violations.append({'id': identity, 'code': 'resource_config', 'message': message})
    for stock in ctx.state.list('resources'):
        data = stock['data']
        if not _number(data.get('quantity')):
            bad(stock['id'], 'quantity must be finite and nonnegative')
        if 'capacity' in data and (not _number(data['capacity']) or
                (_number(data.get('quantity')) and data['quantity'] > data['capacity'])):
            bad(stock['id'], 'invalid stock capacity or over-capacity baseline')
    if not isinstance(policies, dict) or not isinstance(recipes, dict):
        bad('resources', 'policy and recipe registries must be objects')
        return violations
    sanctuary = rules.get('sanctuary', False) or ctx.definitions.get('world')['structural_rules'].get('transcendent_sanctuary', False)
    for identity, policy in sorted(policies.items()):
        stock = ctx.state.get('resources', identity)
        if stock is None or not isinstance(policy, dict) or set(policy) - POLICY_FIELDS or 'capacity' not in policy:
            bad(identity, 'policy requires existing resource, capacity and only known fields')
            continue
        if any(not _number(policy.get(field, 0)) for field in POLICY_FIELDS - {'location_id'}):
            bad(identity, 'policy numbers must be finite and nonnegative')
        elif _number(stock['data'].get('quantity')) and stock['data']['quantity'] > policy['capacity']:
            bad(identity, 'baseline exceeds policy capacity')
        if 'location_id' in policy and (not isinstance(policy['location_id'], str) or policy['location_id'] not in locations):
            bad(identity, 'unknown policy location')
        damage = policy.get('shortage_damage', 0)
        if _number(damage) and damage > 0:
            if not SHORTAGE_ALLOWED or sanctuary:
                bad(identity, 'shortage damage prohibited by world policy')
            if 'location_id' not in policy:
                bad(identity, 'shortage damage requires an explicit location')
    for identity, recipe in sorted(recipes.items()):
        if not isinstance(recipe, dict) or set(recipe) != RECIPE_FIELDS:
            bad(identity, 'recipe fields must be location_id, inputs, outputs, health_cost')
            continue
        if not isinstance(recipe['location_id'], str) or recipe['location_id'] not in locations:
            bad(identity, 'unknown recipe location')
        if not _number(recipe['health_cost']):
            bad(identity, 'health_cost must be finite and nonnegative')
        for field in ('inputs', 'outputs'):
            amounts = recipe[field]
            if not isinstance(amounts, dict) or not amounts:
                bad(identity, field + ' must be a nonempty resource quantity map')
                continue
            for resource_id, quantity in amounts.items():
                stock = ctx.state.get('resources', resource_id)
                if stock is None or not _number(quantity, positive=True):
                    bad(identity, field + ' requires existing resources and finite positive quantities')
                elif field == 'outputs':
                    policy = policies.get(resource_id, {})
                    capacity = policy.get('capacity') if isinstance(policy, dict) else None
                    capacity = stock['data'].get('capacity') if capacity is None else capacity
                    if not _number(capacity):
                        bad(identity, 'outputs require an explicit finite nonnegative capacity')
    return violations


def _checked(ctx):
    violations = validate_resources(ctx)
    if violations:
        raise RuleError('resource_config', 'Invalid resource configuration', violations)


def _set(collection, identity, path, value):
    if path in ('/quantity', '/health') and not _number(value):
        raise RuleError('resource_config', 'Resource arithmetic must remain finite and nonnegative')
    return {'op': 'set', 'collection': collection, 'entity_id': identity, 'path': path, 'value': value}


def resolve_production(ctx, event):
    _checked(ctx)
    action = event['action']
    if set(action) != {'type', 'actor_id', 'recipe_id'} or action.get('type') != 'produce' or not all(isinstance(v, str) and v for v in action.values()):
        raise RuleError('action_shape', 'produce takes only type, actor_id and recipe_id strings')
    actor = ctx.state.get('characters', action['actor_id'])
    recipe = ctx.definitions.get('rules').get('resource_recipes', {}).get(action['recipe_id'])
    if actor is None or actor['data']['status'] != 'alive':
        raise RuleError('invalid_actor', 'Production requires a living actor')
    if recipe is None or actor['data']['location_id'] != recipe['location_id']:
        raise RuleError('invalid_recipe', 'Configured recipe at actor location required')
    deltas = {}
    # Outputs cannot fund inputs; capacity applies to the combined final stock.
    for identity, amount in sorted(recipe['inputs'].items()):
        if ctx.state.get('resources', identity)['data']['quantity'] < amount:
            raise RuleError('insufficient_resources', 'Insufficient recipe inputs')
        deltas[identity] = -amount
    for identity, amount in sorted(recipe['outputs'].items()):
        deltas[identity] = deltas.get(identity, 0) + amount
    for identity, delta in sorted(deltas.items()):
        final = ctx.state.get('resources', identity)['data']['quantity'] + delta
        capacity = _capacity(ctx, identity)
        if not _number(final) or (capacity is not None and final > capacity):
            raise RuleError('resource_capacity', 'Recipe final stock must be finite, nonnegative and fit capacity')
    data, cost = actor['data'], recipe['health_cost']
    if cost and data['health'] is not None and not data['capabilities']['cannot_die'] and data['health'] <= cost:
        raise RuleError('lethal_work', 'Production cannot lethally exhaust a mortal actor')
    effects = [_set('resources', identity, '/quantity', ctx.state.get('resources', identity)['data']['quantity'] + delta)
               for identity, delta in sorted(deltas.items()) if delta != 0]
    if cost and data['health'] is not None and not data['capabilities']['cannot_die']:
        effects.append(_set('characters', actor['id'], '/health', data['health'] - cost))
    return RuleResult(effects, {'production': {'recipe_id': action['recipe_id'], 'resource_deltas': deltas}})


def periodic_resources(ctx):
    _checked(ctx)
    effects, outcomes, damage_by_actor = [], [], {}
    for identity, policy in sorted(ctx.definitions.get('rules').get('resource_policies', {}).items()):
        before = ctx.state.get('resources', identity)['data']['quantity']
        available = min(policy['capacity'], before + policy.get('production_per_turn', 0))
        consumption = policy.get('consumption_per_turn', 0)
        shortage, after = max(0, consumption - available), max(0, available - consumption)
        if after != before:
            effects.append(_set('resources', identity, '/quantity', after))
        outcomes.append({'resource_id': identity, 'before': before, 'after': after, 'shortage': shortage})
        damage = shortage * policy.get('shortage_damage', 0)
        if not _number(damage):
            raise RuleError('resource_config', 'Shortage damage arithmetic must remain finite')
        if SHORTAGE_ALLOWED and damage > 0:
            for actor in ctx.state.list('characters'):
                data = actor['data']
                if data['status'] == 'alive' and data['health'] is not None and not data['capabilities']['cannot_die'] and data['location_id'] == policy['location_id']:
                    damage_by_actor[actor['id']] = damage_by_actor.get(actor['id'], 0) + damage
    injuries = []
    for identity, damage in sorted(damage_by_actor.items()):
        if not _number(damage):
            raise RuleError('resource_config', 'Summed shortage damage must remain finite')
        before = ctx.state.get('characters', identity)['data']['health']
        after = max(0, before - damage)
        effects.extend([_set('characters', identity, '/health', after),
                        _set('characters', identity, '/status', 'dead' if after == 0 else 'alive')])
        injuries.append({'actor_id': identity, 'damage': before - after, 'before': before, 'after': after})
    return RuleResult(effects, {'resources': outcomes, 'resource_shortages': injuries})
