"""Resolve, reduce, validate, commit, then render a captured committed snapshot."""
from copy import deepcopy
import hashlib
import json
import random
from pathlib import Path
import re

from jsonschema import Draft202012Validator

from .contracts import (WorldContract, RuleError, RuleResult, RuleContext, StateView,
                        EVENT_SCHEMA, validate_schema, json_value, load_json, safe_id, object_schema,
                        casefold_unique)
from .state_store import StateStore


def _event(value):
    value = load_json(value) if isinstance(value, (str, Path)) else deepcopy(value)
    validate_schema(Draft202012Validator(EVENT_SCHEMA), value, 'event')
    return value


def _check_event(contract, store, state, event):
    if event['world_id'] != contract.config['world_id']:
        raise RuleError('wrong_world', 'Event belongs to a different world')
    if store.is_duplicate(event['event_id']):
        raise RuleError('duplicate_event', f"Event already applied: {event['event_id']}")
    if event['expected_turn'] != state['clock']['data']['turn']:
        raise RuleError('stale_turn', 'Expected turn differs from committed turn')
    for reference, revision in event.get('expected_revisions', {}).items():
        store.entity_path(reference)
        envelope = state['clock'] if reference == 'clock' else state[reference.split('/')[0]].get(reference.split('/')[1])
        if envelope is None or envelope['revision'] != revision:
            raise RuleError('stale_revision', f'Expected revision differs: {reference}')


def _context(contract, state, rng):
    return RuleContext(StateView(state), contract.definition_view, rng, state['clock']['data']['turn'])


def _call(hook, *args):
    try:
        return hook(*args)
    except RuleError:
        raise
    except Exception as exc:
        raise RuleError('rule_failure', str(exc)) from exc


def _result(value):
    if not isinstance(value, RuleResult) or not isinstance(value.effects, list) or not isinstance(value.outcomes, dict) or not isinstance(value.notes, list) or type(value.advances_turn) is not bool:
        raise RuleError('invalid_rule_result', 'Hooks must return RuleResult with valid field types')
    json_value({'effects':value.effects,'outcomes':value.outcomes,'notes':value.notes})
    if not all(isinstance(note, str) for note in value.notes):
        raise RuleError('invalid_rule_result', 'Notes must be strings')
    return deepcopy(value)


def _pointer(data, pointer):
    if not isinstance(pointer, str) or not pointer.startswith('/'):
        raise RuleError('invalid_effect', 'Expected a non-root JSON pointer into entity data')
    parts = pointer[1:].split('/')
    if any(re.search(r'~(?![01])', part) for part in parts):
        raise RuleError('invalid_effect', 'Invalid JSON pointer escape')
    parts = [part.replace('~1','/').replace('~0','~') for part in parts]
    parent = data
    for part in parts[:-1]:
        if not isinstance(parent, dict) or part not in parent:
            raise RuleError('missing_target', f'Missing dictionary path: {pointer}')
        parent = parent[part]
    if not isinstance(parent, dict) or parts[-1] not in parent:
        raise RuleError('missing_target', f'Missing dictionary field: {pointer}')
    return parent, parts[-1]


def _reduce(contract, state, effects):
    identities = {collection: set(state[collection]) for collection in contract.collections}
    for effect in effects:
        if not isinstance(effect, dict):
            raise RuleError('invalid_effect', 'Effect must be an object')
        op = effect.get('op')
        allowed = {'op','collection','entity_id'}
        if op in ('set','increment'): allowed |= {'path','value'}
        elif op == 'create': allowed |= {'value'}
        elif op == 'remove': allowed |= {'path'}
        else: raise RuleError('invalid_effect', f'Unknown operation: {op}')
        required = allowed if op != 'remove' else {'op','collection','entity_id'}
        if not required <= effect.keys() or not effect.keys() <= allowed:
            raise RuleError('invalid_effect', 'Unknown or missing effect fields')
        collection, entity_id = safe_id(effect['collection']), safe_id(effect['entity_id'])
        clock = collection == 'clock' and entity_id == 'clock'
        if collection not in contract.collections and not clock:
            raise RuleError('invalid_effect', f'Undeclared collection: {collection}')
        entities = {'clock':state['clock']} if clock else state[collection]
        if not clock:
            casefold_unique(identities[collection] | {entity_id}, f'{collection} effect targets')
            identities[collection].add(entity_id)
        if op == 'create':
            if entity_id in entities or not isinstance(effect['value'], dict):
                raise RuleError('invalid_effect', 'Create requires a missing entity and object data')
            entities[entity_id] = {'id':entity_id,'revision':0,'schema_version':1,'data':deepcopy(effect['value'])}
            contract.validate_envelope(collection, entity_id, entities[entity_id])
            continue
        if entity_id not in entities:
            raise RuleError('missing_target', f'Missing entity: {collection}/{entity_id}')
        if op == 'remove' and 'path' not in effect:
            if clock or not contract.collections[collection].get('allow_remove', False):
                raise RuleError('invalid_effect', 'Collection does not permit entity removal')
            del entities[entity_id]
            continue
        if clock and effect['path'] not in ('/day','/display_timestamp'):
            raise RuleError('invalid_effect', 'Clock turn and envelope metadata are engine-owned')
        parent, key = _pointer(entities[entity_id]['data'], effect['path'])
        if op == 'remove':
            # Final schema validation enforces required fields, including composed schemas.
            del parent[key]
        elif op == 'set':
            parent[key] = deepcopy(effect['value'])
        else:
            if type(parent[key]) not in (int,float) or type(effect['value']) not in (int,float):
                raise RuleError('invalid_effect', 'Increment requires numeric, non-boolean operands')
            parent[key] += effect['value']
            json_value(parent[key])


def _changes(before, after):
    changes = {}
    if before['clock']['data'] != after['clock']['data']:
        after['clock']['revision'] = before['clock']['revision'] + 1
        changes['clock'] = {'before':deepcopy(before['clock']),'after':deepcopy(after['clock'])}
    for collection in sorted(set(before) - {'clock'}):
        casefold_unique(set(before[collection]) | set(after[collection]), f'{collection} before/after IDs')
        for entity_id in sorted(set(before[collection]) | set(after[collection])):
            old, new = before[collection].get(entity_id), after[collection].get(entity_id)
            if old is not None and new is not None and old['data'] == new['data']:
                after[collection][entity_id] = deepcopy(old)
                continue
            if old is None and new is None:
                continue
            if old is not None and new is not None:
                new['revision'] = old['revision'] + 1
            changes[f'{collection}/{entity_id}'] = {'before':deepcopy(old),'after':deepcopy(new)}
    return changes


def _render(world_dir, snapshot, report, render):
    if not render:
        return report
    try:
        if callable(render):
            render(deepcopy(snapshot))
        else:
            from .render_map import render_map
            render_map(world_dir, deepcopy(snapshot))
    except Exception as exc:
        report['render_error'] = str(exc)
    return report


def _baseline_sha256(state):
    payload = json.dumps(state, sort_keys=True, separators=(',', ':'),
                         ensure_ascii=False, allow_nan=False).encode('utf-8')
    return hashlib.sha256(payload).hexdigest()


def run_event(world_dir, event_or_path, dry_run=False, seed=0, render=True):
    event = _event(event_or_path)
    json_value(seed)
    contract = WorldContract(world_dir)
    store = StateStore(world_dir, contract)
    with store.locked():
        before = store.load()
        _check_event(contract, store, before, event)
        rng = random.Random(seed)
        result = _result(_call(contract.resolve, _context(contract, before, rng), deepcopy(event)))
        after = deepcopy(before)
        _reduce(contract, after, result.effects)
        if result.advances_turn:
            periodic = _result(_call(contract.after_turn, _context(contract, after, rng),
                                     deepcopy(event), deepcopy(result.outcomes)))
            _reduce(contract, after, periodic.effects)
            result.effects.extend(periodic.effects)
            result.outcomes.update(periodic.outcomes)
            result.notes.extend(periodic.notes)
            after['clock']['data']['turn'] += 1
        changes = _changes(before, after)
        contract.validate_state(after)
        violations = _call(contract.validate, _context(contract, after, rng))
        if not isinstance(violations, list):
            raise RuleError('invalid_rule_result', 'validate must return a list of violations')
        json_value(violations)
        if violations:
            raise RuleError('world_invariant', 'World validation failed', violations)
        report = {'event_id':event['event_id'], 'world_id':event['world_id'], 'event':deepcopy(event),
                  'dry_run':bool(dry_run), 'changes':changes, 'effects':result.effects,
                  'outcomes':result.outcomes, 'notes':result.notes,
                  'turn':{'before':before['clock']['data']['turn'], 'after':after['clock']['data']['turn'],
                          'advances_turn':result.advances_turn},
                  'metadata':{'seed':seed, 'contract_version':contract.config['contract_version'],
                              'state_schema_version':contract.config['state_schema_version'],
                              'baseline_sha256':_baseline_sha256(before),
                              'rule_source_hash':contract.rule_source_hash}}
        json_value(report)
        if not dry_run:
            store.commit(report)
        snapshot = deepcopy(after)
    return report if dry_run else _render(world_dir, snapshot, report, render)


def replay_event(world_dir, committed_event_or_path, render=True):
    recorded = load_json(committed_event_or_path) if isinstance(committed_event_or_path, (str,Path)) else deepcopy(committed_event_or_path)
    json_value(recorded)
    required = {'event_id','world_id','event','dry_run','changes','effects','outcomes','notes','turn','metadata'}
    if not isinstance(recorded, dict) or not required <= recorded.keys() or not recorded.keys() <= required | {'render_error'}:
        raise RuleError('invalid_replay', 'Invalid resolved-event record')
    event = _event(recorded['event'])
    if recorded['event_id'] != event['event_id'] or recorded['world_id'] != event['world_id']:
        raise RuleError('invalid_replay', 'Resolved-event identity differs from event')
    contract = WorldContract(world_dir, load_hooks=False)
    metadata_schema = object_schema({
        'seed': {}, 'contract_version': {'type':'integer','const':1},
        'state_schema_version': {'type':'integer','const':1},
        'rule_source_hash': {'type':'string','pattern':'^[a-f0-9]{64}$'},
        'baseline_sha256': {'type':'string','pattern':'^[a-f0-9]{64}$'},
    }, ('seed','contract_version','state_schema_version','rule_source_hash','baseline_sha256'))
    validate_schema(Draft202012Validator(metadata_schema), recorded['metadata'], 'replay metadata')
    if type(recorded['dry_run']) is not bool:
        raise RuleError('invalid_replay', 'dry_run must be boolean')
    if recorded['metadata']['contract_version'] != contract.config['contract_version'] or recorded['metadata']['state_schema_version'] != contract.config['state_schema_version']:
        raise RuleError('invalid_replay', 'Recorded contract/schema version differs')
    turn = recorded['turn']
    if not isinstance(turn, dict) or set(turn) != {'before','after','advances_turn'} or type(turn['advances_turn']) is not bool or type(turn['before']) is not int or type(turn['after']) is not int or turn['before'] != event['expected_turn'] or turn['after'] != turn['before'] + int(turn['advances_turn']):
        raise RuleError('invalid_replay', 'Invalid recorded turn policy')
    _result(RuleResult(recorded['effects'], recorded['outcomes'], recorded['notes'], turn['advances_turn']))
    store = StateStore(world_dir, contract)
    with store.locked():
        before = store.load()
        _check_event(contract, store, before, event)
        if _baseline_sha256(before) != recorded['metadata']['baseline_sha256']:
            raise RuleError('stale_baseline', 'Replay requires the exact recorded full-state baseline')
        if not isinstance(recorded['changes'], dict):
            raise RuleError('invalid_replay', 'Changes must be an object')
        for reference, images in recorded['changes'].items():
            store.entity_path(reference)
            current = before['clock'] if reference == 'clock' else before[reference.split('/')[0]].get(reference.split('/')[1])
            if not isinstance(images, dict) or set(images) != {'before','after'} or current != images['before']:
                raise RuleError('stale_revision', f'Replay before-image differs: {reference}')
        after = deepcopy(before)
        _reduce(contract, after, recorded['effects'])
        if turn['advances_turn']:
            after['clock']['data']['turn'] += 1
        changes = _changes(before, after)
        if changes != recorded['changes']:
            raise RuleError('invalid_replay', 'Recorded images differ from exact effect reduction')
        contract.validate_state(after)
        report = deepcopy(recorded)
        report.pop('render_error', None)
        report['dry_run'] = False
        store.commit(report)
        snapshot = deepcopy(after)
    return _render(world_dir, snapshot, report, render)


def read_snapshot(world_dir):
    return StateStore(world_dir).snapshot()
