"""Lost World: connected movement and explicitly tagged, location-scoped cold."""
from engine.contracts import RuleError, RuleResult


def _set(collection, identity, path, value):
    return {'op': 'set', 'collection': collection, 'entity_id': identity, 'path': path, 'value': value}


def _shape(action, required):
    if set(action) != set(required):
        raise RuleError('action_shape', f'Action fields must be {sorted(required)}')
    if not all(isinstance(v, str) and v for v in action.values()):
        raise RuleError('action_shape', 'Action values must be nonempty strings')


def resolve(ctx, event):
    action = event['action']
    kind = action['type']
    locations = {loc['id']: loc for loc in ctx.definitions.get('locations')['locations']}
    if kind == 'introduce_threat':
        _shape(action, ('type', 'template_id', 'location_id'))
        templates = ctx.definitions.get('rules')['templates']
        pool = ctx.definitions.get('gm').get('disaster_pool', []) + ctx.definitions.get('gm').get('improvisation_templates', [])
        source = next((t for t in pool if t['id'] == action['template_id']), None)
        template = templates.get(action['template_id'])
        if source is None or template is None or action['location_id'] not in locations:
            raise RuleError('invalid_template', 'Configured GM template and valid location required')
        identity = event['event_id']
        data = {'name': source['name'], 'location_id': action['location_id'], 'active': True,
                'activation_turn': ctx.turn + 1, 'tags': template['tags'], 'stats': template['stats'],
                'metadata': {'template_id': action['template_id'], 'narrative': source}}
        return RuleResult([{'op':'create', 'collection':'threats', 'entity_id':identity, 'value':data}], {'threat_id':identity})
    if kind not in ('move', 'wait'):
        raise RuleError('unsupported_action', 'Supported: move, wait, introduce_threat; legacy updates require migration')
    _shape(action, ('type', 'actor_id', 'location_id') if kind == 'move' else ('type', 'actor_id'))
    actor = ctx.state.get('characters', action['actor_id'])
    if actor is None or actor['data']['status'] != 'alive':
        raise RuleError('invalid_actor', 'A living actor is required')
    if kind == 'wait':
        return RuleResult()
    current, target = actor['data']['location_id'], action['location_id']
    if target not in locations or (target not in locations[current].get('connected_to', []) and current not in locations[target].get('connected_to', [])):
        raise RuleError('unconnected_location', 'Movement follows undirected authored edges; no teleport')
    return RuleResult([_set('characters', actor['id'], '/location_id', target)], {'location_id':target})


def _damage(character, damage):
    data = character['data']
    if data['status'] == 'dead' or data['health'] is None or data['capabilities']['cannot_die']:
        return []
    health = max(0, data['health'] - damage)
    return [_set('characters', character['id'], '/health', health),
            _set('characters', character['id'], '/status', 'dead' if health == 0 else 'alive')]


def after_turn(ctx, event, outcome):
    rules = ctx.definitions.get('rules')['cold']
    gm_trait = next(t for t in ctx.definitions.get('gm')['traits'] if t['trait_id'] == rules['miracle_trait_id'])
    traits = ctx.definitions.get('traits')['traits']
    effects, outcomes = [], []
    # Multiple cold hazards at a location expose each living character only once.
    affected = {t['data'].get('location_id') for t in ctx.state.list('threats')
                if t['data']['active'] and 'cold' in t['data']['tags'] and t['data']['activation_turn'] <= ctx.turn}
    for character in ctx.state.list('characters'):
        data = character['data']
        if data['status'] != 'alive' or data['health'] is None or data['location_id'] not in affected:
            continue
        row = {'actor_id': character['id'], 'before': data['health'], 'after': data['health']}
        if data['capabilities']['cannot_die']:
            row['result'] = 'immune'
        else:
            miracle_roll = ctx.rng.random(); row['miracle_roll'] = miracle_roll
            if miracle_roll < gm_trait['miracle_probability']:
                row['result'] = 'miracle'
            else:
                damage = rules['damage']
                row['result'] = 'exposed'
                if rules['survival_trait_id'] in data['traits']:
                    roll = ctx.rng.random(); row['survival_roll'] = roll
                    failure = traits[rules['survival_trait_id']].get('failure_probability', gm_trait['trait_failure_law']['default_trait_failure_probability'])
                    if roll < failure:
                        damage = rules['failed_damage']; row['result'] = 'survival_failed'
                    else:
                        after = min(data['health'], max(rules['survival_floor'], data['health'] - damage))
                        damage = data['health'] - after; row['result'] = 'survived'
                row['after'] = max(0, data['health'] - damage)
                effects.extend(_damage(character, damage))
        outcomes.append(row)
    return RuleResult(effects, {'cold': outcomes})


def derive(ctx, entity_ref):
    collection, identity = entity_ref.split('/')
    entity = ctx.state.get(collection, identity)
    if collection != 'characters' or entity is None:
        return {}
    data = entity['data']; config = ctx.definitions.get('rules')
    traits = ctx.definitions.get('traits')
    totals, multiplier = {}, 1.0
    for identity in data['traits']:
        trait = traits['traits'][identity]
        for stat, value in trait.get('stat_modifiers', {}).items():
            if not stat.startswith('max_'):
                totals[stat] = totals.get(stat, 0) + value
        multiplier *= trait.get('impact_rules', {}).get('strike_kinetic_multiplier', 1)
    effective = {}
    for stat, base in data['stats'].items():
        value = base + totals.get(stat, 0) - data['baseline']['modifiers'].get(stat, 0)
        if stat in config['bounds']:
            low, high = config['bounds'][stat]; baseline = data['baseline']['stats'][stat]
            value = min(max(high, baseline), max(min(low, baseline), value))
        effective[stat] = value
    formula = traits['kinetic_formula']
    vitality = config['immortal_kinetic_vitality'] if data['capabilities']['cannot_die'] else (data['health'] or 0)
    kinetic = (formula['base_punch_damage'] + vitality * formula['vitality_ratio_scale']) * multiplier
    return {'stats': effective, 'health': data['health'], 'punch_kinetic_impact': round(kinetic, 2)}


def validate(ctx):
    violations = []
    registry = ctx.definitions.get('traits')['traits']
    legacy = ctx.state.get('baseline', 'legacy')
    inventory = legacy['data']['metadata']['inventory_registry'] if legacy else {}
    for character in ctx.state.list('characters'):
        data = character['data']
        if (data['status'] == 'dead' and data['health'] != 0) or (data['health'] == 0 and data['status'] == 'alive' and not data['capabilities']['cannot_die']):
            violations.append({'id':character['id'], 'code':'mortality'})
        if any(t not in registry for t in data['traits']) or data['equipment'] or any(i not in inventory for i in data['inventory']):
            violations.append({'id':character['id'], 'code':'broken_character_reference'})
    return violations
