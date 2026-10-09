"""Owner boundary checks; patched E histories are not native qualification."""
import copy
from pathlib import Path

import pytest

from test_verification import binding, h1_plan, numerical_analysis, reviewed, run_and_ref
from runtime_common import ROOT, load_document, sha256_file
from probe_environment import write_json
from run_verification import run_verification
from validate_verification import validate_verification
from validate_verification_receipt import validate_verification_receipt
from verification_common import analytic_values, Budget


def h2_fixture(root, monkeypatch):
    import verification_analysis
    h1_path, h1 = h1_plan(root)
    base, reference = run_and_ref(root / 'upstream')
    reference['atol'], reference['rtol'] = .01, 0
    base.update(project_id=h1['project_id'], actual={'observed_solver_info': {'Solver': 'ode4'}},
                outputs=[{'port': 1, 'unit': '1', 'time': [0, 1], 'values': analytic_values(base, reference, [0, 1])}])
    other_path = root / 'synthetic-e-second.json'
    write_json(other_path, {'notice': 'owner patched E infrastructure only'})
    identities = [h1['primary'], binding(other_path)]
    runs = {}
    h1['runs'] = []
    for index, receipt in enumerate(identities):
        run = copy.deepcopy(base)
        run.update(receipt=receipt, run_id=f'owner-{index}')
        if index:
            run['protocol']['solver'].update(name='ode45', type='variable-step', fixed_step=None, max_step=.05,
                min_step=1e-12, initial_step=.01, rel_tol=1e-6, abs_tol=1e-8)
            run['actual']['observed_solver_info']['Solver'] = 'ode45'
            run['outputs'][0]['values'][-1] += .0001
        runs[str(Path(receipt['path']).resolve())] = run
        h1['runs'].append({'id': f'r{index}', 'receipt': receipt, 'h1_receipt': None, 'references': [reference]})
    monkeypatch.setattr(verification_analysis, 'read_run', lambda b, *args: copy.deepcopy(runs[str(Path(b['path']).resolve())]))
    reviewed(h1_path, h1)
    h1_result = run_verification(h1_path, root / 'h1-evidence', project_root=root, kind='H1')
    assert h1_result['valid'], h1_result['errors']
    plan = load_document(ROOT / 'templates/contracts/model_verification.yaml')
    analysis = numerical_analysis('solver_final_comparison', ['r0', 'r1'])
    plan.update(project_id=h1['project_id'], primary=identities[0], sources=h1['sources'],
        requirements=[{'id': 'solver', 'method': 'solver_final_comparison', 'required': True, 'reason': 'finite comparison', 'source_ids': ['reference']}],
        runs=[{'id': f'r{i}', 'receipt': r, 'h1_receipt': binding(h1_result['receipt_path']), 'references': []} for i, r in enumerate(identities)],
        analyses=[analysis], material_results=[{'id': 'claim', 'target_claim': 'finite terminal agreement',
            'domain': {'kind': 'terminal_pair', 'description': 'two declared continuous methods'},
            'model_comparison_requirement': 'not_applicable',
            'triggers': dict.fromkeys(['structural_uncertainty', 'multiple_fidelities', 'data_and_mechanistic',
                'simplification_changes_claim', 'user_required', 'structural_stability_claim'], False),
            'reason': 'fixed governing mechanism; numerical method claim only', 'source_ids': ['reference'], 'analysis_ids': ['compare']}])
    path = reviewed(root / 'h2.json', plan)
    return path, plan, runs, h1_result


@pytest.mark.parametrize('threshold,verified', [(.01, True), (.00001, False)])
def test_h2_complete_rejection_is_decided_without_claim_verification(tmp_path, monkeypatch, threshold, verified):
    path, plan, _, _ = h2_fixture(tmp_path, monkeypatch)
    plan['analyses'][0]['threshold'] = threshold
    reviewed(path, plan)
    generated = run_verification(path, tmp_path / 'h2-evidence', project_root=tmp_path, kind='H2')
    checked = validate_verification_receipt(generated['receipt_path'], project_root=tmp_path, kind='H2')
    assert checked['valid'] and checked['evidence_complete'] and checked['model_verification_decided'], checked['errors']
    assert checked['model_verified'] is verified
    assert (checked['analyses'][0]['required_action'] is None) is verified
    from verification_state import enforce_stage
    errors = []
    state_result = {**checked, 'numerically_verified': True}
    enforce_stage({'current_stage': 'MODEL_VERIFICATION_DECIDED'}, state_result, errors, 'model_verification')
    assert not errors
    enforce_stage({'current_stage': 'MODEL_VERIFIED'}, state_result, errors, 'model_verification')
    assert bool(errors) is not verified


def test_material_trigger_and_required_structural_work_cannot_be_NA(tmp_path, monkeypatch):
    path, plan, _, _ = h2_fixture(tmp_path, monkeypatch)
    plan['material_results'][0]['triggers']['user_required'] = True
    reviewed(path, plan)
    assert not validate_verification(path)['valid']
    plan['material_results'][0]['model_comparison_requirement'] = 'required'
    reviewed(path, plan)
    result = validate_verification(path)
    assert not result['reviewed'] and 'required_structural_comparison:claim' in result['missing_gates']


@pytest.mark.parametrize('failure', ['missing_coverage', 'technical', 'H1_error'])
def test_h2_individual_coverage_failure_preserves_partial_without_summary(tmp_path, monkeypatch, failure):
    import verification_analysis
    path, plan, runs, h1_result = h2_fixture(tmp_path, monkeypatch)
    if failure == 'missing_coverage':
        import validate_verification_receipt as consumer
        real = consumer.validate_verification_receipt
        def incomplete(*args, **kwargs):
            checked = real(*args, **kwargs)
            checked['ledger'] = checked['ledger'][:1]
            return checked
        monkeypatch.setattr(consumer, 'validate_verification_receipt', incomplete)
    else:
        original = verification_analysis.read_run
        calls = {'n': 0}
        def damaged(binding, *args):
            calls['n'] += 1
            # First two calls recompute H1; next two read actual H2 rows.
            if failure == 'technical' and calls['n'] == 4:
                raise ValueError('owner controlled E technical failure')
            run = original(binding, *args)
            if failure == 'H1_error' and calls['n'] == 2:
                run['outputs'][0]['values'][-1] += 1
            return run
        monkeypatch.setattr(verification_analysis, 'read_run', damaged)
    checked = verification_analysis.analyze(path, project_root=tmp_path, kind='H2')
    assert not checked['valid'] and not checked['evidence_complete'] and checked['summary'] is None
    assert any(r['status'] == 'failed' for r in checked['ledger'])
    if failure == 'technical':
        assert [r['status'] for r in checked['ledger']] == ['completed', 'failed']
    elif failure == 'H1_error':
        assert [r['status'] for r in checked['ledger']] == ['failed', 'not_attempted']


def test_history_source_drift_invalidates_rehashed_H_receipt(tmp_path, monkeypatch):
    path, plan, _, h1_result = h2_fixture(tmp_path, monkeypatch)
    Path(plan['sources'][0]['path']).write_text('changed independent source', encoding='utf-8')
    result = validate_verification_receipt(h1_result['receipt_path'], project_root=tmp_path)
    assert not result['valid'] and not result['numerically_verified']


@pytest.mark.parametrize('intent', ['numerical_verification', 'sensitivity_analysis', 'robustness_analysis', 'model_comparison', 'solver_comparison', 'model_verification_review'])
def test_H_route_selects_no_native_operations_or_profiles(intent):
    from resolve_runtime import resolve_runtime
    result = resolve_runtime(intent)
    assert result['phase'] == 'H' and result['status'] == 'inspected', result['errors']
    assert result['selected_operations'] == [] and not result['execution_allowed'] and not result['business_execution_allowed']
    assert not result['state_mutated'] and result['profile_sha256'] is None
    blocked = resolve_runtime(intent, required_operations=['matlab.basic_execution'])
    assert blocked['status'] == 'blocked' and not blocked['execution_allowed']


def test_H_state_primary_bundle_and_current_runtime_are_separate(tmp_path, monkeypatch):
    import validate_verification_receipt as consumer
    from verification_state import validate_bindings, primary_errors, validate_artifact
    files = {}
    for name in ['problem', 'model', 'approval', 'mapping', 'protocol', 'primary_run', 'h1', 'h2']:
        p = tmp_path / (name + '.json')
        write_json(p, {'synthetic': name})
        files[name] = binding(p)
    state = {**{k: files[k] for k in ['problem', 'model', 'approval', 'mapping', 'protocol', 'primary_run']},
        'project_id': 'owner', 'current_stage': 'MODEL_VERIFICATION_DECIDED',
        'numerical_verification': files['h1'], 'model_verification': files['h2']}
    report = {'valid': True, 'errors': [], 'project_id': 'owner', 'evidence_complete': True,
        'numerically_verified': True, 'model_verification_decided': True, 'model_verified': False,
        'primary_receipt': files['primary_run'], 'primary_protocol': files['protocol'],
        'primary_upstream': {k: files[k] for k in ['problem', 'model', 'approval', 'mapping']},
        'ledger': [{'independent_second_model_C': 'separate bundle identity'}]}
    monkeypatch.setattr(consumer, 'validate_verification_receipt', lambda *args, **kw: copy.deepcopy(report))
    result = {'implementation_ready': True, 'primary_run_complete': True}
    errors, stale = [], set()
    validate_bindings(state, tmp_path, result, errors, stale, 'model_verification')
    assert not errors and result['model_verification_decided'] and not result['model_verified']
    assert 'environment_checked' not in result
    earlier = {}
    validate_bindings(state, tmp_path, earlier, [], set(), 'model')
    assert not earlier['numerical_verification_checked'] and not earlier['model_verification_checked']
    wrong = copy.deepcopy(report)
    wrong['primary_upstream']['model'] = files['problem']
    assert primary_errors(wrong, state, tmp_path, result)
    artifact = {'id': 'h2-artifact', 'role': 'model_verification', 'path': files['h2']['path'],
        'sha256': files['h2']['sha256'], 'depends_on': list(state.keys())}
    assert any('current runtime' in e for e in validate_artifact(artifact, state=state, result=result, root=tmp_path,
        environment_dependents={'h2-artifact'}, ancestor_roles=lambda _: {'simulation_run', 'simulation_protocol', 'numerical_verification'}))


def test_H2_nested_model_budget(tmp_path, monkeypatch):
    import verification_analysis
    path, _, _, _ = h2_fixture(tmp_path, monkeypatch)
    budget = Budget()
    budget.model_ids.update({('extra1', 'design', 'model'), ('extra2', 'design', 'model')})
    result = verification_analysis.analyze(path, project_root=tmp_path, kind='H2', budget=budget)
    assert not result['valid'] and any('model budget' in e for e in result['errors'])


def test_finite_campaign_requires_ordered_receipts_complete_domain_and_total_budget(tmp_path, monkeypatch):
    import validate_experiment_receipt as consumer
    from verification_analysis import campaign_response
    monkeypatch.setattr(consumer, 'validate_experiment_receipt', lambda *a, **k:
        {'valid': True, 'errors': [], 'campaign_complete': True, 'method': 'monte_carlo_catalog'})
    campaign = tmp_path / 'campaign.json'
    write_json(campaign, {'notice': 'owner mocked G history only'})
    run, _ = run_and_ref(tmp_path / 'upstream')
    runs = {}
    rows = []
    for i in range(2):
        r = copy.deepcopy(run)
        e = tmp_path / f'e{i}.json'
        write_json(e, {'owner': i})
        r.update(receipt=binding(e), run_id=f'owner-{i}', outputs=[{'port': 1, 'unit': '1', 'time': [0, 1], 'values': [.25, 1.0]}])
        runs[f'r{i}'] = r
        rows.append({'receipt': binding(e)})
    write_json(tmp_path / 'campaign-ledger.json', {'rows': rows})
    analysis = numerical_analysis('scenario_response', ['r0', 'r1'])
    analysis.update(campaign=binding(campaign), output_ports=[1], threshold=2)
    claim = {'claim': {'domain': {'kind': 'actual_draws'}}}
    runs['r1']['protocol_report']['contract_path'] = 'different-independent-frozen-protocol'
    runs['r1']['protocol_report']['contract_sha256'] = '0' * 64
    shared_scenario_budget = Budget()
    assert campaign_response(analysis, runs, claim, tmp_path, shared_scenario_budget)['passed']
    assert len(shared_scenario_budget.scenario_ids) == 1
    claim['claim']['domain']['kind'] = 'complete_catalog'
    with pytest.raises(ValueError, match='does not cover'):
        campaign_response(analysis, runs, claim, tmp_path, Budget())
    analysis['method'] = 'finite_domain_robustness'
    with pytest.raises(ValueError, match='MC draws'):
        campaign_response(analysis, runs, claim, tmp_path, Budget())
    monkeypatch.setattr(consumer, 'validate_experiment_receipt', lambda *a, **k:
        {'valid': True, 'errors': [], 'campaign_complete': True, 'method': 'scenario_matrix'})
    assert campaign_response(analysis, runs, claim, tmp_path, Budget())['passed']
    budget = Budget()
    budget.scenario_ids.update((str(i), str(i)) for i in range(16))
    with pytest.raises(ValueError, match='total finite scenario budget'):
        campaign_response(analysis, runs, claim, tmp_path, budget)
    write_json(tmp_path / 'campaign-ledger.json', {'rows': rows[::-1]})
    with pytest.raises(ValueError, match='exact ordered'):
        campaign_response(analysis, runs, claim, tmp_path, Budget())


def test_structural_identity_change_cannot_replace_material_mechanism_review(tmp_path):
    from verification_analysis import comparison
    left, _ = run_and_ref(tmp_path)
    right = copy.deepcopy(left)
    right['protocol_report']['model_sha256'] = '0' * 64
    for run in (left, right):
        run['outputs'] = [{'port': 1, 'unit': '1', 'time': [0, 1], 'values': [.25, 1]}]
    analysis = numerical_analysis('structural_final_comparison', ['left', 'right'])
    analysis['solver_changes'] = []
    analysis['structural_review'] = {'source_ids': ['reference'], 'left_relation_ids': ['kernel'],
        'right_relation_ids': ['kernel'], 'material_difference': 'mechanism', 'physical_conditions_mapping': 'reviewed common physical input',
        'reason': 'owner negative: renaming only is insufficient'}
    with pytest.raises(ValueError, match='material|static/first-order'):
        comparison(analysis, {'left': left, 'right': right}, {'claim': {'domain': {'kind': 'terminal_pair'}}})
    analysis['structural_review']['right_relation_ids'] = ['invented']
    with pytest.raises(ValueError, match='relations'):
        comparison(analysis, {'left': left, 'right': right}, {'claim': {'domain': {'kind': 'terminal_pair'}}})


def test_H_scope_consumes_E_history_without_current_TTL_and_propagates_stale(tmp_path, monkeypatch):
    import validate_verification_receipt as consumer
    from test_simulation_routing_state import complete_state
    from validate_project_state import validate_project_state
    state_path, _ = complete_state(tmp_path, age_hours=25)
    state = load_document(state_path)
    h1 = tmp_path / 'owner-patched-H1.json'
    write_json(h1, {'notice': 'synthetic state infrastructure, H consumer patched'})
    state.update(current_stage='NUMERICALLY_VERIFIED', numerical_verification=binding(h1))
    report = {'valid': True, 'errors': [], 'project_id': state['project_id'], 'evidence_complete': True,
        'numerically_verified': True, 'primary_receipt': state['primary_run'], 'primary_protocol': state['protocol'],
        'primary_upstream': {k: state[k] for k in ['problem', 'model', 'approval', 'mapping']}}
    monkeypatch.setattr(consumer, 'validate_verification_receipt', lambda *a, **k: copy.deepcopy(report))
    run = next(a for a in state['artefacts'] if a['role'] == 'simulation_run')
    state['artefacts'].append({'id': 'H1-record', 'role': 'numerical_verification', 'path': str(h1),
        'sha256': sha256_file(h1), 'status': 'accepted',
        'depends_on': ['problem', 'model', 'approval', 'mapping', 'protocol', 'primary_run', 'numerical_verification', run['id']]})
    write_json(state_path, state)
    before = state_path.read_bytes()
    checked = validate_project_state(state_path, scope='numerical_verification')
    assert checked['valid'] and checked['numerically_verified'], checked['errors']
    assert not checked['environment_checked'] and not checked['simulation_environment_checked']
    assert state_path.read_bytes() == before
    run['status'] = 'stale'
    write_json(state_path, state)
    checked = validate_project_state(state_path, scope='numerical_verification')
    assert not checked['valid'] and not checked['numerically_verified'] and 'H1-record' in checked['stale_artefacts']
    early = validate_project_state(state_path, scope='model')
    assert early['valid'] and not early['numerical_verification_checked'], early['errors']
