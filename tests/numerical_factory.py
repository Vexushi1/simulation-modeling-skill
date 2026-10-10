"""Complete labelled synthetic H1/E histories; no actual MATLAB qualification."""
from __future__ import annotations

import copy
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from scipy.io import savemat

from model_factory import file_ref
from probe_environment import write_json
from problem_factory import write_contract
from runtime_common import load_document, sha256_file
from simulation_factory import make_simulation_protocol
from test_simulation_assurance import make_simulation_profile, synthetic_case
from validate_environment import utc_text
from validate_numerical_verification import SETTINGS_FIELDS, uniform_grid
from validate_simulation_profile import contract as e_contract
from validate_simulation_protocol import semantic_digest as e_digest, validate_simulation_protocol
from verification_common import semantic_digest


def freeze_level(path, root):
    value = load_document(path)
    digest = e_digest(value)
    quote = (f"project_id={value['project_id']}\nprotocol_semantic_sha256={digest}\n"
             "reviewed_by=synthetic-h1-protocol-reviewer\naction=freeze\n"
             "SYNTHETIC INFRASTRUCTURE TEST ONLY; no real user approval or numerical acceptance.")
    decision = root / (path.stem + '-decision.txt')
    decision.write_text(quote + '\n', encoding='utf-8')
    record = write_contract(root / (path.stem + '-freeze.json'), {
        'schema_version': 1, 'project_id': value['project_id'], 'protocol_semantic_sha256': digest,
        'decision': {**file_ref(root, decision), 'start': 0, 'end': len(quote), 'quote': quote,
                     'reviewed_by': 'synthetic-h1-protocol-reviewer', 'action': 'freeze'}})
    value.update(status='frozen', freeze_record=file_ref(root, record))
    return write_contract(path, value)


def review_numerical(path, *, refresh_source=True):
    path = Path(path)
    value = load_document(path)
    root = path.parent
    if refresh_source:
        source = write_contract(root / 'numerical-settings.json', {'settings': {k: value[k] for k in SETTINGS_FIELDS}})
        value['sources'] = [{'id': 'settings', **file_ref(root, source), 'purpose': 'Synthetic complete H1 settings and obligation reasons'}]
        value['settings_source_ref'] = {'source_id': 'settings', 'selector': ['settings']}
    digest = semantic_digest(value)
    quote = (f"project_id={value['project_id']}\nverification_semantic_sha256={digest}\n"
             "reviewed_by=synthetic-h1-reviewer\naction=review\n"
             "SYNTHETIC INFRASTRUCTURE TEST ONLY: tests do not approve actual models or physical truth.")
    decision = root / 'numerical-review-decision.txt'
    decision.write_text(quote + '\n', encoding='utf-8')
    record = write_contract(root / 'numerical-review.json', {
        'schema_version': 1, 'project_id': value['project_id'], 'verification_semantic_sha256': digest,
        'decision': {**file_ref(root, decision), 'start': 0, 'end': len(quote), 'quote': quote,
                     'reviewed_by': 'synthetic-h1-reviewer', 'action': 'review'}})
    value.update(status='reviewed', review_record=file_ref(root, record))
    return write_contract(path, value)


def make_numerical_contract(root, *, method='ode4_step_refinement', reviewed=True, age_hours=0, qualification_root=None):
    root = Path(root).resolve()
    solver = 'ode4' if method == 'ode4_step_refinement' else 'ode45'
    base = make_simulation_protocol(root, solver=solver, age_hours=age_hours)
    source = load_document(base)
    if qualification_root is not None:
        # Create this new D/E chain against original external qualifications;
        # never move/rebind any already-produced historical evidence.
        from native_factory import make_implementation_profile, make_implementation_receipt
        from test_runtime import make_profile
        qualification_root = Path(qualification_root).resolve()
        a = make_profile(qualification_root / 'a-profile', include_statistics=True, age_hours=age_hours)
        d = make_implementation_profile(qualification_root / 'd-profile', a, age_hours=age_hours)
        mapping_path = root / source['mapping']['path']
        mapping = load_document(mapping_path)
        mapping.update(status='mapped', implementation=None)
        write_contract(mapping_path, mapping)
        receipt = make_implementation_receipt(root / 'implementation-external', mapping_path, a, d, age_hours=age_hours)
        mapping.update(status='ready', implementation=file_ref(root, receipt))
        write_contract(mapping_path, mapping)
        source['mapping'] = file_ref(root, mapping_path)
    if solver == 'ode4':
        source['solver']['fixed_step'] = 0.1
    protocols = []
    for index in range(3):
        value = copy.deepcopy(source)
        value.update(status='draft', freeze_record=None)
        if solver == 'ode4':
            value['solver']['fixed_step'] = source['solver']['fixed_step'] / (2 ** index)
        else:
            for key in ('rel_tol', 'abs_tol'):
                value['solver'][key] = source['solver'][key] / (10 ** index)
        path = write_contract(root / ('numerical-protocol-' + str(index) + '.json'), value)
        protocols.append(freeze_level(path, root))
    base_spec = validate_simulation_protocol(protocols[0], project_root=root, require_frozen=True)['run_spec']
    comparison = uniform_grid(0.0, 1.0, 0.1) if solver == 'ode4' else [0.0, 1.0]
    value = {'schema_version': 1, 'project_id': source['project_id'], 'status': 'draft',
             'primary_protocol': file_ref(root, protocols[0]), 'refinement_protocols': [file_ref(root, p) for p in protocols[1:]],
             'method': method, 'comparison_times': comparison,
             'outputs': [{**{k: output[k] for k in ('port', 'variable_id', 'unit')},
                          'absolute_tolerance': 0.001, 'relative_tolerance': 0.0,
                          'contraction_limit': 0.5, 'roundoff_floor': 1e-14} for output in base_spec['outputs']],
             'obligations': {name: {'status': 'not_applicable', 'reason': 'Synthetic finite endpoint/grid comparison imposes no separate ' + name + ' claim',
                                    'source_ids': ['settings']} for name in ('residual', 'constraint', 'conservation', 'event_localization', 'numerical_drift')},
             'budget': {'max_file_bytes': 67108864, 'max_total_bytes': 268435456,
                        'max_samples_per_output': 12001, 'max_result_bytes': 4194304},
             'claim_limit': 'Only synthetic three-level sample agreement on the declared finite grid; no physical validity or true error bound.',
             'sources': [], 'settings_source_ref': None, 'review_record': None}
    path = write_contract(root / 'numerical-verification.json', value)
    if reviewed:
        review_numerical(path)
    return path


def export_case(actual, directory, run_id, times, values):
    actual['saved_time'] = times
    for output in actual['outputs']:
        output.update(time=times, values=values)
        (directory / output['csv_file']).write_text(''.join(format(t, '.17g') + ',' + format(v, '.17g') + '\n' for t, v in zip(times, values)), encoding='utf-8')
    write_json(directory / actual['data_file'], {'schema_version': 1, 'run_id': run_id, 'outputs': actual['outputs']})
    count = len(actual['outputs'])
    variables, units, mt, mv = (np.empty((count, 1), dtype=object) for _ in range(4))
    for index, output in enumerate(actual['outputs']):
        variables[index, 0], units[index, 0] = output['variable_id'], output['unit'] or ''
        mt[index, 0], mv[index, 0] = np.array(times).reshape(-1, 1), np.array(values).reshape(-1, 1)
    savemat(directory / actual['mat_file'], {'run_id': run_id, 'output_ports': np.array([o['port'] for o in actual['outputs']], dtype=float).reshape(-1, 1),
            'output_variables': variables, 'output_units': units, 'output_times': mt, 'output_values': mv, 'saved_time': np.array(times).reshape(-1, 1)}, format='5')


def make_numerical_runs(root, *, method='ode4_step_refinement', offsets=(1e-4, 6.25e-6, 3.90625e-7), age_hours=0, qualification_root=None):
    """A labelled complete E chain exercises independent consumer composition."""
    from run_simulation import finish_task_request, make_task_request
    path = make_numerical_contract(root, method=method, age_hours=age_hours, qualification_root=qualification_root)
    root, value = path.parent, load_document(path)
    qualification = Path(qualification_root).resolve() if qualification_root is not None else root
    a = qualification / 'a-profile' / 'evidence' / 'profile.json'
    e = make_simulation_profile(qualification / 'numerical-e-profile', a, age_hours=age_hours)
    receipts = []
    protocols = [value['primary_protocol'], *value['refinement_protocols']]
    for index, binding in enumerate(protocols):
        protocol = root / binding['path']
        report = validate_simulation_protocol(protocol, project_root=root, require_frozen=True)
        assert report['valid'], report['errors']
        directory = root / ('numerical-e-run-' + str(index))
        request = make_task_request(protocol, load_document(a)['runtime']['executable'], directory, report, a, e, project_root=root)
        directory.mkdir()
        names = e_contract()['evidence']
        write_json(directory / names['input'], request)
        (directory / names['log']).write_text('SYNTHETIC H1 E CHAIN; NO MATLAB EXECUTION.\n', encoding='utf-8')
        raw = load_document(e.parent / names['raw'])
        actual = synthetic_case(request['cases'][0], directory, request['run_id'], primary=True)
        spec = report['run_spec']
        times = uniform_grid(spec['start_time'], spec['stop_time'], spec['solver']['fixed_step']) if method == 'ode4_step_refinement' else [i / 100 for i in range(101)]
        parameters = {p['code_name']: p['value'] for p in spec['parameters']}
        decay, forcing = parameters['a'], parameters['b']
        values = [forcing/decay + (0.25-forcing/decay)*math.exp(-decay*t) + offsets[index]*t for t in times]
        export_case(actual, directory, request['run_id'], times, values)
        reference = datetime.now(timezone.utc) - timedelta(hours=age_hours, seconds=0.05)
        raw.update(run_id=request['run_id'], input_identity=request['input_identity'], source_identity=request['source_identity'],
                   started_at=utc_text(reference), finished_at=utc_text(reference + timedelta(milliseconds=10)), cases=[actual])
        process = {'started_at': utc_text(reference-timedelta(milliseconds=5)), 'finished_at': utc_text(reference+timedelta(milliseconds=15)),
                   'process_state': 'completed', 'exit_code': 0, 'pid': 0, 'command': ['SYNTHETIC INFRASTRUCTURE TEST ONLY; NO MATLAB']}
        write_json(directory / names['raw'], raw)
        write_json(directory / names['process'], process)
        receipts.append(finish_task_request(request, process))
    return path, receipts
