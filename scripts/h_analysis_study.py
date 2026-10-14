"""Source-bound analysis design, adaptive replay and native-point assessment.

This module never changes approved physics, project state, or a primary run.
Algorithm results become study evidence only after actual native triplets pass
H1 and the complete frozen design has been independently reconstructed.
"""
from __future__ import annotations

from copy import deepcopy
import itertools
import math
import statistics

from runtime_common import canonical_digest
from uncertainty_metrics import (UNCERTAINTY_METHODS, compute_uncertainty, exact,
                                 generate_uncertainty_design, inference_settings, integer, limits, real)
from verification_common import finite, typed_equal

INPUT_NAME = 'h-analysis-study-input.json'
RESULT_NAME = 'h-analysis-study-result.json'
RECEIPT_NAME = 'h-analysis-study-receipt.json'
OPERATION = 'h.analysis_study'
SENSITIVITY_METHODS = ('local_derivative', 'normalized_sensitivity', 'parameter_oat', 'morris', 'sobol', 'variance_based', 'prcc')
CATALOG_METHODS = ('initial_condition_catalog', 'joint_stress_catalog', 'scenario_response')
GRID_METHODS = ('initial_condition_grid', 'stress_grid')
METHODS = SENSITIVITY_METHODS+UNCERTAINTY_METHODS+CATALOG_METHODS+GRID_METHODS+('failure_boundary', 'runtime_comparison')
SETTINGS_FIELDS = ('base_protocol', 'base_receipt', 'primary_numerical_receipt', 'factors', 'method', 'settings',
                   'design', 'metric', 'numerical_policy', 'inference', 'criterion', 'budget', 'claim_limit')
NATIVE_BUDGET_FIELDS = ('max_file_bytes', 'max_total_bytes', 'max_samples_per_output', 'max_groups',
                        'max_cases', 'process_timeout', 'simulation_timeout')
TIMING_FIELDS = ('InitializationElapsedWallTime', 'ExecutionElapsedWallTime', 'TerminationElapsedWallTime', 'TotalElapsedWallTime')


def design_record(method, factors, rows, metadata):
    return {'schema_version': 1, 'method': method, 'factor_ids': [f['id'] for f in factors], 'rows': rows, 'metadata': metadata}


def factor_values(values, factors, label):
    if not isinstance(values, list) or len(values) != len(factors):
        raise ValueError(label + ': complete ordered factor vector required')
    numbers = [real(v, label) for v in values]
    if any(not f['domain']['lower'] <= v <= f['domain']['upper'] for f, v in zip(factors, numbers)):
        raise ValueError(label + ': value outside reviewed execution domain; no clipping')
    return numbers


def validate_factor_records(factors, budget):
    bounds = limits(budget)
    integer(len(factors), 0, bounds['max_factors'], 'ordered factor count')
    ids, targets = set(), set()
    for f in factors:
        if f['id'] in ids:
            raise ValueError('duplicate study factor id')
        ids.add(f['id'])
        low, high, baseline = real(f['domain']['lower'], 'domain lower'), real(f['domain']['upper'], 'domain upper'), real(f['baseline'], 'factor baseline')
        if low >= high or not finite(high-low) or not low <= baseline <= high:
            raise ValueError('factor domain must have positive finite span containing the exact baseline')
        loc = f['locator']
        kind = f['kind']
        if kind == 'parameter':
            if not loc['code_name'] or any(loc[k] is not None for k in ('block_path', 'input_port', 'state_selector')) or f['waveform'] is not None:
                raise ValueError('parameter factor requires only a registered code_name locator')
            key = kind, loc['code_name']
        elif kind == 'initial_condition':
            if not loc['block_path'] or loc['code_name'] is not None or loc['input_port'] is not None or f['waveform'] is not None:
                raise ValueError('initial condition requires an exact existing Integrator block path')
            key = kind, loc['block_path']
        elif kind == 'external_input':
            if type(loc['input_port']) is not int or loc['input_port'] < 1 or loc['code_name'] is not None or loc['state_selector'] is not None or f['waveform'] is None:
                raise ValueError('input factor requires one existing root-input port and continuous waveform')
            key = kind, loc['input_port']
            wave = f['waveform']
            if len(wave['time']) != len(wave['baseline_values']) or any(not finite(x) for x in wave['time']+wave['baseline_values']) or any(a >= b for a,b in zip(wave['time'],wave['time'][1:])):
                raise ValueError('complete strictly ordered finite waveform required')
        else:
            raise ValueError('unsupported hypothetical factor kind')
        if key in targets:
            raise ValueError('two factors overwrite the same native physical target')
        targets.add(key)
        if any(not finite(x) or not low <= x <= high for x in f['levels']) or len(set(f['levels'])) != len(f['levels']):
            raise ValueError('factor levels must be finite, distinct and inside domain')
        if f['probabilities'] is not None and (len(f['probabilities']) != len(f['levels']) or any(not finite(p) or p < 0 for p in f['probabilities']) or math.fsum(f['probabilities']) != 1.0):
            raise ValueError('finite-level probabilities must be nonnegative, complete and sum exactly to one')


def boundary_settings(factors, settings, budget):
    exact(settings, ('factor_id','brackets','pass_rule','x_tolerance','response_tolerance','max_evaluations','monotonicity','search_scope'), 'boundary settings')
    if settings['search_scope'] != 'local_brackets' or settings['factor_id'] not in {f['id'] for f in factors}:
        raise ValueError('boundary search requires a declared single factor and local bracket scope')
    if not isinstance(settings['brackets'], list) or not 1 <= len(settings['brackets']) <= 16:
        raise ValueError('one to sixteen reviewed local brackets required')
    index = [f['id'] for f in factors].index(settings['factor_id'])
    domain = factors[index]['domain']
    ids = set()
    for bracket in settings['brackets']:
        exact(bracket, ('id','lower','upper','lower_class','upper_class'), 'boundary bracket')
        a,b=real(bracket['lower'],'bracket lower'),real(bracket['upper'],'bracket upper')
        if bracket['id'] in ids or not domain['lower'] <= a < b <= domain['upper']:
            raise ValueError('unique positive in-domain boundary bracket required')
        ids.add(bracket['id'])
        if bracket['lower_class'] not in ('pass','fail') or bracket['upper_class'] not in ('pass','fail') or bracket['lower_class'] == bracket['upper_class']:
            raise ValueError('reviewed bracket must declare opposite endpoint classes')
    rule=settings['pass_rule'];exact(rule,('direction','threshold','guard'),'boundary pass rule')
    if rule['direction'] not in ('at_most','at_least') or real(rule['guard'],'classification guard') < 0:
        raise ValueError('boundary comparison requires explicit direction and nonnegative guard')
    real(rule['threshold'],'boundary threshold')
    if real(settings['x_tolerance'],'x tolerance') <= 0 or real(settings['response_tolerance'],'response tolerance') < 0:
        raise ValueError('positive x tolerance and nonnegative response tolerance required')
    maximum=integer(settings['max_evaluations'],2*len(ids),budget['max_points'],'boundary evaluations')
    if maximum*maximum*max(1,math.ceil(math.log2(maximum)))>budget['max_work_items']:
        raise ValueError('complete adaptive boundary replay work exceeds reviewed budget before native allocation')
    if maximum > budget['max_groups'] or 3*maximum > budget['max_cases'] or maximum > budget['max_iterations']:
        raise ValueError('boundary maximum evaluations exceed complete native triplet budget')
    mono=settings['monotonicity'];exact(mono,('claim','direction','source_ids','rationale'),'monotonicity')
    if mono['claim'] == 'none':
        if mono['direction'] is not None:
            raise ValueError('no monotonicity claim must leave direction null')
    elif mono['claim'] == 'reviewed_monotonic':
        if mono['direction'] not in ('increasing','decreasing') or not mono['source_ids'] or not mono['rationale'].strip():
            raise ValueError('conditional monotonic uniqueness requires explicit supporting sources and direction')
    else:
        raise ValueError('unsupported monotonicity claim')
    return index


def runtime_settings(factors, settings, budget):
    exact(settings,('configurations','repetitions','order','comparison','metric_comparison'),'runtime settings')
    configurations=settings['configurations']
    if not isinstance(configurations,list) or not 2 <= len(configurations) <= 8:
        raise ValueError('two to eight declared numerical configurations required')
    ids=[]
    for config in configurations:
        exact(config,('id','numerical_policy'),'runtime configuration')
        if config['id'] in ids:raise ValueError('duplicate runtime configuration')
        ids.append(config['id'])
    n=integer(settings['repetitions'],2,128,'runtime repetitions')
    order=settings['order']
    if not isinstance(order,list) or len(order) != n*len(ids) or any(order.count(i)!=n for i in ids) or any(i not in ids for i in order):
        raise ValueError('complete prior execution order with exactly declared repetitions required')
    comparison=settings['comparison'];exact(comparison,('reference','alternatives','timing_field','statistic','zero_denominator','level_index'),'runtime comparison')
    if comparison['reference'] not in ids or comparison['alternatives'] != [x for x in ids if x != comparison['reference']] or comparison['timing_field'] not in TIMING_FIELDS or comparison['statistic'] not in ('median','mean') or comparison['zero_denominator'] != 'undefined':
        raise ValueError('runtime comparison fields/order or zero denominator rule invalid')
    integer(comparison['level_index'],0,2,'runtime timing level')
    tolerance=settings['metric_comparison'];exact(tolerance,('absolute_tolerance','relative_tolerance'),'runtime metric comparison')
    if real(tolerance['absolute_tolerance'],'absolute tolerance') <= 0 or real(tolerance['relative_tolerance'],'relative tolerance') < 0:
        raise ValueError('runtime physical metric tolerances invalid')
    if n*n*len(ids)>budget['max_work_items']:
        raise ValueError('complete per-repeat runtime agreement work exceeds reviewed budget before native allocation')
    if len(order)>budget['max_points'] or len(order)>budget['max_groups'] or 3*len(order)>budget['max_cases']:
        raise ValueError('runtime repeated triplets exceed reviewed budget')
    return ids


def generate_design(method, factors, settings, *, budget):
    validate_factor_records(factors,budget)
    if method in SENSITIVITY_METHODS:
        from sensitivity_design import generate_sensitivity_design
        design=generate_sensitivity_design(method,factors,settings,budget=budget)
    elif method in UNCERTAINTY_METHODS:
        design=generate_uncertainty_design(method,factors,settings,budget=budget)
    elif method in CATALOG_METHODS:
        exact(settings,('rows','scope'),'finite catalog settings')
        if settings['scope']!='finite_catalog' or not isinstance(settings['rows'],list) or not settings['rows']:
            raise ValueError('nonempty finite catalog and explicit scope required')
        rows=[];ids=set()
        for source in settings['rows']:
            exact(source,('id','values'),'catalog row')
            if source['id'] in ids:raise ValueError('duplicate catalog occurrence id')
            ids.add(source['id'])
            rows.append({'id':source['id'],'values':factor_values(source['values'],factors,'catalog values'),
                         'role':{'kind':'catalog_scenario','scenario_id':source['id']},'weight':None})
        design=design_record(method,factors,rows,{'scope':'finite_catalog','complete_catalog':True})
    elif method in GRID_METHODS:
        exact(settings,('levels','scope'),'finite grid settings')
        if settings['scope']!='finite_grid' or not isinstance(settings['levels'],dict) or set(settings['levels'])!={f['id'] for f in factors} or not factors:
            raise ValueError('finite grid needs complete factor-level mappings')
        axes=[]
        count=1
        for f in factors:
            axis=settings['levels'][f['id']]
            if not isinstance(axis,list) or not 2<=len(axis)<=16 or len(set(axis))!=len(axis):
                raise ValueError('grid axis must have two to sixteen distinct levels')
            axis=[real(x,'grid level') for x in axis]
            if any(not f['domain']['lower']<=x<=f['domain']['upper'] for x in axis):raise ValueError('grid level leaves domain')
            axes.append(axis);count*=len(axis)
            if count>budget['max_points']:raise ValueError('full Cartesian grid exceeds budget before allocation')
        rows=[{'id':f'grid_{i:06d}','values':list(values),'role':{'kind':'grid_cell','cell':i},'weight':None}
              for i,values in enumerate(itertools.product(*axes),1)]
        design=design_record(method,factors,rows,{'scope':'complete_finite_grid','axes':deepcopy(settings['levels'])})
    elif method=='failure_boundary':
        index=boundary_settings(factors,settings,budget);rows=[]
        for bracket in settings['brackets']:
            for side in ('lower','upper'):
                values=[float(f['baseline']) for f in factors];values[index]=float(bracket[side])
                rows.append({'id':bracket['id']+'_'+side,'values':values,
                             'role':{'kind':'boundary_endpoint','bracket_id':bracket['id'],'side':side,
                                     'expected_class':bracket[side+'_class']},'weight':None})
        design=design_record(method,factors,rows,{'algorithm':'ordered_bracket_bisection_v1','adaptive':True,
                                               'realized_rows_location':'study receipt; deterministic prefix replay',
                                               'scope':'reviewed local transition brackets'})
    elif method=='runtime_comparison':
        runtime_settings(factors,settings,budget);counts={};rows=[]
        for order,identity in enumerate(settings['order'],1):
            counts[identity]=counts.get(identity,0)+1
            rows.append({'id':f'runtime_{order:06d}','values':[float(f['baseline']) for f in factors],
                         'role':{'kind':'runtime_repeat','configuration_id':identity,'repeat':counts[identity],'order':order},'weight':None})
        design=design_record(method,factors,rows,{'scope':'actual native TimingInfo; declared serial order','repetitions':settings['repetitions']})
    else:raise ValueError('unsupported implemented study method')
    n=len(design['rows'])
    if n>budget['max_points'] or n>budget['max_groups'] or 3*n>budget['max_cases'] or n*max(1,len(factors))>budget['max_matrix_cells']:
        raise ValueError('complete frozen study exceeds point/group/case/matrix budget')
    if method.startswith('initial_condition_') and (not factors or any(f['kind']!='initial_condition' for f in factors)):
        raise ValueError('initial-condition study factors must be existing Integrator initial conditions')
    if method=='joint_stress_catalog' and len({f['kind'] for f in factors})<2:
        raise ValueError('joint stress requires factors from at least two physical kinds')
    if method not in UNCERTAINTY_METHODS:
        for row in design['rows']:factor_values(row['values'],factors,'design row')
    if len({r['id'] for r in design['rows']})!=n:raise ValueError('duplicate design point id; repeated physics still needs distinct occurrences')
    return design


def validate_design(design,method,factors,settings,*,budget):
    expected=generate_design(method,factors,settings,budget=budget)
    if not typed_equal(design,expected):raise ValueError('frozen design differs from complete method/settings/seed replay')
    return expected


def materialize_manifest(report,design=None):
    from h_analysis_trial import materialize_trial_manifest
    return materialize_trial_manifest(report,design=design)


def point_policy(report,row):
    if row['role'].get('kind')=='runtime_repeat':
        return next(c['numerical_policy'] for c in report['settings']['configurations'] if c['id']==row['role']['configuration_id'])
    return report['numerical_policy']


def assess_point(report,row,group):
    from numerical_obligations import evaluate_trial_numeric
    from numerical_math_common import evaluate_metric
    if group.get('point_id')!=row['id'] or not typed_equal(group.get('factor_values'),row['values']):
        raise ValueError('actual native group identity/factor row differs')
    policy=point_policy(report,row)
    if not typed_equal(group.get('numeric_policy'),policy):raise ValueError('point numerical policy differs')
    levels=group['levels']
    numeric=evaluate_trial_numeric(levels,policy,group.get('context'),project_id=report['project_id'],physical_sha256=group['physical_sha256'])
    # Null selectors are syntax for not applicable; do not pass them as a
    # requested null window/event occurrence to the metric evaluator.
    metric={k:v for k,v in report['metric'].items() if v is not None}
    value=evaluate_metric(metric,levels[2],context=group.get('context'),numeric_policy=policy)
    accepted=numeric.get('numerically_verified') is True and value.get('defined') is True
    timing=[deepcopy(level.get('timing_info')) for level in levels]
    return {'point_id':row['id'],'factor_values':deepcopy(row['values']),'role':deepcopy(row['role']),
            'physical_sha256':group['physical_sha256'],'numeric':numeric,'metric':value,
            'accepted':accepted,'timing_info':timing}


def boundary_classification(value,settings):
    rule=settings['pass_rule'];value=real(value,'boundary response')
    margin=rule['threshold']-value if rule['direction']=='at_most' else value-rule['threshold']
    if abs(margin)<=settings['response_tolerance']:return 'threshold'
    if margin>rule['guard']:return 'pass'
    if margin < -rule['guard']:return 'fail'
    return 'ambiguous'


def replay_boundary(report,points):
    """Reconstruct the next trial using only the verified prefix, never lookahead."""
    settings,factors,budget=report['settings'],report['factors'],report['budget']
    index=boundary_settings(factors,settings,budget)
    seed=generate_design('failure_boundary',factors,settings,budget=budget)
    rows=deepcopy(seed['rows']);states=[];expected=[];records=[]
    for bracket in settings['brackets']:
        states.append({'bracket_id':bracket['id'],'lower':float(bracket['lower']),'upper':float(bracket['upper']),
                       'lower_class':None,'upper_class':None,'iterations':0,'stop_reason':None})
    if not isinstance(points,list) or len(points)>settings['max_evaluations']:raise ValueError('boundary realized prefix exceeds budget')
    by_id={s['bracket_id']:s for s in states}
    cursor=0
    def consume(row):
        nonlocal cursor
        if cursor>=len(points):return False
        point=points[cursor]
        if point['point_id']!=row['id'] or not typed_equal(point['factor_values'],row['values']) or not typed_equal(point['role'],row['role']):
            raise ValueError('adaptive point differs from exact verified-prefix bisection replay')
        cursor+=1;expected.append(row)
        state=by_id[row['role']['bracket_id']]
        if not point.get('accepted'):
            state['stop_reason']='technical_or_numeric_failure';classification=None
        else:classification=boundary_classification(point['metric']['value'],settings)
        records.append({'point_id':row['id'],'bracket_id':state['bracket_id'],'x':row['values'][index],
                        'response':point['metric']['value'] if point.get('accepted') else None,'classification':classification,
                        'accepted':point.get('accepted') is True})
        mono=settings['monotonicity']
        if mono['claim']=='reviewed_monotonic':
            observed=sorted((r for r in records if r['accepted'] and r['bracket_id']==state['bracket_id']),key=lambda r:r['x'])
            sign=1 if mono['direction']=='increasing' else -1
            if any((a['x']==b['x'] and a['response']!=b['response']) or sign*(b['response']-a['response']) < 0 for a,b in zip(observed,observed[1:])):
                state['stop_reason']='observed_monotonicity_contradiction'
        role=row['role']
        if role['kind']=='boundary_endpoint':
            state[role['side']+'_class']=classification
            if classification != role['expected_class'] and state['stop_reason'] is None:
                state['stop_reason']='endpoint_not_verified_as_reviewed'
        elif state['stop_reason'] is None:
            state['iterations']+=1
            if classification=='threshold':
                state['stop_reason']='response_tolerance_met';state['threshold_point']=row['values'][index]
            elif classification=='ambiguous':state['stop_reason']='classification_guard_ambiguous'
            elif classification==state['lower_class']:
                state['lower']=row['values'][index]
            elif classification==state['upper_class']:
                state['upper']=row['values'][index]
            else:state['stop_reason']='unclassified_response'
        return True
    for row in rows:
        if not consume(row):
            return {'complete':False,'next_row':row,'rows':expected,'brackets':states,'records':records,'stop_reason':'awaiting_endpoint'}
    while True:
        open_state=None
        for state in states:
            if state['stop_reason'] is not None:continue
            if state['lower_class']==state['upper_class'] or {state['lower_class'],state['upper_class']}!={'pass','fail'}:
                state['stop_reason']='no_verified_opposite_bracket';continue
            if state['upper']-state['lower']<=settings['x_tolerance']:
                state['stop_reason']='x_tolerance_met';continue
            open_state=state;break
        if open_state is None:break
        if len(expected)>=settings['max_evaluations']:
            for state in states:
                if state['stop_reason'] is None:state['stop_reason']='evaluation_budget_exhausted'
            break
        a,b=open_state['lower'],open_state['upper'];mid=a+(b-a)/2
        if not a<mid<b:
            open_state['stop_reason']='floating_point_bracket_exhausted';continue
        values=[float(f['baseline']) for f in factors];values[index]=mid
        row={'id':open_state['bracket_id']+f'_bisect_{open_state["iterations"]+1:06d}','values':values,
             'role':{'kind':'boundary_bisection','bracket_id':open_state['bracket_id'],
                     'iteration':open_state['iterations']+1,'prior_lower':a,'prior_upper':b},'weight':None}
        if not consume(row):
            return {'complete':False,'next_row':row,'rows':expected,'brackets':states,'records':records,'stop_reason':'awaiting_bisection'}
    if cursor!=len(points):raise ValueError('unexpected adaptive points after deterministic stop condition')
    complete=all(s['stop_reason'] in ('x_tolerance_met','response_tolerance_met') for s in states)
    for s in states:s['width']=s['upper']-s['lower']
    return {'complete':complete,'next_row':None,'rows':expected,'brackets':states,'records':records,
            'stop_reason':'all_brackets_refined' if complete else 'limited_or_failed',
            'uniqueness':'blocked_by_observed_monotonicity_contradiction' if any(s['stop_reason']=='observed_monotonicity_contradiction' for s in states) else 'conditional_on_reviewed_monotonicity_within_each_bracket' if settings['monotonicity']['claim']=='reviewed_monotonic' else 'no_global_or_unique_boundary_claim',
            'scope':'local observed transition brackets only; no exhaustive continuous-domain search'}


def compute_runtime(settings,points):
    comparison=settings['comparison'];field=comparison['timing_field'];level=comparison['level_index']
    if len(points)!=len(settings['order']) or [p['role'].get('configuration_id') for p in points]!=settings['order']:
        raise ValueError('actual runtime repetitions differ from complete reviewed serial order')
    timing={c['id']:[] for c in settings['configurations']};responses={k:[] for k in timing}
    for point in points:
        identity=point['role']['configuration_id']
        info=point['timing_info'][level]
        if not isinstance(info,dict) or any(not finite(info.get(key)) or info[key]<0 for key in TIMING_FIELDS):
            raise ValueError('actual complete native TimingInfo duration fields required')
        timing[identity].append(float(info[field]));responses[identity].append(real(point['metric']['value'],'runtime response'))
    if any(len(values)!=settings['repetitions'] for values in timing.values()):
        raise ValueError('actual runtime repetition counts differ')
    summarize=statistics.median if comparison['statistic']=='median' else statistics.fmean
    summaries={k:float(summarize(v)) for k,v in timing.items()}
    reference=comparison['reference'];denominator=summaries[reference];ratios=[]
    tolerance=settings['metric_comparison'];agreement=True;repeat_checks=[]
    # Each actual repeat must agree with every reference repeat. Summary
    # cancellation cannot conceal a divergent physical response.
    for identity in timing:
        checks=[]
        for repeat,actual in enumerate(responses[identity],1):
            for reference_repeat,baseline in enumerate(responses[reference],1):
                threshold=tolerance['absolute_tolerance']+tolerance['relative_tolerance']*max(abs(actual),abs(baseline))
                agrees=abs(actual-baseline)<=threshold;agreement &= agrees
                checks.append({'configuration_id':identity,'repeat':repeat,'reference_repeat':reference_repeat,
                               'difference':abs(actual-baseline),'threshold':threshold,'satisfied':agrees})
        repeat_checks.extend(checks)
        if identity in comparison['alternatives']:
            ratios.append({'configuration_id':identity,'reference_id':reference,'ratio':None if denominator==0 else real(summaries[identity]/denominator,'timing ratio'),
                           'defined':denominator!=0,'reason':'zero measured reference duration' if denominator==0 else None,
                           'physical_metric_agreement':all(c['satisfied'] for c in checks),
                           'metric_difference':max(c['difference'] for c in checks),'metric_threshold':min(c['threshold'] for c in checks)})
    return {'method':'runtime_comparison','complete':True,'defined':denominator!=0 and agreement,
            'timing_field':field,'level_index':level,'statistic':comparison['statistic'],'samples':timing,
            'summaries':summaries,'ratios':ratios,'physical_metric_agreement':agreement,'repeat_metric_checks':repeat_checks,
            'degeneracies':(['zero_reference_timing'] if denominator==0 else [])+(['repeat_physical_metric_disagreement'] if not agreement else []),
            'scope':'actual SimulationMetadata TimingInfo in the declared serial repetitions/order; host-specific evidence'}


def compute_analysis(report,points):
    method=report['method'];design=report['design'];ids=[r['id'] for r in design['rows']]
    if method=='failure_boundary':
        replay=replay_boundary(report,points)
        return {'method':method,'factor_id':report['settings']['factor_id'],'complete':replay['complete'],'defined':replay['complete'],**replay}
    if [p['point_id'] for p in points]!=ids or any(not p['accepted'] for p in points):
        return {'method':method,'complete':False,'defined':False,'reason':'missing, unordered, undefined or numerically unverified native points'}
    responses={p['point_id']:real(p['metric']['value'],'accepted metric') for p in points}
    if method in SENSITIVITY_METHODS:
        from sensitivity_metrics import compute_sensitivity
        return compute_sensitivity(method,report['factors'],report['settings'],design,responses,inference=report['inference'],budget=report['budget'],output_unit=report['metric']['unit'])
    if method in UNCERTAINTY_METHODS:
        return compute_uncertainty(method,report['factors'],report['settings'],design,responses,inference=report['inference'],budget=report['budget'],metric_unit=report['metric']['unit'])
    if method=='runtime_comparison':return compute_runtime(report['settings'],points)
    values=list(responses.values())
    maximum=max(values);minimum=min(values)
    return {'method':method,'complete':True,'defined':True,'responses':responses,'minimum':minimum,'maximum':maximum,
            'mean':math.fsum(values)/len(values),'worst_minimum_point_ids':[k for k,v in responses.items() if v==minimum],
            'worst_maximum_point_ids':[k for k,v in responses.items() if v==maximum],
            'scope':'complete declared finite catalog/grid only; no continuous-domain worst-case or probabilistic inference'}


def _selector(selector):
    if not isinstance(selector,list) or not selector or any(type(k) not in (str,int) or type(k) is int and k<0 for k in selector):
        raise ValueError('analysis criterion requires an exact typed result selector')
    return selector


def sensitivity_metric_units(method,factor,metric):
    unit=metric['unit']
    if method in ('local_derivative','parameter_oat','normalized_sensitivity'):
        out={'derivative':unit+'/'+factor['unit'],'coarse_derivative':unit+'/'+factor['unit']}
        if method=='normalized_sensitivity':out['normalized']='1'
        return out
    if method=='morris':return {'mu':unit,'mu_star':unit,'sigma':unit,'physical_mu':unit+'/'+factor['unit']}
    if method in ('sobol','variance_based'):return {'S1':'1','ST':'1'}
    if method=='prcc':return {'PRCC':'1'}
    return {}


def analysis_selector_unit(method,selector,metric,factors,settings,inference):
    """Preflight the complete implemented scalar-result grammar before trials."""
    import json
    q=_selector(selector);unit=metric['unit'];squared='('+unit+')^2'
    def index(value,count):return type(value) is int and 0<=value<count
    if method in SENSITIVITY_METHODS:
        if len(q)==4 and q[0]=='factors' and index(q[1],len(factors)) and q[2]=='metrics':
            out=sensitivity_metric_units(method,factors[q[1]],metric).get(q[3])
            if out is not None:return out
        if len(q)==4 and q[:2]==['bootstrap','intervals'] and q[3] in ('lower','upper') and isinstance(q[2],str) and inference.get('method')=='percentile_bootstrap':
            keys={json.dumps([f['id'],name],separators=(',',':')):u for f in factors for name,u in sensitivity_metric_units(method,f,metric).items()}
            if method=='sobol' and settings['second_order']:
                keys.update({json.dumps(['interaction','S2',a['id'],b['id']],separators=(',',':')):'1' for i,a in enumerate(factors) for b in factors[i+1:]})
            if q[2] in keys:return keys[q[2]]
        if q==['global','variance'] and method in ('sobol','variance_based'):return squared
        if q==['global','pooled_center'] and method=='sobol':return unit
        if q==['global','mean'] and method=='variance_based':return unit
        if method=='variance_based':
            if len(q)==2 and q[0]=='global' and q[1] in ('subset_variance_sum','variance_closure_error'):return squared
            if len(q)==2 and q[0]=='global' and q[1] in ('product_weight_sum','variance_closure_relative_error'):return '1'
            if len(q)==4 and q[:2]==['global','subsets'] and index(q[2],2**len(factors)-1) and q[3] in ('index','variance'):return '1' if q[3]=='index' else squared
        if method=='sobol' and settings['second_order'] and len(q)==4 and q[:2]==['global','second_order'] and index(q[2],len(factors)*(len(factors)-1)//2) and q[3]=='S2':return '1'
    elif method in UNCERTAINTY_METHODS:
        if len(q)==1 and q[0] in ('sample_minimum','sample_maximum'):return unit
        if len(q)==3 and q[0]=='empirical_cdf' and index(q[1],settings['samples']) and q[2] in ('value','count_le','probability'):
            # Cardinality depends on ties. Fixed selectors are not source-ready
            # because a requested later index can disappear after observing y.
            if q[1]==0:return unit if q[2]=='value' else '1'
        if len(q)>=3 and q[0]=='quantiles' and index(q[1],len(inference['quantiles'])):
            if q[2:] in (['estimate'],['confidence_interval','lower'],['confidence_interval','upper']):return unit
            if q[2:]==['probability']:return '1'
        if q[0]=='mean':
            if q[1:] in (['estimate'],['standard_error']):return unit
            if q[1:]==['sample_variance']:return squared
            if inference['mean']['method']=='student_t':
                if q[1:] in (['confidence_interval','lower'],['confidence_interval','upper']):return unit
                if q[1:]==['confidence_interval','alpha']:return '1'
        if len(q)==2 and q[0]=='dkw' and q[1] in ('epsilon','alpha','confidence'):return '1'
        if len(q)>=3 and q[0]=='proportions' and q[1] in ('event','coverage') and inference[q[1]] is not None:
            if q[2:] in (['successes'],['n'],['estimate'],['confidence_interval','lower'],['confidence_interval','upper'],['confidence_interval','alpha']):return '1'
            if q[2:] in (['bounds','lower'],['bounds','upper']) and inference[q[1]][q[-1]] is not None:return unit
    elif method in CATALOG_METHODS+GRID_METHODS:
        if len(q)==1 and q[0] in ('minimum','maximum','mean'):return unit
        if len(q)==2 and q[0]=='responses' and q[1] in {row['id'] for row in generate_design(method,factors,settings,budget={'max_points':2048,'max_groups':2048,'max_cases':8192,'max_matrix_cells':65536,'max_factors':8})['rows']}:return unit
    elif method=='failure_boundary':
        if len(q)==3 and q[0]=='brackets' and index(q[1],len(settings['brackets'])) and q[2] in ('lower','upper','width','threshold_point'):
            return next(f['unit'] for f in factors if f['id']==settings['factor_id'])
    elif method=='runtime_comparison':
        ids=[c['id'] for c in settings['configurations']]
        if len(q)==3 and q[0]=='ratios' and index(q[1],len(settings['comparison']['alternatives'])) and q[2]=='ratio':return '1'
        if len(q)==2 and q[0]=='summaries' and q[1] in ids:return 's'
        if len(q)==3 and q[0]=='samples' and q[1] in ids and index(q[2],settings['repetitions']):return 's'
    raise ValueError('unsupported method-specific analysis selector/path/index')


def selected_analysis_value(analysis,selector,metric,factors):
    q=_selector(selector);value=analysis
    for key in q:
        if isinstance(value,dict) and type(key) is str and key in value:value=value[key]
        elif isinstance(value,list) and type(key) is int and key<len(value):value=value[key]
        elif len(q)==3 and q[0]=='brackets' and q[2]=='threshold_point' and key=='threshold_point' and isinstance(value,dict):value=None
        else:raise ValueError('analysis criterion selector is missing or ambiguous')
    # Native result records carry actual units. Never replace substrings in a
    # legitimate factor unit or infer probability units from a loose prefix.
    unit=None
    if len(q)==4 and q[0]=='factors' and q[2]=='metrics':unit=analysis['factors'][q[1]]['units'].get(q[3])
    elif len(q)==4 and q[:2]==['bootstrap','intervals'] and q[3] in ('lower','upper'):unit=analysis['bootstrap']['intervals'][q[2]].get('unit')
    elif len(q)==4 and q[:2]==['global','subsets'] and q[3] in ('index','variance'):
        item=analysis['global']['subsets'][q[2]];unit=item.get('unit') if q[3]=='index' else item.get('variance_unit')
    elif len(q)==4 and q[:2]==['global','second_order'] and q[3]=='S2':unit=analysis['global']['second_order'][q[2]].get('unit')
    elif q==['global','variance']:unit=analysis['global'].get('variance_unit')
    elif q==['global','mean']:unit=analysis['global'].get('mean_unit')
    elif q in (['global','pooled_center'],):unit=metric['unit']
    elif q in (['global','subset_variance_sum'],['global','variance_closure_error']):unit=analysis['global'].get('variance_unit')
    elif q in (['global','product_weight_sum'],['global','variance_closure_relative_error']):unit='1'
    elif q[0]=='mean':
        if q[1:] in (['estimate'],['standard_error'],['confidence_interval','lower'],['confidence_interval','upper']):unit=metric['unit']
        elif q[1:]==['sample_variance']:unit='('+metric['unit']+')^2'
        elif q[1:]==['confidence_interval','alpha']:unit='1'
        elif len(q)==1:unit=metric['unit']
    elif q[0]=='quantiles':
        if q[2:] in (['estimate'],['confidence_interval','lower'],['confidence_interval','upper']):unit=metric['unit']
        elif q[2:]==['probability']:unit='1'
    elif q[0]=='proportions':
        if q[2:] in (['bounds','lower'],['bounds','upper']):unit=metric['unit']
        elif q[2:] in (['successes'],['n'],['estimate'],['confidence_interval','lower'],['confidence_interval','upper'],['confidence_interval','alpha']):unit='1'
    elif q[0]=='dkw' and len(q)==2 and q[1] in ('epsilon','alpha','confidence'):unit='1'
    elif len(q)==3 and q[0]=='brackets' and q[2] in ('lower','upper','width','threshold_point'):unit=next(f['unit'] for f in factors if f['id']==analysis.get('factor_id'))
    elif len(q)==3 and q[0]=='ratios' and q[2]=='ratio':unit='1'
    elif len(q)==2 and q[0]=='summaries' or len(q)==3 and q[0]=='samples':unit='s'
    elif len(q)==1 and q[0] in ('minimum','maximum','sample_minimum','sample_maximum'):unit=metric['unit']
    elif len(q)==2 and q[0]=='responses':unit=metric['unit']
    elif len(q)==3 and q[0]=='empirical_cdf' and q[2] in ('value','count_le','probability'):unit=metric['unit'] if q[2]=='value' else '1'
    if not isinstance(unit,str) or not unit:raise ValueError('selected analysis quantity has no supported explicit unit mapping')
    if value is not None:real(value,'selected analysis estimator')
    return value,unit


def evaluate_criterion(criterion,analysis,points,metric,factors):
    if not analysis.get('complete') or not analysis.get('defined'):
        return {'defined':False,'satisfied':False,'values':[],'reason':'complete defined method result required'}
    quantity=criterion['quantity']
    if criterion['unit']!=metric['unit'] and quantity not in ('event_probability','coverage_probability','runtime_ratio','analysis_defined','boundary_width','analysis_value'):
        raise ValueError('study criterion metric unit differs')
    if quantity!='analysis_value' and criterion['result_selector'] is not None:raise ValueError('result_selector only applies to analysis_value')
    if quantity=='analysis_value':
        value,unit=selected_analysis_value(analysis,criterion['result_selector'],metric,factors)
        if value is None:return {'defined':False,'satisfied':False,'values':[None],'reason':'selected estimator/interval endpoint undefined'}
        if criterion['unit']!=unit:raise ValueError('selected analysis estimator unit differs')
        values=[value]
    elif quantity=='analysis_defined':
        if criterion['unit']!='1' or criterion['lower'] is not None or criterion['upper'] is not None:raise ValueError('analysis_defined criterion requires dimensionless null bounds')
        return {'defined':True,'satisfied':True,'values':[],'reason':criterion['reason']}
    elif quantity=='all_points':values=[p['metric']['value'] for p in points]
    elif quantity in ('maximum','minimum','mean'):
        raw=[p['metric']['value'] for p in points]
        values=[max(raw) if quantity=='maximum' else min(raw) if quantity=='minimum' else math.fsum(raw)/len(raw)]
    elif quantity in ('event_probability','coverage_probability'):
        key='event' if quantity=='event_probability' else 'coverage';entry=analysis.get('proportions',{}).get(key)
        if criterion['unit']!='1' or entry is None:raise ValueError('probability criterion requires requested event/coverage interval')
        # Acceptance of a population bound uses the complete confidence
        # interval, never the favorable sample proportion alone.
        values=[entry['confidence_interval']['lower'],entry['confidence_interval']['upper']]
    elif quantity=='boundary_width':values=[b['width'] for b in analysis['brackets']]
    elif quantity=='runtime_ratio':
        if criterion['unit']!='1':raise ValueError('runtime ratio criterion must be dimensionless')
        values=[r['ratio'] for r in analysis['ratios']]
    else:raise ValueError('unsupported study criterion quantity')
    if not values or any(not finite(v) for v in values):return {'defined':False,'satisfied':False,'values':values,'reason':'criterion quantity undefined'}
    if criterion['lower'] is None and criterion['upper'] is None:raise ValueError('finite threshold required for criterion')
    satisfied=all((criterion['lower'] is None or v>=criterion['lower']) and (criterion['upper'] is None or v<=criterion['upper']) for v in values)
    return {'defined':True,'satisfied':satisfied,'values':values,'reason':criterion['reason']}


def assess_study(report,points):
    analysis=compute_analysis(report,points)
    criterion=evaluate_criterion(report['criterion'],analysis,points,report['metric'],report['factors'])
    complete=analysis.get('complete') is True and all(p['accepted'] for p in points)
    defined=analysis.get('defined') is True and criterion['defined']
    accepted=complete and defined and criterion['satisfied']
    return {'schema_version':1,'project_id':report['project_id'],'method':report['method'],'metric':report['metric'],
            'study_complete':complete,'study_accepted':accepted,'defined':defined,'points':points,'analysis':analysis,
            'criterion':criterion,'disposition':'accept' if accepted else report['criterion']['failure_disposition'] if complete and defined else 'incomplete',
            'claim_limit':report['claim_limit'],'scope':'reviewed hypothetical numerical study; no adoption, primary approval or real-system validation'}


def validate_h_analysis_study(path,*,project_root=None,require_reviewed=False):
    """Lazy public alias keeps native/consumer imports free of circular gates."""
    from validate_h_analysis_study import validate_h_analysis_study as validate
    return validate(path,project_root=project_root,require_reviewed=require_reviewed)
