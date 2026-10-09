"""Selected-world seeded proposal generation; no authoritative state mutation."""
import json
import os
from pathlib import Path
import random
import uuid
from engine.contracts import RuleError, WorldContract
from engine.runner import read_snapshot
from world_utils import require_canonical


def propose_event(world_dir, *, seed=0, improvise=False):
    world = Path(world_dir).resolve()
    require_canonical(world)
    contract = WorldContract(world, load_hooks=False)
    gm = contract.definitions['gm']
    pool = gm.get('improvisation_templates' if improvise else 'disaster_pool', [])
    fallback = False
    if not pool and improvise:
        pool = gm.get('disaster_pool', []); fallback = True
    if not pool:
        raise RuleError('no_templates', 'Selected world has no configured GM pool')
    template = random.Random(seed).choice(pool)
    rules = contract.definitions['rules']
    if template['id'] not in rules['templates']:
        raise RuleError('unsupported_template', 'Template lacks explicit mechanical configuration')
    snapshot = read_snapshot(world)
    player = snapshot['characters'][contract.config['player_character_id']]['data']
    event = {'schema_version':1, 'event_id':'gm_'+uuid.uuid4().hex, 'world_id':contract.config['world_id'],
             'expected_turn':snapshot['clock']['data']['turn'], 'expected_revisions':{'clock':snapshot['clock']['revision']},
             'action':{'type':'introduce_threat','template_id':template['id'],'location_id':rules['templates'][template['id']].get('location_id', player['location_id'])},
             'narrative':template['name'] + ': ' + template.get('description', template.get('threat',''))}
    if fallback:
        event['narrative'] += ' [No improvisation pool: selected-world disaster_pool fallback.]'
    if rules['sanctuary'] or contract.definitions['world']['structural_rules'].get('transcendent_sanctuary', False):
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


if __name__ == '__main__':
    from world_cli import main
    raise SystemExit(main('gm'))
