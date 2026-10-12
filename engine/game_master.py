"""Selected-world seeded proposal generation; no authoritative state mutation."""
import json
import os
from pathlib import Path
import random
import uuid
from .contracts import RuleError, WorldContract
from .runner import read_snapshot
from .world_utils import require_canonical


def allowed_templates(contract):
    gm = contract.definitions['gm']
    pool = gm.get('disaster_pool', []) + gm.get('improvisation_templates', [])
    rules = contract.definitions['rules']
    sanctuary = rules.get('sanctuary', False) or contract.definitions['world'].get('structural_rules', {}).get('transcendent_sanctuary', False)
    allowed = []
    for t in pool:
        tid = t['id']
        spec = rules.get('templates', {}).get(tid)
        if spec is None:
            continue
        tags = spec.get('tags', [])
        if sanctuary and any(tag in ('hostile', 'cold') for tag in tags):
            continue
        allowed.append(t)
    return allowed


def propose_event(world_dir, *, seed=0, improvise=False):
    world = Path(world_dir).resolve()
    require_canonical(world)
    contract = WorldContract(world, load_hooks=False)
    rules = contract.definitions['rules']
    sanctuary = rules.get('sanctuary', False) or contract.definitions['world'].get('structural_rules', {}).get('transcendent_sanctuary', False)

    gm = contract.definitions['gm']
    raw_pool = gm.get('improvisation_templates' if improvise else 'disaster_pool', [])
    fallback = False
    if not raw_pool and improvise:
        raw_pool = gm.get('disaster_pool', [])
        fallback = True
    if not raw_pool:
        raise RuleError('no_templates', 'Selected world has no configured GM pool')

    templates_cfg = rules.get('templates', {})
    pool = []
    for t in raw_pool:
        tid = t.get('id')
        if tid not in templates_cfg:
            continue
        tags = templates_cfg[tid].get('tags', [])
        if sanctuary and any(tag in ('hostile', 'cold') for tag in tags):
            continue
        pool.append(t)

    if not pool:
        raise RuleError('no_templates', 'No eligible templates under current world constraints')

    template = random.Random(seed).choice(pool)
    snapshot = read_snapshot(world)
    player = snapshot['characters'][contract.config['player_character_id']]['data']
    event = {'schema_version':1, 'event_id':'gm_'+uuid.uuid4().hex, 'world_id':contract.config['world_id'],
             'expected_turn':snapshot['clock']['data']['turn'], 'expected_revisions':{'clock':snapshot['clock']['revision']},
             'action':{'type':'introduce_threat','template_id':template['id'],'location_id':rules['templates'][template['id']].get('location_id', player['location_id'])},
             'narrative':template['name'] + ': ' + template.get('description', template.get('threat',''))}
    if fallback:
        event['narrative'] += ' [No improvisation pool: selected-world disaster_pool fallback.]'
    # Only append stale marker if sanctuary is active AND the chosen template is actually hostile/cold
    if sanctuary and any(tag in ('hostile', 'cold') for tag in rules['templates'][template['id']].get('tags', [])):
        event['narrative'] += ' [STALE HOSTILE TEMPLATE: sanctuary prohibits application; author inspection only.]'
    directory = world / 'events/proposed'
    if directory.is_symlink() or directory.parent.is_symlink():
        raise RuleError('unsafe_path', 'Proposal directory must not be a symlink')
    directory.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents proposal identities from being overwritten.
    with (directory / (event['event_id']+'.json')).open('x') as stream:
        json.dump(event, stream, ensure_ascii=False, indent=2); stream.write('\n')
        stream.flush(); os.fsync(stream.fileno())
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return event
