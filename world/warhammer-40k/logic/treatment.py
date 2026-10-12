"""Resource-backed healing and gated restoration for Warhammer 40k."""
from engine.contracts import RuleError, RuleResult, safe_id
from .resources import _number

ALLOWED_TREATMENT_FIELDS = {'resource_id', 'resource_cost', 'heal_amount', 'health_ceiling'}
ALLOWED_RESTORATION_FIELDS = {'enabled', 'resource_id', 'resource_cost', 'restore_health'}


def _set(collection, identity, path, value):
    return {'op': 'set', 'collection': collection, 'entity_id': identity, 'path': path, 'value': value}


def validate_treatment(ctx):
    rules = ctx.definitions.get('rules')
    if rules is None:
        return []
    violations = []

    def bad(identity, message):
        violations.append({'id': identity, 'code': 'treatment_config', 'message': message})

    if 'treatment_recipes' in rules:
        recipes = rules['treatment_recipes']
        if not isinstance(recipes, dict):
            bad('treatment', 'treatment_recipes must be an object')
        else:
            for recipe_id, recipe in sorted(recipes.items()):
                if not isinstance(recipe, dict):
                    bad(recipe_id, 'recipe must be an object')
                    continue
                if set(recipe) != ALLOWED_TREATMENT_FIELDS:
                    bad(recipe_id, f'Recipe requires exact fields: {sorted(ALLOWED_TREATMENT_FIELDS)}')
                    continue
                res_id = recipe['resource_id']
                if not isinstance(res_id, str) or ctx.state.get('resources', res_id) is None:
                    bad(recipe_id, f'Unknown resource reference: {res_id}')
                if not _number(recipe['resource_cost'], positive=True):
                    bad(recipe_id, 'resource_cost must be finite positive number')
                if not _number(recipe['heal_amount'], positive=True):
                    bad(recipe_id, 'heal_amount must be finite positive number')
                if not _number(recipe['health_ceiling'], positive=True):
                    bad(recipe_id, 'health_ceiling must be finite positive number')

    if 'restoration_policy' in rules:
        policy = rules['restoration_policy']
        if not isinstance(policy, dict):
            bad('restoration', 'restoration_policy must be an object')
        else:
            if 'enabled' not in policy or not isinstance(policy['enabled'], bool):
                bad('restoration', 'restoration_policy enabled must be a boolean')
            elif policy['enabled']:
                if set(policy) != ALLOWED_RESTORATION_FIELDS:
                    bad('restoration', f'Restoration policy requires exact fields: {sorted(ALLOWED_RESTORATION_FIELDS)}')
                else:
                    res_id = policy.get('resource_id')
                    if res_id != 'primordial_life_restoration' or ctx.state.get('resources', res_id) is None:
                        bad('restoration', 'restoration requires primordial_life_restoration resource')
                    if policy.get('resource_cost') != 1 or type(policy.get('resource_cost')) is bool:
                        bad('restoration', 'restoration resource_cost must be 1')
                    if policy.get('restore_health') != 100 or type(policy.get('restore_health')) is bool:
                        bad('restoration', 'restoration restore_health must be 100')

    return violations


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
