"""Read a historical hypothetical H batch and independently check every point."""
from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path

from h_analysis_trial import (artifact_manifest, assert_case, assert_case_functions, contract, materialize_trial_manifest, observed_runtime,
                             physical_snapshot, preflight_request, source_identities, validate_case_qualifications,
                             _HistoricalReplay, _mint_historical_replay, _finish_historical_replay)
from runtime_common import canonical_digest, emit, load_document, sha256_file
from validate_environment import _path, _time
from validate_implementation_receipt import same_runtime
from verification_common import assert_unchanged, typed_equal


def verify_study_bindings(request, report):
    b = request['bindings']
    expected = {'project_id', 'project_root', 'study', 'study_snapshot', 'study_semantic_sha256', 'base_protocol',
                'base_simulation_receipt', 'primary_numerical_receipt', 'bound_files', 'required_A_operations',
                'protected_files', 'current_state', 'design', 'environment_profile', 'environment_receipt', 'simulation_profile',
                'simulation_profile_receipt', 'h_analysis_profile', 'h_analysis_profile_receipt'}
    if set(b) != expected or request['mode'] != 'trial': raise ValueError('hypothetical trial exact study binding surface differs')
    if not report['valid'] or not report['reviewed'] or not report['execution_ready']:
        raise ValueError('current approved-base independently reviewed study required')
    if b['project_id'] != report['project_id'] or b['study_semantic_sha256'] != report['semantic_sha256'] or not typed_equal(b['study_snapshot'], report['_contract']) or not typed_equal(b['bound_files'], report['bound_files']) or not typed_equal(request['budget'], report['native_budget']):
        raise ValueError('complete reviewed study semantic/source/budget snapshot differs')
    if _path(b['study']['path']) != _path(report['contract_path']) or b['study']['sha256'] != report['contract_sha256']:
        raise ValueError('trial binds a different current study')
    protocol = report['base_protocol_report']
    pairs = [('base_protocol', protocol['contract_path'], protocol['contract_sha256']),
             ('base_simulation_receipt', report['base_simulation_report']['receipt_path'], report['base_simulation_report']['receipt_sha256']),
             ('primary_numerical_receipt', report['primary_numerical_report']['receipt_path'], report['primary_numerical_report']['receipt_sha256'])]
    for key, path, digest in pairs:
        if _path(b[key]['path']) != _path(path) or b[key]['sha256'] != digest: raise ValueError('approved current baseline anchor differs: ' + key)
    for binding in b['protected_files']:
        if sha256_file(binding['path']) != binding['sha256']: raise ValueError('approved/base/primary/state protected bytes changed')
    protected = {(_path(x['path']), x['sha256']) for x in b['protected_files']}
    if not {(_path(x['path']), x['sha256']) for x in report['bound_files']} <= protected:
        raise ValueError('approved baseline protected file union was dropped')
    if b['current_state'] is not None:
        from runtime_common import contained_path
        state = b['current_state']
        if not isinstance(state, dict) or set(state) != {'path', 'sha256'} or not (str(contained_path(b['project_root'], state['path'])), state['sha256']) in {(str(Path(x['path']).resolve()), x['sha256']) for x in b['protected_files']}:
            raise ValueError('explicit current-state byte binding is missing from protected proof')
    if not set(report['required_A_operations']) <= set(b['required_A_operations']): raise ValueError('study-required A operations were dropped')
    # Fixed designs must be reproduced exactly. Adaptive prefix selection is
    # separately replayed by the complete study consumer; trial scope authorizes
    # only finite points in this same prior reviewed hypothetical domain.
    adaptive = report['method'] == 'failure_boundary'
    if not adaptive and not typed_equal(b['design'], report['design']): raise ValueError('fixed prior complete point design changed')
    expected_groups = materialize_trial_manifest(report, b['design'])
    if not typed_equal(request['groups'], expected_groups): raise ValueError('actual trial manifest differs from independently materialized reviewed factors/design')
    if len(request['cases']) != 3 * len(expected_groups): raise ValueError('every study point requires its own three actual levels')
    by_id = {case['case_id']: case for case in request['cases']}
    for group in expected_groups:
        for level, case_id in enumerate(group['case_ids']):
            case = by_id[case_id]
            expected_spec = deepcopy(protocol['run_spec'])
            expected_spec.update(parameters=deepcopy(group['physical_snapshot']['parameters']), inputs=deepcopy(group['physical_snapshot']['inputs']),
                                 solver=deepcopy(group['numeric_policy']['solver_levels'][level]), metrics=[])
            if not typed_equal(case['run_spec'], expected_spec) or not typed_equal(case['build_spec'], protocol['mapping_validation']['build_spec']):
                raise ValueError('trial changed the baseline outside the reviewed physical overlay/numeric settings')
            if not typed_equal(case['initial_conditions'], group['physical_snapshot']['initial_conditions']):
                raise ValueError('trial initial conditions differ from the prior reviewed point')
    return report


def assess_trial_request(request, raw, directory, report, *, process=None, _historical_replay=None):
    """One immutable qualification/read set for the batch, with per-case gates."""
    verify_study_bindings(request, report)
    before = preflight_request(request, role='h_trial_request')
    replay = _historical_replay if isinstance(_historical_replay, _HistoricalReplay) and \
        _historical_replay.matches(request, raw=raw, directory=directory) else None
    records = raw.get('cases')
    if not isinstance(records, list) or len(records) != len(request['cases']):
        raise ValueError('complete native point/level ledger cardinality differs')
    if process is None:
        from verification_common import limited_document
        process = limited_document(Path(directory) / contract()['evidence']['process'], request['budget'])
    runtime = observed_runtime(raw, request) if isinstance(raw.get('runtime'), dict) else None
    levels, errors, cache, case_results = {}, [], {}, []
    if process['process_state'] != 'completed' or process['exit_code'] != 0:
        errors.append('native process did not complete successfully: ' + process['process_state'])
    if (_time(process['finished_at']) - _time(process['started_at'])).total_seconds() > process['execution_timeout']:
        errors.append('actual native process elapsed exceeded its enforced cap')
    if raw['status'] != 'completed': errors.append('native raw batch did not complete: ' + raw['status'])
    batch_stop = _time(raw['finished_at']) if raw.get('finished_at') else _time(process['finished_at'])
    previous_finish = _time(raw['started_at'])
    for case, actual in zip(request['cases'], records):
        if not isinstance(actual, dict) or actual.get('case_id') != case['case_id'] or type(actual.get('attempted')) is not bool or type(actual.get('completed')) is not bool:
            raise ValueError('complete failed/attempted native ledger identity differs')
        case_errors = []
        try:
            if actual.get('started_at'):
                current_start = _time(actual['started_at'])
                if current_start < previous_finish:
                    raise ValueError('actual native case intervals overlap in a serial batch')
                if actual.get('finished_at'):
                    current_finish = _time(actual['finished_at'])
                    if not current_start <= current_finish <= batch_stop:
                        raise ValueError('actual per-case finished timestamp outside native batch')
                    previous_finish = current_finish
            if actual['attempted'] is False:
                if actual['completed'] is not False or actual.get('simulation_returned') is True:
                    raise ValueError('unattempted native row claims returned/completed evidence')
                if actual.get('started_at') and not _time(raw['started_at']) <= _time(actual['started_at']) <= batch_stop:
                    raise ValueError('unattempted native row timestamp outside batch')
                raise ValueError('native case was not attempted: ' + str(actual.get('framework_error', {})))
            if not _time(raw['started_at']) <= _time(actual['started_at']) <= batch_stop:
                raise ValueError('actual per-case timestamp outside native batch')
            if actual.get('finished_at') and not _time(actual['started_at']) <= _time(actual['finished_at']) <= batch_stop:
                raise ValueError('actual per-case finished timestamp outside native batch')
            if runtime is None: raise ValueError('attempted native case lacks actual runtime identity')
            assert_case_functions(actual, raw['functions'], raw['runtime']['matlabroot'])
            qualified = validate_case_qualifications(request, case, actual['started_at'], _cache=cache,
                                                    _historical_replay=replay)
            if not same_runtime(runtime, qualified): raise ValueError('actual trial runtime differs from execution-time independent A/E/H')
            checked = assert_case(actual, case, Path(directory) / 'cases' / case['case_id'], request['run_id'], request['budget'])
            if not checked['complete']: raise ValueError('hypothetical study point is technically incomplete')
            levels[case['case_id']] = {'level_id': case['level_id'], 'case_id': case['case_id'], 'run_spec': deepcopy(case['run_spec']),
                'outputs': checked['outputs'], 'states': checked['states'], 'timing_info': checked['timing_info'], 'timing_provenance': checked['timing_provenance'],
                'started_at': actual['started_at'], 'finished_at': actual['finished_at'],
                'raw_path': str(Path(directory) / 'cases' / case['case_id'] / actual['raw_mat_file']),
                'mat_path': str(Path(directory) / 'cases' / case['case_id'] / actual['mat_file']),
                'data_path': str(Path(directory) / 'cases' / case['case_id'] / actual['data_file']),
                'state_mat_path': str(Path(directory) / 'cases' / case['case_id'] / actual['state_mat_file']),
                'state_data_path': str(Path(directory) / 'cases' / case['case_id'] / actual['state_data_file'])}
        except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
            case_errors.append(case['case_id'] + ': ' + str(error))
            errors.extend(case_errors)
        case_results.append({'case_id': case['case_id'], 'group_id': case['group_id'], 'level_id': case['level_id'],
                             'attempted': actual['attempted'], 'native_completed': actual['completed'],
                             'technically_verified': case['case_id'] in levels, 'native_record': deepcopy(actual), 'errors': case_errors})
    from numerical_obligations import evaluate_trial_numeric
    numeric, groups = [], []
    for group in request['groups']:
        completed_levels = [levels[x] for x in group['case_ids'] if x in levels]
        result = None
        if len(completed_levels) == 3:
            try:
                result = evaluate_trial_numeric(completed_levels, group['numeric_policy'], group['context'],
                                                project_id=report['project_id'], physical_sha256=group['physical_sha256'])
            except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
                errors.append(group['group_id'] + ': ' + str(error))
        numeric.append({'group_id': group['group_id'], 'physical_sha256': group['physical_sha256'], 'result': result})
        selected_cases = [x for x in case_results if x['case_id'] in group['case_ids']]
        status = 'unattempted' if not any(x['attempted'] for x in selected_cases) else 'complete' if len(completed_levels) == 3 else 'failed'
        groups.append({**deepcopy(group), 'levels': completed_levels, 'status': status, 'attempted': any(x['attempted'] for x in selected_cases), 'case_results': selected_cases, 'numerical_result': result,
                       'numerically_verified': bool(result and result.get('numerically_verified'))})
    complete = not errors and all(x['result'] is not None and x['result'].get('complete') is True for x in numeric)
    assert_unchanged(before)
    if source_identities() != request['sources']: raise ValueError('H safety source changed during batch consumption')
    return {'complete': complete, 'numerically_verified': complete and all(g['numerically_verified'] for g in groups),
            'numeric_results': numeric, 'groups': groups, 'case_results': case_results, 'errors': errors, 'input_manifest': before}


def validate_h_analysis_trial_receipt(receipt_path, *, project_root=None, study_report=None):
    # The session is confined to this read-only consumer. A producer's earlier
    # source/profile gates cannot leave a qualification proof alive here.
    from verification_common import validation_session
    with validation_session():
        return _validate_h_analysis_trial_receipt(receipt_path, project_root=project_root, study_report=study_report)


def _validate_h_analysis_trial_receipt(receipt_path, *, project_root=None, study_report=None):
    result = {'valid': False, 'trial_complete': False, 'numerically_verified': False, 'project_id': None, 'study_path': None,
              'study_sha256': None, 'study_semantic_sha256': None, 'base_protocol_path': None, 'base_protocol_sha256': None,
              'base_simulation_receipt_path': None, 'primary_numerical_receipt_path': None, 'receipt_path': None,
              'receipt_sha256': None, 'raw_path': None, 'runtime': None, 'installation_identity_checked': False, 'numeric_results': [], 'groups': [], 'case_results': [], 'process': None, 'input_manifest': [], 'errors': []}
    replay = None
    try:
        from validate_h_analysis_profile import evidence_chain
        from h_analysis_study import validate_h_analysis_study
        path, names = Path(receipt_path).resolve(), contract()['evidence']
        if path.name != names['run_receipt']: raise ValueError('unexpected H trial receipt filename')
        request, raw, receipt, times, before = evidence_chain(path, project_root=project_root)
        b = request['bindings']
        root = Path(b['project_root']).resolve()
        if project_root is not None and root != Path(project_root).resolve(): raise ValueError('H trial project root differs')
        report = validate_h_analysis_study(b['study']['path'], project_root=root, require_reviewed=True)
        if study_report is not None and any(not typed_equal(study_report[k], report[k]) for k in ('project_id', 'contract_sha256', 'semantic_sha256', 'bound_files', 'design', 'native_budget')):
            raise ValueError('supplied current study report differs from independent baseline/source validation')
        verify_study_bindings(request, report)
        replay = _mint_historical_replay(request, raw, path.parent)
        checked = assess_trial_request(request, raw, path.parent, report, process=receipt['process'],
                                       _historical_replay=replay)
        if receipt.get('project_id') != report['project_id'] or receipt.get('study_semantic_sha256') != report['semantic_sha256'] or not typed_equal(receipt.get('protected_files'), b['protected_files']):
            raise ValueError('H trial receipt project/study/protected identity differs')
        if not typed_equal(receipt.get('numeric_results'), checked['numeric_results']) or receipt.get('status') != ('completed' if checked['complete'] else 'incomplete') or not typed_equal(receipt.get('errors'), checked['errors']):
            raise ValueError('H trial receipt differs from independent per-point numerical recomputation')
        assert_unchanged(before)
        # A new qualification fact is published only after the real complete
        # historical receipt's original source/native/result and final guards.
        _finish_historical_replay(replay, complete=checked['complete'])
        replay = None
        result.update(valid=True, trial_complete=checked['complete'], numerically_verified=checked['numerically_verified'],
                      project_id=report['project_id'], study_path=report['contract_path'], study_sha256=report['contract_sha256'],
                      study_semantic_sha256=report['semantic_sha256'], base_protocol_path=b['base_protocol']['path'],
                      base_protocol_sha256=b['base_protocol']['sha256'], base_simulation_receipt_path=b['base_simulation_receipt']['path'],
                      primary_numerical_receipt_path=b['primary_numerical_receipt']['path'], receipt_path=str(path), receipt_sha256=sha256_file(path),
                      raw_path=str(path.parent / names['raw']), runtime=receipt['runtime'], installation_identity_checked=receipt['runtime'] is not None, numeric_results=checked['numeric_results'],
                      groups=checked['groups'], case_results=checked['case_results'], process=receipt['process'], input_manifest=before, errors=checked['errors'])
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        result['errors'].append(str(error))
    finally:
        _finish_historical_replay(replay, complete=False)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('receipt', type=Path)
    parser.add_argument('--project-root', type=Path)
    args = parser.parse_args()
    result = validate_h_analysis_trial_receipt(args.receipt, project_root=args.project_root)
    emit(result)
    return 0 if result['valid'] and result['trial_complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
