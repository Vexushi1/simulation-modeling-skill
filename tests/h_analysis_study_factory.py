"""Source-reviewed synthetic H studies over an existing immutable E/H1 baseline.

These development records never imply an actual person's model approval or
native execution. Whole-chain tests use synthetic native-format files and the
real independent readers, rather than substitute successful validator reports.
"""
from copy import deepcopy
from pathlib import Path

from h_analysis_study import SETTINGS_FIELDS, generate_design
from model_factory import file_ref
from numerical_math_common import DEFAULT_MATH_BUDGET
from problem_factory import write_contract
from runtime_common import load_document
from validate_simulation_protocol import SOLVER_FIELDS
from validate_numerical_verification_receipt import validate_numerical_verification_receipt
from verification_common import semantic_digest


def study_budget():
    return {'max_file_bytes':67108864,'max_total_bytes':1073741824,'max_samples_per_output':12001,
            'max_result_bytes':16777216,'max_groups':2048,'max_cases':8192,'process_timeout':3600,
            'simulation_timeout':120,'total_timeout':14400,'max_iterations':2048,'max_factors':8,
            'max_points':2048,'max_matrix_cells':65536,'max_bootstrap_replicates':1000,'max_work_items':2000000}


def review_h_analysis_study(path,*,project_root=None,refresh_settings=True):
    path=Path(path).resolve();root=Path(project_root or path.parent).resolve();value=load_document(path)
    stem=path.stem
    source=root/(stem+'-settings.json')
    if refresh_settings:write_contract(source,{'settings':{key:value[key] for key in SETTINGS_FIELDS}})
    value['sources']=[{'id':'settings',**file_ref(root,source),'purpose':'SYNTHETIC INFRASTRUCTURE TEST; hypothetical prior settings and complete design only.'}]
    value['settings_source_ref']={'source_id':'settings','selector':['settings']}
    digest=semantic_digest(value)
    quote=(f"project_id={value['project_id']}\nverification_semantic_sha256={digest}\n"
           'reviewed_by=synthetic-h-study-reviewer\naction=review\n'
           'SYNTHETIC INFRASTRUCTURE TEST ONLY; this is not a real human model approval or physical-distribution validation.')
    decision=root/(stem+'-review-decision.txt');decision.write_text(quote+'\n',encoding='utf-8')
    record=write_contract(root/(stem+'-review.json'),{'schema_version':1,'project_id':value['project_id'],
             'verification_semantic_sha256':digest,'decision':{**file_ref(root,decision),'start':0,'end':len(quote),'quote':quote,
             'reviewed_by':'synthetic-h-study-reviewer','action':'review'}})
    value.update(status='reviewed',review_record=file_ref(root,record))
    return write_contract(path,value)


def make_study_for_primary(primary_h1_receipt,*,project_root=None,filename='h-analysis-study.json',upper=3.):
    """Reuse one complete labelled CI baseline; do not rebuild or mutate it."""
    primary_h1_receipt=Path(primary_h1_receipt).resolve();root=Path(project_root or primary_h1_receipt.parent.parent).resolve()
    primary=validate_numerical_verification_receipt(primary_h1_receipt,project_root=root)
    assert primary['valid'] and primary['numerically_verified'],primary['errors']
    protocol=primary['primary_protocol_report'];h1=load_document(primary['contract_path'])
    h1_protocols=[root/item['path'] for item in [h1['primary_protocol'],*h1['refinement_protocols']]]
    registry=[p for p in protocol['mapping_validation']['parameter_validation']['parameters'] if all(p['reference'][k]==protocol[k] for k in ('design_id','model_id'))]
    registration=next((p for p in registry if p['code_name']=='b'),registry[0])
    baseline=float(registration['value']);domain={'lower':baseline-.5,'upper':baseline+.5}
    factor={'id':'coefficient','kind':'parameter','variable_id':registration['reference']['variable_id'],
            'unit':registration['unit'],'baseline':baseline,'domain':domain,'law':None,'levels':[],'probabilities':None,
            'locator':{'code_name':registration['code_name'],'block_path':None,'input_port':None,'state_selector':None},'waveform':None}
    settings={'rows':[{'id':'baseline','values':[baseline]},{'id':'higher','values':[baseline+.5]}],'scope':'finite_catalog'}
    budget=study_budget();design=generate_design('scenario_response',[factor],settings,budget=budget)
    numeric={'method':h1['method'],'scope':'actual_points','solver_levels':[{key:load_document(p)['solver'][key] for key in SOLVER_FIELDS} for p in h1_protocols],
             'comparison_times':h1['comparison_times'],'outputs':deepcopy(h1['outputs']),'obligations':deepcopy(h1['obligations']),
             'observables':[],'checks':[],'math_budget':dict(DEFAULT_MATH_BUDGET),'budget':deepcopy(h1['budget']),
             'claim_limit':'SYNTHETIC three-level infrastructure numerical comparison; no actual solution-error or physical validity claim.'}
    mapping=protocol['mapping_validation'];target=next(t for t in mapping['mapping_snapshot']['targets'] if t['id']==protocol['target_id'])
    from numerical_obligations import numeric_context_from_documents
    context=numeric_context_from_documents(load_document(protocol['model_path']),protocol,load_document(protocol['parameters_path']))
    variables={v['id']:v for v in context['variables']}
    criteria={key:numeric['outputs'][0][key] for key in ('absolute_tolerance','relative_tolerance','contraction_limit','roundoff_floor')}
    for block in mapping['build_spec']['blocks']:
        if block['type']!='Integrator':continue
        matches=[t['subject_id'] for t in target['traces'] if t['kind']=='variable' and t['disposition']=='mapped' and block['id'] in t['block_ids'] and 'state' in variables[t['subject_id']]['roles']]
        assert len(matches)==1,'Synthetic state fixture requires the exact existing D Integrator/C state trace.'
        identity=matches[0]
        if not any(o.get('kind')=='state' and o.get('variable_id')==identity and o.get('block_path')==block['path'] for o in numeric['outputs']):
            numeric['outputs'].append({'kind':'state','variable_id':identity,'block_path':block['path'],'unit':variables[identity]['unit'],**criteria})
    output=protocol['run_spec']['outputs'][0]
    metric={'statistic':'final','unit':output['unit'],'kind':'output','output_port':output['port'],'variable_id':None,
            'block_path':None,'window':None,'event':None,'event_index':None,'check':None}
    value={'schema_version':1,'project_id':primary['project_id'],'status':'draft',
           'base_protocol':file_ref(root,Path(protocol['contract_path'])),'base_receipt':file_ref(root,Path(primary['primary_receipt_path'])),
           'primary_numerical_receipt':file_ref(root,primary_h1_receipt),'factors':[factor],'method':'scenario_response','settings':settings,
           'design':design,'metric':metric,'numerical_policy':numeric,'inference':{'method':'none'},
           'criterion':{'quantity':'all_points','result_selector':None,'lower':None,'upper':upper,'unit':metric['unit'],
                        'failure_disposition':'modify','reason':'Prior bound on the exact finite hypothetical response catalog.'},
           'sources':[],'settings_source_ref':None,'budget':budget,
           'claim_limit':'SYNTHETIC INFRASTRUCTURE TEST ONLY. This finite hypothetical parameter study adopts no values or primary result.',
           'review_record':None}
    path=write_contract(root/filename,value)
    return review_h_analysis_study(path,project_root=root)


def make_study_history(study_path,*,project_root=None,output_name='synthetic-study-evidence',h_profile=None):
    """Build full native-format history and consume it with unmocked readers.

    This is a CI fixture writer. Its closed-form state oracle is independent of
    the production sampler, H1 estimator, and study metric computation.
    It never runs MATLAB or qualifies any real runtime.
    """
    from datetime import datetime,timedelta,timezone
    import math
    import uuid

    import h_analysis_trial as native
    from h_analysis_native_factory import make_h_analysis_profile,synthetic_native_case
    from h_analysis_study import INPUT_NAME,OPERATION,RECEIPT_NAME,RESULT_NAME,assess_study
    from probe_environment import write_json
    from run_h_analysis_study import collect_batch_points,execution_record
    from runtime_common import canonical_digest,sha256_file
    from validate_environment import _time,utc_text
    from validate_h_analysis_study import validate_h_analysis_study
    from validate_h_analysis_trial_receipt import assess_trial_request,validate_h_analysis_trial_receipt
    from validate_h_analysis_study_receipt import validate_h_analysis_study_receipt
    from verification_common import source_identities

    study_path=Path(study_path).resolve();root=Path(project_root or study_path.parent).resolve()
    report=validate_h_analysis_study(study_path,project_root=root,require_reviewed=True)
    assert report['valid'] and report['study_ready'],report['errors']+report['missing_gates']
    assert report['method']!='failure_boundary','Synthetic history helper serves fixed designs; actual native driver owns adaptive searches.'
    a=root/'a-profile'/'evidence'/'profile.json';e=root/'numerical-e-profile'/'simulation-profile.json'
    if h_profile is None:h_profile=make_h_analysis_profile(root/'synthetic-h-profile',a,e)
    output=root/output_name;output.mkdir()
    study_request={'schema_version':1,'operation_id':OPERATION,'run_id':str(uuid.uuid4()),'project_id':report['project_id'],
                   'project_root':str(root),'study':{'path':str(study_path),'sha256':report['contract_sha256']},
                   'semantic_sha256':report['semantic_sha256'],'contract_snapshot':report['_contract'],
                   'contract_original_text':study_path.read_bytes().decode('utf-8'),'design':report['design'],
                   'input_manifest':report['input_manifest'],'sources':source_identities()}
    write_json(output/INPUT_NAME,study_request)
    batch=output/'trial-batch-000001'
    request=native.make_task_request(study_path,load_document(a)['runtime']['executable'],batch,report,
                                    environment_profile=a,simulation_profile=e,h_analysis_profile=h_profile,project_root=root)
    batch.mkdir();names=native.contract()['evidence'];write_json(batch/names['input'],request)
    (batch/names['log']).write_text('SYNTHETIC INFRASTRUCTURE TEST. NO MATLAB EXECUTION OR REAL QUALIFICATION.\n',encoding='utf-8')
    # Reuse runtime installation identities from the independently checked
    # synthetic H probe, rather than manufacture a successful report object.
    raw=deepcopy(load_document(Path(h_profile).parent/names['raw']))
    qualification_floor=max(_time(load_document(h_profile)['captured_at']),_time(load_document(Path(h_profile).parent/names['profile_receipt'])['process']['finished_at']))
    actuals=[]
    for case in request['cases']:
        parameters={p['code_name']:float(p['value']) for p in case['run_spec']['parameters']}
        decay,forcing=parameters['a'],parameters['b']
        inputs=case['run_spec']['inputs'];assert len(inputs)==1 and len(set(inputs[0]['values']))==1
        command=float(inputs[0]['values'][0]);initial=case['initial_conditions'];assert len(initial)==1
        state_id=initial[0]['variable_id'];start=case['run_spec']['start_time'];x0=initial[0]['value']
        def oracle(t,k=decay,b=forcing,u=command,x=x0,id=state_id,t0=start):
            steady=b*u/k
            return {id:steady+(x-steady)*math.exp(-k*(t-t0))}
        actual=synthetic_native_case(case,batch/'cases'/case['case_id'],request['run_id'],state_values=oracle,not_before=qualification_floor)
        actual['functions']=deepcopy(raw['functions']);actuals.append(actual)
    start=min(_time(x['started_at']) for x in actuals);stop=max(_time(x['finished_at']) for x in actuals)
    raw.update(schema_version=1,run_id=request['run_id'],channel=request['channel'],host_fingerprint=request['host_fingerprint'],
               input_identity=request['input_identity'],source_identity=request['source_identity'],status='completed',
               started_at=utc_text(start-timedelta(milliseconds=1)),finished_at=utc_text(stop+timedelta(milliseconds=1)),cases=actuals)
    process={'process_state':'completed','exit_code':0,'pid':0,'command':['SYNTHETIC H STUDY FORMAT ONLY; NO MATLAB'],
             'started_at':utc_text(start-timedelta(milliseconds=2)),'finished_at':utc_text(stop+timedelta(milliseconds=2)),
             'execution_timeout':request['budget']['process_timeout']}
    write_json(batch/names['raw'],raw);write_json(batch/names['process'],process)
    assessment=assess_trial_request(request,raw,batch,report)
    trial_receipt={'schema_version':1,'run_id':request['run_id'],'project_id':report['project_id'],'study_semantic_sha256':report['semantic_sha256'],
                   'sources':request['sources'],'process':process,'runtime':native.observed_runtime(raw,request),
                   'protected_files':request['bindings']['protected_files'],'artifacts':native.artifact_manifest(batch),
                   'numeric_results':assessment['numeric_results'],'status':'completed' if assessment['complete'] else 'incomplete','errors':assessment['errors']}
    trial_path=batch/names['run_receipt'];write_json(trial_path,trial_receipt)
    trial_report=validate_h_analysis_trial_receipt(trial_path,project_root=root,study_report=report)
    assert trial_report['valid'] and trial_report['trial_complete'],trial_report['errors']
    points=collect_batch_points(report,report['design'],trial_report);computed=assess_study(report,points)
    write_json(output/RESULT_NAME,{'schema_version':1,'run_id':study_request['run_id'],'result':computed,'errors':[]})
    parent_start=utc_text(start-timedelta(milliseconds=3));parent_finish=utc_text(stop+timedelta(milliseconds=3))
    batch_start=utc_text(start-timedelta(milliseconds=2));batch_finish=utc_text(stop+timedelta(milliseconds=2))
    execution=execution_record([{'index':1,'design_sha256':canonical_digest(request['bindings']['design']),
              'group_count':len(request['groups']),'case_count':len(request['cases']),'attempted_case_count':len(actuals),
              'started_at':batch_start,'finished_at':batch_finish,
              'elapsed_before':(_time(batch_start)-_time(parent_start)).total_seconds(),
              'elapsed_after':(_time(batch_finish)-_time(parent_start)).total_seconds(),
              'process_timeout_limit':report['budget']['total_timeout']-.001,'status':'complete','errors':[]}],parent_start,parent_finish)
    receipt={'schema_version':1,'operation_id':OPERATION,'run_id':study_request['run_id'],'project_id':report['project_id'],'project_root':str(root),
             'started_at':parent_start,'finished_at':parent_finish,'execution':execution,
             'study':study_request['study'],'semantic_sha256':report['semantic_sha256'],'input_identity':canonical_digest(study_request),
             'sources':study_request['sources'],'trial_receipts':[{'path':str(trial_path),'sha256':sha256_file(trial_path)}],
             'input_manifest':study_request['input_manifest'],'status':'complete','errors':[],
             'artifacts':{key:{'file':filename,'sha256':sha256_file(output/filename)} for key,filename in [('input',INPUT_NAME),('result',RESULT_NAME)]}}
    path=output/RECEIPT_NAME;write_json(path,receipt)
    result=validate_h_analysis_study_receipt(path,project_root=root,study_report=report)
    assert result['valid'] and result['study_complete'] and result['defined'],result['errors']
    return path
