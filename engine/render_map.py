"""Escaped projection of one committed snapshot, with stale-render protection and committed outcome rendering."""
import hashlib
from html import escape
import json
import os
from pathlib import Path
import random
import tempfile
from engine.contracts import RuleContext, RuleError, StateView, WorldContract
from engine.state_store import StateStore
from .world_utils import require_canonical


def _fingerprint(snapshot):
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def render_map(world_dir, snapshot=None, *, committed_event=None):
    world = Path(world_dir).resolve(); require_canonical(world)
    contract = WorldContract(world)
    store = StateStore(world, contract)

    with store.locked():
        store.recover(); current = store.load()
        if snapshot is None:
            snapshot = current
        elif _fingerprint(current) != _fingerprint(snapshot):
            raise RuleError('stale_render', 'Captured snapshot is no longer current; retry python -m engine render without replaying an event')


        # Find latest matching gameplay receipt if not explicitly provided
        clock = snapshot['clock']['data']
        current_turn = clock['turn']

        receipt = committed_event
        if receipt is None:
            committed_dir = world / 'events/committed'
            if committed_dir.exists():
                best_turn = -1
                for path in committed_dir.glob('*.json'):
                    if path.name.startswith('.') or path.stem == 'engine_baseline':
                        continue
                    try:
                        data = json.loads(path.read_text())
                        r_turn = data.get('turn', {}).get('after')
                        if type(r_turn) is int and r_turn == current_turn and r_turn > best_turn:
                            # Verify changes match snapshot after-images
                            changes = data.get('changes', {})
                            match = True
                            for ref, img in changes.items():
                                if ref == 'clock':
                                    if snapshot.get('clock') != img.get('after'):
                                        match = False; break
                                else:
                                    col, ident = ref.split('/')
                                    if snapshot.get(col, {}).get(ident) != img.get('after'):
                                        match = False; break
                            if match:
                                receipt = data
                                best_turn = r_turn
                    except Exception:
                        continue
        else:
            # Validate provided receipt matches snapshot turn and after-images
            r_turn = receipt.get('turn', {}).get('after') if isinstance(receipt.get('turn'), dict) else None
            changes = receipt.get('changes')
            if r_turn is None or r_turn != current_turn or not isinstance(changes, dict):
                receipt = None
            else:
                for ref, img in changes.items():
                    if ref == 'clock':
                        if snapshot.get('clock') != img.get('after'):
                            receipt = None; break
                    else:
                        col, ident = ref.split('/')
                        if snapshot.get(col, {}).get(ident) != img.get('after'):
                            receipt = None; break

        view = StateView(snapshot)
        ctx = RuleContext(view, contract.definition_view, random.Random(0), current_turn)
        lore = contract.definitions['world']; locations = lore['locations']
        text = lambda value: escape(str(value), quote=True)

        parts = ['<!doctype html><html><head><meta charset="utf-8"><title>'+text(lore['name'])+'</title>',
                 '<style>body{font:16px system-ui;margin:2em;background:#101820;color:#eee}table{border-collapse:collapse}td{border:1px solid #678;padding:1em;vertical-align:top}small{display:block}li{margin:.6em}</style></head><body>',
                 '<h1>'+text(lore['name'])+'</h1><p>Turn '+text(clock['turn'])+' · Day '+text(clock['day'])+' · '+text(clock['display_timestamp'])+'</p>',
                 '<p>'+text(lore.get('theme', ''))+'</p>']

        # Render Last Event Outcomes if a valid committed receipt is found
        if receipt is not None:
            outcomes = receipt.get('outcomes', {})
            event_obj = receipt.get('event', {})
            narrative = event_obj.get('narrative') or receipt.get('narrative', '')
            parts.append('<h2>Last Event Outcomes</h2><div class="outcomes">')
            if narrative:
                parts.append('<p><strong>Narrative:</strong> '+text(narrative)+'</p>')
            if 'damage_dealt' in outcomes:
                rem_hp = outcomes.get('remaining_health', 0)
                parts.append(f'<p>Damage Dealt: {text(outcomes["damage_dealt"])} · Remaining Threat Health: {text(rem_hp)}</p>')
            if 'casualties' in outcomes:
                parts.append(f'<p>Casualties: {text(outcomes["casualties"])}</p>')
            if 'injuries' in outcomes and isinstance(outcomes['injuries'], dict):
                parts.append('<ul>')
                for pid, inj in sorted(outcomes['injuries'].items()):
                    parts.append(f'<li>{text(pid)}: damage {text(inj.get("damage", 0))} · status {text(inj.get("status", ""))} · health {text(inj.get("health", ""))}</li>')
                parts.append('</ul>')
            if 'healed' in outcomes:
                parts.append(f'<p>Healed: {text(outcomes["healed"])} · New Health: {text(outcomes.get("new_health", 0))}</p>')
            if 'restored_health' in outcomes:
                parts.append(f'<p>Restored Health: {text(outcomes["restored_health"])}</p>')
            if 'trial_id' in outcomes:
                parts.append(f'<p>Trial Resolved: {text(outcomes["trial_id"])} by {text(outcomes.get("resolved_by", ""))}</p>')
            if 'project_action' in outcomes:
                parts.append(f'<p>Project Action: {text(outcomes["project_action"])} · Project: {text(outcomes.get("project_id", ""))}</p>')
            if 'resources' in outcomes:
                parts.append(f'<p>Resource Outcomes: {text(json.dumps(outcomes["resources"], sort_keys=True))}</p>')
            # Other outcome keys
            handled = {'damage_dealt', 'remaining_health', 'retaliations', 'retaliation_raw',
                       'retaliation_damage', 'armor_mitigation', 'injuries', 'casualties',
                       'stance', 'healed', 'new_health', 'action', 'actor_id', 'target_id',
                       'recipe_id', 'restored_health', 'trial_id', 'resolved_by',
                       'project_action', 'project_id', 'resources'}
            for k, v in sorted(outcomes.items()):
                if k not in handled:
                    parts.append(f'<p>{text(k)}: {text(str(v))}</p>')
            parts.append('</div>')

        parts.append('<table>')
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

        sanctuary = contract.definitions['rules'].get('sanctuary', False) or contract.definitions['world'].get('structural_rules', {}).get('transcendent_sanctuary', False)

        for collection in contract.collections:
            entities = view.list(collection)
            if not entities or collection == 'baseline':
                continue
            section_title = 'Trials and Opportunities' if collection == 'threats' and sanctuary else collection.replace('_',' ').title()
            parts.append('<h2>'+text(section_title)+'</h2><ul>')
            for entity in entities:
                data = entity['data']
                projection = contract.derive(ctx, collection+'/'+entity['id']) if collection == 'characters' else {k:v for k,v in data.items() if k != 'metadata'}
                extra = ''
                if collection == 'actions' and data.get('kind') == 'project':
                    extra = f"<p>Progress: {text(data.get('hours_committed', 0))} / {text(contract.definitions['rules'].get('project_templates', {}).get(data.get('template_id'), {}).get('hours_required', '?'))} hours · Status: {text(data.get('status', 'active')).title()}</p>"
                parts.append('<li><strong>'+text(data.get('name',entity['id']))+'</strong>'+extra+'<pre>'+text(json.dumps(projection,ensure_ascii=False,sort_keys=True))+'</pre></li>')
            parts.append('</ul>')
        parts.append('</body></html>'); html = ''.join(parts)

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
