"""Labelled synthetic H2 histories; tests never approve or qualify real models."""
from __future__ import annotations

import copy
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

from model_factory import file_ref
from numerical_factory import export_case, freeze_level, make_numerical_runs
from probe_environment import write_json
from problem_factory import write_contract
from run_numerical_verification import run_numerical_verification
from runtime_common import load_document
from test_simulation_assurance import synthetic_case
from validate_environment import utc_text
from validate_numerical_verification import SETTINGS_FIELDS, uniform_grid
from validate_simulation_profile import contract as e_contract
from validate_simulation_protocol import validate_simulation_protocol
from verification_common import HARD_BUDGET, semantic_digest
from model_verification_common import KINDS, obligation_snapshot, settings_snapshot


def review_model_verification(path, *, refresh_settings=True, refresh_obligations=True):
    path, root = Path(path), Path(path).parent
    value = load_document(path)
    source_path = root / 'model-verification-settings.json'
    source = load_document(source_path) if source_path.exists() else {}
    if refresh_settings:
        source['settings'] = settings_snapshot(value)
    if refresh_obligations:
        source['obligations'] = {claim['id']: obligation_snapshot(claim) for claim in value['claims']}
    write_contract(source_path, source)
    value['sources'] = [{'id': 'settings', **file_ref(root, source_path), 'purpose': 'SYNTHETIC H2 settings/obligations only'}]
    value['settings_source_ref'] = {'source_id': 'settings', 'selector': ['settings']}
    digest = semantic_digest(value)
    quote = (f"project_id={value['project_id']}\nverification_semantic_sha256={digest}\n"
             'reviewed_by=synthetic-h2-reviewer\naction=review\n'
             'SYNTHETIC INFRASTRUCTURE TEST ONLY; no real approval, qualification or physical validity.')
    decision = root / 'model-verification-review-decision.txt'
    decision.write_text(quote + '\n', encoding='utf-8')
    record = write_contract(root / 'model-verification-review.json', {
        'schema_version': 1, 'project_id': value['project_id'], 'verification_semantic_sha256': digest,
        'decision': {**file_ref(root, decision), 'start': 0, 'end': len(quote), 'quote': quote,
                     'reviewed_by': 'synthetic-h2-reviewer', 'action': 'review'}})
    value.update(status='reviewed', review_record=file_ref(root, record))
    return write_contract(path, value)


def omitted(kind):
    return {'kind': kind, 'requirement': 'not_applicable' if kind == 'model_comparison' else 'not_required',
            'reason': 'The finite synthetic input-response claim requires no ' + kind + ' evidence.',
            'method': None, 'member_ids': [], 'metric': None, 'factor': None, 'bounds': None,
            'comparison': None, 'structural_review': None}


def _review_other_h1(path):
    root, value = Path(path).parent, load_document(path)
    stem = Path(path).stem
    source = write_contract(root / (stem + '-settings.json'), {'settings': {k: value[k] for k in SETTINGS_FIELDS}})
    value['sources'] = [{'id': 'settings', **file_ref(root, source), 'purpose': 'SYNTHETIC independent H1 review'}]
    value['settings_source_ref'] = {'source_id': 'settings', 'selector': ['settings']}
    digest = semantic_digest(value)
    quote = (f"project_id={value['project_id']}\nverification_semantic_sha256={digest}\n"
             'reviewed_by=synthetic-h2-member-reviewer\naction=review\nSYNTHETIC INFRASTRUCTURE TEST ONLY.')
    decision = root / (stem + '-decision.txt')
    decision.write_text(quote + '\n', encoding='utf-8')
    record = write_contract(root / (stem + '-review.json'), {
        'schema_version': 1, 'project_id': value['project_id'], 'verification_semantic_sha256': digest,
        'decision': {**file_ref(root, decision), 'start': 0, 'end': len(quote), 'quote': quote,
                     'reviewed_by': 'synthetic-h2-member-reviewer', 'action': 'review'}})
    value.update(status='reviewed', review_record=file_ref(root, record))
    return write_contract(path, value)


def make_model_verification_contract(root):
    """Return two accepted labelled synthetic H1 participants sharing exact C/D."""
    from run_simulation import finish_task_request, make_task_request
    root = Path(root).resolve()
    primary_path, primary_runs = make_numerical_runs(root)
    primary_h1 = run_numerical_verification(primary_path, primary_runs, root / 'h2-primary-h1', project_root=root)
    assert primary_h1['valid'] and primary_h1['numerically_verified'], primary_h1['errors']
    primary = load_document(primary_path)
    others = []
    for index, binding in enumerate([primary['primary_protocol'], *primary['refinement_protocols']]):
        value = load_document(root / binding['path'])
        input_data = copy.deepcopy(value['inputs'][0]['data'])
        input_data['value'] = 2.0
        source = write_contract(root / ('h2-input-2-' + str(index) + '.json'), {'u': input_data})
        value['inputs'][0]['data'] = input_data
        value['sources'] = [{**value['sources'][0], **file_ref(root, source)}]
        value.update(status='draft', freeze_record=None)
        path = write_contract(root / ('h2-input-2-protocol-' + str(index) + '.json'), value)
        others.append(freeze_level(path, root))
    other_h1_contract = copy.deepcopy(primary)
    other_h1_contract.update(primary_protocol=file_ref(root, others[0]),
        refinement_protocols=[file_ref(root, p) for p in others[1:]], status='draft', review_record=None)
    other_path = write_contract(root / 'h2-member-numerical.json', other_h1_contract)
    _review_other_h1(other_path)
    a = root / 'a-profile' / 'evidence' / 'profile.json'
    e = root / 'numerical-e-profile' / 'simulation-profile.json'
    names = e_contract()['evidence']
    # Producer profile filename is contractual, not inferred from a successful flag.
    e = root / 'numerical-e-profile' / names['profile']
    runs = []
    for index, protocol in enumerate(others):
        report = validate_simulation_protocol(protocol, project_root=root, require_frozen=True)
        assert report['valid'], report['errors']
        directory = root / ('h2-input-2-e-run-' + str(index))
        request = make_task_request(protocol, load_document(a)['runtime']['executable'], directory, report, a, e, project_root=root)
        directory.mkdir()
        write_json(directory / names['input'], request)
        (directory / names['log']).write_text('SYNTHETIC H2 E CHAIN; NO MATLAB EXECUTION.\n', encoding='utf-8')
        raw = load_document(e.parent / names['raw'])
        actual = synthetic_case(request['cases'][0], directory, request['run_id'], primary=True)
        spec = report['run_spec']
        times = uniform_grid(spec['start_time'], spec['stop_time'], spec['solver']['fixed_step'])
        parameters = {p['code_name']: p['value'] for p in spec['parameters']}
        decay, forcing = parameters['a'], parameters['b'] * 2.0
        offset = (1e-4, 6.25e-6, 3.90625e-7)[index]
        values = [forcing/decay + (0.25-forcing/decay)*math.exp(-decay*t) + offset*t for t in times]
        export_case(actual, directory, request['run_id'], times, values)
        reference = datetime.now(timezone.utc) - timedelta(seconds=0.05)
        raw.update(run_id=request['run_id'], input_identity=request['input_identity'], source_identity=request['source_identity'],
                   started_at=utc_text(reference), finished_at=utc_text(reference + timedelta(milliseconds=10)), cases=[actual])
        process = {'started_at': utc_text(reference-timedelta(milliseconds=5)), 'finished_at': utc_text(reference+timedelta(milliseconds=15)),
                   'process_state': 'completed', 'exit_code': 0, 'pid': 0, 'command': ['SYNTHETIC H2 TEST ONLY; NO MATLAB']}
        write_json(directory / names['raw'], raw)
        write_json(directory / names['process'], process)
        runs.append(finish_task_request(request, process))
    other_h1 = run_numerical_verification(other_path, runs, root / 'h2-member-h1', project_root=root)
    assert other_h1['valid'] and other_h1['numerically_verified'], other_h1['errors']
    metric = {'statistic': 'final', 'unit': '1', 'primary_output_port': 1,
              'member_output_ports': [{'member_id': 'input_two', 'output_port': 1}]}
    analyses = [omitted(kind) for kind in KINDS]
    analyses[0].update(requirement='required', method='external_input_oat', member_ids=['primary', 'input_two'],
        metric=metric, factor={'input_port': 1, 'variable_id': 'u', 'unit': '1', 'levels': [1.0, 2.0]},
        bounds={'lower': 0.0, 'upper': 2.0, 'unit': '1/1'})
    analyses[1].update(requirement='required', method='finite_scenarios', member_ids=['primary', 'input_two'],
                       metric=metric, bounds={'lower': 0.0, 'upper': 3.0, 'unit': '1'})
    value = {'schema_version': 1, 'project_id': primary['project_id'], 'status': 'draft',
             'primary_numerical_receipt': file_ref(root, Path(primary_h1['receipt_path'])),
             'members': [{'id': 'input_two', 'numerical_receipt': file_ref(root, Path(other_h1['receipt_path']))}],
             'claims': [{'id': 'finite_response', 'target_claim': 'Declared synthetic finite external-input response satisfies prior slope and point bounds.',
                        'requirement_ids': ['R5'], 'obligation_source_ref': {'source_id': 'settings', 'selector': ['obligations', 'finite_response']},
                        'analyses': analyses, 'failure_disposition': 'modify', 'impact_scope': 'Only this finite response catalog',
                        'required_action': 'Narrow the declared synthetic claim or return to model design', 'return_stage': 'C',
                        'claim_limit': 'Only these finite external inputs; no derivative, continuous robustness or physical truth.'}],
             'sources': [], 'settings_source_ref': None, 'budget': dict(HARD_BUDGET),
             'claim_limit': 'SYNTHETIC INFRASTRUCTURE TEST ONLY. Finite metrics with H1 scoped sample agreement; no reality validity.',
             'review_record': None}
    path = write_contract(root / 'model-verification.json', value)
    return review_model_verification(path)
