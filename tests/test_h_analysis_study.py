"""Method oracles and gate negatives; pure fixtures are not native acceptance."""
from copy import deepcopy
import json
import math
from pathlib import Path

import pytest
import yaml

from h_analysis_study import (assess_study, compute_runtime, design_record, evaluate_criterion, generate_design,
                              replay_boundary, selected_analysis_value, validate_design)
from runtime_common import ROOT
from uncertainty_metrics import (compute_uncertainty, correlation_factor, generate_uncertainty_design,
                                 inference_settings, sample_statistics, validate_uncertainty_design)
from validate_h_analysis_study import validate_h_analysis_study
from validate_h_analysis_study_receipt import validate_h_analysis_study_receipt


def budget():
    return {'max_file_bytes':67108864,'max_total_bytes':1073741824,'max_samples_per_output':12001,
            'max_result_bytes':16777216,'max_groups':2048,'max_cases':8192,'process_timeout':3600,
            'simulation_timeout':120,'total_timeout':14400,'max_iterations':2048,'max_factors':8,
            'max_points':2048,'max_matrix_cells':65536,'max_bootstrap_replicates':1000,'max_work_items':2000000}


def factor(identity='a',kind='parameter',baseline=1.,domain=(-10.,10.),law=None):
    return {'id':identity,'kind':kind,'variable_id':identity,'unit':'1','baseline':baseline,
            'domain':{'lower':domain[0],'upper':domain[1]},'law':law,'levels':[],'probabilities':None,
            'locator':{'code_name':identity if kind=='parameter' else None,'block_path':'m/'+identity if kind=='initial_condition' else None,
                       'input_port':None,'state_selector':[] if kind=='initial_condition' else None},'waveform':None}


def settings(n=64,seed=19,correlation=None,space='independent'):
    return {'seed':seed,'samples':n,'correlation':correlation,'correlation_space':space,'rng':'PCG64','unsafe_draw_policy':'block_preserve_all'}


def inference():
    return {'confidence':.95,'family_size':4,'quantiles':[.01,.5,.99],
            'event':{'lower':None,'upper':.5,'unit':'1'},'coverage':{'lower':0.,'upper':1.,'unit':'1'},
            'mean':{'method':'student_t','assumption':'iid_clt_approximation','min_samples':20}}


def test_uniform_fixed_design_and_distribution_oracle():
    f=[factor(law={'kind':'uniform','parameters':{'lower':0.,'upper':1.}})]
    s=settings(128);d=generate_uncertainty_design('independent_mc',f,s,budget=budget())
    # Exact algorithmic replay plus explicit affine response; no fake receipt.
    validate_uncertainty_design(deepcopy(d),'independent_mc',f,s,budget=budget())
    responses={r['id']:2*r['values'][0]+1 for r in d['rows']}
    result=compute_uncertainty('independent_mc',f,s,d,responses,inference=inference(),budget=budget(),metric_unit='1')
    assert result['n']==128 and result['complete'] and result['defined']
    assert result['mean']['estimate']==pytest.approx(sum(responses.values())/128)
    assert result['mean']['confidence_interval']['exact_only_if_iid_normal_output'] is False
    assert result['quantiles'][0]['confidence_interval']['lower'] is None
    assert result['quantiles'][-1]['confidence_interval']['upper'] is None
    assert result['quantiles'][0]['confidence_interval']['lower_tail_unbounded_or_unknown']
    assert result['proportions']['coverage']['successes']==0
    assert result['proportions']['coverage']['confidence_interval']['lower']==0
    assert 0<result['proportions']['coverage']['confidence_interval']['upper']<1


@pytest.mark.parametrize('rho',[-1.,0.,1.])
def test_joint_normal_singular_and_independent_limits(rho):
    f=[factor('a',law={'kind':'normal','parameters':{'mean':0.,'std':1.}}),factor('b',law={'kind':'normal','parameters':{'mean':0.,'std':2.}})]
    s=settings(32,correlation=[[1.,rho],[rho,1.]],space='physical_normal')
    d=generate_uncertainty_design('gaussian_joint_mc',f,s,budget=budget())
    if abs(rho)==1:
        assert all(r['values'][1]==pytest.approx(2*rho*r['values'][0],abs=1e-14) for r in d['rows'])
    assert d['metadata']['correlation_space']=='physical_normal' and d['metadata']['iid_rows']


def test_mixed_copula_correlation_is_latent_not_observed():
    f=[factor('a',law={'kind':'uniform','parameters':{'lower':0.,'upper':1.}}),factor('b',law={'kind':'normal','parameters':{'mean':0.,'std':1.}})]
    s=settings(32,correlation=[[1.,.7],[.7,1.]],space='latent_gaussian')
    d=generate_uncertainty_design('gaussian_copula_mc',f,s,budget=budget())
    assert d['metadata']['correlation_space']=='latent_gaussian'
    assert all(0<=r['values'][0]<=1 for r in d['rows'])
    bad=deepcopy(s);bad['correlation_space']='physical_normal'
    with pytest.raises(ValueError,match='interpretation'):generate_uncertainty_design('gaussian_copula_mc',f,bad,budget=budget())


@pytest.mark.parametrize('matrix',[[[1.,2.],[2.,1.]],[[1.,.2],[.3,1.]],[[1.,.9,.9],[.9,1.,-.9],[.9,-.9,1.]],[[True,0.],[0.,1.]]])
def test_invalid_covariance_rejected(matrix):
    with pytest.raises(ValueError):correlation_factor(matrix,len(matrix))


def test_normal_tail_preserves_all_fixed_n_draws_and_blocks():
    f=[factor(domain=(-.01,.01),baseline=0.,law={'kind':'normal','parameters':{'mean':0.,'std':1.}})]
    s=settings(32);d=generate_uncertainty_design('independent_mc',f,s,budget=budget())
    assert len(d['rows'])==32 and not d['metadata']['execution_safe'] and d['metadata']['unsafe_draws']
    assert any(abs(r['values'][0])>.01 for r in d['rows'])
    with pytest.raises(ValueError,match='unsafe fixed-N'):compute_uncertainty('independent_mc',f,s,d,{r['id']:r['values'][0] for r in d['rows']},inference=inference(),budget=budget(),metric_unit='1')
    altered=deepcopy(d);altered['rows'][0]['values'][0]=0.
    with pytest.raises(ValueError,match='replay'):validate_uncertainty_design(altered,'independent_mc',f,s,budget=budget())


@pytest.mark.parametrize('change', [{'seed':True},{'samples':True},{'rng':'MT19937'},{'unsafe_draw_policy':'clip'}])
def test_typed_sampling_settings_reject_coercion(change):
    f=[factor(law={'kind':'uniform','parameters':{'lower':0.,'upper':1.}})];s=settings();s.update(change)
    with pytest.raises(ValueError):generate_uncertainty_design('independent_mc',f,s,budget=budget())


def test_mean_ci_requires_output_assumption_and_family_allocation():
    value=inference();value['mean']['assumption']='none'
    with pytest.raises(ValueError,match='output distribution'):inference_settings(value)
    value=inference();value['family_size']=1
    with pytest.raises(ValueError,match='omits'):inference_settings(value)


def boundary_report(*,brackets=None):
    factors=[factor('a',baseline=0.,domain=(-2.,2.))]
    s={'factor_id':'a','brackets':brackets or [{'id':'root','lower':0.,'upper':2.,'lower_class':'pass','upper_class':'fail'}],
       'pass_rule':{'direction':'at_most','threshold':1.,'guard':0.},'x_tolerance':.02,'response_tolerance':0.,
       'max_evaluations':32,'monotonicity':{'claim':'none','direction':None,'source_ids':[],'rationale':'No uniqueness or monotonic assumption.'},'search_scope':'local_brackets'}
    return {'project_id':'synthetic','method':'failure_boundary','factors':factors,'settings':s,'budget':budget(),
            'design':generate_design('failure_boundary',factors,s,budget=budget()),'metric':{'unit':'1'},
            'criterion':{'quantity':'analysis_defined','lower':None,'upper':None,'result_selector':None,'unit':'1','failure_disposition':'modify','reason':'Numerical local transition is defined.'},
            'claim_limit':'SYNTHETIC INFRASTRUCTURE TEST; pure replay oracle only.'}


def replay_with_function(report,function):
    points=[]
    while True:
        replay=replay_boundary(report,points)
        if replay['next_row'] is None:return points,replay
        row=replay['next_row'];value=function(row['values'][0])
        points.append({'point_id':row['id'],'factor_values':row['values'],'role':row['role'],'accepted':True,
                       'metric':{'value':value,'defined':True}})


def test_boundary_bisection_preserves_both_nonmonotone_local_roots():
    report=boundary_report(brackets=[{'id':'negative','lower':-2.,'upper':0.,'lower_class':'fail','upper_class':'pass'},
                                    {'id':'positive','lower':0.,'upper':2.,'lower_class':'pass','upper_class':'fail'}])
    points,replay=replay_with_function(report,lambda x:x*x)
    assert replay['complete'] and len(replay['brackets'])==2
    assert [b['threshold_point'] for b in replay['brackets']]==[-1.,1.]
    assert replay['uniqueness']=='no_global_or_unique_boundary_claim'
    assert len(points)==6 and len({p['point_id'] for p in points})==6


def test_boundary_replays_prefix_and_rejects_arbitrary_new_midpoint():
    report=boundary_report();points,replay=replay_with_function(report,lambda x:x*.7)
    assert replay['complete'] and replay['brackets'][0]['width']<=.02
    tampered=deepcopy(points);tampered[2]['factor_values'][0]=.75
    with pytest.raises(ValueError,match='prefix'):replay_boundary(report,tampered)
    tampered=deepcopy(points);tampered.append(deepcopy(points[-1]))
    with pytest.raises(ValueError):replay_boundary(report,tampered)


def test_boundary_same_sign_actual_endpoints_and_budget_do_not_accept():
    report=boundary_report();_,replay=replay_with_function(report,lambda x:0.)
    assert not replay['complete'] and replay['brackets'][0]['stop_reason']=='endpoint_not_verified_as_reviewed'
    report=boundary_report();report['settings']['max_evaluations']=2
    _,replay=replay_with_function(report,lambda x:x*.7)
    assert not replay['complete'] and replay['brackets'][0]['stop_reason']=='evaluation_budget_exhausted'


def test_finite_ic_grid_is_complete_and_not_continuous_worst_case():
    f=[factor('x',kind='initial_condition',baseline=0.,domain=(-1.,1.)),factor('z',kind='initial_condition',baseline=0.,domain=(-2.,2.))]
    s={'levels':{'x':[-1.,0.,1.],'z':[-2.,2.]},'scope':'finite_grid'}
    d=generate_design('initial_condition_grid',f,s,budget=budget())
    assert len(d['rows'])==6 and d['metadata']['scope']=='complete_finite_grid'
    missing=deepcopy(d);missing['rows'].pop()
    with pytest.raises(ValueError,match='complete'):validate_design(missing,'initial_condition_grid',f,s,budget=budget())


def runtime_fixture(reference_time=1.):
    s={'configurations':[{'id':'coarse','numerical_policy':{}},{'id':'fine','numerical_policy':{}}],
       'repetitions':2,'order':['coarse','fine','fine','coarse'],
       'comparison':{'reference':'coarse','alternatives':['fine'],'timing_field':'TotalElapsedWallTime','statistic':'median','zero_denominator':'undefined','level_index':2},
       'metric_comparison':{'absolute_tolerance':.01,'relative_tolerance':0.}}
    points=[]
    for identity in s['order']:
        duration=reference_time if identity=='coarse' else 2.
        points.append({'role':{'configuration_id':identity},'metric':{'value':1.},'timing_info':[{key:duration for key in ['InitializationElapsedWallTime','ExecutionElapsedWallTime','TerminationElapsedWallTime','TotalElapsedWallTime']} for _ in range(3)]})
    return s,points


def test_actual_timing_ratio_and_zero_denominator_rule():
    s,p=runtime_fixture();result=compute_runtime(s,p)
    assert result['ratios'][0]['ratio']==2. and result['physical_metric_agreement']
    s,p=runtime_fixture(0.);result=compute_runtime(s,p)
    assert not result['defined'] and result['ratios'][0]['ratio'] is None
    s,p=runtime_fixture();p[1]['timing_info'][2]['TotalElapsedWallTime']=True
    with pytest.raises(ValueError,match='actual'):compute_runtime(s,p)


def test_method_specific_estimator_threshold_distinguishes_modify_from_undefined():
    analysis={'complete':True,'defined':True,'factors':[{'factor_id':'a','metrics':{'ST':.7},'units':{'ST':'1'}}]}
    c={'quantity':'analysis_value','result_selector':['factors',0,'metrics','ST'],'lower':None,'upper':.5,'unit':'1','failure_disposition':'modify','reason':'Reviewed sensitivity upper limit.'}
    checked=evaluate_criterion(c,analysis,[],{'unit':'m'},[factor()])
    assert checked['defined'] and not checked['satisfied']
    c['unit']='m'
    with pytest.raises(ValueError,match='unit'):evaluate_criterion(c,analysis,[],{'unit':'m'},[factor()])
    c['unit']='1';analysis['factors'][0]['metrics']['ST']=None
    checked=evaluate_criterion(c,analysis,[],{'unit':'m'},[factor()])
    assert not checked['defined'] and not checked['satisfied']


def test_probability_bound_uses_entire_ci_not_sample_estimate():
    c={'quantity':'event_probability','result_selector':None,'lower':None,'upper':.1,'unit':'1','failure_disposition':'reject','reason':'Prior population event probability limit.'}
    analysis={'complete':True,'defined':True,'proportions':{'event':{'estimate':0.,'confidence_interval':{'lower':0.,'upper':.3}}}}
    checked=evaluate_criterion(c,analysis,[],{'unit':'m'},[])
    assert checked['defined'] and not checked['satisfied'] and checked['values']==[0.,.3]


def test_draft_study_is_read_only_and_cannot_execute(tmp_path):
    value=yaml.safe_load((ROOT/'templates/contracts/h_analysis_study.yaml').read_text());file=tmp_path/'study.yaml';file.write_text(yaml.safe_dump(value))
    before=file.read_bytes();report=validate_h_analysis_study(file,project_root=tmp_path)
    assert report['valid'] and report['schema_valid'] and not report['study_ready'] and not report['execution_allowed']
    assert file.read_bytes()==before and not (tmp_path/'state.yaml').exists()
    required=validate_h_analysis_study(file,project_root=tmp_path,require_reviewed=True)
    assert not required['valid'] and 'current complete reviewed executable H study required' in required['errors']


@pytest.mark.parametrize('value',[True,0,-1,1.5])
def test_study_declared_budget_rejects_untyped_counts_before_dependencies(tmp_path,value):
    contract=yaml.safe_load((ROOT/'templates/contracts/h_analysis_study.yaml').read_text());contract['budget']=budget();contract['budget']['max_cases']=value
    path=tmp_path/'study.yaml';path.write_text(yaml.safe_dump(contract));report=validate_h_analysis_study(path,project_root=tmp_path)
    assert not report['valid'] and not report['study_ready']


def test_cyclic_or_duplicate_structured_source_cannot_form_study(tmp_path):
    file=tmp_path/'study.yaml';file.write_text('schema_version: 1\nschema_version: 1\n')
    report=validate_h_analysis_study(file,project_root=tmp_path)
    assert not report['valid'] and report['errors']


def test_receipt_wrong_filename_and_empty_evidence_never_accepts(tmp_path):
    file=tmp_path/'fake.json';file.write_text('{}')
    report=validate_h_analysis_study_receipt(file,project_root=tmp_path)
    assert not report['valid'] and not report['study_complete'] and not report['study_accepted']
    file=tmp_path/'h-analysis-study-receipt.json';file.write_text('{}')
    report=validate_h_analysis_study_receipt(file,project_root=tmp_path)
    assert not report['valid'] and not report['study_accepted']


def test_runtime_divergent_repetitions_cannot_cancel_in_summary():
    s,points=runtime_fixture()
    points[1]['metric']['value']=.5
    points[2]['metric']['value']=1.5
    result=compute_runtime(s,points)
    assert result['summaries']['fine']==2.
    assert not result['defined'] and not result['physical_metric_agreement']
    assert len([check for check in result['repeat_metric_checks'] if not check['satisfied']])==4
    wrong_order=deepcopy(points);wrong_order[0],wrong_order[1]=wrong_order[1],wrong_order[0]
    with pytest.raises(ValueError,match='serial order'):compute_runtime(s,wrong_order)


def test_boundary_reviewed_monotonicity_contradiction_keeps_observations():
    report=boundary_report()
    report['settings']['monotonicity']={'claim':'reviewed_monotonic','direction':'increasing','source_ids':['proof'],
                                     'rationale':'SYNTHETIC INFRASTRUCTURE TEST; contradiction must block this conditional claim.'}
    # Both endpoint pass/fail classes are correct, but an interior rise then
    # fall contradicts the reviewed monotonicity even while a bracket exists.
    points,result=replay_with_function(report,lambda x:.9 if x==0 else 1.1 if x==2 else 1.5)
    assert not result['complete']
    assert result['uniqueness']=='blocked_by_observed_monotonicity_contradiction'
    assert result['brackets'][0]['stop_reason']=='observed_monotonicity_contradiction'
    assert [row['response'] for row in result['records']]==[.9,1.1,1.5]
    assert len(points)==3


def test_failure_collection_preserves_later_failed_and_unattempted_rows():
    from run_h_analysis_study import collect_batch_points
    rows=[{'id':identity,'values':[1.],'role':{'kind':'catalog_scenario'},'weight':None} for identity in ('first','second','last')]
    report={'metric':{'unit':'m'}}
    native={'valid':True,'errors':['first native error','second native error'],
            'groups':[{'point_id':'first','levels':[],'status':'failed','attempted':True},
                      {'point_id':'second','levels':[],'status':'failed','attempted':True}]}
    points=collect_batch_points(report,{'rows':rows},native)
    assert [p['point_id'] for p in points]==['first','second','last']
    assert [p['status'] for p in points]==['failed','failed','unattempted']
    assert all(not p['accepted'] and p['metric']['value'] is None for p in points)
    bad=deepcopy(native);bad['groups'].append({'point_id':'invented','levels':[]})
    with pytest.raises(ValueError,match='undeclared'):collect_batch_points(report,{'rows':rows},bad)


def test_zero_probability_finite_law_rows_are_preserved_with_exact_sum():
    from h_analysis_study import validate_factor_records
    f=factor();f.update(levels=[0.,1.],probabilities=[0.,1.])
    validate_factor_records([f],budget())
    invalid=deepcopy(f);invalid['probabilities']=[0.,1.-1e-13]
    with pytest.raises(ValueError,match='exactly'):validate_factor_records([invalid],budget())
    invalid=deepcopy(f);invalid['probabilities']=[-1e-14,1.]
    with pytest.raises(ValueError,match='nonnegative'):validate_factor_records([invalid],budget())


def test_correlation_requested_and_effective_law_are_inspectable():
    f=[factor('a',law={'kind':'normal','parameters':{'mean':0.,'std':1.}}),factor('b',law={'kind':'normal','parameters':{'mean':0.,'std':1.}})]
    requested=[[1.,1.],[1.,1.]]
    d=generate_uncertainty_design('gaussian_joint_mc',f,settings(16,correlation=requested,space='physical_normal'),budget=budget())
    diagnostics=d['metadata']['correlation_diagnostics']
    assert diagnostics['requested_matrix']==requested and diagnostics['effective_matrix']==requested
    assert diagnostics['factor']==[[1.,0.],[1.,0.]]
    assert diagnostics['maximum_absolute_residual']==0.
    assert diagnostics['physical_pearson_correlation_asserted']
    altered=deepcopy(d);altered['metadata']['correlation_diagnostics']['effective_matrix'][0][1]=.9
    with pytest.raises(ValueError,match='replay'):validate_uncertainty_design(altered,'gaussian_joint_mc',f,settings(16,correlation=requested,space='physical_normal'),budget=budget())


def test_uncertainty_budget_includes_full_inference_before_native():
    from uncertainty_metrics import validate_uncertainty_inference
    f=[factor(law={'kind':'uniform','parameters':{'lower':0.,'upper':1.}})]
    tight=budget();tight['max_work_items']=128
    with pytest.raises(ValueError,match='before execution'):
        validate_uncertainty_inference('independent_mc',f,settings(128),inference(),budget=tight,metric_unit='1')


@pytest.mark.parametrize('selector,unit',[
    (['mean','confidence_interval','alpha'],'1'),
    (['mean','confidence_interval','lower'],'m'),
    (['mean','sample_variance'],'(m)^2'),
    (['proportions','event','confidence_interval','alpha'],'1'),
    (['proportions','event','bounds','upper'],'m'),
    (['quantiles',1,'confidence_interval','upper'],'m'),
    (['dkw','epsilon'],'1'),
])
def test_full_uncertainty_selector_preflight_has_actual_units(selector,unit):
    from h_analysis_study import analysis_selector_unit
    i=inference();i['event']['unit']='m';i['coverage']['unit']='m'
    assert analysis_selector_unit('independent_mc',selector,{'unit':'m'},[factor()],settings(),i)==unit
    analysis={'mean':{'confidence_interval':{'alpha':.025,'lower':1.},'sample_variance':2.},
              'proportions':{'event':{'confidence_interval':{'alpha':.025},'bounds':{'upper':.5}}},
              'quantiles':[{}, {'confidence_interval':{'upper':3.}}], 'dkw':{'epsilon':.1}}
    assert selected_analysis_value(analysis,selector,{'unit':'m'},[factor()])[1]==unit


def test_selector_preflight_rejects_wrong_method_missing_rule_and_bad_indexes():
    from h_analysis_study import analysis_selector_unit
    f=[factor()]
    for selector in (['quantiles',3,'estimate'],['quantiles',True,'estimate'],['mean','confidence_interval','bogus'],['proportions','event','bounds','lower']):
        with pytest.raises(ValueError,match='selector'):
            analysis_selector_unit('independent_mc',selector,{'unit':'m'},f,settings(),inference())
    with pytest.raises(ValueError,match='selector'):
        analysis_selector_unit('scenario_response',['quantiles',0,'estimate'],{'unit':'m'},f,{'rows':[{'id':'x','values':[1.]}],'scope':'finite_catalog'},{'method':'none'})


def test_sensitivity_global_and_bootstrap_selectors_preserve_units():
    from h_analysis_study import analysis_selector_unit
    f=[factor('a'),factor('b')];f[0]['unit']='output_unit/kg'
    metric={'unit':'m'};inf={'method':'percentile_bootstrap'};sobol={'second_order':True}
    key=json.dumps(['a','physical_mu'],separators=(',',':'))
    cases=[('variance_based',['global','subsets',2,'index'],'1',{},inf),
           ('variance_based',['global','subsets',2,'variance'],'(m)^2',{},inf),
           ('sobol',['global','second_order',0,'S2'],'1',sobol,inf),
           ('morris',['bootstrap','intervals',key,'upper'],'m/output_unit/kg',{},inf)]
    for method,selector,unit,s,i in cases:
        assert analysis_selector_unit(method,selector,metric,f,s,i)==unit
    analysis={'factors':[{'units':{'physical_mu':'m/output_unit/kg'},'metrics':{'physical_mu':2.}}],
              'global':{'subsets':[{}, {}, {'index':.25,'variance':2.,'unit':'1','variance_unit':'(m)^2'}],
                        'second_order':[{'S2':.5,'unit':'1'}]},
              'bootstrap':{'intervals':{key:{'lower':None,'upper':3.,'unit':'m/output_unit/kg'}}}}
    assert selected_analysis_value(analysis,['factors',0,'metrics','physical_mu'],metric,f)==(2.,'m/output_unit/kg')
    for _,selector,unit,_,_ in cases:assert selected_analysis_value(analysis,selector,metric,f)[1]==unit
    with pytest.raises(ValueError,match='selector'):
        analysis_selector_unit('sobol',['global','second_order',1,'S2'],metric,f,sobol,inf)
    with pytest.raises(ValueError,match='selector'):
        analysis_selector_unit('morris',['bootstrap','intervals',key,'lower'],metric,f,{}, {'method':'none'})


def execution_fixture(*,duration=2.,total_timeout=10):
    from datetime import datetime,timedelta,timezone
    from run_h_analysis_study import execution_record
    from runtime_common import canonical_digest
    start=datetime(2026,1,1,tzinfo=timezone.utc)
    stamp=lambda seconds:(start+timedelta(seconds=seconds)).isoformat()
    request={'bindings':{'design':{'rows':['one']}},'groups':[{}],'cases':[{}, {}, {}]}
    raw={'cases':[{'attempted':True},{'attempted':True},{'attempted':False}]}
    child={'process':{'started_at':stamp(.5),'finished_at':stamp(duration-.5),'execution_timeout':total_timeout-.5}}
    native={'valid':True,'trial_complete':True,'errors':[]}
    entry={'index':1,'design_sha256':canonical_digest(request['bindings']['design']),'group_count':1,'case_count':3,'attempted_case_count':2,
           'started_at':stamp(.25),'finished_at':stamp(duration-.25),'elapsed_before':.25,'elapsed_after':duration-.25,
           'process_timeout_limit':total_timeout-.25,'status':'complete','errors':[]}
    receipt={'started_at':stamp(0),'finished_at':stamp(duration),'trial_receipts':[{}],'status':'complete','errors':[],
             'execution':execution_record([entry],stamp(0),stamp(duration))}
    b=budget();b['total_timeout']=total_timeout
    return receipt,b,[(request,raw,child,native)]


def test_actual_parent_child_timing_counts_timeout_and_error_ledger():
    from validate_h_analysis_study_receipt import validate_execution_ledger
    receipt,b,children=execution_fixture()
    assert validate_execution_ledger(receipt,b,children)
    changed=deepcopy(receipt);changed['execution']['attempted_case_count']=3
    with pytest.raises(ValueError,match='count'):validate_execution_ledger(changed,b,children)
    changed=deepcopy(children);changed[0][2]['process']['started_at']='2025-12-31T23:59:59+00:00'
    with pytest.raises(ValueError,match='interval'):validate_execution_ledger(receipt,b,changed)
    changed=deepcopy(children);changed[0][2]['process']['execution_timeout']=10.
    with pytest.raises(ValueError,match='cap'):validate_execution_ledger(receipt,b,changed)
    changed=deepcopy(children);changed[0][3]['errors']=['actual failed case'];changed[0][3]['trial_complete']=False
    with pytest.raises(ValueError,match='status/error'):validate_execution_ledger(receipt,b,changed)


def test_actual_total_timeout_after_completed_batch_never_accepts():
    from validate_h_analysis_study_receipt import validate_execution_ledger
    receipt,b,children=execution_fixture(duration=11.,total_timeout=10)
    with pytest.raises(ValueError,match='incomplete/timed-out'):validate_execution_ledger(receipt,b,children)
    receipt.update(status='incomplete',errors=['declared total study timeout exhausted after native batch'])
    assert not validate_execution_ledger(receipt,b,children)


def test_factor_baseline_uses_exact_selected_D_model_before_code_name():
    from validate_h_analysis_study import factor_baseline
    selected={'code_name':'a','value':1.,'unit':'1','reference':{'design_id':'d','model_id':'selected','variable_id':'a'}}
    foreign={'code_name':'a','value':99.,'unit':'kg','reference':{'design_id':'d','model_id':'foreign','variable_id':'a'}}
    mapping={'mapping_snapshot':{'targets':[{'id':'t','blocks':[],'traces':[]}]},'build_spec':{'blocks':[]},
             'parameter_validation':{'parameters':[selected,foreign]}}
    protocol={'design_id':'d','model_id':'selected','target_id':'t','mapping_validation':mapping,
              'run_spec':{'parameters':[{'code_name':'a','unit':'1','value':1.}],'inputs':[]}}
    factor_baseline([factor()],protocol,{'variables':[{'id':'a','unit':'1','roles':['parameter']}]})
    protocol['mapping_validation']['parameter_validation']['parameters']=[foreign]
    with pytest.raises(ValueError,match='baseline/reference/unit'):
        factor_baseline([factor()],protocol,{'variables':[{'id':'a','unit':'1','roles':['parameter']}]})


def test_initial_condition_source_baseline_resolves_only_registered_literal():
    from validate_h_analysis_study import _initial_value
    params=[{'code_name':'x0','value':.25}]
    assert _initial_value('x0',params)==.25 and _initial_value('0.25',params)==.25
    with pytest.raises(ValueError,match='only'):_initial_value('x0+1',params)
    with pytest.raises(ValueError,match='registered'):_initial_value('missing',params)


def test_runtime_and_adaptive_replay_work_are_preflighted():
    from h_analysis_study import boundary_settings,runtime_settings
    tight=budget();tight['max_work_items']=7
    s,_=runtime_fixture()
    with pytest.raises(ValueError,match='before native allocation'):runtime_settings([],s,tight)
    report=boundary_report()
    tight=budget();tight['max_work_items']=100
    with pytest.raises(ValueError,match='before native allocation'):
        boundary_settings(report['factors'],report['settings'],tight)


# SYNTHETIC INFRASTRUCTURE TEST. These independent closed-form priors test
# arithmetic/criteria; they are not an accepted native or model receipt.
def _uncertainty_response_prior(values, *, mean_method='none'):
    f=[factor(law={'kind':'uniform','parameters':{'lower':0.,'upper':1.}})]
    s=settings(len(values));d=generate_uncertainty_design('independent_mc',f,s,budget=budget())
    i={'confidence':.95,'family_size':2 if mean_method=='student_t' else 1,
       'quantiles':[.5],'event':None,'coverage':None,
       'mean':{'method':mean_method,'assumption':'iid_normal_output' if mean_method=='student_t' else 'none','min_samples':2}}
    responses={row['id']:value for row,value in zip(d['rows'],values)}
    analysis=compute_uncertainty('independent_mc',f,s,d,responses,inference=i,budget=budget(),metric_unit='1')
    return f,s,d,i,analysis


@pytest.mark.parametrize('anchor,reverse',[(0.,False),(0.,True),(1e16,False),(1e16,True)])
def test_uncertainty_offset_variance_has_independent_20_over_3_prior(anchor,reverse):
    values=[anchor+x for x in (0.,2.,4.,6.)]
    if reverse:values.reverse()
    result=sample_statistics(values)
    assert result['defined'] and not result['constant_response']
    # Independent closed form: (-3)^2+(-1)^2+1^2+3^2=20, divisor 3.
    assert result['sample_variance']==pytest.approx(20/3,rel=2e-15)
    assert result['standard_error']==pytest.approx(math.sqrt(5/3),rel=2e-15)
    if anchor:
        assert result['estimate'] is None and not result['estimate_defined']
        assert abs(result['centering']['display_rounding_error'])==1.
        assert result['centering']['display_resolution_guard']<1e-12
        assert 'mean_display_rounding_unresolved' in result['degeneracies']
    else:
        assert result['estimate']==3. and result['estimate_defined']


def test_uncertainty_offset_variance_source_prior_genuinely_rejects():
    f,s,d,i,analysis=_uncertainty_response_prior([1e16+x for x in (0.,2.,4.,6.)])
    criterion={'quantity':'analysis_value','result_selector':['mean','sample_variance'],'lower':7.,'upper':None,
               'unit':'(1)^2','failure_disposition':'reject','reason':'Independent predeclared variance lower bound is seven.'}
    checked=evaluate_criterion(criterion,analysis,[],{'unit':'1'},f)
    assert analysis['complete'] and analysis['defined']
    assert checked['defined'] and not checked['satisfied'] and checked['values']==pytest.approx([20/3])
    # Pure ordered scalar points exercise the actual disposition function.
    # No numerical/native acceptance report is fabricated by this test.
    report={'project_id':'synthetic-arithmetic-prior','method':'independent_mc','factors':f,'settings':s,'design':d,
            'inference':i,'budget':budget(),'metric':{'unit':'1'},'criterion':criterion,
            'claim_limit':'SYNTHETIC INFRASTRUCTURE TEST: pure scalar estimator prior only.'}
    points=[{'point_id':row['id'],'accepted':True,'metric':{'value':1e16+x}}
            for row,x in zip(d['rows'],(0.,2.,4.,6.))]
    assessed=assess_study(report,points)
    assert assessed['study_complete'] and assessed['defined'] and not assessed['study_accepted']
    assert assessed['disposition']=='reject'
    undefined=deepcopy(criterion);undefined['result_selector']=['mean','estimate'];undefined['unit']='1'
    assert not evaluate_criterion(undefined,analysis,[],{'unit':'1'},f)['defined']


def test_uncertainty_large_finite_variance_avoids_intermediate_overflow():
    result=sample_statistics([-9e153,-9e153,9e153,9e153])
    # Independent prior: 4*(9e153)^2/3 = 1.08e308 (finite binary64).
    assert result['defined'] and result['sample_variance']==pytest.approx(1.08e308,rel=2e-15)
    assert result['standard_error']==pytest.approx(math.sqrt(1.08e308)/2,rel=2e-15)
    assert math.isfinite(result['sample_variance'])


@pytest.mark.parametrize('magnitude',[1e-200,1e308])
def test_uncertainty_unresolved_nonzero_variance_cannot_be_constant(magnitude):
    _,_,_,_,result=_uncertainty_response_prior([-magnitude,-magnitude,magnitude,magnitude])
    assert result['complete'] and not result['defined']
    assert result['mean']['sample_variance'] is None and result['mean']['standard_error'] is None
    assert 'constant_response' not in result['degeneracies']
    assert any(code in result['degeneracies'] for code in ('sample_variance_unresolved','sample_centering_unresolved'))
    criterion={'quantity':'analysis_value','result_selector':['mean','sample_variance'],'lower':None,'upper':1.,
               'unit':'(1)^2','failure_disposition':'reject','reason':'Unresolved positive moment may not pass an upper bound.'}
    assert not evaluate_criterion(criterion,result,[],{'unit':'1'},[])['defined']


def test_uncertainty_critical_ci_rounding_is_undefined_without_widening_prior():
    _,_,_,_,result=_uncertainty_response_prior([1e16+x for x in (0.,2.,4.,6.)],mean_method='student_t')
    interval=result['mean']['confidence_interval']
    assert result['complete'] and not result['defined'] and not interval['defined']
    assert interval['lower'] is None and interval['upper'] is None
    assert interval['display_lower'] is not None and interval['display_upper'] is not None
    assert 'mean_confidence_interval_unresolved' in result['degeneracies']
    assert abs(interval['lower_rounding_error'])>interval['lower_resolution_guard'] or abs(interval['upper_rounding_error'])>interval['upper_resolution_guard']


def test_uncertainty_ordinary_rounding_and_genuine_constants_remain_resolved():
    _,_,_,_,result=_uncertainty_response_prior([.2,.7,1.3,2.6],mean_method='student_t')
    assert result['defined'] and result['mean']['estimate_defined']
    assert result['mean']['estimate']==pytest.approx(1.2)
    assert result['mean']['confidence_interval']['defined']
    constant=sample_statistics([1e16]*4)
    assert constant['defined'] and constant['estimate']==1e16
    assert constant['sample_variance']==0. and constant['standard_error']==0.
    assert constant['degeneracies']==['constant_response']


def test_study_request_virtual_input_aggregate_rejects_before_hash_or_serialization(tmp_path,monkeypatch):
    import run_h_analysis_study as producer
    import verification_common as common
    leaf=tmp_path/'source.txt';leaf.write_bytes(b'frozen source bytes')
    request={'schema_version':1,'design':{'label':'温度','rows':[{'id':'same','values':[1.]}]}}
    expected=(json.dumps(request,indent=2,ensure_ascii=False,allow_nan=False)+'\n').encode('utf-8')
    declared=budget();declared['max_total_bytes']=leaf.stat().st_size+len(expected)-1
    paths=common.EvidencePaths([leaf]);events=[]
    def authorized(value,root,bounds,*,role):
        assert value is request and root==tmp_path and bounds is declared and role=='h_study_request'
        events.append('authorized');return paths
    monkeypatch.setattr(producer,'evidence_paths_for_request',authorized)
    monkeypatch.setattr(common,'serialized_json',lambda value:pytest.fail('aggregate failure must precede payload allocation'))
    monkeypatch.setattr(producer,'input_manifest',lambda *args:pytest.fail('aggregate failure must precede source hash'))
    with pytest.raises(ValueError,match='complete input byte/file'):
        producer.capture_study_request(request,tmp_path,declared)
    assert events==['authorized'] and declared['max_total_bytes']==leaf.stat().st_size+len(expected)-1


def test_study_request_exact_utf8_bytes_and_authorized_input_manifest(tmp_path,monkeypatch):
    import run_h_analysis_study as producer
    import verification_common as common
    import hashlib
    leaf=tmp_path/'source.txt';source=b'frozen source bytes';leaf.write_bytes(source)
    request={'schema_version':1,'design':{'label':'温度','rows':[{'id':'same','values':[1.]}]}}
    expected=(json.dumps(request,indent=2,ensure_ascii=False,allow_nan=False)+'\n').encode('utf-8')
    declared=budget();declared['max_total_bytes']=len(source)+len(expected)
    paths=common.EvidencePaths([leaf]);events=[]
    def authorized(*args,**kwargs):
        assert kwargs=={'role':'h_study_request'}
        events.append('authorized');return paths
    original=producer.input_manifest
    def hashed(*args,**kwargs):
        events.append('hashed');return original(*args,**kwargs)
    monkeypatch.setattr(producer,'evidence_paths_for_request',authorized)
    monkeypatch.setattr(producer,'input_manifest',hashed)
    payload,manifest=producer.capture_study_request(request,tmp_path,declared)
    assert payload==expected and payload.endswith(b'\n') and b'\r' not in payload
    assert manifest==[{'path':str(leaf),'bytes':len(source),'sha256':hashlib.sha256(source).hexdigest()}]
    assert events==['authorized','hashed'] and leaf.read_bytes()==source


@pytest.mark.parametrize('cap', ['max_document_nodes','max_document_depth','max_file_bytes','max_files'])
def test_study_request_expanded_node_depth_and_virtual_file_caps_precede_hash(tmp_path,monkeypatch,cap):
    import run_h_analysis_study as producer
    import verification_common as common
    leaf=tmp_path/'source.txt';leaf.write_bytes(b'original')
    shared=[1.]
    for _ in range(8):shared=[shared,shared]
    request={'design':shared};declared=budget()
    declared[cap]=8 if cap=='max_document_nodes' else 2 if cap=='max_document_depth' else 1024 if cap=='max_file_bytes' else 1
    monkeypatch.setattr(producer,'evidence_paths_for_request',lambda *args,**kwargs:common.EvidencePaths([leaf]))
    monkeypatch.setattr(common,'serialized_json',lambda value:pytest.fail('forecast failure must precede expansion allocation'))
    monkeypatch.setattr(producer,'input_manifest',lambda *args:pytest.fail('forecast failure must precede source hash'))
    with pytest.raises(ValueError,match='budget exceeded'):
        producer.capture_study_request(request,tmp_path,declared)


@pytest.fixture(scope='module')
def explicit_parent_state_history(tmp_path_factory):
    """One actual-format baseline/study with explicit opaque caller bytes.

    SYNTHETIC INFRASTRUCTURE TEST ONLY. Real readers consume the full chain;
    no accepted report is substituted and no MATLAB is run by this factory.
    """
    from h_analysis_study_factory import make_study_for_primary,make_study_history
    from model_verification_factory import make_model_verification_contract
    from problem_factory import write_contract
    from runtime_common import load_document,sha256_file
    root=tmp_path_factory.mktemp('SYNTHETIC-parent-state-full-wire')
    baseline=make_model_verification_contract(root)
    original=load_document(baseline);primary=root/original['primary_numerical_receipt']['path']
    state=write_contract(root/'explicit-caller-state.json',{
        'schema_version':1,'project_id':original['project_id'],'current_stage':'NUMERICALLY_VERIFIED',
        'primary_numerical_receipt':{'path':str(primary),'sha256':sha256_file(primary)},
        'purpose':'SYNTHETIC INFRASTRUCTURE TEST; caller bytes only, no real state promotion.'})
    state_bytes=state.read_bytes()
    study=make_study_for_primary(primary,project_root=root)
    receipt=make_study_history(study,project_root=root,state_binding={'path':state.name,'sha256':sha256_file(state)})
    assert state.read_bytes()==state_bytes
    return {'root':root,'study':study,'receipt':receipt,'state':state,'state_bytes':state_bytes}


def test_actual_parent_caller_state_is_prebound_opaque_and_unchanged(explicit_parent_state_history):
    from runtime_common import load_document,sha256_file
    from run_h_analysis_study import canonical_state_bindings
    item=explicit_parent_state_history;root=item['root']
    expected=canonical_state_bindings({'path':item['state'].name,'sha256':sha256_file(item['state'])},root)
    # Actual constant names are source API values, not an invented filename.
    from h_analysis_study import INPUT_NAME
    request=load_document(item['receipt'].parent/INPUT_NAME)
    assert request['bindings']==expected and Path(expected['current_state']['path']).is_absolute()
    report=validate_h_analysis_study_receipt(item['receipt'],project_root=root)
    assert report['valid'] and report['study_complete'] and report['study_accepted'],report['errors']
    assert report['current_state']==expected['current_state']
    for child in load_document(item['receipt'])['trial_receipts']:
        native_request=load_document(Path(child['path']).parent/'h-analysis-input.json')
        assert native_request['bindings']['current_state']==expected['current_state']
    assert item['state'].read_bytes()==item['state_bytes']


@pytest.mark.parametrize('replacement',['different_valid_state','null'])
def test_rehashed_parent_state_cannot_differ_from_actual_child(explicit_parent_state_history,replacement):
    from h_analysis_study import INPUT_NAME
    from problem_factory import write_contract
    from run_h_analysis_study import canonical_state_bindings
    from runtime_common import canonical_digest,load_document,sha256_file
    item=explicit_parent_state_history;root=item['root'];receipt_path=item['receipt']
    input_path=receipt_path.parent/INPUT_NAME
    saved={path:path.read_bytes() for path in (input_path,receipt_path)}
    alternate=None
    try:
        caller=None
        if replacement=='different_valid_state':
            alternate=write_contract(root/'different-valid-caller-bytes.json',{
                'schema_version':1,'project_id':load_document(receipt_path)['project_id'],
                'purpose':'SYNTHETIC INFRASTRUCTURE TEST; another well-formed caller byte binding.'})
            caller={'path':str(alternate),'sha256':sha256_file(alternate)}
        request=load_document(input_path);request['bindings']=canonical_state_bindings(caller,root)
        write_contract(input_path,request)
        receipt=load_document(receipt_path);receipt['input_identity']=canonical_digest(request)
        receipt['artifacts']['input']['sha256']=sha256_file(input_path);write_contract(receipt_path,receipt)
        # Parent and both caller byte hashes are valid. Child execution still
        # binds the original state, so rehashing must not launder the mismatch.
        report=validate_h_analysis_study_receipt(receipt_path,project_root=root)
        assert not report['valid'] and not report['study_complete'] and not report['study_accepted']
        assert any('current-state binding differs from canonical parent' in error for error in report['errors'])
    finally:
        for path,data in saved.items():path.write_bytes(data)
        if alternate is not None:alternate.unlink()
    assert item['state'].read_bytes()==item['state_bytes']


def test_parent_state_full_readset_aggregate_fails_before_allocation_or_hash(tmp_path,monkeypatch):
    import hashlib
    import run_h_analysis_study as producer
    import verification_common as common
    state=tmp_path/'state.json';state.write_bytes(b'{"caller":"SYNTHETIC INFRASTRUCTURE TEST"}')
    source=tmp_path/'source.txt';source.write_bytes(b'reviewed original input')
    binding=lambda path:{'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    request={'bindings':producer.canonical_state_bindings(binding(state),tmp_path),'sources':[binding(source)]}
    declared=budget()
    paths=common.evidence_paths_for_request(request,tmp_path,declared,role='h_study_request')
    assert state in paths and source in paths
    complete_input_bytes=sum(path.stat().st_size for path in paths)
    expected=(json.dumps(request,indent=2,ensure_ascii=False,allow_nan=False)+'\n').encode('utf-8')
    declared['max_total_bytes']=complete_input_bytes+len(expected)-1
    # Omitting the known state would fit. The complete request/read set cannot.
    assert complete_input_bytes-state.stat().st_size+len(expected)<=declared['max_total_bytes']
    monkeypatch.setattr(common,'serialized_json',lambda value:pytest.fail('complete known-state aggregate must fail before allocation'))
    monkeypatch.setattr(producer,'input_manifest',lambda *args:pytest.fail('complete known-state aggregate must fail before source/state hashing'))
    with pytest.raises(ValueError,match='complete input byte/file'):
        producer.capture_study_request(request,tmp_path,declared)


@pytest.mark.parametrize('change',[{'sha256':'A'*64},{'sha256':True},{'extra':'unapproved'}])
def test_parent_state_binding_rejects_noncanonical_shape_before_source_reads(tmp_path,change):
    from run_h_analysis_study import canonical_state_bindings
    supplied={'path':'explicit.json','sha256':'0'*64};supplied.update(change)
    with pytest.raises(ValueError,match='exact caller-bound'):canonical_state_bindings(supplied,tmp_path)
    assert canonical_state_bindings(None,tmp_path)=={'current_state':None,'protected_files':[]}
    with pytest.raises(ValueError):canonical_state_bindings({'path':'../foreign.json','sha256':'0'*64},tmp_path)


@pytest.mark.parametrize('attack',['relative_path','wrong_sha','duplicate_protected'])
def test_rehashed_parent_caller_shape_or_sha_cannot_accept(explicit_parent_state_history,attack):
    from h_analysis_study import INPUT_NAME
    from problem_factory import write_contract
    from runtime_common import canonical_digest,load_document,sha256_file
    item=explicit_parent_state_history;receipt_path=item['receipt'];input_path=receipt_path.parent/INPUT_NAME
    saved={path:path.read_bytes() for path in (input_path,receipt_path)}
    try:
        request=load_document(input_path);bindings=request['bindings']
        if attack=='relative_path':
            bindings['current_state']['path']=item['state'].name
            bindings['protected_files'][0]['path']=item['state'].name
        elif attack=='wrong_sha':
            bindings['current_state']['sha256']='0'*64
            bindings['protected_files'][0]['sha256']='0'*64
        else:bindings['protected_files'].append(deepcopy(bindings['current_state']))
        write_contract(input_path,request)
        receipt=load_document(receipt_path);receipt['input_identity']=canonical_digest(request)
        receipt['artifacts']['input']['sha256']=sha256_file(input_path);write_contract(receipt_path,receipt)
        report=validate_h_analysis_study_receipt(receipt_path,project_root=item['root'])
        assert not report['valid'] and not report['study_complete'] and not report['study_accepted']
        assert any('canonical contained path/SHA/protected' in error or 'byte claim' in error or 'claimed byte identity' in error for error in report['errors'])
    finally:
        for path,data in saved.items():path.write_bytes(data)
    assert item['state'].read_bytes()==item['state_bytes']
