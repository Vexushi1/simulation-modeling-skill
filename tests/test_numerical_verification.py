"""H1 contract/number/history regressions; fixtures qualify no real simulation."""
import copy
import math
import shutil
from pathlib import Path

import pytest

from numerical_factory import freeze_level, make_numerical_contract, make_numerical_runs, review_numerical
from probe_environment import write_json
from problem_factory import write_contract
from run_numerical_verification import (INPUT_NAME, RECEIPT_NAME, RESULT_NAME, actual_samples,
                                        assess_numerical, refinement_result, run_numerical_verification)
from runtime_common import ROOT, load_document, sha256_file
from validate_numerical_verification import time_tolerance, uniform_grid, validate_numerical_verification
from validate_numerical_verification_receipt import validate_numerical_verification_receipt
from verification_common import HARD_BUDGET, evidence_paths, input_manifest, serialized_json, typed_equal


@pytest.fixture(scope='module')
def accepted_history(tmp_path_factory):
    """Construct once; every adversarial test still invokes the real consumer."""
    root = tmp_path_factory.mktemp('h1-accepted-history')
    contract, receipts = make_numerical_runs(root)
    report = run_numerical_verification(contract, receipts, root / 'accepted', project_root=root)
    assert report['valid'] and report['numerically_verified'], report['errors']
    return {'root': root, 'contract': contract, 'receipts': receipts,
            'receipt': Path(report['receipt_path']), 'report': report}


@pytest.fixture
def history(accepted_history, request):
    root = accepted_history['root']
    saved = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    saved_directories = {p for p in root.rglob('*') if p.is_dir()}
    directory = root / ('case-' + request.node.name.replace('[', '-').replace(']', '-'))
    shutil.copytree(accepted_history['receipt'].parent, directory)
    value = {**accepted_history, 'directory': directory, 'receipt': directory / RECEIPT_NAME}
    try:
        yield value
    finally:
        for path in root.rglob('*'):
            if path.is_file() and path not in saved:
                path.unlink()
        for path, payload in saved.items():
            path.write_bytes(payload)
        for path in sorted((p for p in root.rglob('*') if p.is_dir() and p not in saved_directories),
                           key=lambda p: len(p.parts), reverse=True):
            shutil.rmtree(path, ignore_errors=True)
        shutil.rmtree(directory, ignore_errors=True)


def rebind_artifact(receipt_path, artifact_path):
    receipt = load_document(receipt_path)
    receipt['artifacts'][artifact_path.name].update(sha256=sha256_file(artifact_path), bytes=artifact_path.stat().st_size)
    write_json(receipt_path, receipt)


def check(path, **kwargs):
    return validate_numerical_verification(path, project_root=path.parent, **kwargs)


def test_unknown_draft_is_valid_read_only_without_acceptance(tmp_path):
    path = tmp_path / 'draft.yaml'
    path.write_bytes((ROOT / 'templates/contracts/numerical_verification.yaml').read_bytes())
    before = path.read_bytes()
    result = check(path)
    assert result['valid'] and result['schema_valid'], result['errors']
    assert not result['assessment_ready'] and not result['reviewed']
    assert not result['environment_checked'] and not result['execution_allowed']
    assert not check(path, require_reviewed=True)['valid']
    assert path.read_bytes() == before


@pytest.mark.parametrize('method', ['ode4_step_refinement', 'ode45_tolerance_refinement'])
def test_current_three_protocol_plan_and_real_format_synthetic_e_history(tmp_path, method):
    path, receipts = make_numerical_runs(tmp_path, method=method)
    report = check(path, require_reviewed=True)
    assert report['valid'] and report['assessment_ready'], report['errors']
    inputs = {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    result = run_numerical_verification(path, receipts, tmp_path / 'analysis', project_root=tmp_path)
    assert result['valid'] and result['numerically_verified'], result['errors']
    output = result['outputs'][0]
    assert output['D01'] > output['D12'] > 0
    assert output['sample_count'] == (11 if method == 'ode4_step_refinement' else 2)
    assert (output['empirical_order'] is None) == method.startswith('ode45')
    assert all(p.read_bytes() == original for p, original in inputs.items())
    again = validate_numerical_verification_receipt(result['receipt_path'], project_root=tmp_path)
    assert again['valid'] and again['primary_receipt_path'] == str(receipts[0])
    assert not again['environment_checked'] and not again['execution_allowed']
    with pytest.raises(FileExistsError):
        run_numerical_verification(path, receipts, tmp_path / 'analysis', project_root=tmp_path)


@pytest.mark.parametrize('change', ['required', 'deferred', 'wrong_source', 'wrong_unit', 'floor_too_large', 'wrong_grid', 'missing_review'])
def test_review_cannot_supply_missing_necessary_obligations_or_wrong_settings(tmp_path, change):
    path = make_numerical_contract(tmp_path)
    value = load_document(path)
    if change in {'required', 'deferred'}:
        value['obligations']['residual']['status'] = change
    elif change == 'wrong_source':
        value['obligations']['residual']['source_ids'] = ['absent']
    elif change == 'wrong_unit':
        value['outputs'][0]['unit'] = 'wrong-unit'
    elif change == 'floor_too_large':
        value['outputs'][0]['roundoff_floor'] = 1.0
    elif change == 'wrong_grid':
        value['comparison_times'] = [0.0, 1.0]
    else:
        value['review_record'] = None
        value['status'] = 'reviewed'
    write_contract(path, value)
    if change != 'missing_review':
        review_numerical(path)
    result = check(path, require_reviewed=True)
    assert not result['valid'] and not result['assessment_ready']


@pytest.mark.parametrize('field,value', [('absolute_tolerance', True), ('relative_tolerance', '0'), ('contraction_limit', 1.0), ('roundoff_floor', -1.0)])
def test_fake_numbers_and_invalid_limits_fail_before_assessment(tmp_path, field, value):
    path = make_numerical_contract(tmp_path)
    source = load_document(path)
    source['outputs'][0][field] = value
    write_contract(path, source)
    assert not check(path)['valid']


def criteria(**changes):
    value = {'port': 1, 'variable_id': 'x', 'unit': '1', 'absolute_tolerance': 0.01,
             'relative_tolerance': 0.0, 'contraction_limit': 0.5, 'roundoff_floor': 1e-12}
    value.update(changes)
    return value


def test_primary_difference_must_pass_even_when_fine_levels_agree():
    result = refinement_result(criteria(), [[1.0], [0.0], [0.0]])
    assert not result['criteria_satisfied'] and result['fine_difference_satisfied']


@pytest.mark.parametrize('samples,passed,order', [([[0.0], [0.0], [0.0]], True, None),
    ([[0.0], [0.0], [1e-13]], True, None), ([[0.0], [0.0], [1e-5]], False, None),
    ([[0.0], [0.001], [0.003]], False, -1.0)])
def test_floor_and_noncontracting_differences_are_distinct(samples, passed, order):
    result = refinement_result(criteria(), samples)
    assert result['criteria_satisfied'] == passed
    assert result['empirical_order'] is None if order is None else result['empirical_order'] == pytest.approx(order)


def test_nonfinite_subtraction_and_tolerance_overflow_are_blocked():
    with pytest.raises(ValueError, match='non-finite'):
        refinement_result(criteria(), [[1e308], [-1e308], [-1e308]])
    with pytest.raises(ValueError, match='non-finite'):
        refinement_result(criteria(relative_tolerance=1e308), [[1e308], [1e308], [1e308]])


def test_native_common_times_use_unique_real_samples_without_interpolation():
    output = {'time': [0.0, 0.5, 1.0], 'values': [0.0, 1.0, 2.0]}
    assert actual_samples(output, [0.0, 1.0]) == [0.0, 2.0]
    with pytest.raises(ValueError, match='missing or ambiguous'):
        actual_samples(output, [0.25])
    output['time'][1] = time_tolerance(0.0)/2
    with pytest.raises(ValueError, match='ambiguous'):
        actual_samples(output, [0.0])
    with pytest.raises(ValueError, match='complete integer grid'):
        actual_samples({'time': [0.0, 1.0], 'values': [0.0, 1.0]}, [0.0, 1.0], native_grid=[0.0, 0.5, 1.0])


def test_integer_grid_negative_start_nonbinary_step_and_unrepresentable_boundary():
    grid = uniform_grid(-0.3, 0.3, 0.1)
    assert len(grid) == 7 and grid[-1] == 0.3
    assert len(uniform_grid(0.0, 30.0, 0.01)) == 3001
    with pytest.raises(ValueError, match='3000'):
        uniform_grid(0.0, 30.0, 0.001)
    with pytest.raises(ValueError, match='integer'):
        uniform_grid(0.0, 1.0, 0.3)


def test_failed_criteria_produce_valid_reject_evidence(tmp_path):
    path, receipts = make_numerical_runs(tmp_path, offsets=(1.0, 0.0, 0.0))
    report = run_numerical_verification(path, receipts, tmp_path / 'rejected')
    assert report['valid'] and not report['criteria_satisfied'] and not report['numerically_verified'], report['errors']


def test_wrong_order_and_incomplete_e_history_preserve_blocked_receipt(tmp_path):
    path, receipts = make_numerical_runs(tmp_path)
    result = run_numerical_verification(path, list(reversed(receipts)), tmp_path / 'blocked')
    assert not result['valid'] and not result['numerically_verified']
    assert load_document(result['receipt_path'])['status'] == 'blocked'
    assert (tmp_path / 'blocked' / 'numerical-verification-input.json').is_file()


def test_receipt_claim_cannot_replace_independent_numeric_recomputation(history):
    receipt_path = history['receipt']
    stored_path = history['directory'] / RESULT_NAME
    stored = load_document(stored_path)
    stored['outputs'][0]['D01'] = 0.0
    write_json(stored_path, stored)
    rebind_artifact(receipt_path, stored_path)
    changed = validate_numerical_verification_receipt(receipt_path, project_root=history['root'])
    assert not changed['valid'] and any('recomputation' in e for e in changed['errors'])


def test_read_budgets_reject_without_truncating_input(tmp_path):
    path = make_numerical_contract(tmp_path)
    value = load_document(path)
    value['budget'].update(max_file_bytes=64, max_total_bytes=1024)
    write_contract(path, value)
    review_numerical(path)
    assert not check(path)['valid']


def test_historical_runtime_ttl_does_not_expire_unchanged_assessment(tmp_path):
    path, receipts = make_numerical_runs(tmp_path, age_hours=25)
    result = run_numerical_verification(path, receipts, tmp_path / 'historical')
    assert result['valid'] and result['numerically_verified'], result['errors']


@pytest.mark.parametrize('change', ['seed', 'admission', 'wrong_ratio', 'solver'])
def test_independently_frozen_legal_e_settings_still_need_h_comparability(tmp_path, change):
    path = make_numerical_contract(tmp_path)
    value = load_document(path)
    protocol_path = tmp_path / value['refinement_protocols'][0]['path']
    protocol = load_document(protocol_path)
    if change == 'seed':
        protocol['seed']['value'] += 1
    elif change == 'admission':
        protocol['metrics'][0]['upper'] = 1e7
    elif change == 'wrong_ratio':
        protocol['solver']['fixed_step'] = 0.025
    else:
        protocol['solver'].update(name='ode45', type='variable-step', fixed_step=None,
                                  max_step=0.05, min_step=1e-12, initial_step=0.01, rel_tol=1e-6, abs_tol=1e-8)
    write_contract(protocol_path, protocol)
    freeze_level(protocol_path, tmp_path)
    value['refinement_protocols'][0]['sha256'] = sha256_file(protocol_path)
    write_contract(path, value)
    review_numerical(path)
    result = check(path, require_reviewed=True)
    assert not result['valid'] and not result['assessment_ready']


def test_complete_source_snapshot_binds_units_limits_and_claim_scope(tmp_path):
    path = make_numerical_contract(tmp_path)
    value = load_document(path)
    value['claim_limit'] += 'Changed after original source review.'
    write_contract(path, value)
    review_numerical(path, refresh_source=False)
    result = check(path)
    assert not result['valid'] and any('source snapshot' in e for e in result['errors'])


@pytest.mark.parametrize('field', ['reviewed_by', 'action', 'verification_semantic_sha256'])
def test_review_unique_context_cannot_be_replaced_with_a_flag(tmp_path, field):
    path = make_numerical_contract(tmp_path)
    value = load_document(path)
    record_path = tmp_path / value['review_record']['path']
    record = load_document(record_path)
    decision = record['decision']
    decision['quote'] += '\n' + field + '=different-or-duplicated-context'
    decision_path = tmp_path / decision['path']
    decision_path.write_text(decision['quote'] + '\n', encoding='utf-8')
    decision.update(end=len(decision['quote']), sha256=sha256_file(decision_path))
    write_contract(record_path, record)
    value['review_record']['sha256'] = sha256_file(record_path)
    write_contract(path, value)
    assert not check(path, require_reviewed=True)['valid']


def test_source_and_result_snapshot_comparison_preserves_number_types():
    assert not typed_equal({'number': 0}, {'number': 0.0})
    assert not typed_equal({'number': False}, {'number': 0})


def test_read_manifest_rejects_paths_outside_project_root(tmp_path):
    root = tmp_path / 'project'
    root.mkdir()
    external = tmp_path / 'external.json'
    write_json(external, {'external': True})
    with pytest.raises(ValueError, match='leaves project root'):
        input_manifest([external], root, HARD_BUDGET)


def test_rebound_review_cannot_accept_changed_numeric_source_type(history):
    path = history['contract']
    contract = load_document(path)
    source_path = history['root'] / contract['sources'][0]['path']
    source = load_document(source_path)
    source['settings']['outputs'][0]['port'] = float(source['settings']['outputs'][0]['port'])
    write_json(source_path, source)
    contract['sources'][0]['sha256'] = sha256_file(source_path)
    write_contract(path, contract)
    review_numerical(path, refresh_source=False)
    result = validate_numerical_verification(path, project_root=history['root'], require_reviewed=True)
    assert not result['valid'] and not result['assessment_ready']
    assert any('typed source snapshot differs' in error for error in result['errors'])


@pytest.mark.parametrize('field', list(HARD_BUDGET))
def test_reviewed_read_budget_requires_exact_integer_counts(history, field):
    contract = load_document(history['contract'])
    contract['budget'][field] = float(contract['budget'][field])
    write_contract(history['contract'], contract)
    review_numerical(history['contract'])
    report = validate_numerical_verification(history['contract'], project_root=history['root'], require_reviewed=True)
    assert not report['valid'] and not report['assessment_ready']
    assert any('integer counts' in error for error in report['errors'])


@pytest.mark.parametrize('field', ['port', 'sample_count'])
def test_rehashed_actual_result_integer_to_float_is_not_accepted(history, field):
    result_path = history['directory'] / RESULT_NAME
    stored = load_document(result_path)
    stored['outputs'][0][field] = float(stored['outputs'][0][field])
    write_json(result_path, stored)
    rebind_artifact(history['receipt'], result_path)
    report = validate_numerical_verification_receipt(history['receipt'], project_root=history['root'])
    assert not report['valid'] and not report['numerically_verified']
    assert any('recomputation' in error for error in report['errors'])


@pytest.mark.parametrize('filename', [RECEIPT_NAME, INPUT_NAME, RESULT_NAME])
def test_own_receipt_and_artifact_changes_after_decoding_are_rejected(history, monkeypatch, filename):
    import validate_numerical_verification_receipt as consumer
    original = consumer.typed_equal
    changed = False

    def compare(actual, expected):
        nonlocal changed
        equal = original(actual, expected)
        if not changed and isinstance(actual, dict) and 'disposition' in actual and 'outputs' in actual:
            target = history['directory'] / filename
            target.write_bytes(target.read_bytes() + b' ')
            changed = True
        return equal

    monkeypatch.setattr(consumer, 'typed_equal', compare)
    report = consumer.validate_numerical_verification_receipt(history['receipt'], project_root=history['root'])
    assert changed and not report['valid'] and not report['numerically_verified']
    assert any('changed during assessment' in error for error in report['errors'])


def test_safety_source_change_during_receipt_read_is_rejected(history, monkeypatch):
    import validate_numerical_verification_receipt as consumer
    original = consumer.source_identities
    calls = 0

    def identities():
        nonlocal calls
        calls += 1
        result = original()
        if calls > 1:
            key = next(iter(result))
            result[key] = '0' * 64
        return result

    monkeypatch.setattr(consumer, 'source_identities', identities)
    report = consumer.validate_numerical_verification_receipt(history['receipt'], project_root=history['root'])
    assert calls >= 2 and not report['valid']
    assert any('source changed during reading' in error for error in report['errors'])


@pytest.mark.parametrize('field,value', [('run_id', 1), ('errors', {})])
def test_actual_receipt_requires_exact_run_and_error_types(history, field, value):
    receipt = load_document(history['receipt'])
    receipt[field] = value
    write_json(history['receipt'], receipt)
    if field == 'run_id':
        input_path = history['directory'] / INPUT_NAME
        request = load_document(input_path)
        request['run_id'] = value
        from runtime_common import canonical_digest
        request['input_identity'] = canonical_digest({k: v for k, v in request.items() if k != 'input_identity'})
        write_json(input_path, request)
        rebind_artifact(history['receipt'], input_path)
    report = validate_numerical_verification_receipt(history['receipt'], project_root=history['root'])
    assert not report['valid'] and not report['numerically_verified']


def test_total_budget_is_checked_for_all_files_before_first_hash(tmp_path, monkeypatch):
    import verification_common as common
    files = [tmp_path / name for name in ('a.txt', 'b.txt')]
    for file in files:
        file.write_bytes(b'x' * 80)
    budget = {**HARD_BUDGET, 'max_file_bytes': 100, 'max_total_bytes': 159}
    hashes = []
    monkeypatch.setattr(common, 'sha256_file', lambda path: hashes.append(path))
    with pytest.raises(ValueError, match='byte budget'):
        common.input_manifest(files, tmp_path, budget)
    assert hashes == []


def test_oversized_own_result_rejects_before_its_hash_or_decode(history, monkeypatch):
    import verification_common as common
    target = history['directory'] / RESULT_NAME
    with target.open('ab') as stream:
        stream.truncate(HARD_BUDGET['max_result_bytes'] + 1)
    seen = []
    original_hash, original_load = common.sha256_file, common.load_document

    def hash_file(path):
        if Path(path).resolve() == target:
            seen.append('hash')
        return original_hash(path)

    def load_file(path):
        if Path(path).resolve() == target:
            seen.append('decode')
        return original_load(path)

    monkeypatch.setattr(common, 'sha256_file', hash_file)
    monkeypatch.setattr(common, 'load_document', load_file)
    report = validate_numerical_verification_receipt(history['receipt'], project_root=history['root'])
    assert not report['valid'] and any('result byte budget' in error for error in report['errors'])
    assert seen == []


def test_oversized_e_receipt_blocks_producer_before_its_hash_or_decode(history, monkeypatch):
    import verification_common as common
    import run_numerical_verification as producer
    target = history['root'] / 'oversized-e-receipt.json'
    with target.open('wb') as stream:
        stream.truncate(HARD_BUDGET['max_file_bytes'] + 1)
    seen = []
    original_hash, original_load = common.sha256_file, common.load_document

    def hash_file(path):
        if Path(path).resolve() == target:
            seen.append('hash')
        return original_hash(path)

    def load_file(path):
        if Path(path).resolve() == target:
            seen.append('decode')
        return original_load(path)

    monkeypatch.setattr(common, 'sha256_file', hash_file)
    monkeypatch.setattr(common, 'load_document', load_file)
    monkeypatch.setattr(producer, 'sha256_file', hash_file)
    report = producer.run_numerical_verification(history['contract'], [*history['receipts'][:2], target],
                                                 history['root'] / 'over-budget-producer', project_root=history['root'])
    assert not report['valid'] and seen == []
    stored = load_document(report['receipt_path'])
    assert stored['status'] == 'blocked' and any('byte budget' in error for error in stored['errors'])


def test_own_and_upstream_files_share_the_reviewed_aggregate_budget(history, monkeypatch):
    import verification_common as common
    receipt = load_document(history['receipt'])
    upstream_size = sum(item['bytes'] for item in receipt['input_manifest'])
    contract = load_document(history['contract'])
    contract['budget']['max_file_bytes'] = max(item['bytes'] for item in history['report']['bound_files']) + 1000
    contract['budget']['max_total_bytes'] = upstream_size + 1000
    write_contract(history['contract'], contract)
    review_numerical(history['contract'])
    current = validate_numerical_verification(history['contract'], project_root=history['root'], require_reviewed=True)
    assert current['valid'] and current['assessment_ready'], current['errors']
    target = history['directory'] / RESULT_NAME
    original_hash = common.sha256_file
    seen = []

    def hash_file(path):
        if Path(path).resolve() == target:
            seen.append(path)
        return original_hash(path)

    monkeypatch.setattr(common, 'sha256_file', hash_file)
    report = validate_numerical_verification_receipt(history['receipt'], project_root=history['root'])
    assert not report['valid'] and any('byte budget' in error for error in report['errors'])
    assert seen == []


def test_declared_sample_budget_blocks_before_native_mat_consumer(history, monkeypatch):
    import run_numerical_verification as producer
    receipt = load_document(history['receipts'][0])
    path = history['receipts'][0].parent / receipt['artifacts']['data']['file']
    data = load_document(path)
    data['outputs'][0].update(time=list(range(12002)), values=[0.0] * 12002)
    write_json(path, data)
    receipt['artifacts']['data']['sha256'] = sha256_file(path)
    write_json(history['receipts'][0], receipt)
    report = validate_numerical_verification(history['contract'], project_root=history['root'], require_reviewed=True)
    assert report['valid'] and report['assessment_ready'], report['errors']
    calls = []
    monkeypatch.setattr(producer, 'validate_simulation_receipt', lambda *args, **kwargs: calls.append(args))
    with pytest.raises(ValueError, match='sample count budget'):
        assess_numerical(report, history['receipts'], project_root=history['root'])
    assert calls == []


def test_source_reader_failure_preserves_blocked_producer_receipt(history, monkeypatch):
    import run_numerical_verification as producer

    def failed_reader():
        raise ValueError('synthetic unavailable safety source')

    monkeypatch.setattr(producer, 'source_identities', failed_reader)
    report = producer.run_numerical_verification(history['contract'], history['receipts'],
                                                 history['root'] / 'missing-source', project_root=history['root'])
    assert not report['valid']
    receipt = load_document(report['receipt_path'])
    assert receipt['status'] == 'blocked' and receipt['errors'] == ['synthetic unavailable safety source']


@pytest.mark.parametrize('delta,valid', [(0, True), (-1, False)])
def test_result_byte_budget_uses_the_exact_persisted_serializer(history, delta, valid):
    expected_bytes = len(serialized_json(load_document(history['directory'] / RESULT_NAME)))
    assert expected_bytes == (history['directory'] / RESULT_NAME).stat().st_size
    contract = load_document(history['contract'])
    contract['budget']['max_result_bytes'] = expected_bytes + delta
    write_contract(history['contract'], contract)
    review_numerical(history['contract'])
    report = run_numerical_verification(history['contract'], history['receipts'], history['root'] / 'result-boundary',
                                         project_root=history['root'])
    assert report['valid'] is valid, report['errors']
    receipt = load_document(report['receipt_path'])
    assert receipt['status'] == ('complete' if valid else 'blocked')
    if valid:
        assert (Path(report['receipt_path']).parent / RESULT_NAME).stat().st_size == expected_bytes
    else:
        assert any('result exceeds declared byte budget' in error for error in receipt['errors'])


@pytest.mark.parametrize('samples,passed', [([[1e308], [0.0], [5e-324]], True),
                                         ([[5e-324], [0.0], [1e308]], False)])
def test_extreme_positive_differences_keep_finite_empirical_order_and_disposition(samples, passed):
    result = refinement_result(criteria(absolute_tolerance=1e308, roundoff_floor=0.0), samples)
    assert result['D01'] > 0 and result['D12'] > 0
    assert math.isfinite(result['empirical_order'])
    assert result['criteria_satisfied'] is passed


def test_original_external_qualifications_are_readonly_budgeted_and_task_paths_stay_contained(tmp_path):
    project, qualification = tmp_path / 'project', tmp_path / 'qualifications'
    path, receipts = make_numerical_runs(project, qualification_root=qualification)
    original = {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    result = run_numerical_verification(path, receipts, project / 'analysis', project_root=project)
    assert result['valid'] and result['numerically_verified'], result['errors']
    external = {Path(item) for item in result['allowed_external']}
    assert any(item.name == 'profile.json' for item in external)
    assert any(item.name == 'implementation-profile.json' for item in external)
    assert any(item.name == 'simulation-profile.json' for item in external)
    assert any(item.suffix == '.mat' for item in external)
    assert all(item.is_relative_to(qualification) for item in external)
    assert all(p.read_bytes() == payload for p, payload in original.items())
    # Even a same-byte numeric artifact is not qualification evidence.
    receipt = load_document(receipts[0])
    data = project / 'numerical-e-run-0' / receipt['artifacts']['data']['file']
    outside = qualification / 'external-task-data.json'
    outside.write_bytes(data.read_bytes())
    receipt['artifacts']['data']['file'] = str(outside)
    write_json(receipts[0], receipt)
    changed = validate_numerical_verification_receipt(result['receipt_path'], project_root=project)
    assert not changed['valid'] and any('escapes project root' in e or 'leaves project root' in e for e in changed['errors'])
    receipts[0].write_bytes(original[receipts[0]])
    contract = load_document(path)
    source = project / contract['sources'][0]['path']
    outside_source = qualification / 'external-task-source.json'
    outside_source.write_bytes(source.read_bytes())
    contract['sources'][0]['path'] = str(outside_source)
    write_contract(path, contract)
    review_numerical(path, refresh_source=False)
    changed = validate_numerical_verification(path, project_root=project, require_reviewed=True)
    assert not changed['valid'] and not changed['assessment_ready']


@pytest.mark.parametrize('filename', ['simulation-receipt.json', 'implementation-receipt.json'])
def test_reviewed_task_source_cannot_gain_qualification_privileges_from_its_filename(history, tmp_path, monkeypatch, filename):
    import verification_common as common
    root, path = history['root'], history['contract']
    external = tmp_path / 'arbitrary.json'
    write_json(external, {'unrelated_external_task_file': True})
    contract = load_document(path)
    source = load_document(root / contract['sources'][0]['path'])
    directory = root / ('masquerading-' + filename.removesuffix('.json'))
    directory.mkdir()
    fake_input = directory / 'fake-input.json'
    write_json(fake_input, {'bindings': {'environment_profile': {
        'path': str(external), 'sha256': sha256_file(external)}}})
    source['artifacts'] = {'input': {'file': fake_input.name, 'sha256': sha256_file(fake_input)}}
    source_path = directory / filename
    write_json(source_path, source)
    contract['sources'][0].update(path=str(source_path.relative_to(root)), sha256=sha256_file(source_path))
    write_contract(path, contract)
    review_numerical(path, refresh_source=False)
    observed = []
    original_hash, original_load = common.sha256_file, common.load_document

    def hash_file(file):
        if Path(file).resolve() == external:
            observed.append('hash')
        return original_hash(file)

    def load_file(file):
        if Path(file).resolve() == external:
            observed.append('load')
        return original_load(file)

    monkeypatch.setattr(common, 'sha256_file', hash_file)
    monkeypatch.setattr(common, 'load_document', load_file)
    report = validate_numerical_verification(path, project_root=root, require_reviewed=True)
    assert not report['valid'] and not report['assessment_ready']
    assert any('leaves project root' in error for error in report['errors'])
    assert observed == []


def test_unknown_evidence_root_context_cannot_authorize_qualification(tmp_path):
    with pytest.raises(ValueError, match='unknown verification evidence root context'):
        evidence_paths([tmp_path / 'unread.json'], tmp_path, HARD_BUDGET,
                       root_contexts={tmp_path / 'unread.json': 'qualification_e_receipt'})
