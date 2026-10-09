"""Recompute H receipt mathematics and all historical source bindings; read only."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from runtime_common import canonical_digest, emit
from run_verification import FILES, RECEIPT, numeric_csv, source_identities
from verification_analysis import analyze
from verification_common import Budget


def validate_verification_receipt(path, *, project_root=None, kind=None, budget=None):
    budget = budget or Budget()
    failure = {'valid': False, 'evidence_complete': False, 'checks_passed': False,
               'numerically_verified': False, 'model_verification_decided': False,
               'model_verified': False, 'ledger': [], 'errors': []}
    try:
        path = Path(path).resolve()
        if path.name != RECEIPT:
            raise ValueError('unexpected H receipt filename')
        receipt = budget.read(path)
        expected = {'schema_version', 'kind', 'project_id', 'started_at', 'finished_at', 'sources', 'artifacts', 'native_execution'}
        if set(receipt) != expected or type(receipt['schema_version']) is not int or receipt['schema_version'] != 1 or receipt['native_execution'] is not False:
            raise ValueError('H receipt exact surface differs')
        if receipt['sources'] != source_identities():
            raise ValueError('H consumer source closure changed')
        start, finish = [datetime.fromisoformat(receipt[k]) for k in ('started_at', 'finished_at')]
        if start.tzinfo is None or finish.tzinfo is None or not start <= finish <= datetime.now(timezone.utc) or (finish-start).total_seconds() > 120:
            raise ValueError('H recorded analysis chronology/budget differs')
        if set(receipt['artifacts']) != set(FILES):
            raise ValueError('H exact artifact set differs')
        for name in FILES:
            binding = receipt['artifacts'][name]
            if set(binding) != {'file', 'sha256'} or binding['file'] != name:
                raise ValueError('H artifact identity differs')
            budget.bind({'path': name, 'sha256': binding['sha256']}, path.parent)
        inputs = budget.read(path.parent / FILES[0])
        if set(inputs) != {'schema_version', 'kind', 'project_root', 'plan', 'plan_snapshot', 'plan_original_text', 'sources'} or inputs['schema_version'] != 1:
            raise ValueError('H captured input surface differs')
        root = Path(inputs['project_root']).resolve()
        if project_root is not None and root != Path(project_root).resolve():
            raise ValueError('H project root differs')
        if not path.is_relative_to(root) or inputs['sources'] != receipt['sources'] or inputs['kind'] != receipt['kind'] or (kind and receipt['kind'] != kind):
            raise ValueError('H root/source/kind identity differs')
        plan_path = budget.bind(inputs['plan'], root)
        if plan_path.read_text(encoding='utf-8') != inputs['plan_original_text'] or canonical_digest(budget.read(plan_path)) != canonical_digest(inputs['plan_snapshot']):
            raise ValueError('H complete captured plan changed')
        result = analyze(plan_path, project_root=root, kind=receipt['kind'], budget=budget)
        if result['project_id'] != receipt['project_id'] or canonical_digest(result) != canonical_digest(budget.read(path.parent / FILES[1])):
            raise ValueError('H producer result differs from independent recomputation')
        if (path.parent / FILES[2]).read_text(encoding='utf-8') != numeric_csv(result):
            raise ValueError('H numeric CSV differs from recomputation')
        budget.finish()
        result.update(receipt_path=str(path), receipt_sha256=budget.identities[path], project_root=str(root))
        return result
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError, RecursionError) as error:
        failure['errors'].append(str(error))
        return failure


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', type=Path)
    parser.add_argument('--project-root', type=Path)
    parser.add_argument('--kind', choices=['H1', 'H2'])
    args = parser.parse_args()
    result = validate_verification_receipt(args.path, project_root=args.project_root, kind=args.kind)
    emit(result)
    return 0 if result['valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
