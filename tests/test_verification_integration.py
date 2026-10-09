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


def selected_e_fixture(directory, *, qualification=True):
    """Typed JSON boundary fixture; never represents native qualification."""
    directory.mkdir(parents=True, exist_ok=True)
    run_id = 'owner-' + directory.name
    output = {'port': 1, 'unit': '1', 'time': list(range(5)), 'values': [1.0] * 5}
    request = {'run_id': run_id, 'mode': 'primary', 'cases': [{'case_id': 'primary'}], 'bindings': {}}
    qualified_raw = None
    if qualification:
        folder = directory.parent / ('qualification-' + directory.name)
        folder.mkdir()
        qualified_raw = folder / 'raw-simulation.json'
        large = {'port': 1, 'time': list(range(3645)), 'values': [1.0] * 3645}
        write_json(qualified_raw, {'cases': [{'case_id': 'early_stop', 'outputs': [large]},
            {'case_id': 'multiple_outputs', 'outputs': [output] * 3}]})
        profile = folder / 'simulation-profile.json'
        write_json(profile, {'artifacts': {'raw': {'file': qualified_raw.name, 'sha256': sha256_file(qualified_raw)}}})
        request['bindings']['simulation_profile'] = binding(profile)
    write_json(directory / 'simulation-inputs.json', request)
    write_json(directory / 'primary-outputs.json', {'run_id': run_id, 'outputs': [output]})
    write_json(directory / 'raw-simulation.json', {'run_id': run_id,
        'cases': [{'case_id': 'primary', 'data_file': 'primary-outputs.json', 'outputs': [output]}]})
    receipt = directory / 'simulation-receipt.json'
    refresh_e_fixture(receipt, run_id)
    return receipt, qualified_raw


def refresh_e_fixture(receipt, run_id=None):
    old = load_document(receipt) if receipt.exists() else {'run_id': run_id}
    old['artifacts'] = {role: {'file': name, 'sha256': sha256_file(receipt.parent / name)}
        for role, name in [('input', 'simulation-inputs.json'), ('raw', 'raw-simulation.json'), ('data', 'primary-outputs.json')]}
    write_json(receipt, old)


def campaign_fixture(directory, rows):
    from run_experiment import artifact_manifest, LEDGER, RECEIPT
    write_json(directory / LEDGER, {'rows': rows})
    sample = directory / 'sampling' / 'sample-receipt.json'
    sample.parent.mkdir(exist_ok=True)
    write_json(sample, {'notice': 'owner sampling binding boundary only'})
    path = directory / RECEIPT
    write_json(path, {'rows': rows, 'sampling_receipt': {'path': 'sampling/' + sample.name, 'sha256': sha256_file(sample)},
                     'artifacts': artifact_manifest(directory)})
    return path


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
    directory = tmp_path / 'campaign'
    directory.mkdir()
    run, _ = run_and_ref(tmp_path / 'upstream')
    runs = {}
    rows = []
    for i in range(2):
        r = copy.deepcopy(run)
        e, _ = selected_e_fixture(directory / f'draw-{i+1:03d}')
        r.update(receipt=binding(e), run_id=f'owner-{i}', outputs=[{'port': 1, 'unit': '1', 'time': [0, 1], 'values': [.25, 1.0]}])
        runs[f'r{i}'] = r
        rows.append({'status': 'completed', 'receipt': {'path': e.relative_to(directory).as_posix(), 'sha256': sha256_file(e)}})
    campaign = campaign_fixture(directory, rows)
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
    campaign = campaign_fixture(directory, rows[::-1])
    analysis['campaign'] = binding(campaign)
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


@pytest.mark.parametrize('challenge,eligible', [('non_equilibrium', True), ('linear_a_zero', True),
    ('zero_vector_field', False), ('equilibrium', False)])
def test_structural_gate_uses_exact_recomputed_H1_approved_reference_origins(tmp_path, monkeypatch, challenge, eligible):
    from verification_common import parameters
    path, plan, runs, _ = h2_fixture(tmp_path, monkeypatch)
    static, static_ref = run_and_ref(tmp_path / 'static-upstream', 'static')
    dynamic = runs[plan['runs'][1]['receipt']['path']]
    static.update(project_id=plan['project_id'], run_id='owner-0', receipt=plan['runs'][0]['receipt'],
        outputs=[{'port': 1, 'unit': '1', 'time': [0, 1], 'values': [2, 2]}])
    # Owner read_run fixture isolates H; both upstream identities are openly
    # synthetic. The same reviewed B/scenario maps separate model C/D graphs.
    static['protocol_report']['problem_sha256'] = dynamic['protocol_report']['problem_sha256']
    static['protocol']['scenario']['requirement_ids'] = dynamic['protocol']['scenario']['requirement_ids']
    runs[plan['runs'][0]['receipt']['path']] = static
    ps = parameters(dynamic)
    if challenge in {'linear_a_zero', 'zero_vector_field'}:
        ps['a']['value'] = 0
    if challenge == 'zero_vector_field':
        ps['b']['value'] = 0
    if not eligible:
        dynamic['model']['body']['initial_conditions']['value'] = {'x': 2}
        blocks = dynamic['protocol_report']['mapping_validation']['build_spec']['blocks']
        next(b for b in blocks if b['type'] == 'Integrator')['parameters']['InitialCondition'] = '2'
    h1_path = tmp_path / 'h1.json'
    h1 = load_document(h1_path)
    h1['runs'][0]['references'] = [static_ref]
    dynamic_ref = h1['runs'][1]['references'][0]
    dynamic['outputs'][0]['values'] = analytic_values(dynamic, dynamic_ref, [0, 1])
    reviewed(h1_path, h1)
    h1_result = run_verification(h1_path, tmp_path / 'structural-h1-evidence', project_root=tmp_path, kind='H1')
    checked_h1 = validate_verification_receipt(h1_result['receipt_path'], project_root=tmp_path, kind='H1')
    assert checked_h1['valid'] and checked_h1['numerically_verified'], checked_h1['errors']
    dynamic_metadata = checked_h1['ledger'][1]['verified_references'][0]
    assert dynamic_metadata['structural_eligible'] is eligible
    assert dynamic_metadata['approved_origins']['a']['reference']['variable_id'] == dynamic_ref['a_parameter']
    assert dynamic_metadata['approved_origins']['initial']['selector'] == dynamic_ref['initial_selector']
    assert dynamic_metadata['initial_derivative'] == (1.5 if challenge == 'linear_a_zero' else 1.3125 if eligible else 0)
    analysis = numerical_analysis('structural_final_comparison', ['r0', 'r1'])
    analysis.update(threshold=10, solver_changes=[], structural_review={'source_ids': ['reference'],
        'left_relation_ids': ['kernel'], 'right_relation_ids': ['kernel'], 'material_difference': 'mechanism',
        'physical_conditions_mapping': 'source-reviewed common physical input and terminal observable',
        'reason': 'owner comparison of algebraic and dynamic mechanisms; different states acknowledged'})
    plan['analyses'] = [analysis]
    plan['requirements'][0]['method'] = 'structural_final_comparison'
    plan['material_results'][0]['model_comparison_requirement'] = 'required'
    plan['material_results'][0]['triggers']['user_required'] = True
    for member in plan['runs']:
        member['h1_receipt'] = binding(h1_result['receipt_path'])
    reviewed(path, plan)
    generated = run_verification(path, tmp_path / 'structural-h2-evidence', project_root=tmp_path, kind='H2')
    checked = validate_verification_receipt(generated['receipt_path'], project_root=tmp_path, kind='H2')
    assert checked['valid'] is eligible and checked['model_verified'] is eligible, checked['errors']
    if eligible:
        assert checked['analyses'][0]['numeric']['reference_eligibility'][1] == dynamic_metadata
    else:
        assert not checked['evidence_complete'] and checked['summary'] is None
        assert any('nonzero approved initial derivative' in e for e in checked['errors'])
        assert plan['material_results'][0]['model_comparison_requirement'] == 'required'


def test_nested_receipt_and_plan_routes_preserve_verified_project_root(tmp_path, monkeypatch):
    import verification_analysis
    import subprocess
    import sys
    from resolve_runtime import resolve_runtime
    path, plan = h1_plan(tmp_path)
    run, _ = run_and_ref(tmp_path / 'upstream', 'constant')
    run.update(project_id=plan['project_id'], run_id='owner-nested', receipt=plan['primary'],
        outputs=[{'port': 1, 'unit': '1', 'time': [0, 1], 'values': [2, 2]}])
    monkeypatch.setattr(verification_analysis, 'read_run', lambda *a: copy.deepcopy(run))
    for bound in [plan['primary'], plan['runs'][0]['receipt'], *plan['sources']]:
        bound['path'] = Path(bound['path']).relative_to(tmp_path).as_posix()
    nested = tmp_path / 'plans' / 'reviewed-h1.json'
    nested.parent.mkdir()
    reviewed(nested, plan)
    generated = run_verification(nested, tmp_path / 'nested-evidence', project_root=tmp_path, kind='H1')
    checked = validate_verification_receipt(generated['receipt_path'], kind='H1')
    assert checked['valid'] and checked['project_root'] == str(tmp_path.resolve()), checked['errors']
    routed = resolve_runtime('numerical_verification', verification_receipt_path=generated['receipt_path'])
    assert routed['status'] == 'inspected' and not routed['execution_allowed'], routed['errors']
    direct = resolve_runtime('numerical_verification', verification_plan_path=nested, verification_project_root=tmp_path)
    assert direct['status'] == 'inspected' and direct['verification_plan_validation']['reviewed'], direct['errors']
    cli = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/resolve_runtime.py'), '--intent', 'numerical_verification',
        '--verification-plan', str(nested), '--verification-project-root', str(tmp_path)], capture_output=True, text=True)
    assert cli.returncode == 0 and '"status": "inspected"' in cli.stdout, cli.stderr + cli.stdout
    wrong = tmp_path / 'other-project'
    wrong.mkdir()
    mismatch = resolve_runtime('numerical_verification', verification_receipt_path=generated['receipt_path'], verification_project_root=wrong)
    assert mismatch['status'] == 'blocked' and any('root differs' in e for e in mismatch['errors'])
    mismatch = resolve_runtime('numerical_verification', verification_plan_path=nested, verification_project_root=wrong)
    assert mismatch['status'] == 'blocked' and any('leaves project root' in e for e in mismatch['errors'])
    state = wrong / 'state.json'
    write_json(state, {'schema_version': 1, 'project_id': plan['project_id'], 'project_root': '.',
        'current_stage': 'NEW', 'environment': None, 'artefacts': []})
    mismatch = resolve_runtime('numerical_verification', state_path=state, verification_plan_path=nested, verification_project_root=tmp_path)
    assert mismatch['status'] == 'blocked' and any('differs from state root' in e for e in mismatch['errors'])
    mismatch = resolve_runtime('numerical_verification', state_path=state, verification_receipt_path=generated['receipt_path'])
    assert mismatch['status'] == 'blocked' and any('root differs' in e for e in mismatch['errors'])


@pytest.mark.parametrize('method', ['strict_interruptible_deadline', 'decompressed_memory_guarantee'])
def test_stronger_required_resource_guarantees_are_blocked(tmp_path, method):
    path, plan = h1_plan(tmp_path)
    plan['requirements'].append({'id': 'resource', 'method': method, 'required': True,
        'reason': 'task requires stronger resource enforcement', 'source_ids': ['reference']})
    reviewed(path, plan)
    checked = validate_verification(path)
    assert not checked['valid'] and not checked['reviewed'] and f'unsupported_required:{method}' in checked['missing_gates']


def test_cooperative_timeout_blocks_after_E_consumer_returns_and_small_read_budget(tmp_path, monkeypatch):
    import verification_common
    import validate_simulation_receipt as consumer
    receipt = tmp_path / 'owner-E.json'
    write_json(receipt, {})
    budget, returned = Budget(), []
    monkeypatch.setattr(verification_common, 'preflight_e', lambda *a: None)
    monkeypatch.setattr(verification_common, 'preflight_selected_e', lambda *a: None)
    def blocking_boundary(*a, **k):
        budget.started -= 121  # Small clock fixture, no sleeping or native call.
        returned.append(True)
        return {'valid': True, 'primary_run_complete': True}
    monkeypatch.setattr(consumer, 'validate_simulation_receipt', blocking_boundary)
    with pytest.raises(ValueError, match='wall-time budget'):
        verification_common.read_run(binding(receipt), tmp_path, budget)
    assert returned == [True]
    file = tmp_path / 'tiny.txt'
    file.write_text('abcd', encoding='utf-8')
    budget = Budget()
    budget.limits['total_read_bytes'] = 7
    budget.charge(file)
    with pytest.raises(ValueError, match='total bound-data read budget'):
        budget.charge(file)


def test_small_selected_E_preserves_large_and_three_output_qualification_before_consumer(tmp_path, monkeypatch):
    import verification_common as common
    import validate_simulation_receipt as consumer
    receipt, qualified_raw = selected_e_fixture(tmp_path / 'actual')
    budget, entered = Budget(), []
    def full_e_boundary(*args, **kwargs):
        # E still receives its complete qualification binding and actual input.
        assert qualified_raw.resolve() in budget.identities
        assert budget.identities[qualified_raw.resolve()] == sha256_file(qualified_raw)
        entered.append(True)
        raise StopIteration('entered existing E consumer')
    monkeypatch.setattr(consumer, 'validate_simulation_receipt', full_e_boundary)
    with pytest.raises(StopIteration, match='entered existing E consumer'):
        common.read_run(binding(receipt), tmp_path, budget)
    assert entered == [True]
    assert budget.finish()['read_bytes'] >= qualified_raw.stat().st_size


@pytest.mark.parametrize('role', ['raw', 'data'])
@pytest.mark.parametrize('defect,message', [('samples', 'sample budget'), ('signals', 'signal count'),
    ('length', 'shape differs'), ('nested_time', 'finite flat real'), ('nested_values', 'finite flat real'),
    ('boolean', 'finite flat real')])
def test_selected_E_raw_and_primary_shapes_block_before_E_numerical_consumer(tmp_path, monkeypatch, role, defect, message):
    import verification_common as common
    import validate_simulation_receipt as consumer
    receipt, _ = selected_e_fixture(tmp_path / 'actual')
    file = receipt.parent / ('raw-simulation.json' if role == 'raw' else 'primary-outputs.json')
    doc = load_document(file)
    outputs = doc['cases'][0]['outputs'] if role == 'raw' else doc['outputs']
    signal = outputs[0]
    if defect == 'samples':
        signal.update(time=list(range(302)), values=[1.0] * 302)
    elif defect == 'signals':
        outputs.extend([copy.deepcopy(signal), copy.deepcopy(signal)])
    elif defect == 'length':
        signal['values'].pop()
    elif defect == 'nested_time':
        signal['time'][0] = [0, 1, 2]
    elif defect == 'nested_values':
        signal['values'][0] = [1.0, 2.0]
    else:
        signal['values'][0] = True
    write_json(file, doc)
    refresh_e_fixture(receipt)
    entered = []
    monkeypatch.setattr(consumer, 'validate_simulation_receipt', lambda *a, **k: entered.append(True))
    with pytest.raises(ValueError, match=message):
        common.read_run(binding(receipt), tmp_path, Budget())
    assert not entered


@pytest.mark.parametrize('defect', ['case_identity', 'data_identity', 'data_role', 'input_role', 'artifact_SHA'])
def test_selected_E_exact_role_and_identity_block_before_consumer(tmp_path, monkeypatch, defect):
    import verification_common as common
    import validate_simulation_receipt as consumer
    receipt, _ = selected_e_fixture(tmp_path / 'actual')
    if defect in {'case_identity', 'data_role'}:
        file = receipt.parent / 'raw-simulation.json'
        doc = load_document(file)
        doc['cases'][0]['case_id' if defect == 'case_identity' else 'data_file'] = 'qualification'
        write_json(file, doc)
        refresh_e_fixture(receipt)
    elif defect == 'data_identity':
        file = receipt.parent / 'primary-outputs.json'
        doc = load_document(file)
        doc['run_id'] = 'different-actual-run'
        write_json(file, doc)
        refresh_e_fixture(receipt)
    else:
        doc = load_document(receipt)
        if defect == 'input_role':
            doc['artifacts']['input'] = doc['artifacts']['data']
        else:
            doc['artifacts']['data']['sha256'] = '0' * 64
        write_json(receipt, doc)
    entered = []
    monkeypatch.setattr(consumer, 'validate_simulation_receipt', lambda *a, **k: entered.append(True))
    with pytest.raises(ValueError):
        common.read_run(binding(receipt), tmp_path, Budget())
    assert not entered


@pytest.mark.parametrize('defect,message', [('missing', 'missing'), ('tamper', 'SHA differs'),
    ('file_bytes', 'file byte limit'), ('total_bytes', 'total bound-data read budget')])
def test_qualification_bound_files_keep_SHA_presence_and_byte_guards(tmp_path, monkeypatch, defect, message):
    import verification_common as common
    import validate_simulation_receipt as consumer
    receipt, qualified_raw = selected_e_fixture(tmp_path / 'actual')
    budget, entered = Budget(), []
    if defect == 'missing':
        qualified_raw.unlink()
    elif defect == 'tamper':
        qualified_raw.write_text('{}', encoding='utf-8')
    elif defect == 'file_bytes':
        budget.limits['input_file_bytes'] = qualified_raw.stat().st_size - 1
    else:
        budget.limits['total_read_bytes'] = qualified_raw.stat().st_size - 1
    monkeypatch.setattr(consumer, 'validate_simulation_receipt', lambda *a, **k: entered.append(True))
    with pytest.raises((ValueError, OSError), match=message):
        common.read_run(binding(receipt), tmp_path, budget)
    assert not entered


def test_qualification_change_after_consumer_is_caught_by_shared_budget(tmp_path, monkeypatch):
    import verification_common as common
    import validate_simulation_receipt as consumer
    receipt, qualified_raw = selected_e_fixture(tmp_path / 'actual')
    budget = Budget()
    def changed(*a, **k):
        qualified_raw.write_text('{}', encoding='utf-8')
        raise StopIteration('E boundary returned')
    monkeypatch.setattr(consumer, 'validate_simulation_receipt', changed)
    with pytest.raises(StopIteration):
        common.read_run(binding(receipt), tmp_path, budget)
    with pytest.raises(ValueError, match='bound input changed'):
        budget.finish()


@pytest.mark.parametrize('defect', [None, 'oversized', 'oversized_raw', 'uncovered'])
def test_G_nested_E_preflight_precedes_campaign_consumer_and_shares_budget(tmp_path, monkeypatch, defect):
    from verification_analysis import campaign_response
    import validate_experiment_receipt as consumer
    import validate_simulation_receipt as e_consumer
    directory = tmp_path / 'campaign'
    directory.mkdir()
    receipt, qualified_raw = selected_e_fixture(directory / 'draw-001')
    if defect in {'oversized', 'oversized_raw'}:
        file = receipt.parent / ('primary-outputs.json' if defect == 'oversized' else 'raw-simulation.json')
        doc = load_document(file)
        outputs = doc['outputs'] if defect == 'oversized' else doc['cases'][0]['outputs']
        outputs[0].update(time=list(range(302)), values=[1.0] * 302)
        write_json(file, doc)
        refresh_e_fixture(receipt)
    rows = [{'status': 'completed', 'receipt': {'path': 'draw-001/' + receipt.name, 'sha256': sha256_file(receipt)}}]
    campaign = campaign_fixture(directory, rows)
    run, _ = run_and_ref(tmp_path / 'upstream')
    run.update(receipt=binding(receipt), run_id='owner-actual', outputs=[{'port': 1, 'unit': '1', 'time': [0, 1], 'values': [1., 1.]}])
    if defect == 'uncovered':
        run['receipt']['sha256'] = '0' * 64
    analysis = numerical_analysis('scenario_response', ['r0'])
    analysis.update(campaign=binding(campaign), output_ports=[1], threshold=2)
    budget, entered, e_entered = Budget(), [], []
    budget.run_ids.add('earlier-nested-H1')
    def nested_E_boundary(*a, **k):
        # G's real consumer invokes E/SciPy; all selected actual JSON guards
        # must already have run when this boundary is entered.
        assert qualified_raw.resolve() in budget.identities
        assert (receipt.parent / 'primary-outputs.json').resolve() in budget.identities
        entered.append(True)
        e_consumer.validate_simulation_receipt(receipt, project_root=tmp_path)
        return {'valid': True, 'errors': [], 'campaign_complete': True, 'method': 'scenario_matrix'}
    monkeypatch.setattr(e_consumer, 'validate_simulation_receipt', lambda *a, **k: e_entered.append(True))
    monkeypatch.setattr(consumer, 'validate_experiment_receipt', nested_E_boundary)
    if defect:
        with pytest.raises(ValueError, match='sample budget|exact ordered'):
            campaign_response(analysis, {'r0': run}, {'claim': {'domain': {'kind': 'actual_draws'}}}, tmp_path, budget)
        assert not entered
        assert not e_entered
    else:
        assert campaign_response(analysis, {'r0': run}, {'claim': {'domain': {'kind': 'actual_draws'}}}, tmp_path, budget)['passed']
        assert entered == [True]
        assert e_entered == [True]
        assert budget.finish()['actual_E_runs'] == 1


@pytest.mark.parametrize('order', ['bad_first', 'good_first', 'late_discovered'])
def test_conflicting_bound_SHA_never_evades_seen_file_checks(tmp_path, order):
    from verification_common import preflight_e
    file = tmp_path / 'source.txt'
    file.write_text('small reviewed source', encoding='utf-8')
    good = {'file': file.name, 'sha256': sha256_file(file)}
    bad = {'file': file.name, 'sha256': '0' * 64}
    if order == 'late_discovered':
        nested = tmp_path / 'nested.json'
        write_json(nested, {'later_reference': bad})
        doc = {'nested': {'file': nested.name, 'sha256': sha256_file(nested)}, 'direct': good}
    else:
        doc = {'first': good, 'second': bad} if order == 'bad_first' else {'first': bad, 'second': good}
    path = tmp_path / 'binding-metadata.json'
    write_json(path, doc)
    with pytest.raises(ValueError, match='SHA differs'):
        preflight_e(path, tmp_path, Budget())


def historical_D_fixture(root):
    """Capture-role infrastructure only: model bytes are not native evidence."""
    import json
    from probe_implementation import make_request, qualification_cases
    from runtime_common import canonical_digest
    from validate_domain_mapping import semantic_digest as mapping_digest
    e, _ = selected_e_fixture(root / 'actual-E', qualification=False)
    directory = root / 'native-D'
    directory.mkdir()
    mapping = root / 'mapping.json'
    original = {'schema_version': 1, 'project_id': 'owner-history-role', 'status': 'mapped',
                'implementation': None, 'mathematics': {'slope': 2.5}}
    text = json.dumps(original, indent=2) + '\n'
    mapping.write_bytes(text.encode('utf-8'))
    (directory / 'mapping-original.yaml').write_bytes(text.encode('utf-8'))
    snapshot = {k: v for k, v in original.items() if k not in {'status', 'implementation'}}
    write_json(directory / 'mapping-snapshot.json', snapshot)
    identity = '12a62a6d-15bc-4567-890a-abcdef123456'
    spec = qualification_cases(identity)[0]['build_spec']
    b = {'project_id': original['project_id'], 'mapping_semantic_sha256': mapping_digest(original),
         'mapping_snapshot': snapshot, 'mapping_original_text': text, 'mapping_input': binding(mapping),
         'parameter_provenance_sha256': 'a' * 64, 'build_spec_sha256': canonical_digest(spec), 'bound_files': []}
    request = make_request('owner-no-native.exe', directory, run_id=identity, mode='implementation',
                           cases=[{'case_id': 'implementation', 'expect_failure': False, 'build_spec': spec}], bindings=b)
    write_json(directory / 'inputs.json', request)
    write_json(directory / 'raw-implementation.json', {k: request[k] for k in
        ('run_id', 'channel', 'host_fingerprint', 'input_identity', 'source_identity')})
    (directory / 'matlab-batch.log').write_text('OWNER BOUNDARY FIXTURE; no native run', encoding='utf-8')
    (directory / (spec['model_name'] + '.slx')).write_bytes(b'OWNER NON-NATIVE PLACEHOLDER')
    write_json(directory / 'implementation-structure.json', {'notice': 'not native evidence'})
    d = directory / 'implementation-receipt.json'
    write_json(d, {'schema_version': 1, 'run_id': identity, 'sources': request['sources'],
                  **{k: b[k] for k in ('project_id', 'mapping_semantic_sha256', 'parameter_provenance_sha256', 'build_spec_sha256')}})
    refresh_historical_fixture(e, d, mapping)
    return e, d, mapping


def refresh_historical_fixture(e, d, mapping, *, restamp_input=True):
    from runtime_common import canonical_digest
    request = load_document(d.parent / 'inputs.json')
    if restamp_input:
        request['input_identity'] = canonical_digest({k: v for k, v in request.items() if k != 'input_identity'})
        write_json(d.parent / 'inputs.json', request)
        write_json(d.parent / 'raw-implementation.json', {k: request[k] for k in
            ('run_id', 'channel', 'host_fingerprint', 'input_identity', 'source_identity')})
    doc = load_document(d)
    spec = request['cases'][0]['build_spec']
    expected = {'input': 'inputs.json', 'raw': 'raw-implementation.json', 'log': 'matlab-batch.log',
                'mapping_original': 'mapping-original.yaml', 'mapping_snapshot': 'mapping-snapshot.json',
                'implementation_model': spec['model_name'] + '.slx', 'implementation_structure': 'implementation-structure.json'}
    doc['artifacts'] = {role: {'file': name, 'sha256': sha256_file(d.parent / name)} for role, name in expected.items()}
    write_json(d, doc)
    refresh_historical_attachment(e, d, mapping)


def refresh_historical_attachment(e, d, mapping):
    current = load_document(mapping)
    current.update(status='implemented', implementation=binding(d))
    write_json(mapping, current)
    request = load_document(e.parent / 'simulation-inputs.json')
    request['bindings'].update(implementation_receipt=binding(d), bound_files=[binding(mapping)])
    write_json(e.parent / 'simulation-inputs.json', request)
    refresh_e_fixture(e)


def test_D_archived_origin_allows_only_authenticated_attachment_and_charges_current(tmp_path, monkeypatch):
    from verification_common import read_run
    import validate_simulation_receipt as consumer
    e, d, mapping = historical_D_fixture(tmp_path)
    archive = d.parent / 'mapping-original.yaml'
    assert sha256_file(archive) != sha256_file(mapping)
    budget, entered = Budget(), []
    def stop(*a, **k):
        assert mapping.resolve() in budget.identities and archive.resolve() in budget.identities
        assert budget.identities[mapping.resolve()] == sha256_file(mapping)
        assert budget.identities[archive.resolve()] == sha256_file(archive)
        entered.append(True)
        raise StopIteration('existing E still must validate full history')
    monkeypatch.setattr(consumer, 'validate_simulation_receipt', stop)
    with pytest.raises(StopIteration, match='full history'):
        read_run(binding(e), tmp_path, budget)
    assert entered == [True]
    budget.finish()


@pytest.mark.parametrize('defect', ['archive_SHA', 'text', 'origin_SHA', 'snapshot_semantics', 'current_semantics',
    'attachment', 'manifest_missing', 'archive_escape', 'input_role', 'origin_escape', 'raw_identity',
    'receipt_identity', 'input_identity', 'nested_current_binding', 'receipt_schema', 'build_identity', 'project_identity'])
def test_D_capture_tamper_blocks_before_E_without_historical_exemptions(tmp_path, monkeypatch, defect):
    from verification_common import read_run
    import validate_simulation_receipt as consumer
    e, d, mapping = historical_D_fixture(tmp_path)
    input_path = d.parent / 'inputs.json'
    if defect in {'text', 'origin_SHA', 'origin_escape', 'input_identity', 'build_identity', 'project_identity'}:
        doc = load_document(input_path)
        if defect == 'text':
            doc['bindings']['mapping_original_text'] += ' '
        elif defect == 'origin_SHA':
            doc['bindings']['mapping_input']['sha256'] = '0' * 64
        elif defect == 'origin_escape':
            doc['bindings']['mapping_input']['path'] = str(tmp_path.parent / 'escaped-mapping.json')
        elif defect == 'build_identity':
            doc['bindings']['build_spec_sha256'] = '0' * 64
            receipt = load_document(d)
            receipt['build_spec_sha256'] = '0' * 64
            write_json(d, receipt)
        elif defect == 'project_identity':
            doc['bindings']['project_id'] = 'different-from-captured-project'
            receipt = load_document(d)
            receipt['project_id'] = doc['bindings']['project_id']
            write_json(d, receipt)
        else:
            doc['bindings']['mapping_original_text'] += ' '
        write_json(input_path, doc)
        refresh_historical_fixture(e, d, mapping, restamp_input=defect != 'input_identity')
    elif defect in {'archive_SHA', 'snapshot_semantics'}:
        file = d.parent / ('mapping-original.yaml' if defect == 'archive_SHA' else 'mapping-snapshot.json')
        doc = load_document(file)
        doc['mathematics']['slope'] = 3.0
        write_json(file, doc)
        # A newly hashed manifest cannot repair the declared capture identity.
        refresh_historical_fixture(e, d, mapping)
    elif defect in {'manifest_missing', 'archive_escape', 'input_role', 'receipt_identity', 'receipt_schema'}:
        doc = load_document(d)
        if defect == 'manifest_missing':
            doc['artifacts'].pop('implementation_structure')
        elif defect == 'archive_escape':
            doc['artifacts']['mapping_original']['file'] = '../mapping-original.yaml'
        elif defect == 'input_role':
            doc['artifacts']['input'] = doc['artifacts']['mapping_snapshot']
        elif defect == 'receipt_schema':
            doc['schema_version'] = True
        else:
            doc['project_id'] = 'different-owner-project'
        write_json(d, doc)
        refresh_historical_attachment(e, d, mapping)
    elif defect == 'raw_identity':
        raw = load_document(d.parent / 'raw-implementation.json')
        raw['run_id'] = 'different-owner-run'
        write_json(d.parent / 'raw-implementation.json', raw)
        refresh_historical_fixture(e, d, mapping, restamp_input=False)
    elif defect in {'current_semantics', 'attachment'}:
        doc = load_document(mapping)
        if defect == 'current_semantics':
            doc['mathematics']['slope'] = 3.0
        else:
            doc['implementation']['sha256'] = '0' * 64
        write_json(mapping, doc)
        request = load_document(e.parent / 'simulation-inputs.json')
        request['bindings']['bound_files'] = [binding(mapping)]
        write_json(e.parent / 'simulation-inputs.json', request)
        refresh_e_fixture(e)
    else:
        request = load_document(e.parent / 'simulation-inputs.json')
        request['bindings']['protocol_snapshot'] = {'mapping': {'path': str(mapping), 'sha256': sha256_file(d.parent / 'mapping-original.yaml')}}
        write_json(e.parent / 'simulation-inputs.json', request)
        refresh_e_fixture(e)
    entered = []
    monkeypatch.setattr(consumer, 'validate_simulation_receipt', lambda *a, **k: entered.append(True))
    with pytest.raises((ValueError, KeyError, OSError)):
        read_run(binding(e), tmp_path, Budget())
    assert not entered


@pytest.mark.parametrize('order', ['bad_first', 'good_first'])
def test_D_archive_same_role_conflicting_SHA_is_not_overridden(tmp_path, monkeypatch, order):
    from verification_common import read_run
    import validate_simulation_receipt as consumer
    e, d, mapping = historical_D_fixture(tmp_path)
    archive = d.parent / 'mapping-original.yaml'
    good, bad = binding(archive), {'path': str(archive), 'sha256': '0' * 64}
    request = load_document(d.parent / 'inputs.json')
    request['bindings']['bound_files'] = [good, bad] if order == 'bad_first' else [bad, good]
    write_json(d.parent / 'inputs.json', request)
    refresh_historical_fixture(e, d, mapping)
    entered = []
    monkeypatch.setattr(consumer, 'validate_simulation_receipt', lambda *a, **k: entered.append(True))
    with pytest.raises(ValueError, match='SHA differs'):
        read_run(binding(e), tmp_path, Budget())
    assert not entered


def test_unselected_fake_D_manifest_cannot_assign_origin_role(tmp_path):
    from verification_common import preflight_e
    e, d, mapping = historical_D_fixture(tmp_path)
    fake = tmp_path / 'arbitrary-source.json'
    doc = load_document(d.parent / 'inputs.json')
    doc['artifacts'] = {role: {**item, 'file': str(d.parent / item['file'])}
                        for role, item in load_document(d)['artifacts'].items()}
    write_json(fake, doc)
    with pytest.raises(ValueError, match='SHA differs'):
        preflight_e(fake, tmp_path, Budget())


def test_G_reuses_only_selected_D_capture_context_before_nested_E_consumption(tmp_path):
    from verification_common import preflight_campaign
    e, d, mapping = historical_D_fixture(tmp_path)
    rows = [{'status': 'completed', 'receipt': {'path': e.relative_to(tmp_path).as_posix(), 'sha256': sha256_file(e)}}]
    g = campaign_fixture(tmp_path, rows)
    budget = Budget()
    preflight_campaign(g, tmp_path, budget, [binding(e)])
    assert budget.identities[mapping.resolve()] == sha256_file(mapping)
    assert budget.identities[(d.parent / 'mapping-original.yaml').resolve()] == sha256_file(d.parent / 'mapping-original.yaml')
    budget.finish()
