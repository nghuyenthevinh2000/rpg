"""Resource-backed healing and gated restoration for Warhammer 40k."""
from engine.contracts import RuleError, RuleResult, safe_id


def _set(collection, identity, path, value):
    return {'op': 'set', 'collection': collection, 'entity_id': identity, 'path': path, 'value': value}


def resolve_treatment(ctx, event):
    action = event['action']
    kind = action['type']
    rules = ctx.definitions.get('rules')

    if kind == 'heal':
        if set(action) != {'type', 'actor_id', 'target_id', 'recipe_id'}:
            raise RuleError('action_shape', 'Required fields: type, actor_id, target_id, recipe_id')
        for val in action.values():
            if not isinstance(val, str) or not val:
                raise RuleError('action_shape', 'Action values must be nonempty strings')
            safe_id(val)

        actor_id = action['actor_id']
        actor = ctx.state.get('characters', actor_id)
        if actor is None or actor['data']['status'] != 'alive':
            raise RuleError('invalid_actor', 'Living actor required')
        actor_loc = actor['data']['location_id']

        target_id = action['target_id']
        target = ctx.state.get('characters', target_id)
        if target is None:
            raise RuleError('invalid_target', 'Target character must exist')
        tdata = target['data']

        # Reject dead targets
        if tdata['status'] != 'alive' or tdata['health'] == 0:
            raise RuleError('invalid_target', 'Cannot heal dead character')
        # Reject null-health synthetic entities
        if tdata['health'] is None:
            raise RuleError('invalid_target', 'Cannot heal synthetic character with null health')
        # Reject co-location mismatch
        if tdata['location_id'] != actor_loc:
            raise RuleError('invalid_target', 'Target must be co-located with actor')
        # Reject immortal targets (never treat immortality sentinel as a number or heal immortal)
        if tdata['capabilities'].get('cannot_die'):
            raise RuleError('invalid_target', 'Cannot heal immortal character')

        recipes = rules.get('treatment_recipes', {})
        recipe_id = action['recipe_id']
        if recipe_id not in recipes:
            raise RuleError('invalid_recipe', f'Unknown treatment recipe: {recipe_id}')
        recipe = recipes[recipe_id]

        res_id = recipe['resource_id']
        cost = recipe['resource_cost']
        res = ctx.state.get('resources', res_id)
        if res is None or res['data'].get('quantity', 0) < cost:
            raise RuleError('insufficient_resources', f'Insufficient {res_id} stock')

        current_hp = tdata['health']
        ceiling = recipe.get('health_ceiling', 100)
        # If already at or above ceiling, reject as full-health/no-op
        if current_hp >= ceiling:
            raise RuleError('full_health', f'Target is already at or above ceiling {ceiling}')

        heal_amt = recipe['heal_amount']
        new_hp = min(ceiling, current_hp + heal_amt)

        effects = [
            _set('resources', res_id, '/quantity', res['data']['quantity'] - cost),
            _set('characters', target_id, '/health', new_hp)
        ]
        return RuleResult(effects, {
            'action': 'heal',
            'actor_id': actor_id,
            'target_id': target_id,
            'recipe_id': recipe_id,
            'healed': new_hp - current_hp,
            'new_health': new_hp
        })

    elif kind == 'restore_life':
        if set(action) != {'type', 'actor_id', 'target_id'}:
            raise RuleError('action_shape', 'Required fields: type, actor_id, target_id')
        for val in action.values():
            if not isinstance(val, str) or not val:
                raise RuleError('action_shape', 'Action values must be nonempty strings')
            safe_id(val)

        policy = rules.get('restoration_policy', {})
        if not policy.get('enabled'):
            raise RuleError('restoration_disabled', 'Restoration policy is disabled')

        actor_id = action['actor_id']
        actor = ctx.state.get('characters', actor_id)
        if actor is None or actor['data']['status'] != 'alive':
            raise RuleError('invalid_actor', 'Living actor required')
        if not actor['data']['capabilities'].get('cannot_die'):
            raise RuleError('invalid_actor', 'Restoration requires living immortal actor')
        actor_loc = actor['data']['location_id']

        target_id = action['target_id']
        target = ctx.state.get('characters', target_id)
        if target is None:
            raise RuleError('invalid_target', 'Target character must exist')
        tdata = target['data']

        if tdata['status'] != 'dead':
            raise RuleError('invalid_target', 'Target must be dead to restore life')
        if tdata['location_id'] != actor_loc:
            raise RuleError('invalid_target', 'Target must be co-located with actor')

        res_id = policy['resource_id']
        cost = policy['resource_cost']
        res = ctx.state.get('resources', res_id)
        if res is None or res['data'].get('quantity', 0) < cost:
            raise RuleError('insufficient_resources', f'Insufficient {res_id} stock')

        restore_hp = policy.get('restore_health', 100)
        effects = [
            _set('resources', res_id, '/quantity', res['data']['quantity'] - cost),
            _set('characters', target_id, '/health', restore_hp),
            _set('characters', target_id, '/status', 'alive')
        ]
        return RuleResult(effects, {
            'action': 'restore_life',
            'actor_id': actor_id,
            'target_id': target_id,
            'restored_health': restore_hp
        })

    else:
        raise RuleError('unsupported_action', f'Unsupported treatment action: {kind}')
