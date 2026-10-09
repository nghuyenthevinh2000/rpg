"""Escaped projection of one committed snapshot, with stale-render protection."""
import hashlib
from html import escape
import json
import os
from pathlib import Path
import random
import tempfile
from engine.contracts import RuleContext, RuleError, StateView, WorldContract
from engine.state_store import StateStore
from world_utils import require_canonical


def _fingerprint(snapshot):
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def render_map(world_dir, snapshot=None):
    world = Path(world_dir).resolve(); require_canonical(world)
    contract = WorldContract(world)
    store = StateStore(world, contract)
    if snapshot is None:
        snapshot = store.snapshot()
    view = StateView(snapshot)
    ctx = RuleContext(view, contract.definition_view, random.Random(0), snapshot['clock']['data']['turn'])
    lore = contract.definitions['world']; locations = lore['locations']
    text = lambda value: escape(str(value), quote=True)
    clock = snapshot['clock']['data']
    parts = ['<!doctype html><html><head><meta charset="utf-8"><title>'+text(lore['name'])+'</title>',
             '<style>body{font:16px system-ui;margin:2em;background:#101820;color:#eee}table{border-collapse:collapse}td{border:1px solid #678;padding:1em;vertical-align:top}small{display:block}li{margin:.6em}</style></head><body>',
             '<h1>'+text(lore['name'])+'</h1><p>Turn '+text(clock['turn'])+' · Day '+text(clock['day'])+' · '+text(clock['display_timestamp'])+'</p>',
             '<p>'+text(lore.get('theme', ''))+'</p><table>']
    cells = {}
    for location in locations:
        coord = location['coordinate']; key = (coord['row'], coord['col'])
        cells.setdefault(key, []).append(location)
    grid = lore.get('grid', {})
    for row in range(grid.get('rows', max((k[0] for k in cells), default=0)+1)):
        parts.append('<tr>')
        for col in range(grid.get('cols', max((k[1] for k in cells), default=0)+1)):
            parts.append('<td>')
            for location in cells.get((row,col), []):
                parts.append('<strong>'+text(location['name'])+'</strong><small>'+text(location.get('description',''))+'</small>')
                for character in view.list('characters'):
                    if character['data']['location_id'] == location['id']:
                        marker = '★ ' if character['id'] == contract.config['player_character_id'] else ''
                        parts.append('<p>'+marker+text(character['data']['name'])+' · '+text(character['data']['status'])+'</p>')
            parts.append('</td>')
        parts.append('</tr>')
    parts.append('</table>')
    for collection in contract.collections:
        entities = view.list(collection)
        if not entities or collection == 'baseline':
            continue
        parts.append('<h2>'+text(collection.replace('_',' ').title())+'</h2><ul>')
        for entity in entities:
            data = entity['data']
            projection = contract.derive(ctx, collection+'/'+entity['id']) if collection == 'characters' else {k:v for k,v in data.items() if k != 'metadata'}
            parts.append('<li><strong>'+text(data.get('name',entity['id']))+'</strong><pre>'+text(json.dumps(projection,ensure_ascii=False,sort_keys=True))+'</pre></li>')
        parts.append('</ul>')
    parts.append('</body></html>'); html = ''.join(parts)
    # One engine lock protects compare + replacement, preventing an older render
    # from replacing a newer committed-state map even after another turn.
    with store.locked():
        store.recover(); current = store.load()
        if _fingerprint(current) != _fingerprint(snapshot):
            raise RuleError('stale_render', 'Captured snapshot is no longer current; retry render_map.py without replaying an event')
        target = world / 'map.html'
        if target.is_symlink():
            raise RuleError('unsafe_path', 'Map output must not be a symlink')
        fd, temporary = tempfile.mkstemp(prefix='.map-', dir=world)
        try:
            with os.fdopen(fd,'w') as stream:
                stream.write(html); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary,target); store._fsync_directory(world)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return target
