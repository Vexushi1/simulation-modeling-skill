"""Analytic full-H1 numerical oracles and source-bound synthetic history.

These are infrastructure tests, not MATLAB qualification or model approval.
"""
from __future__ import annotations

import copy
import math
import shutil
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from numerical_math_common import (Series, WorkBudget, dimensions, evaluate_expression,
    evaluate_metric, observable_scale, unit_dimensions, unit_scale,
    validate_expression, validate_metric_policy)
from numerical_obligations import (evaluate_trial_numeric, numeric_context_from_documents,
    _time_weighted_slope, validate_check, validate_observables, validate_trial_numeric_policy)
from verification_common import HARD_BUDGET, serialized_json


def var(name):
    return {'op': 'variable', 'id': name}


def const(value, unit='m/s', dims=None):
    return {'op': 'constant', 'value': value, 'unit': unit,
            'dimensions': {'length': 1, 'time': -1} if dims is None else dims}


def full_case(method='ode45_tolerance_refinement'):
    fixed = method == 'ode4_step_refinement'
    axes = [[i/2 for i in range(3)], [i/4 for i in range(5)], [i/8 for i in range(9)]] if fixed else [[0., .4, 1.], [0., .25, .8, 1.], [0., .2, .5, .9, 1.]]
    name = 'ode4' if fixed else 'ode15s' if method.startswith('ode15s') else 'ode45'
    solvers = [{'name': name, 'type': 'fixed-step' if fixed else 'variable-step',
        'fixed_step': .5/(2**i) if fixed else None, 'max_step': None if fixed else 1.,
        'min_step': None if fixed else 1e-12, 'initial_step': None if fixed else .01,
        'rel_tol': None if fixed else 1e-4/(10**i), 'abs_tol': None if fixed else 1e-6/(10**i),
        'zero_crossing': 'DisableAll'} for i in range(3)]
    levels = [{'run_spec': {'start_time': 0., 'stop_time': 1., 'solver': solver,
        'parameters': [], 'inputs': [], 'outputs': [{'port': 1, 'variable_id': 'x', 'unit': 'm'}]},
        'outputs': [{'port': 1, 'variable_id': 'x', 'unit': 'm', 'time': axis, 'values': list(axis)}],
        'states': []} for solver, axis in zip(solvers, axes)]
    context = {'project_id': 'synthetic-full-math', 'variables': [
        {'id': 'x', 'unit': 'm', 'roles': ['state', 'output']}],
        'relations': [{'id': 'law', 'variable_ids': ['x']}], 'parameter_bindings': []}
    policy = {'method': method, 'scope': 'pwl_trajectory', 'solver_levels': solvers,
        'trajectory': {'mode': 'pwl_union', 'max_gap': 1.}, 'comparison_times': None,
        'outputs': [{'port': 1, 'variable_id': 'x', 'unit': 'm', 'absolute_tolerance': .01,
            'relative_tolerance': 0., 'contraction_limit': .9, 'roundoff_floor': 1e-12}],
        'obligations': {kind: {'status': 'not_applicable', 'reason': 'Analytic infrastructure case', 'source_ids': ['settings']} for kind in
            ('residual', 'constraint', 'conservation', 'event_localization', 'numerical_drift')},
        'observables': [{'id': 'x', 'kind': 'output', 'port': 1, 'variable_id': 'x', 'unit': 'm', 'dimensions': {'length': 1}},
            {'id': 't', 'kind': 'time', 'unit': 's', 'dimensions': {'time': 1}}],
        'checks': [], 'budget': dict(HARD_BUDGET),
        'math_budget': {'max_ast_nodes': 512, 'max_ast_depth': 24, 'max_evaluations': 200000,
                        'max_checks': 32, 'max_union_knots': 36003},
        'claim_limit': 'SYNTHETIC INFRASTRUCTURE TEST; recorded reconstruction only'}
    return levels, policy, context


def check_definition(kind):
    value = {'id': kind, 'kind': kind, 'window': [0., 1.], 'source_ids': ['settings'],
             'relation_ids': ['law'], 'unit': 'm', 'dimensions': {'length': 1}}
    if kind != 'event_localization':
        value.update(absolute_tolerance=1e-9, relative_tolerance=0., scale=1.)
    if kind == 'residual': value.update(mode='integral', state=var('x'), rhs=const(1.))
    elif kind == 'constraint': value.update(expression=var('x'), relation='ge', threshold=0.)
    elif kind == 'conservation': value.update(inventory=var('x'), flux=const(1.))
    elif kind == 'numerical_drift':
        value.update(expression=var('x'), reference={'op': 'mul', 'args': [var('t'), const(1.)]},
                     drift_tolerance=1e-9, rate_unit='m/s')
    else:
        value.update(expression=var('x'), threshold=.5, direction='rising', expected_count=1,
                     matching='all', time_tolerance=1e-6, value_tolerance=0., max_bracket_width=1.)
    return value


def require(policy, *checks):
    policy['checks'] = list(checks)
    for check in checks:
        policy['obligations'][check['kind']].update(status='required', check_ids=[check['id']])
    return policy


@pytest.mark.parametrize('method', ['ode4_step_refinement', 'ode45_tolerance_refinement', 'ode15s_tolerance_refinement'])
def test_three_methods_compare_complete_non_nested_trajectories(method):
    levels, policy, context = full_case(method)
    result = evaluate_trial_numeric(levels, policy, context)
    assert result['complete'] and result['numerically_verified'], result
    assert result['scope'] == 'pwl_trajectory'
    assert result['outputs'][0]['D01'] == pytest.approx(0., abs=1e-14)
    assert result['outputs'][0]['D12'] == pytest.approx(0., abs=1e-14)
    assert result['outputs'][0]['sample_count'] == len(set(t for level in levels for t in level['outputs'][0]['time']))
    assert result['outputs'][0]['empirical_order'] is None


def test_full_trajectory_finds_interior_error_hidden_by_endpoint_agreement():
    levels, policy, context = full_case()
    levels[0]['outputs'][0]['values'][1] += .2
    full = evaluate_trial_numeric(levels, policy, context)
    assert full['complete'] and not full['numerically_verified']
    assert not full['outputs'][0]['primary_difference_satisfied']
    policy.update(scope='actual_points', trajectory={'mode': 'actual_points', 'max_gap': 1.}, comparison_times=[0., 1.])
    endpoint = evaluate_trial_numeric(levels, policy, context)
    assert endpoint['numerically_verified'] and endpoint['scope'] == 'actual_points'


def test_fixed_pwl_mode_still_rejects_missing_actual_grid_point():
    levels, policy, context = full_case('ode4_step_refinement')
    del levels[1]['outputs'][0]['time'][1]
    del levels[1]['outputs'][0]['values'][1]
    result = evaluate_trial_numeric(levels, policy, context)
    assert not result['complete'] and any('complete integer grid' in e for e in result['errors'])


def test_all_five_required_checks_execute_on_all_levels():
    levels, policy, context = full_case()
    require(policy, *(check_definition(k) for k in policy['obligations']))
    result = evaluate_trial_numeric(levels, policy, context)
    assert result['numerically_verified'], result
    assert len(result['checks']) == 5
    assert all(len(c['levels']) == 3 and c['criteria_satisfied'] for c in result['checks'])
    event = next(c for c in result['checks'] if c['kind'] == 'event_localization')
    assert all(c['events'][0]['time'] == pytest.approx(.5) for c in event['levels'])


@pytest.mark.parametrize('kind', ['residual', 'constraint', 'conservation', 'event_localization', 'numerical_drift'])
def test_real_criterion_violation_preserves_complete_rejection(kind):
    levels, policy, context = full_case()
    check = check_definition(kind)
    if kind == 'residual': check['rhs'] = const(0.)
    elif kind == 'conservation': check['flux'] = const(0.)
    elif kind == 'constraint': check.update(relation='le', threshold=.5)
    elif kind == 'event_localization': check['expected_count'] = 2
    else: del check['reference']
    require(policy, check)
    result = evaluate_trial_numeric(levels, policy, context)
    assert result['complete'] and not result['criteria_satisfied'] and result['disposition'] == 'reject', result


def test_mathematically_undefined_check_is_incomplete_not_zero():
    levels, policy, context = full_case()
    check = check_definition('residual')
    check.pop('state'); check.pop('rhs'); check.pop('mode')
    check['expression'] = {'op': 'div', 'args': [var('x'), const(0., '1', {})]}
    require(policy, check)
    result = evaluate_trial_numeric(levels, policy, context)
    assert not result['complete'] and result['disposition'] == 'incomplete'
    assert all('division by zero' in c['errors'][0] for c in result['checks'][0]['levels'])


@pytest.mark.parametrize('shape', ['platform', 'grazing', 'wide_bracket', 'boundary'])
def test_unresolved_events_cannot_be_numerically_verified(shape):
    levels, policy, context = full_case()
    check = check_definition('event_localization')
    if shape in ('platform', 'grazing'):
        for level in levels:
            level['outputs'][0].update(time=[0., .4, .6, 1.], values=[0., .5, .5, 1.] if shape == 'platform' else [1., .5, 1., 1.])
    elif shape == 'wide_bracket': check['max_bracket_width'] = .1
    else: check['threshold'] = 0.
    require(policy, check)
    result = evaluate_trial_numeric(levels, policy, context)
    assert not result['complete'] and not result['numerically_verified'], result


def test_recorded_contact_is_explicit_and_not_a_continuous_tangency_proof():
    levels, policy, context = full_case()
    for level in levels:
        level['outputs'][0].update(time=[0., .5, 1.], values=[1., 0., 1.])
    check = check_definition('event_localization')
    check.update(threshold=0., direction='either', event_type='contact')
    require(policy, check)
    result = evaluate_trial_numeric(levels, policy, context)
    assert result['numerically_verified'], result
    assert result['checks'][0]['levels'][0]['scope'] == 'recorded_pwl_reconstruction'


def test_event_signs_do_not_underflow_at_a_native_zero():
    levels, policy, context = full_case()
    for level in levels:
        level['outputs'][0].update(time=[0., .5, 1.], values=[-1e-200, 0., 1e-200])
    check = check_definition('event_localization'); check['threshold'] = 0.
    require(policy, check)
    result = evaluate_trial_numeric(levels, policy, context)
    assert result['numerically_verified'], result


def test_absolute_integral_splits_a_subnormal_product_zero_crossing():
    assert Series([0., 1.], [-1e-200, 1e-200]).integral([0., 1.], 'absolute_integral') == pytest.approx(5e-201, rel=1e-14, abs=0.)


def test_nonuniform_central_stencil_matches_quadratic_derivative():
    series = Series([0., .3, 1.], [0., .09, 1.])
    assert series.derivative(.3, 'central') == pytest.approx(.6)
    assert series.derivative(0., 'central') == pytest.approx(.3)


@pytest.mark.parametrize('scheme,time', [('forward', 1.), ('backward', 0.)])
def test_explicit_one_sided_stencil_does_not_silently_change_direction(scheme, time):
    with pytest.raises(ValueError, match='stencil is missing'):
        Series([0., 1.], [0., 1.]).derivative(time, scheme)


@pytest.mark.parametrize('fault', ['required_missing', 'obligation_ids', 'not_applicable_check', 'unknown_anchor', 'wrong_dimensions', 'bool_count', 'irrelevant_field'])
def test_policy_faults_block_before_any_numerical_acceptance(fault):
    levels, policy, context = full_case()
    check = check_definition('event_localization' if fault == 'bool_count' else 'constraint')
    require(policy, check)
    if fault == 'required_missing': policy['checks'] = []
    elif fault == 'obligation_ids': policy['obligations'][check['kind']]['check_ids'] = ['other']
    elif fault == 'not_applicable_check': policy['obligations'][check['kind']]['status'] = 'not_applicable'
    elif fault == 'unknown_anchor': check['relation_ids'] = ['invented']
    elif fault == 'wrong_dimensions': check['dimensions'] = {'mass': 1}
    elif fault == 'bool_count': check['expected_count'] = True
    else: check['flux'] = const(1.)
    result = evaluate_trial_numeric(levels, policy, context)
    assert not result['complete'] and result['errors'], result


@pytest.mark.parametrize('op', ['eval', 'callback', 'system'])
def test_arbitrary_expression_execution_is_rejected(op):
    with pytest.raises(ValueError, match='unsupported'):
        validate_expression({'op': op, 'args': []}, {}, WorkBudget())


def test_expression_cycle_is_bounded_and_rejected():
    node = {'op': 'neg', 'args': []}; node['args'].append(node)
    with pytest.raises(ValueError, match='cyclic'):
        validate_expression(node, {}, WorkBudget())


def test_unit_prefixes_convert_before_comparing_equations():
    levels, policy, context = full_case()
    context['variables'][0]['unit'] = 'cm'
    policy['outputs'][0]['unit'] = 'cm'; policy['observables'][0]['unit'] = 'cm'
    for level in levels:
        level['run_spec']['outputs'][0]['unit'] = 'cm'
        level['outputs'][0]['unit'] = 'cm'
        level['outputs'][0]['values'] = [100*t for t in level['outputs'][0]['time']]
    check = check_definition('residual')
    require(policy, check)
    result = evaluate_trial_numeric(levels, policy, context)
    assert result['numerically_verified'], result
    assert result['checks'][0]['levels'][0]['maximum_violation'] < 1e-12


@pytest.mark.parametrize('unit', [
    '*'.join(['mm^32/m^32']*4),
    '*'.join(['mm^32/m^32']*4+['km^32/m^32']),
    '*'.join(['km^32/m^32']*4),
    '*'.join(['km^32/m^32']*4+['mm^32/m^32']),
], ids=['scale_underflow', 'intermediate_underflow_then_cancel',
        'scale_overflow', 'intermediate_overflow_then_cancel'])
def test_unit_conversion_scale_loss_is_controlled_before_cancellation(unit):
    assert unit_dimensions(unit) == dimensions({})
    with pytest.raises(ValueError, match='unresolved canonical unit conversion'):
        unit_scale(unit)


@pytest.mark.parametrize('value,unit', [
    (1e-308, 'mm^32/m^32'), (-1e-308, 'mm^32/m^32'),
    (1e308, 'km^32/m^32'),
], ids=['positive_nonzero_underflow', 'negative_nonzero_underflow',
        'nonzero_overflow'])
def test_nonzero_constant_conversion_must_not_underflow_or_overflow(value, unit):
    expression = const(value, unit, {})
    assert unit_scale(unit) > 0
    with pytest.raises(ValueError, match='conversion'):
        validate_expression(expression, {}, WorkBudget())
    with pytest.raises(ValueError, match='conversion'):
        evaluate_expression(expression, {}, 0., WorkBudget())


@pytest.mark.parametrize('method', [
    'ode4_step_refinement', 'ode45_tolerance_refinement',
    'ode15s_tolerance_refinement',
])
def test_unit_conversion_decimal_counterexample_blocks_complete_three_level_policy(method):
    # This oracle deliberately uses exact decimal factors and no production
    # conversion helper: 1e308 * (1e-3)^(32*4) = 1e-76, above the fixed prior.
    with localcontext() as decimal_context:
        decimal_context.prec = 80
        canonical = Decimal('1e308')*(Decimal('0.001')**32)**4
        assert canonical == Decimal('1e-76')
        assert canonical > Decimal('1e-80')
    levels, policy, context = full_case(method)
    check = check_definition('residual')
    for key in ('state', 'rhs', 'mode'):
        check.pop(key)
    check.update(unit='1', dimensions={}, absolute_tolerance=1e-80,
        expression=const(1e308, '*'.join(['mm^32/m^32']*4), {}))
    require(policy, check)
    source = validate_trial_numeric_policy(policy, levels[0]['run_spec'], context)
    assert not source['valid'] and any('unit conversion' in e for e in source['errors']), source
    result = evaluate_trial_numeric(levels, policy, context)
    assert not result['complete'] and not result['criteria_satisfied'] and not result['numerically_verified'], result
    assert result['disposition'] == 'incomplete'
    assert any('unit conversion' in e for e in result['errors']), result
    assert check['absolute_tolerance'] == 1e-80


@pytest.mark.parametrize('unit', [
    '*'.join(['mm^32/m^32']*4), '*'.join(['km^32/m^32']*4),
], ids=['check_unit_underflow', 'check_unit_overflow'])
def test_source_check_unit_conversion_is_validated_before_trial_arrays(unit):
    levels, policy, context = full_case()
    check = check_definition('residual')
    for key in ('state', 'rhs', 'mode'):
        check.pop(key)
    check.update(unit=unit, dimensions={}, expression=const(0., '1', {}))
    require(policy, check)
    source = validate_trial_numeric_policy(policy, levels[0]['run_spec'], context)
    assert not source['valid'] and any('unit conversion' in e for e in source['errors']), source
    result = evaluate_trial_numeric(levels, policy, context)
    assert not result['complete'] and not result['numerically_verified'], result


@pytest.mark.parametrize('value', [0., -0.], ids=['true_zero', 'negative_true_zero'])
def test_resolved_unit_conversion_preserves_true_zero(value):
    levels, policy, context = full_case()
    check = check_definition('residual')
    for key in ('state', 'rhs', 'mode'):
        check.pop(key)
    check.update(unit='1', dimensions={}, expression=const(value, 'mm^32/m^32', {}))
    require(policy, check)
    source = validate_trial_numeric_policy(policy, levels[0]['run_spec'], context)
    assert source['valid'], source
    result = evaluate_trial_numeric(levels, policy, context)
    assert result['complete'] and result['numerically_verified'], result
    assert all(level['maximum_violation'] == 0. for level in result['checks'][0]['levels'])


@pytest.mark.parametrize('value,unit,dims,expected', [
    (100., 'cm', {'length': 1}, 1.),
    (1000., 'ms', {'time': 1}, 1.),
    (1e308, '*'.join(['mm^32/m^32']*3), {}, 1e20),
], ids=['centimetres', 'milliseconds', 'finite_small_scale_large_constant'])
def test_normal_unit_conversion_preserves_nonzero_closed_form(value, unit, dims, expected):
    expression = const(value, unit, dims)
    assert validate_expression(expression, {}, WorkBudget()) == dimensions(dims)
    assert evaluate_expression(expression, {}, 0., WorkBudget()) == pytest.approx(expected, rel=1e-13, abs=0.)


@pytest.mark.parametrize('canonical_unit,scale', [
    ('mm^32/m^32', 1e-308), ('km^32/m^32', 1e308),
], ids=['reviewed_scale_product_underflow', 'reviewed_scale_product_overflow'])
def test_reviewed_observable_conversion_product_must_remain_resolved(canonical_unit, scale):
    with pytest.raises(ValueError, match='unresolved canonical observable unit conversion'):
        observable_scale({'unit': 'reviewed_custom_ratio', 'canonical_unit': canonical_unit, 'scale': scale})


def test_explicit_conversion_cannot_contradict_a_known_unit():
    levels, policy, context = full_case()
    policy['observables'][0].update(canonical_unit='cm', scale=1.)
    result = evaluate_trial_numeric(levels, policy, context)
    assert not result['complete'] and any('physical unit conversion' in e for e in result['errors'])


def test_custom_affine_observation_mapping_is_explicit():
    levels, policy, context = full_case()
    context['variables'][0]['unit'] = 'custom_temperature'
    policy['outputs'][0]['unit'] = 'custom_temperature'
    policy['observables'][0].update(unit='custom_temperature', dimensions={'temperature': 1}, canonical_unit='K', scale=1., offset=273.15)
    for level in levels:
        level['run_spec']['outputs'][0]['unit'] = 'custom_temperature'
        level['outputs'][0].update(unit='custom_temperature', values=[0.]*len(level['outputs'][0]['time']))
    check = check_definition('constraint')
    check.update(unit='K', dimensions={'temperature': 1}, relation='eq', threshold=273.15)
    require(policy, check)
    assert evaluate_trial_numeric(levels, policy, context)['numerically_verified']


def test_parameter_observation_requires_actual_approved_code_binding():
    levels, policy, context = full_case()
    context['variables'].append({'id': 'gain', 'unit': 'm/s', 'roles': ['parameter']})
    context['relations'][0]['variable_ids'].append('gain')
    context['parameter_bindings'] = [{'reference': {'variable_id': 'gain'}, 'code_name': 'syn_gain', 'unit': 'm/s'}]
    policy['observables'].append({'id': 'gain', 'kind': 'parameter', 'variable_id': 'gain', 'code_name': 'syn_gain', 'unit': 'm/s', 'dimensions': {'length': 1, 'time': -1}})
    for level in levels: level['run_spec']['parameters'] = [{'code_name': 'syn_gain', 'value': 1., 'unit': 'm/s'}]
    check = check_definition('residual'); check['rhs'] = var('gain'); require(policy, check)
    assert evaluate_trial_numeric(levels, policy, context)['numerically_verified']
    policy['observables'][-1]['code_name'] = 'guessed_name'
    assert not evaluate_trial_numeric(levels, policy, context)['complete']


@pytest.mark.parametrize('covered', [True, False])
def test_trial_state_refinement_uses_real_identity_and_complete_coverage(covered):
    levels, policy, context = full_case()
    for level in levels:
        root = level['outputs'][0]
        level['states'] = [{'variable_id': 'x', 'block_path': 'model/State', 'unit': 'm', 'time': root['time'], 'values': root['values']}]
    if covered:
        state = {**policy['outputs'][0], 'kind': 'state', 'block_path': 'model/State'}; state.pop('port')
        policy['outputs'].append(state)
    result = evaluate_trial_numeric(levels, policy, context)
    assert result['numerically_verified'] is covered
    if covered: assert result['outputs'][1]['kind'] == 'state' and 'port' not in result['outputs'][1]


@pytest.mark.parametrize('budget', ['max_union_knots', 'max_evaluations', 'max_ast_nodes'])
def test_complete_math_budget_exhaustion_never_truncates_to_accept(budget):
    levels, policy, context = full_case()
    if budget == 'max_ast_nodes': require(policy, check_definition('residual'))
    policy['math_budget'][budget] = 1
    result = evaluate_trial_numeric(levels, policy, context)
    assert not result['complete'] and not result['numerically_verified']


def test_pure_evaluator_keeps_all_caller_inputs_immutable():
    levels, policy, context = full_case(); require(policy, check_definition('conservation'))
    before = copy.deepcopy((levels, policy, context))
    evaluate_trial_numeric(levels, policy, context)
    assert (levels, policy, context) == before


def envelope(policy, *, error=1e-6):
    policy['continuous_scope'] = {'target': 'underlying_continuous', 'source_ids': ['proof'], 'reason': 'Synthetic reviewed analytic envelope assumption',
        'envelope': {'kind': 'reviewed_uniform_bound', 'window': [0., 1.], 'proof_source_ids': ['proof'],
            'output_bounds': [{'variable_id': 'x', 'unit': 'm', 'levels': [error]*3}],
            'check_bounds': [{'id': c['id'], 'unit': 's' if c['kind'] == 'event_localization' else c['unit'], 'levels': [error]*3,
                **({'rate_unit': c['rate_unit'], 'rate_levels': [error]*3} if c['kind'] == 'numerical_drift' else {})} for c in policy['checks']]}}


@pytest.mark.parametrize('error,passed', [(1e-6, True), (.1, False)])
def test_continuous_envelope_is_conditional_and_checks_primary_bound(error, passed):
    levels, policy, context = full_case(); envelope(policy, error=error)
    result = evaluate_trial_numeric(levels, policy, context)
    assert result['complete'] and result['numerically_verified'] is passed, result
    assert result['continuous_scope'] == 'conditional_on_reviewed_uniform_envelope'


@pytest.mark.parametrize('fault', ['missing', 'window', 'unit', 'event_amplitude_unit', 'drift_missing_rate'])
def test_continuous_claim_needs_complete_applicable_and_typed_bounds(fault):
    levels, policy, context = full_case()
    if fault == 'event_amplitude_unit': require(policy, check_definition('event_localization'))
    if fault == 'drift_missing_rate': require(policy, check_definition('numerical_drift'))
    envelope(policy)
    bound = policy['continuous_scope']['envelope']
    if fault == 'missing': policy['continuous_scope'].pop('envelope')
    elif fault == 'window': bound['window'] = [.1, 1.]
    elif fault == 'unit': bound['output_bounds'][0]['unit'] = 's'
    elif fault == 'event_amplitude_unit': bound['check_bounds'][0]['unit'] = 'm'
    else: bound['check_bounds'][0].pop('rate_levels')
    result = evaluate_trial_numeric(levels, policy, context)
    assert not result['complete'] and result['errors'], result


@pytest.mark.parametrize('statistic,unit,value', [('final', 'm', 1.), ('peak', 'm', 1.), ('peak_time', 's', 1.),
    ('integral', 'm*s', .5), ('absolute_integral', 'm*s', .5), ('squared_integral', '(m)^2*s', 1/3)])
def test_shared_metrics_have_analytic_units_and_values(statistic, unit, value):
    levels, policy, context = full_case()
    result = evaluate_metric({'statistic': statistic, 'output_port': 1, 'unit': unit}, levels[0], context=context, numeric_policy=policy)
    assert result['defined'] and result['value'] == pytest.approx(value), result


def test_nonunique_peak_time_remains_undefined():
    levels, policy, context = full_case()
    levels[0]['outputs'][0]['values'] = [1., 1., 1.]
    result = evaluate_metric({'statistic': 'peak_time', 'output_port': 1, 'unit': 's'}, levels[0], context=context, numeric_policy=policy)
    assert not result['defined'] and result['value'] is None


@pytest.mark.parametrize('fault', ['kind', 'unit', 'port_type', 'unknown_key', 'window', 'unbound_check'])
def test_metric_false_acceptance_boundaries(fault):
    levels, policy, context = full_case(); check = check_definition('constraint'); require(policy, check)
    metric = {'statistic': 'constraint', 'check': check, 'unit': 'm'}
    if fault == 'kind': metric['statistic'] = 'conservation'
    elif fault == 'unit': metric['unit'] = 's'
    elif fault == 'port_type': metric = {'statistic': 'final', 'output_port': 1., 'unit': 'm'}
    elif fault == 'unknown_key': metric['arbitrary_code'] = 'evil()'
    elif fault == 'window': metric['window'] = [0., 2.]
    else: metric['check'] = {**check, 'threshold': 5.}
    result = evaluate_metric(metric, levels[0], context=context, numeric_policy=policy)
    assert not result['defined'] and result['errors'], result


def test_new_whole_metric_cannot_upgrade_endpoint_h1_scope():
    levels, policy, context = full_case()
    policy.update(scope='actual_points', trajectory={'mode': 'actual_points', 'max_gap': 1.}, comparison_times=[0., 1.])
    assert not evaluate_metric({'statistic': 'integral', 'output_port': 1, 'unit': 'm*s'}, levels[0], context=context, numeric_policy=policy)['defined']
    assert evaluate_metric({'statistic': 'maximum', 'output_port': 1, 'unit': 'm'}, levels[0], context=context, numeric_policy=policy)['defined']


def test_prior_trial_policy_validation_requires_exact_declared_solvers():
    levels, policy, context = full_case()
    before = copy.deepcopy(policy)
    report = validate_trial_numeric_policy(policy, levels[0]['run_spec'], context)
    assert report['valid'] and policy == before
    policy['solver_levels'][1]['rel_tol'] *= 2
    assert not validate_trial_numeric_policy(policy, levels[0]['run_spec'], context)['valid']


@pytest.mark.parametrize('method', ['ode4_step_refinement', 'ode45_tolerance_refinement', 'ode15s_tolerance_refinement'])
@pytest.mark.parametrize('fault', ['protocol_metadata', 'missing_field', 'wrong_type', 'zero_crossing', 'bool_refinement', 'applicability'])
def test_source_solver_fields_are_strict_before_any_native_trial(method, fault):
    levels, policy, context = full_case(method)
    solver = policy['solver_levels'][1]
    if fault == 'protocol_metadata': solver.update(reason='Not a numeric run field', classification={'dynamics': 'continuous'})
    elif fault == 'missing_field': solver.pop('zero_crossing')
    elif fault == 'wrong_type': solver['type'] = 'variable-step' if method.startswith('ode4_') else 'fixed-step'
    elif fault == 'zero_crossing': solver['zero_crossing'] = 'unknown'
    elif fault == 'bool_refinement': solver['fixed_step' if method.startswith('ode4_') else 'rel_tol'] = True
    else: solver['max_step' if method.startswith('ode4_') else 'fixed_step'] = .1
    report = validate_trial_numeric_policy(policy, levels[0]['run_spec'], context)
    assert not report['valid'] and report['errors']


@pytest.mark.parametrize('fault', ['time_identity', 'output_block', 'state_port', 'unrefined_state', 'missing_parameter', 'duplicate_sources', 'missing_threshold', 'future_integral'])
def test_complete_source_identity_and_check_bindings_fail_closed(fault):
    levels, policy, context = full_case()
    check = check_definition('constraint'); require(policy, check)
    if fault == 'time_identity': policy['observables'][1]['variable_id'] = 'x'
    elif fault == 'output_block': policy['observables'][0]['block_path'] = 'foreign/Output'
    elif fault in ('state_port', 'unrefined_state'):
        symbol = {'id': 'state_x', 'kind': 'state', 'variable_id': 'x', 'block_path': 'model/State', 'unit': 'm', 'dimensions': {'length': 1}}
        if fault == 'state_port': symbol['port'] = 1
        policy['observables'].append(symbol)
    elif fault == 'missing_parameter':
        context['variables'].append({'id': 'gain', 'unit': 'm/s', 'roles': ['parameter']})
        context['parameter_bindings'] = [{'reference': {'variable_id': 'gain'}, 'code_name': 'gain', 'unit': 'm/s'}]
        policy['observables'].append({'id': 'gain', 'kind': 'parameter', 'variable_id': 'gain', 'code_name': 'gain', 'unit': 'm/s', 'dimensions': {'length': 1, 'time': -1}})
    elif fault == 'duplicate_sources': check['source_ids'].append('settings')
    elif fault == 'missing_threshold': check.pop('threshold')
    else:
        check['expression'] = {'op': 'integral', 'id': 'x', 'start': .5}
        check.update(unit='m*s', dimensions={'length': 1, 'time': 1})
    report = validate_trial_numeric_policy(policy, levels[0]['run_spec'], context)
    assert not report['valid'] and report['errors']


@pytest.mark.parametrize('span,value,opposite', [(1e-200, 1e200, False), (1e200, 1e-200, False),
    (1e-200, 1e200, True), (1e200, 1e-200, True)])
def test_squared_pwl_integral_has_finite_closed_form_without_intermediate_scale_loss(span, value, opposite):
    values = [value, -value if opposite else value]
    expected = (1e200 if span == 1e-200 else 1e-200)/(3 if opposite else 1)
    assert Series([0., span], values).integral([0., span], 'squared_integral') == pytest.approx(expected, rel=2e-14, abs=0.)


@pytest.mark.parametrize('span,slope', [(1e-200, 1e200), (1e200, 1e-200)])
def test_time_weighted_drift_normalization_keeps_finite_linear_oracle(span, slope):
    # y=slope*t has exact continuous least-squares slope, independent of span.
    result = _time_weighted_slope([(0., span, 0., slope, 0.)], [0., span])
    assert result == pytest.approx(slope, rel=2e-14, abs=0.)


@pytest.mark.parametrize('statistic', ['integral', 'absolute_integral'])
def test_pwl_integral_preserves_finite_subnormal_observation_under_large_time_scale(statistic):
    tiny = math.ulp(0.)
    result = Series([0., 1e308], [tiny, tiny]).integral([0., 1e308], statistic)
    assert result == pytest.approx(tiny*1e308, rel=2e-14, abs=0.)


def test_current_numeric_context_filters_foreign_model_parameter_bindings():
    selection = {'design_id': 'current_design', 'model_id': 'current_model'}
    body = {'variables': [{'id': 'a', 'roles': ['parameter'], 'unit': '1/s'}], 'relations': []}
    model = {'project_id': 'current', 'designs': [{'id': 'current_design', 'models': [{'id': 'current_model', 'body': body}]}]}
    current = {'reference': {**selection, 'variable_id': 'a'}, 'code_name': 'syn_a', 'unit': '1/s'}
    foreign = {'reference': {'design_id': 'other', 'model_id': 'other', 'variable_id': 'a'}, 'code_name': 'syn_a', 'unit': '1/s'}
    context = numeric_context_from_documents(model, selection, {'parameters': [foreign, current]})
    assert context['parameter_bindings'] == [current]


@pytest.mark.parametrize('mode', ['interior_curvature', 'subnormal_flux'])
def test_integrated_balance_cannot_lose_real_violation_through_intermediate_scale(mode):
    levels, policy, context = full_case()
    span = 1e200 if mode == 'interior_curvature' else 1e308
    values = [0., .5] if mode == 'interior_curvature' else [0., 0.]
    flux = [0., 1e-200] if mode == 'interior_curvature' else [math.ulp(0.), math.ulp(0.)]
    expected = .125 if mode == 'interior_curvature' else math.ulp(0.)*span
    policy['trajectory']['max_gap'] = None
    context['variables'].append({'id': 'flux', 'roles': ['commanded_input'], 'unit': 'm/s'})
    context['relations'][0]['variable_ids'].append('flux')
    policy['observables'].append({'id': 'flux', 'kind': 'input', 'port': 1, 'variable_id': 'flux', 'unit': 'm/s', 'dimensions': {'length': 1, 'time': -1}})
    for level in levels:
        level['run_spec'].update(stop_time=span, inputs=[{'port': 1, 'variable_id': 'flux', 'unit': 'm/s', 'time': [0., span], 'values': flux, 'interpolation': 'linear'}])
        level['outputs'][0].update(time=[0., span], values=values)
    check = check_definition('conservation')
    check.update(window=[0., span], flux=var('flux'), absolute_tolerance=expected/10)
    require(policy, check)
    result = evaluate_trial_numeric(levels, policy, context)
    assert result['complete'] and not result['numerically_verified'], result
    assert all(level['maximum_violation'] == pytest.approx(expected, rel=2e-14, abs=0.) for level in result['checks'][0]['levels'])


def test_event_result_preserves_actual_sample_support_without_claiming_native_event_detection():
    levels, policy, context = full_case(); require(policy, check_definition('event_localization'))
    result = evaluate_trial_numeric(levels, policy, context)
    assert result['numerically_verified'], result
    for level, evaluated in zip(levels, result['checks'][0]['levels']):
        event = evaluated['events'][0]
        assert 'native_zero' not in event and type(event['reconstructed_zero']) is bool
        assert event['sample_brackets'][0]['observable_id'] == 'x'
        for sample in event['sample_brackets'][0]['native_samples']:
            assert sample['time'] == level['outputs'][0]['time'][sample['index']]
            assert sample['value'] == level['outputs'][0]['values'][sample['index']]


def test_unrelated_dense_union_cannot_shrink_sparse_native_event_support():
    levels, policy, context = full_case()
    check = check_definition('event_localization'); check['max_bracket_width'] = .1; require(policy, check)
    context['variables'].append({'id': 'z', 'unit': 'm', 'roles': ['output']})
    policy['outputs'].append({**policy['outputs'][0], 'port': 2, 'variable_id': 'z'})
    policy['observables'].append({'id': 'z', 'kind': 'output', 'port': 2, 'variable_id': 'z', 'unit': 'm', 'dimensions': {'length': 1}})
    for level in levels:
        level['run_spec']['outputs'].append({'port': 2, 'variable_id': 'z', 'unit': 'm'})
        level['outputs'][0].update(time=[0., 1.], values=[0., 1.])
        level['outputs'].append({'port': 2, 'variable_id': 'z', 'unit': 'm', 'time': [0., .49, .51, 1.], 'values': [0., 0., 0., 0.]})
    result = evaluate_trial_numeric(levels, policy, context)
    assert not result['complete'] and not result['numerically_verified'], result
    assert all(any('actual observable support' in e for e in level['errors']) for level in result['checks'][0]['levels'])


@pytest.mark.parametrize('fault', ['uncovered_output', 'output_type', 'unused_event', 'unused_check', 'wrong_state_path', 'not_required_check', 'unmatched_event_occurrence'])
def test_metric_prior_bindings_are_checked_before_native_arrays_exist(fault):
    levels, policy, context = full_case()
    check = check_definition('event_localization' if fault == 'unmatched_event_occurrence' else 'constraint'); require(policy, check)
    metric = {'statistic': 'event_time', 'event': check, 'unit': 's'} if fault == 'unmatched_event_occurrence' else {'statistic': 'constraint', 'check': check, 'unit': 'm'}
    if fault == 'uncovered_output': metric['output_port'] = 2
    elif fault == 'output_type': metric['output_port'] = 1.
    elif fault == 'unused_event': metric['event'] = check
    elif fault == 'unused_check': metric = {'statistic': 'final', 'check': check, 'output_port': 1, 'unit': 'm'}
    elif fault == 'wrong_state_path': metric.update(kind='state', variable_id='x', block_path='unrefined/State')
    elif fault == 'not_required_check': policy['obligations']['constraint'].update(status='not_applicable', check_ids=[])
    else: check.update(matching='first', expected_count=2); metric['event_index'] = 1
    report = validate_metric_policy(metric, policy, levels[0]['run_spec'], context)
    assert not report['valid'] and report['errors']


@pytest.mark.parametrize('statistic,unit', [('peak', 'm'), ('peak_time', 's'), ('integral', 'm*s'), ('absolute_integral', 'm*s'), ('squared_integral', '(m)^2*s')])
def test_all_new_whole_record_metrics_require_full_refinement_scope(statistic, unit):
    levels, policy, context = full_case()
    policy.update(scope='actual_points', trajectory={'mode': 'actual_points', 'max_gap': 1.}, comparison_times=[0., 1.])
    report = validate_metric_policy({'statistic': statistic, 'output_port': 1, 'unit': unit}, policy, levels[0]['run_spec'], context)
    assert not report['valid'] and report['errors']


def test_legacy_endpoint_final_cannot_be_interpolated_to_an_unverified_internal_time():
    levels, policy, context = full_case()
    policy.update(scope='actual_points', trajectory={'mode': 'actual_points', 'max_gap': 1.}, comparison_times=[0., 1.])
    metric = {'statistic': 'final', 'output_port': 1, 'unit': 'm', 'window': [0., .5]}
    assert not validate_metric_policy(metric, policy, levels[0]['run_spec'], context)['valid']
    assert not evaluate_metric(metric, levels[0], context=context, numeric_policy=policy)['defined']


def test_reviewed_uniform_envelope_cannot_upgrade_endpoint_refinement_to_full_window():
    levels, policy, context = full_case()
    policy.update(scope='actual_points', trajectory={'mode': 'actual_points', 'max_gap': 1.}, comparison_times=[0., 1.])
    envelope(policy)
    assert not validate_trial_numeric_policy(policy, levels[0]['run_spec'], context)['valid']
    result = evaluate_trial_numeric(levels, policy, context)
    assert not result['complete'] and not result['numerically_verified']
    assert any('endpoints cannot upgrade scope' in error for error in result['errors'])


def _review_extended(path):
    from numerical_factory import review_numerical
    from model_factory import file_ref
    from problem_factory import write_contract
    from runtime_common import load_document
    from validate_numerical_verification import settings_snapshot
    value = load_document(path)
    source = write_contract(path.parent/'numerical-settings.json', {'settings': settings_snapshot(value)})
    value['sources'] = [{'id': 'settings', **file_ref(path.parent, source), 'purpose': 'Complete synthetic full-H1 settings'}]
    value['settings_source_ref'] = {'source_id': 'settings', 'selector': ['settings']}
    write_contract(path, value)
    return review_numerical(path, refresh_source=False)


def _linear_source_history(root):
    """New y=u=t source and complete E wire evidence; no native execution.

    The prior is unchanged (.001, contraction .5).  Each synthetic level is
    exactly (1+epsilon_i)*t; its PWL interpolation has zero mathematical error.
    Thus the independent closed-form sup errors are epsilon_i, and adjacent
    differences are epsilon_i-epsilon_j on [0,1].  This avoids repurposing a
    coarse exponential-record criterion after seeing an assessment result.
    """
    from datetime import datetime, timedelta, timezone
    from model_factory import file_ref
    from numerical_factory import export_case, freeze_level
    from probe_environment import write_json
    from problem_factory import write_contract
    from runtime_common import load_document
    from run_simulation import finish_task_request, make_task_request
    from simulation_factory import make_simulation_protocol
    from test_simulation_assurance import make_simulation_profile, synthetic_case
    from validate_environment import utc_text
    from validate_numerical_verification import uniform_grid
    from validate_simulation_profile import contract as e_contract
    from validate_simulation_protocol import validate_simulation_protocol
    base = make_simulation_protocol(root, case='passthrough', solver='ode4', status='draft')
    primary = load_document(base)
    signal = {'kind': 'sampled', 'value': None, 'time': [0., 1.], 'values': [0., 1.], 'interpolation': 'linear'}
    scenario = write_contract(root/'scenario-source.json', {'description': 'SYNTHETIC exact identity y=u=t on [0,1]; no native qualification', 'u': signal})
    primary['sources'][0].update(file_ref(root, scenario))
    primary['inputs'][0]['data'] = signal
    protocols = []
    for index in range(3):
        value = copy.deepcopy(primary)
        value.update(status='draft', freeze_record=None)
        value['solver']['fixed_step'] = .1/(2**index)
        protocols.append(freeze_level(write_contract(root/f'linear-protocol-{index}.json', value), root))
    spec = validate_simulation_protocol(protocols[0], project_root=root, require_frozen=True)['run_spec']
    contract = {'schema_version': 1, 'project_id': primary['project_id'], 'status': 'draft',
        'primary_protocol': file_ref(root, protocols[0]), 'refinement_protocols': [file_ref(root, p) for p in protocols[1:]],
        'method': 'ode4_step_refinement', 'comparison_times': uniform_grid(0., 1., .1),
        'outputs': [{**{k: o[k] for k in ('port', 'variable_id', 'unit')}, 'absolute_tolerance': .001,
            'relative_tolerance': 0., 'contraction_limit': .5, 'roundoff_floor': 1e-14} for o in spec['outputs']],
        'obligations': {kind: {'status': 'not_applicable', 'reason': 'SYNTHETIC source prior: only the explicitly selected recorded checks are required',
            'source_ids': ['settings']} for kind in ('residual', 'constraint', 'conservation', 'event_localization', 'numerical_drift')},
        'budget': dict(HARD_BUDGET), 'claim_limit': 'SYNTHETIC INFRASTRUCTURE ONLY; linear PWL reconstruction and explicit criteria; no actual qualification or physical truth',
        'sources': [], 'settings_source_ref': None, 'review_record': None}
    path = write_contract(root/'numerical-verification.json', contract)
    _review_extended(path)
    a = root/'a-profile/evidence/profile.json'
    e = make_simulation_profile(root/'numerical-e-profile', a)
    receipts, offsets = [], (1e-4, 6.25e-6, 3.90625e-7)
    for index, protocol in enumerate(protocols):
        report = validate_simulation_protocol(protocol, project_root=root, require_frozen=True)
        assert report['valid'], report
        directory = root/f'linear-e-run-{index}'
        request = make_task_request(protocol, load_document(a)['runtime']['executable'], directory, report, a, e, project_root=root)
        directory.mkdir()
        names = e_contract()['evidence']
        write_json(directory/names['input'], request)
        (directory/names['log']).write_text('SYNTHETIC exact-linear E wire fixture; NO MATLAB EXECUTION\n', encoding='utf-8')
        actual = synthetic_case(request['cases'][0], directory, request['run_id'], primary=True)
        times = uniform_grid(0., 1., report['run_spec']['solver']['fixed_step'])
        values = [(1+offsets[index])*t for t in times]
        assert max(abs(y-t) for t, y in zip(times, values)) == pytest.approx(offsets[index], abs=4e-16)
        export_case(actual, directory, request['run_id'], times, values)
        now = datetime.now(timezone.utc)-timedelta(milliseconds=50)
        raw = load_document(e.parent/names['raw'])
        raw.update(run_id=request['run_id'], input_identity=request['input_identity'], source_identity=request['source_identity'],
            started_at=utc_text(now), finished_at=utc_text(now+timedelta(milliseconds=10)), cases=[actual])
        process = {'started_at': utc_text(now-timedelta(milliseconds=1)), 'finished_at': utc_text(now+timedelta(milliseconds=11)),
            'process_state': 'completed', 'exit_code': 0, 'pid': 0, 'command': ['SYNTHETIC; NO MATLAB']}
        write_json(directory/names['raw'], raw); write_json(directory/names['process'], process)
        receipts.append(finish_task_request(request, process))
    return path, receipts, offsets


@pytest.fixture(scope='module')
def full_history(tmp_path_factory):
    from problem_factory import write_contract
    from runtime_common import load_document
    from run_numerical_verification import run_numerical_verification
    from validate_numerical_verification import validate_numerical_verification
    root = tmp_path_factory.mktemp('full-H1-source-history')
    path, receipts, offsets = _linear_source_history(root)
    base = validate_numerical_verification(path, project_root=root)
    value = load_document(path); output = value['outputs'][0]
    dim = unit_dimensions(output['unit'])
    assert dim is not None
    dims = {k: p for k, p in zip(('mass', 'length', 'time', 'current', 'temperature', 'amount', 'luminous_intensity'), dim) if p}
    variable = output['variable_id']
    anchors = [r['id'] for r in base['numeric_context']['relations'] if variable in r['variable_ids']]
    value.update(scope='pwl_trajectory', trajectory={'mode': 'pwl_union', 'max_gap': 1.},
        observables=[{'id': 'observed', 'kind': 'output', 'port': output['port'], 'variable_id': variable, 'unit': output['unit'], 'dimensions': dims}],
        math_budget=full_case()[1]['math_budget'],
        checks=[{'id': 'output_bound', 'kind': 'constraint', 'window': [0., 1.], 'source_ids': ['settings'], 'relation_ids': anchors,
            'unit': output['unit'], 'dimensions': dims, 'expression': var('observed'), 'relation': 'le', 'threshold': 10.,
            'absolute_tolerance': 1e-9, 'relative_tolerance': 0., 'scale': 1.}])
    value['obligations']['constraint'].update(status='required', check_ids=['output_bound'])
    write_contract(path, value); _review_extended(path)
    report = run_numerical_verification(path, receipts, root/'accepted-full', project_root=root)
    assert report['valid'] and report['numerically_verified'], report
    from run_numerical_verification import RESULT_NAME
    result = load_document(Path(report['receipt_path']).parent/RESULT_NAME)
    assert result['outputs'][0]['D01'] == pytest.approx(offsets[0]-offsets[1], abs=4e-16)
    assert result['outputs'][0]['D12'] == pytest.approx(offsets[1]-offsets[2], abs=4e-16)
    assert value['outputs'][0]['absolute_tolerance'] == .001
    return {'root': root, 'path': path, 'receipts': receipts, 'report': report}


@pytest.fixture
def full_mutation(full_history):
    root = full_history['root']
    saved = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    try: yield full_history
    finally:
        for path in root.rglob('*'):
            if path.is_file() and path not in saved: path.unlink()
        for path, data in saved.items(): path.write_bytes(data)
        for directory in sorted((p for p in root.rglob('*') if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
            if not any(directory.iterdir()): directory.rmdir()


def test_complete_source_review_and_receipt_independently_execute_required_check(full_history):
    from validate_numerical_verification_receipt import validate_numerical_verification_receipt
    report = validate_numerical_verification_receipt(full_history['report']['receipt_path'], project_root=full_history['root'])
    assert report['valid'] and report['numerically_verified'], report
    assert len(report['checks']) == 1 and report['checks'][0]['kind'] == 'constraint'


def test_full_source_rebound_legitimate_constraint_failure_stays_valid_reject(full_mutation):
    from runtime_common import load_document
    from problem_factory import write_contract
    from run_numerical_verification import run_numerical_verification
    value = load_document(full_mutation['path']); value['checks'][0]['threshold'] = -10.
    write_contract(full_mutation['path'], value); _review_extended(full_mutation['path'])
    report = run_numerical_verification(full_mutation['path'], full_mutation['receipts'], full_mutation['root']/'reject-full', project_root=full_mutation['root'])
    assert report['valid'] and report['complete'] and not report['numerically_verified'], report


def test_full_source_rebound_wrong_check_dimensions_cannot_be_reviewed(full_mutation):
    from runtime_common import load_document
    from problem_factory import write_contract
    from validate_numerical_verification import validate_numerical_verification
    value = load_document(full_mutation['path']); value['checks'][0]['dimensions'] = {'mass': 1}
    write_contract(full_mutation['path'], value); _review_extended(full_mutation['path'])
    report = validate_numerical_verification(full_mutation['path'], project_root=full_mutation['root'], require_reviewed=True)
    assert not report['valid'] and not report['assessment_ready']


@pytest.mark.parametrize('fault', ['constant', 'check_unit'])
def test_full_source_rebound_cannot_review_unresolved_unit_conversion(full_mutation, fault):
    from runtime_common import load_document
    from problem_factory import write_contract
    from validate_numerical_verification import validate_numerical_verification
    value = load_document(full_mutation['path'])
    unit = '*'.join(['mm^32/m^32']*4)
    check = value['checks'][0]
    check.update(unit=unit if fault == 'check_unit' else '1', dimensions={}, threshold=0.,
        absolute_tolerance=1e-80, expression=const(0. if fault == 'check_unit' else 1e308,
            '1' if fault == 'check_unit' else unit, {}))
    write_contract(full_mutation['path'], value)
    _review_extended(full_mutation['path'])
    report = validate_numerical_verification(full_mutation['path'], project_root=full_mutation['root'], require_reviewed=True)
    assert report['schema_valid'], report
    assert not report['valid'] and not report['assessment_ready'] and not report['reviewed'], report
    assert any('unit conversion' in e for e in report['errors']), report


def test_rehashed_full_receipt_cannot_forge_required_check_pass(full_mutation):
    from runtime_common import load_document, sha256_file
    from probe_environment import write_json
    from run_numerical_verification import RESULT_NAME
    from validate_numerical_verification_receipt import validate_numerical_verification_receipt
    path = Path(full_mutation['report']['receipt_path']); artifact = path.parent/RESULT_NAME
    data = load_document(artifact); data['checks'][0]['levels'][0]['maximum_violation'] = 1.
    write_json(artifact, data)
    receipt = load_document(path); receipt['artifacts'][RESULT_NAME].update(sha256=sha256_file(artifact), bytes=artifact.stat().st_size)
    write_json(path, receipt)
    report = validate_numerical_verification_receipt(path, project_root=full_mutation['root'])
    assert not report['valid'] and any('recomputation' in e for e in report['errors'])
