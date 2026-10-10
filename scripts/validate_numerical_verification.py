"""Read a source-reviewed H1 plan; do not run MATLAB or accept numeric evidence."""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

from runtime_common import emit, load_contract, schema_errors, sha256_file
from validate_parameter_provenance import bind_file
from validate_simulation_protocol import validate_simulation_protocol
from verification_common import (HARD_BUDGET, assert_unchanged, bind_sources, checked_binding, evidence_paths, finite, input_manifest,
                                 limited_document, semantic_digest, source_snapshot, typed_equal, validate_review)

SETTINGS_FIELDS = ('method', 'comparison_times', 'outputs', 'obligations', 'budget', 'claim_limit')
EXTENDED_SETTINGS_FIELDS = ('scope', 'trajectory', 'observables', 'checks', 'math_budget', 'continuous_scope')


def settings_snapshot(value):
    return {k: value[k] for k in (*SETTINGS_FIELDS, *EXTENDED_SETTINGS_FIELDS) if k in value}


def time_tolerance(time):
    return 64 * sys.float_info.epsilon * max(1, abs(time))


def uniform_grid(start, stop, step, *, max_steps=3000):
    span = stop - start
    ratio = span / step
    if type(max_steps) is not int or not 1 <= max_steps <= 12000 or not finite(ratio) or ratio <= 0 or ratio > max_steps:
        raise ValueError(f'fixed refinement must fit 1–{max_steps} complete bounded native steps per level')
    count = round(ratio)
    if count < 1 or abs(ratio - count) > 64 * sys.float_info.epsilon * max(1, abs(ratio)):
        raise ValueError('fixed refinement span must contain an integer number of steps')
    grid = [start + index * step for index in range(count + 1)]
    grid[-1] = stop
    if any(a >= b for a, b in zip(grid, grid[1:])):
        raise ValueError('fixed refinement time grid is not representable without duplicates')
    return grid


def comparable_configuration(value, report, method):
    spec = report['run_spec']
    solver = dict(spec['solver'])
    for key in ('fixed_step',) if method == 'ode4_step_refinement' else ('rel_tol', 'abs_tol'):
        solver.pop(key)
    return {'run_spec': {**spec, 'solver': solver}, 'conditions': value['conditions'],
            'logging': value['logging'], 'selection': value['selection'],
            'mapping_path': report['mapping_path'], 'mapping_sha256': report['mapping_sha256'],
            'model_identity': report['model_identity']}


def validate_numerical_verification(path, *, project_root=None, require_reviewed=False):
    path = Path(path).resolve()
    root = Path(project_root or path.parent).resolve()
    result = {'valid': False, 'schema_valid': False, 'reviewed': False, 'assessment_ready': False,
              'environment_checked': False, 'execution_allowed': False, 'contract_path': str(path),
              'contract_sha256': None, 'project_id': None, 'semantic_sha256': None, 'bound_files': [],
              'changed_sources': [], 'errors': [], 'missing_gates': [], 'protocol_reports': [],
              'primary_protocol_path': None, 'model_identity': None, 'budget': None}
    errors, missing, bound = (result[k] for k in ('errors', 'missing_gates', 'bound_files'))
    try:
        if not path.is_relative_to(root):
            raise ValueError('numerical verification contract leaves project root')
        bootstrap = input_manifest([path], root, HARD_BUDGET)
        value = limited_document(path)
        schema = load_contract('core/numerical_verification_contract.yaml')
        issues = schema_errors(value, schema)
        errors.extend(issues)
        if issues:
            return result
        if type(value['schema_version']) is not int:
            raise ValueError('schema_version must be an integer, not bool')
        budget = value['budget'] or HARD_BUDGET
        if any(type(v) is not int for v in budget.values()):
            raise ValueError('read budgets require integer counts, not bool or float')
        initial_paths = evidence_paths([path], root, budget, root_contexts={path: 'h1_contract'})
        initial_manifest = input_manifest(initial_paths, root, budget)
        result.update(schema_valid=True, contract_sha256=sha256_file(path), project_id=value['project_id'],
                      semantic_sha256=semantic_digest(value), method=value['method'], budget=value['budget'],
                      claim_limit=value['claim_limit'], outputs=value['outputs'], comparison_times=value['comparison_times'],
                      allowed_external=sorted(map(str, initial_paths.allowed_external)), input_manifest=initial_manifest)
        if value['budget'] is None:
            missing.append('source_declared_read_budget')
        if budget['max_total_bytes'] < budget['max_file_bytes']:
            errors.append('total read budget is smaller than per-file budget')
        bound.append({'label': 'numerical_verification', 'path': str(path), 'sha256': result['contract_sha256']})
        sources = bind_sources(value['sources'], root, result)
        source_snapshot(value['settings_source_ref'], sources, root, result,
                        settings_snapshot(value), label='numerical_settings')
        result['numeric_policy'] = settings_snapshot(value)
        if value['method'] is None:
            missing.append('explicit_three_level_method')
        if value['obligations'] is None:
            missing.append('reviewed_numerical_check_obligations')
        else:
            for name, obligation in value['obligations'].items():
                if not set(obligation['source_ids']) <= set(sources):
                    errors.append(name + ': unknown obligation source')
                if obligation['status'] == 'deferred' or obligation['status'] == 'required' and not any(c['kind'] == name for c in value.get('checks', [])):
                    missing.append('unsupported_required_check:' + name)
        for check in value.get('checks', []):
            if not set(check['source_ids']) <= set(sources):
                errors.append('numerical check references an unknown source')
        continuous = value.get('continuous_scope')
        if continuous and (not set(continuous['source_ids']) <= set(sources) or not set((continuous.get('envelope') or {}).get('proof_source_ids', [])) <= set(sources)):
            errors.append('continuous envelope references an unknown proof/scope source')
        if continuous and continuous['target'] == 'underlying_continuous' and continuous.get('envelope') is None:
            missing.append('independently_reviewed_continuous_envelope')
        paths = []
        for index, binding in enumerate([value['primary_protocol'], *value['refinement_protocols']]):
            protocol = checked_binding(root, binding, result, 'refinement_protocol:' + str(index), budget)
            if protocol is None:
                missing.append('current_frozen_protocol:' + str(index))
                continue
            # Budget preflight precedes the transitive E consumer.
            input_manifest(evidence_paths([protocol], root, budget, root_contexts={protocol: 'simulation_protocol'}), root, budget)
            report = validate_simulation_protocol(protocol, project_root=root, require_frozen=True)
            result['protocol_reports'].append(report)
            paths.append(protocol)
            if not report['valid'] or not report['execution_ready']:
                errors.extend('E protocol: ' + e for e in report['errors'])
                missing.extend('E protocol: ' + e for e in report['missing_gates'])
            bound.extend(report['bound_files'])
            if report['project_id'] != value['project_id']:
                errors.append('refinement protocol project differs')
        if len(value['refinement_protocols']) != 2 or len(result['protocol_reports']) != 3:
            missing.append('three_independent_frozen_protocols')
        if len(paths) != len(set(paths)):
            errors.append('three independently frozen distinct protocols required')
        reports = result['protocol_reports']
        if reports and reports[0].get('run_spec'):
            primary = reports[0]
            result.update(primary_protocol_path=primary['contract_path'], primary_protocol_sha256=primary['contract_sha256'],
                          primary_protocol_report=primary, model_identity=primary['model_identity'])
            for name in ('problem', 'model', 'approval', 'mapping'):
                for suffix in ('path', 'sha256'):
                    result[name + '_' + suffix] = primary.get(name + '_' + suffix)
        if len(reports) == 3 and all(r.get('run_spec') for r in reports) and value['method'] is not None:
            configurations = [comparable_configuration(limited_document(p, budget), r, value['method']) for p, r in zip(paths, reports)]
            if any(not typed_equal(c, configurations[0]) for c in configurations[1:]):
                errors.append('refinement changed approved model, physical conditions or non-refined execution settings')
            specs = [r['run_spec'] for r in reports]
            primary = specs[0]
            if not any(k in value for k in EXTENDED_SETTINGS_FIELDS) and (primary['stop_time']-primary['start_time'] > 30 or len(primary['outputs']) > 2):
                errors.append('legacy bounded H1 requires span <= 30 seconds and <= 2 outputs; review an extended policy for new analyses')
            from numerical_obligations import numeric_context_from_documents, validate_numeric_policy
            protocol_value = limited_document(paths[0], budget)
            context = numeric_context_from_documents(limited_document(reports[0]['model_path'], budget),
                protocol_value['selection'], limited_document(reports[0]['parameters_path'], budget))
            result['numeric_context'] = context
            try:
                validated = validate_numeric_policy(result['numeric_policy'], specs, context)
                result['scope'] = validated['scope']
                if any(o.get('kind') == 'state' for o in value['outputs']):
                    missing.append('native_state_capture_not_present_in_E_receipt; use the independently qualified H trial state interface')
                if value['method'] == 'ode4_step_refinement':
                    limit = budget['max_samples_per_output']-1 if any(k in value for k in EXTENDED_SETTINGS_FIELDS) else 3000
                    grids = [uniform_grid(s['start_time'], s['stop_time'], s['solver']['fixed_step'], max_steps=limit) for s in specs]
                    if any(len(g) > budget['max_samples_per_output'] for g in grids):
                        errors.append('declared native sample budget cannot cover all fixed refinement grids')
            except (ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
                message = str(error)
                if message.startswith('unsupported_required_check:'):
                    if message not in missing:
                        missing.append(message)
                else:
                    errors.append(message)
        elif not value['outputs']:
            missing.append('declared_output_refinement_criteria')
        review_ok = validate_review(value, root, result, schema, label='numerical_verification')
        result['reviewed'] = value['status'] == 'reviewed' and review_ok and not errors and not missing
        result['assessment_ready'] = result['reviewed']
        if require_reviewed and not result['reviewed']:
            errors.append('current complete reviewed numerical verification contract required')
        if value['status'] == 'reviewed' and missing:
            errors.append('reviewed numerical contract lacks necessary gates')
        input_manifest([b['path'] for b in bound], root, budget, allowed_external=result['allowed_external'])
        assert_unchanged(initial_manifest)
        assert_unchanged(bootstrap)
        result['valid'] = not errors
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        errors.append(str(error))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', type=Path)
    parser.add_argument('--project-root', type=Path)
    parser.add_argument('--require-reviewed', action='store_true')
    args = parser.parse_args()
    result = validate_numerical_verification(args.path, project_root=args.project_root, require_reviewed=args.require_reviewed)
    emit(result)
    return 0 if result['valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
