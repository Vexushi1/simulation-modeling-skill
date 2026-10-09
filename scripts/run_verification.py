"""Generate fresh H evidence using Python historical consumers; never spawn MATLAB."""
from __future__ import annotations

import argparse
import csv
import io
from datetime import datetime, timezone
from pathlib import Path

from probe_environment import write_json
from runtime_common import ROOT, emit, load_contract, sha256_file
from verification_analysis import analyze
from verification_common import Budget

RECEIPT = 'verification-receipt.json'
FILES = ('verification-inputs.json', 'verification-result.json', 'verification-numeric.csv')


def source_identities():
    paths = load_contract('core/numerical_verification_contract.yaml')['source_files']
    if not paths or len(paths) != len(set(paths)):
        raise ValueError('complete unique H source closure required')
    return {p: sha256_file(ROOT / p) for p in sorted(paths)}


def numeric_csv(result):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, lineterminator='\n')
    writer.writerow(['record', 'id', 'port_or_index', 'metric', 'value'])
    for row in result['ledger']:
        for check in row['checks']:
            for metric in ('max_abs_error', 'max_scaled_error', 'terminal_error'):
                writer.writerow(['run', row['id'], check['output_port'], metric, repr(check[metric])])
    for analysis in result['analyses']:
        for index, value in enumerate(analysis['numeric']['values'], 1):
            writer.writerow(['analysis', analysis['id'], index, 'criterion_value', repr(value)])
    return stream.getvalue()


def run_verification(path, directory, *, project_root=None, kind=None):
    root = Path(project_root or Path(path).resolve().parent).resolve()
    directory = Path(directory).resolve()
    if not directory.is_relative_to(root) or directory == root or directory.exists():
        raise ValueError('H requires a new evidence directory inside the project root')
    budget = Budget()
    plan_path = Path(path).resolve()
    if not plan_path.is_relative_to(root):
        raise ValueError('H plan leaves project root')
    plan = budget.read(plan_path)
    original = plan_path.read_text(encoding='utf-8')
    sources = source_identities()
    started = datetime.now(timezone.utc).isoformat()
    result = analyze(plan_path, project_root=root, kind=kind, budget=budget)
    finished = datetime.now(timezone.utc).isoformat()
    if sources != source_identities():
        result.update(valid=False, evidence_complete=False, numerically_verified=False,
                      model_verified=False, summary=None)
        result['errors'].append('H consumer source changed during analysis')
    inputs = {'schema_version': 1, 'kind': result['kind'], 'project_root': str(root),
              'plan': {'path': str(plan_path), 'sha256': budget.identities[plan_path]},
              'plan_snapshot': plan, 'plan_original_text': original, 'sources': sources}
    directory.mkdir(parents=True, exist_ok=False)
    write_json(directory / FILES[0], inputs)
    write_json(directory / FILES[1], result)
    (directory / FILES[2]).write_text(numeric_csv(result), encoding='utf-8', newline='\n')
    receipt = {'schema_version': 1, 'kind': result['kind'], 'project_id': result['project_id'],
               'started_at': started, 'finished_at': finished, 'sources': sources,
               'artifacts': {name: {'file': name, 'sha256': sha256_file(directory / name)} for name in FILES},
               'native_execution': False}
    write_json(directory / RECEIPT, receipt)
    result['receipt_path'] = str(directory / RECEIPT)
    return result


def main(kind=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', type=Path)
    parser.add_argument('--project-root', type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    try:
        result = run_verification(args.path, args.output_dir, project_root=args.project_root, kind=kind)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        result = {'valid': False, 'errors': [str(error)]}
    emit(result)
    return 0 if result['valid'] else 1
