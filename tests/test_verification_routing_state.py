"""H permission, scope and caller-acceptance boundaries; no native qualification."""
from pathlib import Path

import pytest

from problem_factory import write_contract
from resolve_runtime import resolve_runtime
from runtime_common import load_document, sha256_file
from validate_project_state import validate_project_state

H1_INTENTS = ['numerical_verification', 'numerical_verification_review']
H2_INTENTS = ['model_verification', 'model_verification_review', 'sensitivity_analysis',
              'robustness_analysis', 'solver_comparison', 'model_comparison']
PERMISSIONS = ['execution_allowed', 'business_execution_allowed', 'simulation_execution_allowed',
               'implementation_execution_allowed', 'parameter_study_execution_allowed',
               'experiment_execution_allowed', 'state_mutated']


def report(path, *, reviewed=False, **extra):
    return {'valid': True, 'reviewed': reviewed, 'assessment_ready': reviewed,
            'contract_path': str(path.resolve()), 'contract_sha256': sha256_file(path),
            'project_id': 'synthetic-h', 'semantic_sha256': '1' * 64,
            'errors': [], 'missing_gates': [] if reviewed else ['source_bound_review'],
            'bound_files': [], **extra}


@pytest.mark.parametrize('intent', H1_INTENTS + H2_INTENTS)
def test_missing_h_contract_never_falls_back_to_environment_execution(intent):
    value = resolve_runtime(intent)
    assert value['status'] == 'blocked'
    assert value['phase'] == 'H'
    assert all(value[key] is False for key in PERMISSIONS)
    assert value['selected_operations'] == []
    assert not value['activated_resources']


@pytest.mark.parametrize('intent', H1_INTENTS + H2_INTENTS)
def test_h_review_cannot_select_runtime_operations(intent):
    value = resolve_runtime(intent, required_operations=['matlab.basic_execution'])
    assert value['status'] == 'blocked'
    assert 'h_review_has_no_selected_operations' in value['missing_gates']
    assert value['selected_operations'] == []
    assert all(value[key] is False for key in PERMISSIONS)


def test_h1_draft_review_is_read_only_and_has_no_runtime_requirement(tmp_path, monkeypatch):
    import validate_numerical_verification as consumer
    path = write_contract(tmp_path / 'h1.json', {'synthetic': 'route-only boundary'})
    monkeypatch.setattr(consumer, 'validate_numerical_verification', lambda *a, **k: report(path))
    before = path.read_bytes()
    value = resolve_runtime('numerical_verification', numerical_verification_path=path,
                            profile_path=tmp_path / 'absent-current-profile.json')
    assert value['status'] == 'inspected'
    assert value['missing_gates'] == ['source_bound_review']
    assert value['activated_modules'] == ['numerical_verification']
    assert all(value[key] is False for key in PERMISSIONS)
    assert path.read_bytes() == before


def test_failed_h1_criteria_are_inspectable_without_acceptance(tmp_path, monkeypatch):
    import validate_numerical_verification as contract_consumer
    import validate_numerical_verification_receipt as receipt_consumer
    path = write_contract(tmp_path / 'h1.json', {'synthetic': 'route-only boundary'})
    receipt = write_contract(tmp_path / 'receipt.json', {'synthetic': 'failed numerical criteria'})
    monkeypatch.setattr(contract_consumer, 'validate_numerical_verification', lambda *a, **k: report(path, reviewed=True))
    monkeypatch.setattr(receipt_consumer, 'validate_numerical_verification_receipt',
                        lambda *a, **k: report(path, reviewed=True, numerically_verified=False))
    value = resolve_runtime('numerical_verification_review', numerical_verification_path=path,
                            numerical_verification_receipt_path=receipt)
    assert value['status'] == 'inspected' and not value['numerically_verified']
    assert value['missing_gates'] == ['numerical_verification_criteria_satisfied']
    assert all(value[key] is False for key in PERMISSIONS)


@pytest.mark.parametrize('intent,kind', [('sensitivity_analysis', 'sensitivity'),
    ('robustness_analysis', 'robustness'), ('solver_comparison', 'solver_comparison'),
    ('model_comparison', 'model_comparison')])
def test_h2_named_analysis_requires_the_declared_kind(tmp_path, monkeypatch, intent, kind):
    import validate_model_verification as consumer
    path = write_contract(tmp_path / 'h2.json', {'synthetic': 'route-only boundary'})
    monkeypatch.setattr(consumer, 'validate_model_verification',
                        lambda *a, **k: report(path, required_analysis_kinds=[]))
    absent = resolve_runtime(intent, model_verification_path=path)
    assert absent['status'] == 'blocked'
    assert absent['missing_gates'] == ['requested_analysis_required']
    monkeypatch.setattr(consumer, 'validate_model_verification',
                        lambda *a, **k: report(path, required_analysis_kinds=[kind]))
    present = resolve_runtime(intent, model_verification_path=path)
    assert present['status'] == 'inspected'
    assert all(present[key] is False for key in PERMISSIONS)


def test_h2_completed_reject_is_not_model_verified(tmp_path, monkeypatch):
    import validate_model_verification as contract_consumer
    import validate_model_verification_receipt as receipt_consumer
    path = write_contract(tmp_path / 'h2.json', {'synthetic': 'route-only boundary'})
    receipt = write_contract(tmp_path / 'receipt.json', {'synthetic': 'rejected finite claim'})
    monkeypatch.setattr(contract_consumer, 'validate_model_verification', lambda *a, **k: report(path, reviewed=True))
    monkeypatch.setattr(receipt_consumer, 'validate_model_verification_receipt',
                        lambda *a, **k: report(path, reviewed=True, model_verification_decided=True,
                                              model_verified=False, claim_supported=False))
    value = resolve_runtime('model_verification_review', model_verification_path=path,
                            model_verification_receipt_path=receipt)
    assert value['status'] == 'inspected' and value['model_verification_decided']
    assert not value['model_verified'] and not value['claim_supported']
    assert all(value[key] is False for key in PERMISSIONS)


def test_state_bound_h_contract_cannot_be_replaced_by_same_bytes(tmp_path, monkeypatch):
    import validate_project_state as state_consumer
    path = write_contract(tmp_path / 'bound.json', {'synthetic': 'route-only boundary'})
    copied = tmp_path / 'copy.json'
    copied.write_bytes(path.read_bytes())
    state = write_contract(tmp_path / 'state.json', {'project_id': 'synthetic-h'})
    monkeypatch.setattr(state_consumer, 'validate_project_state', lambda *a, **k:
        {'valid': True, 'current_stage': 'NEW', 'project_root': str(tmp_path),
         'numerical_verification_path': str(path), 'errors': []})
    value = resolve_runtime('numerical_verification', state_path=state,
                            numerical_verification_path=copied)
    assert value['status'] == 'blocked'
    assert value['missing_gates'] == ['verification_state_binding_matches']
    assert all(value[key] is False for key in PERMISSIONS)


@pytest.mark.parametrize('scope', ['problem', 'model', 'implementation', 'simulation', 'parameter_study', 'experiment'])
def test_earlier_scopes_leave_h_history_unassessed(tmp_path, scope):
    value = {'schema_version': 1, 'project_id': 'synthetic-h', 'project_root': '.',
             'current_stage': 'NEW', 'environment': None, 'artefacts': [],
             'numerical_verification': {'path': 'missing-h1.json', 'sha256': '0' * 64},
             'model_verification': {'path': 'missing-h2.json', 'sha256': '0' * 64}}
    path = write_contract(tmp_path / 'state.json', value)
    before = path.read_bytes()
    result = validate_project_state(path, scope=scope)
    assert result['valid'], result['errors']
    assert not result['numerical_verification_checked']
    assert not result['model_verification_checked']
    assert not result['numerically_verified'] and not result['model_verified']
    assert not result['environment_checked']
    assert path.read_bytes() == before
    assert not validate_project_state(path, scope='numerical_verification')['valid']


@pytest.mark.parametrize('stage', ['NUMERICALLY_VERIFIED', 'MODEL_VERIFICATION_DECIDED', 'MODEL_VERIFIED'])
def test_h_stage_cannot_be_written_without_its_exact_upstream_bindings(tmp_path, stage):
    path = write_contract(tmp_path / 'state.json', {'schema_version': 1, 'project_id': 'synthetic-h',
        'project_root': '.', 'current_stage': stage, 'environment': None, 'artefacts': []})
    result = validate_project_state(path, scope='model_verification')
    assert not result['valid']
    assert any('required property' in message for message in result['errors'])


def test_accepted_h1_evidence_rejects_environment_and_missing_ancestors(tmp_path):
    from numerical_verification_state import validate_artifact
    path = write_contract(tmp_path / 'h1.json', {'synthetic': 'dependency-only boundary'})
    binding = {'path': path.name, 'sha256': sha256_file(path)}
    item = {'id': 'h1-record', 'role': 'numerical_verification_contract', 'path': path.name,
            'sha256': binding['sha256'], 'status': 'accepted',
            'depends_on': ['problem', 'model', 'approval', 'mapping', 'protocol', 'numerical_verification']}
    result = {'numerical_verification_path': str(path), 'numerical_verification_reviewed': True}
    missing = validate_artifact(item, state={'numerical_verification': binding}, result=result,
        root=tmp_path, environment_dependents={'h1-record'}, ancestor_roles=lambda item: set())
    assert any('current environment readiness' in message for message in missing)
    assert any('dependency chain' in message for message in missing)


def test_accepted_h2_disposition_does_not_require_support(tmp_path):
    from model_verification_state import validate_artifact
    path = write_contract(tmp_path / 'h2-receipt.json', {'synthetic': 'completed reject boundary'})
    binding = {'path': path.name, 'sha256': sha256_file(path)}
    item = {'id': 'h2-record', 'role': 'model_verification_evidence', 'path': path.name,
            'sha256': binding['sha256'], 'status': 'accepted',
            'depends_on': ['problem', 'model', 'approval', 'mapping', 'protocol', 'primary_run',
                'numerical_verification', 'numerical_verification_receipt',
                'model_verification', 'model_verification_receipt']}
    result = {'model_verification_receipt_path': str(path), 'model_verification_reviewed': True,
              'numerically_verified': True, 'model_verification_decided': True, 'model_verified': False}
    missing = validate_artifact(item, state={'model_verification_receipt': binding}, result=result,
        root=tmp_path, environment_dependents=set(), ancestor_roles=lambda item:
            {'simulation_protocol', 'simulation_run', 'numerical_verification_evidence', 'model_verification_contract'})
    assert missing == []


def test_h2_route_does_not_emit_internal_full_numeric_cache(tmp_path, monkeypatch):
    import validate_model_verification as consumer
    path = write_contract(tmp_path / 'h2.json', {'synthetic': 'output boundary'})
    monkeypatch.setattr(consumer, 'validate_model_verification',
                        lambda *a, **k: report(path, _members={'internal': object()}))
    value = resolve_runtime('model_verification', model_verification_path=path)
    assert value['status'] == 'inspected'
    assert '_members' not in value['model_verification_validation']
    import json
    json.dumps(value)


def synthetic_h1_state(root, *, age_hours=0, offsets=(1e-4, 6.25e-6, 3.90625e-7)):
    """Compose real consumers over synthetic E MAT/JSON/CSV, never actual MATLAB."""
    from numerical_factory import make_numerical_runs
    from run_numerical_verification import run_numerical_verification
    from validate_numerical_verification_receipt import validate_numerical_verification_receipt
    contract, runs = make_numerical_runs(root, age_hours=age_hours, offsets=offsets)
    assessment = run_numerical_verification(contract, runs, root / 'h1-assessment', project_root=root)
    assert assessment['valid'], assessment['errors']
    receipt = Path(assessment['receipt_path'])
    report = validate_numerical_verification_receipt(receipt, project_root=root)
    assert report['valid'], report['errors']
    return state_from_h1_receipt(root, receipt, report=report), contract, runs, receipt


def state_from_h1_receipt(root, receipt, *, report=None):
    from validate_numerical_verification_receipt import validate_numerical_verification_receipt
    from test_mapping_state import d_artefact, mapping_artefacts
    report = report or validate_numerical_verification_receipt(receipt, project_root=root)
    assert report['valid'], report['errors']
    contract = Path(report['contract_path'])
    state = {'schema_version': 1, 'project_id': report['project_id'], 'project_root': '.',
             'current_stage': 'NUMERICALLY_VERIFIED' if report['numerically_verified'] else 'PRIMARY_RUN_COMPLETE',
             'environment': None, 'artefacts': []}
    for anchor in ('problem', 'model', 'approval', 'mapping'):
        state[anchor] = {'path': Path(report[anchor + '_path']).relative_to(root).as_posix(),
                         'sha256': report[anchor + '_sha256']}
    for anchor, path in [('protocol', Path(report['primary_protocol_path'])), ('primary_run', Path(report['primary_receipt_path'])),
        ('numerical_verification', contract), ('numerical_verification_receipt', receipt)]:
        state[anchor] = {'path': path.relative_to(root).as_posix(), 'sha256': sha256_file(path)}
    upstream = ['problem', 'model', 'approval', 'mapping']
    items = mapping_artefacts(root, Path(report['mapping_path']))
    primary_protocol = report['primary_protocol_report']
    items.append(d_artefact(root, Path(primary_protocol['native_model_path']), 'implementation_model',
                            'native-model-record', upstream + ['mapping-record']))
    items.append(d_artefact(root, Path(primary_protocol['implementation_receipt_path']), 'structure_evidence',
                            'structure-record', upstream + ['native-model-record']))
    items.append(d_artefact(root, Path(report['primary_protocol_path']), 'simulation_protocol',
                            'protocol-record', upstream + ['protocol', 'structure-record']))
    items.append(d_artefact(root, Path(report['primary_receipt_path']), 'simulation_run', 'run-record',
                            upstream + ['protocol', 'primary_run', 'protocol-record']))
    items.append(d_artefact(root, contract, 'numerical_verification_contract', 'h1-contract-record',
                            upstream + ['protocol', 'numerical_verification', 'protocol-record']))
    items.append(d_artefact(root, receipt, 'numerical_verification_evidence', 'h1-evidence-record',
                            upstream + ['protocol', 'primary_run', 'numerical_verification',
                                'numerical_verification_receipt', 'run-record', 'h1-contract-record']))
    if not report['numerically_verified']:
        items[-1]['status'] = 'draft'
    state['artefacts'] = items
    return write_contract(root / 'h-state.json', state)


def test_current_complete_h1_state_and_review_are_read_only(tmp_path):
    state, contract, runs, receipt = synthetic_h1_state(tmp_path)
    before = {path: path.read_bytes() for path in tmp_path.rglob('*') if path.is_file()}
    value = validate_project_state(state, scope='numerical_verification')
    assert value['valid'] and value['numerically_verified'], value['errors']
    assert value['primary_run_complete'] and value['numerical_verification_checked']
    assert not value['environment_checked'] and not value['model_verification_checked']
    route = resolve_runtime('numerical_verification_review', state_path=state)
    assert route['status'] == 'inspected' and route['numerically_verified'], route['errors']
    assert all(route[key] is False for key in PERMISSIONS)
    assert before == {path: path.read_bytes() for path in before}


def test_expired_current_profiles_do_not_expire_h1_history(tmp_path):
    state, contract, runs, receipt = synthetic_h1_state(tmp_path, age_hours=25)
    value = validate_project_state(state, scope='numerical_verification')
    assert value['valid'] and value['numerically_verified'], value['errors']
    review = resolve_runtime('numerical_verification_review', state_path=state)
    assert review['status'] == 'inspected' and review['numerically_verified'], review['errors']
    request = load_document(runs[0].parent / 'simulation-inputs.json')
    execution = resolve_runtime('simulation_execution', state_path=state,
        profile_path=request['bindings']['environment_profile']['path'],
        simulation_profile_path=request['bindings']['simulation_profile']['path'])
    assert execution['status'] == 'blocked' and not execution['execution_allowed']


def test_missing_refinement_history_stales_h1_without_erasing_primary_e(tmp_path):
    state, contract, runs, receipt = synthetic_h1_state(tmp_path)
    runs[2].unlink()
    value = validate_project_state(state, scope='numerical_verification')
    assert not value['valid'] and not value['numerically_verified']
    assert value['primary_run_complete']
    assert {'numerical_verification_receipt', 'h1-evidence-record'} <= set(value['stale_artefacts'])
    earlier = validate_project_state(state, scope='simulation')
    assert earlier['valid'] and earlier['primary_run_complete'], earlier['errors']
    assert not earlier['numerical_verification_checked']


def test_failed_h1_evidence_can_be_bound_but_not_accepted(tmp_path):
    state, contract, runs, receipt = synthetic_h1_state(tmp_path, offsets=(0.01, 6.25e-6, 3.90625e-7))
    evidence = validate_project_state(state, scope='numerical_verification')
    assert evidence['valid'] and not evidence['numerically_verified'], evidence['errors']
    value = load_document(state)
    value['artefacts'][-1]['status'] = 'accepted'
    write_contract(state, value)
    invalid = validate_project_state(state, scope='numerical_verification')
    assert not invalid['valid'] and 'h1-evidence-record' in invalid['stale_artefacts']


def synthetic_h2_state(root, *, failure=False):
    from model_verification_factory import make_model_verification_contract, review_model_verification
    from run_model_verification import run_model_verification
    from test_mapping_state import d_artefact
    contract = make_model_verification_contract(root)
    if failure:
        value = load_document(contract)
        value['claims'][0]['analyses'][0]['bounds']['upper'] = 0.1
        write_contract(contract, value)
        review_model_verification(contract)
    report = run_model_verification(contract, root / 'h2-assessment', project_root=root)
    assert report['valid'] and report['model_verification_decided'], report['errors']
    receipt = Path(report['receipt_path'])
    state = state_from_h1_receipt(root, Path(report['primary_numerical_receipt_path']))
    value = load_document(state)
    value['current_stage'] = 'MODEL_VERIFIED' if report['model_verified'] else 'MODEL_VERIFICATION_DECIDED'
    for anchor, path in [('model_verification', contract), ('model_verification_receipt', receipt)]:
        value[anchor] = {'path': path.relative_to(root).as_posix(), 'sha256': sha256_file(path)}
    upstream = ['problem', 'model', 'approval', 'mapping', 'protocol', 'primary_run',
                'numerical_verification', 'numerical_verification_receipt', 'model_verification']
    value['artefacts'].append(d_artefact(root, contract, 'model_verification_contract',
        'h2-contract-record', upstream + ['h1-evidence-record']))
    value['artefacts'].append(d_artefact(root, receipt, 'model_verification_evidence',
        'h2-evidence-record', upstream + ['model_verification_receipt', 'h2-contract-record']))
    write_contract(state, value)
    return state, contract, receipt


def test_supported_h2_state_requires_current_h1_and_preserves_e(tmp_path):
    state, contract, receipt = synthetic_h2_state(tmp_path)
    value = validate_project_state(state, scope='model_verification')
    assert value['valid'] and value['model_verified'], value['errors']
    assert value['model_verification_decided'] and value['numerically_verified']
    assert value['primary_run_complete'] and not value['environment_checked']
    assert '_members' not in value['model_verification_validation']
    route = resolve_runtime('model_verification_review', state_path=state)
    assert route['status'] == 'inspected' and route['model_verified'], route['errors']
    assert all(route[key] is False for key in PERMISSIONS)
    contents = load_document(state)
    (tmp_path / contents['numerical_verification_receipt']['path']).unlink()
    stale = validate_project_state(state, scope='model_verification')
    assert not stale['valid'] and not stale['model_verified'] and not stale['model_verification_decided']
    assert stale['primary_run_complete']
    assert {'numerical_verification_receipt', 'h1-evidence-record', 'h2-contract-record',
            'h2-evidence-record'} <= set(stale['stale_artefacts'])


def test_complete_h2_modify_state_cannot_claim_model_verified(tmp_path):
    state, contract, receipt = synthetic_h2_state(tmp_path, failure=True)
    value = validate_project_state(state, scope='model_verification')
    assert value['valid'] and value['model_verification_decided'], value['errors']
    assert not value['model_verified'] and not value['claim_supported']
    assert value['numerically_verified'] and value['primary_run_complete']
    contents = load_document(state)
    contents['current_stage'] = 'MODEL_VERIFIED'
    write_contract(state, contents)
    invalid = validate_project_state(state, scope='model_verification')
    assert not invalid['valid'] and not invalid['model_verified']
    assert any('support' in message for message in invalid['errors'])


@pytest.mark.parametrize('intent', ['numerical_verification', 'model_verification'])
def test_nested_h_contract_uses_explicit_root_without_inventing_state(tmp_path, intent):
    if intent == 'numerical_verification':
        from numerical_factory import make_numerical_contract
        source = make_numerical_contract(tmp_path)
        keyword = 'numerical_verification_path'
    else:
        from model_verification_factory import make_model_verification_contract
        source = make_model_verification_contract(tmp_path)
        keyword = 'model_verification_path'
    directory = tmp_path / 'contracts'
    directory.mkdir()
    nested = directory / source.name
    nested.write_bytes(source.read_bytes())
    inferred = resolve_runtime(intent, **{keyword: nested})
    assert inferred['status'] == 'blocked'
    explicit = resolve_runtime(intent, project_root=tmp_path, **{keyword: nested})
    assert explicit['status'] == 'inspected', explicit['errors']
    assert 'state_validation' not in explicit
    assert 'current_stage' not in explicit
    assert all(explicit[key] is False for key in PERMISSIONS)


def test_explicit_root_cannot_replace_real_state_root(tmp_path):
    path = write_contract(tmp_path / 'state.json', {'schema_version': 1, 'project_id': 'synthetic-h',
        'project_root': '.', 'current_stage': 'NEW', 'environment': None, 'artefacts': []})
    other = tmp_path / 'other'
    other.mkdir()
    value = resolve_runtime('numerical_verification', state_path=path, project_root=other)
    assert value['status'] == 'blocked'
    assert value['missing_gates'] == ['project_root_state_binding_matches']
    assert value['state_validation']['project_root'] == str(tmp_path)
    assert value['state_validation']['valid']
    assert all(value[key] is False for key in PERMISSIONS)


def test_root_only_context_cannot_supply_state_or_deferred_prerequisites(tmp_path):
    inspected = resolve_runtime('inspect', project_root=tmp_path)
    assert inspected['status'] == 'inspected'
    assert 'state_validation' not in inspected and 'current_stage' not in inspected
    deferred = resolve_runtime('validation', project_root=tmp_path)
    assert deferred['status'] == 'deferred'
    assert 'accepted_verification_evidence' in deferred['missing_gates']
    assert 'state_validation' not in deferred and 'current_stage' not in deferred
    assert all(deferred[key] is False for key in PERMISSIONS)


def test_project_root_cli_resolves_nested_h1_contract_read_only(tmp_path):
    import json
    import subprocess
    import sys
    from numerical_factory import make_numerical_contract
    from runtime_common import ROOT
    source = make_numerical_contract(tmp_path)
    directory = tmp_path / 'contracts'
    directory.mkdir()
    nested = directory / source.name
    nested.write_bytes(source.read_bytes())
    process = subprocess.run([sys.executable, str(ROOT / 'scripts/resolve_runtime.py'),
        '--intent', 'numerical_verification', '--numerical-verification', str(nested),
        '--project-root', str(tmp_path)], capture_output=True, text=True, check=False)
    value = json.loads(process.stdout)
    assert process.returncode == 0 and value['status'] == 'inspected', value['errors']
    assert 'state_validation' not in value
    assert all(value[key] is False for key in PERMISSIONS)
