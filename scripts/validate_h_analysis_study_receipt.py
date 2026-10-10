"""Independently replay a native H study; never grant execution or write state."""
from __future__ import annotations

import argparse
from datetime import datetime,timezone
from pathlib import Path

from uncertainty_metrics import exact, real
from h_analysis_study import (INPUT_NAME, OPERATION, RECEIPT_NAME, RESULT_NAME, assess_study,
                              replay_boundary, typed_equal)
from run_h_analysis_study import collect_batch_points
from runtime_common import canonical_digest, contained_path, emit, load_contract, schema_errors
from validate_h_analysis_study import validate_h_analysis_study
from verification_common import (HARD_BUDGET,assert_unchanged,evidence_paths,input_manifest,limited_document,source_identities)


def validate_execution_ledger(receipt,budget,children):
    """Verify independently bound child counts and actual serial intervals."""
    execution=receipt['execution']
    exact(execution,('batch_count','group_count','case_count','attempted_case_count','total_elapsed_seconds','batches'),'study execution ledger')
    batches=execution['batches']
    if not isinstance(batches,list) or len(batches)!=len(children) or len(batches)!=len(receipt['trial_receipts']):
        raise ValueError('complete study batch/count ledger differs from native bindings')
    parent_start,parent_finish=(datetime.fromisoformat(receipt[k]) for k in ('started_at','finished_at'))
    actual_total=(parent_finish-parent_start).total_seconds()
    if real(execution['total_elapsed_seconds'],'total study elapsed')!=actual_total:raise ValueError('actual total study duration differs from parent timestamps')
    counts={'batch_count':len(batches),'group_count':0,'case_count':0,'attempted_case_count':0};previous=parent_start
    infrastructure_complete=True
    for i,(entry,child) in enumerate(zip(batches,children),1):
        exact(entry,('index','design_sha256','group_count','case_count','attempted_case_count','started_at','finished_at','elapsed_before','elapsed_after','process_timeout_limit','status','errors'),'study batch ledger')
        if type(entry['index']) is not int or entry['index']!=i:raise ValueError('study batch ledger index/order differs')
        request,raw,native_receipt,native=child
        if entry['design_sha256']!=canonical_digest(request['bindings']['design']):raise ValueError('study ledger native design identity differs')
        actual={'group_count':len(request['groups']),'case_count':len(request['cases']),
                'attempted_case_count':sum(case.get('attempted',True) is True for case in raw['cases'])}
        for key,value in actual.items():
            if type(entry[key]) is not int or entry[key]!=value:raise ValueError('actual study native count differs: '+key)
            counts[key]+=value
        begin,end=(datetime.fromisoformat(entry[k]) for k in ('started_at','finished_at'))
        process=native_receipt['process'];process_begin,process_end=(datetime.fromisoformat(process[k]) for k in ('started_at','finished_at'))
        if any(t.tzinfo is None for t in (begin,end,process_begin,process_end)) or not previous<=begin<=process_begin<=process_end<=end<=parent_finish:
            raise ValueError('actual child process interval must be inside parent batch and serial study order')
        previous=end
        before,after=(begin-parent_start).total_seconds(),(end-parent_start).total_seconds()
        if real(entry['elapsed_before'],'elapsed before batch')!=before or real(entry['elapsed_after'],'elapsed after batch')!=after:
            raise ValueError('study elapsed-before/after ledger differs from actual timestamps')
        timeout=real(entry['process_timeout_limit'],'remaining parent process timeout')
        actual_timeout=real(process.get('execution_timeout'),'actual child process timeout')
        # Timestamp capture and monotonic-clock reads can differ by microseconds.
        # A one millisecond allowance covers serialization only, never runtime.
        if timeout<=0 or timeout>budget['total_timeout']-before+.001 or actual_timeout<=0 or actual_timeout>min(timeout,budget['process_timeout'],budget['total_timeout']-(process_begin-parent_start).total_seconds())+.001:
            raise ValueError('actual child timeout exceeds lower-only remaining parent/source cap')
        expected_status='complete' if native.get('valid') and native.get('trial_complete') else 'incomplete'
        if entry['status']!=expected_status or not typed_equal(entry['errors'],native.get('errors',[])):
            raise ValueError('study native batch status/error ledger differs from independent readback')
        if not isinstance(entry['errors'],list) or any(not isinstance(e,str) for e in entry['errors']):raise ValueError('typed native batch errors required')
        infrastructure_complete &= expected_status=='complete' and not entry['errors'] and after<=budget['total_timeout']
    for key,value in counts.items():
        if type(execution[key]) is not int or execution[key]!=value:raise ValueError('study aggregate execution count differs: '+key)
    if counts['batch_count']>budget['max_iterations'] or counts['group_count']>min(budget['max_groups'],budget['max_points']) or counts['case_count']>budget['max_cases']:
        raise ValueError('actual complete native batch/group/case budget exceeded')
    infrastructure_complete &= actual_total<=budget['total_timeout']
    if not infrastructure_complete and (receipt['status']!='incomplete' or not receipt['errors']):
        raise ValueError('incomplete/timed-out native history requires preserved parent status/errors')
    return infrastructure_complete


def validate_h_analysis_study_receipt(path,*,project_root=None,study_report=None):
    path=Path(path).resolve()
    result={'valid':False,'study_complete':False,'study_accepted':False,'defined':False,'result':None,'method':None,'metric':None,
            'project_id':None,'receipt_path':str(path),'receipt_sha256':None,'contract_path':None,'contract_sha256':None,'semantic_sha256':None,
            'primary_numerical_receipt_path':None,'primary_numerical_receipt_sha256':None,
            'bound_files':[],'input_manifest':[],'allowed_external':[],'environment_checked':False,'execution_allowed':False,'errors':[]}
    try:
        if path.name!=RECEIPT_NAME:raise ValueError('unexpected H study receipt filename')
        bootstrap=input_manifest([path],path.parent,HARD_BUDGET)
        receipt=limited_document(path)
        fields={'schema_version','operation_id','run_id','project_id','project_root','started_at','finished_at','study','semantic_sha256',
                'input_identity','sources','trial_receipts','input_manifest','status','errors','artifacts','execution'}
        if set(receipt)!=fields or type(receipt['schema_version']) is not int or receipt['schema_version']!=1 or receipt['operation_id']!=OPERATION:
            raise ValueError('exact typed H study receipt fields/version/operation required')
        if not isinstance(receipt['run_id'],str) or not receipt['run_id'] or not isinstance(receipt['project_root'],str):raise ValueError('typed nonempty study run/root identity required')
        if receipt['status'] not in ('complete','incomplete') or not isinstance(receipt['errors'],list) or any(not isinstance(e,str) for e in receipt['errors']):raise ValueError('typed status and preserved error ledger required')
        root=Path(receipt['project_root']).resolve()
        if project_root is not None and root!=Path(project_root).resolve():raise ValueError('study receipt explicit project root differs')
        if not path.is_relative_to(root):raise ValueError('study receipt leaves project root')
        stamps=[datetime.fromisoformat(receipt[k]) for k in ('started_at','finished_at')]
        if any(t.tzinfo is None for t in stamps) or not stamps[0]<=stamps[1]<=datetime.now(timezone.utc):raise ValueError('invalid study timestamp ordering')
        binding=receipt['study']
        if not isinstance(binding,dict) or set(binding)!={'path','sha256'}:raise ValueError('exact study file binding required')
        contract_path=contained_path(root,binding['path']);contract_bootstrap=input_manifest([contract_path],root,HARD_BUDGET)
        contract=limited_document(contract_path)
        issues=schema_errors(contract,load_contract('core/h_analysis_study.schema.yaml'))
        if issues or contract['budget'] is None or any(type(v) is not int for v in contract['budget'].values()):raise ValueError('current typed source-declared study schema/budget required')
        budget=contract['budget']
        if not isinstance(receipt['artifacts'],dict) or set(receipt['artifacts'])!={'input','result'}:raise ValueError('exact study owned artifact set required')
        for key,name in [('input',INPUT_NAME),('result',RESULT_NAME)]:
            artifact=receipt['artifacts'][key]
            if not isinstance(artifact,dict) or set(artifact)!={'file','sha256'} or artifact['file']!=name:raise ValueError('study artifact binding fields/name differ')
        if (path.parent/RESULT_NAME).stat().st_size>budget['max_result_bytes']:raise ValueError('persisted complete result exceeds result-byte budget')
        paths=evidence_paths([path],root,budget,root_contexts={path:'h_study_receipt'})
        paths.update([contract_path,path.parent/INPUT_NAME,path.parent/RESULT_NAME])
        complete_manifest=input_manifest(paths,root,budget)
        verified={i['path']:i for i in complete_manifest}
        if verified[str(contract_path)]['sha256']!=binding['sha256']:raise ValueError('reviewed study bytes changed')
        for key,artifact in receipt['artifacts'].items():
            if verified[str(path.parent/artifact['file'])]['sha256']!=artifact['sha256']:raise ValueError('study owned artifact bytes changed')
        initial_sources=source_identities()
        if not typed_equal(receipt['sources'],initial_sources):raise ValueError('study safety closure changed')
        report=validate_h_analysis_study(contract_path,project_root=root,require_reviewed=True)
        if not report['valid'] or not report['study_ready']:raise ValueError('current reviewed executable study required: '+'; '.join(report['errors']+report['missing_gates']))
        if study_report is not None and any(not typed_equal(study_report.get(k),report.get(k)) for k in ('project_id','contract_path','contract_sha256','semantic_sha256','input_manifest')):
            raise ValueError('supplied study report differs from independently read current evidence')
        request=limited_document(path.parent/INPUT_NAME,budget)
        expected={'schema_version','operation_id','run_id','project_id','project_root','study','semantic_sha256','contract_snapshot',
                  'contract_original_text','design','input_manifest','sources'}
        if set(request)!=expected or type(request['schema_version']) is not int or request['schema_version']!=1 or request['operation_id']!=OPERATION:raise ValueError('exact study request fields/version/operation required')
        if canonical_digest(request)!=receipt['input_identity']:raise ValueError('captured study input identity differs')
        for key in ('run_id','project_id','project_root','study','semantic_sha256','sources','input_manifest'):
            if not typed_equal(request[key],receipt[key]):raise ValueError('study input/receipt identity differs: '+key)
        if request['project_id']!=report['project_id'] or request['semantic_sha256']!=report['semantic_sha256'] or not typed_equal(request['contract_snapshot'],report['_contract']) or request['contract_original_text'].encode('utf-8')!=contract_path.read_bytes():raise ValueError('full original reviewed study differs from captured text/snapshot')
        if not typed_equal(request['design'],report['design']) or not typed_equal(request['input_manifest'],report['input_manifest']):raise ValueError('captured complete design/source read set differs')
        if not isinstance(receipt['trial_receipts'],list):raise ValueError('ordered native receipt bindings required')
        from validate_h_analysis_trial_receipt import validate_h_analysis_trial_receipt
        points=[];native_reports=[];children=[];seen=set()
        next_design=report['design'];current_state=None;state_seen=False
        for batch_index,item in enumerate(receipt['trial_receipts']):
            if not isinstance(item,dict) or set(item)!={'path','sha256'}:raise ValueError('exact native trial receipt file binding required')
            file=contained_path(root,item['path'])
            if file in seen or file.parent!=path.parent/f'trial-batch-{batch_index+1:06d}':raise ValueError('trial batch ownership/order/duplicate differs')
            seen.add(file)
            if verified[str(file)]['sha256']!=item['sha256']:raise ValueError('bound trial receipt bytes changed')
            native=validate_h_analysis_trial_receipt(file,project_root=root,study_report=report)
            native_reports.append(native)
            if not native.get('valid'):raise ValueError('native trial identity/readback failed: '+'; '.join(native.get('errors',[])))
            # Independently read the bounded captured trial request to verify
            # its exact adaptive override; this is not trusted from result JSON.
            trial_request=limited_document(file.parent/'h-analysis-input.json',budget)
            from h_analysis_trial import contract as trial_contract
            trial_raw=limited_document(file.parent/trial_contract()['evidence']['raw'],budget)
            trial_receipt=limited_document(file,budget)
            children.append((trial_request,trial_raw,trial_receipt,native))
            child_state=trial_request['bindings'].get('current_state')
            if state_seen and not typed_equal(current_state,child_state):raise ValueError('explicit caller current-state binding differs between study batches')
            current_state=child_state;state_seen=True
            actual_design=trial_request['bindings']['design']
            if not typed_equal(actual_design,next_design):raise ValueError('native batch design differs from frozen/replayed next design')
            points.extend(collect_batch_points(report,next_design,native))
            if report['method']!='failure_boundary':
                if batch_index!=0 or len(receipt['trial_receipts'])!=1:raise ValueError('fixed design requires exactly one native batch')
            else:
                replay=replay_boundary(report,points)
                if replay['next_row'] is None:
                    if batch_index!=len(receipt['trial_receipts'])-1:raise ValueError('additional native boundary points after stopping condition')
                else:
                    from h_analysis_study import design_record
                    next_design=design_record('failure_boundary',report['factors'],[replay['next_row']],
                                              {'algorithm':'ordered_bracket_bisection_v1','adaptive':True,'prefix_points':len(points)})
        infrastructure_complete=validate_execution_ledger(receipt,budget,children)
        stored=limited_document(path.parent/RESULT_NAME,budget)
        if set(stored)!={'schema_version','run_id','result','errors'} or type(stored['schema_version']) is not int or stored['schema_version']!=1 or stored['run_id']!=receipt['run_id'] or not typed_equal(stored['errors'],receipt['errors']):raise ValueError('study result wrapper fields/error ledger differ')
        computed=assess_study(report,points)
        if stored['result'] is not None and not typed_equal(stored['result'],computed):raise ValueError('study result differs from native numeric/metric/design/algorithm recomputation')
        if receipt['status']=='complete' and (receipt['errors'] or stored['result'] is None):raise ValueError('complete infrastructure receipt cannot hide errors/missing result')
        if receipt['status']=='incomplete' and not receipt['errors']:raise ValueError('incomplete preserved study requires an explicit error ledger')
        infrastructure_complete &= receipt['status']=='complete' and not receipt['errors'] and stored['result'] is not None
        assert_unchanged(complete_manifest);assert_unchanged(bootstrap);assert_unchanged(contract_bootstrap)
        if not typed_equal(source_identities(),initial_sources):raise ValueError('safety source changed during study historical read')
        result.update(valid=True,study_complete=infrastructure_complete and computed['study_complete'],study_accepted=infrastructure_complete and computed['study_accepted'],defined=infrastructure_complete and computed['defined'],result=computed,
                      infrastructure_complete=infrastructure_complete,execution=receipt['execution'],current_state=current_state,errors=list(receipt['errors']),
                      analysis=computed['analysis'],disposition=computed['disposition'] if infrastructure_complete else 'incomplete',method=report['method'],metric=report['metric'],
                      project_id=report['project_id'],project_root=str(root),contract_path=str(contract_path),contract_sha256=report['contract_sha256'],
                      semantic_sha256=report['semantic_sha256'],receipt_sha256=verified[str(path)]['sha256'],
                      primary_numerical_receipt_path=report['primary_numerical_report']['receipt_path'],
                      primary_numerical_receipt_sha256=report['primary_numerical_report']['receipt_sha256'],
                      base_protocol_report=report['base_protocol_report'],base_simulation_report=report['base_simulation_report'],
                      primary_numerical_report=report['primary_numerical_report'],required_A_operations=report['required_A_operations'],
                      bound_files=complete_manifest,input_manifest=complete_manifest,allowed_external=sorted(map(str,paths.allowed_external)),
                      trial_reports=native_reports,budget=budget)
        for name in ('problem','model','approval','mapping','parameters','native_model','implementation_receipt'):
            for suffix in ('path','sha256'):result[name+'_'+suffix]=report.get(name+'_'+suffix)
    except (OSError,ValueError,KeyError,TypeError,AttributeError,OverflowError,ZeroDivisionError,StopIteration) as error:
        result['errors'].append(type(error).__name__+': '+str(error))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('path',type=Path);parser.add_argument('--project-root',type=Path)
    args=parser.parse_args();result=validate_h_analysis_study_receipt(args.path,project_root=args.project_root)
    emit({k:v for k,v in result.items() if not k.startswith('_')});return 0 if result['valid'] and result['study_complete'] else 1


if __name__=='__main__':raise SystemExit(main())
