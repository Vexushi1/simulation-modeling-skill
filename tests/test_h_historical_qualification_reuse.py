"""Whole-wire synthetic controls for private historical A/E/H proof reuse.

These tests build explicitly SYNTHETIC records and call the actual readers.
They neither execute MATLAB nor replace a validator with a successful report.
"""
from contextlib import contextmanager
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

import pytest

import h_analysis_trial as native
import validate_h_analysis_trial_receipt as reader
import verification_common as shared
from h_analysis_native_factory import write_synthetic_timing_primitives
from probe_environment import write_json
from runtime_common import load_document
from validate_environment import _time


@pytest.fixture(scope='module')
def historical_pair(tmp_path_factory):
    from numerical_factory import make_numerical_runs
    from run_numerical_verification import run_numerical_verification
    from h_analysis_study_factory import make_study_for_primary, make_study_history
    root = tmp_path_factory.mktemp('SYNTHETIC-historical-qualification-reuse')
    contract, receipts = make_numerical_runs(root)
    primary = run_numerical_verification(contract, receipts, root / 'primary-h1', project_root=root)
    assert primary['valid'] and primary['numerically_verified'], primary['errors']
    first_study = make_study_for_primary(primary['receipt_path'], project_root=root, filename='study-one.json')
    second_study = make_study_for_primary(primary['receipt_path'], project_root=root, filename='study-two.json')
    first = make_study_history(first_study, project_root=root, output_name='study-one-evidence')
    profile = root / 'synthetic-h-profile' / native.contract()['evidence']['profile']
    second = make_study_history(second_study, project_root=root, output_name='study-two-evidence', h_profile=profile)
    name = native.contract()['evidence']['run_receipt']
    return root, first.parent / 'trial-batch-000001' / name, second.parent / 'trial-batch-000001' / name, profile


@contextmanager
def preserve(directory):
    directory = Path(directory)
    original = {path: path.read_bytes() for path in directory.rglob('*') if path.is_file()}
    try:
        yield
    finally:
        for path in directory.rglob('*'):
            if path.is_file() and path not in original:
                path.unlink()
        for path, data in original.items():
            path.write_bytes(data)


def task(path):
    names = native.contract()['evidence']
    return load_document(path.parent / names['input']), load_document(path.parent / names['raw'])


def rehash_trial(path, raw, *, process=None):
    """Rehash exact native bytes without manufacturing a passing assessment."""
    names = native.contract()['evidence']
    receipt = load_document(path)
    write_json(path.parent / names['raw'], raw)
    if process is not None:
        receipt['process'] = process
        write_json(path.parent / names['process'], process)
    receipt['artifacts'] = native.artifact_manifest(path.parent)
    write_json(path, receipt)


def spy_actual_consumers(monkeypatch):
    calls = {'full': [], 'native': [], 'numeric': [], 'case_gates': []}
    original_full = native._collect_qualification_facts
    original_native = reader.assert_case
    original_apply = native._apply_qualification_facts
    import numerical_obligations
    original_numeric = numerical_obligations.evaluate_trial_numeric

    def full(request, case, started_at, *, include_h):
        if request['mode'] == 'trial' and include_h:
            calls['full'].append(request['run_id'])
        return original_full(request, case, started_at, include_h=include_h)

    def actual_case(actual, case, directory, run_id, budget):
        calls['native'].append((run_id, case['case_id']))
        return original_native(actual, case, directory, run_id, budget)

    def numeric(levels, policy, context=None, **kwargs):
        if kwargs.get('project_id') != 'SYNTHETIC-H-QUALIFICATION':
            calls['numeric'].append(tuple(level['case_id'] for level in levels))
        return original_numeric(levels, policy, context, **kwargs)

    def apply(request, case, started_at, facts, *, include_h):
        try:
            result = original_apply(request, case, started_at, facts, include_h=include_h)
        except ValueError as error:
            if request['mode'] == 'trial':
                calls['case_gates'].append((request['run_id'], case['case_id'], str(error)))
            raise
        if request['mode'] == 'trial':
            calls['case_gates'].append((request['run_id'], case['case_id'], None))
        return result

    monkeypatch.setattr(native, '_collect_qualification_facts', full)
    monkeypatch.setattr(reader, 'assert_case', actual_case)
    monkeypatch.setattr(native, '_apply_qualification_facts', apply)
    monkeypatch.setattr(numerical_obligations, 'evaluate_trial_numeric', numeric)
    return calls


def test_distinct_studies_share_real_qualification_only_and_check_every_actual_level(historical_pair, monkeypatch):
    root, first, second, _ = historical_pair
    one_request, _ = task(first)
    two_request, _ = task(second)
    assert one_request['run_id'] != two_request['run_id']
    assert one_request['bindings']['study'] != two_request['bindings']['study']
    calls = spy_actual_consumers(monkeypatch)
    with shared.validation_session():
        one = reader.validate_h_analysis_trial_receipt(first, project_root=root)
        two = reader.validate_h_analysis_trial_receipt(second, project_root=root)
    assert one['valid'] and one['trial_complete'] and one['numerically_verified'], one['errors']
    assert two['valid'] and two['trial_complete'] and two['numerically_verified'], two['errors']
    assert len(calls['full']) == 1, calls['full']
    expected_cases = {(r['run_id'], c['case_id']) for r in (one_request, two_request) for c in r['cases']}
    assert set(calls['native']) == expected_cases and len(calls['native']) == len(expected_cases)
    assert {(run_id, case_id) for run_id, case_id, error in calls['case_gates'] if error is None} == expected_cases
    assert set(calls['numeric']) == {tuple(g['case_ids']) for r in (one_request, two_request) for g in r['groups']}
    assert len(calls['numeric']) == len(one_request['groups']) + len(two_request['groups'])


def test_independent_public_calls_never_retain_a_previous_session(historical_pair, monkeypatch):
    root, first, second, _ = historical_pair
    calls = spy_actual_consumers(monkeypatch)
    one = reader.validate_h_analysis_trial_receipt(first, project_root=root)
    two = reader.validate_h_analysis_trial_receipt(second, project_root=root)
    assert one['valid'] and two['valid'], [one['errors'], two['errors']]
    assert len(calls['full']) == 2


def test_returned_runtime_cannot_modify_the_committed_private_fact(historical_pair, monkeypatch):
    root, first, second, _ = historical_pair
    calls = spy_actual_consumers(monkeypatch)
    with shared.validation_session():
        one = reader.validate_h_analysis_trial_receipt(first, project_root=root)
        assert one['valid'], one['errors']
        version = one['runtime']['version']
        one['runtime']['version'] = 'SYNTHETIC caller mutation; never evidence'
        one['groups'][0]['levels'][0]['timing_info']['TotalElapsedWallTime'] = -1
        two = reader.validate_h_analysis_trial_receipt(second, project_root=root)
    assert two['valid'] and two['trial_complete'], two['errors']
    assert two['runtime']['version'] == version
    assert len(calls['full']) == 1


@pytest.mark.parametrize('cap', ['_MEMO_ENTRIES', '_MEMO_BYTES'])
def test_shared_capacity_exhaustion_uses_real_original_consumers(historical_pair, monkeypatch, cap):
    root, first, second, _ = historical_pair
    calls = spy_actual_consumers(monkeypatch)
    monkeypatch.setattr(shared, cap, 0 if cap == '_MEMO_ENTRIES' else 1)
    with shared.validation_session():
        one = reader.validate_h_analysis_trial_receipt(first, project_root=root)
        two = reader.validate_h_analysis_trial_receipt(second, project_root=root)
    assert one['valid'] and two['valid'], [one['errors'], two['errors']]
    assert len(calls['full']) == 2


@pytest.mark.parametrize('forged', [None, True, {'valid': True, 'complete': True}])
def test_ambient_session_and_caller_marker_cannot_enable_direct_case_reuse(historical_pair, monkeypatch, forged):
    root, first, _, _ = historical_pair
    request, raw = task(first)
    calls = spy_actual_consumers(monkeypatch)
    with shared.validation_session():
        accepted = reader.validate_h_analysis_trial_receipt(first, project_root=root)
        assert accepted['valid'], accepted['errors']
        runtime = native.validate_case_qualifications(request, request['cases'][0], raw['cases'][0]['started_at'],
                                                      _historical_replay=forged)
    assert runtime['executable'] == request['matlab_executable']
    assert len(calls['full']) == 2


def test_include_h_false_retains_full_original_profile_consumers(historical_pair, monkeypatch):
    root, first, _, _ = historical_pair
    request, raw = task(first)
    original = native._collect_qualification_facts
    direct = []

    def collect(r, c, start, *, include_h):
        if r is request:
            direct.append(include_h)
        return original(r, c, start, include_h=include_h)

    monkeypatch.setattr(native, '_collect_qualification_facts', collect)
    with shared.validation_session():
        accepted = reader.validate_h_analysis_trial_receipt(first, project_root=root)
        assert accepted['valid'], accepted['errors']
        for _ in range(2):
            native.validate_case_qualifications(request, request['cases'][0], raw['cases'][0]['started_at'], include_h=False)
    assert direct == [False, False]


def test_current_profile_and_expired_profile_always_use_the_original_gate(historical_pair, monkeypatch):
    from validate_h_analysis_profile import validate_h_analysis_profile
    import validate_h_analysis_profile as profile_reader
    root, first, _, profile = historical_pair
    original = profile_reader.derive_profile
    calls = []

    def derive(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)

    with shared.validation_session():
        accepted = reader.validate_h_analysis_trial_receipt(first, project_root=root)
        assert accepted['valid'], accepted['errors']
        monkeypatch.setattr(profile_reader, 'derive_profile', derive)
        current = validate_h_analysis_profile(profile)
        expired = validate_h_analysis_profile(profile, now=_time(load_document(profile)['valid_until']) + timedelta(microseconds=1))
    assert current['valid'] and current['profile_current'], current['errors']
    assert not expired['valid'] and any('expired' in error for error in expired['errors'])
    assert len(calls) == 2


def test_sealed_capability_cannot_move_to_a_copied_request_or_outlive_its_scope(historical_pair, monkeypatch):
    root, first, _, _ = historical_pair
    request, raw = task(first)
    calls = spy_actual_consumers(monkeypatch)
    original = reader.validate_case_qualifications
    captured = []

    def per_case(r, case, start, **kwargs):
        replay = kwargs.get('_historical_replay')
        if not captured and isinstance(replay, native._HistoricalReplay):
            assert replay.matches(r)
            clone = deepcopy(r)
            assert not replay.matches(clone)
            native.validate_case_qualifications(clone, clone['cases'][0], start, _historical_replay=replay)
            captured.append(replay)
        return original(r, case, start, **kwargs)

    monkeypatch.setattr(reader, 'validate_case_qualifications', per_case)
    with shared.validation_session():
        assert native._mint_historical_replay(request, raw, first.parent) is None
        accepted = reader.validate_h_analysis_trial_receipt(first, project_root=root)
        assert accepted['valid'], accepted['errors']
        assert len(captured) == 1
        replay = captured[0]
        assert not replay.matches(replay._request)
        assert not replay.matches(request)
        native.validate_case_qualifications(request, request['cases'][0], raw['cases'][0]['started_at'], _historical_replay=replay)
    assert len(calls['full']) == 3


def test_every_case_rechecks_solver_and_exact_deadline_after_request_local_hit(historical_pair):
    _, first, _, _ = historical_pair
    request, raw = task(first)
    cache = {}
    native.validate_case_qualifications(request, request['cases'][0], raw['cases'][0]['started_at'], _cache=cache)
    wrong = deepcopy(request['cases'][1])
    wrong['qualification_not_after'] = native.stable_utc(_time(wrong['qualification_not_after']) + timedelta(microseconds=1))
    with pytest.raises(ValueError, match='solver/deadline'):
        native.validate_case_qualifications(request, wrong, raw['cases'][1]['started_at'], _cache=cache)
    with pytest.raises(ValueError, match='time windows'):
        native.validate_case_qualifications(request, request['cases'][1],
            _time(request['cases'][1]['qualification_not_after']) + timedelta(microseconds=1), _cache=cache)
    wrong = deepcopy(request['cases'][1])
    wrong['run_spec']['solver']['name'] = 'UNQUALIFIED-SYNTHETIC-SOLVER'
    with pytest.raises(ValueError, match='solver/deadline'):
        native.validate_case_qualifications(request, wrong, raw['cases'][1]['started_at'], _cache=cache)


def test_reused_proof_rejects_case_between_capture_and_qualification_process_finish(historical_pair, monkeypatch):
    root, first, second, profile = historical_pair
    calls = spy_actual_consumers(monkeypatch)
    with preserve(second.parent), shared.validation_session():
        accepted = reader.validate_h_analysis_trial_receipt(first, project_root=root)
        assert accepted['valid'], accepted['errors']
        request, raw = task(second)
        names = native.contract()['evidence']
        h = load_document(profile)
        h_receipt = load_document(profile.parent / names['profile_receipt'])
        start = _time(h['captured_at'])
        assert start < _time(h_receipt['process']['finished_at'])
        actual = raw['cases'][0]
        duration = actual['timing_info']['TotalElapsedWallTime']
        call_start = start + timedelta(microseconds=1)
        call_stop = call_start + timedelta(seconds=duration, microseconds=1)
        actual.update(started_at=native.stable_utc(start), finished_at=native.stable_utc(call_stop + timedelta(microseconds=1)))
        actual['timing_provenance'].update(call_started_at=native.stable_utc(call_start), call_finished_at=native.stable_utc(call_stop))
        actual['timing_info'].update(WallClockTimestampStart=call_start.strftime('%Y-%m-%d %H:%M:%S'),
                                    WallClockTimestampStop=call_stop.strftime('%Y-%m-%d %H:%M:%S'))
        write_synthetic_timing_primitives(actual, second.parent / 'cases' / actual['case_id'], request['run_id'])
        raw['started_at'] = native.stable_utc(start - timedelta(microseconds=1))
        process = load_document(second)['process']
        process['started_at'] = native.stable_utc(start - timedelta(microseconds=2))
        rehash_trial(second, raw, process=process)
        rejected = reader.validate_h_analysis_trial_receipt(second, project_root=root)
    assert not rejected['valid'], rejected
    assert len(calls['full']) == 1, calls['full']
    assert any('completion floor' in (error or '') for run_id, _, error in calls['case_gates'] if run_id == request['run_id'])


def test_new_qualification_owned_file_is_freshly_detected_after_committed_proof(historical_pair):
    root, first, second, profile = historical_pair
    with preserve(profile.parent), shared.validation_session():
        accepted = reader.validate_h_analysis_trial_receipt(first, project_root=root)
        assert accepted['valid'], accepted['errors']
        (profile.parent / 'SYNTHETIC-unlisted-evidence.txt').write_text('SYNTHETIC inventory mutation; not approved evidence.\n', encoding='utf-8')
        rejected = reader.validate_h_analysis_trial_receipt(second, project_root=root)
    assert not rejected['valid'], rejected


def test_reused_qualification_never_skips_a_changed_raw_timing_primitive(historical_pair, monkeypatch):
    from scipy.io import loadmat, savemat
    root, first, second, _ = historical_pair
    calls = spy_actual_consumers(monkeypatch)
    with preserve(second.parent), shared.validation_session():
        accepted = reader.validate_h_analysis_trial_receipt(first, project_root=root)
        assert accepted['valid'], accepted['errors']
        request, raw = task(second)
        actual = raw['cases'][0]
        mat_path = second.parent / 'cases' / actual['case_id'] / actual['raw_mat_file']
        primitive = {key: value for key, value in loadmat(mat_path).items() if not key.startswith('__')}
        primitive['timing_durations'][0, 0] += 0.000001
        savemat(mat_path, primitive, format='5')
        rehash_trial(second, raw)
        rejected = reader.validate_h_analysis_trial_receipt(second, project_root=root)
    assert not rejected['valid'], rejected
    assert len(calls['full']) == 1
    assert len(calls['native']) == len(task(first)[0]['cases']) + len(request['cases'])


def test_incomplete_historical_receipt_does_not_publish_qualification_facts(historical_pair, monkeypatch):
    from validate_h_analysis_study import validate_h_analysis_study
    root, first, second, _ = historical_pair
    with preserve(first.parent):
        request, raw = task(first)
        raw['cases'][0].update(completed=False, framework_error={'identifier': 'SYNTHETIC:Failure', 'message': 'SYNTHETIC controlled native incompleteness'})
        report = validate_h_analysis_study(request['bindings']['study']['path'], project_root=root, require_reviewed=True)
        write_json(first.parent / native.contract()['evidence']['raw'], raw)
        receipt = load_document(first)
        checked = reader.assess_trial_request(request, raw, first.parent, report, process=receipt['process'])
        assert not checked['complete']
        receipt.update(status='incomplete', numeric_results=checked['numeric_results'], errors=checked['errors'],
                       artifacts=native.artifact_manifest(first.parent))
        write_json(first, receipt)
        calls = spy_actual_consumers(monkeypatch)
        with shared.validation_session():
            incomplete = reader.validate_h_analysis_trial_receipt(first, project_root=root)
            complete = reader.validate_h_analysis_trial_receipt(second, project_root=root)
        assert incomplete['valid'] and not incomplete['trial_complete'], incomplete['errors']
        assert complete['valid'] and complete['trial_complete'], complete['errors']
        assert len(calls['full']) == 2


def test_receipt_failure_after_native_checks_does_not_publish_qualification_facts(historical_pair, monkeypatch):
    root, first, second, _ = historical_pair
    with preserve(first.parent):
        receipt = load_document(first)
        receipt['numeric_results'][0]['physical_sha256'] = '0' * 64
        write_json(first, receipt)
        calls = spy_actual_consumers(monkeypatch)
        with shared.validation_session():
            failed = reader.validate_h_analysis_trial_receipt(first, project_root=root)
            complete = reader.validate_h_analysis_trial_receipt(second, project_root=root)
        assert not failed['valid'] and any('numerical recomputation' in error for error in failed['errors'])
        assert complete['valid'] and complete['trial_complete'], complete['errors']
        assert len(calls['full']) == 2


def test_in_memory_raw_scope_change_at_final_guard_cannot_publish_a_proof(historical_pair, monkeypatch):
    root, first, second, _ = historical_pair
    calls = spy_actual_consumers(monkeypatch)
    original_case = reader.validate_case_qualifications
    original_unchanged = reader.assert_unchanged
    captured = []
    mutated = []

    def case(r, c, start, **kwargs):
        replay = kwargs.get('_historical_replay')
        if not captured and isinstance(replay, native._HistoricalReplay):
            captured.append(replay)
        return original_case(r, c, start, **kwargs)

    def unchanged(manifest):
        original_unchanged(manifest)
        if captured and not mutated and any(Path(entry['path']) == first for entry in manifest):
            captured[0]._raw['cases'][0]['last_warning_message'] = 'SYNTHETIC in-memory mutation after original final guard'
            mutated.append(True)

    monkeypatch.setattr(reader, 'validate_case_qualifications', case)
    monkeypatch.setattr(reader, 'assert_unchanged', unchanged)
    with shared.validation_session():
        failed = reader.validate_h_analysis_trial_receipt(first, project_root=root)
        complete = reader.validate_h_analysis_trial_receipt(second, project_root=root)
    assert mutated and not failed['valid']
    assert any('request/raw scope changed before publication' in error for error in failed['errors'])
    assert complete['valid'] and complete['trial_complete'], complete['errors']
    assert len(calls['full']) == 2
