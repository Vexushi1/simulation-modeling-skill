"""Qualify h.analysis_trials using one real serial owned MATLAB batch."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import uuid

from h_analysis_trial import (artifact_manifest, contract, execute_request, file_binding,
                             physical_snapshot, preflight_request, source_identities, stable_utc)
from probe_environment import write_json
from runtime_common import canonical_digest, emit, host_fingerprint, load_document
from validate_environment import _time


def _solver(name, level):
    fixed = name == 'ode4'
    rel = 1e-3 / (10 ** level)
    return {'name': name, 'type': 'fixed-step' if fixed else 'variable-step',
            'max_step': None if fixed else 2.0, 'min_step': None if fixed else 1e-9,
            'initial_step': None if fixed else 0.02, 'rel_tol': None if fixed else rel,
            'abs_tol': None if fixed else (1e-3 / 10) / (10 ** level), 'fixed_step': 0.1 / (2 ** level) if fixed else None,
            'zero_crossing': 'DisableAll'}


def _numeric_policy(name, states):
    criteria = {'absolute_tolerance': 0.001, 'relative_tolerance': 0.0, 'contraction_limit': 0.9, 'roundoff_floor': 1e-12}
    outputs = [{'port': 1, 'variable_id': 'y', 'unit': '1', **criteria}]
    outputs.extend({'kind': 'state', **state, **criteria} for state in states)
    return {'method': name + ('_step_refinement' if name == 'ode4' else '_tolerance_refinement'),
            'scope': 'actual_points', 'solver_levels': [_solver(name, i) for i in range(3)],
            'comparison_times': [i * 0.1 for i in range(21)] if name == 'ode4' else [0.0, 2.0],
            'outputs': outputs,
            'obligations': {kind: {'status': 'not_applicable', 'reason': 'SYNTHETIC fixed qualification source scripts/probe_h_analysis.py::qualification_cases; analytic state oracle and no task obligation supplied.', 'source_ids': ['synthetic_qualification']}
                            for kind in ('residual', 'constraint', 'conservation', 'event_localization', 'numerical_drift')},
            'observables': [], 'checks': [],
            'math_budget': {'max_ast_nodes': 512, 'max_ast_depth': 24, 'max_evaluations': 200000, 'max_checks': 32, 'max_union_knots': 36003},
            'budget': {'max_file_bytes': 67108864, 'max_total_bytes': 268435456, 'max_samples_per_output': 12001, 'max_result_bytes': 4194304},
            'claim_limit': 'SYNTHETIC INFRASTRUCTURE TEST. Native operation and finite empirical refinement only; no approved project or physical validity.'}


def qualification_cases(run_id, directory, qualification_not_after):
    """A fixed prior matrix; never obtain expected values from tests/factories."""
    directory = Path(directory).resolve()
    suffix = uuid.UUID(run_id).hex[:12]
    cases, groups = [], []
    definitions = [('first_ode4', 'ode4', False, [1.0, 1.0], [0.2], [1.0, 1.0]),
                   ('cascade_ode45', 'ode45', True, [1.0, 1.0], [0.2, -0.1], [1.0, 2.0]),
                   ('first_ode15s', 'ode15s', False, [2.0, 1.0], [0.4], [1.0, 1.0]),
                   ('first_pwl', 'ode4', False, [1.0, 1.0], [0.2], [0.0, 1.0, 0.0]),
                   ('zero_response', 'ode4', False, [1.0, 1.0], [0.0], [0.0, 0.0])]
    for occurrence, (group_id, solver_name, cascade, parameter_values, initial_values, input_values) in enumerate(definitions, 1):
        model = 'qh_' + group_id + '_' + suffix
        def block(identity, kind, values): return {'id': identity, 'path': model + '/' + identity, 'type': kind, 'parameters': values}
        def line(a, b, port=1): return {'source': {'block_id': a, 'port': 1}, 'destination': {'block_id': b, 'port': port}}
        parameters = [{'code_name': 'a', 'value': parameter_values[0], 'unit': '1/s'}, {'code_name': 'b', 'value': parameter_values[1], 'unit': '1/s'}]
        blocks = [block('Input', 'Inport', {'Port': '1'}), block('Forcing', 'Gain', {'Gain': 'b'}),
                  block('Decay', 'Gain', {'Gain': 'a'}), block('Balance', 'Sum', {'Inputs': '+-'}),
                  block('State', 'Integrator', {'InitialCondition': '0.25'}), block('Output', 'Outport', {'Port': '1'})]
        connections = [line('Input', 'Forcing'), line('Forcing', 'Balance'), line('State', 'Decay'), line('Decay', 'Balance', 2), line('Balance', 'State')]
        if cascade:
            blocks.extend([block('Transfer', 'Gain', {'Gain': 'b'}), block('DecayTwo', 'Gain', {'Gain': 'a'}),
                           block('BalanceTwo', 'Sum', {'Inputs': '+-'}), block('StateTwo', 'Integrator', {'InitialCondition': '0.15'})])
            connections.extend([line('State', 'Transfer'), line('Transfer', 'BalanceTwo'), line('StateTwo', 'DecayTwo'), line('DecayTwo', 'BalanceTwo', 2), line('BalanceTwo', 'StateTwo'), line('StateTwo', 'Output')])
        else: connections.append(line('State', 'Output'))
        baseline_parameters = [{**p, 'value': p['value'] - 0.25} for p in parameters]
        build = {'schema_version': 1, 'model_name': model, 'parameters': baseline_parameters, 'blocks': blocks, 'connections': connections}
        initial = [{'block_path': model + '/State', 'variable_id': 'x1', 'unit': '1', 'value': initial_values[0]}]
        if cascade: initial.append({'block_path': model + '/StateTwo', 'variable_id': 'x2', 'unit': '1', 'value': initial_values[1]})
        states = [{k: item[k] for k in ('block_path', 'variable_id', 'unit')} for item in initial]
        policy = _numeric_policy(solver_name, states)
        spec = {'schema_version': 1, 'model_name': model,
                'model_path': str(directory / 'qualification-baselines' / (model + '.slx')), 'model_sha256': '0' * 64,
                'parameters': parameters,
                'inputs': [{'port': 1, 'block_path': model + '/Input', 'variable_id': 'u', 'unit': '1',
                            'time': [0.0, 1.0, 2.0] if len(input_values) == 3 else [0.0, 2.0],
                            'values': input_values, 'interpolation': 'linear'}],
                'outputs': [{'port': 1, 'block_path': model + '/Output', 'variable_id': 'y', 'unit': '1', 'sample_time': 0}],
                'solver': policy['solver_levels'][0], 'start_time': 0.0, 'stop_time': 2.0, 'seed': 731,
                'metrics': [], 'runtime_class': 'normal_serial', 'warning_policy': 'record'}
        snapshot = physical_snapshot(spec, initial)
        group = {'group_id': group_id, 'point_id': group_id, 'occurrence': occurrence, 'factor_values': parameter_values + initial_values,
                 'roles': [{'kind': 'qualification'}], 'physical_snapshot': snapshot, 'physical_sha256': canonical_digest(snapshot),
                 'numeric_policy': policy, 'context': {'project_id': 'SYNTHETIC-H-QUALIFICATION',
                     'variables': [{'id': s['variable_id'], 'unit': s['unit'], 'roles': ['state'],
                                    'origin': 'SYNTHETIC fixed independent qualification fixture'} for s in states],
                     'relations': [], 'parameter_bindings': [],
                     'qualification_source': {'id': 'synthetic_qualification', 'repository_path': 'scripts/probe_h_analysis.py',
                                              'declaration': 'qualification_cases', 'scope': 'SYNTHETIC operation qualification only'}},
                 'case_ids': [group_id + '-level-' + str(i) for i in range(3)]}
        groups.append(group)
        for level, case_id in enumerate(group['case_ids']):
            run_spec = deepcopy(spec)
            run_spec['solver'] = deepcopy(policy['solver_levels'][level])
            cases.append({'case_id': case_id, 'group_id': group_id, 'level_id': level, 'point_id': group_id, 'occurrence': occurrence,
                          'run_spec': run_spec, 'build_spec': deepcopy(build), 'initial_conditions': deepcopy(initial), 'states': deepcopy(states),
                          'simulation_timeout': 20, 'expectation': 'success', 'warning_policy': 'record', 'qualification_not_after': qualification_not_after})
    first = cases[0]
    for identity, expectation in [('controlled_error', 'error'), ('controlled_timeout', 'early_stop'), ('controlled_no_output', 'no_output'), ('timing_repeat_1', 'success'), ('timing_repeat_2', 'success')]:
        item = deepcopy(first)
        item.update(case_id=identity, group_id=identity, point_id=identity, occurrence=len(cases) + 1, expectation=expectation)
        if expectation == 'early_stop':
            item['simulation_timeout'] = 1e-6
            item['run_spec']['stop_time'] = 30.0
            item['run_spec']['inputs'][0]['time'][-1] = 30.0
        if expectation == 'no_output':
            item['run_spec']['outputs'] = []
            item['build_spec']['blocks'] = [b for b in item['build_spec']['blocks'] if b['type'] != 'Outport']
            item['build_spec']['connections'] = [c for c in item['build_spec']['connections'] if c['destination']['block_id'] != 'Output']
            # Separate immutable controlled fixture; never mutate another case's SLX.
            model = item['run_spec']['model_name'] + '_noout'
            old = item['run_spec']['model_name']
            item['run_spec']['model_name'] = item['build_spec']['model_name'] = model
            item['run_spec']['model_path'] = str(directory / 'qualification-baselines' / (model + '.slx'))
            for b in item['build_spec']['blocks']: b['path'] = b['path'].replace(old + '/', model + '/')
            for collection in (item['run_spec']['inputs'], item['initial_conditions'], item['states']):
                for entry in collection: entry['block_path'] = entry['block_path'].replace(old + '/', model + '/')
        cases.append(item)
    return cases, groups


def make_request(executable, directory, *, environment_profile, simulation_profile, timeout=600, run_id=None):
    directory = Path(directory).resolve()
    bindings = {}
    for key, path, receipt in [('environment_profile', environment_profile, 'receipt.json'), ('simulation_profile', simulation_profile, 'simulation-profile-receipt.json')]:
        bindings[key] = {'path': str(Path(path).resolve()), 'sha256': '0' * 64}
        bindings['environment_receipt' if key == 'environment_profile' else 'simulation_profile_receipt'] = {'path': str(Path(path).resolve().parent / receipt), 'sha256': '0' * 64}
    bindings['required_A_operations'] = contract()['required_A_operations']
    budget = {k: contract()['hard_budget'][k] for k in contract()['hard_budget']}
    budget.update(max_groups=8, max_cases=24, process_timeout=timeout, simulation_timeout=20)
    request = {'schema_version': 1, 'run_id': run_id or str(uuid.uuid4()), 'mode': 'probe', 'channel': 'matlab_batch',
               'host_fingerprint': host_fingerprint(), 'matlab_executable': str(Path(executable).resolve()), 'output_directory': str(directory),
               'sources': {}, 'source_identity': '', 'required_functions': contract()['required_functions'], 'cases': [], 'groups': [],
               'bindings': bindings, 'budget': budget, 'input_identity': ''}
    preflight_request(request, role='qualification_h_request')
    for key in ('environment_profile', 'environment_receipt', 'simulation_profile', 'simulation_profile_receipt'):
        bindings[key] = file_binding(bindings[key]['path'])
    deadline = stable_utc(min(_time(load_document(path)['valid_until']) for path in (environment_profile, simulation_profile)))
    request['cases'], request['groups'] = qualification_cases(request['run_id'], directory, deadline)
    request['sources'] = source_identities()
    request['source_identity'] = canonical_digest(request['sources'])
    request['input_identity'] = canonical_digest({k: v for k, v in request.items() if k != 'input_identity'})
    return request


def probe_h_analysis(executable, directory, *, environment_profile, simulation_profile, timeout=600):
    from h_analysis_trial import validate_case_qualifications
    from validate_h_analysis_profile import derive_profile, validate_h_analysis_profile
    request = make_request(executable, directory, environment_profile=environment_profile, simulation_profile=simulation_profile, timeout=timeout)
    before = preflight_request(request, role='qualification_h_request')
    cache = {}
    for case in request['cases']:
        validate_case_qualifications(request, case, datetime.now(timezone.utc), include_h=False, _cache=cache)
    process = execute_request(request)
    directory, names = Path(directory), contract()['evidence']
    raw = load_document(directory / names['raw'])
    receipt = {'schema_version': 1, 'run_id': request['run_id'], 'sources': request['sources'], 'process': process,
               'runtime': None, 'artifacts': {}, 'errors': []}
    try:
        from verification_common import assert_unchanged
        assert_unchanged(before)
        profile = derive_profile(raw, request, process)
        receipt['runtime'] = profile['runtime']
        write_json(directory / names['profile'], profile)
        receipt['artifacts'] = artifact_manifest(directory, include_profile=True)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        receipt['errors'].append(str(error))
        write_json(directory / names['profile'], {'schema_version': 1, 'run_id': request['run_id'], 'qualified': False, 'error': str(error)})
        try: receipt['artifacts'] = artifact_manifest(directory, include_profile=True)
        except (OSError, ValueError, KeyError) as artifact_error: receipt['errors'].append(str(artifact_error))
    write_json(directory / names['profile_receipt'], receipt)
    result = validate_h_analysis_profile(directory / names['profile'])
    result['profile_path'] = str((directory / names['profile']).resolve())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('matlab-executable', 'output-dir', 'environment-profile', 'simulation-profile'):
        parser.add_argument('--' + option, required=True, type=Path)
    parser.add_argument('--timeout', type=float, default=600)
    args = parser.parse_args()
    try:
        result = probe_h_analysis(args.matlab_executable, args.output_dir, environment_profile=args.environment_profile, simulation_profile=args.simulation_profile, timeout=args.timeout)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        result = {'valid': False, 'h_analysis_assured': False, 'errors': [str(error)]}
    emit(result)
    return 0 if result['valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
