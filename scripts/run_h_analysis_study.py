"""Execute a reviewed hypothetical study in new owned evidence directories."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime,timezone
import json
from pathlib import Path
import time
import uuid

from h_analysis_study import (INPUT_NAME, OPERATION, RECEIPT_NAME, RESULT_NAME, assess_point,
                              assess_study, design_record, replay_boundary)
from runtime_common import canonical_digest, emit, sha256_file
from validate_h_analysis_study import validate_h_analysis_study
from verification_common import (assert_unchanged,evidence_paths_for_request,input_manifest,limited_document,
                                 source_identities,typed_equal)


def json_bytes(value):return (json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n').encode('utf-8')


def write_json(path,value):path.write_bytes(json_bytes(value))


def collect_batch_points(report,design,trial_report):
    groups=trial_report.get('groups',[])
    if not isinstance(groups,list):raise ValueError('native trial consumer must return a group ledger')
    by_id={group['point_id']:group for group in groups}
    if len(by_id)!=len(groups):raise ValueError('native consumer returned duplicate point identities')
    if not set(by_id)<={row['id'] for row in design['rows']}:raise ValueError('native consumer returned an undeclared point')
    points=[]
    for row in design['rows']:
        group=by_id.get(row['id']);levels=[] if group is None else group.get('levels',[])
        if trial_report.get('valid') and group is not None and group.get('complete',True) and len(levels)==3:
            point=assess_point(report,row,group);point['status']='complete' if point['numeric'].get('complete') else 'failed'
            points.append(point);continue
        status='unattempted' if group is None or group.get('status')=='unattempted' or group.get('attempted') is False else 'failed'
        errors=['native group absent; declared occurrence unattempted'] if group is None else list(group.get('errors',trial_report.get('errors',[])))
        if not trial_report.get('valid'):errors.append('native identity/readback invalid; no point metric accepted')
        points.append({'point_id':row['id'],'factor_values':deepcopy(row['values']),'role':deepcopy(row['role']),
                       'physical_sha256':None if group is None else group.get('physical_sha256'),'accepted':False,'status':status,
                       'numeric':{'complete':False,'numerically_verified':False,'errors':errors},
                       'metric':{'defined':False,'value':None,'unit':report['metric']['unit'],'errors':['incomplete actual native triplet']},
                       'timing_info':[deepcopy(level.get('timing_info')) for level in levels]})
    return points


def execution_record(batches,started_at,finished_at):
    return {'batch_count':len(batches),'group_count':sum(b['group_count'] for b in batches),
            'case_count':sum(b['case_count'] for b in batches),'attempted_case_count':sum(b['attempted_case_count'] for b in batches),
            'total_elapsed_seconds':(datetime.fromisoformat(finished_at)-datetime.fromisoformat(started_at)).total_seconds(),
            'batches':batches}


def run_h_analysis_study(study_path,executable,output_dir,*,environment_profile,simulation_profile,h_analysis_profile,
                         project_root=None,required_operations=None,state_binding=None):
    started_at=datetime.now(timezone.utc).isoformat();clock_start=time.monotonic()
    from h_analysis_trial import run_h_analysis_trials
    output=Path(output_dir).resolve()
    if output.exists():raise ValueError('H analysis study requires a new evidence directory')
    sources=source_identities()
    report=validate_h_analysis_study(study_path,project_root=project_root,require_reviewed=True)
    if not report['valid'] or not report['execution_ready']:raise ValueError('H study blocked: '+'; '.join(report['errors']+report['missing_gates']))
    root=Path(report['project_root']);contract=Path(report['contract_path']);budget=report['budget']
    if not output.is_relative_to(root):raise ValueError('H study output leaves project root')
    if any(Path(item['path']).is_relative_to(output) for item in report['input_manifest']):raise ValueError('study output would own a source input')
    request={'schema_version':1,'operation_id':OPERATION,'run_id':str(uuid.uuid4()),'project_id':report['project_id'],
             'project_root':str(root),'study':{'path':str(contract),'sha256':report['contract_sha256']},
             'semantic_sha256':report['semantic_sha256'],'contract_snapshot':report['_contract'],
             'contract_original_text':contract.read_bytes().decode('utf-8'),'design':report['design'],
             'input_manifest':report['input_manifest'],'sources':sources}
    # Profiles and their independently bound receipts are native-request
    # authority. Study request preflight binds reviewed sources before writes.
    initial=input_manifest(evidence_paths_for_request(request,root,budget,role='h_study_request'),root,budget)
    if len(json_bytes(request))>budget['max_file_bytes']:raise ValueError('study captured input exceeds reviewed file budget')
    output.mkdir(parents=True,exist_ok=False);write_json(output/INPUT_NAME,request)
    trials=[];points=[];errors=[];result=None;batches=[]
    try:
        assert_unchanged(initial)
        design=deepcopy(report['design'])
        iteration=0
        while True:
            remaining=budget['total_timeout']-(time.monotonic()-clock_start)
            if remaining<=0:
                errors.append('declared total study timeout exhausted before next native batch');break
            if iteration>=budget['max_iterations']:
                errors.append('declared study batch iteration budget exhausted');break
            if sum(x['group_count'] for x in batches)+len(design['rows'])>budget['max_groups'] or sum(x['case_count'] for x in batches)+3*len(design['rows'])>budget['max_cases']:
                errors.append('declared aggregate study group/case budget exhausted');break
            directory=output/f'trial-batch-{iteration+1:06d}'
            batch_start=datetime.now(timezone.utc).isoformat()
            trial=run_h_analysis_trials(contract,executable,directory,environment_profile=environment_profile,
                                        simulation_profile=simulation_profile,h_analysis_profile=h_analysis_profile,
                                        project_root=root,required_operations=required_operations,design_override=design,
                                        process_timeout_limit=remaining,state_binding=state_binding)
            batch_finish=datetime.now(timezone.utc).isoformat()
            receipt_path=Path(trial.get('receipt_path') or directory/'h-analysis-trial-receipt.json').resolve()
            if not receipt_path.is_file():raise ValueError('native producer returned no preserved trial receipt')
            trials.append({'path':str(receipt_path),'sha256':sha256_file(receipt_path)})
            child_request=limited_document(directory/'h-analysis-input.json',budget)
            from h_analysis_trial import contract as trial_contract
            raw=limited_document(directory/trial_contract()['evidence']['raw'],budget)
            attempted=sum(record.get('attempted',True) is True for record in raw.get('cases',[]))
            batches.append({'index':iteration+1,'design_sha256':canonical_digest(design),'group_count':len(child_request['groups']),
                            'case_count':len(child_request['cases']),'attempted_case_count':attempted,
                            'started_at':batch_start,'finished_at':batch_finish,
                            'elapsed_before':(datetime.fromisoformat(batch_start)-datetime.fromisoformat(started_at)).total_seconds(),
                            'elapsed_after':(datetime.fromisoformat(batch_finish)-datetime.fromisoformat(started_at)).total_seconds(),
                            'process_timeout_limit':remaining,'status':'complete' if trial.get('valid') and trial.get('trial_complete') else 'incomplete',
                            'errors':deepcopy(trial.get('errors',[]))})
            observed=collect_batch_points(report,design,trial);points.extend(observed);iteration+=1
            if time.monotonic()-clock_start>budget['total_timeout'] or batches[-1]['elapsed_after']>budget['total_timeout']:
                errors.append('declared total study timeout exhausted after native batch');break
            if not trial.get('valid') or not trial.get('trial_complete'):
                errors.extend('native trial: '+e for e in trial.get('errors',[]))
                errors.append('native trial incomplete; all declared failed/unattempted points preserved');break
            if report['method']!='failure_boundary':break
            replay=replay_boundary(report,points)
            next_row=replay['next_row']
            if next_row is None:break
            if any(not p['accepted'] for p in observed):
                errors.append('boundary native/numeric point failure; preserve verified prefix');break
            design=design_record('failure_boundary',report['factors'],[next_row],
                                 {'algorithm':'ordered_bracket_bisection_v1','adaptive':True,'prefix_points':len(points)})
        result=assess_study(report,points)
        assert_unchanged(initial)
        if not typed_equal(source_identities(),sources):raise ValueError('study safety source changed during execution')
    except (OSError,ValueError,KeyError,TypeError,AttributeError,OverflowError,ZeroDivisionError) as error:
        errors.append(type(error).__name__+': '+str(error))
    if time.monotonic()-clock_start>budget['total_timeout']:
        errors.append('declared total study timeout exhausted at completion')
    result_record={'schema_version':1,'run_id':request['run_id'],'result':result,'errors':errors}
    if len(json_bytes(result_record))>budget['max_result_bytes']:
        # No truncation: preserve all point records in the native ledger and
        # retain an explicit failed result rather than manufacture a summary.
        errors.append('complete study result exceeds reviewed result-byte budget');result=None
        result_record={'schema_version':1,'run_id':request['run_id'],'result':None,'errors':errors}
    write_json(output/RESULT_NAME,result_record)
    finished_at=datetime.now(timezone.utc).isoformat()
    execution=execution_record(batches,started_at,finished_at)
    if execution['total_elapsed_seconds']>budget['total_timeout'] and not any('timeout exhausted' in e for e in errors):
        errors.append('declared total study timeout exhausted at persistence')
        result_record['errors']=errors;write_json(output/RESULT_NAME,result_record)
    receipt={'schema_version':1,'operation_id':OPERATION,'run_id':request['run_id'],'project_id':report['project_id'],
             'project_root':str(root),'started_at':started_at,'finished_at':finished_at,'execution':execution,
             'study':request['study'],'semantic_sha256':report['semantic_sha256'],'input_identity':canonical_digest(request),
             'sources':sources,'trial_receipts':trials,'input_manifest':request['input_manifest'],
             'status':'complete' if result is not None and not errors else 'incomplete','errors':errors,
             'artifacts':{key:{'file':filename,'sha256':sha256_file(output/filename)} for key,filename in [('input',INPUT_NAME),('result',RESULT_NAME)]}}
    write_json(output/RECEIPT_NAME,receipt)
    from validate_h_analysis_study_receipt import validate_h_analysis_study_receipt
    return validate_h_analysis_study_receipt(output/RECEIPT_NAME,project_root=root,study_report=report)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('study_path',type=Path);parser.add_argument('--matlab-executable',required=True,type=Path)
    parser.add_argument('--output-dir',required=True,type=Path);parser.add_argument('--environment-profile',required=True,type=Path)
    parser.add_argument('--simulation-profile',required=True,type=Path);parser.add_argument('--h-analysis-profile',required=True,type=Path)
    parser.add_argument('--project-root',type=Path);parser.add_argument('--require-operation',action='append',default=[])
    parser.add_argument('--current-state',type=Path);parser.add_argument('--current-state-sha256')
    args=parser.parse_args()
    try:
        if (args.current_state is None)!=(args.current_state_sha256 is None):raise ValueError('explicit current state path and SHA must be supplied together')
        state_binding=None if args.current_state is None else {'path':str(args.current_state),'sha256':args.current_state_sha256}
        result=run_h_analysis_study(args.study_path,args.matlab_executable,args.output_dir,environment_profile=args.environment_profile,
                                  simulation_profile=args.simulation_profile,h_analysis_profile=args.h_analysis_profile,project_root=args.project_root,
                                  required_operations=args.require_operation,state_binding=state_binding)
    except (OSError,ValueError) as error:
        result={'valid':False,'study_complete':False,'study_accepted':False,'defined':False,'errors':[str(error)]}
    emit({k:v for k,v in result.items() if not k.startswith('_')});return 0 if result['valid'] and result['study_complete'] else 1


if __name__=='__main__':raise SystemExit(main())
