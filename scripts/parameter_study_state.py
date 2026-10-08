"""Assess the optional B/C/F branch without writing state or approving candidates."""
from pathlib import Path

from runtime_common import contained_path, load_document, sha256_file

STAGES = {'PARAMETER_STUDY_REVIEWED', 'PARAMETER_CANDIDATE_COMPLETE'}
HISTORICAL_ROLES = {'parameter_study', 'parameter_trial', 'parameter_candidate'}
CURRENT_ROLES = {'parameter_study_profile', 'parameter_study_route_decision'}


def validate_bindings(state, root, result, errors, stale, scope, requested_profile=None):
    result.update(parameter_study_checked=False, study_reviewed=False, candidate_complete=False,
                  parameter_environment_checked=False, study_path=None, parameter_trial_path=None,
                  parameter_environment_path=None)
    for anchor in ('study','parameter_trial','parameter_environment'):
        binding = state.get(anchor)
        field = 'profile_path' if anchor == 'parameter_environment' else 'path'
        path = contained_path(root, binding[field]) if binding else None
        result[anchor + '_path'] = str(path) if path else None
    if scope == 'all' and state.get('parameter_environment'):
        from validate_parameter_study_profile import validate_parameter_study_profile
        result['parameter_environment_checked'] = True
        path = result['parameter_environment_path']
        binding = state['parameter_environment']
        study_path = result['study_path']
        selected = [load_document(Path(study_path)).get('method')] if study_path and Path(study_path).is_file() else None
        report = validate_parameter_study_profile(path, required_operations=selected)
        result['parameter_environment_validation'] = report
        if requested_profile is not None and Path(requested_profile).resolve() != Path(path):
            errors.append('requested F profile differs from state binding')
        if not report['valid'] or any(report.get(key) != binding[key] for key in ('profile_sha256','receipt_sha256')):
            errors.extend('F environment: ' + error for error in report['errors'])
            errors.append('F qualification or SHA binding is invalid')
            stale.add('parameter_environment')
    if scope not in {'all','parameter_study'}:
        return
    result['parameter_study_checked'] = True
    if state.get('study'):
        from validate_parameter_study import validate_parameter_study
        report = validate_parameter_study(result['study_path'], project_root=root,
                                         require_reviewed=state['current_stage'] in STAGES)
        result['study_validation'] = report
        invalid = list(report['errors']) if not report['valid'] else []
        if report.get('study_sha256') != state['study']['sha256'] or report.get('project_id') != state['project_id']:
            invalid.append('study differs from state project/SHA binding')
        for name in ('problem','model','approval'):
            binding = state.get(name)
            if not binding or report.get(name+'_path') != result.get(name+'_path') or report.get(name+'_sha256') != binding['sha256']:
                invalid.append('study differs from state ' + name + ' binding')
        if not result['model_approved']:
            invalid.append('study requires current bound approved C design')
        if invalid:
            errors.extend('study: ' + error for error in invalid)
            stale.add('study')
        result['study_reviewed'] = bool(report.get('reviewed') and not invalid)
    elif state.get('parameter_trial'):
        errors.append('parameter trial requires a study binding')
        stale.add('parameter_trial')
    if state.get('parameter_trial'):
        from validate_parameter_study_receipt import validate_parameter_study_receipt
        binding = state['parameter_trial']
        report = validate_parameter_study_receipt(result['parameter_trial_path'], project_root=root,
                                                 study_report=result.get('study_validation'))
        result['trial_validation'] = report
        invalid = list(report['errors']) if not report['valid'] else []
        if not report.get('candidate_complete'):
            invalid.append('actual complete candidate trial evidence required')
        path = Path(result['parameter_trial_path'])
        if not path.is_file() or sha256_file(path) != binding['sha256']:
            invalid.append('parameter trial SHA differs from state binding')
        if not result['study_reviewed']:
            invalid.append('parameter trial requires current reviewed study')
        if invalid:
            errors.extend('parameter trial: ' + error for error in invalid)
            stale.add('parameter_trial')
        result['candidate_complete'] = not invalid
    if state['current_stage'] in STAGES and not result['study_reviewed']:
        errors.append('PARAMETER_STUDY_REVIEWED requires the current complete reviewed study')
        stale.add('study')
    if state['current_stage'] == 'PARAMETER_CANDIDATE_COMPLETE' and not result['candidate_complete']:
        errors.append('PARAMETER_CANDIDATE_COMPLETE requires actual complete candidate evidence')
        stale.add('parameter_trial')


def validate_artifact(item, *, state, result, root, environment_dependents, ancestor_roles):
    role = item['role']
    invalid = []
    path = contained_path(root, item['path'])
    parents = set(item['depends_on'])
    if role in HISTORICAL_ROLES:
        if item['id'] in environment_dependents:
            invalid.append('historical F evidence cannot depend on current environment readiness')
        if not {'problem','model','approval','study'} <= parents:
            invalid.append('accepted F evidence must depend on B/C/study anchors')
        if not result['study_reviewed']:
            invalid.append('accepted F evidence requires current reviewed study')
        if role == 'parameter_study':
            binding = state.get('study')
            if not binding or path != Path(result['study_path']) or item['sha256'] != binding['sha256']:
                invalid.append('accepted study differs from its state binding')
        else:
            if 'parameter_trial' not in parents or not result['candidate_complete']:
                invalid.append('accepted candidate/trial requires actual complete bound trial')
            if 'parameter_study' not in ancestor_roles(item):
                invalid.append('accepted candidate/trial lacks study dependency chain')
            if role == 'parameter_trial':
                binding = state.get('parameter_trial')
                if not binding or path != Path(result['parameter_trial_path']) or item['sha256'] != binding['sha256']:
                    invalid.append('accepted trial differs from state binding')
            elif result['candidate_complete']:
                receipt_path = Path(result['parameter_trial_path'])
                receipt = load_document(receipt_path)
                candidates = {str((receipt_path.parent / binding['file']).resolve()):binding['sha256']
                    for name,binding in receipt.get('artifacts',{}).items()
                    if name in {'trial_data_file','trial_mat_file'} and isinstance(binding,dict)
                    and 'file' in binding and 'sha256' in binding}
                if candidates.get(str(path)) != item['sha256'] or 'parameter_trial' not in ancestor_roles(item):
                    invalid.append('accepted candidate must match validated numeric trial output and dependency chain')
    elif role == 'parameter_study_profile':
        binding = state.get('parameter_environment')
        if not binding or 'parameter_environment' not in parents or path != Path(result['parameter_environment_path']) or item['sha256'] != binding['profile_sha256'] or not result.get('parameter_environment_validation',{}).get('valid'):
            invalid.append('accepted F profile differs from current qualification binding')
    else:
        if not {'environment','parameter_environment','problem','model','approval','study'} <= parents:
            invalid.append('accepted F route lacks required execution anchors')
        else:
            from parameter_study_route import METHOD_INTENTS
            from resolve_runtime import resolve_runtime
            route = load_document(path)
            method = result.get('study_validation',{}).get('method')
            expected = resolve_runtime(METHOD_INTENTS.get(method), study_path=result['study_path'],
                profile_path=result['environment_path'], parameter_study_profile_path=result['parameter_environment_path'],
                simulation_profile_path=result.get('simulation_environment_path'), required_operations=route.get('selected_operations'))
            fields = ('intent','phase','status','execution_scope','execution_allowed','business_execution_allowed',
                'parameter_study_execution_allowed','simulation_execution_allowed','implementation_execution_allowed',
                'activated_modules','activated_resources','activated_packs','upstream_skills','selected_operations','required_gates','missing_gates',
                'profile_sha256','receipt_sha256','study_sha256','study_semantic_sha256',
                'parameter_study_profile_sha256','parameter_study_receipt_sha256','simulation_profile_sha256','simulation_receipt_sha256','state_mutated')
            if method == 'calibration.simulink_gain' and 'simulation_environment' not in parents:
                invalid.append('accepted gain route lacks E qualification anchor')
            if expected['status'] != 'allowed' or any(route.get(key) != expected.get(key) for key in fields):
                invalid.append('accepted F route differs from current method/operation qualification')
    return invalid
