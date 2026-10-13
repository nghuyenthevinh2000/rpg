"""Atlas presentation generated from temporary canonical snapshots."""
from html.parser import HTMLParser

from engine.render_map import render_map
from tests.world_fixtures import TemporaryWorldCase, hashes


class AtlasMarkup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.nodes = []
        self.panels = []
        self.edges = []
        self.raw_open = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'button' and 'map-node' in attrs.get('class', '').split():
            self.nodes.append(attrs)
        if 'data-location-panel' in attrs:
            self.panels.append(attrs)
        if tag == 'line':
            self.edges.append(attrs)
        if tag == 'details' and 'raw-data' in attrs.get('class', ''):
            self.raw_open.append('open' in attrs)


class AtlasTests(TemporaryWorldCase):
    def test_atlas_has_connected_selectable_locations_and_closed_raw_details(self):
        world = self.make_world('warhammer-40k')
        before = hashes(world / 'state')
        html = render_map(world).read_text()
        markup = AtlasMarkup()
        markup.feed(html)
        self.assertEqual(11, len(markup.nodes))
        self.assertEqual(11, len(markup.panels))
        self.assertGreater(len(markup.edges), 0)
        self.assertEqual({'location-' + n['data-location-target'] for n in markup.nodes},
                         {p['id'] for p in markup.panels})
        current = next(n for n in markup.nodes if n['data-location-target'] == 'loc_shrine_aquila')
        self.assertEqual('true', current['aria-pressed'])
        self.assertTrue(markup.raw_open)
        self.assertFalse(any(markup.raw_open))
        self.assertIn('name="viewport"', html)
        self.assertIn('Sanctuary', html)
        self.assertIn('Your location', html)
        self.assertNotIn('<table>', html)
        self.assertEqual(before, hashes(world / 'state'))

    def test_location_lore_is_escaped_in_atlas_and_detail_panel(self):
        world = self.make_world('lost-world')
        import json
        path = world / 'definitions/world.json'
        lore = json.loads(path.read_text())
        lore['locations'][0]['name'] = '<script>location</script>'
        lore['locations'][0]['description'] = '<img src=x onerror=alert(1)>'
        path.write_text(json.dumps(lore))
        html = render_map(world).read_text()
        self.assertIn('&lt;script&gt;location&lt;/script&gt;', html)
        self.assertIn('&lt;img src=x onerror=alert(1)&gt;', html)
        self.assertNotIn('<script>location</script>', html)
        self.assertNotIn('<img src=x', html)
