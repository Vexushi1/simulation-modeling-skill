"""Synthetic H wire/numeric consumer tests. No native qualification is supplied."""
from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import uuid

import numpy as np
import pytest
from scipy.io import loadmat, savemat

import h_analysis_trial as trial
from probe_h_analysis import qualification_cases
from validate_h_analysis_profile import analytic_state
from h_analysis_native_factory import make_h_analysis_profile, synthetic_native_case, write_synthetic_timing_primitives


def matrix(tmp_path):
    deadline = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    return qualification_cases(str(uuid.uuid4()), tmp_path, deadline)


def test_probe_matrix_has_independent_triplets_and_actual_controls(tmp_path):
    cases, groups = matrix(tmp_path)
    assert len(cases) == 20 and len(groups) == 5
    assert {c['run_spec']['solver']['name'] for c in cases} == {'ode4', 'ode45', 'ode15s'}
    ids = [c['case_id'] for c in cases]
    assert len(set(ids)) == len(ids)
    for group in groups:
        assert len(group['case_ids']) == 3
        selected = [next(c for c in cases if c['case_id'] == identity) for identity in group['case_ids']]
        assert [x['level_id'] for x in selected] == [0, 1, 2]
        assert all(trial.physical_snapshot(c['run_spec'], c['initial_conditions']) == group['physical_snapshot'] for c in selected)
    assert {c['expectation'] for c in cases} == {'success', 'error', 'early_stop', 'no_output'}


def test_native_case_does_not_use_baseline_parameters_as_trial_values(tmp_path):
    cases, _ = matrix(tmp_path)
    case = cases[0]
    assert case['run_spec']['parameters'][0]['value'] != case['build_spec']['parameters'][0]['value']
    assert case['initial_conditions'][0]['value'] != float(next(x['parameters']['InitialCondition'] for x in case['build_spec']['blocks'] if x['type'] == 'Integrator'))
    assert trial.validate_case_spec(case, mode='probe', budget=trial.contract()['hard_budget']) is case


@pytest.mark.parametrize('mutation,match', [
    (lambda c: c.update(level_id=True), 'level'),
    (lambda c: c['states'][0].update(variable_id=''), 'state'),
    (lambda c: c['initial_conditions'][0].update(value=True), 'finite'),
    (lambda c: c['run_spec']['inputs'][0].update(interpolation='zoh', values=[0.0, 1.0]), 'continuous'),
    (lambda c: c['run_spec']['parameters'].append(deepcopy(c['run_spec']['parameters'][0])), 'workspace'),
])
def test_native_case_rejects_ambiguous_or_unbounded_overlays(tmp_path, mutation, match):
    case = deepcopy(matrix(tmp_path)[0][0])
    mutation(case)
    with pytest.raises(ValueError, match=match):
        trial.validate_case_spec(case, mode='probe', budget=trial.contract()['hard_budget'])


def test_controlled_missing_symbol_is_never_allowed_in_business_trial(tmp_path):
    case = next(c for c in matrix(tmp_path)[0] if c['expectation'] == 'error')
    with pytest.raises(ValueError, match='qualification'):
        trial.validate_case_spec(case, mode='trial', budget=trial.contract()['hard_budget'])


def test_prior_native_budget_rejects_complete_formula_count():
    budget = deepcopy(trial.contract()['hard_budget'])
    budget.update(max_groups=2, max_cases=6)
    trial.check_budget(budget, groups=2, cases=6)
    with pytest.raises(ValueError, match='complete point'):
        trial.check_budget(budget, groups=3, cases=9)
    budget['max_cases'] = True
    with pytest.raises(ValueError, match='max_cases'):
        trial.check_budget(budget)


def test_parameter_consumer_rejects_real_dtype_or_unit_mismatch():
    expected = [{'code_name': 'syn_a', 'value': 1.0, 'unit': '1/s'}]
    actual = [{'code_name': 'syn_a', 'value': 1.0, 'unit': '1/s', 'class': 'Simulink.Parameter',
               'data_type': 'double', 'value_class': 'double', 'shape': [1, 1], 'is_real': True}]
    trial.assert_parameter_records(actual, expected)
    for field, value in [('data_type', 'single'), ('value_class', 'single'), ('shape', [1, 2]), ('is_real', False), ('unit', 's'), ('value', True)]:
        wrong = deepcopy(actual)
        wrong[0][field] = value
        with pytest.raises(ValueError, match='parameter'):
            trial.assert_parameter_records(wrong, expected)


def state_evidence(tmp_path):
    """Handwritten MAT/JSON/CSV serialization fixture, never a MATLAB receipt."""
    case = matrix(tmp_path)[0][0]
    state = case['states'][0]
    run_id = 'SYNTHETIC-NO-MATLAB'
    record = {**state, 'label': 'CSTATE', 'observed_unit': '', 'time': [0.0, 2.0],
              'values': [case['initial_conditions'][0]['value'], 0.8], 'csv_file': 'state.csv'}
    actual = {'states': [record], 'state_data_file': 'states.json', 'state_mat_file': 'states.mat'}
    (tmp_path / 'states.json').write_text(json.dumps({'schema_version': 1, 'run_id': run_id, 'case_id': case['case_id'], 'states': [record]}), encoding='utf-8')
    (tmp_path / 'state.csv').write_text('0,0.20000000000000001\n2,0.80000000000000004\n', encoding='utf-8')
    mat = {'run_id': run_id, 'case_id': case['case_id']}
    for name, values in [('state_variables', [record['variable_id']]), ('state_units', [record['unit']]),
                         ('state_paths', [record['block_path']]), ('state_labels', [record['label']]),
                         ('state_times', [record['time']]), ('state_values', [record['values']])]:
        value = np.empty((1, 1), dtype=object)
        value[0, 0] = values[0] if isinstance(values[0], str) else np.asarray(values[0], dtype=float).reshape(-1, 1)
        mat[name] = value
    savemat(tmp_path / 'states.mat', mat, format='5')
    return case, run_id, actual, mat


def test_states_have_true_path_class_and_exact_three_formats(tmp_path):
    case, run_id, actual, _ = state_evidence(tmp_path)
    assert trial._read_states(tmp_path, actual, case, run_id, trial.contract()['hard_budget']) == actual['states']
    (tmp_path / 'state.csv').write_text('0,0.2\n2,0.81\n', encoding='utf-8')
    with pytest.raises(ValueError, match='CSV'):
        trial._read_states(tmp_path, actual, case, run_id, trial.contract()['hard_budget'])


@pytest.mark.parametrize('kind', ['single', 'complex', 'row', 'logical'])
def test_states_reject_native_mat_dtype_complexity_and_shape(tmp_path, kind):
    case, run_id, actual, mat = state_evidence(tmp_path)
    if kind == 'single': mat['state_values'][0, 0] = np.asarray([0.2, 0.8], dtype=np.float32).reshape(-1, 1)
    if kind == 'complex': mat['state_values'][0, 0] = np.asarray([0.2 + 1j, 0.8]).reshape(-1, 1)
    if kind == 'row': mat['state_values'][0, 0] = np.asarray([0.2, 0.8]).reshape(1, -1)
    if kind == 'logical': mat['state_values'][0, 0] = np.asarray([False, True]).reshape(-1, 1)
    savemat(tmp_path / 'states.mat', mat, format='5')
    with pytest.raises(ValueError, match='MAT|complex'):
        trial._read_states(tmp_path, actual, case, run_id, trial.contract()['hard_budget'])


def test_analytic_oracle_covers_nonzero_initials_affine_input_and_cascade(tmp_path):
    cases, _ = matrix(tmp_path)
    first = cases[0]
    assert analytic_state(first, 'x1', 0.0) == pytest.approx(0.2)
    assert analytic_state(first, 'x1', 2.0) == pytest.approx(1 + (0.2 - 1) * np.exp(-2))
    cascade = next(c for c in cases if c['group_id'] == 'cascade_ode45')
    assert analytic_state(cascade, 'x1', 0.0) == pytest.approx(0.2)
    assert analytic_state(cascade, 'x2', 0.0) == pytest.approx(-0.1)
    assert analytic_state(cascade, 'x2', 2.0) == pytest.approx(1 + (-0.1 - 1 + 1 + (0.2 - 1 + 0.5) * 2) * np.exp(-2))
    zero = next(c for c in cases if c['group_id'] == 'zero_response')
    assert analytic_state(zero, 'x1', 1.3) == 0.0


def test_matlab_trial_surface_keeps_primary_files_unmodified():
    source = (trial.ROOT / 'scripts/matlab/run_h_analysis_trials.m').read_text(encoding='utf-8')
    assert "'SaveState', 'on'" in source and 'metadata.TimingInfo' in source
    assert "'Workspace', model" in source and "'InitialCondition', numtext(initial.value)" in source
    assert 'input_sampling_restored' in source and 'initial_conditions_restored' in source
    assert 'assignin(workspace' in source  # Private fixed probe fixture construction only.
    runtime = source[source.index('function record = simulateOwned'):source.index('function buildFixture')]
    assert 'save_system(' not in runtime and 'assignin(' not in runtime and 'setPreSimFcn' not in runtime


def test_per_case_gate_cache_still_rejects_expiry_and_solver():
    now = datetime.now(timezone.utc)
    request = {'input_identity': 'synthetic', 'bindings': {'required_A_operations': trial.contract()['required_A_operations']}}
    case = {'qualification_not_after': (now + timedelta(seconds=10)).isoformat(), 'run_spec': {'solver': {'name': 'ode4'}}}
    cache = {('synthetic', True): {'windows': [(now - timedelta(seconds=10), now + timedelta(seconds=10))],
             'deadline': now + timedelta(seconds=10), 'solvers': {'ode4'}, 'runtime': {'SYNTHETIC': 'not qualification'}}}
    assert trial.validate_case_qualifications(request, case, now, _cache=cache)['SYNTHETIC'] == 'not qualification'
    with pytest.raises(ValueError, match='time windows'):
        trial.validate_case_qualifications(request, case, now + timedelta(seconds=11), _cache=cache)
    case['run_spec']['solver']['name'] = 'ode45'
    with pytest.raises(ValueError, match='solver'):
        trial.validate_case_qualifications(request, case, now, _cache=cache)


def test_complete_actual_format_case_is_independently_consumed(tmp_path):
    case = matrix(tmp_path)[0][0]
    directory = tmp_path / 'cases' / case['case_id']
    actual = synthetic_native_case(case, directory, 'SYNTHETIC-NO-MATLAB',
        state_values=lambda t: {'x1': 0.2 if t == 0.0 else 1 + (0.2 - 1) * np.exp(-t)})
    checked = trial.assert_case(actual, case, directory, 'SYNTHETIC-NO-MATLAB', trial.contract()['hard_budget'])
    assert checked['complete'] and checked['states'][0]['values'] == checked['outputs'][0]['values']
    actual['reopened_initial_conditions'][0]['value'] = '0.2'
    with pytest.raises(ValueError, match='initial-condition restoration'):
        trial.assert_case(actual, case, directory, 'SYNTHETIC-NO-MATLAB', trial.contract()['hard_budget'])


@pytest.fixture(scope='module')
def complete_h_profile(tmp_path_factory):
    from test_runtime import make_profile
    from test_simulation_assurance import make_simulation_profile
    root = tmp_path_factory.mktemp('synthetic-H-operation-full-wire')
    a = make_profile(root / 'a-profile')
    e = make_simulation_profile(root / 'e-profile', a)
    return make_h_analysis_profile(root / 'h-profile', a, e)


@contextmanager
def preserved_native_directory(directory):
    snapshots = {path: path.read_bytes() for path in Path(directory).rglob('*') if path.is_file()}
    try:
        yield
    finally:
        for path, contents in snapshots.items(): path.write_bytes(contents)
        for path in Path(directory).rglob('*'):
            if path.is_file() and path not in snapshots: path.unlink()


def rebind_synthetic_h_profile(path, raw, request=None):
    from probe_environment import write_json
    from runtime_common import canonical_digest, load_document
    from validate_h_analysis_profile import derive_profile
    names = trial.contract()['evidence']
    request = request or load_document(path.parent / names['input'])
    request['input_identity'] = canonical_digest({k: v for k, v in request.items() if k != 'input_identity'})
    raw['input_identity'] = request['input_identity']
    write_json(path.parent / names['input'], request)
    write_json(path.parent / names['raw'], raw)
    receipt = load_document(path.parent / names['profile_receipt'])
    derived = derive_profile(raw, request, receipt['process'])
    write_json(path, derived)
    receipt['runtime'] = derived['runtime']
    receipt['artifacts'] = trial.artifact_manifest(path.parent, include_profile=True)
    write_json(path.parent / names['profile_receipt'], receipt)


def test_standalone_profile_consumes_real_sibling_and_all_triplets(complete_h_profile):
    from validate_h_analysis_profile import validate_h_analysis_profile
    report = validate_h_analysis_profile(complete_h_profile)
    assert report['valid'] and report['h_analysis_assured'], report['errors']
    assert report['installation_identity_checked'] and len(report['case_results']) == 20
    assert set(report['qualified_solvers']) == {'ode4', 'ode45', 'ode15s'}


@pytest.mark.parametrize('mutation,match', [
    (lambda x: x['effective_configuration'].update(StartTime=False), 'interval/mode'),
    (lambda x: x['observed_solver_info'].update(FixedStepSize=True), 'solver/type/step'),
    (lambda x: x['reopened_configuration'].update(SaveState='on'), 'configuration restoration'),
    (lambda x: x['functions'].pop(), 'function inventory'),
    (lambda x: x['states'][0].update(label='OUTPUT'), 'state JSON exact identity/records'),
    (lambda x: x['reopened_initial_conditions'][0].update(value='0.2'), 'initial-condition restoration'),
    (lambda x: x['timing_info'].update(TotalElapsedWallTime=True), 'TimingInfo'),
])
def test_rehashed_full_native_profile_rejects_actual_metadata(complete_h_profile, mutation, match):
    from runtime_common import load_document
    from validate_h_analysis_profile import validate_h_analysis_profile
    with preserved_native_directory(complete_h_profile.parent):
        raw = load_document(complete_h_profile.parent / trial.contract()['evidence']['raw'])
        mutation(raw['cases'][0])
        rebind_synthetic_h_profile(complete_h_profile, raw)
        report = validate_h_analysis_profile(complete_h_profile)
        assert not report['valid'] and not report['h_analysis_assured']
        assert any(match in error for case in report['case_results'] for error in case['errors']), report


def test_consistent_three_format_wrong_label_reaches_actual_CSTATE_gate(complete_h_profile):
    from probe_environment import write_json
    from runtime_common import load_document
    from validate_h_analysis_profile import validate_h_analysis_profile
    with preserved_native_directory(complete_h_profile.parent):
        raw = load_document(complete_h_profile.parent / trial.contract()['evidence']['raw'])
        actual = raw['cases'][0]
        actual['states'][0]['label'] = 'OUTPUT'
        directory = complete_h_profile.parent / 'cases' / actual['case_id']
        state_json = load_document(directory / actual['state_data_file'])
        state_json['states'] = deepcopy(actual['states'])
        write_json(directory / actual['state_data_file'], state_json)
        mat = {k: v for k, v in loadmat(directory / actual['state_mat_file'], mat_dtype=True).items() if not k.startswith('__')}
        mat['state_labels'][0, 0] = 'OUTPUT'
        savemat(directory / actual['state_mat_file'], mat, format='5')
        rebind_synthetic_h_profile(complete_h_profile, raw)
        report = validate_h_analysis_profile(complete_h_profile)
        assert not report['valid'] and not report['h_analysis_assured'], report
        assert any('BlockPath/CSTATE/unit state identity' in e for result in report['case_results'] for e in result['errors']), report


def test_whole_profile_rejects_independently_fitting_sets_combined_over_budget(complete_h_profile):
    from runtime_common import load_document
    from verification_common import evidence_paths_for_request
    from validate_h_analysis_profile import validate_h_analysis_profile
    names = trial.contract()['evidence']
    with preserved_native_directory(complete_h_profile.parent):
        request = load_document(complete_h_profile.parent / names['input'])
        paths = evidence_paths_for_request(request, complete_h_profile.parent, request['budget'], role='qualification_h_request')
        owned = {p.resolve() for p in complete_h_profile.parent.rglob('*') if p.is_file()}
        upstream = set(paths) - owned
        own_bytes = sum(p.stat().st_size for p in owned)
        upstream_bytes = sum(p.stat().st_size for p in upstream)
        request['budget']['max_total_bytes'] = max(own_bytes, upstream_bytes) + min(own_bytes, upstream_bytes) // 4
        request['budget']['max_file_bytes'] = min(request['budget']['max_file_bytes'], request['budget']['max_total_bytes'])
        raw = load_document(complete_h_profile.parent / names['raw'])
        rebind_synthetic_h_profile(complete_h_profile, raw, request)
        report = validate_h_analysis_profile(complete_h_profile)
        assert not report['valid'] and any('budget' in e for e in report['errors']), report


def test_exact_request_serialization_checks_virtual_file_and_total_before_native(tmp_path):
    from verification_common import EvidencePaths, serialized_request_bytes
    source = tmp_path / 'prior.txt'
    source.write_bytes(b'x' * 40)
    budget = {'max_file_bytes': 100, 'max_total_bytes': 50}
    with pytest.raises(ValueError, match='complete input byte/file budget'):
        serialized_request_bytes({'scope': 'SYNTHETIC only'}, EvidencePaths([source]), tmp_path, budget)
    budget['max_total_bytes'] = 1000
    with pytest.raises(ValueError, match='expanded bytes'):
        serialized_request_bytes({'long': 'x' * 1000}, EvidencePaths([source]), tmp_path, budget)


def test_registered_initials_never_evaluate_arbitrary_expressions():
    assert trial.resolve_initial_value('syn_x0', [{'code_name': 'syn_x0', 'value': 0.25}]) == 0.25
    assert trial.resolve_initial_value('-1.25e-2', []) == -0.0125
    for text in ['a+b', '__import__("os")', 'NaN', 'Inf', 'unregistered']:
        with pytest.raises(ValueError, match='initial'):
            trial.resolve_initial_value(text, [])


@pytest.fixture(scope='module')
def complete_h_trial(tmp_path_factory):
    from numerical_factory import make_numerical_runs
    from run_numerical_verification import run_numerical_verification
    from h_analysis_study_factory import make_study_for_primary, make_study_history
    root = tmp_path_factory.mktemp('synthetic-H-trial-full-wire')
    h1_path, receipts = make_numerical_runs(root)
    h1 = run_numerical_verification(h1_path, receipts, root / 'primary-h1', project_root=root)
    assert h1['valid'] and h1['numerically_verified'], h1['errors']
    study = make_study_for_primary(h1['receipt_path'], project_root=root)
    history = make_study_history(study, project_root=root)
    return root, history.parent / 'trial-batch-000001' / trial.contract()['evidence']['run_receipt']


def rebind_synthetic_h_trial(path, root, raw):
    from probe_environment import write_json
    from runtime_common import load_document
    from validate_h_analysis_study import validate_h_analysis_study
    from validate_h_analysis_trial_receipt import assess_trial_request
    names = trial.contract()['evidence']
    request = load_document(path.parent / names['input'])
    write_json(path.parent / names['raw'], raw)
    report = validate_h_analysis_study(request['bindings']['study']['path'], project_root=root, require_reviewed=True)
    receipt = load_document(path)
    checked = assess_trial_request(request, raw, path.parent, report, process=receipt['process'])
    receipt.update(numeric_results=checked['numeric_results'], errors=checked['errors'],
                   status='completed' if checked['complete'] else 'incomplete', artifacts=trial.artifact_manifest(path.parent))
    write_json(path, receipt)


def test_failed_actual_trial_keeps_whole_ledger_readable_without_numeric_acceptance(complete_h_trial):
    from runtime_common import load_document
    from validate_h_analysis_trial_receipt import validate_h_analysis_trial_receipt
    root, path = complete_h_trial
    with preserved_native_directory(path.parent):
        raw = load_document(path.parent / trial.contract()['evidence']['raw'])
        raw['cases'][0].update(completed=False, framework_error={'identifier': 'SYNTHETIC:CapturedFailure', 'message': 'SYNTHETIC technical failure only'})
        rebind_synthetic_h_trial(path, root, raw)
        report = validate_h_analysis_trial_receipt(path, project_root=root)
        assert report['valid'] and not report['trial_complete'] and not report['numerically_verified'], report['errors']
        assert len(report['case_results']) == len(raw['cases'])
        assert report['groups'][0]['status'] == 'failed' and len(report['groups'][0]['case_results']) == 3


def test_raw_process_timeout_preserves_unattempted_groups_and_every_case(complete_h_trial):
    from runtime_common import load_document
    from probe_environment import write_json
    from validate_h_analysis_trial_receipt import validate_h_analysis_trial_receipt
    root, path = complete_h_trial
    with preserved_native_directory(path.parent):
        names = trial.contract()['evidence']
        raw = load_document(path.parent / names['raw'])
        raw.update(status='running', finished_at='')
        for item in raw['cases'][3:]:
            item.update(attempted=False, completed=False, started_at='', finished_at='', simulation_returned=False,
                        framework_error={})
        receipt = load_document(path)
        receipt['process'].update(process_state='timed_out', exit_code=-9)
        write_json(path.parent / names['process'], receipt['process'])
        write_json(path, receipt)
        rebind_synthetic_h_trial(path, root, raw)
        report = validate_h_analysis_trial_receipt(path, project_root=root)
        assert report['valid'] and not report['trial_complete'], report['errors']
        assert report['groups'][1]['status'] == 'unattempted'
        assert len(report['case_results']) == len(raw['cases']) and len(report['groups'][1]['case_results']) == 3


def test_rehashed_missing_native_case_never_becomes_readable_complete_trial(complete_h_trial):
    from runtime_common import load_document
    from probe_environment import write_json
    from validate_h_analysis_trial_receipt import validate_h_analysis_trial_receipt
    root, path = complete_h_trial
    with preserved_native_directory(path.parent):
        names = trial.contract()['evidence']
        raw = load_document(path.parent / names['raw'])
        raw['cases'].pop()
        write_json(path.parent / names['raw'], raw)
        receipt = load_document(path)
        receipt['artifacts'] = trial.artifact_manifest(path.parent)
        write_json(path, receipt)
        report = validate_h_analysis_trial_receipt(path, project_root=root)
        assert not report['valid'] and any('ledger cardinality' in e for e in report['errors']), report


def timing_case(tmp_path):
    case = matrix(tmp_path)[0][0]
    run_id = 'SYNTHETIC-TIMING-NO-MATLAB'
    actual = synthetic_native_case(case, tmp_path, run_id,
        state_values=lambda t: {'x1': analytic_state(case, 'x1', t)})
    return actual, run_id


@pytest.mark.parametrize('zero,offset', [(False, 0), (True, 0), (False, 19800), (False, -18000)])
def test_native_timing_zero_subsecond_and_true_local_quantization(tmp_path, zero, offset):
    actual, run_id = timing_case(tmp_path)
    p, info = actual['timing_provenance'], actual['timing_info']
    for clock_key, call_key in [('WallClockTimestampStart', 'call_started_at'), ('WallClockTimestampStop', 'call_finished_at')]:
        local = datetime.fromisoformat(p[call_key].replace('Z', '+00:00')) + timedelta(seconds=offset)
        info[clock_key] = local.strftime('%Y-%m-%d %H:%M:%S')
    p['local_utc_offset_start'] = p['local_utc_offset_stop'] = float(offset)
    if zero:
        for key in trial.TIMING_FIELDS: info[key] = 0.0
    write_synthetic_timing_primitives(actual, tmp_path, run_id)
    timing, provenance = trial.read_native_timing(actual, tmp_path, run_id, actual['case_id'])
    assert timing == info and provenance == p
    assert info['TotalElapsedWallTime'] < 1 and len(info['WallClockTimestampStart']) == 19
    assert len(p['call_started_at']) == 27


@pytest.mark.parametrize('mutation,match', [
    (lambda x: x['timing_info'].update(TotalElapsedWallTime=True), 'finite nonnegative'),
    (lambda x: x['timing_info'].update(ExecutionElapsedWallTime=float('inf')), 'finite nonnegative'),
    (lambda x: x['timing_info'].update(InitializationElapsedWallTime=-1.0), 'finite nonnegative'),
    (lambda x: x['timing_info'].update(WallClockTimestampStart='2026-01-01T00:00:00.000000Z'), 'original local timestamp format'),
    (lambda x: x['timing_info'].update(WallClockTimestampStart='2099-01-01 00:00:00', WallClockTimestampStop='2000-01-01 00:00:00'), 'timestamp order'),
    (lambda x: x['timing_info'].update(WallClockTimestampStart='2000-01-01 00:00:00', WallClockTimestampStop='2000-01-01 00:00:00'), 'quantization misses'),
    (lambda x: x['timing_info'].update(TotalElapsedWallTime=0.1), 'components and total'),
    (lambda x: x['timing_info'].update(InitializationElapsedWallTime=0.01, ExecutionElapsedWallTime=0.02, TerminationElapsedWallTime=0.03, TotalElapsedWallTime=0.06), 'duration exceeds'),
    (lambda x: x['timing_provenance'].update(local_utc_offset_start=True), 'actual local UTC offset'),
    (lambda x: x['timing_provenance'].update(clock_resolution_seconds=0.000001), 'documented resolution'),
    (lambda x: x['timing_provenance'].update(call_started_at='2000-01-01T00:00:00.000000Z'), 'actual case enclosure'),
    (lambda x: x['timing_provenance'].update(call_finished_at=x['timing_provenance']['call_started_at']), 'duration exceeds'),
])
def test_native_timing_rejects_source_and_impossible_physical_metadata(tmp_path, mutation, match):
    actual, run_id = timing_case(tmp_path)
    mutation(actual)
    # Rebind even the primitive file: rejection must come from the physical
    # source/type/interval gate, not a stale artifact hash or JSON mismatch.
    write_synthetic_timing_primitives(actual, tmp_path, run_id)
    with pytest.raises(ValueError, match=match):
        trial.read_native_timing(actual, tmp_path, run_id, actual['case_id'])


@pytest.mark.parametrize('field,kind', [
    ('timing_durations', 'single'), ('timing_durations', 'logical'),
    ('timing_durations', 'complex'), ('timing_durations', 'row'),
    ('timing_durations', 'altered'), ('timing_durations', 'missing'),
    ('timing_utc_offsets', 'altered'), ('timing_resolutions', 'altered'),
    ('timing_start_local', 'altered'), ('timing_call_start_utc', 'altered'),
])
def test_native_timing_primitive_MAT_types_shapes_and_exact_JSON_values(tmp_path, field, kind):
    actual, run_id = timing_case(tmp_path)
    mat = write_synthetic_timing_primitives(actual, tmp_path, run_id)
    if kind == 'single': mat[field] = mat[field].astype(np.float32)
    if kind == 'logical': mat[field] = mat[field].astype(bool)
    if kind == 'complex': mat[field] = mat[field].astype(complex) + 1j
    if kind == 'row': mat[field] = mat[field].T
    if kind == 'missing': del mat[field]
    if kind == 'altered':
        if isinstance(mat[field], str): mat[field] = 'DIFFERENT NATIVE CLOCK'
        else: mat[field][0, 0] += 0.01
    savemat(tmp_path / actual['raw_mat_file'], mat, format='5')
    with pytest.raises(ValueError, match='primitive MAT'):
        trial.read_native_timing(actual, tmp_path, run_id, actual['case_id'])


def test_native_timing_timestamp_difference_must_agree_with_elapsed_quantization(tmp_path):
    actual, run_id = timing_case(tmp_path)
    actual.update(started_at='2020-01-01T00:00:00.000000Z', finished_at='2020-01-01T00:00:03.000000Z')
    actual['timing_provenance'].update(call_started_at=actual['started_at'], call_finished_at=actual['finished_at'])
    actual['timing_info'].update(WallClockTimestampStart='2020-01-01 00:00:00', WallClockTimestampStop='2020-01-01 00:00:03')
    write_synthetic_timing_primitives(actual, tmp_path, run_id)
    with pytest.raises(ValueError, match='elapsed and timestamp quantization are incompatible'):
        trial.read_native_timing(actual, tmp_path, run_id, actual['case_id'])


def test_native_timing_component_resolution_does_not_replace_exact_primitive_values(tmp_path):
    actual, run_id = timing_case(tmp_path)
    actual['timing_info']['TotalElapsedWallTime'] += 2e-6
    mat = write_synthetic_timing_primitives(actual, tmp_path, run_id)
    trial.read_native_timing(actual, tmp_path, run_id, actual['case_id'])
    mat['timing_durations'][3, 0] -= 1e-6
    savemat(tmp_path / actual['raw_mat_file'], mat, format='5')
    with pytest.raises(ValueError, match='MAT double-column/JSON exact mismatch'):
        trial.read_native_timing(actual, tmp_path, run_id, actual['case_id'])


def test_rehashed_whole_profile_cannot_substitute_native_timing_primitive(complete_h_profile):
    from runtime_common import load_document
    from validate_h_analysis_profile import validate_h_analysis_profile
    with preserved_native_directory(complete_h_profile.parent):
        raw = load_document(complete_h_profile.parent / trial.contract()['evidence']['raw'])
        actual = raw['cases'][0]
        directory = complete_h_profile.parent / 'cases' / actual['case_id']
        mat = write_synthetic_timing_primitives(actual, directory, raw['run_id'])
        mat['timing_durations'][1, 0] += 0.01
        savemat(directory / actual['raw_mat_file'], mat, format='5')
        rebind_synthetic_h_profile(complete_h_profile, raw)
        report = validate_h_analysis_profile(complete_h_profile)
        assert not report['valid'] and not report['h_analysis_assured'], report
        assert any('TimingInfo primitive MAT' in error for row in report['case_results'] for error in row['errors']), report


def dense_forecast_request(tmp_path, *, knots):
    """Review's independent exact-count construction, without native launch."""
    cases = deepcopy(matrix(tmp_path)[0][:3])
    for level, case in enumerate(cases):
        spec = case['run_spec']
        spec['solver']['fixed_step'] = 2.0 / (3000 * 2 ** level)
        spec['inputs'] = [{**spec['inputs'][0], 'port': port, 'block_path': spec['model_name'] + '/Input' + str(port),
                           'time': [2.0 * i / (knots - 1) for i in range(knots)], 'values': [1.0] * knots} for port in range(1, 9)]
        spec['outputs'] = [{**spec['outputs'][0], 'port': port, 'block_path': spec['model_name'] + '/Output' + str(port)} for port in range(1, 9)]
        case['states'] = [{**case['states'][0], 'variable_id': 'x' + str(i), 'block_path': case['build_spec']['model_name'] + '/State' + str(i)} for i in range(1, 5)]
        case['initial_conditions'] = [{**state, 'value': 0.2} for state in case['states']]
        blocks = []
        connections = []
        model = spec['model_name']
        for i in range(1, 9):
            blocks.extend([{'id': 'Input' + str(i), 'path': model + '/Input' + str(i), 'type': 'Inport', 'parameters': {'Port': str(i)}},
                           {'id': 'Output' + str(i), 'path': model + '/Output' + str(i), 'type': 'Outport', 'parameters': {'Port': str(i)}}])
            connections.append({'source': {'block_id': 'State' + str((i - 1) % 4 + 1), 'port': 1},
                                'destination': {'block_id': 'Output' + str(i), 'port': 1}})
        for i in range(1, 5):
            blocks.append({'id': 'State' + str(i), 'path': model + '/State' + str(i), 'type': 'Integrator', 'parameters': {'InitialCondition': '0.25'}})
            connections.append({'source': {'block_id': 'Input' + str(i), 'port': 1}, 'destination': {'block_id': 'State' + str(i), 'port': 1}})
        case['build_spec']['blocks'], case['build_spec']['connections'] = blocks, connections
    return {'cases': cases, 'groups': [{'group_id': 'SYNTHETIC-dense-triplet',
                'physical_snapshot': trial.physical_snapshot(cases[0]['run_spec'], cases[0]['initial_conditions'])}],
            'budget': deepcopy(trial.contract()['hard_budget']), 'output_directory': str(tmp_path)}


def test_raw_forecast_rejects_dense_constant_inputs_when_request_itself_fits(tmp_path):
    from verification_common import serialization_forecast
    request = dense_forecast_request(tmp_path, knots=12001)
    for case in request['cases']:
        trial.validate_case_spec(case, mode='trial', budget=request['budget'])
    measured = serialization_forecast(request, request['budget'])
    assert measured['nodes'] < 1000000
    sample_nodes = 25 * (3001 + 6001 + 12001) + 3 * 8 * 2 * 12001
    assert sample_nodes == 1101123
    with pytest.raises(ValueError, match='raw report forecast exceeds document node budget'):
        trial.forecast_native_report(request)
    assert not (tmp_path / trial.contract()['evidence']['input']).exists()


def test_raw_forecast_short_inputs_pass_nodes_and_account_prettyprint_bytes(tmp_path):
    request = dense_forecast_request(tmp_path, knots=2)
    forecast = trial.forecast_native_report(request)
    assert forecast['sample_numbers'] == 25 * (3001 + 6001 + 12001) + 3 * 8 * 4
    assert forecast['sample_numbers'] < forecast['nodes'] < 1000000
    assert forecast['bytes_upper_bound'] > 32 * forecast['sample_numbers']
    request['budget']['max_file_bytes'] = forecast['bytes_upper_bound'] - 1
    with pytest.raises(ValueError, match='declared file byte budget'):
        trial.forecast_native_report(request)


def test_raw_forecast_measures_copied_and_escaped_metadata_strings(tmp_path):
    request = {'cases': deepcopy(matrix(tmp_path)[0][:3]), 'budget': deepcopy(trial.contract()['hard_budget'])}
    base = trial.forecast_native_report(request)
    for case in request['cases']:
        case['run_spec']['inputs'][0]['unit'] = '\n"\\' * 1000
    escaped = trial.forecast_native_report(request)
    added_per_case = len(json.dumps('\n"\\' * 1000, ensure_ascii=True)) - len(json.dumps('1', ensure_ascii=True))
    assert escaped['nodes'] == base['nodes']
    assert escaped['bytes_upper_bound'] - base['bytes_upper_bound'] == 3 * added_per_case
