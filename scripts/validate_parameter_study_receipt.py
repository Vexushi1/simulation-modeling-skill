"""Read historical candidate trials; never adopt parameters or promote project state."""
from __future__ import annotations

import argparse
from pathlib import Path

from parameter_study_common import assert_case, contract, records
from runtime_common import canonical_digest, emit, load_document, sha256_file
from run_parameter_study import verify_trial_bindings
from validate_environment import _path
from validate_implementation_receipt import same_runtime
from validate_parameter_study_profile import observed_runtime, validate_evidence_chain


def validate_parameter_study_receipt(path, *, project_root=None, study_report=None):
    result = {'valid': False, 'trial_complete': False, 'candidate_complete': False, 'criteria_satisfied': False,
              'study_sha256': None, 'study_semantic_sha256': None, 'native_spec_sha256': None, 'operation_id': None, 'method': None,
              'environment_profile_sha256': None, 'parameter_study_profile_sha256': None, 'runtime': None, 'receipt_sha256': None, 'errors': []}
    try:
        path = Path(path).resolve()
        if path.name != contract()['evidence']['run_receipt']:
            raise ValueError('unexpected F trial receipt filename')
        request, raw, receipt, times = validate_evidence_chain(path)
        if request['mode'] != 'trial' or len(request['operations']) != 1:
            raise ValueError('independent probe cannot produce project candidate completion')
        if project_root is not None and Path(project_root).resolve() != Path(request['bindings']['project_root']).resolve():
            raise ValueError('trial project identity differs')
        report, runtime = verify_trial_bindings(request, historical_start=times[0])
        if study_report is not None and (study_report['study_sha256'] != report['study_sha256'] or study_report['semantic_sha256'] != report['semantic_sha256']):
            raise ValueError('supplied study report is stale')
        if receipt['project_id'] != report['project_id'] or receipt['study_sha256'] != report['study_sha256'] or receipt['study_semantic_sha256'] != report['semantic_sha256'] or receipt['native_spec_sha256'] != canonical_digest(report['native_spec']):
            raise ValueError('trial receipt study identity changed')
        actual_runtime = observed_runtime(raw, request)
        if not same_runtime(actual_runtime, runtime):
            raise ValueError('actual trial differs from qualified F runtime')
        qualification_raw = load_document(Path(request['bindings']['parameter_study_profile']['path']).parent/contract()['evidence']['raw'])
        qualified_functions = {item['name']: item['path'] for item in records(qualification_raw['functions'], 'qualification.functions')}
        if any(item['name'] not in qualified_functions or _path(item['path']) != _path(qualified_functions[item['name']]) for item in raw['functions']):
            raise ValueError('actual trial function resolution differs from qualified selected method')
        qualified_files = {_path(item['path']): item['sha256'] for item in runtime['function_files']}
        if any(qualified_files.get(_path(item['path'])) != item['sha256'] for item in actual_runtime['function_files']):
            raise ValueError('actual trial function-file bytes differ from qualified selected method')
        cases = records(raw['cases'], 'raw.cases')
        if len(cases) != 1:
            raise ValueError('single candidate trial required')
        metrics = assert_case(cases[0], request['cases'][0], path.parent, request['run_id'])
        result.update(valid=True, trial_complete=True, candidate_complete=metrics['candidate_complete'], criteria_satisfied=metrics['criteria_satisfied'],
                      study_sha256=report['study_sha256'], study_semantic_sha256=report['semantic_sha256'], native_spec_sha256=receipt['native_spec_sha256'],
                      operation_id=report['operation_id'], method=report['method'], runtime=actual_runtime, receipt_sha256=sha256_file(path),
                      environment_profile_sha256=request['bindings']['environment_profile']['sha256'], parameter_study_profile_sha256=request['bindings']['parameter_study_profile']['sha256'],
                      candidate=cases[0]['theta'], ledger=cases[0]['ledger'])
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        result['errors'].append(str(error))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', type=Path)
    parser.add_argument('--project-root', type=Path)
    args = parser.parse_args()
    result = validate_parameter_study_receipt(args.path, project_root=args.project_root)
    emit(result)
    return 0 if result['valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
