"""Create finite H2 assessment evidence in a new directory; no MATLAB/state writes."""
from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path

from runtime_common import canonical_digest, emit, sha256_file
from model_verification_common import RECEIPT_NAME, compute_assessment
from validate_model_verification import validate_model_verification
from verification_common import assert_unchanged, limited_document, source_identities

INPUT_NAME = 'model-verification-inputs.json'
RESULT_NAME = 'model-verification-results.json'


def json_bytes(value):
    return (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')


def write_json(path, value):
    path.write_bytes(json_bytes(value))


def run_model_verification(contract_path, output_dir, *, project_root=None):
    output = Path(output_dir).resolve()
    if output.exists():
        raise ValueError('H2 assessment requires a new output directory')
    sources = source_identities()
    report = validate_model_verification(contract_path, project_root=project_root, require_reviewed=True)
    if not report['valid'] or not report['assessment_ready']:
        raise ValueError('H2 assessment blocked: ' + '; '.join(report['errors'] + report['missing_gates']))
    root = Path(report['project_root'])
    if not output.is_relative_to(root):
        raise ValueError('H2 output directory leaves project root')
    if any(Path(item['path']).is_relative_to(output) for item in report['input_manifest']):
        raise ValueError('H2 output directory would own an input file')
    contract = Path(report['contract_path'])
    value = limited_document(contract, report['budget'])
    request = {'schema_version': 1, 'operation_id': 'verification.model_claims', 'run_id': str(uuid.uuid4()),
               'project_root': str(root), 'project_id': report['project_id'],
               'contract': {'path': str(contract), 'sha256': report['contract_sha256']},
               'contract_semantic_sha256': report['semantic_sha256'], 'contract_snapshot': value,
               'contract_original_text': contract.read_bytes().decode('utf-8'),
               'input_manifest': report['input_manifest'], 'sources': sources}
    if len(json_bytes(request)) > report['budget']['max_file_bytes']:
        raise ValueError('H2 captured input exceeds reviewed file byte budget')
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / INPUT_NAME, request)
    result, errors = None, []
    try:
        assert_unchanged(report['input_manifest'])
        result = compute_assessment(value, report['_members'])
        assert_unchanged(report['input_manifest'])
        if source_identities() != sources:
            raise ValueError('H2 safety source changed during assessment')
        result_record = {'schema_version': 1, 'run_id': request['run_id'], 'assessment': result, 'errors': []}
        result_bytes = len(json_bytes(result_record))
        if result_bytes > report['budget']['max_result_bytes']:
            raise ValueError('H2 result exceeds reviewed result byte budget')
        prototype = {'schema_version': 1, 'operation_id': request['operation_id'], 'run_id': request['run_id'],
                     'project_id': request['project_id'], 'contract_semantic_sha256': report['semantic_sha256'],
                     'input_identity': canonical_digest(request), 'sources': sources, 'assessment_complete': True,
                     'artifacts': {key: {'file': name, 'sha256': '0' * 64}
                                   for key, name in (('input', INPUT_NAME), ('result', RESULT_NAME))}}
        receipt_bytes = len(json_bytes(prototype))
        if max(result_bytes, receipt_bytes) > report['budget']['max_file_bytes']:
            raise ValueError('H2 output artifact exceeds reviewed file byte budget')
        if (sum(item['bytes'] for item in report['input_manifest']) + len(json_bytes(request)) +
                result_bytes + receipt_bytes > report['budget']['max_total_bytes']):
            raise ValueError('H2 own artifacts and upstream inputs exceed aggregate byte budget')
    except (OSError, ValueError, KeyError, TypeError, OverflowError, ZeroDivisionError) as error:
        result = None
        errors.append(str(error))
    write_json(output / RESULT_NAME, {'schema_version': 1, 'run_id': request['run_id'],
                                    'assessment': result, 'errors': errors})
    receipt = {'schema_version': 1, 'operation_id': request['operation_id'], 'run_id': request['run_id'],
               'project_id': request['project_id'], 'contract_semantic_sha256': report['semantic_sha256'],
               'input_identity': canonical_digest(request), 'sources': sources,
               'assessment_complete': result is not None,
               'artifacts': {key: {'file': name, 'sha256': sha256_file(output / name)}
                             for key, name in (('input', INPUT_NAME), ('result', RESULT_NAME))}}
    write_json(output / RECEIPT_NAME, receipt)
    from validate_model_verification_receipt import validate_model_verification_receipt
    return validate_model_verification_receipt(output / RECEIPT_NAME, project_root=root, contract_report=report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('contract_path', type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--project-root', type=Path)
    args = parser.parse_args()
    try:
        result = run_model_verification(args.contract_path, args.output_dir, project_root=args.project_root)
    except (OSError, ValueError) as error:
        emit({'valid': False, 'model_verification_decided': False, 'model_verified': False,
              'claim_supported': False, 'errors': [str(error)], 'environment_checked': False, 'execution_allowed': False})
        return 1
    emit(result)
    return 0 if result['valid'] and result['model_verification_decided'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
