"""Validated world contracts and defensive rule interfaces (trusted Python only)."""
from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import importlib
from importlib.abc import Loader, MetaPathFinder
from importlib.machinery import ModuleSpec
import json
import math
from pathlib import Path
import re
import sys
from types import ModuleType
from urllib.parse import unquote, urljoin, urlparse

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012


class RuleError(Exception):
    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code, self.message, self.details = code, message, details

    def to_dict(self):
        return {'code': self.code, 'message': self.message, 'details': self.details}


def safe_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}', value):
        raise RuleError('unsafe_id', f'Unsafe identifier: {value!r}')
    return value


def casefold_unique(values, label):
    """Preserve authored spelling, rejecting portable filesystem aliases."""
    seen = {}
    for value in values:
        folded = value.casefold()
        if folded in seen and seen[folded] != value:
            raise RuleError('casefold_collision', f'{label}: {seen[folded]!r} aliases {value!r}')
        seen[folded] = value


def contained_path(root, relative):
    root = Path(root).resolve()
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise RuleError('unsafe_path', f'Expected world-relative path: {relative!r}')
    parts = Path(relative).parts
    if '..' in parts or ':' in relative or '\\' in relative:
        raise RuleError('unsafe_path', f'Unsafe path: {relative!r}')
    path = root
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise RuleError('unsafe_path', f'Symlink is not allowed: {path}')
    if not path.resolve().is_relative_to(root):
        raise RuleError('unsafe_path', f'Path escapes world: {relative!r}')
    return path


def json_value(value):
    """Reject non-JSON Python values, including NaN/Infinity and non-string keys."""
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float) and math.isfinite(value):
        return
    if isinstance(value, list):
        for item in value:
            json_value(item)
        return
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for item in value.values():
            json_value(item)
        return
    raise RuleError('invalid_json', f'Not a finite JSON value: {value!r}')


def load_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f'Duplicate JSON key: {key}')
            result[key] = value
        return result
    try:
        value = json.loads(Path(path).read_text(), object_pairs_hook=pairs)
        json_value(value)
        return value
    except (OSError, ValueError) as exc:
        raise RuleError('invalid_json', f'Cannot read {path}: {exc}') from exc


def validate_schema(validator, value, label):
    json_value(value)
    try:
        errors = sorted(validator.iter_errors(value), key=lambda e: str(e.path))
    except Exception as exc:
        raise RuleError('invalid_schema', f'{label}: {exc}') from exc
    if errors:
        raise RuleError('schema_violation', f'{label}: {errors[0].message}',
                        {'path': list(errors[0].absolute_path)})


@dataclass
class RuleResult:
    effects: list = field(default_factory=list)
    outcomes: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)
    advances_turn: bool = True


class StateView:
    def __init__(self, state):
        self.__state = deepcopy(state)

    def get(self, collection, entity_id):
        safe_id(collection); safe_id(entity_id)
        if collection == 'clock':
            return deepcopy(self.__state.get('clock')) if entity_id == 'clock' else None
        return deepcopy(self.__state.get(collection, {}).get(entity_id))

    def list(self, collection):
        safe_id(collection)
        if collection == 'clock':
            return [deepcopy(self.__state['clock'])] if 'clock' in self.__state else []
        return [deepcopy(value) for _, value in sorted(self.__state.get(collection, {}).items())]


class DefinitionView:
    def __init__(self, definitions):
        self.__definitions = deepcopy(definitions)

    def get(self, name):
        return deepcopy(self.__definitions.get(name))


@dataclass(frozen=True)
class RuleContext:
    state: StateView
    definitions: DefinitionView
    rng: object
    turn: int


def object_schema(properties, required=()):
    return {'type': 'object', 'properties': properties, 'required': list(required),
            'additionalProperties': False}


STRING = {'type': 'string'}
NUMBER = {'type': 'number'}
NONNEG_INT = {'type': 'integer', 'minimum': 0}
ID = {'type': 'string', 'pattern': r'^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$'}
COMMON = {'name': STRING, 'description': STRING, 'status': STRING,
          'location_id': ID, 'metadata': {'type': 'object'}}
BUILTIN_SCHEMAS = {
    'resource': object_schema({**COMMON, 'amount': NUMBER, 'quantity': NUMBER,
                              'capacity': NUMBER, 'unit': STRING}),
    'threat': object_schema({**COMMON, 'stats': {'type':'object','additionalProperties':NUMBER},
                            'level': NUMBER, 'active': {'type':'boolean'},
                            'activation_turn': NONNEG_INT, 'tags': {'type':'array','items':STRING}}),
    'location': object_schema({**COMMON, 'owner_id': ID, 'damage': NUMBER, 'tension': NUMBER}),
    'action': object_schema({**COMMON, 'type': STRING, 'completed': {'type':'boolean'},
                            'progress': NUMBER, 'actor_id': ID, 'target_id': ID}),
    'group': object_schema({**COMMON, 'members': {'type':'array','items':ID},
                           'count': NONNEG_INT, 'stats': {'type':'object','additionalProperties':NUMBER}}),
}
CLOCK_SCHEMA = object_schema({'turn': NONNEG_INT, 'day': NONNEG_INT,
                              'display_timestamp': STRING}, ('turn','day','display_timestamp'))
ENVELOPE_SCHEMA = object_schema({'id': ID, 'revision': NONNEG_INT,
                                 'schema_version': {'type':'integer','const':1},
                                 'data': {'type':'object'}}, ('id','revision','schema_version','data'))
EVENT_SCHEMA = object_schema({
    'schema_version': {'type':'integer','const':1}, 'event_id': ID, 'world_id': ID,
    'expected_turn': NONNEG_INT,
    'expected_revisions': {'type':'object','additionalProperties':NONNEG_INT},
    'action': {'type':'object','required':['type'],'properties':{'type':{'type':'string','minLength':1}}},
    'narrative': STRING,
}, ('schema_version','event_id','world_id','expected_turn','action'))
CONTRACT_SCHEMA = object_schema({
    'world_id': ID, 'contract_version': {'type':'integer','const':1},
    'state_schema_version': {'type':'integer','const':1}, 'player_character_id': ID,
    'collections': {'type':'object','minProperties':1,'additionalProperties': object_schema(
        {'schema':STRING,'allow_remove':{'type':'boolean'}}, ('schema',))},
    'definitions': {'type':'object','additionalProperties':STRING},
    'logic': object_schema({name:STRING for name in ('resolve','after_turn','derive','validate')}, ('resolve',)),
}, ('world_id','contract_version','state_schema_version','player_character_id','collections','logic'))


class _RuleSources(MetaPathFinder, Loader):
    """Import only captured source in registered, hash-scoped rule packages."""
    def __init__(self):
        self.packages = {}

    def find_spec(self, fullname, path=None, target=None):
        namespace, _, relative = fullname.partition('.')
        if namespace not in self.packages or not relative:
            return None
        directory, sources = self.packages[namespace]
        base = directory.joinpath(*relative.split('.'))
        module_path = base.with_suffix('.py')
        package_path = base / '__init__.py'
        is_package = package_path in sources
        if is_package:
            module_path = package_path
        elif module_path not in sources:
            if any(source.is_relative_to(base) for source in sources):
                spec = ModuleSpec(fullname, None, is_package=True)
                spec.submodule_search_locations = [str(base)]
                return spec
            # Do not fall through to filesystem/bytecode imports of unhashed files.
            raise ModuleNotFoundError(f'No captured rule source: {fullname}', name=fullname)
        spec = ModuleSpec(fullname, self, origin=str(module_path), is_package=is_package)
        spec.loader_state = (module_path, sources[module_path])
        if is_package:
            spec.submodule_search_locations = [str(base)]
        return spec

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        path, source = module.__spec__.loader_state
        module.__file__ = str(path)
        # Compile captured bytes, never timestamp/size-validated cached bytecode.
        exec(compile(source, str(path), 'exec'), module.__dict__)


_RULE_SOURCES = _RuleSources()


class WorldContract:
    def __init__(self, world_dir, *, load_hooks=True):
        self.world_dir = Path(world_dir).resolve()
        self.config = load_json(contained_path(self.world_dir, 'world.json'))
        validate_schema(Draft202012Validator(CONTRACT_SCHEMA), self.config, 'world contract')
        self.collections = self.config['collections']
        casefold_unique([*self.collections, 'clock'], 'Collection names')
        self.schemas, self.validators = {}, {}
        self._schema_documents = {}
        for name, config in self.collections.items():
            safe_id(name)
            if name == 'clock':
                raise RuleError('invalid_contract', 'clock is reserved')
            reference = config['schema']
            if reference.startswith('engine:'):
                try:
                    schema = deepcopy(BUILTIN_SCHEMAS[reference[7:]])
                except KeyError as exc:
                    raise RuleError('invalid_contract', f'Unknown built-in schema: {reference}') from exc
            else:
                path = contained_path(self.world_dir, reference)
                schema = self._load_schema(path)
            self.schemas[name] = schema
        registry = Registry().with_resources((uri, Resource.from_contents(schema, default_specification=DRAFT202012))
                                             for uri, schema in self._schema_documents.items())
        for name, schema in self.schemas.items():
            self.validators[name] = Draft202012Validator(schema, registry=registry)
        self.definitions = {}
        for name, reference in self.config.get('definitions', {}).items():
            safe_id(name)
            self.definitions[name] = load_json(contained_path(self.world_dir, reference))
        self.definition_view = DefinitionView(self.definitions)
        self.resolve = None
        self.after_turn = lambda ctx, event, outcome: RuleResult()
        self.derive = lambda ctx, entity_ref: {}
        self.validate = lambda ctx: []
        source_hash = hashlib.sha256()
        hooks, directories, sources = {}, set(), {}
        for name, reference in sorted(self.config['logic'].items()):
            if reference.count(':') != 1:
                raise RuleError('invalid_hook', f'Invalid hook reference: {reference}')
            filename, function = reference.split(':')
            if not function.isidentifier():
                raise RuleError('invalid_hook', f'Invalid function name: {function}')
            path = contained_path(self.world_dir, filename)
            if path.suffix != '.py':
                raise RuleError('invalid_hook', 'Rule modules must be Python files')
            hooks[name] = (path, function, reference)
            directories.add(path.parent)
        if not load_hooks:
            self.rule_source_hash = source_hash.hexdigest()
            return  # Replay/snapshots/recovery validate references, not Python source.
        try:
            for directory in sorted(directories):
                for candidate in directory.rglob('*'):
                    if '__pycache__' in candidate.relative_to(directory).parts:
                        continue
                    path = contained_path(self.world_dir, str(candidate.relative_to(self.world_dir)))
                    if path.is_file() and path.suffix == '.py':
                        sources[path] = path.read_bytes()
            for path, _, reference in hooks.values():
                if path not in sources:
                    raise RuleError('invalid_hook', f'Missing rule source: {reference}')
        except OSError as exc:
            raise RuleError('invalid_hook', f'Cannot read rule sources: {exc}') from exc
        for path, source in sorted(sources.items()):
            source_hash.update(str(path.relative_to(self.world_dir)).encode())
            source_hash.update(b'\0')
            source_hash.update(len(source).to_bytes(8, 'big'))
            source_hash.update(source)
        self.rule_source_hash = source_hash.hexdigest()
        if _RULE_SOURCES not in sys.meta_path:
            sys.meta_path.insert(0, _RULE_SOURCES)
        packages = {}
        for directory in sorted(directories):
            identity = hashlib.sha256(str(directory).encode()).hexdigest()
            namespace = 'rpg_rules_' + identity + '_' + self.rule_source_hash
            packages[directory] = namespace
            if namespace not in sys.modules:
                package = ModuleType(namespace)
                package.__package__ = namespace
                package.__path__ = [str(directory)]
                package.__spec__ = ModuleSpec(namespace, None, is_package=True)
                package.__spec__.submodule_search_locations = package.__path__
                _RULE_SOURCES.packages[namespace] = (directory, sources)
                sys.modules[namespace] = package
        for name, (path, function, reference) in hooks.items():
            try:
                namespace = packages[path.parent]
                module = importlib.import_module(namespace + '.' + path.stem)
            except Exception as exc:
                raise RuleError('invalid_hook', f'Cannot load {reference}: {exc}') from exc
            hook = getattr(module, function, None)
            if not callable(hook):
                raise RuleError('invalid_hook', f'Not a callable hook: {reference}')
            setattr(self, name, hook)

    def _load_schema(self, path):
        uri = path.as_uri()
        if uri in self._schema_documents:
            return self._schema_documents[uri]
        schema = load_json(path)
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as exc:
            raise RuleError('invalid_schema', f'{path}: {exc}') from exc
        if not isinstance(schema, dict):
            raise RuleError('invalid_schema', 'Collection schemas must be objects')
        if '$id' in schema and schema['$id'] != uri:
            raise RuleError('invalid_schema', 'Schema $id must equal its contained file URI or be omitted')
        schema['$id'] = uri
        self._schema_documents[uri] = schema
        def inspect(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key == '$id' and value is not schema:
                        raise RuleError('invalid_schema', 'Nested schema $id is not supported')
                    if key in ('$ref', '$dynamicRef'):
                        parsed = urlparse(urljoin(uri, item))
                        if parsed.scheme != 'file' or parsed.netloc or parsed.query:
                            raise RuleError('invalid_schema', 'External schema references are forbidden')
                        target = Path(unquote(parsed.path))
                        if not target.is_relative_to(self.world_dir):
                            raise RuleError('invalid_schema', 'Schema reference escapes world')
                        target = contained_path(self.world_dir, str(target.relative_to(self.world_dir)))
                        if target != path:
                            self._load_schema(target)
                    inspect(item)
            elif isinstance(value, list):
                for item in value: inspect(item)
        inspect(schema)
        return schema

    def validate_envelope(self, collection, entity_id, envelope):
        validate_schema(Draft202012Validator(ENVELOPE_SCHEMA), envelope, f'{collection}/{entity_id}')
        if envelope['id'] != entity_id:
            raise RuleError('identity_mismatch', f'Envelope ID differs from filename: {collection}/{entity_id}')
        validator = Draft202012Validator(CLOCK_SCHEMA) if collection == 'clock' else self.validators[collection]
        validate_schema(validator, envelope['data'], f'{collection}/{entity_id} data')

    def validate_state(self, state):
        casefold_unique(state, 'State collection names')
        self.validate_envelope('clock', 'clock', state['clock'])
        locations = set(state.get('locations', {}))
        definitions = self.definitions.get('locations', {})
        if isinstance(definitions, dict):
            entries = definitions.get('locations', definitions)
        else:
            entries = definitions
        if isinstance(entries, dict):
            locations.update(entries)
        elif isinstance(entries, list):
            locations.update(item.get('id') for item in entries if isinstance(item, dict))
        for collection in self.collections:
            casefold_unique(state[collection], f'{collection} entity IDs')
            for entity_id, envelope in state[collection].items():
                self.validate_envelope(collection, entity_id, envelope)
                location = envelope['data'].get('location_id')
                if location is not None and location not in locations:
                    raise RuleError('invalid_reference', f'{collection}/{entity_id}: unknown location_id {location}')
