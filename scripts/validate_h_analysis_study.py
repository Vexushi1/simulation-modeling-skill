"""Read-only source/review gate for a hypothetical H study, before native trials."""
from __future__ import annotations

import argparse
from pathlib import Path

from h_analysis_study import (METHODS, NATIVE_BUDGET_FIELDS, SETTINGS_FIELDS, UNCERTAINTY_METHODS,
                              analysis_selector_unit, generate_design, materialize_manifest, validate_design, validate_factor_records)
from numerical_obligations import numeric_context_from_documents, validate_trial_numeric_policy
from numerical_math_common import validate_metric_policy
from runtime_common import emit, load_contract, schema_errors, sha256_file
from uncertainty_metrics import real, validate_uncertainty_inference
from validate_simulation_protocol import validate_simulation_protocol
from validate_simulation_receipt import validate_simulation_receipt
from validate_numerical_verification_receipt import validate_numerical_verification_receipt
from verification_common import (HARD_BUDGET, assert_unchanged, bind_sources, checked_binding, evidence_paths,
                                 input_manifest, limited_document, semantic_digest, source_snapshot,
                                 typed_equal, validate_review)


def _initial_value(value,parameters):
    from h_analysis_trial import resolve_initial_value
    return resolve_initial_value(value,parameters)


def factor_baseline(factors,protocol,context):
    spec=protocol['run_spec'];mapping=protocol['mapping_validation'];snapshot=mapping['mapping_snapshot']
    target=next(t for t in snapshot['targets'] if t['id']==protocol['target_id'])
    blocks={b['path']:b for b in mapping['build_spec']['blocks']}
    raw_blocks={b['path']:b for b in target['blocks']}
    parameters={p['code_name']:p for p in spec['parameters']}
    registered={p['code_name']:p for p in mapping['parameter_validation']['parameters'] if all(p['reference'][k]==protocol[k] for k in ('design_id','model_id'))}
    variables={v['id']:v for v in context['variables']}
    for factor in factors:
        kind,loc=factor['kind'],factor['locator'];variable=variables.get(factor['variable_id'])
        if variable is None or variable['unit']!=factor['unit']:raise ValueError('factor must bind an actual selected C variable with exact unit')
        if kind=='parameter':
            name=loc['code_name'];item=parameters.get(name);registration=registered.get(name)
            if item is None or registration is None or registration['reference']['variable_id']!=factor['variable_id'] or item['unit']!=factor['unit'] or item['value']!=factor['baseline']:
                raise ValueError('parameter factor baseline/reference/unit differs from the approved model workspace')
        elif kind=='initial_condition':
            block=blocks.get(loc['block_path']);raw=raw_blocks.get(loc['block_path'])
            if block is None or raw is None or block['type']!='Integrator' or 'state' not in variable['roles'] or _initial_value(block['parameters']['InitialCondition'],spec['parameters'])!=factor['baseline']:
                raise ValueError('initial-condition baseline must bind an existing D Integrator C state')
            reference=raw['parameters']['InitialCondition'].get('value_ref')
            if reference is None or reference['field']!='initial_conditions' or not typed_equal(reference['selector'],loc['state_selector']):
                raise ValueError('initial-condition locator must retain the exact D approved initial-value selector')
            traces=[trace for trace in target['traces'] if trace['kind']=='variable' and trace['disposition']=='mapped' and block['id'] in trace['block_ids'] and trace['subject_id']==factor['variable_id']]
            if len(traces)!=1:raise ValueError('initial-condition variable must have one exact reviewed D trace')
        else:
            items=[i for i in spec['inputs'] if i['port']==loc['input_port'] and i['variable_id']==factor['variable_id']]
            if len(items)!=1 or items[0]['unit']!=factor['unit'] or (loc['block_path'] is not None and loc['block_path']!=items[0]['block_path']):
                raise ValueError('input factor must bind an existing reviewed E root-input identity')
            wave=factor['waveform'];item=items[0]
            if wave['time'][0]!=spec['start_time'] or wave['time'][-1]!=spec['stop_time'] or len(wave['time'])>12001:
                raise ValueError('factor waveform must span the exact reviewed interval')
            # Baseline may use a denser PWL knot set, but it must reconstruct
            # exactly the already approved input. No new baseline condition.
            from numerical_math_common import Series
            baseline=Series(item['time'],item['values'],interpolation=item['interpolation'])
            physical=[factor['baseline'] for _ in wave['time']] if wave['mode']=='constant' else [x*factor['baseline'] for x in wave['baseline_values']] if wave['mode']=='scale' else [x+factor['baseline'] for x in wave['baseline_values']]
            union=sorted(set(wave['time']+item['time']))
            hypothetical=Series(wave['time'],physical)
            if any(baseline.at(t)!=hypothetical.at(t) for t in union):
                raise ValueError('input factor baseline PWL differs from frozen E input')


def _criterion(value,method,factors,metric):
    c=value
    for key in ('lower','upper'):
        if c[key] is not None:real(c[key], 'criterion '+key)
    if c['lower'] is not None and c['upper'] is not None and c['lower']>c['upper']:raise ValueError('reversed criterion bounds')
    if c['quantity']=='analysis_value':
        if not c['result_selector']:raise ValueError('method-specific criterion requires complete result_selector')
        if c['lower'] is None and c['upper'] is None:raise ValueError('method-specific criterion requires finite bounds')
    elif c['result_selector'] is not None:raise ValueError('result_selector only applies to analysis_value')
    if c['quantity']=='analysis_defined':
        if c['unit']!='1' or c['lower'] is not None or c['upper'] is not None:raise ValueError('analysis_defined requires dimensionless null bounds')
    elif c['quantity']!='analysis_value':
        if c['lower'] is None and c['upper'] is None:raise ValueError('criterion requires finite reviewed threshold')
        expected_unit='1' if c['quantity'] in ('event_probability','coverage_probability','runtime_ratio') else next(f['unit'] for f in factors if f['id']==metric.get('_boundary_factor')) if c['quantity']=='boundary_width' else metric['unit']
        if c['unit']!=expected_unit:raise ValueError('preflight criterion quantity/unit differs')
    if c['quantity']=='boundary_width':
        if method!='failure_boundary' or c['unit']!=next(f['unit'] for f in factors if f['id']==metric['_boundary_factor']):raise ValueError('boundary width criterion unit/method differs')
    if c['quantity']=='runtime_ratio' and method!='runtime_comparison':raise ValueError('runtime ratio requires real runtime comparison')
    if c['quantity'] in ('event_probability','coverage_probability') and method not in UNCERTAINTY_METHODS:raise ValueError('population probability requires fixed-N iid uncertainty study')


def validate_h_analysis_study(path,*,project_root=None,require_reviewed=False):
    path=Path(path).resolve();root=Path(project_root or path.parent).resolve()
    result={'valid':False,'schema_valid':False,'reviewed':False,'study_ready':False,'assessment_ready':False,'execution_ready':False,
            'environment_checked':False,'execution_allowed':False,'contract_path':str(path),'contract_sha256':None,
            'project_root':str(root),'project_id':None,'semantic_sha256':None,'bound_files':[],'changed_sources':[],
            'errors':[],'missing_gates':[],'required_A_operations':[],'budget':None,'native_budget':None,
            'base_protocol_report':None,'base_simulation_report':None,'primary_numerical_report':None}
    errors,missing=result['errors'],result['missing_gates']
    try:
        if not path.is_relative_to(root):raise ValueError('study contract leaves explicit project root')
        bootstrap=input_manifest([path],root,HARD_BUDGET)
        value=limited_document(path);schema=load_contract('core/h_analysis_study.schema.yaml')
        issues=schema_errors(value,schema);errors.extend(issues)
        if issues:return result
        if type(value['schema_version']) is not int:raise ValueError('study version must be exact integer, not bool')
        budget=value['budget'] or HARD_BUDGET
        if value['budget'] is None:
            missing.append('source_declared_complete_study_budget')
        else:
            if any(type(v) is not int for v in budget.values()):raise ValueError('study budgets require exact integers, not bool/float')
            if budget['max_total_bytes']<budget['max_file_bytes'] or budget['max_result_bytes']>budget['max_file_bytes']:raise ValueError('inconsistent total/file/result byte budgets')
        paths=evidence_paths([path],root,budget,root_contexts={path:'h_study_contract'})
        manifest=input_manifest(paths,root,budget)
        result.update(schema_valid=True,contract_sha256=sha256_file(path),project_id=value['project_id'],semantic_sha256=semantic_digest(value),
                      budget=value['budget'],_contract=value,input_manifest=manifest,allowed_external=sorted(map(str,paths.allowed_external)),
                      method=value['method'],settings=value['settings'],design=value['design'],factors=value['factors'],metric=value['metric'],
                      numerical_policy=value['numerical_policy'],inference=value['inference'],criterion=value['criterion'],claim_limit=value['claim_limit'])
        if value['budget'] is not None:result['native_budget']={k:budget[k] for k in NATIVE_BUDGET_FIELDS}
        result['bound_files'].append({'label':'h_analysis_study','path':str(path),'sha256':result['contract_sha256']})
        sources=bind_sources(value['sources'],root,result)
        source_snapshot(value['settings_source_ref'],sources,root,result,{k:value[k] for k in SETTINGS_FIELDS},label='complete_h_analysis_study_settings')
        for field in ('method','settings','design','metric','numerical_policy','inference','criterion'):
            if value[field] is None:missing.append('reviewed_'+field)
        base_paths={}
        for label in ('base_protocol','base_receipt','primary_numerical_receipt'):
            file=checked_binding(root,value[label],result,label,budget)
            if file is None:missing.append('current_'+label)
            else:base_paths[label]=file
        protocol=None
        if 'base_protocol' in base_paths:
            protocol=validate_simulation_protocol(base_paths['base_protocol'],project_root=root,require_frozen=True)
            result['base_protocol_report']=protocol
            result['bound_files'].extend(protocol['bound_files'])
            if not protocol['valid'] or not protocol['frozen']:errors.extend('base_protocol: '+e for e in protocol['errors']);missing.append('current_frozen_baseline')
            if protocol['project_id']!=value['project_id']:errors.append('baseline protocol project differs')
            result['required_A_operations']=protocol['required_A_operations']
            for name in ('problem','model','approval','mapping','parameters','native_model','implementation_receipt'):
                for suffix in ('path','sha256'):result[name+'_'+suffix]=protocol.get(name+'_'+suffix)
            result['model_identity']=protocol['model_identity']
        if 'base_receipt' in base_paths and protocol is not None:
            base=validate_simulation_receipt(base_paths['base_receipt'],project_root=root,protocol_report=protocol)
            result['base_simulation_report']=base
            if not base['valid'] or not base['primary_run_complete']:errors.extend('base_receipt: '+e for e in base['errors']);missing.append('actual_complete_baseline_simulation')
        if 'primary_numerical_receipt' in base_paths:
            primary=validate_numerical_verification_receipt(base_paths['primary_numerical_receipt'],project_root=root)
            result['primary_numerical_report']=primary
            result['bound_files'].extend(primary.get('bound_files',[]))
            if not primary['valid'] or not primary['numerically_verified']:errors.extend('primary_H1: '+e for e in primary['errors']);missing.append('accepted_current_primary_H1')
            if protocol and (primary.get('primary_protocol_path')!=protocol['contract_path'] or primary.get('primary_receipt_path')!=str(base_paths.get('base_receipt'))):errors.append('primary H1 must bind the exact study baseline E protocol and actual receipt')
        complete_fields=not any(value[k] is None for k in ('method','settings','design','metric','numerical_policy','inference','criterion','budget'))
        if complete_fields:
            if value['method'] not in METHODS:raise ValueError('unimplemented study method')
            validate_factor_records(value['factors'],budget)
            expected=validate_design(value['design'],value['method'],value['factors'],value['settings'],budget=budget)
            if value['method'] in UNCERTAINTY_METHODS:
                validate_uncertainty_inference(value['method'],value['factors'],value['settings'],value['inference'],budget=budget,metric_unit=value['metric']['unit'])
                if not expected['metadata']['execution_safe']:missing.append('unsafe_fixed_n_draws_preserved_no_clipping_or_resampling')
            elif value['method'] in ('local_derivative','normalized_sensitivity','parameter_oat','morris','sobol','variance_based','prcc'):
                from sensitivity_metrics import validate_sensitivity_inference
                validate_sensitivity_inference(value['method'],value['factors'],value['settings'],value['inference'],budget=budget)
            else:
                if value['inference']!={'method':'none'}:raise ValueError('finite scenario/boundary/runtime designs do not grant iid statistical inference')
            if value['criterion']['quantity'] in ('event_probability','coverage_probability') and value['method'] in UNCERTAINTY_METHODS and value['inference']['event' if value['criterion']['quantity']=='event_probability' else 'coverage'] is None:
                raise ValueError('population criterion requires its predeclared event/coverage inference rule')
            criterion_metric=dict(value['metric'])
            if value['method']=='failure_boundary':
                criterion_metric['_boundary_factor']=value['settings']['factor_id']
                if not set(value['settings']['monotonicity']['source_ids'])<=set(sources):raise ValueError('unknown monotonicity evidence source')
            _criterion(value['criterion'],value['method'],value['factors'],criterion_metric)
            if value['criterion']['quantity']=='analysis_value':
                selected_unit=analysis_selector_unit(value['method'],value['criterion']['result_selector'],value['metric'],value['factors'],value['settings'],value['inference'])
                if selected_unit!=value['criterion']['unit']:raise ValueError('preflight selected analysis estimator unit differs')
            if protocol and protocol['valid'] and protocol['run_spec']:
                context=numeric_context_from_documents(limited_document(protocol['model_path'],budget),protocol,limited_document(protocol['parameters_path'],budget))
                result['context']=context
                factor_baseline(value['factors'],protocol,context)
                policies=[value['numerical_policy']]
                if value['method']=='runtime_comparison':policies.extend(c['numerical_policy'] for c in value['settings']['configurations'])
                for policy in policies:
                    numeric=validate_trial_numeric_policy(policy,protocol['run_spec'],context)
                    if not numeric['valid']:errors.extend('trial_numeric_policy: '+e for e in numeric['errors'])
                    metric_gate=validate_metric_policy({k:v for k,v in value['metric'].items() if v is not None},policy,protocol['run_spec'],context)
                    if not metric_gate['valid']:errors.extend('study_metric_policy: '+e for e in metric_gate['errors'])
                    if policy['budget']['max_samples_per_output']>budget['max_samples_per_output']:errors.append('point numeric sample budget exceeds study budget')
                    for item in policy['obligations'].values():
                        if not set(item['source_ids'])<=set(sources):errors.append('numeric obligation references unknown study source')
                    if any(not set(check.get('source_ids',[]))<=set(sources) for check in policy['checks']):errors.append('numeric check references unknown study source')
                if value['method'] not in UNCERTAINTY_METHODS or expected['metadata']['execution_safe']:
                    manifest_groups=materialize_manifest(result)
                    for group in manifest_groups:
                        expected_states=[{k:item[k] for k in ('variable_id','unit','block_path')} for item in group['physical_snapshot']['initial_conditions']]
                        declared_states=[{k:item[k] for k in ('variable_id','unit','block_path')} for item in group['numeric_policy']['outputs'] if item.get('kind')=='state']
                        if len(declared_states)!=len(expected_states) or any(sum(typed_equal(item,declared) for declared in declared_states)!=1 for item in expected_states):errors.append('point numeric policy must cover the complete exact actual D Integrator states')
        review_ok=validate_review(value,root,result,schema,label='h_analysis_study')
        result['reviewed']=value['status']=='reviewed' and review_ok and not errors and not missing
        result['study_ready']=result['assessment_ready']=result['execution_ready']=result['reviewed']
        if require_reviewed and not result['reviewed']:errors.append('current complete reviewed executable H study required')
        if value['status']=='reviewed' and missing:errors.append('reviewed H study lacks required source/physics/numerical/design gates')
        assert_unchanged(manifest);assert_unchanged(bootstrap)
        result['valid']=not errors
    except (OSError,ValueError,KeyError,TypeError,AttributeError,OverflowError,StopIteration) as error:
        errors.append(type(error).__name__+': '+str(error))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('path',type=Path);parser.add_argument('--project-root',type=Path);parser.add_argument('--require-reviewed',action='store_true')
    args=parser.parse_args();result=validate_h_analysis_study(args.path,project_root=args.project_root,require_reviewed=args.require_reviewed)
    emit({k:v for k,v in result.items() if not k.startswith('_')});return 0 if result['valid'] else 1


if __name__=='__main__':raise SystemExit(main())
