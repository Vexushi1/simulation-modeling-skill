"""Actual whole-wire controls for operation-local H proof reuse.

Fixtures and every acceptance result are explicitly SYNTHETIC INFRASTRUCTURE
TESTS. These controls call the actual consumers; they never execute MATLAB or
substitute a successful validator report.
"""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import os
import sys
import weakref

import pytest

import verification_common as shared
import validate_h_analysis_study as source_reader
import validate_h_analysis_study_receipt as study_reader
import validate_model_verification as h2_source_reader
import validate_model_verification_receipt as h2_reader
from runtime_common import load_document
from test_h_analysis_integration import full_wire_history
from test_h_analysis_study import explicit_parent_state_history


@contextmanager
def preserved(*directories):
    files = {p: p.read_bytes() for d in directories for p in Path(d).rglob('*') if p.is_file()}
    try:
        yield
    finally:
        for directory in directories:
            for path in Path(directory).rglob('*'):
                if path.is_file() and path not in files:
                    path.unlink()
        for path, data in files.items():
            path.write_bytes(data)


def readers(item):
    root = item['root']
    return (
        lambda: source_reader.validate_h_analysis_study(item['study'], project_root=root, require_reviewed=True),
        lambda: study_reader.validate_h_analysis_study_receipt(item['study_receipt'], project_root=root),
        lambda: h2_source_reader.validate_model_verification(item['h2'], project_root=root, require_reviewed=True),
        lambda: h2_reader.validate_model_verification_receipt(item['h2_receipt'], project_root=root),
    )


def spy_original(monkeypatch, module, name, calls, label):
    original = getattr(module, name)
    def observe(*args, **kwargs):
        calls.append(label)
        return original(*args, **kwargs)
    monkeypatch.setattr(module, name, observe)


def test_actual_four_roles_and_three_baselines_reuse_with_fresh_whole_graph_and_independent_copies(full_wire_history, monkeypatch):
    from json import dumps
    item = full_wire_history
    calls, guards, phases, active_phases, issues = [], [], [], [], []
    proof_events, role_in_progress, read_ordinal = [], None, 0
    capacity_samples = []
    original_capacity, original_builder_check = shared._memo_capacity, shared._memo_builder_check
    common_file = str(Path(shared.__file__).resolve())
    def own_role_frame(frame):
        try:
            while frame is not None:
                if (str(Path(frame.f_code.co_filename).resolve()) == common_file and
                        frame.f_code.co_name == '_attempt_h_validation_reuse'):
                    return frame.f_locals.get('kind') == role_in_progress
                frame = frame.f_back
            return False
        finally:
            del frame
    def capacity(*args, **kwargs):
        sample = {'live_measured': False, 'reserve_measured': False, 'live_bytes': None, 'reserve_bytes': None}
        capacity_samples.append(sample)
        try:
            return original_capacity(*args, **kwargs)
        except shared._MemoCapacityUnavailable as error:
            caller = sys._getframe(1)
            try:
                if role_in_progress is not None and own_role_frame(caller):
                    proof_events.append({'role': role_in_progress, 'read': read_ordinal,
                        'event': 'own_guard_capacity_refusal', 'phase': caller.f_code.co_name,
                        'line': caller.f_lineno, 'message': str(error),
                        'byte_limit': min(shared._MEMO_BYTES, 64 * 1024 * 1024), **sample})
            finally:
                del caller
            raise
        finally:
            capacity_samples.pop()
    def capacity_size(value, actual):
        caller = sys._getframe(2)
        try:
            if (capacity_samples and caller.f_code.co_name == '_memo_capacity' and
                    str(Path(caller.f_code.co_filename).resolve()) == common_file):
                sample = capacity_samples[-1]
                if value is caller.f_locals.get('reserve'):
                    sample['reserve_measured'], sample['reserve_bytes'] = True, actual
                else:
                    sample['live_measured'], sample['live_bytes'] = True, actual
        finally:
            del caller
    def builder_check(ledger, extra=0):
        try:
            return original_builder_check(ledger, extra)
        except shared._MemoCapacityUnavailable as error:
            caller = sys._getframe(1)
            try:
                if role_in_progress is not None and own_role_frame(caller):
                    proof_events.append({'role': role_in_progress, 'read': read_ordinal,
                        'event': 'own_builder_capacity_refusal', 'phase': caller.f_code.co_name,
                        'line': caller.f_lineno, 'base': ledger['base'],
                        'charged': ledger['charged'], 'extra': extra, 'message': str(error),
                        'byte_limit': min(shared._MEMO_BYTES, 64 * 1024 * 1024)})
            finally:
                del caller
            raise
    def attempt_size(actual):
        caller = sys._getframe(2)
        try:
            if (role_in_progress is not None and caller.f_code.co_name == '_attempt_h_validation_reuse' and
                    str(Path(caller.f_code.co_filename).resolve()) == common_file and
                    caller.f_locals.get('kind') == role_in_progress):
                proof_events.append({'role': role_in_progress, 'read': read_ordinal,
                    'event': 'own_attempt_admission_size', 'line': caller.f_lineno,
                    'bytes': actual, 'byte_limit': min(shared._MEMO_BYTES, 64 * 1024 * 1024)})
        finally:
            del caller
    def publication_size(value, actual):
        caller = sys._getframe(2)
        try:
            if (role_in_progress is not None and caller.f_code.co_name == '_publish_validation' and
                    str(Path(caller.f_code.co_filename).resolve()) == common_file):
                key = caller.f_locals.get('key')
                if type(key) is tuple and key[0] == role_in_progress and type(value) is tuple and len(value) in (2, 4):
                    proof_events.append({'role': role_in_progress, 'read': read_ordinal,
                        'event': 'own_publication_size', 'part': 'live' if len(value) == 4 else 'copy',
                        'bytes': actual, 'byte_limit': min(shared._MEMO_BYTES, 64 * 1024 * 1024)})
        finally:
            del caller
    monkeypatch.setattr(shared, '_memo_capacity', capacity)
    monkeypatch.setattr(shared, '_memo_builder_check', builder_check)
    original_size = shared._retained_size
    def size(value):
        if active_phases:
            phase = active_phases[-1]
            if type(value) is tuple and any(type(child) is shared._ValidationSession for child in value):
                phase['full'] += 1
            else:
                phase['local'] += 1
                if type(value) is dict and ('cases' in value or 'operations' in value):
                    for key in ('cases', 'operations'):
                        records = value.get(key)
                        phase['records'] += len(records) if type(records) is list else int(type(records) is dict)
        actual = original_size(value)
        capacity_size(value, actual)
        attempt_size(actual)
        publication_size(value, actual)
        return actual
    def phase_observer(name, original):
        def observe(*args, **kwargs):
            phase = {'name': name, 'full': 0, 'local': 0, 'records': 0, 'complete': False}
            phases.append(phase)
            active_phases.append(phase)
            try:
                result = original(*args, **kwargs)
                phase['complete'] = True
                return result
            finally:
                active_phases.pop()
        return observe
    def check(condition, obligation, **evidence):
        if not condition:
            issues.append({'role': role_in_progress, 'obligation': obligation, **evidence})
    monkeypatch.setattr(shared, '_retained_size', size)
    for name in ('_memo_extra_preflight', '_memo_extras'):
        monkeypatch.setattr(shared, name, phase_observer(name, getattr(shared, name)))
    baseline_labels = ('validate_simulation_protocol', 'validate_simulation_receipt', 'validate_numerical_verification_receipt')
    for name in baseline_labels:
        spy_original(monkeypatch, source_reader, name, calls, name)
    spy_original(monkeypatch, source_reader, 'schema_errors', calls, 'study_source')
    spy_original(monkeypatch, h2_source_reader, 'schema_errors', calls, 'h2_source')
    spy_original(monkeypatch, study_reader, 'assess_study', calls, 'study_metric')
    spy_original(monkeypatch, h2_reader, 'compute_assessment', calls, 'h2_metric')
    spy_original(monkeypatch, shared, 'input_manifest', guards, 'fresh_manifest')
    roles = ('study_source', 'study_receipt', 'h2_source', 'h2_receipt')
    labels = ('study_source', 'study_metric', 'h2_source', 'h2_metric')
    ready_fields = ('study_ready', 'study_complete', 'assessment_ready', 'model_verified')
    for kind, label, ready, call in zip(roles, labels, ready_fields, readers(item)):
        role_in_progress = kind
        initial_calls = calls.count(label)
        baseline_before = {name: calls.count(name) for name in baseline_labels}
        with shared.validation_session() as session:
            read_ordinal = 1
            cold_before = len(guards)
            first = call()
            check(len(guards) >= cold_before + 3, 'complete cold pre/after/final manifests')
            before = len(guards)
            cached_before = any(key[0] == kind for key in session.entries)
            read_ordinal = 2
            second = call()
            check(first['valid'] and second['valid'], 'actual cold and adjacent reread valid',
                  errors=[first['errors'], second['errors']])
            check(first.get(ready) is True, 'actual role readiness')
            if kind == 'study_receipt':
                check(first.get('defined') is True, 'actual study defined')
            check(shared.typed_equal(first, second), 'cold and adjacent reread typed equal')
            check(len(guards) >= before + 2, 'complete fresh pre/final manifests on adjacent reread')
            check(cached_before and any(key[0] == kind for key in session.entries),
                  'own actual role proof retained for demonstrated hit')
            check(calls.count(label) - initial_calls == 1, 'strict one actual own computation through reread',
                  actual=calls.count(label) - initial_calls)
            # Mutate each returned role without retaining all four private proofs.
            if kind == 'study_source':
                second['metric']['unit'] = 'SYNTHETIC caller mutation'
            else:
                second[ready] = False
            read_ordinal = 3
            third_before = len(guards)
            third = call()
            check(len(guards) >= third_before + 2, 'complete fresh pre/final manifests after caller mutation')
            check(third['valid'] and shared.typed_equal(first, third), 'actual returned-copy isolation')
            check(calls.count(label) - initial_calls == 1, 'strict one actual own computation after caller mutation',
                  actual=calls.count(label) - initial_calls)
            if kind == 'study_source':
                check({key[0] for key in session.entries} >=
                      {'study_source', 'baseline_protocol', 'baseline_simulation', 'baseline_h1'},
                      'source and its actual baseline triplet retained')
                check(all(calls.count(name) - baseline_before[name] == 1 for name in baseline_labels),
                      'strict one actual computation per baseline',
                      actual={name: calls.count(name) - baseline_before[name] for name in baseline_labels})
            check(not any('memo' in key or 'session' in key for report in (first, second, third) for key in report),
                  'private proof metadata absent from all public reports')
            check(shared._retained_size(session) is not None, 'actual session bounded and measurable')
        check(not session.active and not session.entries and not session.capabilities,
              'each role session releases all proof and capabilities')
        check(shared._H_VALIDATION_SESSION.get() is None, 'each role releases ambient session')
    role_in_progress = None
    completed = [phase for phase in phases if phase['complete']]
    check({phase['name'] for phase in completed} == {'_memo_extra_preflight', '_memo_extras'},
          'both closed accounting phases complete', completed=completed)
    check(all(0 < phase['full'] <= 4 for phase in completed),
          'fixed number of full owner/ancestor walks per closed phase', completed=completed)
    check(any(phase['records'] > 10 and phase['local'] > phase['full'] for phase in completed),
          'complete many-record native accounting uses local additions', completed=completed)
    assert not issues, 'H_CACHE_PROOF_DIAGNOSTIC=' + dumps(
        {'issues': issues, 'own_proof_events': proof_events, 'calls': calls},
        sort_keys=True, separators=(',', ':'))


def test_distinct_actual_study_sources_share_only_current_baseline_triplet(full_wire_history, monkeypatch):
    from h_analysis_study_factory import make_study_for_primary
    item = full_wire_history
    calls = []
    with preserved(item['root']):
        value = load_document(item['study'])
        primary = item['root'] / value['primary_numerical_receipt']['path']
        second = make_study_for_primary(primary, project_root=item['root'], filename='SYNTHETIC-reuse-second-study.json')
        for name in ('validate_simulation_protocol', 'validate_simulation_receipt', 'validate_numerical_verification_receipt'):
            spy_original(monkeypatch, source_reader, name, calls, name)
        with shared.validation_session() as session:
            one = readers(item)[0]()
            two = source_reader.validate_h_analysis_study(second, project_root=item['root'], require_reviewed=True)
            assert one['valid'] and two['valid'], [one['errors'], two['errors']]
            assert one['contract_path'] != two['contract_path']
            assert all(calls.count(name) == 1 for name in ('validate_simulation_protocol',
                'validate_simulation_receipt', 'validate_numerical_verification_receipt')), calls
            assert len([key for key in session.entries if key[0] == 'study_source']) == 2


def test_real_receipts_do_not_accept_supplied_forged_source_reports_on_a_hit(full_wire_history):
    item = full_wire_history
    with shared.validation_session():
        source, study, h2, receipt = [call() for call in readers(item)]
        assert study['valid'] and receipt['valid'], [study['errors'], receipt['errors']]
        forged = deepcopy(source); forged['contract_sha256'] = '0' * 64
        rejected = study_reader.validate_h_analysis_study_receipt(item['study_receipt'], project_root=item['root'], study_report=forged)
        assert not rejected['valid'] and not rejected['study_complete']
        assert any('supplied' in error for error in rejected['errors'])
        forged = deepcopy(h2); forged['input_manifest'] = []
        rejected = h2_reader.validate_model_verification_receipt(item['h2_receipt'], project_root=item['root'], contract_report=forged)
        assert not rejected['valid'] and not rejected['model_verification_decided']
        assert any('supplied' in error for error in rejected['errors'])
    # Neither a cold call nor a malformed optional object can seed a proof or
    # escape the original controlled-invalid-report boundary.
    for index, argument, source_report in ((1, 'study_report', source), (3, 'contract_report', h2)):
        forged = deepcopy(source_report); forged['contract_sha256'] = '0' * 64
        consumer = study_reader.validate_h_analysis_study_receipt if index == 1 else h2_reader.validate_model_verification_receipt
        path = item['study_receipt'] if index == 1 else item['h2_receipt']
        kind = 'study_receipt' if index == 1 else 'h2_receipt'
        with shared.validation_session() as session:
            for supplied in (forged, [], 'SYNTHETIC malformed optional report'):
                assert not any(k[0] == kind for k in session.entries)
                rejected = consumer(path, project_root=item['root'], **{argument: supplied})
                assert not rejected['valid'] and rejected['errors'], rejected
                assert not any(k[0] == kind for k in session.entries)


def test_real_whole_receipt_rechecks_mutated_bytes_and_exact_owned_inventory(full_wire_history):
    import h_analysis_trial as native
    item = full_wire_history
    names = native.contract()['evidence']
    trial = item['study_receipt'].parent / 'trial-batch-000001'
    qualification = item['profiles']['h_analysis_environment'].parent
    with preserved(item['root']), shared.validation_session():
        initial = readers(item)[1]()
        assert initial['valid'], initial['errors']
        # Neither extra is in the receipt's declared graph. The original exact
        # inventory consumer must reject each instead of returning cached proof.
        for directory in (trial, qualification):
            extra = directory / 'SYNTHETIC-undeclared-evidence.txt'
            extra.write_text('SYNTHETIC undeclared inventory attack', encoding='utf-8')
            invalid = readers(item)[1]()
            assert not invalid['valid'] or not invalid['study_complete'], invalid
            extra.unlink()
            restored = readers(item)[1]()
            assert restored['valid'] and restored['study_complete'], restored['errors']
            # A second lexical name for the same declared target must count as
            # an undeclared artifact even though all declared bytes stay equal.
            alias = directory / 'SYNTHETIC-undeclared-alias.json'
            try:
                alias.symlink_to(directory / names['raw'])
                invalid = readers(item)[1]()
                assert not invalid['valid'] or not invalid['study_complete'], invalid
            finally:
                alias.unlink(missing_ok=True)
            restored = readers(item)[1]()
            assert restored['valid'] and restored['study_complete'], restored['errors']
        raw = trial / names['raw']
        data = raw.read_bytes()
        raw.write_bytes(data + b'\n ')
        invalid = readers(item)[1]()
        assert not invalid['valid'] and not invalid['study_complete']


def test_current_installation_function_library_executable_and_version_bytes_are_fresh(full_wire_history):
    item = full_wire_history
    runtime = load_document(item['profiles']['environment'])['runtime']
    install = Path(runtime['matlabroot'])
    targets = list(dict.fromkeys([Path(runtime['executable']), install / 'VersionInfo.xml',
        *[Path(binding['path']) for binding in runtime['function_files']]]))
    assert targets
    with preserved(item['root'], install), shared.validation_session():
        initial = readers(item)[1]()
        assert initial['valid'], initial['errors']
        for target in targets:
            data = target.read_bytes(); target.write_bytes(data + b'\nSYNTHETIC byte mutation\n')
            invalid = readers(item)[1]()
            assert not invalid['valid'] or not invalid['study_complete'], (str(target), invalid)
            target.write_bytes(data)
            restored = readers(item)[1]()
            assert restored['valid'], restored['errors']


def test_mid_consumer_external_mutation_cannot_publish_old_proof_under_new_guard(full_wire_history, monkeypatch):
    item = full_wire_history
    runtime = load_document(item['profiles']['environment'])['runtime']
    executable = Path(runtime['executable'])
    original = study_reader.assess_study
    def after_last_native_check(*args, **kwargs):
        result = original(*args, **kwargs)
        executable.write_bytes(executable.read_bytes() + b'\nSYNTHETIC post-check mutation\n')
        return result
    with preserved(item['root'], executable.parent.parent), shared.validation_session() as session:
        monkeypatch.setattr(study_reader, 'assess_study', after_last_native_check)
        invalid = readers(item)[1]()
        assert not invalid['valid'] and not invalid['study_complete'], invalid
        assert any('installation' in error or 'bytes changed' in error for error in invalid['errors'])
        assert not any(key[0] == 'study_receipt' for key in session.entries)


def test_current_host_and_caller_root_flags_cannot_inherit_a_cached_scope(full_wire_history, monkeypatch):
    import runtime_common
    import h_analysis_trial
    import validate_environment
    import validate_simulation_profile
    item = full_wire_history
    with shared.validation_session():
        initial = readers(item)[1]()
        assert initial['valid'], initial['errors']
        original_host = runtime_common.host_fingerprint
        with monkeypatch.context() as patch:
            changed_host = lambda: original_host() + '-SYNTHETIC-different-host'
            for module in (runtime_common, h_analysis_trial, validate_environment, validate_simulation_profile):
                patch.setattr(module, 'host_fingerprint', changed_host)
            invalid = readers(item)[1]()
            assert not invalid['valid'] or not invalid['study_complete'], invalid
        outside = item['root'].parent / 'SYNTHETIC-wrong-project-root'
        invalid = study_reader.validate_h_analysis_study_receipt(item['study_receipt'], project_root=outside)
        assert not invalid['valid'] and not invalid['study_complete']
        relaxed = source_reader.validate_h_analysis_study(item['study'], project_root=item['root'], require_reviewed=False)
        strict = readers(item)[0]()
        assert relaxed['valid'] and strict['valid'] and strict['study_ready']


def test_hit_reapplies_complete_aggregate_budget_before_baseline_or_numeric_work(full_wire_history, monkeypatch):
    from problem_factory import write_contract
    item = full_wire_history
    with preserved(item['root']), shared.validation_session():
        current = readers(item)[0]()
        assert current['valid'], current['errors']
        total = sum(entry['bytes'] for entry in current['input_manifest'])
        value = load_document(item['study'])
        # Leave room for the few serialized digits changed below: only the
        # aggregate is over budget, while every individual file remains valid.
        total_cap = total - max(4096, item['study'].stat().st_size // 2)
        assert total_cap > max(entry['bytes'] for entry in current['input_manifest'])
        value['budget']['max_total_bytes'] = total_cap
        value['budget']['max_file_bytes'] = min(value['budget']['max_file_bytes'], total_cap)
        value['budget']['max_result_bytes'] = min(value['budget']['max_result_bytes'], value['budget']['max_file_bytes'])
        write_contract(item['study'], value)
        calls = []
        for name in ('validate_simulation_protocol', 'validate_simulation_receipt', 'validate_numerical_verification_receipt'):
            spy_original(monkeypatch, source_reader, name, calls, name)
        invalid = readers(item)[0]()
        assert not invalid['valid'] and not invalid['study_ready'], invalid
        assert any('budget' in error for error in invalid['errors'])
        assert not calls


def test_hit_reapplies_selected_source_bytes_typed_authority_and_graph_limits(full_wire_history):
    from problem_factory import write_contract
    from runtime_common import sha256_file
    item = full_wire_history
    with preserved(item['root']), shared.validation_session():
        initial = readers(item)[0]()
        assert initial['valid'], initial['errors']
        contract = load_document(item['study'])
        selected = item['root'] / contract['sources'][0]['path']
        original = selected.read_bytes(); selected.write_bytes(original + b'\n ')
        invalid = readers(item)[0]()
        assert not invalid['valid'] and not invalid['study_ready']
        selected.write_bytes(original)
        contract['budget']['max_files'] = len(initial['input_manifest']) - 1
        write_contract(item['study'], contract)
        invalid = readers(item)[0]()
        assert not invalid['valid'] and any('budget' in error for error in invalid['errors'])
        # A plain task source cannot grant qualification authority to a new
        # outside byte-identical profile. No filename-based role promotion.
        original_contract = initial['_contract']
        outside = item['root'].parent / (item['root'].name + '-SYNTHETIC-unselected-profile.json')
        outside.write_bytes(item['profiles']['environment'].read_bytes())
        try:
            malicious = deepcopy(original_contract)
            malicious['sources'].append({'id':'unselected', 'path':str(outside), 'sha256':sha256_file(outside),
                'purpose':'SYNTHETIC outside task-source authority attack'})
            write_contract(item['study'], malicious)
            invalid = readers(item)[0]()
            assert not invalid['valid'] and not invalid['study_ready']
        finally:
            outside.unlink()


def test_byte_identical_root_binding_symlink_retarget_gets_new_original_proof(full_wire_history, monkeypatch):
    item = full_wire_history
    with preserved(item['root']):
        twin = item['root'] / 'SYNTHETIC-byte-identical-study.json'
        twin.write_bytes(item['study'].read_bytes())
        alias = item['root'] / 'SYNTHETIC-study-alias.json'
        alias.symlink_to(item['study'])
        calls = []
        spy_original(monkeypatch, source_reader, 'schema_errors', calls, 'real_source')
        with shared.validation_session():
            one = source_reader.validate_h_analysis_study(alias, project_root=item['root'], require_reviewed=True)
            assert one['valid'], one['errors']
            alias.unlink(); alias.symlink_to(twin)
            two = source_reader.validate_h_analysis_study(alias, project_root=item['root'], require_reviewed=True)
            assert two['valid'], two['errors']
            assert two['contract_path'] == str(twin) and one['contract_path'] != two['contract_path']
            assert calls == ['real_source', 'real_source']
        alias.unlink()


@pytest.mark.parametrize('cap,value', [('_MEMO_ENTRIES', 0), ('_MEMO_BYTES', 1)])
def test_capacity_fallback_preserves_actual_acceptance_and_retains_no_proof(full_wire_history, monkeypatch, cap, value):
    item = full_wire_history
    calls = []
    spy_original(monkeypatch, source_reader, 'schema_errors', calls, 'real_source')
    monkeypatch.setattr(shared, cap, value)
    with shared.validation_session() as session:
        one = readers(item)[0](); two = readers(item)[0]()
        assert one['valid'] and two['valid'], [one['errors'], two['errors']]
        assert not session.entries and calls == ['real_source', 'real_source']
    if cap == '_MEMO_BYTES':
        # Decline a real newly parsed raw graph midway through the closed extras
        # phase, using its measured size and the phase's actual live baseline.
        # This also verifies that each admission reads the current cap.
        monkeypatch.setattr(shared, '_MEMO_BYTES', 64 * 1024 * 1024)
        expected = readers(item)[1]()
        assert expected['valid'], expected['errors']
        refused, guards, original_calls = [], [], []
        original_add, original_extras = shared._memo_builder_add, shared._memo_extras
        original_receipt, original_size = study_reader.schema_errors, shared._retained_size
        def add(ledger, graph=(), **kwargs):
            if not refused and type(graph) is dict and ('cases' in graph or 'operations' in graph):
                charge = original_size(graph)
                assert charge is not None and charge > 0
                limit = ledger['base'] + ledger['charged'] + charge // 2
                assert 0 < charge < limit < 64 * 1024 * 1024
                assert ledger['base'] + ledger['charged'] < limit
                patch.setattr(shared, '_MEMO_BYTES', limit)
                try:
                    return original_add(ledger, graph, **kwargs)
                except shared._MemoCapacityUnavailable:
                    refused.append((charge, limit))
                    raise
                pytest.fail('actual new raw graph exceeded the current live cap without declining')
            return original_add(ledger, graph, **kwargs)
        def extras(paths, *args, **kwargs):
            if not refused:
                guards.append(weakref.ref(paths))
            return original_extras(paths, *args, **kwargs)
        def receipt(*args, **kwargs):
            original_calls.append(True)
            assert refused and sys.exc_info()[0] is None
            assert guards and all(reference() is None for reference in guards)
            assert shared._H_VALIDATION_CAPTURE.get() is None
            assert not shared._H_VALIDATION_SESSION.get().working
            return original_receipt(*args, **kwargs)
        with monkeypatch.context() as patch:
            patch.setattr(shared, '_memo_builder_add', add)
            patch.setattr(shared, '_memo_extras', extras)
            patch.setattr(study_reader, 'schema_errors', receipt)
            with shared.validation_session() as session:
                actual = readers(item)[1]()
                assert actual['valid'] and shared.typed_equal(expected, actual), actual['errors']
                assert len(refused) == 1 and original_calls == [True]
                assert not any(key[0] == 'study_receipt' for key in session.entries)
                assert not session.working and all(reference() is None for reference in guards)
        with shared.validation_session() as session:
            recovered = readers(item)[1]()
            assert recovered['valid'] and shared.typed_equal(expected, recovered), recovered['errors']
            assert any(key[0] == 'study_receipt' for key in session.entries)


def test_actual_object_memory_unknown_types_cycles_and_exception_cleanup():
    assert shared._retained_size({'known': ['a', 1, 1.0, None]}) is not None
    assert shared._retained_size({'unknown': Path('/SYNTHETIC')}) is None
    cycle = []; cycle.append(cycle)
    assert shared._retained_size(cycle) is None
    with pytest.raises(RuntimeError, match='SYNTHETIC owner failure'):
        with shared.validation_session() as session:
            assert session.active
            raise RuntimeError('SYNTHETIC owner failure')
    assert not session.active and session.entries == {} and session.capabilities == []
    assert shared._H_VALIDATION_SESSION.get() is None


def test_foreign_owner_and_unlisted_publisher_never_obtain_proof(monkeypatch, tmp_path):
    computed = []
    def original():
        computed.append(True)
        return {'SYNTHETIC': 'This is not an acceptance report'}
    with shared.validation_session() as session:
        session.owner = (session.owner[0] + 1, session.owner[1])
        report = shared._reuse_validation('study_source', project_root=tmp_path, budget=shared.HARD_BUDGET,
            compute=original, eligible=lambda _: True, roots=[])
        assert report['SYNTHETIC'] and computed == [True] and not session.entries
    with shared.validation_session() as session:
        report = shared._reuse_validation('study_source', project_root=tmp_path, budget=shared.HARD_BUDGET,
            compute=original, eligible=lambda _: True, roots=[])
        assert report['SYNTHETIC'] and computed == [True, True] and not session.entries
        assert shared._historical_validation_capability(tmp_path) is None
    with pytest.raises(ValueError, match='restricted'):
        shared._memoized_h_validation('study_source', 'h_study_contract')(original)


def test_same_size_mtime_source_mutation_still_hashes_actual_bytes(full_wire_history, monkeypatch):
    item = full_wire_history
    with preserved(item['root']), shared.validation_session():
        initial = readers(item)[0]()
        assert initial['valid'], initial['errors']
        value = load_document(item['study'])
        selected = item['root'] / value['sources'][0]['path']
        original, stat = selected.read_bytes(), selected.stat()
        changed = original.replace(b'finite', b'FinIte', 1)
        if changed == original:
            changed = original.replace(b'settings', b'SETTINGS', 1)
        assert changed != original and len(changed) == len(original)
        selected.write_bytes(changed)
        os.utime(selected, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        calls = []
        original_hash = shared.sha256_file
        def observe(path):
            if Path(path).resolve() == selected.resolve():
                calls.append(True)
            return original_hash(path)
        monkeypatch.setattr(shared, 'sha256_file', observe)
        invalid = readers(item)[0]()
        assert not invalid['valid'] and not invalid['study_ready'] and calls, invalid
        selected.write_bytes(original)
        os.utime(selected, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        restored = readers(item)[0]()
        assert restored['valid'] and restored['study_ready'], restored['errors']


@pytest.mark.parametrize('limit', ['max_document_nodes', 'max_document_depth', 'max_edges', 'max_files'])
def test_hot_source_graph_limits_precede_selected_hash_and_heavy_children(full_wire_history, monkeypatch, limit):
    from problem_factory import write_contract
    item = full_wire_history
    with preserved(item['root']), shared.validation_session():
        initial = readers(item)[0]()
        assert initial['valid'], initial['errors']
        value = load_document(item['study'])
        selected = item['root'] / value['sources'][0]['path']
        value['budget'][limit] = 1
        write_contract(item['study'], value)
        original_hash = shared.sha256_file
        def bounded_hash(path):
            # Actual small contract bootstrap remains permitted. The selected
            # aggregate/task source cannot be hashed after graph failure.
            assert Path(path).resolve() != selected.resolve(), 'selected hash preceded whole graph budget'
            return original_hash(path)
        monkeypatch.setattr(shared, 'sha256_file', bounded_hash)
        for name in ('validate_simulation_protocol', 'validate_simulation_receipt', 'validate_numerical_verification_receipt'):
            monkeypatch.setattr(source_reader, name, lambda *a, **k: pytest.fail('heavy child preceded graph budget'))
        rejected = readers(item)[0]()
        assert not rejected['valid'] and not rejected['study_ready'], rejected
        assert any('budget' in error for error in rejected['errors']), rejected['errors']


@pytest.mark.parametrize('role', ['study', 'h2'])
def test_matching_supplied_source_never_precedes_parent_aggregate_preflight(full_wire_history, monkeypatch, role):
    from problem_factory import write_contract
    from h_analysis_study_factory import review_h_analysis_study
    from model_verification_factory import review_model_verification
    item = full_wire_history
    source_path, receipt_path = (item['study'], item['study_receipt']) if role == 'study' else (item['h2'], item['h2_receipt'])
    read_source = readers(item)[0 if role == 'study' else 2]
    read_receipt = readers(item)[1 if role == 'study' else 3]
    consumer = study_reader.validate_h_analysis_study_receipt if role == 'study' else h2_reader.validate_model_verification_receipt
    argument = 'study_report' if role == 'study' else 'contract_report'
    with preserved(item['root']), shared.validation_session():
        original_source, initial = read_source(), read_receipt()
        assert original_source['valid'] and initial['valid'], [original_source['errors'], initial['errors']]
        value = load_document(source_path)
        paths = shared.evidence_paths([receipt_path], item['root'], value['budget'],
            root_contexts={receipt_path: 'h_study_receipt' if role == 'study' else 'h2_receipt'}, include_repository_sources=True)
        stats = shared.stat_manifest(paths, item['root'], value['budget'])
        total = sum(entry['bytes'] for entry in stats)
        source_total = sum(entry['bytes'] for entry in original_source['input_manifest'])
        cap = total - 128
        assert source_total + 128 < cap and max(entry['bytes'] for entry in stats) < cap
        value['budget']['max_total_bytes'] = cap
        value['budget']['max_file_bytes'] = min(cap, value['budget']['max_file_bytes'])
        value['budget']['max_result_bytes'] = min(value['budget']['max_result_bytes'], value['budget']['max_file_bytes'])
        write_contract(source_path, value)
        if role == 'study':
            review_h_analysis_study(source_path, project_root=item['root'])
        else:
            review_model_verification(source_path, project_root=item['root'], prefix='SYNTHETIC-parent-budget-h2')
        current = read_source()
        assert current['valid'], current['errors']
        # Use the original declared artifact spelling, not an invented name.
        result_path = receipt_path.parent / load_document(receipt_path)['artifacts']['result']['file']
        original_hash = shared.sha256_file
        def bounded_hash(path):
            assert Path(path).resolve() != result_path.resolve(), 'parent result hash preceded its aggregate budget'
            return original_hash(path)
        monkeypatch.setattr(shared, 'sha256_file', bounded_hash)
        module, name = (study_reader, 'validate_h_analysis_study') if role == 'study' else (h2_reader, 'validate_model_verification')
        monkeypatch.setattr(module, name, lambda *a, **k: pytest.fail('source child preceded parent aggregate budget'))
        rejected = consumer(receipt_path, project_root=item['root'], **{argument: current})
        assert not rejected['valid'] and any('budget' in error for error in rejected['errors']), rejected


def test_inherited_thread_and_async_contexts_get_isolated_real_sessions(full_wire_history):
    import asyncio
    from contextvars import copy_context
    from concurrent.futures import ThreadPoolExecutor
    item = full_wire_history
    async def exercise():
        with shared.validation_session() as parent:
            initial = readers(item)[0]()
            assert initial['valid'], initial['errors']
            owner, entry_keys = parent.owner, set(parent.entries)
            def thread_child():
                with shared.validation_session() as child:
                    assert child is not parent and child.owner != owner
                    result = readers(item)[0]()
                    assert result['valid'], result['errors']
                    assert child.entries
                assert not child.active and not child.entries
                return child.owner
            inherited = copy_context()
            # One worker runs while the parent is idle: no simultaneous reader
            # or numerical computation is needed to prove inherited ownership.
            with ThreadPoolExecutor(max_workers=1) as executor:
                child_owner = executor.submit(inherited.run, thread_child).result()
            assert child_owner != owner and parent.owner == owner and set(parent.entries) == entry_keys
            async def task_child():
                with shared.validation_session() as child:
                    assert child is not parent and child.owner != owner
                    result = readers(item)[0]()
                    assert result['valid'], result['errors']
                    raise RuntimeError('SYNTHETIC inherited task cleanup')
            task = asyncio.create_task(task_child())
            with pytest.raises(RuntimeError, match='inherited task cleanup'):
                await task
            assert shared._H_VALIDATION_SESSION.get() is parent
            assert parent.active and parent.owner == owner and set(parent.entries) == entry_keys
    asyncio.run(exercise())
    assert shared._H_VALIDATION_SESSION.get() is None


def test_parent_traversal_symlink_binding_uses_original_source_each_time(full_wire_history, monkeypatch):
    item = full_wire_history
    calls = []
    with preserved(item['root']):
        directory = item['root'] / 'SYNTHETIC-provenance-sub'
        (directory / 'a').mkdir(parents=True, exist_ok=True)
        (directory / 'b').mkdir()
        twin = directory / item['study'].name
        twin.write_bytes(item['study'].read_bytes())
        link = item['root'] / 'SYNTHETIC-parent-link'
        link.symlink_to(directory / 'a', target_is_directory=True)
        lexical = link / '..' / item['study'].name
        spy_original(monkeypatch, source_reader, 'schema_errors', calls, 'original_source')
        try:
            with shared.validation_session() as session:
                one = source_reader.validate_h_analysis_study(lexical, project_root=item['root'], require_reviewed=True)
                assert one['valid'], one['errors']
                link.unlink(); link.symlink_to(directory / 'b', target_is_directory=True)
                two = source_reader.validate_h_analysis_study(lexical, project_root=item['root'], require_reviewed=True)
                assert two['valid'] and one['contract_path'] == two['contract_path'], two['errors']
                assert calls == ['original_source', 'original_source']
                assert not any(key[0] == 'study_source' for key in session.entries)
        finally:
            link.unlink(missing_ok=True)


def test_opaque_parent_state_hot_mutation_cannot_reuse_history(explicit_parent_state_history):
    item = explicit_parent_state_history
    with preserved(item['root']), shared.validation_session():
        first = study_reader.validate_h_analysis_study_receipt(item['receipt'], project_root=item['root'])
        assert first['valid'] and first['study_complete'], first['errors']
        item['state'].write_bytes(item['state'].read_bytes() + b'\n ')
        rejected = study_reader.validate_h_analysis_study_receipt(item['receipt'], project_root=item['root'])
        assert not rejected['valid'] and not rejected['study_complete'], rejected
        item['state'].write_bytes(item['state_bytes'])
        restored = study_reader.validate_h_analysis_study_receipt(item['receipt'], project_root=item['root'])
        assert restored['valid'] and restored['study_complete'] and not restored.get('execution_allowed', False), restored


@pytest.mark.parametrize('role', ['trial', 'qualification'])
def test_claimed_output_directory_never_reads_unrelated_inventory(full_wire_history, monkeypatch, tmp_path, role):
    import h_analysis_trial as native
    from probe_environment import write_json
    from runtime_common import sha256_file
    item = full_wire_history
    names = native.contract()['evidence']
    directory = item['study_receipt'].parent / 'trial-batch-000001' if role == 'trial' else item['profiles']['h_analysis_environment'].parent
    outside = tmp_path / 'SYNTHETIC-unrelated-owned-root'
    outside.mkdir(); (outside / 'private.json').write_text('{"SYNTHETIC": "never read"}', encoding='utf-8')
    original_hash, original_load, original_rglob = shared.sha256_file, shared.limited_document, Path.rglob
    original_preflight = shared._memo_extra_preflight
    touched = []
    def observe_preflight(paths, *a, **k):
        for (path, context, _), value in paths._documents.items():
            if path == str(directory / names['input']) and context == ('h_trial_request' if role == 'trial' else 'qualification_h_request') and value.get('output_directory') == str(outside):
                touched.append(True)
        return original_preflight(paths, *a, **k)
    def safe_hash(path):
        assert not Path(path).resolve().is_relative_to(outside), 'unchecked output directory was hashed'
        return original_hash(path)
    def safe_load(path, *a, **k):
        assert not Path(path).resolve().is_relative_to(outside), 'unchecked output directory was decoded'
        return original_load(path, *a, **k)
    def safe_rglob(path, *a, **k):
        assert not Path(path).resolve().is_relative_to(outside), 'unchecked output directory was traversed'
        return original_rglob(path, *a, **k)
    with preserved(item['root']):
        for hot in (False, True):
            with shared.validation_session():
                if hot:
                    first = readers(item)[1]()
                    assert first['valid'], first['errors']
                input_path = directory / names['input']
                original_input = input_path.read_bytes()
                receipt_path = directory / (names['run_receipt'] if role == 'trial' else names['profile_receipt'])
                original_receipt = receipt_path.read_bytes()
                request, receipt = load_document(input_path), load_document(receipt_path)
                request['output_directory'] = str(outside)
                write_json(input_path, request)
                receipt['artifacts']['input']['sha256'] = sha256_file(input_path)
                write_json(receipt_path, receipt)
                parent_original = item['study_receipt'].read_bytes()
                if role == 'trial':
                    parent = load_document(item['study_receipt'])
                    parent['trial_receipts'][0]['sha256'] = sha256_file(receipt_path)
                    write_json(item['study_receipt'], parent)
                try:
                    with monkeypatch.context() as patch:
                        touched.clear()
                        patch.setattr(shared, '_memo_extra_preflight', observe_preflight)
                        patch.setattr(shared, 'sha256_file', safe_hash)
                        patch.setattr(shared, 'limited_document', safe_load)
                        patch.setattr(Path, 'rglob', safe_rglob)
                        rejected = readers(item)[1]()
                    assert touched and not rejected['valid'] and not rejected['study_complete'], rejected
                finally:
                    input_path.write_bytes(original_input); receipt_path.write_bytes(original_receipt)
                    item['study_receipt'].write_bytes(parent_original)


def rebind_trial_raw_for_control(item, raw):
    """Preserve complete artifacts; change only a synthetic raw binding chain."""
    import h_analysis_trial as native
    from probe_environment import write_json
    from runtime_common import sha256_file
    names = native.contract()['evidence']
    directory = item['study_receipt'].parent / 'trial-batch-000001'
    raw_path, receipt_path = directory / names['raw'], directory / names['run_receipt']
    write_json(raw_path, raw)
    receipt = load_document(receipt_path)
    receipt['artifacts']['raw']['sha256'] = sha256_file(raw_path)
    write_json(receipt_path, receipt)
    parent = load_document(item['study_receipt'])
    parent['trial_receipts'][0]['sha256'] = sha256_file(receipt_path)
    write_json(item['study_receipt'], parent)


def test_rehashed_malformed_raw_function_shape_remains_controlled_invalid(full_wire_history):
    import h_analysis_trial as native
    item = full_wire_history
    names = native.contract()['evidence']
    directory = item['study_receipt'].parent / 'trial-batch-000001'
    with preserved(item['root']):
        with shared.validation_session():
            first = readers(item)[1]()
            assert first['valid'], first['errors']
            raw = load_document(directory / names['raw'])
            raw['functions'][0]['path'] = None
            rebind_trial_raw_for_control(item, raw)
            hot = readers(item)[1]()
            assert not hot['valid'] and not hot['study_complete'] and hot['errors'], hot
        with shared.validation_session():
            cold = readers(item)[1]()
            assert not cold['valid'] and not cold['study_complete'] and cold['errors'], cold


@pytest.mark.parametrize('spelling', ['direct_link', 'parent_traversal'])
def test_actual_raw_lexical_function_retarget_never_inherits_its_previous_proof(full_wire_history, monkeypatch, spelling):
    import h_analysis_trial as native
    import validate_h_analysis_profile as profile_reader
    item = full_wire_history
    names = native.contract()['evidence']
    trial = item['study_receipt'].parent / 'trial-batch-000001'
    raw = load_document(trial / names['raw'])
    runtime = load_document(item['profiles']['environment'])['runtime']
    install = Path(runtime['matlabroot'])
    target = Path(raw['functions'][0]['path'])
    calls = []
    with preserved(item['root'], install):
        twin = target.parent / ('SYNTHETIC-twin-' + target.name)
        twin.write_bytes(target.read_bytes())
        link = target.parent / 'SYNTHETIC-raw-function-link'
        if spelling == 'direct_link':
            link.symlink_to(target)
            lexical = str(link)
        else:
            (target.parent / 'SYNTHETIC-a').mkdir()
            (target.parent / 'SYNTHETIC-b').mkdir()
            link.symlink_to(target.parent / 'SYNTHETIC-a', target_is_directory=True)
            lexical = str(link / '..' / target.name)
        name = raw['functions'][0]['name']
        for record in [raw, *raw['cases']]:
            for function in record['functions']:
                if function['name'] == name:
                    function['path'] = lexical
        rebind_trial_raw_for_control(item, raw)
        spy_original(monkeypatch, profile_reader, 'observed_runtime', calls, 'actual_native_runtime')
        try:
            with shared.validation_session() as session:
                initial = readers(item)[1]()
                assert initial['valid'] and initial['study_complete'], initial['errors']
                before = len(calls)
                if spelling == 'direct_link':
                    assert any(key[0] == 'study_receipt' for key in session.entries)
                    link.unlink(); link.symlink_to(twin)
                    changed = readers(item)[1]()
                    assert not changed['valid'] and not changed['study_complete'], changed
                else:
                    assert not any(key[0] == 'study_receipt' for key in session.entries)
                    link.unlink(); link.symlink_to(target.parent / 'SYNTHETIC-b', target_is_directory=True)
                    changed = readers(item)[1]()
                    assert changed['valid'] and changed['study_complete'], changed['errors']
                    assert not any(key[0] == 'study_receipt' for key in session.entries)
                assert len(calls) > before, 'original native reader must see changed lexical provenance'
        finally:
            link.unlink(missing_ok=True)


@pytest.fixture(scope='module')
def failed_reuse_history(full_wire_history):
    from h_analysis_study_factory import make_study_for_primary, make_study_history
    item = full_wire_history
    source = load_document(item['study'])
    primary = item['root'] / source['primary_numerical_receipt']['path']
    study = make_study_for_primary(primary, project_root=item['root'], filename='SYNTHETIC-failed-reuse-study.json', upper=0.)
    receipt = make_study_history(study, project_root=item['root'], output_name='SYNTHETIC-failed-reuse-history',
                                 h_profile=item['profiles']['h_analysis_environment'])
    return {**item, 'failed_study': study, 'failed_receipt': receipt}


@pytest.mark.parametrize('disposition', ['modify', 'reject'])
def test_lawful_failed_study_and_H2_dispositions_hit_without_promotion(failed_reuse_history, monkeypatch, disposition):
    from json import dumps
    from model_factory import file_ref
    from model_verification_factory import review_model_verification
    from problem_factory import write_contract
    from run_model_verification import run_model_verification
    item, calls, guards, issues = failed_reuse_history, [], [], []
    proof_events, role_in_progress, read_ordinal = [], None, 0
    capacity_samples = []
    original_capacity, original_builder_check = shared._memo_capacity, shared._memo_builder_check
    common_file = str(Path(shared.__file__).resolve())
    def own_role_frame(frame):
        try:
            while frame is not None:
                if (str(Path(frame.f_code.co_filename).resolve()) == common_file and
                        frame.f_code.co_name == '_attempt_h_validation_reuse'):
                    return frame.f_locals.get('kind') == role_in_progress
                frame = frame.f_back
            return False
        finally:
            del frame
    def capacity(*args, **kwargs):
        sample = {'live_measured': False, 'reserve_measured': False, 'live_bytes': None, 'reserve_bytes': None}
        capacity_samples.append(sample)
        try:
            return original_capacity(*args, **kwargs)
        except shared._MemoCapacityUnavailable as error:
            caller = sys._getframe(1)
            try:
                if role_in_progress is not None and own_role_frame(caller):
                    proof_events.append({'role': role_in_progress, 'read': read_ordinal,
                        'event': 'own_guard_capacity_refusal', 'phase': caller.f_code.co_name,
                        'line': caller.f_lineno, 'message': str(error),
                        'byte_limit': min(shared._MEMO_BYTES, 64 * 1024 * 1024), **sample})
            finally:
                del caller
            raise
        finally:
            capacity_samples.pop()
    def capacity_size(value, actual):
        caller = sys._getframe(2)
        try:
            if (capacity_samples and caller.f_code.co_name == '_memo_capacity' and
                    str(Path(caller.f_code.co_filename).resolve()) == common_file):
                sample = capacity_samples[-1]
                if value is caller.f_locals.get('reserve'):
                    sample['reserve_measured'], sample['reserve_bytes'] = True, actual
                else:
                    sample['live_measured'], sample['live_bytes'] = True, actual
        finally:
            del caller
    def builder_check(ledger, extra=0):
        try:
            return original_builder_check(ledger, extra)
        except shared._MemoCapacityUnavailable as error:
            caller = sys._getframe(1)
            try:
                if role_in_progress is not None and own_role_frame(caller):
                    proof_events.append({'role': role_in_progress, 'read': read_ordinal,
                        'event': 'own_builder_capacity_refusal', 'phase': caller.f_code.co_name,
                        'line': caller.f_lineno, 'base': ledger['base'],
                        'charged': ledger['charged'], 'extra': extra, 'message': str(error),
                        'byte_limit': min(shared._MEMO_BYTES, 64 * 1024 * 1024)})
            finally:
                del caller
            raise
    def attempt_size(actual):
        caller = sys._getframe(2)
        try:
            if (role_in_progress is not None and caller.f_code.co_name == '_attempt_h_validation_reuse' and
                    str(Path(caller.f_code.co_filename).resolve()) == common_file and
                    caller.f_locals.get('kind') == role_in_progress):
                proof_events.append({'role': role_in_progress, 'read': read_ordinal,
                    'event': 'own_attempt_admission_size', 'line': caller.f_lineno,
                    'bytes': actual, 'byte_limit': min(shared._MEMO_BYTES, 64 * 1024 * 1024)})
        finally:
            del caller
    def publication_size(value, actual):
        caller = sys._getframe(2)
        try:
            if (role_in_progress is not None and caller.f_code.co_name == '_publish_validation' and
                    str(Path(caller.f_code.co_filename).resolve()) == common_file):
                key = caller.f_locals.get('key')
                if type(key) is tuple and key[0] == role_in_progress and type(value) is tuple and len(value) in (2, 4):
                    proof_events.append({'role': role_in_progress, 'read': read_ordinal,
                        'event': 'own_publication_size', 'part': 'live' if len(value) == 4 else 'copy',
                        'bytes': actual, 'byte_limit': min(shared._MEMO_BYTES, 64 * 1024 * 1024)})
        finally:
            del caller
    monkeypatch.setattr(shared, '_memo_capacity', capacity)
    monkeypatch.setattr(shared, '_memo_builder_check', builder_check)
    original_size = shared._retained_size
    def size(value):
        actual = original_size(value)
        capacity_size(value, actual)
        attempt_size(actual)
        publication_size(value, actual)
        return actual
    def check(condition, obligation, **evidence):
        if not condition:
            issues.append({'role': role_in_progress, 'obligation': obligation, **evidence})
    monkeypatch.setattr(shared, '_retained_size', size)
    with preserved(item['root']):
        value = load_document(item['h2'])
        value['claims'][0]['failure_disposition'] = disposition
        value['claims'][0]['study_requirements'][0].update(
            study_contract=file_ref(item['root'], item['failed_study']), study_receipt=file_ref(item['root'], item['failed_receipt']))
        contract = write_contract(item['root'] / ('SYNTHETIC-reuse-' + disposition + '.json'), value)
        review_model_verification(contract, project_root=item['root'], prefix='SYNTHETIC-reuse-' + disposition)
        produced = run_model_verification(contract, item['root'] / ('SYNTHETIC-reuse-decision-' + disposition), project_root=item['root'])
        assert produced['valid'] and produced['model_verification_decided'] and not produced['model_verified'], produced['errors']
        path = Path(produced['receipt_path'])
        spy_original(monkeypatch, study_reader, 'assess_study', calls, 'study_metric')
        spy_original(monkeypatch, h2_reader, 'compute_assessment', calls, 'claim_metric')
        spy_original(monkeypatch, shared, 'input_manifest', guards, 'fresh_manifest')
        role_in_progress = 'study_receipt'
        with shared.validation_session() as session:
            read_ordinal = 1
            cold_before = len(guards)
            first = study_reader.validate_h_analysis_study_receipt(item['failed_receipt'], project_root=item['root'])
            check(len(guards) >= cold_before + 3, 'failed-study cold pre/after/final manifests')
            before = len(guards)
            cached_before = any(key[0] == 'study_receipt' for key in session.entries)
            read_ordinal = 2
            second = study_reader.validate_h_analysis_study_receipt(item['failed_receipt'], project_root=item['root'])
            check(first['valid'] and first['study_complete'] and first['defined'] and not first['study_accepted'],
                  'actual complete defined lawful failed study')
            check(shared.typed_equal(first, second), 'failed study cold and adjacent reread typed equal')
            check(cached_before and any(key[0] == 'study_receipt' for key in session.entries),
                  'actual failed-study proof retained for demonstrated hit')
            check(len(guards) >= before + 2, 'failed-study fresh whole-graph pre/final manifests')
            check(calls.count('study_metric') == 1, 'strict one actual failed-study computation through reread',
                  actual=calls.count('study_metric'))
            second['study_accepted'] = True
            read_ordinal = 3
            third_before = len(guards)
            third = study_reader.validate_h_analysis_study_receipt(item['failed_receipt'], project_root=item['root'])
            check(len(guards) >= third_before + 2, 'failed-study fresh pre/final manifests after caller mutation')
            check(not third['study_accepted'] and shared.typed_equal(first, third), 'failed-study returned-copy isolation without promotion')
            check(calls.count('study_metric') == 1, 'strict one actual failed-study computation after caller mutation',
                  actual=calls.count('study_metric'))
        check(not session.active and not session.entries and not session.capabilities,
              'failed-study session releases all proof and capabilities')
        check(shared._H_VALIDATION_SESSION.get() is None, 'failed-study releases ambient session')
        # The larger H2 graph starts without retained study proof from another role.
        role_in_progress = 'h2_receipt'
        with shared.validation_session() as session:
            read_ordinal = 1
            cold_before = len(guards)
            decision = h2_reader.validate_model_verification_receipt(path, project_root=item['root'])
            check(len(guards) >= cold_before + 3, 'lawful H2 cold pre/after/final manifests')
            before = len(guards)
            cached_before = any(key[0] == 'h2_receipt' for key in session.entries)
            read_ordinal = 2
            again = h2_reader.validate_model_verification_receipt(path, project_root=item['root'])
            check(shared.typed_equal(decision, again), 'lawful H2 cold and adjacent reread typed equal')
            check(decision['valid'] and decision['model_verification_decided'] and not decision['model_verified'] and not decision['claim_supported'],
                  'actual lawful H2 decision remains unverified and unsupported')
            check(decision['claims'][0]['disposition'] == disposition, 'exact declared H2 disposition')
            check(decision['claims'][0]['required_action'] == value['claims'][0]['required_action'], 'exact declared required action')
            check(decision['claims'][0]['impact_scope'] == value['claims'][0]['impact_scope'], 'exact declared impact scope')
            check(cached_before and any(key[0] == 'h2_receipt' for key in session.entries),
                  'actual lawful H2 proof retained for demonstrated hit')
            check(len(guards) >= before + 2, 'lawful H2 fresh whole-graph pre/final manifests')
            check(calls.count('claim_metric') == 1, 'strict one actual lawful H2 computation through reread',
                  actual=calls.count('claim_metric'))
            again['model_verified'] = True
            read_ordinal = 3
            third_before = len(guards)
            third_decision = h2_reader.validate_model_verification_receipt(path, project_root=item['root'])
            check(len(guards) >= third_before + 2, 'lawful H2 fresh pre/final manifests after caller mutation')
            check(not third_decision['model_verified'] and shared.typed_equal(decision, third_decision),
                  'lawful H2 returned-copy isolation without promotion')
            check(calls.count('claim_metric') == 1, 'strict one actual lawful H2 computation after caller mutation',
                  actual=calls.count('claim_metric'))
        check(not session.active and not session.entries and not session.capabilities,
              'lawful H2 session releases all proof and capabilities')
        check(shared._H_VALIDATION_SESSION.get() is None, 'lawful H2 releases ambient session')
        role_in_progress = None
        with monkeypatch.context() as patch:
            patch.setattr(shared, '_MEMO_ENTRIES', 0)
            with shared.validation_session() as session:
                plain = study_reader.validate_h_analysis_study_receipt(item['failed_receipt'], project_root=item['root'])
                plain_decision = h2_reader.validate_model_verification_receipt(path, project_root=item['root'])
                check(shared.typed_equal(first, plain) and shared.typed_equal(decision, plain_decision),
                      'actual zero-entry original paths exactly preserve both reports')
                check(not session.entries, 'zero-entry retains no optional proof')
        check(not session.active and not session.entries and not session.capabilities,
              'zero-entry session releases all proof and capabilities')
        check(shared._H_VALIDATION_SESSION.get() is None, 'zero-entry releases ambient session')
    assert not issues, 'H_CACHE_PROOF_DIAGNOSTIC=' + dumps(
        {'issues': issues, 'own_proof_events': proof_events, 'calls': calls},
        sort_keys=True, separators=(',', ':'))


def test_original_discovery_never_retains_optional_metadata_under_ambient_session(full_wire_history, monkeypatch):
    item = full_wire_history
    calls, original = [], shared.evidence_paths
    def observe(*args, **kwargs):
        paths = original(*args, **kwargs)
        if shared._H_VALIDATION_CAPTURE.get() is None:
            calls.append(True)
            assert not paths._documents and not paths._edges and paths._guard_memory is None
        return paths
    monkeypatch.setattr(shared, 'evidence_paths', observe)
    with shared.validation_session() as session:
        paths = shared.evidence_paths([item['study']], item['root'], load_document(item['study'])['budget'],
            root_contexts={item['study']: 'h_study_contract'}, include_repository_sources=True)
        assert paths and not paths._documents and not paths._edges
        # A nonzero live bound can fit a real report while declining to retain
        # the extra discovery projection. Original full evidence stays intact.
        report = readers(item)[0]()
        assert report['valid'], report['errors']
        report_size = shared._retained_size(report)
        assert report_size is not None and report_size > 4096
        session.entries.clear()
        monkeypatch.setattr(shared, '_MEMO_BYTES', report_size)
        plain = readers(item)[0]()
        assert plain['valid'] and shared.typed_equal(report, plain), plain['errors']
        assert calls and not session.entries
    assert shared._H_VALIDATION_CAPTURE.get() is None


@pytest.mark.parametrize('mode', ['miss', 'hit'])
def test_final_real_guard_capacity_fallback_preserves_complete_source(full_wire_history, monkeypatch, mode):
    item, calls, guard_counts, refused = full_wire_history, [], [], []
    original, original_source = shared._memo_base, source_reader.schema_errors
    armed = False
    def compute(*args, **kwargs):
        calls.append('real_source')
        if mode == 'hit' and armed and refused:
            assert sys.exc_info()[0] is None
            assert refused[-1]() is None  # Final guard and private clone frame exited.
            assert shared._H_VALIDATION_CAPTURE.get() is None
            assert not shared._H_VALIDATION_SESSION.get().working
        return original_source(*args, **kwargs)
    def observe(descriptor, **kwargs):
        result = original(descriptor, **kwargs)
        if armed and descriptor['roots'] == (str(item['study']),):
            guard_counts.append(True)
            target = 3 if mode == 'miss' else 2
            if len(guard_counts) % target == 0:
                session = shared._H_VALIDATION_SESSION.get()
                snapshot, paths = result
                live = shared._retained_size((session, kwargs.get('working', ()), snapshot, paths._documents, paths._edges, paths._guard_memory))
                assert live is not None and live > 4096
                refused.append(weakref.ref(paths))
                monkeypatch.setattr(shared, '_MEMO_BYTES', live + 1024)
        return result
    monkeypatch.setattr(source_reader, 'schema_errors', compute)
    monkeypatch.setattr(shared, '_memo_base', observe)
    with shared.validation_session() as session:
        prime = None
        if mode == 'hit':
            prime = readers(item)[0]()
            assert prime['valid'], prime['errors']
            assert any(key[0] == 'study_source' for key in session.entries)
        armed = True
        one = readers(item)[0]()
        assert one['valid'], one['errors']
        assert len(guard_counts) == (3 if mode == 'miss' else 2)
        assert not any(key[0] == 'study_source' for key in session.entries)
        assert not session.working and refused[-1]() is None
        if prime is not None:
            assert shared.typed_equal(prime, one) and calls == ['real_source', 'real_source']
            # The dropped hit cannot make a later complete access inherit it.
            armed = False
        monkeypatch.setattr(shared, '_MEMO_BYTES', 64 * 1024 * 1024)
        two = readers(item)[0]()
        assert two['valid'] and shared.typed_equal(one, two), two['errors']
        assert len(calls) == (2 if mode == 'miss' else 3)
        if mode == 'miss':
            assert not any(key[0] == 'study_source' for key in session.entries)
        assert not session.working


def test_nested_real_H2_child_shares_parent_live_cap_and_releases_refused_guards(full_wire_history, monkeypatch):
    item, boundaries, refused, originals, isolated_guards = full_wire_history, [], [], [], []
    original_extras, original_receipt = shared._memo_extras, study_reader.schema_errors
    original_cap = 64 * 1024 * 1024
    testing_nested = True
    def extras(paths, budget, **kwargs):
        result = original_extras(paths, budget, **kwargs)
        working = kwargs.get('working', ())
        if not working or not isinstance(working[0], dict):
            return result
        descriptor = working[0]
        if descriptor['roots'] != (str(item['study_receipt']),):
            return result
        session = shared._H_VALIDATION_SESSION.get()
        parents = [work for work in session.working if work[0].get('roots') == (str(item['h2']),)]
        if parents:
            # Measure the actual same child graph with the actual accounting
            # function; only the prospective isolated owner's parent stack is
            # absent. Neither observer invents a byte count or successful result.
            isolated = shared._ValidationSession()
            isolated.entries = session.entries
            isolated.inflight = session.inflight
            isolated.capabilities = session.capabilities
            isolated_size = shared._retained_size((isolated, working, result))
            parent_size = shared._retained_size(session)
            combined = shared._retained_size((session, working, result))
            assert None not in (isolated_size, parent_size, combined)
            lower = max(isolated_size, parent_size)
            assert combined > lower + 4096
            cap = (lower + combined) // 2
            assert 0 < isolated_size < cap < combined
            boundaries.append((isolated_size, parent_size, combined, cap))
            refused.append(weakref.ref(paths))
            monkeypatch.setattr(shared, '_MEMO_BYTES', cap)
            assert shared._retained_size((session, working, result)) is None
        elif boundaries:
            measured = shared._retained_size((session, working, result))
            if measured is not None:
                isolated_guards.append(measured)
        return result
    def receipt(*args, **kwargs):
        originals.append(True)
        if testing_nested and refused:
            assert sys.exc_info()[0] is None
            assert refused[-1]() is None
            assert shared._H_VALIDATION_CAPTURE.get() is None
            session = shared._H_VALIDATION_SESSION.get()
            assert shared._retained_size(session) is not None
            assert not any(work[0].get('roots') == (str(item['study_receipt']),) for work in session.working)
        return original_receipt(*args, **kwargs)
    # A real normal result establishes parity before the bounded original-path
    # control. It is a separate operation and cannot seed the tested owner.
    expected = readers(item)[2]()
    assert expected['valid'] and expected['assessment_ready'], expected['errors']
    monkeypatch.setattr(shared, '_memo_extras', extras)
    monkeypatch.setattr(study_reader, 'schema_errors', receipt)
    with shared.validation_session() as session:
        for occurrence in range(2):
            monkeypatch.setattr(shared, '_MEMO_BYTES', original_cap)
            actual = readers(item)[2]()
            assert actual['valid'] and shared.typed_equal(expected, actual), actual['errors']
            assert len(boundaries) == occurrence + 1 and len(originals) == occurrence + 1
            assert not any(key[0] in {'h2_source', 'study_receipt'} for key in session.entries)
            assert not session.working and refused[-1]() is None
    # The isolated actual child can construct this complete private guard under
    # the chosen nonzero cap, while the preceding combined parent+child cannot.
    testing_nested = False
    monkeypatch.setattr(shared, '_MEMO_BYTES', boundaries[-1][-1])
    with shared.validation_session() as session:
        isolated = readers(item)[1]()
        assert isolated['valid'] and isolated['study_complete'], isolated['errors']
        assert isolated_guards and all(size <= boundaries[-1][-1] for size in isolated_guards)
        assert not session.working


def test_deferred_real_qualification_commit_capacity_drops_only_optional_fact(full_wire_history, monkeypatch):
    import h_analysis_trial as native
    import validate_h_analysis_trial_receipt as native_reader
    item, calls = full_wire_history, []
    names = native.contract()['evidence']
    path = item['study_receipt'].parent / 'trial-batch-000001' / names['run_receipt']
    original_finish = native_reader._finish_historical_replay
    original_collect = native._collect_qualification_facts
    def finish(replay, *, complete):
        if replay is not None and complete and replay._capability.pending is not None:
            session = shared._H_VALIDATION_SESSION.get()
            live = shared._retained_size((session, replay._capability.pending))
            assert live is not None and live > 4096
            monkeypatch.setattr(shared, '_MEMO_BYTES', live + 1024)
        return original_finish(replay, complete=complete)
    def collect(request, case, started_at, *, include_h):
        if request['mode'] == 'trial' and include_h is True:
            calls.append(True)
        return original_collect(request, case, started_at, include_h=include_h)
    monkeypatch.setattr(native_reader, '_finish_historical_replay', finish)
    monkeypatch.setattr(native, '_collect_qualification_facts', collect)
    with shared.validation_session() as session:
        first = native_reader.validate_h_analysis_trial_receipt(path, project_root=item['root'])
        assert first['valid'] and first['trial_complete'], first['errors']
        assert not any(key[0] == 'historical_qualification' for key in session.entries)
        monkeypatch.setattr(shared, '_MEMO_BYTES', 64 * 1024 * 1024)
        second = native_reader.validate_h_analysis_trial_receipt(path, project_root=item['root'])
        assert second['valid'] and second['trial_complete'] and len(calls) == 2, (calls, second['errors'])
        assert not any(key[0] == 'historical_qualification' for key in session.entries)
