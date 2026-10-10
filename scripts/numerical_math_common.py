"""Bounded typed mathematics for recorded numerical evidence; no execution gates.

Interpolation evaluates an explicitly declared reconstruction.  It never adds
an actual sample to a native record or establishes an error bound for a solver.
"""
from __future__ import annotations

import bisect
import math
import re
import sys

from verification_common import finite, typed_equal

DIMENSION_KEYS = ('mass', 'length', 'time', 'current', 'temperature', 'amount', 'luminous_intensity')
MATH_LIMITS = {'max_ast_nodes': 4096, 'max_ast_depth': 32, 'max_evaluations': 2000000,
               'max_checks': 128, 'max_union_knots': 48004}
DEFAULT_MATH_BUDGET = {'max_ast_nodes': 512, 'max_ast_depth': 24, 'max_evaluations': 200000,
                       'max_checks': 32, 'max_union_knots': 36003}
UNARY = {'neg', 'abs', 'sqrt', 'exp', 'log', 'sin', 'cos'}
BINARY = {'add', 'sub', 'mul', 'div', 'min', 'max'}


def number(value, label='number'):
    if not finite(value):
        raise ValueError('non-finite or non-numeric '+label+'; finite real number required, not bool')
    return float(value)


def stable_product(*values, divisor=1.0, label='scaled product'):
    """Multiply finite factors without avoidable intermediate scale overflow."""
    denominator = number(divisor, label+' divisor')
    if denominator == 0:
        raise ValueError(label+' division by zero')
    factors = [number(value, label+' factor') for value in values]
    if any(value == 0 for value in factors):
        return 0.0
    mantissa, exponent = 1.0, 0
    for value in factors:
        part, power = math.frexp(value)
        mantissa *= part
        mantissa, adjustment = math.frexp(mantissa)
        exponent += power+adjustment
    part, power = math.frexp(denominator)
    mantissa /= part
    mantissa, adjustment = math.frexp(mantissa)
    exponent += adjustment-power
    return number(math.ldexp(mantissa, exponent), label)


def dimensions(value):
    if not isinstance(value, dict) or set(value) - set(DIMENSION_KEYS):
        raise ValueError('explicit supported dimension mapping required')
    if any(type(v) is not int or abs(v) > 32 for v in value.values()):
        raise ValueError('dimension exponents must be bounded integers')
    return tuple(value.get(key, 0) for key in DIMENSION_KEYS)


def dimension_map(value):
    return {key: power for key, power in zip(DIMENSION_KEYS, value) if power}


def dimension_add(a, b, sign=1):
    result = tuple(x + sign * y for x, y in zip(a, b))
    if any(abs(x) > 64 for x in result):
        raise ValueError('derived dimension exponent exceeds hard limit')
    return result


TIME_DIMENSION = dimensions({'time': 1})
ZERO_DIMENSION = dimensions({})
UNIT_DIMENSIONS = {
    '1': {}, 'm': {'length': 1}, 'cm': {'length': 1}, 'mm': {'length': 1}, 'km': {'length': 1},
    's': {'time': 1}, 'ms': {'time': 1}, 'min': {'time': 1}, 'h': {'time': 1},
    'kg': {'mass': 1}, 'g': {'mass': 1}, 'K': {'temperature': 1},
    'A': {'current': 1}, 'mol': {'amount': 1}, 'cd': {'luminous_intensity': 1},
    'rad': {}, 'Hz': {'time': -1}, 'N': {'mass': 1, 'length': 1, 'time': -2},
    'Pa': {'mass': 1, 'length': -1, 'time': -2}, 'J': {'mass': 1, 'length': 2, 'time': -2},
    'W': {'mass': 1, 'length': 2, 'time': -3}, 'V': {'mass': 1, 'length': 2, 'time': -3, 'current': -1}}
UNIT_SCALES = {'cm': .01, 'mm': .001, 'km': 1000.0, 'ms': .001, 'min': 60.0, 'h': 3600.0, 'g': .001}


def unit_dimensions(unit):
    """Recognized multiplicative units; unknown labels need a reviewed mapping."""
    if type(unit) is not str or not unit or len(unit) > 128:
        return None
    parts = re.split(r'([*/])', unit)
    result, sign = ZERO_DIMENSION, 1
    for part in parts:
        if part in ('*', '/'):
            sign = 1 if part == '*' else -1
            continue
        match = re.fullmatch(r'(1|[A-Za-z]+)(?:\^(-?\d+))?', part)
        if match is None or match[1] not in UNIT_DIMENSIONS:
            return None
        power = int(match[2] or '1')
        if abs(power) > 32:
            return None
        base = dimensions(UNIT_DIMENSIONS[match[1]])
        result = dimension_add(result, tuple(power*x for x in base), sign)
    return result


def _positive_scale(value, label):
    """An unresolved unit conversion cannot represent an exact zero."""
    if not finite(value) or value <= 0:
        raise ValueError('unresolved '+label+'; strictly positive finite scale required')
    return number(value, label)


def unit_scale(unit):
    if unit_dimensions(unit) is None:
        raise ValueError('unsupported canonical multiplicative unit')
    scale, sign = 1.0, 1
    for part in re.split(r'([*/])', unit):
        if part in ('*', '/'):
            sign = 1 if part == '*' else -1
        else:
            base, exponent = re.fullmatch(r'(1|[A-Za-z]+)(?:\^(-?\d+))?', part).groups()
            factor = _positive_scale(UNIT_SCALES.get(base, 1.0) ** (sign*int(exponent or '1')),
                                     'canonical unit conversion factor')
            scale = _positive_scale(scale*factor, 'canonical unit conversion')
    return _positive_scale(scale, 'canonical unit conversion')


def _canonical_constant(value, unit):
    value = number(value, 'constant')
    result = number(value*unit_scale(unit), 'canonical constant conversion')
    if value != 0 and result == 0:
        raise ValueError('unresolved constant unit conversion; nonzero constant underflowed to zero')
    return result


def observable_scale(symbol):
    if 'canonical_unit' not in symbol:
        return unit_scale(symbol['unit'])
    canonical = unit_scale(symbol['canonical_unit'])
    declared = _positive_scale(symbol.get('scale', 1), 'reviewed unit conversion')
    if unit_dimensions(symbol['unit']) is not None:
        ratio = _positive_scale(unit_scale(symbol['unit'])/canonical, 'recognized observable unit conversion')
        if declared != ratio:
            raise ValueError('observable scale contradicts recognized physical unit conversion')
    return _positive_scale(declared*canonical, 'canonical observable unit conversion')


class WorkBudget:
    def __init__(self, value=None):
        self.limits = dict(DEFAULT_MATH_BUDGET if value is None else value)
        if set(self.limits) != set(MATH_LIMITS) or any(type(v) is not int or v < 1 or
                v > MATH_LIMITS[k] for k, v in self.limits.items()):
            raise ValueError('exact typed positive bounded mathematical budgets required')
        self.evaluations = 0
        self.nodes = 0

    def charge(self, amount=1):
        self.evaluations += amount
        if self.evaluations > self.limits['max_evaluations']:
            raise ValueError('declared mathematical evaluation budget exhausted')

    def knots(self, values):
        if len(values) > self.limits['max_union_knots']:
            raise ValueError('complete union time axis exceeds mathematical budget')


def rounding_time(time):
    return 64 * sys.float_info.epsilon * max(1, abs(time))


class Series:
    """A finite native axis and its declared PWL or held reconstruction."""
    def __init__(self, time, values, *, interpolation='linear', max_samples=12001,
                 max_gap=None, window=None):
        if not isinstance(time, list) or not isinstance(values, list) or len(time) != len(values) or not 2 <= len(time) <= max_samples:
            raise ValueError('complete bounded native time/value arrays required')
        self.time = [number(t, 'sample time') for t in time]
        self.values = [number(y, 'sample value') for y in values]
        self.native_time, self.native_values = list(time), list(values)
        if any(a >= b for a, b in zip(self.time, self.time[1:])):
            raise ValueError('native times must be strictly ordered without duplicates')
        if interpolation not in ('linear', 'zoh'):
            raise ValueError('unsupported reconstruction interpolation')
        self.interpolation = interpolation
        if max_gap is not None:
            gap = number(max_gap, 'maximum observation gap')
            if gap <= 0 or any(b-a > gap + rounding_time(b) for a, b in zip(self.time, self.time[1:])):
                raise ValueError('native observation gap exceeds prior maximum')
        if window is not None:
            start, stop = checked_window(window)
            if self.time[0] > start + rounding_time(start) or self.time[-1] < stop - rounding_time(stop):
                raise ValueError('native observation does not cover declared interval')
            # Canonicalize only endpoint representation roundoff.  Original
            # arrays remain in the native artifact and are never overwritten.
            if abs(self.time[0]-start) <= rounding_time(start):
                self.time[0] = start
            if abs(self.time[-1]-stop) <= rounding_time(stop):
                self.time[-1] = stop
            if any(a >= b for a, b in zip(self.time, self.time[1:])):
                raise ValueError('endpoint roundoff normalization made time ambiguous')

    def at(self, time):
        time = number(time, 'evaluation time')
        if time < self.time[0] or time > self.time[-1]:
            raise ValueError('reconstruction cannot extrapolate missing coverage')
        index = bisect.bisect_right(self.time, time) - 1
        if index == len(self.time)-1 or self.time[index] == time or self.interpolation == 'zoh':
            return self.values[index]
        fraction = (time-self.time[index])/(self.time[index+1]-self.time[index])
        result = (1-fraction)*self.values[index] + fraction*self.values[index+1]
        return number(result, 'reconstructed value')

    def derivative(self, time, scheme='central'):
        if scheme not in ('central', 'forward', 'backward'):
            raise ValueError('explicit finite-difference scheme required')
        if self.interpolation != 'linear':
            raise ValueError('derivative of discontinuous held observations is undefined')
        self.at(time)
        index = bisect.bisect_left(self.time, time)
        if index == len(self.time) or self.time[index] != time:
            index -= 1
            return number((self.values[index+1]-self.values[index])/(self.time[index+1]-self.time[index]), 'PWL slope')
        if scheme == 'forward' and index == len(self.time)-1 or scheme == 'backward' and index == 0:
            raise ValueError('requested one-sided finite-difference stencil is missing at endpoint')
        if index == 0 or scheme == 'forward' and index < len(self.time)-1:
            return number((self.values[index+1]-self.values[index])/(self.time[index+1]-self.time[index]), 'forward slope')
        if index == len(self.time)-1 or scheme == 'backward':
            return number((self.values[index]-self.values[index-1])/(self.time[index]-self.time[index-1]), 'backward slope')
        left, right = self.time[index]-self.time[index-1], self.time[index+1]-self.time[index]
        a = (self.values[index]-self.values[index-1])/left
        b = (self.values[index+1]-self.values[index])/right
        return number((right*a + left*b)/(left+right), 'nonuniform central slope')

    def clipped(self, window):
        start, stop = checked_window(window)
        self.at(start)
        self.at(stop)
        times = [start, *(t for t in self.time if start < t < stop), stop]
        return times, [self.at(t) for t in times]

    def integral(self, window, statistic='integral'):
        times, values = self.clipped(window)
        pieces = []
        for a, b, y0, y1 in zip(times, times[1:], values, values[1:]):
            dt = b-a
            if self.interpolation == 'zoh':
                y1 = y0
            scale = max(abs(y0), abs(y1))
            if statistic == 'integral':
                coefficient = 0.0 if scale == 0 else (y0/scale+y1/scale)/2
                area = stable_product(dt, scale, coefficient, label='signed PWL segment integral')
            elif statistic == 'squared_integral':
                if scale == 0:
                    area = 0.0
                else:
                    left, right = y0/scale, y1/scale
                    coefficient = (left*left+left*right+right*right)/3
                    area = stable_product(dt, scale, scale, coefficient, label='squared PWL segment integral')
            elif statistic == 'absolute_integral':
                if y0 == 0 or y1 == 0 or (y0 > 0) == (y1 > 0):
                    coefficient = 0.0 if scale == 0 else (abs(y0)/scale+abs(y1)/scale)/2
                    area = stable_product(dt, scale, coefficient, label='absolute PWL segment integral')
                else:
                    if abs(y0) >= abs(y1):
                        fraction = 1/(1+abs(y1)/abs(y0))
                    else:
                        ratio = abs(y0)/abs(y1)
                        fraction = ratio/(1+ratio)
                    coefficient = (abs(y0)/scale*fraction + abs(y1)/scale*(1-fraction))/2
                    area = stable_product(dt, scale, coefficient, label='crossing absolute PWL segment integral')
            else:
                raise ValueError('unsupported PWL integral statistic')
            pieces.append(number(area, 'PWL segment integral'))
        return number(math.fsum(pieces), 'PWL integral')


def checked_window(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError('explicit two-time interval required')
    start, stop = (number(x, 'interval endpoint') for x in value)
    if start >= stop or not finite(stop-start):
        raise ValueError('finite positive interval required')
    return start, stop


def union_knots(series, window, budget):
    start, stop = checked_window(window)
    unique = {start, stop}
    for item in series:
        budget.charge(len(item.time))
        for time in item.time:
            if start < time < stop:
                unique.add(time)
                if len(unique) > budget.limits['max_union_knots']:
                    raise ValueError('complete union time axis exceeds mathematical budget')
    result = sorted(unique)
    budget.knots(result)
    return result


def validate_expression(expression, symbols, budget, *, _active=None, _depth=0):
    if not isinstance(expression, dict) or _depth > budget.limits['max_ast_depth']:
        raise ValueError('bounded typed expression object required')
    active = set() if _active is None else _active
    if id(expression) in active:
        raise ValueError('cyclic expression is forbidden')
    active.add(id(expression))
    budget.nodes += 1
    if budget.nodes > budget.limits['max_ast_nodes']:
        raise ValueError('declared expression node budget exhausted')
    try:
        op = expression.get('op')
        if op == 'constant':
            if set(expression) != {'op', 'value', 'unit', 'dimensions'} or not isinstance(expression['unit'], str):
                raise ValueError('constant requires exact value, unit and dimensions')
            number(expression['value'], 'constant')
            dim = dimensions(expression['dimensions'])
            if unit_dimensions(expression['unit']) != dim:
                raise ValueError('constant unit does not match its dimensions or supported unit grammar')
            _canonical_constant(expression['value'], expression['unit'])
            return dim
        if op in ('variable', 'derivative', 'integral'):
            expected = {'op', 'id'} | ({'scheme'} if op == 'derivative' else {'start'} if op == 'integral' else set())
            if set(expression) != expected or expression['id'] not in symbols:
                raise ValueError('expression references undeclared observable or wrong fields')
            dim = dimensions(symbols[expression['id']]['dimensions'])
            if op == 'derivative':
                if expression['scheme'] not in ('central', 'forward', 'backward'):
                    raise ValueError('unsupported finite-difference derivative scheme')
                return dimension_add(dim, TIME_DIMENSION, -1)
            if op == 'integral':
                number(expression['start'], 'integral start')
                return dimension_add(dim, TIME_DIMENSION)
            return dim
        if op not in UNARY | BINARY | {'pow'}:
            raise ValueError('unsupported expression operation; arbitrary code is forbidden')
        if set(expression) != ({'op', 'args', 'exponent'} if op == 'pow' else {'op', 'args'}):
            raise ValueError('expression exact fields differ')
        args = expression['args']
        if not isinstance(args, list) or len(args) != (2 if op in BINARY else 1):
            raise ValueError('expression arity differs')
        dims = [validate_expression(a, symbols, budget, _active=active, _depth=_depth+1) for a in args]
        if op in ('add', 'sub', 'min', 'max'):
            if dims[0] != dims[1]:
                raise ValueError('addition/comparison dimensions differ')
            return dims[0]
        if op in ('mul', 'div'):
            return dimension_add(dims[0], dims[1], 1 if op == 'mul' else -1)
        if op == 'pow':
            power = expression['exponent']
            if type(power) is not int or not -16 <= power <= 16:
                raise ValueError('bounded integer power required')
            return dimensions(dimension_map(tuple(power*x for x in dims[0])))
        if op == 'sqrt':
            if any(x % 2 for x in dims[0]):
                raise ValueError('sqrt dimensions require even powers')
            return tuple(x//2 for x in dims[0])
        if op in ('exp', 'log', 'sin', 'cos') and dims[0] != ZERO_DIMENSION:
            raise ValueError('transcendental argument must be dimensionless')
        return dims[0]
    finally:
        active.remove(id(expression))


def evaluate_expression(expression, environment, time, budget):
    budget.charge()
    op = expression['op']
    if op == 'constant':
        result = _canonical_constant(expression['value'], expression['unit'])
    elif op in ('variable', 'derivative', 'integral'):
        entry = environment[expression['id']]
        if op == 'variable':
            result = entry['at'](time)
        elif 'series' not in entry:
            if op == 'derivative':
                result = 1 if entry.get('time') else 0
            else:
                start = number(expression['start'])
                if start > time or start < entry['window'][0]:
                    raise ValueError('integral start follows evaluation time')
                result = stable_product(time/2+start/2, time-start, label='time integral') if entry.get('time') else stable_product(entry['at'](time), time-start, label='constant integral')
        elif op == 'derivative':
            result = entry['series'].derivative(time, expression['scheme']) * entry['scale']
        else:
            start = number(expression['start'])
            budget.charge(len(entry['series'].time))
            result = 0 if start == time else entry['series'].integral([start, time]) * entry['scale'] + entry.get('offset', 0)*(time-start)
    else:
        args = [evaluate_expression(a, environment, time, budget) for a in expression['args']]
        if op == 'add': result = args[0]+args[1]
        elif op == 'sub': result = args[0]-args[1]
        elif op == 'mul': result = args[0]*args[1]
        elif op == 'div':
            if args[1] == 0: raise ValueError('expression division by zero')
            result = args[0]/args[1]
        elif op == 'pow': result = args[0] ** expression['exponent']
        elif op == 'neg': result = -args[0]
        elif op == 'abs': result = abs(args[0])
        elif op == 'min': result = min(args)
        elif op == 'max': result = max(args)
        elif op == 'sqrt': result = math.sqrt(args[0])
        elif op == 'exp': result = math.exp(args[0])
        elif op == 'log': result = math.log(args[0])
        elif op == 'sin': result = math.sin(args[0])
        elif op == 'cos': result = math.cos(args[0])
        else: raise ValueError('unsupported expression operation')
    return number(result, 'expression result')


def level_environment(level, observables, budget, *, max_samples=12001, max_gap=None):
    spec = level['run_spec']
    window = [spec['start_time'], spec['stop_time']]
    environment, all_series = {}, []
    for symbol in observables:
        scale = observable_scale(symbol)
        offset = number(symbol.get('offset', 0), 'observable canonical offset') * unit_scale(symbol.get('canonical_unit', symbol['unit']))
        if scale <= 0:
            raise ValueError('observable unit scale must be positive')
        kind = symbol['kind']
        if kind == 'time':
            entry = {'at': lambda t, s=scale: t*s, 'time': True, 'window': window}
        elif kind == 'parameter':
            matches = [p for p in spec.get('parameters', []) if p.get('code_name') == symbol['code_name']]
            if len(matches) != 1:
                raise ValueError('approved parameter observable missing or ambiguous')
            item = matches[0]
            if not typed_equal(item.get('unit'), symbol['unit']):
                raise ValueError('parameter observable unit differs')
            value = number(item['value'], 'parameter observable')*scale+offset
            entry = {'at': lambda t, v=value: v, 'window': window}
        else:
            records = level.get('outputs', []) if kind == 'output' else level.get('states', []) if kind == 'state' else spec.get('inputs', [])
            matches = [r for r in records if r.get('variable_id') == symbol['variable_id'] and
                       (kind != 'output' and kind != 'input' or r.get('port') == symbol.get('port')) and
                       (kind != 'state' or r.get('block_path') == symbol.get('block_path'))]
            if len(matches) != 1 or not typed_equal(matches[0].get('unit'), symbol['unit']):
                raise ValueError('actual observable identity/unit missing or ambiguous')
            item = matches[0]
            series = Series(item['time'], item['values'], interpolation=item.get('interpolation', 'linear'),
                            max_samples=max_samples, max_gap=max_gap if kind != 'input' else None, window=window)
            all_series.append(series)
            entry = {'at': lambda t, s=series, k=scale, c=offset: s.at(t)*k+c, 'series': series, 'scale': scale, 'offset': offset}
        environment[symbol['id']] = entry
    budget.knots(union_knots(all_series, window, budget))
    return environment, all_series


def evaluate_metric(metric, level, *, context=None, numeric_policy=None):
    """Compute a source-selected metric; undefined remains explicit, never zero.

    The caller verifies native/approval/source identities before this pure API.
    """
    result = {'defined': False, 'value': None, 'unit': metric.get('unit') if isinstance(metric, dict) else None,
              'scope': 'recorded_pwl_reconstruction', 'errors': [], 'metadata': {}}
    try:
        if not isinstance(metric, dict) or type(metric.get('statistic')) is not str:
            raise ValueError('typed metric definition required')
        allowed = {'id', 'statistic', 'output_port', 'port', 'variable_id', 'kind', 'block_path', 'unit',
                   'window', 'event', 'check', 'event_index', 'reason', 'lower', 'upper'}
        if set(metric) - allowed or 'unit' not in metric:
            raise ValueError('metric exact fields differ')
        if any(type(metric[k]) is not int or metric[k] < 1 for k in ('port', 'output_port') if k in metric):
            raise ValueError('metric root port must be a typed positive integer')
        if 'port' in metric and 'output_port' in metric and metric['port'] != metric['output_port']:
            raise ValueError('metric port aliases disagree')
        policy = numeric_policy or {}
        if numeric_policy is None and metric['statistic'] not in ('final', 'minimum', 'maximum'):
            raise ValueError('new whole-record or derived metric requires a complete numerical policy')
        if numeric_policy is not None:
            assessment = validate_metric_policy(metric, policy, level['run_spec'], context)
            if not assessment['valid']:
                raise ValueError('; '.join(assessment['errors']))
        work = WorkBudget(policy.get('math_budget'))
        statistic = metric['statistic']
        if statistic in ('event_time', 'event_count', 'residual', 'constraint', 'conservation', 'drift'):
            from numerical_obligations import evaluate_check, validate_check, validate_observables
            check = metric.get('event') if statistic.startswith('event_') else metric.get('check')
            if check is None:
                raise ValueError('complete source-selected check definition required for derived metric')
            expected_kind = 'event_localization' if statistic.startswith('event_') else 'numerical_drift' if statistic == 'drift' else statistic
            if not isinstance(check, dict) or check.get('kind') != expected_kind:
                raise ValueError('metric statistic and numerical check kind differ')
            definitions = [c for c in policy.get('checks', []) if c.get('id') == check.get('id')]
            if len(definitions) != 1 or not typed_equal(check, definitions[0]):
                raise ValueError('derived metric must bind a complete current H1 check definition')
            expected_unit = 's' if statistic == 'event_time' else '1' if statistic == 'event_count' else check.get('rate_unit') if statistic == 'drift' else check.get('unit')
            if not typed_equal(metric['unit'], expected_unit) or 'window' in metric and not typed_equal(metric['window'], check['window']):
                raise ValueError('derived metric result unit/window differs from the bound H1 check')
            symbols = validate_observables(policy.get('observables', []), context or {}, [level['run_spec']])
            validate_check(check, symbols, work, context or {})
            entry = evaluate_check(check, level, policy, context or {}, work)
            result['metadata'] = entry
            if not entry['complete']:
                raise ValueError('; '.join(entry['errors']))
            if statistic == 'event_count':
                value = len(entry['events'])
            elif statistic == 'event_time':
                index = metric.get('event_index', 0)
                if type(index) is not int or not 0 <= index < len(entry['events']):
                    raise ValueError('requested event occurrence absent or undefined')
                value = entry['events'][index]['time']
            else:
                value = entry['slope'] if statistic == 'drift' else entry['maximum_violation']
            result.update(defined=True, value=value)
            return result
        records = level.get('states', []) if metric.get('kind') == 'state' else level.get('outputs', [])
        if metric.get('kind') == 'state':
            matches = [r for r in records if r.get('variable_id') == metric.get('variable_id') and r.get('block_path') == metric.get('block_path')]
        else:
            matches = [r for r in records if r.get('port') == metric.get('output_port', metric.get('port'))]
        if len(matches) != 1:
            raise ValueError('metric native output identity missing or ambiguous')
        output = matches[0]
        if 'variable_id' in metric and not typed_equal(metric['variable_id'], output.get('variable_id')):
            raise ValueError('metric variable identity differs from the native observable')
        spec = level['run_spec']
        window = metric.get('window', [spec['start_time'], spec['stop_time']])
        checked_window(window)
        series = Series(output['time'], output['values'], max_samples=policy.get('budget', {}).get('max_samples_per_output', 12001), window=[spec['start_time'], spec['stop_time']])
        times, values = series.clipped(window)
        work.charge(len(times))
        if statistic == 'final':
            if numeric_policy is not None and assessment['scope'] == 'actual_points':
                matches = [i for i, t in enumerate(series.native_time) if abs(t-window[1]) <= rounding_time(window[1])]
                if len(matches) != 1:
                    raise ValueError('final metric requires one actual refined comparison sample')
                value = series.values[matches[0]]
            else:
                value = values[-1]
        elif statistic == 'minimum': value = min(values)
        elif statistic in ('maximum', 'peak'): value = max(values)
        elif statistic == 'peak_time':
            maximum = max(values)
            indices = [i for i, y in enumerate(values) if y == maximum]
            if len(indices) != 1:
                raise ValueError('peak time is nonunique on the complete reconstruction')
            value = times[indices[0]]
        elif statistic in ('integral', 'absolute_integral', 'squared_integral'):
            value = series.integral(window, statistic)
        else:
            raise ValueError('unsupported metric statistic')
        if statistic in ('final', 'minimum', 'maximum', 'peak') and not typed_equal(metric.get('unit'), output.get('unit')):
            raise ValueError('metric/output unit differs')
        if statistic == 'peak_time' and metric.get('unit') != 's':
            raise ValueError('peak time unit must be s')
        if statistic.endswith('integral'):
            expected = (output['unit'] + '*s' if statistic != 'squared_integral' else '('+output['unit']+')^2*s') if isinstance(output.get('unit'), str) else None
            if metric.get('unit') != expected:
                raise ValueError('integral metric unit must explicitly match derived output unit')
        result.update(defined=True, value=number(value, 'metric'), metadata={'window': list(window), 'native_sample_count': len(output['time']), 'evaluated_knot_count': len(times)})
        if statistic in ('minimum', 'maximum') and numeric_policy is not None and assessment['scope'] == 'actual_points':
            result['scope'] = 'recorded_extremum; refinement limited to declared comparison points'
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError, ZeroDivisionError) as error:
        result['errors'].append(str(error))
    return result


def validate_metric_policy(metric, policy, base_spec, context=None):
    """Check a metric's prior policy bindings without invented native arrays."""
    report = {'valid': False, 'scope': None, 'errors': []}
    try:
        from numerical_obligations import policy_scope, validate_check, validate_observables
        allowed = {'id', 'statistic', 'output_port', 'port', 'variable_id', 'kind', 'block_path', 'unit',
                   'window', 'event', 'check', 'event_index', 'reason', 'lower', 'upper'}
        if not isinstance(metric, dict) or set(metric)-allowed or not {'statistic', 'unit'} <= set(metric):
            raise ValueError('metric exact typed fields differ')
        statistic = metric['statistic']
        if type(statistic) is not str:
            raise ValueError('metric statistic must be a typed string')
        if any(type(metric[k]) is not int or metric[k] < 1 for k in ('port', 'output_port') if k in metric) or 'port' in metric and 'output_port' in metric and metric['port'] != metric['output_port']:
            raise ValueError('typed positive unambiguous metric root port required')
        scope = policy_scope(policy)
        report['scope'] = scope
        if 'window' in metric:
            start, stop = checked_window(metric['window'])
            if start < base_spec['start_time'] or stop > base_spec['stop_time']:
                raise ValueError('metric window exceeds the declared complete interval')
        if statistic in ('event_time', 'event_count', 'residual', 'constraint', 'conservation', 'drift'):
            if statistic.startswith('event_') and 'check' in metric or not statistic.startswith('event_') and any(k in metric for k in ('event', 'event_index')):
                raise ValueError('derived metric contains fields for a different statistic')
            check = metric.get('event') if statistic.startswith('event_') else metric.get('check')
            expected = 'event_localization' if statistic.startswith('event_') else 'numerical_drift' if statistic == 'drift' else statistic
            if not isinstance(check, dict) or check.get('kind') != expected:
                raise ValueError('metric statistic and bound check kind differ')
            matching = [c for c in policy.get('checks', []) if c.get('id') == check.get('id')]
            if len(matching) != 1 or not typed_equal(check, matching[0]):
                raise ValueError('metric must bind an exact executed policy check')
            obligation = policy.get('obligations', {}).get(expected, {})
            if obligation.get('status') != 'required' or check['id'] not in obligation.get('check_ids', [c['id'] for c in matching]):
                raise ValueError('derived metric check is not a required executed numerical obligation')
            symbols = validate_observables(policy.get('observables', []), context or {}, [base_spec])
            validate_check(check, symbols, WorkBudget(policy.get('math_budget')), context or {})
            unit = 's' if statistic == 'event_time' else '1' if statistic == 'event_count' else check.get('rate_unit') if statistic == 'drift' else check['unit']
            if metric['unit'] != unit or 'window' in metric and not typed_equal(metric['window'], check['window']):
                raise ValueError('metric derived result unit/window differs')
            if 'event_index' in metric and (type(metric['event_index']) is not int or metric['event_index'] < 0):
                raise ValueError('event occurrence index must be a nonnegative integer')
            if statistic == 'event_time' and (metric.get('event_index', 0) >= check['expected_count'] or check['matching'] == 'first' and metric.get('event_index', 0) != 0):
                raise ValueError('event time occurrence is not covered by the declared event matching scope')
            if any(k in metric for k in ('port', 'output_port', 'kind', 'block_path', 'variable_id')):
                identity = {k: metric[k] for k in ('port', 'output_port', 'kind', 'block_path', 'variable_id') if k in metric}
                identity.update(statistic='final')
                kind = metric.get('kind', 'output')
                candidates = [o for o in policy['outputs'] if o.get('kind', 'output') == kind and
                    (o.get('port') == metric.get('output_port', metric.get('port')) if kind == 'output' else o.get('variable_id') == metric.get('variable_id') and o.get('block_path') == metric.get('block_path'))]
                if len(candidates) != 1:
                    raise ValueError('derived metric output/state identity is not covered by H1 criteria')
                identity['unit'] = candidates[0]['unit']
                covered = validate_metric_policy(identity, policy, base_spec, context)
                if not covered['valid']:
                    raise ValueError('; '.join(covered['errors']))
        else:
            if any(k in metric for k in ('check', 'event', 'event_index')):
                raise ValueError('output statistic contains an unused check/event definition')
            if statistic not in ('final', 'minimum', 'maximum', 'peak', 'peak_time', 'integral', 'absolute_integral', 'squared_integral'):
                raise ValueError('unsupported selected numeric statistic')
            if statistic in ('peak', 'peak_time', 'integral', 'absolute_integral', 'squared_integral') and scope != 'pwl_trajectory':
                raise ValueError('whole-reconstruction metric requires whole-trajectory numerical policy')
            kind = metric.get('kind', 'output')
            if kind not in ('output', 'state'):
                raise ValueError('metric output/state kind differs')
            if kind == 'state':
                covered = [o for o in policy['outputs'] if o.get('kind') == 'state' and o['variable_id'] == metric.get('variable_id') and o['block_path'] == metric.get('block_path')]
                if 'output_port' in metric or 'port' in metric:
                    raise ValueError('state metric must not use a fabricated root port')
            else:
                port = metric.get('output_port', metric.get('port'))
                if type(port) is not int or port < 1 or 'port' in metric and 'output_port' in metric and metric['port'] != metric['output_port']:
                    raise ValueError('typed positive unambiguous metric root port required')
                covered = [o for o in policy['outputs'] if o.get('kind', 'output') == 'output' and o['port'] == port]
                if 'block_path' in metric:
                    actual = [o for o in base_spec['outputs'] if o['port'] == port]
                    if len(actual) != 1 or not typed_equal(metric['block_path'], actual[0].get('block_path')):
                        raise ValueError('metric BlockPath differs from the current physical output binding')
            if len(covered) != 1 or 'variable_id' in metric and covered[0]['variable_id'] != metric['variable_id']:
                raise ValueError('metric is not covered by complete H1 output/state criteria')
            unit = covered[0]['unit']
            if statistic not in ('final', 'minimum', 'maximum') and (type(unit) is not str or not unit):
                raise ValueError('new whole-record metric requires a known source-bound output unit')
            expected = 's' if statistic == 'peak_time' else unit+'*s' if statistic in ('integral', 'absolute_integral') and isinstance(unit, str) else '('+unit+')^2*s' if statistic == 'squared_integral' and isinstance(unit, str) else unit
            if not typed_equal(metric['unit'], expected):
                raise ValueError('selected metric unit differs from its covered output/statistic')
            if statistic == 'final' and scope == 'actual_points':
                endpoint = metric.get('window', [base_spec['start_time'], base_spec['stop_time']])[1]
                if not any(abs(t-endpoint) <= rounding_time(endpoint) for t in policy.get('comparison_times', [])):
                    raise ValueError('final metric endpoint is outside the declared actual refinement points')
        report['valid'] = True
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        report['errors'].append(str(error))
    return report
