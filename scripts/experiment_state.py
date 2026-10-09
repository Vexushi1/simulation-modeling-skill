"""Read-only G state/history dependencies; no state or primary-run writeback."""
from pathlib import Path

from runtime_common import contained_path, load_document, sha256_file

STAGES = {'EXPERIMENT_DESIGN_REVIEWED', 'CAMPAIGN_COMPLETE'}
HISTORICAL_ROLES = {'experiment_design', 'experiment_campaign', 'experiment_summary'}
CURRENT_ROLES = {'experiment_profile', 'experiment_route_decision'}


def validate_bindings(state, root, result, errors, stale, scope, requested_profile=None):
    result.update(experiment_checked=False, experiment_design_reviewed=False, campaign_complete=False,
                  experiment_environment_checked=False, experiment_design_path=None, campaign_path=None,
                  experiment_environment_path=None)
    for anchor in ('experiment_design', 'campaign', 'experiment_environment'):
        binding = state.get(anchor)
        field = 'profile_path' if anchor == 'experiment_environment' else 'path'
        path = contained_path(root, binding[field]) if binding else None
        result[anchor + '_path'] = str(path) if path else None
    if scope == 'all' and state.get('experiment_environment'):
        from validate_experiment_profile import validate_experiment_profile
        result['experiment_environment_checked'] = True
        path, binding = result['experiment_environment_path'], state['experiment_environment']
        design_path = result['experiment_design_path']
        method = load_document(Path(design_path)).get('method') if design_path and Path(design_path).is_file() else None
        report = validate_experiment_profile(path, required_method=method)
        result['experiment_environment_validation'] = report
        if requested_profile is not None and Path(requested_profile).resolve() != Path(path):
            errors.append('requested G profile differs from state binding')
        if not report['valid'] or any(report.get(k) != binding[k] for k in ('profile_sha256', 'receipt_sha256')):
            errors.extend('G environment: ' + error for error in report['errors'])
            errors.append('G sampling qualification or SHA binding is invalid')
            stale.add('experiment_environment')
    if scope not in {'all', 'experiment'}:
        return
    result['experiment_checked'] = True
    if state.get('experiment_design'):
        from validate_experiment_design import validate_experiment_design
        binding = state['experiment_design']
        report = validate_experiment_design(result['experiment_design_path'], project_root=root,
                                             require_reviewed=state['current_stage'] in STAGES)
        result['experiment_design_validation'] = report
        require_complete = state['current_stage'] in STAGES or report.get('reviewed', False)
        invalid = list(report['errors']) if not report['valid'] else []
        if report.get('design_sha256') != binding['sha256'] or report.get('project_id') != state['project_id']:
            invalid.append('experiment design differs from state project/SHA binding')
        if not result.get('model_approved') or not result.get('implementation_ready'):
            invalid.append('experiment design requires current bound B/C/D evidence')
        for name in ('problem', 'model', 'approval', 'mapping'):
            path, digest = report.get(name + '_path'), report.get(name + '_sha256')
            if path is not None and digest is not None:
                upstream = state.get(name)
                if not upstream or path != result.get(name + '_path') or digest != upstream['sha256']:
                    invalid.append('experiment design differs from state ' + name + ' binding')
        for member in report.get('catalog', []):
            protocol = member.get('protocol_report')
            if protocol is None:
                if require_complete:
                    invalid.append('catalog lacks current independently frozen complete E protocol')
                continue
            for name in ('problem', 'model', 'approval', 'mapping'):
                path, digest = protocol.get(name + '_path'), protocol.get(name + '_sha256')
                if not require_complete and (path is None or digest is None):
                    continue
                upstream = state.get(name)
                if not upstream or path != result.get(name + '_path') or digest != upstream['sha256']:
                    invalid.append('catalog differs from state ' + name + ' binding')
            if require_complete and (not protocol.get('frozen') or not protocol.get('execution_ready')):
                invalid.append('catalog lacks current independently frozen complete E protocol')
        if invalid:
            errors.extend('experiment design: ' + error for error in invalid)
            stale.add('experiment_design')
        result['experiment_design_reviewed'] = bool(report.get('reviewed') and not invalid)
    elif state.get('campaign'):
        errors.append('campaign requires an experiment-design binding')
        stale.add('campaign')
    if state.get('campaign'):
        from validate_experiment_receipt import validate_experiment_receipt
        binding = state['campaign']
        report = validate_experiment_receipt(result['campaign_path'], project_root=root,
                                            design_report=result.get('experiment_design_validation'))
        result['campaign_validation'] = report
        invalid = list(report['errors']) if not report['valid'] else []
        if not report.get('campaign_complete'):
            invalid.append('actual complete fixed-n campaign evidence required')
        path = Path(result['campaign_path'])
        if not path.is_file() or sha256_file(path) != binding['sha256']:
            invalid.append('campaign receipt SHA differs from state binding')
        if not result['experiment_design_reviewed']:
            invalid.append('campaign requires current reviewed experiment design')
        if invalid:
            errors.extend('campaign: ' + error for error in invalid)
            stale.add('campaign')
        result['campaign_complete'] = not invalid
    if state['current_stage'] in STAGES and not result['experiment_design_reviewed']:
        errors.append('EXPERIMENT_DESIGN_REVIEWED requires the current complete reviewed design')
        stale.add('experiment_design')
    if state['current_stage'] == 'CAMPAIGN_COMPLETE' and not result['campaign_complete']:
        errors.append('CAMPAIGN_COMPLETE requires actual complete campaign evidence')
        stale.add('campaign')


def validate_artifact(item, *, state, result, root, environment_dependents, ancestor_roles):
    role, parents = item['role'], set(item['depends_on'])
    path, invalid = contained_path(root, item['path']), []
    if role in HISTORICAL_ROLES:
        if item['id'] in environment_dependents:
            invalid.append('historical G evidence cannot depend on current runtime readiness')
        if not {'problem', 'model', 'approval', 'mapping', 'experiment_design'} <= parents:
            invalid.append('accepted G evidence must depend on current B/C/D/design anchors')
        if not result['experiment_design_reviewed']:
            invalid.append('accepted G evidence requires current reviewed experiment design')
        if role == 'experiment_design':
            binding = state.get('experiment_design')
            if not binding or path != Path(result['experiment_design_path']) or item['sha256'] != binding['sha256']:
                invalid.append('accepted experiment design differs from its state binding')
            if not {'mapping_contract', 'parameter_provenance', 'structure_evidence'} <= ancestor_roles(item):
                invalid.append('accepted experiment design lacks historical D dependency chain')
        else:
            if 'campaign' not in parents or not result['campaign_complete']:
                invalid.append('accepted campaign/summary requires the complete bound campaign')
            if 'experiment_design' not in ancestor_roles(item):
                invalid.append('accepted campaign/summary lacks experiment-design dependency chain')
            if role == 'experiment_campaign':
                binding = state.get('campaign')
                if not binding or path != Path(result['campaign_path']) or item['sha256'] != binding['sha256']:
                    invalid.append('accepted campaign differs from its state binding')
            elif result['campaign_complete']:
                receipt_path = Path(result['campaign_path'])
                receipt = load_document(receipt_path)
                from run_experiment import SUMMARY
                binding = receipt['artifacts'].get(SUMMARY)
                if not binding or path != receipt_path.parent / SUMMARY or item['sha256'] != binding['sha256']:
                    invalid.append('accepted summary must match validated campaign summary bytes')
                if 'experiment_campaign' not in ancestor_roles(item):
                    invalid.append('accepted summary lacks campaign dependency chain')
    elif role == 'experiment_profile':
        binding = state.get('experiment_environment')
        if (not binding or 'experiment_environment' not in parents or path != Path(result['experiment_environment_path'])
                or item['sha256'] != binding['profile_sha256'] or not result.get('experiment_environment_validation', {}).get('valid')):
            invalid.append('accepted G profile differs from current sampling qualification')
    else:
        if not {'environment', 'simulation_environment', 'experiment_environment', 'problem', 'model',
                'approval', 'mapping', 'experiment_design'} <= parents:
            invalid.append('accepted G route lacks current execution anchors')
        else:
            from resolve_runtime import resolve_runtime
            route = load_document(path)
            expected = resolve_runtime('experiment_campaign', design_path=result['experiment_design_path'],
                profile_path=result['environment_path'], simulation_profile_path=result['simulation_environment_path'],
                experiment_profile_path=result['experiment_environment_path'], required_operations=route.get('selected_operations'))
            fields = ('intent', 'phase', 'status', 'execution_scope', 'execution_allowed', 'business_execution_allowed',
                      'experiment_execution_allowed', 'simulation_execution_allowed', 'implementation_execution_allowed',
                      'activated_modules', 'activated_resources', 'activated_packs', 'upstream_skills', 'selected_operations',
                      'required_gates', 'missing_gates', 'profile_sha256', 'receipt_sha256', 'design_sha256',
                      'design_semantic_sha256', 'experiment_profile_sha256', 'experiment_receipt_sha256',
                      'simulation_profile_sha256', 'simulation_receipt_sha256', 'state_mutated')
            if expected['status'] != 'allowed' or any(route.get(k) != expected.get(k) for k in fields):
                invalid.append('accepted G route differs from current reviewed design and A/E/G qualifications')
    return invalid
