"""Read-only routing for reviewed, independently qualified parameter trials."""
from pathlib import Path

from runtime_common import load_contract, load_document

METHOD_INTENTS = {'identification.arx_111': 'parameter_identification', 'calibration.simulink_gain': 'calibration',
                  'optimization.quadratic_sqp': 'optimization'}
OPERATIONS = {'identification.arx_111', 'calibration.simulink_gain', 'optimization.quadratic_sqp'}


def parameter_study_route(result, *, router, resources, state_result=None, state_path=None,
                          study_path=None, problem_path=None, model_path=None, approval_path=None,
                          profile_path=None, parameter_study_profile_path=None,
                          simulation_profile_path=None, parameter_trial_receipt_path=None,
                          requested=(), expected_root=None):
    state_result = state_result or {}
    intent = result['intent']
    root = state_result.get('project_root')

    def block(gate, errors, key='parameter_study_invalid'):
        fallback = router['fallback'][key]
        result.update(status='blocked', missing_gates=[gate], errors=errors,
                      fallback=fallback, next_step=fallback['reason'])
        return result

    selected = {}
    for supplied, name in ((study_path,'study'), (problem_path,'problem'), (model_path,'model'),
                          (approval_path,'approval'), (profile_path,'environment'),
                          (parameter_study_profile_path,'parameter_environment'),
                          (simulation_profile_path,'simulation_environment'),
                          (parameter_trial_receipt_path,'parameter_trial')):
        bound = state_result.get(name + '_path')
        if bound and supplied is not None and Path(supplied).resolve() != Path(bound).resolve():
            return block(name + '_state_binding_matches', [f'requested {name} differs from state binding'])
        selected[name] = supplied if supplied is not None else bound

    if selected['study'] is None:
        if intent != 'parameter_study' or selected['model'] is None:
            return block('parameter_study_supplied', ['supply the current study; drafting requires an approved model'])
        from validate_model_contract import validate_model_contract
        report = validate_model_contract(selected['model'], project_root=root,
            problem_path=selected['problem'], approval_path=selected['approval'], require_approved=True)
        result['model_validation'] = report
        if not report['valid'] or not report['approved']:
            return block('model_design_approved', report['errors'])
        if state_path and report['project_id'] != load_document(Path(state_path))['project_id']:
            return block('project_id_matches', ['model differs from project state'])
        result.update(status='allowed', execution_scope='parameter_study_review',
                      activated_modules=[intent], activated_resources=list(resources),
                      missing_gates=['parameter_study_supplied','parameter_study_reviewed'])
        return result

    from validate_parameter_study import validate_parameter_study
    study = validate_parameter_study(selected['study'], project_root=root,
                                    require_reviewed=intent != 'parameter_study')
    result.update(study_validation=study, study_path=str(Path(selected['study']).resolve()),
                  study_sha256=study.get('study_sha256'), study_semantic_sha256=study.get('semantic_sha256'))
    if not study['valid']:
        return block('parameter_study_valid', study['errors'])
    for name in ('problem','model','approval'):
        bound = study.get(name + '_path')
        if selected[name] is not None and (not bound or Path(selected[name]).resolve() != Path(bound).resolve()):
            return block(name + '_study_binding_matches', [f'requested {name} differs from study binding'])
    if state_path and study['project_id'] != load_document(Path(state_path))['project_id']:
        return block('project_id_matches', ['study differs from project state'])
    if intent == 'parameter_study':
        result.update(status='inspected', execution_scope='parameter_study_review',
                      activated_modules=[intent], activated_resources=list(resources),
                      missing_gates=list(study['missing_gates']))
        return result
    if not study.get('reviewed') or not study.get('trial_execution_ready'):
        return block('parameter_study_reviewed', ['current complete reviewed study is required'])
    if intent == 'parameter_candidate_review':
        if selected['parameter_trial'] is None:
            return block('current_parameter_trial_receipt', ['supply the actual candidate trial receipt'])
        from validate_parameter_study_receipt import validate_parameter_study_receipt
        report = validate_parameter_study_receipt(selected['parameter_trial'], project_root=root, study_report=study)
        result['trial_validation'] = report
        if not report['valid'] or not report.get('candidate_complete'):
            return block('current_parameter_trial_receipt', report['errors'] or ['complete candidate evidence required'])
        result.update(status='inspected', execution_scope='parameter_candidate_review',
                      activated_modules=[intent], activated_resources=list(resources), missing_gates=[])
        return result
    if METHOD_INTENTS.get(study['method']) != intent:
        return block('method_matches_intent', ['requested intent differs from the reviewed study method'])
    operation = study['operation_id']
    if set(requested) & (OPERATIONS - {operation}):
        return block('required_operations_match_method', ['qualification for another F method does not authorize this study'])

    from validate_environment import validate_environment
    from validate_parameter_study_profile import validate_parameter_study_profile
    from validate_implementation_receipt import same_runtime
    operations = list(dict.fromkeys(load_contract('core/runtime_assurance_contract.yaml')['core_operations'] +
        study['required_A_operations'] + [op for op in requested if op not in OPERATIONS]))
    result['selected_operations'] = operations + [operation]
    if selected['environment'] is None or selected['parameter_environment'] is None:
        return block('current_a_and_f_profiles', ['current independent A/F profiles are required'], 'parameter_study_profile_invalid')
    a = validate_environment(selected['environment'], required_operations=operations, expected_root=expected_root)
    f = validate_parameter_study_profile(selected['parameter_environment'], required_operations=[operation], expected_root=expected_root)
    result.update(environment_validation=a, parameter_study_environment_validation=f)
    if not a['valid'] or not a['profile_current'] or not a['runtime_assured']:
        return block('required_operations_qualified', a['errors'], 'parameter_study_profile_invalid')
    if not f['valid'] or not f['profile_current'] or operation not in f['qualified_operations']:
        return block('parameter_study_operation_qualified', f['errors'], 'parameter_study_profile_invalid')
    if not same_runtime(load_document(Path(selected['environment']))['runtime'], f['runtime']):
        return block('parameter_study_runtime_matches', ['A/F runtime identities differ'], 'parameter_study_profile_invalid')
    if study['method'] == 'calibration.simulink_gain':
        from validate_simulation_profile import validate_simulation_profile
        if selected['simulation_environment'] is None:
            return block('current_e_ode4_profile', ['gain calibration requires independent current E ode4 qualification'], 'parameter_study_profile_invalid')
        e = validate_simulation_profile(selected['simulation_environment'], required_solver='ode4', expected_root=expected_root)
        result['simulation_environment_validation'] = e
        if not e['valid'] or not e['profile_current'] or not e['simulation_assured']:
            return block('current_e_ode4_profile', e['errors'], 'parameter_study_profile_invalid')
        if not same_runtime(e['runtime'], f['runtime']):
            return block('parameter_study_runtime_matches', ['E/F runtime identities differ'], 'parameter_study_profile_invalid')
        binding = load_document(Path(state_path)).get('simulation_environment') if state_path else None
        if binding and any(binding[key] != e.get(key) for key in ('profile_sha256','receipt_sha256')):
            return block('simulation_environment_state_binding_matches', ['E profile or receipt SHA differs from state'])
        result.update(simulation_profile_sha256=e['profile_sha256'], simulation_receipt_sha256=e['receipt_sha256'])
    for name, report in (('environment',a), ('parameter_environment',f)):
        binding = load_document(Path(state_path)).get(name) if state_path else None
        if binding and any(binding[key] != report.get(key) for key in ('profile_sha256','receipt_sha256')):
            return block(name + '_state_binding_matches', [f'{name} SHA differs from state'])
    result.update(status='allowed', missing_gates=[], execution_scope='parameter_trial',
        execution_allowed=True, business_execution_allowed=True, parameter_study_execution_allowed=True,
        activated_modules=[intent], activated_resources=list(resources),
        activated_packs=[f'packs/task/{intent}.md'],
        profile_sha256=a['profile_sha256'], receipt_sha256=a['receipt_sha256'],
        parameter_study_profile_path=str(Path(selected['parameter_environment']).resolve()),
        parameter_study_profile_sha256=f['profile_sha256'], parameter_study_receipt_sha256=f['receipt_sha256'])
    return result
