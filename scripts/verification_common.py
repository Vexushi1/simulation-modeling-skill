"""Bounded H arithmetic and historical E readback; no native execution or eval."""
from __future__ import annotations

import copy
import math
import time
from pathlib import Path

from runtime_common import ROOT, canonical_digest, contained_path, load_contract, load_document, sha256_file

POLICY = 'core/numerical_verification_contract.yaml'
H1_METHODS = {'analytic_reference', 'step_refinement'}
H2_METHODS = {'scenario_response', 'finite_domain_robustness', 'solver_final_comparison', 'structural_final_comparison'}


def semantic_digest(plan):
    return canonical_digest({k: v for k, v in plan.items() if k not in {'status', 'review_record'}})


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


class Budget:
    """Charge each preflight binding read, including nested qualifications/analyses."""
    def __init__(self):
        self.limits = load_contract(POLICY)['limits']
        self.started = time.monotonic()
        self.bytes = 0
        self.identities = {}
        self.run_ids = set()
        self.model_ids = set()
        self.scenario_ids = set()

    def check(self):
        if time.monotonic() - self.started > self.limits['wall_seconds']:
            raise ValueError('H analysis wall-time budget exceeded')

    def charge(self, path):
        self.check()
        path = Path(path).resolve()
        size = path.stat().st_size
        if size > self.limits['input_file_bytes']:
            raise ValueError('H input file byte limit exceeded: ' + str(path))
        self.bytes += size
        if self.bytes > self.limits['total_read_bytes']:
            raise ValueError('H total bound-data read budget exceeded')
        digest = sha256_file(path)
        if path in self.identities and self.identities[path] != digest:
            raise ValueError('H input changed during analysis: ' + str(path))
        self.identities[path] = digest
        return path

    def read(self, path):
        return load_document(self.charge(path))

    def bind(self, binding, root):
        if not isinstance(binding, dict) or set(binding) != {'path', 'sha256'}:
            raise ValueError('complete exact file binding required')
        path = contained_path(root, binding['path'])
        self.charge(path)
        if self.identities[path] != binding['sha256']:
            raise ValueError('H file SHA differs: ' + str(path))
        return path

    def finish(self):
        self.check()
        for path, digest in self.identities.items():
            if sha256_file(path) != digest:
                raise ValueError('H bound input changed before completion: ' + str(path))
        return {'read_bytes': self.bytes, 'actual_E_runs': len(self.run_ids)}


def preflight_e(receipt_path, root, budget):
    """Bound files before the existing E consumer can open native/JSON/CSV data.

    Walk exact binding records and evidence-directory artefacts, never MATLAB
    installation inventory strings. Qualification bindings are included.
    """
    pending = [Path(receipt_path).resolve()]
    seen = set()
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        seen.add(path)
        budget.charge(path)
        if path.suffix.lower() not in {'.json', '.yaml', '.yml'}:
            continue
        value = load_document(path)
        if path.name.endswith('receipt.json') or path.name.endswith('profile.json'):
            pending.extend(item.resolve() for item in path.parent.iterdir() if item.is_file())

        def walk(item):
            if isinstance(item, dict):
                if isinstance(item.get('time'), list) and isinstance(item.get('values'), list) and len(item['time']) > budget.limits['samples_per_signal']:
                    raise ValueError('H per-signal sample budget exceeded before numerical consumption')
                if 'sha256' in item and ('path' in item or 'file' in item):
                    name = item.get('path', item.get('file'))
                    if isinstance(name, str):
                        candidate = Path(name)
                        if not candidate.is_absolute():
                            candidate = (path.parent / name) if 'file' in item else (root / name)
                        if not candidate.is_file():
                            raise ValueError('bound historical input is missing: ' + str(candidate))
                        pending.append(candidate.resolve())
                for child in item.values():
                    walk(child)
            elif isinstance(item, list):
                for child in item:
                    walk(child)
        walk(value)


def read_run(binding, root, budget):
    from validate_simulation_receipt import validate_simulation_receipt
    from validate_simulation_protocol import validate_simulation_protocol
    path = budget.bind(binding, root)
    preflight_e(path, root, budget)
    checked = validate_simulation_receipt(path, project_root=root)
    budget.check()
    if not checked['valid'] or not checked['primary_run_complete']:
        raise ValueError('H requires complete admissible E history: ' + '; '.join(checked['errors']))
    protocol = validate_simulation_protocol(Path(checked['protocol_path']), project_root=root, require_frozen=True)
    if not protocol['valid'] or not protocol['execution_ready']:
        raise ValueError('H requires current approved frozen E protocol')
    request = budget.read(path.parent / 'simulation-inputs.json')
    raw = budget.read(checked['raw_path'])
    data = budget.read(checked['data_path'])
    outputs = data['outputs']
    if isinstance(outputs, dict):
        outputs = [outputs]
    if not 1 <= len(outputs) <= budget.limits['signals']:
        raise ValueError('H signal count exceeds scope')
    for item in outputs:
        if not 2 <= len(item['time']) <= budget.limits['samples_per_signal']:
            raise ValueError('H per-signal sample budget exceeded')
    receipt = budget.read(path)
    run_id = receipt['run_id']
    budget.run_ids.add(run_id)
    if len(budget.run_ids) > 32:
        raise ValueError('H total actual E attempt budget exceeded')
    model_contract = budget.read(protocol['model_path'])
    budget.model_ids.add((protocol['model_sha256'], protocol['design_id'], protocol['model_id']))
    design = next(d for d in model_contract['designs'] if d['id'] == protocol['design_id'])
    model = next(m for m in design['models'] if m['id'] == protocol['model_id'])
    actual = raw['cases'][0] if isinstance(raw['cases'], list) else raw['cases']
    return {'receipt': {'path': str(path), 'sha256': sha256_file(path)}, 'run_id': run_id,
            'protocol': budget.read(protocol['contract_path']), 'protocol_report': protocol,
            'spec': request['cases'][0]['run_spec'], 'actual': actual,
            'outputs': outputs, 'model': model, 'project_id': checked['project_id']}


def parameters(run):
    records = run['protocol_report']['mapping_validation']['parameter_validation']['parameters']
    selection = run['protocol']['selection']
    return {p['reference']['variable_id']: p for p in records
            if p['reference']['design_id'] == selection['design_id']
            and p['reference']['model_id'] == selection['model_id']}


def constant_input(run, identity):
    found = [p for p in run['spec']['inputs'] if p['variable_id'] == identity]
    if len(found) != 1 or not found[0]['values'] or any(x != found[0]['values'][0] for x in found[0]['values']):
        raise ValueError('analytic reference requires one approved constant input: ' + str(identity))
    return found[0]['values'][0]


def initial_value(run, selector):
    from validate_simulation_protocol import selected_value
    condition = run['model']['body']['initial_conditions']
    if condition['status'] != 'specified':
        raise ValueError('first-order reference requires approved initial condition')
    value = selected_value(condition['value'], selector)
    if not finite(value):
        raise ValueError('finite approved scalar initial value required')
    return value


def graph_expression(run, ref, output=False):
    """Finite linear graph signature in approved parameter/variable symbols."""
    spec = run['protocol_report']['mapping_validation']['build_spec']
    blocks = {b['id']: b for b in spec['blocks']}
    edges = {(c['destination']['block_id'], c['destination']['port']): c['source']['block_id'] for c in spec['connections']}
    param_codes = {p['code_name']: identity for identity, p in parameters(run).items()}
    input_ids = {p['block_path']: p['variable_id'] for p in run['spec']['inputs']}
    visiting = set()
    def expression(identity):
        if identity in visiting:
            raise ValueError('unsupported algebraic cycle in H reference')
        visiting.add(identity)
        b, kind = blocks[identity], blocks[identity]['type']
        if kind == 'Inport':
            result = {((), input_ids[b['path']]): 1}
        elif kind == 'Integrator':
            result = {((), ref['state_id']): 1}
        elif kind == 'Constant':
            result = {((param_codes[b['parameters']['Value']],), None): 1}
        elif kind == 'Gain':
            p = param_codes[b['parameters']['Gain']]
            result = {(tuple(sorted(term + (p,))), variable): coefficient
                      for (term, variable), coefficient in expression(edges[(identity, 1)]).items()}
        elif kind == 'Sum':
            result = {}
            for port, sign in enumerate(b['parameters']['Inputs'], 1):
                for term, coefficient in expression(edges[(identity, port)]).items():
                    result[term] = result.get(term, 0) + (1 if sign == '+' else -1) * coefficient
            result = {k: v for k, v in result.items() if v}
        elif kind == 'Outport':
            result = expression(edges[(identity, 1)])
        else:
            raise ValueError('reference graph outside supported linear family')
        visiting.remove(identity)
        return result
    states = [b for b in blocks.values() if b['type'] == 'Integrator']
    output_block = next(b['id'] for b in blocks.values() if b['path'] == next(p['block_path'] for p in run['spec']['outputs'] if p['port'] == ref['output_port']))
    if ref['family'] == 'static_affine':
        if states:
            raise ValueError('static analytic reference cannot omit approved states')
        expected = {}
        if ref['constant_parameter'] is not None:
            expected[((ref['constant_parameter'],), None)] = 1
        for term in ref['terms']:
            key = ((term['parameter_id'],) if term['parameter_id'] is not None else (), term['input_id'])
            expected[key] = expected.get(key, 0) + 1
        if expression(output_block) != expected:
            raise ValueError('static reference differs from approved linear graph')
    else:
        if len(states) != 1 or expression(output_block) != {((), ref['state_id']): 1}:
            raise ValueError('first-order reference requires single state with y=x')
        expected = {((ref['a_parameter'],), ref['state_id']): -1,
                    ((ref['b_parameter'],), ref['input_id']): 1}
        if expression(edges[(states[0]['id'], 1)]) != expected:
            raise ValueError('first-order reference differs from approved governing graph')
        if float(states[0]['parameters']['InitialCondition']) != initial_value(run, ref['initial_selector']):
            raise ValueError('reference initial value differs from approved implementation')


def analytic_values(run, ref, times):
    ps = parameters(run)
    def parameter(identity):
        if identity not in ps or not finite(ps[identity]['value']) or not ps[identity]['unit']:
            raise ValueError('reference parameter lacks approved finite value/unit: ' + str(identity))
        return ps[identity]['value']
    variables = {v['id']: v for v in run['model']['body']['variables']}
    relations = {r['id']: r for r in run['model']['body']['relations']}
    if not ref['relation_ids'] or set(ref['relation_ids']) - set(relations):
        raise ValueError('reference requires current approved relation IDs')
    relevant = set().union(*(set(relations[r]['variable_ids']) for r in ref['relation_ids']))
    used = {x for x in (ref['constant_parameter'], ref['a_parameter'], ref['b_parameter'], ref['input_id'], ref['state_id']) if x is not None}
    used |= {x for t in ref['terms'] for x in t.values() if x is not None}
    bound_output = next(p for p in run['spec']['outputs'] if p['port'] == ref['output_port'])
    used.add(bound_output['variable_id'])
    if not used <= relevant or not used <= set(variables) or bound_output['unit'] != ref['unit']:
        raise ValueError('analytic reference relation/variable/output/unit binding differs')
    graph_expression(run, ref)
    if ref['family'] == 'static_affine':
        if any(ref[k] is not None for k in ('a_parameter', 'b_parameter', 'input_id', 'state_id')) or ref['initial_selector']:
            raise ValueError('static reference contains hidden dynamic fields')
        value = math.fsum(([parameter(ref['constant_parameter'])] if ref['constant_parameter'] is not None else []) +
                          [(parameter(t['parameter_id']) if t['parameter_id'] is not None else 1) * constant_input(run, t['input_id']) for t in ref['terms']])
        values = [value] * len(times)
    else:
        if ref['constant_parameter'] is not None or ref['terms']:
            raise ValueError('first-order reference contains hidden affine fields')
        if ref['state_id'] not in {v['id'] for v in run['model']['body']['variables'] if 'state' in v['roles']}:
            raise ValueError('first-order state must be an approved state variable')
        a, forcing = parameter(ref['a_parameter']), parameter(ref['b_parameter']) * constant_input(run, ref['input_id'])
        if a < 0:
            raise ValueError('first-order a must be nonnegative')
        x0, t0 = initial_value(run, ref['initial_selector']), run['spec']['start_time']
        values = []
        for t in times:
            dt = t - t0
            # Stable near a=0: divide expm1 by a after multiplication by dt.
            z = a * dt
            response = dt if a == 0 or z == 0 else -math.expm1(-z) / a
            values.append(x0 * math.exp(-z) + forcing * response)
    if not all(finite(v) for v in values):
        raise ValueError('nonfinite analytic reference')
    return values


def reference_errors(run, refs):
    if {r['output_port'] for r in refs} != {o['port'] for o in run['outputs']} or len(refs) != len(run['outputs']):
        raise ValueError('every material E output needs exactly one reference')
    checks = []
    for ref in refs:
        signal = next(o for o in run['outputs'] if o['port'] == ref['output_port'])
        expected = analytic_values(run, ref, signal['time'])
        scales = [ref['atol'] + ref['rtol'] * abs(v) for v in expected]
        if not finite(ref['atol']) or not finite(ref['rtol']) or any(not finite(s) or s <= 0 for s in scales):
            raise ValueError('reference error scale must be finite and strictly positive at every sample')
        errors = [abs(a-b) for a, b in zip(signal['values'], expected)]
        scaled = [e/s for e, s in zip(errors, scales)]
        if not all(finite(x) for x in errors + scaled):
            raise ValueError('nonfinite numerical error')
        checks.append({'output_port': ref['output_port'], 'unit': ref['unit'],
                       'max_abs_error': max(errors), 'max_scaled_error': max(scaled),
                       'terminal_error': errors[-1], 'passed': max(scaled) <= 1})
    return checks


def same_protocol(left, right, method, changes):
    allowed = {'fixed_step'} if method == 'step_refinement' else {'name', 'type', 'max_step', 'min_step', 'initial_step', 'rel_tol', 'abs_tol', 'fixed_step', 'reason', 'classification.reason'}
    if not changes or set(changes) - allowed or (method == 'step_refinement' and changes != ['fixed_step']):
        raise ValueError('designated solver changes outside supported numerical fields')
    a, b = copy.deepcopy(left), copy.deepcopy(right)
    for p in (a, b):
        for key in ('status', 'freeze_record'):
            p.pop(key)
        for key in changes:
            if key == 'classification.reason':
                p['solver']['classification'].pop('reason')
            else:
                p['solver'].pop(key)
    if canonical_digest(a) != canonical_digest(b):
        raise ValueError('frozen protocol differs outside designated numerical fields')


def terminal(run, port, unit):
    signal = next((s for s in run['outputs'] if s['port'] == port), None)
    if signal is None or signal['unit'] != unit:
        raise ValueError('terminal observable/unit differs')
    return signal['time'][-1], signal['values'][-1]
