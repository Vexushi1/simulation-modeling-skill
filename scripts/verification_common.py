"""Strict shared Phase H readers; no runtime execution or decision writeback."""
from __future__ import annotations

import math
import json
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


class EvidencePaths(set):
    def __init__(self, paths=(), *, allowed_external=()):
        super().__init__()
        self.allowed_external = set(allowed_external)
        self.claimed_hashes = {}
        self.source_authorities = []
        self.update(paths)

    def update(self, *others):
        for other in others:
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

    def add_repository_sources():
        nonlocal repository_added
        if repository_added or include_repository_sources is False:
            return
        repository_added = True
        source_paths = repository_source_paths()
        stat_manifest(source_paths, ROOT, budget)
        source_paths.assert_authority_unchanged()
        source_snapshots.append(source_paths)
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
        candidate = Path(binding['path']).resolve()
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
            paths.add(path)
            if len(paths) > file_limit:
                raise ValueError('verification evidence file count budget exceeded')
        if context == 'opaque' or path is not None and path.suffix.lower() not in {'.json', '.yaml', '.yml'}:
            continue
        if value is None:
            value = limited_source_document(path, budget) if context == 'task' else limited_document(path, budget)
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
        paths.claimed_hashes[candidate] = sha256
    for source_paths in source_snapshots:
        source_paths.assert_authority_unchanged()
    return paths
