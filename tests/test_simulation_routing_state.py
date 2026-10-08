"""E scope and binding gates; synthetic records do not qualify a MATLAB run."""
from pathlib import Path

import pytest

from runtime_common import load_document, sha256_file
from problem_factory import write_contract
from simulation_factory import make_simulation_protocol
from resolve_runtime import resolve_runtime
from validate_project_state import validate_project_state
from validate_simulation_protocol import validate_simulation_protocol


def frozen_state(root):
    protocol = make_simulation_protocol(root)
    report = validate_simulation_protocol(protocol, project_root=root, require_frozen=True)
    assert report['valid'] and report['frozen'], report['errors']
    state = {'schema_version': 1, 'project_id': report['project_id'], 'project_root': '.',
             'current_stage': 'SIMULATION_PROTOCOL_FROZEN', 'environment': None, 'artefacts': []}
    for anchor in ('problem', 'model', 'approval', 'mapping'):
        state[anchor] = {'path': str(Path(report[anchor + '_path']).relative_to(root)),
                         'sha256': report[anchor + '_sha256']}
    state['protocol'] = {'path': protocol.name, 'sha256': sha256_file(protocol)}
    return write_contract(root / 'e-state.json', state), protocol


def test_no_protocol_or_approval_grants_simulation():
    report = resolve_runtime('simulation_execution')
    assert report['status'] == 'blocked'
    assert 'simulation_protocol_supplied' in report['missing_gates']
    assert not report['execution_allowed'] and not report['business_execution_allowed']


def test_current_frozen_protocol_is_read_only_and_needs_independent_profiles(tmp_path):
    state, protocol = frozen_state(tmp_path)
    before = {path: path.read_bytes() for path in tmp_path.rglob('*') if path.is_file()}
    report = validate_project_state(state, scope='simulation')
    assert report['valid'] and report['protocol_frozen'], report['errors']
    assert report['simulation_checked'] and not report['environment_checked']
    assert not report['simulation_environment_checked'] and not report['primary_run_complete']
    review = resolve_runtime('simulation_protocol', state_path=state)
    assert review['status'] == 'inspected' and not review['execution_allowed']
    execution = resolve_runtime('simulation_execution', state_path=state)
    assert execution['status'] == 'blocked' and 'current_a_and_e_profiles' in execution['missing_gates']
    assert not execution['simulation_execution_allowed']
    assert before == {path: path.read_bytes() for path in before}


@pytest.mark.parametrize('scope', ['problem', 'model', 'implementation'])
def test_earlier_scopes_leave_stale_e_evidence_unassessed(tmp_path, scope):
    state, protocol = frozen_state(tmp_path)
    protocol.write_text('{}', encoding='utf-8')
    result = validate_project_state(state, scope=scope)
    assert result['valid'], result['errors']
    assert not result['simulation_checked'] and not result['protocol_frozen']
    full = validate_project_state(state, scope='simulation')
    assert not full['valid'] and 'protocol' in full['stale_artefacts']


@pytest.mark.parametrize('anchor', ['problem', 'model', 'approval', 'mapping', 'protocol'])
def test_state_does_not_accept_another_upstream_or_protocol_sha(tmp_path, anchor):
    state, _ = frozen_state(tmp_path)
    value = load_document(state)
    value[anchor]['sha256'] = '0' * 64
    write_contract(state, value)
    report = validate_project_state(state, scope='simulation')
    assert not report['valid'] and not report['primary_run_complete']


def test_requested_protocol_cannot_replace_state_binding(tmp_path):
    state, protocol = frozen_state(tmp_path)
    copied = tmp_path / 'other-protocol.json'
    copied.write_bytes(protocol.read_bytes())
    route = resolve_runtime('simulation_protocol', state_path=state, protocol_path=copied)
    assert route['status'] == 'blocked'
    assert 'protocol_state_binding_matches' in route['missing_gates']


def test_current_protocol_without_actual_receipt_cannot_complete_primary_run(tmp_path):
    state, _ = frozen_state(tmp_path)
    value = load_document(state)
    fake = write_contract(tmp_path / 'fake-success.json', {'success': True, 'primary_run_complete': True})
    value.update(current_stage='PRIMARY_RUN_COMPLETE', primary_run={'path': fake.name, 'sha256': sha256_file(fake)})
    write_contract(state, value)
    result = validate_project_state(state, scope='simulation')
    assert not result['valid'] and not result['primary_run_complete']


def test_frozen_protocol_cannot_be_accepted_without_d_dependency_chain(tmp_path):
    state, protocol = frozen_state(tmp_path)
    value = load_document(state)
    value['artefacts'] = [{'id': 'accepted-protocol', 'role': 'simulation_protocol', 'path': protocol.name,
        'sha256': sha256_file(protocol), 'status': 'accepted',
        'depends_on': ['problem', 'model', 'approval', 'mapping', 'protocol']}]
    write_contract(state, value)
    report = validate_project_state(state, scope='simulation')
    assert not report['valid'] and 'accepted-protocol' in report['stale_artefacts']


def test_diagnostics_requires_the_actual_bound_run_receipt(tmp_path):
    _, protocol = frozen_state(tmp_path)
    route = resolve_runtime('solver_diagnostics', protocol_path=protocol)
    assert route['status'] == 'blocked' and 'current_run_receipt' in route['missing_gates']
    assert not route['execution_allowed']


def complete_state(root, *, age_hours=0):
    """Synthetic consumer records only; no actual MATLAB qualification."""
    from test_simulation_assurance import make_primary_receipt
    from test_mapping_state import d_artefact, mapping_artefacts
    receipt = make_primary_receipt(root, age_hours=age_hours)
    request = load_document(receipt.parent / 'simulation-inputs.json')
    protocol = Path(request['bindings']['protocol_input']['path'])
    report = validate_simulation_protocol(protocol, project_root=root, require_frozen=True)
    state = {'schema_version': 1, 'project_id': report['project_id'], 'project_root': '.',
             'current_stage': 'PRIMARY_RUN_COMPLETE', 'environment': None, 'artefacts': []}
    for anchor in ('problem', 'model', 'approval', 'mapping'):
        state[anchor] = {'path': str(Path(report[anchor + '_path']).relative_to(root)),
                         'sha256': report[anchor + '_sha256']}
    state['protocol'] = {'path': protocol.name, 'sha256': sha256_file(protocol)}
    state['primary_run'] = {'path': receipt.relative_to(root).as_posix(), 'sha256': sha256_file(receipt)}
    anchors = ['problem', 'model', 'approval', 'mapping']
    items = mapping_artefacts(root, Path(report['mapping_path']))
    items.append(d_artefact(root, Path(report['native_model_path']), 'implementation_model',
                            'native-model-record', anchors + ['mapping-record']))
    items.append(d_artefact(root, Path(report['implementation_receipt_path']), 'structure_evidence',
                            'structure-record', anchors + ['native-model-record']))
    parents = anchors + ['protocol']
    items.append(d_artefact(root, protocol, 'simulation_protocol', 'protocol-record', parents + ['structure-record']))
    items.append(d_artefact(root, receipt, 'simulation_run', 'run-record', parents + ['primary_run', 'protocol-record']))
    output = receipt.parent / load_document(receipt)['artifacts']['data']['file']
    items.append(d_artefact(root, output, 'simulation_output', 'output-record', parents + ['primary_run', 'run-record']))
    state['artefacts'] = items
    return write_contract(root / 'e-state.json', state), request


def test_complete_primary_state_accepts_exact_output_chain_read_only(tmp_path):
    state, request = complete_state(tmp_path)
    before = {path: path.read_bytes() for path in tmp_path.rglob('*') if path.is_file()}
    report = validate_project_state(state, scope='simulation')
    assert report['valid'] and report['primary_run_complete'], report['errors']
    assert not report['stale_artefacts'] and not report['environment_checked']
    route = resolve_runtime('simulation_execution', state_path=state,
        profile_path=request['bindings']['environment_profile']['path'],
        simulation_profile_path=request['bindings']['simulation_profile']['path'])
    assert route['status'] == 'allowed' and route['simulation_execution_allowed'], route.get('errors')
    assert before == {path: path.read_bytes() for path in before}


@pytest.mark.parametrize('change', ['unbound_output', 'missing_run_parent', 'environment_dependency'])
def test_primary_output_requires_bound_numeric_artifact_and_historical_dependencies(tmp_path, change):
    state, request = complete_state(tmp_path)
    value = load_document(state)
    output = next(item for item in value['artefacts'] if item['role'] == 'simulation_output')
    if change == 'unbound_output':
        copy = tmp_path / 'copied-output.json'
        copy.write_bytes((tmp_path / output['path']).read_bytes())
        output['path'] = copy.name
    elif change == 'missing_run_parent':
        output['depends_on'].remove('run-record')
    else:
        a = Path(request['bindings']['environment_profile']['path'])
        value['environment'] = {'profile_path': a.relative_to(tmp_path).as_posix(),
            'profile_sha256': sha256_file(a), 'receipt_sha256': sha256_file(a.parent / 'receipt.json')}
        output['depends_on'].append('environment')
    write_contract(state, value)
    report = validate_project_state(state, scope='simulation')
    assert not report['valid'] and 'output-record' in report['stale_artefacts']


def test_expired_current_profiles_do_not_erase_historical_primary_state(tmp_path):
    state, request = complete_state(tmp_path, age_hours=25)
    historical = validate_project_state(state, scope='simulation')
    assert historical['valid'] and historical['primary_run_complete'], historical['errors']
    route = resolve_runtime('simulation_execution', state_path=state,
        profile_path=request['bindings']['environment_profile']['path'],
        simulation_profile_path=request['bindings']['simulation_profile']['path'])
    assert route['status'] == 'blocked' and not route['simulation_execution_allowed']


def test_route_rejects_qualified_alternate_installation_before_execution(tmp_path):
    from test_runtime import make_profile
    from test_simulation_assurance import make_simulation_profile
    _, protocol = frozen_state(tmp_path)
    a = make_profile(tmp_path / 'alternate-a')
    e = make_simulation_profile(tmp_path / 'alternate-e', a)
    route = resolve_runtime('simulation_execution', protocol_path=protocol,
                            profile_path=a, simulation_profile_path=e)
    assert route['status'] == 'blocked' and 'simulation_runtime_matches' in route['missing_gates']
    assert not route['execution_allowed'] and not route['simulation_execution_allowed']
    assert route['errors'] == ['approved D implementation and E runtime differ']


def test_missing_primary_receipt_propagates_stale_to_descendants(tmp_path):
    state, _ = frozen_state(tmp_path)
    value = load_document(state)
    descendant = tmp_path / 'draft-output.txt'
    descendant.write_text('Synthetic draft only.', encoding='utf-8')
    value['current_stage'] = 'PRIMARY_RUN_COMPLETE'
    value['primary_run'] = {'path': 'removed/simulation-receipt.json', 'sha256': '0' * 64}
    value['artefacts'] = [{'id': 'draft-descendant', 'role': 'simulation_output', 'path': descendant.name,
        'sha256': sha256_file(descendant), 'status': 'draft', 'depends_on': ['primary_run']}]
    write_contract(state, value)
    result = validate_project_state(state, scope='simulation')
    assert not result['valid'] and not result['primary_run_complete']
    assert {'primary_run', 'draft-descendant'} <= set(result['stale_artefacts'])


@pytest.mark.parametrize('field,replacement', [('activated_packs', ['parallel_campaign']),
    ('upstream_skills', ['simulink-run-parallel-simulations']), ('required_gates', [])])
def test_accepted_route_cannot_admit_deferred_capabilities_or_drop_gates(tmp_path, field, replacement):
    from test_mapping_state import d_artefact
    state, request = complete_state(tmp_path)
    value = load_document(state)
    for anchor, key, receipt_name in [('environment', 'environment_profile', 'receipt.json'),
        ('simulation_environment', 'simulation_profile', 'simulation-profile-receipt.json')]:
        profile = Path(request['bindings'][key]['path'])
        value[anchor] = {'profile_path': profile.relative_to(tmp_path).as_posix(),
            'profile_sha256': sha256_file(profile), 'receipt_sha256': sha256_file(profile.parent / receipt_name)}
    route = resolve_runtime('simulation_execution', protocol_path=tmp_path / value['protocol']['path'],
        profile_path=request['bindings']['environment_profile']['path'],
        simulation_profile_path=request['bindings']['simulation_profile']['path'])
    path = write_contract(tmp_path / 'route.json', route)
    dependencies = ['problem', 'model', 'approval', 'mapping', 'protocol', 'environment',
        'simulation_environment', 'protocol-record']
    value['artefacts'].append(d_artefact(tmp_path, path, 'simulation_route_decision', 'route-record', dependencies))
    write_contract(state, value)
    baseline = validate_project_state(state)
    assert baseline['valid'], baseline['errors']
    route[field] = replacement
    write_contract(path, route)
    value['artefacts'][-1]['sha256'] = sha256_file(path)
    write_contract(state, value)
    result = validate_project_state(state)
    assert not result['valid'] and 'route-record' in result['stale_artefacts']
