"""Source-bound hypothetical H trials; approved primary evidence is immutable.

All computation is explicit. Importing this module never executes MATLAB,
validates a project, records a decision, or changes project state.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import csv
import json
from datetime import datetime, timezone
import math
from pathlib import Path
import re
import time
import uuid

from probe_environment import _matlab_quote, _run_process, write_json
from runtime_common import ROOT, canonical_digest, contained_path, emit, host_fingerprint, load_document, sha256_file
from validate_environment import _official_function, _path, _time, _version_info, runtime_identity, validate_environment
from validate_implementation_profile import record_array, validate_build_spec
from validate_implementation_receipt import same_runtime
from validate_simulation_profile import (_read_outputs, finite, native_records_equal, numeric_vector,
                                         validate_run_spec, validate_simulation_profile)
from verification_common import assert_unchanged, input_manifest, limited_document, typed_equal

OPERATION = 'h.analysis_trials'
BUDGET_FIELDS = ('max_file_bytes', 'max_total_bytes', 'max_samples_per_output', 'max_groups',
                 'max_cases', 'process_timeout', 'simulation_timeout')
CASE_FIELDS = {'case_id', 'group_id', 'level_id', 'point_id', 'occurrence', 'run_spec', 'build_spec',
               'initial_conditions', 'states', 'simulation_timeout', 'expectation', 'warning_policy',
               'qualification_not_after'}
GROUP_FIELDS = {'group_id', 'point_id', 'occurrence', 'factor_values', 'roles', 'physical_snapshot',
                'physical_sha256', 'numeric_policy', 'context', 'case_ids'}
TIMING_FIELDS = ('InitializationElapsedWallTime', 'ExecutionElapsedWallTime',
                 'TerminationElapsedWallTime', 'TotalElapsedWallTime')
CONFIGURATION_FIELDS = ('Solver', 'SolverType', 'MaxStep', 'MinStep', 'InitialStep', 'RelTol',
    'AbsTol', 'FixedStep', 'ZeroCrossControl', 'StartTime', 'StopTime', 'SimulationMode',
    'SaveOutput', 'OutputSaveName', 'SaveFormat', 'DatasetSignalFormat', 'SaveTime',
    'TimeSaveName', 'SaveState', 'StateSaveName', 'SaveFinalState', 'SaveOperatingPoint',
    'SignalLogging', 'LoadExternalInput', 'ExternalInput', 'LimitDataPoints', 'Decimation')


def stable_utc(value):
    return _time(value).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def resolve_initial_value(text, parameters):
    """Resolve only a finite literal or one already registered scalar name."""
    if not isinstance(text, str): raise ValueError('approved Integrator initial must be text')
    stripped = text.strip()
    if re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,62}', stripped):
        matches = [p['value'] for p in parameters if p['code_name'] == stripped]
        if len(matches) != 1: raise ValueError('Integrator initial does not bind one registered scalar parameter')
        value = matches[0]
    else:
        if not re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?', stripped):
            raise ValueError('Integrator initial supports finite literals or registered names only')
        value = float(stripped)
    if not finite(value): raise ValueError('Integrator initial must resolve to a real finite scalar')
    return value


def assert_mat_identity(path, run_id, case_id):
    import numpy as np
    from scipy.io import loadmat
    mat = loadmat(path, variable_names=['run_id', 'case_id'], mat_dtype=True,
                  chars_as_strings=False, squeeze_me=False)
    for name, identity in [('run_id', run_id), ('case_id', case_id)]:
        value = mat.get(name)
        if value is None or value.dtype != np.dtype('U1') or value.shape != (1, len(identity)) or ''.join(value[0]) != identity:
            raise ValueError('MAT native run/case char-row identity differs: ' + name)


def assert_output_mat_shapes(path, outputs, saved):
    import numpy as np
    from scipy.io import loadmat
    mat = loadmat(path, variable_names=['output_times', 'output_values', 'saved_time'],
                  mat_dtype=True, squeeze_me=False)
    if mat['saved_time'].dtype != np.dtype('float64') or mat['saved_time'].shape != (len(saved), 1):
        raise ValueError('output MAT saved-time double column shape differs')
    for name in ('output_times', 'output_values'):
        if mat[name].dtype != np.dtype('O') or mat[name].shape != (len(outputs), 1):
            raise ValueError('output MAT native cell column differs')
        for index, item in enumerate(outputs):
            value = mat[name][index, 0]
            if value.dtype != np.dtype('float64') or value.shape != (len(item['time']), 1):
                raise ValueError('output MAT native double column shape differs')


def assert_case_functions(actual, functions, runtime_root):
    records = record_array(actual.get('functions'), 'case.functions')
    if not typed_equal(records, functions) or any(set(x) != {'name', 'path'} or not _official_function(x['path'], runtime_root) for x in records):
        raise ValueError('actual per-case official function inventory differs')


def read_native_timing(actual, directory, run_id, case_id):
    """Exact primitive MAT provenance plus documented clock-resolution bounds."""
    import numpy as np
    from scipy.io import loadmat
    policy = contract()['timing_provenance']
    timing, provenance = actual.get('timing_info'), actual.get('timing_provenance')
    fields = {'source', 'duration_fields', 'clock_resolution_seconds', 'duration_resolution_seconds',
              'call_started_at', 'call_finished_at', 'local_utc_offset_start', 'local_utc_offset_stop'}
    if not isinstance(timing, dict) or any(not finite(timing.get(k)) or timing[k] < 0 for k in TIMING_FIELDS):
        raise ValueError('native TimingInfo requires four finite nonnegative durations')
    if not isinstance(provenance, dict) or set(provenance) != fields or provenance['source'] != policy['source'] or not typed_equal(provenance['duration_fields'], list(TIMING_FIELDS)):
        raise ValueError('native TimingInfo exact source/field provenance differs')
    for key in ('clock_resolution_seconds', 'duration_resolution_seconds'):
        if not finite(provenance[key]) or provenance[key] != policy[key]:
            raise ValueError('native TimingInfo documented resolution differs')
    for key in ('local_utc_offset_start', 'local_utc_offset_stop'):
        if not finite(provenance[key]) or abs(provenance[key]) > 86400:
            raise ValueError('native TimingInfo actual local UTC offset differs')
    utc_pattern = r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z'
    for key in ('call_started_at', 'call_finished_at'):
        if not isinstance(provenance[key], str) or re.fullmatch(utc_pattern, provenance[key]) is None:
            raise ValueError('native TimingInfo invocation requires actual six-fraction UTC format')
    call_start, call_stop = (_time(provenance[k]) for k in ('call_started_at', 'call_finished_at'))
    case_start, case_stop = (_time(actual[k]) for k in ('started_at', 'finished_at'))
    if not case_start <= call_start <= call_stop <= case_stop:
        raise ValueError('native TimingInfo invocation is outside its actual case enclosure')
    clocks = []
    from datetime import timedelta
    for key, offset_key in (('WallClockTimestampStart', 'local_utc_offset_start'), ('WallClockTimestampStop', 'local_utc_offset_stop')):
        value = timing.get(key)
        if not isinstance(value, str) or re.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', value) is None:
            raise ValueError('native TimingInfo original local timestamp format differs')
        clock = datetime.strptime(value, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
        clocks.append(clock - timedelta(seconds=provenance[offset_key]))
    if clocks[0] > clocks[1]:
        raise ValueError('native TimingInfo timestamp order is impossible')
    radius = timedelta(seconds=policy['clock_resolution_seconds'])
    windows = [(max(call_start, clock - radius), min(call_stop, clock + radius)) for clock in clocks]
    if any(lo > hi for lo, hi in windows):
        raise ValueError('native TimingInfo timestamp quantization misses its actual invocation')
    durations = [timing[k] for k in TIMING_FIELDS]
    quantum = policy['duration_resolution_seconds']
    # Each documented microsecond value may differ by one quantum from its
    # underlying elapsed measurement. This is not a performance-claim tolerance.
    if abs(math.fsum(durations[:3]) - durations[3]) > 4 * quantum:
        raise ValueError('native TimingInfo components and total are inconsistent')
    elapsed = (call_stop - call_start).total_seconds()
    capture_quantum = policy['call_clock_resolution_seconds']
    if durations[3] > elapsed + quantum + 2 * capture_quantum or any(v > elapsed + quantum + 2 * capture_quantum for v in durations[:3]):
        raise ValueError('native TimingInfo duration exceeds its actual invocation enclosure')
    lower = max(0.0, (windows[1][0] - windows[0][1]).total_seconds())
    upper = (windows[1][1] - windows[0][0]).total_seconds()
    if upper < 0 or durations[3] + quantum < lower or max(0.0, durations[3] - quantum) > upper + 2 * capture_quantum:
        raise ValueError('native TimingInfo elapsed and timestamp quantization are incompatible')
    path = contained_path(directory, actual['raw_mat_file'])
    assert_mat_identity(path, run_id, case_id)
    names = policy['mat_fields']
    stored = loadmat(path, variable_names=names, mat_dtype=False, squeeze_me=False)
    for key in ('timing_durations', 'timing_utc_offsets', 'timing_resolutions'):
        if key not in stored or np.iscomplexobj(stored[key]):
            raise ValueError('native TimingInfo primitive MAT missing or complex: ' + key)
    mat = loadmat(path, variable_names=names, mat_dtype=True, chars_as_strings=False, squeeze_me=False)
    for key, values in [('timing_durations', durations),
                        ('timing_utc_offsets', [provenance['local_utc_offset_start'], provenance['local_utc_offset_stop']]),
                        ('timing_resolutions', [policy['clock_resolution_seconds'], quantum])]:
        value = mat[key]
        if value.dtype != np.dtype('float64') or value.shape != (len(values), 1) or value[:, 0].tolist() != values:
            raise ValueError('native TimingInfo primitive MAT double-column/JSON exact mismatch: ' + key)
    for key, value in [('timing_start_local', timing['WallClockTimestampStart']), ('timing_stop_local', timing['WallClockTimestampStop']),
                       ('timing_call_start_utc', provenance['call_started_at']), ('timing_call_stop_utc', provenance['call_finished_at'])]:
        field = mat.get(key)
        if field is None or field.dtype != np.dtype('U1') or field.shape != (1, len(value)) or ''.join(field[0]) != value:
            raise ValueError('native TimingInfo primitive MAT native char-row/JSON exact mismatch: ' + key)
    return deepcopy(timing), deepcopy(provenance)


def contract():
    return limited_document(ROOT / 'core/h_analysis_assurance_contract.yaml',
                            {'max_file_bytes': 1048576, 'max_total_bytes': 1048576})


def source_identities():
    from verification_common import repository_source_paths, stat_manifest
    repository_paths = repository_source_paths()
    paths = {Path(path).resolve() for path in repository_paths}
    paths.update(contained_path(ROOT, name) for name in contract()['source_files'])
    stat_manifest(paths, ROOT, contract()['hard_budget'])
    repository_paths.assert_authority_unchanged()
    identities = {path.relative_to(ROOT).as_posix(): sha256_file(path) for path in sorted(paths, key=str)}
    repository_paths.assert_authority_unchanged()
    return identities


def file_binding(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': sha256_file(path)}


def check_budget(budget, *, groups=0, cases=0):
    if not isinstance(budget, dict) or set(budget) != set(BUDGET_FIELDS):
        raise ValueError('native budget requires all seven explicit fields')
    hard = contract()['hard_budget']
    for key in BUDGET_FIELDS:
        value = budget[key]
        integer = key not in {'process_timeout', 'simulation_timeout'}
        if not finite(value) or value <= 0 or value > hard[key] or integer and type(value) is not int:
            raise ValueError('invalid native hard budget: ' + key)
    if budget['max_total_bytes'] < budget['max_file_bytes'] or budget['max_samples_per_output'] < 2:
        raise ValueError('native file/total/sample budgets are inconsistent')
    if groups > budget['max_groups'] or cases > budget['max_cases']:
        raise ValueError('complete point/three-level count exceeds reviewed native budget')


def preflight_request(request, *, role):
    """Budget the complete typed transitive read set before the first digest/load."""
    from verification_common import evidence_paths_for_request
    root = Path(request['bindings'].get('project_root', request['output_directory'])).resolve()
    paths = evidence_paths_for_request(request, root, request['budget'], role=role)
    return input_manifest(paths, root, request['budget'])


def physical_snapshot(spec, initial_conditions):
    return {'parameters': deepcopy(spec['parameters']), 'initial_conditions': deepcopy(initial_conditions),
            'inputs': deepcopy(spec['inputs'])}


def validate_case_spec(case, *, mode, budget):
    if not isinstance(case, dict) or set(case) != CASE_FIELDS:
        raise ValueError('trial case exact fields differ')
    if any(not isinstance(case[k], str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,119}', case[k])
           for k in ('case_id', 'group_id', 'point_id')):
        raise ValueError('safe owned case/group/point identifiers required')
    if type(case['level_id']) is not int or case['level_id'] not in {0, 1, 2} or type(case['occurrence']) is not int or case['occurrence'] < 1:
        raise ValueError('explicit level and occurrence identity required')
    if case['expectation'] not in {'success', 'error', 'early_stop', 'no_output'} or mode == 'trial' and case['expectation'] != 'success':
        raise ValueError('controlled negatives belong only to the fixed qualification probe')
    validate_run_spec(case['run_spec'])
    validate_build_spec(case['build_spec'])
    spec, build = case['run_spec'], case['build_spec']
    if spec['model_name'] != build['model_name'] or case['warning_policy'] != spec['warning_policy']:
        raise ValueError('trial baseline model or warning identity differs')
    if not finite(case['simulation_timeout']) or not 0 < case['simulation_timeout'] <= budget['simulation_timeout']:
        raise ValueError('case simulation timeout exceeds reviewed budget')
    _time(case['qualification_not_after'])
    baseline = {item['code_name']: item for item in build['parameters']}
    if len(spec['parameters']) != len(baseline) or any(p['code_name'] not in baseline or p['unit'] != baseline[p['code_name']]['unit'] for p in spec['parameters']):
        raise ValueError('trial may vary values only in the complete registered model workspace')
    blocks = {item['path']: item for item in build['blocks']}
    integrators = {path for path, block in blocks.items() if block['type'] == 'Integrator'}
    initials, states = record_array(case['initial_conditions'], 'case.initial_conditions'), record_array(case['states'], 'case.states')
    if len(initials) != len(integrators) or len(states) != len(integrators):
        raise ValueError('complete Integrator initial and state identity mapping required')
    for items, fields in ((initials, {'block_path', 'variable_id', 'unit', 'value'}),
                          (states, {'block_path', 'variable_id', 'unit'})):
        if {item.get('block_path') for item in items} != integrators or len({item.get('variable_id') for item in items}) != len(items):
            raise ValueError('unique exact Integrator/state mapping required')
        for item in items:
            if set(item) != fields or not isinstance(item['variable_id'], str) or not item['variable_id'] or not isinstance(item['unit'], str) or not item['unit'].strip() or 'value' in item and not finite(item['value']):
                raise ValueError('finite typed initial/state identity required')
    if any({k: item[k] for k in ('block_path', 'variable_id', 'unit')} != state for item, state in zip(initials, states)):
        raise ValueError('initial values and state mapping have different ordered identities')
    if not spec['outputs'] and case['expectation'] != 'no_output':
        raise ValueError('at least one observed output is required')
    if len(spec['outputs']) > 8 or len(states) > 8:
        raise ValueError('native scalar observable count exceeds hard boundary')
    for signal in spec['inputs']:
        if signal['interpolation'] == 'zoh' and len(set(signal['values'])) != 1:
            raise ValueError('hypothetical inputs are constant or continuous linear only')
        if len(signal['time']) > budget['max_samples_per_output']:
            raise ValueError('input knots exceed sample budget')
    return case


def validate_request(request):
    fields = {'schema_version', 'run_id', 'mode', 'channel', 'host_fingerprint', 'matlab_executable',
              'output_directory', 'sources', 'source_identity', 'required_functions', 'cases', 'groups',
              'bindings', 'budget', 'input_identity'}
    if not isinstance(request, dict) or set(request) != fields or type(request['schema_version']) is not int or request['schema_version'] != 1 or request['mode'] not in {'probe', 'trial'} or request['channel'] != 'matlab_batch':
        raise ValueError('H trial request exact identity surface differs')
    uuid.UUID(request['run_id'])
    if request['host_fingerprint'] != host_fingerprint() or request['sources'] != source_identities() or request['source_identity'] != canonical_digest(request['sources']) or request['required_functions'] != contract()['required_functions']:
        raise ValueError('H native current source/host/function identity differs')
    if request['input_identity'] != canonical_digest({k: v for k, v in request.items() if k != 'input_identity'}):
        raise ValueError('complete H native request identity differs')
    cases, groups = record_array(request['cases'], 'request.cases'), record_array(request['groups'], 'request.groups')
    check_budget(request['budget'], groups=len(groups), cases=len(cases))
    if not cases or len({case.get('case_id') for case in cases}) != len(cases):
        raise ValueError('nonempty complete unique native case ledger required')
    for case in cases:
        validate_case_spec(case, mode=request['mode'], budget=request['budget'])
    by_id = {case['case_id']: case for case in cases}
    if len({g.get('group_id') for g in groups}) != len(groups):
        raise ValueError('unique group identities required')
    used = set()
    for group in groups:
        if set(group) != GROUP_FIELDS or len(group['case_ids']) != 3 or len(set(group['case_ids'])) != 3:
            raise ValueError('exact group fields and three independent level cases required')
        if group['physical_sha256'] != canonical_digest(group['physical_snapshot']):
            raise ValueError('complete hypothetical physical snapshot identity differs')
        for index, case_id in enumerate(group['case_ids']):
            case = by_id.get(case_id)
            if case is None or case_id in used or case['level_id'] != index or any(case[k] != group[k] for k in ('group_id', 'point_id', 'occurrence')) or not typed_equal(physical_snapshot(case['run_spec'], case['initial_conditions']), group['physical_snapshot']):
                raise ValueError('ordered trial group/level/physical identity differs')
            used.add(case_id)
        base = deepcopy(by_id[group['case_ids'][0]]['run_spec'])
        for case_id in group['case_ids'][1:]:
            other = deepcopy(by_id[case_id]['run_spec'])
            base.pop('solver', None)
            other.pop('solver', None)
            if not typed_equal(base, other):
                raise ValueError('three levels changed non-numerical execution settings')
    if request['mode'] == 'trial' and used != set(by_id):
        raise ValueError('every actual trial must belong to exactly one numerical triplet')
    return request


def observed_runtime(raw, request):
    functions = record_array(raw.get('functions'), 'raw.functions')
    names = {item.get('name'): item.get('path') for item in functions}
    if len(names) != len(functions) or set(names) != set(contract()['required_functions']) or any(not _official_function(path, raw['runtime']['matlabroot']) for path in names.values()):
        raise ValueError('H native actual official function resolution differs')
    # Installation identities have a separate maintained machine boundary.
    # They never grant business-data or review paths external graph authority.
    root = Path(raw['runtime']['matlabroot']).resolve()
    executable = Path(request['matlab_executable']).resolve()
    if not executable.is_relative_to(root): raise ValueError('actual MATLAB executable leaves official installation root')
    files = {executable, root / 'VersionInfo.xml'} | {Path(p).resolve() for p in names.values() if Path(p).is_file()}
    from verification_common import stat_manifest
    stat_manifest(files, root, contract()['installation_identity_budget'])
    return runtime_identity({**raw, 'operations': [{'operation_id': OPERATION, 'functions': functions}]}, request['matlab_executable'])


def assert_parameter_records(records, expected):
    fields = {'code_name', 'value', 'unit', 'class', 'data_type', 'value_class', 'shape', 'is_real'}
    if not isinstance(records, list) or len(records) != len(expected):
        raise ValueError('actual complete workspace snapshot required')
    for actual, item in zip(records, expected):
        wanted = {**item, 'unit': item['unit'] or '', 'class': 'Simulink.Parameter',
                  'data_type': 'double', 'value_class': 'double', 'shape': [1, 1], 'is_real': True}
        if set(actual) != fields or actual.get('is_real') is not True or not isinstance(actual.get('shape'), list) or any(type(x) is not int for x in actual['shape']) or not native_records_equal([actual], [wanted]):
            raise ValueError('actual parameter dtype/shape/unit/value differs')


def _read_states(directory, actual, case, run_id, budget):
    import numpy as np
    from scipy.io import loadmat
    items = record_array(actual.get('states'), 'case.states')
    expected = case['states']
    if len(items) != len(expected):
        raise ValueError('complete native state set required')
    data = limited_document(contained_path(directory, actual['state_data_file']), budget)
    if set(data) != {'schema_version', 'run_id', 'case_id', 'states'} or type(data['schema_version']) is not int or data['schema_version'] != 1 or data['run_id'] != run_id or data['case_id'] != case['case_id'] or not typed_equal(data['states'], items):
        raise ValueError('native state JSON exact identity/records differ')
    path = contained_path(directory, actual['state_mat_file'])
    names = ['run_id', 'case_id', 'state_variables', 'state_units', 'state_paths', 'state_labels', 'state_times', 'state_values']
    stored = loadmat(path, variable_names=names, mat_dtype=False, squeeze_me=False)
    if any(k not in stored for k in names) or any(np.iscomplexobj(value) for name in ('state_times', 'state_values') for value in stored[name].flat):
        raise ValueError('state MAT missing or complex storage')
    mat = loadmat(path, variable_names=names, mat_dtype=True, chars_as_strings=False, squeeze_me=False)
    for name, identity in (('run_id', run_id), ('case_id', case['case_id'])):
        value = mat[name]
        if value.dtype != np.dtype('U1') or value.shape != (1, len(identity)) or ''.join(value[0]) != identity:
            raise ValueError('state MAT native char-row identity differs')
    for name in names[2:]:
        if mat[name].dtype != np.dtype('O') or mat[name].shape != (len(items), 1):
            raise ValueError('state MAT native cell-column shape differs')
    for index, (item, declaration) in enumerate(zip(items, expected)):
        fields = {'block_path', 'variable_id', 'unit', 'label', 'observed_unit', 'time', 'values', 'csv_file'}
        if set(item) != fields or any(item[k] != declaration[k] for k in ('block_path', 'variable_id', 'unit')) or item['label'] != 'CSTATE' or not isinstance(item['observed_unit'], str) or item['observed_unit'] not in {'', declaration['unit']}:
            raise ValueError('actual BlockPath/CSTATE/unit state identity differs')
        time, values = numeric_vector(item['time'], 'state.time'), numeric_vector(item['values'], 'state.values')
        if len(time) != len(values) or len(time) > budget['max_samples_per_output'] or any(a >= b for a, b in zip(time, time[1:])):
            raise ValueError('state native sample shape/order/budget differs')
        for name, key in (('state_variables', 'variable_id'), ('state_units', 'unit'), ('state_paths', 'block_path'), ('state_labels', 'label')):
            value = mat[name][index, 0]
            if value.dtype != np.dtype('U1') or value.shape != (1, len(item[key])) or ''.join(value[0]) != item[key]:
                raise ValueError('state MAT native char cell differs: ' + name)
        for name, values_list in (('state_times', time), ('state_values', values)):
            value = mat[name][index, 0]
            if value.dtype != np.dtype('float64') or value.shape != (len(values_list), 1) or value[:, 0].tolist() != values_list:
                raise ValueError('state MAT double column/JSON exact mismatch')
        with contained_path(directory, item['csv_file']).open(encoding='utf-8', newline='') as stream:
            rows = list(csv.reader(stream))
        if len(rows) != len(time) or any(len(row) != 2 for row in rows) or [[float(x) for x in row] for row in rows] != [[t, v] for t, v in zip(time, values)]:
            raise ValueError('state CSV complete exact numeric mismatch')
        spec = case['run_spec']
        from validate_numerical_verification import time_tolerance
        if abs(time[0] - spec['start_time']) > time_tolerance(spec['start_time']) or abs(time[-1] - spec['stop_time']) > time_tolerance(spec['stop_time']):
            raise ValueError('native state interval incomplete')
        initial = case['initial_conditions'][index]['value']
        if values[0] != initial:
            raise ValueError('actual native initial state does not equal the reviewed trial override')
    return items


def assert_case(actual, case, directory, run_id, budget):
    """Read actual evidence independently; no applied declaration is trusted alone."""
    directory = Path(directory)
    if actual.get('case_id') != case['case_id'] or actual.get('attempted') is not True or actual.get('completed') is not True or actual.get('framework_error'):
        raise ValueError('native trial was not technically completed: ' + str(actual.get('framework_error')))
    if any(actual.get(key) is not True for key in ('source_unchanged', 'owned_model_unchanged', 'configuration_restored',
            'parameters_restored', 'output_sampling_restored', 'initial_conditions_restored', 'input_sampling_restored', 'reopened', 'closed_without_save')):
        raise ValueError('actual owned/base/configuration/parameter/IC/input restoration failed')
    before_config = actual.get('before_configuration')
    if not isinstance(before_config, dict) or set(before_config) != set(CONFIGURATION_FIELDS) or any(not isinstance(value, str) for value in before_config.values()):
        raise ValueError('actual full solver/logging configuration snapshot missing')
    if any(not typed_equal(actual.get(key), before_config) for key in ('after_configuration', 'reopened_configuration')):
        raise ValueError('actual full solver/logging configuration restoration differs')
    spec, build = case['run_spec'], case['build_spec']
    for key in ('before_parameters', 'after_parameters', 'reopened_parameters'):
        assert_parameter_records(actual.get(key), build['parameters'])
    assert_parameter_records(actual.get('applied_parameters'), spec['parameters'])
    initial_before = [{'block_path': x['block_path'], 'value': next(b['parameters']['InitialCondition'] for b in build['blocks'] if b['path'] == x['block_path'])} for x in case['initial_conditions']]
    applied_initial = [{'block_path': x['block_path'], 'value': format(x['value'], '.17g')} for x in case['initial_conditions']]
    for key in ('before_initial_conditions', 'after_initial_conditions', 'reopened_initial_conditions'):
        if actual.get(key) != initial_before:
            raise ValueError('actual approved Integrator initial-condition restoration differs')
    if actual.get('applied_initial_conditions') != applied_initial:
        raise ValueError('actual SimulationInput initial-condition override differs')
    for stem, expected in (('output_sampling', [{'port': x['port'], 'block_path': x['block_path'], 'sample_time': '0'} for x in spec['outputs']]),
                           ('input_sampling', [{'port': x['port'], 'block_path': x['block_path'], 'interpolate': 'on' if x['interpolation'] == 'linear' else 'off'} for x in spec['inputs']])):
        before = actual.get('before_' + stem)
        if not isinstance(before, list) or len(before) != len(expected) or any(not isinstance(a, dict) or set(a) != set(e) or type(a.get('port')) is not int or a['port'] <= 0 or any(a[k] != e[k] for k in ('port', 'block_path')) or not isinstance(a['sample_time' if stem == 'output_sampling' else 'interpolate'], str) for a, e in zip(before, expected)):
            raise ValueError('actual complete sampling surface missing')
        if not typed_equal(actual.get('configured_' + stem), expected) or any(not typed_equal(actual.get(k + '_' + stem), before) for k in ('after', 'reopened')):
            raise ValueError('actual sampling override/restoration differs: ' + stem)
    applied_inputs = actual.get('applied_inputs', [])
    if not isinstance(applied_inputs, list) or any(not isinstance(x, dict) or any(not isinstance(x.get(k), list) or not all(finite(v) for v in x[k]) for k in ('time', 'values')) for x in applied_inputs) or not native_records_equal(applied_inputs, spec['inputs']):
        raise ValueError('actual SimulationInput Dataset time/value/interpolation differs')
    owned = contained_path(directory, spec['model_name'] + '.slx')
    if _path(actual.get('model_file', '')) != _path(owned) or _path(actual.get('source_model_file', '')) != _path(spec['model_path']) or sha256_file(owned) != sha256_file(spec['model_path']):
        raise ValueError('actual owned model path/bytes differ from immutable baseline')
    returned = contained_path(directory, actual.get('raw_mat_file', ''))
    if actual.get('simulation_returned') is not True or not returned.is_file() or not returned.stat().st_size:
        raise ValueError('actual returned SimulationOutput was not immediately preserved')
    assert_mat_identity(returned, run_id, case['case_id'])
    timing, timing_provenance = read_native_timing(actual, directory, run_id, case['case_id'])
    saved = numeric_vector(actual.get('saved_time'), 'native.tout', nonempty=False)
    if actual.get('time_source') != 'SimulationOutput.tout' or saved and not finite(actual.get('stop_event_time')) or actual.get('stop_event_time') != (saved[-1] if saved else None) or any(a > b for a, b in zip(saved, saved[1:])):
        raise ValueError('actual termination time is not preserved native tout')
    for key in ('warnings', 'errors'):
        record_array(actual.get(key), 'case.' + key)
    expectation = case['expectation']
    if expectation == 'error':
        if actual.get('stop_event') != 'DiagnosticError' or 'phase_h_controlled_missing_symbol' not in actual.get('error_message', '') or not any(x.get('identifier') == 'Simulink:Parameters:InvParamSetting' for x in actual['errors']):
            raise ValueError('actual controlled H missing-symbol error not observed')
        return {'complete': False, 'outputs': [], 'states': [], 'timing_info': timing, 'timing_provenance': timing_provenance}
    if expectation == 'early_stop':
        if str(actual.get('stop_event')).lower() != 'timeout' or actual.get('error_message') != '' or actual['errors'] or not saved or saved[-1] >= spec['stop_time'] or not any(x.get('identifier') == 'Simulink:Commands:SimTimeExceededTimeOut' for x in actual['warnings']):
            raise ValueError('actual controlled H timeout evidence missing')
        return {'complete': False, 'outputs': [], 'states': [], 'timing_info': timing, 'timing_provenance': timing_provenance}
    if actual.get('error_message') != '' or actual['errors'] or actual.get('stop_event') != 'ReachedStopTime' or not saved or saved[-1] != spec['stop_time']:
        raise ValueError('actual simulation did not reach reviewed stop without errors')
    if expectation == 'no_output':
        if type(actual.get('output_count')) is not int or actual['output_count'] != 0 or not actual.get('output_boundary_error'):
            raise ValueError('actual controlled missing-output boundary not observed')
        return {'complete': False, 'outputs': [], 'states': [], 'timing_info': timing, 'timing_provenance': timing_provenance}
    if case['warning_policy'] == 'reject' and (actual['warnings'] or actual.get('last_warning_message') or actual.get('last_warning_identifier')):
        raise ValueError('source-reviewed warning policy rejected native diagnostics')
    if not isinstance(actual.get('requested_solver'), dict) or not native_records_equal([actual['requested_solver']], [spec['solver']]):
        raise ValueError('actual requested solver differs')
    configured, effective, info = actual.get('configured_parameters'), actual.get('effective_configuration'), actual.get('observed_solver_info')
    if not all(isinstance(x, dict) for x in (configured, effective, info)):
        raise ValueError('actual public solver metadata missing')
    for key, field in (('name', 'Solver'), ('type', 'SolverType'), ('fixed_step', 'FixedStep'), ('max_step', 'MaxStep'), ('min_step', 'MinStep'), ('initial_step', 'InitialStep'), ('rel_tol', 'RelTol'), ('abs_tol', 'AbsTol'), ('zero_crossing', 'ZeroCrossControl')):
        value = spec['solver'][key]
        if key == 'type': value = {'fixed-step': 'Fixed-step', 'variable-step': 'Variable-step'}[value]
        if value is not None and (configured.get(field) != value or key in {'fixed_step', 'max_step', 'min_step', 'initial_step', 'rel_tol', 'abs_tol'} and not finite(configured.get(field))):
            raise ValueError('actual configured solver parameter differs: ' + field)
    if not finite(effective.get('StartTime')) or not finite(effective.get('StopTime')) or effective['StartTime'] != spec['start_time'] or effective['StopTime'] != spec['stop_time'] or effective.get('SimulationMode') != 'normal':
        raise ValueError('actual public interval/mode metadata differs')
    continuous = bool(case['states'])
    name = spec['solver']['name'] if continuous else ('FixedStepDiscrete' if spec['solver']['name'] == 'ode4' else 'VariableStepDiscrete')
    field = 'FixedStepSize' if spec['solver']['name'] == 'ode4' else 'MaxStepSize'
    if info.get('Solver') != name or actual.get('observed_solver_name') != name or effective.get('Solver') != name or str(info.get('Type', '')).lower() != spec['solver']['type'] or not finite(info.get(field)) or info[field] != spec['solver']['fixed_step' if field == 'FixedStepSize' else 'max_step']:
        raise ValueError('actual effective solver/type/step metadata differs')
    for output in actual.get('outputs', []):
        if not isinstance(output.get('time'), list) or len(output['time']) > budget['max_samples_per_output'] or not isinstance(output.get('values'), list) or len(output['values']) > budget['max_samples_per_output']:
            raise ValueError('native output exceeds sample budget before MAT read')
    data = limited_document(contained_path(directory, actual['data_file']), budget)
    if data.get('case_id') != case['case_id']:
        raise ValueError('native output JSON case identity differs')
    outputs = _read_outputs(directory, actual, spec, run_id)
    assert_mat_identity(contained_path(directory, actual['mat_file']), run_id, case['case_id'])
    assert_output_mat_shapes(contained_path(directory, actual['mat_file']), outputs, saved)
    if type(actual.get('output_count')) is not int or actual['output_count'] != len(outputs):
        raise ValueError('actual output cardinality differs')
    states = _read_states(directory, actual, case, run_id, budget)
    from validate_numerical_verification import time_tolerance
    for item in outputs + states:
        if abs(item['time'][0] - spec['start_time']) > time_tolerance(spec['start_time']) or abs(item['time'][-1] - spec['stop_time']) > time_tolerance(spec['stop_time']):
            raise ValueError('native output interval incomplete')
        limit = spec['solver']['fixed_step'] if spec['solver']['name'] == 'ode4' else spec['solver']['max_step']
        if max(b - a for a, b in zip(item['time'], item['time'][1:])) > limit + 1e-10 * max(1, limit):
            raise ValueError('actual logged output/state step exceeds configured step limit')
    return {'complete': True, 'outputs': outputs, 'states': states, 'timing_info': timing, 'timing_provenance': timing_provenance}


def artifact_manifest(directory, *, include_profile=False):
    """Exact owned file set, including partial/error artifacts, never just successes."""
    directory = Path(directory).resolve()
    names = contract()['evidence']
    excluded = {names['profile_receipt'], names['run_receipt']}
    if not include_profile: excluded.add(names['profile'])
    files = sorted(path for path in directory.rglob('*') if path.is_file() and path.relative_to(directory).parts[0] not in {'cache', 'codegen'})
    budget_path = directory / names['input']
    budget = load_document(budget_path)['budget'] if budget_path.exists() else contract()['hard_budget']
    total = sum(path.stat().st_size for path in files)
    if total > budget['max_total_bytes'] or any(path.stat().st_size > budget['max_file_bytes'] for path in files):
        raise ValueError('actual native artifacts exceed whole-batch byte budget')
    result = {}
    for path in files:
        relative = path.relative_to(directory).as_posix()
        if relative in excluded: continue
        key = next((key for key, name in names.items() if name == relative), 'artifact:' + relative)
        result[key] = {'file': relative, 'sha256': sha256_file(path)}
    return result


def execute_request(request, *, process_timeout_limit=None):
    cap_entry = time.monotonic()
    # The complete expanded request and transitive set are checked before its
    # owned directory is created, and the exact measured bytes are persisted.
    from verification_common import evidence_paths_for_request, serialized_request_bytes
    root = Path(request['bindings'].get('project_root', request['output_directory'])).resolve()
    paths = evidence_paths_for_request(request, root, request['budget'], role='qualification_h_request' if request['mode'] == 'probe' else 'h_trial_request')
    serialized = serialized_request_bytes(request, paths, root, request['budget'])
    before = input_manifest(paths, root, request['budget'])
    validate_request(request)
    forecast_native_report(request)
    if process_timeout_limit is not None:
        if not finite(process_timeout_limit) or process_timeout_limit <= 0:
            raise ValueError('parent process timeout cap must be finite and positive')
    directory, names = Path(request['output_directory']), contract()['evidence']
    directory.mkdir(parents=True, exist_ok=False)
    (directory / names['input']).write_bytes(serialized)
    assert_unchanged(before)
    statement = "addpath('{}'); run_h_analysis_trials('{}')".format(_matlab_quote(ROOT / 'scripts/matlab'), _matlab_quote(directory / names['input']))
    import os
    command = [request['matlab_executable']] + (['-wait'] if os.name == 'nt' else []) + ['-batch', statement, '-logfile', str(directory / names['log'])]
    timeout = request['budget']['process_timeout']
    if process_timeout_limit is not None:
        remaining = process_timeout_limit - (time.monotonic() - cap_entry)
        if remaining <= 0: raise ValueError('parent timeout budget exhausted before any native invocation')
        timeout = min(timeout, remaining)
    process, console = _run_process(command, directory, timeout)
    process['execution_timeout'] = timeout
    write_json(directory / names['process'], process)
    log = directory / names['log']
    if not log.exists(): log.write_text(console, encoding='utf-8')
    elif console:
        with log.open('a', encoding='utf-8') as stream: stream.write('\nRunner console:\n' + console)
    if not (directory / names['raw']).exists():
        write_json(directory / names['raw'], {'schema_version': 1, 'run_id': request['run_id'], 'status': 'failed',
            'channel': request['channel'], 'host_fingerprint': request['host_fingerprint'], 'input_identity': request['input_identity'],
            'source_identity': request['source_identity'], 'started_at': process['started_at'], 'finished_at': process['finished_at'],
            'runtime': None, 'functions': [], 'cases': [{'case_id': case['case_id'], 'attempted': False, 'completed': False,
                'started_at': '', 'finished_at': '', 'framework_error': {'identifier': 'PhaseH:NativeNotStarted', 'message': 'native raw report absent; process preserved'}} for case in request['cases']],
            'error': 'native raw report absent; process preserved'})
    return process


def forecast_native_report(request):
    """Forecast every emitted array, key and metadata surface before launch.

    Symbolic repeated arrays avoid materializing a large speculative document.
    Four-space PrettyPrint indentation and ASCII escaping bound actual UTF-8
    JSON; finite numeric tokens reserve 32 bytes before indentation.
    """
    from verification_common import graph_limit
    def measure(value, depth=0):
        indent = 4 * (depth + 1)
        if isinstance(value, tuple):
            count, child = value
            nodes, size = measure(child, depth + 1)
            return 1 + count * nodes, 2 + 4 * depth + count * (size + indent + 2)
        if isinstance(value, dict):
            nodes, size = 1 + len(value), 2 + 4 * depth
            for key, child in value.items():
                child_nodes, child_size = measure(child, depth + 1)
                nodes += child_nodes
                size += len(json.dumps(key, ensure_ascii=True).encode('ascii')) + child_size + indent + 4
            return nodes, size
        if isinstance(value, list):
            nodes, size = 1, 2 + 4 * depth
            for child in value:
                child_nodes, child_size = measure(child, depth + 1)
                nodes += child_nodes
                size += child_size + indent + 2
            return nodes, size
        if isinstance(value, str): return 1, len(json.dumps(value, ensure_ascii=True).encode('ascii'))
        return 1, 32

    installation_prefix = str(Path(request.get('matlab_executable', 'matlab')).parent.parent)
    function_path_bound = 'x' * (512 + len(installation_prefix.encode('utf-8')))
    functions = [{'name': name, 'path': function_path_bound} for name in request.get('required_functions', contract()['required_functions'])]
    # Known data copied from request strings is measured at its real escaped
    # size, including arbitrary legal units. Fixed native metadata reserves its
    # scalar fields, complete configurations, diagnostics and function paths.
    records, sample_numbers = [], 0
    for case in request['cases']:
        spec = case['run_spec']
        if spec['solver']['type'] == 'fixed-step':
            count = int(round((spec['stop_time'] - spec['start_time']) / spec['solver']['fixed_step'])) + 1
            if count > request['budget']['max_samples_per_output']:
                raise ValueError('complete fixed native grid exceeds prior sample budget')
        else:
            count = request['budget']['max_samples_per_output']
        sample_numbers += count * (1 + 2 * (len(spec['outputs']) + len(case['states'])))
        sample_numbers += sum(len(signal['time']) + len(signal['values']) for signal in spec['inputs'])
        def parameters(items):
            return [{**item, 'class': 'Simulink.Parameter', 'data_type': 'double', 'value_class': 'double',
                     'shape': [1, 1], 'is_real': True} for item in items]
        record = {name: 'x' * 128 for name in (
            'case_id', 'model_file', 'source_model_file', 'mat_file', 'raw_mat_file', 'data_file',
            'state_mat_file', 'state_data_file', 'stop_event', 'time_source', 'observed_solver_name',
            'started_at', 'finished_at', 'error_message', 'last_warning_message', 'last_warning_identifier', 'output_boundary_error')}
        record.update(case_id=case['case_id'], model_file=str(Path(request.get('output_directory', '.')) / 'cases' / case['case_id'] / (spec['model_name'] + '.slx')),
                      source_model_file=spec['model_path'], functions=functions, requested_solver=spec['solver'],
                      saved_time=(count, 0.0), stop_event_time=0.0, output_count=len(spec['outputs']))
        for name in ('attempted', 'completed', 'simulation_returned', 'source_unchanged', 'owned_model_unchanged',
                     'configuration_restored', 'parameters_restored', 'output_sampling_restored', 'initial_conditions_restored',
                     'input_sampling_restored', 'reopened', 'closed_without_save'): record[name] = True
        for key in ('before_configuration', 'after_configuration', 'reopened_configuration'):
            record[key] = {field: 'x' * 128 for field in CONFIGURATION_FIELDS}
        for key in ('configured_parameters', 'effective_configuration', 'observed_solver_info'):
            record[key] = {field: 'x' * 128 for field in CONFIGURATION_FIELDS}
        for prefix in ('before', 'after', 'reopened'):
            record[prefix + '_parameters'] = parameters(case['build_spec']['parameters'])
        record['applied_parameters'] = parameters(spec['parameters'])
        initial = [{**item, 'value': 'x' * 64} for item in case['initial_conditions']]
        baseline_blocks = {block['path']: block for block in case['build_spec']['blocks']}
        for item in initial:
            item['value'] = baseline_blocks[item['block_path']]['parameters']['InitialCondition'] + 'x' * 64
        for prefix in ('before', 'applied', 'after', 'reopened'): record[prefix + '_initial_conditions'] = initial
        for prefix in ('before', 'configured', 'after', 'reopened'):
            record[prefix + '_input_sampling'] = [{**{key: signal[key] for key in ('port', 'block_path')}, 'interpolate': 'off'} for signal in spec['inputs']]
            record[prefix + '_output_sampling'] = [{**{key: signal[key] for key in ('port', 'block_path')}, 'sample_time': 'x' * 64} for signal in spec['outputs']]
        record['applied_inputs'] = [{**signal, 'time': (len(signal['time']), 0.0), 'values': (len(signal['values']), 0.0)} for signal in spec['inputs']]
        record['outputs'] = [{**output, 'observed_unit': output['unit'] or '', 'time': (count, 0.0), 'values': (count, 0.0), 'csv_file': case['case_id'] + '-output-123.csv'} for output in spec['outputs']]
        record['states'] = [{**state, 'label': 'CSTATE', 'observed_unit': state['unit'], 'time': (count, 0.0), 'values': (count, 0.0), 'csv_file': case['case_id'] + '-state-123.csv'} for state in case['states']]
        record['timing_info'] = {**{key: 0.0 for key in TIMING_FIELDS}, 'WallClockTimestampStart': 'x' * 19, 'WallClockTimestampStop': 'x' * 19, 'ProfilerData': 'x' * 128}
        record['timing_provenance'] = {'source': contract()['timing_provenance']['source'], 'duration_fields': list(TIMING_FIELDS),
            'clock_resolution_seconds': 1.0, 'duration_resolution_seconds': 1e-6, 'call_started_at': 'x' * 27,
            'call_finished_at': 'x' * 27, 'local_utc_offset_start': 0.0, 'local_utc_offset_stop': 0.0}
        # These reserves cover fixed normal and controlled qualification
        # diagnostics; arbitrary diagnostic content still passes the actual
        # complete-document gate before any successful receipt is accepted.
        record['warnings'] = record['errors'] = (8, {'phase': 'x' * 128, 'time': 0.0, 'class': 'x' * 128, 'identifier': 'x' * 512, 'message': 'x' * 2048})
        record['framework_error'] = {'identifier': 'x' * 512, 'message': 'x' * 2048, 'report': 'x' * 4096,
            'stack': (8, {'file': 'x' * 512, 'name': 'x' * 128, 'line': 1})}
        records.append(record)
    shape = {'schema_version': 1, 'run_id': request.get('run_id', 'x' * 36), 'status': 'completed', 'channel': 'matlab_batch',
             'host_fingerprint': 'x' * 128, 'input_identity': 'x' * 64, 'source_identity': 'x' * 64,
             'started_at': 'x' * 27, 'finished_at': 'x' * 27, 'runtime': {'release': 'R2025b', 'version': 'x' * 128, 'matlabroot': installation_prefix + 'x' * 512, 'platform': 'x' * 128},
             'installed_products': (128, {'Name': 'x' * 128, 'Version': 'x' * 64, 'Release': 'x' * 32, 'Date': 'x' * 64}),
             'license_test': 1, 'licenses_inuse': (128, {'feature': 'x' * 128, 'user': 'x' * 128}), 'functions': functions, 'cases': records}
    nodes, byte_bound = measure(shape)
    if nodes > graph_limit(request['budget'], 'max_document_nodes'):
        raise ValueError('complete native raw report forecast exceeds document node budget')
    if byte_bound > request['budget']['max_file_bytes']:
        raise ValueError('complete native raw report forecast exceeds declared file byte budget')
    return {'sample_numbers': sample_numbers, 'overhead_nodes': nodes - sample_numbers, 'nodes': nodes, 'bytes_upper_bound': byte_bound}


_HISTORICAL_REPLAY_MARKER = object()


def _historical_request_context(request):
    return (request['run_id'], request['input_identity'], request['source_identity'],
            request['mode'], request['channel'], request['host_fingerprint'],
            request['matlab_executable'], request['output_directory'],
            request['bindings']['project_root'], canonical_digest(request['budget']))


class _HistoricalReplay:
    """Receipt-owned scope around the shared live-session capability.

    This object is never accepted from a public API or emitted in a report.
    Full in-memory request/raw identities are checked once at assessment entry;
    subsequent cases remain bound to that exact request object and context.
    """
    __slots__ = ('_marker', '_identity', '_capability', '_request', '_raw', '_context', '_request_digest',
                 '_raw_digest', '_directory', '_receipt', '_active')

    def __init__(self, marker, capability, request, raw, directory):
        self._marker = marker
        # Copies retain this integer, but their own object identity differs.
        # The seal adds no self-reference or request retention to the session.
        self._identity = id(self)
        self._capability = capability
        self._request = request
        self._raw = raw
        self._context = _historical_request_context(request)
        self._request_digest = canonical_digest(request)
        self._raw_digest = canonical_digest(raw)
        self._directory = Path(directory).resolve()
        self._receipt = self._directory / contract()['evidence']['run_receipt']
        self._active = True

    def matches(self, request, *, raw=None, directory=None):
        if self._marker is not _HISTORICAL_REPLAY_MARKER or self._identity != id(self) or not self._active or self._request is not request:
            return False
        if self._context != _historical_request_context(request):
            return False
        if raw is not None and (canonical_digest(raw) != self._raw_digest or canonical_digest(request) != self._request_digest):
            return False
        if directory is not None and (Path(directory).resolve() != self._directory or
                self._receipt != Path(directory).resolve() / contract()['evidence']['run_receipt']):
            return False
        return True


def _mint_historical_replay(request, raw, directory):
    """Called only after the real historical receipt's original full guards."""
    import sys
    caller = sys._getframe(1)
    if caller.f_code.co_name != '_validate_h_analysis_trial_receipt' or \
            Path(caller.f_code.co_filename).resolve() != ROOT / 'scripts/validate_h_analysis_trial_receipt.py':
        return None
    from verification_common import _historical_validation_capability
    if request['mode'] != 'trial': return None
    capability = _historical_validation_capability(request['bindings']['project_root'])
    if capability is None: return None
    return _HistoricalReplay(_HISTORICAL_REPLAY_MARKER, capability, request, raw, directory)


def _finish_historical_replay(replay, *, complete):
    if not isinstance(replay, _HistoricalReplay) or replay._identity != id(replay) or not replay._active: return
    from verification_common import _commit_historical_validation
    try:
        if complete is True and not replay.matches(replay._request, raw=replay._raw, directory=replay._directory):
            _commit_historical_validation(replay._capability, complete=False)
            raise ValueError('historical receipt-owned request/raw scope changed before publication')
        _commit_historical_validation(replay._capability, complete=complete is True)
    finally:
        replay._active = False


def _collect_qualification_facts(request, case, started_at, *, include_h):
    """Original full profile consumers establish facts, never caller reports."""
    b = request['bindings']
    required = b['required_A_operations']
    for name in ('environment_profile', 'environment_receipt', 'simulation_profile', 'simulation_profile_receipt') + (('h_analysis_profile', 'h_analysis_profile_receipt') if include_h else ()):
        binding = b[name]
        if sha256_file(binding['path']) != binding['sha256']:
            raise ValueError('execution-time qualification bytes changed: ' + name)
    a = validate_environment(b['environment_profile']['path'], required_operations=required, now=started_at, expected_host=request['host_fingerprint'])
    e = validate_simulation_profile(b['simulation_profile']['path'], now=started_at, required_solver=case['run_spec']['solver']['name'])
    if not a['valid'] or not e['valid']:
        raise ValueError('actual per-case A/E qualification failed: ' + '; '.join(a['errors'] + e['errors']))
    runtime = load_document(b['environment_profile']['path'])['runtime']
    if not same_runtime(runtime, e['runtime']) or _path(request['matlab_executable']) != _path(runtime['executable']):
        raise ValueError('actual per-case A/E/executable runtime differs')
    if include_h:
        from validate_h_analysis_profile import validate_h_analysis_profile
        h = validate_h_analysis_profile(b['h_analysis_profile']['path'], now=started_at, required_solver=case['run_spec']['solver']['name'])
        if not h['valid'] or not same_runtime(runtime, h['runtime']):
            raise ValueError('actual per-case independent H qualification failed: ' + '; '.join(h['errors']))
    keys = ('environment_profile', 'simulation_profile') + (('h_analysis_profile',) if include_h else ())
    windows = []
    from verification_common import limited_document
    for key in keys:
        profile = limited_document(b[key]['path'], request['budget'])
        receipt_key = 'environment_receipt' if key == 'environment_profile' else key + '_receipt'
        receipt = limited_document(b[receipt_key]['path'], request['budget'])
        raw_name = profile['evidence']['raw_file'] if key == 'environment_profile' else (
            'raw-simulation.json' if key == 'simulation_profile' else contract()['evidence']['raw'])
        raw = limited_document(contained_path(Path(b[key]['path']).parent, raw_name), request['budget'])
        windows.append({'captured_at': profile['captured_at'], 'valid_until': profile['valid_until'],
                        'process_started_at': receipt['process']['started_at'],
                        'raw_started_at': raw['started_at'], 'raw_finished_at': raw['finished_at'],
                        'process_finished_at': receipt['process']['finished_at']})
    facts = {'runtime': deepcopy(runtime), 'deadline': stable_utc(min(_time(x['valid_until']) for x in windows)),
             'windows': windows, 'solvers': sorted(set(e['qualified_solvers']) &
                 (set(h['qualified_solvers']) if include_h else set(contract()['solvers']))),
             'qualified_A_operations': deepcopy(a['qualified_operations']), 'required_A_operations': deepcopy(required),
             'host_fingerprint': request['host_fingerprint'], 'matlab_executable': request['matlab_executable'],
             'include_h': include_h}
    _apply_qualification_facts(request, case, started_at, facts, include_h=include_h)
    return facts


def _apply_qualification_facts(request, case, started_at, facts, *, include_h):
    """Always compare this actual case; facts never mean blanket acceptance."""
    required = request['bindings']['required_A_operations']
    if not typed_equal(facts['required_A_operations'], required) or not set(required) <= set(facts['qualified_A_operations']):
        raise ValueError('case required A operation union differs from independently verified qualifications')
    if facts['include_h'] is not include_h or facts['host_fingerprint'] != request['host_fingerprint'] or facts['matlab_executable'] != request['matlab_executable'] or _path(request['matlab_executable']) != _path(facts['runtime']['executable']):
        raise ValueError('case host/executable/runtime differs from independently verified qualifications')
    clock = _time(started_at)
    for window in facts['windows']:
        process_start, raw_start, raw_stop, process_stop = (_time(window[key]) for key in
            ('process_started_at', 'raw_started_at', 'raw_finished_at', 'process_finished_at'))
        captured, expiry = _time(window['captured_at']), _time(window['valid_until'])
        if not process_start <= raw_start <= raw_stop <= process_stop or captured != raw_stop:
            raise ValueError('independently verified qualification process/raw ordering differs')
        if not max(captured, process_stop) <= clock <= expiry:
            raise ValueError('case began outside independently verified qualification time windows or completion floor')
    deadlines = [_time(window['valid_until']) for window in facts['windows']]
    if _time(facts['deadline']) != min(deadlines) or _time(case['qualification_not_after']) != min(deadlines):
        raise ValueError('case solver/deadline differs from independently verified qualifications')
    if case['run_spec']['solver']['name'] not in facts['solvers']:
        raise ValueError('case solver/deadline differs from independently verified qualifications')
    return deepcopy(facts['runtime'])


def _historical_qualification_facts(replay, request, case, started_at):
    from verification_common import _reuse_validation
    b = request['bindings']
    keys = ('environment_profile', 'environment_receipt', 'simulation_profile', 'simulation_profile_receipt',
            'h_analysis_profile', 'h_analysis_profile_receipt')
    qualification_request = {'bindings': {key: deepcopy(b[key]) for key in keys}}
    options = {'bindings': deepcopy(qualification_request['bindings']),
               'required_A_operations': deepcopy(b['required_A_operations']), 'include_h': True,
               'host_fingerprint': request['host_fingerprint'], 'matlab_executable': request['matlab_executable'],
               'sources': deepcopy(request['sources'])}
    return _reuse_validation('historical_qualification', project_root=b['project_root'], budget=request['budget'],
        request=qualification_request, request_role='h_trial_request', options=options,
        capability=replay._capability,
        compute=lambda: _collect_qualification_facts(request, case, started_at, include_h=True),
        eligible=lambda value: isinstance(value, dict) and value.get('include_h') is True)


def validate_case_qualifications(request, case, started_at, *, include_h=True, _cache=None,
                                 _historical_replay=None):
    required = request['bindings']['required_A_operations']
    if not isinstance(required, list) or not set(contract()['required_A_operations']) <= set(required):
        raise ValueError('H required A operation union was dropped')
    cache_key = (request['input_identity'], include_h)
    if _cache is not None and cache_key in _cache:
        return _apply_qualification_facts(request, case, started_at, _cache[cache_key], include_h=include_h)
    if include_h is True and isinstance(_historical_replay, _HistoricalReplay) and _historical_replay.matches(request):
        facts = _historical_qualification_facts(_historical_replay, request, case, started_at)
    else:
        # Actual new execution, direct/current profiles and include_h=False
        # qualification reconstruction always retain the original full path.
        facts = _collect_qualification_facts(request, case, started_at, include_h=include_h)
    runtime = _apply_qualification_facts(request, case, started_at, facts, include_h=include_h)
    if _cache is not None: _cache[cache_key] = deepcopy(facts)
    return runtime


def materialize_trial_manifest(report, design=None):
    """Derive every hypothetical value from the reviewed ordered design, never C edits."""
    from validate_parameter_provenance import mathematical_models
    from numerical_obligations import numeric_context_from_documents
    protocol = report['base_protocol_report']
    spec = protocol['run_spec']
    mapping = protocol['mapping_validation']['mapping_snapshot']
    target = next(x for x in mapping['targets'] if x['id'] == protocol['target_id'])
    model_document = load_document(protocol['model_path'])
    model = mathematical_models(model_document)[(protocol['design_id'], protocol['model_id'])]
    context = numeric_context_from_documents(model_document,
        {'design_id': protocol['design_id'], 'model_id': protocol['model_id']}, load_document(protocol['parameters_path']))
    variables = {x['id']: x for x in model['body']['variables']}
    states = []
    for block in protocol['mapping_validation']['build_spec']['blocks']:
        if block['type'] != 'Integrator': continue
        candidates = {trace['subject_id'] for trace in target['traces'] if trace['kind'] == 'variable' and trace['disposition'] == 'mapped' and block['id'] in trace['block_ids'] and trace['subject_id'] in variables and 'state' in variables[trace['subject_id']]['roles']}
        if len(candidates) != 1:
            raise ValueError('Integrator requires one actual reviewed C state-variable D trace')
        variable = variables[candidates.pop()]
        states.append({'block_path': block['path'], 'variable_id': variable['id'], 'unit': variable['unit'],
                       'value': resolve_initial_value(block['parameters']['InitialCondition'], spec['parameters'])})
    design = report['design'] if design is None else design
    rows = record_array(design['rows'], 'design.rows')
    check_budget(report['native_budget'], groups=len(rows), cases=3 * len(rows))
    factors = report['factors']
    if design['factor_ids'] != [factor['id'] for factor in factors]:
        raise ValueError('design ordered factors differ from reviewed study')
    result = []
    for occurrence, row in enumerate(rows, 1):
        roles = row['role'] if isinstance(row['role'], list) else [row['role']]
        runtime_role = next((role for role in roles if isinstance(role, dict) and role.get('kind') == 'runtime_repeat'), None)
        numeric = deepcopy(next(x['numerical_policy'] for x in report['settings']['configurations'] if x['id'] == runtime_role['configuration_id']) if runtime_role else report['numerical_policy'])
        if not isinstance(numeric.get('solver_levels'), list) or len(numeric['solver_levels']) != 3:
            raise ValueError('trial numerical policy requires three complete solver levels')
        values = numeric_vector(row['values'], 'design.factor_values',
                                nonempty=not (report['method'] == 'runtime_comparison' and not factors))
        if len(values) != len(factors): raise ValueError('complete ordered factor row required')
        snapshot = physical_snapshot(spec, states)
        touched = set()
        for factor, value in zip(factors, values):
            if not factor['domain']['lower'] <= value <= factor['domain']['upper']:
                raise ValueError('sample outside reviewed hypothetical execution domain; no clipping/retry')
            locator, kind = factor['locator'], factor['kind']
            key = (kind, locator['code_name'], locator['block_path'], locator['input_port'])
            if key in touched: raise ValueError('multiple factors overwrite the same native target')
            touched.add(key)
            if kind == 'parameter':
                item = next(x for x in snapshot['parameters'] if x['code_name'] == locator['code_name'])
                if item['unit'] != factor['unit']: raise ValueError('factor parameter unit differs')
                item['value'] = value
            elif kind == 'initial_condition':
                item = next(x for x in snapshot['initial_conditions'] if x['block_path'] == locator['block_path'] and x['variable_id'] == factor['variable_id'])
                if item['unit'] != factor['unit']: raise ValueError('factor initial-state unit differs')
                item['value'] = value
            elif kind == 'external_input':
                item = next(x for x in snapshot['inputs'] if x['port'] == locator['input_port'] and x['variable_id'] == factor['variable_id'])
                if item['unit'] != factor['unit']: raise ValueError('factor external-input unit differs')
                wave = factor['waveform']
                item['time'] = deepcopy(wave['time'])
                item['values'] = [value for _ in wave['time']] if wave['mode'] == 'constant' else [x * value for x in wave['baseline_values']] if wave['mode'] == 'scale' else [x + value for x in wave['baseline_values']]
                item['interpolation'] = 'linear'
            else: raise ValueError('unsupported native factor kind')
        identity = row['id']
        result.append({'group_id': identity, 'point_id': identity, 'occurrence': occurrence, 'factor_values': deepcopy(values),
                       'roles': deepcopy(roles),
                       'physical_snapshot': snapshot, 'physical_sha256': canonical_digest(snapshot), 'numeric_policy': deepcopy(numeric),
                       'context': deepcopy(context),
                       'case_ids': [identity + '-level-' + str(index) for index in range(3)]})
    return result


def make_task_request(study_path, executable, directory, report, *, environment_profile, simulation_profile,
                      h_analysis_profile, project_root, required_operations=None, design_override=None, state_binding=None):
    groups = materialize_trial_manifest(report, design_override)
    profiles = {'environment_profile': environment_profile, 'simulation_profile': simulation_profile, 'h_analysis_profile': h_analysis_profile}
    selected = list(dict.fromkeys(contract()['required_A_operations'] + report['required_A_operations'] + list(required_operations or [])))
    minimum = [name for name in selected if name not in {'simulink.core_simulation', OPERATION}]
    known_a = set(load_document(ROOT / 'core/runtime_assurance_contract.yaml')['operations'])
    if not set(minimum) <= known_a: raise ValueError('unknown requested A qualification operation')
    protocol = report['base_protocol_report']
    bindings = {'project_id': report['project_id'], 'project_root': str(Path(project_root).resolve()),
                'study': {'path': str(Path(study_path).resolve()), 'sha256': '0' * 64}, 'study_snapshot': report['_contract'],
                'study_semantic_sha256': report['semantic_sha256'],
                'base_protocol': {'path': protocol['contract_path'], 'sha256': protocol['contract_sha256']},
                'base_simulation_receipt': {'path': report['base_simulation_report']['receipt_path'], 'sha256': report['base_simulation_report']['receipt_sha256']},
                'primary_numerical_receipt': {'path': report['primary_numerical_report']['receipt_path'], 'sha256': report['primary_numerical_report']['receipt_sha256']},
                'bound_files': deepcopy(report['bound_files']), 'required_A_operations': minimum,
                'protected_files': deepcopy(report['bound_files']), 'current_state': deepcopy(state_binding),
                'design': deepcopy(report['design'] if design_override is None else design_override)}
    for key, path in profiles.items():
        bindings[key] = {'path': str(Path(path).resolve()), 'sha256': '0' * 64}
        name = 'receipt.json' if key == 'environment_profile' else 'simulation-profile-receipt.json' if key == 'simulation_profile' else contract()['evidence']['profile_receipt']
        bindings[key.replace('profile', 'receipt') if key == 'environment_profile' else key + '_receipt'] = {'path': str(Path(path).resolve().parent / name), 'sha256': '0' * 64}
    # Current state/primary-run files are protected only when actually supplied.
    for path in report.get('protected_paths', []):
        bindings['protected_files'].append({'path': str(Path(path).resolve()), 'sha256': '0' * 64})
    if state_binding is not None:
        if not isinstance(state_binding, dict) or set(state_binding) != {'path', 'sha256'} or not isinstance(state_binding['path'], str) or not re.fullmatch(r'[a-f0-9]{64}', state_binding['sha256']):
            raise ValueError('current state requires an explicit caller-bound path and exact SHA')
        state_path = contained_path(project_root, state_binding['path'])
        bindings['current_state'] = {'path': str(state_path), 'sha256': state_binding['sha256']}
        bindings['protected_files'].append(deepcopy(bindings['current_state']))
    request = {'schema_version': 1, 'run_id': str(uuid.uuid4()), 'mode': 'trial', 'channel': 'matlab_batch',
               'host_fingerprint': host_fingerprint(), 'matlab_executable': str(Path(executable).resolve()),
               'output_directory': str(Path(directory).resolve()), 'sources': {}, 'source_identity': '',
               'required_functions': contract()['required_functions'], 'cases': [], 'groups': groups, 'bindings': bindings,
               'budget': deepcopy(report['native_budget']), 'input_identity': ''}
    preflight_request(request, role='h_trial_request')
    if state_binding is not None and sha256_file(bindings['current_state']['path']) != bindings['current_state']['sha256']:
        raise ValueError('explicit caller-bound current state bytes differ')
    for key in ('study', 'base_protocol', 'base_simulation_receipt', 'primary_numerical_receipt', 'environment_profile', 'environment_receipt', 'simulation_profile', 'simulation_profile_receipt', 'h_analysis_profile', 'h_analysis_profile_receipt'):
        bindings[key] = file_binding(bindings[key]['path'])
    bindings['protected_files'] = [file_binding(x['path']) for x in bindings['protected_files']]
    deadline = stable_utc(min(_time(load_document(path)['valid_until']) for path in profiles.values()))
    for group in groups:
        for level, case_id in enumerate(group['case_ids']):
            spec = deepcopy(protocol['run_spec'])
            spec.update(parameters=deepcopy(group['physical_snapshot']['parameters']), inputs=deepcopy(group['physical_snapshot']['inputs']),
                        solver=deepcopy(group['numeric_policy']['solver_levels'][level]))
            # E admission metrics belong to the approved primary. Hypothetical
            # metrics are assessed by the prior H policy, including failed points.
            spec['metrics'] = []
            initials = deepcopy(group['physical_snapshot']['initial_conditions'])
            request['cases'].append({'case_id': case_id, 'group_id': group['group_id'], 'level_id': level, 'point_id': group['point_id'],
                'occurrence': group['occurrence'], 'run_spec': spec, 'build_spec': deepcopy(protocol['mapping_validation']['build_spec']),
                'initial_conditions': initials, 'states': [{k: x[k] for k in ('block_path', 'variable_id', 'unit')} for x in initials],
                'simulation_timeout': request['budget']['simulation_timeout'], 'expectation': 'success', 'warning_policy': spec['warning_policy'], 'qualification_not_after': deadline})
    request['sources'] = source_identities()
    request['source_identity'] = canonical_digest(request['sources'])
    request['input_identity'] = canonical_digest({k: v for k, v in request.items() if k != 'input_identity'})
    validate_request(request)
    return request


def run_h_analysis_trials(study_path, executable, output_dir, *, environment_profile, simulation_profile,
                          h_analysis_profile, project_root=None, required_operations=None, design_override=None,
                          process_timeout_limit=None, state_binding=None):
    cap_entry = time.monotonic()
    if process_timeout_limit is not None and (not finite(process_timeout_limit) or process_timeout_limit <= 0):
        raise ValueError('parent process timeout cap must be finite and positive')
    from h_analysis_study import validate_h_analysis_study
    root = Path(project_root or Path(study_path).resolve().parent).resolve()
    report = validate_h_analysis_study(study_path, project_root=root, require_reviewed=True)
    if not report['valid'] or not report['execution_ready']:
        raise ValueError('current approved-base reviewed H hypothetical study required: ' + '; '.join(report['errors'] + report['missing_gates']))
    request = make_task_request(study_path, executable, output_dir, report, environment_profile=environment_profile,
                               simulation_profile=simulation_profile, h_analysis_profile=h_analysis_profile, project_root=root,
                               required_operations=required_operations, design_override=design_override, state_binding=state_binding)
    if not Path(request['output_directory']).is_relative_to(root):
        raise ValueError('H trial output leaves project root')
    initial = preflight_request(request, role='h_trial_request')
    from resolve_runtime import resolve_runtime
    route = resolve_runtime('h_analysis_trials', h_analysis_study_path=study_path, h_analysis_profile_path=h_analysis_profile,
                            profile_path=environment_profile, simulation_profile_path=simulation_profile,
                            project_root=root, required_operations=required_operations,
                            state_path=None if request['bindings']['current_state'] is None else request['bindings']['current_state']['path'])
    if not route.get('h_analysis_execution_allowed') or route.get('execution_scope') != 'h_analysis_trials':
        raise ValueError('public H trial route blocked: ' + '; '.join(route.get('errors', []) + route.get('blocked_reasons', [])))
    cache = {}
    for case in request['cases']:
        validate_case_qualifications(request, case, datetime.now(timezone.utc), _cache=cache)
    remaining = None if process_timeout_limit is None else process_timeout_limit - (time.monotonic() - cap_entry)
    if remaining is not None and remaining <= 0: raise ValueError('parent timeout budget exhausted during H trial preflight')
    process = execute_request(request, process_timeout_limit=remaining)
    directory, names = Path(output_dir), contract()['evidence']
    raw = limited_document(directory / names['raw'], request['budget'])
    receipt = {'schema_version': 1, 'run_id': request['run_id'], 'project_id': report['project_id'], 'study_semantic_sha256': report['semantic_sha256'],
               'sources': request['sources'], 'process': process, 'runtime': None, 'protected_files': request['bindings']['protected_files'],
               'artifacts': {}, 'numeric_results': [], 'status': 'incomplete', 'errors': []}
    try:
        assert_unchanged(initial)
        if source_identities() != request['sources']: raise ValueError('native safety source changed while executing')
        receipt['runtime'] = observed_runtime(raw, request) if isinstance(raw.get('runtime'), dict) else None
        receipt['artifacts'] = artifact_manifest(directory)
        from validate_h_analysis_trial_receipt import assess_trial_request
        assessment = assess_trial_request(request, raw, directory, report, process=process)
        receipt['numeric_results'] = assessment['numeric_results']
        receipt['status'] = 'completed' if assessment['complete'] else 'incomplete'
        receipt['errors'] = assessment['errors']
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        receipt['errors'].append(str(error))
        try: receipt['artifacts'] = artifact_manifest(directory)
        except (OSError, ValueError, KeyError) as artifact_error: receipt['errors'].append(str(artifact_error))
    path = directory / names['run_receipt']
    write_json(path, receipt)
    from validate_h_analysis_trial_receipt import validate_h_analysis_trial_receipt
    result = validate_h_analysis_trial_receipt(path, project_root=root, study_report=report)
    result.update(receipt_path=str(path.resolve()), raw_path=str((directory / names['raw']).resolve()))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('study', type=Path)
    for option in ('matlab-executable', 'output-dir', 'environment-profile', 'simulation-profile', 'h-analysis-profile'):
        parser.add_argument('--' + option, type=Path, required=True)
    parser.add_argument('--project-root', type=Path)
    parser.add_argument('--current-state', type=Path)
    parser.add_argument('--current-state-sha256')
    parser.add_argument('--process-timeout-limit', type=float)
    parser.add_argument('--require-operation', action='append', default=[])
    args = parser.parse_args()
    try:
        if (args.current_state is None) != (args.current_state_sha256 is None):
            raise ValueError('explicit current state requires both path and caller-bound SHA')
        state_binding = None if args.current_state is None else {'path': str(args.current_state), 'sha256': args.current_state_sha256}
        result = run_h_analysis_trials(args.study, args.matlab_executable, args.output_dir, environment_profile=args.environment_profile,
            simulation_profile=args.simulation_profile, h_analysis_profile=args.h_analysis_profile, project_root=args.project_root, required_operations=args.require_operation,
            process_timeout_limit=args.process_timeout_limit, state_binding=state_binding)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        result = {'valid': False, 'trial_complete': False, 'errors': [str(error)]}
    emit(result)
    return 0 if result['valid'] and result.get('trial_complete') else 1


if __name__ == '__main__':
    raise SystemExit(main())
