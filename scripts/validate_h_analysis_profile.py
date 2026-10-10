"""Independently reconstruct actual H trial operation qualification, read-only."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import math
from pathlib import Path

from h_analysis_trial import (OPERATION, artifact_manifest, assert_case, assert_case_functions, check_budget, contract, observed_runtime,
                             preflight_request, source_identities, validate_case_qualifications, validate_request)
from runtime_common import canonical_digest, contained_path, emit, load_document, sha256_file
from validate_environment import _path, _time, _version_info, utc_text
from validate_implementation_receipt import same_runtime
from verification_common import assert_unchanged, limited_document, typed_equal


def analytic_state(case, variable_id, time):
    """Independent closed-form oracle for the fixed synthetic qualification only."""
    spec = case['run_spec']
    params = {x['code_name']: x['value'] for x in spec['parameters']}
    a, b = params['a'], params['b']
    initial = {x['variable_id']: x['value'] for x in case['initial_conditions']}
    signal = spec['inputs'][0]
    if time == spec['start_time']: return initial[variable_id]
    if len(initial) == 2:
        # This probe's second model has a=b=1 and one affine input segment.
        if a != 1 or b != 1 or len(signal['time']) != 2:
            raise ValueError('fixed cascade qualification oracle identity differs')
        slope = (signal['values'][1] - signal['values'][0]) / (signal['time'][1] - signal['time'][0])
        u = signal['values'][0]
        offset = initial['x1'] - u + slope
        if variable_id == 'x1': return u + slope * (time - 1) + offset * math.exp(-time)
        return u + slope * (time - 2) + (initial['x2'] - u + 2 * slope + offset * time) * math.exp(-time)
    value = initial['x1']
    for left, right, u0, u1 in zip(signal['time'], signal['time'][1:], signal['values'], signal['values'][1:]):
        if time <= left: break
        width = min(time, right) - left
        slope = (u1 - u0) / (right - left)
        equilibrium = b * u0 / a
        value = equilibrium + b * slope * (width / a - 1 / (a * a)) + (value - equilibrium + b * slope / (a * a)) * math.exp(-a * width)
        if time <= right: break
    return value


def derive_profile(raw, request, process):
    validate_request(request)
    if request['mode'] != 'probe': raise ValueError('only an independent probe qualifies H')
    from probe_h_analysis import qualification_cases
    deadline = request['cases'][0]['qualification_not_after']
    expected_cases, expected_groups = qualification_cases(request['run_id'], request['output_directory'], deadline)
    if not typed_equal(request['cases'], expected_cases) or not typed_equal(request['groups'], expected_groups):
        raise ValueError('H operation qualification requires the exact fixed independent native matrix')
    runtime = observed_runtime(raw, request)
    actuals = raw.get('cases')
    if not isinstance(actuals, list) or len(actuals) != len(request['cases']):
        raise ValueError('complete actual qualification ledger cardinality differs')
    results, levels, cache = [], {}, {}
    previous_finish = _time(raw['started_at'])
    for case, actual in zip(request['cases'], actuals):
        errors = []
        try:
            assert_case_functions(actual, raw['functions'], raw['runtime']['matlabroot'])
            if not _time(raw['started_at']) <= _time(actual['started_at']) <= _time(actual['finished_at']) <= _time(raw['finished_at']):
                raise ValueError('actual per-case timestamps outside native batch')
            if _time(actual['started_at']) < previous_finish:
                raise ValueError('actual qualification case intervals overlap in a serial native batch')
            previous_finish = _time(actual['finished_at'])
            qualified_runtime = validate_case_qualifications(request, case, actual['started_at'], include_h=False, _cache=cache)
            if not same_runtime(runtime, qualified_runtime): raise ValueError('actual H probe runtime differs from independent A/E')
            checked = assert_case(actual, case, Path(request['output_directory']) / 'cases' / case['case_id'], request['run_id'], request['budget'])
            if case['expectation'] == 'success':
                if not checked['complete']: raise ValueError('successful qualification must have complete native output/state')
                for series in checked['states'] + checked['outputs']:
                    variable = series['variable_id'] if series in checked['states'] else ('x2' if len(case['states']) == 2 else 'x1')
                    if max(abs(y - analytic_state(case, variable, t)) for t, y in zip(series['time'], series['values'])) > 0.0005:
                        raise ValueError('native qualification differs from prior independent analytic state oracle')
                levels[case['case_id']] = {'run_spec': case['run_spec'], **checked}
        except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
            errors.append(str(error))
        results.append({'case_id': case['case_id'], 'passed': not errors, 'errors': errors})
    numeric = []
    from numerical_obligations import evaluate_trial_numeric
    for group in request['groups']:
        try:
            result = evaluate_trial_numeric([levels[x] for x in group['case_ids']], group['numeric_policy'], group['context'],
                                            project_id=group['context']['project_id'], physical_sha256=group['physical_sha256'])
            if not result['numerically_verified']: raise ValueError('qualification numerical triplet failed prior policy')
            numeric.append({'group_id': group['group_id'], 'passed': True, 'result': result, 'errors': []})
        except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
            numeric.append({'group_id': group['group_id'], 'passed': False, 'result': None, 'errors': [str(error)]})
    inventory = raw.get('installed_products', [])
    products = {x['Name']: x for x in inventory}
    target = raw['runtime']['release'] == contract()['target']['matlab_release'] and products.get('Simulink', {}).get('Version') == contract()['target']['simulink_version'] and set(products) >= {'MATLAB', 'Simulink'} and len(products) == len(inventory)
    good_process = raw.get('status') == 'completed' and process.get('process_state') == 'completed' and type(process.get('exit_code')) is int and process['exit_code'] == 0
    from validate_simulation_profile import finite
    good_process = good_process and finite(process.get('execution_timeout')) and 0 < process['execution_timeout'] <= request['budget']['process_timeout'] and (_time(process['finished_at']) - _time(process['started_at'])).total_seconds() <= process['execution_timeout']
    license_ok = type(raw.get('license_test')) in (int, float) and raw['license_test'] == 1
    common = all(x['passed'] for x in results) and all(x['passed'] for x in numeric)
    qualified = target and good_process and license_ok and common
    solvers = {name: {'qualified': bool(qualified and any(g['numeric_policy']['solver_levels'][0]['name'] == name for g in request['groups'])),
                     'group_ids': [g['group_id'] for g in request['groups'] if g['numeric_policy']['solver_levels'][0]['name'] == name]} for name in contract()['solvers']}
    return {'schema_version': 1, 'run_id': request['run_id'], 'captured_at': raw['finished_at'],
            'valid_until': utc_text(_time(raw['finished_at']) + timedelta(seconds=contract()['validity_seconds'])),
            'execution': {'channel': 'matlab_batch', 'host_fingerprint': request['host_fingerprint'], **process}, 'runtime': runtime,
            'sources': request['sources'], 'input_identity': request['input_identity'],
            'operation': {'operation_id': OPERATION, 'qualified': bool(qualified), 'scope': contract()['scope'],
                          'solvers': solvers, 'features': {feature: bool(qualified) for feature in contract()['features']},
                          'case_results': results, 'numeric_results': numeric}}


def evidence_chain(path, *, expected_root=None, now=None, project_root=None):
    from verification_common import EvidencePaths, evidence_paths, evidence_paths_for_request, input_manifest
    path = Path(path).resolve()
    directory, names = path.parent, contract()['evidence']
    profile = path.name == names['profile']
    receipt_path = directory / (names['profile_receipt'] if profile else names['run_receipt'])
    input_path = directory / names['input']
    # Bootstrap exact bytes before the first decode. A later graph/manifest
    # cannot legitimize a changed first-decoded request or receipt.
    bootstrap = input_manifest([path, receipt_path, input_path], directory, contract()['hard_budget'])
    request = limited_document(input_path, contract()['hard_budget'])
    assert_unchanged(bootstrap)
    check_budget(request['budget'])
    root = Path(project_root or request['bindings'].get('project_root', directory)).resolve()
    persisted = evidence_paths([receipt_path], root, request['budget'],
        root_contexts={receipt_path: 'qualification_h_receipt' if profile else 'h_trial_receipt'})
    inputs = evidence_paths_for_request(request, root, request['budget'],
        role='qualification_h_request' if profile else 'h_trial_request')
    paths = EvidencePaths()
    paths.update(persisted)
    paths.update(inputs)
    paths.update([path, receipt_path, input_path])
    paths.allowed_external.update(persisted.allowed_external | inputs.allowed_external)
    before = input_manifest(paths, root, request['budget'])
    assert_unchanged(bootstrap)
    validate_request(request)
    raw = limited_document(directory / names['raw'], request['budget'])
    receipt = limited_document(receipt_path, request['budget'])
    if _path(request['output_directory']) != _path(directory): raise ValueError('H evidence directory differs')
    for key in ('run_id', 'channel', 'host_fingerprint', 'input_identity', 'source_identity'):
        if raw.get(key) != request[key]: raise ValueError('H actual raw/request identity differs: ' + key)
    if type(raw.get('schema_version')) is not int or raw['schema_version'] != 1 or raw.get('status') not in {'completed', 'running', 'failed'}:
        raise ValueError('H native batch status/identity differs')
    if not isinstance(receipt.get('errors'), list) or any(not isinstance(x, str) for x in receipt['errors']):
        raise ValueError('H receipt requires the complete error ledger')
    if profile and (raw['status'] != 'completed' or receipt['errors']):
        raise ValueError('H qualification requires an error-free completed native batch')
    process = receipt['process']
    if process.get('process_state') not in {'completed', 'failed', 'timed_out'} or process.get('exit_code') is not None and type(process['exit_code']) is not int or not typed_equal(limited_document(directory / names['process'], request['budget']), process):
        raise ValueError('H actual process completion/failure metadata differs')
    from validate_simulation_profile import finite
    if not finite(process.get('execution_timeout')) or not 0 < process['execution_timeout'] <= request['budget']['process_timeout']:
        raise ValueError('H actual process timeout exceeds the source-reviewed cap')
    if profile and (process['process_state'] != 'completed' or process['exit_code'] != 0):
        raise ValueError('H operation qualification process did not complete successfully')
    times = [_time(process['started_at']), _time(raw['started_at']),
             _time(raw['finished_at']) if raw.get('finished_at') else _time(process['finished_at']), _time(process['finished_at'])]
    clock = _time(now) if now is not None else datetime.now(timezone.utc)
    if not times[0] <= times[1] <= times[2] <= times[3] <= clock or times[0] == times[3]:
        raise ValueError('H native process/raw time order differs')
    if profile and (times[3] - times[0]).total_seconds() > process['execution_timeout']:
        raise ValueError('H qualification process exceeded its enforced cap')
    if type(receipt.get('schema_version')) is not int or receipt['schema_version'] != 1 or receipt.get('run_id') != request['run_id'] or not typed_equal(receipt.get('sources'), request['sources']):
        raise ValueError('H receipt run/source identity differs')
    actual_runtime = None
    if isinstance(raw.get('runtime'), dict):
        root_path = raw['runtime']['matlabroot']
        if expected_root is not None and _path(root_path) != _path(expected_root): raise ValueError('H runtime root differs')
        actual_runtime = observed_runtime(raw, request)
        release, version = _version_info(root_path)
        if release != contract()['target']['matlab_release'] or not raw['runtime']['version'].startswith(version):
            raise ValueError('H native runtime release/version differs')
    elif profile or raw['status'] != 'failed' or raw.get('runtime') is not None or raw.get('functions') != [] or any(x.get('attempted') is not False for x in raw.get('cases', [])):
        raise ValueError('missing actual runtime is permitted only for a complete not-started failure ledger')
    if not typed_equal(receipt['artifacts'], artifact_manifest(directory, include_profile=profile)):
        raise ValueError('H exact complete native artifact set differs')
    for binding in receipt['artifacts'].values():
        artifact = contained_path(directory, binding['file'])
        if sha256_file(artifact) != binding['sha256']: raise ValueError('H native artifact SHA differs')
    if not typed_equal(receipt['runtime'], actual_runtime):
        raise ValueError('H receipt actual runtime identity differs')
    assert_unchanged(before)
    return request, raw, receipt, times, before


def validate_h_analysis_profile(profile_path, *, expected_root=None, now=None, require_current=True, required_solver=None):
    result = {'valid': False, 'profile_current': False, 'h_analysis_assured': False, 'qualified_operations': [], 'qualified_solvers': [],
              'runtime': None, 'installation_identity_checked': False, 'host_fingerprint': None, 'profile_sha256': None, 'receipt_sha256': None, 'case_results': [], 'errors': []}
    try:
        path, names = Path(profile_path).resolve(), contract()['evidence']
        if path.name != names['profile']: raise ValueError('unexpected H qualification profile filename')
        request, raw, receipt, times, before = evidence_chain(path, expected_root=expected_root, now=now)
        expected_bindings = {'environment_profile', 'environment_receipt', 'simulation_profile', 'simulation_profile_receipt', 'required_A_operations'}
        if request['mode'] != 'probe' or set(request['bindings']) != expected_bindings:
            raise ValueError('only independent A/E-bound H probe can qualify the operation')
        declared = limited_document(path, request['budget'])
        derived = derive_profile(raw, request, receipt['process'])
        if not typed_equal(declared, derived): raise ValueError('H profile differs from independently reconstructed actual qualification')
        solvers = [name for name, item in derived['operation']['solvers'].items() if item['qualified']]
        current = (_time(now) if now is not None else datetime.now(timezone.utc)) <= _time(derived['valid_until'])
        result.update(profile_current=current, qualified_solvers=solvers, case_results=derived['operation']['case_results'])
        if derived['operation']['qualified'] is not True: raise ValueError('actual H operation qualification cases/target/process failed')
        if require_current and not current: raise ValueError('H qualification expired; re-probe before new execution')
        if required_solver is not None and required_solver not in solvers: raise ValueError('requested solver lacks actual H qualification')
        assert_unchanged(before)
        if source_identities() != request['sources']: raise ValueError('H native safety sources changed during qualification consumption')
        result.update(valid=True, h_analysis_assured=True, installation_identity_checked=True, qualified_operations=[OPERATION], runtime=derived['runtime'],
                      host_fingerprint=request['host_fingerprint'], profile_sha256=sha256_file(path), receipt_sha256=sha256_file(path.parent / names['profile_receipt']))
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        result['errors'].append(str(error))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile', type=Path)
    parser.add_argument('--expected-root', type=Path)
    parser.add_argument('--require-solver')
    args = parser.parse_args()
    result = validate_h_analysis_profile(args.profile, expected_root=args.expected_root, required_solver=args.require_solver)
    emit(result)
    return 0 if result['valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
