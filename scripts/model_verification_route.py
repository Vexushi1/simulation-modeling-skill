"""Read-only finite H2 review; completion and claim support remain distinct."""
from pathlib import Path

from numerical_verification_route import match_bindings, select_bindings

ANALYSIS_KINDS = {'sensitivity_analysis': 'sensitivity', 'robustness_analysis': 'robustness',
                  'solver_comparison': 'solver_comparison', 'model_comparison': 'model_comparison'}


def model_verification_route(result, *, router, resources, state_result=None, state_path=None,
                             model_verification_path=None, model_verification_receipt_path=None,
                             numerical_verification_receipt_path=None, problem_path=None,
                             model_path=None, approval_path=None, mapping_path=None,
                             protocol_path=None, run_receipt_path=None, requested=()):
    state_result = state_result or {}
    fallback = router['fallback']['model_verification_invalid']

    def block(gate, errors):
        result.update(status='blocked', missing_gates=[gate], errors=errors,
                      fallback=fallback, next_step=fallback['reason'])
        return result

    if requested:
        return block('h_review_has_no_selected_operations', ['H review does not select or qualify MATLAB operations'])
    try:
        selected = select_bindings({'model_verification': model_verification_path,
            'model_verification_receipt': model_verification_receipt_path,
            'numerical_verification_receipt': numerical_verification_receipt_path,
            'problem': problem_path, 'model': model_path, 'approval': approval_path,
            'mapping': mapping_path, 'protocol': protocol_path, 'primary_run': run_receipt_path}, state_result)
    except ValueError as error:
        return block('verification_state_binding_matches', [str(error)])
    if selected['model_verification'] is None:
        return block('model_verification_contract_supplied', ['supply the source-bound H2 contract'])
    from validate_model_verification import validate_model_verification
    report = validate_model_verification(selected['model_verification'],
        project_root=state_result.get('project_root'), require_reviewed=result['intent'].endswith('_review'))
    result.update(model_verification_validation={key: value for key, value in report.items() if key != '_members'},
                  model_verification_path=str(Path(selected['model_verification']).resolve()),
                  model_verification_sha256=report.get('contract_sha256'),
                  model_verification_semantic_sha256=report.get('semantic_sha256'))
    errors = match_bindings(report, selected, state_path=state_path)
    actual_h1 = report.get('primary_numerical_receipt_path')
    if selected['numerical_verification_receipt'] is not None and actual_h1 is not None and Path(actual_h1).resolve() != Path(selected['numerical_verification_receipt']).resolve():
        errors.append('H2 primary H1 receipt differs from project/request binding')
    if not report['valid'] or errors:
        return block('model_verification_contract_valid', report['errors'] + errors)
    kind = ANALYSIS_KINDS.get(result['intent'])
    if kind and kind not in report.get('required_analysis_kinds', []):
        return block('requested_analysis_required', ['the current H2 contract does not require ' + kind])
    if result['intent'] == 'model_verification_review':
        if selected['model_verification_receipt'] is None:
            return block('current_model_verification_receipt', ['supply the actual H2 assessment receipt'])
        from validate_model_verification_receipt import validate_model_verification_receipt
        receipt = validate_model_verification_receipt(selected['model_verification_receipt'],
            project_root=state_result.get('project_root'), contract_report=report)
        result['model_verification_receipt_validation'] = receipt
        errors = match_bindings(receipt, selected, state_path=state_path)
        if (receipt.get('contract_path') != str(Path(selected['model_verification']).resolve()) or
                receipt.get('contract_sha256') != report.get('contract_sha256')):
            errors.append('assessment receipt differs from current H2 contract')
        if selected['numerical_verification_receipt'] is not None and receipt.get('primary_numerical_receipt_path') != str(Path(selected['numerical_verification_receipt']).resolve()):
            errors.append('H2 assessment differs from current primary H1 receipt')
        if not receipt['valid'] or errors:
            return block('current_model_verification_receipt', receipt['errors'] + errors)
        for field in ('model_verification_decided', 'model_verified', 'claim_supported'):
            result[field] = receipt.get(field, False)
        missing = [] if result['model_verification_decided'] else ['required_analyses_complete']
    else:
        missing = list(report.get('missing_gates', []))
    result.update(status='inspected', execution_scope='model_verification_review',
                  activated_modules=[result['intent']], activated_resources=list(resources),
                  missing_gates=missing)
    return result
