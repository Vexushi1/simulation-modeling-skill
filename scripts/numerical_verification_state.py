"""Read-only H1 state and accepted historical evidence bindings."""
from pathlib import Path

from runtime_common import contained_path, sha256_file

STAGES = {'NUMERICALLY_VERIFIED', 'MODEL_VERIFICATION_DECIDED', 'MODEL_VERIFIED'}
SCOPES = {'all', 'numerical_verification', 'model_verification'}
HISTORICAL_ROLES = {'numerical_verification_contract', 'numerical_verification_evidence'}


def upstream_errors(report, state, result):
    errors = []
    if report.get('project_id') != state['project_id']:
        errors.append('verification project differs from project state')
    for anchor in ('problem', 'model', 'approval', 'mapping', 'protocol', 'primary_run'):
        path_field = {'protocol': 'primary_protocol_path', 'primary_run': 'primary_receipt_path'}.get(anchor, anchor + '_path')
        sha_field = {'protocol': 'primary_protocol_sha256', 'primary_run': 'primary_receipt_sha256'}.get(anchor, anchor + '_sha256')
        actual = report.get(path_field)
        digest = report.get(sha_field)
        # The complete H consumer validates its closure; the baseline still must
        # coincide with the project's independently bound E and approved model.
        if actual is None:
            if anchor in {'protocol', 'primary_run'}:
                errors.append('complete verification lacks baseline ' + anchor + ' path')
            continue
        binding = state.get(anchor)
        expected_path = result.get(anchor + '_path')
        if not binding or expected_path is None or Path(actual).resolve() != Path(expected_path).resolve():
            errors.append('verification differs from state ' + anchor + ' binding')
        elif (digest if digest is not None else sha256_file(Path(actual))) != binding['sha256']:
            errors.append('verification differs from state ' + anchor + ' SHA binding')
    return errors


def validate_bindings(state, root, result, errors, stale, scope):
    result.update(numerical_verification_checked=False, numerical_verification_reviewed=False,
                  numerically_verified=False, numerical_verification_path=None,
                  numerical_verification_receipt_path=None)
    for anchor in ('numerical_verification', 'numerical_verification_receipt'):
        binding = state.get(anchor)
        path = contained_path(root, binding['path']) if binding else None
        result[anchor + '_path'] = str(path) if path else None
    if scope not in SCOPES:
        return
    result['numerical_verification_checked'] = True
    binding = state.get('numerical_verification')
    if binding:
        from validate_numerical_verification import validate_numerical_verification
        report = validate_numerical_verification(result['numerical_verification_path'],
            project_root=root, require_reviewed=state['current_stage'] in STAGES or bool(state.get('numerical_verification_receipt')))
        result['numerical_verification_validation'] = report
        invalid = list(report['errors']) if not report['valid'] else []
        if report.get('contract_sha256') != binding['sha256'] or report.get('project_id') != state['project_id']:
            invalid.append('H1 contract differs from state project/SHA binding')
        if report.get('reviewed'):
            # A reviewed contract's E prerequisite is verified by its consumer.
            # Receipt/acceptance below additionally binds the state's primary run.
            for anchor in ('problem', 'model', 'approval', 'mapping'):
                actual = report.get(anchor + '_path')
                if actual is not None and (not state.get(anchor) or actual != result.get(anchor + '_path') or report.get(anchor + '_sha256') != state[anchor]['sha256']):
                    invalid.append('H1 contract differs from state ' + anchor + ' binding')
            if report.get('primary_protocol_path') != result.get('protocol_path'):
                invalid.append('H1 contract differs from state baseline protocol')
        if invalid:
            errors.extend('H1 contract: ' + error for error in invalid)
            stale.add('numerical_verification')
        result['numerical_verification_reviewed'] = bool(report.get('reviewed') and not invalid)
    elif state.get('numerical_verification_receipt'):
        errors.append('H1 assessment requires an H1 contract binding')
        stale.add('numerical_verification_receipt')
    binding = state.get('numerical_verification_receipt')
    if binding:
        from validate_numerical_verification_receipt import validate_numerical_verification_receipt
        report = validate_numerical_verification_receipt(result['numerical_verification_receipt_path'],
            project_root=root, contract_report=result.get('numerical_verification_validation'))
        result['numerical_verification_receipt_validation'] = report
        invalid = list(report['errors']) if not report['valid'] else []
        path = Path(result['numerical_verification_receipt_path'])
        if not path.is_file() or sha256_file(path) != binding['sha256']:
            invalid.append('H1 receipt SHA differs from state binding')
        if not result['numerical_verification_reviewed']:
            invalid.append('H1 assessment requires the current reviewed contract')
        if report.get('contract_path') != result['numerical_verification_path'] or report.get('contract_sha256') != (state.get('numerical_verification') or {}).get('sha256'):
            invalid.append('H1 assessment differs from state H1 contract binding')
        invalid.extend(upstream_errors(report, state, result))
        if not result['primary_run_complete']:
            invalid.append('H1 assessment requires the current bound complete primary E run')
        if invalid:
            errors.extend('H1 assessment: ' + error for error in invalid)
            stale.add('numerical_verification_receipt')
        result['numerically_verified'] = bool(report.get('numerically_verified') and not invalid)
    if state['current_stage'] in STAGES and not result['numerically_verified']:
        errors.append('NUMERICALLY_VERIFIED requires current complete accepted H1 evidence')
        stale.add('numerical_verification_receipt')


def validate_artifact(item, *, state, result, root, environment_dependents, ancestor_roles):
    role, parents = item['role'], set(item['depends_on'])
    path, invalid = contained_path(root, item['path']), []
    anchor = 'numerical_verification' if role == 'numerical_verification_contract' else 'numerical_verification_receipt'
    binding = state.get(anchor)
    required = {'problem', 'model', 'approval', 'mapping', 'protocol', 'numerical_verification'}
    if role == 'numerical_verification_evidence':
        required |= {'primary_run', 'numerical_verification_receipt'}
    if item['id'] in environment_dependents:
        invalid.append('historical H1 evidence cannot depend on current environment readiness')
    if not required <= parents or not binding or result.get(anchor + '_path') is None or path != Path(result[anchor + '_path']) or item['sha256'] != binding['sha256']:
        invalid.append('accepted H1 evidence must match and depend on its project anchors')
    needed_roles = {'simulation_protocol', 'mapping_contract', 'parameter_provenance', 'structure_evidence'}
    if role == 'numerical_verification_evidence':
        needed_roles |= {'simulation_run', 'numerical_verification_contract'}
    if not needed_roles <= ancestor_roles(item):
        invalid.append('accepted H1 evidence lacks its approved implementation/protocol/run dependency chain')
    if not result['numerical_verification_reviewed']:
        invalid.append('accepted H1 evidence requires a current reviewed contract')
    if role == 'numerical_verification_evidence' and not result['numerically_verified']:
        invalid.append('accepted H1 assessment requires all declared numerical acceptance checks')
    return invalid
