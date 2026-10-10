"""Read-only H2 contract, required analyses, C/D/E/H1 and source review checks."""
from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path

from runtime_common import contained_path, emit, load_contract, load_document, schema_errors, sha256_file
from validate_parameter_provenance import bind_file
from validate_simulation_protocol import validate_simulation_protocol
from model_verification_common import (KINDS, METHODS, constant_level, execution_configuration,
    metric_value, obligation_snapshot, output_port, settings_snapshot, structural_snapshot, variable_quantity)
from verification_common import (HARD_BUDGET, assert_unchanged, bind_sources, evidence_paths, finite,
    input_manifest, limited_document, checked_binding, semantic_digest, source_snapshot, typed_equal, validate_review)


def _member(binding, identity, root, result):
    path = checked_binding(root, binding, result, 'H2_H1:' + identity)
    if path is None:
        result['missing_gates'].append('accepted_H1_member:' + identity)
        return None
    from validate_numerical_verification_receipt import validate_numerical_verification_receipt
    report = validate_numerical_verification_receipt(path, project_root=root)
    result['bound_files'].extend(report.get('bound_files', []))
    if not report['valid'] or not report['numerically_verified']:
        result['errors'].extend(identity + ': H1: ' + error for error in report.get('errors', []))
        result['missing_gates'].append('current_accepted_H1_member:' + identity)
        return None
    if report['project_id'] != result['project_id']:
        result['errors'].append(identity + ': H1 project identity differs')
        return None
    protocol_path, receipt_path = Path(report['primary_protocol_path']), Path(report['primary_receipt_path'])
    protocol_report = report.get('primary_protocol_report')
    if protocol_report is None:
        protocol_report = validate_simulation_protocol(protocol_path, project_root=root, require_frozen=True)
    simulation_report = report.get('primary_simulation_report')
    if simulation_report is None:
        from validate_simulation_receipt import validate_simulation_receipt
        simulation_report = validate_simulation_receipt(receipt_path, project_root=root, protocol_report=protocol_report)
    if not protocol_report['valid'] or not protocol_report['execution_ready'] or not simulation_report['valid']:
        result['errors'].append(identity + ': current complete frozen E evidence required')
        return None
    result['bound_files'].extend(protocol_report['bound_files'])
    data = limited_document(Path(simulation_report['data_path']), result['budget'])
    if any(len(output['time']) > (result['budget'] or HARD_BUDGET)['max_samples_per_output'] for output in data['outputs']):
        result['errors'].append(identity + ': actual output sample budget exceeded')
        return None
    return {'id': identity, 'numerical_path': str(path), 'numerical_report': report,
            'protocol_report': protocol_report, 'simulation_report': simulation_report,
            'protocol': limited_document(protocol_path, result['budget']), 'data': data}


def _bounds(bounds, unit, label, result):
    if bounds is None:
        result['missing_gates'].append(label + ':prior_bounds')
        return
    if bounds['unit'] != unit:
        result['errors'].append(label + ': criterion unit differs')
    if all(bounds[key] is None for key in ('lower', 'upper')):
        result['missing_gates'].append(label + ':at_least_one_finite_bound')
    elif any(bounds[key] is not None and not finite(bounds[key]) for key in ('lower', 'upper')):
        result['errors'].append(label + ': finite typed bounds required')
    elif bounds['lower'] is not None and bounds['upper'] is not None and bounds['lower'] > bounds['upper']:
        result['errors'].append(label + ': lower bound exceeds upper')


def _analysis(analysis, claim, members, sources, root, result):
    kind, requirement = analysis['kind'], analysis['requirement']
    label = claim['id'] + ':' + kind
    omit = 'not_applicable' if kind == 'model_comparison' else 'not_required'
    if requirement not in ('required', omit):
        result['errors'].append(label + ': illegal omission decision for analysis kind')
    if requirement != 'required':
        if (analysis['method'] is not None or analysis['member_ids'] or
                any(analysis[key] is not None for key in ('metric', 'factor', 'bounds', 'comparison', 'structural_review'))):
            result['errors'].append(label + ': omitted analysis must not carry fabricated execution evidence')
        return
    result['required_analysis_kinds'].append(kind)
    if analysis['method'] is None:
        result['missing_gates'].append(label + ':implemented_method')
        return
    if analysis['method'] != METHODS[kind]:
        result['errors'].append(label + ': method and kind differ')
    ids = analysis['member_ids']
    if 'primary' not in ids or len(ids) < (1 if kind == 'robustness' else 2):
        result['missing_gates'].append(label + ':primary_and_complete_finite_domain')
    if set(ids) - set(members):
        result['missing_gates'].append(label + ':current_accepted_member_evidence')
        return
    if analysis['metric'] is None:
        result['missing_gates'].append(label + ':common_metric_output_mapping')
        return
    metric = analysis['metric']
    if (type(metric['primary_output_port']) is not int or
            any(type(item['output_port']) is not int for item in metric['member_output_ports']) or
            analysis['factor'] is not None and type(analysis['factor']['input_port']) is not int):
        result['errors'].append(label + ': port identities must be actual integers, not equivalent floats')
        return
    mapped = [item['member_id'] for item in metric['member_output_ports']]
    if len(set(mapped)) != len(mapped) or set(mapped) != set(ids) - {'primary'}:
        result['errors'].append(label + ': explicit member output mappings must exactly cover domain')
        return
    primary = members.get('primary')
    if primary is None:
        result['missing_gates'].append(label + ':accepted_primary_H1')
        return
    quantities = []
    for identity in ids:
        member = members[identity]
        try:
            metric_value(member, analysis, identity)
            port = output_port(analysis, identity)
            output = next(item for item in member['protocol_report']['run_spec']['outputs'] if item['port'] == port)
            quantities.append(variable_quantity(member, output['variable_id']))
            if kind != 'model_comparison' and (port != metric['primary_output_port'] or
                    output['variable_id'] != next(item for item in primary['protocol_report']['run_spec']['outputs']
                                                if item['port'] == metric['primary_output_port'])['variable_id']):
                result['errors'].append(label + ': same-model observable identity differs')
        except (ValueError, KeyError, StopIteration) as error:
            result['errors'].append(label + ':' + identity + ': ' + str(error))
    if quantities and any(item != quantities[0] for item in quantities):
        result['errors'].append(label + ': common physical observable quantity differs')
    if kind == 'sensitivity':
        if analysis['factor'] is None:
            result['missing_gates'].append(label + ':source_bound_external_factor')
            return
        if analysis['comparison'] is not None or analysis['structural_review'] is not None:
            result['errors'].append(label + ': unrelated comparator settings supplied')
        factor, levels = analysis['factor'], []
        for identity in ids:
            try:
                levels.append(constant_level(members[identity], factor))
            except ValueError as error:
                result['errors'].append(label + ':' + identity + ': ' + str(error))
        if (len(set(levels)) != len(levels) or not typed_equal(levels, factor['levels'])):
            result['errors'].append(label + ': finite distinct source levels and member order differ')
        reference = execution_configuration(primary, input_mode='factor', factor_port=factor['input_port'])
        for identity in ids:
            if not typed_equal(reference, execution_configuration(members[identity], input_mode='factor', factor_port=factor['input_port'])):
                result['errors'].append(label + ': beyond single constant external-input OAT')
        _bounds(analysis['bounds'], metric['unit'] + '/' + factor['unit'], label, result)
    elif kind == 'robustness':
        if any(analysis[key] is not None for key in ('factor', 'comparison', 'structural_review')):
            result['errors'].append(label + ': unrelated factor/comparator settings supplied')
        reference = execution_configuration(primary, input_mode='scenarios')
        for identity in ids:
            if not typed_equal(reference, execution_configuration(members[identity], input_mode='scenarios')):
                result['errors'].append(label + ': finite scenarios change approved model/parameters/conditions or numerical configuration')
        _bounds(analysis['bounds'], metric['unit'], label, result)
    else:
        if analysis['factor'] is not None or analysis['bounds'] is not None:
            result['errors'].append(label + ': unrelated factor/bounds supplied')
        comparison = analysis['comparison']
        if comparison is None:
            result['missing_gates'].append(label + ':prior_comparison_tolerance')
        elif (not finite(comparison['absolute_tolerance']) or comparison['absolute_tolerance'] <= 0 or
              not finite(comparison['relative_tolerance']) or comparison['relative_tolerance'] < 0):
            result['errors'].append(label + ': finite applicable comparison tolerances required')
        if kind == 'solver_comparison':
            if analysis['structural_review'] is not None:
                result['errors'].append(label + ': solver choice is not a structural comparator')
            reference = execution_configuration(primary, solver=False)
            names = set()
            for identity in ids:
                member = members[identity]
                names.add(member['protocol_report']['run_spec']['solver']['name'])
                if not typed_equal(reference, execution_configuration(member, solver=False)):
                    result['errors'].append(label + ': solver comparison changes nonnumerical settings')
            if names != {'ode4', 'ode45'}:
                result['errors'].append(label + ': first comparison requires actual ode4 and ode45 H1 members')
        else:
            reviews = analysis['structural_review']
            if reviews is None:
                result['missing_gates'].append(label + ':material_structure_review')
                return
            review_ids = [item['member_id'] for item in reviews]
            if len(set(review_ids)) != len(review_ids) or set(review_ids) != set(ids) - {'primary'}:
                result['errors'].append(label + ': structure reviews must exactly cover comparators')
                return
            base = primary['protocol_report']
            base_spec = base['run_spec']
            def common_inputs(member):
                return [{key: item[key] for key in ('port', 'unit', 'time', 'values', 'interpolation')}
                        | {'quantity': variable_quantity(member, item['variable_id'])}
                        for item in member['protocol_report']['run_spec']['inputs']]
            for review in reviews:
                identity = review['member_id']
                member, report = members[identity], members[identity]['protocol_report']
                spec = report['run_spec']
                if any(report[key] != base[key] for key in ('project_id', 'problem_path', 'problem_sha256')):
                    result['errors'].append(label + ': structural comparator differs from the common frozen Problem')
                if report['model_identity'] == base['model_identity']:
                    result['errors'].append(label + ': same registered structure is not a structural comparator')
                if any(not typed_equal(spec[key], base_spec[key]) for key in ('start_time', 'stop_time', 'solver', 'seed', 'warning_policy')):
                    result['errors'].append(label + ': structural comparison common scenario/numerical settings differ')
                if not typed_equal(common_inputs(primary), common_inputs(member)):
                    result['errors'].append(label + ': structural comparator common input waveform/unit/quantity differs')
                try:
                    expected = structural_snapshot(review, primary, member)
                    source_snapshot(review['source_ref'], sources, root, result, expected, label=label + ':structure:' + identity)
                except (ValueError, KeyError, IndexError, TypeError) as error:
                    result['errors'].append(label + ': ' + str(error))


def validate_model_verification(path, *, project_root=None, require_reviewed=False):
    result = {'valid': False, 'schema_valid': False, 'reviewed': False, 'assessment_ready': False,
              'environment_checked': False, 'execution_allowed': False, 'contract_path': None,
              'contract_sha256': None, 'project_id': None, 'semantic_sha256': None, 'bound_files': [],
              'primary_numerical_receipt_path': None, 'primary_protocol_path': None, 'primary_receipt_path': None,
              'model_identity': None, 'required_analysis_kinds': [], 'members': [], 'budget': None,
              'errors': [], 'missing_gates': [], 'changed_sources': []}
    try:
        path = Path(path).resolve()
        root = Path(project_root).resolve() if project_root is not None else path.parent
        path = contained_path(root, str(path))
        value = limited_document(path)
        result.update(contract_path=str(path), contract_sha256=sha256_file(path), project_root=str(root))
        schema = load_contract('core/model_verification_contract.yaml')
        result['errors'].extend(schema_errors(value, schema))
        if type(value.get('schema_version')) is not int:
            result['errors'].append('schema_version must be integer 1')
        if result['errors']:
            return result
        result.update(schema_valid=True, project_id=value['project_id'], semantic_sha256=semantic_digest(value), budget=value['budget'])
        budget = value['budget'] or HARD_BUDGET
        if any(type(count) is not int for count in budget.values()):
            result['errors'].append('read budgets require exact integer counts')
            return result
        initial = [path] + [contained_path(root, entry['path']) for entry in value['sources']]
        initial += [contained_path(root, item['numerical_receipt']['path']) for item in value['members'] if item['numerical_receipt']]
        if value['primary_numerical_receipt']:
            initial.append(contained_path(root, value['primary_numerical_receipt']['path']))
        if value['review_record']:
            initial.append(contained_path(root, value['review_record']['path']))
        paths = evidence_paths(initial, root, budget)
        manifest = input_manifest(paths, root, budget)
        result['allowed_external'] = sorted(str(item) for item in paths.allowed_external)
        result['bound_files'].append({'label': 'model_verification', 'path': str(path), 'sha256': result['contract_sha256']})
        if budget['max_total_bytes'] < budget['max_file_bytes']:
            result['errors'].append('total read budget is smaller than per-file budget')
        if value['budget'] is None:
            result['missing_gates'].append('reviewed_input_budget')
        sources = bind_sources(value['sources'], root, result)
        source_snapshot(value['settings_source_ref'], sources, root, result, settings_snapshot(value), label='H2_complete_settings')
        members = {}
        primary = _member(value['primary_numerical_receipt'], 'primary', root, result)
        if primary:
            members['primary'] = primary
            p = primary['protocol_report']
            result.update(primary_numerical_receipt_path=primary['numerical_path'],
                          primary_protocol_path=p['contract_path'], primary_receipt_path=primary['simulation_report']['receipt_path'],
                          model_identity=p['model_identity'])
            for key in ('model_path', 'model_sha256', 'mapping_path', 'mapping_sha256', 'problem_path', 'problem_sha256', 'approval_path', 'approval_sha256'):
                result[key] = p[key]
        seen = {'primary'}
        for member in value['members']:
            identity = member['id']
            if identity in seen:
                result['errors'].append('duplicate/reserved member id: ' + identity)
                continue
            seen.add(identity)
            entry = _member(member['numerical_receipt'], identity, root, result)
            if entry:
                members[identity] = entry
        claims_seen = set()
        if not value['claims']:
            result['missing_gates'].append('material_claim_decisions')
        used_members = {'primary'}
        problem = limited_document(Path(primary['protocol_report']['problem_path']), budget) if primary else None
        requirement_ids = {entry['id'] for entry in problem['requirements']} if problem else set()
        for claim in value['claims']:
            if claim['id'] in claims_seen:
                result['errors'].append('duplicate claim id')
            claims_seen.add(claim['id'])
            if problem and set(claim['requirement_ids']) - requirement_ids:
                result['errors'].append(claim['id'] + ': unknown frozen Problem requirement')
            kinds = [item['kind'] for item in claim['analyses']]
            if len(set(kinds)) != len(kinds) or set(kinds) != set(KINDS):
                result['errors'].append(claim['id'] + ': every analysis kind needs exactly one source-bound decision')
            source_snapshot(claim['obligation_source_ref'], sources, root, result, obligation_snapshot(claim), label=claim['id'] + ':task_obligations')
            for analysis in claim['analyses']:
                used_members.update(analysis['member_ids'])
                try:
                    _analysis(analysis, claim, members, sources, root, result)
                except (ValueError, KeyError, TypeError, IndexError, StopIteration) as error:
                    result['errors'].append(claim['id'] + ':' + analysis['kind'] + ': ' + str(error))
        if set(seen) - used_members:
            result['errors'].append('registered H1 member is outside every declared finite analysis domain')
        result['reviewed'] = validate_review(value, root, result, schema, label='model_verification')
        result['required_analysis_kinds'] = sorted(set(result['required_analysis_kinds']))
        result['members'] = [{'id': identity, 'numerical_receipt_path': member['numerical_path'],
                              'primary_protocol_path': member['protocol_report']['contract_path'],
                              'primary_receipt_path': member['simulation_report']['receipt_path'],
                              'model_identity': member['protocol_report']['model_identity']} for identity, member in members.items()]
        result['numerical_scopes'] = [
            {'member_id': identity, 'method': limited_document(member['numerical_report']['contract_path'], budget)['method'],
             'claim_limit': member['numerical_report']['claim_limit'],
             'outputs': [{key: output[key] for key in ('port', 'variable_id', 'unit', 'sample_count')}
                         for output in member['numerical_report']['outputs']]}
            for identity, member in members.items()]
        result['_members'] = members
        result['input_manifest'] = manifest
        assert_unchanged(manifest)
        result['assessment_ready'] = result['reviewed'] and not result['errors'] and not result['missing_gates']
        result['valid'] = not result['errors'] and (not require_reviewed or result['assessment_ready'])
    except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError, OverflowError) as error:
        result['errors'].append(str(error))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', type=Path)
    parser.add_argument('--project-root', type=Path)
    parser.add_argument('--require-reviewed', action='store_true')
    args = parser.parse_args()
    result = validate_model_verification(args.path, project_root=args.project_root, require_reviewed=args.require_reviewed)
    emit({key: value for key, value in result.items() if key != '_members'})
    return 0 if result['valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
