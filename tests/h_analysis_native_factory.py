"""Explicitly synthetic actual-format H evidence for Python contract tests.

These files contain no MATLAB execution or user approval. The production probe
and independent native acceptance project must never import this module.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil

import numpy as np
from scipy.io import savemat

import h_analysis_trial as trial
from probe_environment import write_json
from runtime_common import canonical_digest, load_document
from validate_environment import _time, utc_text
from validate_numerical_verification import uniform_grid


def _cells(values):
    result = np.empty((len(values), 1), dtype=object)
    for index, value in enumerate(values):
        result[index, 0] = value if isinstance(value, str) else np.asarray(value, dtype=float).reshape(-1, 1)
    return result


def synthetic_native_case(case, directory, run_id, *, state_values, not_before=None):
    """Write native-shaped records from the caller's independent physical oracle."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    spec, build = case['run_spec'], case['build_spec']
    source = Path(spec['model_path'])
    if not source.exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b'SYNTHETIC H CONTRACT TEST; NOT A SIMULINK MODEL\n')
    owned = directory / (spec['model_name'] + '.slx')
    shutil.copyfile(source, owned)
    clock = datetime.now(timezone.utc)
    reference = clock - timedelta(microseconds=50)
    if not_before is not None:
        reference = max(reference, _time(not_before) + timedelta(microseconds=1))
    if reference + timedelta(microseconds=3) > clock:
        raise ValueError('synthetic case qualification floor must precede the current clock')
    solver = spec['solver']
    step = solver['fixed_step'] if solver['type'] == 'fixed-step' else (spec['stop_time'] - spec['start_time']) / 20
    times = uniform_grid(spec['start_time'], spec['stop_time'], step)
    if case['expectation'] == 'error': times = []
    if case['expectation'] == 'early_stop': times = [spec['start_time'], spec['start_time'] + 0.1]
    def parameters(records):
        return [{**p, 'unit': p['unit'] or '', 'class': 'Simulink.Parameter', 'data_type': 'double',
                 'value_class': 'double', 'shape': [1, 1], 'is_real': True} for p in records]
    baseline_initial = [{'block_path': item['block_path'], 'value': next(b['parameters']['InitialCondition'] for b in build['blocks'] if b['path'] == item['block_path'])} for item in case['initial_conditions']]
    applied_initial = [{'block_path': item['block_path'], 'value': format(item['value'], '.17g')} for item in case['initial_conditions']]
    output_sampling = [{'port': p['port'], 'block_path': p['block_path'], 'sample_time': '0'} for p in spec['outputs']]
    input_sampling = [{'port': p['port'], 'block_path': p['block_path'], 'interpolate': 'on' if p['interpolation'] == 'linear' else 'off'} for p in spec['inputs']]
    configured = {'StartTime': spec['start_time'], 'StopTime': spec['stop_time'], 'SimulationMode': 'normal'}
    for key, field in [('name', 'Solver'), ('type', 'SolverType'), ('fixed_step', 'FixedStep'), ('max_step', 'MaxStep'),
                       ('min_step', 'MinStep'), ('initial_step', 'InitialStep'), ('rel_tol', 'RelTol'), ('abs_tol', 'AbsTol'), ('zero_crossing', 'ZeroCrossControl')]:
        value = solver[key]
        if key == 'type': value = {'fixed-step': 'Fixed-step', 'variable-step': 'Variable-step'}[value]
        if value is not None: configured[field] = value
    step_field = 'FixedStepSize' if solver['name'] == 'ode4' else 'MaxStepSize'
    baseline_configuration = {name: '' for name in trial.CONFIGURATION_FIELDS}
    baseline_configuration.update(Solver='ode45', SolverType='Variable-step', StartTime='0', StopTime='10',
        SimulationMode='normal', SaveOutput='on', SaveFormat='Dataset', DatasetSignalFormat='timeseries',
        SaveTime='on', SaveState='off', SaveFinalState='off', SaveOperatingPoint='off', SignalLogging='off',
        LimitDataPoints='off', Decimation='1')
    actual = {'case_id': case['case_id'], 'attempted': True, 'completed': True, 'framework_error': {},
              'started_at': utc_text(reference), 'finished_at': utc_text(reference + timedelta(microseconds=1)),
              'functions': [], 'simulation_returned': True, 'model_file': str(owned.resolve()),
              'source_model_file': str(source.resolve()), 'raw_mat_file': 'simulation-output.mat',
              'before_parameters': parameters(build['parameters']), 'applied_parameters': parameters(spec['parameters']),
              'after_parameters': parameters(build['parameters']), 'reopened_parameters': parameters(build['parameters']),
              'before_initial_conditions': baseline_initial, 'applied_initial_conditions': applied_initial,
              'after_initial_conditions': deepcopy(baseline_initial), 'reopened_initial_conditions': deepcopy(baseline_initial),
              'applied_inputs': deepcopy(spec['inputs']), 'requested_solver': deepcopy(solver),
              'configured_parameters': configured, 'effective_configuration': deepcopy(configured),
              'before_configuration': baseline_configuration, 'after_configuration': deepcopy(baseline_configuration),
              'reopened_configuration': deepcopy(baseline_configuration),
              'observed_solver_name': solver['name'], 'observed_solver_info': {'Solver': solver['name'], 'Type': solver['type'], step_field: solver['fixed_step'] if solver['name'] == 'ode4' else solver['max_step']},
              'saved_time': times, 'time_source': 'SimulationOutput.tout', 'stop_event_time': times[-1] if times else None,
              'stop_event': 'ReachedStopTime', 'error_message': '', 'errors': [], 'warnings': [],
              'last_warning_message': '', 'last_warning_identifier': '', 'output_count': len(spec['outputs']),
              'output_boundary_error': '', 'data_file': 'outputs.json', 'mat_file': 'outputs.mat',
              'state_data_file': 'states.json', 'state_mat_file': 'states.mat',
              'timing_info': {'WallClockTimestampStart': utc_text(reference), 'WallClockTimestampStop': utc_text(reference + timedelta(milliseconds=1)),
                              'InitializationElapsedWallTime': 0.0002, 'ExecutionElapsedWallTime': 0.0005,
                              'TerminationElapsedWallTime': 0.0003, 'TotalElapsedWallTime': 0.001}}
    for key in ['source_unchanged', 'owned_model_unchanged', 'configuration_restored', 'parameters_restored',
                'output_sampling_restored', 'initial_conditions_restored', 'input_sampling_restored', 'reopened', 'closed_without_save']:
        actual[key] = True
    for stem, records in [('output_sampling', output_sampling), ('input_sampling', input_sampling)]:
        for prefix in ['before', 'configured', 'after', 'reopened']: actual[prefix + '_' + stem] = deepcopy(records)
    savemat(directory / actual['raw_mat_file'], {'run_id': run_id, 'case_id': case['case_id'],
        'SYNTHETIC_NO_MATLAB': 'NOT A MATLAB SimulationOutput'}, format='5')
    if case['expectation'] == 'error':
        actual.update(stop_event='DiagnosticError', error_message='SYNTHETIC phase_h_controlled_missing_symbol',
                      errors=[{'identifier': 'Simulink:Parameters:InvParamSetting', 'message': 'SYNTHETIC phase_h_controlled_missing_symbol'}])
    if case['expectation'] == 'early_stop':
        actual.update(stop_event='Timeout', warnings=[{'identifier': 'Simulink:Commands:SimTimeExceededTimeOut', 'message': 'SYNTHETIC timeout'}])
    if case['expectation'] == 'no_output': actual['output_boundary_error'] = 'SYNTHETIC required output is absent'
    actual['states'] = [{**state, 'label': 'CSTATE', 'observed_unit': '', 'time': times,
                         'values': [float(state_values(t)[state['variable_id']]) for t in times], 'csv_file': f'state-{i + 1}.csv'} for i, state in enumerate(case['states'])]
    actual['outputs'] = [{**out, 'observed_unit': '', 'time': times,
                          'values': [float(state_values(t)[case['states'][-1]['variable_id']]) for t in times],
                          'csv_file': f'output-{i + 1}.csv'} for i, out in enumerate(spec['outputs'])]
    for records in [actual['states'], actual['outputs']]:
        for record in records:
            (directory / record['csv_file']).write_text(''.join(f'{t:.17g},{v:.17g}\n' for t, v in zip(record['time'], record['values'])), encoding='utf-8')
    write_json(directory / actual['data_file'], {'schema_version': 1, 'run_id': run_id, 'case_id': case['case_id'], 'outputs': actual['outputs']})
    write_json(directory / actual['state_data_file'], {'schema_version': 1, 'run_id': run_id, 'case_id': case['case_id'], 'states': actual['states']})
    output_mat = {'run_id': run_id, 'case_id': case['case_id'], 'saved_time': np.asarray(times, dtype=float).reshape(-1, 1),
                  'output_ports': np.asarray([r['port'] for r in actual['outputs']], dtype=float).reshape(-1, 1)}
    for name, key in [('output_variables', 'variable_id'), ('output_units', 'unit'), ('output_times', 'time'), ('output_values', 'values')]:
        output_mat[name] = _cells([r[key] for r in actual['outputs']])
    savemat(directory / actual['mat_file'], output_mat, format='5')
    state_mat = {'run_id': run_id, 'case_id': case['case_id']}
    for name, key in [('state_variables', 'variable_id'), ('state_units', 'unit'), ('state_paths', 'block_path'), ('state_labels', 'label'), ('state_times', 'time'), ('state_values', 'values')]:
        state_mat[name] = _cells([r[key] for r in actual['states']])
    savemat(directory / actual['state_mat_file'], state_mat, format='5')
    return actual


def make_h_analysis_profile(directory, a_profile, e_profile):
    """Build a clearly synthetic full-wire chain; never actual qualification."""
    from probe_h_analysis import make_request
    from validate_h_analysis_profile import analytic_state, derive_profile
    directory = Path(directory)
    executable = load_document(a_profile)['runtime']['executable']
    request = make_request(executable, directory, environment_profile=a_profile, simulation_profile=e_profile)
    directory.mkdir()
    names = trial.contract()['evidence']
    write_json(directory / names['input'], request)
    (directory / names['log']).write_text('SYNTHETIC H FORMAT TEST ONLY. NO MATLAB EXECUTION OR REAL QUALIFICATION.\n', encoding='utf-8')
    raw = deepcopy(load_document(Path(e_profile).parent / 'raw-simulation.json'))
    runtime_root = Path(raw['runtime']['matlabroot'])
    functions = []
    for name in request['required_functions']:
        path = runtime_root / 'toolbox' / 'fixture' / (name + '.m')
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists(): path.write_text('% SYNTHETIC H function identity fixture; never executable qualification\n', encoding='utf-8')
        functions.append({'name': name, 'path': str(path.resolve())})
    actuals = []
    qualification_floor = max(_time(load_document(path)['captured_at']) for path in (a_profile, e_profile))
    for case in request['cases']:
        actual = synthetic_native_case(case, directory / 'cases' / case['case_id'], request['run_id'],
                                      state_values=lambda t, c=case: {s['variable_id']: analytic_state(c, s['variable_id'], t) for s in c['states']},
                                      not_before=qualification_floor)
        actual['functions'] = deepcopy(functions)
        actuals.append(actual)
    starts = [x['started_at'] for x in actuals]
    stops = [x['finished_at'] for x in actuals]
    start, stop = min(map(_time, starts)), max(map(_time, stops))
    raw.update(schema_version=1, run_id=request['run_id'], channel=request['channel'], host_fingerprint=request['host_fingerprint'],
               input_identity=request['input_identity'], source_identity=request['source_identity'], status='completed', functions=functions,
               license_test=1, started_at=utc_text(start - timedelta(microseconds=1)), finished_at=utc_text(stop + timedelta(microseconds=1)), cases=actuals)
    process = {'process_state': 'completed', 'exit_code': 0, 'pid': 0, 'command': ['SYNTHETIC ONLY; NO MATLAB'],
               'execution_timeout': request['budget']['process_timeout'],
               'started_at': utc_text(start - timedelta(microseconds=2)), 'finished_at': utc_text(stop + timedelta(microseconds=2))}
    write_json(directory / names['raw'], raw)
    write_json(directory / names['process'], process)
    profile = derive_profile(raw, request, process)
    write_json(directory / names['profile'], profile)
    receipt = {'schema_version': 1, 'run_id': request['run_id'], 'sources': request['sources'], 'process': process,
               'runtime': profile['runtime'], 'artifacts': trial.artifact_manifest(directory, include_profile=True), 'errors': []}
    write_json(directory / names['profile_receipt'], receipt)
    return directory / names['profile']
