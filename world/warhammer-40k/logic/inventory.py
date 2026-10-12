"""Possession-aware equipment, audit, and trait rewards."""
from engine.contracts import RuleError, RuleResult, safe_id


def _set(collection, identity, path, value):
    return {'op': 'set', 'collection': collection, 'entity_id': identity, 'path': path, 'value': value}


def resolve_inventory(ctx, event):
    action = event['action']
    kind = action['type']
    if kind not in ('equip', 'unequip'):
        raise RuleError('unsupported_action', 'Unsupported inventory action')
    if set(action) != {'type', 'actor_id', 'item_id'}:
        raise RuleError('action_shape', 'Exact fields required: type, actor_id, item_id')
    for val in action.values():
        if not isinstance(val, str) or not val:
            raise RuleError('action_shape', 'Action values must be nonempty strings')
        safe_id(val)
    actor_id, item_id = action['actor_id'], action['item_id']
    actor = ctx.state.get('characters', actor_id)
    if actor is None or actor['data']['status'] != 'alive':
        raise RuleError('invalid_actor', 'Living character required')
    data = actor['data']
    equipment_items = ctx.definitions.get('equipment')
    if equipment_items is None or 'items' not in equipment_items:
        raise RuleError('unsupported_action', 'World does not support mechanical equipment')
    items = equipment_items['items']
    if item_id not in items:
        raise RuleError('unknown_item', f'Item {item_id} not recognized in equipment registry')
    item_spec = items[item_id]
    slot = item_spec.get('slot')
    if not slot:
        raise RuleError('invalid_item_slot', f'Item {item_id} does not define a mechanical slot')
    equipment = list(data.get('equipment', []))
    inventory = list(data.get('inventory', []))

    if kind == 'equip':
        if item_id not in inventory:
            raise RuleError('not_in_inventory', f'Character does not possess {item_id} in inventory')
        if item_id in equipment:
            raise RuleError('already_equipped', f'Item {item_id} is already equipped')
        # Check occupied slot
        for equipped_id in equipment:
            if equipped_id in items and items[equipped_id].get('slot') == slot:
                raise RuleError('slot_occupied', f'Slot {slot} is already occupied by {equipped_id}')
        new_inv = [i for i in inventory if i != item_id]
        new_equip = sorted(set(equipment + [item_id]))
        effects = [
            _set('characters', actor_id, '/inventory', new_inv),
            _set('characters', actor_id, '/equipment', new_equip)
        ]
        return RuleResult(effects, {'action': 'equip', 'actor_id': actor_id, 'item_id': item_id, 'slot': slot})

    elif kind == 'unequip':
        if item_id not in equipment:
            raise RuleError('not_equipped', f'Item {item_id} is not currently equipped')
        new_equip = [i for i in equipment if i != item_id]
        new_inv = sorted(set(inventory + [item_id]))
        effects = [
            _set('characters', actor_id, '/equipment', new_equip),
            _set('characters', actor_id, '/inventory', new_inv)
        ]
        return RuleResult(effects, {'action': 'unequip', 'actor_id': actor_id, 'item_id': item_id, 'slot': slot})


import math
from .resources import _number

LEGACY_METADATA_KEYS = {'physical_vitality', 'max_agency', 'max_agility', 'max_clarity', 'max_psychic', 'max_strength', 'max_vitality'}


def _finite_number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


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


def audit_character(ctx, character_id):
    char = ctx.state.get('characters', character_id)
    if not char:
        return {}
    d = char['data']
    rules = ctx.definitions.get('rules')
    traits_doc = ctx.definitions.get('traits')
    traits_def = traits_doc.get('traits', {}) if traits_doc else {}
    equip_doc = ctx.definitions.get('equipment')
    equip_def = equip_doc.get('items', {}) if equip_doc else {}

    current_mods = {}
    legacy_mods = {}
    for tid in d.get('traits', []):
        for stat, val in traits_def.get(tid, {}).get('stat_modifiers', {}).items():
            if stat in LEGACY_METADATA_KEYS or stat.startswith('max_'):
                legacy_mods[stat] = legacy_mods.get(stat, 0) + val
            else:
                current_mods[stat] = current_mods.get(stat, 0) + val
    for eqid in d.get('equipment', []):
        for stat, val in equip_def.get(eqid, {}).get('stat_modifiers', {}).items():
            if stat in LEGACY_METADATA_KEYS or stat.startswith('max_'):
                legacy_mods[stat] = legacy_mods.get(stat, 0) + val
            else:
                current_mods[stat] = current_mods.get(stat, 0) + val

    # Effective stats
    derived_stats = {}
    multiplier = 1.0
    for tid in d.get('traits', []):
        multiplier *= traits_def.get(tid, {}).get('impact_rules', {}).get('strike_kinetic_multiplier', 1)
    for eqid in d.get('equipment', []):
        multiplier *= equip_def.get(eqid, {}).get('impact_rules', {}).get('strike_kinetic_multiplier', 1)

    bounds = rules.get('bounds', {})
    for stat, base in d['stats'].items():
        value = base + current_mods.get(stat, 0) - d['baseline']['modifiers'].get(stat, 0)
        if stat in bounds:
            low, high = bounds[stat]
            baseline = d['baseline']['stats'].get(stat, value)
            value = min(max(high, baseline), max(min(low, baseline), value))
        derived_stats[stat] = value

    bounds_exceptions = {}
    for stat, val in derived_stats.items():
        if stat in bounds:
            lo, hi = bounds[stat]
            if not (lo <= val <= hi):
                bounds_exceptions[stat] = {'value': val, 'bounds': bounds[stat]}

    return {
        'static': copy_dict(d.get('stats', {})),
        'baseline_modifiers': copy_dict(d.get('baseline', {}).get('modifiers', {})),
        'current_modifiers': current_mods,
        'effective_values': derived_stats,
        'legacy_metadata_modifiers': legacy_mods,
        'health': d.get('health'),
        'bounds_exceptions': bounds_exceptions
    }


def copy_dict(d):
    return {k: v for k, v in d.items()}
