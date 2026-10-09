"""Review source-bound H plans; incomplete drafts grant no analysis acceptance."""
from __future__ import annotations

import argparse
from pathlib import Path

from runtime_common import emit, load_contract, schema_errors
from verification_common import Budget, H1_METHODS, H2_METHODS, semantic_digest


def validate_verification(path, *, project_root=None, kind=None, require_reviewed=False, budget=None):
    budget = budget or Budget()
    result = {'schema_valid': False, 'valid': False, 'reviewed': False, 'plan_complete': False,
              'plan_path': str(Path(path).resolve()), 'plan_sha256': None, 'project_id': None,
              'semantic_sha256': None, 'kind': None, 'errors': [], 'missing_gates': [],
              'environment_checked': False, 'execution_allowed': False}
    errors, missing = result['errors'], result['missing_gates']
    try:
        path = Path(path).resolve()
        root = Path(project_root or path.parent).resolve()
        if not path.is_relative_to(root):
            raise ValueError('H plan leaves project root')
        plan = budget.read(path)
        errors.extend(schema_errors(plan, load_contract('core/verification.schema.yaml')))
        if errors:
            return result
        result.update(schema_valid=True, plan_sha256=budget.identities[path], project_id=plan['project_id'],
                      kind=plan['kind'], semantic_sha256=semantic_digest(plan))
        if type(plan['schema_version']) is not int or (kind and plan['kind'] != kind):
            raise ValueError('H plan kind/schema version differs')
        source_ids = {s['id'] for s in plan['sources']}
        if len(source_ids) != len(plan['sources']):
            raise ValueError('duplicate H source IDs')
        for source in plan['sources']:
            budget.bind({k: source[k] for k in ('path', 'sha256')}, root)
        def sources(item):
            if not item['source_ids'] or set(item['source_ids']) - source_ids:
                raise ValueError('source-bound H technical/reference decision required')
        methods = H1_METHODS if plan['kind'] == 'H1' else H2_METHODS
        if not plan['requirements']:
            missing.append('task_check_requirements')
        requirement_ids = [r['id'] for r in plan['requirements']]
        if len(set(requirement_ids)) != len(requirement_ids):
            raise ValueError('duplicate H requirement IDs')
        for requirement in plan['requirements']:
            sources(requirement)
            if requirement['required'] and requirement['method'] not in methods:
                missing.append('unsupported_required:' + requirement['method'])
        if plan['kind'] == 'H1' and not any(r['required'] and r['method'] == 'analytic_reference' for r in plan['requirements']):
            missing.append('required_analytic_reference')
        if plan['primary'] is None:
            missing.append('primary_E_receipt')
        else:
            budget.bind(plan['primary'], root)
        maximum = 16 if plan['kind'] == 'H1' else 32
        if not plan['runs'] or len(plan['runs']) > maximum:
            missing.append('bounded_actual_E_runs')
        run_ids = {r['id'] for r in plan['runs']}
        if len(run_ids) != len(plan['runs']):
            raise ValueError('duplicate H member IDs')
        receipt_bindings = []
        for run in plan['runs']:
            if run['receipt'] is None:
                missing.append('E_receipt:' + run['id'])
            else:
                receipt_bindings.append(run['receipt'])
                budget.bind(run['receipt'], root)
            if plan['kind'] == 'H1':
                if run['h1_receipt'] is not None:
                    raise ValueError('H1 cannot recursively supply an H1 receipt')
                if not run['references']:
                    missing.append('analytic_references:' + run['id'])
                for reference in run['references']:
                    sources(reference)
            else:
                if run['references']:
                    raise ValueError('H2 uses independently recomputed H1, not inline replacement references')
                if run['h1_receipt'] is None:
                    missing.append('exact_H1_coverage:' + run['id'])
                else:
                    budget.bind(run['h1_receipt'], root)
        if len({(r['path'], r['sha256']) for r in receipt_bindings}) != len(receipt_bindings):
            raise ValueError('H members must bind distinct actual E receipts')
        if plan['primary'] and plan['primary'] not in receipt_bindings:
            missing.append('primary_in_actual_run_set')
        analysis_ids = {a['id'] for a in plan['analyses']}
        if len(analysis_ids) != len(plan['analyses']):
            raise ValueError('duplicate H analysis IDs')
        for analysis in plan['analyses']:
            if analysis['method'] not in methods:
                missing.append('unsupported_analysis:' + analysis['method'])
            if not analysis['run_ids'] or set(analysis['run_ids']) - run_ids:
                raise ValueError('analysis requires exact known run IDs')
            if plan['kind'] == 'H1' and analysis['method'] != 'step_refinement':
                raise ValueError('H1 analyses contain only conditional step_refinement')
            if analysis['structural_review']:
                sources(analysis['structural_review'])
            if analysis['campaign']:
                budget.bind(analysis['campaign'], root)
        implemented = {'analytic_reference'} if plan['kind'] == 'H1' and plan['runs'] else set()
        implemented |= {a['method'] for a in plan['analyses']}
        for requirement in plan['requirements']:
            if requirement['required'] and requirement['method'] not in implemented:
                missing.append('required_analysis:' + requirement['method'])
        if plan['kind'] == 'H1' and plan['material_results']:
            raise ValueError('H1 numerical checks do not supply H2 material decisions')
        if plan['kind'] == 'H2':
            if not plan['material_results'] or not plan['analyses']:
                missing.append('material_claim_decisions_and_analyses')
            claims = {c['id']: c for c in plan['material_results']}
            if len(claims) != len(plan['material_results']):
                raise ValueError('duplicate material result IDs')
            used = set()
            for claim in claims.values():
                sources(claim)
                if any(claim['triggers'].values()) and claim['model_comparison_requirement'] != 'required':
                    raise ValueError('material structural trigger cannot be not_applicable')
                if not claim['analysis_ids'] or set(claim['analysis_ids']) - analysis_ids:
                    raise ValueError('material claim needs known analysis IDs')
                selected = [a for a in plan['analyses'] if a['id'] in claim['analysis_ids']]
                if any(a['claim_id'] != claim['id'] for a in selected):
                    raise ValueError('analysis/material claim binding differs')
                if claim['model_comparison_requirement'] == 'required' and not any(a['method'] == 'structural_final_comparison' for a in selected):
                    missing.append('required_structural_comparison:' + claim['id'])
                used.update(claim['analysis_ids'])
            if used != analysis_ids:
                raise ValueError('every H2 analysis requires a material claim decision')
        result['plan_complete'] = not missing and not errors
        if plan['review_record'] is None:
            missing.append('source_bound_H_review')
        else:
            review = budget.read(budget.bind(plan['review_record'], root))
            if (set(review) != {'schema_version', 'project_id', 'verification_semantic_sha256', 'decision'}
                    or type(review['schema_version']) is not int or review['schema_version'] != 1
                    or review['project_id'] != plan['project_id'] or review['verification_semantic_sha256'] != semantic_digest(plan)):
                raise ValueError('H review identity/digest differs')
            decision = review['decision']
            if set(decision) != {'path', 'sha256', 'start', 'end', 'quote', 'reviewed_by', 'action'}:
                raise ValueError('H review exact decision surface differs')
            text = budget.bind({k: decision[k] for k in ('path', 'sha256')}, root).read_text(encoding='utf-8')
            if (type(decision['start']) is not int or type(decision['end']) is not int
                    or not 0 <= decision['start'] < decision['end'] <= len(text)
                    or text[decision['start']:decision['end']] != decision['quote']
                    or decision['action'] != 'review' or not isinstance(decision['reviewed_by'], str) or not decision['reviewed_by'].strip()):
                raise ValueError('H review source quote/action differs')
            lines = decision['quote'].splitlines()
            expected = {'project_id': plan['project_id'], 'verification_semantic_sha256': semantic_digest(plan),
                        'reviewed_by': decision['reviewed_by'], 'action': 'review'}
            if any([line for line in lines if line.startswith(key+'=')] != [key+'='+value] for key, value in expected.items()):
                raise ValueError('H review exact context differs')
            result['reviewed'] = plan['status'] == 'reviewed' and result['plan_complete']
        if plan['status'] == 'reviewed' and not result['reviewed']:
            errors.append('reviewed H plan requires all current source-bound gates')
        if require_reviewed and not result['reviewed']:
            errors.append('required: complete reviewed H plan')
        result['valid'] = not errors
        budget.check()
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError, RecursionError, StopIteration) as error:
        errors.append(str(error))
    result['valid'] = result['valid'] and not errors
    result['missing_gates'] = sorted(set(missing))
    return result


def main(kind=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', type=Path)
    parser.add_argument('--project-root', type=Path)
    parser.add_argument('--require-reviewed', action='store_true')
    args = parser.parse_args()
    result = validate_verification(args.path, project_root=args.project_root, kind=kind, require_reviewed=args.require_reviewed)
    emit(result)
    return 0 if result['valid'] else 1
