"""Deterministic H2 finite metrics; never execute or alter a model."""
from __future__ import annotations

import math
import json
import re
from copy import deepcopy
from pathlib import Path

from runtime_common import load_document
from validate_parameter_provenance import mathematical_models
from validate_simulation_protocol import selected_value
from verification_common import finite, typed_equal

KINDS = ('sensitivity', 'robustness', 'solver_comparison', 'model_comparison')
METHODS = dict(zip(KINDS, ('external_input_oat', 'finite_scenarios', 'solver_metrics', 'structural_metrics')))
RECEIPT_NAME = 'model-verification-receipt.json'
H2_FILES = (
    'core/model_verification_contract.yaml', 'modules/08_model_verification.md',
    'templates/contracts/model_verification.yaml', 'scripts/model_verification_common.py',
    'scripts/validate_model_verification.py', 'scripts/run_model_verification.py',
    'scripts/validate_model_verification_receipt.py', 'packs/evidence/sensitivity.md',
    'packs/evidence/model_comparison.md', 'packs/evidence/solver_comparison.md',
)


def settings_snapshot(value):
    return {key: deepcopy(value[key]) for key in ('claims', 'budget', 'claim_limit')}


def obligation_snapshot(claim):
    return {'target_claim': claim['target_claim'], 'requirement_ids': claim['requirement_ids'],
            'requirements': {item['kind']: item['requirement'] for item in claim['analyses']}}


def selected_model(member):
    report = member['protocol_report']
    model = load_document(Path(report['model_path']))
    return mathematical_models(model)[(report['design_id'], report['model_id'])]


def variable_quantity(member, variable_id):
    variables = selected_model(member)['body']['variables']
    variable = next((item for item in variables if item['id'] == variable_id), None)
    if variable is None:
        raise ValueError('unknown current C observable/input variable')
    return variable['quantity']


def execution_configuration(member, *, input_mode='exact', factor_port=None, solver=True):
    """Compare actual E execution semantics, excluding review/description bytes."""
    spec = deepcopy(member['protocol_report']['run_spec'])
    if not solver:
        spec.pop('solver')
    if input_mode == 'factor':
        for item in spec['inputs']:
            if item['port'] == factor_port:
                item.pop('values')
    elif input_mode == 'scenarios':
        for item in spec['inputs']:
            for key in ('time', 'values', 'interpolation'):
                item.pop(key)
    protocol = member['protocol']
    return {'spec': spec, 'conditions': protocol['conditions'], 'logging': protocol['logging'],
            'selection': protocol['selection'],
            'upstream': {key: member['protocol_report'][key] for key in
                         ('model_path', 'model_sha256', 'mapping_path', 'mapping_sha256',
                          'approval_path', 'approval_sha256', 'parameters_path', 'parameters_sha256',
                          'problem_path', 'problem_sha256', 'model_identity')}}


def constant_level(member, factor):
    item = next((value for value in member['protocol_report']['run_spec']['inputs']
                 if value['port'] == factor['input_port']), None)
    if item is None or item['variable_id'] != factor['variable_id'] or item['unit'] != factor['unit']:
        raise ValueError('OAT factor is not the current approved external input/units')
    values = item['values']
    if not values or not all(finite(v) and v == values[0] for v in values):
        raise ValueError('OAT supports constant external input levels only')
    return values[0]


def output_port(analysis, member_id):
    metric = analysis['metric']
    if member_id == 'primary':
        return metric['primary_output_port']
    mapping = [item['output_port'] for item in metric['member_output_ports'] if item['member_id'] == member_id]
    if len(mapping) != 1:
        raise ValueError('explicit unique member output mapping required')
    return mapping[0]


def metric_value(member, analysis, member_id):
    metric, port = analysis['metric'], output_port(analysis, member_id)
    declarations = member['protocol_report']['run_spec']['metrics']
    if not any(item['output_port'] == port and item['statistic'] == metric['statistic'] and
               item['unit'] == metric['unit'] for item in declarations):
        raise ValueError('H2 metric must be declared in each current frozen E protocol')
    data = member['data']
    output = next((item for item in data['outputs'] if item['port'] == port), None)
    if output is None or output['unit'] != metric['unit']:
        raise ValueError('common output/unit differs from actual E output')
    values = output['values']
    if not values or not all(finite(value) for value in values):
        raise ValueError('finite complete E output values required')
    return {'final': values[-1], 'minimum': min(values), 'maximum': max(values)}[metric['statistic']]


def in_bounds(value, bounds):
    return ((bounds['lower'] is None or value >= bounds['lower']) and
            (bounds['upper'] is None or value <= bounds['upper']))


def _mathematical_anchor(model, selector, kind):
    """Remove names/provenance from a relevant registered mathematical anchor.

    This rejects obvious naming-only differences; it is not symbolic equivalence.
    """
    allowed = {'governing_equations': {'relations'}, 'mechanism': {'mechanisms'},
               'model_order': {'variables', 'order'}, 'physical_abstraction': {'object', 'boundary', 'assumptions'},
               'constitutive_relation': {'relations'}, 'coupling_structure': {'relations', 'mechanisms', 'coupling'},
               'state_representation': {'variables', 'relations'},
               'fidelity': {'mechanisms', 'scales', 'order', 'coupling', 'relations', 'assumptions'}}
    if len(selector) < 2 or selector[0] not in {'body', 'fidelity'} or selector[1] not in allowed[kind]:
        raise ValueError('structural review must anchor a relevant mathematical C structure field')
    if selector[0] == 'fidelity':
        if len(selector) != 2 or selector[1] not in {'mechanisms', 'scales', 'order', 'coupling'}:
            raise ValueError('fidelity anchor must describe substantive mechanisms/scales/order/coupling')
        return selected_value(model, selector)
    field = selector[1]
    if field in {'object', 'boundary'}:
        if len(selector) != 2:
            raise ValueError('physical abstraction must anchor the complete object/boundary')
        return selected_value(model, selector)
    variables = model['body']['variables']
    descriptor = lambda item: {'quantity': item['quantity'], 'roles': sorted(item['roles']), 'unit': item['unit']}
    descriptors = sorted({json.dumps(descriptor(item), sort_keys=True) for item in variables})
    replacements = {}
    for variable in variables:
        tag = 'V' + str(descriptors.index(json.dumps(descriptor(variable), sort_keys=True)))
        replacements[variable['id']] = tag
        replacements[variable['symbol']] = tag
    def expression(text):
        # One substitution avoids replacing a newly inserted token a second time.
        tokens = sorted(replacements, key=len, reverse=True)
        pattern = r'(?<![A-Za-z0-9_])(' + '|'.join(re.escape(token) for token in tokens) + r')(?![A-Za-z0-9_])'
        # Recognize the registered compact derivative spelling dx/dt as well.
        derivatives = sorted((item['symbol'] for item in variables), key=len, reverse=True)
        for symbol in derivatives:
            text = re.sub(r'(?<![A-Za-z0-9_])d' + re.escape(symbol) + r'(?=/d)',
                          lambda match, tag=replacements[symbol]: 'd' + tag, text)
        normalized = re.sub(pattern, lambda match: replacements[match.group(0)], text) if tokens else text
        return re.sub(r'\s+', '', normalized)
    records = model['body'][field]
    if len(selector) == 2:
        chosen = records
        leaf = None
    elif len(selector) in {3, 4} and type(selector[2]) is int:
        chosen = [records[selector[2]]]
        leaf = selector[3] if len(selector) == 4 else None
    else:
        raise ValueError('structural anchor must select a complete substantive record or allowed mathematical leaf')
    if field == 'variables':
        if leaf not in {None, 'quantity', 'roles', 'unit'}:
            raise ValueError('variable identifier/symbol/parameter/provenance is not a structural anchor')
        return [descriptor(item) if leaf is None else item[leaf] for item in chosen]
    if field == 'relations':
        roles = {'governing'} if kind == 'governing_equations' else ({'constitutive'} if kind == 'constitutive_relation' else {'governing', 'constitutive', 'constraint'})
        if leaf not in {None, 'expression'}:
            raise ValueError('relation identifier/reference/provenance is not a mathematical anchor')
        if len(selector) > 2 and chosen[0]['role'] not in roles:
            raise ValueError('relation role is unrelated to the declared mathematical difference')
        chosen = [item for item in chosen if item['role'] in roles]
        if not chosen:
            raise ValueError('no relevant governing/constitutive relation in structural anchor')
        return sorted([{'role': item['role'], 'expression': expression(item['expression'])} for item in chosen],
                      key=lambda item: (item['role'], item['expression']))
    if field == 'mechanisms':
        if leaf not in {None, 'description'}:
            raise ValueError('mechanism identifier/reference is not a material anchor')
        return sorted(expression(item['description']) for item in chosen)
    if field == 'assumptions':
        if leaf not in {None, 'meaning', 'mathematical_role'}:
            raise ValueError('assumption identifier/justification/test/provenance is not a material anchor')
        return [dict(meaning=expression(item['meaning']), mathematical_role=expression(item['mathematical_role']))
                if leaf is None else expression(item[leaf]) for item in chosen]
    raise ValueError('unsupported mathematical structural anchor')


def structural_snapshot(review, primary, member):
    left, right = selected_model(primary), selected_model(member)
    kind = review['difference_kind']
    if kind == 'model_order':
        state_counts = [sum('state' in item['roles'] for item in model['body']['variables']) for model in (left, right)]
        if state_counts[0] == state_counts[1]:
            raise ValueError('model_order comparator needs an actual different state dimension')
    def registered_mathematics(model):
        body = model['body']
        content = {'object': body.get('object'), 'boundary': body.get('boundary'),
                   'variables': sorted([{'quantity': item['quantity'], 'roles': sorted(item['roles']), 'unit': item['unit']}
                                        for item in body['variables']], key=lambda item: json.dumps(item, sort_keys=True))}
        for field, difference in (('relations', 'governing_equations'), ('relations', 'constitutive_relation'),
                                  ('mechanisms', 'mechanism'), ('assumptions', 'physical_abstraction')):
            if not body.get(field):
                continue
            if field == 'relations' and not any(item['role'] == ('governing' if difference == 'governing_equations' else 'constitutive')
                                                for item in body[field]):
                continue
            content[difference] = _mathematical_anchor(model, ['body', field], difference)
        return content
    left_anchor = _mathematical_anchor(left, review['primary_selector'], kind)
    right_anchor = _mathematical_anchor(right, review['member_selector'], kind)
    if typed_equal(registered_mathematics(left), registered_mathematics(right)):
        raise ValueError('registered bodies have no substantive mathematical difference beyond names/provenance/fidelity labels')
    if typed_equal(left_anchor, right_anchor):
        raise ValueError('structural anchors have no substantive mathematical difference after removing naming/provenance')
    return {'difference_kind': kind, 'primary_selector': review['primary_selector'],
            'member_selector': review['member_selector'], 'primary_value': selected_value(left, review['primary_selector']),
            'member_value': selected_value(right, review['member_selector']),
            'primary_conditions': primary['protocol']['conditions'], 'member_conditions': member['protocol']['conditions'],
            'rationale': review['rationale'], 'equivalence_review': review['equivalence_review'],
            'physical_target': review['physical_target']}


def compute_assessment(value, members):
    """Recompute every registered finite claim, keeping threshold failures as evidence."""
    claims = []
    for claim in value['claims']:
        results, supported = [], True
        for analysis in claim['analyses']:
            if analysis['requirement'] != 'required':
                results.append({'kind': analysis['kind'], 'requirement': analysis['requirement'],
                                'reason': analysis['reason'], 'disposition': analysis['requirement'], 'rows': []})
                continue
            metric, kind, rows = analysis['metric'], analysis['kind'], []
            baseline = metric_value(members['primary'], analysis, 'primary')
            if kind == 'sensitivity':
                baseline_level = constant_level(members['primary'], analysis['factor'])
            analysis_supported = True
            for member_id in analysis['member_ids']:
                observed = metric_value(members[member_id], analysis, member_id)
                difference = observed - baseline
                if not finite(difference):
                    raise ValueError('H2 finite metric difference overflow')
                relative = difference / abs(baseline) if baseline != 0 else None
                if relative is not None and not finite(relative):
                    raise ValueError('H2 relative metric difference overflow')
                row = {'member_id': member_id, 'value': observed, 'difference': difference,
                       'relative_difference': relative, 'unit': metric['unit']}
                if kind == 'sensitivity':
                    level = constant_level(members[member_id], analysis['factor'])
                    delta = level - baseline_level
                    slope = difference / delta if member_id != 'primary' else None
                    if not finite(delta) or slope is not None and not finite(slope):
                        raise ValueError('H2 finite difference overflow')
                    passed = True if slope is None else in_bounds(slope, analysis['bounds'])
                    row.update(input_level=level, input_difference=delta, finite_difference=slope,
                               finite_difference_unit=analysis['bounds']['unit'], passed=passed)
                elif kind == 'robustness':
                    row.update(passed=in_bounds(observed, analysis['bounds']))
                else:
                    criterion = analysis['comparison']
                    limit = criterion['absolute_tolerance'] + criterion['relative_tolerance'] * max(abs(baseline), abs(observed))
                    if not finite(limit):
                        raise ValueError('H2 comparison tolerance overflow')
                    row.update(absolute_difference=abs(difference), tolerance=limit, passed=abs(difference) <= limit)
                analysis_supported &= row['passed']
                rows.append(row)
            supported &= analysis_supported
            results.append({'kind': kind, 'requirement': 'required', 'method': analysis['method'],
                            'disposition': 'support' if analysis_supported else claim['failure_disposition'],
                            'rows': rows})
        claims.append({'id': claim['id'], 'target_claim': claim['target_claim'], 'analyses': results,
                       'disposition': 'support' if supported else claim['failure_disposition'],
                       'impact_scope': claim['impact_scope'],
                       'required_action': None if supported else claim['required_action'],
                       'return_stage': None if supported else claim['return_stage'], 'claim_limit': claim['claim_limit']})
    supported = bool(claims) and all(claim['disposition'] == 'support' for claim in claims)
    return {'model_verification_decided': bool(claims), 'claim_supported': supported,
            'model_verified': supported, 'claims': claims, 'claim_limit': value['claim_limit'],
            'physical_validation': False, 'environment_checked': False, 'execution_allowed': False}
