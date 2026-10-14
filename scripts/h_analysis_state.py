"""Optional multi-study H history and separate current trial qualification."""
from pathlib import Path

from h_analysis_route import baseline_report, public_report
from numerical_verification_state import upstream_errors
from runtime_common import contained_path, load_document, sha256_file

SCOPES = {'all', 'h_analysis_study', 'model_verification'}
HISTORICAL_ROLES = {'h_analysis_study', 'h_analysis_study_evidence', 'h_analysis_trial'}
CURRENT_ROLES = {'h_analysis_profile', 'h_analysis_route_decision'}


def baseline_errors(report, state, result):
    baseline = baseline_report(report)
    errors = upstream_errors(baseline, state, result)
    for anchor in ('problem', 'model', 'approval', 'mapping'):
        if baseline.get(anchor + '_path') is None:
            errors.append('complete H study lacks its baseline ' + anchor + ' identity')
    path = baseline.get('primary_numerical_receipt_path')
    binding = state.get('numerical_verification_receipt')
    if not path or not binding or path != result.get('numerical_verification_receipt_path'):
        errors.append('study differs from the original state primary H1 receipt')
    elif (baseline.get('primary_numerical_receipt_sha256') or sha256_file(Path(path))) != binding['sha256']:
        errors.append('study primary H1 SHA differs from state')
    if not result.get('numerically_verified'):
        errors.append('H study requires current accepted primary H1 evidence')
    return errors


def validate_bindings(state, root, result, errors, stale, scope, requested_profile=None):
    result.update(h_analysis_checked=False, h_analysis_environment_checked=False,
                  h_analysis_environment_path=None, h_analysis_studies=[])
    binding = state.get('h_analysis_environment')
    path = contained_path(root, binding['profile_path']) if binding else None
    result['h_analysis_environment_path'] = str(path) if path else None
    if scope == 'all' and binding:
        from validate_h_analysis_profile import validate_h_analysis_profile
        result['h_analysis_environment_checked'] = True
        report = validate_h_analysis_profile(path)
        result['h_analysis_environment_validation'] = report
        invalid = list(report.get('errors', [])) if not report.get('valid') else []
        if requested_profile is not None and Path(requested_profile).resolve() != path:
            invalid.append('requested H profile differs from state')
        if not report.get('profile_current') or not report.get('h_analysis_assured') or any(report.get(key) != binding[key] for key in ('profile_sha256', 'receipt_sha256')):
            invalid.append('current H trial qualification or exact SHA binding is invalid')
        if invalid:
            errors.extend('H environment: ' + message for message in invalid)
            stale.add('h_analysis_environment')
    entries = state.get('h_analysis_studies', [])
    identities, study_paths, receipt_paths = set(), set(), set()
    for entry in entries:
        study = contained_path(root, entry['study']['path'])
        receipt = contained_path(root, entry['receipt']['path']) if entry.get('receipt') else None
        if entry['id'] in identities or study in study_paths or receipt is not None and receipt in receipt_paths:
            errors.append('H state study IDs/contracts/receipts must be unique')
            stale.add('h_analysis_studies')
        identities.add(entry['id'])
        study_paths.add(study)
        if receipt is not None:
            receipt_paths.add(receipt)
        result['h_analysis_studies'].append({'id': entry['id'], 'study_path': str(study),
            'study_sha256': entry['study']['sha256'], 'receipt_path': str(receipt) if receipt else None,
            'receipt_sha256': entry['receipt']['sha256'] if receipt else None,
            'reviewed': False, 'study_complete': False, 'study_accepted': False, 'defined': False})
    if scope not in SCOPES:
        return
    result['h_analysis_checked'] = True
    for entry, current in zip(entries, result['h_analysis_studies']):
        from validate_h_analysis_study import validate_h_analysis_study
        report = validate_h_analysis_study(current['study_path'], project_root=root,
                                         require_reviewed=bool(entry.get('receipt')))
        current['study_validation'] = public_report(report)
        invalid = list(report.get('errors', [])) if not report.get('valid') else []
        if report.get('contract_sha256') != current['study_sha256'] or report.get('project_id') != state['project_id']:
            invalid.append('H study contract differs from state project/SHA binding')
        if report.get('reviewed'):
            invalid.extend(baseline_errors(report, state, result))
        current['reviewed'] = bool(report.get('reviewed') and not invalid)
        if entry.get('receipt'):
            from validate_h_analysis_study_receipt import validate_h_analysis_study_receipt
            receipt = validate_h_analysis_study_receipt(current['receipt_path'], project_root=root, study_report=report)
            current['receipt_validation'] = public_report(receipt)
            if not receipt.get('valid'):
                invalid.extend(receipt.get('errors', []))
                invalid.append('current independently checked H study receipt required')
            if (receipt.get('contract_path') != current['study_path'] or receipt.get('contract_sha256') != current['study_sha256'] or
                    receipt.get('project_id') != state['project_id'] or receipt.get('receipt_sha256') != current['receipt_sha256']):
                invalid.append('H study receipt differs from exact state contract/project/receipt SHA')
            if not current['reviewed']:
                invalid.append('H study receipt requires the current reviewed contract')
            if not receipt.get('study_complete'):
                invalid.append('H study state receipt requires the complete realized trial evidence')
            current['study_complete'] = bool(receipt.get('study_complete') and not invalid)
            current['study_accepted'] = bool(receipt.get('study_accepted') and current['study_complete'])
            current['defined'] = bool(receipt.get('defined') and current['study_complete'])
        if invalid:
            errors.extend('H study ' + entry['id'] + ': ' + message for message in invalid)
            stale.add('h_analysis_studies')


def ancestor_items(item, state):
    by_id = {entry['id']: entry for entry in state['artefacts']}
    pending, seen, found = list(item['depends_on']), set(), []
    while pending:
        identity = pending.pop()
        if identity in seen or identity not in by_id:
            continue
        seen.add(identity)
        found.append(by_id[identity])
        pending.extend(by_id[identity]['depends_on'])
    return found


def validate_artifact(item, *, state, result, root, environment_dependents, ancestor_roles):
    role, parents = item['role'], set(item['depends_on'])
    path, invalid = contained_path(root, item['path']), []
    if role in HISTORICAL_ROLES:
        required = {'problem', 'model', 'approval', 'mapping', 'protocol', 'primary_run',
                    'numerical_verification', 'numerical_verification_receipt', 'h_analysis_studies'}
        if item['id'] in environment_dependents:
            invalid.append('historical H study evidence cannot depend on current environment readiness')
        if not required <= parents or not result.get('numerically_verified'):
            invalid.append('accepted H study evidence lacks its exact original B/C/D/E/H1 anchors')
        if not {'simulation_protocol', 'simulation_run', 'numerical_verification_evidence'} <= ancestor_roles(item):
            invalid.append('accepted H study evidence lacks the original E/H1 accepted chain')
        candidates = result.get('h_analysis_studies', [])
        if role == 'h_analysis_study':
            matching = [entry for entry in candidates if entry['study_path'] == str(path) and entry['study_sha256'] == item['sha256']]
            if len(matching) != 1 or not matching[0]['reviewed']:
                invalid.append('accepted H study contract must match one current reviewed state study')
        elif role == 'h_analysis_study_evidence':
            matching = [entry for entry in candidates if entry['receipt_path'] == str(path) and entry['receipt_sha256'] == item['sha256']]
            if len(matching) != 1 or not matching[0]['study_complete'] or not matching[0]['defined']:
                invalid.append('accepted H study evidence requires complete defined numerical analysis')
            elif not any(parent['status'] == 'accepted' and parent['role'] == 'h_analysis_study' and
                         contained_path(root, parent['path']) == Path(matching[0]['study_path']) and parent['sha256'] == matching[0]['study_sha256']
                         for parent in ancestor_items(item, state)):
                invalid.append('accepted H study evidence lacks its exact accepted study contract ancestor')
        else:
            from validate_h_analysis_trial_receipt import validate_h_analysis_trial_receipt
            report = validate_h_analysis_trial_receipt(path, project_root=root)
            if not report.get('valid') or not report.get('trial_complete') or not report.get('numerically_verified') or report.get('receipt_sha256') != item['sha256']:
                invalid.append('accepted H trial requires independently accepted complete three-level numerical evidence')
            matching = [entry for entry in candidates if entry['study_path'] == report.get('study_path') and entry['study_sha256'] == report.get('study_sha256') and entry['reviewed']]
            if len(matching) != 1:
                invalid.append('accepted H trial differs from every reviewed state study')
            else:
                invalid.extend(baseline_errors(matching[0]['study_validation'], state, result))
    elif role == 'h_analysis_profile':
        binding = state.get('h_analysis_environment')
        if (not binding or 'h_analysis_environment' not in parents or path != Path(result['h_analysis_environment_path']) or
                item['sha256'] != binding['profile_sha256'] or not result.get('h_analysis_environment_validation', {}).get('valid')):
            invalid.append('accepted H profile differs from current state qualification')
    else:
        from resolve_runtime import resolve_runtime
        route = load_document(path)
        required = {'environment', 'simulation_environment', 'h_analysis_environment', 'h_analysis_studies'}
        if not required <= parents:
            invalid.append('accepted H execution route lacks current qualification/study anchors')
        expected = resolve_runtime('h_analysis_trials', project_root=root,
            h_analysis_study_path=route.get('h_analysis_study_path'),
            profile_path=result.get('environment_path'), simulation_profile_path=result.get('simulation_environment_path'),
            h_analysis_profile_path=result.get('h_analysis_environment_path'), required_operations=route.get('selected_operations'))
        fields = ('intent', 'status', 'execution_scope', 'execution_allowed', 'business_execution_allowed',
                  'h_analysis_execution_allowed', 'state_mutated', 'selected_operations', 'missing_gates',
                  'h_analysis_study_sha256', 'h_analysis_study_semantic_sha256', 'profile_sha256', 'receipt_sha256',
                  'simulation_profile_sha256', 'simulation_receipt_sha256', 'h_analysis_profile_sha256', 'h_analysis_receipt_sha256')
        if not expected.get('h_analysis_execution_allowed') or any(route.get(key) != expected.get(key) for key in fields):
            invalid.append('accepted H execution route differs from an independently rederived current gate')
    return invalid
