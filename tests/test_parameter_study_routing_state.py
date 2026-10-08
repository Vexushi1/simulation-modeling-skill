"""Optional F branch, operation gates and read-only dependency behavior."""
import json

import pytest

from parameter_study_factory import METHODS, make_parameter_study
from problem_factory import read_contract, write_contract
from resolve_runtime import resolve_runtime
from runtime_common import sha256_file
from validate_parameter_study import validate_parameter_study
from validate_project_state import validate_project_state

INTENTS = ('parameter_identification','calibration','optimization')


def make_state(root, study, *, stage='PARAMETER_STUDY_REVIEWED', artifacts=None):
    report=validate_parameter_study(study,require_reviewed=True)
    assert report['valid'],report['errors']
    state={'schema_version':1,'project_id':report['project_id'],'project_root':'.',
        'current_stage':stage,'environment':None,'artefacts':artifacts or []}
    for name in ('problem','model','approval'):
        from pathlib import Path
        state[name]={'path':Path(report[name+'_path']).relative_to(root).as_posix(),'sha256':report[name+'_sha256']}
    state['study']={'path':study.relative_to(root).as_posix(),'sha256':sha256_file(study)}
    return write_contract(root/'project-state.json',state)


@pytest.mark.parametrize('method',METHODS)
def test_reviewed_unknowns_need_no_d_e_or_current_runtime(tmp_path,method):
    study=make_parameter_study(tmp_path,method)
    state=make_state(tmp_path,study)
    before={p:p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    report=validate_project_state(state,scope='parameter_study')
    assert report['valid'],report['errors']
    assert report['study_reviewed'] and not report['candidate_complete']
    assert not report['environment_checked'] and not report['implementation_checked']
    assert not report['simulation_checked'] and report['parameter_study_checked']
    route=resolve_runtime('parameter_study',state_path=state)
    assert route['status']=='inspected',route['errors']
    assert not route['execution_allowed'] and not route['parameter_study_execution_allowed']
    assert route['selected_operations']==[]
    assert {p:p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}==before


@pytest.mark.parametrize('method,intent',list(zip(METHODS,INTENTS)))
def test_complete_study_alone_cannot_authorize_trial(tmp_path,method,intent):
    study=make_parameter_study(tmp_path,method)
    route=resolve_runtime(intent,study_path=study)
    assert route['status']=='blocked',route
    assert route['missing_gates']==['current_a_and_f_profiles']
    assert not route['execution_allowed'] and not route['business_execution_allowed']
    assert not route['parameter_study_execution_allowed']


def test_draft_and_wrong_method_return_explicit_gates(tmp_path):
    study=make_parameter_study(tmp_path,status='draft')
    review=resolve_runtime('parameter_study',study_path=study)
    assert review['status']=='inspected'
    assert not review['execution_allowed'] and review['missing_gates']
    assert resolve_runtime('calibration',study_path=study)['status']=='blocked'
    study=make_parameter_study(tmp_path/'other',METHODS[0])
    route=resolve_runtime('optimization',study_path=study)
    assert route['status']=='blocked' and route['missing_gates']==['method_matches_intent']


def test_another_f_operation_is_not_an_a_requirement(tmp_path):
    study=make_parameter_study(tmp_path,METHODS[0])
    route=resolve_runtime('parameter_identification',study_path=study,
                          required_operations=[METHODS[2]])
    assert route['status']=='blocked' and route['missing_gates']==['required_operations_match_method']
    assert not route['execution_allowed']


@pytest.mark.parametrize('scope',['problem','model','implementation','simulation'])
def test_earlier_partial_scopes_leave_missing_f_history_unassessed(tmp_path,scope):
    study=make_parameter_study(tmp_path)
    state=make_state(tmp_path,study)
    study.unlink()
    report=validate_project_state(state,scope=scope)
    assert report['valid'],report['errors']
    assert not report['parameter_study_checked'] and not report['study_reviewed']
    report=validate_project_state(state,scope='parameter_study')
    assert not report['valid'] and 'study' in report['stale_artefacts']


def test_changed_data_invalidates_c_study_and_dependents_conservatively(tmp_path):
    study=make_parameter_study(tmp_path)
    record={'id':'f-review','role':'parameter_study','path':study.name,'sha256':sha256_file(study),
            'status':'accepted','depends_on':['problem','model','approval','study']}
    state=make_state(tmp_path,study,artifacts=[record])
    baseline=validate_project_state(state,scope='parameter_study')
    assert baseline['valid'],baseline['errors']
    path=tmp_path/'observations.csv'
    path.write_bytes(path.read_bytes()+b'\n')
    report=validate_project_state(state,scope='parameter_study')
    assert not report['valid'] and not report['study_reviewed']
    assert {'problem','model','study','f-review'}<=set(report['stale_artefacts'])


def test_candidate_stage_and_review_cannot_invent_missing_receipt(tmp_path):
    study=make_parameter_study(tmp_path)
    state=make_state(tmp_path,study,stage='PARAMETER_CANDIDATE_COMPLETE')
    content=read_contract(state)
    content['parameter_trial']={'path':'missing-receipt.json','sha256':'0'*64}
    write_contract(state,content)
    report=validate_project_state(state,scope='parameter_study')
    assert not report['valid'] and not report['candidate_complete']
    assert 'parameter_trial' in report['stale_artefacts']
    route=resolve_runtime('parameter_candidate_review',study_path=study)
    assert route['status']=='blocked' and route['missing_gates']==['current_parameter_trial_receipt']


def test_state_supplied_path_mismatch_blocks_before_runtime(tmp_path):
    study=make_parameter_study(tmp_path)
    state=make_state(tmp_path,study)
    duplicate=tmp_path/'same-bytes.json'
    duplicate.write_bytes(study.read_bytes())
    route=resolve_runtime('calibration',state_path=state,study_path=duplicate)
    assert route['status']=='blocked' and route['missing_gates']==['study_state_binding_matches']


def test_review_only_draft_preparation_requires_actual_approved_c(tmp_path):
    assert resolve_runtime('parameter_study')['status']=='blocked'
    study=make_parameter_study(tmp_path)
    report=validate_parameter_study(study)
    route=resolve_runtime('parameter_study',model_path=report['model_path'])
    assert route['status']=='allowed' and not route['execution_allowed']
    assert route['missing_gates']==['parameter_study_supplied','parameter_study_reviewed']


@pytest.mark.parametrize('method,intent',list(zip(METHODS,INTENTS)))
def test_selected_qualified_method_has_candidate_permission_only(tmp_path,method,intent):
    from test_parameter_study_assurance import make_trial
    receipt=make_trial(tmp_path,method)
    route=resolve_runtime(intent,study_path=tmp_path/'parameter-study.json',
        profile_path=tmp_path/'a/evidence/profile.json',
        parameter_study_profile_path=tmp_path/'f/parameter-study-profile.json',
        simulation_profile_path=tmp_path/'e/simulation-profile.json' if method==METHODS[1] else None)
    assert route['status']=='allowed',route['errors']
    assert route['parameter_study_execution_allowed'] and route['execution_scope']=='parameter_trial'
    assert not route['simulation_execution_allowed'] and not route['implementation_execution_allowed']
    assert route['activated_packs']==[f'packs/task/{intent}.md'] and route['upstream_skills']==[]
    review=resolve_runtime('parameter_candidate_review',study_path=tmp_path/'parameter-study.json',parameter_trial_receipt_path=receipt)
    assert review['status']=='inspected',review['errors']
    assert not review['execution_allowed'] and not review['parameter_study_execution_allowed']


def test_missing_bound_trial_stales_accepted_candidate_transitively(tmp_path):
    from test_parameter_study_assurance import make_trial
    receipt=make_trial(tmp_path,METHODS[2])
    study=tmp_path/'parameter-study.json'
    candidate=receipt.parent/'trial-numeric.json'
    artifacts=[{'id':'study-item','role':'parameter_study','path':study.name,'sha256':sha256_file(study),
        'status':'accepted','depends_on':['problem','model','approval','study']},
        {'id':'trial-item','role':'parameter_trial','path':receipt.relative_to(tmp_path).as_posix(),'sha256':sha256_file(receipt),
        'status':'accepted','depends_on':['problem','model','approval','study','parameter_trial','study-item']},
        {'id':'candidate-item','role':'parameter_candidate','path':candidate.relative_to(tmp_path).as_posix(),'sha256':sha256_file(candidate),
        'status':'accepted','depends_on':['problem','model','approval','study','parameter_trial','study-item','trial-item']}]
    state=make_state(tmp_path,study,stage='PARAMETER_CANDIDATE_COMPLETE',artifacts=artifacts)
    content=read_contract(state)
    content['parameter_trial']={'path':receipt.relative_to(tmp_path).as_posix(),'sha256':sha256_file(receipt)}
    write_contract(state,content)
    valid=validate_project_state(state,scope='parameter_study')
    assert valid['valid'] and valid['candidate_complete'],valid['errors']
    receipt.unlink()
    invalid=validate_project_state(state,scope='parameter_study')
    assert not invalid['valid'] and not invalid['candidate_complete']
    assert {'parameter_trial','trial-item','candidate-item'}<=set(invalid['stale_artefacts'])


def test_state_all_checks_selected_f_operation_without_promoting_unrelated_failure(tmp_path):
    from test_parameter_study_assurance import make_parameter_profile,rebind
    from test_runtime import make_profile
    from validate_parameter_study_profile import validate_parameter_study_profile
    study=make_parameter_study(tmp_path,METHODS[0])
    a=make_profile(tmp_path/'a')
    f=make_parameter_profile(tmp_path/'f',a)
    raw_path=f.parent/'raw-parameter-study.json'
    raw=read_contract(raw_path)
    for case in raw['cases']:
        if case['case_id']=='quadratic_positive':case['candidate_complete']=False
    write_contract(raw_path,raw)
    rebind(f)
    profile=validate_parameter_study_profile(f,required_operations=[METHODS[0]])
    assert profile['valid'] and METHODS[2] not in profile['qualified_operations']
    state=make_state(tmp_path,study)
    content=read_contract(state)
    content['parameter_environment']={'profile_path':f.relative_to(tmp_path).as_posix(),
        'profile_sha256':sha256_file(f),'receipt_sha256':sha256_file(f.parent/'parameter-study-profile-receipt.json')}
    write_contract(state,content)
    result=validate_project_state(state,scope='all')
    assert result['valid'],result['errors']
    assert result['parameter_environment_checked']
    assert METHODS[2] not in result['parameter_environment_validation']['qualified_operations']


@pytest.mark.parametrize('field',['profile_sha256','receipt_sha256'])
def test_gain_route_checks_current_e_state_sha_even_in_f_partial_scope(tmp_path,field):
    from test_parameter_study_assurance import make_trial
    make_trial(tmp_path,METHODS[1])
    state=make_state(tmp_path,tmp_path/'parameter-study.json')
    content=read_contract(state)
    content['simulation_environment']={'profile_path':'e/simulation-profile.json',
        'profile_sha256':sha256_file(tmp_path/'e/simulation-profile.json'),
        'receipt_sha256':sha256_file(tmp_path/'e/simulation-profile-receipt.json')}
    content['simulation_environment'][field]='0'*64
    write_contract(state,content)
    route=resolve_runtime('calibration',state_path=state,profile_path=tmp_path/'a/evidence/profile.json',
        parameter_study_profile_path=tmp_path/'f/parameter-study-profile.json')
    assert route['status']=='blocked',route
    assert route['missing_gates']==['simulation_environment_state_binding_matches']
    assert not route['execution_allowed']
