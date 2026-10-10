"""H evidence authority and aggregate-budget boundaries; no native execution."""
import json
from pathlib import Path

import pytest

from runtime_common import sha256_file
from verification_common import (HARD_BUDGET, evidence_paths, evidence_paths_for_request,
                                 input_manifest, limited_source_document, repository_source_paths,
                                 serialization_forecast, serialized_json, serialized_request_bytes)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')
    return path


def binding(path):
    return {'path': str(path.resolve()), 'sha256': sha256_file(path)}


def budget(**overrides):
    return {**HARD_BUDGET, **overrides}


def test_constructed_probe_discovers_external_profiles_without_hashing(tmp_path, monkeypatch):
    root = tmp_path / 'project'
    root.mkdir()
    outside = write_json(tmp_path / 'qualification' / 'a.json', {})
    e = write_json(tmp_path / 'qualification' / 'e.json', {})
    request = {'bindings': {'environment_profile': binding(outside), 'simulation_profile': binding(e)}}
    monkeypatch.setattr('verification_common.sha256_file', lambda path: pytest.fail('discovery must not hash'))
    paths = evidence_paths_for_request(request, root, budget(), role='qualification_h_request', include_repository_sources=False)
    assert paths == {outside, e}
    assert paths.allowed_external == {outside, e}


@pytest.mark.parametrize('filename', ['h-analysis-input.json', 'h-analysis-profile-receipt.json'])
def test_ordinary_source_filename_never_authorizes_external_qualification(tmp_path, filename):
    root = tmp_path / 'project'
    root.mkdir()
    outside = write_json(tmp_path / 'qualification' / 'profile.json', {})
    source = write_json(root / filename, {'sources': [{'id': 'external', **binding(outside)}]})
    with pytest.raises(ValueError, match='leaves project root'):
        evidence_paths([source], root, budget())


def test_complete_native_artifact_preflight_precedes_any_hash(tmp_path, monkeypatch):
    artifact = tmp_path / 'numeric.mat'
    artifact.write_bytes(b'x' * 1025)
    receipt = write_json(tmp_path / 'receipt.json', {'artifacts': {'data': {'file': artifact.name, 'sha256': '0' * 64}}})
    monkeypatch.setattr('verification_common.sha256_file', lambda path: pytest.fail('no hash before aggregate preflight'))
    with pytest.raises(ValueError, match='file byte budget'):
        input_manifest(evidence_paths([receipt], tmp_path, budget(max_file_bytes=1024),
                                     root_contexts={receipt: 'h_trial_receipt'}, include_repository_sources=False), tmp_path, budget(max_file_bytes=1024))


def test_constructed_request_cannot_create_artifact_authority(tmp_path):
    with pytest.raises(ValueError, match='unpersisted artifact'):
        evidence_paths_for_request({'artifacts': {'input': {'file': 'nonexistent.json'}}}, tmp_path,
                                  budget(), include_repository_sources=False)


def test_repeated_trial_and_study_bindings_deduplicate_physical_files(tmp_path):
    study = write_json(tmp_path / 'study.json', {})
    request = write_json(tmp_path / 'trial-input.json', {'bindings': {'study': binding(study)}})
    trial = write_json(tmp_path / 'trial.json', {'artifacts': {'input': {'file': request.name}}})
    study_request = write_json(tmp_path / 'study-input.json', {'study': binding(study), 'trial_receipts': [binding(trial), binding(trial)]})
    # Read-set deduplication does not deduplicate native occurrences: the study
    # consumer separately verifies every ordered occurrence and its design role.
    total = sum(path.stat().st_size for path in (study, trial, request, study_request))
    paths = evidence_paths([study_request], tmp_path, budget(max_total_bytes=total), root_contexts={study_request: 'h_study_request'}, include_repository_sources=False)
    manifest = input_manifest(paths, tmp_path, budget(max_total_bytes=total))
    assert {item['path'] for item in manifest} == {str(path) for path in (study, trial, request, study_request)}
    assert sum(item['bytes'] for item in manifest) == total


def test_h2_required_study_follows_real_h_qualification_edges(tmp_path):
    root = tmp_path / 'project'
    root.mkdir()
    external = tmp_path / 'qualification'
    a = write_json(external / 'a.json', {})
    e = write_json(external / 'e.json', {})
    h = write_json(external / 'h.json', {})
    q_input = write_json(external / 'h-input.json', {'bindings': {'environment_profile': binding(a), 'simulation_profile': binding(e)}})
    q_receipt = write_json(external / 'h-receipt.json', {'artifacts': {'input': {'file': q_input.name}, 'profile': {'file': h.name}}})
    trial_input = write_json(root / 'trial-input.json', {'bindings': {'h_analysis_profile': binding(h), 'h_analysis_profile_receipt': binding(q_receipt)}})
    trial = write_json(root / 'trial.json', {'artifacts': {'input': {'file': trial_input.name}}})
    study = write_json(root / 'study.json', {})
    study_input = write_json(root / 'study-input.json', {'trial_receipts': [binding(trial)]})
    study_receipt = write_json(root / 'study-receipt.json', {'artifacts': {'input': {'file': study_input.name}}})
    h2 = write_json(root / 'h2.json', {'claims': [{'study_requirements': [{'study_contract': binding(study), 'study_receipt': binding(study_receipt)}]}]})
    paths = evidence_paths([h2], root, budget(), root_contexts={h2: 'h2_contract'}, include_repository_sources=False)
    manifest = input_manifest(paths, root, budget())
    assert {a, e, h, q_input, q_receipt} <= paths.allowed_external
    assert len(manifest) == 11


def test_aggregate_file_count_blocks_before_hash(tmp_path, monkeypatch):
    files = [write_json(tmp_path / (str(index) + '.json'), {}) for index in range(3)]
    monkeypatch.setattr('verification_common.sha256_file', lambda path: pytest.fail('file-count preflight must precede hashing'))
    with pytest.raises(ValueError, match='file count'):
        input_manifest(files, tmp_path, budget(max_files=2))


def test_discovery_edge_budget_limits_large_binding_graph(tmp_path):
    files = [write_json(tmp_path / (str(index) + '.json'), {}) for index in range(3)]
    source = write_json(tmp_path / 'source.json', {'sources': [binding(path) for path in files]})
    with pytest.raises(ValueError, match='edge budget'):
        evidence_paths([source], tmp_path, budget(max_edges=2))


def test_document_depth_budget_blocks_deep_structured_sources(tmp_path):
    source = write_json(tmp_path / 'source.json', {'values': [[[[1]]]]})
    with pytest.raises(ValueError, match='node/depth budget'):
        limited_source_document(source, budget(max_document_depth=3))


def test_yaml_alias_cycles_and_expansion_are_bounded(tmp_path):
    source = tmp_path / 'source.yaml'
    source.write_text('values: &loop [*loop]\n', encoding='utf-8')
    with pytest.raises(ValueError, match='cyclic'):
        limited_source_document(source)
    source.write_text('first: &a [1, 2, 3]\nsecond: &b [*a, *a, *a]\nthird: [*b, *b, *b]\n', encoding='utf-8')
    # Shared input reading has a finite physical-node budget; actual emitted
    # JSON has an independent expansion budget. Neither truncates an alias.
    value = limited_source_document(source, budget(max_document_nodes=25))
    with pytest.raises(ValueError, match='node'):
        serialization_forecast(value, budget(max_document_nodes=25))


def test_claimed_external_duplicate_is_only_an_independent_byte_claim(tmp_path):
    root = tmp_path / 'project'
    root.mkdir()
    external = write_json(tmp_path / 'qualified' / 'h.json', {})
    request = write_json(root / 'input.json', {'bindings': {
        'h_analysis_profile': binding(external), 'bound_files': [binding(external)],
        'protected_files': [binding(external)]}})
    paths = evidence_paths([request], root, budget(), root_contexts={request: 'h_trial_request'}, include_repository_sources=False)
    assert external in paths.allowed_external
    input_manifest(paths, root, budget())
    orphan = write_json(external.parent / 'unselected.json', {})
    value = json.loads(request.read_text())
    value['bindings']['protected_files'].append(binding(orphan))
    write_json(request, value)
    with pytest.raises(ValueError, match='independently authorized'):
        evidence_paths([request], root, budget(), root_contexts={request: 'h_trial_request'}, include_repository_sources=False)
    value['bindings']['protected_files'] = [{'path': str(external), 'sha256': '0' * 64}]
    value['bindings']['bound_files'] = []
    write_json(request, value)
    paths = evidence_paths([request], root, budget(), root_contexts={request: 'h_trial_request'}, include_repository_sources=False)
    with pytest.raises(ValueError, match='claimed byte identity'):
        input_manifest(paths, root, budget())


@pytest.mark.parametrize('role', ['h_trial_request', 'h_study_request'])
def test_explicit_caller_state_edge_protects_bytes_without_qualification_privilege(tmp_path, role):
    root = tmp_path / 'project'
    root.mkdir()
    external = write_json(tmp_path / 'qualification' / 'external.json', {})
    state = write_json(root / 'state.json', {'bindings': {'h_analysis_profile': binding(external)}})
    request = {'bindings': {'current_state': binding(state), 'protected_files': [binding(state)]}}
    paths = evidence_paths_for_request(request, root, budget(), role=role, include_repository_sources=False)
    assert paths == {state} and not paths.allowed_external
    input_manifest(paths, root, budget())
    request['bindings']['protected_files'].append(binding(external))
    with pytest.raises(ValueError, match='independently authorized'):
        evidence_paths_for_request(request, root, budget(), role=role, include_repository_sources=False)
    state.write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='claimed byte identity'):
        input_manifest(paths, root, budget())


def test_new_h_repository_bytes_are_statted_before_any_digest(tmp_path, monkeypatch):
    source = write_json(tmp_path / 'study.json', {})
    sources = repository_source_paths()
    source_bytes = sum(path.stat().st_size for path in sources)
    monkeypatch.setattr('verification_common.sha256_file', lambda path: pytest.fail('source preflight must precede any digest'))
    with pytest.raises(ValueError, match='byte budget'):
        evidence_paths([source], tmp_path, budget(max_total_bytes=source_bytes - 1), root_contexts={source: 'h_study_contract'})
    paths = evidence_paths([source], tmp_path, budget(), root_contexts={source: 'h_study_contract'})
    assert set(sources) <= paths and set(sources) <= paths.allowed_external


def test_known_source_authority_cannot_change_during_merged_manifest_hashing(tmp_path, monkeypatch):
    import verification_common as common
    authority = write_json(tmp_path / 'authority.json', {'source_files': ['leaf.txt']})
    leaf = tmp_path / 'leaf.txt'
    leaf.write_text('original', encoding='utf-8')
    paths = common.EvidencePaths([authority, leaf])
    paths.source_authorities.append(common.RepositorySourcePaths([authority, leaf], authority, authority.read_bytes()))
    # Native consumers merge persisted and constructed read sets; that merge
    # must preserve the independently selected source-list identity guard.
    merged = common.EvidencePaths()
    merged.update(common.EvidencePaths(paths))
    original_hash = common.sha256_file

    def change_authority(path):
        digest = original_hash(path)
        if path == leaf:
            write_json(authority, {'source_files': ['unselected.txt']})
        return digest

    monkeypatch.setattr(common, 'sha256_file', change_authority)
    with pytest.raises(ValueError, match='source authority changed'):
        input_manifest(merged, tmp_path, budget())


def test_exact_serialized_request_forecast_includes_virtual_file_and_utf8(tmp_path):
    leaf = tmp_path / 'input.txt'
    leaf.write_bytes(b'original')
    shared = {'variable': '温度', 'levels': [0.0, 1.0, None]}
    request = {'groups': [shared, shared], 'bindings': {}}
    expected = serialized_json(request)
    forecast = serialization_forecast(request, budget())
    assert forecast['bytes'] == len(expected)
    assert serialized_request_bytes(request, [leaf], tmp_path, budget()) == expected
    with pytest.raises(ValueError, match='complete input byte'):
        serialized_request_bytes(request, [leaf], tmp_path, budget(max_total_bytes=len(expected) + leaf.stat().st_size - 1))
    with pytest.raises(ValueError, match='bytes/node/depth'):
        serialized_request_bytes(request, [leaf], tmp_path, budget(max_file_bytes=len(expected) - 1))


def test_large_alias_is_read_once_but_cannot_be_serialized_unbounded(tmp_path, monkeypatch):
    source = tmp_path / 'shared.yaml'
    source.write_text('leaf: &a0 [1]\n' + ''.join(f'level{i}: &a{i} [*a{i-1}, *a{i-1}]\n' for i in range(1, 25)), encoding='utf-8')
    value = limited_source_document(source)
    assert value['level24'][0] is value['level24'][1]
    monkeypatch.setattr('verification_common.serialized_json', lambda value: pytest.fail('large expansion must fail before allocation'))
    with pytest.raises(ValueError, match='expanded'):
        serialized_request_bytes(value, [], tmp_path, budget())


@pytest.mark.parametrize('scope', ['simulation', 'numerical_verification', 'h_analysis_study', 'model_verification'])
def test_partial_scopes_leave_current_h_qualification_unassessed(tmp_path, scope):
    from validate_project_state import validate_project_state
    invalid_profile = write_json(tmp_path / 'expired-h-profile.json', {})
    state = write_json(tmp_path / 'state.json', {'schema_version': 1, 'project_id': 'Synthetic',
        'project_root': '.', 'current_stage': 'NEW', 'environment': None, 'artefacts': [],
        'h_analysis_environment': {'profile_path': invalid_profile.name, 'profile_sha256': sha256_file(invalid_profile), 'receipt_sha256': '0' * 64},
        'h_analysis_studies': []})
    report = validate_project_state(state, scope=scope)
    assert report['valid'], report['errors']
    assert report['h_analysis_environment_checked'] is False
    assert report['environment_checked'] is False
    assert report['h_analysis_checked'] is (scope in {'h_analysis_study', 'model_verification'})


def test_h2_requires_the_exact_study_ancestors_not_just_matching_roles(tmp_path):
    from model_verification_state import validate_artifact
    study = write_json(tmp_path / 'study.json', {})
    receipt = write_json(tmp_path / 'study-receipt.json', {})
    h2 = write_json(tmp_path / 'h2.json', {})
    wrong = write_json(tmp_path / 'other-study.json', {})
    parents = {'problem', 'model', 'approval', 'mapping', 'protocol', 'primary_run',
               'numerical_verification', 'numerical_verification_receipt', 'model_verification'}
    item = {'id': 'H2', 'role': 'model_verification_contract', 'path': str(h2), 'sha256': sha256_file(h2),
            'status': 'accepted', 'depends_on': list(parents) + ['Study', 'StudyEvidence']}
    study_item = {'id': 'Study', 'role': 'h_analysis_study', 'path': str(wrong), 'sha256': sha256_file(wrong), 'status': 'accepted', 'depends_on': []}
    evidence_item = {'id': 'StudyEvidence', 'role': 'h_analysis_study_evidence', 'path': str(receipt), 'sha256': sha256_file(receipt), 'status': 'accepted', 'depends_on': []}
    state = {'model_verification': binding(h2), 'artefacts': [item, study_item, evidence_item]}
    result = {'model_verification_path': str(h2), 'model_verification_reviewed': True, 'numerically_verified': True,
        'model_verification_validation': {'study_reports': [{'id': 'sobol', 'requirement': 'required',
            'study_contract_path': str(study), 'study_contract_sha256': sha256_file(study),
            'study_receipt_path': str(receipt), 'study_receipt_sha256': sha256_file(receipt)}]}}
    roles = lambda artifact: {'simulation_protocol', 'simulation_run', 'numerical_verification_evidence'}
    errors = validate_artifact(item, state=state, result=result, root=tmp_path,
                               environment_dependents=set(), ancestor_roles=roles)
    assert any('exact source-required h_analysis_study ancestor' in error for error in errors)
    study_item.update(path=str(study), sha256=sha256_file(study))
    assert validate_artifact(item, state=state, result=result, root=tmp_path,
                             environment_dependents=set(), ancestor_roles=roles) == []


@pytest.fixture(scope='module')
def full_wire_history(tmp_path_factory):
    """One native-format baseline/study/H2; no substituted success reports."""
    from h_analysis_study_factory import make_study_for_primary, make_study_history
    from model_factory import file_ref
    from model_verification_common import KINDS
    from model_verification_factory import omitted, review_model_verification
    from problem_factory import write_contract
    from run_model_verification import run_model_verification
    from runtime_common import load_document
    from test_mapping_state import d_artefact
    from test_verification_routing_state import synthetic_h1_state

    root = tmp_path_factory.mktemp('SYNTHETIC-H-integration-full-wire')
    state_path, h1_contract, runs, h1_receipt = synthetic_h1_state(root)
    study = make_study_for_primary(h1_receipt, project_root=root)
    study_receipt = make_study_history(study, project_root=root)
    project_id = load_document(h1_contract)['project_id']
    obligation = {'id': 'parameter_response', 'method': 'scenario_response', 'requirement': 'required',
                  'reason': 'SYNTHETIC prior finite parameter study required for this infrastructure claim.',
                  'study_contract': file_ref(root, study), 'study_receipt': file_ref(root, study_receipt)}
    value = {'schema_version': 1, 'project_id': project_id, 'status': 'draft',
             'primary_numerical_receipt': file_ref(root, h1_receipt), 'members': [],
             'claims': [{'id': 'finite_response', 'target_claim': 'SYNTHETIC required finite hypothetical parameter response.',
                        'requirement_ids': ['R5'], 'obligation_source_ref': {'source_id': 'settings', 'selector': ['obligations', 'finite_response']},
                        'analyses': [omitted(kind) for kind in KINDS], 'study_requirements': [obligation],
                        'failure_disposition': 'modify', 'impact_scope': 'Only these two finite hypothetical points',
                        'required_action': 'Return to the explicitly reviewed finite claim', 'return_stage': 'C',
                        'claim_limit': 'SYNTHETIC infrastructure only; no real approval or physical validity.'}],
             'sources': [], 'settings_source_ref': None, 'budget': budget(),
             'claim_limit': 'SYNTHETIC complete finite parameter catalog only; no automatic adoption.', 'review_record': None}
    h2 = write_contract(root / 'full-wire-h2.json', value)
    review_model_verification(h2)
    assessment = run_model_verification(h2, root / 'full-wire-h2-evidence', project_root=root)
    assert assessment['valid'] and assessment['model_verified'], assessment['errors']
    h2_receipt = Path(assessment['receipt_path'])
    state = load_document(state_path)
    state['current_stage'] = 'MODEL_VERIFIED'
    state['h_analysis_studies'] = [{'id': obligation['id'], 'study': file_ref(root, study), 'receipt': file_ref(root, study_receipt)}]
    base_parents = ['problem', 'model', 'approval', 'mapping', 'protocol', 'primary_run',
                    'numerical_verification', 'numerical_verification_receipt']
    study_parents = base_parents + ['h_analysis_studies', 'h1-evidence-record']
    state['artefacts'].extend([
        d_artefact(root, study, 'h_analysis_study', 'study-contract', study_parents),
        d_artefact(root, study_receipt, 'h_analysis_study_evidence', 'study-evidence', study_parents + ['study-contract'])])
    for anchor, path in [('model_verification', h2), ('model_verification_receipt', h2_receipt)]:
        state[anchor] = file_ref(root, path)
    h2_parents = base_parents + ['model_verification', 'h1-evidence-record', 'study-contract', 'study-evidence']
    state['artefacts'].extend([
        d_artefact(root, h2, 'model_verification_contract', 'h2-contract', h2_parents),
        d_artefact(root, h2_receipt, 'model_verification_evidence', 'h2-evidence', h2_parents + ['model_verification_receipt', 'h2-contract'])])
    e_request = load_document(runs[0].parent / 'simulation-inputs.json')
    structure = next(item for item in state['artefacts'] if item['role'] == 'structure_evidence')
    d_request = load_document((root / structure['path']).parent / 'inputs.json')
    profiles = {'environment': e_request['bindings']['environment_profile'],
                'simulation_environment': e_request['bindings']['simulation_profile'],
                'implementation_environment': d_request['bindings']['implementation_profile'],
                'h_analysis_environment': {'path': str(root / 'synthetic-h-profile/h-analysis-profile.json')}}
    filenames = {'environment': 'receipt.json', 'simulation_environment': 'simulation-profile-receipt.json',
                 'implementation_environment': 'implementation-profile-receipt.json',
                 'h_analysis_environment': 'h-analysis-profile-receipt.json'}
    for anchor, item in profiles.items():
        path = Path(item['path'])
        state[anchor] = {'profile_path': path.relative_to(root).as_posix(), 'profile_sha256': sha256_file(path),
                         'receipt_sha256': sha256_file(path.parent / filenames[anchor])}
    write_contract(state_path, state)
    return {'root': root, 'state': state_path, 'study': study, 'study_receipt': study_receipt,
            'h2': h2, 'h2_receipt': h2_receipt, 'profiles': {key: Path(item['path']) for key, item in profiles.items()}}


def test_actual_required_study_state_and_readonly_route_keep_primary_and_runtime_boundaries(full_wire_history):
    from resolve_runtime import resolve_runtime
    from runtime_common import load_document
    from validate_project_state import validate_project_state
    item = full_wire_history
    state = load_document(item['state'])
    guarded = {path: sha256_file(path) for path in item['root'].rglob('*') if path.is_file()}
    report = validate_project_state(item['state'], scope='model_verification')
    assert report['valid'] and report['model_verified'], report['errors']
    assert report['numerically_verified'] and report['primary_run_complete'] and report['h_analysis_checked']
    assert report['h_analysis_studies'][0]['study_complete'] and report['h_analysis_studies'][0]['study_accepted']
    assert all(report[flag] is False for flag in ('environment_checked', 'implementation_environment_checked',
                                               'simulation_environment_checked', 'h_analysis_environment_checked'))
    route = resolve_runtime('h_analysis_study_review', state_path=item['state'], project_root=item['root'],
                            h_analysis_study_path=item['study'])
    assert route['status'] == 'inspected' and route['study_complete'], route['errors']
    assert all(route[flag] is False for flag in ('execution_allowed', 'business_execution_allowed',
                                             'simulation_execution_allowed', 'h_analysis_execution_allowed', 'state_mutated'))
    for intent in ('sensitivity_analysis', 'robustness_analysis'):
        named = resolve_runtime(intent, model_verification_path=item['h2'], project_root=item['root'])
        assert named['status'] == 'inspected' and named['required_study_methods'] == ['scenario_response'], named['errors']
        assert not named['execution_allowed'] and not named['h_analysis_execution_allowed'] and 'state_validation' not in named
    current = validate_project_state(item['state'], scope='all')
    assert current['valid'] and current['model_verified'], current['errors']
    assert all(current[flag] is True for flag in ('environment_checked', 'implementation_environment_checked',
                                               'simulation_environment_checked', 'h_analysis_environment_checked'))
    assert load_document(item['state'])['primary_run'] == state['primary_run']
    assert all(sha256_file(path) == sha for path, sha in guarded.items())


def test_actual_source_required_study_needs_exact_accepted_ancestry(full_wire_history):
    from problem_factory import write_contract
    from runtime_common import load_document
    from validate_project_state import validate_project_state
    path = full_wire_history['state']
    original = path.read_bytes()
    try:
        value = load_document(path)
        for artifact in value['artefacts']:
            if artifact['role'] in {'model_verification_contract', 'model_verification_evidence'}:
                artifact['depends_on'] = [identity for identity in artifact['depends_on'] if identity != 'study-evidence']
        write_contract(path, value)
        report = validate_project_state(path, scope='model_verification')
        assert not report['valid'] and not report['model_verified']
        assert any('exact source-required h_analysis_study_evidence ancestor' in error for error in report['errors'])
    finally:
        path.write_bytes(original)


def test_actual_trial_route_preserves_extra_A_and_blocks_missing_comparator_solver(full_wire_history):
    from copy import deepcopy
    from h_analysis_study import generate_design
    from h_analysis_study_factory import review_h_analysis_study
    from problem_factory import write_contract
    from resolve_runtime import resolve_runtime
    from runtime_common import load_document
    from test_runtime import make_profile
    from test_simulation_assurance import make_simulation_profile, _rebind
    item = full_wire_history
    root, profiles = item['root'], item['profiles']
    arguments = {'project_root': root, 'h_analysis_study_path': item['study'],
                 'profile_path': profiles['environment'], 'simulation_profile_path': profiles['simulation_environment'],
                 'h_analysis_profile_path': profiles['h_analysis_environment']}
    allowed = resolve_runtime('h_analysis_trials', required_operations=['statistics.normcdf', 'simulink.core_simulation', 'h.analysis_trials'], **arguments)
    assert allowed['status'] == 'allowed' and allowed['h_analysis_execution_allowed'], allowed['errors']
    assert 'statistics.normcdf' in allowed['required_A_operations']
    assert not {'simulink.core_simulation', 'h.analysis_trials'} & set(allowed['required_A_operations'])
    assert allowed['required_solvers'] == ['ode4'] and not allowed['state_mutated'] and not allowed['simulation_execution_allowed']
    missing_a = make_profile(root / 'unavailable-extra-a', include_statistics=False)
    blocked = resolve_runtime('h_analysis_trials', required_operations=['statistics.fitlm'], **{**arguments, 'profile_path': missing_a})
    assert blocked['status'] == 'blocked' and not blocked['h_analysis_execution_allowed']
    assert 'statistics.fitlm' in blocked['selected_operations']
    # This new current E profile truthfully fails the ode45 assertion while
    # retaining its real ode4 qualification. Original history stays immutable.
    partial_e = make_simulation_profile(root / 'current-E-without-ode45', profiles['environment'])
    raw_path = partial_e.parent / 'raw-simulation.json'
    raw = load_document(raw_path)
    raw['cases'][0]['observed_solver_name'] = 'ode15s'
    write_json(raw_path, raw)
    _rebind(partial_e, derive=True)
    value = load_document(item['study'])
    adaptive = deepcopy(value['numerical_policy'])
    adaptive['method'] = 'ode45_tolerance_refinement'
    adaptive['solver_levels'] = [{'name': 'ode45', 'type': 'variable-step', 'fixed_step': None, 'max_step': 0.1,
        'min_step': 1e-9, 'initial_step': 0.01, 'rel_tol': 1e-4 / 10**index,
        'abs_tol': 1e-6 / 10**index, 'zero_crossing': 'EnableAll'} for index in range(3)]
    value['method'] = 'runtime_comparison'
    value['settings'] = {'configurations': [{'id': 'fixed', 'numerical_policy': deepcopy(value['numerical_policy'])},
                                           {'id': 'adaptive', 'numerical_policy': adaptive}],
        'repetitions': 2, 'order': ['fixed', 'adaptive', 'adaptive', 'fixed'],
        'comparison': {'reference': 'fixed', 'alternatives': ['adaptive'], 'timing_field': 'TotalElapsedWallTime',
                       'statistic': 'median', 'zero_denominator': 'undefined', 'level_index': 2},
        'metric_comparison': {'absolute_tolerance': 1e-4, 'relative_tolerance': 0.}}
    value['design'] = generate_design(value['method'], value['factors'], value['settings'], budget=value['budget'])
    runtime_study = write_contract(root / 'runtime-comparator-study.json', value)
    review_h_analysis_study(runtime_study, project_root=root)
    missing_solver = resolve_runtime('h_analysis_trials', **{**arguments, 'h_analysis_study_path': runtime_study, 'simulation_profile_path': partial_e})
    assert missing_solver['status'] == 'blocked' and not missing_solver['h_analysis_execution_allowed']
    assert missing_solver['required_solvers'] == ['ode4', 'ode45']
    assert missing_solver['missing_gates'] == ['h_analysis_solver_union']
    assert any('E lacks actual required solver qualification: ode45' in error for error in missing_solver['errors'])
