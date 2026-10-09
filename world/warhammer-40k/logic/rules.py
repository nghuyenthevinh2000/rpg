"""Warhammer: sanctuary-aware movement/combat; final retaliation on killing blow."""
from engine.contracts import RuleError, RuleResult


def _set(collection, identity, path, value):
    return {'op':'set', 'collection':collection, 'entity_id':identity, 'path':path, 'value':value}


def _shape(action, required, optional=()):
    if not set(required) <= set(action) or set(action) - set(required) - set(optional):
        raise RuleError('action_shape', f'Required {required}; optional {optional}; no extra fields')
    if not all(isinstance(value, str) and value for value in action.values()):
        raise RuleError('action_shape', 'Action values must be nonempty strings')


def _sanctuary(ctx):
    # Authored combat copies must change BOTH policy and structural lore.
    return ctx.definitions.get('rules')['sanctuary'] or ctx.definitions.get('world')['structural_rules'].get('transcendent_sanctuary', False)


def resolve(ctx, event):
    action = event['action']; kind = action['type']; rules = ctx.definitions.get('rules')
    locations = {l['id']: l for l in ctx.definitions.get('locations')['locations']}
    if kind in ('attack', 'introduce_threat') and _sanctuary(ctx):
        raise RuleError('sanctuary', 'Current structural sanctuary prohibits combat and hostile GM introductions; stale templates do not authorize hostility')
    if kind == 'introduce_threat':
        _shape(action, ('type','template_id','location_id'))
        gm = ctx.definitions.get('gm')
        pool = gm.get('disaster_pool', []) + gm.get('improvisation_templates', [])
        source = next((t for t in pool if t['id'] == action['template_id']), None)
        template = rules['templates'].get(action['template_id'])
        if source is None or template is None or action['location_id'] not in locations:
            raise RuleError('invalid_template', 'Configured GM template and valid location required')
        data = {'name':source['name'], 'location_id':action['location_id'], 'active':True, 'activation_turn':ctx.turn+1,
                'tags':template['tags'], 'stats':template['stats'], 'metadata':{'template_id':action['template_id'], 'narrative':source}}
        return RuleResult([{'op':'create','collection':'threats','entity_id':event['event_id'],'value':data}], {'threat_id':event['event_id']})
    if kind not in ('move','wait','attack'):
        raise RuleError('unsupported_action', 'Supported: move, wait, attack, introduce_threat; legacy updates require migration')
    required = ('type','actor_id','location_id') if kind == 'move' else ('type','actor_id','target_id','weapon_id') if kind == 'attack' else ('type','actor_id')
    _shape(action, required, ('resource_id',) if kind == 'attack' else ())
    actor = ctx.state.get('characters', action['actor_id'])
    if actor is None or actor['data']['status'] != 'alive':
        raise RuleError('invalid_actor', 'A living actor is required')
    if kind == 'wait':
        return RuleResult()
    current = actor['data']['location_id']
    if kind == 'move':
        target = action['location_id']
        if target not in locations or (target not in locations[current].get('connected_to', []) and current not in locations[target].get('connected_to', [])):
            raise RuleError('unconnected_location', 'Movement follows undirected authored edges; no teleport')
        return RuleResult([_set('characters',actor['id'],'/location_id',target)], {'location_id':target})
    target = ctx.state.get('threats', action['target_id'])
    if target is None or not target['data']['active'] or target['data']['activation_turn'] > ctx.turn or target['data'].get('location_id') != current or target['data']['stats']['health'] <= 0:
        raise RuleError('invalid_target', 'Attack requires a co-located living active threat')
    weapon_id = action['weapon_id']
    equipment = ctx.definitions.get('equipment')['items']
    if weapon_id not in actor['data']['equipment'] or weapon_id not in equipment or weapon_id not in rules['weapons']:
        raise RuleError('invalid_weapon', 'A recognized equipped weapon with configured combat mechanics is required')
    weapon = rules['weapons'][weapon_id]; effects = []
    if 'ammo_id' in weapon:
        if action.get('resource_id') != weapon['ammo_id']:
            raise RuleError('ammunition', f'Resource must be {weapon["ammo_id"]}')
        resource = ctx.state.get('resources', action['resource_id'])
        if resource is None or resource['data'].get('quantity', 0) < weapon['ammo_cost']:
            raise RuleError('ammunition', 'Insufficient ammunition; entire turn rejected')
        effects.append(_set('resources', resource['id'], '/quantity', resource['data']['quantity'] - weapon['ammo_cost']))
    elif 'resource_id' in action:
        raise RuleError('ammunition', 'This weapon does not consume a resource')
    derived = derive(ctx, 'characters/' + actor['id'])
    kinetic = derived['punch_kinetic_impact']
    gross = weapon['power'] + kinetic * equipment[weapon_id].get('impact_rules', {}).get('strike_kinetic_multiplier', 1)
    armor = max(0, target['data']['stats']['armor'] - weapon['penetration'])
    damage = round(gross * (1 - armor), 2)
    remaining = max(0, target['data']['stats']['health'] - damage)
    effects.extend([_set('threats',target['id'],'/stats/health',remaining), _set('threats',target['id'],'/active',remaining > 0)])
    mitigation = max((rules['armor'].get(item, 0) for item in actor['data']['equipment']), default=0)
    retaliation = round(target['data']['stats']['retaliation'] * (1-mitigation), 2)
    health = actor['data']['health'] if actor['data']['capabilities']['cannot_die'] else max(0, actor['data']['health']-retaliation)
    effects.extend([_set('characters',actor['id'],'/health',health), _set('characters',actor['id'],'/status','dead' if health == 0 and not actor['data']['capabilities']['cannot_die'] else 'alive')])
    return RuleResult(effects, {'damage_dealt':damage, 'remaining_health':remaining, 'retaliations':1, 'retaliation_raw':target['data']['stats']['retaliation'], 'retaliation_damage':actor['data']['health']-health, 'armor_mitigation':mitigation})


def after_turn(ctx, event, outcome):
    return RuleResult()  # Combat retaliation belongs exclusively to resolve.


def derive(ctx, entity_ref):
    collection, identity = entity_ref.split('/')
    entity = ctx.state.get(collection, identity)
    if collection != 'characters' or entity is None:
        return {}
    data = entity['data']; rules = ctx.definitions.get('rules'); traits = ctx.definitions.get('traits')
    totals, multiplier = {}, 1.0
    for registry, identities in ((traits['traits'], data['traits']), (ctx.definitions.get('equipment')['items'], data['equipment'])):
        for identity in identities:
            entry = registry[identity]
            for stat, amount in entry.get('stat_modifiers', {}).items():
                if not stat.startswith('max_'):
                    totals[stat] = totals.get(stat, 0)+amount
            multiplier *= entry.get('impact_rules', {}).get('strike_kinetic_multiplier', 1)
    stats = {}
    for stat, base in data['stats'].items():
        value = base + totals.get(stat, 0) - data['baseline']['modifiers'].get(stat, 0)
        if stat in rules['bounds']:
            low, high = rules['bounds'][stat]; baseline = data['baseline']['stats'][stat]
            value = min(max(high, baseline), max(min(low, baseline), value))
        stats[stat] = value
    formula = traits['kinetic_formula']
    vitality = rules['immortal_kinetic_vitality'] if data['capabilities']['cannot_die'] else data['health']
    kinetic = (formula['base_punch_damage'] + stats.get('strength', 0)*formula['strength_ratio_scale'] + vitality*formula['vitality_ratio_scale']) * multiplier
    return {'stats':stats, 'health':data['health'], 'punch_kinetic_impact':round(kinetic, 2)}


def validate(ctx):
    violations = []
    traits, equipment = ctx.definitions.get('traits')['traits'], ctx.definitions.get('equipment')['items']
    legacy = ctx.state.get('baseline','legacy')
    inventory = legacy['data']['metadata']['inventory_registry'] if legacy else {}
    for character in ctx.state.list('characters'):
        d = character['data']
        if (d['status'] == 'dead' and d['health'] != 0) or (d['health'] == 0 and d['status'] == 'alive' and not d['capabilities']['cannot_die']):
            violations.append({'id':character['id'], 'code':'mortality'})
        if any(i not in traits for i in d['traits']) or any(i not in equipment for i in d['equipment']) or any(i not in inventory and i not in equipment for i in d['inventory']):
            violations.append({'id':character['id'], 'code':'broken_character_reference'})
    return violations
