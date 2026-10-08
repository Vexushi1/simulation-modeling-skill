"""Read current or execution-time independent F operation qualifications."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from parameter_study_common import METHODS, assert_case, contract, records
from runtime_common import canonical_digest, contained_path, emit, load_document, sha256_file
from validate_environment import _official_function, _path, _time, _version_info, runtime_identity, utc_text, validate_environment
from validate_implementation_receipt import same_runtime


def observed_runtime(raw, request):
    functions = records(raw['functions'], 'raw.functions')
    names = {item['name']: item['path'] for item in functions}
    if len(names) != len(functions) or set(names) != set(request['required_functions']) or not all(_official_function(value, raw['runtime']['matlabroot']) for value in names.values()):
        raise ValueError('F function resolution differs from complete unique official method surface')
    return runtime_identity({**raw, 'operations': [{'functions': functions}]}, request['matlab_executable'])


def derive_profile(raw, request, process):
    from probe_parameter_study import validate_request
    validate_request(request)
    runtime = observed_runtime(raw, request)
    cases = records(raw.get('cases'), 'raw.cases')
    if len(cases) != len(request['cases']):
        raise ValueError('F raw case set incomplete')
    case_results = []
    for actual, case in zip(cases, request['cases']):
        errors = []
        try:
            assert_case(actual, case, Path(request['output_directory']), request['run_id'])
        except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
            errors.append(str(error))
        case_results.append({'case_id': case['case_id'], 'passed': not errors, 'errors': errors})
    results = {item['case_id']: item for item in case_results}
    inventory = records(raw.get('installed_products'), 'raw.installed_products')
    products = {v['Name']: v for v in inventory}
    diagnostics = records(raw.get('operation_diagnostics'), 'raw.operation_diagnostics')
    by_op = {v['operation_id']: v for v in diagnostics}
    if len(products) != len(inventory) or len(by_op) != len(diagnostics) or set(by_op) != set(request['operations']):
        raise ValueError('unique product and operation diagnostic sets required')
    all_functions = records(raw['functions'], 'raw.functions')
    global_functions = {v['name']: v['path'] for v in all_functions}
    if len(global_functions) != len(all_functions) or set(global_functions) != set(request['required_functions']):
        raise ValueError('complete unique resolved function-file identity set required')
    methods = {}
    for op in request['operations']:
        policy = contract()['operations'][op]
        evidence = by_op[op]
        functions = records(evidence['functions'], 'operation.functions')
        fn = {v['name']: v['path'] for v in functions}
        if any(global_functions.get(name) != path for name,path in fn.items()):
            raise ValueError('operation function paths differ from bound runtime identity')
        resolvable = len(fn) == len(functions) and set(fn) == set(policy['functions']) and all(_official_function(v, raw['runtime']['matlabroot']) for v in fn.values())
        passed = all(results[name]['passed'] for name in policy['cases'])
        licensed = type(evidence['license_test']) in (int, float) and evidence['license_test'] == 1
        target = raw['runtime']['release'] == contract()['target']['matlab_release'] and products.get('Simulink', {}).get('Version') == '25.2'
        complete = raw['status'] == 'completed' and process['process_state'] == 'completed' and type(process['exit_code']) is int and process['exit_code'] == 0
        methods[op] = {'product': policy['product'], 'installed': policy['product'] in products, 'licensed': licensed,
                       'resolvable': resolvable, 'callable': results[policy['cases'][0]]['passed'],
                       'qualified': bool(passed and licensed and resolvable and policy['product'] in products and target and complete),
                       'case_ids': policy['cases']}
    captured = raw['finished_at']
    return {'schema_version': 1, 'run_id': request['run_id'], 'captured_at': captured,
            'valid_until': utc_text(_time(captured)+timedelta(seconds=contract()['validity_seconds'])),
            'execution': {'channel': 'matlab_batch', 'host_fingerprint': request['host_fingerprint'], **process},
            'runtime': runtime, 'sources': request['sources'], 'input_identity': request['input_identity'],
            'operations': methods, 'case_results': case_results}


def validate_evidence_chain(path, *, expected_root=None, now=None):
    from probe_parameter_study import artifact_manifest, validate_request
    directory, names = Path(path).resolve().parent, contract()['evidence']
    key = 'profile_receipt' if Path(path).name == names['profile'] else 'run_receipt'
    request, raw, receipt = (load_document(directory/names[k]) for k in ('input', 'raw', key))
    validate_request(request)
    if _path(request['output_directory']) != _path(directory):
        raise ValueError('F output directory identity differs')
    for k in ('run_id', 'channel', 'host_fingerprint', 'source_identity', 'input_identity'):
        if raw.get(k) != request[k]:
            raise ValueError('F raw identity differs: '+k)
    if type(raw.get('schema_version')) is not int or raw['schema_version'] != 1 or raw['status'] != 'completed':
        raise ValueError('native F raw did not complete')
    records(raw['functions'], 'raw.functions')
    records(raw['licenses_inuse'], 'raw.licenses_inuse')
    process = receipt['process']
    if process['process_state'] != 'completed' or type(process['exit_code']) is not int or process['exit_code'] != 0 or canonical_digest(process) != canonical_digest(load_document(directory/names['process'])):
        raise ValueError('actual process did not complete with recorded exit zero')
    clock = _time(now) if now is not None else datetime.now(timezone.utc)
    times = [_time(process['started_at']), _time(raw['started_at']), _time(raw['finished_at']), _time(process['finished_at'])]
    if not times[0] <= times[1] <= times[2] <= times[3] <= clock or times[0] == times[3]:
        raise ValueError('F raw/process future or inconsistent timestamps')
    if type(receipt['schema_version']) is not int or receipt['schema_version'] != 1 or receipt['run_id'] != request['run_id'] or receipt['sources'] != request['sources'] or receipt.get('normalization_error'):
        raise ValueError('F receipt identity/normalization failed')
    root = raw['runtime']['matlabroot']
    release, version = _version_info(root)
    if expected_root is not None and _path(expected_root) != _path(root) or release != 'R2025b' or not raw['runtime']['version'].startswith(version):
        raise ValueError('F target/runtime installation identity differs')
    if receipt['artifacts'] != artifact_manifest(directory, raw, include_profile=key == 'profile_receipt'):
        raise ValueError('exact F artifact manifest differs')
    for binding in receipt['artifacts'].values():
        file = contained_path(directory, binding['file'])
        if not file.is_file() or not file.stat().st_size or sha256_file(file) != binding['sha256']:
            raise ValueError('F artifact bytes differ: '+binding['file'])
    runtime = observed_runtime(raw, request)
    if canonical_digest(receipt['runtime']) != canonical_digest(runtime):
        raise ValueError('actual F runtime identity changed')
    for k in ('environment_profile', 'environment_receipt'):
        b = request['bindings'][k]
        if sha256_file(b['path']) != b['sha256']:
            raise ValueError('F A evidence binding changed')
    a = validate_environment(request['bindings']['environment_profile']['path'], required_operations=request['bindings']['required_A_operations'], expected_root=root, expected_host=request['host_fingerprint'], now=times[0])
    if not a['valid'] or not same_runtime(runtime, load_document(request['bindings']['environment_profile']['path'])['runtime']):
        raise ValueError('execution-time required A evidence/runtime failed: '+'; '.join(a['errors']))
    return request, raw, receipt, times


def validate_parameter_study_profile(path, *, required_operations=None, expected_root=None, now=None, require_current=True, required_operation=None):
    result = {'valid': False, 'profile_current': False, 'parameter_study_assured': False, 'qualified_operations': [], 'runtime': None,
              'profile_sha256': None, 'receipt_sha256': None, 'case_results': [], 'errors': []}
    try:
        path = Path(path).resolve()
        if path.name != contract()['evidence']['profile']:
            raise ValueError('unexpected F profile filename')
        request, raw, receipt, times = validate_evidence_chain(path, expected_root=expected_root, now=now)
        if request['mode'] != 'probe' or set(request['bindings']) != {'environment_profile', 'environment_receipt', 'required_A_operations'}:
            raise ValueError('only independent F probes qualify methods')
        minimum_a = {name for op in request['operations'] for name in contract()['operations'][op]['required_A_operations']}
        if set(request['bindings']['required_A_operations']) != minimum_a:
            raise ValueError('independent F probe required A set changed')
        derived = derive_profile(raw, request, receipt['process'])
        if canonical_digest(load_document(path)) != canonical_digest(derived):
            raise ValueError('F profile differs from recomputed actual method evidence')
        qualified = [op for op, value in derived['operations'].items() if value['qualified']]
        result.update(qualified_operations=qualified, case_results=derived['case_results'])
        required = list(request['operations'] if required_operations is None else required_operations)
        if required_operation is not None:
            required.append(required_operation)
        if not required or any(op not in METHODS for op in required) or not set(required) <= set(qualified):
            raise ValueError('required F operations lack independent qualification')
        clock = _time(now) if now is not None else datetime.now(timezone.utc)
        current = clock <= _time(derived['valid_until'])
        result.update(profile_current=current, qualified_operations=qualified, case_results=derived['case_results'])
        if require_current and not current:
            raise ValueError('F operation profile expired; re-probe before new trial')
        result.update(valid=True, parameter_study_assured=True, runtime=derived['runtime'], profile_sha256=sha256_file(path),
                      receipt_sha256=sha256_file(path.parent/contract()['evidence']['profile_receipt']))
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        result['errors'].append(str(error))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', type=Path)
    parser.add_argument('--expected-root', type=Path)
    parser.add_argument('--require-operation', action='append')
    args = parser.parse_args()
    result = validate_parameter_study_profile(args.path, expected_root=args.expected_root, required_operations=args.require_operation)
    emit(result)
    return 0 if result['valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
