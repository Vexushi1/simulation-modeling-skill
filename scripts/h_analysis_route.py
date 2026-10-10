"""Separate historical H study review from explicitly qualified native trials."""
from pathlib import Path

from numerical_verification_route import match_bindings, select_bindings
from runtime_common import ROOT, load_document

INTENTS = {'h_analysis_study', 'h_analysis_trials', 'h_analysis_trial_review',
           'h_analysis_study_review'}
NATIVE_OPERATIONS = {'simulink.core_simulation', 'h.analysis_trials'}


def required_solvers(report):
    """Every executed level/configuration must have independent E/H support."""
    policies = ([item['numerical_policy'] for item in report['settings']['configurations']]
                if report.get('method') == 'runtime_comparison' else [report.get('numerical_policy') or {}])
    solvers = []
    for policy in policies:
        levels = policy.get('solver_levels')
        if isinstance(levels, list) and levels:
            names = [item.get('name') for item in levels]
        else:
            solver = policy.get('solver')
            names = [solver.get('name') if isinstance(solver, dict) else solver]
            if names == [None]:
                names = [{'ode4_step_refinement': 'ode4', 'ode45_tolerance_refinement': 'ode45',
                          'ode15s_tolerance_refinement': 'ode15s'}.get(policy.get('method'))]
        for name in names:
            if not isinstance(name, str) or not name:
                raise ValueError('reviewed actual H levels lack an explicit solver identity')
            if name not in solvers:
                solvers.append(name)
    return solvers


def public_report(report):
    return {key: value for key, value in report.items() if not key.startswith('_')}


def baseline_report(report):
    """Use independently derived baseline reports, never hypothetical point values."""
    protocol = report.get('base_protocol_report') or {}
    numerical = report.get('primary_numerical_report') or {}
    simulation = report.get('base_simulation_report') or {}
    bindings = report.get('bindings') or {}
    result = {'project_id': report.get('project_id')}
    for name in ('problem', 'model', 'approval', 'mapping'):
        for suffix in ('path', 'sha256'):
            result[name + '_' + suffix] = report.get(name + '_' + suffix) or protocol.get(name + '_' + suffix) or numerical.get(name + '_' + suffix)
    for name, fields, fallback in (
        ('protocol', ('primary_protocol_path', 'primary_protocol_sha256'), 'base_protocol'),
        ('primary_run', ('primary_receipt_path', 'primary_receipt_sha256'), 'base_receipt'),
    ):
        binding = bindings.get(fallback) or {}
        if name == 'protocol':
            result[fields[0]] = report.get(fields[0]) or report.get('base_protocol_path') or protocol.get('contract_path') or numerical.get(fields[0]) or binding.get('path')
            result[fields[1]] = report.get(fields[1]) or report.get('base_protocol_sha256') or protocol.get('contract_sha256') or numerical.get(fields[1]) or binding.get('sha256')
        else:
            result[fields[0]] = report.get(fields[0]) or report.get('base_simulation_receipt_path') or simulation.get('receipt_path') or numerical.get(fields[0]) or binding.get('path')
            result[fields[1]] = report.get(fields[1]) or report.get('base_simulation_receipt_sha256') or simulation.get('receipt_sha256') or numerical.get(fields[1]) or binding.get('sha256')
    binding = bindings.get('primary_numerical_receipt') or {}
    result['primary_numerical_receipt_path'] = report.get('primary_numerical_receipt_path') or numerical.get('receipt_path') or binding.get('path')
    result['primary_numerical_receipt_sha256'] = report.get('primary_numerical_receipt_sha256') or numerical.get('receipt_sha256') or binding.get('sha256')
    result['model_identity'] = report.get('model_identity') or protocol.get('model_identity') or numerical.get('model_identity')
    return result


def h_analysis_route(result, *, router, resources, state_result=None, state_path=None,
                     h_analysis_study_path=None, h_analysis_trial_receipt_path=None,
                     h_analysis_study_receipt_path=None, h_analysis_profile_path=None,
                     profile_path=None, simulation_profile_path=None, expected_root=None,
                     problem_path=None, model_path=None, approval_path=None, mapping_path=None,
                     protocol_path=None, run_receipt_path=None,
                     numerical_verification_receipt_path=None, requested=()):
    context = state_result or {}
    root, intent = context.get('project_root'), result['intent']

    def block(gate, errors, key='h_analysis_study_invalid'):
        fallback = router['fallback'][key]
        result.update(status='blocked', missing_gates=[gate], errors=errors,
                      fallback=fallback, next_step=fallback['reason'])
        return result

    try:
        selected = select_bindings({'problem': problem_path, 'model': model_path,
            'approval': approval_path, 'mapping': mapping_path, 'protocol': protocol_path,
            'primary_run': run_receipt_path,
            'numerical_verification_receipt': numerical_verification_receipt_path,
            'environment': profile_path, 'simulation_environment': simulation_profile_path,
            'h_analysis_environment': h_analysis_profile_path}, context)
    except ValueError as error:
        return block('h_analysis_state_bindings_match', [str(error)])
    entries = context.get('h_analysis_studies', [])
    chosen = None
    if h_analysis_study_path is not None:
        matching = [item for item in entries if Path(item['study_path']).resolve() == Path(h_analysis_study_path).resolve()]
        chosen = matching[0] if matching else None
        if entries and chosen is None:
            return block('h_analysis_state_bindings_match', ['requested H study differs from the actual state studies'])
    elif len(entries) == 1:
        chosen = entries[0]
        h_analysis_study_path = chosen['study_path']
    if h_analysis_study_path is None:
        return block('h_analysis_study_supplied', ['supply one explicit source-bound H study'])
    if chosen and chosen.get('receipt_path'):
        if h_analysis_study_receipt_path is not None and Path(h_analysis_study_receipt_path).resolve() != Path(chosen['receipt_path']).resolve():
            return block('h_analysis_state_bindings_match', ['requested study receipt differs from its exact state binding'])
        h_analysis_study_receipt_path = h_analysis_study_receipt_path or chosen['receipt_path']
    if intent != 'h_analysis_trials' and requested:
        return block('h_review_has_no_selected_operations', ['historical H review does not select MATLAB operations'])
    from validate_h_analysis_study import validate_h_analysis_study
    report = validate_h_analysis_study(h_analysis_study_path, project_root=root,
                                     require_reviewed=intent != 'h_analysis_study')
    result.update(h_analysis_study_validation=public_report(report),
                  h_analysis_study_path=str(Path(h_analysis_study_path).resolve()),
                  h_analysis_study_sha256=report.get('contract_sha256'),
                  h_analysis_study_semantic_sha256=report.get('semantic_sha256'))
    baseline = baseline_report(report)
    errors = match_bindings(baseline, selected, state_path=state_path)
    expected_h1 = selected['numerical_verification_receipt']
    if expected_h1 is not None and baseline.get('primary_numerical_receipt_path') != str(Path(expected_h1).resolve()):
        errors.append('study differs from the original primary H1 binding')
    if not report.get('valid') or errors:
        return block('h_analysis_study_valid', list(report.get('errors', [])) + errors)
    if intent == 'h_analysis_study':
        result.update(status='inspected', execution_scope='h_analysis_study_review',
                      activated_modules=[intent], activated_resources=list(resources),
                      missing_gates=list(report.get('missing_gates', [])))
        return result
    if intent in {'h_analysis_trial_review', 'h_analysis_study_review'}:
        path = h_analysis_trial_receipt_path if intent == 'h_analysis_trial_review' else h_analysis_study_receipt_path
        if path is None:
            return block('h_analysis_receipt_supplied', ['supply the actual requested H receipt'])
        if intent == 'h_analysis_trial_review':
            from validate_h_analysis_trial_receipt import validate_h_analysis_trial_receipt
            receipt = validate_h_analysis_trial_receipt(path, project_root=root, study_report=report)
            complete = receipt.get('trial_complete') and receipt.get('numerically_verified')
            contract_path, contract_sha = receipt.get('study_path'), receipt.get('study_sha256')
        else:
            from validate_h_analysis_study_receipt import validate_h_analysis_study_receipt
            receipt = validate_h_analysis_study_receipt(path, project_root=root, study_report=report)
            complete = receipt.get('study_complete')
            contract_path, contract_sha = receipt.get('contract_path'), receipt.get('contract_sha256')
        result['h_analysis_receipt_validation'] = public_report(receipt)
        errors = []
        if contract_path != str(Path(h_analysis_study_path).resolve()) or contract_sha != report.get('contract_sha256'):
            errors.append('H receipt differs from the current exact study contract')
        if receipt.get('project_id') != report.get('project_id'):
            errors.append('H receipt differs from the study project')
        if not receipt.get('valid') or errors:
            return block('current_h_analysis_receipt', list(receipt.get('errors', [])) + errors)
        result.update(status='inspected', execution_scope=intent,
                      activated_modules=[intent], activated_resources=list(resources),
                      missing_gates=[] if complete else ['h_analysis_evidence_complete'],
                      study_complete=bool(receipt.get('study_complete')),
                      study_accepted=bool(receipt.get('study_accepted')),
                      numerically_verified=bool(receipt.get('numerically_verified')))
        return result

    if not report.get('reviewed') or not report.get('execution_ready'):
        return block('h_analysis_study_reviewed', ['current complete reviewed trial-ready study required'])
    native_authority = load_document(ROOT / 'core/h_analysis_assurance_contract.yaml')
    required = list(dict.fromkeys(native_authority['required_A_operations'] +
        list(report.get('required_A_operations', [])) + [operation for operation in requested if operation not in NATIVE_OPERATIONS]))
    if not required or any(operation in NATIVE_OPERATIONS for operation in required):
        return block('h_analysis_operation_union', ['A operation requirements must remain separate from E/H native qualifications'])
    result['selected_operations'] = list(dict.fromkeys(required + ['simulink.core_simulation', 'h.analysis_trials']))
    result['required_A_operations'] = required
    if any(selected[name] is None for name in ('environment', 'simulation_environment', 'h_analysis_environment')):
        return block('current_a_e_h_profiles', ['current independent A/E/H qualification is required'], 'h_analysis_profile_invalid')
    from validate_environment import validate_environment
    from validate_simulation_profile import validate_simulation_profile
    from validate_h_analysis_profile import validate_h_analysis_profile
    from validate_implementation_receipt import same_runtime
    try:
        solvers = required_solvers(report)
    except (KeyError, TypeError, ValueError) as error:
        return block('h_analysis_solver_union', [str(error)])
    result['required_solvers'] = solvers
    a = validate_environment(selected['environment'], required_operations=required, expected_root=expected_root)
    e = validate_simulation_profile(selected['simulation_environment'], expected_root=expected_root)
    h = validate_h_analysis_profile(selected['h_analysis_environment'], expected_root=expected_root)
    result.update(environment_validation=a, simulation_environment_validation=e,
                  h_analysis_environment_validation=h)
    if not (a.get('valid') and a.get('runtime_assured') and a.get('profile_current') and
            e.get('valid') and e.get('simulation_assured') and e.get('profile_current') and
            h.get('valid') and h.get('h_analysis_assured') and h.get('profile_current') and
            'h.analysis_trials' in h.get('qualified_operations', [])):
        return block('current_a_e_h_qualified', list(a.get('errors', [])) + list(e.get('errors', [])) + list(h.get('errors', [])), 'h_analysis_profile_invalid')
    missing = {'E': [name for name in solvers if name not in e.get('qualified_solvers', [])],
               'H': [name for name in solvers if name not in h.get('qualified_solvers', [])]}
    if any(missing.values()):
        return block('h_analysis_solver_union', [label + ' lacks actual required solver qualification: ' + ', '.join(names)
                     for label, names in missing.items() if names], 'h_analysis_profile_invalid')
    runtime = load_document(Path(selected['environment']))['runtime']
    host = load_document(Path(selected['environment']))['execution']['host_fingerprint']
    e_host = load_document(Path(selected['simulation_environment']))['execution']['host_fingerprint']
    if not same_runtime(runtime, e['runtime']) or not same_runtime(runtime, h['runtime']) or host != e_host or host != h.get('host_fingerprint'):
        return block('h_analysis_runtime_matches', ['A/E/H host or actual runtime identities differ'], 'h_analysis_profile_invalid')
    if state_path:
        state = load_document(Path(state_path))
        for name, validation in (('environment', a), ('simulation_environment', e), ('h_analysis_environment', h)):
            binding = state.get(name)
            if binding and any(binding[key] != validation.get(key) for key in ('profile_sha256', 'receipt_sha256')):
                return block('h_analysis_state_bindings_match', [name + ' qualification SHA differs from state'])
    result.update(status='allowed', missing_gates=[], execution_scope='h_analysis_trials',
                  execution_allowed=True, business_execution_allowed=True, h_analysis_execution_allowed=True,
                  activated_modules=[intent], activated_resources=list(resources),
                  profile_sha256=a['profile_sha256'], receipt_sha256=a['receipt_sha256'],
                  simulation_profile_sha256=e['profile_sha256'], simulation_receipt_sha256=e['receipt_sha256'],
                  h_analysis_profile_path=str(Path(selected['h_analysis_environment']).resolve()),
                  h_analysis_profile_sha256=h['profile_sha256'], h_analysis_receipt_sha256=h['receipt_sha256'])
    return result
