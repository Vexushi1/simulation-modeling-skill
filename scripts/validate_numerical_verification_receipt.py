"""Read-only independent recomputation of an H1 historical assessment."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from runtime_common import canonical_digest, contained_path, emit, load_contract, schema_errors
from run_numerical_verification import INPUT_NAME, ORIGINAL_NAME, RECEIPT_NAME, RESULT_NAME, assess_numerical
from validate_numerical_verification import validate_numerical_verification
from verification_common import (HARD_BUDGET, assert_unchanged, evidence_paths, input_manifest, limited_document,
                                 source_identities, typed_equal)


def validate_numerical_verification_receipt(path, *, project_root=None, contract_report=None):
    path = Path(path).resolve()
    result = {'valid': False, 'criteria_satisfied': False, 'numerically_verified': False,
              'primary_protocol_path': None, 'primary_receipt_path': None, 'model_identity': None,
              'project_id': None, 'bound_files': [], 'receipt_path': str(path), 'receipt_sha256': None,
              'contract_path': None, 'contract_sha256': None, 'environment_checked': False,
              'execution_allowed': False, 'errors': []}
    try:
        if path.name != RECEIPT_NAME:
            raise ValueError('unexpected numerical verification receipt filename')
        bootstrap = input_manifest([path], path.parent, HARD_BUDGET)
        receipt = limited_document(path)
        fields = {'schema_version', 'run_id', 'project_id', 'project_root', 'started_at', 'finished_at',
                  'numerical_verification', 'sources', 'status', 'artifacts', 'errors', 'input_manifest', 'semantic_sha256'}
        if not isinstance(receipt, dict) or set(receipt) != fields or type(receipt['schema_version']) is not int or receipt['schema_version'] != 1 or receipt['status'] != 'complete' or type(receipt['errors']) is not list or receipt['errors']:
            raise ValueError('complete error-free historical H1 assessment required')
        if type(receipt['run_id']) is not str or not receipt['run_id'] or type(receipt['project_root']) is not str:
            raise ValueError('exact typed numerical receipt run/root identity required')
        root = Path(receipt['project_root']).resolve()
        if project_root is not None and Path(project_root).resolve() != root:
            raise ValueError('numerical receipt project root differs')
        if not path.is_relative_to(root):
            raise ValueError('numerical receipt leaves project root')
        times = [datetime.fromisoformat(receipt[k]) for k in ('started_at', 'finished_at')]
        if any(t.tzinfo is None for t in times) or not times[0] <= times[1] <= datetime.now(timezone.utc):
            raise ValueError('numerical assessment time order invalid')
        binding = receipt['numerical_verification']
        if not isinstance(binding, dict) or set(binding) != {'path', 'sha256'}:
            raise ValueError('exact numerical contract binding fields required')
        contract_path = contained_path(root, binding['path'])
        contract_bootstrap = input_manifest([contract_path], root, HARD_BUDGET)
        # Only bounded bootstrap receipt/contract reads precede complete input
        # discovery. No artifact or transitive evidence hash/MAT read does.
        contract = limited_document(contract_path)
        issues = schema_errors(contract, load_contract('core/numerical_verification_contract.yaml'))
        if issues or contract['budget'] is None or any(type(v) is not int for v in contract['budget'].values()):
            raise ValueError('valid typed source-declared numerical read budget required')
        budget = contract['budget']
        if not isinstance(receipt['artifacts'], dict) or set(receipt['artifacts']) != {INPUT_NAME, ORIGINAL_NAME, RESULT_NAME}:
            raise ValueError('numerical receipt exact artifact set differs')
        artifacts = []
        for filename, artifact in receipt['artifacts'].items():
            if not isinstance(artifact, dict) or set(artifact) != {'file', 'sha256', 'bytes'} or artifact['file'] != filename or type(artifact['bytes']) is not int:
                raise ValueError('numerical artifact exact binding fields differ')
            file = contained_path(path.parent, filename)
            if filename == RESULT_NAME and file.stat().st_size > budget['max_result_bytes']:
                raise ValueError('persisted numerical result exceeds declared result byte budget')
            artifacts.append(file)
        paths = evidence_paths([path], root, budget)
        paths.update([contract_path, *artifacts])
        complete_manifest = input_manifest(paths, root, budget)
        verified = {item['path']: item for item in complete_manifest}
        if verified[str(contract_path)]['sha256'] != binding['sha256']:
            raise ValueError('numerical assessment contract identity changed')
        for filename, artifact in receipt['artifacts'].items():
            entry = verified[str(path.parent / filename)]
            if not typed_equal(entry['bytes'], artifact['bytes']) or entry['sha256'] != artifact['sha256']:
                raise ValueError('numerical assessment artifact identity changed')
        initial_sources = source_identities()
        if not typed_equal(receipt['sources'], initial_sources):
            raise ValueError('numerical assessment safety source identity changed')
        report = validate_numerical_verification(contract_path, project_root=root, require_reviewed=True)
        if not report['valid'] or not report['assessment_ready']:
            raise ValueError('current complete reviewed numerical contract required: ' + '; '.join(report['errors'] + report['missing_gates']))
        if contract_report is not None and any(not typed_equal(contract_report.get(k), report.get(k)) for k in ('project_id', 'contract_path', 'contract_sha256', 'semantic_sha256', 'bound_files')):
            raise ValueError('supplied numerical contract report differs from current source bindings')
        request = limited_document(path.parent / INPUT_NAME, budget)
        expected = {'schema_version', 'run_id', 'project_root', 'numerical_verification', 'contract_snapshot',
                    'semantic_sha256', 'receipts', 'sources', 'input_identity'}
        if not isinstance(request, dict) or set(request) != expected or type(request['schema_version']) is not int or request['schema_version'] != 1:
            raise ValueError('numerical request exact fields differ')
        digest = canonical_digest({k: v for k, v in request.items() if k != 'input_identity'})
        if request['input_identity'] != digest or not typed_equal(request['run_id'], receipt['run_id']) or request['project_root'] != str(root):
            raise ValueError('numerical input/run identity changed')
        if not typed_equal(request['sources'], receipt['sources']) or not typed_equal(request['numerical_verification'], binding):
            raise ValueError('numerical input source/contract identity differs')
        if not typed_equal(request['contract_snapshot'], limited_document(contract_path, report['budget'])) or (path.parent / ORIGINAL_NAME).read_bytes() != contract_path.read_bytes():
            raise ValueError('complete original numerical contract differs from captured snapshot')
        if request['semantic_sha256'] != report['semantic_sha256'] or receipt['semantic_sha256'] != report['semantic_sha256'] or receipt['project_id'] != report['project_id']:
            raise ValueError('numerical assessment semantic/project identity differs')
        if not isinstance(request['receipts'], list) or len(request['receipts']) != 3:
            raise ValueError('three exact E receipt bindings required')
        receipt_paths = []
        for item in request['receipts']:
            if not isinstance(item, dict) or set(item) != {'path', 'sha256'}:
                raise ValueError('exact E receipt binding fields required')
            file = contained_path(root, item['path'])
            if verified[str(file)]['sha256'] != item['sha256']:
                raise ValueError('bound E receipt identity changed')
            receipt_paths.append(file)
        computed, manifest, runs = assess_numerical(report, receipt_paths, project_root=root)
        if not typed_equal(receipt['input_manifest'], manifest):
            raise ValueError('numerical receipt complete input manifest differs')
        stored = limited_document(path.parent / RESULT_NAME, report['budget'])
        if not typed_equal(stored, computed):
            raise ValueError('numerical result differs from independent native-output recomputation')
        assert_unchanged(complete_manifest)
        assert_unchanged(bootstrap)
        assert_unchanged(contract_bootstrap)
        if not typed_equal(initial_sources, source_identities()):
            raise ValueError('numerical assessment safety source changed during reading')
        result.update(valid=True, criteria_satisfied=computed['criteria_satisfied'], numerically_verified=computed['numerically_verified'],
                      project_id=report['project_id'], model_identity=report['model_identity'],
                      contract_path=str(contract_path), contract_sha256=report['contract_sha256'],
                      numerical_verification_path=str(contract_path), numerical_verification_sha256=report['contract_sha256'],
                      primary_protocol_path=report['primary_protocol_path'], primary_protocol_sha256=report['primary_protocol_sha256'],
                      primary_receipt_path=str(receipt_paths[0]), primary_receipt_sha256=verified[str(receipt_paths[0])]['sha256'],
                      primary_protocol_report=report['protocol_reports'][0], primary_simulation_report=runs[0],
                      outputs=computed['outputs'], claim_limit=computed['claim_limit'],
                      bound_files=complete_manifest, input_manifest=complete_manifest,
                      allowed_external=sorted(map(str, paths.allowed_external)),
                      receipt_sha256=verified[str(path)]['sha256'])
        for name in ('problem', 'model', 'approval', 'mapping'):
            for suffix in ('path', 'sha256'):
                result[name + '_' + suffix] = report.get(name + '_' + suffix)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        result['errors'].append(str(error))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', type=Path)
    parser.add_argument('--project-root', type=Path)
    args = parser.parse_args()
    result = validate_numerical_verification_receipt(args.path, project_root=args.project_root)
    emit(result)
    return 0 if result['valid'] and result['numerically_verified'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
