"""Run a reviewed finite catalog through the existing frozen-E executor."""
from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from runtime_common import ROOT, canonical_digest, contained_path, emit, load_contract, load_document, sha256_file
from validate_environment import validate_environment
from validate_implementation_receipt import same_runtime
from validate_simulation_profile import finite, validate_simulation_profile

INPUT = 'campaign-inputs.json'
LEDGER = 'campaign-ledger.json'
SUMMARY = 'campaign-summary.json'
RECEIPT = 'experiment-receipt.json'
METHODS = ('scenario_matrix', 'full_factorial', 'monte_carlo_catalog')
OPERATIONS = {'experiment.sample_plan.' + method for method in METHODS}


def contract():
    return load_contract('core/experiment_assurance_contract.yaml')


def source_identities():
    return {name: sha256_file(ROOT / name) for name in contract()['source_files']}


def file_binding(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': sha256_file(path)}


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def checkpoint(path, value):
    """Encode before opening; retain the old checkpoint and temporary on failure."""
    path = Path(path)
    encoded = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
    temporary = path.parent / (path.name + '.' + str(uuid.uuid4()) + '.tmp')
    if path.is_dir():
        raise ValueError('checkpoint target is a directory')
    with temporary.open('xb') as stream:
        if stream.write(encoded) != len(encoded):
            raise OSError('incomplete checkpoint write')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    if path.read_bytes() != encoded:
        raise OSError('checkpoint replacement differs from encoded bytes')


def required_a_operations(report, requested=()):
    if not isinstance(requested, (list, tuple)) or not all(isinstance(v, str) for v in requested):
        raise ValueError('required operations must be an array of IDs')
    selected = 'experiment.sample_plan.' + report['method']
    if set(requested) & (OPERATIONS - {selected}):
        raise ValueError('another G sampling method does not authorize this campaign')
    caller = [v for v in requested if v not in {selected, 'simulink.core_simulation'}]
    policy = load_contract('core/runtime_assurance_contract.yaml')
    operations = list(dict.fromkeys(policy['core_operations'] + report['required_A_operations'] + caller))
    if set(operations) - set(policy['operations']):
        raise ValueError('unknown required A operation')
    return operations


def verify_request(request, *, historical_start=None, expected_root=None):
    """Recheck immutable design sources and current or execution-time A/E/G."""
    from validate_experiment_design import validate_experiment_design
    from validate_experiment_profile import validate_experiment_profile
    expected = {'schema_version', 'run_id', 'project_id', 'project_root', 'output_directory',
                'design', 'design_snapshot', 'design_semantic_sha256', 'sampling_spec', 'sources',
                'required_A_operations', 'caller_required_operations', 'bindings', 'input_identity'}
    if set(request) != expected or type(request['schema_version']) is not int or request['schema_version'] != 1:
        raise ValueError('campaign request exact schema differs')
    uuid.UUID(request['run_id'])
    if request['sources'] != source_identities() or request['input_identity'] != canonical_digest({k:v for k,v in request.items() if k != 'input_identity'}):
        raise ValueError('campaign current source or input identity changed')
    root = Path(request['project_root']).resolve()
    directory = Path(request['output_directory']).resolve()
    if not directory.is_relative_to(root):
        raise ValueError('campaign output directory leaves project root')
    design = contained_path(root, request['design']['path'])
    if sha256_file(design) != request['design']['sha256'] or canonical_digest(load_document(design)) != canonical_digest(request['design_snapshot']):
        raise ValueError('complete reviewed design changed')
    report = validate_experiment_design(design, project_root=root, require_reviewed=True)
    if not report['valid'] or not report['design_ready'] or not report['reviewed'] or not report['campaign_execution_ready']:
        raise ValueError('current reviewed complete experiment design required: ' + '; '.join(report['errors'] + report['missing_gates']))
    if (report['project_id'] != request['project_id'] or report['design_sha256'] != request['design']['sha256']
            or report['semantic_sha256'] != request['design_semantic_sha256']
            or canonical_digest(report['sampling_spec']) != canonical_digest(request['sampling_spec'])):
        raise ValueError('campaign project, design or sampling identity changed')
    if required_a_operations(report, request['caller_required_operations']) != request['required_A_operations']:
        raise ValueError('required A operation union changed')
    for item in report['bound_files']:
        if sha256_file(contained_path(root, item['path'])) != item['sha256']:
            raise ValueError('campaign source bytes changed')
    bindings = request['bindings']
    if set(bindings) != {'environment_profile', 'environment_receipt', 'simulation_profile',
                         'simulation_profile_receipt', 'experiment_profile', 'experiment_profile_receipt', 'matlab_executable'}:
        raise ValueError('campaign qualification binding surface differs')
    for name, binding in bindings.items():
        if name != 'matlab_executable' and sha256_file(binding['path']) != binding['sha256']:
            raise ValueError('campaign qualification bytes changed: ' + name)
    a = validate_environment(bindings['environment_profile']['path'], required_operations=request['required_A_operations'], now=historical_start, expected_root=expected_root)
    e = validate_simulation_profile(bindings['simulation_profile']['path'], required_solver='ode4', now=historical_start, expected_root=expected_root)
    g = validate_experiment_profile(bindings['experiment_profile']['path'], required_method=report['method'], now=historical_start)
    if not a['valid'] or not e['valid'] or not g['valid']:
        raise ValueError('required independent A/E/G qualification failed: ' + '; '.join(a['errors'] + e['errors'] + g['errors']))
    runtime = load_document(bindings['environment_profile']['path'])['runtime']
    if not same_runtime(runtime, e['runtime']) or not same_runtime(runtime, g['runtime']) or Path(bindings['matlab_executable']).resolve() != Path(runtime['executable']).resolve():
        raise ValueError('campaign A/E/G runtime or requested executable differs')
    for member in report['catalog']:
        protocol = member['protocol_report']
        if not protocol['execution_ready'] or protocol['run_spec']['solver']['name'] != 'ode4':
            raise ValueError('each member requires the current complete frozen E ode4 protocol')
        if not same_runtime(load_document(protocol['implementation_receipt_path'])['runtime'], runtime):
            raise ValueError('campaign historical D and execution runtime differ')
    return report, runtime


def artifact_manifest(directory):
    directory = Path(directory).resolve()
    result = {}
    for path in sorted(directory.rglob('*')):
        if path.is_file() and path != directory / RECEIPT:
            if not path.resolve().is_relative_to(directory):
                raise ValueError('campaign artifact leaves owned directory')
            relative = path.relative_to(directory).as_posix()
            result[relative] = {'sha256': sha256_file(path), 'bytes': path.stat().st_size}
    return result


def enforce_artifact_budget(directory, maximum):
    if sum(item['bytes'] for item in artifact_manifest(directory).values()) > maximum:
        raise ValueError('campaign artifact byte budget exceeded; all evidence retained')


def run_experiment(design_path, executable, directory, *, environment_profile, simulation_profile,
                   experiment_profile, project_root=None, required_operations=None):
    from validate_experiment_design import validate_experiment_design
    from experiment_sampling import sample_experiment, validate_sample_receipt
    from run_simulation import run_simulation
    from validate_experiment_receipt import metric_value, summarize, validate_experiment_receipt
    root = Path(project_root or Path(design_path).resolve().parent).resolve()
    directory = Path(directory).resolve()
    report = validate_experiment_design(design_path, project_root=root, require_reviewed=True)
    if not report['valid'] or not report['design_ready'] or not report['reviewed'] or not report['campaign_execution_ready']:
        raise ValueError('current complete reviewed campaign required: ' + '; '.join(report['errors'] + report['missing_gates']))
    request = {'schema_version': 1, 'run_id': str(uuid.uuid4()), 'project_id': report['project_id'],
               'project_root': str(root), 'output_directory': str(directory), 'design': file_binding(design_path),
               'design_snapshot': load_document(design_path), 'design_semantic_sha256': report['semantic_sha256'],
               'sampling_spec': report['sampling_spec'], 'sources': source_identities(),
               'caller_required_operations': list(required_operations or []),
               'required_A_operations': required_a_operations(report, required_operations or []),
               'bindings': {'environment_profile': file_binding(environment_profile),
                   'environment_receipt': file_binding(Path(environment_profile).parent / 'receipt.json'),
                   'simulation_profile': file_binding(simulation_profile),
                   'simulation_profile_receipt': file_binding(Path(simulation_profile).parent / load_contract('core/simulation_assurance_contract.yaml')['evidence']['profile_receipt']),
                   'experiment_profile': file_binding(experiment_profile),
                   'experiment_profile_receipt': file_binding(Path(experiment_profile).parent / contract()['evidence']['profile_receipt']),
                   'matlab_executable': str(Path(executable).resolve())}}
    request['input_identity'] = canonical_digest(request)
    report, runtime = verify_request(request)
    directory.mkdir(parents=True, exist_ok=False)
    started, monotonic_start = utc_now(), time.monotonic()
    budget, rows, sample_binding, summary, errors = report['budget'], [], None, None, []
    ledger = {'schema_version': 1, 'run_id': request['run_id'], 'status': 'running', 'rows': rows, 'errors': errors}
    checkpoint(directory / INPUT, request)
    checkpoint(directory / LEDGER, ledger)
    checkpoint(directory / SUMMARY, {'summary': None})
    try:
        remaining = budget['total_timeout'] - (time.monotonic() - monotonic_start)
        if remaining <= 0:
            raise ValueError('campaign total timeout exhausted before sampling')
        sample_path = Path(sample_experiment(report['sampling_spec'], executable, directory / 'sampling',
            environment_profile=environment_profile, experiment_profile=experiment_profile, timeout=remaining)).resolve()
        if not sample_path.is_relative_to(directory):
            raise ValueError('sampling receipt leaves owned campaign directory')
        sample_binding = file_binding(sample_path)
        sample = validate_sample_receipt(sample_path)
        if not sample['valid'] or sample['method'] != report['method'] or canonical_digest(sample['sampling_spec']) != canonical_digest(report['sampling_spec']) or not same_runtime(sample['runtime'], runtime):
            raise ValueError('actual sampling receipt failed or differs from campaign')
        indices = sample['sample_indices']
        if len(indices) != report['sampling_spec']['draws'] or len(indices) > budget['max_cases']:
            raise ValueError('actual draw count differs from fixed campaign budget')
        for draw, index in enumerate(indices, 1):
            if type(index) not in (int, float) or not finite(index) or int(index) != index or not 1 <= index <= len(report['catalog']):
                raise ValueError('sampling index is not a supported one-based catalog index')
            member = report['catalog'][int(index) - 1]
            rows.append({'draw': draw, 'catalog_index': int(index), 'catalog_id': member['id'],
                         'status': 'not_attempted', 'receipt': None, 'metric_value': None,
                         'started_at': None, 'finished_at': None, 'errors': []})
        checkpoint(directory / LEDGER, ledger)
        enforce_artifact_budget(directory, budget['max_artifact_bytes'])
        for row in rows:
            remaining = budget['total_timeout'] - (time.monotonic() - monotonic_start)
            if remaining <= 0:
                raise ValueError('campaign total timeout exhausted; remaining draws unattempted')
            process_timeout = min(budget['member_process_timeout'], remaining)
            if process_timeout <= budget['member_simulation_timeout']:
                raise ValueError('remaining campaign time cannot cover the declared E simulation timeout')
            verify_request(request)
            member = report['catalog'][row['catalog_index'] - 1]
            row.update(status='running', started_at=utc_now())
            checkpoint(directory / LEDGER, ledger)
            try:
                result = run_simulation(member['protocol_path'], executable, directory / ('draw-%03d' % row['draw']),
                    environment_profile=environment_profile, simulation_profile=simulation_profile,
                    project_root=root, timeout=process_timeout, simulation_timeout=budget['member_simulation_timeout'],
                    required_operations=request['required_A_operations'])
                if result.get('receipt_path') and Path(result['receipt_path']).is_file():
                    row['receipt'] = file_binding(result['receipt_path'])
                if not result['valid'] or not result.get('primary_run_complete'):
                    raise ValueError('E member failed: ' + '; '.join(result['errors']))
                if row['receipt'] is None:
                    raise ValueError('completed E draw has no persisted receipt')
                row['metric_value'] = metric_value(result, report['metric'])
                row.update(status='completed', finished_at=utc_now())
                enforce_artifact_budget(directory, budget['max_artifact_bytes'])
            except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
                row.update(status='failed', finished_at=utc_now(), metric_value=None, errors=[str(error)])
                checkpoint(directory / LEDGER, ledger)
                raise
            checkpoint(directory / LEDGER, ledger)
        if time.monotonic() - monotonic_start > budget['total_timeout']:
            raise ValueError('campaign total timeout exceeded after final draw')
        summary = summarize([row['metric_value'] for row in rows], report['method'], report['event'])
        ledger['status'] = 'completed'
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        errors.append(str(error))
        ledger['status'] = 'failed'
        summary = None
    for name, value in ((LEDGER, ledger), (SUMMARY, {'summary': summary})):
        try:
            checkpoint(directory / name, value)
        except (OSError, ValueError, TypeError, OverflowError) as error:
            errors.append('final checkpoint failed: ' + str(error))
            ledger['status'], summary = 'failed', None
    finished = utc_now()
    receipt = {'schema_version': 1, 'run_id': request['run_id'], 'project_id': request['project_id'],
               'input_identity': request['input_identity'], 'sources': request['sources'], 'runtime': runtime,
               'process': {'started_at': started, 'finished_at': finished, 'status': ledger['status']},
               'sampling_receipt': sample_binding, 'rows': rows, 'summary': summary, 'errors': errors,
               'artifacts': artifact_manifest(directory)}
    encoded_size = len((json.dumps(receipt, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8'))
    if sum(item['bytes'] for item in receipt['artifacts'].values()) + encoded_size > budget['max_artifact_bytes']:
        ledger['status'], summary = 'failed', None
        receipt['process']['status'], receipt['summary'] = 'failed', None
        errors.append('campaign artifact byte budget exceeded; evidence retained')
        checkpoint(directory / LEDGER, ledger)
        checkpoint(directory / SUMMARY, {'summary': None})
        receipt['artifacts'] = artifact_manifest(directory)
    checkpoint(directory / RECEIPT, receipt)
    result = validate_experiment_receipt(directory / RECEIPT, project_root=root, design_report=report)
    result['receipt_path'] = str(directory / RECEIPT)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('design', type=Path)
    parser.add_argument('--project-root', type=Path)
    parser.add_argument('--matlab-executable', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--environment-profile', type=Path, required=True)
    parser.add_argument('--simulation-profile', type=Path, required=True)
    parser.add_argument('--experiment-profile', type=Path, required=True)
    parser.add_argument('--require-operation', action='append', default=[])
    args = parser.parse_args()
    try:
        result = run_experiment(args.design, args.matlab_executable, args.output_dir,
            environment_profile=args.environment_profile, simulation_profile=args.simulation_profile,
            experiment_profile=args.experiment_profile, project_root=args.project_root, required_operations=args.require_operation)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        result = {'valid': False, 'campaign_complete': False, 'errors': [str(error)]}
    emit(result)
    return 0 if result['valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
