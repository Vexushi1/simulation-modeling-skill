"""Read-only H2 state: a completed disposition is distinct from support."""
from pathlib import Path

from numerical_verification_state import upstream_errors
from runtime_common import contained_path, sha256_file

STAGES = {'MODEL_VERIFICATION_DECIDED', 'MODEL_VERIFIED'}
SCOPES = {'all', 'model_verification'}
HISTORICAL_ROLES = {'model_verification_contract', 'model_verification_evidence'}


def validate_bindings(state, root, result, errors, stale, scope):
    result.update(model_verification_checked=False, model_verification_reviewed=False,
                  model_verification_decided=False, model_verified=False, claim_supported=False,
                  model_verification_path=None, model_verification_receipt_path=None)
    for anchor in ('model_verification', 'model_verification_receipt'):
        binding = state.get(anchor)
        path = contained_path(root, binding['path']) if binding else None
        result[anchor + '_path'] = str(path) if path else None
    if scope not in SCOPES:
        return
    result['model_verification_checked'] = True
    binding = state.get('model_verification')
    if binding:
        from validate_model_verification import validate_model_verification
        report = validate_model_verification(result['model_verification_path'], project_root=root,
            require_reviewed=state['current_stage'] in STAGES or bool(state.get('model_verification_receipt')))
        result['model_verification_validation'] = {key: value for key, value in report.items() if key != '_members'}
        invalid = list(report['errors']) if not report['valid'] else []
        if report.get('contract_sha256') != binding['sha256'] or report.get('project_id') != state['project_id']:
            invalid.append('H2 contract differs from state project/SHA binding')
        if report.get('reviewed'):
            invalid.extend(upstream_errors(report, state, result))
            if report.get('primary_numerical_receipt_path') != result['numerical_verification_receipt_path']:
                invalid.append('H2 contract differs from state primary H1 receipt')
            if not result['numerically_verified']:
                invalid.append('H2 requires the current accepted primary H1')
        if invalid:
            errors.extend('H2 contract: ' + error for error in invalid)
            stale.add('model_verification')
        result['model_verification_reviewed'] = bool(report.get('reviewed') and not invalid)
    elif state.get('model_verification_receipt'):
        errors.append('H2 assessment requires an H2 contract binding')
        stale.add('model_verification_receipt')
    binding = state.get('model_verification_receipt')
    if binding:
        from validate_model_verification_receipt import validate_model_verification_receipt
        report = validate_model_verification_receipt(result['model_verification_receipt_path'],
            project_root=root, contract_report=result.get('model_verification_validation'))
        result['model_verification_receipt_validation'] = report
        invalid = list(report['errors']) if not report['valid'] else []
        path = Path(result['model_verification_receipt_path'])
        if not path.is_file() or sha256_file(path) != binding['sha256']:
            invalid.append('H2 receipt SHA differs from state binding')
        if not result['model_verification_reviewed']:
            invalid.append('H2 assessment requires the current reviewed contract')
        if report.get('contract_path') != result['model_verification_path'] or report.get('contract_sha256') != (state.get('model_verification') or {}).get('sha256'):
            invalid.append('H2 assessment differs from state H2 contract binding')
        invalid.extend(upstream_errors(report, state, result))
        if report.get('primary_numerical_receipt_path') != result['numerical_verification_receipt_path']:
            invalid.append('H2 assessment differs from state primary H1 receipt')
        if not result['numerically_verified']:
            invalid.append('H2 assessment requires current accepted primary H1')
        if invalid:
            errors.extend('H2 assessment: ' + error for error in invalid)
            stale.add('model_verification_receipt')
        result['model_verification_decided'] = bool(report.get('model_verification_decided') and not invalid)
        result['model_verified'] = bool(report.get('model_verified') and result['model_verification_decided'])
        result['claim_supported'] = report.get('claim_supported', False) if not invalid else False
    if state['current_stage'] in STAGES and not result['model_verification_decided']:
        errors.append('MODEL_VERIFICATION_DECIDED requires current H1 and complete required analysis decisions')
        stale.add('model_verification_receipt')
    if state['current_stage'] == 'MODEL_VERIFIED' and not result['model_verified']:
        errors.append('MODEL_VERIFIED requires support from every required analysis')
        stale.add('model_verification_receipt')


def validate_artifact(item, *, state, result, root, environment_dependents, ancestor_roles):
    role, parents = item['role'], set(item['depends_on'])
    path, invalid = contained_path(root, item['path']), []
    anchor = 'model_verification' if role == 'model_verification_contract' else 'model_verification_receipt'
    binding = state.get(anchor)
    required = {'problem', 'model', 'approval', 'mapping', 'protocol', 'primary_run',
                'numerical_verification', 'numerical_verification_receipt', 'model_verification'}
    if role == 'model_verification_evidence':
        required.add('model_verification_receipt')
    if item['id'] in environment_dependents:
        invalid.append('historical H2 evidence cannot depend on current environment readiness')
    if not required <= parents or not binding or result.get(anchor + '_path') is None or path != Path(result[anchor + '_path']) or item['sha256'] != binding['sha256']:
        invalid.append('accepted H2 evidence must match and depend on its project anchors')
    needed_roles = {'simulation_protocol', 'simulation_run', 'numerical_verification_evidence'}
    if role == 'model_verification_evidence':
        needed_roles.add('model_verification_contract')
    if not needed_roles <= ancestor_roles(item):
        invalid.append('accepted H2 evidence lacks its approved E/H1 dependency chain')
    if not result['model_verification_reviewed'] or not result['numerically_verified']:
        invalid.append('accepted H2 evidence requires current reviewed contract and primary H1')
    if role == 'model_verification_evidence' and not result['model_verification_decided']:
        invalid.append('accepted H2 disposition requires every required analysis complete; support is separate')
    return invalid
