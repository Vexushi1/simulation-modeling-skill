"""Recompute bounded H1/H2 evidence from current, source-bound historical data."""
from __future__ import annotations

import math
from pathlib import Path

from runtime_common import canonical_digest
from validate_verification import validate_verification
from verification_common import Budget, finite, read_run, reference_errors, same_protocol, terminal


def binding_key(binding, root):
    return str((Path(root) / binding['path']).resolve()), binding['sha256']


def _criterion(analysis, values):
    if analysis['direction'] not in {'le', 'ge'} or not finite(analysis['threshold']) or not values or not all(finite(v) for v in values):
        raise ValueError('complete finite predeclared criterion required')
    passed = all(v <= analysis['threshold'] if analysis['direction'] == 'le' else v >= analysis['threshold'] for v in values)
    return {'values': values, 'unit': analysis['unit'], 'direction': analysis['direction'],
            'threshold': analysis['threshold'], 'passed': passed}


def refinement(analysis, runs):
    if len(analysis['run_ids']) != 3 or len(analysis['output_ports']) != 1:
        raise ValueError('step refinement requires exactly three layers and one terminal observable')
    selected = [runs[r] for r in analysis['run_ids']]
    steps = []
    values, times = [], []
    for run in selected:
        solver = run['protocol']['solver']
        if solver['name'] != 'ode4':
            raise ValueError('step refinement requires frozen ode4 at each layer')
        h = solver['fixed_step']
        span = run['spec']['stop_time'] - run['spec']['start_time']
        ratio = span / h
        if not finite(ratio) or abs(ratio - round(ratio)) > 8 * max(math.ulp(ratio), math.ulp(1.0)):
            raise ValueError('refinement interval must align with every fixed step')
        same_protocol(selected[0]['protocol'], run['protocol'], 'step_refinement', analysis['solver_changes'])
        t, value = terminal(run, analysis['output_ports'][0], analysis['unit'])
        steps.append(h)
        times.append(t)
        values.append(value)
    if steps[1] != steps[0]/2 or steps[2] != steps[0]/4 or len(set(times)) != 1:
        raise ValueError('exact h,h/2,h/4 and common actual terminal time required')
    differences = [abs(values[0]-values[1]), abs(values[1]-values[2])]
    return {**_criterion(analysis, differences), 'steps': steps, 'terminal_values': values,
            'terminal_time': times[0], 'order_estimate': None,
            'order_information': 'unassessed; zero differences/roundoff never establish convergence order'}


def _physical_inputs(run):
    return [{k: p[k] for k in ('port', 'unit', 'time', 'values', 'interpolation')} for p in run['spec']['inputs']]


def _structure_shape(run):
    blocks = run['protocol_report']['mapping_validation']['build_spec']['blocks']
    state_count = sum(b['type'] == 'Integrator' for b in blocks)
    # The supported reference families supply a concrete mechanism difference.
    # Names, coefficient values, solver and redundant metadata are excluded.
    return {'states': state_count, 'input_ports': [p['port'] for p in run['spec']['inputs']],
            'family': 'first_order_constant' if state_count else 'static_affine'}


def comparison(analysis, runs, claims):
    if len(analysis['run_ids']) != 2 or len(analysis['output_ports']) != 2:
        raise ValueError('comparison requires exactly two actual runs and mapped output ports')
    left, right = [runs[r] for r in analysis['run_ids']]
    if _physical_inputs(left) != _physical_inputs(right) or any(left['spec'][k] != right['spec'][k] for k in ('start_time', 'stop_time', 'seed')):
        raise ValueError('comparison physical inputs/time/seed differ')
    method = analysis['method']
    if method == 'solver_final_comparison':
        same_protocol(left['protocol'], right['protocol'], method, analysis['solver_changes'])
        observed = []
        for run in (left, right):
            if run['protocol']['solver']['classification']['dynamics'] != 'continuous':
                raise ValueError('solver comparison requires continuous dynamics')
            name = run['actual']['observed_solver_info']['Solver']
            if name != run['protocol']['solver']['name'] or name not in {'ode4', 'ode45', 'ode15s'}:
                raise ValueError('actual observed continuous solver differs from qualified requested method')
            observed.append(name)
        if observed[0] == observed[1]:
            raise ValueError('solver comparison requires two different actual solvers')
        detail = {'observed_solvers': observed}
    else:
        review = analysis['structural_review']
        if review is None or analysis['solver_changes']:
            raise ValueError('structural comparison requires source-reviewed material differences')
        if left['protocol_report']['problem_sha256'] != right['protocol_report']['problem_sha256']:
            raise ValueError('structural comparison requires the same frozen B')
        for run, side in ((left, 'left'), (right, 'right')):
            known = {r['id'] for r in run['model']['body']['relations']}
            if not review[side+'_relation_ids'] or set(review[side+'_relation_ids']) - known:
                raise ValueError('structural review must identify current approved relations')
        if _structure_shape(left) == _structure_shape(right):
            raise ValueError('no supported material mechanism difference; names/parameters/equivalent rewrites do not qualify')
        # First version admits an explicit dynamic-state versus algebraic
        # mechanism, not an automatic general symbolic equivalence prover.
        if {_structure_shape(left)['states'], _structure_shape(right)['states']} != {0, 1}:
            raise ValueError('structural comparator outside supported static/first-order mechanism pair')
        if left['protocol']['scenario']['requirement_ids'] != right['protocol']['scenario']['requirement_ids']:
            raise ValueError('structural comparison scenario requirement basis differs')
        detail = {'material_review': review, 'left_shape': _structure_shape(left), 'right_shape': _structure_shape(right)}
    if claims[analysis['claim_id']]['domain']['kind'] != 'terminal_pair':
        raise ValueError('terminal comparison cannot verify a different domain claim')
    ta, va = terminal(left, analysis['output_ports'][0], analysis['unit'])
    tb, vb = terminal(right, analysis['output_ports'][1], analysis['unit'])
    if ta != tb:
        raise ValueError('comparison needs equal actual terminal times')
    return {**_criterion(analysis, [abs(va-vb)]), **detail,
            'terminal_values': [va, vb], 'terminal_time': ta, 'metric': 'absolute_terminal_difference'}


def campaign_response(analysis, runs, claims, root, budget):
    from validate_experiment_receipt import validate_experiment_receipt
    if analysis['campaign'] is None or len(analysis['run_ids']) > 16 or len(analysis['output_ports']) != 1:
        raise ValueError('finite response requires a complete G campaign and one observable')
    path = budget.bind(analysis['campaign'], root)
    from verification_common import preflight_e
    preflight_e(path, root, budget)
    report = validate_experiment_receipt(path, project_root=root)
    budget.check()
    if not report['valid'] or not report['campaign_complete']:
        raise ValueError('H2 requires complete current G history: ' + '; '.join(report['errors']))
    ledger = budget.read(path.parent / 'campaign-ledger.json')
    rows = ledger['rows'] if isinstance(ledger, dict) else ledger
    selected = [runs[r] for r in analysis['run_ids']]
    actual = [binding_key({'path': str(path.parent / row['receipt']['path']), 'sha256': row['receipt']['sha256']}, root) for row in rows]
    expected = [binding_key(run['receipt'], root) for run in selected]
    if actual != expected or len(rows) > 16:
        raise ValueError('H2 needs exact ordered H1 coverage for every actual G draw, including repeats')
    # Independent model/protocol identities may share one physical scenario.
    budget.scenario_ids.update(canonical_digest({'inputs': _physical_inputs(run),
        'time': [run['spec']['start_time'], run['spec']['stop_time']], 'seed': run['spec']['seed'],
        'requirement_ids': run['protocol']['scenario']['requirement_ids']}) for run in selected)
    if len(budget.scenario_ids) > 16:
        raise ValueError('H2 total finite scenario budget exceeded')
    domain = claims[analysis['claim_id']]['domain']['kind']
    method = report['method']
    if analysis['method'] == 'finite_domain_robustness' and (method not in {'scenario_matrix', 'full_factorial'} or domain != 'complete_catalog'):
        raise ValueError('robustness requires complete finite catalog; MC draws cannot prove catalog coverage')
    if domain not in {'complete_catalog', 'actual_draws'} or (domain == 'complete_catalog' and method == 'monte_carlo_catalog'):
        raise ValueError('campaign evidence does not cover the declared finite domain')
    values = [terminal(run, analysis['output_ports'][0], analysis['unit'])[1] for run in selected]
    return {**_criterion(analysis, values), 'method': method, 'domain': domain,
            'actual_run_ids': [run['run_id'] for run in selected], 'metric': 'recorded_terminal_output'}


def analyze(path, *, project_root=None, kind=None, budget=None):
    budget = budget or Budget()
    root = Path(project_root or Path(path).resolve().parent).resolve()
    report = validate_verification(path, project_root=root, kind=kind, require_reviewed=True, budget=budget)
    result = {'schema_valid': report['schema_valid'], 'reviewed': report['reviewed'],
              'valid': False, 'kind': report['kind'], 'project_id': report['project_id'],
              'plan_path': report['plan_path'], 'plan_sha256': report['plan_sha256'],
              'semantic_sha256': report['semantic_sha256'], 'evidence_complete': False,
              'checks_passed': False, 'numerically_verified': False,
              'model_verification_decided': False, 'model_verified': False,
              'primary_receipt': None, 'primary_protocol': None, 'primary_upstream': None,
              'ledger': [], 'analyses': [], 'summary': None, 'errors': list(report['errors']),
              'missing_gates': report['missing_gates'], 'physical_validity_claim': False}
    if not report['valid'] or not report['reviewed']:
        return result
    try:
        plan = budget.read(path)
        result['primary_receipt'] = plan['primary']
        runs = {}
        seen = set()
        h1_cache = {}
        for index, member in enumerate(plan['runs']):
            try:
                if plan['kind'] == 'H2':
                    h1_path = budget.bind(member['h1_receipt'], root)
                    if h1_path not in h1_cache:
                        from validate_verification_receipt import validate_verification_receipt
                        h1 = validate_verification_receipt(h1_path, project_root=root, kind='H1', budget=budget)
                        if not h1['valid'] or not h1['evidence_complete'] or not h1['checks_passed']:
                            raise ValueError('every H2 actual run requires successful recomputed H1: ' + '; '.join(h1['errors']))
                        h1_cache[h1_path] = h1
                    covered = h1_cache[h1_path]['ledger']
                run = read_run(member['receipt'], root, budget)
                if run['project_id'] != plan['project_id'] or run['run_id'] in seen:
                    raise ValueError('H actual E project/runID differs or is duplicated')
                seen.add(run['run_id'])
                if plan['kind'] == 'H1':
                    checks = reference_errors(run, member['references'])
                    passed = all(c['passed'] for c in checks)
                else:
                    match = [r for r in covered if r['status'] == 'completed'
                             and binding_key(r['receipt'], root) == binding_key(run['receipt'], root)
                             and r['run_id'] == run['run_id'] and r['passed']]
                    if len(match) != 1:
                        raise ValueError('H1 does not exactly cover this E receipt SHA/runID')
                    checks, passed = [], True
                runs[member['id']] = run
                result['ledger'].append({'id': member['id'], 'status': 'completed', 'receipt': run['receipt'],
                                         'run_id': run['run_id'], 'passed': passed, 'checks': checks})
                if binding_key(member['receipt'], root) == binding_key(plan['primary'], root):
                    pr = run['protocol_report']
                    result['primary_protocol'] = {'path': pr['contract_path'], 'sha256': pr['contract_sha256']}
                    result['primary_upstream'] = {k: {'path': pr[k+'_path'], 'sha256': pr[k+'_sha256']}
                                                  for k in ('problem', 'model', 'approval', 'mapping')}
            except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError, StopIteration) as error:
                result['ledger'].append({'id': member['id'], 'status': 'failed', 'receipt': member['receipt'],
                                         'run_id': None, 'passed': False, 'checks': [], 'error': str(error)})
                result['ledger'].extend({'id': m['id'], 'status': 'not_attempted', 'receipt': m['receipt'],
                                        'run_id': None, 'passed': False, 'checks': []} for m in plan['runs'][index+1:])
                raise
        if not all(row['passed'] for row in result['ledger']):
            raise ValueError('primary numerical error criterion failed; no H2 permission')
        claims = {c['id']: c for c in plan['material_results']}
        models = {(r['protocol_report']['model_sha256'], r['protocol_report']['design_id'], r['protocol_report']['model_id']) for r in runs.values()}
        if plan['kind'] == 'H2' and len(models | budget.model_ids) > 2:
            raise ValueError('H2 model budget exceeded')
        for analysis in plan['analyses']:
            if plan['kind'] == 'H1':
                numeric = refinement(analysis, runs)
                result['analyses'].append({'id': analysis['id'], 'numeric': numeric, 'passed': numeric['passed']})
            else:
                if any(analysis[k] is None for k in ('failure_disposition', 'impact_scope', 'required_action', 'return_stage')):
                    raise ValueError('H2 requires predeclared failure/impact/action/return disposition')
                numeric = (comparison(analysis, runs, claims) if analysis['method'] in {'solver_final_comparison', 'structural_final_comparison'}
                           else campaign_response(analysis, runs, claims, root, budget))
                result['analyses'].append({'id': analysis['id'], 'claim_id': analysis['claim_id'], 'numeric': numeric,
                                          'disposition': 'support' if numeric['passed'] else analysis['failure_disposition'],
                                          'impact_scope': analysis['impact_scope'],
                                          'required_action': None if numeric['passed'] else analysis['required_action'],
                                          'return_stage': None if numeric['passed'] else analysis['return_stage']})
        budget.finish()
        result['evidence_complete'] = True
        result['checks_passed'] = all(a.get('passed', a['numeric']['passed']) for a in result['analyses'])
        if plan['kind'] == 'H1':
            result['numerically_verified'] = result['checks_passed']
            result['valid'] = result['checks_passed']
        else:
            result['model_verification_decided'] = True
            result['model_verified'] = all(a['disposition'] == 'support' and a['required_action'] is None for a in result['analyses'])
            result['valid'] = True  # Completed rejection evidence is not a verified claim.
        result['summary'] = {'actual_runs': len(runs), 'scope': 'finite recorded samples / terminal criteria only',
                             'material_decisions': plan['material_results']}
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError, RecursionError, StopIteration) as error:
        result['errors'].append(str(error))
    return result
