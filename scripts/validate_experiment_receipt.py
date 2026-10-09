"""Re-read sampled draws and each E receipt; independently reconstruct the campaign."""
from __future__ import annotations

import argparse
import math
from datetime import datetime, timezone
from pathlib import Path

from runtime_common import canonical_digest, contained_path, emit, load_document, sha256_file
from validate_environment import _time
from validate_implementation_receipt import same_runtime
from validate_simulation_profile import contract as simulation_contract, finite

WILSON_Z = 1.959963984540054


def metric_value(member_report, definition):
    matches = [v for v in member_report['metrics'] if v['id'] == definition['id']]
    if len(matches) != 1 or not finite(matches[0]['value']) or matches[0].get('passed') is not True:
        raise ValueError('exact complete admissible E metric required')
    return float(matches[0]['value'])


def summarize(values, method, event):
    """Fixed-n descriptive results; nominal Wilson applies only to a declared MC event."""
    if not values or not all(finite(v) for v in values):
        raise ValueError('complete finite draws required for a campaign summary')
    n = len(values)
    mean = math.fsum(v / n for v in values)
    if not finite(mean):
        raise ValueError('nonfinite campaign mean')
    result = {'method': method, 'n': n, 'mean': mean, 'minimum': min(values), 'maximum': max(values), 'event': None}
    if method != 'monte_carlo_catalog':
        if event is not None:
            raise ValueError('deterministic campaign does not grant a confidence interval')
        return result
    if (not isinstance(event, dict) or set(event) != {'comparator', 'threshold', 'confidence', 'interval', 'unit'}
            or event['comparator'] not in {'gt', 'lt'} or not finite(event['threshold'])
            or event['confidence'] != 0.95 or event['interval'] != 'wilson_95'):
        raise ValueError('frozen nominal 95 percent Wilson event required')
    k = sum(v > event['threshold'] if event['comparator'] == 'gt' else v < event['threshold'] for v in values)
    p, z2 = k / n, WILSON_Z ** 2
    denominator = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denominator
    half = WILSON_Z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denominator
    result['event'] = {**event, 'count': k, 'denominator': n, 'estimate': p,
                       'lower': max(0.0, center - half), 'upper': min(1.0, center + half)}
    return result


def validate_experiment_receipt(path, *, project_root=None, design_report=None):
    result = {'valid': False, 'campaign_complete': False,
              'receipt_path': None, 'receipt_sha256': None, 'project_id': None,
              'design_path': None, 'design_sha256': None, 'semantic_sha256': None,
              'method': None, 'rows': [], 'summary': None, 'errors': []}
    try:
        from run_experiment import INPUT, LEDGER, SUMMARY, RECEIPT, artifact_manifest, verify_request
        from experiment_sampling import validate_sample_receipt
        from validate_simulation_receipt import validate_simulation_receipt
        path = Path(path).resolve()
        if path.name != RECEIPT:
            raise ValueError('unexpected campaign receipt filename')
        directory = path.parent
        receipt, request = load_document(path), load_document(directory / INPUT)
        fields = {'schema_version', 'run_id', 'project_id', 'input_identity', 'sources', 'runtime',
                  'process', 'sampling_receipt', 'rows', 'summary', 'errors', 'artifacts'}
        if set(receipt) != fields or type(receipt['schema_version']) is not int or receipt['schema_version'] != 1:
            raise ValueError('campaign receipt exact schema differs')
        for field in ('run_id', 'project_id', 'input_identity', 'sources'):
            if receipt[field] != request[field]:
                raise ValueError('campaign receipt/input identity differs: ' + field)
        if Path(request['output_directory']).resolve() != directory:
            raise ValueError('campaign owned directory identity differs')
        if project_root is not None and Path(project_root).resolve() != Path(request['project_root']).resolve():
            raise ValueError('campaign project root differs')
        process = receipt['process']
        if set(process) != {'started_at', 'finished_at', 'status'} or process['status'] not in {'completed', 'failed'}:
            raise ValueError('campaign process status surface differs')
        start, finish = _time(process['started_at']), _time(process['finished_at'])
        if not start < finish <= datetime.now(timezone.utc):
            raise ValueError('campaign future/reversed/incomplete chronology')
        report, runtime = verify_request(request, historical_start=start)
        if not same_runtime(runtime, receipt['runtime']):
            raise ValueError('campaign runtime identity changed')
        if design_report is not None and any(canonical_digest(design_report[key]) != canonical_digest(report[key])
                for key in ('project_id', 'design_sha256', 'semantic_sha256', 'sampling_spec', 'metric', 'event', 'budget', 'bound_files')):
            raise ValueError('supplied design report differs from the current source-bound campaign')
        actual_manifest = artifact_manifest(directory)
        if receipt['artifacts'] != actual_manifest or sum(v['bytes'] for v in actual_manifest.values()) + path.stat().st_size > report['budget']['max_artifact_bytes']:
            raise ValueError('campaign exact artifact set/digests or byte budget differs')
        ledger = load_document(directory / LEDGER)
        if (set(ledger) != {'schema_version', 'run_id', 'status', 'rows', 'errors'} or ledger['schema_version'] != 1
                or ledger['run_id'] != request['run_id'] or ledger['status'] != process['status']
                or ledger['rows'] != receipt['rows'] or ledger['errors'] != receipt['errors']):
            raise ValueError('persisted campaign ledger differs')
        if load_document(directory / SUMMARY) != {'summary': receipt['summary']}:
            raise ValueError('persisted campaign summary differs')
        if not isinstance(receipt['rows'], list) or not isinstance(receipt['errors'], list) or not all(isinstance(v, str) for v in receipt['errors']):
            raise ValueError('campaign rows/errors must be arrays')
        result.update(receipt_path=str(path), receipt_sha256=sha256_file(path), project_id=report['project_id'],
                      design_path=report['contract_path'], design_sha256=report['design_sha256'],
                      semantic_sha256=report['semantic_sha256'], method=report['method'], rows=receipt['rows'])
        sample_binding = receipt['sampling_receipt']
        if sample_binding is None:
            if process['status'] != 'failed' or receipt['rows'] or receipt['summary'] is not None:
                raise ValueError('missing sampling receipt cannot establish a campaign')
            raise ValueError('sampling did not complete; retained campaign is incomplete')
        if set(sample_binding) != {'path', 'sha256'}:
            raise ValueError('sampling receipt binding differs')
        sample_path = contained_path(directory, sample_binding['path'])
        if sample_path.parent != directory / 'sampling' or sha256_file(sample_path) != sample_binding['sha256']:
            raise ValueError('actual owned sampling receipt changed')
        sample = validate_sample_receipt(sample_path)
        if not sample['valid'] or sample['method'] != report['method'] or canonical_digest(sample['sampling_spec']) != canonical_digest(report['sampling_spec']) or not same_runtime(sample['runtime'], runtime):
            raise ValueError('independent actual sampling evidence differs or failed')
        sample_process = sample.get('process') or load_document(sample_path)['process']
        sample_start, sample_finish = _time(sample_process['started_at']), _time(sample_process['finished_at'])
        if not start <= sample_start <= sample_finish <= finish:
            raise ValueError('sampling execution leaves campaign chronology')
        indices = sample['sample_indices']
        if len(indices) != report['sampling_spec']['draws'] or len(indices) > report['budget']['max_cases'] or len(receipt['rows']) != len(indices):
            raise ValueError('fixed draw count or exact row count differs')
        values, seen_receipts, seen_run_ids, incomplete = [], set(), set(), False
        previous_finish = sample_finish
        for draw, (row, index) in enumerate(zip(receipt['rows'], indices), 1):
            row_fields = {'draw', 'catalog_index', 'catalog_id', 'status', 'receipt', 'metric_value', 'started_at', 'finished_at', 'errors'}
            if set(row) != row_fields or type(row['draw']) is not int or row['draw'] != draw:
                raise ValueError('campaign exact draw row identity differs')
            if type(index) not in (int, float) or not finite(index) or int(index) != index or not 1 <= index <= len(report['catalog']):
                raise ValueError('actual sampling index is invalid')
            member = report['catalog'][int(index) - 1]
            if type(row['catalog_index']) is not int or row['catalog_index'] != int(index) or row['catalog_id'] != member['id']:
                raise ValueError('draw order/catalog identity differs from actual sampled indices')
            if row['status'] not in {'completed', 'failed', 'not_attempted'} or not isinstance(row['errors'], list):
                raise ValueError('final campaign row status/errors differ')
            if row['status'] == 'not_attempted':
                if any(row[k] is not None for k in ('receipt', 'metric_value', 'started_at', 'finished_at')) or row['errors']:
                    raise ValueError('unattempted draw contains fabricated execution evidence')
                incomplete = True
                continue
            if incomplete:
                raise ValueError('campaign continued after a failed or unattempted draw')
            row_start, row_finish = _time(row['started_at']), _time(row['finished_at'])
            if not previous_finish <= row_start <= row_finish <= finish:
                raise ValueError('campaign members were not sequential within recorded execution')
            verify_request(request, historical_start=row_start)
            previous_finish = row_finish
            binding = row['receipt']
            if binding is None:
                if row['status'] != 'failed' or row['metric_value'] is not None:
                    raise ValueError('successful draw has no actual E receipt')
                incomplete = True
                continue
            if set(binding) != {'path', 'sha256'}:
                raise ValueError('E member receipt binding differs')
            e_path = contained_path(directory, binding['path'])
            if e_path.parent != directory / ('draw-%03d' % draw) or sha256_file(e_path) != binding['sha256'] or str(e_path) in seen_receipts:
                raise ValueError('draw needs a distinct unchanged E receipt in its owned directory')
            seen_receipts.add(str(e_path))
            e_receipt = load_document(e_path)
            if e_receipt['run_id'] in seen_run_ids:
                raise ValueError('repeated catalog draws must have independent E run IDs')
            seen_run_ids.add(e_receipt['run_id'])
            e_start, e_finish = _time(e_receipt['process']['started_at']), _time(e_receipt['process']['finished_at'])
            if not row_start <= e_start <= e_finish <= row_finish:
                raise ValueError('actual E process leaves its draw chronology')
            e_input = load_document(e_path.parent / simulation_contract()['evidence']['input'])
            e_bindings = e_input['bindings']
            for name in ('environment_profile', 'environment_receipt', 'simulation_profile', 'simulation_profile_receipt'):
                if e_bindings[name] != request['bindings'][name]:
                    raise ValueError('actual E qualification differs from campaign binding: ' + name)
            expected_operations = list(dict.fromkeys(member['protocol_report']['required_A_operations']
                                                     + request['required_A_operations']))
            if e_bindings['required_A_operations'] != expected_operations:
                raise ValueError('actual E required A operations differ from the complete campaign union')
            e_cases = e_input['cases']
            if (not isinstance(e_cases, list) or len(e_cases) != 1
                    or not finite(e_cases[0]['simulation_timeout'])
                    or e_cases[0]['simulation_timeout'] != report['budget']['member_simulation_timeout']):
                raise ValueError('actual E simulation timeout differs from the reviewed member budget')
            if (e_finish - e_start).total_seconds() > report['budget']['member_process_timeout']:
                raise ValueError('actual E process exceeded the reviewed member budget')
            actual = validate_simulation_receipt(e_path, project_root=request['project_root'], protocol_report=member['protocol_report'])
            if row['status'] == 'failed':
                if row['metric_value'] is not None:
                    raise ValueError('failed draw contains a summary metric')
                incomplete = True
                continue
            if row['errors'] or not actual['valid'] or not actual.get('primary_run_complete'):
                raise ValueError('completed draw lacks actual admissible E evidence')
            value = metric_value(actual, report['metric'])
            if not finite(row['metric_value']) or value != row['metric_value']:
                raise ValueError('draw metric differs from independent E numeric readback')
            values.append(value)
        if incomplete or process['status'] != 'completed' or receipt['errors']:
            if receipt['summary'] is not None:
                raise ValueError('incomplete campaign cannot publish a complete summary or confidence interval')
            raise ValueError('campaign contains a failed or unattempted draw; no complete fixed-n result')
        if (finish - start).total_seconds() > report['budget']['total_timeout']:
            raise ValueError('campaign exceeded its total wall-clock budget')
        expected_summary = summarize(values, report['method'], report['event'])
        if canonical_digest(receipt['summary']) != canonical_digest(expected_summary):
            raise ValueError('campaign summary/counts/denominator/Wilson interval differ from actual ordered draws')
        result.update(valid=True, campaign_complete=True, summary=expected_summary)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        result['errors'].append(str(error))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', type=Path)
    parser.add_argument('--project-root', type=Path)
    args = parser.parse_args()
    result = validate_experiment_receipt(args.path, project_root=args.project_root)
    emit(result)
    return 0 if result['valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
