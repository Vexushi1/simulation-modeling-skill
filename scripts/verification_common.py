"""Strict shared Phase H readers; no runtime execution or decision writeback."""
from __future__ import annotations

import math
import json
import os
import sys
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

import yaml

from runtime_common import (ROOT, UniqueLoader, _invalid_constant, _unique_json, canonical_digest,
                            contained_path, load_contract, load_document, schema_errors, sha256_file)
from validate_parameter_provenance import bind_file
from validate_simulation_protocol import selected_value

H1_FILES = (
    'core/numerical_verification_contract.yaml', 'modules/07_numerical_verification.md',
    'templates/contracts/numerical_verification.yaml', 'packs/evidence/convergence.md',
    'scripts/verification_common.py', 'scripts/validate_numerical_verification.py',
    'scripts/run_numerical_verification.py', 'scripts/validate_numerical_verification_receipt.py',
)
HARD_BUDGET = {'max_file_bytes': 67108864, 'max_total_bytes': 268435456,
               'max_samples_per_output': 12001, 'max_result_bytes': 4194304}
GRAPH_LIMITS = {'max_files': 16384, 'max_edges': 131072,
                'max_document_nodes': 1000000, 'max_document_depth': 128}
BYTE_LIMITS = {'max_file_bytes': 67108864, 'max_total_bytes': 1073741824}
SOURCE_AUTHORITY_BUDGET = {**HARD_BUDGET, 'max_file_bytes': 1048576,
                           'max_total_bytes': 1048576,
                           'max_document_nodes': 20000, 'max_document_depth': 32}


def graph_limit(budget, name):
    """Legacy four-field budgets retain explicit bounded discovery ceilings."""
    value = (budget or {}).get(name, GRAPH_LIMITS[name])
    if type(value) is not int or not 0 < value <= GRAPH_LIMITS[name]:
        raise ValueError('invalid verification graph budget: ' + name)
    return value


def byte_limit(budget, name):
    value = budget[name]
    if type(value) is not int or not 0 < value <= BYTE_LIMITS[name]:
        raise ValueError('invalid verification byte budget: ' + name)
    return value


class RepositorySourcePaths(list):
    """Known source-list metadata is guarded independently of claimed paths."""
    def __init__(self, paths, authority, original_bytes):
        super().__init__(paths)
        self.authority = authority
        self.original_bytes = original_bytes

    def assert_authority_unchanged(self):
        if self.authority.read_bytes() != self.original_bytes:
            raise ValueError('repository source authority changed during discovery')


def repository_source_paths():
    """Only the maintained safety closure can grant repository path authority."""
    authority = ROOT / 'core/simulation_assurance_contract.yaml'
    if not authority.is_file() or authority.stat().st_size > SOURCE_AUTHORITY_BUDGET['max_file_bytes']:
        raise ValueError('repository source authority exceeds bounded metadata bootstrap')
    original = authority.read_bytes()
    value = _parse_structured(original.decode('utf-8-sig'), authority, SOURCE_AUTHORITY_BUDGET)
    names = value.get('source_files') if isinstance(value, dict) else None
    if not isinstance(names, list) or not names or any(not isinstance(name, str) or not name for name in names):
        raise ValueError('repository source authority requires a complete file list')
    if any(Path(name).is_absolute() or '..' in Path(name).parts for name in names):
        raise ValueError('repository source authority must use contained relative paths')
    paths = [contained_path(ROOT, name) for name in dict.fromkeys(names + list(H1_FILES))]
    if authority not in paths:
        raise ValueError('repository source closure must bind its own authority')
    result = RepositorySourcePaths(paths, authority, original)
    result.assert_authority_unchanged()
    return result


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def typed_equal(actual, expected):
    """Preserve exact JSON snapshot/result types, including integer versus float."""
    if type(actual) is not type(expected):
        return False
    if type(actual) in (int, float):
        return finite(actual) and finite(expected) and actual == expected
    if isinstance(actual, dict):
        return set(actual) == set(expected) and all(typed_equal(actual[k], expected[k]) for k in actual)
    if isinstance(actual, list):
        return len(actual) == len(expected) and all(typed_equal(a, b) for a, b in zip(actual, expected))
    return actual == expected


def semantic_digest(value):
    return canonical_digest({k: v for k, v in value.items() if k not in {'status', 'review_record'}})


def source_identities(budget=None):
    paths = repository_source_paths()
    # The complete maintained source set is statted before any source digest.
    stat_manifest(paths, ROOT, budget or HARD_BUDGET)
    paths.assert_authority_unchanged()
    result = {path.relative_to(ROOT).as_posix(): sha256_file(path) for path in paths}
    paths.assert_authority_unchanged()
    return result


def bound_file(path, root=None):
    path = Path(path).resolve()
    if root is not None and not path.is_relative_to(Path(root).resolve()):
        raise ValueError('verification input leaves project root: ' + str(path))
    return {'path': str(path), 'sha256': sha256_file(path)}


def limited_document(path, budget=None):
    value = limited_source_document(path, budget)
    if not isinstance(value, dict):
        raise ValueError('expected an object in ' + str(path))
    return value


def limited_source_document(path, budget=None):
    """Read an object/array task source with the existing unique parser rules.

    This broader root shape never applies to business/qualification documents.
    Array selectors are data selection, not evidence-role authorization.
    """
    path = Path(path)
    if not path.is_file() or path.stat().st_size > byte_limit(budget or HARD_BUDGET, 'max_file_bytes'):
        raise ValueError('verification source missing or exceeds byte budget: ' + str(path))
    text = path.read_text(encoding='utf-8-sig')
    return _parse_structured(text, path, budget)


def _parse_structured(text, path, budget):
    try:
        if path.suffix.lower() == '.json':
            value = json.loads(text, object_pairs_hook=_unique_json, parse_constant=_invalid_constant)
        else:
            value = yaml.load(text, Loader=UniqueLoader)
    except (yaml.YAMLError, RecursionError) as error:
        raise ValueError(f'invalid or excessively nested structured source in {path}: {error}') from error
    if not isinstance(value, (dict, list)):
        raise ValueError('expected a structured source object or array in ' + str(path))
    _bounded_document(value, budget, label=str(path))
    return value


def _bounded_document(value, budget, *, label):
    """Bound actual shared nodes/depth; aliases do not require expansion to read.

    Expanded JSON work is assessed separately when an actual request/result is
    serialized. Legal old YAML DAGs remain shared during evidence discovery.
    """
    node_limit = graph_limit(budget, 'max_document_nodes')
    depth_limit = graph_limit(budget, 'max_document_depth')
    pending, active, complete, depths = [(value, False)], set(), set(), {}
    count = 0
    while pending:
        node, leaving = pending.pop()
        if not leaving:
            count += 1
            if count > node_limit:
                raise ValueError('structured evidence node budget exceeded: ' + label)
        if type(node) is float and not math.isfinite(node):
            raise ValueError('non-finite structured source value in ' + label)
        if not isinstance(node, (dict, list)):
            continue
        identity = id(node)
        if leaving:
            active.remove(identity)
            complete.add(identity)
            children = [item for pair in node.items() for item in pair] if isinstance(node, dict) else node
            depths[identity] = 1 + max((depths[id(child)] if isinstance(child, (dict, list)) else 0 for child in children), default=0)
            if depths[identity] > depth_limit:
                raise ValueError('structured evidence node/depth budget exceeded: ' + label)
            continue
        if identity in active:
            raise ValueError('cyclic structured source in ' + label)
        if identity in complete:
            continue
        active.add(identity)
        pending.append((node, True))
        if isinstance(node, dict):
            for key, child in node.items():
                pending.append((key, False))
                pending.append((child, False))
        else:
            pending.extend((child, False) for child in node)


def serialization_forecast(value, budget, *, label='verification serialization'):
    """Exact pretty-JSON byte and expanded-node forecast without expansion.

    Each shared container is evaluated once. Byte size is affine in indentation
    depth, so repeated aliases at different depths are measured exactly before
    json.dumps allocates their expanded representation.
    """
    _bounded_document(value, budget, label=label)
    metrics, pending = {}, [(value, False)]
    node_limit = graph_limit(budget, 'max_document_nodes')
    depth_limit = graph_limit(budget, 'max_document_depth')
    byte_cap = byte_limit(budget, 'max_file_bytes')
    while pending:
        node, leaving = pending.pop()
        if not isinstance(node, (dict, list)):
            continue
        identity = id(node)
        if identity in metrics:
            continue
        children = list(node.values()) if isinstance(node, dict) else node
        if not leaving:
            pending.append((node, True))
            pending.extend((child, False) for child in children if isinstance(child, (dict, list)))
            continue
        if isinstance(node, dict) and any(not isinstance(key, str) for key in node):
            raise ValueError('serialized verification object keys must be strings')
        child_metrics = [metrics[id(child)] if isinstance(child, (dict, list)) else
                         (len(json.dumps(child, ensure_ascii=False, allow_nan=False).encode('utf-8')), 0, 1, 0)
                         for child in children]
        count = len(children)
        if not count:
            item = (2, 0, 1, 1)
        else:
            key_bytes = sum(len(json.dumps(key, ensure_ascii=False).encode('utf-8')) for key in node) if isinstance(node, dict) else 0
            base = 2 + (6 if isinstance(node, dict) else 4) * count + key_bytes + sum(base + slope for base, slope, _, _ in child_metrics)
            slope = 2 * (count + 1) + sum(item[1] for item in child_metrics)
            nodes = 1 + (count if isinstance(node, dict) else 0) + sum(item[2] for item in child_metrics)
            depth = 1 + max((item[3] for item in child_metrics), default=0)
            item = (base, slope, nodes, depth)
        if item[0] + 1 > byte_cap or item[2] > node_limit or item[3] > depth_limit:
            raise ValueError(label + ' expanded bytes/node/depth budget exceeded')
        metrics[identity] = item
    if isinstance(value, (dict, list)):
        size, _, nodes, depth = metrics[id(value)]
    else:
        size, nodes, depth = len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')), 1, 0
    if size + 1 > byte_cap or nodes > node_limit:
        raise ValueError(label + ' expanded bytes/node/depth budget exceeded')
    return {'bytes': size + 1, 'nodes': nodes, 'depth': depth}


def serialized_request_bytes(request, paths, root, budget):
    """Measure exact emitted request plus unique inputs before any source hash."""
    forecast = serialization_forecast(request, budget, label='constructed native request')
    stats = stat_manifest(paths, root, budget)
    if len(stats) + 1 > graph_limit(budget, 'max_files') or sum(item['bytes'] for item in stats) + forecast['bytes'] > budget['max_total_bytes']:
        raise ValueError('constructed native request plus complete input byte/file budget exceeded')
    payload = serialized_json(request)
    if len(payload) != forecast['bytes']:
        raise ValueError('serialized request differs from exact preflight forecast')
    return payload


def checked_binding(root, binding, result, label, budget=None):
    if binding is not None:
        input_manifest([contained_path(root, binding['path'])], root, budget or result.get('budget') or HARD_BUDGET)
    return bind_file(root, binding, label, result['errors'], result.setdefault('changed_sources', []), result['bound_files'])


def validate_review(value, root, result, schema, *, label='verification', digest_key='verification_semantic_sha256'):
    errors, missing, bound = (result[k] for k in ('errors', 'missing_gates', 'bound_files'))
    changed = result.setdefault('changed_sources', [])
    binding = value['review_record']
    if binding is None:
        missing.append('source_bound_' + label + '_review')
        if value['status'] == 'reviewed':
            errors.append('reviewed status has no independent review record')
        return False
    if value['status'] != 'reviewed':
        errors.append('review record requires reviewed status')
    path = checked_binding(root, binding, result, label + '_review', value.get('budget'))
    if path is None:
        return False
    record = limited_document(path, value.get('budget'))
    issues = schema_errors(record, {'$schema': schema['$schema'], '$defs': schema['$defs'], **schema['$defs']['review_record']})
    errors.extend('review: ' + issue for issue in issues)
    if issues:
        return False
    if type(record['schema_version']) is not int or record['project_id'] != value['project_id'] or record[digest_key] != result['semantic_sha256']:
        errors.append('review: project/version/semantic identity differs')
    decision = record['decision']
    path = checked_binding(root, decision, result, label + '_review_decision', value.get('budget'))
    if path is None:
        return False
    if path.stat().st_size > (value.get('budget') or HARD_BUDGET)['max_file_bytes']:
        raise ValueError('review decision exceeds byte budget')
    text = path.read_text(encoding='utf-8-sig')
    start, end = decision['start'], decision['end']
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text) or text[start:end] != decision['quote']:
        errors.append('review: Unicode source slice differs')
    lines = decision['quote'].splitlines()
    context = {'project_id': value['project_id'], digest_key: result['semantic_sha256'],
               'reviewed_by': decision['reviewed_by'], 'action': 'review'}
    for key, item in context.items():
        if [line for line in lines if line.startswith(key + '=')] != [key + '=' + item]:
            errors.append('review: exact unique context line required for ' + key)
    return not errors


def bind_sources(sources, root, result):
    entries = {}
    for source in sources:
        if source['id'] in entries:
            result['errors'].append('duplicate verification source id')
        path = checked_binding(root, source, result, 'verification_source:' + source['id'])
        entries[source['id']] = (source, path)
    return entries


def source_snapshot(reference, sources, root, result, expected, *, label):
    del root
    if reference is None:
        result['missing_gates'].append('source_bound_' + label)
        return False
    entry = sources.get(reference['source_id'])
    if entry is None:
        result['errors'].append(label + ': unknown source id')
        return False
    path = entry[1]
    if path is None:
        return False
    if path.suffix.lower() not in {'.json', '.yaml', '.yml'}:
        result['errors'].append(label + ': structured JSON/YAML source required')
        return False
    actual = selected_value(limited_source_document(path, result.get('budget')), reference['selector'])
    if not typed_equal(actual, expected):
        result['errors'].append(label + ': complete typed source snapshot differs')
        return False
    return True


def serialized_json(value):
    """Exact persisted LF bytes; budget the same serialization on every platform."""
    return (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')


class _GuardMemory:
    """Private conservative reservation for the original typed Path read set."""
    __slots__ = ('charged',)
    def __init__(self, charged):
        self.charged = charged


def _guard_path_charge(path):
    # This projection is exclusive to actual typed discovery paths. Arbitrary
    # Path objects in caller/report graphs remain unknown to _retained_size.
    if type(path) is not type(Path()):
        raise _ReuseUnavailable('unknown private guard path representation')
    spelling, parts = str(path), tuple(path.parts)
    hash(path)
    projection = _retained_size((spelling, parts))
    if projection is None:
        raise _MemoCapacityUnavailable('private guard path capacity unavailable')
    charge = sys.getsizeof(path)
    for cls in type(path).__mro__:
        for slot in getattr(cls, '__slots__', ()):
            value = getattr(path, slot, None)
            size = _retained_size(value)
            if size is None:
                raise _ReuseUnavailable('unknown private guard path metadata')
            charge += size
    # Cover later spelling/parts/comparison caches as well as current slots;
    # aliases and shared strings may be charged repeatedly conservatively.
    return charge + 4 * projection + 512


def _guard_member_charge(value):
    if type(value) is type(Path()):
        return _guard_path_charge(value)
    if type(value) is RepositorySourcePaths:
        charge = 2 * sys.getsizeof(value) + sys.getsizeof(value.__dict__)
        charge += _guard_path_charge(value.authority)
        original = _retained_size(value.original_bytes)
        if original is None:
            raise _MemoCapacityUnavailable('source authority guard capacity unavailable')
        return charge + original + sum(_guard_path_charge(path) for path in value)
    if type(value) is tuple:
        return sys.getsizeof(value) + sum(_guard_member_charge(item) for item in value)
    size = _retained_size(value)
    if size is None:
        raise _ReuseUnavailable('unknown private read-set guard metadata')
    return size


def _capture_guard_member(paths, value):
    capture, reservation = _H_VALIDATION_CAPTURE.get(), paths._guard_memory
    if capture is None or reservation is None or capture['owner'] != _validation_owner():
        return
    charge = _guard_member_charge(value) + 512
    containers = 2 * (sys.getsizeof(paths._documents) + sys.getsizeof(paths._edges))
    if (capture['base_bytes'] + capture['charged'] + reservation.charged + charge + containers + 4096 >
            min(_MEMO_BYTES, 64 * 1024 * 1024)):
        raise _MemoCapacityUnavailable('typed read-set guard capacity unavailable')
    reservation.charged += charge


class EvidencePaths(set):
    def __init__(self, paths=(), *, allowed_external=()):
        super().__init__()
        self.allowed_external = set(allowed_external)
        self.claimed_hashes = {}
        self.source_authorities = []
        self._edges = []
        self._documents = {}
        capture = _H_VALIDATION_CAPTURE.get()
        self._guard_memory = (_GuardMemory(4096) if capture is not None and
                              capture['owner'] == _validation_owner() else None)
        self.update(paths)

    def update(self, *others):
        for other in others:
            self._edges.extend(getattr(other, '_edges', ()))
            self._documents.update(getattr(other, '_documents', {}))
            self.allowed_external.update(getattr(other, 'allowed_external', ()))
            for authority in getattr(other, 'source_authorities', ()):
                if authority not in self.source_authorities:
                    self.source_authorities.append(authority)
            for path, sha256 in getattr(other, 'claimed_hashes', {}).items():
                if path in self.claimed_hashes and self.claimed_hashes[path] != sha256:
                    raise ValueError('conflicting verification byte claims')
                self.claimed_hashes[path] = sha256
            super().update(other)

    def __or__(self, other):
        result = EvidencePaths(self)
        result.update(other)
        return result

    def __ior__(self, other):
        self.update(other)
        return self


def _capture_metadata(paths, value):
    """Admit optional graph metadata once, with conservative running charges."""
    capture = _H_VALIDATION_CAPTURE.get()
    if capture is None or capture['owner'] != _validation_owner():
        return False
    charge = _retained_size(value)
    containers = 2 * (sys.getsizeof(paths._documents) + sys.getsizeof(paths._edges))
    if (charge is None or capture['base_bytes'] + capture['charged'] + charge + containers +
            (paths._guard_memory.charged if paths._guard_memory is not None else 0) + 4096 >
            min(_MEMO_BYTES, 64 * 1024 * 1024)):
        raise _MemoCapacityUnavailable('optional evidence metadata capacity unavailable')
    capture['charged'] += charge
    return True


def _capture_edge(paths, edge):
    if _capture_metadata(paths, edge):
        paths._edges.append(edge)


def _capture_document(paths, key, value):
    if _capture_metadata(paths, (key, value)):
        paths._documents[key] = value


def stat_manifest(paths, root, budget, *, allowed_external=()):
    """Complete stat-only preflight, reusable before constructed/source digests."""
    file_cap, total_cap = (byte_limit(budget, name) for name in ('max_file_bytes', 'max_total_bytes'))
    allowed = {Path(p).resolve() for p in allowed_external}
    allowed.update(Path(p).resolve() for p in getattr(paths, 'allowed_external', ()))
    root, pending, total = Path(root).resolve(), [], 0
    unique = {Path(p).resolve() for p in paths}
    if len(unique) > graph_limit(budget, 'max_files'):
        raise ValueError('verification input file count budget exceeded')
    for path in sorted(unique, key=str):
        if not path.is_relative_to(root) and path not in allowed:
            raise ValueError('verification input leaves project root: ' + str(path))
        if not path.is_file():
            raise ValueError('verification input is not a file: ' + str(path))
        size = path.stat().st_size
        total += size
        if size > file_cap or total > total_cap:
            raise ValueError('verification input byte budget exceeded')
        pending.append((path, size))
    return [{'path': str(path), 'bytes': size} for path, size in pending]


def input_manifest(paths, root, budget, *, allowed_external=()):
    """No digest occurs before every unique input passes the same stat budget."""
    stats = stat_manifest(paths, root, budget, allowed_external=allowed_external)
    authorities = getattr(paths, 'source_authorities', ())
    for authority in authorities:
        authority.assert_authority_unchanged()
    claims = getattr(paths, 'claimed_hashes', {})
    result = []
    for item in stats:
        path = Path(item['path'])
        sha256 = sha256_file(path)
        if path in claims and claims[path] != sha256:
            raise ValueError('verification claimed byte identity differs: ' + str(path))
        result.append({**item, 'sha256': sha256})
    for authority in authorities:
        authority.assert_authority_unchanged()
    return result


def assert_unchanged(manifest):
    for binding in manifest:
        path = Path(binding['path'])
        if not path.is_file() or path.stat().st_size != binding['bytes'] or sha256_file(path) != binding['sha256']:
            raise ValueError('verification input changed during assessment: ' + str(path))


def evidence_paths(receipt_paths, root, budget, *, root_contexts=None,
                   include_repository_sources=None):
    return _discover_evidence(receipt_paths, root, budget, root_contexts=root_contexts,
                              include_repository_sources=include_repository_sources)


def evidence_paths_for_request(request, root, budget, *, role='h_trial_request',
                               include_repository_sources=True):
    """Preflight a constructed native request before creating its file bindings.

    The producer explicitly selects a request role; ordinary task sources never
    acquire this role. Consumers start from the actual receipt and input bytes.
    No virtual request is returned as persisted evidence or hashed by this helper.
    """
    if role not in {'h_trial_request', 'qualification_h_request', 'h_study_request'}:
        raise ValueError('unsupported in-memory verification request role')
    if not isinstance(request, dict):
        raise ValueError('constructed verification request must be an object')
    _bounded_document(request, budget, label='constructed ' + role)
    return _discover_evidence([], root, budget, root_documents=[(request, role)],
                              include_repository_sources=include_repository_sources)


def _discover_evidence(receipt_paths, root, budget, *, root_contexts=None,
                       root_documents=(), include_repository_sources=None):
    """Discover bounded evidence using caller-selected roles, never filenames.

    Only the selected H/E/D chain can introduce original A/D/E/H qualification
    paths. Ordinary sources/reviews and snapshots stay task-only. Real E/D/H
    consumers subsequently verify every selected historical identity.
    """
    root = Path(root).resolve()
    allowed_roots = {'task', 'h1_contract', 'h1_receipt', 'h2_contract', 'h2_receipt',
                     'simulation_protocol', 'simulation_receipt', 'implementation_receipt',
                     'h_study_contract', 'h_study_receipt', 'h_study_request',
                     'h_trial_receipt', 'h_trial_request', 'qualification_h_receipt',
                     'qualification_h_request'}
    contexts = {Path(p).resolve(): kind for p, kind in (root_contexts or {}).items()}
    if any(kind not in allowed_roots for kind in contexts.values()):
        raise ValueError('unknown verification evidence root context')
    queued = [(Path(p).resolve(), contexts.get(Path(p).resolve(), 'task'), None, None) for p in receipt_paths]
    queued.extend((None, context, None, value) for value, context in root_documents)
    paths, visited, total = EvidencePaths(), set(), 0
    byte_claims, source_snapshots, repository_added = [], [], False
    edge_count = len(queued)
    edge_limit = graph_limit(budget, 'max_edges')
    file_limit = graph_limit(budget, 'max_files')
    if edge_count > edge_limit:
        raise ValueError('verification evidence edge budget exceeded')

    def queue(path, kind, qualification_root=None, value=None):
        nonlocal edge_count
        edge_count += 1
        if edge_count > edge_limit:
            raise ValueError('verification evidence edge budget exceeded')
        queued.append((path, kind, qualification_root, value))
        if path is not None:
            _capture_edge(paths, (str(path), kind, str(qualification_root) if qualification_root else None))

    def add_repository_sources():
        nonlocal repository_added
        if repository_added or include_repository_sources is False:
            return
        repository_added = True
        source_paths = repository_source_paths()
        stat_manifest(source_paths, ROOT, budget)
        source_paths.assert_authority_unchanged()
        source_snapshots.append(source_paths)
        _capture_guard_member(paths, source_paths)
        paths.source_authorities.append(source_paths)
        for source in source_paths:
            queue(source, 'opaque', ROOT)

    def claim(binding):
        if not isinstance(binding, dict) or not isinstance(binding.get('path'), str) or not isinstance(binding.get('sha256'), str):
            raise ValueError('malformed verification evidence byte claim')
        candidate = Path(binding['path'])
        candidate = (candidate if candidate.is_absolute() else root / candidate).resolve()
        byte_claims.append((candidate, binding['sha256']))

    def enqueue(binding, kind='task', qualification_root=None):
        if binding is None:
            return
        if not isinstance(binding, dict) or not isinstance(binding.get('path'), str):
            raise ValueError('malformed verification evidence path binding')
        base = qualification_root or root
        lexical = Path(binding['path'])
        lexical = lexical if lexical.is_absolute() else base / lexical
        _capture_edge(paths, (str(lexical), kind, str(qualification_root) if qualification_root else None))
        candidate = Path(binding['path'])
        candidate = (candidate if candidate.is_absolute() else base / candidate).resolve()
        if qualification_root is None and not candidate.is_relative_to(root):
            # A duplicate ordinary byte claim may refer to an independently
            # selected exact qualification/source path, but grants no new role.
            claim(binding)
            return
        queue(contained_path(base, binding['path']), kind, qualification_root)

    def qualification(binding, kind):
        if not isinstance(binding, dict) or not isinstance(binding.get('path'), str):
            raise ValueError('malformed original qualification binding')
        lexical = Path(binding['path'])
        _capture_edge(paths, (str(lexical), kind, str(lexical.parent)))
        candidate = lexical.resolve()
        queue(candidate, kind, candidate.parent)

    def task_bindings(node, *, skip=()):
        pending, visited_nodes = [(node, set(skip))], set()
        excluded = {'sources', 'runtime', 'functions', 'bindings', 'artifacts', 'input_manifest',
                    'contract_snapshot', 'protocol_snapshot', 'mapping_snapshot',
                    'study_snapshot', 'physical_snapshot', 'bound_files', 'protected_files'}
        while pending:
            current, current_skip = pending.pop()
            if not isinstance(current, (dict, list)) or id(current) in visited_nodes:
                continue
            visited_nodes.add(id(current))
            if isinstance(current, dict):
                if isinstance(current.get('path'), str) and isinstance(current.get('sha256'), str):
                    enqueue(current)
                pending.extend((child, set()) for key, child in current.items()
                               if key not in current_skip | excluded)
                if isinstance(current.get('sources'), list):
                    pending.append((current['sources'], set()))
            else:
                pending.extend((child, set()) for child in current)

    receipt_inputs = {'h1_receipt': 'h1_request', 'h2_receipt': 'h2_request',
                      'h_study_receipt': 'h_study_request', 'h_trial_receipt': 'h_trial_request',
                      'simulation_receipt': 'simulation_request',
                      'implementation_receipt': 'implementation_request',
                      'qualification_a_receipt': 'qualification_a_request',
                      'qualification_d_receipt': 'qualification_d_request',
                      'qualification_e_receipt': 'qualification_e_request',
                      'qualification_h_receipt': 'qualification_h_request'}
    qualification_roles = {
        'simulation_request': {'environment_profile': 'qualification_a_profile',
                               'environment_receipt': 'qualification_a_receipt',
                               'simulation_profile': 'qualification_e_profile',
                               'simulation_profile_receipt': 'qualification_e_receipt'},
        'implementation_request': {'environment_profile': 'qualification_a_profile',
                                   'environment_receipt': 'qualification_a_receipt',
                                   'implementation_profile': 'qualification_d_profile',
                                   'implementation_profile_receipt': 'qualification_d_receipt'},
        'qualification_e_request': {'environment_profile': 'qualification_a_profile',
                                    'environment_receipt': 'qualification_a_receipt'},
        'h_trial_request': {'environment_profile': 'qualification_a_profile',
                            'environment_receipt': 'qualification_a_receipt',
                            'simulation_profile': 'qualification_e_profile',
                            'simulation_profile_receipt': 'qualification_e_receipt',
                            'h_analysis_profile': 'qualification_h_profile',
                            'h_analysis_profile_receipt': 'qualification_h_receipt'},
        'qualification_h_request': {'environment_profile': 'qualification_a_profile',
                                    'environment_receipt': 'qualification_a_receipt',
                                    'simulation_profile': 'qualification_e_profile',
                                    'simulation_profile_receipt': 'qualification_e_receipt'},
    }
    new_roles = {'h_study_contract', 'h_study_receipt', 'h_study_request',
                 'h_trial_receipt', 'h_trial_request', 'qualification_h_receipt',
                 'qualification_h_request'}
    if include_repository_sources is True:
        add_repository_sources()
    while queued:
        path, context, qualification_root, value = queued.pop()
        if path is not None:
            path = contained_path(qualification_root or root, str(Path(path).resolve()))
            if qualification_root is not None and not path.is_relative_to(root):
                _capture_guard_member(paths, path)
                paths.allowed_external.add(path)
        key = (path if path is not None else id(value), context, qualification_root)
        if key in visited:
            continue
        visited.add(key)
        if path is not None and path not in paths:
            if not path.is_file() or path.stat().st_size > budget['max_file_bytes']:
                raise ValueError('verification evidence missing or exceeds file byte budget')
            total += path.stat().st_size
            if total > budget['max_total_bytes']:
                raise ValueError('verification total evidence byte budget exceeded')
            _capture_guard_member(paths, path)
            paths.add(path)
            if len(paths) > file_limit:
                raise ValueError('verification evidence file count budget exceeded')
        if context == 'opaque' or path is not None and path.suffix.lower() not in {'.json', '.yaml', '.yml'}:
            continue
        if value is None:
            value = limited_source_document(path, budget) if context == 'task' else limited_document(path, budget)
        _capture_document(paths, (str(path) if path is not None else None, context,
                                  str(qualification_root) if qualification_root else None), value)
        if (context in new_roles or context == 'h1_contract' and
                any(key in value for key in ('scope', 'trajectory', 'observables', 'checks', 'math_budget', 'continuous_scope'))):
            add_repository_sources()
        if context == 'task' and isinstance(value, list):
            task_bindings(value)
            continue
        # A receipt's role comes from an actual selected binding, not basename.
        for artifact_key, binding in value.get('artifacts', {}).items():
            if isinstance(binding, dict) and isinstance(binding.get('file'), str):
                if path is None:
                    raise ValueError('constructed request cannot introduce unpersisted artifact edges')
                child = contained_path(path.parent, binding['file'])
                is_input = artifact_key == 'input' or context == 'h1_receipt' and artifact_key == 'numerical-verification-input.json'
                child_context = receipt_inputs.get(context, 'task') if is_input else 'opaque'
                _capture_edge(paths, (str(path.parent / binding['file']), child_context, str(qualification_root) if qualification_root else None))
                queue(child, child_context, qualification_root)

        skip = set()
        if context == 'h1_contract':
            enqueue(value.get('primary_protocol'), 'simulation_protocol')
            for binding in value.get('refinement_protocols', []):
                enqueue(binding, 'simulation_protocol')
            skip.update({'primary_protocol', 'refinement_protocols'})
        elif context == 'h2_contract':
            enqueue(value.get('primary_numerical_receipt'), 'h1_receipt')
            for member in value.get('members', []):
                enqueue(member.get('numerical_receipt'), 'h1_receipt')
            skip.update({'primary_numerical_receipt', 'members'})
            for claim_record in value.get('claims', []):
                for requirement in claim_record.get('study_requirements', []):
                    enqueue(requirement.get('study_contract'), 'h_study_contract')
                    enqueue(requirement.get('study_receipt'), 'h_study_receipt')
            # Generic task traversal may discover these again, but cannot turn
            # their ordinary sources into trial/qualification authority.
        elif context in {'h1_receipt', 'h1_request'}:
            enqueue(value.get('numerical_verification'), 'h1_contract')
            skip.add('numerical_verification')
            if context == 'h1_request':
                for binding in value.get('receipts', []):
                    enqueue(binding, 'simulation_receipt')
                skip.add('receipts')
        elif context == 'h2_request':
            enqueue(value.get('contract'), 'h2_contract')
            skip.add('contract')
        elif context in {'h_study_contract', 'h_study_receipt', 'h_study_request',
                         'h_trial_receipt', 'h_trial_request'}:
            business_roles = {'study': 'h_study_contract', 'contract': 'h_study_contract',
                              'base_protocol': 'simulation_protocol',
                              'base_receipt': 'simulation_receipt',
                              'base_simulation_receipt': 'simulation_receipt',
                              'primary_numerical_receipt': 'h1_receipt'}
            for binding_key, kind in business_roles.items():
                enqueue(value.get(binding_key), kind)
                skip.add(binding_key)
            for binding in value.get('trial_receipts', []):
                enqueue(binding, 'h_trial_receipt')
            skip.add('trial_receipts')
        elif context == 'simulation_protocol':
            enqueue(value.get('mapping'), 'mapping_contract')
            skip.add('mapping')
        elif context == 'mapping_contract':
            enqueue(value.get('implementation'), 'implementation_receipt')
            skip.add('implementation')

        bindings = value.get('bindings', {})
        if isinstance(bindings, dict):
            roles = qualification_roles.get(context, {})
            for binding_key, binding in bindings.items():
                if isinstance(binding, dict) and isinstance(binding.get('path'), str):
                    if binding_key in roles:
                        qualification(binding, roles[binding_key])
                    else:
                        kind = 'task'
                        if context == 'simulation_request':
                            kind = {'implementation_receipt': 'implementation_receipt',
                                    'protocol_input': 'simulation_protocol'}.get(binding_key, kind)
                        elif context == 'implementation_request' and binding_key == 'mapping_input':
                            kind = 'mapping_contract'
                        elif context in {'h_study_contract', 'h_study_receipt', 'h_study_request',
                                         'h_trial_receipt', 'h_trial_request'}:
                            kind = {'study': 'h_study_contract', 'contract': 'h_study_contract',
                                    'base_protocol': 'simulation_protocol',
                                    'base_receipt': 'simulation_receipt',
                                    'base_simulation_receipt': 'simulation_receipt',
                                    'primary_numerical_receipt': 'h1_receipt'}.get(binding_key, kind)
                            if context in {'h_trial_request', 'h_study_request'} and binding_key == 'current_state':
                                # Explicit caller bytes only. A state filename
                                # or ordinary task field never grants this role.
                                kind = 'opaque'
                        enqueue(binding, kind)
                elif binding_key in {'bound_files', 'protected_files', 'trial_receipts'} and isinstance(binding, list):
                    # Claims cannot introduce an external path, a new file, or
                    # a role. Authoritative original edges are discovered first.
                    for item in binding:
                        if binding_key == 'trial_receipts':
                            enqueue(item, 'h_trial_receipt')
                        else:
                            claim(item)
        if context in new_roles:
            for key in ('bound_files', 'protected_files', 'input_manifest'):
                for item in value.get(key, []):
                    claim(item)
        if not context.startswith('qualification_'):
            task_bindings(value, skip=skip)
    for candidate, sha256 in byte_claims:
        if candidate not in paths:
            raise ValueError('verification byte claim is outside the independently authorized read set or leaves project root: ' + str(candidate))
        if candidate in paths.claimed_hashes and paths.claimed_hashes[candidate] != sha256:
            raise ValueError('conflicting verification evidence byte claims')
        _capture_guard_member(paths, (candidate, sha256))
        paths.claimed_hashes[candidate] = sha256
    for source_paths in source_snapshots:
        source_paths.assert_authority_unchanged()
    return paths


# These proofs live only inside one read-only public validation. They are never
# evidence fields, caller reports, current qualifications or execution grants.
_H_VALIDATION_SESSION = ContextVar('h_validation_session', default=None)
_H_VALIDATION_CAPTURE = ContextVar('h_validation_metadata_capture', default=None)
_MEMO_ENTRIES = 64
_MEMO_BYTES = 64 * 1024 * 1024
_MEMO_KINDS = frozenset({'study_source', 'study_receipt', 'h2_source', 'h2_receipt',
                         'baseline_protocol', 'baseline_simulation', 'baseline_h1',
                         'historical_qualification'})


class _ReuseUnavailable(ValueError):
    pass


class _MemoCapacityUnavailable(_ReuseUnavailable):
    pass


class _ValidationReuseChanged(ValueError):
    def __init__(self, message, report=None):
        super().__init__(message)
        self.report = report


def _validation_owner():
    import asyncio
    try:
        task = asyncio.current_task()
    except RuntimeError:
        task = None
    return threading.get_ident(), id(task) if task is not None else None


class _ValidationSession:
    __slots__ = ('owner', 'entries', 'inflight', 'capabilities', 'working', 'active')
    def __init__(self):
        self.owner = _validation_owner()
        self.entries = {}
        self.inflight = set()
        self.capabilities = []
        self.working = []
        self.active = True

    def clear(self):
        self.active = False
        for capability in self.capabilities:
            capability.pending = None
        self.capabilities.clear()
        self.entries.clear()
        self.inflight.clear()
        self.working.clear()


@contextmanager
def validation_session():
    existing = _H_VALIDATION_SESSION.get()
    if existing is not None and existing.active and existing.owner == _validation_owner():
        yield existing
        return
    current = _ValidationSession()
    token = _H_VALIDATION_SESSION.set(current)
    try:
        yield current
    finally:
        current.clear()
        _H_VALIDATION_SESSION.reset(token)


def _validation_operation(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with validation_session():
            return function(*args, **kwargs)
    return wrapped


class _HistoricalCapability:
    __slots__ = ('session', 'root', 'pending')
    def __init__(self, session, root):
        self.session = session
        self.root = root
        self.pending = None


def _historical_validation_capability(project_root):
    caller = sys._getframe(1)
    if (Path(caller.f_code.co_filename).resolve() != ROOT / 'scripts/h_analysis_trial.py' or
            caller.f_code.co_name != '_mint_historical_replay'):
        return None
    session = _H_VALIDATION_SESSION.get()
    if session is None or not session.active or session.owner != _validation_owner():
        return None
    capability = _HistoricalCapability(session, str(Path(project_root).resolve()))
    session.capabilities.append(capability)
    if _retained_size(session) is None:
        session.capabilities.pop()
        return None
    return capability


def _live_capability(capability, session, root):
    return (type(capability) is _HistoricalCapability and capability.session is session and
            session.active and session.owner == _validation_owner() and
            capability.root == str(Path(root).resolve()) and
            any(value is capability for value in session.capabilities))


def _retained_size(value):
    """Conservative retained Python memory, including private proof metadata."""
    pending, seen, active, total = [(value, False)], set(), set(), 0
    work = 0
    while pending:
        node, leaving = pending.pop()
        identity = id(node)
        if leaving:
            active.remove(identity)
            continue
        if identity in active:
            return None
        if identity in seen:
            continue
        seen.add(identity)
        work += 1
        if work > 1000000:
            return None
        total += sys.getsizeof(node)
        if total > min(_MEMO_BYTES, 64 * 1024 * 1024):
            return None
        if type(node) in (dict, list, tuple, set, frozenset, _HistoricalCapability, _ValidationSession, _GuardMemory):
            active.add(identity)
            pending.append((node, True))
        if type(node) is dict:
            pending.extend((child, False) for child in node.keys())
            pending.extend((child, False) for child in node.values())
        elif type(node) in (list, tuple, set, frozenset):
            pending.extend((child, False) for child in node)
        elif type(node) is _GuardMemory:
            if type(node.charged) is not int or node.charged < 0:
                return None
            total += node.charged
            if total > min(_MEMO_BYTES, 64 * 1024 * 1024):
                return None
            pending.append((node.charged, False))
        elif type(node) is _HistoricalCapability:
            # session is the owner, not retained as a second recursive graph.
            pending.extend(((node.root, False), (node.pending, False)))
        elif type(node) is _ValidationSession:
            pending.extend((child, False) for child in
                           (node.owner, node.entries, node.inflight, node.capabilities, node.working, node.active))
        elif type(node) not in (str, bytes, int, float, bool, type(None)):
            return None
    return total


def _path_provenance(path):
    """Record lexical bindings and all traversed links, including link targets."""
    # abspath removes parent components before following a preceding link.
    # Let the original contained resolver handle these legal spellings; they
    # cannot acquire an optional proof from a different lexical projection.
    if '..' in Path(path).parts:
        raise _ReuseUnavailable('parent-traversal provenance requires original validation')
    lexical = Path(os.path.abspath(str(path)))
    todo, visited, links = [lexical], set(), []
    while todo:
        current = todo.pop()
        if str(current) in visited:
            continue
        visited.add(str(current))
        if len(visited) > 128:
            raise ValueError('bounded validation symlink provenance exceeded')
        prefix = Path(current.anchor)
        for part in current.parts[1:]:
            prefix = prefix / part
            if prefix.is_symlink():
                stat = prefix.lstat()
                target = os.readlink(prefix)
                if '..' in Path(target).parts:
                    raise _ReuseUnavailable('parent-traversal link requires original validation')
                links.append((str(prefix), target, stat.st_dev, stat.st_ino))
                actual = Path(target) if Path(target).is_absolute() else prefix.parent / target
                todo.append(Path(os.path.abspath(str(actual))))
    return str(lexical), str(lexical.resolve()), tuple(sorted(set(links)))


def _memo_paths(descriptor, *, working=()):
    # The original consumers never retain optional parsed documents merely
    # because an ambient public validation session happens to exist.
    capture = {'owner': _validation_owner(), 'working': (descriptor, working),
               'base_bytes': 0, 'charged': 0}
    capture['base_bytes'] = _memo_capacity(capture, reserve=_GuardMemory(4096))
    token = _H_VALIDATION_CAPTURE.set(capture)
    try:
        if descriptor['request'] is not None:
            return evidence_paths_for_request(descriptor['request'], descriptor['root'], descriptor['budget'],
                                              role=descriptor['request_role'])
        return evidence_paths(descriptor['roots'], descriptor['root'], descriptor['budget'],
                              root_contexts=descriptor['contexts'], include_repository_sources=True)
    finally:
        _H_VALIDATION_CAPTURE.reset(token)


def _memo_capacity(*working, reserve=()):
    """Account live private guards and reserve the next complete guard/copy."""
    size = _retained_size((_H_VALIDATION_SESSION.get(), working))
    extra = _retained_size(reserve)
    if size is None or extra is None or size + extra > min(_MEMO_BYTES, 64 * 1024 * 1024):
        raise _MemoCapacityUnavailable('live validation proof/guard capacity unavailable')
    return size + extra


def _memo_base(descriptor, *, working=()):
    _memo_capacity(working, descriptor)
    paths = _memo_paths(descriptor, working=working)
    _memo_capacity(working, descriptor, paths._documents, paths._edges, paths._guard_memory)
    # Include exact owned inventories in the stat-only phase. They may contain
    # additional lexical members outside the ordinary declared input graph.
    stats = stat_manifest(paths, descriptor['root'], descriptor['budget'])
    extra_preflight = _memo_extra_preflight(paths, descriptor['budget'],
        working=(working, descriptor, paths._documents, paths._edges, paths._guard_memory, stats))
    _memo_capacity(working, descriptor, paths._documents, paths._edges, paths._guard_memory, stats, extra_preflight)
    manifest = input_manifest(paths, descriptor['root'], descriptor['budget'])
    _memo_capacity(working, descriptor, paths._documents, paths._edges, paths._guard_memory, stats, extra_preflight,
                   manifest, reserve=paths._edges)
    edges = list(paths._edges)
    edges.extend((str(path), descriptor['contexts'].get(str(Path(path).resolve()), 'task'), None)
                 for path in descriptor['roots'])
    retained_before_provenance = _memo_capacity(working, descriptor, paths._documents, paths._edges, paths._guard_memory,
                                              stats, extra_preflight, manifest, edges)
    provenance, provenance_bytes = [], 0
    def record_provenance(path):
        nonlocal provenance_bytes
        row = _path_provenance(path)
        charge = _retained_size(row)
        if charge is None or retained_before_provenance + provenance_bytes + charge + 2 * sys.getsizeof(provenance) + 1024 > min(_MEMO_BYTES, 64 * 1024 * 1024):
            raise _MemoCapacityUnavailable('lexical evidence provenance capacity unavailable')
        provenance.append(row)
        provenance_bytes += charge
    record_provenance(descriptor['root_lexical'])
    if descriptor.get('caller_root_lexical') is not None:
        record_provenance(descriptor['caller_root_lexical'])
    for path, _, _ in edges:
        record_provenance(path)
    value = None
    for authority in paths.source_authorities:
        value = limited_document(authority.authority, SOURCE_AUTHORITY_BUDGET)
        retained_before_provenance = _memo_capacity(working, descriptor, paths._documents, paths._edges, paths._guard_memory,
                                                  stats, extra_preflight, manifest, edges, value)
        for name in value['source_files']:
            record_provenance(ROOT / name)
        authority.assert_authority_unchanged()
    snapshot = {'manifest': manifest, 'edges': sorted(edges, key=repr),
                'provenance': sorted(set(provenance), key=repr),
                'allowed_external': sorted(map(str, paths.allowed_external)),
                'claimed_hashes': sorted((str(path), sha) for path, sha in paths.claimed_hashes.items()),
                'authority': [(str(a.authority), a.original_bytes) for a in paths.source_authorities]}
    _memo_capacity(working, descriptor, paths._documents, paths._edges, paths._guard_memory, stats, extra_preflight,
                   snapshot, edges, provenance, value)
    return snapshot, paths


def _memo_records(value):
    if value is None:
        return []
    if type(value) is list:
        return value
    if type(value) is dict:
        return [value]
    raise _ReuseUnavailable('native record shape unavailable for reuse')


def _memo_installation(runtime):
    if not isinstance(runtime, dict) or not {'matlabroot', 'executable', 'executable_sha256',
                                            'version_file_sha256', 'function_files'} <= set(runtime):
        raise _ReuseUnavailable('complete runtime identity is unavailable for validation reuse')
    install = Path(runtime['matlabroot']).resolve()
    executable = contained_path(install, runtime['executable'])
    version = contained_path(install, str(install / 'VersionInfo.xml'))
    expected = {executable: runtime['executable_sha256'], version: runtime['version_file_sha256']}
    for binding in runtime['function_files']:
        target = contained_path(install, binding['path'])
        if target in expected and expected[target] != binding['sha256']:
            raise ValueError('conflicting actual installation identity')
        expected[target] = binding['sha256']
    return install, expected


def _memo_extra_preflight(paths, budget, *, working=()):
    """Stat all original extra proof surfaces before any extra or graph digest."""
    policy = limited_document(ROOT / 'core/h_analysis_assurance_contract.yaml', SOURCE_AUTHORITY_BUDGET)
    machine_budget, names = policy['installation_identity_budget'], policy['evidence']
    installations, runtimes, owned = {}, [], []
    _memo_capacity(working, paths._documents, paths._edges, paths._guard_memory, policy)
    for (path, role, _), value in paths._documents.items():
        runtime = value.get('runtime') if isinstance(value, dict) else None
        trusted = role.startswith('qualification_') and role.endswith('_profile') or role in {
            'simulation_receipt', 'implementation_receipt', 'h_trial_receipt'}
        if trusted and runtime is not None:
            install, expected = _memo_installation(runtime)
            selected = installations.setdefault(str(install), {})
            for target, sha in expected.items():
                if str(target) in selected and selected[str(target)] != sha:
                    raise ValueError('conflicting complete installation identity')
                selected[str(target)] = sha
            runtimes.append((path, role, runtime, str(install), {str(p): sha for p, sha in expected.items()}))
            del expected, selected
        if role not in {'h_trial_request', 'qualification_h_request'} or 'output_directory' not in value:
            continue
        # Authority is the independently selected persisted input and its typed
        # receipt edge. The request's own directory field grants no read root.
        if path is None:
            raise _ReuseUnavailable('owned inventory requires a persisted input authority')
        input_path = Path(path)
        directory = input_path.parent
        include_profile = role == 'qualification_h_request'
        receipt_role = 'qualification_h_receipt' if include_profile else 'h_trial_receipt'
        receipt_name = names['profile_receipt'] if include_profile else names['run_receipt']
        if input_path.name != names['input'] or Path(value['output_directory']).resolve() != directory:
            raise ValueError('H owned output directory differs from actual persisted input')
        receipt = paths._documents.get((str(directory / receipt_name), receipt_role,
                                       str(directory) if include_profile else None))
        if receipt is None:
            selected_receipts = [v for (p, r, _), v in paths._documents.items()
                                 if p == str(directory / receipt_name) and r == receipt_role]
            if len(selected_receipts) != 1:
                raise _ReuseUnavailable('owned inventory requires its actual selected receipt')
            receipt = selected_receipts[0]
        if contained_path(directory, receipt['artifacts']['input']['file']) != input_path:
            raise ValueError('H owned input differs from actual selected receipt')
        excluded = {names['profile_receipt'], names['run_receipt']}
        if not include_profile:
            excluded.add(names['profile'])
        # Preserve every lexical file name and its byte charge, including two
        # links to one physical target. Original artifact_manifest does so too.
        stats, nodes, total = [], 0, 0
        retained_before_stats = _memo_capacity(working, paths._documents, paths._edges, paths._guard_memory, policy,
                                             installations, runtimes, owned, receipt, excluded)
        stat_bytes = 0
        for target in directory.rglob('*'):
            nodes += 1
            if nodes > graph_limit(value['budget'], 'max_document_nodes'):
                raise _ReuseUnavailable('bounded owned-inventory validation reuse exceeded')
            relative = target.relative_to(directory)
            if not target.is_file() or relative.parts[0] in {'cache', 'codegen'}:
                continue
            contained_path(directory, str(target))
            size = target.stat().st_size
            total += size
            if size > byte_limit(value['budget'], 'max_file_bytes') or total > byte_limit(value['budget'], 'max_total_bytes'):
                raise ValueError('actual native artifacts exceed whole-batch byte budget')
            row = (str(target), relative.as_posix(), size, _path_provenance(target))
            row_bytes = _retained_size(row)
            # Charge each row independently, conservatively double-counting
            # shared strings, plus both old and prospective list storage.
            if row_bytes is None or retained_before_stats + stat_bytes + row_bytes + 2 * sys.getsizeof(stats) + 1024 > min(_MEMO_BYTES, 64 * 1024 * 1024):
                raise _MemoCapacityUnavailable('owned lexical guard capacity unavailable')
            stats.append(row)
            stat_bytes += row_bytes
            if len(stats) > graph_limit(value['budget'], 'max_files'):
                raise _ReuseUnavailable('bounded owned-inventory file count exceeded')
        owned.append((str(directory), _path_provenance(value['output_directory']), include_profile,
                      tuple(sorted(excluded)), sorted(stats), receipt))
        _memo_capacity(working, paths._documents, paths._edges, paths._guard_memory, policy, installations, runtimes, owned,
                       stats, receipt, excluded, row if stats else None)
    installation_stats, installation_total = {}, 0
    for install, expected in installations.items():
        stats = stat_manifest(expected, install, machine_budget)
        installation_total += sum(entry['bytes'] for entry in stats)
        if installation_total > machine_budget['max_total_bytes']:
            raise _ReuseUnavailable('complete bounded installation identity exceeds reuse budget')
        installation_stats[install] = {entry['path']: entry for entry in stats}
        _memo_capacity(working, paths._documents, paths._edges, paths._guard_memory, policy, installations, runtimes, owned,
                       installation_stats, stats, expected)
    return {'runtimes': runtimes, 'installation_stats': installation_stats, 'owned': owned}


def _memo_extras(paths, budget, *, working=()):
    """Fresh installation/host and exact lexical inventories under old authority."""
    from runtime_common import host_fingerprint
    preflight = _memo_extra_preflight(paths, budget, working=working)
    # Reserve an independent projection, including generated SHA/record fields;
    # the stat/preflight graph already contains every selected lexical member.
    _memo_capacity(working, paths._documents, paths._edges, paths._guard_memory, preflight, reserve=preflight)
    runtimes, owned, runtime_roots, resolutions = [], [], {}, []
    raw, records, function_paths, actual, declared = None, (), (), {}, {}
    for path, role, runtime, install, expected in preflight['runtimes']:
        runtime_roots[str(Path(path).parent)] = install
        files = []
        for target in sorted(expected):
            entry = preflight['installation_stats'][install][target]
            sha = sha256_file(target)
            if sha != expected[target]:
                raise ValueError('actual installation bytes changed during validation reuse')
            files.append({**entry, 'sha256': sha})
        from validate_environment import _version_info
        release, version_text = _version_info(install)
        if runtime.get('release') != release or not runtime.get('version', '').startswith(version_text):
            raise ValueError('actual installation release/version changed')
        runtimes.append((path, role, files, [_path_provenance(runtime['matlabroot']),
            _path_provenance(runtime['executable']), _path_provenance(Path(install) / 'VersionInfo.xml')] +
            [_path_provenance(binding['path']) for binding in runtime['function_files']]))
    for directory, provenance, include_profile, excluded, stats, receipt in preflight['owned']:
        inventory = [(relative, size, sha256_file(target), lexical)
                     for target, relative, size, lexical in stats]
        actual = {row[0]: row[2] for row in inventory if row[0] not in excluded}
        declared = {binding['file']: binding['sha256'] for binding in receipt['artifacts'].values()}
        if actual != declared:
            raise ValueError('exact H owned inventory changed during validation reuse')
        owned.append((directory, provenance, include_profile, inventory))
    _memo_capacity(working, paths._documents, paths._edges, paths._guard_memory, preflight, runtimes, owned,
                   runtime_roots, actual, declared)
    receipt_roles = {'qualification_a_receipt', 'qualification_d_receipt', 'qualification_e_receipt',
                     'qualification_h_receipt', 'simulation_receipt', 'implementation_receipt', 'h_trial_receipt'}
    for (path, role, _), value in paths._documents.items():
        if path is None or role not in receipt_roles:
            continue
        binding = value.get('artifacts', {}).get('raw')
        if binding is None:
            continue
        directory = Path(path).parent
        install = runtime_roots.get(str(directory))
        if install is None:
            raise _ReuseUnavailable('actual raw resolution installation authority unavailable')
        raw_path = contained_path(directory, binding['file'])
        raw = limited_document(raw_path, budget)
        _memo_capacity(working, paths._documents, paths._edges, paths._guard_memory, preflight, runtimes, owned,
                       runtime_roots, actual, declared, resolutions, raw)
        records = [raw, *_memo_records(raw.get('cases')), *_memo_records(raw.get('operations'))]
        retained_before_resolutions = _memo_capacity(working, paths._documents, paths._edges, paths._guard_memory, preflight,
            runtimes, owned, runtime_roots, actual, declared, resolutions, raw, records)
        resolution_bytes = 0
        for record in records:
            functions = _memo_records(record.get('functions'))
            _memo_capacity(working, paths._documents, paths._edges, paths._guard_memory, preflight,
                runtimes, owned, runtime_roots, actual, declared, resolutions, raw, records, reserve=functions)
            function_paths = [item['path'] for item in functions]
            if record.get('operation_id') == 'simulink.library_load':
                function_paths.append(record['output']['file_name'])
            for name in function_paths:
                if name.startswith('built-in (') and name.endswith(')'):
                    name = name[len('built-in ('):-1]
                contained_path(install, name)
                projection = (str(raw_path), _path_provenance(name), Path(name).is_file())
                projection_bytes = _retained_size(projection)
                if projection_bytes is None or retained_before_resolutions + resolution_bytes + projection_bytes + 2 * sys.getsizeof(resolutions) + sys.getsizeof(function_paths) + 1024 > min(_MEMO_BYTES, 64 * 1024 * 1024):
                    raise _MemoCapacityUnavailable('raw lexical resolution guard capacity unavailable')
                resolutions.append(projection)
                resolution_bytes += projection_bytes
        _memo_capacity(working, paths._documents, paths._edges, paths._guard_memory, preflight, runtimes, owned,
                       runtime_roots, actual, declared, resolutions, raw, records, function_paths, functions,
                       projection if function_paths else None)
    result = {'host': host_fingerprint(), 'installation': sorted(runtimes, key=repr),
              'owned': sorted(owned, key=repr), 'resolutions': sorted(resolutions, key=repr)}
    _memo_capacity(working, paths._documents, paths._edges, paths._guard_memory, preflight, result, runtime_roots,
                   actual, declared, raw, records, function_paths, functions if records else None)
    return result


def _publish_validation(session, key, snapshot, extras, result, *, working=()):
    caller = sys._getframe(1)
    if (Path(caller.f_code.co_filename).resolve() != ROOT / 'scripts/verification_common.py' or
            caller.f_code.co_name not in {'_attempt_h_validation_reuse', '_commit_historical_validation'}):
        return
    if len(session.entries) >= min(_MEMO_ENTRIES, 64):
        return
    entry = {'snapshot': snapshot, 'extras': extras, 'result': result,
             'clock': datetime.now(timezone.utc).isoformat()}
    # Include the live proof/copy and retained session while allocating a second
    # graph. Two upper bounds conservatively count any shared immutable objects.
    live_size = _retained_size((session, key, entry, working))
    copy_size = _retained_size((key, entry))
    if live_size is None or copy_size is None or live_size + copy_size > min(_MEMO_BYTES, 64 * 1024 * 1024):
        return
    try:
        copied = deepcopy(entry)
    except (TypeError, ValueError, RecursionError, MemoryError):
        return
    session.entries[key] = copied
    if _retained_size(session) is None:
        session.entries.pop(key, None)


def _reuse_validation(kind, *, project_root, budget, compute, eligible, options=(), roots=(),
                      root_contexts=None, request=None, request_role=None, capability=None):
    """Only actual H-owned consumers can publish operation-local proof results."""
    session = _H_VALIDATION_SESSION.get()
    root = Path(project_root).resolve()
    caller = sys._getframe(1)
    permitted = {'wrapped', '_validated_h_baseline'} if kind != 'historical_qualification' else {'_historical_qualification_facts'}
    owner_file = ROOT / ('scripts/h_analysis_trial.py' if kind == 'historical_qualification' else 'scripts/verification_common.py')
    if (kind not in _MEMO_KINDS or session is None or not session.active or
            Path(caller.f_code.co_filename).resolve() != owner_file or caller.f_code.co_name not in permitted or
            session.owner != _validation_owner() or
            kind == 'historical_qualification' and not _live_capability(capability, session, root)):
        return compute()
    changed = None
    try:
        result = _attempt_h_validation_reuse(kind, session=session, root=root, project_root=project_root,
            budget=budget, compute=compute, eligible=eligible, options=options, roots=roots,
            root_contexts=root_contexts, request=request, request_role=request_role, capability=capability)
    except _ValidationReuseChanged as error:
        changed = (str(error), error.report)
    # The failed attempt's frame and caught traceback have exited before either
    # original nested computation or a clean public rejection is evaluated.
    if changed is not None:
        raise _ValidationReuseChanged(*changed) from None
    if result is _MEMO_ORIGINAL:
        return compute()
    return result


_MEMO_ORIGINAL = object()


def _attempt_h_validation_reuse(kind, *, session, root, project_root, budget, compute, eligible,
                                options, roots, root_contexts, request, request_role, capability):
    caller = sys._getframe(1)
    if (Path(caller.f_code.co_filename).resolve() != ROOT / 'scripts/verification_common.py' or
            caller.f_code.co_name != '_reuse_validation'):
        return _MEMO_ORIGINAL
    try:
        _memo_capacity(budget, request, options, reserve=(budget, request))
        descriptor = {'root': str(root), 'root_lexical': str(project_root), 'budget': deepcopy(budget),
                      'roots': tuple(map(str, roots)), 'contexts': {str(p): r for p, r in (root_contexts or {}).items()},
                      'request': deepcopy(request), 'request_role': request_role}
        descriptor['caller_root_lexical'] = options.get('root_lexical') if isinstance(options, dict) else None
        key = (kind, str(root), str(project_root), tuple(map(str, roots)),
               canonical_digest(budget), canonical_digest(options), request_role)
        before, paths = _memo_base(descriptor, working=(key, budget, request, options))
        extras_before = _memo_extras(paths, descriptor['budget'],
            working=(descriptor, key, before, paths._documents, paths._edges, paths._guard_memory, budget, request, options))
        if _retained_size((session, descriptor, key, before, extras_before, paths._documents, paths._edges, paths._guard_memory, budget, request, options)) is None:
            return _MEMO_ORIGINAL
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError, RecursionError, MemoryError):
        return _MEMO_ORIGINAL
    previous = session.entries.get(key)
    if previous is not None:
        try:
            if (typed_equal(before, previous['snapshot']) and
                    datetime.now(timezone.utc) >= datetime.fromisoformat(previous['clock']) and
                    typed_equal(extras_before, previous['extras'])):
                retained = _retained_size((session, descriptor, key, before, extras_before, paths._documents, paths._edges, paths._guard_memory, budget, request, options))
                cloned = _retained_size(previous['result'])
                if retained is None or cloned is None or retained + cloned > min(_MEMO_BYTES, 64 * 1024 * 1024):
                    return _MEMO_ORIGINAL
                result = deepcopy(previous['result'])
                try:
                    working = (descriptor, key, before, extras_before, paths._documents, paths._edges, paths._guard_memory, result, budget, request, options)
                    _memo_capacity(working, reserve=(before, extras_before, paths._documents, paths._edges, paths._guard_memory))
                    assert_unchanged(before['manifest'])
                    final, final_paths = _memo_base(descriptor, working=working)
                    final_extras = _memo_extras(final_paths, descriptor['budget'],
                        working=(working, final, final_paths._documents, final_paths._edges, final_paths._guard_memory))
                    _memo_capacity(working, final, final_paths._documents, final_paths._edges, final_paths._guard_memory, final_extras)
                    if not typed_equal(before, final) or not typed_equal(final_extras, previous['extras']):
                        raise ValueError('validation reuse evidence changed before return')
                except _MemoCapacityUnavailable:
                    session.entries.pop(key, None)
                    return _MEMO_ORIGINAL
                except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError, RecursionError) as error:
                    session.entries.pop(key, None)
                    raise _ValidationReuseChanged(str(error), result) from error
                return result
        except _ValidationReuseChanged:
            raise
        except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError, RecursionError, MemoryError):
            pass
        session.entries.pop(key, None)
    if key in session.inflight:
        return _MEMO_ORIGINAL
    work = (descriptor, key, before, extras_before, paths._documents, paths._edges, paths._guard_memory, budget, request, options)
    try:
        # Include the current complete graph and conservatively reserve both
        # registry containers' growth before adding the nested parent.
        live = _memo_capacity(work)
        growth = 4 * sys.getsizeof(session.inflight) + 2 * sys.getsizeof(session.working) + 1024
        if live + growth > min(_MEMO_BYTES, 64 * 1024 * 1024):
            return _MEMO_ORIGINAL
    except _MemoCapacityUnavailable:
        return _MEMO_ORIGINAL
    session.inflight.add(key)
    session.working.append(work)
    try:
        result = compute()
        if not eligible(result):
            return result
        try:
            working_before = (descriptor, key, before, extras_before, paths._documents, paths._edges, paths._guard_memory, result, budget, request, options)
            _memo_capacity(working_before, reserve=(before, extras_before, paths._documents, paths._edges, paths._guard_memory))
            after, after_paths = _memo_base(descriptor, working=working_before)
            if not typed_equal(before, after):
                raise _ValidationReuseChanged('validation evidence changed during complete consumer', result)
            extras = _memo_extras(after_paths, descriptor['budget'],
                working=(working_before, after, after_paths._documents, after_paths._edges, after_paths._guard_memory))
            if not typed_equal(extras_before, extras):
                raise _ValidationReuseChanged('validation installation/host/owned inventory changed during complete consumer', result)
        except _ValidationReuseChanged:
            raise
        except _MemoCapacityUnavailable:
            return result
        except _ReuseUnavailable as error:
            # A missing guard before compute uses the original path. Losing an
            # established guard during compute is an observed mutation/failure.
            raise _ValidationReuseChanged('complete validation guard became unavailable: ' + str(error), result) from error
        except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError, RecursionError) as error:
            raise _ValidationReuseChanged(str(error), result) from error
        working = (descriptor, key, before, extras_before, paths._documents, paths._edges, paths._guard_memory,
                   after, extras, after_paths._documents, after_paths._edges, after_paths._guard_memory, result, budget, request, options)
        retainable = _retained_size((session, working)) is not None
        if kind == 'historical_qualification' and retainable:
            try:
                _memo_capacity(working, reserve=(None, None, None, None, None))
            except _MemoCapacityUnavailable:
                pass
            else:
                pending = (key, descriptor, after, extras, result)
                capability.pending = pending
                if _retained_size((session, working, pending)) is None:
                    capability.pending = None
        try:
            _memo_capacity(working, reserve=(after, extras, after_paths._documents, after_paths._edges, after_paths._guard_memory))
            final, final_paths = _memo_base(descriptor, working=working)
            final_extras = _memo_extras(final_paths, descriptor['budget'],
                working=(working, final, final_paths._documents, final_paths._edges, final_paths._guard_memory))
            _memo_capacity(working, final, final_paths._documents, final_paths._edges, final_paths._guard_memory, final_extras)
            if not typed_equal(before, final) or not typed_equal(extras_before, final_extras):
                raise ValueError('validation evidence changed before complete consumer return')
        except _MemoCapacityUnavailable:
            session.entries.pop(key, None)
            if kind == 'historical_qualification':
                capability.pending = None
            return result
        except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError, RecursionError) as error:
            session.entries.pop(key, None)
            if kind == 'historical_qualification':
                capability.pending = None
            raise _ValidationReuseChanged(str(error), result) from error
        if kind != 'historical_qualification' and retainable:
            # Publish after the last real guard, including its live graph in the
            # prospective copy bound. No copied entry predates this final check.
            _publish_validation(session, key, after, extras, result,
                working=(working, final, final_paths._documents, final_paths._edges, final_paths._guard_memory, final_extras))
        return result
    finally:
        session.working.pop()
        session.inflight.discard(key)


def _commit_historical_validation(capability, *, complete):
    caller = sys._getframe(1)
    if (Path(caller.f_code.co_filename).resolve() != ROOT / 'scripts/h_analysis_trial.py' or
            caller.f_code.co_name != '_finish_historical_replay'):
        return
    session = _H_VALIDATION_SESSION.get()
    if session is None or not _live_capability(capability, session, capability.root):
        return
    pending, capability.pending = capability.pending, None
    if not complete or pending is None:
        return
    key, descriptor, before, extras, result = pending
    try:
        _memo_capacity(pending, reserve=(before, extras))
        after, paths = _memo_base(descriptor, working=(pending,))
        fresh_extras = _memo_extras(paths, descriptor['budget'],
            working=(pending, after, paths._documents, paths._edges, paths._guard_memory))
        _memo_capacity(pending, after, paths._documents, paths._edges, paths._guard_memory, fresh_extras)
    except _MemoCapacityUnavailable:
        return
    if not typed_equal(before, after) or not typed_equal(extras, fresh_extras):
        raise ValueError('historical qualification proof changed before complete receipt publication')
    _publish_validation(session, key, after, fresh_extras, result,
        working=(pending, descriptor, paths._documents, paths._edges, paths._guard_memory, fresh_extras))


def _memoized_h_validation(kind, role):
    """Finite public H source/receipt whitelist; supplied reports are comparisons."""
    def decorate(function):
        owners = {'study_source': ('validate_h_analysis_study', 'validate_h_analysis_study', 'h_study_contract'),
                  'study_receipt': ('validate_h_analysis_study_receipt', 'validate_h_analysis_study_receipt', 'h_study_receipt'),
                  'h2_source': ('validate_model_verification', 'validate_model_verification', 'h2_contract'),
                  'h2_receipt': ('validate_model_verification_receipt', 'validate_model_verification_receipt', 'h2_receipt')}
        owner = owners.get(kind)
        if (owner is None or function.__name__ != owner[1] or role != owner[2] or
                Path(function.__code__.co_filename).resolve() != ROOT / ('scripts/' + owner[0] + '.py')):
            raise ValueError('validation reuse is restricted to actual H-owned source/receipt validators')
        @wraps(function)
        def wrapped(path, *, project_root=None, **kwargs):
            with validation_session():
                def compute():
                    return function(path, project_root=project_root, **kwargs)
                def prepare():
                    # Optional bootstrap documents leave this frame before the
                    # main attempt, or before original fallback begins.
                    try:
                        actual = Path(path).resolve()
                        value = limited_document(actual)
                        root = Path(project_root or (value['project_root'] if kind == 'study_receipt' else actual.parent)).resolve()
                        if kind == 'h2_receipt':
                            request_value = limited_document(actual.parent / 'model-verification-inputs.json')
                            root = Path(project_root or request_value['project_root']).resolve()
                            contract = contained_path(root, request_value['contract']['path'])
                        elif kind == 'study_receipt':
                            contract = contained_path(root, value['study']['path'])
                        else:
                            contract = actual
                        source = limited_document(contract)
                        budget = source.get('budget') or HARD_BUDGET
                        supplied = kwargs.get('study_report') if kind == 'study_receipt' else kwargs.get('contract_report')
                        if supplied is not None:
                            descriptor = {'root': str(root), 'root_lexical': str(project_root or root),
                                'budget': budget, 'roots': (str(path),), 'contexts': {str(actual): role},
                                'request': None, 'request_role': None}
                            before, paths = _memo_base(descriptor, working=(value, source))
                            session = _H_VALIDATION_SESSION.get()
                            work = (descriptor, before, paths._documents, paths._edges, paths._guard_memory, value, source)
                            live = _memo_capacity(work)
                            if live + 2 * sys.getsizeof(session.working) + 1024 > min(_MEMO_BYTES, 64 * 1024 * 1024):
                                return _MEMO_ORIGINAL
                            session.working.append(work)
                            try:
                                if kind == 'study_receipt':
                                    from validate_h_analysis_study import validate_h_analysis_study
                                    current = validate_h_analysis_study(contract, project_root=root, require_reviewed=True)
                                    fields = ('project_id', 'contract_path', 'contract_sha256', 'semantic_sha256', 'input_manifest')
                                else:
                                    from validate_model_verification import validate_model_verification
                                    current = validate_model_verification(contract, project_root=root, require_reviewed=True)
                                    fields = ('contract_path', 'contract_sha256', 'project_id', 'semantic_sha256', 'input_manifest')
                                if any(not typed_equal(supplied.get(key), current.get(key)) for key in fields):
                                    return _MEMO_ORIGINAL
                            finally:
                                session.working.pop()
                        options = {'explicit_root': project_root is not None,
                                   'root_lexical': str(project_root) if project_root is not None else None,
                                   'require_reviewed': kwargs.get('require_reviewed', False)}
                        return str(root), budget, options, str(actual)
                    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError, RecursionError):
                        return _MEMO_ORIGINAL
                prepared = prepare()
                if prepared is _MEMO_ORIGINAL:
                    return compute()
                root, budget, options, actual = prepared
                def eligible(report):
                    if not report.get('valid'):
                        return False
                    return {'study_source': report.get('reviewed') and report.get('study_ready'),
                            'h2_source': report.get('reviewed') and report.get('assessment_ready'),
                            'study_receipt': report.get('study_complete'),
                            'h2_receipt': report.get('model_verification_decided')}[kind] is True
                changed = None
                try:
                    return _reuse_validation(kind, project_root=root, budget=budget, compute=compute, eligible=eligible,
                        options=options, roots=[path], root_contexts={actual: role})
                except _ValidationReuseChanged as error:
                    # Every rejection report is the actual attempt's public
                    # result or its independent cached-entry clone. Supplied
                    # reports and cached entry objects are never returned here.
                    changed = (str(error), error.report)
                except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError, RecursionError):
                    pass
                if changed is None:
                    return compute()
                message, report = changed
                if not isinstance(report, dict):
                    report = compute()
                for field in ('valid', 'reviewed', 'study_ready', 'assessment_ready', 'execution_ready',
                              'study_complete', 'study_accepted', 'defined', 'model_verification_decided',
                              'model_verified', 'claim_supported'):
                    if field in report:
                        report[field] = False
                report.setdefault('errors', []).append(message)
                return report
        return wrapped
    return decorate


def _validated_h_baseline(kind, path, *, project_root, budget, compute, options=()):
    caller = sys._getframe(1)
    if (Path(caller.f_code.co_filename).resolve() != ROOT / 'scripts/validate_h_analysis_study.py' or
            caller.f_code.co_name != 'validate_h_analysis_study'):
        return compute()
    roles = {'baseline_protocol': 'simulation_protocol', 'baseline_simulation': 'simulation_receipt',
             'baseline_h1': 'h1_receipt'}
    def eligible(report):
        return report.get('valid') is True and bool({'baseline_protocol': report.get('frozen'),
            'baseline_simulation': report.get('primary_run_complete'),
            'baseline_h1': report.get('numerically_verified')}[kind])
    return _reuse_validation(kind, project_root=project_root, budget=budget, compute=compute, eligible=eligible,
        options=options, roots=[path], root_contexts={Path(path).resolve(): roles[kind]})
