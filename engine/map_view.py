"""Self-contained, read-only atlas presentation of a captured world snapshot."""
from html import escape
import json


STYLE = """
:root{color-scheme:dark;--bg:#111916;--panel:#19221e;--line:#354238;--text:#f3eee0;--muted:#b7c1b5;--accent:#ebca7b;--soft:#27342b;--radius:20px}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:radial-gradient(ellipse at 75% 0,#35432b55,transparent 55%),var(--bg);color:var(--text);font:15px/1.6 system-ui,-apple-system,sans-serif}
body.frontier{--bg:#111a22;--panel:#18252e;--line:#334955;--accent:#a6d5e1;--soft:#243943}
a{color:var(--accent);text-underline-offset:4px}button,summary,a{-webkit-tap-highlight-color:transparent}button{font:inherit}button:focus-visible,summary:focus-visible,a:focus-visible{outline:3px solid var(--accent);outline-offset:5px}
.skip-link{position:absolute;top:-80px;left:20px;padding:12px;background:var(--panel);z-index:5}.skip-link:focus{top:12px}.shell{max-width:1450px;margin:auto;padding:32px 40px 50px}
.topbar{display:flex;justify-content:space-between;gap:20px;align-items:center;border-bottom:1px solid var(--line);padding-bottom:20px}.brand{color:var(--accent);font-size:12px;font-weight:700;letter-spacing:.22em;text-transform:uppercase}.brand span{font-size:24px;vertical-align:middle;margin-right:10px}.topbar nav{display:flex;gap:24px;font-size:13px}.topbar nav a{text-decoration:none;color:var(--muted)}.topbar nav a:hover{color:var(--accent)}
.hero{display:grid;grid-template-columns:1fr auto;gap:30px;align-items:center;padding:38px 0 28px}.eyebrow{text-transform:uppercase;letter-spacing:.16em;font-size:11px;color:var(--accent);font-weight:700;margin:0 0 10px}h1{font:500 clamp(28px,3.4vw,48px)/1.16 Georgia,serif;max-width:850px;letter-spacing:-.025em;margin:0 0 14px}h2{font:500 24px/1.3 Georgia,serif;margin:0}h3{font-size:16px;line-height:1.4;margin:0}.subtitle,.muted{color:var(--muted)}.subtitle{margin:0;max-width:780px;font-size:13px}.world-clock{text-align:right;min-width:170px}.world-clock strong{font:500 30px Georgia,serif;display:block}.world-clock small{color:var(--muted);display:block;font-size:12px;max-width:245px;overflow-wrap:anywhere}
.badge{display:inline-flex;align-items:center;padding:4px 10px;border:1px solid var(--line);border-radius:30px;font-size:11px;color:var(--muted);line-height:1.5}.badge.gold{color:var(--accent);border-color:#857044;background:#c9a75813}.badge.fallen{color:#c9b7b2;border-color:#624c46}.badge.player{color:var(--accent);border-color:#857044}.overview{display:grid;grid-template-columns:repeat(4,1fr);border:1px solid var(--line);border-radius:var(--radius);background:var(--panel);margin-bottom:28px}.overview div{padding:16px 24px;border-right:1px solid var(--line)}.overview div:last-child{border:0}.overview strong{font:500 25px Georgia,serif;margin-right:10px}.overview span{font-size:12px;color:var(--muted)}
.atlas-layout{display:grid;grid-template-columns:minmax(0,1.9fr) minmax(290px,1fr);gap:20px;align-items:start}.panel{border:1px solid var(--line);border-radius:var(--radius);background:var(--panel);overflow:hidden}.panel-heading{display:flex;justify-content:space-between;gap:16px;align-items:center;padding:22px 24px 12px}.panel-heading p{margin:6px 0;color:var(--muted);font-size:12px}.legend{display:flex;gap:16px;align-items:center;padding:0 24px 14px;font-size:11px;color:var(--muted)}.legend i{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--accent);margin-right:6px}.legend .route{width:18px;height:1px;border-radius:0;background:#84947b}.map-scroll{overflow-x:auto;padding:0 12px 12px}.map-canvas{position:relative;min-width:760px;width:100%;background:radial-gradient(ellipse at 45% 40%,#bfa5630b,transparent 70%),radial-gradient(#66775c30 1px,transparent 1px);background-size:auto,24px 24px;border-radius:12px}.connections{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}.connections line{stroke:#748766;stroke-width:1.3;stroke-dasharray:5 5;opacity:.65;vector-effect:non-scaling-stroke}
.map-node{position:absolute;transform:translate(-50%,-50%);width:145px;min-height:76px;border:1px solid #52614d;border-radius:12px;background:#1e2b23;box-shadow:0 5px 20px #0003;color:var(--text);padding:10px 9px;cursor:pointer;text-align:center;transition:border-color .15s,background .15s,box-shadow .15s}.frontier .map-node{background:#20323e}.map-node:hover{border-color:var(--accent);background:var(--soft)}.map-node[aria-pressed=true]{border-color:var(--accent);box-shadow:0 0 0 3px #ebca7b14,0 8px 28px #0004}.node-name{display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden;font-size:12px;font-weight:600;line-height:1.4}.node-caption{display:block;color:var(--muted);font-size:10px;margin-top:6px}.map-node.current .node-caption{color:var(--accent)}
.location-panel{padding:24px}.location-panel h2{font-size:26px;margin:12px 0}.location-panel .description{font-size:13px;color:var(--muted);line-height:1.8}.location-panel h3{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--accent);margin:24px 0 10px}.location-panel .symbol{font-style:italic;color:var(--muted);font-size:12px}.occupants{list-style:none;padding:0;margin:0}.occupants li{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid var(--line);font-size:12px}.route-links{display:flex;flex-wrap:wrap;gap:8px}.route-links button{border:1px solid var(--line);border-radius:8px;background:var(--soft);color:var(--text);padding:7px 10px;font-size:11px;cursor:pointer;text-align:left}.route-links button:hover{border-color:var(--accent)}
.section{margin-top:34px;scroll-margin-top:20px}.section-heading{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}.section-heading small{font-size:11px;color:var(--muted)}.card-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}.entity-card{border:1px solid var(--line);background:var(--panel);border-radius:16px;padding:20px;min-width:0}.entity-card.is-player{border-color:#857044}.card-head{display:flex;gap:12px;align-items:flex-start;margin-bottom:16px}.avatar{flex:none;display:grid;place-items:center;width:40px;height:40px;border-radius:12px;background:var(--soft);font:500 20px Georgia,serif;color:var(--accent)}.dead .avatar{color:#baa8a1}.card-head h3{font-size:14px;margin:0 0 7px}.card-head .badge{font-size:10px}.entity-card p{font-size:12px;color:var(--muted);margin:8px 0}.entity-card .quantity{font:500 30px Georgia,serif;color:var(--text);margin:12px 0 4px}.entity-card .quantity small{font:12px system-ui;color:var(--muted);display:block;margin-top:6px}.stat-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:16px 0}.stat-grid div{background:var(--soft);border-radius:8px;padding:9px}.stat-grid dt{font-size:10px;color:var(--muted);overflow-wrap:anywhere}.stat-grid dd{margin:2px 0 0;font-size:15px}.labels{display:flex;flex-wrap:wrap;gap:5px;margin:12px 0}.labels span{border:1px solid var(--line);border-radius:6px;padding:3px 7px;font-size:10px;color:var(--muted)}
details{border-top:1px solid var(--line);margin-top:14px;padding-top:12px}summary{cursor:pointer;font-size:12px;color:var(--muted)}summary:hover{color:var(--accent)}pre{font:11px/1.6 ui-monospace,monospace;white-space:pre-wrap;overflow-wrap:anywhere;padding:12px;background:var(--bg);border-radius:8px;color:var(--muted);max-height:350px;overflow:auto}.recent{padding:24px;margin-top:28px;border-left:3px solid var(--accent)}.recent h2{font-size:22px;margin-bottom:12px}.recent p{font-size:13px;line-height:1.8;color:var(--muted);max-width:1000px;overflow-wrap:anywhere}.recent li{font-size:13px;color:var(--muted)}.recent .outcomes{display:flex;gap:10px;flex-wrap:wrap}.recent .outcomes p{margin:0;background:var(--soft);border-radius:8px;padding:8px 12px}.empty{font-size:13px;color:var(--muted)}footer{display:flex;justify-content:space-between;gap:20px;border-top:1px solid var(--line);padding-top:20px;margin-top:40px;color:var(--muted);font-size:11px}[hidden]{display:none!important}
@media(min-width:1100px){.map-canvas{min-width:0}.map-node{width:clamp(105px,10.5vw,145px)}}
@media(max-width:900px){.shell{padding:24px}.atlas-layout{grid-template-columns:1fr}.card-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.hero{grid-template-columns:1fr}.world-clock{text-align:left}.world-clock small{max-width:none}.overview div{padding:14px}.location-panel{padding:22px}}
@media(max-width:560px){.shell{padding:18px 14px}.topbar{align-items:flex-start;gap:12px;flex-direction:column}.topbar nav{gap:18px}.hero{padding:26px 0;gap:18px}.overview{grid-template-columns:repeat(2,1fr)}.overview div:nth-child(2){border-right:0}.overview div:nth-child(-n+2){border-bottom:1px solid var(--line)}.overview strong{font-size:22px}.card-grid{grid-template-columns:1fr}.panel-heading{padding:18px 18px 10px}.legend{padding-left:18px}.recent{padding:20px}footer{flex-direction:column;gap:8px}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}*{transition:none!important}}
"""

SCRIPT = """
(() => {
  const nodes = [...document.querySelectorAll('.map-node')];
  const panels = [...document.querySelectorAll('[data-location-panel]')];
  const select = (id) => {
    nodes.forEach(node => node.setAttribute('aria-pressed', String(node.dataset.locationTarget === id)));
    panels.forEach(panel => { panel.hidden = panel.dataset.locationPanel !== id; });
  };
  // Native buttons support Enter/Space; route controls select locally, never execute a turn.
  document.querySelectorAll('[data-location-target]').forEach(button => {
    button.addEventListener('click', () => {
      select(button.dataset.locationTarget);
      if (!button.classList.contains('map-node')) {
        const node = nodes.find(item => item.dataset.locationTarget === button.dataset.locationTarget);
        if (node) node.focus({preventScroll: true});
      }
    });
  });
  const current = nodes.find(node => node.getAttribute('aria-pressed') === 'true') || nodes[0];
  if (current) select(current.dataset.locationTarget);
})();
"""


def text(value):
    return escape(str(value), quote=True)


def label(value):
    return str(value).replace('_', ' ').capitalize()


def number(value):
    return f'{value:,.2f}'.rstrip('0').rstrip('.') if isinstance(value, float) else f'{value:,}' if isinstance(value, int) else str(value)


def raw_details(projection):
    return '<details class="raw-data"><summary>Technical details</summary><pre>' + text(json.dumps(projection, ensure_ascii=False, sort_keys=True, indent=2)) + '</pre></details>'


def atlas_html(contract, ctx, view, snapshot, recent):
    lore = contract.definitions['world']
    locations = lore['locations']
    by_id = {loc['id']: loc for loc in locations}
    rules = contract.definitions.get('rules', {})
    sanctuary = rules.get('sanctuary', False) or lore.get('structural_rules', {}).get('transcendent_sanctuary', False)
    characters = view.list('characters')
    player_id = contract.config['player_character_id']
    player = view.get('characters', player_id)
    current_id = player['data']['location_id'] if player else None
    selected_id = current_id if current_id in by_id else locations[0]['id'] if locations else None
    clock = snapshot['clock']['data']
    living = sum(entity['data']['status'] == 'alive' for entity in characters)
    resources = view.list('resources') if 'resources' in contract.collections else []
    active = sum(entity['data'].get('active', False) for entity in view.list('threats')) if 'threats' in contract.collections else 0
    parts = ['<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">',
             '<title>' + text(lore['name']) + ' · World Atlas</title><style>' + STYLE + '</style></head>',
             '<body class="' + ('sanctuary' if sanctuary else 'frontier') + '"><a class="skip-link" href="#atlas">Skip to world atlas</a><div class="shell">',
             '<div class="topbar"><div class="brand"><span aria-hidden="true">✧</span>Living World / Atlas</div><nav aria-label="Page sections"><a href="#characters">Characters</a><a href="#resources">Resources</a><a href="#chronicle">Chronicle</a></nav></div>',
             '<header class="hero"><div><p class="eyebrow">' + ('Transcendent sanctuary' if sanctuary else 'An unfolding world') + '</p><h1>' + text(lore['name']) + '</h1><p class="subtitle">' + text(lore.get('theme', '')) + '</p></div>',
             '<div class="world-clock"><span class="badge gold">' + ('Sanctuary' if sanctuary else 'World snapshot') + '</span><strong>Day ' + text(clock['day']) + '</strong><small>Turn ' + text(clock['turn']) + ' · ' + text(clock['display_timestamp']) + '</small></div></header>',
             '<div class="overview" aria-label="World overview">']
    for count, title in ((len(locations), 'Places connected'), (living, 'Living characters'), (len(resources), 'Resource stocks'), (active, 'Active opportunities' if sanctuary else 'Active threats')):
        parts.append('<div><strong>' + text(count) + '</strong><span>' + text(title) + '</span></div>')
    parts.append('</div><main><section id="atlas" class="atlas-layout" aria-label="World atlas"><div class="panel"><div class="panel-heading"><div><p class="eyebrow">' + ('Explore the haven' if sanctuary else 'Explore the world'))
    parts.append('</p><h2>World atlas</h2><p>Select a place to read its story and see who is there.</p></div></div><div class="legend"><span><i></i>Your location</span><span><i class="route"></i>Connected route</span><span>Read-only · selection is not movement</span></div>')

    cols = max((loc['coordinate']['col'] for loc in locations), default=0) + 1
    rows = max((loc['coordinate']['row'] for loc in locations), default=0) + 1
    width, height = max(cols, 1) * 180 + 40, max(rows, 1) * 120 + 30
    points = {loc['id']: (110 + loc['coordinate']['col'] * 180, 75 + loc['coordinate']['row'] * 120) for loc in locations}
    parts.append(f'<div class="map-scroll" tabindex="0" role="region" aria-label="Location map, scroll horizontally on small screens"><div class="map-canvas" style="aspect-ratio:{width}/{height}"><svg class="connections" viewBox="0 0 {width} {height}" aria-hidden="true" focusable="false">')
    edges = set()
    # World movement uses undirected authored edges; draw each route exactly once.
    for loc in locations:
        for other in loc.get('connected_to', []):
            edge = tuple(sorted((loc['id'], other)))
            if other in points and other != loc['id'] and edge not in edges:
                edges.add(edge)
                x1, y1 = points[loc['id']]
                x2, y2 = points[other]
                parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"/>')
    parts.append('</svg>')
    for loc in locations:
        identity = loc['id']
        occupants = [char for char in characters if char['data']['location_id'] == identity]
        x, y = points[identity]
        caption = 'You are here' if identity == current_id else f'{len(occupants)} present' if occupants else 'Sanctuary' if loc.get('safe_zone') else 'Explore'
        parts.append(f'<button type="button" class="map-node{" current" if identity == current_id else ""}" style="left:{x / width * 100:.3f}%;top:{y / height * 100:.3f}%" data-location-target="{text(identity)}" aria-controls="location-{text(identity)}" aria-pressed="{str(identity == selected_id).lower()}" title="{text(loc["name"])}"><span class="node-name">{text(loc["name"])}</span><span class="node-caption">{text(caption)}</span></button>')
    parts.append('</div></div><noscript><p class="empty">Location descriptions are listed below. Enable JavaScript for map selection.</p></noscript></div><aside class="panel" aria-label="Location details">')
    for loc in locations:
        identity = loc['id']
        parts.append(f'<section class="location-panel" id="location-{text(identity)}" data-location-panel="{text(identity)}"><p class="eyebrow">Location / {loc["coordinate"]["row"] + 1}.{loc["coordinate"]["col"] + 1}</p>')
        if identity == current_id:
            parts.append('<span class="badge gold">Your location</span>')
        if loc.get('safe_zone'):
            parts.append(' <span class="badge">Safe zone</span>')
        parts.append('<h2>' + text(loc['name']) + '</h2><p class="symbol">' + text(loc.get('symbol', '')) + '</p><p class="description">' + text(loc.get('description', '')) + '</p>')
        if loc.get('ambient_tension'):
            parts.append('<details><summary>Atmosphere</summary><p class="description">' + text(loc['ambient_tension']) + '</p></details>')
        occupants = [char for char in characters if char['data']['location_id'] == identity]
        parts.append('<h3>People here</h3><ul class="occupants">')
        for char in occupants:
            status = char['data']['status']
            parts.append('<li><span>' + ('★ ' if char['id'] == player_id else '') + text(char['data']['name']) + '</span><span class="badge' + (' fallen' if status == 'dead' else '') + '">' + text(label(status)) + '</span></li>')
        if not occupants:
            parts.append('<li class="empty">No characters recorded here.</li>')
        parts.append('</ul><h3>Connected places</h3><div class="route-links">')
        neighbors = {other for a, b in edges for here, other in ((a, b), (b, a)) if here == identity}
        for other in sorted(neighbors):
            parts.append('<button type="button" data-location-target="' + text(other) + '" aria-controls="location-' + text(other) + '">' + text(by_id[other]['name']) + ' ↗</button>')
        if not neighbors:
            parts.append('<span class="empty">No authored routes.</span>')
        parts.append('</div></section>')
    parts.append('</aside></section>')

    traits = contract.definitions.get('traits', {}).get('traits', {})
    equipment = contract.definitions.get('equipment', {}).get('items', {})
    for collection in contract.collections:
        if collection == 'baseline':
            continue
        entities = view.list(collection)
        if not entities and collection not in ('characters', 'resources'):
            continue
        title = 'Trials and Opportunities' if collection == 'threats' and sanctuary else label(collection)
        parts.append('<section class="section" id="' + text(collection) + '"><div class="section-heading"><h2>' + text(title) + '</h2><small>' + text(len(entities)) + ' recorded</small></div><div class="card-grid">')
        for entity in entities:
            data = entity['data']
            projection = contract.derive(ctx, collection + '/' + entity['id']) if collection == 'characters' else {k: v for k, v in data.items() if k != 'metadata'}
            name = data.get('name', entity['id'])
            if name == entity['id']:
                name = label(name)
            classes = 'entity-card' + (' is-player' if entity['id'] == player_id else '') + (' dead' if data.get('status') == 'dead' else '')
            parts.append('<article class="' + classes + '"><div class="card-head"><span class="avatar" aria-hidden="true">' + text(str(name)[0:1]) + '</span><div><h3>' + text(name) + '</h3>')
            if entity['id'] == player_id:
                parts.append('<span class="badge player">Player</span> ')
            if data.get('status'):
                parts.append('<span class="badge' + (' fallen' if data['status'] == 'dead' else '') + '">' + text(label(data['status'])) + '</span>')
            if data.get('capabilities', {}).get('cannot_die'):
                parts.append(' <span class="badge gold">Immortal</span>')
            parts.append('</div></div>')
            if data.get('location_id'):
                parts.append('<p>' + text(by_id.get(data['location_id'], {}).get('name', data['location_id'])) + '</p>')
            if collection == 'characters':
                vitality = 'Non-biological' if data['health'] is None else number(data['health']) + ' vitality'
                parts.append('<p class="quantity">' + text(vitality) + '</p><dl class="stat-grid">')
                for stat, value in projection.get('stats', {}).items():
                    if stat.startswith('max_'):
                        continue
                    parts.append('<div><dt>' + text(label(stat)) + '</dt><dd>' + text(number(value)) + '</dd></div>')
                parts.append('</dl>')
                for heading, ids, registry in (('Traits', data.get('traits', []), traits), ('Equipment', data.get('equipment', []), equipment)):
                    if ids:
                        parts.append('<details><summary>' + heading + ' · ' + text(len(ids)) + '</summary><div class="labels">')
                        for identity in ids:
                            parts.append('<span>' + text(registry.get(identity, {}).get('name', label(identity))) + '</span>')
                        parts.append('</div></details>')
            elif collection == 'resources':
                parts.append('<p class="quantity">' + text(number(data.get('quantity', 0))) + '<small>' + text(data.get('unit', 'units')) + '</small></p>')
                if data.get('capacity') is not None:
                    parts.append('<p>Capacity · ' + text(number(data['capacity'])) + '</p>')
            elif collection == 'groups':
                if 'count' in data:
                    parts.append('<p class="quantity">' + text(number(data['count'])) + '<small>Members available</small></p>')
                for identity in data.get('members', []):
                    member = view.get('characters', identity)
                    parts.append('<p>' + text(member['data']['name'] if member else identity) + '</p>')
            elif collection == 'actions' and data.get('kind') == 'project':
                template = rules.get('project_templates', {}).get(data.get('template_id'), {})
                parts.append('<p class="quantity">' + text(data.get('hours_committed', 0)) + ' / ' + text(template.get('hours_required', '?')) + '<small>Labor hours · ' + text(label(data.get('status', 'active'))) + '</small></p>')
                for identity, quantity in data.get('materials_committed', {}).items():
                    parts.append('<p>' + text(label(identity)) + ' · ' + text(number(quantity)) + ' / ' + text(number(template.get('materials', {}).get(identity, '?'))) + '</p>')
            else:
                if 'completed' in data:
                    parts.append('<span class="badge">' + ('Completed' if data['completed'] else 'In progress') + '</span>')
                if 'active' in data:
                    parts.append('<span class="badge">' + ('Active' if data['active'] else 'Resolved') + '</span>')
            parts.append(raw_details(projection) + '</article>')
        if not entities:
            parts.append('<p class="empty">No ' + text(collection) + ' recorded.</p>')
        parts.append('</div></section>')
    parts.append('<section id="chronicle" class="panel recent">' + (recent or '<p class="eyebrow">Chronicle</p><h2>No recent event</h2><p>This atlas shows the current committed baseline.</p>') + '</section></main><footer><span>Living World Atlas · ' + text(contract.config['world_id']) + '</span><span>Read-only projection · select to inspect, not to act</span></footer></div><script>' + SCRIPT + '</script></body></html>')
    return ''.join(parts)
