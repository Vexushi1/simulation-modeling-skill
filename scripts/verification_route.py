"""Finite H inspection and historical recomputation, without native permission."""
from pathlib import Path

from runtime_common import contained_path, load_document
from validate_verification import validate_verification
from validate_verification_receipt import validate_verification_receipt
from verification_state import primary_errors

METHODS = {'sensitivity_analysis': 'scenario_response', 'robustness_analysis': 'finite_domain_robustness',
           'model_comparison': 'structural_final_comparison', 'solver_comparison': 'solver_final_comparison'}


def verification_route(result, *, resources, state_result, state_path, plan_path, receipt_path, requested):
    intent = result['intent']
    kind = 'H1' if intent == 'numerical_verification' else 'H2'
    anchor = 'numerical_verification' if kind == 'H1' else 'model_verification'
    root = Path(state_result['project_root']) if state_result else None
    result.update(execution_scope='historical_verification', activated_modules=[intent],
                  activated_resources=list(resources), activated_packs=['packs/evidence/convergence.md'] if kind == 'H1'
                  else ['packs/evidence/' + {'sensitivity_analysis': 'sensitivity', 'robustness_analysis': 'sensitivity',
                      'model_comparison': 'model_comparison', 'solver_comparison': 'solver_comparison'}.get(intent, 'model_comparison') + '.md'])
    if requested:
        result.update(status='blocked', missing_gates=['H_read_only_operations_empty'],
                      errors=['H routes cannot select native operations'])
        return result
    bound = state_result.get(anchor + '_path') if state_result else None
    if bound and receipt_path is not None and Path(receipt_path).resolve() != Path(bound):
        result.update(status='blocked', missing_gates=['H_state_binding_matches'], errors=['H receipt differs from state binding'])
        return result
    receipt_path = receipt_path or bound
    if receipt_path is not None:
        receipt_path = Path(receipt_path).resolve()
        report = validate_verification_receipt(receipt_path, project_root=root, kind=kind)
        result['verification_validation'] = report
        invalid = list(report['errors']) if not report['valid'] else []
        if not report.get('evidence_complete'):
            invalid.append('complete recomputed H evidence required')
        if state_result:
            state = load_document(Path(state_path))
            invalid.extend(primary_errors(report, state, root, state_result))
        if plan_path is not None and (Path(plan_path).resolve() != Path(report.get('plan_path') or '') or
                                     load_document(plan_path).get('kind') != kind):
            invalid.append('requested H plan differs from receipt binding')
        if invalid:
            result.update(status='blocked', missing_gates=['H_evidence_current'], errors=invalid)
            return result
        plan_path = Path(report['plan_path'])
    if plan_path is None:
        result.update(status='inspected', missing_gates=['H_plan_supplied'],
                      next_step='Prepare a source-bound H draft; numerical or model claims need recomputed evidence.')
        return result
    if root is not None:
        plan_path = contained_path(root, str(Path(plan_path).resolve()))
    report = validate_verification(plan_path, project_root=root, kind=kind)
    result['verification_plan_validation'] = report
    if not report['valid']:
        result.update(status='blocked', missing_gates=report['missing_gates'], errors=report['errors'])
        return result
    plan = load_document(Path(plan_path))
    if intent in METHODS and not any(a['method'] == METHODS[intent] for a in plan['analyses']):
        result.update(status='blocked', missing_gates=['requested_H_method_declared'],
                      errors=['H plan does not declare the requested finite method'])
        return result
    result.update(status='inspected', missing_gates=report['missing_gates'],
                  next_step='Review the fixed source-bound plan, then analyze existing independent E/G history in a fresh directory; state updates are explicit caller actions.')
    return result
