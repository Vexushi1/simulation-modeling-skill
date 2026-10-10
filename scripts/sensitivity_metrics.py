"""Recomputable sensitivity estimators over complete, frozen scalar responses.

No estimator runs a simulator, drops a failed row, clips an index, or replaces an
undefined quantity with zero. Sampling statements apply only to the registered law.
"""
from __future__ import annotations

import itertools
import json
import math

from sensitivity_design import (SENSITIVITY_METHODS, integer, number,
    planned_sensitivity_count, sensitivity_budget, validate_sensitivity_design)
from verification_common import finite


def _degenerate(code, detail, factor_id=None):
    return {'code': code, 'factor_id': factor_id, 'detail': detail}


def _factor(factor, metrics, units, diagnostics=None):
    return {'factor_id': factor['id'], 'defined': all(value is not None for value in metrics.values()),
            'metrics': metrics, 'units': units, 'diagnostics': diagnostics or {}}


def _estimate(method, factors, settings, rows, values, output_unit):
    """Internal estimator; bootstrap calls preserve complete blocks and roles."""
    degeneracies, entries, global_result = [], [], {}
    dimension = len(factors)
    if method in SENSITIVITY_METHODS[:3]:
        baseline = values[0]
        normalization = settings.get('normalization')
        for index, factor in enumerate(factors):
            step = settings['steps'][index]
            derivatives = []
            for scale_index, scale in enumerate((1.0, 0.5)):
                first, second = values[1 + 4 * index + 2 * scale_index:3 + 4 * index + 2 * scale_index]
                h = number(step['h'], 'step') * scale
                if step['scheme'] == 'central':
                    derivative = (second - first) / (2 * h)
                else:
                    derivative = (4 * (first - baseline) - (second - baseline)) / (2 * h)
                    if step['scheme'] == 'backward':
                        derivative = -derivative
                derivatives.append(derivative)
            coarse, fine = derivatives
            tolerance = (settings['agreement']['absolute_tolerance'] +
                         settings['agreement']['relative_tolerance'] * max(abs(coarse), abs(fine)))
            agreed = abs(coarse - fine) <= tolerance
            if not agreed:
                degeneracies.append(_degenerate('two_scale_disagreement', 'Declared finite-difference agreement failed.', factor['id']))
            metrics = {'derivative': fine, 'coarse_derivative': coarse}
            units = {'derivative': output_unit + '/' + factor['unit'], 'coarse_derivative': output_unit + '/' + factor['unit']}
            if method == 'normalized_sensitivity':
                if normalization['mode'] == 'relative_elasticity':
                    if factor['baseline'] == 0 or baseline == 0:
                        normalized = None
                        degeneracies.append(_degenerate('zero_relative_reference', 'Relative elasticity needs nonzero factor and output baselines.', factor['id']))
                    else:
                        normalized = fine * factor['baseline'] / baseline
                else:
                    normalized = fine * normalization['factor_scales'][index] / normalization['output_scale']
                metrics['normalized'] = normalized
                units['normalized'] = '1'
            entries.append(_factor(factor, metrics, units, {'two_scale_agreed': agreed,
                'agreement_difference': abs(coarse - fine), 'agreement_tolerance': tolerance,
                'baseline_response': baseline, 'scheme': step['scheme']}))
        scope = 'Declared finite-difference stencils at the registered baseline; two-scale agreement is numerical evidence, not differentiability proof.'
    elif method == 'morris':
        effects = [[] for _ in factors]
        for start in range(0, len(rows), dimension + 1):
            for offset in range(1, dimension + 1):
                role = rows[start + offset]['role']
                effect = (values[start + offset] - values[start + offset - 1]) / (role['direction'] * settings['delta'])
                effects[role['changed_factor']].append(effect)
        for factor, observed in zip(factors, effects):
            mean = math.fsum(observed) / len(observed)
            absolute = math.fsum(abs(value) for value in observed) / len(observed)
            sigma = math.sqrt(math.fsum((value - mean)**2 for value in observed) / (len(observed) - 1))
            entries.append(_factor(factor, {'mu': mean, 'mu_star': absolute, 'sigma': sigma,
                'physical_mu': mean / (factor['domain']['upper'] - factor['domain']['lower'])},
                {'mu': output_unit, 'mu_star': output_unit, 'sigma': output_unit,
                 'physical_mu': output_unit + '/' + factor['unit']}, {'elementary_effects': observed}))
        scope = 'Finite random grid trajectories under the declared normalized domain. Sigma combines nonlinearity, interaction and numerical variation.'
    elif method == 'sobol':
        count = len(rows) // (2 * dimension + 2 if settings['second_order'] else dimension + 2)
        a, b = values[:count], values[count:2 * count]
        reference = a[0]
        center = reference + math.fsum(value - reference for value in a + b) / (2 * count)
        variance = math.fsum((value - center)**2 for value in a + b) / (2 * count)
        global_result.update(variance=variance, pooled_center=center, base_samples=count,
                             estimator='saltelli_jansen_pooled_center_v1', second_order=[])
        ab = [values[(2 + i) * count:(3 + i) * count] for i in range(dimension)]
        for index, factor in enumerate(factors):
            first = math.fsum((bj - center) * (hybrid - aj) for aj, bj, hybrid in zip(a, b, ab[index])) / (count * variance) if variance else None
            total = math.fsum((aj - hybrid)**2 for aj, hybrid in zip(a, ab[index])) / (2 * count * variance) if variance else None
            entries.append(_factor(factor, {'S1': first, 'ST': total}, {'S1': '1', 'ST': '1'}))
        if settings['second_order']:
            ba = [values[(2 + dimension + i) * count:(3 + dimension + i) * count] for i in range(dimension)]
            for left in range(dimension):
                for right in range(left + 1, dimension):
                    interaction = (math.fsum((bai - center) * (abj - center) - (aj - center) * (bj - center)
                        for bai, abj, aj, bj in zip(ba[left], ab[right], a, b)) / (count * variance) -
                        entries[left]['metrics']['S1'] - entries[right]['metrics']['S1']) if variance else None
                    global_result['second_order'].append({'factor_ids': [factors[left]['id'], factors[right]['id']], 'S2': interaction, 'unit': '1'})
        if variance == 0:
            degeneracies.append(_degenerate('zero_sample_variance', 'No output variance resolved in this finite A/B sample; population constancy is not established.'))
        scope = 'Finite Monte Carlo estimates for the source-reviewed independent product law. Indices are untrimmed; finite negative or greater-than-one estimates remain evidence.'
    elif method == 'variance_based':
        reference = next(value for row, value in zip(rows, values) if row['weight'] > 0)
        offsets = [value - reference for value in values]
        mean_offset = math.fsum(row['weight'] * offset for row, offset in zip(rows, offsets))
        # The displayed raw mean can round at a large common offset. It must
        # never be subtracted back from observations or conditional means.
        mean = reference + mean_offset
        centered = [offset - mean_offset for offset in offsets]
        variance = math.fsum(row['weight'] * value**2 for row, value in zip(rows, centered))
        components = {(): [0.0] * len(rows)}
        subset_records = []
        orthogonality_maximum = 0.0

        def conditional_means(subset, observations):
            groups = {}
            for row, observed in zip(rows, observations):
                key = tuple(row['role']['level_indices'][index] for index in subset)
                weights, products = groups.setdefault(key, ([], []))
                weights.append(row['weight'])
                products.append(row['weight'] * observed)
            return {key: (math.fsum(products) / math.fsum(weights) if math.fsum(weights) else 0.0)
                    for key, (weights, products) in groups.items()}

        for size in range(1, dimension + 1):
            for subset in itertools.combinations(range(dimension), size):
                groups = conditional_means(subset, centered)
                component = []
                for row_index, row in enumerate(rows):
                    key = tuple(row['role']['level_indices'][index] for index in subset)
                    # A zero-probability conditional cell is not part of the law.
                    # All its native rows still remain required and consumed.
                    conditional = groups[key]
                    component.append(conditional - math.fsum(previous[row_index] for other, previous in components.items() if set(other) < set(subset)))
                components[subset] = component
                contribution = math.fsum(row['weight'] * value**2 for row, value in zip(rows, component))
                # For an independent product measure these conditional means
                # vanish after removing any one factor of U. This checks the
                # orthogonality property without an unbudgeted all-pairs matrix.
                orthogonality = max(abs(value) for removed in subset
                    for value in conditional_means(tuple(index for index in subset if index != removed), component).values())
                orthogonality_maximum = max(orthogonality_maximum, orthogonality)
                subset_records.append({'factor_ids': [factors[index]['id'] for index in subset], 'variance': contribution,
                                       'index': contribution / variance if variance else None, 'unit': '1',
                                       'orthogonality_maximum': orthogonality})
        for index, factor in enumerate(factors):
            first = next(item['index'] for item in subset_records if item['factor_ids'] == [factor['id']])
            total = math.fsum(item['index'] for item in subset_records if factor['id'] in item['factor_ids']) if variance else None
            entries.append(_factor(factor, {'S1': first, 'ST': total}, {'S1': '1', 'ST': '1'}))
        variance_sum = math.fsum(item['variance'] for item in subset_records)
        weight_sum = math.fsum(row['weight'] for row in rows)
        reconstruction_error = max((abs(math.fsum(component[index] for subset, component in components.items() if subset) - centered[index])
            for index, row in enumerate(rows) if row['weight'] > 0), default=0.0)
        centered_mean = math.fsum(row['weight'] * value for row, value in zip(rows, centered))
        unresolved_weights = [row['id'] for row in rows if row['weight'] == 0.0 and all(
            factor['probabilities'][level] > 0 for factor, level in zip(factors, row['role']['level_indices']))]
        # Fixed machine-roundoff guards scale with the actual bounded design,
        # never with its large raw offset or a source-selected repair tolerance.
        epsilon = 2**-52
        relative_guard = 128 * epsilon * max(1, len(rows), len(subset_records))
        effect_guard = relative_guard * max((abs(value) for value in centered), default=0.0)
        variance_guard = relative_guard * max(variance, variance_sum)
        weight_guard = 128 * epsilon * max(1, dimension)
        closure = {'product_weight': abs(weight_sum - 1.0) <= weight_guard,
                   'centered_mean': abs(centered_mean) <= effect_guard,
                   'total_variance': abs(variance_sum - variance) <= variance_guard,
                   'reconstruction': reconstruction_error <= effect_guard,
                   'orthogonality': orthogonality_maximum <= effect_guard,
                   'positive_probability_resolved': not unresolved_weights}
        if not all(closure.values()):
            degeneracies.append(_degenerate('anova_closure_unresolved', 'Complete finite-law decomposition did not satisfy fixed machine-roundoff closure guards.'))
        global_result.update(mean=mean, variance=variance, subsets=subset_records,
            mean_anchor=reference, mean_offset=mean_offset, centered_mean=centered_mean,
            product_weight_sum=weight_sum, subset_variance_sum=variance_sum,
            variance_closure_error=variance_sum - variance,
            variance_closure_relative_error=(variance_sum - variance) / variance if variance else None,
            closure_satisfied=all(closure.values()), closure_checks=closure,
            roundoff_guards={'relative': relative_guard, 'product_weight': weight_guard,
                             'effect': effect_guard, 'variance': variance_guard},
            reconstruction_maximum_error=reconstruction_error, orthogonality_maximum=orthogonality_maximum,
            unresolved_positive_probability_rows=unresolved_weights,
            zero_probability_rows=[row['id'] for row in rows if row['weight'] == 0.0])
        if variance == 0:
            degeneracies.append(_degenerate('zero_finite_law_variance', 'No output variance is resolved for the registered finite weighted measure.'))
        scope = 'Exact full-subset ANOVA for the registered independent finite discrete product law; it does not establish continuous-domain variance contributions.'
    else:
        import numpy as np
        from scipy.stats import rankdata
        ranks = np.array([rankdata([row['values'][index] for row in rows], method='average') for index in range(dimension)], dtype=float).T
        output_ranks = np.array(rankdata(values, method='average'), dtype=float)
        for index, factor in enumerate(factors):
            # Remove the intercept exactly before numerical rank detection, so
            # any declared tolerance retains the constant control subspace.
            controls = np.delete(ranks, index, axis=1)
            controls = controls - controls.mean(axis=0)
            u, singular, _ = np.linalg.svd(controls, full_matrices=False)
            control_rank = int(np.sum(singular > settings['rank_tolerance'] * singular[0])) if len(singular) else 0
            rank = control_rank + 1
            basis = u[:, :control_rank]
            centered_x = ranks[:, index] - ranks[:, index].mean()
            centered_y = output_ranks - output_ranks.mean()
            x = centered_x - basis @ (basis.T @ centered_x)
            y = centered_y - basis @ (basis.T @ centered_y)
            xx, yy = float(x @ x), float(y @ y)
            tolerance = settings['rank_tolerance']**2
            x_scale = max(float(ranks[:, index] @ ranks[:, index]), 1.0)
            y_scale = max(float(output_ranks @ output_ranks), 1.0)
            coefficient = None if xx <= tolerance * x_scale or yy <= tolerance * y_scale else float(x @ y) / math.sqrt(xx * yy)
            if coefficient is None:
                degeneracies.append(_degenerate('zero_rank_residual', 'Factor or response ranks have no resolved residual after projection onto other ranks.', factor['id']))
            diagnostics = {'control_rank': rank, 'control_columns': dimension, 'degrees_of_freedom': len(rows) - rank - 1,
                'rank_deficient_controls': rank < dimension, 'x_residual_sum_squares': xx, 'y_residual_sum_squares': yy,
                'standard_inference_available': rank == dimension and len(rows) - rank - 1 > 0}
            entries.append(_factor(factor, {'PRCC': coefficient}, {'PRCC': '1'}, diagnostics))
        global_result['rank_tolerance'] = float(settings['rank_tolerance'])
        scope = 'Partial Pearson correlation of average ranks after fixed-tolerance linear projection; conditional rank association, including correlated inputs, is not causal attribution or a Sobol index.'
    defined = not degeneracies and all(item['defined'] for item in entries)
    return {'method': method, 'complete': True, 'defined': defined, 'factors': entries,
            'global': global_result, 'degeneracies': degeneracies, 'scope': scope}


def _flat(result):
    # Structured encoded identities avoid collisions from legal dotted factor IDs.
    values = {json.dumps([item['factor_id'], key], separators=(',', ':')): value
              for item in result['factors'] for key, value in item['metrics'].items()}
    values.update({json.dumps(['interaction', 'S2', *item['factor_ids']], separators=(',', ':')): item['S2']
                   for item in result['global'].get('second_order', [])})
    return values


def _inference(value, method, limits, work):
    if value is None or value == {'method': 'none'}:
        value = {'method': 'none', 'replicates': 0, 'seed': 0, 'confidence': 0.95, 'min_valid_fraction': 1.0}
    if not isinstance(value, dict) or set(value) != {'method', 'replicates', 'seed', 'confidence', 'min_valid_fraction'}:
        raise ValueError('exact source-declared sensitivity inference fields required')
    if value.get('method') not in {'none', 'percentile_bootstrap'}:
        raise ValueError('declared none/percentile_bootstrap inference required')
    count = integer(value['replicates'], 'bootstrap replicates', 0, limits['max_bootstrap_replicates'])
    integer(value['seed'], 'bootstrap seed', 0, 2**32 - 1)
    if not 0 < number(value['confidence'], 'confidence') < 1 or not 0 < number(value['min_valid_fraction'], 'valid bootstrap fraction') <= 1:
        raise ValueError('bounded confidence/valid fraction required')
    if value['method'] == 'none' and count != 0 or value['method'] == 'percentile_bootstrap' and count < 2:
        raise ValueError('bootstrap method and replicate count differ')
    if count and method not in {'morris', 'sobol', 'prcc'}:
        raise ValueError('bootstrap is defined only for trajectory/block/row sampling estimators')
    if (count + 1) * work > limits['max_work_items']:
        raise ValueError('complete sensitivity and bootstrap work budget exceeded')
    return value


def validate_sensitivity_inference(method, factors, settings, inference=None, *, budget=None):
    """Controller preflight: no point allocation and no native execution."""
    count = planned_sensitivity_count(method, factors, settings, budget=budget)
    dimension = len(factors)
    work = count * (2**dimension + dimension * 2**(dimension - 1) if method == 'variance_based' else dimension**3 if method == 'prcc' else dimension)
    parsed = _inference(inference, method, sensitivity_budget(budget), work)
    if method == 'prcc' and settings.get('rows') is not None and parsed['method'] != 'none':
        raise ValueError('explicit deterministic PRCC rows have no declared IID row-bootstrap sampling interpretation')
    return parsed


def compute_sensitivity(method, factors, settings, design, responses, *, inference=None, budget=None, output_unit='1'):
    inference = validate_sensitivity_inference(method, factors, settings, inference, budget=budget)
    validate_sensitivity_design(design, method, factors, settings, budget=budget)
    rows = design['rows']
    if not isinstance(responses, dict) or set(responses) != {row['id'] for row in rows}:
        raise ValueError('exact complete scalar response identity coverage required; rows cannot be dropped')
    values = [number(responses[row['id']], 'response') for row in rows]
    dimension = len(factors)
    if not isinstance(output_unit, str) or not output_unit.strip():
        raise ValueError('actual metric output unit required')
    result = _estimate(method, factors, settings, rows, values, output_unit)
    if method in {'sobol', 'variance_based'}:
        result['global']['variance_unit'] = '(' + output_unit + ')^2'
    if method == 'variance_based':
        result['global']['mean_unit'] = output_unit
        for subset in result['global']['subsets']:
            subset['variance_unit'] = '(' + output_unit + ')^2'
    bootstrap = {'method': inference['method'], 'requested': inference['replicates'], 'valid': 0, 'invalid': 0,
                 'replicates': [], 'intervals': {}, 'defined': True, 'scope': 'No sampling interval requested.'}
    if inference['replicates']:
        import numpy as np
        rng = np.random.Generator(np.random.PCG64(inference['seed']))
        count = settings['trajectories'] if method == 'morris' else settings['base_samples'] if method == 'sobol' else len(rows)
        for replicate in range(inference['replicates']):
            selected = [int(value) for value in rng.integers(0, count, size=count)]
            if method == 'morris':
                indices = [index * (dimension + 1) + offset for index in selected for offset in range(dimension + 1)]
            elif method == 'sobol':
                indices = [offset * count + index for offset in range(len(rows) // count) for index in selected]
            else:
                indices = selected
            estimated = _estimate(method, factors, settings, [rows[index] for index in indices], [values[index] for index in indices], output_unit)
            bootstrap['replicates'].append({'index': replicate, 'defined': estimated['defined'], 'estimates': _flat(estimated),
                                             'degeneracies': estimated['degeneracies']})
        bootstrap['valid'] = sum(item['defined'] for item in bootstrap['replicates'])
        bootstrap['invalid'] = inference['replicates'] - bootstrap['valid']
        enough = bootstrap['valid'] / inference['replicates'] >= inference['min_valid_fraction'] and bootstrap['valid'] >= 2
        bootstrap['defined'] = enough
        alpha = (1.0 - inference['confidence']) / 2
        units = {json.dumps([entry['factor_id'], key], separators=(',', ':')): unit
                 for entry in result['factors'] for key, unit in entry['units'].items()}
        units.update({json.dumps(['interaction', 'S2', *entry['factor_ids']], separators=(',', ':')): '1'
                      for entry in result['global'].get('second_order', [])})
        for key in _flat(result):
            estimates = [item['estimates'][key] for item in bootstrap['replicates'] if item['defined']]
            bounds = [float(value) for value in np.quantile(estimates, [alpha, 1 - alpha], method='linear')] if enough else [None, None]
            bootstrap['intervals'][key] = {'lower': bounds[0], 'upper': bounds[1], 'valid_replicates': len(estimates),
                                          'conditional': bootstrap['invalid'] > 0,
                                          'unit': units[key]}
        bootstrap['scope'] = ('Percentile resampling of complete trajectories, paired A/B/hybrid blocks or complete rank rows. '
            'Every degenerate replicate remains recorded; intervals with invalid replicates are conditional on mathematical definability, not nominal unconditional coverage.')
        if not enough:
            result['degeneracies'].append(_degenerate('insufficient_defined_bootstrap', 'Declared minimum complete valid resampling fraction/count was not met.'))
            result['defined'] = False
    result['bootstrap'] = bootstrap
    def finite_tree(value):
        if isinstance(value, dict):
            return all(finite_tree(item) for item in value.values())
        if isinstance(value, list):
            return all(finite_tree(item) for item in value)
        return not isinstance(value, float) or finite(value)
    if not finite_tree(result):
        raise ValueError('sensitivity estimator overflow; no nonfinite result may be exported')
    return result
