"""H2 finite claim checks; synthetic histories confer no native/physical approval."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from model_verification_factory import make_model_verification_contract, omitted, review_model_verification
from model_verification_common import KINDS, compute_assessment, structural_snapshot
from probe_environment import write_json
from problem_factory import write_contract
from run_model_verification import run_model_verification, RESULT_NAME, INPUT_NAME
import validate_model_verification_receipt as receipt_consumer
import verification_common as shared_readers
from runtime_common import ROOT, load_document, sha256_file
from validate_model_verification import _analysis, validate_model_verification
from validate_model_verification_receipt import validate_model_verification_receipt
from verification_common import typed_equal


def test_unknown_draft_remains_read_only_without_acceptance(tmp_path):
    path = tmp_path / 'draft.yaml'
    path.write_bytes((ROOT / 'templates/contracts/model_verification.yaml').read_bytes())
    original = path.read_bytes()
    report = validate_model_verification(path, project_root=tmp_path)
    assert report['schema_valid'] and report['valid'], report['errors']
    assert not report['assessment_ready'] and not report['reviewed']
    assert not report['environment_checked'] and not report['execution_allowed']
    assert not validate_model_verification(path, project_root=tmp_path, require_reviewed=True)['valid']
    assert path.read_bytes() == original


@pytest.fixture(scope='module')
def model_history(tmp_path_factory):
    path = make_model_verification_contract(tmp_path_factory.mktemp('synthetic-h2'))
    before = {p: p.read_bytes() for p in path.parent.rglob('*') if p.is_file()}
    report = run_model_verification(path, path.parent / 'baseline-assessment', project_root=path.parent)
    assert report['valid'] and report['model_verified'], report['errors']
    assert all(p.read_bytes() == original for p, original in before.items())
    return path


@pytest.fixture
def current_history(model_history):
    root = model_history.parent
    saved = {path: path.read_bytes() for path in root.rglob('*') if path.is_file()}
    directories = {path for path in root.rglob('*') if path.is_dir()}
    yield model_history
    for path in sorted(root.rglob('*'), key=lambda p: len(p.parts), reverse=True):
        if path.is_file() and path not in saved:
            path.unlink()
        elif path.is_dir() and path not in directories:
            path.rmdir()
    for path, content in saved.items():
        path.write_bytes(content)


def test_complete_synthetic_H1_E_composition_and_independent_recomputation(current_history):
    path, root = current_history, current_history.parent
    original = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    result = validate_model_verification_receipt(root / 'baseline-assessment' / 'model-verification-receipt.json', project_root=root)
    assert result['valid'] and result['model_verification_decided'] and result['model_verified'], result['errors']
    assert result['claim_supported'] and not result['physical_validation']
    assert not result['environment_checked'] and not result['execution_allowed']
    assert result['claims'][0]['analyses'][0]['rows'][0]['finite_difference'] is None
    assert result['claims'][0]['analyses'][0]['rows'][1]['finite_difference'] > 0
    assert all(path.read_bytes() == content for path, content in original.items())
    with pytest.raises(ValueError, match='new output directory'):
        run_model_verification(path, root / 'baseline-assessment', project_root=root)


@pytest.mark.parametrize('disposition', ['modify', 'reject'])
def test_H2_claim_failure_preserves_valid_decided_evidence(current_history, disposition):
    path, root = current_history, current_history.parent
    value = load_document(path)
    value['claims'][0]['failure_disposition'] = disposition
    value['claims'][0]['analyses'][1]['bounds']['upper'] = 0.1
    write_contract(path, value)
    review_model_verification(path)
    report = run_model_verification(path, root / 'failed-claim', project_root=root)
    assert report['valid'] and report['model_verification_decided'], report['errors']
    assert not report['claim_supported'] and not report['model_verified']
    claim = report['claims'][0]
    assert claim['disposition'] == disposition and claim['return_stage'] == 'C'
    assert len(claim['analyses'][1]['rows']) == 2
    assert all(row['passed'] is False for row in claim['analyses'][1]['rows'])


@pytest.mark.parametrize('change', ['missing_method', 'wrong_unit', 'duplicate_kind', 'missing_member', 'false_omission'])
def test_required_analyses_cannot_be_hidden_by_review(current_history, change):
    path = current_history
    value = load_document(path)
    analysis = value['claims'][0]['analyses'][0]
    if change == 'missing_method':
        analysis['method'] = None
    elif change == 'wrong_unit':
        analysis['bounds']['unit'] = 'W'
    elif change == 'duplicate_kind':
        value['claims'][0]['analyses'][2] = copy.deepcopy(analysis)
    elif change == 'missing_member':
        value['members'][0]['numerical_receipt'] = None
    else:
        value['claims'][0]['analyses'][0] = omitted('sensitivity')
    write_contract(path, value)
    review_model_verification(path, refresh_obligations=change != 'false_omission')
    report = validate_model_verification(path, project_root=path.parent, require_reviewed=True)
    assert not report['valid'] and not report['assessment_ready']
    assert report['errors'] or report['missing_gates']


def test_technical_missing_H1_is_blocked_not_a_domain_failure(current_history):
    path = current_history
    value = load_document(path)
    h1 = path.parent / value['members'][0]['numerical_receipt']['path']
    h1.unlink()
    report = validate_model_verification(path, project_root=path.parent, require_reviewed=True)
    assert not report['assessment_ready']
    with pytest.raises(ValueError, match='blocked'):
        run_model_verification(path, path.parent / 'technical-failure', project_root=path.parent)


def test_consumer_rejects_rehashed_fake_result(current_history):
    path = current_history
    receipt_path = path.parent / 'baseline-assessment' / 'model-verification-receipt.json'
    numeric_path = receipt_path.parent / RESULT_NAME
    actual = load_document(numeric_path)
    actual['assessment']['claims'][0]['analyses'][0]['rows'][1]['finite_difference'] += 0.1
    write_json(numeric_path, actual)
    receipt = load_document(receipt_path)
    receipt['artifacts']['result']['sha256'] = sha256_file(numeric_path)
    write_json(receipt_path, receipt)
    report = validate_model_verification_receipt(receipt_path, project_root=path.parent)
    assert not report['valid'] and not report['model_verification_decided']
    assert any('recomputed' in error for error in report['errors'])


def test_member_and_result_budget_cannot_truncate_failure_points(current_history):
    path = current_history
    value = load_document(path)
    value['budget']['max_samples_per_output'] = 2
    write_contract(path, value)
    review_model_verification(path)
    report = validate_model_verification(path, project_root=path.parent, require_reviewed=True)
    assert not report['valid'] and not report['assessment_ready']
    assert any('sample budget' in error for error in report['errors'])


def test_present_H1_null_budget_draft_remains_valid_but_unready(current_history):
    value = load_document(current_history)
    value['budget'] = None
    write_contract(current_history, value)
    review_model_verification(current_history)
    value = load_document(current_history)
    value.update(status='draft', review_record=None)
    write_contract(current_history, value)
    before = {path: path.read_bytes() for path in current_history.parent.rglob('*') if path.is_file()}

    report = validate_model_verification(current_history, project_root=current_history.parent)

    assert report['schema_valid'] and report['valid'], report['errors']
    assert report['primary_numerical_receipt_path'] and len(report['_members']) == 2
    assert report['budget'] is None and 'reviewed_input_budget' in report['missing_gates']
    assert not report['reviewed'] and not report['assessment_ready']
    assert not report['environment_checked'] and not report['execution_allowed']
    assert all(path.read_bytes() == content for path, content in before.items())


def metric_member(value, *, level=1.0):
    return {'protocol_report': {'run_spec': {'inputs': [{'port': 1, 'variable_id': 'u', 'unit': '1', 'values': [level, level]}],
             'metrics': [{'output_port': 1, 'statistic': 'final', 'unit': '1'}]}},
            'data': {'outputs': [{'port': 1, 'unit': '1', 'values': [0.0, value]}]}}


def finite_value(kind='sensitivity'):
    analyses = [omitted(item) for item in KINDS]
    item = analyses[KINDS.index(kind)]
    item.update(requirement='required', method={'sensitivity': 'external_input_oat', 'robustness': 'finite_scenarios',
        'solver_comparison': 'solver_metrics', 'model_comparison': 'structural_metrics'}[kind], member_ids=['primary', 'other'],
        metric={'statistic': 'final', 'unit': '1', 'primary_output_port': 1,
                'member_output_ports': [{'member_id': 'other', 'output_port': 1}]})
    if kind == 'sensitivity':
        item.update(factor={'input_port': 1, 'variable_id': 'u', 'unit': '1', 'levels': [1.0, 2.0]},
                    bounds={'lower': 0.0, 'upper': 2.0, 'unit': '1/1'})
    elif kind == 'robustness':
        item['bounds'] = {'lower': 0.0, 'upper': 2.0, 'unit': '1'}
    else:
        item['comparison'] = {'absolute_tolerance': 0.1, 'relative_tolerance': 0.0}
    return {'claims': [{'id': 'claim', 'target_claim': 'Synthetic finite response only', 'analyses': analyses,
            'failure_disposition': 'reject', 'impact_scope': 'finite catalog', 'required_action': 'review',
            'return_stage': 'H', 'claim_limit': 'No physical truth'}], 'claim_limit': 'Synthetic arithmetic only'}


def test_zero_primary_keeps_relative_response_undefined():
    result = compute_assessment(finite_value(), {'primary': metric_member(0.0), 'other': metric_member(1.0, level=2.0)})
    rows = result['claims'][0]['analyses'][0]['rows']
    assert rows[0]['finite_difference'] is None
    assert rows[0]['relative_difference'] is None and rows[1]['relative_difference'] is None
    assert rows[1]['finite_difference'] == 1.0 and result['claim_supported']


@pytest.mark.parametrize('kind', ['solver_comparison', 'model_comparison'])
def test_comparison_uses_declared_metric_not_sampling_indices(kind):
    result = compute_assessment(finite_value(kind), {'primary': metric_member(1.0), 'other': metric_member(1.1)})
    row = result['claims'][0]['analyses'][KINDS.index(kind)]['rows'][1]
    assert row['absolute_difference'] == pytest.approx(0.1)
    assert row['tolerance'] == 0.1
    # Binary64 1.1 - 1 is just above 0.1; exact predeclared boundary is retained.
    assert not row['passed'] and not result['model_verified']


def test_overflow_is_technical_failure_not_support():
    with pytest.raises(ValueError, match='overflow'):
        compute_assessment(finite_value('solver_comparison'), {'primary': metric_member(1e308), 'other': metric_member(-1e308)})


@pytest.mark.parametrize('value', [True, '1', float('inf')])
def test_typed_result_comparison_never_coerces_fake_numbers(value):
    assert not typed_equal({'metric': value}, {'metric': 1.0})


def test_source_and_result_snapshot_preserve_integer_float_types():
    assert not typed_equal({'port': 1}, {'port': 1.0})


def test_model_order_needs_actual_state_dimension_not_label(tmp_path):
    from model_verification_common import structural_snapshot
    first = {'body': {'variables': [{'id': 'x', 'roles': ['state']}], 'initial_conditions': {}, 'boundary_conditions': {}}, 'fidelity': {'order': 'one'}}
    second = copy.deepcopy(first)
    second['fidelity']['order'] = 'two descriptive words'
    def member(name, model):
        path = write_contract(tmp_path / (name + '.json'), {'designs': [{'id': 'd', 'models': [{'id': 'm', **model}]}]})
        return {'protocol_report': {'model_path': str(path), 'design_id': 'd', 'model_id': 'm'},
                'protocol': {'conditions': {}}}
    review = {'difference_kind': 'model_order', 'primary_selector': ['fidelity', 'order'], 'member_selector': ['fidelity', 'order'],
              'rationale': 'Synthetic false label', 'equivalence_review': 'material_change_not_rename_or_equivalent_reformulation',
              'physical_target': 'same synthetic target'}
    with pytest.raises(ValueError, match='different state dimension'):
        structural_snapshot(review, member('one', first), member('two', second))



def baseline_receipt(path):
    return path.parent / 'baseline-assessment' / 'model-verification-receipt.json'


def rehash_result(receipt_path):
    receipt = load_document(receipt_path)
    receipt['artifacts']['result']['sha256'] = sha256_file(receipt_path.parent / RESULT_NAME)
    write_json(receipt_path, receipt)


def test_rehashed_numeric_type_substitution_fails_actual_recomputation(current_history):
    receipt = baseline_receipt(current_history)
    stored = load_document(receipt.parent / RESULT_NAME)
    row = stored['assessment']['claims'][0]['analyses'][0]['rows'][0]
    assert type(row['difference']) is float and row['difference'] == 0.0
    row['difference'] = 0
    write_json(receipt.parent / RESULT_NAME, stored)
    rehash_result(receipt)
    report = validate_model_verification_receipt(receipt, project_root=current_history.parent)
    assert not report['valid']
    assert any('independently recomputed' in error for error in report['errors'])


def test_actual_settings_snapshot_type_change_is_not_hidden_by_new_review(current_history):
    value = load_document(current_history)
    value['claims'][0]['analyses'][0]['factor']['levels'][0] = 1
    write_contract(current_history, value)
    review_model_verification(current_history, refresh_settings=False, refresh_obligations=False)
    report = validate_model_verification(current_history, project_root=current_history.parent, require_reviewed=True)
    assert not report['valid']
    assert any('complete typed source snapshot differs' in error for error in report['errors'])


@pytest.mark.parametrize('field', ['primary', 'member', 'factor'])
def test_equivalent_float_port_fails_even_with_source_and_review_rebound(current_history, field):
    value = load_document(current_history)
    analysis = value['claims'][0]['analyses'][0]
    if field == 'primary':
        analysis['metric']['primary_output_port'] = 1.0
    elif field == 'member':
        analysis['metric']['member_output_ports'][0]['output_port'] = 1.0
    else:
        analysis['factor']['input_port'] = 1.0
    write_contract(current_history, value)
    review_model_verification(current_history)
    report = validate_model_verification(current_history, project_root=current_history.parent, require_reviewed=True)
    assert not report['valid']
    assert any('actual integers' in error for error in report['errors'])


@pytest.mark.parametrize('artifact', ['receipt', 'input', 'result'])
def test_own_H2_artifact_mutation_mid_compute_cannot_return_valid(current_history, monkeypatch, artifact):
    receipt = baseline_receipt(current_history)
    target = {'receipt': receipt, 'input': receipt.parent / INPUT_NAME, 'result': receipt.parent / RESULT_NAME}[artifact]
    original = receipt_consumer.compute_assessment
    def mutate_after_parse(*args, **kwargs):
        answer = original(*args, **kwargs)
        target.write_bytes(target.read_bytes() + b' ')
        return answer
    monkeypatch.setattr(receipt_consumer, 'compute_assessment', mutate_after_parse)
    report = validate_model_verification_receipt(receipt, project_root=current_history.parent)
    assert not report['valid'] and not report['model_verification_decided']
    assert any('changed during assessment' in error for error in report['errors'])


def test_oversized_result_is_rejected_before_hash_or_load(current_history, monkeypatch):
    receipt = baseline_receipt(current_history)
    target = receipt.parent / RESULT_NAME
    with target.open('wb') as stream:
        stream.truncate(67108865)
    original_hash = shared_readers.sha256_file
    original_load = shared_readers.limited_document
    def safe_hash(path):
        assert Path(path).resolve() != target, 'oversized file was hashed before budget rejection'
        return original_hash(path)
    def safe_load(path, *args, **kwargs):
        assert Path(path).resolve() != target, 'oversized file was loaded before budget rejection'
        return original_load(path, *args, **kwargs)
    monkeypatch.setattr(shared_readers, 'sha256_file', safe_hash)
    monkeypatch.setattr(receipt_consumer, 'sha256_file', safe_hash)
    monkeypatch.setattr(shared_readers, 'limited_document', safe_load)
    monkeypatch.setattr(receipt_consumer, 'limited_document', safe_load)
    report = validate_model_verification_receipt(receipt, project_root=current_history.parent)
    assert not report['valid'] and any('budget' in error for error in report['errors'])


def test_aggregate_budget_includes_own_H2_artifacts(current_history):
    path, root = current_history, current_history.parent
    receipt = baseline_receipt(path)
    request = load_document(receipt.parent / INPUT_NAME)
    value = load_document(path)
    upstream_bytes = sum(item['bytes'] for item in request['input_manifest'])
    own_sizes = [file.stat().st_size for file in (receipt, receipt.parent / INPUT_NAME, receipt.parent / RESULT_NAME)]
    value['budget']['max_file_bytes'] = max([item['bytes'] for item in request['input_manifest']] + own_sizes)
    assert upstream_bytes + sum(own_sizes) > upstream_bytes
    value['budget']['max_total_bytes'] = upstream_bytes
    write_contract(path, value)
    review_model_verification(path)
    report = validate_model_verification_receipt(receipt, project_root=root)
    assert not report['valid'] and any('byte budget' in error for error in report['errors'])


@pytest.mark.parametrize('offset,expected_complete', [(-1, False), (0, True)])
def test_exact_written_result_byte_boundary(current_history, offset, expected_complete):
    path, root = current_history, current_history.parent
    size = (baseline_receipt(path).parent / RESULT_NAME).stat().st_size
    value = load_document(path)
    value['budget']['max_result_bytes'] = size + offset
    write_contract(path, value)
    review_model_verification(path)
    report = run_model_verification(path, root / 'exact-result-budget', project_root=root)
    receipt = load_document(root / 'exact-result-budget' / 'model-verification-receipt.json')
    assert receipt['assessment_complete'] is expected_complete
    assert report['valid'] is expected_complete
    if expected_complete:
        assert (root / 'exact-result-budget' / RESULT_NAME).stat().st_size == size
    else:
        stored = load_document(root / 'exact-result-budget' / RESULT_NAME)
        assert stored['assessment'] is None and any('result byte budget' in error for error in stored['errors'])


def model_member(tmp_path, name, *, expression='dx/dt = u - x', role='governing', state='x', extra_state=False):
    variables = [{'id': state, 'symbol': state, 'quantity': 'response', 'roles': ['state'], 'unit': '1'},
                 {'id': 'u', 'symbol': 'u', 'quantity': 'external input', 'roles': ['commanded_input'], 'unit': '1'}]
    if extra_state:
        variables.append({'id': 'z', 'symbol': 'z', 'quantity': 'second response', 'roles': ['state'], 'unit': '1'})
    body = {'variables': variables, 'relations': [{'id': name + '-relation', 'expression': expression,
            'variable_ids': [state, 'u'], 'requirement_ids': [name + '-requirement'], 'role': role}],
            'initial_conditions': {}, 'boundary_conditions': {}}
    contract = {'designs': [{'id': 'd', 'models': [{'id': 'm', 'body': body, 'fidelity': {'order': 'two' if extra_state else 'one'}}]}]}
    path = write_contract(tmp_path / (name + '.json'), contract)
    return {'protocol_report': {'model_path': str(path), 'design_id': 'd', 'model_id': 'm'}, 'protocol': {'conditions': {}}}


def structure_review(kind, selector):
    return {'difference_kind': kind, 'primary_selector': selector, 'member_selector': selector,
            'rationale': 'Synthetic registered mechanism comparison; not reality evidence',
            'equivalence_review': 'material_change_not_rename_or_equivalent_reformulation', 'physical_target': 'same target'}


@pytest.mark.parametrize('selector', [['body', 'relations', 0, 'id'], ['body', 'relations', 0, 'requirement_ids']])
def test_identifiers_and_requirement_refs_are_not_mathematical_anchors(tmp_path, selector):
    with pytest.raises(ValueError, match='not a mathematical anchor'):
        structural_snapshot(structure_review('governing_equations', selector), model_member(tmp_path, 'one'), model_member(tmp_path, 'two'))


def test_output_relation_cannot_stand_in_for_governing_comparator(tmp_path):
    with pytest.raises(ValueError, match='role is unrelated'):
        structural_snapshot(structure_review('governing_equations', ['body', 'relations', 0]),
            model_member(tmp_path, 'one'), model_member(tmp_path, 'two', role='output', expression='y = x'))


def test_relation_and_variable_rename_only_are_rejected(tmp_path):
    with pytest.raises(ValueError, match='no substantive mathematical difference'):
        structural_snapshot(structure_review('governing_equations', ['body', 'relations', 0]),
            model_member(tmp_path, 'one'), model_member(tmp_path, 'two', state='renamed', expression='drenamed/dt = u - renamed'))


def test_real_one_state_two_state_anchor_remains_admissible(tmp_path):
    result = structural_snapshot(structure_review('model_order', ['body', 'variables']),
        model_member(tmp_path, 'one'), model_member(tmp_path, 'two', extra_state=True))
    assert len(result['primary_value']) == 2 and len(result['member_value']) == 3


def test_same_model_analyses_reject_upstream_identity_change_with_equal_run_spec(current_history):
    # Exercise the refusal branch directly: a new H1/E producer history is unnecessary
    # when only one already-consumed upstream identity changes in this internal input.
    root = current_history.parent
    model = model_member(root, 'same-model-control')
    model_path = Path(model['protocol_report']['model_path'])
    alternate_model = root / 'same-model-identical-body.json'
    alternate_model.write_bytes(model_path.read_bytes())
    upstream_keys = ('model_path', 'model_sha256', 'mapping_path', 'mapping_sha256',
                     'approval_path', 'approval_sha256', 'parameters_path', 'parameters_sha256',
                     'problem_path', 'problem_sha256', 'model_identity')
    primary = metric_member(1.0)
    primary['protocol_report'].update(model['protocol_report'])
    primary['protocol_report'].update({key: str(model_path) if key.endswith('_path') else sha256_file(model_path)
                                       for key in upstream_keys})
    spec = primary['protocol_report']['run_spec']
    spec['inputs'][0].update(time=[0.0, 1.0], interpolation='zoh')
    spec.update(outputs=[{'port': 1, 'variable_id': 'x', 'unit': '1'}], solver={'name': 'ode4'})
    primary['protocol'] = {'conditions': {}, 'logging': {}, 'selection': {'design_id': 'd', 'model_id': 'm'}}
    expected_errors = {'sensitivity': 'beyond single constant external-input OAT',
                       'robustness': 'finite scenarios change approved model/parameters/conditions',
                       'solver_comparison': 'solver comparison changes nonnumerical settings'}

    for kind, expected_error in expected_errors.items():
        value = finite_value(kind)
        claim = value['claims'][0]
        analysis = claim['analyses'][KINDS.index(kind)]
        other = copy.deepcopy(primary)
        if kind == 'solver_comparison':
            other['protocol_report']['run_spec']['solver']['name'] = 'ode45'
        else:
            other['protocol_report']['run_spec']['inputs'][0]['values'] = [2.0, 2.0]
        control = {'errors': [], 'missing_gates': [], 'required_analysis_kinds': []}
        _analysis(analysis, claim, {'primary': primary, 'other': other}, {}, root, control)
        assert not control['errors'] and not control['missing_gates'], (kind, control)

        for key in upstream_keys:
            changed = copy.deepcopy(other)
            changed['protocol_report'][key] = str(alternate_model) if key.endswith('_path') else 'b' * 64
            assert changed['protocol_report']['run_spec'] == other['protocol_report']['run_spec']
            result = {'errors': [], 'missing_gates': [], 'required_analysis_kinds': []}
            _analysis(analysis, claim, {'primary': primary, 'other': changed}, {}, root, result)
            assert any(expected_error in error for error in result['errors']), (kind, key, result)
