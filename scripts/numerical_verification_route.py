"""Read-only H1 routing; review never grants native execution or writes state."""
from pathlib import Path

from runtime_common import load_document


def select_bindings(supplied, state_result):
    """Supplied inputs cannot replace a project's exact historical anchors."""
    selected = {}
    for name, path in supplied.items():
        bound = state_result.get(name + '_path')
        if bound and path is not None and Path(path).resolve() != Path(bound).resolve():
            raise ValueError('requested ' + name + ' differs from project-state binding')
        selected[name] = path if path is not None else bound
    return selected


def match_bindings(report, selected, *, state_path=None):
    errors = []
    if state_path and report.get('project_id') != load_document(Path(state_path))['project_id']:
        errors.append('verification project_id differs from project state')
    for name in ('problem', 'model', 'approval', 'mapping', 'protocol', 'primary_run'):
        field = {'protocol': 'primary_protocol_path', 'primary_run': 'primary_receipt_path'}.get(name, name + '_path')
        actual = report.get(field)
        if selected.get(name) is not None and actual is not None and Path(selected[name]).resolve() != Path(actual).resolve():
            errors.append('verification differs from requested ' + name + ' binding')
    return errors


def numerical_verification_route(result, *, router, resources, state_result=None,
                                 state_path=None, numerical_verification_path=None,
                                 numerical_verification_receipt_path=None,
                                 problem_path=None, model_path=None, approval_path=None,
                                 mapping_path=None, protocol_path=None, run_receipt_path=None,
                                 requested=()):
    state_result = state_result or {}
    fallback = router['fallback']['numerical_verification_invalid']

    def block(gate, errors):
        result.update(status='blocked', missing_gates=[gate], errors=errors,
                      fallback=fallback, next_step=fallback['reason'])
        return result

    if requested:
        return block('h_review_has_no_selected_operations', ['H review does not select or qualify MATLAB operations'])
    try:
        selected = select_bindings({'numerical_verification': numerical_verification_path,
            'numerical_verification_receipt': numerical_verification_receipt_path,
            'problem': problem_path, 'model': model_path, 'approval': approval_path,
            'mapping': mapping_path, 'protocol': protocol_path, 'primary_run': run_receipt_path}, state_result)
    except ValueError as error:
        return block('verification_state_binding_matches', [str(error)])
    if selected['numerical_verification'] is None:
        return block('numerical_verification_contract_supplied', ['supply the source-bound H1 contract'])
    from validate_numerical_verification import validate_numerical_verification
    report = validate_numerical_verification(selected['numerical_verification'],
        project_root=state_result.get('project_root'), require_reviewed=result['intent'].endswith('_review'))
    result.update(numerical_verification_validation=report,
                  numerical_verification_path=str(Path(selected['numerical_verification']).resolve()),
                  numerical_verification_sha256=report.get('contract_sha256'),
                  numerical_verification_semantic_sha256=report.get('semantic_sha256'))
    errors = match_bindings(report, selected, state_path=state_path)
    if not report['valid'] or errors:
        return block('numerical_verification_contract_valid', report['errors'] + errors)
    if result['intent'] == 'numerical_verification_review':
        if selected['numerical_verification_receipt'] is None:
            return block('current_numerical_verification_receipt', ['supply the actual H1 assessment receipt'])
        from validate_numerical_verification_receipt import validate_numerical_verification_receipt
        receipt = validate_numerical_verification_receipt(selected['numerical_verification_receipt'],
            project_root=state_result.get('project_root'), contract_report=report)
        result['numerical_verification_receipt_validation'] = receipt
        errors = match_bindings(receipt, selected, state_path=state_path)
        if (receipt.get('contract_path') != str(Path(selected['numerical_verification']).resolve()) or
                receipt.get('contract_sha256') != report.get('contract_sha256')):
            errors.append('assessment receipt differs from current H1 contract')
        if not receipt['valid'] or errors:
            return block('current_numerical_verification_receipt', receipt['errors'] + errors)
        result['numerically_verified'] = bool(receipt.get('numerically_verified'))
        missing = [] if result['numerically_verified'] else ['numerical_verification_criteria_satisfied']
    else:
        missing = list(report.get('missing_gates', []))
    result.update(status='inspected', execution_scope='numerical_verification_review',
                  activated_modules=[result['intent']], activated_resources=list(resources),
                  missing_gates=missing)
    return result
