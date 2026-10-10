"""Independently recompute H2 receipt evidence and every finite claim disposition."""
from __future__ import annotations

import argparse
from pathlib import Path
import uuid

from runtime_common import canonical_digest, contained_path, emit, load_contract, schema_errors, sha256_file
from model_verification_common import RECEIPT_NAME, compute_assessment
from verification_common import (HARD_BUDGET, assert_unchanged, evidence_paths, input_manifest,
                                 limited_document, source_identities, typed_equal)
from validate_model_verification import validate_model_verification
from run_model_verification import INPUT_NAME, RESULT_NAME


def validate_model_verification_receipt(path, *, project_root=None, contract_report=None):
    result = {'valid': False, 'model_verification_decided': False, 'model_verified': False,
              'claim_supported': False, 'primary_numerical_receipt_path': None,
              'primary_protocol_path': None, 'primary_receipt_path': None, 'model_identity': None,
              'project_id': None, 'bound_files': [], 'receipt_path': str(Path(path).resolve()), 'receipt_sha256': None,
              'contract_path': None, 'contract_sha256': None, 'semantic_sha256': None,
              'environment_checked': False, 'execution_allowed': False, 'errors': []}
    try:
        path = Path(path).resolve()
        if path.name != RECEIPT_NAME:
            raise ValueError('unexpected H2 receipt filename')
        # This small hard-bounded bootstrap discovers the original project contract.
        # The result is not read or hashed until its reviewed aggregate budget passes.
        bootstrap = input_manifest([path, path.parent / INPUT_NAME], path.parent, HARD_BUDGET)
        receipt = limited_document(path)
        fields = {'schema_version', 'operation_id', 'run_id', 'project_id', 'contract_semantic_sha256',
                  'input_identity', 'sources', 'assessment_complete', 'artifacts'}
        if set(receipt) != fields or type(receipt['schema_version']) is not int or receipt['schema_version'] != 1:
            raise ValueError('H2 receipt exact schema differs')
        uuid.UUID(receipt['run_id'])
        if receipt['operation_id'] != 'verification.model_claims' or type(receipt['assessment_complete']) is not bool:
            raise ValueError('H2 operation/completion identity differs')
        if not typed_equal(receipt['sources'], source_identities()):
            raise ValueError('H2 safety source identity changed')
        if receipt['assessment_complete'] is not True:
            raise ValueError('H2 technical failure or incomplete evidence has no claim decision')
        if set(receipt['artifacts']) != {'input', 'result'}:
            raise ValueError('H2 exact input/result artifact set differs')
        files = {}
        for key, name in (('input', INPUT_NAME), ('result', RESULT_NAME)):
            binding = receipt['artifacts'][key]
            if set(binding) != {'file', 'sha256'} or binding['file'] != name:
                raise ValueError('H2 artifact name/binding differs')
            files[key] = contained_path(path.parent, name)
        request = limited_document(files['input'])
        request_fields = {'schema_version', 'operation_id', 'run_id', 'project_root', 'project_id', 'contract',
                          'contract_semantic_sha256', 'contract_snapshot', 'contract_original_text', 'input_manifest', 'sources'}
        if set(request) != request_fields or type(request['schema_version']) is not int or request['schema_version'] != 1:
            raise ValueError('H2 captured input exact schema differs')
        if canonical_digest(request) != receipt['input_identity']:
            raise ValueError('H2 captured input digest differs')
        if (any(request[key] != receipt[key] for key in ('operation_id', 'run_id', 'project_id', 'contract_semantic_sha256')) or
                not typed_equal(request['sources'], receipt['sources'])):
            raise ValueError('H2 input/receipt identities differ')
        root = Path(project_root).resolve() if project_root is not None else Path(request['project_root']).resolve()
        if Path(request['project_root']).resolve() != root or not path.is_relative_to(root):
            raise ValueError('H2 receipt project root differs or leaves root')
        if set(request['contract']) != {'path', 'sha256'}:
            raise ValueError('H2 captured contract binding schema differs')
        contract = contained_path(root, request['contract']['path'])
        # Inspect only a hard-bounded schema-valid contract before heavy H1/E readers.
        contract_bootstrap = input_manifest([contract], root, HARD_BUDGET)
        value = limited_document(contract)
        assert_unchanged(contract_bootstrap)
        issues = schema_errors(value, load_contract('core/model_verification_contract.yaml'))
        if issues or value['budget'] is None or any(type(count) is not int for count in value['budget'].values()):
            raise ValueError('complete schema-valid H2 contract budget required')
        budget = value['budget']
        paths = evidence_paths([contract], root, budget, root_contexts={contract: 'h2_contract'})
        paths.update([path, *files.values()])
        complete_manifest = input_manifest(paths, root, budget)
        if files['result'].stat().st_size > budget['max_result_bytes']:
            raise ValueError('H2 result exceeds reviewed result byte budget')
        for key, artifact in files.items():
            if sha256_file(artifact) != receipt['artifacts'][key]['sha256']:
                raise ValueError('H2 artifact changed: ' + key)
        actual = limited_document(files['result'], budget)
        if set(actual) != {'schema_version', 'run_id', 'assessment', 'errors'} or type(actual['schema_version']) is not int or actual['schema_version'] != 1:
            raise ValueError('H2 computed result exact schema differs')
        if actual['run_id'] != receipt['run_id']:
            raise ValueError('H2 result/receipt run identity differs')
        report = validate_model_verification(contract, project_root=root, require_reviewed=True)
        if not report['valid'] or not report['assessment_ready']:
            raise ValueError('current H2 contract not assessment ready: ' + '; '.join(report['errors'] + report['missing_gates']))
        if not typed_equal(budget, report['budget']):
            raise ValueError('H2 bootstrap and independently verified reviewed budgets differ')
        # Reapply the verified current budget to every own/upstream artifact. Keep
        # both manifests: this later pass must not replace an earlier identity.
        verified_budget_manifest = input_manifest(paths, root, report['budget'])
        if files['result'].stat().st_size > report['budget']['max_result_bytes']:
            raise ValueError('H2 result exceeds independently verified reviewed result byte budget')
        if (report['contract_sha256'] != contract_bootstrap[0]['sha256'] or
                report['contract_sha256'] != request['contract']['sha256'] or report['semantic_sha256'] != request['contract_semantic_sha256'] or
                contract.read_bytes().decode('utf-8') != request['contract_original_text'] or
                not typed_equal(limited_document(contract, report['budget']), request['contract_snapshot'])):
            raise ValueError('H2 original contract bytes/full snapshot differs')
        if contract_report is not None and any(not typed_equal(contract_report.get(key), report.get(key)) for key in
                                              ('contract_path', 'contract_sha256', 'project_id', 'semantic_sha256', 'input_manifest')):
            raise ValueError('supplied H2 report differs from current complete bindings')
        if not typed_equal(request['input_manifest'], report['input_manifest']):
            raise ValueError('H2 complete current input manifest differs')
        assert_unchanged(report['input_manifest'])
        if receipt['assessment_complete'] is not True or actual['assessment'] is None or actual['errors'] != []:
            raise ValueError('H2 technical failure or incomplete evidence has no claim decision')
        expected = compute_assessment(request['contract_snapshot'], report['_members'])
        if not typed_equal(expected, actual['assessment']):
            raise ValueError('H2 exact independently recomputed metrics/dispositions differ')
        assert_unchanged(report['input_manifest'])
        assert_unchanged(complete_manifest)
        assert_unchanged(verified_budget_manifest)
        assert_unchanged(bootstrap)
        assert_unchanged(contract_bootstrap)
        if not typed_equal(receipt['sources'], source_identities()):
            raise ValueError('H2 source changed during historical assessment')
        original_bindings = {item['path']: item for item in complete_manifest}
        result.update(valid=True, **{key: expected[key] for key in ('model_verification_decided', 'model_verified', 'claim_supported')},
                      claims=expected['claims'], claim_limit=expected['claim_limit'], physical_validation=False,
                      receipt_path=str(path), receipt_sha256=original_bindings[str(path)]['sha256'],
                      bound_files=report['bound_files'] + complete_manifest,
                      contract_path=report['contract_path'], contract_sha256=report['contract_sha256'], semantic_sha256=report['semantic_sha256'],
                      project_id=report['project_id'], model_identity=report['model_identity'],
                      allowed_external=report.get('allowed_external', []), numerical_scopes=report['numerical_scopes'],
                      primary_numerical_receipt_path=report['primary_numerical_receipt_path'],
                      primary_protocol_path=report['primary_protocol_path'], primary_receipt_path=report['primary_receipt_path'])
        for key in ('model_path', 'model_sha256', 'mapping_path', 'mapping_sha256', 'problem_path', 'problem_sha256', 'approval_path', 'approval_sha256'):
            result[key] = report[key]
    except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError, OverflowError, ZeroDivisionError) as error:
        result['errors'].append(str(error))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', type=Path)
    parser.add_argument('--project-root', type=Path)
    args = parser.parse_args()
    result = validate_model_verification_receipt(args.path, project_root=args.project_root)
    emit(result)
    return 0 if result['valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
