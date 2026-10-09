"""Independent actual G sampling qualification; no project simulation or adoption."""
from __future__ import annotations

import argparse
import copy
import math
import os
from pathlib import Path
import uuid

from experiment_sampling import (METHODS, contract, file_binding, records, source_identities,
                                 validate_sampling_spec, verify_sample_bindings, write_numeric_inputs)
from probe_environment import _matlab_quote, _run_process, write_json
from runtime_common import ROOT, canonical_digest, contained_path, emit, host_fingerprint, load_document, sha256_file
from validate_environment import _path, validate_environment


def qualification_cases():
    """Source-bound synthetic infrastructure inputs; no test-factory dependency."""
    cases = []
    def add(case_id, method, ids, *, draws=None, probabilities=None, seed=None,
            control=None, error=None, uniforms=None):
        spec = {'method': method, 'catalog_ids': ids, 'draws': len(ids) if draws is None else draws,
                'probabilities': probabilities, 'seed': seed}
        cases.append({'case_id': case_id, 'sampling_spec': spec,
                      'expectation': 'error' if error else 'success', 'control': control,
                      'expected_error': error, 'uniforms': [] if uniforms is None else uniforms,
                      'input_mat': case_id + '-input.mat'})
    add('scenario_order', METHODS[0], ['south', 'north', 'base'])
    add('scenario_single', METHODS[0], ['one'])
    add('scenario_bad_count', METHODS[0], ['first', 'second'], draws=1, error='PhaseG:Deterministic')
    add('factorial_order', METHODS[1], ['low-low', 'low-high', 'high-low', 'high-high'])
    add('factorial_limit', METHODS[1], ['combination-' + str(k) for k in range(16)])
    add('factorial_bad_count', METHODS[1], ['one'], draws=0, error='PhaseG:Draws')
    ids, p, seed = ['zero', 'first', 'second', 'last'], [0.0, 0.25, 0.5, 0.25], 20261009
    for name, control in [('mc_seed_first', None), ('mc_seed_repeat', None),
                          ('mc_global_consumed', 'consume_global'), ('mc_special_caller', 'caller_special')]:
        add(name, METHODS[2], ids, draws=16, probabilities=p, seed=seed, control=control)
    add('mc_single', METHODS[2], ['one'], draws=1, probabilities=[1.0], seed=0)
    add('mc_zero_probability_boundary', METHODS[2], ['zero-a', 'half-a', 'zero-b', 'half-b'],
        draws=4, probabilities=[0.0, 0.5, 0.0, 0.5], seed=1, control='uniform_boundary',
        uniforms=[0.0, math.nextafter(0.5, 0.0), 0.5, math.nextafter(1.0, 0.0)])
    add('mc_bad_count', METHODS[2], ids, draws=17, probabilities=p, seed=seed, error='PhaseG:Draws')
    add('mc_bad_catalog', METHODS[2], ['member-' + str(k) for k in range(17)], draws=1,
        probabilities=[1.0] + [0.0] * 16, seed=1, error='PhaseG:Catalog')
    add('mc_bad_probability', METHODS[2], ['a', 'b'], draws=1,
        probabilities=[-0.1, 1.1], seed=1, error='PhaseG:Probability')
    add('mc_bad_total', METHODS[2], ['a', 'b'], draws=1,
        probabilities=[0.4, 0.4], seed=1, error='PhaseG:Probability')
    add('mc_bad_seed', METHODS[2], ['one'], draws=1,
        probabilities=[1.0], seed=2**32, error='PhaseG:Seed')
    add('mc_special_caller_error', METHODS[2], ['a', 'b'], draws=1,
        probabilities=[0.4, 0.4], seed=1, control='caller_special_error', error='PhaseG:Probability')
    return cases


def make_request(executable, directory, *, environment_profile, experiment_profile=None,
                 cases=None, mode='probe', run_id=None):
    policy, sources = contract(), source_identities()
    bindings = {'environment_profile': file_binding(environment_profile),
                'environment_receipt': file_binding(Path(environment_profile).parent / 'receipt.json'),
                'required_A_operations': policy['required_A_operations']}
    if mode == 'sample':
        bindings.update(experiment_profile=file_binding(experiment_profile),
                        experiment_receipt=file_binding(Path(experiment_profile).parent / policy['evidence']['profile_receipt']))
    request = {'schema_version': 1, 'run_id': run_id or str(uuid.uuid4()), 'mode': mode,
               'channel': 'matlab_batch', 'host_fingerprint': host_fingerprint(),
               'matlab_executable': str(Path(executable).resolve()),
               'output_directory': str(Path(directory).resolve()), 'sources': sources,
               'source_identity': canonical_digest(sources), 'required_functions': policy['functions'],
               'methods': list(METHODS) if mode == 'probe' else [cases[0]['sampling_spec']['method']],
               'cases': qualification_cases() if cases is None else copy.deepcopy(cases), 'bindings': bindings}
    request['input_identity'] = canonical_digest(request)
    return request


def validate_request(request):
    fields = {'schema_version', 'run_id', 'mode', 'channel', 'host_fingerprint', 'matlab_executable',
              'output_directory', 'sources', 'source_identity', 'required_functions', 'methods', 'cases',
              'bindings', 'input_identity'}
    if (not isinstance(request, dict) or set(request) != fields or type(request['schema_version']) is not int or
            request['schema_version'] != 1 or request['mode'] not in {'probe', 'sample'} or
            request['channel'] != 'matlab_batch'):
        raise ValueError('exact G sampling request identity required')
    uuid.UUID(request['run_id'])
    if (request['host_fingerprint'] != host_fingerprint() or request['sources'] != source_identities() or
            request['source_identity'] != canonical_digest(request['sources']) or
            request['input_identity'] != canonical_digest({k: v for k, v in request.items() if k != 'input_identity'}) or
            request['required_functions'] != contract()['functions']):
        raise ValueError('G sampling source, host, function surface or input identity changed')
    bindings = request['bindings']
    expected = {'environment_profile', 'environment_receipt', 'required_A_operations'}
    if request['mode'] == 'sample':
        expected |= {'experiment_profile', 'experiment_receipt'}
    if (not isinstance(bindings, dict) or set(bindings) != expected or
            bindings['required_A_operations'] != contract()['required_A_operations']):
        raise ValueError('exact operation-specific sampling qualification bindings required')
    for key in expected - {'required_A_operations'}:
        if (not isinstance(bindings[key], dict) or set(bindings[key]) != {'path', 'sha256'} or
                not isinstance(bindings[key]['path'], str) or not Path(bindings[key]['path']).is_absolute()):
            raise ValueError('absolute source-bound evidence binding required: ' + key)
    cases = records(request['cases'], 'request.cases')
    if request['mode'] == 'probe':
        if request['methods'] != list(METHODS) or canonical_digest(cases) != canonical_digest(qualification_cases()):
            raise ValueError('independent three-method native qualification case set differs')
    else:
        if len(cases) != 1:
            raise ValueError('project sampling requires exactly one uncontrolled sample plan')
        case = cases[0]
        if (set(case) != {'case_id', 'sampling_spec', 'expectation', 'control', 'expected_error', 'uniforms', 'input_mat'} or
                case['case_id'] != 'sample' or case['expectation'] != 'success' or case['control'] is not None or
                case['expected_error'] is not None or case['uniforms'] != [] or case['input_mat'] != 'sample-input.mat'):
            raise ValueError('project sample cannot contain qualification controls')
        validate_sampling_spec(case['sampling_spec'])
        if request['methods'] != [case['sampling_spec']['method']]:
            raise ValueError('selected sampling method identity differs')
    return request


def command_for(request):
    statement = "cd('{}'); sample_experiment('{}')".format(
        _matlab_quote(ROOT / 'scripts/matlab'),
        _matlab_quote(Path(request['output_directory']) / contract()['evidence']['input']))
    return [request['matlab_executable'], *(['-wait'] if os.name == 'nt' else []), '-batch', statement,
            '-logfile', str(Path(request['output_directory']) / contract()['evidence']['log'])]


def execute_request(request, *, timeout=240):
    validate_request(request)
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('positive finite sampling process timeout required')
    b = request['bindings']
    for key in ('environment_profile', 'environment_receipt'):
        if sha256_file(b[key]['path']) != b[key]['sha256']:
            raise ValueError('current A binding changed before sampling')
    a = validate_environment(b['environment_profile']['path'],
                             required_operations=b['required_A_operations'], expected_host=request['host_fingerprint'])
    if (not a['valid'] or
            _path(load_document(b['environment_profile']['path'])['runtime']['executable']) != _path(request['matlab_executable'])):
        raise ValueError('current same-host/runtime A sampling requirements failed: ' + '; '.join(a['errors']))
    if request['mode'] == 'sample':
        verify_sample_bindings(request)
    directory, names = Path(request['output_directory']), contract()['evidence']
    directory.mkdir(parents=True, exist_ok=False)
    write_json(directory / names['input'], request)
    write_numeric_inputs(directory, request['cases'])
    process, console = _run_process(command_for(request), directory, timeout)
    write_json(directory / names['process'], process)
    log = directory / names['log']
    if not log.exists():
        log.write_text(console or 'Actual sampling process failed; MATLAB logfile absent.\n', encoding='utf-8')
    elif console:
        with log.open('a', encoding='utf-8') as stream:
            stream.write('\nRunner console:\n' + console)
    if not (directory / names['raw']).exists():
        write_json(directory / names['raw'], {'schema_version': 1, 'run_id': request['run_id'],
                   'status': 'failed', 'cases': [], 'error': 'Native sampling raw absent; actual process/log preserved'})
    return process


def artifact_manifest(directory, raw, *, include_profile=False, request=None,
                      partial=False, errors=None):
    directory, names = Path(directory), contract()['evidence']
    result = {}
    errors = [] if errors is None else errors

    def add(key, name):
        try:
            path = contained_path(directory, name)
            result[key] = {'file': name, 'sha256': sha256_file(path)}
        except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
            if not partial:
                raise
            errors.append(key + ': ' + type(error).__name__ + ': ' + str(error))

    keys = ['input', 'raw', 'process', 'log'] + (['profile'] if include_profile else [])
    for key in keys:
        add(key, names[key])
    if request is None:
        request = load_document(directory / names['input'])
    for case in records(request['cases'], 'request.cases'):
        case_id = case['case_id']
        add(case_id + '_input_mat', case['input_mat'])
        for key, suffix in (('data_file', '-sample.json'), ('mat_file', '-sample.mat')):
            # Only source-bound expected names; a partial raw need not register an output.
            add(case_id + '_' + key, case_id + suffix)
    return result


def probe_experiment(executable, directory, *, environment_profile, timeout=240):
    request = make_request(executable, directory, environment_profile=environment_profile)
    process = execute_request(request, timeout=timeout)
    from validate_experiment_profile import derive_profile, observed_runtime, validate_experiment_profile
    directory, names = Path(directory).resolve(), contract()['evidence']
    profile_path, receipt_path = directory / names['profile'], directory / names['profile_receipt']
    raw = None
    receipt = {'schema_version': 1, 'run_id': request['run_id'], 'sources': request['sources'],
               'process': process, 'artifacts': {}}
    try:
        raw = load_document(directory / names['raw'])
        if not isinstance(raw, dict):
            raise ValueError('native sampling raw must be an object')
        profile = derive_profile(raw, request, process)
        write_json(profile_path, profile)
        receipt['runtime'] = observed_runtime(raw, request)
        receipt['artifacts'] = artifact_manifest(directory, raw, include_profile=True, request=request)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError, IndexError) as error:
        archive_errors = []
        failure = type(error).__name__ + ': ' + str(error)
        try:
            write_json(profile_path, {'schema_version': 1, 'run_id': request['run_id'],
                       'sampling_assured': False, 'error': failure})
        except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError, IndexError) as profile_error:
            archive_errors.append('profile: ' + type(profile_error).__name__ + ': ' + str(profile_error))
        receipt['artifacts'] = artifact_manifest(directory, raw, include_profile=True, request=request,
                                                 partial=True, errors=archive_errors)
        receipt['normalization_error'] = '; '.join([failure] + archive_errors)
    try:
        write_json(receipt_path, receipt)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError, IndexError) as error:
        raise OSError('Cannot seal G qualification receipt at ' + str(receipt_path) + ': ' + str(error)) from error
    result = validate_experiment_profile(profile_path)
    result['profile_path'], result['receipt_path'] = str(profile_path), str(receipt_path)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matlab-executable', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--environment-profile', type=Path, required=True)
    parser.add_argument('--timeout', type=float, default=240)
    args = parser.parse_args()
    try:
        result = probe_experiment(args.matlab_executable, args.output_dir,
                                  environment_profile=args.environment_profile, timeout=args.timeout)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        result = {'valid': False, 'sampling_assured': False, 'qualified_methods': [], 'errors': [str(error)]}
    emit(result)
    return 0 if result['valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
