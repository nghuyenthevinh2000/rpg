"""Moral trials, dilemmas, and conserved rewards for Covenant Broken."""
import math

from engine.contracts import RuleError, RuleResult, safe_id
from .resources import _number, _capacity

ALLOWED_TRIAL_RECIPE_FIELDS = {
    'template_id', 'location_id', 'resource_costs',
    'resource_rewards', 'trait_rewards', 'structural_requirements'
}

LEGACY_METADATA_KEYS = {'max_agency', 'max_vitality', 'max_clarity', 'max_neural_strain', 'max_dissonance'}


def _finite_number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _set(collection, identity, path, value):
    return {'op': 'set', 'collection': collection, 'entity_id': identity, 'path': path, 'value': value}


def validate_trait_rewards(ctx, trait_ids):
    if not isinstance(trait_ids, list) or isinstance(trait_ids, str):
        return [{'id': 'trait_rewards', 'code': 'trait_config', 'message': 'trait_rewards must be a list'}]
    violations = []
    traits_doc = ctx.definitions.get('traits')
    registry = traits_doc.get('traits', {}) if traits_doc else {}
    rules = ctx.definitions.get('rules')
    allowed_stats = set(rules.get('stat_keys', []))
    seen = set()
    for tid in trait_ids:
        if not isinstance(tid, str) or tid not in registry:
            violations.append({'id': str(tid), 'code': 'trait_config', 'message': f'Unknown trait reference: {tid}'})
            continue
        if tid in seen:
            violations.append({'id': str(tid), 'code': 'trait_config', 'message': f'Duplicate trait reward: {tid}'})
        seen.add(tid)
        trait_def = registry[tid]
        for key, val in trait_def.get('stat_modifiers', {}).items():
            if not _finite_number(val):
                violations.append({'id': tid, 'code': 'trait_config', 'message': f'Modifier {key} must be finite number'})
            if key not in allowed_stats and key not in LEGACY_METADATA_KEYS and not key.startswith('max_'):
                violations.append({'id': tid, 'code': 'trait_config', 'message': f'Unsupported modifier key {key}'})
    return violations


def trait_reward_effects(ctx, actor_id, trait_ids):
    actor = ctx.state.get('characters', actor_id)
    if actor is None:
        raise RuleError('invalid_actor', f'Character {actor_id} not found')
    if not trait_ids:
        return []
    if not isinstance(trait_ids, list) or isinstance(trait_ids, str):
        raise RuleError('invalid_trait_rewards', 'trait_rewards must be a list')
    try:
        if len(trait_ids) != len(set(trait_ids)):
            raise RuleError('duplicate_trait_reward', 'Duplicate trait IDs in rewards')
    except TypeError:
        raise RuleError('invalid_trait_rewards', 'trait_rewards must contain hashable string IDs')

    traits_doc = ctx.definitions.get('traits')
    registry = traits_doc.get('traits', {}) if traits_doc else {}
    rules = ctx.definitions.get('rules')
    allowed_stats = set(rules.get('stat_keys', []))

    for tid in trait_ids:
        safe_id(tid)
        if tid not in registry:
            raise RuleError('unknown_trait', f'Trait {tid} not recognized')
        trait_def = registry[tid]
        for key, val in trait_def.get('stat_modifiers', {}).items():
            if not _finite_number(val):
                raise RuleError('unsupported_trait_stat', f'Modifier for {key} must be finite number')
            if key not in allowed_stats and key not in LEGACY_METADATA_KEYS and not key.startswith('max_'):
                raise RuleError('unsupported_trait_stat', f'Trait {tid} has unsupported modifier key {key}')

    current = actor['data'].get('traits', [])
    new_traits = sorted(set(current) | set(trait_ids))
    if new_traits == sorted(current):
        return []
    return [_set('characters', actor_id, '/traits', new_traits)]


def validate_trials(ctx):
    rules = ctx.definitions.get('rules')
    if rules is None:
        return []
    if 'trial_recipes' not in rules:
        return []
    recipes = rules['trial_recipes']
    if not isinstance(recipes, dict):
        return [{'id': 'trials', 'code': 'trial_config', 'message': 'trial_recipes must be an object'}]

    violations = []

    def bad(identity, message):
        violations.append({'id': identity, 'code': 'trial_config', 'message': message})

    loc_doc = ctx.definitions.get('locations')
    locations = {loc['id'] for loc in loc_doc.get('locations', [])} if loc_doc else set()
    templates = rules.get('templates', {})
    world_doc = ctx.definitions.get('world')
    structural = world_doc.get('structural_rules', {}) if world_doc else {}

    for recipe_id, recipe in sorted(recipes.items()):
        if not isinstance(recipe, dict):
            bad(recipe_id, 'recipe must be an object')
            continue
        if set(recipe) - ALLOWED_TRIAL_RECIPE_FIELDS:
            bad(recipe_id, f'Unknown fields in trial recipe: {sorted(set(recipe) - ALLOWED_TRIAL_RECIPE_FIELDS)}')
            continue
        if 'template_id' not in recipe or 'location_id' not in recipe:
            bad(recipe_id, 'recipe requires template_id and location_id')
            continue

        tid = recipe['template_id']
        if not isinstance(tid, str) or tid not in templates:
            bad(recipe_id, f'Unknown template reference: {tid}')
        else:
            tpl = templates[tid]
            if not isinstance(tpl, dict) or 'location_id' not in tpl or not tpl['location_id']:
                bad(recipe_id, f'Template {tid} must author an explicit location_id')
            elif tpl['location_id'] != recipe['location_id']:
                bad(recipe_id, 'recipe location_id does not match template location_id')

        loc_id = recipe['location_id']
        if not isinstance(loc_id, str) or loc_id not in locations:
            bad(recipe_id, f'Unknown location reference: {loc_id}')

        costs = recipe.get('resource_costs', {})
        if not isinstance(costs, dict):
            bad(recipe_id, 'resource_costs must be an object')
        else:
            for res_id, cost in sorted(costs.items()):
                if ctx.state.get('resources', res_id) is None:
                    bad(recipe_id, f'Unknown resource in costs: {res_id}')
                if not _number(cost, positive=False):
                    bad(recipe_id, f'Cost for {res_id} must be finite nonnegative number')

        rewards = recipe.get('resource_rewards', {})
        if not isinstance(rewards, dict):
            bad(recipe_id, 'resource_rewards must be an object')
        else:
            for res_id, reward in sorted(rewards.items()):
                if ctx.state.get('resources', res_id) is None:
                    bad(recipe_id, f'Unknown resource in rewards: {res_id}')
                if not _number(reward, positive=False):
                    bad(recipe_id, f'Reward for {res_id} must be finite nonnegative number')

        if 'structural_requirements' in recipe:
            struct_req = recipe['structural_requirements']
            if not isinstance(struct_req, dict):
                bad(recipe_id, 'structural_requirements must be an object')
            else:
                for k, v in sorted(struct_req.items()):
                    if k not in structural:
                        bad(recipe_id, f'Unknown structural requirement name: {k}')
                    elif not isinstance(v, bool):
                        bad(recipe_id, f'Structural requirement {k} must be a boolean')

        if 'trait_rewards' in recipe:
            tr_rewards = recipe['trait_rewards']
            for v in validate_trait_rewards(ctx, tr_rewards):
                bad(recipe_id, v['message'])

    return violations


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

    if threat['data'].get('activation_turn', 0) > ctx.turn:
        raise RuleError('trial_inactive', 'Trial is not yet active on current turn')

    rules = ctx.definitions.get('rules')
    recipes = rules.get('trial_recipes', {})
    if recipe_id not in recipes:
        raise RuleError('unknown_recipe', f'Trial recipe {recipe_id} not recognized')
    recipe = recipes[recipe_id]

    site = recipe['location_id']
    if actor['data']['location_id'] != site or threat['data'].get('location_id') != site:
        raise RuleError('trial_location', 'Configured trial site required')

    if recipe.get('template_id') != threat['data'].get('metadata', {}).get('template_id'):
        raise RuleError('invalid_recipe', 'Recipe does not match trial template')

    world_doc = ctx.definitions.get('world')
    structural = world_doc.get('structural_rules', {}) if world_doc else {}
    for req_key, req_val in recipe.get('structural_requirements', {}).items():
        if structural.get(req_key) != req_val:
            raise RuleError('trial_structural', f'Structural requirement {req_key} unmet')

    effects = []
    costs = recipe.get('resource_costs', {})
    rewards = recipe.get('resource_rewards', {})
    for resource_id in sorted(set(costs) | set(rewards)):
        stock = ctx.state.get('resources', resource_id)
        if stock is None:
            raise RuleError('unknown_resource', f'Resource {resource_id} does not exist')
        old = stock['data']['quantity']
        cost = costs.get(resource_id, 0)
        reward = rewards.get(resource_id, 0)
        if old < cost:
            raise RuleError('insufficient_resources', resource_id)
        final = old - cost + reward
        capacity = _capacity(ctx, resource_id)
        if capacity is not None and final > capacity:
            raise RuleError('resource_capacity', resource_id)
        if final != old:
            effects.append(_set('resources', resource_id, '/quantity', final))

    trait_ids = recipe.get('trait_rewards', [])
    if trait_ids:
        effects.extend(trait_reward_effects(ctx, actor_id, trait_ids))

    effects.append(_set('threats', trial_id, '/active', False))
    return RuleResult(effects, {'trial_id': trial_id, 'recipe_id': recipe_id, 'resolved_by': actor_id})
