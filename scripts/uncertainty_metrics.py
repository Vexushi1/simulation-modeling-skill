"""Frozen fixed-N uncertainty designs and explicitly conditional inference.

Rows, including repeated physical draws and unsafe normal-tail draws, are never
removed, clipped or resampled. Correlation is of latent Gaussian coordinates
for a copula; it is not asserted to be physical Pearson correlation.
"""
from __future__ import annotations

import math
import itertools

import numpy as np
from scipy.stats import beta, norm, t

from verification_common import finite, typed_equal

UNCERTAINTY_METHODS = ('independent_mc', 'gaussian_joint_mc', 'gaussian_copula_mc')
LIMITS = {'max_factors': 8, 'max_points': 4096, 'max_matrix_cells': 65536,
          'max_bootstrap_replicates': 1000, 'max_work_items': 2000000}


def real(value, label):
    if not finite(value):
        raise ValueError(label + ': finite real number required, not bool')
    return float(value)


def integer(value, lower, upper, label):
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError(label + ': bounded exact integer required')
    return value


def exact(value, fields, label):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ValueError(label + ': exact fields required: ' + ','.join(fields))


def limits(budget):
    out = {key: (budget or {}).get(key, maximum) for key, maximum in LIMITS.items()}
    for key, maximum in LIMITS.items():
        integer(out[key], 1, maximum, key)
    return out


def correlation_factor(matrix, dimension):
    """Deterministic semidefinite Cholesky, including exact singular laws."""
    if not isinstance(matrix, list) or len(matrix) != dimension or any(not isinstance(row, list) or len(row) != dimension for row in matrix):
        raise ValueError('complete square latent correlation matrix required')
    a = np.asarray([[real(x, 'correlation') for x in row] for row in matrix], dtype=np.float64)
    tolerance = 128 * np.finfo(float).eps * max(1, dimension)
    if np.max(np.abs(a-a.T)) > tolerance or np.max(np.abs(np.diag(a)-1)) > tolerance or np.max(np.abs(a)) > 1+tolerance:
        raise ValueError('correlation must be symmetric, unit diagonal and in [-1,1]')
    lower = np.zeros_like(a)
    for i in range(dimension):
        for j in range(i+1):
            residual = float(a[i, j]-np.dot(lower[i, :j], lower[j, :j]))
            if i == j:
                if residual < -tolerance:
                    raise ValueError('correlation is not positive semidefinite')
                lower[i, j] = math.sqrt(max(0.0, residual))
            elif lower[j, j] > tolerance:
                lower[i, j] = residual/lower[j, j]
            elif abs(residual) > tolerance:
                raise ValueError('singular correlation has inconsistent covariance')
    if np.max(np.abs(lower@lower.T-a)) > 8*tolerance:
        raise ValueError('correlation factor residual exceeds floating-point tolerance')
    return lower


def marginal(factor):
    law = factor.get('law')
    exact(law, ('kind', 'parameters'), 'factor law')
    p = law['parameters']
    if law['kind'] == 'uniform':
        exact(p, ('lower', 'upper'), 'uniform law')
        low, high = real(p['lower'], 'uniform lower'), real(p['upper'], 'uniform upper')
        if low >= high or not finite(high-low):
            raise ValueError('uniform law requires finite positive span')
        return 'uniform', (low, high)
    if law['kind'] == 'normal':
        exact(p, ('mean', 'std'), 'normal law')
        mean, std = real(p['mean'], 'normal mean'), real(p['std'], 'normal std')
        if std <= 0:
            raise ValueError('normal standard deviation must be positive')
        return 'normal', (mean, std)
    raise ValueError('supported continuous marginal laws are uniform and normal')


def uncertainty_settings(method, factors, settings, budget=None):
    bounds = limits(budget)
    if method not in UNCERTAINTY_METHODS:
        raise ValueError('unsupported uncertainty method')
    integer(len(factors), 1, bounds['max_factors'], 'factors')
    exact(settings, ('seed', 'samples', 'correlation', 'correlation_space', 'rng', 'unsafe_draw_policy'), 'uncertainty settings')
    integer(settings['seed'], 0, 2**32-1, 'seed')
    n = integer(settings['samples'], 2, bounds['max_points'], 'fixed sample count')
    if n*len(factors) > bounds['max_matrix_cells'] or n*len(factors) > bounds['max_work_items']:
        raise ValueError('uncertainty design exceeds declared matrix/work budget')
    if settings['rng'] != 'PCG64' or settings['unsafe_draw_policy'] != 'block_preserve_all':
        raise ValueError('PCG64 and block_preserve_all are required; no clipping/resampling')
    laws = [marginal(f) for f in factors]
    if method == 'independent_mc':
        if settings['correlation'] is not None or settings['correlation_space'] != 'independent':
            raise ValueError('independent MC must not contain a correlation matrix')
        lower = None
    else:
        expected = 'physical_normal' if method == 'gaussian_joint_mc' else 'latent_gaussian'
        if settings['correlation_space'] != expected:
            raise ValueError('correlation interpretation differs from declared method')
        if method == 'gaussian_joint_mc' and any(kind != 'normal' for kind, _ in laws):
            raise ValueError('Gaussian joint sampling requires all normal marginals')
        lower = correlation_factor(settings['correlation'], len(factors))
    return n, laws, lower


def generate_uncertainty_design(method, factors, settings, *, budget=None):
    n, laws, lower = uncertainty_settings(method, factors, settings, budget)
    rng = np.random.Generator(np.random.PCG64(settings['seed']))
    # One fixed row-major latent block is generated. It is never extended after
    # observing values or native responses.
    if lower is None:
        uniforms = rng.random((n, len(factors)))
        normals = None
    else:
        normals = rng.standard_normal((n, len(factors)))@lower.T
        uniforms = norm.cdf(normals)
    covariance=None if lower is None else lower@lower.T
    correlation_diagnostics=None if lower is None else {
        'requested_matrix': [list(row) for row in settings['correlation']],
        'factor': lower.tolist(), 'effective_matrix': covariance.tolist(),
        'maximum_absolute_residual': float(np.max(np.abs(covariance-np.asarray(settings['correlation'],dtype=float)))),
        'machine_residual_limit': float(8*128*np.finfo(float).eps*max(1,len(factors))),
        'interpretation': settings['correlation_space'],
        'physical_pearson_correlation_asserted': method=='gaussian_joint_mc'}
    rows, unsafe = [], []
    for index in range(n):
        values = []
        for column, (kind, p) in enumerate(laws):
            if kind == 'uniform':
                value = p[0]+(p[1]-p[0])*float(uniforms[index, column])
            else:
                z = float(normals[index, column]) if normals is not None else float(norm.ppf(uniforms[index, column]))
                value = p[0]+p[1]*z
            value = real(value, 'sampled physical value')
            values.append(value)
            domain = factors[column]['domain']
            if not real(domain['lower'], 'domain lower') <= value <= real(domain['upper'], 'domain upper'):
                unsafe.append({'point_id': f'draw_{index+1:06d}', 'factor_id': factors[column]['id'], 'value': value,
                               'domain': dict(domain)})
        rows.append({'id': f'draw_{index+1:06d}', 'values': values,
                     'role': {'kind': 'iid_draw', 'draw': index+1}, 'weight': None})
    return {'schema_version': 1, 'method': method, 'factor_ids': [f['id'] for f in factors], 'rows': rows,
            'metadata': {'rng': 'PCG64', 'seed': settings['seed'], 'fixed_n': n,
                         'iid_rows': True, 'correlation_space': settings['correlation_space'],
                         'correlation_diagnostics': correlation_diagnostics,
                         'unsafe_draws': unsafe, 'execution_safe': not unsafe,
                         'law_scope': 'reviewed mathematical input law; no physical distribution validation'}}


def validate_uncertainty_design(design, method, factors, settings, *, budget=None):
    expected = generate_uncertainty_design(method, factors, settings, budget=budget)
    if not typed_equal(design, expected):
        raise ValueError('uncertainty design differs from complete seed/law/order replay')
    return expected


def inference_settings(value):
    fields = ('confidence', 'family_size', 'quantiles', 'event', 'coverage', 'mean')
    exact(value, fields, 'uncertainty inference')
    confidence = real(value['confidence'], 'confidence')
    if not 0 < confidence < 1:
        raise ValueError('confidence must lie strictly between zero and one')
    integer(value['family_size'], 1, 1024, 'predeclared interval family size')
    if not isinstance(value['quantiles'], list) or len(value['quantiles']) > 64 or len(set(value['quantiles'])) != len(value['quantiles']):
        raise ValueError('bounded distinct quantile probabilities required')
    if any(not 0 < real(p, 'quantile probability') < 1 for p in value['quantiles']):
        raise ValueError('quantile probabilities must lie in (0,1)')
    for name in ('event', 'coverage'):
        item = value[name]
        if item is None:
            continue
        exact(item, ('lower', 'upper', 'unit'), name)
        if item['lower'] is None and item['upper'] is None:
            raise ValueError(name + ': at least one finite bound required')
        if item['lower'] is not None: real(item['lower'], name+' lower')
        if item['upper'] is not None: real(item['upper'], name+' upper')
        if item['lower'] is not None and item['upper'] is not None and item['lower'] > item['upper']:
            raise ValueError(name + ': reversed bounds')
    mean = value['mean']
    exact(mean, ('method', 'assumption', 'min_samples'), 'mean inference')
    if mean['method'] not in ('none', 'student_t') or mean['assumption'] not in ('none', 'iid_normal_output', 'iid_clt_approximation'):
        raise ValueError('unsupported mean CI method or assumption')
    integer(mean['min_samples'], 2, LIMITS['max_points'], 'mean minimum sample count')
    if (mean['method'] == 'none') != (mean['assumption'] == 'none'):
        raise ValueError('mean CI needs an explicit output distribution/CLT assumption')
    # DKW is one simultaneous CDF band; its derived quantiles count as one
    # family member. Each separate binomial or mean interval adds one.
    required_family = 1+sum(value[k] is not None for k in ('event', 'coverage'))+(mean['method'] != 'none')
    if value['family_size'] < required_family:
        raise ValueError('family_size omits a requested confidence interval')
    return (1-confidence)/value['family_size']


def inverted_empirical(values, probability):
    # p=0/1 are reserved for unknown population tails in DKW inversion.
    return values[max(0, min(len(values)-1, math.ceil(len(values)*probability)-1))]


def binomial_interval(successes, n, alpha):
    lower = 0.0 if successes == 0 else float(beta.ppf(alpha/2, successes, n-successes+1))
    upper = 1.0 if successes == n else float(beta.ppf(1-alpha/2, successes+1, n-successes))
    return {'lower': lower, 'upper': upper, 'method': 'clopper_pearson_equal_tail', 'alpha': alpha}


def validate_uncertainty_inference(method,factors,settings,inference,*,budget=None,metric_unit=None):
    n,_,_=uncertainty_settings(method,factors,settings,budget)
    alpha=inference_settings(inference)
    for name in ('event','coverage'):
        if inference[name] is not None and inference[name]['unit']!=metric_unit:
            raise ValueError(name+': metric unit differs')
    # Conservative sort + grouped ECDF + every requested inversion/proportion.
    work=n*(max(1,len(factors))+math.ceil(math.log2(n))+len(inference['quantiles'])+5)
    if work>limits(budget)['max_work_items']:raise ValueError('complete uncertainty inference work exceeds reviewed budget before execution')
    return alpha


def compute_uncertainty(method, factors, settings, design, responses, *, inference, budget=None, metric_unit=None):
    validate_uncertainty_design(design, method, factors, settings, budget=budget)
    alpha = validate_uncertainty_inference(method,factors,settings,inference,budget=budget,metric_unit=metric_unit)
    ids = [row['id'] for row in design['rows']]
    if not isinstance(responses, dict) or set(responses) != set(ids):
        raise ValueError('all fixed-N draw responses required, with no missing or additional rows')
    ys = [real(responses[key], 'native response') for key in ids]
    if not design['metadata']['execution_safe']:
        raise ValueError('unsafe fixed-N law realization cannot yield a complete native uncertainty result')
    n = len(ys)
    ordered = sorted(ys)
    epsilon = math.sqrt(math.log(2/alpha)/(2*n))
    quantiles = []
    for p in inference['quantiles']:
        lower_p, upper_p = p-epsilon, p+epsilon
        quantiles.append({'probability': p, 'estimate': inverted_empirical(ordered, p),
                          'confidence_interval': {'lower': None if lower_p <= 0 else inverted_empirical(ordered, lower_p),
                                                  'upper': None if upper_p >= 1 else inverted_empirical(ordered, upper_p),
                                                  'lower_tail_unbounded_or_unknown': lower_p <= 0,
                                                  'upper_tail_unbounded_or_unknown': upper_p >= 1,
                                                  'scope': 'population quantile under fixed-N iid response assumption'}})
    proportions = {}
    for name in ('event', 'coverage'):
        rule = inference[name]
        if rule is None:
            proportions[name] = None
            continue
        if rule['unit'] != metric_unit:
            raise ValueError(name + ': metric unit differs')
        indicators = [(rule['lower'] is None or y >= rule['lower']) and (rule['upper'] is None or y <= rule['upper']) for y in ys]
        count = sum(indicators)
        proportions[name] = {'successes': count, 'n': n, 'estimate': count/n,
                             'confidence_interval': binomial_interval(count, n, alpha), 'bounds': dict(rule),
                             'scope': 'mathematical input law event probability; no real-system coverage claim'}
    mean_value = real(math.fsum(ys)/n, 'response mean')
    variance = real(math.fsum((y-mean_value)**2 for y in ys)/(n-1), 'sample variance')
    mean = {'estimate': mean_value, 'sample_variance': variance, 'standard_error': math.sqrt(variance/n),
            'confidence_interval': None, 'assumption': inference['mean']['assumption'], 'defined': True}
    if inference['mean']['method'] == 'student_t':
        if n < inference['mean']['min_samples']:
            mean.update(defined=False, reason='predeclared minimum sample count not met')
        else:
            half = real(float(t.ppf(1-alpha/2, n-1))*math.sqrt(variance/n), 'mean interval half-width')
            mean['confidence_interval'] = {'lower': real(mean_value-half, 'mean CI lower'),
                                           'upper': real(mean_value+half, 'mean CI upper'),
                                           'method': 'student_t', 'alpha': alpha,
                                           'exact_only_if_iid_normal_output': inference['mean']['assumption'] == 'iid_normal_output'}
    ecdf=[];count_le=0
    for y,group in itertools.groupby(ordered):
        count_le+=sum(1 for _ in group)
        ecdf.append({'value':y,'count_le':count_le,'probability':count_le/n})
    return {'method': method, 'complete': True, 'defined': mean['defined'], 'n': n, 'unit': metric_unit,
            'empirical_cdf': ecdf, 'sample_minimum': ordered[0], 'sample_maximum': ordered[-1],
            'quantiles': quantiles, 'dkw': {'epsilon': epsilon, 'alpha': alpha,
                                          'confidence': 1-alpha, 'simultaneous': True,
                                          'assumptions': 'fixed N independent identically distributed rows; measurable fixed response'},
            'proportions': proportions, 'mean': mean, 'degeneracies': ['constant_response'] if variance == 0 else [],
            'scope': 'reviewed hypothetical mathematical input law and recorded numerical metric'}
