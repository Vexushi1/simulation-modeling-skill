"""SYNTHETIC consumer evidence only. No fixture establishes actual MATLAB qualification."""
import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest
from scipy.io import loadmat, savemat

import probe_parameter_study as producer
import run_parameter_study as runner
from parameter_study_common import METHODS, assert_case, contract, numeric_readback, objective_value, predictions, residuals, validate_native_spec
from parameter_study_factory import make_parameter_study
from probe_environment import write_json
from runtime_common import canonical_digest, load_document, sha256_file
from test_runtime import make_profile
from test_simulation_assurance import make_simulation_profile
from validate_environment import runtime_identity, utc_text
from validate_parameter_study import validate_parameter_study
from validate_parameter_study_profile import derive_profile, observed_runtime, validate_parameter_study_profile
from validate_parameter_study_receipt import validate_parameter_study_receipt


def synthetic_case(case, directory, identity):
    """Explicit synthetic raw/MAT/JSON fixture; never used for actual qualification."""
    s = case['native_spec']
    actual = {'case_id': case['case_id'], 'method': s['method'], 'status': 'completed', 'candidate_complete': True,
              'error': '', 'error_identifier': '', 'theta': [], 'train_prediction': [], 'holdout_prediction': [],
              'train_residual': [], 'holdout_residual': [], 'objective': [], 'exitflag': [], 'algorithm': '',
              'iterations': 1, 'func_count': 1, 'firstorderopt': 0.0, 'rank': None, 'condition_number': None,
              'ledger': [], 'diagnostics': [], 'restored': True, 'model_file': '',
              'data_file': case['case_id']+'-numeric.json', 'mat_file': case['case_id']+'-numeric.mat'}
    if case['expectation'] not in {'success', 'budget', 'criterion'}:
        actual.update(status='failed', candidate_complete=False, error='SYNTHETIC controlled negative', error_identifier='PhaseF:Bounds' if 'bounds' in case['case_id'] else 'PhaseF:TimeGrid' if 'time' in case['case_id'] else 'PhaseF:RankDeficient')
        if case['expectation'] == 'simulation_error':
            actual['error_identifier'] = 'PhaseF:SimulationError'
            actual['ledger'] = [{'sequence': 1, 'phase': 'train', 'theta': s['initial'], 'prediction': [], 'residual': [], 'objective': None, 'error': 'SYNTHETIC controlled phase_f_controlled_missing_symbol sim failure', 'error_identifier': 'PhaseF:SimulationError'}]
    else:
        theta = case['expected_theta']
        if theta is None:
            if s['method'] == METHODS[0]:
                X = np.column_stack((s['train']['output'][:-1], s['train']['input'][:-1]))
                theta = np.linalg.lstsq(X, s['train']['output'][1:], rcond=None)[0].tolist()
            elif s['method'] == METHODS[1]:
                d = s['train']; theta = [sum(w*u*y for w,u,y in zip(d['weights'], d['input'], d['output']))/sum(w*u*u for w,u in zip(d['weights'], d['input']))]
            else:
                theta = [1.5, 1.5]  # This factory's explicit symmetric convex fixture.
        if case['expectation'] == 'budget':
            theta = s['initial']; actual.update(status='budget_exhausted', candidate_complete=False, iterations=0)
        actual['theta'] = theta
        actual['algorithm'] = 'arx_prediction_111' if s['method'] == METHODS[0] else 'trust-region-reflective' if s['method'] == METHODS[1] else 'sqp'
        actual['exitflag'] = [] if s['method'] == METHODS[0] else [0.0] if case['expectation'] == 'budget' else [1.0]
        if s['method'] == METHODS[2]:
            value = objective_value(s, theta); actual['objective'] = [value]
            actual['ledger'] = [{'sequence': 1, 'phase': 'train', 'theta': theta, 'prediction': [], 'residual': [], 'objective': value, 'error': '', 'error_identifier': ''}]
        else:
            if s['method'] == METHODS[0]:
                X = np.column_stack((s['train']['output'][:-1], s['train']['input'][:-1]))
                actual.update(rank=int(np.linalg.matrix_rank(X)), condition_number=float(np.linalg.cond(X)))
            for split in ('train', 'holdout') if case['expectation'] in {'success', 'criterion'} else ('train',):
                p = predictions(s, theta, split); r = residuals(s, p, split)
                actual[split+'_prediction'] = p; actual[split+'_residual'] = r
                value = sum(v*v for v in r)
                if split == 'train':
                    actual['objective'] = [value]
                call = {'sequence': len(actual['ledger'])+1, 'phase': split, 'theta': theta, 'prediction': p, 'residual': r, 'objective': value, 'error': '', 'error_identifier': ''}
                if s['method'] == METHODS[1]:
                    call.update(solver='FixedStepDiscrete', solver_type='Fixed-Step', stop_event='ReachedStopTime',
                                output_time=s[split]['time'], saved_time=s[split]['time'], requested_solver='ode4', requested_step=s['sample_time'],
                                parameter_before=s['initial'][0], parameter_after=s['initial'][0], configuration_restored=True, simulation_file=case['case_id']+'-'+split+'-returned.mat')
                    savemat(directory/call['simulation_file'],{'simulation_output':'SYNTHETIC ONLY; NO MATLAB'},format='5')
                if s['method'] == METHODS[1] and split == 'holdout' and case['expectation'] == 'success':
                    final = copy.deepcopy(actual['ledger'][0]); final.update(sequence=2,phase='final')
                    actual['ledger'].append(final); call['sequence']=3
                actual['ledger'].append(call)
        if case['expectation'] == 'criterion':
            actual.update(status='failed', candidate_complete=False, error='SYNTHETIC heldout criterion failure after actual-shaped fitted numeric data', error_identifier='PhaseF:HoldoutCriterion')
    names = ('theta', 'train_prediction', 'holdout_prediction', 'train_residual', 'holdout_residual', 'objective', 'exitflag')
    data = {name: actual[name] for name in names}
    data.update(schema_version=1, run_id=identity, case_id=case['case_id'])
    write_json(directory/actual['data_file'], data)
    mat = {name: np.asarray(actual[name], dtype=np.float64).reshape(-1,1) for name in names}
    mat.update(run_id=identity, case_id=case['case_id'])
    savemat(directory/actual['mat_file'], mat, format='5')
    return actual


def make_parameter_profile(directory, a_profile, *, age_hours=0, operations=None):
    directory = Path(directory); directory.mkdir(parents=True)
    a = load_document(a_profile); root = Path(a['runtime']['matlabroot'])
    request = producer.make_request(a['runtime']['executable'], directory, environment_profile=a_profile, operations=operations)
    reference = datetime.now(timezone.utc)-timedelta(seconds=0.05, hours=age_hours)
    raw = {key: request[key] for key in ('run_id', 'channel', 'host_fingerprint', 'source_identity', 'input_identity')}
    raw.update(schema_version=1, status='completed', started_at=utc_text(reference-timedelta(seconds=0.01)), finished_at=utc_text(reference),
               runtime={key: a['runtime'][key] for key in ('release', 'version', 'matlabroot', 'platform')},
               installed_products=[{'Name': n, 'Version': '25.2'} for n in ('MATLAB', 'Simulink', 'System Identification Toolbox', 'Optimization Toolbox')],
               licenses_inuse=[], functions=[], operation_diagnostics=[], cases=[])
    for name in request['required_functions']:
        p = root/'toolbox'/'fixture'/(name+'.m'); p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.write_text('% SYNTHETIC F FUNCTION; NO MATLAB\n', encoding='utf-8')
        raw['functions'].append({'name': name, 'path': str(p.resolve())})
    by_name = {f['name']: f for f in raw['functions']}
    for op in request['operations']:
        raw['operation_diagnostics'].append({'operation_id': op, 'license_test': 1, 'functions': [by_name[name] for name in contract()['operations'][op]['functions']]})
    raw['cases'] = [synthetic_case(case, directory, request['run_id']) for case in request['cases']]
    process = {'started_at': utc_text(reference-timedelta(seconds=0.02)), 'finished_at': utc_text(reference+timedelta(seconds=0.01)),
               'process_state': 'completed', 'exit_code': 0, 'pid': 0, 'command': ['SYNTHETIC NO MATLAB']}
    names = contract()['evidence']
    for key,value in (('input', request), ('raw', raw), ('process', process)):
        write_json(directory/names[key], value)
    (directory/names['log']).write_text('SYNTHETIC CONSUMER EVIDENCE ONLY; NO ACTUAL MATLAB\n', encoding='utf-8')
    path = directory/names['profile']
    rebind(path)
    return path


def rebind(path, *, derive=True):
    d = path.parent; names = contract()['evidence']
    request, raw, process = (load_document(d/names[k]) for k in ('input', 'raw', 'process'))
    if derive:
        write_json(path, derive_profile(raw, request, process))
    receipt = {'schema_version': 1, 'run_id': request['run_id'], 'sources': request['sources'], 'process': process,
               'runtime': observed_runtime(raw, request), 'artifacts': producer.artifact_manifest(d, raw, include_profile=True)}
    write_json(d/names['profile_receipt'], receipt)


def make_trial(root, method=METHODS[2], *, required_operations=None):
    study = make_parameter_study(root, method)
    report = validate_parameter_study(study, project_root=root, require_reviewed=True)
    assert report['trial_execution_ready'], report
    a = make_profile(root/'a', include_statistics=True)
    f = make_parameter_profile(root/'f', a)
    e = make_simulation_profile(root/'e', a) if method == METHODS[1] else None
    d = root/'trial'; d.mkdir()
    request = runner.make_task_request(study, load_document(a)['runtime']['executable'], d, report, a, f, project_root=root, simulation_profile=e, required_operations=required_operations)
    _,runtime = runner.verify_trial_bindings(request)
    profile_raw = load_document(f.parent/contract()['evidence']['raw'])
    clock = datetime.now(timezone.utc)-timedelta(seconds=0.005)
    raw = copy.deepcopy(profile_raw)
    raw['functions'] = [item for item in raw['functions'] if item['name'] in request['required_functions']]
    raw['operation_diagnostics'] = [item for item in raw['operation_diagnostics'] if item['operation_id'] == method]
    raw.update({key: request[key] for key in ('run_id','channel','host_fingerprint','source_identity','input_identity')})
    raw.update(started_at=utc_text(clock), finished_at=utc_text(clock+timedelta(milliseconds=1)),
               cases=[synthetic_case(request['cases'][0], d, request['run_id'])])
    process = {'started_at': utc_text(clock-timedelta(milliseconds=1)), 'finished_at': utc_text(clock+timedelta(milliseconds=2)), 'process_state':'completed', 'exit_code':0, 'pid':0, 'command':['SYNTHETIC NO MATLAB']}
    names = contract()['evidence']
    for key,value in (('input',request),('raw',raw),('process',process)):
        write_json(d/names[key],value)
    (d/names['log']).write_text('SYNTHETIC candidate fixture; no MATLAB\n', encoding='utf-8')
    receipt = {'schema_version':1,'run_id':request['run_id'],'project_id':report['project_id'],'study_sha256':report['study_sha256'],
               'study_semantic_sha256':report['semantic_sha256'],'native_spec_sha256':canonical_digest(report['native_spec']),
               'sources':request['sources'],'process':process,'runtime':observed_runtime(raw,request),'artifacts':producer.artifact_manifest(d,raw)}
    path=d/names['run_receipt']; write_json(path,receipt)
    return path


def test_each_independent_method_profile_has_own_cases_and_no_adoption(tmp_path):
    a=make_profile(tmp_path/'a'); path=make_parameter_profile(tmp_path/'f',a)
    result=validate_parameter_study_profile(path)
    assert result['valid'], result
    assert result['qualified_operations']==list(METHODS)
    assert len(result['case_results'])==11
    assert 'primary_run_complete' not in result


@pytest.mark.parametrize('case_id', ['arx_positive','arx_rank_deficient','arx_invalid_time','arx_holdout_rejected','gain_positive','gain_simulation_error','gain_budget','gain_invalid_bounds','quadratic_positive','quadratic_budget','quadratic_invalid_bounds'])
def test_failure_is_specific_to_its_method_and_cannot_be_declared_qualified(tmp_path,case_id):
    a=make_profile(tmp_path/'a'); path=make_parameter_profile(tmp_path/'f',a)
    raw=load_document(path.parent/contract()['evidence']['raw'])
    actual=next(c for c in raw['cases'] if c['case_id']==case_id)
    op=actual['method']; actual['status']='unexpected'
    write_json(path.parent/contract()['evidence']['raw'],raw); rebind(path)
    assert not validate_parameter_study_profile(path,required_operations=[op])['valid']
    other=next(m for m in METHODS if m!=op)
    assert validate_parameter_study_profile(path,required_operations=[other])['valid']


@pytest.mark.parametrize('state,code',[('failed',0),('completed',1),('timed_out',-1),('completed',False)])
def test_actual_process_failure_cannot_qualify_method(tmp_path,state,code):
    a=make_profile(tmp_path/'a'); path=make_parameter_profile(tmp_path/'f',a)
    p=load_document(path.parent/contract()['evidence']['process']); p.update(process_state=state,exit_code=code)
    write_json(path.parent/contract()['evidence']['process'],p); rebind(path)
    assert not validate_parameter_study_profile(path)['valid']


@pytest.mark.parametrize('field',['theta','train_prediction','holdout_prediction','train_residual','holdout_residual','objective','exitflag'])
@pytest.mark.parametrize('dtype',[np.uint8,np.bool_,np.complex128])
def test_matlab_class_and_complex_storage_cannot_pass_casting(tmp_path,field,dtype):
    case=producer.qualification_cases([METHODS[1]])[0]
    actual=synthetic_case(case,tmp_path,'synthetic-run')
    mat=loadmat(tmp_path/actual['mat_file']); mat={k:v for k,v in mat.items() if not k.startswith('__')}
    mat[field]=mat[field].astype(dtype)
    if dtype==np.complex128: mat[field]=mat[field]+1j
    savemat(tmp_path/actual['mat_file'],mat)
    with pytest.raises(ValueError): numeric_readback(tmp_path,actual,'synthetic-run')


@pytest.mark.parametrize('field',['theta','train_prediction','objective','exitflag'])
def test_exact_numeric_and_shape_readback_survives_manifest_rebinding(tmp_path,field):
    case=producer.qualification_cases([METHODS[1]])[0]; actual=synthetic_case(case,tmp_path,'synthetic-run')
    mat=loadmat(tmp_path/actual['mat_file']); mat={k:v for k,v in mat.items() if not k.startswith('__')}
    mat[field]=mat[field]+1e-5; savemat(tmp_path/actual['mat_file'],mat)
    with pytest.raises(ValueError): numeric_readback(tmp_path,actual,'synthetic-run')


@pytest.mark.parametrize('method',METHODS)
def test_candidate_receipt_is_readonly_and_keeps_null_approved_values(tmp_path,method):
    path=make_trial(tmp_path,method)
    before={str(p):sha256_file(p) for p in tmp_path.rglob('*') if p.is_file()}
    result=validate_parameter_study_receipt(path,project_root=tmp_path)
    assert result['valid'] and result['trial_complete'] and result['candidate_complete'],result
    assert 'primary_run_complete' not in result and 'accepted' not in result
    after={str(p):sha256_file(p) for p in tmp_path.rglob('*') if p.is_file()}
    assert before==after


@pytest.mark.parametrize('operation',['statistics.fitlm','statistics.lhsdesign','statistics.normcdf'])
def test_required_statistics_union_blocks_before_directory_or_matlab(tmp_path,monkeypatch,operation):
    study=make_parameter_study(tmp_path,METHODS[2]); report=validate_parameter_study(study,project_root=tmp_path,require_reviewed=True)
    a=make_profile(tmp_path/'a',include_statistics=True,failing_operations=[operation]); f=make_parameter_profile(tmp_path/'f',a)
    directory=tmp_path/'blocked'; request=runner.make_task_request(study,load_document(a)['runtime']['executable'],directory,report,a,f,project_root=tmp_path,required_operations=[operation])
    monkeypatch.setattr(producer,'_run_process',lambda *a,**k:pytest.fail('MATLAB must not start'))
    with pytest.raises(ValueError): producer.execute_request(request,timeout=report['native_spec']['budget']['process_timeout'])
    assert not directory.exists()


@pytest.mark.parametrize('field,value',[('max_iterations',False),('max_evaluations',0),('process_timeout',float('inf'))])
def test_illegal_budget_is_rejected_without_native_launch(field,value):
    spec=copy.deepcopy(producer.qualification_cases([METHODS[2]])[0]['native_spec']); spec['budget'][field]=value
    with pytest.raises(ValueError): validate_native_spec(spec)


def test_history_retains_execution_time_qualification_but_new_trial_expires(tmp_path,monkeypatch):
    path=make_trial(tmp_path,METHODS[2]); request=load_document(path.parent/contract()['evidence']['input'])
    profile=Path(request['bindings']['parameter_study_profile']['path'])
    future=datetime.now(timezone.utc)+timedelta(hours=25)
    assert not validate_parameter_study_profile(profile,now=future)['valid']
    assert validate_parameter_study_profile(profile,now=future,require_current=False)['valid']
    assert validate_parameter_study_receipt(path)['valid']


def test_manifest_and_current_study_sources_remain_required(tmp_path):
    path=make_trial(tmp_path,METHODS[1]); source=tmp_path/'observations.csv'; source.write_text(source.read_text()+'0,0,0\n')
    assert not validate_parameter_study_receipt(path)['valid']


def test_json_record_array_does_not_promote_single_object(tmp_path):
    a=make_profile(tmp_path/'a'); path=make_parameter_profile(tmp_path/'f',a)
    raw=load_document(path.parent/contract()['evidence']['raw']); raw['cases']=raw['cases'][0]
    write_json(path.parent/contract()['evidence']['raw'],raw)
    assert not validate_parameter_study_profile(path)['valid']


@pytest.mark.parametrize('method',METHODS)
@pytest.mark.parametrize('mutation',['empty','failed_call','holdout_early','wrong_candidate'])
def test_completed_candidate_rejects_incomplete_failed_or_selective_ledger(tmp_path,method,mutation):
    case=producer.qualification_cases([method])[0]; actual=synthetic_case(case,tmp_path,'synthetic-run')
    if mutation=='empty': actual['ledger']=[]
    elif mutation=='failed_call': actual['ledger'][0]['error']='SYNTHETIC failed call must stop candidate'
    elif mutation=='holdout_early': actual['ledger'][0]['phase']='holdout'
    else:
        actual['ledger'][-1]['theta']=[v+0.1 for v in actual['theta']]
    with pytest.raises(ValueError): assert_case(actual,case,tmp_path,'synthetic-run')


@pytest.mark.parametrize('field,value',[('iterations',-1),('func_count',0),('firstorderopt',None),('firstorderopt',float('nan')),('iterations',999),('func_count',999)])
def test_completed_optimizer_rejects_invalid_or_over_budget_diagnostics(tmp_path,field,value):
    case=producer.qualification_cases([METHODS[2]])[0]; actual=synthetic_case(case,tmp_path,'synthetic-run'); actual[field]=value
    with pytest.raises(ValueError): assert_case(actual,case,tmp_path,'synthetic-run')


@pytest.mark.parametrize('case_id',['arx_rank_deficient','arx_invalid_time','gain_invalid_bounds','quadratic_invalid_bounds'])
def test_unrelated_native_failure_does_not_qualify_controlled_rejection(tmp_path,case_id):
    case=next(c for c in producer.qualification_cases() if c['case_id']==case_id); actual=synthetic_case(case,tmp_path,'synthetic-run')
    actual['error_identifier']='MATLAB:UndefinedFunction'
    with pytest.raises(ValueError): assert_case(actual,case,tmp_path,'synthetic-run')


@pytest.mark.parametrize('method',METHODS)
@pytest.mark.parametrize('value',[float('nan'),float('inf'),True,None])
def test_successful_ledger_requires_finite_typed_objective(tmp_path,method,value):
    case=producer.qualification_cases([method])[0]; actual=synthetic_case(case,tmp_path,'synthetic-run')
    actual['ledger'][0]['objective']=value
    with pytest.raises(ValueError): assert_case(actual,case,tmp_path,'synthetic-run')


@pytest.mark.parametrize('mutation',['none','missing_ledger','missing_theta','wrong_error'])
def test_arx_holdout_failure_preserves_fitted_candidate_and_both_numeric_calls(tmp_path,mutation):
    case=next(c for c in producer.qualification_cases() if c['case_id']=='arx_holdout_rejected')
    actual=synthetic_case(case,tmp_path,'synthetic-run')
    if mutation=='missing_ledger': actual['ledger']=actual['ledger'][:1]
    elif mutation=='missing_theta': actual['theta']=[]
    elif mutation=='wrong_error': actual['error_identifier']='MATLAB:UndefinedFunction'
    if mutation=='none':
        report=assert_case(actual,case,tmp_path,'synthetic-run')
        assert not report['candidate_complete'] and len(actual['ledger'])==2 and len(actual['theta'])==2
    else:
        with pytest.raises(ValueError): assert_case(actual,case,tmp_path,'synthetic-run')


@pytest.mark.parametrize('method',METHODS[1:])
@pytest.mark.parametrize('field,value',[('algorithm','bogus'),('iterations',999999),('iterations',-1),('func_count',-999),('func_count',0),('firstorderopt',None),('firstorderopt',True)])
def test_controlled_budget_requires_actual_typed_method_and_count_diagnostics(tmp_path,method,field,value):
    case=next(c for c in producer.qualification_cases([method]) if c['expectation']=='budget')
    actual=synthetic_case(case,tmp_path,'synthetic-run'); actual[field]=value
    with pytest.raises(ValueError): assert_case(actual,case,tmp_path,'synthetic-run')


@pytest.mark.parametrize('method',METHODS[1:])
def test_controlled_budget_cannot_hide_over_budget_objective_calls(tmp_path,method):
    case=next(c for c in producer.qualification_cases([method]) if c['expectation']=='budget')
    actual=synthetic_case(case,tmp_path,'synthetic-run')
    actual['ledger']=[{**copy.deepcopy(actual['ledger'][0]),'sequence':index+1} for index in range(case['native_spec']['budget']['max_evaluations']+1)]
    actual['func_count']=len(actual['ledger'])
    with pytest.raises(ValueError): assert_case(actual,case,tmp_path,'synthetic-run')


@pytest.mark.parametrize('split',['train','holdout'])
def test_arx_ledger_single_residual_cannot_broadcast_to_a_whole_experiment(tmp_path,split):
    case=producer.qualification_cases([METHODS[0]])[0]; actual=synthetic_case(case,tmp_path,'synthetic-run')
    call=next(c for c in actual['ledger'] if c['phase']==split); call['residual']=[0.0]
    with pytest.raises(ValueError): assert_case(actual,case,tmp_path,'synthetic-run')


@pytest.mark.parametrize('split',['train','holdout'])
def test_arx_final_single_residual_cannot_broadcast_after_numeric_rebinding(tmp_path,split):
    case=producer.qualification_cases([METHODS[0]])[0]; actual=synthetic_case(case,tmp_path,'synthetic-run')
    field=split+'_residual'; actual[field]=[0.0]
    data=load_document(tmp_path/actual['data_file']); data[field]=[0.0]; write_json(tmp_path/actual['data_file'],data)
    mat=loadmat(tmp_path/actual['mat_file']); mat={k:v for k,v in mat.items() if not k.startswith('__')}
    mat[field]=np.asarray([[0.0]],dtype=np.float64); savemat(tmp_path/actual['mat_file'],mat)
    with pytest.raises(ValueError): assert_case(actual,case,tmp_path,'synthetic-run')


@pytest.mark.parametrize('method',METHODS)
@pytest.mark.parametrize('mutation',['missing','duplicate','extra','outside_installation'])
def test_trial_requires_exact_unique_official_method_functions_after_receipt_rebinding(tmp_path,method,mutation):
    path=make_trial(tmp_path,method); names=contract()['evidence']
    request=load_document(path.parent/names['input']); raw=load_document(path.parent/names['raw'])
    if mutation=='missing': raw['functions']=raw['functions'][1:]
    elif mutation=='duplicate': raw['functions'].append(copy.deepcopy(raw['functions'][0]))
    elif mutation=='extra':
        qualification_raw=load_document(Path(request['bindings']['parameter_study_profile']['path']).parent/names['raw'])
        raw['functions'].append(next(copy.deepcopy(item) for item in qualification_raw['functions'] if item['name'] not in request['required_functions']))
    else:
        outsider=tmp_path/'shadow-function.m'; outsider.write_text('% SYNTHETIC outside MATLAB installation\n',encoding='utf-8')
        raw['functions'][0]['path']=str(outsider.resolve())
    write_json(path.parent/names['raw'],raw)
    receipt=load_document(path)
    # Recreate the prior permissive normalization to ensure the consumer rejects
    # method evidence even when all mutable raw/receipt manifest bytes agree.
    receipt['runtime']=runtime_identity({**raw,'operations':[{'functions':raw['functions']}]},request['matlab_executable'])
    receipt['artifacts']=producer.artifact_manifest(path.parent,raw); write_json(path,receipt)
    result=validate_parameter_study_receipt(path)
    assert not result['valid'] and any('official method surface' in error for error in result['errors']),result


@pytest.mark.parametrize('method',METHODS)
def test_trial_cannot_reuse_qualification_for_different_official_function_resolution(tmp_path,method):
    path=make_trial(tmp_path,method); names=contract()['evidence']
    request=load_document(path.parent/names['input']); raw=load_document(path.parent/names['raw'])
    original=Path(raw['functions'][0]['path']); alternate=original.parent/'other-official'/original.name
    alternate.parent.mkdir(); alternate.write_bytes(original.read_bytes())
    raw['functions'][0]['path']=str(alternate.resolve()); write_json(path.parent/names['raw'],raw)
    receipt=load_document(path); receipt['runtime']=observed_runtime(raw,request)
    receipt['artifacts']=producer.artifact_manifest(path.parent,raw); write_json(path,receipt)
    result=validate_parameter_study_receipt(path)
    assert not result['valid'] and any('qualified selected method' in error for error in result['errors']),result


@pytest.mark.parametrize('method',METHODS)
def test_trial_function_bytes_must_match_qualified_selected_method(tmp_path,monkeypatch,method):
    import validate_parameter_study_receipt as consumer
    path=make_trial(tmp_path,method); original=consumer.observed_runtime
    def changed_after_qualification(raw,request):
        runtime=copy.deepcopy(original(raw,request)); runtime['function_files'][0]['sha256']='0'*64
        return runtime
    monkeypatch.setattr(consumer,'observed_runtime',changed_after_qualification)
    result=consumer.validate_parameter_study_receipt(path)
    assert not result['valid'] and any('function-file bytes' in error for error in result['errors']),result


def test_gain_controlled_budget_uses_positive_reviewed_iteration_limit(tmp_path):
    case=next(c for c in producer.qualification_cases([METHODS[1]]) if c['expectation']=='budget')
    assert case['native_spec']['budget']['max_iterations']==1
    actual=synthetic_case(case,tmp_path,'synthetic-run'); actual['iterations']=1
    assert not assert_case(actual,case,tmp_path,'synthetic-run')['candidate_complete']
    actual['iterations']=2
    with pytest.raises(ValueError): assert_case(actual,case,tmp_path,'synthetic-run')


@pytest.mark.parametrize('split',['train','holdout'])
@pytest.mark.parametrize('mutation',['truncate_both','prediction_value','residual_value'])
def test_arx_rejected_holdout_preserves_complete_final_arrays_bound_to_verified_ledger(tmp_path,split,mutation):
    case=next(c for c in producer.qualification_cases([METHODS[0]]) if c['expectation']=='criterion')
    actual=synthetic_case(case,tmp_path,'synthetic-run')
    if mutation=='truncate_both':
        fields=[split+'_prediction',split+'_residual']
        for field in fields: actual[field]=actual[field][:1]
    else:
        field=split+('_prediction' if mutation=='prediction_value' else '_residual')
        fields=[field]; actual[field]=list(actual[field]); actual[field][0]+=0.1
    data=load_document(tmp_path/actual['data_file'])
    mat=loadmat(tmp_path/actual['mat_file']); mat={k:v for k,v in mat.items() if not k.startswith('__')}
    for field in fields:
        data[field]=actual[field]; mat[field]=np.asarray(actual[field],dtype=np.float64).reshape(-1,1)
    write_json(tmp_path/actual['data_file'],data); savemat(tmp_path/actual['mat_file'],mat)
    with pytest.raises(ValueError,match='complete verified split ledger'):
        assert_case(actual,case,tmp_path,'synthetic-run')


@pytest.mark.parametrize('method', METHODS)
@pytest.mark.parametrize('nested_explicit_root', [False, True])
def test_public_producer_preserves_project_root_at_real_review_gate(tmp_path, monkeypatch, method, nested_explicit_root):
    """A nested reviewed study must reach runtime gates using its caller root."""
    import resolve_runtime as routing

    root = tmp_path / 'project'
    study = make_parameter_study(root, method)
    if nested_explicit_root:
        nested = root / 'nested'
        nested.mkdir()
        study = study.replace(nested / study.name)
    direct = validate_parameter_study(study, project_root=root, require_reviewed=True)
    assert direct['valid'] and direct['trial_execution_ready'], direct['errors']
    before = {path: path.read_bytes() for path in root.rglob('*') if path.is_file()}
    actual_resolver, observed = routing.resolve_runtime, []

    def route_without_runtime_evidence(intent, **kwargs):
        # Exercise the actual source/review route with the producer's selected
        # root. Deliberately omit runtime profiles to stop before native work.
        report = actual_resolver(intent, study_path=kwargs['study_path'],
                                 project_root=kwargs.get('project_root'))
        observed.append((kwargs, report))
        return report

    monkeypatch.setattr(routing, 'resolve_runtime', route_without_runtime_evidence)
    output = root / 'native-attempt'
    selected_root = {'project_root': root} if nested_explicit_root else {}
    with pytest.raises(ValueError, match='public parameter-trial route blocked'):
        runner.run_parameter_study(study, root / 'matlab.exe', output,
            environment_profile=root / 'unqualified-a.json',
            parameter_study_profile=root / 'unqualified-f.json',
            simulation_profile=root / 'unqualified-e.json' if method == METHODS[1] else None,
            **selected_root)
    assert len(observed) == 1
    forwarded, route = observed[0]
    assert forwarded['project_root'] == root.resolve()
    assert route['study_validation']['valid'] and route['study_validation']['trial_execution_ready'], route['errors']
    assert route['status'] == 'blocked' and route['missing_gates'] == ['current_a_and_f_profiles'], route
    assert not route['parameter_study_execution_allowed'] and not output.exists()
    assert {path: path.read_bytes() for path in root.rglob('*') if path.is_file()} == before
