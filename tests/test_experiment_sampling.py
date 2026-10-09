"""Sampling wire/independent numeric-consumer regression; not native qualification."""
import copy
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy.io import savemat

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from experiment_sampling import (METHODS, categorical_indices, numeric_readback,
                                 validate_sampling_spec, write_numeric_inputs)
from probe_environment import write_json


def spec(method=METHODS[2]):
    return {'method': method, 'catalog_ids': ['a', 'b', 'c'], 'draws': 3,
            'probabilities': [0.0, 0.5, 0.5] if method == METHODS[2] else None,
            'seed': 0 if method == METHODS[2] else None}


@pytest.mark.parametrize('method', METHODS)
def test_bounded_catalog_methods(method):
    assert validate_sampling_spec(spec(method)) is None


@pytest.mark.parametrize('change', [
    {'draws': 0}, {'draws': 17}, {'draws': True}, {'draws': 1.0},
    {'seed': -1}, {'seed': 2**32}, {'seed': True}, {'seed': 1.0},
    {'probabilities': [0.0, 0.4, 0.4]}, {'probabilities': [0.0, -0.1, 1.1]},
    {'probabilities': [0.0, float('nan'), 1.0]}, {'probabilities': [0.0, float('inf'), 1.0]},
    {'probabilities': [False, 0.5, 0.5]}, {'probabilities': [0.0, 1.0]},
    {'catalog_ids': []}, {'catalog_ids': ['a', 'a', 'b']}, {'catalog_ids': ['a', ' ', 'c']},
    {'catalog_ids': list(map(str, range(17)))}, {'method': 'lhsdesign'}, {'extra': 'ignored'},
])
def test_illegal_sampling_inputs_rejected(change):
    value = spec(); value.update(change)
    with pytest.raises(ValueError):
        validate_sampling_spec(value)


def test_exact_fields_and_deterministic_nulls():
    value = spec(); del value['seed']
    with pytest.raises(ValueError):
        validate_sampling_spec(value)
    for method in METHODS[:2]:
        for change in ({'draws': 2}, {'seed': 0}, {'probabilities': [0, 0.5, 0.5]}):
            value = spec(method); value.update(change)
            with pytest.raises(ValueError):
                validate_sampling_spec(value)


def test_zero_probability_strict_boundaries_preserve_order_and_repeats():
    assert categorical_indices([0.0, 0.5, 0.0, 0.5], [0.5, 0.0, 0.5, 0.25]) == [4, 2, 4, 2]
    with pytest.raises(ValueError):
        categorical_indices([0.5, 0.5], [1.0])


def test_validity_uses_accurate_sum_without_normalizing():
    value = spec(); value['probabilities'] = [1e-16, 1e-16, 0.9999999999999998]
    assert validate_sampling_spec(value) is None
    original = copy.deepcopy(value)
    categorical_indices(value['probabilities'], [0.0, 0.9])
    assert value == original


def numeric_case(tmp_path, n, method):
    value = spec(method)
    value.update(catalog_ids=['member-' + str(k) for k in range(n)], draws=n)
    if method == METHODS[2]:
        value['probabilities'] = [1.0] + [0.0] * (n - 1)
    case = {'case_id': 'sample', 'sampling_spec': value, 'input_mat': 'sample-input.mat'}
    write_numeric_inputs(tmp_path, [case])
    indices = np.ones((n, 1)) if method == METHODS[2] else np.arange(1, n + 1, dtype=np.float64).reshape(n, 1)
    uniforms = np.full((n, 1), 0.25) if method == METHODS[2] else np.empty((0, 1), dtype=np.float64)
    arrays = {'sample_indices': indices, 'uniforms': uniforms}
    actual = {'status': 'completed', 'data_file': 'sample-sample.json', 'mat_file': 'sample-sample.mat',
              'sample_indices': indices[:, 0].tolist(), 'uniforms': uniforms[:, 0].tolist(),
              'matrix_shapes': {key: list(value.shape) for key, value in arrays.items()}}
    savemat(tmp_path / actual['mat_file'], arrays)
    data = {'schema_version': 1, 'run_id': 'bound-run', 'case_id': 'sample', 'method': method,
            **{key: actual[key] for key in ('sample_indices', 'uniforms', 'matrix_shapes')}}
    write_json(tmp_path / actual['data_file'], data)
    return actual, case, arrays


@pytest.mark.parametrize('n', [1, 3, 16])
@pytest.mark.parametrize('method', [METHODS[0], METHODS[2]])
def test_numeric_empty_single_many_shapes_read_back(tmp_path, n, method):
    actual, case, _ = numeric_case(tmp_path, n, method)
    assert len(numeric_readback(tmp_path, actual, case, 'bound-run')['sample_indices']) == n


@pytest.mark.parametrize('mutation', ['row', 'complex', 'single', 'extra', 'value', 'input'])
def test_mat_tampering_rejected_independently(tmp_path, mutation):
    actual, case, arrays = numeric_case(tmp_path, 3, METHODS[2])
    if mutation == 'row':
        arrays['sample_indices'] = arrays['sample_indices'].T
    elif mutation == 'complex':
        arrays['sample_indices'] = arrays['sample_indices'].astype(np.complex128) + 1j
    elif mutation == 'single':
        arrays['sample_indices'] = arrays['sample_indices'].astype(np.float32)
    elif mutation == 'extra':
        arrays['unbound'] = np.ones((1, 1))
    elif mutation == 'value':
        arrays['sample_indices'][1, 0] = 2
    else:
        savemat(tmp_path / case['input_mat'], {'draws': np.array([[3.0]])})
    savemat(tmp_path / actual['mat_file'], arrays)
    with pytest.raises(ValueError):
        numeric_readback(tmp_path, actual, case, 'bound-run')


def test_failed_numeric_record_preserves_empty_column_shape(tmp_path):
    actual, case, _ = numeric_case(tmp_path, 3, METHODS[2])
    actual.update(status='failed', sample_indices=[], uniforms=[],
                  matrix_shapes={'sample_indices': [0, 1], 'uniforms': [0, 1]})
    arrays = {'sample_indices': np.empty((0, 1), dtype=np.float64),
              'uniforms': np.empty((0, 1), dtype=np.float64)}
    savemat(tmp_path / actual['mat_file'], arrays)
    data = {'schema_version': 1, 'run_id': 'bound-run', 'case_id': 'sample', 'method': METHODS[2],
            **{key: actual[key] for key in ('sample_indices', 'uniforms', 'matrix_shapes')}}
    write_json(tmp_path / actual['data_file'], data)
    assert numeric_readback(tmp_path, actual, case, 'bound-run') == {'sample_indices': [], 'uniforms': []}
    arrays['sample_indices'] = np.empty((0, 0), dtype=np.float64)
    savemat(tmp_path / actual['mat_file'], arrays)
    with pytest.raises(ValueError):
        numeric_readback(tmp_path, actual, case, 'bound-run')
