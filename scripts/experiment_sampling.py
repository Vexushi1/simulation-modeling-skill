"""Strict finite catalog sampling wire and independent historical MAT consumers."""
from __future__ import annotations

import math
from pathlib import Path

from runtime_common import ROOT, canonical_digest, contained_path, load_document, sha256_file
from validate_environment import _path, validate_environment
from validate_implementation_receipt import same_runtime

METHODS = ('scenario_matrix', 'full_factorial', 'monte_carlo_catalog')


def contract():
    return load_document(ROOT / 'core/experiment_assurance_contract.yaml')


def source_identities():
    return {name: sha256_file(ROOT / name) for name in contract()['source_files']}


def records(value, label):
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(label + ': explicit 0/1/N record array required')
    return value


def file_binding(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': sha256_file(path)}


def validate_sampling_spec(spec):
    fields = {'method', 'catalog_ids', 'draws', 'probabilities', 'seed'}
    if not isinstance(spec, dict) or set(spec) != fields or spec['method'] not in METHODS:
        raise ValueError('exact supported catalog sampling surface required')
    ids = spec['catalog_ids']
    if (not isinstance(ids, list) or not 1 <= len(ids) <= 16 or
            any(not isinstance(value, str) or not value.strip() for value in ids) or
            len(set(ids)) != len(ids)):
        raise ValueError('one to sixteen unique ordered catalog IDs required')
    draws = spec['draws']
    if type(draws) is not int or not 1 <= draws <= 16:
        raise ValueError('fixed integer draws must be in [1,16]')
    if spec['method'] != METHODS[2]:
        if draws != len(ids) or spec['probabilities'] is not None or spec['seed'] is not None:
            raise ValueError('deterministic catalog order requires one draw per member and null probability/seed')
        return None
    probabilities = spec['probabilities']
    if (not isinstance(probabilities, list) or len(probabilities) != len(ids) or
            any(type(value) not in (int, float) or not math.isfinite(value) or value < 0
                for value in probabilities) or math.fsum(probabilities) != 1.0):
        raise ValueError('categorical probabilities must be finite nonnegative and math.fsum exactly one')
    if type(spec['seed']) is not int or not 0 <= spec['seed'] < 2**32:
        raise ValueError('explicit uint32 seed required')
    return None


def categorical_indices(probabilities, uniforms):
    """Preserve order/repeats; only the CDF floating endpoint is repaired."""
    cdf = [math.fsum(probabilities[:index + 1]) for index in range(len(probabilities))]
    cdf[-1] = 1.0
    result = []
    for value in uniforms:
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value < 1:
            raise ValueError('uniform draws must be finite and in [0,1)')
        result.append(next(index + 1 for index, boundary in enumerate(cdf) if value < boundary))
    return result


def _input_arrays(spec):
    import numpy as np
    p = spec['probabilities']
    p = [] if p is None else p
    cdf = [math.fsum(p[:index + 1]) for index in range(len(p))]
    if cdf:
        cdf[-1] = 1.0
    return {'catalog_count': np.array([[len(spec['catalog_ids'])]], dtype=np.float64),
            'draws': np.array([[spec['draws']]], dtype=np.float64),
            'probabilities': np.asarray(p, dtype=np.float64).reshape(-1, 1),
            'cdf': np.asarray(cdf, dtype=np.float64).reshape(-1, 1),
            'seed': np.asarray([] if spec['seed'] is None else [spec['seed']], dtype=np.float64).reshape(-1, 1)}


def write_numeric_inputs(directory, cases):
    from scipy.io import savemat
    for case in cases:
        savemat(contained_path(directory, case['input_mat']), _input_arrays(case['sampling_spec']),
                do_compression=False, oned_as='column')


def _mat_arrays(path, expected):
    import numpy as np
    from scipy.io import loadmat
    # Check storage before any MATLAB-class conversion can discard imaginary parts.
    try:
        stored = loadmat(path, squeeze_me=False, mat_dtype=False)
        if any(np.iscomplexobj(value) for key, value in stored.items() if not key.startswith('__')):
            raise ValueError('complex MAT data is outside the real double boundary')
        data = loadmat(path, squeeze_me=False, mat_dtype=True)
    except Exception as error:
        raise ValueError('Cannot decode G MAT artifact ' + str(path) + ': ' +
                         type(error).__name__ + ': ' + str(error)) from error
    names = {key for key in data if not key.startswith('__')}
    if names != set(expected):
        raise ValueError('exact input/output MAT variable set required')
    for name, shape in expected.items():
        value = data[name]
        if (value.dtype != np.dtype('float64') or np.iscomplexobj(value) or
                value.shape != shape or not np.isfinite(value).all()):
            raise ValueError('real double MAT shape/value differs: ' + name)
    return data


def numeric_readback(directory, actual, case, run_id):
    import numpy as np
    spec = case['sampling_spec']
    expected_input = _input_arrays(spec)
    inputs = _mat_arrays(contained_path(directory, case['input_mat']),
                         {name: value.shape for name, value in expected_input.items()})
    if any(not np.array_equal(inputs[name], values) for name, values in expected_input.items()):
        raise ValueError('input MAT values differ from exact sampling specification')
    data = load_document(contained_path(directory, actual['data_file']))
    fields = {'schema_version', 'run_id', 'case_id', 'method', 'sample_indices', 'uniforms', 'matrix_shapes'}
    if (set(data) != fields or type(data['schema_version']) is not int or data['schema_version'] != 1 or
            data['run_id'] != run_id or data['case_id'] != case['case_id'] or data['method'] != spec['method']):
        raise ValueError('sampling numeric JSON identity differs')
    n = spec['draws'] if actual['status'] == 'completed' else 0
    uniform_n = n if spec['method'] == METHODS[2] else 0
    shapes = {'sample_indices': [n, 1], 'uniforms': [uniform_n, 1]}
    if (data['matrix_shapes'] != shapes or actual['matrix_shapes'] != shapes or
            any(type(dimension) is not int for shape in data['matrix_shapes'].values() for dimension in shape) or
            any(type(dimension) is not int for shape in actual['matrix_shapes'].values() for dimension in shape)):
        raise ValueError('recorded sample matrix shapes differ')
    arrays = _mat_arrays(contained_path(directory, actual['mat_file']),
                         {name: tuple(shape) for name, shape in shapes.items()})
    result = {}
    for name in shapes:
        values = data[name]
        if (not isinstance(values, list) or len(values) != shapes[name][0] or
                any(type(value) not in (int, float) or not math.isfinite(value) for value in values) or
                values != actual[name] or not np.array_equal(arrays[name][:, 0], values)):
            raise ValueError('MAT/JSON/raw sample values differ: ' + name)
        result[name] = list(values)
    if any(isinstance(value, float) and not value.is_integer() for value in result['sample_indices']):
        raise ValueError('one-based integer-valued double indices required')
    if any(not 1 <= value <= len(spec['catalog_ids']) for value in result['sample_indices']):
        raise ValueError('sample index lies outside the bound catalog')
    return result


def _stream_snapshot(value):
    fields = {'Type', 'Seed', 'NumStreams', 'StreamIndex', 'State', 'Substream',
              'NormalTransform', 'Antithetic', 'FullPrecision', 'StateClass', 'StateShape'}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError('complete actual random-stream configuration/state required')
    for name in ('Seed', 'NumStreams', 'StreamIndex', 'Substream'):
        number = value[name]
        if (type(number) not in (int, float) or not math.isfinite(number) or
                number != math.floor(number) or number < (0 if name == 'Seed' else 1)):
            raise ValueError('invalid actual random-stream property: ' + name)
    if (value['Seed'] >= 2**32 or value['StreamIndex'] > value['NumStreams'] or
            not isinstance(value['Type'], str) or not value['Type'] or
            value['NormalTransform'] not in {'Ziggurat', 'Polar', 'Inversion'} or
            type(value['Antithetic']) is not bool or type(value['FullPrecision']) is not bool or
            value['StateClass'] not in {'uint32', 'uint64'} or
            not isinstance(value['StateShape'], list) or len(value['StateShape']) != 2 or
            any(type(dimension) is not int or dimension < 1 for dimension in value['StateShape']) or
            not isinstance(value['State'], list) or not value['State'] or
            math.prod(value['StateShape']) != len(value['State']) or
            any(not isinstance(number, str) or not number.isascii() or not number.isdecimal() or
                not 0 <= int(number) < 2**(32 if value['StateClass'] == 'uint32' else 64)
                for number in value['State'])):
        raise ValueError('invalid actual random-stream configuration/state')
    return value


def assert_case(actual, case, directory, run_id):
    if (actual.get('case_id') != case['case_id'] or actual.get('method') != case['sampling_spec']['method'] or
            actual.get('input_mat') != case['input_mat'] or
            actual.get('mat_file') != case['case_id'] + '-sample.mat' or
            actual.get('data_file') != case['case_id'] + '-sample.json'):
        raise ValueError('native sampling case identity/files differ')
    values = numeric_readback(directory, actual, case, run_id)
    before, after = _stream_snapshot(actual['caller_before']), _stream_snapshot(actual['caller_after'])
    if (canonical_digest(before) != canonical_digest(after) or actual['caller_unchanged'] is not True or
            actual['caller_handle_unchanged'] is not True):
        raise ValueError('caller stream configuration/state was not preserved')
    if case['control'] in {'caller_special', 'caller_special_error'}:
        if (before['Type'] != 'mt19937ar' or before['Seed'] != 2026 or
                before['NormalTransform'] != 'Polar' or before['Antithetic'] is not True or
                before['FullPrecision'] is not True or before['StateClass'] != 'uint32' or len(before['State']) != 625):
            raise ValueError('nondefault caller stream configuration was not actually tested')
        original = _stream_snapshot(actual['global_before_override'])
        restored = _stream_snapshot(actual['global_after_restore'])
        if (actual['owned_override'] is not True or actual['global_handle_restored'] is not True or
                canonical_digest(original) != canonical_digest(restored)):
            raise ValueError('owned caller override did not restore the original global stream')
    if case['expectation'] == 'error':
        if (actual['status'] != 'failed' or actual['error_identifier'] != case['expected_error'] or
                not actual['error'] or values['sample_indices'] or values['uniforms']):
            raise ValueError('controlled invalid sampling request was not rejected cleanly')
        return values
    validate_sampling_spec(case['sampling_spec'])
    if actual['status'] != 'completed' or actual['error'] or actual['error_identifier']:
        raise ValueError('native sample did not complete cleanly')
    spec = case['sampling_spec']
    if spec['method'] == METHODS[2]:
        if case['control'] == 'uniform_boundary':
            if values['uniforms'] != case['uniforms']:
                raise ValueError('controlled zero-probability boundary uniforms differ')
        elif actual['algorithm'] != 'mt19937ar' or len(values['uniforms']) != spec['draws']:
            raise ValueError('actual local mt19937ar uniform draw count differs')
        if values['sample_indices'] != categorical_indices(spec['probabilities'], values['uniforms']):
            raise ValueError('indices do not follow U<CDF in bound catalog order')
        for key in ('local_before', 'local_after'):
            local = _stream_snapshot(actual[key])
            if (local['Type'] != 'mt19937ar' or local['Seed'] != spec['seed'] or
                    local['NormalTransform'] != 'Ziggurat' or local['Antithetic'] is not False or
                    local['FullPrecision'] is not True or local['StateClass'] != 'uint32' or len(local['State']) != 625):
                raise ValueError('local stream configuration/state is missing or changed')
        if case['control'] != 'uniform_boundary' and actual['local_before']['State'] == actual['local_after']['State']:
            raise ValueError('local stream state did not advance for actual sampling')
    elif (values['sample_indices'] != list(range(1, spec['draws'] + 1)) or values['uniforms'] or
          actual['algorithm'] != 'catalog_order' or actual['local_before'] != [] or actual['local_after'] != []):
        raise ValueError('deterministic catalog sampling changed order or invented randomness')
    return values


def verify_sample_bindings(request, *, historical_start=None):
    from validate_experiment_profile import validate_experiment_profile
    bindings = request['bindings']
    for key in ('environment_profile', 'environment_receipt', 'experiment_profile', 'experiment_receipt'):
        binding = bindings[key]
        if set(binding) != {'path', 'sha256'} or sha256_file(binding['path']) != binding['sha256']:
            raise ValueError('sampling qualification bytes changed: ' + key)
    spec = request['cases'][0]['sampling_spec']
    a = validate_environment(bindings['environment_profile']['path'],
                             required_operations=bindings['required_A_operations'],
                             expected_host=request['host_fingerprint'], now=historical_start)
    g = validate_experiment_profile(bindings['experiment_profile']['path'], required_method=spec['method'],
                                    require_current=True, now=historical_start)
    aruntime = load_document(bindings['environment_profile']['path'])['runtime']
    if (not a['valid'] or not g['valid'] or not same_runtime(aruntime, g['runtime']) or
            _path(aruntime['executable']) != _path(request['matlab_executable'])):
        raise ValueError('current/execution-time same-runtime A/G sampling qualification failed: ' +
                         '; '.join(a['errors'] + g['errors']))
    return g


def sample_experiment(spec, executable, directory, *, environment_profile, experiment_profile, timeout=240):
    """Execute only sampling in a fresh directory; always return its preserved receipt path."""
    from probe_environment import write_json
    from probe_experiment import artifact_manifest, execute_request, make_request
    from validate_experiment_profile import observed_runtime
    validate_sampling_spec(spec)
    case = {'case_id': 'sample', 'sampling_spec': spec, 'expectation': 'success', 'control': None,
            'expected_error': None, 'uniforms': [], 'input_mat': 'sample-input.mat'}
    request = make_request(executable, directory, environment_profile=environment_profile,
                           experiment_profile=experiment_profile, cases=[case], mode='sample')
    process = execute_request(request, timeout=timeout)
    directory, names = Path(directory).resolve(), contract()['evidence']
    path = directory / names['sample_receipt']
    raw = None
    receipt = {'schema_version': 1, 'run_id': request['run_id'], 'sources': request['sources'],
               'process': process, 'artifacts': {}}
    try:
        raw = load_document(directory / names['raw'])
        if not isinstance(raw, dict):
            raise ValueError('native sampling raw must be an object')
        receipt['runtime'] = observed_runtime(raw, request)
        assert_case(raw['cases'][0], case, directory, request['run_id'])
        receipt['artifacts'] = artifact_manifest(directory, raw, request=request)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError, IndexError) as error:
        archive_errors = []
        receipt['artifacts'] = artifact_manifest(directory, raw, request=request,
                                                 partial=True, errors=archive_errors)
        receipt['normalization_error'] = '; '.join(
            [type(error).__name__ + ': ' + str(error)] + archive_errors)
    try:
        write_json(path, receipt)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError, IndexError) as error:
        raise OSError('Cannot seal G sample receipt at ' + str(path) + ': ' + str(error)) from error
    return path


def validate_sample_receipt(path):
    from validate_experiment_profile import observed_runtime, validate_evidence_chain
    result = {'valid': False, 'errors': [], 'sample_indices': [], 'uniforms': [], 'method': None,
              'sampling_spec': None, 'run_id': None, 'runtime': None, 'receipt_sha256': None,
              'started_at': None, 'process': None}
    try:
        path = Path(path).resolve()
        if path.name != contract()['evidence']['sample_receipt']:
            raise ValueError('unexpected sampling receipt filename')
        request, raw, receipt, times = validate_evidence_chain(path)
        if request['mode'] != 'sample' or len(request['cases']) != 1:
            raise ValueError('qualification probe is not a project sample plan')
        g = verify_sample_bindings(request, historical_start=times[0])
        runtime = observed_runtime(raw, request)
        if not same_runtime(runtime, g['runtime']):
            raise ValueError('actual sampler runtime differs from qualified runtime')
        profile_request = load_document(Path(request['bindings']['experiment_profile']['path']).parent / contract()['evidence']['input'])
        profile_raw = load_document(Path(request['bindings']['experiment_profile']['path']).parent / contract()['evidence']['raw'])
        qualified_functions = {item['name']: item['path'] for item in records(profile_raw['functions'], 'qualified.functions')}
        if (request['required_functions'] != profile_request['required_functions'] or
                any(_path(qualified_functions.get(item['name'], '')) != _path(item['path']) for item in raw['functions'])):
            raise ValueError('actual sampling function resolution differs from independent qualification')
        qualified_bytes = {_path(item['path']): item['sha256'] for item in g['runtime']['function_files']}
        if any(qualified_bytes.get(_path(item['path'])) != item['sha256'] for item in runtime['function_files']):
            raise ValueError('actual sampler function-file bytes differ from independent qualification')
        values = assert_case(raw['cases'][0], request['cases'][0], path.parent, request['run_id'])
        result.update(valid=True, **values, method=request['cases'][0]['sampling_spec']['method'],
                      sampling_spec=request['cases'][0]['sampling_spec'], run_id=request['run_id'], runtime=runtime,
                      receipt_sha256=sha256_file(path), started_at=receipt['process']['started_at'], process=receipt['process'])
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError, IndexError) as error:
        result['errors'].append(str(error))
    return result
