"""Read-only routing for reviewed, separately qualified frozen-E campaigns."""
from pathlib import Path

from runtime_common import load_document
from run_experiment import METHODS, OPERATIONS, required_a_operations


def experiment_route(result, *, router, resources, state_result=None, state_path=None,
                     design_path=None, mapping_path=None, problem_path=None, model_path=None, approval_path=None,
                     profile_path=None, simulation_profile_path=None, experiment_profile_path=None,
                     campaign_receipt_path=None, requested=(), expected_root=None):
    state_result = state_result or {}
    intent, root = result['intent'], state_result.get('project_root')

    def block(gate, errors, key='experiment_design_invalid'):
        fallback = router['fallback'][key]
        result.update(status='blocked', missing_gates=[gate], errors=errors,
                      fallback=fallback, next_step=fallback['reason'])
        return result

    selected = {}
    for supplied, name in ((design_path, 'experiment_design'), (mapping_path, 'mapping'), (problem_path, 'problem'),
                          (model_path, 'model'), (approval_path, 'approval'),
                          (profile_path, 'environment'), (simulation_profile_path, 'simulation_environment'),
                          (experiment_profile_path, 'experiment_environment'), (campaign_receipt_path, 'campaign')):
        bound = state_result.get(name + '_path')
        if bound and supplied is not None and Path(supplied).resolve() != Path(bound).resolve():
            return block(name + '_state_binding_matches', [f'requested {name} differs from state binding'])
        selected[name] = supplied if supplied is not None else bound
    if selected['experiment_design'] is None:
        return block('experiment_design_supplied', ['supply the current source-bound finite experiment design'])
    from validate_experiment_design import validate_experiment_design
    design = validate_experiment_design(selected['experiment_design'], project_root=root,
                                         require_reviewed=intent != 'experiment_design')
    result.update(experiment_design_validation=design,
                  design_path=str(Path(selected['experiment_design']).resolve()),
                  design_sha256=design.get('design_sha256'), design_semantic_sha256=design.get('semantic_sha256'))
    if not design['valid']:
        return block('experiment_design_valid', design['errors'])
    if state_path and design['project_id'] != load_document(Path(state_path))['project_id']:
        return block('project_id_matches', ['experiment design differs from project state'])
    for name in ('mapping', 'problem', 'model', 'approval'):
        if selected[name] is not None:
            bound = design.get(name + '_path')
            if bound is not None and Path(bound).resolve() != Path(selected[name]).resolve():
                return block(name + '_design_binding_matches', [f'design differs from requested {name} binding'])
            for member in design['catalog']:
                protocol = member.get('protocol_report')
                if protocol is None:
                    if intent != 'experiment_design':
                        return block('current_frozen_E_catalog', ['each campaign member needs its complete frozen E report'])
                    continue
                bound = protocol.get(name + '_path')
                if bound is not None and Path(bound).resolve() != Path(selected[name]).resolve():
                    return block(name + '_design_binding_matches', [f'catalog differs from requested {name} binding'])
                if bound is None and intent != 'experiment_design':
                    return block(name + '_design_binding_matches', [f'complete catalog member has no {name} binding'])
    if intent == 'experiment_design':
        result.update(status='inspected', execution_scope='experiment_design_review',
                      activated_modules=[intent], activated_resources=list(resources),
                      missing_gates=list(design['missing_gates']))
        return result
    if not design.get('design_ready') or not design.get('reviewed') or not design.get('campaign_execution_ready'):
        return block('experiment_design_reviewed', ['current complete reviewed experiment design required'])
    if not design['catalog'] or any(not member.get('protocol_report') or
            not member['protocol_report'].get('frozen') or not member['protocol_report'].get('execution_ready')
            for member in design['catalog']):
        return block('current_frozen_E_catalog', ['every campaign member needs its complete current frozen E report'])
    if intent == 'campaign_review':
        if selected['campaign'] is None:
            return block('current_campaign_receipt', ['supply the actual campaign receipt'])
        from validate_experiment_receipt import validate_experiment_receipt
        campaign = validate_experiment_receipt(selected['campaign'], project_root=root, design_report=design)
        result['campaign_validation'] = campaign
        if not campaign['valid'] or not campaign['campaign_complete']:
            return block('current_campaign_receipt', campaign['errors'])
        result.update(status='inspected', execution_scope='campaign_review',
                      activated_modules=[intent], activated_resources=list(resources), missing_gates=[])
        return result
    if intent != 'experiment_campaign' or design['method'] not in METHODS:
        return block('experiment_method_supported', ['this route grants only the reviewed finite serial campaign'])
    try:
        operations = required_a_operations(design, list(requested))
    except (ValueError, KeyError, TypeError) as error:
        return block('required_operations_match_method', [str(error)])
    operation = 'experiment.sample_plan.' + design['method']
    result['selected_operations'] = operations + ['simulink.core_simulation', operation]
    if any(selected[name] is None for name in ('environment', 'simulation_environment', 'experiment_environment')):
        return block('current_a_e_g_profiles', ['current independent A/E/G profiles are required'], 'experiment_profile_invalid')
    from validate_environment import validate_environment
    from validate_simulation_profile import validate_simulation_profile
    from validate_experiment_profile import validate_experiment_profile
    from validate_implementation_receipt import same_runtime
    a = validate_environment(selected['environment'], required_operations=operations, expected_root=expected_root)
    e = validate_simulation_profile(selected['simulation_environment'], required_solver='ode4', expected_root=expected_root)
    g = validate_experiment_profile(selected['experiment_environment'], required_method=design['method'])
    result.update(environment_validation=a, simulation_environment_validation=e, experiment_environment_validation=g)
    if not a['valid'] or not a['runtime_assured'] or not a['profile_current']:
        return block('required_operations_qualified', a['errors'], 'experiment_profile_invalid')
    if not e['valid'] or not e['simulation_assured'] or not e['profile_current']:
        return block('requested_solver_qualified', e['errors'], 'experiment_profile_invalid')
    if not g['valid'] or not g['sampling_assured'] or design['method'] not in g['qualified_methods']:
        return block('sample_plan_qualified', g['errors'], 'experiment_profile_invalid')
    runtime = load_document(Path(selected['environment']))['runtime']
    if not same_runtime(runtime, e['runtime']) or not same_runtime(runtime, g['runtime']):
        return block('experiment_runtime_matches', ['A/E/G runtime identities differ'], 'experiment_profile_invalid')
    for member in design['catalog']:
        protocol = member['protocol_report']
        if protocol['run_spec']['solver']['name'] != 'ode4' or not same_runtime(load_document(protocol['implementation_receipt_path'])['runtime'], runtime):
            return block('experiment_runtime_matches', ['each frozen E member needs ode4 and its same-runtime historical D'], 'experiment_profile_invalid')
    for name, report in (('environment', a), ('simulation_environment', e), ('experiment_environment', g)):
        binding = load_document(Path(state_path)).get(name) if state_path else None
        if binding and any(binding[key] != report.get(key) for key in ('profile_sha256', 'receipt_sha256')):
            return block(name + '_state_binding_matches', [f'{name} profile/receipt SHA differs from state'])
    result.update(status='allowed', missing_gates=[], execution_scope='experiment_campaign',
                  execution_allowed=True, business_execution_allowed=True, experiment_execution_allowed=True,
                  activated_modules=[intent], activated_resources=list(resources),
                  profile_sha256=a['profile_sha256'], receipt_sha256=a['receipt_sha256'],
                  simulation_profile_path=str(Path(selected['simulation_environment']).resolve()),
                  simulation_profile_sha256=e['profile_sha256'], simulation_receipt_sha256=e['receipt_sha256'],
                  experiment_profile_path=str(Path(selected['experiment_environment']).resolve()),
                  experiment_profile_sha256=g['profile_sha256'], experiment_receipt_sha256=g['receipt_sha256'])
    return result
