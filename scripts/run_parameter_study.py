"""Explicitly execute one approved reviewed F study as candidates, preserving evidence."""
from __future__ import annotations

import argparse
from pathlib import Path

from parameter_study_common import METHODS, contract
from probe_environment import write_json
from probe_parameter_study import artifact_manifest, execute_request, file_binding, make_request
from runtime_common import canonical_digest, emit, load_document, sha256_file
from validate_environment import _path, validate_environment
from validate_implementation_receipt import _bound_external, same_runtime
from validate_parameter_study_profile import observed_runtime, validate_parameter_study_profile
from validate_simulation_profile import validate_simulation_profile


def make_task_request(study_path, executable, directory, report, environment_profile, parameter_study_profile, *, project_root, simulation_profile=None, required_operations=None):
    required = list(dict.fromkeys(contract()['operations'][report['operation_id']]['required_A_operations']+report['required_A_operations']+list(required_operations or [])))
    bindings = {'project_id': report['project_id'], 'project_root': str(Path(project_root).resolve()),
                'study': file_binding(study_path), 'study_snapshot': load_document(study_path), 'study_semantic_sha256': report['semantic_sha256'],
                'native_spec_sha256': canonical_digest(report['native_spec']), 'bound_files': report['bound_files'],
                'environment_profile': file_binding(environment_profile), 'environment_receipt': file_binding(Path(environment_profile).parent/'receipt.json'),
                'parameter_study_profile': file_binding(parameter_study_profile),
                'parameter_study_profile_receipt': file_binding(Path(parameter_study_profile).parent/contract()['evidence']['profile_receipt']),
                'simulation_profile': file_binding(simulation_profile) if simulation_profile is not None else None,
                'simulation_profile_receipt': file_binding(Path(simulation_profile).parent/'simulation-profile-receipt.json') if simulation_profile is not None else None,
                'required_A_operations': required}
    case = {'case_id': 'trial', 'expectation': 'success', 'native_spec': report['native_spec'], 'control': None, 'expected_theta': None}
    return make_request(executable, directory, environment_profile=environment_profile, operations=[report['operation_id']], mode='trial', cases=[case], bindings=bindings)


def verify_trial_bindings(request, *, historical_start=None):
    from validate_parameter_study import validate_parameter_study
    b = request['bindings']
    expected = {'project_id', 'project_root', 'study', 'study_snapshot', 'study_semantic_sha256', 'native_spec_sha256', 'bound_files', 'environment_profile', 'environment_receipt', 'parameter_study_profile', 'parameter_study_profile_receipt', 'simulation_profile', 'simulation_profile_receipt', 'required_A_operations'}
    if set(b) != expected:
        raise ValueError('trial binding surface differs')
    root = Path(b['project_root']).resolve()
    if not Path(request['output_directory']).resolve().is_relative_to(root):
        raise ValueError('trial output leaves project')
    study = _bound_external(b['study'], root)
    if canonical_digest(load_document(study)) != canonical_digest(b['study_snapshot']):
        raise ValueError('complete study snapshot changed')
    report = validate_parameter_study(study, project_root=root, require_reviewed=True)
    if not report['valid'] or not report['trial_execution_ready']:
        raise ValueError('current approved and reviewed study required: '+'; '.join(report['errors']+report['missing_gates']))
    if report['project_id'] != b['project_id'] or report['semantic_sha256'] != b['study_semantic_sha256'] or canonical_digest(report['native_spec']) != b['native_spec_sha256'] or canonical_digest(request['cases'][0]['native_spec']) != b['native_spec_sha256'] or canonical_digest(report['bound_files']) != canonical_digest(b['bound_files']):
        raise ValueError('approved study semantic/native/source closure changed')
    for item in b['bound_files']:
        _bound_external(item, root)
    minimum = set(report['required_A_operations']) | set(contract()['operations'][report['operation_id']]['required_A_operations'])
    if not isinstance(b['required_A_operations'], list) or not minimum <= set(b['required_A_operations']):
        raise ValueError('method/study/caller required A operations dropped')
    for k in ('environment_profile', 'environment_receipt', 'parameter_study_profile', 'parameter_study_profile_receipt'):
        _bound_external(b[k])
    a = validate_environment(b['environment_profile']['path'], required_operations=b['required_A_operations'], now=historical_start, expected_host=request['host_fingerprint'])
    f = validate_parameter_study_profile(b['parameter_study_profile']['path'], required_operations=[report['operation_id']], now=historical_start)
    if not a['valid'] or not f['valid']:
        raise ValueError('independent current/execution-time A/F qualification failed: '+'; '.join(a['errors']+f['errors']))
    runtime = load_document(b['environment_profile']['path'])['runtime']
    if not same_runtime(runtime, f['runtime']) or _path(request['matlab_executable']) != _path(f['runtime']['executable']):
        raise ValueError('required A/F executable/runtime differs')
    if report['operation_id'] == METHODS[1]:
        for k in ('simulation_profile', 'simulation_profile_receipt'):
            _bound_external(b[k])
        e = validate_simulation_profile(b['simulation_profile']['path'], now=historical_start, required_solver='ode4')
        if not e['valid'] or not same_runtime(runtime, e['runtime']):
            raise ValueError('gain trial requires same-runtime actual E ode4 qualification: '+'; '.join(e['errors']))
    elif b['simulation_profile'] is not None or b['simulation_profile_receipt'] is not None:
        raise ValueError('non-simulation studies must not bind irrelevant E profiles')
    return report, f['runtime']


def run_parameter_study(study_path, executable, directory, *, environment_profile, parameter_study_profile, simulation_profile=None, project_root=None, required_operations=None):
    from validate_parameter_study import validate_parameter_study
    root = Path(project_root or Path(study_path).resolve().parent).resolve()
    report = validate_parameter_study(study_path, project_root=root, require_reviewed=True)
    if not report['valid'] or not report['trial_execution_ready']:
        raise ValueError('reviewed study is not trial_execution_ready: '+'; '.join(report['errors']+report['missing_gates']))
    from resolve_runtime import resolve_runtime
    intent = {METHODS[0]: 'parameter_identification', METHODS[1]: 'calibration', METHODS[2]: 'optimization'}[report['operation_id']]
    route = resolve_runtime(intent, study_path=study_path, profile_path=environment_profile,
                            parameter_study_profile_path=parameter_study_profile, simulation_profile_path=simulation_profile,
                            required_operations=required_operations)
    if not route['parameter_study_execution_allowed'] or route['execution_scope'] != 'parameter_trial':
        raise ValueError('public parameter-trial route blocked: '+'; '.join(route.get('errors', [])+route.get('blocked_reasons', [])))
    request = make_task_request(study_path, executable, directory, report, environment_profile, parameter_study_profile, project_root=root, simulation_profile=simulation_profile, required_operations=required_operations)
    verify_trial_bindings(request)
    process = execute_request(request, timeout=report['native_spec']['budget']['process_timeout'])
    directory, names = Path(directory), contract()['evidence']
    raw = load_document(directory/names['raw'])
    receipt = {'schema_version': 1, 'run_id': request['run_id'], 'project_id': report['project_id'],
               'study_sha256': report['study_sha256'], 'study_semantic_sha256': report['semantic_sha256'],
               'native_spec_sha256': canonical_digest(report['native_spec']), 'sources': request['sources'], 'process': process}
    try:
        receipt.update(runtime=observed_runtime(raw, request), artifacts=artifact_manifest(directory, raw))
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        receipt.update(normalization_error=str(error), runtime=None, artifacts=artifact_manifest(directory, {'cases': []}))
    path = directory/names['run_receipt']
    write_json(path, receipt)
    from validate_parameter_study_receipt import validate_parameter_study_receipt
    result = validate_parameter_study_receipt(path, project_root=root, study_report=report)
    result.update(receipt_path=str(path.resolve()), raw_path=str((directory/names['raw']).resolve()))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('study', type=Path)
    parser.add_argument('--project-root', type=Path)
    parser.add_argument('--matlab-executable', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--environment-profile', required=True, type=Path)
    parser.add_argument('--parameter-study-profile', required=True, type=Path)
    parser.add_argument('--simulation-profile', type=Path)
    parser.add_argument('--require-operation', action='append', default=[])
    args = parser.parse_args()
    try:
        result = run_parameter_study(args.study, args.matlab_executable, args.output_dir, environment_profile=args.environment_profile, parameter_study_profile=args.parameter_study_profile, simulation_profile=args.simulation_profile, project_root=args.project_root, required_operations=args.require_operation)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        result = {'valid': False, 'trial_complete': False, 'candidate_complete': False, 'errors': [str(error)]}
    emit(result)
    return 0 if result['valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
