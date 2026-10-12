import math
from engine.contracts import RuleError, safe_id

LEGACY_METADATA_KEYS = {'max_agency', 'max_vitality'}


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
            if key not in allowed_stats and key not in LEGACY_METADATA_KEYS:
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
            if key not in allowed_stats and key not in LEGACY_METADATA_KEYS:
                raise RuleError('unsupported_trait_stat', f'Trait {tid} has unsupported modifier key {key}')

    current = actor['data'].get('traits', [])
    new_traits = sorted(set(current) | set(trait_ids))
    if new_traits == sorted(current):
        return []
    return [_set('characters', actor_id, '/traits', new_traits)]
