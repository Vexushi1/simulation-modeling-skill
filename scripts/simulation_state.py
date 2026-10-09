"""Validate E state bindings and historical dependencies without writing state."""
from pathlib import Path

from runtime_common import contained_path, load_document, sha256_file

STAGES = {'SIMULATION_PROTOCOL_FROZEN', 'PRIMARY_RUN_COMPLETE'}
HISTORICAL_ROLES = {'simulation_protocol', 'simulation_run', 'simulation_output'}
CURRENT_ROLES = {'simulation_profile', 'simulation_route_decision'}


def validate_bindings(state, root, result, errors, stale, scope, requested_profile=None):
    result.update(simulation_checked=False, protocol_frozen=False, primary_run_complete=False,
                  simulation_environment_checked=False, protocol_path=None,
                  primary_run_path=None, simulation_environment_path=None)
    for anchor in ('protocol', 'primary_run', 'simulation_environment'):
        binding = state.get(anchor)
        field = 'profile_path' if anchor == 'simulation_environment' else 'path'
        path = contained_path(root, binding[field]) if binding else None
        result[anchor + '_path'] = str(path) if path else None
    if scope == 'all' and state.get('simulation_environment'):
        from validate_simulation_profile import validate_simulation_profile
        result['simulation_environment_checked'] = True
        path = result['simulation_environment_path']
        binding = state['simulation_environment']
        report = validate_simulation_profile(path)
        result['simulation_environment_validation'] = report
        if requested_profile is not None and Path(requested_profile).resolve() != Path(path):
            errors.append('requested simulation profile differs from project-state binding')
        if not report['valid'] or any(report.get(key) != binding[key] for key in ('profile_sha256', 'receipt_sha256')):
            errors.extend('simulation environment: ' + error for error in report['errors'])
            errors.append('simulation environment qualification or SHA binding is invalid')
            stale.add('simulation_environment')
    if scope not in {'all', 'simulation', 'numerical_verification', 'model_verification'}:
        return
    result['simulation_checked'] = True
    binding = state.get('protocol')
    if binding:
        from validate_simulation_protocol import validate_simulation_protocol
        report = validate_simulation_protocol(result['protocol_path'], project_root=root,
                                             require_frozen=state['current_stage'] in STAGES)
        result['protocol_validation'] = report
        invalid = []
        if not report['valid']:
            invalid.extend(report['errors'] or ['protocol validation failed'])
        if report['contract_sha256'] != binding['sha256'] or report['project_id'] != state['project_id']:
            invalid.append('protocol differs from current project/state SHA binding')
        for anchor in ('mapping', 'model', 'approval', 'problem'):
            upstream = state.get(anchor)
            if (not upstream or report.get(anchor + '_path') != result.get(anchor + '_path') or
                    report.get(anchor + '_sha256') != upstream['sha256']):
                invalid.append('protocol differs from state ' + anchor + ' binding')
        if not result['implementation_ready']:
            invalid.append('protocol state requires the current bound D implementation')
        if invalid:
            errors.extend('protocol: ' + error for error in invalid)
            stale.add('protocol')
        result['protocol_frozen'] = bool(report['frozen'] and not invalid)
    elif state.get('primary_run'):
        errors.append('primary_run binding requires a protocol binding')
        stale.add('primary_run')
    if state.get('primary_run'):
        from validate_simulation_receipt import validate_simulation_receipt
        binding = state['primary_run']
        report = validate_simulation_receipt(result['primary_run_path'], project_root=root,
                                            protocol_report=result.get('protocol_validation'))
        result['run_validation'] = report
        invalid = []
        if not report['valid'] or not report.get('primary_run_complete'):
            invalid.extend(report['errors'] or ['current complete successful run required'])
        receipt_path = Path(result['primary_run_path'])
        if not receipt_path.is_file() or sha256_file(receipt_path) != binding['sha256']:
            invalid.append('primary_run SHA differs from state binding')
        if not result['protocol_frozen']:
            invalid.append('primary_run requires current frozen protocol')
        if invalid:
            errors.extend('primary run: ' + error for error in invalid)
            stale.add('primary_run')
        result['primary_run_complete'] = not invalid
    if state['current_stage'] in STAGES and not result['protocol_frozen']:
        errors.append('SIMULATION_PROTOCOL_FROZEN requires the current complete frozen protocol')
        stale.add('protocol')
    if state['current_stage'] == 'PRIMARY_RUN_COMPLETE' and not result['primary_run_complete']:
        errors.append('PRIMARY_RUN_COMPLETE requires actual current successful simulation evidence')
        stale.add('primary_run')


def validate_artifact(item, *, state, result, root, environment_dependents, ancestor_roles):
    """Accepted is an explicit caller review; its evidence must still be current."""
    role = item['role']
    invalid = []
    path = contained_path(root, item['path'])
    parents = set(item['depends_on'])
    if role in HISTORICAL_ROLES:
        if item['id'] in environment_dependents:
            invalid.append('historical E evidence cannot depend on current environment readiness')
        needed = {'problem', 'model', 'approval', 'mapping', 'protocol'}
        if not needed <= parents:
            invalid.append('accepted E evidence must depend on its current B/C/D/protocol anchors')
        if not result['protocol_frozen']:
            invalid.append('accepted E evidence requires current frozen protocol')
        if role == 'simulation_protocol':
            binding = state.get('protocol')
            if not binding or path != Path(result['protocol_path']) or item['sha256'] != binding['sha256']:
                invalid.append('accepted protocol differs from its binding')
            if not {'mapping_contract', 'parameter_provenance', 'structure_evidence'} <= ancestor_roles(item):
                invalid.append('accepted protocol lacks current D dependency chain')
        else:
            if not result['primary_run_complete']:
                invalid.append('accepted run/output requires an actual complete current primary run')
            if 'primary_run' not in parents:
                invalid.append('accepted run/output must depend on primary_run anchor')
            needed_roles = {'simulation_protocol'} if role == 'simulation_run' else {'simulation_protocol', 'simulation_run'}
            if not needed_roles <= ancestor_roles(item):
                invalid.append('accepted run/output lacks protocol/run dependency chain')
            if role == 'simulation_run':
                binding = state.get('primary_run')
                if not binding or path != Path(result['primary_run_path']) or item['sha256'] != binding['sha256']:
                    invalid.append('accepted run differs from primary_run binding')
            elif result['primary_run_complete'] and result.get('primary_run_path'):
                receipt_path = Path(result['primary_run_path'])
                receipt = load_document(receipt_path)
                output_names = {'data', 'mat', 'csv', 'outputs', 'output_json', 'output_mat', 'output_csv'}
                candidates = {str((receipt_path.parent / binding['file']).resolve()): binding['sha256']
                              for key, binding in receipt.get('artifacts', {}).items()
                              if (key in output_names or key.startswith('csv_')) and isinstance(binding, dict) and 'file' in binding and 'sha256' in binding}
                if candidates.get(str(path)) != item['sha256']:
                    invalid.append('accepted output must match a validated numeric output artifact')
    elif role == 'simulation_profile':
        binding = state.get('simulation_environment')
        if (not binding or 'simulation_environment' not in parents or
                path != Path(result['simulation_environment_path']) or item['sha256'] != binding['profile_sha256'] or
                not result.get('simulation_environment_validation', {}).get('valid')):
            invalid.append('accepted E operation profile differs from current qualification binding')
    elif role == 'simulation_route_decision':
        if not {'environment', 'simulation_environment', 'protocol', 'mapping', 'model', 'approval', 'problem'} <= parents:
            invalid.append('accepted E route lacks current execution dependency anchors')
        elif not {'simulation_protocol', 'mapping_contract', 'parameter_provenance', 'structure_evidence'} <= ancestor_roles(item):
            invalid.append('accepted E route lacks current protocol and D evidence dependency chain')
        else:
            from resolve_runtime import resolve_runtime
            route = load_document(path)
            expected = resolve_runtime('simulation_execution', protocol_path=result['protocol_path'],
                profile_path=result['environment_path'], simulation_profile_path=result['simulation_environment_path'],
                required_operations=route.get('selected_operations'))
            fields = ('intent', 'phase', 'status', 'execution_scope', 'execution_allowed',
                      'business_execution_allowed', 'simulation_execution_allowed', 'implementation_execution_allowed',
                      'activated_modules', 'activated_resources', 'activated_packs', 'upstream_skills',
                      'selected_operations', 'required_gates', 'missing_gates',
                      'profile_sha256', 'receipt_sha256', 'protocol_sha256', 'protocol_semantic_sha256',
                      'simulation_profile_sha256', 'simulation_receipt_sha256', 'state_mutated')
            if expected['status'] != 'allowed' or any(route.get(key) != expected.get(key) for key in fields):
                invalid.append('accepted E route differs from current protocol/operation qualification')
    return invalid
