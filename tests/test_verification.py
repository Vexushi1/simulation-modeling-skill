"""Owner infrastructure tests, never native qualification or independent approval."""
import copy
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from runtime_common import ROOT, load_document, sha256_file
from probe_environment import write_json
from simulation_factory import make_simulation_protocol
from validate_simulation_protocol import validate_simulation_protocol
from validate_verification import validate_verification
from verification_common import Budget, analytic_values, reference_errors, same_protocol, semantic_digest


def binding(path):
    return {'path': str(Path(path).resolve()), 'sha256': sha256_file(path)}


def reviewed(path, plan):
    write_json(path, plan)
    digest = semantic_digest(plan)
    text = f'project_id={plan["project_id"]}\nverification_semantic_sha256={digest}\nreviewed_by=synthetic-owner\naction=review\nSYNTHETIC INFRASTRUCTURE ONLY'
    decision = path.with_suffix('.decision.txt')
    decision.write_text(text, encoding='utf-8')
    record = path.with_suffix('.review.json')
    write_json(record, {'schema_version': 1, 'project_id': plan['project_id'], 'verification_semantic_sha256': digest,
        'decision': {**binding(decision), 'start': 0, 'end': len(text), 'quote': text, 'reviewed_by': 'synthetic-owner', 'action': 'review'}})
    plan.update(status='reviewed', review_record=binding(record))
    write_json(path, plan)
    return path


def run_and_ref(root, case='feedback'):
    path = make_simulation_protocol(root, case=case, solver='ode4')
    report = validate_simulation_protocol(path, project_root=root)
    c = load_document(report['model_path'])
    model = c['designs'][0]['models'][0]
    run = {'protocol': load_document(path), 'protocol_report': report, 'spec': report['run_spec'], 'model': model}
    ref = {'family': 'first_order_constant' if case == 'feedback' else 'static_affine', 'output_port': 1, 'unit': '1',
           'source_ids': ['reference'], 'relation_ids': ['kernel'], 'constant_parameter': 'k' if case == 'constant' else None,
           'terms': [{'parameter_id': 'k' if case == 'static' else None, 'input_id': 'u'}] if case in {'static', 'passthrough'} else [],
           'a_parameter': 'a' if case == 'feedback' else None, 'b_parameter': 'b' if case == 'feedback' else None,
           'input_id': 'u' if case == 'feedback' else None, 'state_id': 'x' if case == 'feedback' else None,
           'initial_selector': ['x'] if case == 'feedback' else [], 'atol': 1e-6, 'rtol': 1e-6}
    return run, ref


@pytest.mark.parametrize('kind,template', [('H1','numerical_verification'),('H2','model_verification')])
def test_unknown_draft_is_readonly_and_never_complete(tmp_path, kind, template):
    path = tmp_path / 'plan.yaml'
    path.write_bytes((ROOT / f'templates/contracts/{template}.yaml').read_bytes())
    before = path.read_bytes()
    result = validate_verification(path, kind=kind)
    assert result['schema_valid'] and result['valid'], result['errors']
    assert not result['reviewed'] and result['missing_gates'] and not result['execution_allowed']
    assert path.read_bytes() == before
    assert not validate_verification(path, kind=kind, require_reviewed=True)['valid']


@pytest.mark.parametrize('case,expected', [('constant',[2,2,2]),('static',[2,2,2]),('passthrough',[1,1,1])])
def test_approved_static_reference_and_graph(tmp_path, case, expected):
    run, ref = run_and_ref(tmp_path, case)
    assert analytic_values(run, ref, [0,.5,1]) == expected
    ref['terms'] = [{'parameter_id': None, 'input_id': 'u'}]
    if case != 'passthrough':
        with pytest.raises(ValueError, match='graph|state|parameter|binding'):
            analytic_values(run, ref, [0,1])


def test_first_order_origin_zero_a_and_near_zero_a(tmp_path):
    run, ref = run_and_ref(tmp_path)
    values = analytic_values(run, ref, [0, .5, 1])
    assert values == pytest.approx([2-1.75*math.exp(-.75*t) for t in [0,.5,1]], abs=1e-15)
    run['spec']['start_time'] = -2
    assert analytic_values(run, ref, [-2,-1])[0] == .25
    records = run['protocol_report']['mapping_validation']['parameter_validation']['parameters']
    a = next(p for p in records if p['reference']['variable_id'] == 'a')
    a['value'] = 0
    assert analytic_values(run, ref, [-2,-1]) == [.25,1.75]
    a['value'] = 1e-320
    assert analytic_values(run, ref, [-2,-1]) == pytest.approx([.25,1.75])
    a['value'] = -.1
    with pytest.raises(ValueError, match='nonnegative'):
        analytic_values(run, ref, [-2,-1])


@pytest.mark.parametrize('change', ['zero_scale','wrong_unit','wrong_parameter','missing_output'])
def test_reference_failures_are_not_tolerance_fallbacks(tmp_path, change):
    run, ref = run_and_ref(tmp_path, 'static')
    run['outputs'] = [{'port':1,'unit':'1','time':[0,1],'values':[2,2]}]
    if change == 'zero_scale':
        ref.update(atol=0, rtol=0)
    elif change == 'wrong_unit':
        ref['unit'] = 'm'
    elif change == 'wrong_parameter':
        ref['terms'][0]['parameter_id'] = 'made_up'
    else:
        run['outputs'].append({'port':2,'unit':'1','time':[0,1],'values':[2,2]})
    with pytest.raises((ValueError, KeyError)):
        reference_errors(run, [ref])


@pytest.mark.parametrize('hidden', ['zero_crossing','metrics','conditions','logging','required_A_operations'])
def test_frozen_delta_does_not_erase_entire_solver_or_protocol(tmp_path, hidden):
    run, _ = run_and_ref(tmp_path)
    left, right = copy.deepcopy(run['protocol']), copy.deepcopy(run['protocol'])
    right['solver']['fixed_step'] /= 2
    same_protocol(left,right,'step_refinement',['fixed_step'])
    if hidden == 'zero_crossing':
        right['solver']['zero_crossing'] = 'EnableAll'
    else:
        right[hidden] = {'silently':'changed'}
    with pytest.raises(ValueError, match='outside designated'):
        same_protocol(left,right,'step_refinement',['fixed_step'])


def h1_plan(root):
    root.mkdir(exist_ok=True)
    source = root / 'source.txt'
    source.write_text('SYNTHETIC reference and declared absolute error <= 1e-6',encoding='utf-8')
    receipt = root / 'synthetic-e.json'
    write_json(receipt, {'notice':'E reader patched in owner unit test; not native evidence'})
    plan = load_document(ROOT/'templates/contracts/numerical_verification.yaml')
    plan.update(project_id='synthetic-H',primary=binding(receipt),
        sources=[{'id':'reference',**binding(source)}],
        requirements=[{'id':'analytic','method':'analytic_reference','required':True,'reason':'sample error check','source_ids':['reference']}],
        runs=[{'id':'primary','receipt':binding(receipt),'h1_receipt':None,'references':[{ 'family':'static_affine','output_port':1,'unit':'1','source_ids':['reference'],'relation_ids':['kernel'],
           'constant_parameter':'k','terms':[],'a_parameter':None,'b_parameter':None,'input_id':None,'state_id':None,'initial_selector':[],'atol':1e-6,'rtol':0}]}])
    return reviewed(root/'h1.json',plan), plan


def test_required_unsupported_and_changed_criterion_cannot_reuse_review(tmp_path):
    path, plan = h1_plan(tmp_path)
    assert validate_verification(path,require_reviewed=True)['reviewed']
    plan['runs'][0]['references'][0]['atol'] = 100
    write_json(path,plan)
    assert not validate_verification(path,require_reviewed=True)['valid']
    plan['requirements'].append({'id':'event','method':'event_localization','required':True,'reason':'requested by task','source_ids':['reference']})
    reviewed(path,plan)
    result = validate_verification(path)
    assert not result['reviewed'] and 'unsupported_required:event_localization' in result['missing_gates']


def test_budget_prevents_large_data_read_and_source_drift(tmp_path):
    path = tmp_path/'big.bin'
    with path.open('wb') as stream:
        stream.truncate(16777217)
    with pytest.raises(ValueError,match='file byte'):
        Budget().charge(path)
    path.write_text('old',encoding='utf-8')
    budget=Budget()
    budget.charge(path)
    path.write_text('new',encoding='utf-8')
    with pytest.raises(ValueError,match='changed'):
        budget.finish()


def test_producer_consumer_recomputes_even_rehashed_fake_summary(tmp_path, monkeypatch):
    import verification_analysis
    from run_verification import run_verification, FILES
    from validate_verification_receipt import validate_verification_receipt
    path, plan = h1_plan(tmp_path)
    run, _ = run_and_ref(tmp_path/'upstream', 'constant')
    run.update(project_id=plan['project_id'], run_id='synthetic-e-run',receipt=plan['primary'],
        outputs=[{'port':1,'unit':'1','time':[0,1],'values':[2,2]}])
    monkeypatch.setattr(verification_analysis,'read_run',lambda *args: copy.deepcopy(run))
    generated = run_verification(path,tmp_path/'h1-evidence',project_root=tmp_path,kind='H1')
    assert generated['valid'] and generated['numerically_verified'], generated['errors']
    receipt_path = Path(generated['receipt_path'])
    checked = validate_verification_receipt(receipt_path,project_root=tmp_path,kind='H1')
    assert checked['valid'] and checked['checks_passed'], checked['errors']
    result_path = receipt_path.parent/FILES[1]
    result=load_document(result_path)
    result['ledger'][0]['checks'][0]['max_abs_error']=123
    write_json(result_path,result)
    receipt=load_document(receipt_path)
    receipt['artifacts'][FILES[1]]['sha256']=sha256_file(result_path)
    write_json(receipt_path,receipt)
    assert not validate_verification_receipt(receipt_path,project_root=tmp_path)['valid']
    with pytest.raises(ValueError,match='new evidence directory'):
        run_verification(path,receipt_path.parent,project_root=tmp_path)


def numerical_analysis(method, ids):
    return {'id':'compare','method':method,'run_ids':ids,'claim_id':'claim','campaign':None,
            'output_ports':[1,1] if method != 'step_refinement' else [1], 'unit':'1','direction':'le','threshold':.01,
            'failure_disposition':'reject','impact_scope':'finite terminal claim','required_action':'review claim','return_stage':'H',
            'structural_review':None,'solver_changes':['fixed_step'] if method=='step_refinement' else ['name','type','max_step','min_step','initial_step','rel_tol','abs_tol','fixed_step']}


def test_three_layer_nonzero_terminal_differences_and_hidden_change(tmp_path):
    from verification_analysis import refinement
    run, _=run_and_ref(tmp_path)
    runs={}
    for index,value in enumerate([1.1,1.101,1.10106]):
        layer=copy.deepcopy(run)
        layer['protocol']['solver']['fixed_step']=.04/(2**index)
        layer['spec']['solver']['fixed_step']=.04/(2**index)
        layer['outputs']=[{'port':1,'unit':'1','time':[0,1],'values':[.25,value]}]
        runs[str(index)]=layer
    analysis=numerical_analysis('step_refinement',list(runs))
    result=refinement(analysis,runs)
    assert result['passed'] and result['values']==pytest.approx([.001,.00006]) and result['order_estimate'] is None
    runs['1']['protocol']['metrics'][0]['upper']=999
    with pytest.raises(ValueError,match='outside designated'):
        refinement(analysis,runs)


def test_solver_comparison_requires_observed_continuous_method(tmp_path):
    from verification_analysis import comparison
    left,_=run_and_ref(tmp_path)
    right=copy.deepcopy(left)
    for run,name in [(left,'ode4'),(right,'ode45')]:
        run['outputs']=[{'port':1,'unit':'1','time':[0,1],'values':[.25,1.2]}]
        run['actual']={'observed_solver_info':{'Solver':name}}
    right['protocol']['solver'].update(name='ode45',type='variable-step',fixed_step=None,max_step=.05,min_step=1e-12,initial_step=.01,rel_tol=1e-6,abs_tol=1e-8)
    analysis=numerical_analysis('solver_final_comparison',['left','right'])
    claims={'claim':{'domain':{'kind':'terminal_pair'}}}
    assert comparison(analysis,{'left':left,'right':right},claims)['passed']
    right['actual']['observed_solver_info']['Solver']='VariableStepDiscrete'
    with pytest.raises(ValueError,match='actual observed'):
        comparison(analysis,{'left':left,'right':right},claims)
