"""Peaceful trial resolution and validated rewards."""
from engine.contracts import RuleError, RuleResult, safe_id
from .resources import _number, _capacity

def _set(collection, identity, path, value):
    return {'op': 'set', 'collection': collection, 'entity_id': identity, 'path': path, 'value': value}

def resolve_trial(ctx, event):
    action = event['action']
    if set(action) != {'type', 'actor_id', 'trial_id', 'recipe_id'}:
        raise RuleError('action_shape', 'Exact fields required: type, actor_id, trial_id, recipe_id')
    for val in action.values():
        if not isinstance(val, str) or not val:
            raise RuleError('action_shape', 'Action values must be nonempty strings')
        safe_id(val)

    actor_id, trial_id, recipe_id = action['actor_id'], action['trial_id'], action['recipe_id']
    actor = ctx.state.get('characters', actor_id)
    if actor is None or actor['data']['status'] != 'alive':
        raise RuleError('invalid_actor', 'Living character required')

    threat = ctx.state.get('threats', trial_id)
    if threat is None or not threat['data'].get('active'):
        raise RuleError('invalid_trial', 'Active trial required')
    
    # Trial must be active and activation_turn <= ctx.turn
    if threat['data'].get('activation_turn', 0) > ctx.turn:
        raise RuleError('trial_inactive', 'Trial is not yet active on current turn')

    if actor['data']['location_id'] != threat['data'].get('location_id'):
        raise RuleError('trial_location', 'Actor and trial must be co-located')

    rules = ctx.definitions.get('rules')
    recipes = rules.get('trial_recipes', {})
    if recipe_id not in recipes:
        raise RuleError('unknown_recipe', f'Trial recipe {recipe_id} not recognized')
    recipe = recipes[recipe_id]

    if recipe.get('template_id') != threat['data'].get('metadata', {}).get('template_id'):
        raise RuleError('invalid_recipe', 'Recipe does not match trial template')

    # Prerequisite structural conditions if any
    world_doc = ctx.definitions.get('world')
    structural = world_doc.get('structural_rules', {}) if world_doc else {}
    for req_key, req_val in recipe.get('structural_requirements', {}).items():
        if structural.get(req_key) != req_val:
            raise RuleError('trial_structural', f'Structural requirement {req_key} unmet')

    effects = []
    # Deduct resource costs
    for res_id, cost in sorted(recipe.get('resource_costs', {}).items()):
        stock = ctx.state.get('resources', res_id)
        if stock is None or stock['data']['quantity'] < cost:
            raise RuleError('insufficient_resources', f'Insufficient resource {res_id}')
        effects.append(_set('resources', res_id, '/quantity', stock['data']['quantity'] - cost))

    # Grant resource rewards
    for res_id, reward in sorted(recipe.get('resource_rewards', {}).items()):
        stock = ctx.state.get('resources', res_id)
        if stock is None:
            raise RuleError('unknown_resource', f'Resource {res_id} does not exist')
        cap = _capacity(ctx, res_id)
        new_qty = stock['data']['quantity'] + reward
        if cap is not None and new_qty > cap:
            raise RuleError('resource_capacity', f'Resource reward exceeds capacity for {res_id}')
        effects.append(_set('resources', res_id, '/quantity', new_qty))

    # Trait rewards if any
    trait_ids = recipe.get('trait_rewards', [])
    if trait_ids:
        from .inventory import trait_reward_effects
        effects.extend(trait_reward_effects(ctx, actor_id, trait_ids))

    # Mark trial inactive
    effects.append(_set('threats', trial_id, '/active', False))

    return RuleResult(effects, {'trial_id': trial_id, 'recipe_id': recipe_id, 'resolved_by': actor_id})
