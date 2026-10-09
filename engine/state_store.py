"""Durable split-state storage. Engine readers must hold the world lock."""
from contextlib import contextmanager
from copy import deepcopy
import fcntl
import os
from pathlib import Path
import tempfile
import json

from .contracts import (WorldContract, RuleError, contained_path, load_json, safe_id,
                        json_value, casefold_unique)


class StateStore:
    def __init__(self, world_dir, contract=None):
        self.world_dir = Path(world_dir).resolve()
        self.contract = contract or WorldContract(self.world_dir, load_hooks=False)

    def path(self, relative):
        return contained_path(self.world_dir, relative)

    @contextmanager
    def locked(self):
        path = self.path('.engine.lock')
        # ponytail: one world-wide lock; partition only if world throughput requires it.
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            self._validate_layout()
            self.recover()
            yield self
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    @staticmethod
    def _fsync_directory(path):
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def _mkdir(self, path):
        if not path.exists():
            self._mkdir(path.parent)
            path.mkdir(exist_ok=True)
            self._fsync_directory(path.parent)

    def _write_json(self, path, value):
        """Atomic durable file boundary, also the fault-injection boundary in tests."""
        path = self.path(str(Path(path).relative_to(self.world_dir)))
        json_value(value)
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n'
        self._mkdir(path.parent)
        fd, name = tempfile.mkstemp(prefix='.engine-', suffix='.tmp', dir=path.parent)
        try:
            with os.fdopen(fd, 'w') as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, path)
            self._fsync_directory(path.parent)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def _remove(self, path):
        path = self.path(str(Path(path).relative_to(self.world_dir)))
        if path.exists():
            path.unlink()
            self._fsync_directory(path.parent)

    def entity_path(self, reference):
        if reference == 'clock':
            return self.path('state/clock.json')
        if not isinstance(reference, str) or reference.count('/') != 1:
            raise RuleError('invalid_reference', f'Invalid entity reference: {reference!r}')
        collection, entity_id = reference.split('/')
        safe_id(collection); safe_id(entity_id)
        if collection not in self.contract.collections:
            raise RuleError('invalid_reference', f'Undeclared collection: {collection}')
        return self.path(f'state/{collection}/{entity_id}.json')

    def _validate_layout(self):
        """Check directory spelling and filenames before recovery can write."""
        state_dir = self.path('state')
        if state_dir.exists():
            casefold_unique([*(entry.name for entry in state_dir.iterdir()),
                             *self.contract.collections, 'clock.json'], 'State layout')
        targets = ['clock.json']
        for collection in self.contract.collections:
            directory = self.path(f'state/{collection}')
            if directory.exists():
                names = [entry.name for entry in directory.iterdir()]
                casefold_unique(names, f'{collection} filenames')
                targets.extend(f'{collection}/{name}' for name in names)
        return targets

    def _validate_targets(self, changes):
        targets = [str(self.entity_path(reference).relative_to(self.world_dir/'state'))
                   for reference in changes]
        casefold_unique(targets, 'Transaction targets')
        casefold_unique([*self._validate_layout(), *targets], 'Transaction/layout targets')

    def load(self):
        """Load under locked(); undeclared legacy collections are deliberately ignored."""
        self._validate_layout()
        state = {'clock': load_json(self.path('state/clock.json'))}
        for collection in self.contract.collections:
            state[collection] = {}
            directory = self.path(f'state/{collection}')
            if not directory.exists():
                continue
            for path in sorted(directory.iterdir()):
                if path.name.startswith('.engine-') and path.suffix == '.tmp':
                    continue
                if path.suffix != '.json' or not path.is_file():
                    raise RuleError('invalid_state', f'Unexpected collection entry: {path}')
                entity_id = safe_id(path.stem)
                state[collection][entity_id] = load_json(self.entity_path(f'{collection}/{entity_id}'))
        self.contract.validate_state(state)
        return state

    def snapshot(self):
        with self.locked():
            return deepcopy(self.load())

    def initialize_baseline(self, snapshot):
        """Journal-install validated envelopes into an empty staged canonical world.

        snapshot has the same shape as snapshot()/read_snapshot(): a clock envelope
        and collection -> entity ID -> envelope mappings. Existing revisions are
        preserved. This is a migration baseline, not a replayable gameplay event.
        """
        snapshot = deepcopy(snapshot)
        json_value(snapshot)
        expected = set(self.contract.collections) | {'clock'}
        if not isinstance(snapshot, dict) or set(snapshot) != expected:
            raise RuleError('invalid_baseline', 'Baseline must contain clock and exactly the declared collections')
        for collection in self.contract.collections:
            if not isinstance(snapshot[collection], dict):
                raise RuleError('invalid_baseline', 'Collections must be ID-keyed objects')
            for entity_id in snapshot[collection]:
                safe_id(entity_id)
        self.contract.validate_state(snapshot)
        with self.locked():
            state_dir = self.path('state')
            if state_dir.exists():
                for entry in state_dir.rglob('*'):
                    self.path(str(entry.relative_to(self.world_dir)))
                    if not entry.is_dir():
                        raise RuleError('existing_state', 'Baseline installation requires empty canonical state')
            transactions = self.path('transactions')
            committed = self.path('events/committed')
            if any(directory.exists() and any(directory.iterdir()) for directory in (transactions, committed)):
                raise RuleError('existing_state', 'Baseline installation requires no prior transactions or committed events')
            changes = {'clock': {'before':None,'after':deepcopy(snapshot['clock'])}}
            for collection in sorted(self.contract.collections):
                for entity_id, envelope in sorted(snapshot[collection].items()):
                    changes[f'{collection}/{entity_id}'] = {'before':None,'after':deepcopy(envelope)}
            report = {'event_id':'engine_baseline', 'world_id':self.contract.config['world_id'],
                      'kind':'baseline', 'dry_run':False, 'changes':changes,
                      'metadata':{'contract_version':self.contract.config['contract_version'],
                                  'state_schema_version':self.contract.config['state_schema_version']}}
            self.commit(report)
            return deepcopy(report)

    def is_duplicate(self, event_id):
        safe_id(event_id)
        return self.path(f'transactions/{event_id}.json').exists() or self.path(f'events/committed/{event_id}.json').exists()

    def _validate_journal(self, journal, event_id):
        if not isinstance(journal, dict) or set(journal) != {'version','status','event_id','expected_revisions','changes','archive'}:
            raise RuleError('invalid_journal', 'Invalid transaction fields')
        if journal['version'] != 1 or journal['status'] not in ('prepared','committed') or journal['event_id'] != event_id:
            raise RuleError('invalid_journal', 'Invalid transaction identity/status')
        if not isinstance(journal['archive'], dict) or journal['archive'].get('event_id') != event_id:
            raise RuleError('invalid_journal', 'Invalid transaction archive')
        if not isinstance(journal['changes'], dict) or not isinstance(journal['expected_revisions'], dict):
            raise RuleError('invalid_journal', 'Invalid transaction changes/revisions')
        if journal['archive'].get('changes') != journal['changes']:
            raise RuleError('invalid_journal', 'Archive images differ from transaction images')
        if set(journal['expected_revisions']) != set(journal['changes']):
            raise RuleError('invalid_journal', 'Revision/image keys differ')
        casefold_unique(journal['changes'], 'Journal targets')
        if journal['status'] == 'prepared':
            self._validate_targets(journal['changes'])
        for reference, images in journal['changes'].items():
            self.entity_path(reference)
            if not isinstance(images, dict) or set(images) != {'before','after'}:
                raise RuleError('invalid_journal', 'Invalid transaction image')
            collection, entity_id = ('clock','clock') if reference == 'clock' else reference.split('/')
            for image in images.values():
                if image is not None:
                    self.contract.validate_envelope(collection, entity_id, image)
            before = images['before']
            if journal['expected_revisions'][reference] != (before['revision'] if before else None):
                raise RuleError('invalid_journal', 'Revision differs from before image')

    def _apply_images(self, changes):
        for reference, images in sorted(changes.items()):
            path = self.entity_path(reference)
            if images['after'] is None:
                self._remove(path)
            else:
                self._write_json(path, images['after'])

    def _finish(self, path, journal):
        archive_path = self.path(f"events/committed/{journal['event_id']}.json")
        # Retain committed journals as durable identity receipts, even if an archive is lost.
        if journal['status'] == 'prepared':
            self._apply_images(journal['changes'])
            journal['status'] = 'committed'
            self._write_json(path, journal)
        if not archive_path.exists():
            self._write_json(archive_path, journal['archive'])
        elif load_json(archive_path) != journal['archive']:
            raise RuleError('archive_conflict', f'Archive differs from journal: {archive_path}')

    def recover(self):
        directory = self.path('transactions')
        if not directory.exists():
            return
        for entry in sorted(directory.iterdir()):
            if entry.name.startswith('.engine-') and entry.suffix == '.tmp':
                continue
            if entry.suffix != '.json' or not entry.is_file():
                raise RuleError('invalid_journal', f'Unexpected transaction entry: {entry}')
            event_id = safe_id(entry.stem)
            path = self.path(f'transactions/{event_id}.json')
            journal = load_json(path)
            self._validate_journal(journal, event_id)
            self._finish(path, journal)

    def commit(self, report):
        event_id = safe_id(report['event_id'])
        if self.is_duplicate(event_id):
            raise RuleError('duplicate_event', f'Event already committed: {event_id}')
        archive = deepcopy(report)
        archive['dry_run'] = False
        journal = {'version':1, 'status':'prepared', 'event_id':event_id,
                   'expected_revisions': {ref: images['before']['revision'] if images['before'] else None
                                          for ref, images in report['changes'].items()},
                   'changes':deepcopy(report['changes']), 'archive':archive}
        self._validate_journal(journal, event_id)
        path = self.path(f'transactions/{event_id}.json')
        self._write_json(path, journal)
        self._finish(path, journal)
