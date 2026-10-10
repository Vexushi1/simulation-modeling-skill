"""Analytic sensitivity oracles and complete-design/degeneracy boundaries."""
import copy
import math

import pytest

from sensitivity_design import (_verify_correlation_root, generate_sensitivity_design,
                                planned_sensitivity_count, validate_sensitivity_design)
from sensitivity_metrics import compute_sensitivity


def factors(count=2, *, baseline=0.5):
    return [{'id': 'x' + str(index), 'unit': 's', 'baseline': baseline,
             'domain': {'lower': 0.0, 'upper': 1.0},
             'law': {'kind': 'uniform', 'parameters': {'lower': 0.0, 'upper': 1.0}},
             'levels': [0.0, 1.0], 'probabilities': [0.5, 0.5]} for index in range(count)]


def settings(method, count=2):
    if method in {'local_derivative', 'normalized_sensitivity', 'parameter_oat'}:
        return {'steps': [{'factor_id': 'x' + str(index), 'h': 0.125, 'scheme': 'central'} for index in range(count)],
                'agreement': {'absolute_tolerance': 1e-12, 'relative_tolerance': 1e-12},
                'normalization': {'mode': 'relative_elasticity'} if method == 'normalized_sensitivity' else None}
    if method == 'morris':
        return {'seed': 21, 'grid_levels': 4, 'trajectories': 8, 'delta': 2/3}
    if method == 'sobol':
        return {'seed': 21, 'base_samples': 512, 'second_order': True, 'dependence': 'independent'}
    if method == 'variance_based':
        return {'dependence': 'independent'}
    return {'seed': 21, 'samples': 12, 'dependence': 'independent', 'correlation': None,
            'rank_tolerance': 1e-12, 'rows': None}


def estimate(method, fn, records=None, config=None, **kwargs):
    records = factors() if records is None else records
    config = settings(method, len(records)) if config is None else config
    design = generate_sensitivity_design(method, records, config, budget=kwargs.get('budget'))
    responses = {row['id']: fn(row['values']) for row in design['rows']}
    return compute_sensitivity(method, records, config, design, responses, **kwargs), design


@pytest.mark.parametrize('method', ['local_derivative', 'normalized_sensitivity', 'parameter_oat'])
def test_linear_derivative_and_elasticity_have_physical_units(method):
    result, design = estimate(method, lambda x: 2*x[0] + 3*x[1])
    assert result['defined'] and len(design['rows']) == 9
    assert [row['metrics']['derivative'] for row in result['factors']] == [2.0, 3.0]
    assert result['factors'][0]['units']['derivative'] == '1/s'
    if method == 'normalized_sensitivity':
        assert [row['metrics']['normalized'] for row in result['factors']] == [0.4, 0.6]


@pytest.mark.parametrize('scheme,baseline', [('forward', 0.0), ('backward', 1.0)])
def test_reviewed_boundary_second_order_stencils(scheme, baseline):
    records, config = factors(1, baseline=baseline), settings('local_derivative', 1)
    config['steps'][0]['scheme'] = scheme
    result, _ = estimate('local_derivative', lambda x: x[0]**2, records, config)
    assert result['defined']
    assert result['factors'][0]['metrics']['derivative'] == 2 * baseline


def test_nonlinear_local_disagreement_is_not_supported_by_small_stencil():
    result, _ = estimate('local_derivative', lambda x: x[0]**3, factors(1), settings('local_derivative', 1))
    assert not result['defined']
    assert result['degeneracies'][0]['code'] == 'two_scale_disagreement'


@pytest.mark.parametrize('zero', ['factor', 'output'])
def test_zero_relative_references_are_undefined_without_epsilon(zero):
    records, config = factors(1, baseline=0.0 if zero == 'factor' else 0.5), settings('normalized_sensitivity', 1)
    config['steps'][0]['scheme'] = 'forward'
    result, _ = estimate('normalized_sensitivity', lambda x: x[0] if zero == 'factor' else 0.0, records, config)
    assert not result['defined'] and result['factors'][0]['metrics']['normalized'] is None
    assert result['degeneracies'][0]['code'] == 'zero_relative_reference'
    config['normalization'] = {'mode': 'reference_scales', 'factor_scales': [2.0], 'output_scale': 4.0}
    result, _ = estimate('normalized_sensitivity', lambda x: x[0] if zero == 'factor' else 0.0, records, config)
    assert result['defined']


def test_morris_linear_mu_star_sigma_and_single_factor_moves():
    result, design = estimate('morris', lambda x: 2*x[0] - 3*x[1])
    assert result['defined']
    for record, coefficient in zip(result['factors'], [2.0, -3.0]):
        assert record['metrics']['mu'] == pytest.approx(coefficient)
        assert record['metrics']['mu_star'] == pytest.approx(abs(coefficient))
        assert record['metrics']['sigma'] == pytest.approx(0.0, abs=1e-14)
    for start in range(0, len(design['rows']), 3):
        changed = []
        for offset in (1, 2):
            left, right = design['rows'][start + offset - 1], design['rows'][start + offset]
            indices = [index for index in range(2) if left['values'][index] != right['values'][index]]
            assert indices == [right['role']['changed_factor']]
            changed += indices
        assert sorted(changed) == [0, 1]


def test_sobol_additive_analytic_product_law_indices_and_second_order():
    result, _ = estimate('sobol', lambda x: x[0] + 2*x[1])
    assert result['defined']
    assert [item['metrics']['S1'] for item in result['factors']] == pytest.approx([0.2, 0.8], abs=0.12)
    assert [item['metrics']['ST'] for item in result['factors']] == pytest.approx([0.2, 0.8], abs=0.12)
    assert result['global']['second_order'][0]['S2'] == pytest.approx(0.0, abs=0.2)


def test_sobol_finite_indices_above_one_remain_unclipped():
    records, config = factors(), settings('sobol')
    config['base_samples'] = 2
    design = generate_sensitivity_design('sobol', records, config)
    responses = {}
    for row in design['rows']:
        role = row['role']
        a = [-1.0, 1.0][role['base_index']]
        b = -a
        responses[row['id']] = b if role['kind'] == 'B' or role['kind'] == 'AB' and role['factor_index'] == 0 or role['kind'] == 'BA' and role['factor_index'] == 1 else a
    result = compute_sensitivity('sobol', records, config, design, responses)
    assert result['factors'][0]['metrics'] == {'S1': 2.0, 'ST': 2.0}
    assert result['factors'][1]['metrics'] == {'S1': 0.0, 'ST': 0.0}
    assert result['global']['second_order'][0]['S2'] == 0.0


@pytest.mark.parametrize('method', ['sobol', 'variance_based', 'prcc'])
def test_constant_response_retains_all_rows_and_undefined_indices(method):
    result, design = estimate(method, lambda x: 5.0)
    assert result['complete'] and not result['defined'] and result['degeneracies']
    assert all(any(value is None for value in row['metrics'].values()) for row in result['factors'])
    assert len(design['rows']) == planned_sensitivity_count(method, factors(), settings(method))


def test_nonbinary_constant_keeps_zero_variance_with_nonpower_sample_count():
    config = settings('sobol')
    config['base_samples'] = 7
    result, _ = estimate('sobol', lambda x: .1, config=config)
    assert result['global']['variance'] == 0.0 and not result['defined']
    records = factors()
    records[0]['probabilities'] = [.1, .9]
    records[1]['probabilities'] = [.3, .7]
    result, _ = estimate('variance_based', lambda x: .1, records)
    assert result['global']['variance'] == 0.0 and not result['defined']


def test_weighted_anova_all_subsets_and_variance_closure():
    records = factors()
    records[0]['probabilities'] = [0.25, 0.75]
    result, _ = estimate('variance_based', lambda x: x[0] + 2*x[1], records)
    assert result['defined'] and result['global']['mean'] == 1.75
    assert result['global']['variance'] == 1.1875
    subsets = result['global']['subsets']
    assert len(subsets) == 3 and sum(item['variance'] for item in subsets) == 1.1875
    assert [row['metrics']['S1'] for row in result['factors']] == pytest.approx([3/19, 16/19])
    assert subsets[-1]['variance'] == 0.0


def test_weighted_anova_interaction_and_zero_probability_rows_are_not_deleted():
    result, _ = estimate('variance_based', lambda x: (2*x[0]-1)*(2*x[1]-1))
    assert [row['metrics']['S1'] for row in result['factors']] == [0.0, 0.0]
    assert [row['metrics']['ST'] for row in result['factors']] == [1.0, 1.0]
    assert result['global']['subsets'][-1]['index'] == 1.0
    records = factors()
    records[0]['probabilities'] = [0.0, 1.0]
    result, design = estimate('variance_based', lambda x: 2*x[1], records)
    assert len(design['rows']) == 4 and len(result['global']['zero_probability_rows']) == 2
    assert result['defined'] and result['factors'][1]['metrics']['S1'] == 1.0


def test_weighted_anova_large_common_offset_keeps_centered_variance_and_orthogonality():
    result, _ = estimate('variance_based', lambda x: 1e16 + 2*x[0] + 4*x[1])
    assert result['defined'] and result['global']['closure_satisfied']
    assert result['global']['mean_anchor'] == 1e16 and result['global']['mean_offset'] == 3.0
    assert result['global']['variance'] == 5.0
    assert [entry['variance'] for entry in result['global']['subsets']] == [1.0, 4.0, 0.0]
    assert result['global']['variance_closure_error'] == 0.0
    assert result['global']['orthogonality_maximum'] == 0.0
    assert all(result['global']['closure_checks'].values())


def test_unresolved_positive_product_mass_cannot_claim_exact_anova_defined():
    records = factors()
    for record in records:
        record['probabilities'] = [1e-200, 1.0]
    result, design = estimate('variance_based', lambda x: x[0] + x[1], records)
    assert len(design['rows']) == 4 and result['complete']
    assert not result['defined'] and not result['global']['closure_satisfied']
    assert not result['global']['closure_checks']['positive_probability_resolved']
    assert result['global']['unresolved_positive_probability_rows'] == [design['rows'][0]['id']]
    assert any(entry['code'] == 'anova_closure_unresolved' for entry in result['degeneracies'])


@pytest.mark.parametrize('method', ['local_derivative', 'morris'])
def test_real_output_unit_substring_in_factor_label_is_preserved(method):
    records = factors(1)
    records[0]['unit'] = 'output_unit'
    result, _ = estimate(method, lambda x: 2*x[0], records, output_unit='kg')
    key = 'derivative' if method == 'local_derivative' else 'physical_mu'
    assert result['factors'][0]['units'][key] == 'kg/output_unit'
    if method == 'morris':
        assert result['factors'][0]['units']['mu_star'] == 'kg'


def test_prcc_midranks_and_monotone_response_without_reranking_residuals():
    records, config = factors(1), settings('prcc', 1)
    config.update(samples=6, rows=[[0.0], [0.2], [0.2], [0.5], [0.8], [1.0]])
    result, _ = estimate('prcc', lambda x: math.exp(x[0]), records, config)
    assert result['defined'] and result['factors'][0]['metrics']['PRCC'] == pytest.approx(1.0)
    assert result['factors'][0]['diagnostics']['degrees_of_freedom'] == 4


def test_prcc_collinear_factor_is_undefined_and_rank_diagnostics_remain():
    records, config = factors(3), settings('prcc', 3)
    config.update(samples=6, rows=[[x, x, z] for x, z in [(0, .7), (.2, .1), (.4, .9), (.6, .3), (.8, .5), (1, 0)]])
    result, _ = estimate('prcc', lambda x: x[0] + .2*x[2], records, config)
    assert not result['defined']
    assert result['factors'][0]['metrics']['PRCC'] is None
    assert result['factors'][2]['diagnostics']['rank_deficient_controls']
    assert not result['factors'][2]['diagnostics']['standard_inference_available']


@pytest.mark.parametrize('method', ['morris', 'sobol', 'prcc'])
def test_bootstrap_is_complete_deterministic_and_retains_degenerate_replicates(method):
    inference = {'method': 'percentile_bootstrap', 'replicates': 12, 'seed': 7, 'confidence': .95, 'min_valid_fraction': 1.0}
    result, design = estimate(method, lambda x: 1.0, inference=inference)
    assert len(result['bootstrap']['replicates']) == 12
    if method == 'morris':
        assert result['bootstrap']['valid'] == 12 and result['defined']
    else:
        assert result['bootstrap']['invalid'] == 12 and not result['bootstrap']['defined']
        assert all(not item['defined'] and item['degeneracies'] for item in result['bootstrap']['replicates'])
    again, _ = estimate(method, lambda x: 1.0, inference=inference)
    assert result == again


@pytest.mark.parametrize('method', ['local_derivative', 'normalized_sensitivity', 'parameter_oat', 'morris', 'sobol', 'variance_based', 'prcc'])
def test_design_roles_and_missing_failed_response_cannot_be_rewritten(method):
    records, config = factors(), settings(method)
    design = generate_sensitivity_design(method, records, config)
    corrupted = copy.deepcopy(design)
    corrupted['rows'][0]['role']['forged'] = True
    with pytest.raises(ValueError, match='typed sensitivity design'):
        validate_sensitivity_design(corrupted, method, records, config)
    responses = {row['id']: 1.0 for row in design['rows']}
    responses.pop(design['rows'][-1]['id'])
    with pytest.raises(ValueError, match='complete scalar response'):
        compute_sensitivity(method, records, config, design, responses)


@pytest.mark.parametrize('method', ['sobol', 'variance_based'])
def test_classic_product_estimators_reject_correlated_law(method):
    config = settings(method)
    config['dependence'] = 'gaussian_copula'
    with pytest.raises(ValueError, match='independent'):
        generate_sensitivity_design(method, factors(), config)


def test_unused_correlation_settings_cannot_masquerade_as_independent_sobol():
    config = settings('sobol')
    config['correlation'] = [[1., .9], [.9, 1.]]
    with pytest.raises(ValueError, match='unused controls'):
        generate_sensitivity_design('sobol', factors(), config)


@pytest.mark.parametrize('attack', ['float_count', 'point_budget', 'bootstrap_budget', 'law_domain', 'invalid_psd', 'duplicate_levels'])
def test_design_and_resampling_budget_preflight(attack):
    records, config = factors(), settings('sobol')
    if attack == 'float_count':
        config['base_samples'] = 2.0
    elif attack == 'point_budget':
        with pytest.raises(ValueError, match='point/matrix budget'):
            generate_sensitivity_design('sobol', records, config, budget={'max_points': 10})
        return
    elif attack == 'bootstrap_budget':
        inference = {'method': 'percentile_bootstrap', 'replicates': 1000, 'seed': 7, 'confidence': .95, 'min_valid_fraction': 1.0}
        with pytest.raises(ValueError, match='work budget'):
            estimate('sobol', lambda x: x[0], inference=inference)
        return
    elif attack == 'law_domain':
        records[0]['law']['parameters']['upper'] = 10.0
    elif attack == 'invalid_psd':
        config = settings('prcc', 3)
        config.update(dependence='gaussian_copula', correlation=[[1., .9, .9], [.9, 1., -.9], [.9, -.9, 1.]])
        with pytest.raises(ValueError, match='semidefinite'):
            generate_sensitivity_design('prcc', factors(3), config)
        return
    else:
        records[0]['levels'] = [0., 0.]
        with pytest.raises(ValueError, match='unique finite ANOVA'):
            generate_sensitivity_design('variance_based', records, settings('variance_based'))
        return
    with pytest.raises(ValueError):
        generate_sensitivity_design('sobol', records, config)


def test_source_joint_sampler_handles_singular_copula_without_renewing_rows():
    records, config = factors(), settings('prcc')
    config.update(dependence='gaussian_copula', correlation=[[1., 1.], [1., 1.]])
    design = generate_sensitivity_design('prcc', records, config)
    assert design['metadata']['correlation_factor_rank'] == 1
    assert all(row['values'][0] == row['values'][1] for row in design['rows'])
    result = compute_sensitivity('prcc', records, config, design, {row['id']: row['values'][0] for row in design['rows']})
    assert not result['defined'] and len(result['degeneracies']) == 2


@pytest.mark.parametrize('declared_tolerance', [None, 1e-6])
def test_prcc_indefinite_copula_is_rejected_before_any_sampling(declared_tolerance, monkeypatch):
    import numpy as np
    config = settings('prcc', 3)
    rho = -.5000001
    config.update(dependence='gaussian_copula', correlation=[[1., rho, rho], [rho, 1., rho], [rho, rho, 1.]])
    if declared_tolerance is not None:
        config['correlation_tolerance'] = declared_tolerance
    class UnsampledGenerator:
        def __init__(self, *args): pass
        def standard_normal(self, *args): raise AssertionError('indefinite law was sampled')
    monkeypatch.setattr(np.random, 'Generator', UnsampledGenerator)
    with pytest.raises(ValueError, match='semidefinite|machine-roundoff'):
        generate_sensitivity_design('prcc', factors(3), config)


def test_covariance_factor_must_reconstruct_exact_declared_matrix_within_machine_bound():
    import numpy as np
    matrix = [[1., .6], [.6, 1.]]
    factor = np.array([[1., 0.], [.6, .8]])
    tolerance = 256 * float(np.finfo(float).eps)
    assert _verify_correlation_root(matrix, factor, tolerance) <= tolerance
    altered = factor.copy()
    altered[1, 0] += 1e-4
    with pytest.raises(ValueError, match='covariance residual'):
        _verify_correlation_root(matrix, altered, tolerance)
