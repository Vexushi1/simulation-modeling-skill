"""Shared strict F wire, source identity and independent numerical consumers."""
from __future__ import annotations

import math
from pathlib import Path

from runtime_common import ROOT, canonical_digest, contained_path, load_document, sha256_file
from validate_simulation_profile import finite, numeric_vector

METHODS = ('identification.arx_111', 'calibration.simulink_gain', 'optimization.quadratic_sqp')


def contract():
    return load_document(ROOT / 'core/parameter_study_assurance_contract.yaml')


def source_identities():
    return {name: sha256_file(ROOT / name) for name in contract()['source_files']}


def records(value, label):
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(label + ': explicit 0/1/N record array required')
    return value


def validate_native_spec(spec, *, controlled_negative=False):
    fields = {'method', 'parameter_ids', 'initial', 'lower', 'upper', 'train', 'holdout', 'sample_time', 'objective', 'budget', 'criteria', 'warning_policy'}
    if not isinstance(spec, dict) or set(spec) != fields or spec['method'] not in METHODS or spec['warning_policy'] not in {'record', 'reject'}:
        raise ValueError('exact supported parameter-study native surface required')
    ids = spec['parameter_ids']
    if not isinstance(ids, list) or not ids or not all(isinstance(v, str) and v for v in ids) or len(set(ids)) != len(ids):
        raise ValueError('unique ordered parameter IDs required')
    n = len(ids)
    method = spec['method']
    if method == METHODS[0]:
        if n != 2 or any(spec[k] is not None for k in ('initial', 'lower', 'upper')):
            raise ValueError('ARX [a,b] does not consume optimizer initialization/bounds')
    else:
        if n not in ((1,) if method == METHODS[1] else (1, 2)):
            raise ValueError('unsupported parameter count')
        for key in ('initial', 'lower', 'upper'):
            if len(numeric_vector(spec[key], key)) != n:
                raise ValueError('parameter-vector dimensions differ')
        if not controlled_negative and any(not lo < hi or not lo <= x <= hi for x, lo, hi in zip(spec['initial'], spec['lower'], spec['upper'])):
            raise ValueError('finite ordered bounds and in-bound initialization required')
    if set(spec['budget']) != {'max_iterations', 'max_evaluations', 'process_timeout', 'simulation_timeout'}:
        raise ValueError('explicit finite budget required')
    b = spec['budget']
    if any(type(b[k]) is not int or b[k] < (0 if controlled_negative else 1) for k in ('max_iterations', 'max_evaluations')) or not finite(b['process_timeout']) or b['process_timeout'] <= 0:
        raise ValueError('positive finite process and integer optimization budgets required')
    if method == METHODS[1]:
        if not finite(b['simulation_timeout']) or not 0 < b['simulation_timeout'] < b['process_timeout']:
            raise ValueError('positive simulation timeout must be below process timeout')
    elif b['simulation_timeout'] is not None:
        raise ValueError('non-simulation methods require null simulation timeout')
    if set(spec['criteria']) != {'max_train_rmse', 'max_holdout_rmse', 'max_condition_number', 'feasibility_tolerance'} or any(v is not None and (not finite(v) or v < (1 if k == 'max_condition_number' else 0) or k == 'feasibility_tolerance' and v == 0) for k,v in spec['criteria'].items()):
        raise ValueError('explicit lawful criteria or method-inapplicable null required')
    used_criteria = {'max_train_rmse', 'max_holdout_rmse', 'max_condition_number'} if method == METHODS[0] else {'max_train_rmse', 'max_holdout_rmse', 'feasibility_tolerance'} if method == METHODS[1] else {'feasibility_tolerance'}
    if any((value is None) == (key in used_criteria) for key,value in spec['criteria'].items()):
        raise ValueError('method criteria must be explicit and unused criteria null')
    if method == METHODS[2]:
        if any(spec[k] is not None for k in ('train', 'holdout', 'sample_time')):
            raise ValueError('quadratic design optimization has no observation data')
        o = spec['objective']
        if not isinstance(o, dict) or set(o) != {'centers', 'weights', 'scales', 'A', 'b'}:
            raise ValueError('explicit quadratic objective required')
        for k in ('centers', 'weights', 'scales'):
            if len(numeric_vector(o[k], k)) != n:
                raise ValueError('quadratic dimensions differ')
        if any(v <= 0 for k in ('weights', 'scales') for v in o[k]):
            raise ValueError('positive weights/scales required')
        if not isinstance(o['A'], list) or len(o['A']) != len(numeric_vector(o['b'], 'b', nonempty=False)):
            raise ValueError('linear constraint dimensions differ')
        for row in o['A']:
            if len(numeric_vector(row, 'A row')) != n:
                raise ValueError('linear constraint width differs')
        if spec['criteria']['feasibility_tolerance'] is None:
            raise ValueError('quadratic feasibility criterion required')
    else:
        if spec['objective'] is not None or not finite(spec['sample_time']) or spec['sample_time'] <= 0:
            raise ValueError('sampled study requires positive sample time and null design objective')
        for key in ('train', 'holdout'):
            data = spec[key]
            if not isinstance(data, dict) or set(data) != {'time', 'input', 'output', 'weights'}:
                raise ValueError('explicit train and holdout arrays required')
            time = numeric_vector(data['time'], key + '.time')
            if len(time) < (3 if method == METHODS[0] else 2):
                raise ValueError('insufficient sampled observations')
            for name in ('input', 'output', 'weights'):
                if len(numeric_vector(data[name], key + '.' + name)) != len(time):
                    raise ValueError('observation dimensions differ')
            if any(v <= 0 for v in data['weights']):
                raise ValueError('positive observation weights required')
            if not controlled_negative:
                dt = spec['sample_time']
                if any(abs((right - left) - dt) > max(1e-12, abs(dt)*1e-9) for left, right in zip(time, time[1:])):
                    raise ValueError('uniform increasing sampled grid required')
                if method == METHODS[1] and (time[0] < 0 or abs(time[0]/dt-round(time[0]/dt)) > 8*max(math.ulp(time[0]/dt), math.ulp(1.0))):
                    raise ValueError('gain start time must align with ode4 grid')
        if any(spec['criteria'][k] is None for k in ('max_train_rmse', 'max_holdout_rmse')):
            raise ValueError('prior training/holdout criteria required')
        if method == METHODS[0] and (spec['criteria']['max_condition_number'] is None or any(v != 1 for key in ('train', 'holdout') for v in spec[key]['weights'])):
            raise ValueError('ARX condition criterion and unit weights required')
    return spec


def predictions(spec, theta, split):
    data = spec[split]
    if spec['method'] == METHODS[0]:
        return [theta[0]*y+theta[1]*u for y, u in zip(data['output'][:-1], data['input'][:-1])]
    return [theta[0]*u for u in data['input']]


def residuals(spec, prediction, split):
    data = spec[split]
    offset = 1 if spec['method'] == METHODS[0] else 0
    return [math.sqrt(w)*(p-y) for p, y, w in zip(prediction, data['output'][offset:], data['weights'][offset:])]


def objective_value(spec, theta):
    o = spec['objective']
    return sum(w*((x-c)/s)**2 for x, c, w, s in zip(theta, o['centers'], o['weights'], o['scales']))


def numeric_readback(directory, actual, run_id):
    """Reject complex storage before MATLAB-class restoration; check exact shapes/values."""
    import numpy as np
    from scipy.io import loadmat
    data = load_document(contained_path(directory, actual['data_file']))
    names = ('theta', 'train_prediction', 'holdout_prediction', 'train_residual', 'holdout_residual', 'objective', 'exitflag')
    if set(data) != {'schema_version', 'run_id', 'case_id', *names} or type(data['schema_version']) is not int or data['schema_version'] != 1 or data['run_id'] != run_id or data['case_id'] != actual['case_id']:
        raise ValueError('numeric JSON exact identity differs')
    path = contained_path(directory, actual['mat_file'])
    stored = loadmat(path, variable_names=list(names), mat_dtype=False, squeeze_me=False)
    if any(k not in stored or np.iscomplexobj(stored[k]) for k in names):
        raise ValueError('native MAT missing/complex numeric fields')
    mat = loadmat(path, variable_names=['run_id', 'case_id', *names], mat_dtype=True, chars_as_strings=False, squeeze_me=False)
    for key in ('run_id', 'case_id'):
        value = mat.get(key)
        expected = run_id if key == 'run_id' else actual['case_id']
        if value is None or value.dtype != np.dtype('U1') or value.shape != (1, len(expected)) or ''.join(value[0]) != expected:
            raise ValueError('MAT char-row identity differs: ' + key)
    for key in names:
        value = numeric_vector(data[key], 'numeric.' + key, nonempty=False)
        expected = np.asarray(value, dtype=np.float64).reshape((len(value), 1))
        if mat[key].dtype != np.dtype('float64') or mat[key].shape != expected.shape or not np.array_equal(mat[key], expected):
            raise ValueError('native MAT double column or exact JSON mismatch: ' + key)
        actual_values = numeric_vector(actual[key], 'raw.' + key, nonempty=False)
        if actual_values != value:
            raise ValueError('raw numeric array differs: ' + key)
    return data


def optimizer_diagnostics(actual, spec, ledger):
    """Actual native termination diagnostics are required even for budget negatives."""
    expected_algorithm = 'sqp' if spec['method'] == METHODS[2] else 'trust-region-reflective'
    if actual['algorithm'] != expected_algorithm or type(actual['iterations']) is not int or not 0 <= actual['iterations'] <= spec['budget']['max_iterations'] or type(actual['func_count']) is not int or not 0 < actual['func_count'] <= spec['budget']['max_evaluations'] or len(ledger) > spec['budget']['max_evaluations'] or actual['func_count'] != sum(item['phase'] == 'train' for item in ledger) or not finite(actual['firstorderopt']) or actual['firstorderopt'] < 0:
        raise ValueError('actual algorithm/count/finite optimality diagnostics differ from reviewed budget')


def assert_case(actual, case, directory, run_id):
    import numpy as np
    spec = case['native_spec']
    if actual['case_id'] != case['case_id'] or actual['method'] != spec['method'] or not isinstance(actual.get('ledger'), list) or not isinstance(actual.get('diagnostics'), list):
        raise ValueError('raw case identity/array surface differs')
    numeric_readback(directory, actual, run_id)
    ledger = records(actual['ledger'], 'case.ledger')
    for index, call in enumerate(ledger, 1):
        if type(call['sequence']) is not int or call['sequence'] != index or call['phase'] not in {'train', 'holdout', 'final'} or not isinstance(call['error'], str):
            raise ValueError('complete ordered objective ledger required')
        theta = numeric_vector(call['theta'], 'ledger.theta')
        if len(theta) != len(spec['parameter_ids']):
            raise ValueError('ledger parameter dimensions differ')
        if not call['error']:
            if not finite(call['objective']):
                raise ValueError('successful objective ledger requires finite real numeric loss')
            numeric_vector(call['prediction'], 'ledger.prediction', nonempty=False)
            numeric_vector(call['residual'], 'ledger.residual', nonempty=False)
            if spec['method'] == METHODS[2]:
                expected = objective_value(spec, theta)
                if not finite(call['objective']) or abs(call['objective']-expected) > 1e-10*max(1, abs(expected)):
                    raise ValueError('quadratic ledger objective differs from independent arithmetic')
            else:
                expected = predictions(spec, theta, 'holdout' if call['phase'] == 'holdout' else 'train')
                if len(call['prediction']) != len(expected) or not np.allclose(call['prediction'], expected, rtol=0, atol=1e-10):
                    raise ValueError('ledger prediction differs from approved method')
                r = residuals(spec, call['prediction'], 'holdout' if call['phase'] == 'holdout' else 'train')
                if len(call['residual']) != len(r) or not np.allclose(call['residual'], r, rtol=0, atol=1e-12) or abs(call['objective']-sum(v*v for v in r)) > 1e-10:
                    raise ValueError('ledger residual/objective differs')
                if spec['method'] == METHODS[1]:
                    split = 'holdout' if call['phase'] == 'holdout' else 'train'
                    times = spec[split]['time']
                    numeric_vector(call['output_time'], 'ledger.output_time')
                    numeric_vector(call['saved_time'], 'ledger.saved_time')
                    simulation_file = contained_path(directory, call['simulation_file'])
                    if not simulation_file.is_file() or not simulation_file.stat().st_size:
                        raise ValueError('actual returned SimulationOutput MAT missing from call ledger')
                    if len(call['output_time']) != len(times) or len(call['saved_time']) != len(times) or not np.allclose(call['output_time'], times, rtol=0, atol=1e-10) or not np.allclose(call['saved_time'], times, rtol=0, atol=1e-10) or call['requested_solver'] != 'ode4' or call['requested_step'] != spec['sample_time'] or call['parameter_before'] != spec['initial'][0] or call['parameter_after'] != spec['initial'][0] or call['configuration_restored'] is not True:
                        raise ValueError('actual per-call gain time/parameter/setting restoration differs')
    if case['expectation'] != 'success':
        if actual['candidate_complete'] is not False:
            raise ValueError('controlled negative cannot be a completed candidate')
        if case['expectation'] == 'budget':
            if actual['status'] != 'budget_exhausted' or actual['exitflag'] != [0.0] or not ledger or any(c['error'] for c in ledger) or any(c['phase'] != 'train' for c in ledger):
                raise ValueError('actual budget termination and preserved calls required')
            optimizer_diagnostics(actual, spec, ledger)
        elif actual['status'] != 'failed' or not actual.get('error'):
            raise ValueError('controlled failure did not fail')
        if case['expectation'] == 'simulation_error':
            if not any('phase_f_controlled_missing_symbol' in item['error'] for item in ledger):
                raise ValueError('controlled missing-symbol actual simulation failure ledger missing')
        elif case['expectation'] == 'criterion':
            if actual['error_identifier'] != 'PhaseF:HoldoutCriterion' or len(actual['theta']) != 2 or [item['phase'] for item in ledger] != ['train', 'holdout'] or any(item['error'] or item['theta'] != actual['theta'] for item in ledger) or not np.allclose(actual['theta'], case['expected_theta'], rtol=0, atol=1e-6) or not actual['train_prediction'] or not actual['holdout_prediction']:
                raise ValueError('failed ARX holdout must preserve actual fitted theta and both call records')
            for split, call in zip(('train', 'holdout'), ledger):
                expected = predictions(spec, actual['theta'], split)
                prediction, residual = actual[split+'_prediction'], actual[split+'_residual']
                if len(prediction) != len(expected) or len(residual) != len(expected) or prediction != call['prediction'] or residual != call['residual']:
                    raise ValueError('failed ARX final predictions/residuals must preserve complete verified split ledger values')
            r = residuals(spec, actual['holdout_prediction'], 'holdout')
            if math.sqrt(sum(v*v for v in r)/sum(spec['holdout']['weights'][1:])) <= spec['criteria']['max_holdout_rmse']:
                raise ValueError('controlled holdout rejection requires an actual failed criterion')
        elif case['expectation'] == 'error':
            expected_error = 'PhaseF:Bounds' if 'bounds' in case['case_id'] else 'PhaseF:TimeGrid' if 'time' in case['case_id'] else 'PhaseF:RankDeficient'
            if actual['error_identifier'] != expected_error:
                raise ValueError('unrelated native failure cannot qualify the controlled rejection')
        return {'criteria_satisfied': False, 'candidate_complete': False}
    if actual['status'] != 'completed' or actual['candidate_complete'] is not True or actual['error'] or len(actual['theta']) != len(spec['parameter_ids']):
        raise ValueError('successful complete candidate fields required')
    theta = actual['theta']
    if not ledger or any(call['error'] for call in ledger):
        raise ValueError('completed candidate requires nonempty error-free objective ledger')
    phases = [call['phase'] for call in ledger]
    if spec['method'] == METHODS[0]:
        if phases != ['train', 'holdout'] or len(ledger) > spec['budget']['max_evaluations'] or any(call['theta'] != theta for call in ledger):
            raise ValueError('ARX fixed candidate train then holdout ledger required')
    elif spec['method'] == METHODS[1]:
        if len(phases) < 3 or phases[-2:] != ['final', 'holdout'] or any(v != 'train' for v in phases[:-2]) or any(call['theta'] != theta for call in ledger[-2:]):
            raise ValueError('gain optimizer calls then fixed candidate final/holdout ledger required')
    elif any(phase != 'train' for phase in phases):
        raise ValueError('quadratic optimizer objective ledger has unrelated phases')
    if spec['warning_policy'] == 'reject' and actual['diagnostics']:
        raise ValueError('candidate violates reject diagnostic policy')
    if spec['method'] != METHODS[0]:
        if len(actual['exitflag']) != 1 or actual['exitflag'][0] <= 0 or any(not lo <= x <= hi for x, lo, hi in zip(theta, spec['lower'], spec['upper'])):
            raise ValueError('positive convergence flag and feasible candidate bounds required')
        optimizer_diagnostics(actual, spec, ledger)
    if spec['method'] == METHODS[2]:
        tol = spec['criteria']['feasibility_tolerance']
        if any(sum(a*x for a, x in zip(row, theta))-b > tol for row, b in zip(spec['objective']['A'], spec['objective']['b'])) or len(actual['objective']) != 1 or not math.isclose(actual['objective'][0], objective_value(spec, theta), rel_tol=1e-10, abs_tol=1e-12):
            raise ValueError('candidate objective or linear feasibility differs')
    else:
        if spec['method'] == METHODS[0]:
            matrix = np.column_stack((spec['train']['output'][:-1], spec['train']['input'][:-1]))
            rank, condition = int(np.linalg.matrix_rank(matrix)), float(np.linalg.cond(matrix))
            if rank != 2 or condition > spec['criteria']['max_condition_number'] or type(actual['rank']) is not int or actual['rank'] != rank or not finite(actual['condition_number']) or not math.isclose(actual['condition_number'], condition, rel_tol=1e-8, abs_tol=1e-10):
                raise ValueError('ARX actual identifiability diagnostics failed')
            estimate = np.linalg.lstsq(matrix, spec['train']['output'][1:], rcond=None)[0]
            if not np.allclose(theta, estimate, rtol=0, atol=1e-8) or actual['algorithm'] != 'arx_prediction_111':
                raise ValueError('ARX coefficients differ from independent least squares')
        else:
            if not any(v != 0 for v in spec['train']['input']):
                raise ValueError('gain has no training excitation')
            if actual.get('restored') is not True or any(call.get('solver') != 'FixedStepDiscrete' or call.get('solver_type') != 'Fixed-Step' or call.get('stop_event') != 'ReachedStopTime' for call in ledger if not call['error']):
                raise ValueError('actual gain solver/termination/restoration evidence missing')
        for split in ('train', 'holdout'):
            expected = predictions(spec, theta, split)
            prediction = actual[split + '_prediction']
            if len(prediction) != len(expected) or not np.allclose(prediction, expected, rtol=0, atol=1e-10):
                raise ValueError('candidate predicted output differs')
            r = residuals(spec, prediction, split)
            offset = 1 if spec['method'] == METHODS[0] else 0
            if len(actual[split + '_residual']) != len(r) or not np.allclose(actual[split + '_residual'], r, rtol=0, atol=1e-12) or math.sqrt(sum(v*v for v in r)/sum(spec[split]['weights'][offset:])) > spec['criteria']['max_' + split + '_rmse']:
                raise ValueError('candidate residual or prior holdout criterion failed')
        if len(actual['objective']) != 1 or not math.isclose(actual['objective'][0], sum(v*v for v in actual['train_residual']), rel_tol=1e-10, abs_tol=1e-12):
            raise ValueError('candidate loss differs from training residuals')
    expected_theta = case.get('expected_theta')
    if expected_theta is not None and not np.allclose(theta, expected_theta, rtol=0, atol=1e-6):
        raise ValueError('qualification candidate differs from predetermined independent truth')
    return {'criteria_satisfied': True, 'candidate_complete': True}
