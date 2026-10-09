"""Current or historical independent sample_plan qualification; never qualify sim."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from experiment_sampling import METHODS, assert_case, contract, records
from runtime_common import ROOT, canonical_digest, contained_path, emit, load_document, sha256_file
from validate_environment import (_official_function, _path, _time, _version_info, runtime_identity,
                                  utc_text, validate_environment)
from validate_implementation_receipt import same_runtime


def observed_runtime(raw, request):
    functions = records(raw['functions'], 'raw.functions')
    paths = {item['name']: item['path'] for item in functions}
    if (len(paths) != len(functions) or set(paths) != set(request['required_functions']) or
            not all(_official_function(path, raw['runtime']['matlabroot']) for path in paths.values()) or
            _path(raw['producer_file']) != _path(ROOT / 'scripts/matlab/sample_experiment.m')):
        raise ValueError('actual sampler/complete official function resolution differs')
    return runtime_identity({**raw, 'operations': [{'functions': functions}]}, request['matlab_executable'])


def derive_profile(raw, request, process):
    from probe_experiment import validate_request
    validate_request(request)
    if request['mode'] != 'probe':
        raise ValueError('project samples cannot qualify sampling methods')
    runtime = observed_runtime(raw, request)
    cases = records(raw.get('cases'), 'raw.cases')
    if len(cases) != len(request['cases']):
        raise ValueError('native sampling qualification case set incomplete')
    case_results, values = [], {}
    for actual, expected in zip(cases, request['cases']):
        errors = []
        try:
            values[expected['case_id']] = assert_case(actual, expected, Path(request['output_directory']), request['run_id'])
        except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError, IndexError) as error:
            errors.append(str(error))
        case_results.append({'case_id': expected['case_id'], 'passed': not errors, 'errors': errors})
    first = values.get('mc_seed_first')
    for item in case_results:
        if item['case_id'] in {'mc_seed_repeat', 'mc_global_consumed', 'mc_special_caller'}:
            if first is None or values.get(item['case_id']) != first:
                item['passed'] = False
                item['errors'].append('same seed/catalog did not reproduce after caller stream changes/consumption')
    by_id = {item['case_id']: item for item in case_results}
    inventory = records(raw['installed_products'], 'raw.installed_products')
    products = {item['Name']: item for item in inventory}
    if len(products) != len(inventory):
        raise ValueError('unique actual product inventory required')
    target = (raw['runtime']['release'] == contract()['target']['matlab_release'] and
              products.get('Simulink', {}).get('Version') == contract()['target']['simulink_version'])
    complete = (raw['status'] == 'completed' and process['process_state'] == 'completed' and
                type(process['exit_code']) is int and process['exit_code'] == 0)
    if type(raw['license_test']) not in (int, float) or raw['license_test'] != 1:
        complete = False
    methods = {name: {'scope': 'sample_plan', 'operation_id': policy['operation_id'],
                     'qualified': bool(target and complete and 'MATLAB' in products and
                                       all(by_id[case]['passed'] for case in policy['cases'])),
                     'case_ids': policy['cases']}
               for name, policy in contract()['methods'].items()}
    captured = raw['finished_at']
    return {'schema_version': 1, 'run_id': request['run_id'], 'scope': 'sample_plan',
            'captured_at': captured,
            'valid_until': utc_text(_time(captured) + timedelta(seconds=contract()['validity_seconds'])),
            'execution': {'channel': 'matlab_batch', 'host_fingerprint': request['host_fingerprint'], **process},
            'runtime': runtime, 'sources': request['sources'], 'input_identity': request['input_identity'],
            'methods': methods, 'case_results': case_results}


def validate_evidence_chain(path, *, now=None):
    from probe_experiment import artifact_manifest, command_for, validate_request
    path, names = Path(path).resolve(), contract()['evidence']
    directory = path.parent
    key = 'profile_receipt' if path.name == names['profile'] else 'sample_receipt'
    request, raw, receipt = (load_document(directory / names[k]) for k in ('input', 'raw', key))
    validate_request(request)
    if _path(request['output_directory']) != _path(directory):
        raise ValueError('sampling output directory identity differs')
    for field in ('run_id', 'channel', 'host_fingerprint', 'source_identity', 'input_identity'):
        if raw.get(field) != request[field]:
            raise ValueError('native sampling identity differs: ' + field)
    if (type(raw.get('schema_version')) is not int or raw['schema_version'] != 1 or
            raw['status'] != 'completed' or type(receipt.get('schema_version')) is not int or
            receipt['schema_version'] != 1 or receipt['run_id'] != request['run_id'] or
            receipt['sources'] != request['sources'] or receipt.get('normalization_error')):
        raise ValueError('sampling receipt/raw normalization or completion failed')
    process = receipt['process']
    if (process['process_state'] != 'completed' or type(process['exit_code']) is not int or process['exit_code'] != 0 or
            process['command'] != command_for(request) or
            canonical_digest(process) != canonical_digest(load_document(directory / names['process']))):
        raise ValueError('actual sampling process/command did not complete with recorded exit zero')
    clock = _time(now) if now is not None else datetime.now(timezone.utc)
    times = [_time(process['started_at']), _time(raw['started_at']), _time(raw['finished_at']), _time(process['finished_at'])]
    if not times[0] <= times[1] <= times[2] <= times[3] <= clock or times[0] == times[3]:
        raise ValueError('sampling process/raw timestamps are reversed, future or inconsistent')
    if receipt['artifacts'] != artifact_manifest(directory, raw, include_profile=key == 'profile_receipt'):
        raise ValueError('sampling exact artifact manifest differs')
    for binding in receipt['artifacts'].values():
        artifact = contained_path(directory, binding['file'])
        if not artifact.is_file() or not artifact.stat().st_size or sha256_file(artifact) != binding['sha256']:
            raise ValueError('sampling artifact bytes changed: ' + binding['file'])
    runtime = observed_runtime(raw, request)
    release, version = _version_info(runtime['matlabroot'])
    if (release != contract()['target']['matlab_release'] or
            runtime['version'].split(' ')[0] != version or receipt['runtime'] != runtime):
        raise ValueError('sampling actual runtime installation identity differs')
    for key in ('environment_profile', 'environment_receipt'):
        binding = request['bindings'][key]
        if sha256_file(binding['path']) != binding['sha256']:
            raise ValueError('sampling bound A evidence bytes changed')
    a = validate_environment(request['bindings']['environment_profile']['path'],
                             required_operations=request['bindings']['required_A_operations'],
                             expected_root=runtime['matlabroot'], expected_host=request['host_fingerprint'], now=times[0])
    aruntime = load_document(request['bindings']['environment_profile']['path'])['runtime']
    if not a['valid'] or not same_runtime(runtime, aruntime):
        raise ValueError('execution-time A sampling qualification/runtime failed: ' + '; '.join(a['errors']))
    cases = records(raw['cases'], 'raw.cases')
    if len(cases) != len(request['cases']):
        raise ValueError('complete ordered native sample case set required')
    records(raw['licenses_inuse'], 'raw.licenses_inuse')
    return request, raw, receipt, times


def validate_experiment_profile(path, *, required_method=None, require_current=True, now=None):
    result = {'valid': False, 'sampling_assured': False, 'qualified_methods': [], 'runtime': None,
              'profile_sha256': None, 'receipt_sha256': None, 'profile_current': False,
              'case_results': [], 'errors': []}
    try:
        path = Path(path).resolve()
        if path.name != contract()['evidence']['profile']:
            raise ValueError('unexpected G sampling profile filename')
        request, raw, receipt, _ = validate_evidence_chain(path, now=now)
        if request['mode'] != 'probe' or request['methods'] != list(METHODS):
            raise ValueError('only independent three-method probes qualify sample_plan')
        derived = derive_profile(raw, request, receipt['process'])
        if canonical_digest(load_document(path)) != canonical_digest(derived):
            raise ValueError('sampling profile differs from recomputed actual assertions')
        qualified = [method for method in METHODS if derived['methods'][method]['qualified']]
        result.update(qualified_methods=qualified, case_results=derived['case_results'])
        required = list(METHODS) if required_method is None else [required_method]
        if any(method not in METHODS for method in required) or not set(required) <= set(qualified):
            raise ValueError('selected sampling method lacks actual independent qualification')
        clock = _time(now) if now is not None else datetime.now(timezone.utc)
        current = clock <= _time(derived['valid_until'])
        result['profile_current'] = current
        if require_current and not current:
            raise ValueError('sampling profile expired; re-probe before new execution')
        result.update(valid=True, sampling_assured=True, runtime=derived['runtime'],
                      profile_sha256=sha256_file(path),
                      receipt_sha256=sha256_file(path.parent / contract()['evidence']['profile_receipt']))
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError, IndexError) as error:
        result['errors'].append(str(error))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', type=Path)
    parser.add_argument('--require-method', choices=METHODS)
    parser.add_argument('--historical', action='store_true')
    args = parser.parse_args()
    result = validate_experiment_profile(args.path, required_method=args.require_method,
                                          require_current=not args.historical)
    emit(result)
    return 0 if result['valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
