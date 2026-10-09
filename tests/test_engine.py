"""Shared engine acceptance tests; every world here is disposable."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def envelope(entity_id, data, revision=0):
    return dict(id=entity_id, revision=revision, schema_version=1, data=data)


RULES = '''
from engine.contracts import RuleResult, RuleError
def resolve(ctx, event):
    action = event['action']
    if action.get('fail'):
        raise RuleError('illegal_action', 'Cannot do this')
    effects = action.get('test_effects', [])
    return RuleResult(effects=effects, outcomes={'roll': ctx.rng.randint(1, 100)},
                      advances_turn=action.get('advances_turn', True))
def after_turn(ctx, event, outcome):
    if event['action'].get('periodic'):
        value = ctx.state.get('characters', 'hero')['data']['hp']
        return RuleResult(effects=[{'op':'set','collection':'characters',
            'entity_id':'hero','path':'/hp','value':value-1}], notes=['periodic'])
    return RuleResult()
def validate(ctx):
    return ['negative hp'] if ctx.state.get('characters', 'hero')['data']['hp'] < 0 else []
'''


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.world = Path(self.temp.name).resolve()
        self.config = dict(world_id='test-world', contract_version=1,
                           state_schema_version=1, player_character_id='hero',
                           collections={'characters': {'schema': 'schemas/character.json'},
                                        'fleets': {'schema': 'schemas/fleet.json', 'allow_remove': True}},
                           definitions={'locations': 'legacy/locations.json'},
                           logic={name: 'logic/rules.py:' + name
                                  for name in ('resolve', 'after_turn', 'validate')})
        self.schema = dict(type='object', additionalProperties=False,
                           required=['hp', 'location_id'], properties={
                               'hp': {'type': 'number'}, 'location_id': {'type': 'string'},
                               'note': {'type': 'string'}, 'tags': {'type': 'array'},
                               'nested': {'type': 'object', 'properties': {'x': {'type': 'number'}},
                                          'additionalProperties': False}})
        write(self.world/'world.json', self.config)
        write(self.world/'schemas/character.json', self.schema)
        write(self.world/'schemas/fleet.json', {'type': 'object', 'properties': {'fuel': {'type':'number'}},
                                              'required':['fuel'], 'additionalProperties':False})
        write(self.world/'legacy/locations.json', {'home': {'name': 'Home'}, 'away': {'name': 'Away'}})
        (self.world/'logic').mkdir()
        (self.world/'logic/rules.py').write_text(RULES)
        write(self.world/'state/characters/hero.json', envelope('hero', {'hp':10, 'location_id':'home'}))
        write(self.world/'state/fleets/old.json', envelope('old', {'fuel':3}))
        write(self.world/'state/clock.json', envelope('clock', {'turn':0, 'day':1, 'display_timestamp':'Dawn'}))

    def event(self, effects=(), **action):
        return dict(schema_version=1, event_id='event_1', world_id='test-world', expected_turn=0,
                    action=dict(type='test', test_effects=list(effects), **action))

    def effect(self, op='increment', path='/hp', value=2, **extra):
        return dict(op=op, collection='characters', entity_id='hero', path=path, value=value, **extra)

    def files(self):
        return {str(p.relative_to(self.world)): p.read_bytes() for p in self.world.rglob('*')
                if p.is_file() and p.name != '.engine.lock'}

    def run_event(self, event=None, **kwargs):
        from engine.runner import run_event
        return run_event(self.world, event or self.event(), render=False, **kwargs)

    def assert_rejected_unchanged(self, event):
        from engine.contracts import RuleError
        before = self.files()
        with self.assertRaises(RuleError):
            self.run_event(event)
        self.assertEqual(before, self.files())

    def test_engine_public_contract_available(self):
        try:
            from engine.contracts import WorldContract, StateView, DefinitionView, RuleContext, RuleResult, RuleError
        except ImportError as exc:
            self.fail(f'Engine public contract not implemented: {exc}')
        contract = WorldContract(self.world)
        self.assertEqual(contract.config['world_id'], 'test-world')
        self.assertTrue(callable(contract.resolve))
        self.assertTrue(callable(contract.derive))
        self.assertEqual(RuleResult().effects, [])
        self.assertTrue(RuleResult().advances_turn)

    def test_views_are_defensive_and_stably_sorted(self):
        from engine.contracts import StateView, DefinitionView
        state = {'things': {'z': envelope('z', {'n':1}), 'a': envelope('a', {'n':2})}}
        view = StateView(state)
        state['things']['a']['data']['n'] = 9
        view.get('things', 'a')['data']['n'] = 7
        self.assertEqual([x['id'] for x in view.list('things')], ['a','z'])
        self.assertEqual(view.get('things','a')['data']['n'], 2)
        defs = DefinitionView({'a': {'nested':[1]}})
        defs.get('a')['nested'].append(2)
        self.assertEqual(defs.get('a'), {'nested':[1]})

    def test_dry_run_is_exactly_read_only(self):
        before = self.files()
        report = self.run_event(self.event([self.effect()], periodic=True), dry_run=True, seed=17)
        self.assertEqual(before, self.files())
        self.assertEqual(report['changes']['characters/hero']['after']['data']['hp'], 11)
        self.assertEqual(report['changes']['characters/hero']['after']['revision'], 1)
        self.assertEqual(len(report['effects']), 2)
        self.assertEqual(report['turn']['after'], 1)
        json.dumps(report, allow_nan=False)

    def test_custom_collection_and_ordered_reducer(self):
        effects = [self.effect('set', value=20), self.effect(value=-2),
                   {'op':'create','collection':'fleets','entity_id':'new','value':{'fuel':8}},
                   {'op':'increment','collection':'fleets','entity_id':'new','path':'/fuel','value':-1}]
        report = self.run_event(self.event(effects))
        self.assertEqual(report['changes']['characters/hero']['after']['data']['hp'], 18)
        self.assertEqual(report['changes']['fleets/new']['after'], envelope('new', {'fuel':7}))
        self.assertEqual(json.loads((self.world/'state/clock.json').read_text())['data']['turn'], 1)
        self.assertTrue((self.world/'events/committed/event_1.json').exists())

    def test_invalid_events_leave_no_changes(self):
        for change in ({'world_id':'other'}, {'expected_turn':1}, {'event_id':'../evil'},
                       {'schema_version':2}, {'action':[]}, {'effects':[]}, {'expected_turn':True},
                       {'expected_revisions':{'characters/hero':9}}):
            with self.subTest(change=change):
                event = self.event(); event.update(change)
                self.assert_rejected_unchanged(event)

    def test_duplicate_and_missing_archive_do_not_reapply(self):
        self.run_event(self.event([self.effect()]))
        (self.world/'events/committed/event_1.json').unlink()
        from engine.contracts import RuleError
        with self.assertRaises(RuleError):
            self.run_event()
        self.assertEqual(json.loads((self.world/'state/characters/hero.json').read_text())['data']['hp'], 12)
        self.assertTrue((self.world/'events/committed/event_1.json').exists())

    def test_failed_rule_and_world_invariant_leave_no_changes(self):
        self.assert_rejected_unchanged(self.event(fail=True))
        self.assert_rejected_unchanged(self.event([self.effect(value=-20)]))

    def test_reducer_rejects_ambiguous_or_invalid_effects(self):
        effects = [self.effect('set', '/missing', 1), self.effect(path='/revision'),
                   self.effect(value=True), self.effect(value=float('inf')),
                   self.effect('set','/hp', 'ten'), self.effect('set','/location_id','missing'),
                   self.effect('set','/tags/0', 'x'), self.effect('remove'),
                   {'op':'remove','collection':'characters','entity_id':'hero'},
                   {'op':'create','collection':'characters','entity_id':'hero','value':{}},
                   self.effect(entity_id_override='oops')]
        for effect in effects:
            with self.subTest(effect=effect):
                self.assert_rejected_unchanged(self.event([effect]))

    def test_optional_field_and_entity_removal(self):
        write(self.world/'state/characters/hero.json', envelope('hero', {'hp':10,'location_id':'home','note':'x'}))
        report = self.run_event(self.event([
            {'op':'remove','collection':'characters','entity_id':'hero','path':'/note'},
            {'op':'remove','collection':'fleets','entity_id':'old'}]))
        self.assertNotIn('note', report['changes']['characters/hero']['after']['data'])
        self.assertIsNone(report['changes']['fleets/old']['after'])
        self.assertFalse((self.world/'state/fleets/old.json').exists())

    def test_non_turn_action_checks_revisions_and_skips_periodic(self):
        event = self.event([self.effect()], advances_turn=False, periodic=True)
        event['expected_revisions'] = {'characters/hero':0}
        report = self.run_event(event)
        self.assertEqual(report['turn'], {'before':0,'after':0,'advances_turn':False})
        self.assertEqual(report['changes']['characters/hero']['after']['data']['hp'],12)
        stale = copy.deepcopy(event); stale['event_id']='event_2'
        self.assert_rejected_unchanged(stale)

    def test_replay_preserves_metadata_without_resolve_or_rng(self):
        from engine.runner import replay_event
        report = self.run_event(self.event([self.effect()], periodic=True), dry_run=True, seed=41)
        (self.world/'logic/rules.py').write_text('raise RuntimeError("rules must not be loaded for replay")')
        with patch('engine.runner.random.Random',side_effect=AssertionError('replay must not use RNG')):
            result = replay_event(self.world, report, render=False)
        self.assertEqual(result['metadata'], report['metadata'])
        self.assertEqual(result['effects'], report['effects'])
        self.assertEqual(result['outcomes'], report['outcomes'])
        self.assertEqual(result['changes'], report['changes'])

    def test_snapshot_recovers_interrupted_create_remove_commit(self):
        from engine.state_store import StateStore
        from engine.runner import read_snapshot
        effects = [{'op':'create','collection':'fleets','entity_id':'new','value':{'fuel':8}},
                   {'op':'remove','collection':'fleets','entity_id':'old'}]
        original = StateStore._write_json
        def interrupted(store, path, value):
            if path == self.world/'state/clock.json':
                raise OSError('simulated power loss')
            return original(store, path, value)
        with patch.object(StateStore, '_write_json', interrupted):
            with self.assertRaises(OSError):
                self.run_event(self.event(effects))
        snapshot = read_snapshot(self.world)
        self.assertEqual(snapshot['clock']['data']['turn'],1)
        self.assertEqual(set(snapshot['fleets']), {'new'})
        self.assertTrue((self.world/'events/committed/event_1.json').exists())
        self.assertEqual(read_snapshot(self.world), snapshot)

    def test_recovery_when_archive_write_fails(self):
        from engine.state_store import StateStore
        from engine.runner import read_snapshot
        original = StateStore._write_json
        def interrupted(store, path, value):
            if path.parent == self.world/'events/committed':
                raise OSError('archive failure')
            return original(store, path, value)
        with patch.object(StateStore, '_write_json', interrupted):
            with self.assertRaises(OSError):
                self.run_event(self.event([self.effect()]))
        self.assertEqual(read_snapshot(self.world)['characters']['hero']['data']['hp'], 12)
        self.assertTrue((self.world/'events/committed/event_1.json').exists())

    def test_contract_rejects_unsafe_paths_invalid_schemas_and_hooks(self):
        from engine.contracts import WorldContract, RuleError
        variants = []
        for field, value in [('world_id','../bad'), ('contract_version',2), ('extra',1)]:
            config=copy.deepcopy(self.config); config[field]=value; variants.append(config)
        config=copy.deepcopy(self.config); config['logic']['resolve']='../outside.py:resolve'; variants.append(config)
        config=copy.deepcopy(self.config); config['logic']['resolve']='logic/rules.py:missing'; variants.append(config)
        config=copy.deepcopy(self.config); config['collections']['characters']['schema']='https://example.com/schema'; variants.append(config)
        for config in variants:
            write(self.world/'world.json',config)
            with self.subTest(config=config), self.assertRaises(RuleError): WorldContract(self.world)
        write(self.world/'world.json',self.config)
        write(self.world/'schemas/character.json', {'type':'bogus'})
        with self.assertRaises(RuleError): WorldContract(self.world)
        write(self.world/'schemas/character.json', {'$ref':'https://example.com/schema'})
        with self.assertRaises(RuleError): WorldContract(self.world)

    def test_symlink_and_strict_envelope_are_rejected(self):
        from engine.runner import read_snapshot
        from engine.contracts import RuleError
        path=self.world/'state/characters/hero.json'
        write(path,dict(envelope('hero',{'hp':10,'location_id':'home'}), extra=True))
        with self.assertRaises(RuleError): read_snapshot(self.world)
        path.unlink(); path.symlink_to(self.world/'state/fleets/old.json')
        with self.assertRaises(RuleError): read_snapshot(self.world)

    def test_renderer_failure_is_reported_after_commit(self):
        from engine.runner import run_event
        def render(snapshot):
            self.assertEqual(snapshot['clock']['data']['turn'],1)
            raise RuntimeError('broken renderer')
        report=run_event(self.world,self.event(),render=render)
        self.assertIn('broken renderer',report['render_error'])
        self.assertTrue((self.world/'events/committed/event_1.json').exists())

    def staged_baseline(self):
        from engine.runner import read_snapshot
        snapshot = read_snapshot(self.world)
        for path in (self.world/'state').rglob('*.json'):
            path.unlink()
        return snapshot

    def test_initialize_baseline_validates_and_refuses_existing_state(self):
        from engine.state_store import StateStore
        from engine.contracts import RuleError
        from engine.runner import read_snapshot
        snapshot = self.staged_baseline()
        store = StateStore(self.world)
        bad = copy.deepcopy(snapshot); bad['characters']['hero']['revision'] = True
        before = self.files()
        with self.assertRaises(RuleError): store.initialize_baseline(bad)
        self.assertEqual(before, self.files())
        store.initialize_baseline(snapshot)
        self.assertEqual(read_snapshot(self.world), snapshot)
        before = self.files()
        with self.assertRaises(RuleError): store.initialize_baseline(snapshot)
        self.assertEqual(before, self.files())

    def test_initialize_baseline_recovers_interrupted_installation(self):
        from engine.state_store import StateStore
        from engine.runner import read_snapshot
        snapshot = self.staged_baseline()
        original = StateStore._write_json
        def interrupted(store, path, value):
            if path == self.world/'state/clock.json': raise OSError('baseline power loss')
            return original(store, path, value)
        with patch.object(StateStore, '_write_json', interrupted):
            with self.assertRaises(OSError): StateStore(self.world).initialize_baseline(snapshot)
        self.assertEqual(read_snapshot(self.world), snapshot)

    def test_contained_schema_references_and_builtin_schemas(self):
        from engine.contracts import WorldContract, BUILTIN_SCHEMAS
        write(self.world/'schemas/number.json', {'type':'number','minimum':0})
        schema=copy.deepcopy(self.schema); schema['properties']['hp']={'$ref':'number.json'}
        write(self.world/'schemas/character.json', schema)
        self.run_event(self.event([self.effect()]), dry_run=True)
        for name in BUILTIN_SCHEMAS:
            self.config['collections'][name+'s']={'schema':'engine:'+name}
        write(self.world/'world.json', self.config)
        contract=WorldContract(self.world)
        for name in BUILTIN_SCHEMAS:
            contract.validate_envelope(name+'s', 'sample', envelope('sample', {'name':'Example'}))
            from engine.contracts import RuleError
            with self.assertRaises(RuleError):
                contract.validate_envelope(name+'s','sample',envelope('sample',{'unknown':1}))

    def test_dict_only_pointer_escapes_and_net_zero_revision(self):
        schema=copy.deepcopy(self.schema)
        schema['properties']['nested']={'type':'object','properties':{'a/b':{'type':'number'},'~x':{'type':'number'}},'additionalProperties':False}
        write(self.world/'schemas/character.json',schema)
        write(self.world/'state/characters/hero.json',envelope('hero',{'hp':10,'location_id':'home','nested':{'a/b':1,'~x':2},'tags':['x']}))
        report=self.run_event(self.event([self.effect(path='/nested/a~1b'),self.effect(path='/nested/~0x')]),dry_run=True)
        self.assertEqual(report['changes']['characters/hero']['after']['data']['nested'],{'a/b':3,'~x':4})
        for pointer in ('/tags/0','/nested/~2x','', '/nested/missing'):
            self.assert_rejected_unchanged(self.event([self.effect(path=pointer)]))
        report=self.run_event(self.event([self.effect(),self.effect(value=-2)],advances_turn=False),dry_run=True)
        self.assertEqual(report['changes'],{})

    def test_replay_rejects_malformed_records_and_stale_before_images(self):
        from engine.runner import replay_event
        from engine.contracts import RuleError
        record=self.run_event(self.event([self.effect()]),dry_run=True)
        for key, value in [('metadata',[]),('turn',None),('effects',{}),('outcomes',[]),('event_id','different')]:
            bad=copy.deepcopy(record); bad[key]=value
            before=self.files()
            with self.subTest(key=key), self.assertRaises(RuleError): replay_event(self.world,bad,render=False)
            self.assertEqual(before,self.files())
        bad=copy.deepcopy(record); bad['changes']['characters/hero']['before']['revision']=4
        with self.assertRaises(RuleError): replay_event(self.world,bad,render=False)

    def test_recovery_at_each_durable_write_boundary(self):
        from engine.state_store import StateStore
        from engine.runner import read_snapshot
        # A normal transaction has prepared, clock, entity, committed, archive writes.
        baseline=self.files()
        for boundary in range(1,6):
            with self.subTest(boundary=boundary):
                # New disposable world for each interruption, never reset live state.
                with tempfile.TemporaryDirectory() as temp:
                    world=Path(temp).resolve()
                    for relative, payload in baseline.items():
                        path=world/relative; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(payload)
                    original=StateStore._write_json
                    count=0
                    def interrupted(store,path,value):
                        nonlocal count
                        original(store,path,value)
                        count+=1
                        if count==boundary: raise OSError('power loss after durable write')
                    from engine.runner import run_event
                    with patch.object(StateStore,'_write_json',interrupted):
                        with self.assertRaises(OSError): run_event(world,self.event([self.effect()]),render=False)
                    snapshot=read_snapshot(world)
                    self.assertEqual(snapshot['characters']['hero']['data']['hp'],12)
                    self.assertEqual(snapshot['clock']['data']['turn'],1)
                    self.assertTrue((world/'events/committed/event_1.json').exists())
                    self.assertEqual(snapshot,read_snapshot(world))

    def test_invalid_hook_results_and_exceptions_leave_state_unchanged(self):
        for body in ('return {}', 'raise RuntimeError("bad rule")',
                     'return RuleResult(advances_turn=1)', 'return RuleResult(notes=[{}])'):
            (self.world/'logic/rules.py').write_text('from engine.contracts import RuleResult\ndef resolve(ctx,event):\n    '+body+'\n')
            config=copy.deepcopy(self.config); config['logic']={'resolve':'logic/rules.py:resolve'}
            write(self.world/'world.json',config)
            self.assert_rejected_unchanged(self.event())

    def test_clock_calendar_effects_and_after_turn_complete_overlay(self):
        effects=[{'op':'set','collection':'clock','entity_id':'clock','path':'/day','value':2},
                 {'op':'set','collection':'clock','entity_id':'clock','path':'/display_timestamp','value':'Evening'}]
        report=self.run_event(self.event(effects),dry_run=True)
        self.assertEqual(report['changes']['clock']['after']['data'],{'turn':1,'day':2,'display_timestamp':'Evening'})
        for pointer in ('/turn','/revision','/schema_version'):
            self.assert_rejected_unchanged(self.event([dict(effects[0],path=pointer)]))

    def test_state_rejects_bad_revision_identity_unknown_fields_and_references(self):
        from engine.runner import read_snapshot
        from engine.contracts import RuleError
        variants=[envelope('other',{'hp':10,'location_id':'home'}),
                  envelope('hero',{'hp':10,'location_id':'home'},revision=True),
                  envelope('hero',{'hp':10,'location_id':'home','unknown':4}),
                  envelope('hero',{'hp':10,'location_id':'missing'}),
                  dict(envelope('hero',{'hp':10,'location_id':'home'}),schema_version=2)]
        for value in variants:
            write(self.world/'state/characters/hero.json',value)
            with self.assertRaises(RuleError): read_snapshot(self.world)

    def test_recovery_rejects_journal_archive_image_mismatch(self):
        from engine.runner import read_snapshot
        from engine.contracts import RuleError
        self.run_event(self.event([self.effect()]))
        path=self.world/'transactions/event_1.json'
        journal=json.loads(path.read_text())
        journal['status']='prepared'
        journal['archive']['changes']['characters/hero']['after']['data']['hp']=99
        write(path,journal)
        (self.world/'events/committed/event_1.json').unlink()
        before=self.files()
        with self.assertRaises(RuleError): read_snapshot(self.world)
        self.assertEqual(before,self.files())

    def test_rules_module_supports_standard_dataclass_decorators(self):
        source='''from __future__ import annotations
from dataclasses import dataclass
from engine.contracts import RuleResult
@dataclass
class Value:
    amount: int = 2
def resolve(ctx,event):
    return RuleResult(outcomes={'amount':Value().amount})
'''
        (self.world/'logic/rules.py').write_text(source)
        config=copy.deepcopy(self.config); config['logic']={'resolve':'logic/rules.py:resolve'}
        write(self.world/'world.json',config)
        self.assertEqual(self.run_event(dry_run=True)['outcomes'],{'amount':2})

    def test_create_must_be_schema_valid_even_when_later_removed(self):
        self.assert_rejected_unchanged(self.event([
            {'op':'create','collection':'fleets','entity_id':'new','value':{'unknown':1}},
            {'op':'remove','collection':'fleets','entity_id':'new'}]))

    def test_remove_recreate_identical_entity_preserves_revision_and_snapshot(self):
        from engine.runner import run_event
        write(self.world/'state/fleets/old.json',envelope('old',{'fuel':3},revision=7))
        captured=[]
        report=run_event(self.world,self.event([
            {'op':'remove','collection':'fleets','entity_id':'old'},
            {'op':'create','collection':'fleets','entity_id':'old','value':{'fuel':3}}]),
            render=lambda snapshot: captured.append(snapshot))
        self.assertNotIn('fleets/old',report['changes'])
        self.assertEqual(captured[0]['fleets']['old']['revision'],7)

    def test_casefold_collection_declarations_reject_read_only(self):
        from engine.contracts import WorldContract, RuleError
        for name in ('CHARACTERS', 'CLOCK'):
            config=copy.deepcopy(self.config)
            config['collections'][name]={'schema':'schemas/character.json'}
            write(self.world/'world.json',config)
            before=self.files()
            with self.subTest(name=name), self.assertRaises(RuleError): WorldContract(self.world)
            self.assertEqual(before,self.files())

    def test_casefold_create_alias_rejects_read_only(self):
        self.assert_rejected_unchanged(self.event([
            {'op':'create','collection':'characters','entity_id':'HERO',
             'value':{'hp':1,'location_id':'home'}}]))

    def test_casefold_remove_create_alias_rejects_read_only(self):
        remove={'op':'remove','collection':'fleets','entity_id':'old'}
        create={'op':'create','collection':'fleets','entity_id':'OLD','value':{'fuel':3}}
        self.assert_rejected_unchanged(self.event([remove,create]))
        # Aliases spanning primary/periodic overlays must not evade identity checks.
        source=RULES+'''\ndef after_turn(ctx,event,outcome):
    return RuleResult(effects=[{'op':'create','collection':'fleets','entity_id':'OLD','value':{'fuel':3}}])
'''
        (self.world/'logic/rules.py').write_text(source)
        self.assert_rejected_unchanged(self.event([remove]))

    def test_casefold_baseline_aliases_reject_before_install(self):
        from engine.state_store import StateStore
        from engine.contracts import RuleError
        snapshot=self.staged_baseline()
        snapshot['characters']['HERO']=envelope('HERO',{'hp':1,'location_id':'home'})
        before=self.files()
        with self.assertRaises(RuleError): StateStore(self.world).initialize_baseline(snapshot)
        self.assertEqual(before,self.files())

    def test_casefold_load_layout_aliases_reject_on_all_filesystems(self):
        from engine.runner import read_snapshot
        from engine.contracts import RuleError
        original=Path.iterdir
        for directory, alias in ((self.world/'state','CHARACTERS'),
                                 (self.world/'state/characters','HERO.json')):
            def entries(path):
                found=list(original(path))
                return iter(found+[path/alias]) if path==directory else iter(found)
            before=self.files()
            with self.subTest(alias=alias), patch.object(Path,'iterdir',entries):
                with self.assertRaises(RuleError) as error: read_snapshot(self.world)
                self.assertEqual(error.exception.code,'casefold_collision')
            self.assertEqual(before,self.files())

    def test_casefold_journal_targets_reject_before_any_writes(self):
        from engine.state_store import StateStore
        from engine.runner import read_snapshot
        from engine.contracts import RuleError
        report=self.run_event(dry_run=True)
        # A corrupt/direct-store target may alias an untouched entity on disk.
        report['changes']['characters/HERO']={'before':None,'after':envelope('HERO',{'hp':1,'location_id':'home'})}
        store=StateStore(self.world)
        before=self.files()
        with store.locked():
            with self.assertRaises(RuleError): store.commit(report)
        self.assertEqual(before,self.files())
        journal={'version':1,'status':'prepared','event_id':report['event_id'],
                 'expected_revisions':{ref:images['before']['revision'] if images['before'] else None
                                       for ref,images in report['changes'].items()},
                 'changes':report['changes'],'archive':report}
        write(self.world/'transactions/event_1.json',journal)
        before=self.files()
        with self.assertRaises(RuleError): read_snapshot(self.world)
        self.assertEqual(before,self.files())

    def test_full_baseline_replay_rejects_untouched_nonturn_change_read_only(self):
        from engine.runner import replay_event
        from engine.contracts import RuleError
        source=RULES+'''\ndef validate(ctx):
    hero=ctx.state.get('characters','hero')['data']['hp']
    fuel=ctx.state.get('fleets','old')['data']['fuel']
    return ['cross-entity invariant'] if hero > fuel+10 else []
'''
        (self.world/'logic/rules.py').write_text(source)
        recorded=self.run_event(self.event([self.effect()]),dry_run=True)
        change=self.event([{'op':'set','collection':'fleets','entity_id':'old','path':'/fuel','value':0}],advances_turn=False)
        change['event_id']='event_other'
        self.run_event(change)
        (self.world/'logic/rules.py').write_text('raise RuntimeError("replay must not load rules")')
        before=self.files()
        with patch('engine.runner.random.Random',side_effect=AssertionError('replay must not use RNG')):
            with self.assertRaises(RuleError) as error: replay_event(self.world,recorded,render=False)
        self.assertEqual(error.exception.code,'stale_baseline')
        self.assertEqual(before,self.files())

    def test_full_baseline_fingerprint_is_canonical_and_complete(self):
        import hashlib
        from engine.runner import read_snapshot
        before=read_snapshot(self.world)
        expected=hashlib.sha256(json.dumps(before,sort_keys=True,separators=(',',':'),
                                            ensure_ascii=False,allow_nan=False).encode('utf-8')).hexdigest()
        report=self.run_event(dry_run=True)
        self.assertEqual(report['metadata'].get('baseline_sha256'),expected)
        # Whitespace/key order on disk must not change semantic baseline identity.
        path=self.world/'state/characters/hero.json'
        path.write_text(json.dumps(dict(reversed(list(before['characters']['hero'].items()))),indent=4))
        self.assertEqual(self.run_event(dry_run=True)['metadata']['baseline_sha256'],expected)
        mutations=[('data',1),('revision',1),('membership',1),('clock',1)]
        for kind,_ in mutations:
            snapshot=copy.deepcopy(before)
            if kind=='data': snapshot['fleets']['old']['data']['fuel']=4
            elif kind=='revision': snapshot['fleets']['old']['revision']=1
            elif kind=='membership': snapshot['fleets']['new']=envelope('new',{'fuel':3})
            else: snapshot['clock']['data']['day']=2
            with tempfile.TemporaryDirectory() as temp:
                world=Path(temp).resolve()
                for relative,payload in self.files().items():
                    path=world/relative; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(payload)
                for collection,entities in snapshot.items():
                    if collection=='clock': write(world/'state/clock.json',entities)
                    else:
                        for entity_id,value in entities.items(): write(world/f'state/{collection}/{entity_id}.json',value)
                from engine.runner import run_event, replay_event
                from engine.contracts import RuleError
                changed=run_event(world,self.event(),dry_run=True,render=False)
                self.assertNotEqual(changed['metadata']['baseline_sha256'],expected)
                untouched={str(p.relative_to(world)):p.read_bytes() for p in world.rglob('*') if p.is_file()}
                with self.assertRaises(RuleError): replay_event(world,report,render=False)
                self.assertEqual(untouched,{str(p.relative_to(world)):p.read_bytes() for p in world.rglob('*') if p.is_file()})


if __name__ == '__main__':
    unittest.main()
