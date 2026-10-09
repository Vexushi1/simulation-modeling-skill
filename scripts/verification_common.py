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
    """On-disk byte charges and cooperative completion time checks.

    A blocking E/SciPy call is checked after return, not interrupted. File size
    does not bound decompressed allocation or process peak memory.
    """
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


def historical_mapping_role(receipt_path, root, budget):
    """Authenticate the selected E's D capture, without granting D readiness.

    Only the precise origin field in its owned input gets an archive role.
    Current mapping and every other binding retain their current-byte role;
    the existing E consumer still performs complete historical D validation.
    """
    from validate_simulation_profile import contract as e_contract
    from validate_implementation_profile import _validate_request, contract as d_contract
    from validate_domain_mapping import semantic_digest as mapping_digest
    path = Path(receipt_path).resolve()
    e_names, d_names = e_contract()['evidence'], d_contract()['evidence']
    if path.name != e_names['run_receipt']:
        return {}, []
    e_receipt = budget.read(path)
    e_input = e_receipt['artifacts']['input']
    if set(e_input) != {'file', 'sha256'} or e_input['file'] != e_names['input']:
        raise ValueError('selected E input role differs before D capture resolution')
    e_request = budget.read(budget.bind({'path': e_input['file'], 'sha256': e_input['sha256']}, path.parent))
    if e_request.get('mode') != 'primary' or e_request.get('run_id') != e_receipt['run_id']:
        raise ValueError('selected E input identity differs before D capture resolution')
    binding = e_request['bindings'].get('implementation_receipt')
    if binding is None:
        return {}, []  # No D origin exemption; full E will enforce its surface.
    d_path = budget.bind(binding, root)
    if d_path.name != d_names['structure_receipt']:
        raise ValueError('selected E implementation receipt role differs')
    receipt = budget.read(d_path)
    manifest = receipt['artifacts']
    def owned(role, name):
        item = manifest[role]
        if set(item) != {'file', 'sha256'} or item['file'] != name:
            raise ValueError('D historical capture artifact role differs: ' + role)
        return budget.bind({'path': item['file'], 'sha256': item['sha256']}, d_path.parent)
    input_path = owned('input', d_names['input'])
    request = budget.read(input_path)
    _validate_request(request)
    b = request['bindings']
    if (request['mode'] != 'implementation' or Path(request['output_directory']).resolve() != d_path.parent
            or type(receipt.get('schema_version')) is not int or receipt['schema_version'] != 1
            or receipt.get('run_id') != request['run_id']
            or receipt.get('sources') != request['sources'] or len(request['cases']) != 1
            or request['cases'][0]['case_id'] != 'implementation' or request['cases'][0]['expect_failure'] is not False):
        raise ValueError('D historical capture receipt/input identity differs')
    for name in ('project_id', 'mapping_semantic_sha256', 'parameter_provenance_sha256', 'build_spec_sha256'):
        if receipt.get(name) != b[name]:
            raise ValueError('D historical capture receipt binding differs: ' + name)
    if canonical_digest(request['cases'][0]['build_spec']) != b['build_spec_sha256']:
        raise ValueError('D historical capture build specification identity differs')
    expected = {'input': d_names['input'], 'raw': d_names['raw'], 'log': d_names['log'],
                'mapping_snapshot': 'mapping-snapshot.json', 'mapping_original': 'mapping-original.yaml',
                'implementation_model': request['cases'][0]['build_spec']['model_name'] + '.slx',
                'implementation_structure': 'implementation-structure.json'}
    if set(manifest) != set(expected):
        raise ValueError('D historical capture artifact manifest differs')
    artifacts = {role: owned(role, name) for role, name in expected.items()}
    raw = budget.read(artifacts['raw'])
    if any(raw.get(name) != request[name] for name in ('run_id', 'channel', 'host_fingerprint', 'input_identity', 'source_identity')):
        raise ValueError('D historical capture raw/input identity differs')
    original, snapshot = artifacts['mapping_original'], budget.read(artifacts['mapping_snapshot'])
    origin = b['mapping_input']
    if not isinstance(origin, dict) or set(origin) != {'path', 'sha256'}:
        raise ValueError('D historical mapping origin exact binding differs')
    current = contained_path(root, origin['path'])
    current_mapping = budget.read(current)
    archived_mapping = budget.read(original)
    if (original.read_bytes() != b['mapping_original_text'].encode('utf-8')
            or budget.identities[original] != origin['sha256']
            or canonical_digest(snapshot) != canonical_digest(b['mapping_snapshot'])
            or any(doc.get('project_id') != b['project_id'] or mapping_digest(doc) != b['mapping_semantic_sha256']
                   for doc in (snapshot, archived_mapping, current_mapping))):
        raise ValueError('D historical mapping original text/SHA or snapshot/current semantics differ')
    attached = current_mapping.get('implementation')
    if attached is not None and (contained_path(root, attached['path']) != d_path or attached['sha256'] != budget.identities[d_path]):
        raise ValueError('current mapping implementation attachment differs from selected D receipt')
    role = (input_path, ('bindings', 'mapping_input'))
    return {role: (origin, original, budget.identities[input_path])}, [current]


def preflight_e(receipt_path, root, budget, *, path_bindings=None, historical_roles=None):
    """Bound files before the existing E consumer can open native/JSON/CSV data.

    Walk exact binding records and evidence-directory artefacts, never MATLAB
    installation inventory strings. Qualification bindings are included, but
    their numerical arrays are not selected H outputs. G supplies its typed
    owned-directory bindings explicitly; other path bindings use project root.
    """
    roles = dict(historical_roles or {})
    captured, current = historical_mapping_role(receipt_path, root, budget)
    for location, role in captured.items():
        if location in roles and roles[location] != role:
            raise ValueError('conflicting D historical mapping role')
        roles[location] = role
    pending = [(Path(receipt_path).resolve(), None)]
    pending.extend((path, None) for path in current)
    seen = set()
    while pending:
        path, expected_sha = pending.pop()
        if path in seen:
            if expected_sha is not None and budget.identities[path] != expected_sha:
                raise ValueError('H file SHA differs: ' + str(path))
            continue
        seen.add(path)
        budget.charge(path)
        if expected_sha is not None and budget.identities[path] != expected_sha:
            raise ValueError('H file SHA differs: ' + str(path))
        if path.suffix.lower() not in {'.json', '.yaml', '.yml'}:
            continue
        value = load_document(path)
        if path.name.endswith('receipt.json') or path.name.endswith('profile.json'):
            pending.extend((item.resolve(), None) for item in path.parent.iterdir() if item.is_file())

        def walk(item, location=()):
            if isinstance(item, dict):
                if 'sha256' in item and ('path' in item or 'file' in item):
                    name = item.get('path', item.get('file'))
                    if isinstance(name, str):
                        role = roles.get((path, location))
                        if role is not None:
                            origin, archive, input_sha = role
                            if item != origin or budget.identities[path] != input_sha:
                                raise ValueError('D historical mapping origin role changed')
                            candidate = archive
                        else:
                            candidate = (path_bindings or {}).get((name, item['sha256']), Path(name))
                        if not candidate.is_absolute():
                            candidate = (path.parent / name) if 'file' in item else (root / name)
                        if not candidate.is_file():
                            raise ValueError('bound historical input is missing: ' + str(candidate))
                        pending.append((candidate.resolve(), item['sha256']))
                for key, child in item.items():
                    walk(child, location + (key,))
            elif isinstance(item, list):
                for index, child in enumerate(item):
                    walk(child, location + (index,))
        walk(value)
    return roles


def bounded_outputs(outputs, budget):
    """Shape/sample guard for explicitly selected actual E outputs only."""
    from validate_simulation_profile import record_array
    outputs = record_array(outputs, 'selected E outputs')
    if not 1 <= len(outputs) <= budget.limits['signals']:
        raise ValueError('H signal count exceeds scope before numerical consumption')
    for item in outputs:
        times, values = item.get('time'), item.get('values')
        if not isinstance(times, list) or not isinstance(values, list) or len(times) != len(values):
            raise ValueError('H selected E time/values shape differs before numerical consumption')
        if not 2 <= len(times) <= budget.limits['samples_per_signal']:
            raise ValueError('H per-signal sample budget exceeded before numerical consumption')
        if not all(finite(x) for x in times + values):
            raise ValueError('H selected E requires finite flat real time/values before numerical consumption')
    return outputs


def preflight_selected_e(receipt_path, root, budget):
    """Resolve primary input/raw/data roles from the bound actual E receipt.

    This is an early H budget gate, not an alternative E admissibility check.
    The existing E consumer still verifies qualifications, MAT classes/shapes,
    raw/JSON/CSV agreement, frozen protocol and historical execution bindings.
    """
    from validate_simulation_profile import contract, record_array
    path = Path(receipt_path).resolve()
    receipt = budget.read(path)
    names = contract()['evidence']
    if path.name != names['run_receipt']:
        raise ValueError('H selected E requires the actual run receipt role')
    def artifact(role):
        binding = receipt['artifacts'][role]
        if not isinstance(binding, dict) or set(binding) != {'file', 'sha256'}:
            raise ValueError('H selected E artifact role binding differs')
        target = budget.bind({'path': binding['file'], 'sha256': binding['sha256']}, path.parent)
        if role in {'input', 'raw'} and target != path.parent / names[role]:
            raise ValueError('H selected E input/raw role differs from E contract')
        return target
    request = budget.read(artifact('input'))
    raw = budget.read(artifact('raw'))
    cases = record_array(raw.get('cases'), 'selected E raw.cases')
    requested = record_array(request.get('cases'), 'selected E input.cases')
    if (request.get('mode') != 'primary' or len(cases) != 1 or len(requested) != 1
            or cases[0].get('case_id') != 'primary' or requested[0].get('case_id') != 'primary'
            or receipt['run_id'] != request.get('run_id') or receipt['run_id'] != raw.get('run_id')):
        raise ValueError('H selected E primary case/run identity differs')
    bounded_outputs(cases[0].get('outputs'), budget)
    data_path = artifact('data')
    if data_path != contained_path(path.parent, cases[0]['data_file']):
        raise ValueError('H selected E primary data role differs from actual raw case')
    data = budget.read(data_path)
    if data.get('run_id') != receipt['run_id']:
        raise ValueError('H selected E primary data run identity differs')
    bounded_outputs(data.get('outputs'), budget)


def preflight_campaign(path, root, budget, selected_bindings):
    """Guard every selected G member before G can invoke its E consumers."""
    from run_experiment import LEDGER, RECEIPT
    path = Path(path).resolve()
    receipt = budget.read(path)
    if path.name != RECEIPT:
        raise ValueError('H2 requires the actual G campaign receipt role')
    for name, item in receipt['artifacts'].items():
        budget.bind({'path': name, 'sha256': item['sha256']}, path.parent)
    ledger = budget.read(contained_path(path.parent, LEDGER))
    if LEDGER not in receipt['artifacts'] or ledger['rows'] != receipt['rows']:
        raise ValueError('H2 campaign ledger/receipt role binding differs')
    rows = ledger['rows']
    if not isinstance(rows, list) or not 1 <= len(rows) <= 16:
        raise ValueError('H2 needs exact ordered H1 coverage for every actual G draw, including repeats')
    actual = []
    path_bindings = {}
    for row in rows:
        binding = row.get('receipt')
        if row.get('status') != 'completed' or not isinstance(binding, dict):
            raise ValueError('H2 needs exact ordered H1 coverage for every actual G draw, including repeats')
        member_path = budget.bind(binding, path.parent)
        actual.append((str(member_path), binding['sha256']))
        path_bindings[(binding['path'], binding['sha256'])] = member_path
    expected = [(str(contained_path(root, b['path'])), b['sha256']) for b in selected_bindings]
    if actual != expected:
        raise ValueError('H2 needs exact ordered H1 coverage for every actual G draw, including repeats')
    sampling = receipt['sampling_receipt']
    sampling_path = budget.bind(sampling, path.parent)
    path_bindings[(sampling['path'], sampling['sha256'])] = sampling_path
    historical_roles = {}
    for member_path, _ in actual:
        preflight_selected_e(member_path, root, budget)
        historical_roles.update(preflight_e(member_path, root, budget))
    preflight_e(path, root, budget, path_bindings=path_bindings, historical_roles=historical_roles)


def read_run(binding, root, budget):
    from validate_simulation_receipt import validate_simulation_receipt
    from validate_simulation_protocol import validate_simulation_protocol
    path = budget.bind(binding, root)
    preflight_selected_e(path, root, budget)
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
    outputs = bounded_outputs(data['outputs'], budget)
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


def verified_reference_metadata(run, refs):
    """Carry reviewed reference selectors and current approved numeric origins.

    Called only after the complete H1 error check; H2 recomputes this metadata
    against its exact covered current E member, never guesses parameter IDs.
    """
    metadata = []
    for ref in refs:
        item = {'reference': copy.deepcopy(ref), 'family': ref['family'],
                'output_port': ref['output_port'], 'unit': ref['unit'],
                'approved_origins': None, 'initial_derivative': None,
                'structural_eligible': ref['family'] == 'static_affine'}
        if ref['family'] == 'first_order_constant':
            ps = parameters(run)
            a, b = ps[ref['a_parameter']], ps[ref['b_parameter']]
            inp = next(p for p in run['spec']['inputs'] if p['variable_id'] == ref['input_id'])
            x0 = initial_value(run, ref['initial_selector'])
            derivative = b['value'] * constant_input(run, ref['input_id']) - a['value'] * x0
            # H1 constant/equilibrium trajectories remain valid; only the
            # conservative first structural challenge requires nonzero slope.
            item.update(approved_origins={'a': copy.deepcopy(a), 'b': copy.deepcopy(b),
                'input': copy.deepcopy(inp), 'initial': {'state_id': ref['state_id'],
                    'selector': copy.deepcopy(ref['initial_selector']), 'value': x0,
                    'condition': copy.deepcopy(run['model']['body']['initial_conditions'])}},
                initial_derivative=derivative if finite(derivative) else None,
                structural_eligible=finite(derivative) and derivative != 0)
        metadata.append(item)
    return metadata


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
