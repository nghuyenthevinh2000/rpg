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
from .map_view import atlas_html


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
        text = lambda value: escape(str(value), quote=True)

        parts = []

        # Render Last Event Outcomes if a valid committed receipt is found
        if receipt is not None:
            outcomes = receipt.get('outcomes', {})
            event_obj = receipt.get('event', {})
            narrative = event_obj.get('narrative') or receipt.get('narrative', '')
            parts.append('<h2>Last Event Outcomes</h2><div class="outcomes">')
            if narrative:
                parts.append('<details><summary>Read the chronicle</summary><p>'+text(narrative)+'</p></details>')
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
            if outcomes.get('resources'):
                parts.append(f'<p>Resource Outcomes: {text(json.dumps(outcomes["resources"], sort_keys=True))}</p>')
            # Other outcome keys
            handled = {'damage_dealt', 'remaining_health', 'retaliations', 'retaliation_raw',
                       'retaliation_damage', 'armor_mitigation', 'injuries', 'casualties',
                       'stance', 'healed', 'new_health', 'action', 'actor_id', 'target_id',
                       'recipe_id', 'restored_health', 'trial_id', 'resolved_by',
                       'project_action', 'project_id', 'resources'}
            for k, v in sorted(outcomes.items()):
                if k not in handled and v not in ([], {}):
                    parts.append(f'<p>{text(k)}: {text(str(v))}</p>')
            parts.append('</div>')

        html = atlas_html(contract, ctx, view, snapshot, ''.join(parts))

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
