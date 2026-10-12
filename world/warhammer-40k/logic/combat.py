"""Group and single-actor combat resolver for Warhammer 40k."""
import math
from engine.contracts import RuleError, RuleResult, safe_id


def _set(collection, identity, path, value):
    return {'op': 'set', 'collection': collection, 'entity_id': identity, 'path': path, 'value': value}


STANCES = {
    'neutral': {'outgoing': 1.0, 'incoming': 1.0},
    'defensive_cover': {'outgoing': 0.8, 'incoming': 0.65},
    'aggressive_assault': {'outgoing': 1.15, 'incoming': 1.25},
}


def resolve_attack(ctx, event, derive_fn):
    action = event['action']
    rules = ctx.definitions.get('rules')
    equipment_doc = ctx.definitions.get('equipment')
    equipment_items = equipment_doc.get('items', {}) if equipment_doc else {}
    weapons = rules.get('weapons', {})
    armor_cfg = rules.get('armor', {})

    required = {'type', 'actor_id', 'target_id', 'weapon_id'}
    allowed = required | {'resource_id', 'participant_ids', 'group_id', 'stance'}
    if not required <= set(action) or set(action) - allowed:
        raise RuleError('action_shape', f'Required {required}; allowed optional fields; no extra fields')

    for key, value in action.items():
        if key == 'participant_ids':
            if not isinstance(value, list) or not value:
                raise RuleError('action_shape', 'participant_ids must be a nonempty list of strings')
            for pid in value:
                if not isinstance(pid, str) or not pid:
                    raise RuleError('action_shape', 'participant ID must be a nonempty string')
                safe_id(pid)
            if len(value) != len(set(value)):
                raise RuleError('action_shape', 'participant_ids must contain unique character IDs')
        else:
            if not isinstance(value, str) or not value:
                raise RuleError('action_shape', f'{key} must be a nonempty string')
            safe_id(value)

    actor_id = action['actor_id']
    actor = ctx.state.get('characters', actor_id)
    if actor is None or actor['data']['status'] != 'alive':
        raise RuleError('invalid_actor', 'A living actor is required')
    current_location = actor['data']['location_id']

    target_id = action['target_id']
    target = ctx.state.get('threats', target_id)
    if (target is None or not target['data']['active'] or
            target['data']['activation_turn'] > ctx.turn or
            target['data'].get('location_id') != current_location or
            target['data']['stats']['health'] <= 0):
        raise RuleError('invalid_target', 'Attack requires a co-located living active threat')

    # Participants
    if 'participant_ids' in action:
        participants = action['participant_ids']
        if actor_id not in participants:
            raise RuleError('invalid_participants', 'Actor must be included in participant_ids')
    else:
        participants = [actor_id]

    living_participants = []
    for pid in sorted(participants):
        p_char = ctx.state.get('characters', pid)
        if p_char is None or p_char['data']['status'] != 'alive':
            raise RuleError('invalid_participants', f'Participant {pid} must be an existing living character')
        if p_char['data']['location_id'] != current_location:
            raise RuleError('invalid_participants', f'Participant {pid} must be co-located with actor')
        living_participants.append(p_char)

    # Stance
    stance_name = action.get('stance', 'neutral')
    if stance_name not in STANCES:
        raise RuleError('invalid_stance', f'Unknown stance: {stance_name}')
    stance = STANCES[stance_name]

    # Group
    group = None
    group_id = action.get('group_id')
    if group_id:
        group_entity = ctx.state.get('groups', group_id)
        if group_entity is None:
            raise RuleError('invalid_group', f'Group {group_id} not found')
        gdata = group_entity['data']
        count = gdata.get('count')
        if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
            raise RuleError('invalid_group', f'Group {group_id} must have a positive integer count')
        g_loc = gdata.get('location_id')
        if g_loc != current_location:
            raise RuleError('invalid_group', f'Group {group_id} must be deployed at actor location')
        for mid in gdata.get('members', []):
            if ctx.state.get('characters', mid) is None:
                raise RuleError('invalid_group', f'Group member reference {mid} does not exist')
        group = group_entity

    effects = []

    # Weapon & ammo check for actor
    actor_weapon_id = action['weapon_id']
    if (actor_weapon_id not in actor['data']['equipment'] or
            actor_weapon_id not in equipment_items or
            actor_weapon_id not in weapons):
        raise RuleError('invalid_weapon', 'A recognized equipped weapon with configured combat mechanics is required')

    actor_weapon = weapons[actor_weapon_id]
    if 'ammo_id' in actor_weapon:
        ammo_id = actor_weapon['ammo_id']
        if action.get('resource_id') != ammo_id:
            raise RuleError('ammunition', f'Resource must be {ammo_id}')
        res = ctx.state.get('resources', ammo_id)
        if res is None or res['data'].get('quantity', 0) < actor_weapon['ammo_cost']:
            raise RuleError('ammunition', 'Insufficient ammunition; entire turn rejected')
        effects.append(_set('resources', res['id'], '/quantity', res['data']['quantity'] - actor_weapon['ammo_cost']))
    elif 'resource_id' in action:
        raise RuleError('ammunition', 'This weapon does not consume a resource')

    # Calculate outgoing damage
    total_damage = 0.0
    for p_char in living_participants:
        pid = p_char['id']
        if pid == actor_id:
            w_id = actor_weapon_id
            w_spec = actor_weapon
        else:
            equipped = p_char['data'].get('equipment', [])
            # Find companion equipped melee/default non-ammo weapon
            melee_id = next((item for item in equipped if item in weapons and equipment_items.get(item, {}).get('slot') == 'melee_weapon' and 'ammo_id' not in weapons[item]), None)
            if melee_id is None:
                melee_id = next((item for item in equipped if item in weapons and 'ammo_id' not in weapons[item]), None)
            if melee_id is None:
                raise RuleError('companion_weapon', f'Companion {pid} has no recognized non-ammo equipped weapon')
            w_id = melee_id
            w_spec = weapons[w_id]

        derived = derive_fn(ctx, 'characters/' + pid)
        kinetic = derived.get('punch_kinetic_impact', 0.0)
        p_gross = (w_spec['power'] + kinetic) * stance['outgoing']
        p_armor = max(0, target['data']['stats']['armor'] - w_spec['penetration'])
        p_dmg = round(p_gross * (1 - p_armor), 2)
        total_damage += p_dmg

    total_damage = round(total_damage, 2)
    remaining_health = max(0, target['data']['stats']['health'] - total_damage)
    effects.append(_set('threats', target['id'], '/stats/health', remaining_health))
    effects.append(_set('threats', target['id'], '/active', remaining_health > 0))

    # Calculate retaliation
    raw_retaliation = target['data']['stats']['retaliation']
    n_participants = len(living_participants)
    retaliation_share = raw_retaliation / n_participants

    injuries = {}
    actor_retaliation_damage = 0.0
    actor_mitigation = 0.0

    for p_char in living_participants:
        pid = p_char['id']
        p_data = p_char['data']
        mitigation = max((armor_cfg.get(item, 0) for item in p_data.get('equipment', [])), default=0)
        incoming = retaliation_share * (1 - mitigation) * stance['incoming']
        damage_taken = round(incoming, 2)

        if pid == actor_id:
            actor_mitigation = mitigation

        if p_data['capabilities'].get('cannot_die'):
            new_health = p_data['health']
            new_status = 'alive'
        else:
            new_health = max(0, p_data['health'] - damage_taken)
            new_status = 'dead' if new_health == 0 else 'alive'

        if pid == actor_id:
            actor_retaliation_damage = p_data['health'] - new_health

        effects.append(_set('characters', pid, '/health', new_health))
        effects.append(_set('characters', pid, '/status', new_status))
        injuries[pid] = {'damage': damage_taken, 'mitigation': mitigation, 'health': new_health, 'status': new_status}

    # Group casualties
    casualties = 0
    if group:
        gdata = group['data']
        count = gdata['count']
        casualties = min(count, math.floor(raw_retaliation / 15))
        effects.append(_set('groups', group['id'], '/count', count - casualties))

    outcomes = {
        'damage_dealt': total_damage,
        'remaining_health': remaining_health,
        'retaliations': 1,
        'retaliation_raw': raw_retaliation,
        'retaliation_damage': actor_retaliation_damage,
        'armor_mitigation': actor_mitigation,
        'injuries': injuries,
        'casualties': casualties,
        'stance': stance_name,
    }
    return RuleResult(effects, outcomes)
