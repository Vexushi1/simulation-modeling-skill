"""Read-only Phase E routing with exact project and operation bindings."""
from pathlib import Path

from runtime_common import load_contract, load_document

OPERATION = 'simulink.core_simulation'


def simulation_route(result, *, router, resources, state_result=None, state_path=None,
                     protocol_path=None, mapping_path=None, problem_path=None,
                     model_path=None, approval_path=None, profile_path=None,
                     simulation_profile_path=None, run_receipt_path=None,
                     requested=(), expected_root=None):
    intent = result['intent']
    state_result = state_result or {}
    project_root = state_result.get('project_root')

    def block(gate, errors, key='simulation_protocol_invalid'):
        fallback = router['fallback'][key]
        result.update(status='blocked', missing_gates=[gate], errors=errors,
                      fallback=fallback, next_step=fallback['reason'])
        return result

    selected = {}
    for supplied, label in ((protocol_path, 'protocol'), (mapping_path, 'mapping'),
                            (problem_path, 'problem'), (model_path, 'model'),
                            (approval_path, 'approval'), (profile_path, 'environment'),
                            (simulation_profile_path, 'simulation_environment'),
                            (run_receipt_path, 'primary_run')):
        bound = state_result.get(label + '_path')
        if bound and supplied is not None and Path(supplied).resolve() != Path(bound).resolve():
            return block(label + '_state_binding_matches', [f'requested {label} differs from project-state binding'])
        selected[label] = supplied if supplied is not None else bound

    from validate_simulation_protocol import validate_simulation_protocol
    protocol = None
    if selected['protocol'] is not None:
        protocol = validate_simulation_protocol(selected['protocol'], project_root=project_root,
                                               require_frozen=intent != 'simulation_protocol')
        result.update(protocol_validation=protocol,
                      protocol_path=str(Path(selected['protocol']).resolve()),
                      protocol_sha256=protocol['contract_sha256'],
                      protocol_semantic_sha256=protocol.get('semantic_sha256'))
        if not protocol['valid']:
            return block('simulation_protocol_valid', protocol['errors'])
        for label in ('mapping', 'problem', 'model', 'approval'):
            bound = protocol.get(label + '_path')
            if selected[label] is not None and (not bound or Path(selected[label]).resolve() != Path(bound).resolve()):
                return block(label + '_protocol_binding_matches', [f'requested {label} differs from protocol binding'])
        if state_path and protocol['project_id'] != load_document(Path(state_path))['project_id']:
            return block('protocol_project_id_matches', ['protocol project differs from project state'])
    elif intent == 'simulation_protocol' and selected['mapping'] is not None:
        from validate_domain_mapping import validate_domain_mapping
        mapping = validate_domain_mapping(selected['mapping'], project_root=project_root, require_ready=True)
        result['mapping_validation'] = mapping
        if not mapping['valid'] or not mapping['implementation_ready']:
            return block('implementation_ready', mapping['errors'] or ['current D implementation is required'])
        for label in ('problem', 'model', 'approval'):
            bound = mapping.get(label + '_path')
            if selected[label] is not None and (not bound or Path(selected[label]).resolve() != Path(bound).resolve()):
                return block(label + '_mapping_binding_matches', [f'requested {label} differs from current mapping'])
        if state_path and mapping['project_id'] != load_document(Path(state_path))['project_id']:
            return block('mapping_project_id_matches', ['mapping project differs from state'])
        result.update(status='allowed', execution_scope='simulation_protocol',
                      activated_modules=[intent], activated_resources=list(resources),
                      missing_gates=['simulation_protocol_supplied', 'simulation_protocol_frozen'])
        return result
    else:
        return block('simulation_protocol_supplied', ['supply the current protocol; protocol drafting requires a current ready mapping'])

    if intent == 'simulation_protocol':
        result.update(status='inspected', execution_scope='simulation_protocol',
                      activated_modules=[intent], activated_resources=list(resources),
                      missing_gates=list(protocol['missing_gates']))
        return result
    if not protocol.get('frozen') or not protocol.get('execution_ready'):
        return block('simulation_protocol_frozen', protocol['errors'] or ['current complete frozen protocol is required'])
    if intent == 'solver_diagnostics':
        if selected['primary_run'] is None:
            return block('current_run_receipt', ['supply the actual run receipt for this protocol'])
        from validate_simulation_receipt import validate_simulation_receipt
        report = validate_simulation_receipt(selected['primary_run'], project_root=project_root, protocol_report=protocol)
        result['run_validation'] = report
        if not report['valid']:
            return block('current_run_receipt', report['errors'])
        result.update(status='inspected', execution_scope='simulation_review', missing_gates=[],
                      activated_modules=[intent], activated_resources=list(resources))
        return result

    from validate_environment import validate_environment
    from validate_simulation_profile import validate_simulation_profile
    from validate_implementation_receipt import same_runtime
    operations = list(dict.fromkeys(load_contract('core/runtime_assurance_contract.yaml')['core_operations']
                                   + protocol['required_A_operations'] + [op for op in requested if op != OPERATION]))
    result['selected_operations'] = operations + [OPERATION]
    if selected['environment'] is None or selected['simulation_environment'] is None:
        return block('current_a_and_e_profiles', ['current independent A and E profiles are required'], 'simulation_profile_invalid')
    a = validate_environment(selected['environment'], expected_root=expected_root, required_operations=operations)
    e = validate_simulation_profile(selected['simulation_environment'], expected_root=expected_root,
                                    required_solver=protocol['run_spec']['solver']['name'])
    result.update(environment_validation=a, simulation_environment_validation=e)
    if not a['valid'] or not a['runtime_assured'] or not a['profile_current']:
        return block('required_operations_qualified', a['errors'], 'simulation_profile_invalid')
    if not e['valid'] or not e['simulation_assured'] or not e['profile_current']:
        return block('requested_solver_qualified', e['errors'], 'simulation_profile_invalid')
    if not same_runtime(load_document(Path(selected['environment']))['runtime'], e['runtime']):
        return block('simulation_runtime_matches', ['A and E runtime identities differ'], 'simulation_profile_invalid')
    if not same_runtime(load_document(protocol['implementation_receipt_path'])['runtime'], e['runtime']):
        return block('simulation_runtime_matches', ['approved D implementation and E runtime differ'], 'simulation_profile_invalid')
    for label, report in (('environment', a), ('simulation_environment', e)):
        binding = load_document(Path(state_path)).get(label) if state_path else None
        if binding and any(binding[key] != report.get(key) for key in ('profile_sha256', 'receipt_sha256')):
            return block(label + '_state_binding_matches', [f'{label} SHA binding differs from state'])
    result.update(status='allowed', missing_gates=[], execution_scope='simulation_execution',
                  execution_allowed=True, business_execution_allowed=True, simulation_execution_allowed=True,
                  activated_modules=[intent], activated_resources=list(resources),
                  profile_sha256=a['profile_sha256'], receipt_sha256=a['receipt_sha256'],
                  simulation_profile_path=str(Path(selected['simulation_environment']).resolve()),
                  simulation_profile_sha256=e['profile_sha256'], simulation_receipt_sha256=e['receipt_sha256'])
    return result
