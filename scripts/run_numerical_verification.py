"""Assess three historical E runs in a new directory; never execute MATLAB."""
from __future__ import annotations

import argparse
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path

from runtime_common import canonical_digest, contained_path, emit, sha256_file
from validate_numerical_verification import time_tolerance, uniform_grid, validate_numerical_verification
from validate_simulation_receipt import validate_simulation_receipt
from verification_common import (assert_unchanged, bound_file, evidence_paths, finite, input_manifest,
                                 limited_document, serialized_json, source_identities, typed_equal)

RECEIPT_NAME = 'numerical-verification-receipt.json'
INPUT_NAME = 'numerical-verification-input.json'
RESULT_NAME = 'numerical-verification-result.json'
ORIGINAL_NAME = 'numerical-contract-original.txt'


def actual_samples(output, times, *, native_grid=None):
    actual = output['time']
    values = output['values']
    if len(actual) != len(values) or any(not finite(x) for x in [*actual, *values]):
        raise ValueError('non-finite or mismatched actual numerical output')
    if any(a >= b for a, b in zip(actual, actual[1:])):
        raise ValueError('actual numerical output time is duplicated or unordered')
    if native_grid is not None:
        if len(actual) != len(native_grid) or any(abs(a-g) > time_tolerance(g) for a, g in zip(actual, native_grid)):
            raise ValueError('actual fixed-step native output does not cover its complete integer grid')
    selected = []
    for time in times:
        indices = [i for i, sample in enumerate(actual) if abs(sample-time) <= time_tolerance(time)]
        if len(indices) != 1:
            raise ValueError('comparison time has missing or ambiguous actual samples')
        selected.append(values[indices[0]])
    return selected


def refinement_result(output, samples):
    from numerical_obligations import refinement_summary
    return refinement_summary(output, samples)


def assess_numerical(report, receipt_paths, *, project_root):
    """Revalidate E history and compute H1; shared by producer and consumer."""
    root = Path(project_root).resolve()
    if not report['valid'] or not report['assessment_ready']:
        raise ValueError('current reviewed numerical contract is not assessment_ready')
    if not isinstance(receipt_paths, (list, tuple)) or len(receipt_paths) != 3:
        raise ValueError('three ordered independent E receipt paths required')
    receipts = [contained_path(root, str(Path(p).resolve())) for p in receipt_paths]
    if len(set(receipts)) != 3:
        raise ValueError('each refinement level requires its own independent E receipt')
    budget = report['budget']
    paths = evidence_paths(receipts, root, budget, root_contexts={path: 'simulation_receipt' for path in receipts})
    paths.update(b['path'] for b in report['bound_files'])
    manifest = input_manifest(paths, root, budget)
    runs, levels = [], []
    for path, protocol in zip(receipts, report['protocol_reports']):
        # Enforce declared native sample bounds before E opens the MAT/CSV.
        evidence = limited_document(path, budget)
        data_path = contained_path(path.parent, evidence['artifacts']['data']['file'])
        outputs = limited_document(data_path, budget)['outputs']
        if not isinstance(outputs, list) or any(not isinstance(item, dict) or
                not isinstance(item.get('time'), list) or not isinstance(item.get('values'), list) or
                len(item['time']) > budget['max_samples_per_output'] or
                len(item['values']) > budget['max_samples_per_output'] for item in outputs):
            raise ValueError('actual native output exceeds declared sample count budget or has malformed arrays')
        run = validate_simulation_receipt(path, project_root=root, protocol_report=protocol)
        if not run['valid'] or not run['primary_run_complete']:
            raise ValueError('complete independently validated E receipt required: ' + '; '.join(run['errors']))
        if Path(run['protocol_path']).resolve() != Path(protocol['contract_path']).resolve() or run['protocol_sha256'] != protocol['contract_sha256']:
            raise ValueError('ordered refinement E receipt binds a different protocol')
        runs.append(run)
        if Path(run['data_path']).resolve() != data_path:
            raise ValueError('independently validated E data artifact differs')
        levels.append({'run_spec': protocol['run_spec'], 'outputs': outputs, 'states': []})
    from numerical_obligations import evaluate_trial_numeric
    from validate_numerical_verification import EXTENDED_SETTINGS_FIELDS
    computed = evaluate_trial_numeric(levels, report['numeric_policy'], report.get('numeric_context'), project_id=report['project_id'])
    if not computed['outputs']:
        raise ValueError('complete numerical output refinement unavailable: '+ '; '.join(computed['errors']))
    result = {**computed, 'comparison_times': report['comparison_times']}
    if not any(k in report['numeric_policy'] for k in EXTENDED_SETTINGS_FIELDS):
        # Preserve the original recorded-point result format for its consumers.
        result = {k: result[k] for k in ('schema_version', 'project_id', 'method', 'comparison_times', 'outputs', 'criteria_satisfied', 'numerically_verified', 'disposition', 'claim_limit')}
        result['outputs'] = [{k: v for k, v in o.items() if k not in ('scope', 'comparison_times')} for o in result['outputs']]
    if len(serialized_json(result)) > budget['max_result_bytes']:
        raise ValueError('numerical result exceeds declared byte budget')
    assert_unchanged(manifest)
    return result, manifest, runs


def run_numerical_verification(contract_path, receipts, output_dir, *, project_root=None):
    contract_path = Path(contract_path).resolve()
    root = Path(project_root or contract_path.parent).resolve()
    directory = contained_path(root, str(Path(output_dir).resolve()))
    directory.mkdir(parents=True, exist_ok=False)
    start = datetime.now(timezone.utc).isoformat(timespec='microseconds')
    receipt = {'schema_version': 1, 'run_id': str(uuid.uuid4()), 'project_id': None,
               'project_root': str(root), 'started_at': start, 'finished_at': None,
               'numerical_verification': None, 'sources': {},
               'status': 'blocked', 'artifacts': {}, 'errors': []}
    try:
        receipt['sources'] = source_identities()
        report = validate_numerical_verification(contract_path, project_root=root, require_reviewed=True)
        if not report['valid'] or not report['assessment_ready']:
            raise ValueError('current reviewed H1 contract required: ' + '; '.join(report['errors'] + report['missing_gates']))
        value = limited_document(contract_path, report['budget'])
        original = contract_path.read_bytes()
        if not isinstance(receipts, (list, tuple)) or len(receipts) != 3:
            raise ValueError('three ordered independent E receipt paths required')
        # Preflight all E inputs before the request's explicit receipt hashes.
        preflight = evidence_paths(receipts, root, report['budget'],
                                   root_contexts={Path(path).resolve(): 'simulation_receipt' for path in receipts})
        preflight.update(b['path'] for b in report['bound_files'])
        initial = input_manifest(preflight, root, report['budget'])
        request = {'schema_version': 1, 'run_id': receipt['run_id'], 'project_root': str(root),
                   'numerical_verification': bound_file(contract_path, root),
                   'contract_snapshot': value, 'semantic_sha256': report['semantic_sha256'],
                   'receipts': [bound_file(p, root) for p in receipts], 'sources': receipt['sources']}
        request['input_identity'] = canonical_digest(request)
        payload = serialized_json(request)
        if len(payload) > report['budget']['max_file_bytes']:
            raise ValueError('numerical input snapshot exceeds declared file byte budget')
        (directory / INPUT_NAME).write_bytes(payload)
        (directory / ORIGINAL_NAME).write_bytes(original)
        receipt.update(project_id=report['project_id'], numerical_verification=request['numerical_verification'])
        result, manifest, _ = assess_numerical(report, receipts, project_root=root)
        if contract_path.read_bytes() != original:
            raise ValueError('numerical contract changed while assessing evidence')
        assert_unchanged(initial)
        assert_unchanged(report['input_manifest'])
        if not typed_equal(receipt['sources'], source_identities()):
            raise ValueError('numerical safety source changed during assessment')
        result_payload = serialized_json(result)
        proposed = {**receipt, 'status': 'complete', 'input_manifest': manifest,
                    'semantic_sha256': report['semantic_sha256'],
                    'finished_at': datetime.now(timezone.utc).isoformat(timespec='microseconds'),
                    'artifacts': {name: {'file': name, 'sha256': '0' * 64, 'bytes': size}
                                  for name, size in ((INPUT_NAME, len(payload)), (ORIGINAL_NAME, len(original)),
                                                     (RESULT_NAME, len(result_payload)))}}
        receipt_size = len(serialized_json(proposed))
        if max(len(payload), len(original), len(result_payload), receipt_size) > report['budget']['max_file_bytes']:
            raise ValueError('numerical output artifact exceeds declared file byte budget')
        if sum(item['bytes'] for item in manifest) + len(payload) + len(original) + len(result_payload) + receipt_size > report['budget']['max_total_bytes']:
            raise ValueError('numerical own artifacts and upstream inputs exceed aggregate byte budget')
        (directory / RESULT_NAME).write_bytes(result_payload)
        receipt.update(status='complete', input_manifest=manifest, semantic_sha256=report['semantic_sha256'])
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        receipt['errors'].append(str(error))
    for file in (INPUT_NAME, ORIGINAL_NAME, RESULT_NAME):
        path = directory / file
        if path.is_file():
            receipt['artifacts'][file] = {'file': file, 'sha256': sha256_file(path), 'bytes': path.stat().st_size}
    receipt['finished_at'] = datetime.now(timezone.utc).isoformat(timespec='microseconds')
    path = directory / RECEIPT_NAME
    path.write_bytes(serialized_json(receipt))
    from validate_numerical_verification_receipt import validate_numerical_verification_receipt
    result = validate_numerical_verification_receipt(path, project_root=root)
    result['receipt_path'] = str(path)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('contract', type=Path)
    parser.add_argument('--receipt', action='append', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--project-root', type=Path)
    args = parser.parse_args()
    try:
        result = run_numerical_verification(args.contract, args.receipt, args.output_dir, project_root=args.project_root)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        result = {'valid': False, 'numerically_verified': False, 'errors': [str(error)]}
    emit(result)
    return 0 if result['valid'] and result.get('numerically_verified') else 1


if __name__ == '__main__':
    raise SystemExit(main())
