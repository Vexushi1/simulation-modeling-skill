"""Actual whole-wire controls for operation-local H proof reuse.

Fixtures and every acceptance result are explicitly SYNTHETIC INFRASTRUCTURE
TESTS. These controls call the actual consumers; they never execute MATLAB or
substitute a successful validator report.
"""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

import pytest

import verification_common as shared
import validate_h_analysis_study as source_reader
import validate_h_analysis_study_receipt as study_reader
import validate_model_verification as h2_source_reader
import validate_model_verification_receipt as h2_reader
from runtime_common import load_document
from test_h_analysis_integration import full_wire_history


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
    item = full_wire_history
    calls, guards = [], []
    for name in ('validate_simulation_protocol', 'validate_simulation_receipt', 'validate_numerical_verification_receipt'):
        spy_original(monkeypatch, source_reader, name, calls, name)
    spy_original(monkeypatch, study_reader, 'assess_study', calls, 'study_metric')
    spy_original(monkeypatch, h2_reader, 'compute_assessment', calls, 'h2_metric')
    spy_original(monkeypatch, shared, 'input_manifest', guards, 'fresh_manifest')
    invoke = readers(item)
    with shared.validation_session() as session:
        first = [call() for call in invoke]
        assert all(report['valid'] for report in first), [r['errors'] for r in first]
        assert first[0]['study_ready'] and first[1]['study_complete'] and first[1]['defined']
        assert first[2]['assessment_ready'] and first[3]['model_verified']
        before = len(guards)
        second = [call() for call in invoke]
        assert all(shared.typed_equal(a, b) for a, b in zip(first, second))
        assert len(guards) >= before + 8  # Complete fresh pre/final manifests for every hit.
        assert {key[0] for key in session.entries} >= {
            'study_source', 'study_receipt', 'h2_source', 'h2_receipt',
            'baseline_protocol', 'baseline_simulation', 'baseline_h1'}
        assert all(calls.count(name) == 1 for name in ('validate_simulation_protocol',
            'validate_simulation_receipt', 'validate_numerical_verification_receipt', 'study_metric', 'h2_metric')), calls
        original_metric = second[0]['metric']['unit']
        second[0]['metric']['unit'] = 'SYNTHETIC caller mutation'
        second[1]['study_complete'] = False
        third = invoke[0]()
        assert third['valid'] and third['metric']['unit'] == original_metric
        assert not any('memo' in key or 'session' in key for report in first for key in report)
        assert shared._retained_size(session) is not None
    assert not session.active and not session.entries and not session.capabilities
    assert shared._H_VALIDATION_SESSION.get() is None


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
