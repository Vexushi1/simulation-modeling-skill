"""Real G source/review/catalog checks with SYNTHETIC D/E upstream reports only."""
import copy
import itertools
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import validate_experiment_design as validator
from probe_environment import write_json
from runtime_common import ROOT, canonical_digest, load_document, sha256_file


def binding(path):
    return {'path': str(Path(path).resolve()), 'sha256': sha256_file(path)}


class SyntheticCatalog:
    """Only upstream native reports are stubbed; G reads all real fixture bytes."""

    def __init__(self, root, monkeypatch, *, method='scenario_matrix', factors=1, extra_inputs=0):
        self.root, self.path = root, root / 'experiment.json'
        self.settings_path = root / 'settings-source.json'
        self.levels_path = root / 'levels-source.json'
        self.probabilities_path = root / 'probabilities-source.json'
        self.review_path, self.decision_path = root / 'review.json', root / 'decision.txt'
        self.upstream = {}
        for name in ('mapping', 'model', 'approval', 'problem', 'implementation'):
            path = root / (name + '.json')
            write_json(path, {'scope': 'SYNTHETIC INFRASTRUCTURE TEST', 'role': name})
            self.upstream[name] = path
        self.mapping_ready, self.e_ready = True, True
        declarations = []
        level_source = {'factors': {}}
        for index in range(factors):
            identity, variable = 'factor-' + str(index + 1), 'u' + str(index + 1)
            levels = [0.0, 1.0] if index == 0 else [10.0, 20.0]
            item = {'id': identity, 'input_port': index + 1, 'variable_id': variable, 'unit': '1',
                    'levels': levels, 'source_ref': {'source_id': 'levels', 'selector': ['factors', variable]}}
            declarations.append(item)
            level_source['factors'][variable] = {key: item[key] for key in ('variable_id', 'unit', 'levels')}
        write_json(self.levels_path, level_source)
        selection = {'design_id': 'design', 'model_id': 'model', 'target_id': 'core'}
        catalog = []
        combinations = itertools.product(*(factor['levels'] for factor in declarations))
        metric = {'id': 'response', 'output_port': 1, 'statistic': 'final', 'unit': '1',
                  'lower': -100.0, 'upper': 100.0, 'reason': 'Synthetic technical admissibility; separate from MC event.'}
        for index, values in enumerate(combinations, 1):
            inputs = [{'port': port, 'block_path': 'synthetic_model/input-' + str(port),
                       'variable_id': factor['variable_id'], 'unit': factor['unit'], 'time': [0.0, 1.0],
                       'values': [value, value], 'interpolation': 'zoh'}
                      for port, (factor, value) in enumerate(zip(declarations, values), 1)]
            for offset in range(extra_inputs):
                port = factors + offset + 1
                inputs.append({'port': port, 'block_path': 'synthetic_model/input-' + str(port),
                               'variable_id': 'fixed-' + str(port), 'unit': '1', 'time': [0.0, 1.0],
                               'values': [9.0, 9.0], 'interpolation': 'zoh'})
            spec = {'schema_version': 1, 'model_name': 'synthetic_model',
                    'model_path': str(root / 'synthetic_model.slx'), 'model_sha256': 'a' * 64,
                    'parameters': [{'code_name': 'approved_gain', 'value': 2.0, 'unit': '1'}],
                    'inputs': inputs, 'outputs': [{'port': 1, 'block_path': 'synthetic_model/output',
                        'variable_id': 'y', 'unit': '1', 'sample_time': 0}],
                    'solver': {'name': 'ode4', 'type': 'fixed-step', 'fixed_step': 0.01,
                        'max_step': None, 'min_step': None, 'initial_step': None, 'rel_tol': None,
                        'abs_tol': None, 'zero_crossing': 'EnableAll'},
                    'start_time': 0.0, 'stop_time': 1.0, 'seed': 17, 'metrics': [copy.deepcopy(metric)],
                    'runtime_class': 'normal_serial', 'warning_policy': 'record'}
            path = root / ('protocol-' + str(index) + '.json')
            write_json(path, {'scope': 'SYNTHETIC D/E REPORT STUB; not an actual approved model',
                'selection': selection, 'conditions': {'initial_conditions': {'value': 0.0},
                    'boundary_conditions': {'value': 'declared external input'}},
                'logging': {'format': 'Dataset', 'sample_time': 0}, 'spec': spec})
            catalog.append({'id': 'member-' + str(index), 'protocol': binding(path),
                            'factor_values': [{'factor_id': factor['id'], 'value': value}
                                              for factor, value in zip(declarations, values)]})
        probability = None
        if method == 'monte_carlo_catalog':
            values = [1.0 / len(catalog)] * len(catalog)
            probability = {'values': values, 'role': 'design_law',
                'reason': 'Synthetic catalog sampling law; not a real-world prevalence.',
                'source_ref': {'source_id': 'probabilities', 'selector': ['law']}}
            write_json(self.probabilities_path, {'law': {'catalog_ids': [member['id'] for member in catalog],
                **{key: probability[key] for key in ('values', 'role', 'reason')}}})
        self.design = {'schema_version': 1, 'project_id': 'synthetic-G', 'status': 'draft',
            'mapping': binding(self.upstream['mapping']), 'selection': selection, 'method': method,
            'catalog': catalog, 'factors': declarations, 'probabilities': probability,
            'sample_count': 4 if probability else len(catalog),
            'seed': {'algorithm': 'mt19937ar', 'value': 1729} if probability else None,
            'metric_id': 'response', 'event': {'comparator': 'gt', 'threshold': 0.5, 'unit': '1',
                'confidence': 0.95, 'interval': 'wilson_95'} if probability else None,
            'budget': {'max_cases': 16, 'total_timeout': 300, 'member_process_timeout': 90,
                'member_simulation_timeout': 30, 'max_artifact_bytes': 10000000},
            'sources': [{'id': 'levels', **binding(self.levels_path), 'role': 'input_levels'}],
            'settings_source_ref': {'source_id': 'settings', 'selector': ['snapshot']},
            'required_A_operations': ['matlab.basic_execution', 'simulink.library_load'],
            'claim_limit': 'SYNTHETIC INFRASTRUCTURE TEST; finite catalog only; no numerical verification or validation.',
            'review_record': None}
        if probability:
            self.design['sources'].append({'id': 'probabilities', **binding(self.probabilities_path), 'role': 'probabilities'})
        self.sync_settings()

        def mapping_report(*args, **kwargs):
            return {'valid': True, 'project_id': self.design['project_id'],
                    'implementation_ready': self.mapping_ready, 'errors': [], 'changed_sources': [],
                    'bound_files': [binding(path) for path in self.upstream.values()]}

        def protocol_report(path, **kwargs):
            document = load_document(path)
            spec = document['spec']
            report = {'valid': True, 'execution_ready': self.e_ready, 'frozen': self.e_ready,
                'errors': [], 'changed_sources': [], 'project_id': self.design['project_id'],
                'mapping_path': str(self.upstream['mapping']),
                'mapping_sha256': sha256_file(self.upstream['mapping']),
                'contract_path': str(Path(path).resolve()), 'contract_sha256': sha256_file(path),
                'semantic_sha256': canonical_digest(document), 'run_spec_sha256': canonical_digest(spec),
                'run_spec': spec, 'bound_files': [binding(path)], 'model_identity': {'structural_sha256': 'b' * 64},
                'required_A_operations': document.get('required_A_operations', self.design['required_A_operations'])}
            report.update(document['selection'])
            for name in ('model', 'approval', 'problem'):
                report[name + '_path'] = str(self.upstream[name])
                report[name + '_sha256'] = sha256_file(self.upstream[name])
            return report

        monkeypatch.setattr(validator, 'validate_domain_mapping', mapping_report)
        monkeypatch.setattr(validator, 'validate_simulation_protocol', protocol_report)
        self.review()

    def sync_settings(self):
        fields = ('method', 'sample_count', 'seed', 'metric_id', 'event', 'budget', 'required_A_operations', 'claim_limit')
        write_json(self.settings_path, {'snapshot': {key: self.design[key] for key in fields}})
        entry = {'id': 'settings', **binding(self.settings_path), 'role': 'settings'}
        self.design['sources'] = [source for source in self.design['sources'] if source['id'] != 'settings'] + [entry]

    def review(self):
        self.design['status'] = 'reviewed'
        digest = validator.semantic_digest(self.design)
        prefix = '开发基础设施测试，不是真实用户模型批准。\n'
        quote = ('SYNTHETIC INFRASTRUCTURE TEST\nproject_id=' + self.design['project_id']
            + '\nexperiment_semantic_sha256=' + digest + '\nreviewed_by=synthetic-reviewer\naction=review\n')
        self.decision_path.write_text(prefix + quote, encoding='utf-8')
        write_json(self.review_path, {'schema_version': 1, 'project_id': self.design['project_id'],
            'experiment_semantic_sha256': digest, 'decision': {**binding(self.decision_path),
                'start': len(prefix), 'end': len(prefix) + len(quote), 'quote': quote,
                'reviewed_by': 'synthetic-reviewer', 'action': 'review'}})
        self.design['review_record'] = binding(self.review_path)
        write_json(self.path, self.design)

    def modify_protocol(self, index, change):
        member = self.design['catalog'][index]
        path = Path(member['protocol']['path'])
        document = load_document(path)
        change(document)
        write_json(path, document)
        member['protocol'] = binding(path)

    def check(self, **kwargs):
        return validator.validate_experiment_design(self.path, project_root=self.root, **kwargs)


@pytest.mark.parametrize('method,factors', [('scenario_matrix', 1), ('full_factorial', 2), ('monte_carlo_catalog', 1)])
def test_real_source_review_and_catalog_valid_without_runtime_permission(tmp_path, monkeypatch, method, factors):
    catalog = SyntheticCatalog(tmp_path, monkeypatch, method=method, factors=factors)
    before = {path: path.read_bytes() for path in tmp_path.rglob('*') if path.is_file()}
    report = catalog.check(require_reviewed=True)
    assert report['valid'] and report['design_ready'] and report['reviewed'], report['errors']
    assert report['campaign_execution_ready'] and not report['environment_checked'] and not report['execution_allowed']
    assert report['sampling_spec']['catalog_ids'] == [member['id'] for member in catalog.design['catalog']]
    assert {item['path'] for item in report['bound_files']} >= {str(catalog.levels_path), str(catalog.settings_path),
        str(catalog.decision_path), str(catalog.review_path)}
    assert all(path.read_bytes() == content for path, content in before.items())


def test_actual_draft_template_preserves_unknowns_and_has_no_readiness(tmp_path):
    path = tmp_path / 'draft.yaml'
    path.write_bytes((ROOT / 'templates/experiment/experiment_design.yaml').read_bytes())
    report = validator.validate_experiment_design(path, project_root=tmp_path)
    assert report['schema_valid'] and report['valid'], report['errors']
    assert not report['design_ready'] and not report['reviewed'] and not report['campaign_execution_ready']
    assert report['missing_gates'] and not report['environment_checked']


def test_complete_draft_is_not_an_independent_review(tmp_path, monkeypatch):
    catalog = SyntheticCatalog(tmp_path, monkeypatch)
    catalog.design.update(status='draft', review_record=None)
    write_json(catalog.path, catalog.design)
    report = catalog.check()
    assert report['valid'] and report['design_ready'] and not report['reviewed']
    assert not report['campaign_execution_ready']
    assert 'source_bound_experiment_review' in report['missing_gates']
    assert not catalog.check(require_reviewed=True)['valid']


@pytest.mark.parametrize('attack', ['level_order', 'unit', 'source_role', 'probability_role', 'catalog_order', 'settings_seed'])
def test_new_review_cannot_replace_unchanged_structured_source_truth(tmp_path, monkeypatch, attack):
    catalog = SyntheticCatalog(tmp_path, monkeypatch, method='monte_carlo_catalog')
    if attack == 'level_order':
        catalog.design['factors'][0]['levels'].reverse()
    elif attack == 'unit':
        catalog.design['factors'][0]['unit'] = 's'
    elif attack == 'source_role':
        catalog.design['sources'][0]['role'] = 'settings'
    elif attack == 'probability_role':
        catalog.design['probabilities']['role'] = 'assumed'
    elif attack == 'catalog_order':
        catalog.design['catalog'].reverse()
    else:
        catalog.design['seed']['value'] += 1
    catalog.review()
    report = catalog.check(require_reviewed=True)
    assert not report['valid'] and not report['campaign_execution_ready']
    assert any('source' in error for error in report['errors']), report['errors']


@pytest.mark.parametrize('attack', ['missing', 'duplicate_combination', 'order'])
def test_full_factorial_checks_actual_ordered_cartesian_combinations(tmp_path, monkeypatch, attack):
    catalog = SyntheticCatalog(tmp_path, monkeypatch, method='full_factorial', factors=2)
    if attack == 'missing':
        catalog.design['catalog'].pop()
        catalog.design['sample_count'] -= 1
        catalog.sync_settings()
    elif attack == 'order':
        catalog.design['catalog'][1], catalog.design['catalog'][2] = catalog.design['catalog'][2], catalog.design['catalog'][1]
    else:
        first = catalog.design['catalog'][0]['factor_values']
        catalog.design['catalog'][1]['factor_values'] = copy.deepcopy(first)
        def duplicate_inputs(document):
            for inp, declaration in zip(document['spec']['inputs'], first):
                inp['values'] = [declaration['value']] * len(inp['time'])
        catalog.modify_protocol(1, duplicate_inputs)
    catalog.review()
    report = catalog.check(require_reviewed=True)
    assert not report['valid'] and not report['campaign_execution_ready']
    assert any('Cartesian' in error for error in report['errors']), report['errors']
    if attack == 'duplicate_combination':
        assert 'duplicate catalog factor combination' in report['errors']


@pytest.mark.parametrize('attack', ['nonfactor_input', 'parameter', 'solver', 'conditions', 'seed', 'metric_limits'])
def test_reviewed_member_cannot_drift_public_configuration(tmp_path, monkeypatch, attack):
    catalog = SyntheticCatalog(tmp_path, monkeypatch, extra_inputs=1)
    def change(document):
        spec = document['spec']
        if attack == 'nonfactor_input':
            spec['inputs'][1]['values'] = [8.0, 8.0]
        elif attack == 'parameter':
            spec['parameters'][0]['value'] = 3.0
        elif attack == 'solver':
            spec['solver']['name'] = 'ode45'
        elif attack == 'conditions':
            document['conditions']['initial_conditions']['value'] = 1.0
        elif attack == 'seed':
            spec['seed'] += 1
        else:
            spec['metrics'][0]['upper'] = 50.0
    catalog.modify_protocol(1, change)
    catalog.review()
    report = catalog.check(require_reviewed=True)
    assert not report['valid'] and not report['campaign_execution_ready']
    assert any('public run settings' in error for error in report['errors']), report['errors']


@pytest.mark.parametrize('lengths,allowed', [([301], True), ([302], False), ([301, 301], True), ([201, 201, 201], False)])
def test_each_input_and_total_sample_caps(tmp_path, monkeypatch, lengths, allowed):
    catalog = SyntheticCatalog(tmp_path, monkeypatch, extra_inputs=len(lengths) - 1)
    for index in range(len(catalog.design['catalog'])):
        def resize(document):
            for inp, count in zip(document['spec']['inputs'], lengths):
                inp['time'] = [i / (count - 1) for i in range(count)]
                inp['values'] = [inp['values'][0]] * count
        catalog.modify_protocol(index, resize)
    catalog.review()
    report = catalog.check(require_reviewed=True)
    assert report['campaign_execution_ready'] is allowed, report['errors']
    if not allowed:
        assert any('input samples exceed' in error for error in report['errors'])


@pytest.mark.parametrize('attack', ['source_bytes', 'review_bytes', 'decision_bytes', 'quote_slice', 'duplicate_context'])
def test_current_source_and_independent_unicode_review_bytes_are_checked(tmp_path, monkeypatch, attack):
    catalog = SyntheticCatalog(tmp_path, monkeypatch)
    if attack in {'source_bytes', 'review_bytes', 'decision_bytes'}:
        path = {'source_bytes': catalog.levels_path, 'review_bytes': catalog.review_path, 'decision_bytes': catalog.decision_path}[attack]
        path.write_bytes(path.read_bytes() + b'\n')
    else:
        record = load_document(catalog.review_path)
        decision = record['decision']
        if attack == 'quote_slice':
            decision['start'] += 1
        else:
            quote = decision['quote'] + 'project_id=' + catalog.design['project_id'] + '\n'
            prefix = '开发基础设施测试，不是真实用户模型批准。\n'
            catalog.decision_path.write_text(prefix + quote, encoding='utf-8')
            decision.update(**binding(catalog.decision_path), quote=quote, end=len(prefix) + len(quote))
        write_json(catalog.review_path, record)
        catalog.design['review_record'] = binding(catalog.review_path)
        write_json(catalog.path, catalog.design)
    report = catalog.check(require_reviewed=True)
    assert not report['valid'] and not report['campaign_execution_ready'], report


def test_factor_source_requires_exact_structured_payload(tmp_path, monkeypatch):
    catalog = SyntheticCatalog(tmp_path, monkeypatch)
    text_path = tmp_path / 'levels.txt'
    text_path.write_bytes(catalog.levels_path.read_bytes())
    catalog.design['sources'][0].update(binding(text_path))
    catalog.review()
    report = catalog.check(require_reviewed=True)
    assert not report['valid']
    assert any('structured JSON/YAML' in error for error in report['errors'])


def test_mc_event_threshold_is_separate_from_technical_e_limits(tmp_path, monkeypatch):
    catalog = SyntheticCatalog(tmp_path, monkeypatch, method='monte_carlo_catalog')
    catalog.design['event']['threshold'] = 200.0
    catalog.sync_settings()
    catalog.review()
    report = catalog.check(require_reviewed=True)
    assert report['campaign_execution_ready'], report['errors']
    assert report['metric']['upper'] == 100.0 and report['event']['threshold'] == 200.0
    catalog.e_ready = False
    failed = catalog.check(require_reviewed=True)
    assert not failed['campaign_execution_ready']
    assert any(gate.startswith('current_frozen_E_member') for gate in failed['missing_gates'])


def test_deterministic_design_cannot_request_mc_interval(tmp_path, monkeypatch):
    catalog = SyntheticCatalog(tmp_path, monkeypatch)
    catalog.design['event'] = {'comparator': 'gt', 'threshold': 1.0, 'unit': '1',
                             'confidence': 0.95, 'interval': 'wilson_95'}
    catalog.sync_settings()
    catalog.review()
    report = catalog.check(require_reviewed=True)
    assert not report['valid'] and not report['campaign_execution_ready']
    assert any('null Monte Carlo event' in error for error in report['errors'])


def test_member_optional_operation_is_propagated_and_missing_d_stays_blocked(tmp_path, monkeypatch):
    catalog = SyntheticCatalog(tmp_path, monkeypatch)
    catalog.modify_protocol(1, lambda document: document.update(required_A_operations=[
        'matlab.basic_execution', 'simulink.library_load', 'statistics.normcdf']))
    catalog.review()
    report = catalog.check(require_reviewed=True)
    assert report['campaign_execution_ready'] and 'statistics.normcdf' in report['required_A_operations']
    catalog.mapping_ready = False
    blocked = catalog.check(require_reviewed=True)
    assert not blocked['campaign_execution_ready']
    assert 'current_implementation_ready_mapping' in blocked['missing_gates']
