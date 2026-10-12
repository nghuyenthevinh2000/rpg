"""Read-only legacy inspection and durable, contract-last current-save import."""
from copy import deepcopy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

from engine.contracts import (RuleContext, RuleError, StateView, WorldContract,
                              casefold_unique, contained_path, load_json, safe_id)
from engine.state_store import StateStore
from world_utils import load_progress


def _atomic(path, value):
    path = Path(path)
    _mkdir(path.parent)
    fd, temp = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.replace(temp, path)
        _sync(path.parent)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def _sync(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _mkdir(path):
    if path.is_symlink():
        raise RuleError('unsafe_path', f'Symlink destination: {path}')
    if not path.exists():
        _mkdir(path.parent)
        path.mkdir(); _sync(path.parent)


def _fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _copy_file(source, target):
    _mkdir(target.parent)
    with source.open('rb') as src, target.open('xb') as dst:
        shutil.copyfileobj(src, dst); dst.flush(); os.fsync(dst.fileno())
    _sync(target.parent)


def _source_files(world):
    """Exact save/definition/history bytes, excluding newly authored integration."""
    paths = [world / 'world.json', world / 'game_master.json', world / 'action_conditions.json']
    for part in ('char', 'conditions', 'event', 'progress'):
        paths.extend((world / part).rglob('*.json'))
    if (world / 'progress.json').exists():
        paths.append(world / 'progress.json')
    for path in sorted(set(paths)):
        if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != world.parent):
            raise RuleError('unsafe_path', f'Symlink migration source: {path}')
        if path.is_file():
            yield path


def _hashes(world):
    return {str(p.relative_to(world)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in _source_files(world)}


def _envelope(identity, data):
    safe_id(identity)
    return {'id': identity, 'revision': 0, 'schema_version': 1, 'data': data}


def _registries(world):
    traits = load_json(world / 'conditions/traits.json')['traits']
    equipment = load_json(world / 'conditions/equipments.json')['items'] if (world / 'conditions/equipments.json').exists() else {}
    return traits, equipment


def modifier_totals(trait_ids, equipment_ids, traits, items):
    totals = {}
    for registry, identities in ((traits, trait_ids), (items, equipment_ids)):
        for identity in identities:
            for stat, amount in registry[identity].get('stat_modifiers', {}).items():
                if not stat.startswith('max_'):
                    totals[stat] = totals.get(stat, 0) + amount
    return totals


def _normalized(world):
    legacy = load_json(world / 'world.json')
    progress = load_progress(world)
    config = load_json(world / 'contract.json')
    rules = load_json(world / 'definitions/engine_rules.json')
    traits, items = _registries(world)
    locations = {l['id']: l for l in legacy['locations']}
    issues, blocking = [], []
    def issue(code, source, detail, fatal=False):
        row = {'code': code, 'source': source, 'detail': detail}
        issues.append(row)
        if fatal:
            blocking.append(row)
    casefold_unique(locations, 'Locations')
    for identity, location in locations.items():
        safe_id(identity)
        for neighbor in location.get('connected_to', []):
            if neighbor not in locations:
                issue('broken_edge', identity, neighbor, True)
    state = {key: {} for key in config['collections']}
    cycle = progress['current_cycle']
    state['clock'] = _envelope('clock', {'turn': cycle['turn_count'], 'day': cycle['day'], 'display_timestamp': cycle['timestamp']})
    inventory_registry = {}
    for path in sorted((world / 'char').glob('*.json')):
        original = load_json(path)
        identity = safe_id(original['id'])
        if identity in state['characters']:
            issue('duplicate_identity', str(path.relative_to(world)), identity, True)
        aliases = {k: original[k] for k in ('location', 'current_location', 'location_id') if k in original}
        location_id = aliases.get('location_id', aliases.get('current_location', aliases.get('location')))
        if len(set(aliases.values())) > 1:
            issue('location_alias_disagreement', identity, aliases, True)
        issue('location_alias', identity, aliases)
        if location_id not in locations:
            issue('broken_location', identity, location_id, True)
        elif original.get('coordinate') != locations[location_id]['coordinate']:
            issue('coordinate_mismatch', identity, {'stored': original.get('coordinate'), 'canonical': locations[location_id]['coordinate']})
        trait_ids = []
        for t in original.get('traits', []):
            tid = t.get('trait_id') if isinstance(t, dict) else t
            if tid not in traits:
                issue('unknown_trait', identity, tid, True)
            else:
                trait_ids.append(tid)
        equipment_ids = []
        raw_equipment = original.get('equipment', {})
        for item in (raw_equipment.values() if isinstance(raw_equipment, dict) else raw_equipment):
            if item in items:
                equipment_ids.append(item)
            elif isinstance(item, str) and item.startswith('item_'):
                issue('unknown_equipment_id', identity, item, True)
            else:
                issue('narrative_equipment', identity, item)
        inventory = []
        for item in original.get('inventory', []):
            tid = item.get('item_id', item.get('id')) if isinstance(item, dict) else item
            if tid:
                safe_id(tid); inventory.append(tid)
                inventory_registry[tid] = deepcopy(item) if isinstance(item, dict) else {'id': tid, 'name': tid}
        raw_stats = original.get('stats', {})
        health = raw_stats.get('physical_vitality')
        immortal = health == -99
        if immortal:
            issue('immortal_sentinel', identity, {'old': -99, 'health': rules['immortal_health']})
            health = rules['immortal_health']
        status_text = str(original.get('current_status', original.get('current_state', '')))
        kia = 'KIA' in status_text.upper().split(' / ')[0]
        status = 'dead' if kia or (health is not None and health <= 0 and not immortal) else 'alive'
        if status == 'dead':
            health = 0
        stats = {}
        for key, value in raw_stats.items():
            if key in ('physical_vitality', 'punch_kinetic_impact', 'applied_equipment_modifiers'):
                continue
            if key in rules['stat_keys'] and isinstance(value, (int,float)) and not isinstance(value,bool):
                stats[key] = value
            else:
                issue('unsupported_stat', identity, {key: value})
        modifiers = modifier_totals(trait_ids, equipment_ids, traits, items) if all(t in traits for t in trait_ids) else {}
        issue('baseline_modifiers', identity, {'policy': 'current values frozen; configured offsets relative to baseline', 'applied': raw_stats.get('applied_equipment_modifiers'), 'configured': modifiers})
        for stat, value in stats.items():
            bounds = rules.get('bounds', {}).get(stat)
            if bounds and not bounds[0] <= value <= bounds[1]:
                issue('bounds_baseline_exception', identity, {stat: value, 'bounds': bounds, 'policy': 'baseline preserved; bounds expanded to include baseline'})
        decisions = original.get('decisions', [])
        duplicates = len(decisions) - len({json.dumps(d, sort_keys=True) for d in decisions})
        if duplicates:
            issue('duplicate_decisions', identity, duplicates)
        data = {'name': original.get('name', identity), 'location_id': location_id, 'status': status,
                'health': health, 'stats': stats, 'capabilities': {'cannot_die': immortal},
                'traits': sorted(set(trait_ids)), 'equipment': sorted(set(equipment_ids)), 'inventory': sorted(set(inventory)),
                'baseline': {'stats': deepcopy(stats), 'modifiers': modifiers}, 'metadata': {'legacy': original}}
        state['characters'][identity] = _envelope(identity, data)
        issue('unsupported_character_fields', identity, sorted(set(original) - {'id','name','stats','traits','equipment','inventory','location','current_location','coordinate'}))
    casefold_unique(state['characters'], 'Characters')
    if config['player_character_id'] not in state['characters']:
        issue('missing_player', 'contract.json', config['player_character_id'], True)
    milestones = progress.get('completed_milestones', [])
    ids = [m.get('milestone_id') for m in milestones]
    if len(ids) != len(set(ids)):
        issue('duplicate_milestones', 'progress', len(ids) - len(set(ids)))
    for action in progress.get('active_actions', []):
        identity = action.get('action_id')
        if not identity:
            issue('unsupported_action_shape', 'progress', action); continue
        safe_id(identity)
        location = action.get('location', action.get('location_id'))
        unresolved = [i for i in action.get('assigned_participants', []) if i not in state['characters']]
        if unresolved:
            issue('unresolved_narrative_participants', identity, unresolved)
        data = {'name': action.get('name', identity), 'type': identity, 'completed': action.get('status') == 'completed', 'metadata': {'legacy': action, 'executable': False}}
        if location:
            data['location_id'] = location
            if location not in locations:
                issue('broken_action_location', identity, location, True)
        if identity in state['actions']:
            issue('duplicate_action_identity', 'progress', identity, True)
        state['actions'][identity] = _envelope(identity, data)
        issue('unsupported_action_shape', identity, 'Imported as non-executable historical record')
    for trial in progress.get('active_disasters_and_trials', []):
        identity = trial.get('trial_id', trial.get('id'))
        if not identity:
            issue('unsupported_threat_shape', 'progress', trial); continue
        safe_id(identity)
        template = rules['templates'].get(identity)
        data = {'name': trial.get('name', identity), 'active': trial.get('status') == 'active',
                'activation_turn': cycle['turn_count'], 'tags': template.get('tags', []) if template else [],
                'stats': deepcopy(template['stats']) if template else {'health': 0, 'armor': 0, 'retaliation': 0}, 'metadata': {'legacy': trial}}
        location = trial.get('location_id', trial.get('location')) or (template or {}).get('location_id')
        if location:
            data['location_id'] = location
            if location not in locations:
                issue('broken_threat_location', identity, location, True)
        elif 'cold' in data['tags'] or 'hostile' in data['tags']:
            issue('missing_hazard_location', identity, 'Mechanical hazards require location_id', True)
        if identity in state['threats']:
            issue('duplicate_threat_identity', 'progress', identity, True)
        state['threats'][identity] = _envelope(identity, data)
        issue('unsupported_threat_fields', identity, 'Only explicit configured tags and numeric mechanics imported; prose remains metadata')
    for category, stock in progress.get('active_resource_stockpile', {}).items():
        if not isinstance(stock, dict):
            continue
        for identity, item in stock.items():
            if not isinstance(item, dict):
                continue
            quantity = item.get('current', item.get('depot_stock'))
            if isinstance(quantity, (int,float)) and not isinstance(quantity,bool):
                safe_id(identity)
                if identity in state['resources']:
                    issue('duplicate_resource', 'progress', identity, True)
                state['resources'][identity] = _envelope(identity, {'name': identity, 'quantity': quantity, 'unit': item.get('unit', ''), 'metadata': {'legacy': item, 'category': category, 'automatic_mechanics': False}})
    garrison = progress.get('garrison_forces', {})
    members = []
    for member in garrison.get('command_and_specialists', []):
        identity = member.get('id')
        if identity in state['characters']:
            members.append(identity)
            if state['characters'][identity]['data']['status'] == 'dead':
                issue('status_disagreement', identity, {'character': 'dead', 'garrison': member.get('status')})
        else:
            issue('unresolved_narrative_garrison', 'progress', identity)
    if garrison:
        state['groups']['garrison'] = _envelope('garrison', {'name': 'Garrison', 'members': members, 'metadata': {'legacy': garrison}})
    for path in sorted((world / 'event').glob('*.json')):
        event = load_json(path)
        issue('legacy_event_shape', str(path.relative_to(world)), sorted(event))
        if '030' in path.name and isinstance(event.get('progress_updates'), dict):
            nested = {k: v for k,v in event['progress_updates'].items() if 'char' in k}
            if nested:
                issue('ignored_nested_event_030_updates', str(path.relative_to(world)), nested)
    if rules['sanctuary']:
        issue('stale_hostile_gm_templates', 'game_master.json', 'Sanctuary rejects hostile introductions; templates retained for inspection')
    for collection in config['collections']:
        casefold_unique(state[collection], f'{collection} identities')
    state['baseline']['legacy'] = _envelope('legacy', {'metadata': {'progress': progress, 'world': legacy, 'inventory_registry': inventory_registry, 'unsupported_mechanics': 'Narrative/history/construction/resource production are not executable'}})
    report = {'world_id': config['world_id'], 'preview': True, 'policy': 'current-save baseline; deterministic normalization; no turn', 'issues': issues, 'blocking': blocking, 'source_sha256': _hashes(world)}
    return state, report


def inspect_world(world_dir):
    world = Path(world_dir).resolve()
    if load_json(world / 'world.json').get('contract_version') == 1:
        from engine.runner import read_snapshot
        snapshot = read_snapshot(world)
        contract = WorldContract(world)
        ctx = RuleContext(StateView(snapshot), contract.definition_view, None, snapshot['clock']['data']['turn'])
        derivation_audit = {}
        for character in snapshot.get('characters', {}).values():
            char_id = character['id']
            derived = contract.derive(ctx, 'characters/' + char_id)
            if 'audit' in derived:
                derivation_audit[char_id] = derived['audit']
        return {
            'world_id': load_json(world / 'world.json')['world_id'],
            'canonical': True,
            'clock': snapshot['clock'],
            'derivation_audit': derivation_audit,
            'legacy_inspection': load_json(world / 'archive/migration-report.json') if (world / 'archive/migration-report.json').exists() else None
        }
    return _normalized(world)[1]


def _cutover(world, stage, journal):
    """Install only StateStore-authored baseline directories; world.json LAST."""
    for part in ('state', 'transactions', 'events'):
        source, target = stage / part, world / part
        if source.exists():
            if target.exists():
                raise RuleError('migration_conflict', f'Both staged and destination {part} exist; inspect journal, do not overwrite')
            os.rename(source, target); _sync(world); _sync(stage)
        elif not target.is_dir():
            raise RuleError('migration_incomplete', f'Missing staged and installed {part}')
    target = world / 'definitions/world.json'
    if not target.exists():
        _copy_file(stage / 'definitions/world.json', target)
    elif target.read_bytes() != (stage / 'definitions/world.json').read_bytes():
        raise RuleError('migration_conflict', 'Existing definitions/world.json differs')
    installed = StateStore(world, WorldContract(stage, load_hooks=False)).snapshot()
    if _fingerprint(installed) != journal['baseline_sha256']:
        raise RuleError('migration_baseline_changed', 'Installed baseline differs from staged candidate; do not cut over or overwrite')
    _atomic(world / 'world.json', load_json(stage / 'world.json'))
    journal['phase'] = 'complete'
    _atomic(world / '.migration.json', journal)


def migrate_world(world_dir, *, dry_run=False, accept_baseline=False, resume=False):
    """Default commits authorized cutover; accept_baseline is a deprecated no-op."""
    world = Path(world_dir).resolve()
    if dry_run:
        return inspect_world(world)
    with (world / '.migration.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        journal_path = world / '.migration.json'
        if journal_path.exists():
            journal = load_json(journal_path)
            if not resume or journal['phase'] != 'ready':
                raise RuleError('migration_incomplete', 'Existing migration journal: only ready cutover can --resume; no archive or state overwrite')
            stage = world / '.migration-stage'
            if load_json(world / 'world.json').get('contract_version') != 1 and _hashes(world) != journal['source_sha256']:
                raise RuleError('migration_source_changed', 'Legacy source changed after staging')
            if _hashes(world / 'archive/legacy-baseline') != journal['source_sha256']:
                raise RuleError('migration_archive_changed', 'Original archive hashes disagree')
            _cutover(world, stage, journal)
            report = load_json(world / 'archive/migration-report.json')
            report['preview'] = False
            _atomic(world / 'archive/migration-report.json', report)
            return report
        if load_json(world / 'world.json').get('contract_version'):
            raise RuleError('already_migrated', 'Canonical world already installed')
        for part in ('archive/legacy-baseline', '.migration-stage', 'state', 'transactions', 'events', 'definitions/world.json'):
            if (world / part).exists():
                raise RuleError('migration_conflict', f'Refusing existing {part}; never overwrite archive/state')
        state, report = _normalized(world)
        if report['blocking']:
            raise RuleError('migration_blocked', 'Fix invalid identities/references before import', report['blocking'])
        journal = {'phase': 'preparing', 'source_sha256': report['source_sha256']}
        _atomic(journal_path, journal)
        archive = world / 'archive/legacy-baseline'
        _mkdir(archive)
        for source in _source_files(world):
            _copy_file(source, archive / source.relative_to(world))
        _atomic(world / 'archive/migration-report.json', report)
        stage = world / '.migration-stage'
        _mkdir(stage)
        for part in ('logic', 'schemas', 'conditions'):
            for source in sorted((world / part).rglob('*')):
                if source.is_file():
                    contained_path(world, str(source.relative_to(world)))
                    _copy_file(source, stage / source.relative_to(world))
        for name in ('game_master.json', 'action_conditions.json', 'definitions/engine_rules.json'):
            _copy_file(world / name, stage / name)
        _copy_file(world / 'world.json', stage / 'definitions/world.json')
        _copy_file(world / 'contract.json', stage / 'world.json')
        contract = WorldContract(stage)
        ctx = RuleContext(StateView(state), contract.definition_view, None, state['clock']['data']['turn'])
        violations = contract.validate(ctx)
        if violations:
            raise RuleError('migration_invariants', 'Imported baseline violates world invariants', violations)
        StateStore(stage).initialize_baseline(state)
        if _hashes(world) != journal['source_sha256'] or _hashes(archive) != journal['source_sha256']:
            raise RuleError('migration_source_changed', 'Legacy source changed during staging')
        journal['baseline_sha256'] = _fingerprint(state)
        journal['phase'] = 'ready'; _atomic(journal_path, journal)
        _cutover(world, stage, journal)
        report['preview'] = False
        _atomic(world / 'archive/migration-report.json', report)
        return report
