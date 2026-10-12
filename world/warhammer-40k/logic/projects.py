"""Typed paid projects; historical action records remain read-only evidence."""
import hashlib
import json

from engine.contracts import RuleError, RuleResult, safe_id
from .resources import _number, _capacity

PROJECT_ACTIONS = {'start_project', 'deliver_materials', 'work_project',
                   'prepare_project_site', 'complete_project'}
TEMPLATE_FIELDS = {'name', 'hours_required', 'materials', 'credit_cost', 'credit_stat',
                   'fatigue_cost', 'conditions', 'site_ids', 'structural_requirements', 'resource_rewards'}
PREPARATIONS = {'sever_telemetry': {'telemetry_severed': True},
                'reject_drones': {'drones_rejected': True}}


def _hash(template):
    return hashlib.sha256(json.dumps(template, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _set(collection, identity, path, value):
    return {'op': 'set', 'collection': collection, 'entity_id': identity, 'path': path, 'value': value}


def _ids(values):
    if not isinstance(values, list) or len(values) != len(set(v for v in values if isinstance(v, str))):
        return False
    try:
        for value in values:
            safe_id(value)
    except RuleError:
        return False
    return True


def validate_projects(ctx):
    """Validate dormant authoring and final fulfillment without emitting effects."""
    rules = ctx.definitions.get('rules')
    templates = rules.get('project_templates', {})
    sites = rules.get('project_sites', {})
    recipes = rules.get('project_preparation_recipes', {})
    locations = {loc['id'] for loc in ctx.definitions.get('locations')['locations']}
    structural = ctx.definitions.get('world')['structural_rules']
    violations = []
    def bad(identity, message):
        violations.append({'id': identity, 'code': 'project_config', 'message': message})
    if not all(isinstance(registry, dict) for registry in (templates, sites, recipes)):
        bad('projects', 'project registries must be objects')
        return violations
    for identity, site in sites.items():
        if identity not in locations or not isinstance(site, dict) or set(site) != {'manual_work', 'template_ids'}:
            bad(identity, 'sites require authored location, manual_work and template_ids')
        elif type(site['manual_work']) is not bool or not _ids(site['template_ids']) or any(t not in templates for t in site['template_ids']):
            bad(identity, 'invalid site template references')
    for identity, recipe in recipes.items():
        if identity not in PREPARATIONS or not isinstance(recipe, dict) or set(recipe) != {'site_ids', 'resource_costs', 'conditions'}:
            bad(identity, 'only fixed site preparation recipes are supported')
            continue
        if recipe['conditions'] != PREPARATIONS[identity] or any(type(v) is not bool for v in recipe['conditions'].values()):
            bad(identity, 'preparation must set only its fixed boolean condition')
        if not _ids(recipe['site_ids']) or not recipe['site_ids'] or any(s not in sites or sites[s].get('manual_work') is not True for s in recipe['site_ids']):
            bad(identity, 'preparation requires registered manual sites')
        if recipe['resource_costs'] != {}:
            bad(identity, 'initial fixed preparations have no stock cost')
    for identity, template in templates.items():
        if not isinstance(template, dict) or set(template) != TEMPLATE_FIELDS:
            bad(identity, 'template fields must match the typed project policy')
            continue
        if not isinstance(template['name'], str) or not template['name']:
            bad(identity, 'template name required')
        if not _number(template['hours_required'], positive=True) or not _number(template['credit_cost']) or not _number(template['fatigue_cost']):
            bad(identity, 'project costs and hours must be finite nonnegative numbers; hours positive')
        if template['credit_stat'] not in (None, 'universal_dividend_balance') or (template['credit_cost'] and template['credit_stat'] is None):
            bad(identity, 'unsupported credit stat')
        if not _ids(template['site_ids']) or not template['site_ids'] or any(s not in sites or identity not in sites[s].get('template_ids', []) for s in template['site_ids']):
            bad(identity, 'template requires reciprocal site references')
        if not _ids(template['conditions']) or any(c not in {'telemetry_severed', 'drones_rejected'} for c in template['conditions']):
            bad(identity, 'unknown structural condition')
        requirements = template['structural_requirements']
        if not isinstance(requirements, dict) or any(k not in structural or type(v) is not bool for k, v in requirements.items()):
            bad(identity, 'structural requirements must reference actual named world booleans')
        for field in ('materials', 'resource_rewards'):
            amounts = template[field]
            if not isinstance(amounts, dict) or (field == 'materials' and not amounts):
                bad(identity, 'materials/rewards must be typed quantity maps')
                continue
            for resource_id, quantity in amounts.items():
                try:
                    safe_id(resource_id)
                except RuleError:
                    bad(identity, 'unsafe resource reference')
                    continue
                if not _number(quantity, positive=True):
                    bad(identity, 'material/reward quantities must be finite positive numbers')
                # Dormant materials need not mint new baseline stock. Rewards must exist.
                if field == 'resource_rewards':
                    stock = ctx.state.get('resources', resource_id)
                    if stock is None or not _number(_capacity(ctx, resource_id)):
                        bad(identity, 'rewards require existing bounded stocks')
    if violations:
        return violations
    seen = set()
    for project in ctx.state.list('actions'):
        data = project['data']
        if data.get('kind') != 'project':
            continue
        template = templates.get(data['template_id'])
        if template is None or data['template_sha256'] != _hash(template):
            bad(project['id'], 'project template fingerprint changed or missing')
            continue
        if not _number(data['hours_committed']) or data['hours_committed'] > template['hours_required']:
            bad(project['id'], 'labor outside template bounds')
        if set(data['materials_committed']) != set(template['materials']) or any(not _number(v) or v > template['materials'][k] for k, v in data['materials_committed'].items()):
            bad(project['id'], 'invalid committed materials')
        if set(data['conditions']) != set(template['conditions']) or any(type(v) is not bool for v in data['conditions'].values()):
            bad(project['id'], 'invalid runtime conditions')
        if data['completed'] != (data['status'] == 'completed'):
            bad(project['id'], 'completion and status disagree')
        if not _ids(data['participant_ids']) or not data['participant_ids'] or data['actor_id'] not in data['participant_ids'] or any(ctx.state.get('characters', p) is None for p in data['participant_ids']):
            bad(project['id'], 'invalid project participants')
        if data['location_id'] not in template['site_ids']:
            bad(project['id'], 'project outside authored sites')
        key = (data['template_id'], data['location_id'])
        if key in seen:
            bad(project['id'], 'duplicate template/site project')
        seen.add(key)
        if data['completed'] and (data['hours_committed'] != template['hours_required'] or data['materials_committed'] != template['materials'] or not all(data['conditions'].values())):
            bad(project['id'], 'completed project requirements unmet')
    return violations


def _site(ctx, template, location):
    rules = ctx.definitions.get('rules')
    site = rules['project_sites'].get(location)
    structural = ctx.definitions.get('world')['structural_rules']
    if location not in template['site_ids'] or site is None or any(structural.get(k) is not v for k, v in template['structural_requirements'].items()):
        raise RuleError('project_site', 'Current authored site and actual structural prerequisites required')
    if template['conditions'] and site['manual_work'] is not True:
        raise RuleError('project_site', 'Manual-work conditions require an authored manual site')


def _workers(ctx, participants, actor_id, location):
    if not _ids(participants) or not participants or actor_id not in participants:
        raise RuleError('project_participants', 'Unique participants including the actor required')
    workers = []
    for identity in participants:
        character = ctx.state.get('characters', identity)
        if character is None or character['data']['status'] != 'alive' or character['data']['location_id'] != location:
            raise RuleError('project_participants', 'Workers must be living and co-located')
        workers.append(character)
    return workers


def resolve_project(ctx, event):
    violations = validate_projects(ctx)
    if violations:
        raise RuleError('project_config', 'Invalid project configuration or fulfillment', violations)
    action = event['action']; kind = action['type']
    required = {'type', 'actor_id', 'project_id'}
    if kind == 'start_project': required |= {'template_id', 'participant_ids'}
    elif kind == 'deliver_materials': required |= {'resource_id', 'quantity'}
    elif kind == 'prepare_project_site': required |= {'recipe_id'}
    elif kind not in PROJECT_ACTIONS: raise RuleError('unsupported_action', 'Unsupported project action')
    if set(action) != required:
        raise RuleError('action_shape', 'Exact typed project action fields required')
    for key, value in action.items():
        if key not in ('quantity', 'participant_ids'):
            safe_id(value)
    if 'quantity' in action and not _number(action['quantity'], positive=True):
        raise RuleError('action_shape', 'Delivery quantity must be finite and positive, not boolean')
    actor = ctx.state.get('characters', action['actor_id'])
    if actor is None or actor['data']['status'] != 'alive':
        raise RuleError('invalid_actor', 'Living project actor required')
    rules = ctx.definitions.get('rules'); identity = action['project_id']
    templates = rules.get('project_templates', {})
    existing = ctx.state.get('actions', identity)
    effects = []
    if kind == 'start_project':
        template = templates.get(action['template_id'])
        if template is None or existing is not None:
            raise RuleError('project_start', 'Known template and unused project instance ID required')
        location = actor['data']['location_id']
        _site(ctx, template, location)
        _workers(ctx, action['participant_ids'], actor['id'], location)
        for record in ctx.state.list('actions'):
            data = record['data']
            same_template = data.get('template_id', data.get('type', record['id'])) == action['template_id']
            if same_template and data.get('location_id') == location and (data.get('completed') or data.get('kind') == 'project'):
                raise RuleError('project_duplicate', 'Historical completion or existing project prevents duplicate construction')
        if any(ctx.state.get('resources', r) is None for r in template['materials']):
            raise RuleError('project_material', 'Starting requires existing material stock references')
        cost, stat = template['credit_cost'], template['credit_stat']
        if cost:
            balance = actor['data']['stats'].get(stat)
            if not _number(balance) or balance < cost:
                raise RuleError('project_credit', 'Insufficient finite credits')
            effects.append(_set('characters', actor['id'], '/stats/' + stat, balance - cost))
        data = {'kind': 'project', 'name': template['name'], 'template_id': action['template_id'],
                'template_sha256': _hash(template), 'actor_id': actor['id'],
                'participant_ids': action['participant_ids'], 'location_id': location, 'status': 'active',
                'completed': False, 'hours_committed': 0,
                'materials_committed': {r: 0 for r in template['materials']},
                'conditions': {c: False for c in template['conditions']}}
        effects.append({'op': 'create', 'collection': 'actions', 'entity_id': identity, 'value': data})
        return RuleResult(effects, {'project_id': identity, 'project_action': kind})
    if existing is None or existing['data'].get('kind') != 'project':
        raise RuleError('project_reference', 'Executable project instance required; history is read-only')
    data = existing['data']; template = templates.get(data['template_id'])
    if template is None or data.get('template_sha256') != _hash(template):
        raise RuleError('project_template', 'Project template definition changed or missing')
    if data['completed'] or actor['id'] != data['actor_id']:
        raise RuleError('project_actor', 'Only the owning actor can advance an active project')
    _site(ctx, template, data['location_id'])
    workers = _workers(ctx, data['participant_ids'], actor['id'], data['location_id'])
    if kind == 'deliver_materials':
        resource_id, quantity = action['resource_id'], action['quantity']
        stock = ctx.state.get('resources', resource_id)
        if stock is None or resource_id not in template['materials'] or quantity > stock['data']['quantity'] or quantity > template['materials'][resource_id] - data['materials_committed'][resource_id]:
            raise RuleError('project_material', 'Existing sufficient stock and bounded required delivery necessary')
        committed = {**data['materials_committed'], resource_id: data['materials_committed'][resource_id] + quantity}
        effects = [_set('resources', resource_id, '/quantity', stock['data']['quantity'] - quantity),
                   _set('actions', identity, '/materials_committed', committed)]
    elif kind == 'work_project':
        remaining = template['hours_required'] - data['hours_committed']
        if remaining <= 0:
            raise RuleError('project_labor', 'No labor remains')
        for worker in workers:
            d = worker['data']; cost = template['fatigue_cost']
            if d['capabilities']['cannot_die'] or cost == 0:
                continue
            if not _number(d['health']) or d['health'] <= cost:
                raise RuleError('project_fatigue', 'Fatigue cannot kill a mortal or charge null health')
            effects.append(_set('characters', worker['id'], '/health', d['health'] - cost))
        effects.append(_set('actions', identity, '/hours_committed', data['hours_committed'] + min(remaining, len(workers))))
    elif kind == 'prepare_project_site':
        recipe = rules['project_preparation_recipes'].get(action['recipe_id'])
        if recipe is None or data['location_id'] not in recipe['site_ids'] or any(c not in data['conditions'] or data['conditions'][c] for c in recipe['conditions']):
            raise RuleError('project_preparation', 'Fixed recipe at permitted site and unmet named conditions required')
        effects.append(_set('actions', identity, '/conditions', {**data['conditions'], **recipe['conditions']}))
    elif kind == 'complete_project':
        if data['hours_committed'] != template['hours_required'] or data['materials_committed'] != template['materials'] or not all(data['conditions'].values()):
            raise RuleError('project_incomplete', 'All labor, materials and structural conditions required')
        for resource_id, amount in template['resource_rewards'].items():
            stock = ctx.state.get('resources', resource_id)
            quantity = stock['data']['quantity'] + amount
            if not _number(quantity) or quantity > _capacity(ctx, resource_id):
                raise RuleError('project_reward', 'Configured reward exceeds existing stock capacity')
            effects.append(_set('resources', resource_id, '/quantity', quantity))
        effects.extend([_set('actions', identity, '/completed', True), _set('actions', identity, '/status', 'completed')])
    return RuleResult(effects, {'project_id': identity, 'project_action': kind})
