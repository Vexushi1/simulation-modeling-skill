"""Synthetic infrastructure routing/state regression; no real model or MATLAB qualification."""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import experiment_route
import experiment_state
import resolve_runtime as resolver
import validate_experiment_design as design_validator
from probe_environment import write_json
from runtime_common import load_contract, load_document, sha256_file
from test_experiment_design import SyntheticCatalog, binding


@pytest.fixture
def routing_catalog(tmp_path, monkeypatch):
    import validate_environment
    import validate_experiment_profile
    import validate_implementation_receipt
    import validate_simulation_profile
    catalog = SyntheticCatalog(tmp_path, monkeypatch)
    executable = tmp_path / 'matlab.exe'
    executable.write_text('SYNTHETIC INFRASTRUCTURE TEST', encoding='utf-8')
    runtime = {'executable': str(executable), 'fingerprint': 'synthetic-same-runtime'}
    write_json(catalog.upstream['implementation'], {'runtime': runtime, 'scope': 'SYNTHETIC NATIVE REPORT'})
    original_report = design_validator.validate_simulation_protocol

    def e_report(*args, **kwargs):
        report = original_report(*args, **kwargs)
        report['implementation_receipt_path'] = str(catalog.upstream['implementation'])
        return report

    monkeypatch.setattr(design_validator, 'validate_simulation_protocol', e_report)
    profiles = {}
    for name, filename, receipt_name in (
        ('a', 'profile.json', 'receipt.json'),
        ('e', 'simulation-profile.json', 'simulation-profile-receipt.json'),
        ('g', 'experiment-profile.json', 'experiment-profile-receipt.json')):
        directory = tmp_path / name
        directory.mkdir()
        path, receipt = directory / filename, directory / receipt_name
        write_json(path, {'runtime': runtime, 'scope': 'SYNTHETIC PROFILE STUB'})
        write_json(receipt, {'scope': 'SYNTHETIC PROFILE STUB'})
        profiles[name] = path

    def qualification(path, receipt_name):
        return {'valid': True, 'errors': [], 'profile_current': True, 'runtime': runtime,
                'profile_sha256': sha256_file(path), 'receipt_sha256': sha256_file(Path(path).parent / receipt_name)}

    monkeypatch.setattr(validate_environment, 'validate_environment', lambda path, **kwargs:
        {**qualification(path, 'receipt.json'), 'runtime_assured': True})
    monkeypatch.setattr(validate_simulation_profile, 'validate_simulation_profile', lambda path, **kwargs:
        {**qualification(path, 'simulation-profile-receipt.json'), 'simulation_assured': True})
    monkeypatch.setattr(validate_experiment_profile, 'validate_experiment_profile', lambda path, **kwargs:
        {**qualification(path, 'experiment-profile-receipt.json'), 'sampling_assured': True,
         'qualified_methods': ['scenario_matrix', 'full_factorial', 'monte_carlo_catalog']})
    monkeypatch.setattr(validate_implementation_receipt, 'same_runtime', lambda a, b: a == b)
    catalog.profiles = profiles
    return catalog


def state_and_truth(catalog, *, stage='NEW'):
    state = {'schema_version': 1, 'project_id': catalog.design['project_id'],
             'project_root': str(catalog.root), 'current_stage': stage, 'environment': None, 'artefacts': [],
             'experiment_design': binding(catalog.path), 'campaign': None, 'experiment_environment': None}
    result = {'model_approved': True, 'implementation_ready': True}
    for name in ('problem', 'model', 'approval', 'mapping'):
        state[name] = binding(catalog.upstream[name])
        result[name + '_path'] = str(catalog.upstream[name])
    return state, result


@pytest.mark.parametrize('explicit_model', [False, True])
def test_legal_null_protocol_draft_inspects_missing_gates_without_exception(routing_catalog, explicit_model):
    catalog = routing_catalog
    catalog.design.update(status='draft', review_record=None)
    catalog.design['catalog'][0]['protocol'] = None
    write_json(catalog.path, catalog.design)
    arguments = {'design_path': catalog.path}
    if explicit_model:
        arguments['model_path'] = catalog.upstream['model']
    result = resolver.resolve_runtime('experiment_design', **arguments)
    assert result['status'] == 'inspected', result['errors']
    assert result['missing_gates'] and not result['execution_allowed'] and not result['business_execution_allowed']
    state, truth = state_and_truth(catalog)
    errors, stale = [], set()
    experiment_state.validate_bindings(state, catalog.root, truth, errors, stale, 'experiment')
    assert not truth['experiment_design_reviewed'] and not truth['campaign_complete']
    assert not errors and not stale
    assert truth['experiment_design_validation']['missing_gates']


@pytest.mark.parametrize('stage, valid', [
    ('IMPLEMENTATION_READY', True),
    ('EXPERIMENT_DESIGN_REVIEWED', False),
])
def test_real_d_state_with_unknown_g_draft_only_blocks_formal_stage(tmp_path, stage, valid):
    from test_mapping_state import ready_native_project
    from validate_project_state import validate_project_state
    # The native evidence fixture is synthetic. All B/C/D state validation and
    # G template/source/schema/missing-gate validation here remain real.
    root = tmp_path / 'draft-state-project'
    root.mkdir()
    mapping, _, _, _, state_path = ready_native_project(root)
    state = load_document(state_path)
    template = Path(__file__).resolve().parents[1] / 'templates/experiment/experiment_design.yaml'
    draft = load_document(template)
    draft['project_id'] = state['project_id']
    draft['mapping'] = {'path': str(Path(mapping).relative_to(root)), 'sha256': sha256_file(mapping)}
    draft['catalog'] = [{'id': 'pending', 'protocol': None, 'factor_values': []}]
    design_path = root / 'experiment-design-draft.json'
    write_json(design_path, draft)
    state.update(current_stage=stage,
                 experiment_design={'path': design_path.name, 'sha256': sha256_file(design_path)})
    write_json(state_path, state)
    before = {path: path.read_bytes() for path in root.rglob('*') if path.is_file()}

    result = validate_project_state(state_path, scope='experiment')

    assert result['valid'] is valid, result['errors']
    assert result['model_approved'] and result['implementation_ready']
    assert result['experiment_checked'] and not result['experiment_environment_checked']
    assert not result['experiment_design_reviewed'] and not result['campaign_complete']
    assert result['experiment_design_validation']['missing_gates']
    if valid:
        assert not result['errors'] and 'experiment_design' not in result['stale_artefacts']
    else:
        assert 'experiment_design' in result['stale_artefacts']
        assert any('reviewed' in error or 'frozen' in error for error in result['errors'])
    assert {path: path.read_bytes() for path in root.rglob('*') if path.is_file()} == before


def test_explicit_mapping_is_forwarded_and_compared_by_real_resolver(routing_catalog):
    catalog = routing_catalog
    other = catalog.root / 'different-mapping.json'
    write_json(other, {'scope': 'SYNTHETIC DIFFERENT BINDING'})
    allowed = resolver.resolve_runtime('experiment_design', design_path=catalog.path, mapping_path=catalog.upstream['mapping'])
    assert allowed['status'] == 'inspected', allowed['errors']
    blocked = resolver.resolve_runtime('experiment_design', design_path=catalog.path, mapping_path=other)
    assert blocked['status'] == 'blocked' and not blocked['execution_allowed']
    assert any('mapping' in error for error in blocked['errors'])


def test_explicit_mapping_cannot_override_state_binding(routing_catalog):
    catalog = routing_catalog
    result = {'intent': 'experiment_design', 'execution_allowed': False, 'business_execution_allowed': False}
    blocked = experiment_route.experiment_route(result, router=load_contract('core/workflow_router.yaml'),
        resources=['modules/06_experiment_design.md'], design_path=catalog.path,
        state_result={'project_root': str(catalog.root), 'mapping_path': str(catalog.upstream['mapping'])},
        mapping_path=catalog.root / 'different-mapping.json')
    assert blocked['status'] == 'blocked'
    assert 'mapping_state_binding_matches' in blocked['missing_gates']


def test_expired_g_sampling_profile_blocks_new_execution(routing_catalog, monkeypatch):
    import validate_experiment_profile
    catalog = routing_catalog
    monkeypatch.setattr(validate_experiment_profile, 'validate_experiment_profile', lambda *args, **kwargs:
        {'valid': False, 'profile_current': False, 'sampling_assured': False,
         'qualified_methods': ['scenario_matrix'], 'errors': ['G profile expired']})
    before = {path: path.read_bytes() for path in catalog.root.rglob('*') if path.is_file()}
    result = resolver.resolve_runtime('experiment_campaign', design_path=catalog.path,
        profile_path=catalog.profiles['a'], simulation_profile_path=catalog.profiles['e'],
        experiment_profile_path=catalog.profiles['g'])
    assert result['status'] == 'blocked' and not result['execution_allowed']
    assert not result.get('experiment_execution_allowed', False)
    assert any('expired' in error for error in result['errors'])
    assert all(path.read_bytes() == content for path, content in before.items())


@pytest.mark.parametrize('intent', ['experiment_design', 'campaign_review'])
def test_read_only_review_never_requires_present_profile_ttl(routing_catalog, monkeypatch, intent):
    import validate_environment
    import validate_experiment_profile
    import validate_experiment_receipt
    import validate_simulation_profile
    catalog = routing_catalog

    def unexpected_profile_check(*args, **kwargs):
        raise AssertionError('read-only review requested current runtime TTL')

    for module, name in ((validate_environment, 'validate_environment'),
                         (validate_simulation_profile, 'validate_simulation_profile'),
                         (validate_experiment_profile, 'validate_experiment_profile')):
        monkeypatch.setattr(module, name, unexpected_profile_check)
    # Execution-time historical evidence is an independent foundational stub;
    # this test targets routing, not the already-covered native receipt chain.
    monkeypatch.setattr(validate_experiment_receipt, 'validate_experiment_receipt', lambda *args, **kwargs:
        {'valid': True, 'campaign_complete': True, 'errors': []})
    receipt = catalog.root / 'historical-experiment-receipt.json'
    write_json(receipt, {'scope': 'SYNTHETIC HISTORICAL EVIDENCE STUB'})
    result = resolver.resolve_runtime(intent, design_path=catalog.path, campaign_receipt_path=receipt,
        profile_path=catalog.profiles['a'], simulation_profile_path=catalog.profiles['e'],
        experiment_profile_path=catalog.profiles['g'])
    assert result['status'] == 'inspected' and not result['execution_allowed'], result['errors']
    assert not result['business_execution_allowed'] and result['state_mutated'] is False


@pytest.mark.parametrize('scope', ['problem', 'model', 'implementation', 'simulation', 'parameter_study'])
def test_earlier_scopes_leave_g_unassessed(routing_catalog, monkeypatch, scope):
    catalog = routing_catalog
    state, result = state_and_truth(catalog, stage='EXPERIMENT_DESIGN_REVIEWED')
    state['experiment_environment'] = {'profile_path': str(catalog.profiles['g']),
                                      'profile_sha256': '0' * 64, 'receipt_sha256': '0' * 64}
    monkeypatch.setattr(design_validator, 'validate_experiment_design', lambda *args, **kwargs:
        pytest.fail('earlier partial scope assessed G design'))
    errors, stale = [], set()
    experiment_state.validate_bindings(state, catalog.root, result, errors, stale, scope)
    assert not errors and not stale
    assert not result['experiment_checked'] and not result['experiment_environment_checked']
    assert not result['experiment_design_reviewed'] and not result['campaign_complete']


def test_experiment_scope_rejects_mismatched_upstream_anchor_without_writes(routing_catalog):
    catalog = routing_catalog
    state, result = state_and_truth(catalog, stage='EXPERIMENT_DESIGN_REVIEWED')
    state['mapping']['sha256'] = '0' * 64
    before = catalog.path.read_bytes()
    errors, stale = [], set()
    experiment_state.validate_bindings(state, catalog.root, result, errors, stale, 'experiment')
    assert 'experiment_design' in stale and not result['experiment_design_reviewed']
    assert any('state mapping binding' in error for error in errors)
    assert catalog.path.read_bytes() == before


@pytest.mark.parametrize('role', sorted(experiment_state.HISTORICAL_ROLES))
def test_accepted_g_history_needs_no_current_environment_dependency(routing_catalog, role):
    from run_experiment import SUMMARY
    catalog = routing_catalog
    state, result = state_and_truth(catalog)
    summary = catalog.root / SUMMARY
    write_json(summary, {'summary': {'scope': 'SYNTHETIC FIXED-N SUMMARY'}})
    receipt = catalog.root / 'experiment-receipt.json'
    write_json(receipt, {'scope': 'SYNTHETIC HISTORICAL GRAPH',
                        'artifacts': {SUMMARY: {'sha256': sha256_file(summary)}}})
    state['campaign'] = binding(receipt)
    result.update(experiment_design_reviewed=True, campaign_complete=True,
                  experiment_design_path=str(catalog.path), campaign_path=str(receipt))
    path = {'experiment_design': catalog.path, 'experiment_campaign': receipt, 'experiment_summary': summary}[role]
    parents = ['problem', 'model', 'approval', 'mapping', 'experiment_design']
    if role != 'experiment_design':
        parents.append('campaign')
    item = {'id': 'historical-record', 'role': role, 'path': str(path), 'sha256': sha256_file(path),
            'status': 'accepted', 'depends_on': parents}
    roles = {'mapping_contract', 'parameter_provenance', 'structure_evidence', 'experiment_design', 'experiment_campaign'}
    arguments = dict(state=state, result=result, root=catalog.root, ancestor_roles=lambda item: roles)
    assert experiment_state.validate_artifact(item, environment_dependents=set(), **arguments) == []
    forbidden = experiment_state.validate_artifact(item, environment_dependents={item['id']}, **arguments)
    assert any('current runtime' in error for error in forbidden)


@pytest.mark.parametrize('attack', ['native-role', 'design-role', 'campaign-role'])
def test_final_stale_propagation_clears_complete_flags(tmp_path, monkeypatch, attack):
    from test_mapping_state import ready_native_project, d_artefact
    from validate_project_state import validate_project_state
    import validate_experiment_receipt
    # Real B/C/D synthetic fixture validation is retained. Only G foundational
    # historical truth is stubbed to isolate the final shared state propagation.
    root = tmp_path / 'state-project'
    root.mkdir()
    mapping, _, _, _, state_path = ready_native_project(root)
    state = load_document(state_path)
    design_path, campaign_path = root / 'g-design.json', root / 'g-campaign.json'
    write_json(design_path, {'method': 'scenario_matrix', 'scope': 'SYNTHETIC G FOUNDATION STUB'})
    write_json(campaign_path, {'artifacts': {}, 'scope': 'SYNTHETIC G FOUNDATION STUB'})
    upstream = {}
    for name in ('problem', 'model', 'approval', 'mapping'):
        upstream[name + '_path'] = str((root / state[name]['path']).resolve())
        upstream[name + '_sha256'] = state[name]['sha256']
    protocol = {**upstream, 'frozen': True, 'execution_ready': True}
    report = {'valid': True, 'design_ready': True, 'reviewed': True, 'campaign_execution_ready': True,
        'project_id': state['project_id'], 'contract_path': str(design_path), 'design_sha256': sha256_file(design_path),
        'method': 'scenario_matrix', 'catalog': [{'id': 'synthetic-member', 'protocol_report': protocol}],
        'errors': [], 'missing_gates': [], **upstream}
    monkeypatch.setattr(design_validator, 'validate_experiment_design', lambda *args, **kwargs: copy.deepcopy(report))
    monkeypatch.setattr(validate_experiment_receipt, 'validate_experiment_receipt', lambda *args, **kwargs:
        {'valid': True, 'campaign_complete': True, 'errors': []})
    state.update(current_stage='CAMPAIGN_COMPLETE', experiment_design={'path': design_path.name, 'sha256': sha256_file(design_path)},
                 campaign={'path': campaign_path.name, 'sha256': sha256_file(campaign_path)})
    if attack != 'native-role':
        parents = ['problem', 'model', 'approval', 'mapping', 'experiment_design']
        state['artefacts'].append(d_artefact(root, design_path, 'experiment_design', 'g-design-record', parents + ['structure-record']))
        state['artefacts'].append(d_artefact(root, campaign_path, 'experiment_campaign', 'g-campaign-record',
                                          parents + ['campaign', 'g-design-record']))
    write_json(state_path, state)
    initial = validate_project_state(state_path, scope='experiment')
    assert initial['valid'] and initial['experiment_design_reviewed'] and initial['campaign_complete'], initial['errors']
    identity = {'native-role': 'native-model-record', 'design-role': 'g-design-record', 'campaign-role': 'g-campaign-record'}[attack]
    next(item for item in state['artefacts'] if item['id'] == identity)['status'] = 'stale'
    write_json(state_path, state)
    before = state_path.read_bytes()
    changed = validate_project_state(state_path, scope='experiment')
    assert not changed['valid'] and identity in changed['stale_artefacts']
    assert not changed['campaign_complete']
    assert changed['experiment_design_reviewed'] is (attack == 'campaign-role')
    if attack == 'native-role':
        assert 'mapping' not in changed['stale_artefacts'] and not changed['implementation_ready']
    assert state_path.read_bytes() == before
