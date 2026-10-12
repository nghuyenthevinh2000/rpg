"""Covenant Broken core rules: action dispatch, derivation, periodic fallout, and invariant validation."""
import copy
from engine.contracts import RuleError, RuleResult, safe_id
from .calendar import calendar_effects, validate_calendar
from .resources import periodic_resources, resolve_production, validate_resources
from .trials import resolve_trial, validate_trials

LEGACY_METADATA_KEYS = {'max_agency', 'max_vitality', 'max_clarity', 'max_neural_strain', 'max_dissonance'}


def _set(collection, identity, path, value):
    return {'op': 'set', 'collection': collection, 'entity_id': identity, 'path': path, 'value': value}


def _shape(action, required, optional=()):
    if not set(required) <= set(action) or set(action) - set(required) - set(optional):
        raise RuleError('action_shape', f'Required {required}; optional {optional}; no extra fields')
    if not all(isinstance(value, str) and value for value in action.values()):
        raise RuleError('action_shape', 'Action values must be nonempty strings')


def resolve(ctx, event):
    violations = (validate_resources(ctx) + validate_calendar(ctx) + validate_trials(ctx))
    if violations:
        code = violations[0].get('code', 'resource_config')
        raise RuleError(code, 'Invalid configuration', violations)

    action = event['action']
    kind = action['type']
    loc_doc = ctx.definitions.get('locations') or {}
    locations = {loc['id']: loc for loc in loc_doc.get('locations', [])}

    if kind == 'produce':
        return resolve_production(ctx, event)
    if kind == 'resolve_trial':
        return resolve_trial(ctx, event)

    if kind == 'introduce_threat':
        _shape(action, ('type', 'template_id', 'location_id'))
        rules_doc = ctx.definitions.get('rules') or {}
        templates = rules_doc.get('templates', {})
        gm = ctx.definitions.get('gm') or {}
        pool = gm.get('disaster_pool', []) + gm.get('improvisation_templates', [])
        source = next((t for t in pool if t.get('id') == action['template_id'] or t.get('template_id') == action['template_id']), None)
        template = templates.get(action['template_id'])
        if source is None or template is None or action['location_id'] not in locations:
            raise RuleError('invalid_template', 'Configured GM template and valid location required')
        if 'location_id' in template:
            if not template['location_id']:
                raise RuleError('invalid_template', 'Template location_id must not be empty')
            if action['location_id'] != template['location_id']:
                raise RuleError('invalid_location', 'Introduction location must match template location')
        elif not any(tag in ('hostile', 'hazard', 'dissonance') for tag in template.get('tags', [])):
            raise RuleError('invalid_template', 'Peaceful template must author an authorized location_id')
        identity = event['event_id']
        data = {
            'name': source['name'],
            'location_id': action['location_id'],
            'active': True,
            'activation_turn': ctx.turn + 1,
            'tags': template.get('tags', ['hazard']),
            'stats': template.get('stats', {'health': 0, 'armor': 0, 'retaliation': 0}),
            'metadata': {'template_id': action['template_id'], 'narrative': source}
        }
        return RuleResult([{'op': 'create', 'collection': 'threats', 'entity_id': identity, 'value': data}], {'threat_id': identity})

    actions_doc = ctx.definitions.get('actions') or {}
    action_defs = actions_doc.get('action_templates', {})
    if kind in action_defs:
        return _resolve_dilemma_action(ctx, event, kind, action_defs[kind])

    if kind not in ('move', 'wait'):
        raise RuleError('unsupported_action', f'Unsupported action type: {kind}')

    required = ('type', 'actor_id', 'location_id') if kind == 'move' else ('type', 'actor_id')
    _shape(action, required)
    actor = ctx.state.get('characters', action['actor_id'])
    if actor is None or actor['data']['status'] != 'alive':
        raise RuleError('invalid_actor', 'A living actor is required')
    if kind == 'wait':
        return RuleResult()

    current, target = actor['data']['location_id'], action['location_id']
    if target not in locations or (target not in locations[current].get('connected_to', []) and current not in locations[target].get('connected_to', [])):
        raise RuleError('unconnected_location', 'Movement follows undirected authored edges; no teleport')
    return RuleResult([_set('characters', actor['id'], '/location_id', target)], {'location_id': target})


def _resolve_dilemma_action(ctx, event, kind, action_template):
    action = event['action']
    _shape(action, ('type', 'actor_id'))
    actor = ctx.state.get('characters', action['actor_id'])
    if actor is None or actor['data']['status'] != 'alive':
        raise RuleError('invalid_actor', 'A living actor is required')

    data = actor['data']
    derived = derive(ctx, f"characters/{actor['id']}")
    effective_stats = derived.get('stats', {})

    conditions = action_template.get('conditions_required', {})
    if 'agency_required' in conditions and effective_stats.get('agency', 0) < conditions['agency_required']:
        raise RuleError('insufficient_agency', f"Requires agency >= {conditions['agency_required']}")
    if 'clarity_required' in conditions and effective_stats.get('clarity', 0) < conditions['clarity_required']:
        raise RuleError('insufficient_clarity', f"Requires clarity >= {conditions['clarity_required']}")
    if 'dissonance_cost' in conditions and effective_stats.get('dissonance', 0) < conditions['dissonance_cost']:
        raise RuleError('insufficient_dissonance', f"Requires dissonance >= {conditions['dissonance_cost']}")
    if 'dissonance_tolerance' in conditions and effective_stats.get('dissonance', 0) > conditions['dissonance_tolerance']:
        raise RuleError('dissonance_exceeded', f"Requires dissonance <= {conditions['dissonance_tolerance']}")
    if 'trait_required' in conditions and conditions['trait_required'] not in data.get('traits', []):
        raise RuleError('missing_trait', f"Requires trait {conditions['trait_required']}")
    if 'trait_compatibility' in conditions and conditions['trait_compatibility'] not in data.get('traits', []):
        raise RuleError('incompatible_trait', f"Requires trait {conditions['trait_compatibility']}")
    if 'required_items' in conditions:
        owned = set(data.get('equipment', [])) | set(data.get('inventory', []))
        for item_id in conditions['required_items']:
            if item_id not in owned:
                raise RuleError('missing_item', f"Requires item {item_id}")

    trade_offs = action_template.get('trade_offs', {})
    rules_doc = ctx.definitions.get('rules') or {}
    bounds = rules_doc.get('bounds', {})

    stat_deltas = {}
    if 'agency_loss' in trade_offs:
        stat_deltas['agency'] = stat_deltas.get('agency', 0) - trade_offs['agency_loss']
    if 'agency_gain' in trade_offs:
        stat_deltas['agency'] = stat_deltas.get('agency', 0) + trade_offs['agency_gain']
    if 'clarity_gain' in trade_offs:
        stat_deltas['clarity'] = stat_deltas.get('clarity', 0) + trade_offs['clarity_gain']
    if 'neural_strain_increase' in trade_offs:
        stat_deltas['neural_strain'] = stat_deltas.get('neural_strain', 0) + trade_offs['neural_strain_increase']
    if 'dissonance_risk' in trade_offs:
        stat_deltas['dissonance'] = stat_deltas.get('dissonance', 0) + trade_offs['dissonance_risk']
    if 'dissonance_increase' in trade_offs:
        stat_deltas['dissonance'] = stat_deltas.get('dissonance', 0) + trade_offs['dissonance_increase']

    effects = []
    new_stats = copy.deepcopy(data.get('stats', {}))
    for stat_name, delta in stat_deltas.items():
        base = new_stats.get(stat_name, 0)
        updated = base + delta
        if stat_name in bounds:
            lo, hi = bounds[stat_name]
            updated = max(lo, min(hi, updated))
        new_stats[stat_name] = updated
        effects.append(_set('characters', actor['id'], f'/stats/{stat_name}', updated))

    if 'biological_vitality_cost' in conditions:
        vit_cost = conditions['biological_vitality_cost']
        old_vit = new_stats.get('biological_vitality', data['health'] or 0)
        new_vit = max(0, old_vit - vit_cost)
        new_stats['biological_vitality'] = new_vit
        effects.append(_set('characters', actor['id'], '/stats/biological_vitality', new_vit))
        if data['health'] is not None and not data['capabilities']['cannot_die']:
            new_health = max(0, data['health'] - vit_cost)
            effects.append(_set('characters', actor['id'], '/health', new_health))
            if new_health == 0:
                effects.append(_set('characters', actor['id'], '/status', 'dead'))

    return RuleResult(effects, {
        'action_type': kind,
        'actor_id': actor['id'],
        'stat_deltas': stat_deltas,
        'consequence': action_template.get('consequence_on_completion', '')
    })


def _damage(character, damage):
    data = character['data']
    if data['status'] == 'dead' or data['health'] is None or data['capabilities']['cannot_die']:
        return []
    health = max(0, data['health'] - damage)
    return [_set('characters', character['id'], '/health', health),
            _set('characters', character['id'], '/status', 'dead' if health == 0 else 'alive')]


def after_turn(ctx, event, outcome):
    res = periodic_resources(ctx)
    effects = list(res.effects)
    fallout_outcomes = []

    # Environmental hazards per location
    hazard_threats = {t['data'].get('location_id'): t for t in ctx.state.list('threats')
                      if t['data'].get('active') and t['data'].get('activation_turn', 0) <= ctx.turn
                      and any(tag in ('hazard', 'environmental', 'dissonance', 'silicon_fallout') for tag in t['data'].get('tags', []))}

    for character in ctx.state.list('characters'):
        data = character['data']
        if data['status'] != 'alive':
            continue

        loc_id = data.get('location_id')
        loc_threat = hazard_threats.get(loc_id)
        has_chimera = 'trait_chimera_graft' in data.get('traits', [])
        has_consensus = 'trait_consensus_tether' in data.get('traits', [])

        # Apply periodic strain or decay
        strain_inc = 0
        vitality_dmg = 0

        if loc_threat is not None:
            tags = loc_threat['data'].get('tags', [])
            if 'silicon_fallout' in tags or 'hazard' in tags:
                vitality_dmg += 10
            if 'dissonance' in tags:
                strain_inc += 10

        if has_chimera:
            strain_inc += 5
            vitality_dmg += 5

        if has_consensus:
            strain_inc += 5

        if strain_inc > 0 and 'neural_strain' in data.get('stats', {}):
            curr_strain = data['stats']['neural_strain']
            rules_doc = ctx.definitions.get('rules') or {}
            hi = rules_doc.get('bounds', {}).get('neural_strain', [0, 100])[1]
            new_strain = min(hi, curr_strain + strain_inc)
            effects.append(_set('characters', character['id'], '/stats/neural_strain', new_strain))

        if vitality_dmg > 0:
            effects.extend(_damage(character, vitality_dmg))

        if strain_inc > 0 or vitality_dmg > 0:
            fallout_outcomes.append({
                'actor_id': character['id'],
                'strain_increase': strain_inc,
                'vitality_damage': vitality_dmg
            })

    effects.extend(calendar_effects(ctx))
    return RuleResult(effects, {**res.outcomes, 'environmental_fallout': fallout_outcomes})


def derive(ctx, entity_ref):
    collection, identity = entity_ref.split('/')
    entity = ctx.state.get(collection, identity)
    if collection != 'characters' or entity is None:
        return {}

    data = entity['data']
    rules = ctx.definitions.get('rules') or {}
    traits_doc = ctx.definitions.get('traits') or {}
    traits_def = traits_doc.get('traits', {})
    equip_doc = ctx.definitions.get('equipment') or {}
    equip_def = equip_doc.get('items', {})

    current_mods = {}
    legacy_mods = {}
    multiplier = 1.0

    for tid in data.get('traits', []):
        t_entry = traits_def.get(tid, {})
        for stat, val in t_entry.get('stat_modifiers', {}).items():
            if stat in LEGACY_METADATA_KEYS or stat.startswith('max_'):
                legacy_mods[stat] = legacy_mods.get(stat, 0) + val
            else:
                current_mods[stat] = current_mods.get(stat, 0) + val
        multiplier *= t_entry.get('impact_rules', {}).get('strike_kinetic_multiplier', 1.0)

    for eqid in data.get('equipment', []):
        e_entry = equip_def.get(eqid, {})
        for stat, val in e_entry.get('stat_modifiers', {}).items():
            if stat in LEGACY_METADATA_KEYS or stat.startswith('max_'):
                legacy_mods[stat] = legacy_mods.get(stat, 0) + val
            else:
                current_mods[stat] = current_mods.get(stat, 0) + val
        multiplier *= e_entry.get('impact_rules', {}).get('strike_kinetic_multiplier', 1.0)

    bounds = rules.get('bounds', {})
    effective = {}
    base_stats = data.get('stats', {})
    baseline_stats = data.get('baseline', {}).get('stats', {})
    baseline_mods = data.get('baseline', {}).get('modifiers', {})

    for stat, base in base_stats.items():
        value = base + current_mods.get(stat, 0) - baseline_mods.get(stat, 0)
        if stat in bounds:
            low, high = bounds[stat]
            baseline_val = baseline_stats.get(stat, base)
            value = min(max(high, baseline_val), max(min(low, baseline_val), value))
        effective[stat] = value

    bounds_exceptions = {}
    for stat, val in effective.items():
        if stat in bounds:
            lo, hi = bounds[stat]
            if not (lo <= val <= hi):
                bounds_exceptions[stat] = {'value': val, 'bounds': bounds[stat]}

    kinetic_formula = traits_doc.get('kinetic_formula', {'base_strike_damage': 5.0, 'vitality_ratio_scale': 0.2})
    vitality = rules.get('immortal_kinetic_vitality', 100) if data.get('capabilities', {}).get('cannot_die') else (data.get('health') or effective.get('biological_vitality', 0))
    kinetic = (kinetic_formula.get('base_strike_damage', 5.0) + vitality * kinetic_formula.get('vitality_ratio_scale', 0.2)) * multiplier

    audit = {
        'static': copy.deepcopy(base_stats),
        'baseline_modifiers': copy.deepcopy(baseline_mods),
        'current_modifiers': current_mods,
        'effective_values': effective,
        'legacy_metadata_modifiers': legacy_mods,
        'health': data.get('health'),
        'bounds_exceptions': bounds_exceptions
    }

    return {
        'stats': effective,
        'health': data.get('health'),
        'punch_kinetic_impact': round(kinetic, 2),
        'audit': audit
    }


def validate(ctx):
    violations = (validate_resources(ctx) + validate_calendar(ctx) + validate_trials(ctx))
    traits_doc = ctx.definitions.get('traits') or {}
    traits_def = traits_doc.get('traits', {})
    equip_doc = ctx.definitions.get('equipment') or {}
    equip_def = equip_doc.get('items', {})
    loc_doc = ctx.definitions.get('locations') or {}
    locations = {loc['id'] for loc in loc_doc.get('locations', [])}
    legacy = ctx.state.get('baseline', 'legacy')
    inventory_registry = legacy['data']['metadata']['inventory_registry'] if legacy and 'metadata' in legacy.get('data', {}) and 'inventory_registry' in legacy['data']['metadata'] else {}

    for character in ctx.state.list('characters'):
        data = character['data']
        # Mortality check
        if (data.get('status') == 'dead' and data.get('health') != 0) or (data.get('health') == 0 and data.get('status') == 'alive' and not data.get('capabilities', {}).get('cannot_die')):
            violations.append({'id': character['id'], 'code': 'mortality', 'message': 'Dead characters must have 0 health; 0 health characters must be dead unless cannot_die'})

        # References check
        if any(t not in traits_def for t in data.get('traits', [])) or \
           any(e not in equip_def for e in data.get('equipment', [])) or \
           any(i not in equip_def and i not in inventory_registry for i in data.get('inventory', [])):
            violations.append({'id': character['id'], 'code': 'broken_character_reference', 'message': 'Character references unregistered trait, equipment, or inventory'})

        # Location check
        if data.get('location_id') not in locations:
            violations.append({'id': character['id'], 'code': 'invalid_location', 'message': f"Character location {data.get('location_id')} not in world locations"})

    return violations
