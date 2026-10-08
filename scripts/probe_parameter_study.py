"""Run independent source-bound actual method probes; preserve every failed case."""
from __future__ import annotations

import argparse
import copy
import os
from pathlib import Path
import uuid

from parameter_study_common import METHODS, contract, records, source_identities, validate_native_spec
from probe_environment import _matlab_quote, _run_process, write_json
from runtime_common import ROOT, canonical_digest, contained_path, emit, host_fingerprint, load_document, sha256_file
from validate_environment import _path, validate_environment


def file_binding(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': sha256_file(path)}


def qualification_cases(operations=None):
    operations = list(METHODS if operations is None else operations)
    cases = []
    budget = {'max_iterations': 60, 'max_evaluations': 200, 'process_timeout': 300.0, 'simulation_timeout': None}
    criteria = {'max_train_rmse': 1e-6, 'max_holdout_rmse': 1e-6, 'max_condition_number': 1e6, 'feasibility_tolerance': None}
    def data(sequence, gain=None):
        output = [0.0]
        for u in sequence[:-1]:
            output.append(0.6*output[-1]+1.2*u)
        return {'time': [index*0.1 for index in range(len(sequence))], 'input': sequence,
                'output': output if gain is None else [gain*u for u in sequence], 'weights': [1.0]*len(sequence)}
    train = data([1.0, -1.0, 2.0, 0.0, -2.0, 3.0, 1.0, -3.0, 2.0, 0.0, 1.0, -1.0])
    hold = data([-2.0, 1.0, 3.0, -1.0, 0.0, 2.0, -3.0, 1.0])
    arx = {'method': METHODS[0], 'parameter_ids': ['a', 'b'], 'initial': None, 'lower': None, 'upper': None,
           'train': train, 'holdout': hold, 'sample_time': 0.1, 'objective': None,
           'budget': copy.deepcopy(budget), 'criteria': copy.deepcopy(criteria), 'warning_policy': 'record'}
    gain = {**copy.deepcopy(arx), 'method': METHODS[1], 'parameter_ids': ['k'], 'initial': [0.5], 'lower': [0.0], 'upper': [3.0],
            'train': data([1.0, 2.0, -1.0, 0.0, 3.0, -2.0], 1.75), 'holdout': data([-1.0, 3.0, 2.0, 1.0], 1.75)}
    gain['budget']['simulation_timeout'] = 20.0
    gain['criteria']['max_condition_number'] = None
    gain['criteria']['feasibility_tolerance'] = 1e-7
    quad = {**copy.deepcopy(arx), 'method': METHODS[2], 'parameter_ids': ['x1', 'x2'], 'initial': [0.2, 0.2], 'lower': [0.0, 0.0], 'upper': [3.0, 3.0],
            'train': None, 'holdout': None, 'sample_time': None,
            'objective': {'centers': [2.0, 1.0], 'weights': [1.0, 1.0], 'scales': [1.0, 1.0], 'A': [[1.0, 1.0]], 'b': [1.0]},
            'criteria': {'max_train_rmse': None, 'max_holdout_rmse': None, 'max_condition_number': None, 'feasibility_tolerance': 1e-7}}
    def add(name, spec, expectation='success', truth=None):
        item = {'case_id': name, 'expectation': expectation, 'native_spec': copy.deepcopy(spec), 'control': None, 'expected_theta': truth}
        cases.append(item)
        return item
    if METHODS[0] in operations:
        add('arx_positive', arx, truth=[0.6, 1.2])
        failed = add('arx_rank_deficient', arx, 'error')
        failed['native_spec']['train'] = data([0.0]*12)
        failed = add('arx_invalid_time', arx, 'error')
        failed['native_spec']['train']['time'][2] = 0.25
        failed = add('arx_holdout_rejected', arx, 'criterion', truth=[0.6, 1.2])
        failed['native_spec']['holdout']['output'] = [value+0.5 for value in failed['native_spec']['holdout']['output']]
    if METHODS[1] in operations:
        add('gain_positive', gain, truth=[1.75])
        add('gain_simulation_error', gain, 'simulation_error')['control'] = 'invalid_gain_expression'
        add('gain_budget', gain, 'budget')['native_spec']['budget']['max_iterations'] = 1
        failed = add('gain_invalid_bounds', gain, 'error')
        failed['native_spec']['lower'] = [4.0]
    if METHODS[2] in operations:
        add('quadratic_positive', quad, truth=[1.0, 0.0])
        add('quadratic_budget', quad, 'budget')['native_spec']['budget']['max_iterations'] = 0
        failed = add('quadratic_invalid_bounds', quad, 'error')
        failed['native_spec']['lower'] = [4.0, 4.0]
    return cases


def make_request(executable, directory, *, environment_profile, operations=None, mode='probe', cases=None, bindings=None, run_id=None):
    operations = list(METHODS if operations is None else operations)
    if not operations or len(set(operations)) != len(operations) or any(k not in METHODS for k in operations):
        raise ValueError('unique supported operation IDs required')
    policy = contract()
    required_functions = list(dict.fromkeys(f for op in operations for f in policy['operations'][op]['functions']))
    required_a = list(dict.fromkeys(f for op in operations for f in policy['operations'][op]['required_A_operations']))
    sources = source_identities()
    request = {'schema_version': 1, 'run_id': run_id or str(uuid.uuid4()), 'mode': mode, 'channel': 'matlab_batch',
               'host_fingerprint': host_fingerprint(), 'matlab_executable': str(Path(executable).resolve()),
               'output_directory': str(Path(directory).resolve()), 'sources': sources, 'source_identity': canonical_digest(sources),
               'operations': operations, 'required_functions': required_functions,
               'cases': qualification_cases(operations) if cases is None else cases,
               'bindings': {'environment_profile': file_binding(environment_profile), 'environment_receipt': file_binding(Path(environment_profile).parent/'receipt.json'), 'required_A_operations': required_a} if bindings is None else bindings}
    request['input_identity'] = canonical_digest(request)
    return request


def validate_request(request):
    fields = {'schema_version', 'run_id', 'mode', 'channel', 'host_fingerprint', 'matlab_executable', 'output_directory', 'sources', 'source_identity', 'operations', 'required_functions', 'cases', 'bindings', 'input_identity'}
    if set(request) != fields or type(request['schema_version']) is not int or request['schema_version'] != 1 or request['mode'] not in {'probe', 'trial'} or request['channel'] != 'matlab_batch':
        raise ValueError('exact F request identity required')
    uuid.UUID(request['run_id'])
    if request['host_fingerprint'] != host_fingerprint() or request['sources'] != source_identities() or request['source_identity'] != canonical_digest(request['sources']) or request['input_identity'] != canonical_digest({k:v for k,v in request.items() if k != 'input_identity'}):
        raise ValueError('F source, host or request identity changed')
    operations = request['operations']
    if not isinstance(operations, list) or not operations or len(set(operations)) != len(operations) or any(k not in METHODS for k in operations):
        raise ValueError('unsupported F operations')
    expected = list(dict.fromkeys(f for op in operations for f in contract()['operations'][op]['functions']))
    if request['required_functions'] != expected:
        raise ValueError('official method surface differs')
    cases = records(request['cases'], 'request.cases')
    if request['mode'] == 'probe':
        if canonical_digest(cases) != canonical_digest(qualification_cases(operations)):
            raise ValueError('independent probe exact controlled cases differ')
    elif len(cases) != 1 or set(cases[0]) != {'case_id', 'expectation', 'native_spec', 'control', 'expected_theta'} or cases[0]['case_id'] != 'trial' or cases[0]['expectation'] != 'success' or cases[0]['control'] is not None or cases[0]['expected_theta'] is not None:
        raise ValueError('project trial cannot contain qualification controls')
    for case in cases:
        if case['native_spec']['method'] not in operations:
            raise ValueError('case operation missing')
        validate_native_spec(case['native_spec'], controlled_negative=request['mode'] == 'probe' and case['expectation'] != 'success')
    return request


def execute_request(request, *, timeout=300):
    validate_request(request)
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not 0 < timeout < float('inf') or any(case['native_spec']['budget']['simulation_timeout'] is not None and timeout <= case['native_spec']['budget']['simulation_timeout'] for case in request['cases']):
        raise ValueError('finite total process timeout must exceed simulation timeout')
    b = request['bindings']
    for key in ('environment_profile', 'environment_receipt'):
        if sha256_file(b[key]['path']) != b[key]['sha256']:
            raise ValueError('required A binding changed')
    a = validate_environment(b['environment_profile']['path'], required_operations=b['required_A_operations'], expected_host=request['host_fingerprint'])
    if not a['valid'] or _path(load_document(b['environment_profile']['path'])['runtime']['executable']) != _path(request['matlab_executable']):
        raise ValueError('current same-host required A operations failed: ' + '; '.join(a['errors']))
    if request['mode'] == 'trial':
        from run_parameter_study import verify_trial_bindings
        verify_trial_bindings(request)
        if timeout != request['cases'][0]['native_spec']['budget']['process_timeout']:
            raise ValueError('trial process timeout must equal reviewed budget')
    directory, names = Path(request['output_directory']), contract()['evidence']
    directory.mkdir(parents=True, exist_ok=False)
    write_json(directory/names['input'], request)
    statement = "cd('{}'); run_parameter_study('{}')".format(_matlab_quote(ROOT/'scripts/matlab'), _matlab_quote(directory/names['input']))
    command = [request['matlab_executable'], *(['-wait'] if os.name == 'nt' else []), '-batch', statement, '-logfile', str(directory/names['log'])]
    process, console = _run_process(command, directory, timeout)
    write_json(directory/names['process'], process)
    log = directory/names['log']
    if not log.exists():
        log.write_text(console or 'MATLAB logfile absent; actual failed process preserved.\n', encoding='utf-8')
    elif console:
        with log.open('a', encoding='utf-8') as stream:
            stream.write('\nRunner console:\n'+console)
    if not (directory/names['raw']).exists():
        write_json(directory/names['raw'], {'schema_version': 1, 'run_id': request['run_id'], 'status': 'failed', 'cases': [], 'error': 'native raw absent; process/log preserved'})
    return process


def artifact_manifest(directory, raw, *, include_profile=False):
    directory, names = Path(directory), contract()['evidence']
    keys = ['input', 'raw', 'process', 'log'] + (['profile'] if include_profile else [])
    result = {k: {'file': names[k], 'sha256': sha256_file(directory/names[k])} for k in keys}
    for actual in records(raw.get('cases', []), 'raw.cases'):
        for key in ('data_file', 'mat_file', 'model_file'):
            if actual.get(key):
                path = contained_path(directory, actual[key])
                result[actual['case_id']+'_'+key] = {'file': actual[key], 'sha256': sha256_file(path)}
        for call in records(actual.get('ledger', []), 'case.ledger'):
            if call.get('simulation_file'):
                path = contained_path(directory, call['simulation_file'])
                result[actual['case_id']+'_simulation_'+str(call['sequence'])] = {'file': call['simulation_file'], 'sha256': sha256_file(path)}
    return result


def probe_parameter_study(executable, directory, *, environment_profile, timeout=300, operations=None):
    request = make_request(executable, directory, environment_profile=environment_profile, operations=operations)
    process = execute_request(request, timeout=timeout)
    from validate_parameter_study_profile import derive_profile, observed_runtime, validate_parameter_study_profile
    directory, names = Path(directory), contract()['evidence']
    raw = load_document(directory/names['raw'])
    try:
        profile = derive_profile(raw, request, process)
        write_json(directory/names['profile'], profile)
        receipt = {'schema_version': 1, 'run_id': request['run_id'], 'sources': request['sources'], 'process': process,
                   'runtime': observed_runtime(raw, request), 'artifacts': artifact_manifest(directory, raw, include_profile=True)}
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        write_json(directory/names['profile'], {'schema_version': 1, 'run_id': request['run_id'], 'qualified': False, 'error': str(error)})
        receipt = {'schema_version': 1, 'run_id': request['run_id'], 'sources': request['sources'], 'process': process, 'normalization_error': str(error),
                   'artifacts': artifact_manifest(directory, {'cases': []}, include_profile=True)}
    write_json(directory/names['profile_receipt'], receipt)
    result = validate_parameter_study_profile(directory/names['profile'])
    result['profile_path'] = str((directory/names['profile']).resolve())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matlab-executable', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--environment-profile', required=True, type=Path)
    parser.add_argument('--timeout', type=float, default=300)
    parser.add_argument('--operation', action='append')
    args = parser.parse_args()
    try:
        result = probe_parameter_study(args.matlab_executable, args.output_dir, environment_profile=args.environment_profile, timeout=args.timeout, operations=args.operation)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        result = {'valid': False, 'parameter_study_assured': False, 'qualified_operations': [], 'errors': [str(error)]}
    emit(result)
    return 0 if result['valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
