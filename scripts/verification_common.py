"""Strict shared Phase H readers; no runtime execution or decision writeback."""
from __future__ import annotations

import math
import json
from pathlib import Path

from runtime_common import ROOT, canonical_digest, contained_path, load_contract, load_document, schema_errors, sha256_file
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
    actual = selected_value(limited_document(path, result.get('budget')), reference['selector'])
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


def evidence_paths(receipt_paths, root, budget):
    """Preflight E receipt directories and their explicit external evidence bindings.

    Repository source/function identities are validated by E and are not project
    data. Only execution-time A/D/E qualification bindings in actual D/E input
    artifacts introduce an external exception; their own receipt artifacts stay
    contained in the original qualification directory. E/D independently verify
    those exact histories before any acceptance.
    """
    root = Path(root).resolve()
    queued = [(Path(p).resolve(), None, None, True) for p in receipt_paths]
    paths, visited = EvidencePaths(), set()
    total = 0
    while queued:
        path, qualification_root, input_kind, scan = queued.pop()
        path = Path(path).resolve()
        if qualification_root is None:
            path = contained_path(root, str(path))
        else:
            path = contained_path(qualification_root, str(path))
            if not path.is_relative_to(root):
                paths.allowed_external.add(path)
        if path in visited:
            continue
        visited.add(path)
        if not path.is_file() or path.stat().st_size > budget['max_file_bytes']:
            raise ValueError('verification evidence missing or exceeds file byte budget')
        total += path.stat().st_size
        if total > budget['max_total_bytes']:
            raise ValueError('verification total evidence byte budget exceeded')
        paths.add(path)
        if not scan or path.suffix.lower() not in {'.json', '.yaml', '.yml'}:
            continue
        value = limited_document(path, budget)
        # Every explicitly saved receipt artifact is relative to that receipt.
        receipt_kinds = {'simulation-receipt.json': 'simulation',
                         'simulation-profile-receipt.json': 'simulation',
                         'implementation-receipt.json': 'implementation',
                         'implementation-profile-receipt.json': 'implementation'}
        for key, binding in value.get('artifacts', {}).items():
            if isinstance(binding, dict) and isinstance(binding.get('file'), str):
                child = contained_path(path.parent, binding['file'])
                kind = receipt_kinds.get(path.name) if key == 'input' else None
                # Only input artifacts introduce bindings. Numeric/raw/result
                # artifacts are budgeted here, decoded by their real consumer.
                scan_child = key == 'input' or child.name in {
                    'numerical-verification-input.json', 'model-verification-input.json'}
                queued.append((child, qualification_root, kind, scan_child))
        bindings = value.get('bindings', {})
        if isinstance(bindings, dict):
            qualification_roles = {'environment_profile', 'environment_receipt'}
            qualification_roles.update({'simulation_profile', 'simulation_profile_receipt'} if input_kind == 'simulation'
                                       else {'implementation_profile', 'implementation_profile_receipt'})
            for key, binding in bindings.items():
                if isinstance(binding, dict) and isinstance(binding.get('path'), str):
                    candidate = Path(binding['path']).resolve()
                    if input_kind in {'simulation', 'implementation'} and key in qualification_roles:
                        queued.append((candidate, candidate.parent, None, True))
                    else:
                        queued.append((contained_path(root, binding['path']), None, None, True))
                elif key == 'bound_files' and isinstance(binding, list):
                    queued.extend((contained_path(root, item['path']), None, None, True) for item in binding)
        # Source-bound task contracts and review text are transitive inputs.
        def task_bindings(node):
            if isinstance(node, dict):
                if isinstance(node.get('path'), str) and isinstance(node.get('sha256'), str):
                    queued.append((contained_path(root, node['path']), None, None, True))
                for key, child in node.items():
                    if key not in {'sources', 'runtime', 'functions', 'bindings', 'artifacts', 'input_manifest'}:
                        task_bindings(child)
                if 'sources' in node and isinstance(node['sources'], list):
                    task_bindings(node['sources'])
            elif isinstance(node, list):
                for child in node:
                    task_bindings(child)
        if qualification_root is None:
            task_bindings(value)
    return paths
