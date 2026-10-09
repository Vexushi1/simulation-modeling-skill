"""Fault sealing and consumer regressions; these never qualify a native runtime."""
import copy
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy.io import savemat
from scipy.io.matlab import MatReadError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import experiment_sampling as sampling
import probe_experiment as probe
import validate_experiment_profile as profiles
from probe_environment import write_json
from runtime_common import load_document, sha256_file


@pytest.fixture
def fault_run(tmp_path, monkeypatch):
    """Inject failure at the process boundary, retaining real request/MAT writers."""
    names = sampling.contract()['evidence']
    a, g = tmp_path / 'a', tmp_path / 'g'
    a.mkdir(); g.mkdir()
    environment, qualified = a / 'profile.json', g / names['profile']
    for path in (environment, a / 'receipt.json', qualified, g / names['profile_receipt']):
        write_json(path, {'unit_test_fault_injection': True})
    options = {'bad_raw': False, 'missing_mat': False, 'unregistered': False}

    def execute(request, *, timeout):
        directory = Path(request['output_directory'])
        directory.mkdir()
        write_json(directory / names['input'], request)
        sampling.write_numeric_inputs(directory, request['cases'])
        process = {'process_state': 'completed', 'exit_code': 0,
                   'command': probe.command_for(request), 'started_at': '2026-10-09T00:00:00Z',
                   'finished_at': '2026-10-09T00:00:01Z', 'pid': 123}
        write_json(directory / names['process'], process)
        (directory / names['log']).write_text('Injected process boundary; no native execution.\n', encoding='utf-8')
        case = request['cases'][0]
        n = case['sampling_spec']['draws']
        indices = np.arange(1, n + 1, dtype=np.float64).reshape(n, 1)
        uniforms = np.empty((0, 1), dtype=np.float64)
        record = {'case_id': case['case_id'], 'method': case['sampling_spec']['method'],
                  'status': 'completed', 'input_mat': case['input_mat'],
                  'data_file': case['case_id'] + '-sample.json', 'mat_file': case['case_id'] + '-sample.mat',
                  'sample_indices': indices[:, 0].tolist(), 'uniforms': [],
                  'matrix_shapes': {'sample_indices': [n, 1], 'uniforms': [0, 1]}}
        write_json(directory / record['data_file'], {'schema_version': 1, 'run_id': request['run_id'],
                   **{key: record[key] for key in ('case_id', 'method', 'sample_indices', 'uniforms', 'matrix_shapes')}})
        if not options['missing_mat']:
            savemat(directory / record['mat_file'], {'sample_indices': indices, 'uniforms': uniforms})
        raw = {key: request[key] for key in ('run_id', 'channel', 'host_fingerprint', 'source_identity', 'input_identity')}
        raw.update(schema_version=1, status='completed', cases=[] if options['unregistered'] else [record])
        if options['bad_raw']:
            (directory / names['raw']).write_text('{incomplete native report', encoding='utf-8')
        else:
            write_json(directory / names['raw'], raw)
        return process

    monkeypatch.setattr(probe, 'execute_request', execute)
    monkeypatch.setattr(profiles, 'observed_runtime', lambda *_: {'unit_test_fault_injection': True})
    # This unit observation cannot qualify: the actual consumer must reject the failure receipt.
    monkeypatch.setattr(profiles, 'derive_profile', lambda *_: {
        'schema_version': 1, 'scope': 'sample_plan', 'sampling_assured': False})

    def run(mode):
        directory = tmp_path / ('run-' + mode)
        options['directory'] = directory
        if mode == 'sample':
            spec = {'method': sampling.METHODS[0], 'catalog_ids': ['a', 'b', 'c'],
                    'draws': 3, 'probabilities': None, 'seed': None}
            path = sampling.sample_experiment(spec, tmp_path / 'unit-only.exe', directory,
                                              environment_profile=environment, experiment_profile=qualified)
        else:
            result = probe.probe_experiment(tmp_path / 'unit-only.exe', directory, environment_profile=environment)
            assert not result['valid'] and not result['sampling_assured'] and not result['qualified_methods']
            path = Path(result['receipt_path'])
        assert path.is_file()
        receipt = load_document(path)
        assert receipt['normalization_error']
        observed = (sampling.validate_sample_receipt(path) if mode == 'sample' else
                    profiles.validate_experiment_profile(directory / names['profile']))
        assert not observed['valid']
        return directory, receipt

    return options, run, names


@pytest.mark.parametrize('mode', ['sample', 'probe'])
def test_bad_raw_is_preserved_in_an_invalid_receipt(fault_run, mode):
    options, run, names = fault_run
    options['bad_raw'] = True
    directory, receipt = run(mode)
    assert receipt['artifacts']['raw']['sha256'] == sha256_file(directory / names['raw'])
    assert (directory / names['raw']).read_text(encoding='utf-8') == '{incomplete native report'
    assert {'input', 'raw', 'process', 'log'} <= receipt['artifacts'].keys()


@pytest.mark.parametrize('mode', ['sample', 'probe'])
def test_missing_mat_does_not_discard_the_other_evidence(fault_run, mode):
    options, run, names = fault_run
    options['missing_mat'] = True
    directory, receipt = run(mode)
    request = load_document(directory / names['input'])
    case_id = request['cases'][0]['case_id']
    assert case_id + '_mat_file' not in receipt['artifacts']
    assert case_id + '_data_file' in receipt['artifacts']
    assert case_id + '_input_mat' in receipt['artifacts']
    assert case_id + '-sample.mat' in receipt['normalization_error']


@pytest.mark.parametrize('mode', ['sample', 'probe'])
def test_unregistered_existing_output_is_bound_by_the_request(fault_run, mode):
    options, run, names = fault_run
    options['unregistered'] = True
    directory, receipt = run(mode)
    assert load_document(directory / names['raw'])['cases'] == []
    case_id = load_document(directory / names['input'])['cases'][0]['case_id']
    binding = receipt['artifacts'][case_id + '_mat_file']
    assert binding['file'] == case_id + '-sample.mat'
    assert binding['sha256'] == sha256_file(directory / binding['file'])


def test_failed_profile_write_still_seals_the_qualification_receipt(fault_run, monkeypatch):
    options, run, names = fault_run
    options['bad_raw'] = True

    def fail_profile(path, value):
        if Path(path).name == names['profile']:
            raise OSError('injected profile write failure')
        write_json(path, value)

    monkeypatch.setattr(probe, 'write_json', fail_profile)
    directory, receipt = run('probe')
    assert not (directory / names['profile']).exists()
    assert 'injected profile write failure' in receipt['normalization_error']
    assert receipt['artifacts']['raw']['sha256'] == sha256_file(directory / names['raw'])


@pytest.mark.parametrize('mode', ['sample', 'probe'])
def test_receipt_write_failure_reports_its_actual_path(fault_run, monkeypatch, mode):
    options, run, names = fault_run
    options['bad_raw'] = True
    target = names['sample_receipt'] if mode == 'sample' else names['profile_receipt']

    def fail_receipt(path, value):
        if Path(path).name == target:
            raise OSError('injected receipt write failure')
        write_json(path, value)

    monkeypatch.setattr(probe, 'write_json', fail_receipt)
    monkeypatch.setattr('probe_environment.write_json', fail_receipt)
    with pytest.raises(OSError) as raised:
        run(mode)
    expected = options['directory'] / target
    assert str(expected) in str(raised.value) and 'injected receipt write failure' in str(raised.value)
    assert not expected.exists()


@pytest.mark.parametrize('error', [MatReadError('truncated MAT'), NotImplementedError('MAT 7.3')])
def test_external_mat_decode_errors_are_normalized(tmp_path, monkeypatch, error):
    def cannot_decode(*_args, **_kwargs):
        raise error

    monkeypatch.setattr('scipy.io.loadmat', cannot_decode)
    path = tmp_path / 'sample.mat'
    with pytest.raises(ValueError) as raised:
        sampling._mat_arrays(path, {'sample_indices': (1, 1)})
    assert str(path) in str(raised.value) and type(error).__name__ in str(raised.value)
    assert raised.value.__cause__ is error


@pytest.mark.parametrize('matlab_class', [6, 9])
def test_matlab_class_is_distinct_from_integer_storage(tmp_path, matlab_class):
    """Independent Level-5 bytes: mxDOUBLE and mxUINT8 share miUINT8 payload."""
    import struct
    from scipy.io import loadmat, whosmat

    def element(kind, payload):
        return struct.pack('<II', kind, len(payload)) + payload + b'\0' * (-len(payload) % 8)

    matrix = (element(6, struct.pack('<II', matlab_class, 0))
              + element(5, struct.pack('<ii', 2, 1))
              + element(1, b'sample_indices') + element(2, bytes([1, 2])))
    header = b'Independent MATLAB Level-5 class/storage regression'.ljust(116, b' ') + b'\0' * 8 + b'\0\1IM'
    path = tmp_path / 'class-storage.mat'
    path.write_bytes(header + element(14, matrix))
    assert loadmat(path, mat_dtype=False)['sample_indices'].dtype.name == 'uint8'
    assert whosmat(path)[0][2] == ('double' if matlab_class == 6 else 'uint8')
    if matlab_class == 6:
        value = sampling._mat_arrays(path, {'sample_indices': (2, 1)})['sample_indices']
        assert value.dtype.name == 'float64' and value[:, 0].tolist() == [1.0, 2.0]
    else:
        with pytest.raises(ValueError, match='real double MAT'):
            sampling._mat_arrays(path, {'sample_indices': (2, 1)})


def test_truncated_actual_mat_bytes_are_rejected(tmp_path):
    path = tmp_path / 'truncated.mat'
    path.write_bytes(b'')
    with pytest.raises(ValueError, match='Cannot decode G MAT artifact'):
        sampling._mat_arrays(path, {'sample_indices': (1, 1)})


def _stream(seed, *, polar=False, advanced=False):
    return {'Type': 'mt19937ar', 'Seed': seed, 'NumStreams': 1, 'StreamIndex': 1,
            'State': ['1' if advanced else '0'] + ['0'] * 624, 'StateClass': 'uint32',
            'StateShape': [625, 1], 'Substream': 1, 'NormalTransform': 'Polar' if polar else 'Ziggurat',
            'Antithetic': polar, 'FullPrecision': True}


@pytest.mark.parametrize('controlled_error', [False, True])
@pytest.mark.parametrize('mutation', [None, 'state', 'handle', 'ownership'])
def test_special_caller_must_restore_the_original_stream(monkeypatch, controlled_error, mutation):
    spec = {'method': sampling.METHODS[2], 'catalog_ids': ['one'], 'draws': 1,
            'probabilities': [1.0], 'seed': 7}
    if controlled_error:
        spec.update(catalog_ids=['one', 'two'], probabilities=[0.4, 0.4])
    case = {'case_id': 'special', 'sampling_spec': spec, 'input_mat': 'special-input.mat',
            'expectation': 'error' if controlled_error else 'success',
            'expected_error': 'PhaseG:Probability' if controlled_error else None,
            'control': 'caller_special_error' if controlled_error else 'caller_special', 'uniforms': []}
    values = {'sample_indices': [], 'uniforms': []} if controlled_error else {
        'sample_indices': [1.0], 'uniforms': [0.25]}
    original = _stream(19)
    caller = _stream(2026, polar=True)
    actual = {'case_id': 'special', 'method': spec['method'], 'input_mat': case['input_mat'],
              'mat_file': 'special-sample.mat', 'data_file': 'special-sample.json',
              'caller_before': caller, 'caller_after': copy.deepcopy(caller),
              'caller_unchanged': True, 'caller_handle_unchanged': True, 'owned_override': True,
              'global_before_override': original, 'global_after_restore': copy.deepcopy(original),
              'global_handle_restored': True, 'status': 'failed' if controlled_error else 'completed',
              'error': 'controlled rejection' if controlled_error else '',
              'error_identifier': case['expected_error'] or '', 'algorithm': 'mt19937ar',
              'local_before': _stream(7), 'local_after': _stream(7, advanced=True)}
    monkeypatch.setattr(sampling, 'numeric_readback', lambda *_: values)
    if mutation == 'state':
        actual['global_after_restore']['State'][0] = '1'
    elif mutation == 'handle':
        actual['global_handle_restored'] = False
    elif mutation == 'ownership':
        actual['owned_override'] = False
    if mutation is None:
        assert sampling.assert_case(actual, case, Path('.'), 'unit-only') == values
    else:
        with pytest.raises(ValueError, match='original global stream'):
            sampling.assert_case(actual, case, Path('.'), 'unit-only')
