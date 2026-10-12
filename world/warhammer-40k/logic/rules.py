from engine.contracts import RuleError, RuleResult
from .calendar import calendar_effects, validate_calendar
from .combat import resolve_attack
from .inventory import audit_character, resolve_inventory
from .projects import PROJECT_ACTIONS, resolve_project, validate_projects
from .resources import periodic_resources, resolve_production, validate_resources
from .treatment import resolve_treatment, validate_treatment
from .trials import resolve_trial, validate_trials


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
    violations = (validate_resources(ctx) + validate_projects(ctx) +
                  validate_calendar(ctx) + validate_trials(ctx) +
                  validate_treatment(ctx))
    if violations:
        code = violations[0].get('code', 'resource_config')
        raise RuleError(code, 'Invalid configuration', violations)
    action = event['action']; kind = action['type']; rules = ctx.definitions.get('rules')
    if kind in PROJECT_ACTIONS:
        return resolve_project(ctx, event)
    if kind == 'produce':
        return resolve_production(ctx, event)
    if kind in ('equip', 'unequip'):
        return resolve_inventory(ctx, event)
    if kind in ('heal', 'restore_life'):
        return resolve_treatment(ctx, event)
    if kind == 'resolve_trial':
        return resolve_trial(ctx, event)
    locations = {l['id']: l for l in ctx.definitions.get('locations')['locations']}
    if kind == 'attack' and _sanctuary(ctx):
        raise RuleError('sanctuary', 'Current structural sanctuary prohibits combat; stale templates do not authorize hostility')
    if kind == 'introduce_threat':
        _shape(action, ('type','template_id','location_id'))
        gm = ctx.definitions.get('gm')
        pool = gm.get('disaster_pool', []) + gm.get('improvisation_templates', [])
        source = next((t for t in pool if t['id'] == action['template_id']), None)
        template = rules['templates'].get(action['template_id'])
        if source is None or template is None or action['location_id'] not in locations:
            raise RuleError('invalid_template', 'Configured GM template and valid location required')
        if _sanctuary(ctx) and any(tag in ('hostile', 'cold') for tag in template.get('tags', [])):
            raise RuleError('sanctuary', 'Current structural sanctuary prohibits hostile and cold GM introductions')
        if 'location_id' in template:
            if not template['location_id']:
                raise RuleError('invalid_template', 'Template location_id must not be empty')
            if action['location_id'] != template['location_id']:
                raise RuleError('invalid_location', 'Introduction location must match template location')
        elif not any(tag in ('hostile', 'cold') for tag in template.get('tags', [])):
            raise RuleError('invalid_template', 'Peaceful template must author an authorized location_id')
        data = {'name':source['name'], 'location_id':action['location_id'], 'active':True, 'activation_turn':ctx.turn+1,
                'tags':template['tags'], 'stats':template['stats'], 'metadata':{'template_id':action['template_id'], 'narrative':source}}
        return RuleResult([{'op':'create','collection':'threats','entity_id':event['event_id'],'value':data}], {'threat_id':event['event_id']})
    if kind not in ('move','wait','attack'):
        raise RuleError('unsupported_action', 'Supported: move, wait, attack, introduce_threat; legacy updates require migration')
    if kind == 'attack':
        return resolve_attack(ctx, event, derive)
    required = ('type','actor_id','location_id') if kind == 'move' else ('type','actor_id')
    _shape(action, required)
    actor = ctx.state.get('characters', action['actor_id'])
    if actor is None or actor['data']['status'] != 'alive':
        raise RuleError('invalid_actor', 'A living actor is required')
    if kind == 'wait':
        return RuleResult()
    current = actor['data']['location_id']
    target = action['location_id']
    if target not in locations or (target not in locations[current].get('connected_to', []) and current not in locations[target].get('connected_to', [])):
        raise RuleError('unconnected_location', 'Movement follows undirected authored edges; no teleport')
    return RuleResult([_set('characters',actor['id'],'/location_id',target)], {'location_id':target})


def after_turn(ctx, event, outcome):
    res = periodic_resources(ctx)  # Reads action overlay; never repeats retaliation.
    res.effects.extend(calendar_effects(ctx))
    return res


def derive(ctx, entity_ref):
    collection, identity = entity_ref.split('/')
    entity = ctx.state.get(collection, identity)
    if collection != 'characters' or entity is None:
        return {}
    data = entity['data']; rules = ctx.definitions.get('rules'); traits = ctx.definitions.get('traits')
    totals, multiplier = {}, 1.0
    for registry, identities in ((traits['traits'], data['traits']), (ctx.definitions.get('equipment')['items'], data['equipment'])):
        for item_id in identities:
            entry = registry[item_id]
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
    return {'stats':stats, 'health':data['health'], 'punch_kinetic_impact':round(kinetic, 2), 'audit':audit_character(ctx, identity)}


def validate(ctx):
    violations = (validate_resources(ctx) + validate_projects(ctx) +
                  validate_calendar(ctx) + validate_trials(ctx) +
                  validate_treatment(ctx))
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
