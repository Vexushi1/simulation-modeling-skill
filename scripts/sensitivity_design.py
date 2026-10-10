"""Frozen, bounded sensitivity designs; no simulation or arbitrary expressions."""
from __future__ import annotations

import itertools
import math

from verification_common import finite, typed_equal

SENSITIVITY_METHODS = ('local_derivative', 'normalized_sensitivity', 'parameter_oat',
                       'morris', 'sobol', 'variance_based', 'prcc')
SENSITIVITY_HARD_BUDGET = {'max_factors': 8, 'max_points': 4096, 'max_matrix_cells': 65536,
                           'max_bootstrap_replicates': 1000, 'max_work_items': 2000000}


def sensitivity_budget(budget=None):
    if budget is not None and not isinstance(budget, dict):
        raise ValueError('source-declared sensitivity budget object required')
    result = dict(SENSITIVITY_HARD_BUDGET)
    for key, hard in result.items():
        if budget is not None and key in budget:
            value = budget[key]
            if type(value) is not int or not 1 <= value <= hard:
                raise ValueError('invalid sensitivity integer budget: ' + key)
            result[key] = value
    return result


def integer(value, label, minimum=1, maximum=None):
    if type(value) is not int or value < minimum or maximum is not None and value > maximum:
        raise ValueError(label + ': exact bounded integer required')
    return value


def number(value, label):
    if not finite(value):
        raise ValueError(label + ': finite real number required')
    return float(value)


def factor_records(factors, budget=None):
    limits = sensitivity_budget(budget)
    if not isinstance(factors, list) or not 1 <= len(factors) <= limits['max_factors']:
        raise ValueError('sensitivity factor budget exceeded or no ordered factors')
    seen = set()
    for item in factors:
        if not isinstance(item, dict) or not isinstance(item.get('id'), str) or not item['id'].strip() or item['id'] in seen:
            raise ValueError('unique ordered sensitivity factor IDs required')
        seen.add(item['id'])
        if not isinstance(item.get('unit'), str) or not item['unit'].strip():
            raise ValueError('declared factor unit required')
        domain = item.get('domain')
        if not isinstance(domain, dict) or set(domain) != {'lower', 'upper'} or 'baseline' not in item:
            raise ValueError('complete finite factor baseline/domain required')
        low, high = number(domain['lower'], 'domain lower'), number(domain['upper'], 'domain upper')
        if low >= high or not finite(high - low):
            raise ValueError('finite nonempty sensitivity factor domain required')
        baseline = number(item['baseline'], 'factor baseline')
        if not low <= baseline <= high:
            raise ValueError('factor baseline leaves its reviewed execution domain')
    return factors


def _law(factor):
    value = factor.get('law')
    if not isinstance(value, dict) or set(value) != {'kind', 'parameters'} or value['kind'] not in {'uniform', 'normal'}:
        raise ValueError('explicit uniform/normal factor law required')
    parameters = value['parameters']
    fields = {'lower', 'upper'} if value['kind'] == 'uniform' else {'mean', 'std'}
    if not isinstance(parameters, dict) or set(parameters) != fields:
        raise ValueError('exact factor law parameter fields required')
    parsed = {key: number(item, 'law ' + key) for key, item in parameters.items()}
    if value['kind'] == 'uniform' and parsed['lower'] >= parsed['upper'] or value['kind'] == 'normal' and parsed['std'] <= 0:
        raise ValueError('nondegenerate reviewed factor law required')
    if value['kind'] == 'uniform' and (not finite(parsed['upper'] - parsed['lower']) or
            parsed['lower'] < factor['domain']['lower'] or parsed['upper'] > factor['domain']['upper']):
        raise ValueError('complete uniform law support must fit reviewed execution domain')
    return value['kind'], parsed


def _transform_uniform(factor, uniform):
    kind, parameters = _law(factor)
    if kind == 'uniform':
        return parameters['lower'] + (parameters['upper'] - parameters['lower']) * float(uniform)
    from scipy.special import ndtri
    return parameters['mean'] + parameters['std'] * float(ndtri(uniform))


def _seed(settings):
    return integer(settings['seed'], 'seed', 0, 2**32 - 1)


def _steps(factors, settings):
    steps = settings['steps']
    if not isinstance(steps, list) or any(not isinstance(item, dict) for item in steps) or [item.get('factor_id') for item in steps] != [item['id'] for item in factors]:
        raise ValueError('ordered step records must cover every factor exactly')
    for item in steps:
        if set(item) != {'factor_id', 'h', 'scheme'} or item['scheme'] not in {'central', 'forward', 'backward'} or number(item['h'], 'step') <= 0:
            raise ValueError('positive source-declared central/forward/backward step required')
    agreement = settings['agreement']
    if (not isinstance(agreement, dict) or set(agreement) != {'absolute_tolerance', 'relative_tolerance'} or
            number(agreement['absolute_tolerance'], 'agreement absolute tolerance') < 0 or
            number(agreement['relative_tolerance'], 'agreement relative tolerance') < 0):
        raise ValueError('nonnegative two-scale agreement criteria required')
    return steps


def planned_sensitivity_count(method, factors, settings, *, budget=None):
    factor_records(factors, budget)
    limits, dimension = sensitivity_budget(budget), len(factors)
    if method not in SENSITIVITY_METHODS:
        raise ValueError('unknown sensitivity method')
    if not isinstance(settings, dict):
        raise ValueError('source-declared sensitivity settings required')
    fields = ({'steps', 'agreement', 'normalization'} if method in SENSITIVITY_METHODS[:3] else
              {'seed', 'grid_levels', 'trajectories', 'delta'} if method == 'morris' else
              {'seed', 'base_samples', 'second_order', 'dependence'} if method == 'sobol' else
              {'dependence'} if method == 'variance_based' else
              {'seed', 'samples', 'dependence', 'correlation', 'rank_tolerance', 'rows'})
    optional = {'correlation_tolerance'} if method == 'prcc' else set()
    if not fields <= set(settings) or set(settings) - fields - optional:
        raise ValueError('exact sensitivity method settings required; unused controls are forbidden')
    if method in SENSITIVITY_METHODS[:3]:
        _steps(factors, settings)
        normalization = settings.get('normalization')
        if method != 'normalized_sensitivity' and normalization is not None:
            raise ValueError('only normalized_sensitivity carries normalization settings')
        if method == 'normalized_sensitivity':
            if not isinstance(normalization, dict) or normalization.get('mode') not in {'relative_elasticity', 'reference_scales'}:
                raise ValueError('source-declared relative/reference normalization required')
            if normalization['mode'] == 'relative_elasticity':
                if set(normalization) != {'mode'}:
                    raise ValueError('relative elasticity uses actual registered baseline only')
            elif (set(normalization) != {'mode', 'factor_scales', 'output_scale'} or
                  not isinstance(normalization['factor_scales'], list) or len(normalization['factor_scales']) != dimension or
                  any(number(item, 'reference factor scale') <= 0 for item in normalization['factor_scales']) or
                  number(normalization['output_scale'], 'reference output scale') <= 0):
                raise ValueError('positive complete physical reference scales required')
        count = 1 + 4 * dimension
    elif method == 'morris':
        grid = integer(settings['grid_levels'], 'Morris grid levels', 4, 1024)
        if grid % 2 or number(settings['delta'], 'Morris delta') != grid / (2 * (grid - 1)):
            raise ValueError('Morris requires even grid and exact standard Delta')
        _seed(settings)
        count = integer(settings['trajectories'], 'Morris trajectories', 2) * (dimension + 1)
    elif method == 'sobol':
        if settings['dependence'] != 'independent' or type(settings['second_order']) is not bool:
            raise ValueError('classic Sobol requires independent product law and typed second_order')
        _seed(settings)
        for factor in factors:
            _law(factor)
        count = integer(settings['base_samples'], 'Sobol base samples', 2) * (2 * dimension + 2 if settings['second_order'] else dimension + 2)
    elif method == 'variance_based':
        if settings['dependence'] != 'independent':
            raise ValueError('product ANOVA requires independent finite law')
        counts = []
        for factor in factors:
            levels = factor['levels']
            if not isinstance(levels, list) or len(levels) < 2:
                raise ValueError('ANOVA nonfixed factor requires at least two levels')
            counts.append(len(levels))
            if math.prod(counts) > limits['max_points']:
                raise ValueError('sensitivity complete design point/matrix budget exceeded')
        for factor in factors:
            levels, probabilities = factor['levels'], factor['probabilities']
            if not isinstance(levels, list) or len(levels) < 2:
                raise ValueError('ANOVA nonfixed factor requires at least two levels')
            values = [number(value, 'ANOVA level') for value in levels]
            if len(set(values)) != len(values):
                raise ValueError('unique finite ANOVA levels required')
            if (not isinstance(probabilities, list) or len(probabilities) != len(levels) or
                    any(not finite(value) or value < 0 for value in probabilities) or math.fsum(probabilities) != 1.0):
                raise ValueError('explicit nonnegative ANOVA product probabilities summing to one required')
        count = math.prod(counts)
    else:
        _seed(settings)
        count = integer(settings['samples'], 'PRCC samples', dimension + 2)
        if not 0 < number(settings['rank_tolerance'], 'PRCC rank tolerance') < 1:
            raise ValueError('relative PRCC rank tolerance must lie strictly between zero and one')
        if settings['dependence'] not in {'independent', 'gaussian_copula'}:
            raise ValueError('explicit PRCC dependence mode required')
        if 'correlation_tolerance' in settings and not 0 < number(settings['correlation_tolerance'], 'correlation tolerance') <= 128 * 2**-52 * dimension:
            raise ValueError('correlation tolerance cannot exceed the machine-roundoff PSD bound')
        if settings.get('rows') is not None:
            rows = settings['rows']
            if not isinstance(rows, list) or len(rows) != count or any(not isinstance(row, list) or len(row) != dimension for row in rows):
                raise ValueError('complete ordered explicit PRCC matrix required')
        else:
            for factor in factors:
                _law(factor)
    if count > limits['max_points'] or count * dimension > limits['max_matrix_cells']:
        raise ValueError('sensitivity complete design point/matrix budget exceeded')
    if method == 'variance_based' and count * (2**dimension + dimension * 2**(dimension - 1)) > limits['max_work_items']:
        raise ValueError('ANOVA complete subset work budget exceeded')
    return count


def _verify_correlation_root(values, root, tolerance):
    import numpy as np
    if root.shape != (len(values), len(values)) or not bool(np.all(np.isfinite(root))):
        raise ValueError('complete finite covariance factor required')
    residual = float(np.max(np.abs(root @ root.T - np.asarray(values, dtype=float))))
    if residual > tolerance:
        raise ValueError('correlation factor covariance residual exceeds machine-roundoff bound')
    return residual


def _correlation_root(settings, dimension):
    import numpy as np
    matrix = settings.get('correlation')
    if settings['dependence'] == 'independent':
        if matrix is not None:
            raise ValueError('independent PRCC design cannot carry a correlation matrix')
        return np.eye(dimension)
    if (not isinstance(matrix, list) or len(matrix) != dimension or
            any(not isinstance(row, list) or len(row) != dimension for row in matrix)):
        raise ValueError('complete Gaussian-copula correlation matrix required')
    values = [[number(value, 'correlation') for value in row] for row in matrix]
    if any(values[i][i] != 1.0 for i in range(dimension)) or any(values[i][j] != values[j][i] or abs(values[i][j]) > 1 for i in range(dimension) for j in range(dimension)):
        raise ValueError('symmetric unit-diagonal correlation matrix required')
    # Only machine-scale roundoff is permitted. A reviewed optional tolerance
    # can tighten this bound, but it cannot authorize a different PSD law.
    tolerance = 128 * float(np.finfo(float).eps) * max(1, dimension)
    if 'correlation_tolerance' in settings:
        declared = number(settings['correlation_tolerance'], 'correlation tolerance')
        if not 0 < declared <= tolerance:
            raise ValueError('correlation tolerance cannot exceed the machine-roundoff PSD bound')
        tolerance = declared
    root = np.zeros((dimension, dimension))
    for i in range(dimension):
        for j in range(i + 1):
            residual = values[i][j] - math.fsum(float(root[i, k] * root[j, k]) for k in range(j))
            if i == j:
                if residual < -tolerance:
                    raise ValueError('correlation matrix is not positive semidefinite')
                root[i, j] = math.sqrt(max(residual, 0.0))
            elif root[j, j] > tolerance:
                root[i, j] = residual / root[j, j]
            elif abs(residual) > tolerance:
                raise ValueError('correlation matrix has inconsistent singular support')
    _verify_correlation_root(values, root, tolerance)
    return root


def generate_sensitivity_design(method, factors, settings, *, budget=None):
    count = planned_sensitivity_count(method, factors, settings, budget=budget)
    dimension, rows = len(factors), []
    baseline = [float(item['baseline']) for item in factors]
    def append(values, role, weight=None):
        values = [number(value, 'design coordinate') for value in values]
        if any(not factor['domain']['lower'] <= value <= factor['domain']['upper'] for factor, value in zip(factors, values)):
            raise ValueError('sample leaves reviewed execution domain; law cannot be clipped or redrawn')
        rows.append({'id': 'p' + str(len(rows)).zfill(6), 'values': values, 'role': role,
                     'weight': None if weight is None else float(weight)})
    metadata = {'sampling': 'deterministic', 'point_count': count}
    if method in SENSITIVITY_METHODS[:3]:
        append(baseline, {'kind': 'baseline'})
        for index, step in enumerate(settings['steps']):
            for scale in (1.0, 0.5):
                offsets = (-1, 1) if step['scheme'] == 'central' else ((1, 2) if step['scheme'] == 'forward' else (-1, -2))
                previous = None
                for offset in offsets:
                    values = list(baseline)
                    values[index] += offset * scale * step['h']
                    if values[index] == baseline[index]:
                        raise ValueError('finite difference step is not representable')
                    if previous == values[index]:
                        raise ValueError('distinct one-sided stencil nodes are not representable')
                    previous = values[index]
                    append(values, {'kind': 'stencil', 'factor_index': index, 'scale': scale, 'offset': offset})
        metadata['stencils'] = [item['scheme'] for item in settings['steps']]
    elif method == 'variance_based':
        for levels in itertools.product(*(range(len(item['levels'])) for item in factors)):
            append([item['levels'][level] for item, level in zip(factors, levels)],
                   {'kind': 'factorial', 'level_indices': list(levels)},
                   math.prod(item['probabilities'][level] for item, level in zip(factors, levels)))
        metadata['law'] = 'independent_finite_product'
    else:
        import numpy as np
        rng = np.random.Generator(np.random.PCG64(_seed(settings)))
        metadata.update(sampling='iid_pcg64', seed=settings['seed'])
        if method == 'morris':
            grid, delta_grid = settings['grid_levels'], settings['grid_levels'] // 2
            for trajectory in range(settings['trajectories']):
                signs = [1 if value else -1 for value in rng.integers(0, 2, size=dimension)]
                position = [int(value) + (delta_grid if sign < 0 else 0)
                            for value, sign in zip(rng.integers(0, delta_grid, size=dimension), signs)]
                order = [int(item) for item in rng.permutation(dimension)]
                def physical():
                    return [factor['domain']['lower'] + (factor['domain']['upper'] - factor['domain']['lower']) * value / (grid - 1)
                            for factor, value in zip(factors, position)]
                append(physical(), {'kind': 'morris', 'trajectory': trajectory, 'step': 0, 'changed_factor': None, 'direction': 0})
                for step, index in enumerate(order, 1):
                    before = physical()
                    position[index] += signs[index] * delta_grid
                    after = physical()
                    if before[index] == after[index]:
                        raise ValueError('Morris physical grid step is not representable')
                    append(after, {'kind': 'morris', 'trajectory': trajectory, 'step': step,
                                        'changed_factor': index, 'direction': signs[index]})
            metadata.update(sampling='morris_random_grid_trajectories', grid_levels=grid, delta=settings['delta'])
        elif method == 'sobol':
            size = settings['base_samples']
            uniforms = rng.random((size, 2 * dimension))
            a = [[_transform_uniform(factor, row[index]) for index, factor in enumerate(factors)] for row in uniforms]
            b = [[_transform_uniform(factor, row[dimension + index]) for index, factor in enumerate(factors)] for row in uniforms]
            for kind, matrix in (('A', a), ('B', b)):
                for index, values in enumerate(matrix):
                    append(values, {'kind': kind, 'base_index': index, 'factor_index': None})
            for kind in (('AB', 'BA') if settings['second_order'] else ('AB',)):
                for factor_index in range(dimension):
                    for index in range(size):
                        values = list(a[index] if kind == 'AB' else b[index])
                        values[factor_index] = (b[index] if kind == 'AB' else a[index])[factor_index]
                        append(values, {'kind': kind, 'base_index': index, 'factor_index': factor_index})
            metadata.update(base_samples=size, second_order=settings['second_order'], estimator='saltelli_jansen_pooled_center_v1')
        else:
            root = _correlation_root(settings, dimension)
            if settings.get('rows') is not None:
                values = settings['rows']
                metadata['sampling'] = 'explicit_ordered_rows'
            else:
                normal = rng.standard_normal((settings['samples'], dimension)) @ root.T
                from scipy.special import ndtr
                values = []
                for row in normal:
                    values.append([parameters['mean'] + parameters['std'] * float(row[index]) if kind == 'normal'
                                   else _transform_uniform(factor, float(ndtr(row[index])))
                                   for index, factor in enumerate(factors) for kind, parameters in [_law(factor)]])
            for index, row in enumerate(values):
                append(row, {'kind': 'prcc', 'sample_index': index})
            metadata.update(dependence=settings['dependence'], correlation=settings.get('correlation'),
                            correlation_space='latent_gaussian' if settings['dependence'] == 'gaussian_copula' else 'independent_product',
                            correlation_factor=root.tolist(),
                            correlation_factor_rank=sum(float(root[index, index]) > 0 for index in range(dimension)),
                            covariance_roundoff_bound=settings.get('correlation_tolerance', 128 * float(np.finfo(float).eps) * max(1, dimension)))
    if len(rows) != count:
        raise ValueError('complete sensitivity design count differs')
    return {'schema_version': 1, 'method': method, 'factor_ids': [item['id'] for item in factors],
            'rows': rows, 'metadata': metadata}


def validate_sensitivity_design(design, method, factors, settings, *, budget=None):
    expected = generate_sensitivity_design(method, factors, settings, budget=budget)
    if not typed_equal(design, expected):
        raise ValueError('complete typed sensitivity design/roles differ from deterministic regeneration')
    return True
