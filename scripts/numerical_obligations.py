"""Source-selected numerical obligations and three-level recorded evidence.

All public functions are pure.  Their callers independently establish current
approval, native artifact identity, operation qualification and source review.
"""
from __future__ import annotations

import bisect
import math

from numerical_math_common import (Series, TIME_DIMENSION, WorkBudget, checked_window,
    dimension_add, dimensions, evaluate_expression, level_environment, number,
    observable_scale, rounding_time, stable_product, union_knots, unit_dimensions, unit_scale, validate_expression)
from verification_common import HARD_BUDGET, finite, typed_equal

KINDS = ('residual', 'constraint', 'conservation', 'event_localization', 'numerical_drift')
METHODS = ('ode4_step_refinement', 'ode45_tolerance_refinement', 'ode15s_tolerance_refinement')
CRITERIA = ('absolute_tolerance', 'relative_tolerance', 'contraction_limit', 'roundoff_floor')
OBSERVABLE_FIELDS = {'id', 'kind', 'variable_id', 'unit', 'dimensions', 'port', 'block_path', 'code_name', 'scale', 'offset', 'canonical_unit', 'relation_ids'}
CHECK_FIELDS = {'id', 'kind', 'window', 'source_ids', 'relation_ids', 'unit', 'dimensions',
    'absolute_tolerance', 'relative_tolerance', 'scale', 'expression', 'mode', 'inventory', 'flux',
    'state', 'rhs', 'relation', 'threshold', 'reference', 'drift_tolerance', 'rate_unit',
    'direction', 'expected_count', 'matching', 'time_tolerance', 'value_tolerance',
    'max_bracket_width', 'include_boundary', 'event_type', 'contraction_limit',
    'roundoff_floor', 'convergence_required'}


def policy_scope(policy):
    scope = policy.get('scope', policy.get('comparison_scope'))
    trajectory = policy.get('trajectory')
    if trajectory is not None:
        if not isinstance(trajectory, dict) or set(trajectory) - {'mode', 'max_gap'} or trajectory.get('mode') not in ('actual_points', 'pwl_union'):
            raise ValueError('explicit supported trajectory policy required')
        implied = 'pwl_trajectory' if trajectory['mode'] == 'pwl_union' else 'actual_points'
        if scope is not None and scope != implied:
            raise ValueError('trajectory and comparison scope disagree')
        scope = implied
        if trajectory.get('max_gap') is not None and number(trajectory['max_gap']) <= 0:
            raise ValueError('maximum trajectory gap must be positive')
    scope = 'actual_points' if scope is None else scope
    if scope not in ('actual_points', 'pwl_trajectory') or policy.get('comparison_scope', scope) != scope:
        raise ValueError('unsupported or contradictory comparison scope')
    return scope


def validate_observables(observables, context, specs):
    if not isinstance(observables, list) or len(observables) > 128:
        raise ValueError('bounded observable list required')
    variables = {v['id']: v for v in context.get('variables', [])}
    relations = {r['id']: r for r in context.get('relations', [])}
    symbols = {}
    for symbol in observables:
        if not isinstance(symbol, dict) or set(symbol) - OBSERVABLE_FIELDS or not {'id', 'kind', 'unit', 'dimensions'} <= set(symbol):
            raise ValueError('observable exact typed fields differ')
        if type(symbol['id']) is not str or not symbol['id'] or symbol['id'] in symbols:
            raise ValueError('observable IDs must be nonempty unique strings')
        kind = symbol['kind']
        if kind not in ('time', 'output', 'state', 'input', 'parameter'):
            raise ValueError('unsupported actual observable kind')
        common = {'id', 'kind', 'unit', 'dimensions', 'scale', 'offset', 'canonical_unit', 'relation_ids'}
        identity = {'time': set(), 'output': {'port', 'variable_id', 'block_path'},
                    'input': {'port', 'variable_id', 'block_path'}, 'state': {'variable_id', 'block_path'},
                    'parameter': {'variable_id', 'code_name'}}[kind]
        if set(symbol)-common-identity:
            raise ValueError('observable contains identity fields for a different kind')
        dim = dimensions(symbol['dimensions'])
        declared_unit = symbol.get('canonical_unit', symbol['unit'])
        if unit_dimensions(declared_unit) != dim:
            raise ValueError('observable unit/dimension mismatch; custom units need an explicit canonical mapping')
        if symbol.get('scale', 1) != 1 and not symbol.get('canonical_unit'):
            raise ValueError('observable conversion scale requires an explicit canonical unit')
        if 'offset' in symbol and not symbol.get('canonical_unit'):
            raise ValueError('affine observable offset requires an explicit canonical unit')
        if unit_dimensions(symbol['unit']) is None and not {'scale', 'canonical_unit'} <= set(symbol):
            raise ValueError('custom observable unit requires a reviewed explicit conversion scale')
        observable_scale(symbol)
        number(symbol.get('offset', 0), 'observable offset')
        if number(symbol.get('scale', 1)) <= 0:
            raise ValueError('observable scale must be positive')
        if kind == 'time':
            if symbol['unit'] != 's' or dim != TIME_DIMENSION or symbol.get('scale', 1) != 1 or symbol.get('offset', 0) != 0:
                raise ValueError('time observable must be seconds with time dimension')
        else:
            variable = variables.get(symbol.get('variable_id'))
            if variable is None or not typed_equal(variable.get('unit'), symbol['unit']):
                raise ValueError('observable does not bind a current C variable/unit')
            if symbol['unit'] is None:
                raise ValueError('mathematical observable requires a known approved unit')
            if kind == 'state' and ('state' not in variable.get('roles', []) or type(symbol.get('block_path')) is not str or not symbol['block_path']):
                raise ValueError('state observable requires current state identity and exact BlockPath')
            if kind == 'parameter' and 'parameter' not in variable.get('roles', []):
                raise ValueError('parameter observable is not a C parameter')
            if kind == 'parameter':
                bindings = [p for p in context.get('parameter_bindings', []) if p.get('reference', p.get('model_ref', p.get('variable_ref', {}))).get('variable_id') == symbol['variable_id']]
                if len(bindings) != 1 or bindings[0].get('code_name') != symbol.get('code_name') or not typed_equal(bindings[0].get('unit'), symbol['unit']):
                    raise ValueError('parameter observable requires the exact current D variable/code_name binding')
                for spec in specs:
                    actual = [p for p in spec.get('parameters', []) if p.get('code_name') == symbol['code_name']]
                    if len(actual) != 1 or not typed_equal(actual[0].get('unit'), symbol['unit']) or not finite(actual[0].get('value')):
                        raise ValueError('parameter observable is absent or differs in the frozen physical specification')
            if kind in ('output', 'input'):
                if type(symbol.get('port')) is not int or symbol['port'] < 1:
                    raise ValueError('actual observable requires typed root port')
                for spec in specs:
                    items = [v for v in spec[kind+'s'] if v['port'] == symbol['port']]
                    if len(items) != 1 or items[0]['variable_id'] != symbol['variable_id'] or not typed_equal(items[0]['unit'], symbol['unit']):
                        raise ValueError('observable root port differs from approved physical specification')
                    if 'block_path' in symbol and not typed_equal(symbol['block_path'], items[0].get('block_path')):
                        raise ValueError('observable BlockPath differs from approved root binding')
        if not isinstance(symbol.get('relation_ids', []), list) or not set(symbol.get('relation_ids', [])) <= set(relations):
            raise ValueError('observable relation anchor missing from current C')
        symbols[symbol['id']] = symbol
    return symbols


def _expression_ids(expression):
    result, pending = set(), [expression]
    while pending:
        node = pending.pop()
        if node['op'] in ('variable', 'derivative', 'integral'):
            result.add(node['id'])
        pending.extend(node.get('args', []))
    return result


def validate_check(check, symbols, budget, context):
    if not isinstance(check, dict) or set(check) - CHECK_FIELDS or not {'id', 'kind', 'window', 'source_ids', 'relation_ids', 'unit', 'dimensions'} <= set(check):
        raise ValueError('complete exact typed numerical check definition required')
    if type(check['id']) is not str or not check['id'] or check['kind'] not in KINDS:
        raise ValueError('unique numerical check identity/kind required')
    checked_window(check['window'])
    if not isinstance(check['source_ids'], list) or not check['source_ids'] or any(type(x) is not str or not x for x in check['source_ids']) or len(set(check['source_ids'])) != len(check['source_ids']):
        raise ValueError('check requires explicit source IDs')
    relations = {r['id']: r for r in context.get('relations', [])}
    if not isinstance(check['relation_ids'], list) or not check['relation_ids'] or not set(check['relation_ids']) <= set(relations):
        raise ValueError('check requires current C relation anchors')
    expected = dimensions(check['dimensions'])
    if unit_dimensions(check['unit']) != expected:
        raise ValueError('numerical check unit/dimension mismatch')
    kind = check['kind']
    common = {'id', 'kind', 'window', 'source_ids', 'relation_ids', 'unit', 'dimensions',
              'contraction_limit', 'roundoff_floor', 'convergence_required'}
    fields = {'residual': {'expression', 'mode', 'inventory', 'flux', 'state', 'rhs', 'threshold'},
              'constraint': {'expression', 'relation', 'threshold'},
              'conservation': {'inventory', 'flux'},
              'numerical_drift': {'expression', 'reference', 'drift_tolerance', 'rate_unit'},
              'event_localization': {'expression', 'threshold', 'direction', 'expected_count', 'matching',
                  'time_tolerance', 'value_tolerance', 'max_bracket_width', 'include_boundary', 'event_type'}}
    permitted = common | fields[kind] | (set() if kind == 'event_localization' else {'absolute_tolerance', 'relative_tolerance', 'scale'})
    if set(check) - permitted:
        raise ValueError('numerical check contains fields for a different check kind')
    expressions = []
    if kind == 'conservation' or kind == 'residual' and check.get('mode', 'algebraic') == 'integral':
        if 'expression' in check or 'threshold' in check or 'inventory' in check and 'state' in check or 'flux' in check and 'rhs' in check:
            raise ValueError('integrated balance expression/aliases are ambiguous')
        inventory = check.get('inventory', check.get('state'))
        flux = check.get('flux', check.get('rhs'))
        if inventory is None or flux is None:
            raise ValueError('integrated balance requires inventory/state and flux/rhs')
        inv_dim = validate_expression(inventory, symbols, budget)
        flux_dim = validate_expression(flux, symbols, budget)
        if inv_dim != expected or dimension_add(flux_dim, TIME_DIMENSION) != expected:
            raise ValueError('integrated balance units/dimensions differ')
        expressions.extend((inventory, flux))
    else:
        if any(k in check for k in ('inventory', 'flux', 'state', 'rhs')):
            raise ValueError('algebraic check contains unused balance terms')
        expression = check.get('expression')
        if expression is None or validate_expression(expression, symbols, budget) != expected:
            raise ValueError('check expression dimension differs from declared quantity')
        expressions.append(expression)
        if check.get('reference') is not None:
            if kind != 'numerical_drift' or validate_expression(check['reference'], symbols, budget) != expected:
                raise ValueError('drift reference dimensions differ')
            expressions.append(check['reference'])
    referenced = {symbols[i].get('variable_id') for expression in expressions for i in _expression_ids(expression)} - {None}
    anchored = {i for relation in check['relation_ids'] for i in relations[relation].get('variable_ids', [])}
    if not referenced <= anchored:
        raise ValueError('check relation anchors do not cover every referenced C variable')
    if kind == 'event_localization':
        required = {'threshold', 'direction', 'expected_count', 'matching', 'time_tolerance', 'value_tolerance', 'max_bracket_width'}
        if not required <= set(check) or check['direction'] not in ('rising', 'falling', 'either') or check['matching'] not in ('first', 'all'):
            raise ValueError('complete prior event direction/count/matching rules required')
        if type(check['expected_count']) is not int or not 0 <= check['expected_count'] <= 1024:
            raise ValueError('bounded integer expected event count required')
        for field in ('threshold', 'time_tolerance', 'value_tolerance', 'max_bracket_width'):
            number(check[field], 'event '+field)
        if check['time_tolerance'] <= 0 or check['value_tolerance'] < 0 or check['max_bracket_width'] <= 0:
            raise ValueError('invalid prior event tolerances')
        if type(check.get('include_boundary', False)) is not bool or check.get('event_type', 'crossing') not in ('crossing', 'contact'):
            raise ValueError('typed event boundary/type rules required')
    else:
        if not {'absolute_tolerance', 'relative_tolerance', 'scale'} <= set(check):
            raise ValueError('complete prior residual/violation scale and tolerance required')
        for field in ('absolute_tolerance', 'relative_tolerance', 'scale'):
            number(check[field], field)
        if check['absolute_tolerance'] <= 0 or check['relative_tolerance'] < 0 or check['scale'] < 0:
            raise ValueError('invalid numerical check tolerance/scale')
        if kind == 'constraint' and (check.get('relation') not in ('eq', 'le', 'ge') or 'threshold' not in check):
            raise ValueError('constraint equality/inequality direction required')
        if kind == 'numerical_drift' and (number(check.get('drift_tolerance'), 'drift rate tolerance') <= 0 or check.get('rate_unit') != check['unit']+'/s'):
            raise ValueError('positive drift rate criterion and derived unit required')
    if 'threshold' in check:
        number(check['threshold'], 'check threshold')
    if check.get('mode', 'algebraic') not in ('algebraic', 'integral'):
        raise ValueError('unsupported residual representation')
    if type(check.get('convergence_required', False)) is not bool:
        raise ValueError('typed check convergence requirement required')
    if check.get('convergence_required'):
        if not 0 < number(check.get('contraction_limit')) < 1 or number(check.get('roundoff_floor')) < 0:
            raise ValueError('check convergence requires prior contraction and roundoff floor')
        if kind != 'event_localization' and check['roundoff_floor'] > check['absolute_tolerance']:
            raise ValueError('check floor exceeds absolute tolerance')


def refinement_summary(output, samples):
    if len(samples) != 3 or not samples[0] or any(len(s) != len(samples[0]) for s in samples):
        raise ValueError('three complete common comparison arrays required')
    scale = max(abs(number(v)) for values in samples for v in values)
    tolerance = number(output['absolute_tolerance'] + output['relative_tolerance']*scale, 'refinement tolerance')
    d01 = number(max(abs(a-b) for a, b in zip(samples[0], samples[1])), 'primary refinement difference')
    d12 = number(max(abs(a-b) for a, b in zip(samples[1], samples[2])), 'fine refinement difference')
    floor = output['roundoff_floor']
    at_floor = d01 <= floor
    contraction = d12 <= floor if at_floor else d12 <= output['contraction_limit']*d01
    order = (math.log(d01)-math.log(d12))/math.log(2) if d01 > floor and d12 > floor and d01 > 0 and d12 > 0 else None
    if order is not None:
        number(order, 'empirical refinement order')
    result = {k: output[k] for k in ('port', 'variable_id', 'unit') if k in output}
    if output.get('kind') == 'state':
        result.update(kind='state', block_path=output['block_path'])
    result.update(sample_count=len(samples[0]), scale=scale, D01=d01, D12=d12, tolerance=tolerance,
        primary_difference_satisfied=d01 <= tolerance, fine_difference_satisfied=d12 <= tolerance,
        contraction_satisfied=contraction, agreement_regime='roundoff_floor' if at_floor and d12 <= floor else 'resolved_difference',
        empirical_order=order, criteria_satisfied=d01 <= tolerance and d12 <= tolerance and contraction)
    return result


def _events(times, values, check):
    shifted = [number(v-check['threshold'], 'event function') for v in values]
    events, errors = [], []
    for i, value in enumerate(shifted):
        if value != 0:
            if abs(value) <= check['value_tolerance'] and (i == 0 or (shifted[i-1] > 0) == (value > 0)) and (i == len(shifted)-1 or (shifted[i+1] > 0) == (value > 0)):
                errors.append('event value tolerance contains an unresolved contact')
            continue
        left = shifted[i-1] if i else None
        right = shifted[i+1] if i+1 < len(shifted) else None
        if left == 0 or right == 0:
            errors.append('event zero platform has no unique location')
            continue
        if left is None or right is None:
            if not check.get('include_boundary', False):
                errors.append('boundary event requires an explicit source rule')
                continue
            slope = right if left is None else -left
            direction = 'rising' if slope > 0 else 'falling'
            bracket = [times[i], times[i+1]] if left is None else [times[i-1], times[i]]
        elif (left > 0) != (right > 0):
            direction = 'rising' if right > left else 'falling'
            bracket = [times[i-1], times[i+1]]
        elif check.get('event_type', 'crossing') == 'contact':
            direction, bracket = 'contact', [times[i-1], times[i+1]]
        else:
            errors.append('grazing event does not establish a unique crossing')
            continue
        if check['direction'] == 'either' or direction == check['direction']:
            events.append({'time': times[i], 'bracket': bracket, 'direction': direction, 'reconstructed_zero': True})
    for i, (a, b) in enumerate(zip(shifted, shifted[1:])):
        if a == 0 or b == 0 or (a > 0) == (b > 0):
            continue
        direction = 'rising' if b > a else 'falling'
        if check['direction'] != 'either' and direction != check['direction']:
            continue
        if abs(a) >= abs(b):
            fraction = 1/(1+abs(b)/abs(a))
        else:
            ratio = abs(a)/abs(b)
            fraction = ratio/(1+ratio)
        events.append({'time': number(times[i]+fraction*(times[i+1]-times[i]), 'PWL event time'),
                       'bracket': [times[i], times[i+1]], 'direction': direction, 'reconstructed_zero': False})
    events.sort(key=lambda e: e['time'])
    if any(b['time']-a['time'] <= check['time_tolerance'] for a, b in zip(events, events[1:])):
        errors.append('events are not uniquely separated at the prior time tolerance')
    if any(e['bracket'][1]-e['bracket'][0] > check['max_bracket_width'] for e in events):
        errors.append('reconstructed event bracket exceeds prior localization width')
    return events, errors


def _event_sample_brackets(event, expression, observables, environment, budget):
    """Retain actual support for every observed term of a reconstructed event."""
    brackets = []
    referenced = _expression_ids(expression)
    for symbol in observables:
        entry = environment[symbol['id']]
        if symbol['id'] not in referenced or 'series' not in entry:
            continue
        series = entry['series']
        left, right = event['bracket']
        first = max(0, bisect.bisect_right(series.time, left)-1)
        last = min(len(series.time)-1, bisect.bisect_left(series.time, right))
        budget.charge(last-first+1)
        brackets.append({'observable_id': symbol['id'], 'kind': symbol['kind'],
            **{k: symbol[k] for k in ('port', 'variable_id', 'block_path') if k in symbol},
            'unit': symbol['unit'], 'interpolation': series.interpolation,
            'native_samples': [{'index': i, 'time': series.native_time[i], 'value': series.native_values[i]} for i in range(first, last+1)]})
    return brackets


def _balance(times, inventory, flux):
    """Exact inventory-PWL minus flux-PWL integral; inspect interior extrema."""
    integrated, extrema, segments = 0.0, [(times[0], 0.0)], []
    for a, b, x0, x1, f0, f1 in zip(times, times[1:], inventory, inventory[1:], flux, flux[1:]):
        dt = b-a
        d0 = number(x0-inventory[0]-integrated, 'balance defect')
        scale = max(abs(f0), abs(f1))
        change = 0.0 if scale == 0 else f1/scale-f0/scale
        # Represent the segment in u=(t-a)/dt.  Dividing curvature by dt
        # could underflow before multiplying by dt^2 and hide a real defect.
        linear = number(x1-x0-stable_product(dt, f0), 'normalized balance derivative')
        quadratic = -stable_product(dt, scale, change, divisor=2, label='normalized balance curvature')
        segments.append((a, dt, d0, linear, quadratic))
        if quadratic != 0 and (linear > 0) != (quadratic > 0) and abs(linear)/2 < abs(quadratic):
            stationary = -linear/quadratic/2
            if 0 < stationary < 1:
                value = math.fsum((d0, stable_product(linear, stationary), stable_product(quadratic, stationary, stationary)))
                extrema.append((a+stationary*dt, number(value, 'interior balance defect')))
        mean = 0.0 if scale == 0 else (f0/scale+f1/scale)/2
        integrated = number(integrated+stable_product(dt, scale, mean), 'balance flux integral')
        extrema.append((b, number(x1-inventory[0]-integrated)))
    return extrema, segments


def _time_weighted_slope(segments, window):
    start, stop = checked_window(window)
    span, terms = stop-start, []
    for a, h, q0, q1, q2 in segments:
        ratio, offset = h/span, (a-start)/span-.5
        linear = stable_product(q1, h, label='local drift change')
        quadratic = stable_product(q2, h, h, label='local drift curvature')
        # Normalize time to remove the avoidable span^3 intermediate scale.
        terms.append(number(math.fsum((stable_product(ratio, offset, q0),
            stable_product(ratio, offset, linear, .5), stable_product(ratio, offset, quadratic, 1/3),
            stable_product(ratio, ratio, q0, .5), stable_product(ratio, ratio, linear, 1/3),
            stable_product(ratio, ratio, quadratic, .25))), 'normalized drift moment'))
    return stable_product(12, math.fsum(terms), divisor=span, label='time-weighted drift rate')


def evaluate_check(check, level, policy, context, budget):
    result = {'id': check['id'], 'kind': check['kind'], 'unit': check['unit'],
              'scope': 'recorded_pwl_reconstruction', 'complete': False, 'criteria_satisfied': False, 'errors': []}
    try:
        window = check['window']
        start, stop = checked_window(window)
        spec = level['run_spec']
        if start < spec['start_time'] or stop > spec['stop_time']:
            raise ValueError('check window exceeds actual complete physical interval')
        environment, series = level_environment(level, policy.get('observables', []), budget,
            max_samples=policy.get('budget', {}).get('max_samples_per_output', 12001),
            max_gap=(policy.get('trajectory') or {}).get('max_gap'))
        times = union_knots(series, window, budget)
        kind = check['kind']
        quantity_scale = unit_scale(check['unit'])
        if kind == 'conservation' or kind == 'residual' and check.get('mode') == 'integral':
            inventory = check.get('inventory', check.get('state'))
            flux = check.get('flux', check.get('rhs'))
            inv_values = [evaluate_expression(inventory, environment, t, budget)/quantity_scale for t in times]
            flux_values = [evaluate_expression(flux, environment, t, budget)/quantity_scale for t in times]
            extrema, segments = _balance(times, inv_values, flux_values)
            result.update(inventory_start=inv_values[0], inventory_end=inv_values[-1],
                flux_integral=Series(times, flux_values).integral(window), balance_terminal=extrema[-1][1])
            violation_time, violation = max(extrema, key=lambda pair: abs(pair[1]))
            violation = abs(violation)
        else:
            values = [evaluate_expression(check['expression'], environment, t, budget)/quantity_scale for t in times]
            if kind == 'event_localization':
                events, errors = _events(times, values, check)
                for event in events:
                    event['sample_brackets'] = _event_sample_brackets(event, check['expression'], policy.get('observables', []), environment, budget)
                    if any(record['native_samples'][-1]['time']-record['native_samples'][0]['time'] > check['max_bracket_width'] for record in event['sample_brackets']):
                        errors.append('actual observable support exceeds prior event localization width')
                result.update(events=events, observed_count=len(events), expected_count=check['expected_count'],
                    complete=not errors, criteria_satisfied=not errors and len(events) == check['expected_count'])
                result['errors'].extend(errors)
                result.update(window=list(window), evaluated_knot_count=len(times), representation='PWL of event-function values on complete observable-union knots')
                return result
            threshold = check.get('threshold', 0)
            if kind == 'numerical_drift':
                if check.get('reference') is not None:
                    values = [number(v-evaluate_expression(check['reference'], environment, t, budget)/quantity_scale, 'detrended value') for t, v in zip(times, values)]
                baseline = values[0]
                values = [number(v-baseline, 'detrended change') for v in values]
                violations = [abs(v) for v in values]
                segments = [(a, b-a, y0, (y1-y0)/(b-a), 0) for a, b, y0, y1 in zip(times, times[1:], values, values[1:])]
                slope = _time_weighted_slope(segments, window)
                result.update(slope=slope, rate_unit=check['rate_unit'], terminal_change=number(values[-1]),
                              drift_rate_satisfied=abs(slope) <= check['drift_tolerance'])
            elif kind == 'constraint' and check['relation'] == 'le':
                violations = [max(0, v-threshold) for v in values]
            elif kind == 'constraint' and check['relation'] == 'ge':
                violations = [max(0, threshold-v) for v in values]
            else:
                violations = [abs(v-threshold) for v in values]
            violation = number(max(violations), 'maximum reconstructed violation')
            violation_time = times[violations.index(violation)]
        tolerance = number(check['absolute_tolerance']+check['relative_tolerance']*check['scale'], 'check tolerance')
        result.update(complete=True, maximum_violation=number(violation), violation_time=violation_time,
            tolerance=tolerance, window=list(window), evaluated_knot_count=len(times),
            representation='PWL of derived expression samples; exact PWL balance integration when applicable',
            criteria_satisfied=violation <= tolerance and result.get('drift_rate_satisfied', True))
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError, ZeroDivisionError) as error:
        result['errors'].append(str(error))
    return result


def validate_numeric_policy(policy, specs, context=None):
    context = context or {}
    if not isinstance(policy, dict) or len(specs) != 3 or policy.get('method') not in METHODS:
        raise ValueError('explicit supported three-level numeric method required')
    allowed = {'method', 'scope', 'comparison_scope', 'solver_levels', 'comparison_times', 'outputs',
               'obligations', 'budget', 'claim_limit', 'trajectory', 'observables', 'checks', 'math_budget', 'continuous_scope'}
    if set(policy) - allowed:
        raise ValueError('numerical policy exact fields differ')
    read_budget = policy.get('budget')
    if not isinstance(read_budget, dict) or set(read_budget) != set(HARD_BUDGET) or any(type(v) is not int or v < 1 or v > HARD_BUDGET[k] for k, v in read_budget.items()) or read_budget['max_samples_per_output'] < 2:
        raise ValueError('exact bounded typed numeric read/sample budgets required')
    if type(policy.get('claim_limit')) is not str or not policy['claim_limit'].strip():
        raise ValueError('explicit numerical claim limit required')
    scope = policy_scope(policy)
    work = WorkBudget(policy.get('math_budget'))
    if (scope == 'pwl_trajectory' or policy.get('checks') or policy.get('observables')) and policy.get('math_budget') is None:
        raise ValueError('new numerical analyses require a source-declared mathematical budget')
    from validate_numerical_verification import uniform_grid
    method = policy['method']
    first = specs[0]
    checked_window([first['start_time'], first['stop_time']])
    base_solver = first['solver']
    from validate_simulation_protocol import SOLVER_FIELDS
    for index, spec in enumerate(specs):
        if not typed_equal({k: v for k, v in spec.items() if k != 'solver'}, {k: v for k, v in first.items() if k != 'solver'}):
            raise ValueError('numeric levels changed physical execution specification')
        solver = spec['solver']
        if not isinstance(solver, dict) or set(solver) != set(SOLVER_FIELDS) or solver.get('zero_crossing') not in ('EnableAll', 'DisableAll'):
            raise ValueError('numeric solver requires exact controlled SOLVER_FIELDS without protocol metadata')
        if method == 'ode4_step_refinement':
            if solver['type'] != 'fixed-step' or any(solver[k] is not None for k in ('max_step', 'min_step', 'initial_step', 'rel_tol', 'abs_tol')):
                raise ValueError('numeric fixed solver type/applicability differs')
        else:
            if solver['type'] != 'variable-step' or solver['fixed_step'] is not None or any(not finite(solver[k]) or solver[k] <= 0 for k in ('max_step', 'min_step', 'initial_step', 'rel_tol', 'abs_tol')) or not solver['min_step'] <= solver['initial_step'] <= solver['max_step']:
                raise ValueError('numeric variable solver type/positive ordered settings differ')
        allowed = {'fixed_step'} if method == 'ode4_step_refinement' else {'rel_tol', 'abs_tol'}
        if not typed_equal({k: v for k, v in solver.items() if k not in allowed}, {k: v for k, v in base_solver.items() if k not in allowed}):
            raise ValueError('numeric levels changed non-refined solver settings')
        expected_solver = 'ode4' if method == 'ode4_step_refinement' else 'ode45' if method == 'ode45_tolerance_refinement' else 'ode15s'
        if solver['name'] != expected_solver:
            raise ValueError('numeric method and actual solver differ')
        for field in allowed:
            factor = 2**index if method == 'ode4_step_refinement' else 10**index
            expected_value = base_solver[field] if index == 0 else base_solver[field]/factor
            if number(solver[field]) <= 0 or not typed_equal(solver[field], expected_value):
                raise ValueError('numeric levels do not match exact declared refinement ratios')
    if 'solver_levels' in policy and not typed_equal(policy['solver_levels'], [s['solver'] for s in specs]):
        raise ValueError('actual solver levels differ from the frozen numerical policy')
    times = policy.get('comparison_times')
    if times is not None and (not isinstance(times, list) or len(times) < 2 or any(not finite(t) for t in times) or any(a >= b for a, b in zip(times, times[1:]))):
        raise ValueError('finite ordered source comparison times required')
    if method == 'ode4_step_refinement':
        limit = policy.get('budget', {}).get('max_samples_per_output', 3001)-1 if 'scope' in policy or 'trajectory' in policy else 3000
        grids = [uniform_grid(s['start_time'], s['stop_time'], s['solver']['fixed_step'], max_steps=limit) for s in specs]
        if scope == 'actual_points' and not typed_equal(times, grids[0]):
            raise ValueError('fixed comparison_times must be the complete primary integer grid')
        if any(rounding_time(t) >= min(s['solver']['fixed_step'] for s in specs)/32 for g in grids for t in g):
            raise ValueError('time roundoff tolerance is too large for the finest fixed step')
        for signal in first.get('inputs', []):
            constant = all(v == signal['values'][0] for v in signal['values'])
            if not constant and signal['interpolation'] != 'linear':
                raise ValueError('fixed refinement requires constant or continuous PWL inputs')
            if not constant and any(first['start_time'] <= t <= first['stop_time'] and not any(abs(t-g) <= rounding_time(g) for g in grids[0]) for t in signal['time']):
                raise ValueError('input breakpoint is not aligned with the complete primary fixed grid')
    elif scope == 'actual_points' and not typed_equal(times, [first['start_time'], first['stop_time']]):
        raise ValueError('legacy tolerance comparison_times must be the two actual endpoints')
    outputs = policy.get('outputs')
    if not isinstance(outputs, list) or not outputs or len(outputs) > 128:
        raise ValueError('complete bounded output/state criteria list required')
    declared_root = [{k: o[k] for k in ('port', 'variable_id', 'unit')} for o in outputs if o.get('kind', 'output') == 'output']
    expected_root = [{k: o[k] for k in ('port', 'variable_id', 'unit')} for o in first['outputs']]
    if not typed_equal(declared_root, expected_root):
        raise ValueError('numeric policy must cover every declared root output in exact order')
    identities = set()
    variables = {v['id']: v for v in context.get('variables', [])}
    for output in outputs:
        if not isinstance(output, dict) or set(output) - {'kind', 'port', 'variable_id', 'block_path', 'unit', *CRITERIA} or not {'variable_id', 'unit', *CRITERIA} <= set(output):
            raise ValueError('exact numerical output/state criteria fields required')
        kind = output.get('kind', 'output')
        if kind not in ('output', 'state') or kind == 'output' and (type(output.get('port')) is not int or output['port'] < 1):
            raise ValueError('typed numerical output/state identity required')
        identity = (kind, output.get('port'), output.get('variable_id'), output.get('block_path'))
        if identity in identities:
            raise ValueError('duplicate numeric output/state criteria')
        identities.add(identity)
        if kind == 'state' and (type(output.get('block_path')) is not str or 'port' in output):
            raise ValueError('state criteria require exact BlockPath without a fabricated port')
        if kind == 'state':
            variable = variables.get(output.get('variable_id'))
            if variable is None or 'state' not in variable.get('roles', []) or not typed_equal(output['unit'], variable.get('unit')):
                raise ValueError('state refinement criteria do not bind a current C state/unit')
        for key in CRITERIA:
            number(output.get(key), 'output '+key)
        if output['absolute_tolerance'] <= 0 or output['relative_tolerance'] < 0 or not 0 < output['contraction_limit'] < 1 or not 0 <= output['roundoff_floor'] <= output['absolute_tolerance']:
            raise ValueError('invalid prior refinement tolerances/contraction/floor')
    symbols = validate_observables(policy.get('observables', []), context, specs)
    for symbol in symbols.values():
        if symbol['kind'] == 'state' and not any(o.get('kind') == 'state' and all(typed_equal(o.get(k), symbol[k]) for k in ('variable_id', 'unit', 'block_path')) for o in outputs):
            raise ValueError('state observable is not covered by complete numerical state refinement criteria')
    checks = policy.get('checks', [])
    if not isinstance(checks, list) or len(checks) > work.limits['max_checks']:
        raise ValueError('complete check list exceeds mathematical budget')
    ids = set()
    for check in checks:
        validate_check(check, symbols, work, context)
        if check['id'] in ids:
            raise ValueError('numerical check IDs must be unique')
        ids.add(check['id'])
        if check['window'][0] < first['start_time'] or check['window'][1] > first['stop_time']:
            raise ValueError('check window exceeds physical interval')
        pending = [check[k] for k in ('expression', 'reference', 'inventory', 'flux', 'state', 'rhs') if k in check]
        while pending:
            node = pending.pop()
            if node['op'] == 'integral' and not first['start_time'] <= node['start'] <= check['window'][0]:
                raise ValueError('integral observable lacks complete prior start/window coverage')
            pending.extend(node.get('args', []))
    obligations = policy.get('obligations')
    if not isinstance(obligations, dict) or set(obligations) != set(KINDS):
        raise ValueError('all five numerical obligations require explicit decisions')
    for kind, obligation in obligations.items():
        if not isinstance(obligation, dict) or set(obligation) - {'status', 'reason', 'source_ids', 'check_ids'} or not {'status', 'reason', 'source_ids'} <= set(obligation) or type(obligation['reason']) is not str or not obligation['reason'].strip() or not isinstance(obligation['source_ids'], list) or not obligation['source_ids'] or any(type(s) is not str or not s for s in obligation['source_ids']) or len(set(obligation['source_ids'])) != len(obligation['source_ids']):
            raise ValueError('complete numerical obligation decision/source/reason required')
        if obligation.get('status') == 'deferred':
            raise ValueError('unsupported_required_check:'+kind)
        if obligation.get('status') not in ('required', 'not_applicable'):
            raise ValueError('explicit required/not_applicable obligation decision required')
        matching = [c for c in checks if c['kind'] == kind]
        declared_ids = obligation.get('check_ids', [c['id'] for c in matching])
        if not isinstance(declared_ids, list) or any(type(i) is not str or not i for i in declared_ids) or len(set(declared_ids)) != len(declared_ids) or set(declared_ids) != {c['id'] for c in matching}:
            raise ValueError('obligation check IDs do not match complete executed checks')
        if obligation['status'] == 'required' and not matching:
            raise ValueError('unsupported_required_check:'+kind)
        if obligation['status'] == 'not_applicable' and matching:
            raise ValueError('not_applicable obligation contradicts requested numerical checks')
        if any(not set(c['source_ids']) <= set(obligation.get('source_ids', [])) for c in matching):
            raise ValueError('obligation sources do not cover its executable checks')
    continuous = policy.get('continuous_scope')
    if continuous is not None:
        if not isinstance(continuous, dict) or set(continuous) - {'target', 'source_ids', 'reason', 'envelope'} or not {'target', 'source_ids', 'reason'} <= set(continuous) or continuous['target'] not in ('recorded_reconstruction', 'underlying_continuous'):
            raise ValueError('complete explicit continuous scope required')
        if type(continuous['reason']) is not str or not continuous['reason'].strip() or not isinstance(continuous['source_ids'], list):
            raise ValueError('continuous scope needs source IDs and a reason')
        if continuous['target'] == 'underlying_continuous' and scope != 'pwl_trajectory':
            raise ValueError('underlying full-window envelope requires complete PWL trajectory refinement; endpoints cannot upgrade scope')
        if continuous.get('envelope') is not None:
            validate_envelope(continuous, outputs, checks, [first['start_time'], first['stop_time']])
    return {'scope': scope, 'work_budget': work}


def validate_trial_numeric_policy(policy, base_spec, context=None):
    report = {'valid': False, 'errors': [], 'missing_gates': [], 'scope': None}
    try:
        if not isinstance(policy.get('solver_levels'), list) or len(policy['solver_levels']) != 3:
            raise ValueError('three exact source-declared trial solver levels required')
        specs = [{**base_spec, 'solver': solver} for solver in policy['solver_levels']]
        validated = validate_numeric_policy(policy, specs, context)
        report.update(valid=True, scope=validated['scope'])
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        report['errors'].append(str(error))
    return report


def numeric_context_from_documents(model, selection, parameters=None):
    """Select already independently validated C/D documents without I/O."""
    bodies = [m['body'] for design in model['designs'] if design['id'] == selection['design_id']
              for m in design['models'] if m['id'] == selection['model_id']]
    if len(bodies) != 1:
        raise ValueError('numeric context requires one exact current approved C selection')
    bindings = [p for p in (parameters or {}).get('parameters', []) if all(p.get('reference', {}).get(k) == selection[k] for k in ('design_id', 'model_id'))]
    return {'project_id': model['project_id'], 'variables': bodies[0]['variables'],
            'relations': bodies[0]['relations'], 'parameter_bindings': bindings}


def _selected_record(level, output):
    kind = output.get('kind', 'output')
    records = level.get('states', []) if kind == 'state' else level.get('outputs', [])
    matches = [r for r in records if all(typed_equal(r.get(k), output[k]) for k in
        (('variable_id', 'unit', 'block_path') if kind == 'state' else ('port', 'variable_id', 'unit')))]
    if len(matches) != 1:
        raise ValueError('actual numerical output/state identity missing or ambiguous')
    return matches[0]


def validate_envelope(continuous, outputs, checks, window):
    envelope = continuous['envelope']
    if not isinstance(envelope, dict) or set(envelope) != {'kind', 'window', 'proof_source_ids', 'output_bounds', 'check_bounds'} or envelope['kind'] != 'reviewed_uniform_bound':
        raise ValueError('complete source-selected uniform envelope required')
    if not typed_equal(envelope['window'], window):
        raise ValueError('continuous envelope window differs from the complete physical interval')
    if not isinstance(envelope['proof_source_ids'], list) or not envelope['proof_source_ids'] or not set(envelope['proof_source_ids']) <= set(continuous['source_ids']):
        raise ValueError('continuous envelope proof sources missing from scope review')
    if not isinstance(envelope['output_bounds'], list) or not isinstance(envelope['check_bounds'], list):
        raise ValueError('complete envelope output/check bounds required')
    output_bounds = {}
    for bound in envelope['output_bounds']:
        if not isinstance(bound, dict) or set(bound) != {'variable_id', 'unit', 'levels'} or bound['variable_id'] in output_bounds:
            raise ValueError('unique exact output envelope definitions required')
        output_bounds[bound['variable_id']] = bound
    check_bounds = {}
    for bound in envelope['check_bounds']:
        if not isinstance(bound, dict) or set(bound) - {'id', 'unit', 'levels', 'rate_levels', 'rate_unit'} or not {'id', 'unit', 'levels'} <= set(bound) or bound['id'] in check_bounds:
            raise ValueError('unique exact check envelope definitions required')
        check_bounds[bound['id']] = bound
    if set(output_bounds) != {o['variable_id'] for o in outputs} or set(check_bounds) != {c['id'] for c in checks}:
        raise ValueError('continuous envelope must cover all outputs and required checks')
    for output in outputs:
        if output_bounds[output['variable_id']]['unit'] != output['unit']:
            raise ValueError('continuous output bound unit differs')
    for check in checks:
        bound = check_bounds[check['id']]
        expected_unit = 's' if check['kind'] == 'event_localization' else check['unit']
        if bound['unit'] != expected_unit:
            raise ValueError('continuous check bound unit differs; event bounds must be time bounds')
        if check['kind'] == 'numerical_drift' and (bound.get('rate_unit') != check['rate_unit'] or 'rate_levels' not in bound):
            raise ValueError('continuous drift requires a separate reviewed rate bound')
    for bound in [*output_bounds.values(), *check_bounds.values()]:
        for levels in [bound['levels'], *([bound['rate_levels']] if 'rate_levels' in bound else [])]:
            if not isinstance(levels, list) or len(levels) != 3 or any(not finite(v) or v < 0 for v in levels):
                raise ValueError('three finite nonnegative prior envelope bounds required')
    return output_bounds, check_bounds


def evaluate_trial_numeric(levels, numeric_policy, context=None, *, project_id=None, physical_sha256=None):
    """Assess three independently validated native levels without I/O or state."""
    context = context or {}
    result = {'schema_version': 1, 'project_id': project_id if project_id is not None else context.get('project_id'),
        'method': numeric_policy.get('method'), 'scope': None, 'outputs': [], 'checks': [],
        'complete': False, 'criteria_satisfied': False, 'numerically_verified': False,
        'disposition': 'incomplete', 'claim_limit': numeric_policy.get('claim_limit', ''), 'errors': []}
    if physical_sha256 is not None:
        result['physical_sha256'] = physical_sha256
    try:
        if not isinstance(levels, list) or len(levels) != 3:
            raise ValueError('three independent complete native numeric levels required')
        specs = [level['run_spec'] for level in levels]
        validated = validate_numeric_policy(numeric_policy, specs, context)
        work, scope = validated['work_budget'], validated['scope']
        result['scope'] = scope
        declared_states = [{k: o[k] for k in ('variable_id', 'unit', 'block_path')} for o in numeric_policy['outputs'] if o.get('kind') == 'state']
        for level in levels:
            actual_states = [{k: o[k] for k in ('variable_id', 'unit', 'block_path')} for o in level.get('states', [])]
            if not typed_equal(actual_states, declared_states):
                raise ValueError('trial numerical policy must cover every actual state in exact order')
        window = [specs[0]['start_time'], specs[0]['stop_time']]
        for output in numeric_policy['outputs']:
            records = [_selected_record(level, output) for level in levels]
            series = [Series(record['time'], record['values'],
                max_samples=numeric_policy.get('budget', {}).get('max_samples_per_output', 12001),
                max_gap=(numeric_policy.get('trajectory') or {}).get('max_gap'), window=window) for record in records]
            if numeric_policy['method'] == 'ode4_step_refinement':
                from validate_numerical_verification import uniform_grid
                for item, spec in zip(series, specs):
                    limit = numeric_policy.get('budget', {}).get('max_samples_per_output', 3001)-1 if 'scope' in numeric_policy or 'trajectory' in numeric_policy else 3000
                    grid = uniform_grid(spec['start_time'], spec['stop_time'], spec['solver']['fixed_step'], max_steps=limit)
                    if len(item.time) != len(grid) or any(abs(t-g) > rounding_time(g) for t, g in zip(item.time, grid)):
                        raise ValueError('actual fixed-step native output does not cover its complete integer grid')
            if scope == 'pwl_trajectory':
                times = union_knots(series, window, work)
                samples = [[item.at(t) for t in times] for item in series]
            else:
                times = numeric_policy['comparison_times']
                samples = []
                for item in series:
                    selected = []
                    for time in times:
                        matches = [i for i, t in enumerate(item.time) if abs(t-time) <= rounding_time(time)]
                        if len(matches) != 1:
                            raise ValueError('comparison time has missing or ambiguous actual samples')
                        selected.append(item.values[matches[0]])
                    samples.append(selected)
            work.charge(len(times)*3)
            computed = refinement_summary(output, samples)
            if numeric_policy['method'] != 'ode4_step_refinement':
                computed['empirical_order'] = None
            computed['comparison_times'] = times
            computed['scope'] = scope
            result['outputs'].append(computed)
        for check in numeric_policy.get('checks', []):
            evaluations = [evaluate_check(check, level, numeric_policy, context, work) for level in levels]
            complete = all(e['complete'] for e in evaluations)
            passed = complete and all(e['criteria_satisfied'] for e in evaluations)
            summary = {'id': check['id'], 'kind': check['kind'], 'levels': evaluations,
                       'complete': complete, 'criteria_satisfied': passed}
            if complete and check['kind'] == 'event_localization':
                counts = [e['observed_count'] for e in evaluations]
                if len(set(counts)) != 1:
                    summary.update(criteria_satisfied=False, event_count_satisfied=False)
                else:
                    event_sets = [e['events'][:1] if check['matching'] == 'first' else e['events'] for e in evaluations]
                    d01 = max((abs(a['time']-b['time']) for a, b in zip(event_sets[0], event_sets[1])), default=0.0)
                    d12 = max((abs(a['time']-b['time']) for a, b in zip(event_sets[1], event_sets[2])), default=0.0)
                    matched = all(a['direction'] == b['direction'] for first, second in zip(event_sets, event_sets[1:]) for a, b in zip(first, second))
                    summary.update(D01=number(d01), D12=number(d12), event_count_satisfied=True,
                        event_matching_satisfied=matched, criteria_satisfied=passed and matched and d01 <= check['time_tolerance'] and d12 <= check['time_tolerance'])
            if complete and check.get('convergence_required'):
                values = [e['maximum_violation'] for e in evaluations] if check['kind'] != 'event_localization' else [summary.get('D01', math.inf), summary.get('D12', math.inf)]
                floor = check['roundoff_floor']
                shrinking = all(b <= floor if a <= floor else b <= check['contraction_limit']*a for a, b in zip(values, values[1:]))
                summary.update(contraction_satisfied=shrinking, criteria_satisfied=summary['criteria_satisfied'] and shrinking)
            result['checks'].append(summary)
        continuous = numeric_policy.get('continuous_scope')
        if continuous and continuous['target'] == 'underlying_continuous':
            if continuous.get('envelope') is None:
                result['errors'].append('underlying continuous-solution claim requires an independently reviewed uniform envelope')
            else:
                output_bounds, check_bounds = validate_envelope(continuous, numeric_policy['outputs'], numeric_policy.get('checks', []), window)
                result['continuous_scope'] = 'conditional_on_reviewed_uniform_envelope'
                result['envelope_sources'] = continuous['envelope']['proof_source_ids']
                for output in result['outputs']:
                    bounds = output_bounds[output['variable_id']]['levels']
                    satisfied = max(bounds) <= output['tolerance'] and output['D01']+bounds[0]+bounds[1] <= output['tolerance'] and output['D12']+bounds[1]+bounds[2] <= output['tolerance']
                    output.update(continuous_envelope_satisfied=satisfied, criteria_satisfied=output['criteria_satisfied'] and satisfied)
                for summary in result['checks']:
                    bound = check_bounds[summary['id']]
                    satisfied = summary['complete']
                    if summary['kind'] == 'event_localization':
                        definition = next(c for c in numeric_policy['checks'] if c['id'] == summary['id'])
                        levels_bound = bound['levels']
                        satisfied = satisfied and summary.get('D01', math.inf)+levels_bound[0]+levels_bound[1] <= definition['time_tolerance'] and summary.get('D12', math.inf)+levels_bound[1]+levels_bound[2] <= definition['time_tolerance']
                    else:
                        satisfied = satisfied and all(e['maximum_violation']+b <= e['tolerance'] for e, b in zip(summary['levels'], bound['levels']))
                        if summary['kind'] == 'numerical_drift':
                            definition = next(c for c in numeric_policy['checks'] if c['id'] == summary['id'])
                            satisfied = satisfied and all(abs(e['slope'])+b <= definition['drift_tolerance'] for e, b in zip(summary['levels'], bound['rate_levels']))
                    summary.update(continuous_envelope_satisfied=satisfied, criteria_satisfied=summary['criteria_satisfied'] and satisfied)
        result['complete'] = not result['errors'] and all(c['complete'] for c in result['checks'])
        result['criteria_satisfied'] = result['complete'] and all(o['criteria_satisfied'] for o in result['outputs']) and all(c['criteria_satisfied'] for c in result['checks'])
        result['numerically_verified'] = result['criteria_satisfied']
        result['disposition'] = 'support' if result['criteria_satisfied'] else 'reject' if result['complete'] else 'incomplete'
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError, ZeroDivisionError) as error:
        result['errors'].append(str(error))
    return result
