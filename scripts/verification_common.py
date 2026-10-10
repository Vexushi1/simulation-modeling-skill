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


def source_identities():
    paths = list(dict.fromkeys(load_contract('core/simulation_assurance_contract.yaml')['source_files'] + list(H1_FILES)))
    return {path: sha256_file(ROOT / path) for path in paths}


def bound_file(path, root=None):
    path = Path(path).resolve()
    if root is not None and not path.is_relative_to(Path(root).resolve()):
        raise ValueError('verification input leaves project root: ' + str(path))
    return {'path': str(path), 'sha256': sha256_file(path)}


def limited_document(path, budget=None):
    path = Path(path)
    limit = (budget or HARD_BUDGET)['max_file_bytes']
    if not path.is_file() or path.stat().st_size > limit:
        raise ValueError('verification file missing or exceeds byte budget: ' + str(path))
    return load_document(path)


def limited_source_document(path, budget=None):
    """Read an object/array task source with the existing unique parser rules.

    This broader root shape never applies to business/qualification documents.
    Array selectors are data selection, not evidence-role authorization.
    """
    path = Path(path)
    if not path.is_file() or path.stat().st_size > (budget or HARD_BUDGET)['max_file_bytes']:
        raise ValueError('verification source missing or exceeds byte budget: ' + str(path))
    text = path.read_text(encoding='utf-8-sig')
    try:
        if path.suffix.lower() == '.json':
            value = json.loads(text, object_pairs_hook=_unique_json, parse_constant=_invalid_constant)
        else:
            value = yaml.load(text, Loader=UniqueLoader)
    except (yaml.YAMLError, RecursionError) as error:
        raise ValueError(f'invalid or excessively nested structured source in {path}: {error}') from error
    if not isinstance(value, (dict, list)):
        raise ValueError('expected a structured source object or array in ' + str(path))
    # Check the graph, not an expanded JSON serialization: bounded YAML aliases
    # can share subtrees exponentially or form cycles. Visit every node once.
    pending, active, complete = [(value, False)], set(), set()
    while pending:
        node, leaving = pending.pop()
        if type(node) is float and not math.isfinite(node):
            raise ValueError('non-finite structured source value in ' + str(path))
        if not isinstance(node, (dict, list)):
            continue
        identity = id(node)
        if leaving:
            active.remove(identity)
            complete.add(identity)
            continue
        if identity in active:
            raise ValueError('cyclic structured source in ' + str(path))
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
    return value


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
        super().__init__(paths)
        self.allowed_external = set(allowed_external)


def input_manifest(paths, root, budget, *, allowed_external=()):
    """Check bytes before hashing; immutable project files only, no truncation."""
    allowed = {Path(p).resolve() for p in allowed_external}
    allowed.update(Path(p).resolve() for p in getattr(paths, 'allowed_external', ()))
    root, pending, total = Path(root).resolve(), [], 0
    for path in sorted({Path(p).resolve() for p in paths}, key=str):
        if not path.is_relative_to(root) and path not in allowed:
            raise ValueError('verification input leaves project root: ' + str(path))
        if not path.is_file():
            raise ValueError('verification input is not a file: ' + str(path))
        size = path.stat().st_size
        total += size
        if size > budget['max_file_bytes'] or total > budget['max_total_bytes']:
            raise ValueError('verification input byte budget exceeded')
        pending.append((path, size))
    # No hash/load of the supplied set occurs before the complete stat preflight.
    return [{'path': str(path), 'sha256': sha256_file(path), 'bytes': size} for path, size in pending]


def assert_unchanged(manifest):
    for binding in manifest:
        path = Path(binding['path'])
        if not path.is_file() or path.stat().st_size != binding['bytes'] or sha256_file(path) != binding['sha256']:
            raise ValueError('verification input changed during assessment: ' + str(path))


def evidence_paths(receipt_paths, root, budget, *, root_contexts=None):
    """Discover bounded evidence using caller-selected roles, never filenames.

    Only the selected H/E/D chain can introduce original A/D/E qualification
    paths. Ordinary sources/reviews and snapshots stay task-only. Real E/D
    consumers subsequently verify every selected historical identity.
    """
    root = Path(root).resolve()
    allowed_roots = {'task', 'h1_contract', 'h1_receipt', 'h2_contract', 'h2_receipt',
                     'simulation_protocol', 'simulation_receipt', 'implementation_receipt'}
    contexts = {Path(p).resolve(): kind for p, kind in (root_contexts or {}).items()}
    if any(kind not in allowed_roots for kind in contexts.values()):
        raise ValueError('unknown verification evidence root context')
    queued = [(Path(p).resolve(), contexts.get(Path(p).resolve(), 'task'), None) for p in receipt_paths]
    paths, visited, total = EvidencePaths(), set(), 0

    def enqueue(binding, kind='task', qualification_root=None):
        if binding is None:
            return
        if not isinstance(binding, dict) or not isinstance(binding.get('path'), str):
            raise ValueError('malformed verification evidence path binding')
        base = qualification_root or root
        queued.append((contained_path(base, binding['path']), kind, qualification_root))

    def qualification(binding, kind):
        if not isinstance(binding, dict) or not isinstance(binding.get('path'), str):
            raise ValueError('malformed original qualification binding')
        candidate = Path(binding['path']).resolve()
        queued.append((candidate, kind, candidate.parent))

    def task_bindings(node, *, skip=()):
        pending, visited_nodes = [(node, set(skip))], set()
        excluded = {'sources', 'runtime', 'functions', 'bindings', 'artifacts', 'input_manifest',
                    'contract_snapshot', 'protocol_snapshot', 'mapping_snapshot'}
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
                      'simulation_receipt': 'simulation_request',
                      'implementation_receipt': 'implementation_request',
                      'qualification_a_receipt': 'qualification_a_request',
                      'qualification_d_receipt': 'qualification_d_request',
                      'qualification_e_receipt': 'qualification_e_request'}
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
    }
    while queued:
        path, context, qualification_root = queued.pop()
        path = contained_path(qualification_root or root, str(Path(path).resolve()))
        if qualification_root is not None and not path.is_relative_to(root):
            paths.allowed_external.add(path)
        key = (path, context, qualification_root)
        if key in visited:
            continue
        visited.add(key)
        if path not in paths:
            if not path.is_file() or path.stat().st_size > budget['max_file_bytes']:
                raise ValueError('verification evidence missing or exceeds file byte budget')
            total += path.stat().st_size
            if total > budget['max_total_bytes']:
                raise ValueError('verification total evidence byte budget exceeded')
            paths.add(path)
        if context == 'opaque' or path.suffix.lower() not in {'.json', '.yaml', '.yml'}:
            continue
        value = limited_source_document(path, budget) if context == 'task' else limited_document(path, budget)
        if context == 'task' and isinstance(value, list):
            task_bindings(value)
            continue
        # A receipt's role comes from an actual selected binding, not basename.
        for artifact_key, binding in value.get('artifacts', {}).items():
            if isinstance(binding, dict) and isinstance(binding.get('file'), str):
                child = contained_path(path.parent, binding['file'])
                is_input = artifact_key == 'input' or context == 'h1_receipt' and artifact_key == 'numerical-verification-input.json'
                child_context = receipt_inputs.get(context, 'task') if is_input else 'opaque'
                queued.append((child, child_context, qualification_root))

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
                        enqueue(binding, kind)
                elif binding_key == 'bound_files' and isinstance(binding, list):
                    # Bind each byte identity; scan the authoritative originals
                    # through protocol/mapping roles rather than this claimed list.
                    for item in binding:
                        enqueue(item, 'opaque')
        if not context.startswith('qualification_'):
            task_bindings(value, skip=skip)
    return paths
