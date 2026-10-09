"""Campaign composition attacks; fixtures do not qualify MATLAB or actual models."""
import copy
import uuid
from datetime import timedelta
from pathlib import Path

import pytest

import run_experiment as runner
import validate_experiment_receipt as consumer
from runtime_common import canonical_digest, load_document, sha256_file


EVENT = {'comparator': 'gt', 'threshold': 0.5, 'confidence': 0.95, 'interval': 'wilson_95', 'unit': '1'}


@pytest.fixture
def campaign(tmp_path, monkeypatch):
    """Fake only the already-independent native validators; exercise the real G wrapper."""
    import experiment_sampling
    import run_simulation
    import validate_environment
    import validate_experiment_design
    import validate_experiment_profile
    import validate_simulation_profile
    import validate_simulation_receipt
    executable = tmp_path / 'matlab.exe'
    executable.write_text('SYNTHETIC INFRASTRUCTURE TEST', encoding='utf-8')
    runtime = {'executable': str(executable), 'fingerprint': 'same-runtime'}
    design_path = tmp_path / 'design.json'
    runner.checkpoint(design_path, {'method': 'monte_carlo_catalog', 'synthetic': True})
    profiles = {}
    for name, receipt_name in (('a', 'receipt.json'), ('e', 'simulation-profile-receipt.json'), ('g', 'experiment-profile-receipt.json')):
        directory = tmp_path / name
        directory.mkdir()
        profiles[name] = directory / 'profile.json'
        runner.checkpoint(profiles[name], {'runtime': runtime})
        runner.checkpoint(directory / receipt_name, {'synthetic': True})
    d_receipt = tmp_path / 'D.json'
    runner.checkpoint(d_receipt, {'runtime': runtime})
    catalog = []
    for identity, value in (('low', 0.0), ('high', 1.0)):
        protocol = tmp_path / (identity + '.json')
        runner.checkpoint(protocol, {'synthetic': True, 'value': value})
        catalog.append({'id': identity, 'protocol_path': str(protocol), 'protocol_sha256': sha256_file(protocol),
            'protocol_semantic_sha256': identity, 'run_spec_sha256': identity,
            'protocol_report': {'execution_ready': True, 'frozen': True, 'contract_sha256': sha256_file(protocol),
                'implementation_receipt_path': str(d_receipt), 'run_spec': {'solver': {'name': 'ode4'}},
                'contract_path': str(protocol), 'synthetic_metric_value': value,
                'required_A_operations': ['matlab.basic_execution', 'simulink.library_load']}})
    report = {'valid': True, 'schema_valid': True, 'design_ready': True, 'reviewed': True,
        'campaign_execution_ready': True, 'errors': [], 'missing_gates': [], 'project_root': str(tmp_path),
        'project_id': 'synthetic', 'contract_path': str(design_path), 'design_sha256': sha256_file(design_path),
        'semantic_sha256': 'synthetic-semantic', 'method': 'monte_carlo_catalog',
        'sampling_spec': {'method': 'monte_carlo_catalog', 'catalog_ids': ['low', 'high'], 'draws': 3,
                          'probabilities': [0.5, 0.5], 'seed': 17},
        'catalog': catalog, 'metric': {'id': 'final', 'unit': '1'}, 'event': EVENT,
        'budget': {'max_cases': 16, 'total_timeout': 60, 'member_process_timeout': 10,
                   'member_simulation_timeout': 1, 'max_artifact_bytes': 1_000_000},
        'bound_files': [], 'required_A_operations': ['matlab.basic_execution', 'simulink.library_load']}
    expected_sampling = copy.deepcopy(report['sampling_spec'])
    calls, a_calls, indices = [], [], [2, 2, 1]
    def fake_a(path, *, required_operations=None, **kwargs):
        a_calls.append((list(required_operations or []), kwargs.get('now')))
        return {'valid': True, 'runtime_assured': True, 'profile_current': True, 'errors': []}
    def fake_e_profile(path, **kwargs):
        return {'valid': True, 'simulation_assured': True, 'profile_current': True, 'runtime': runtime, 'errors': []}
    def fake_g_profile(path, **kwargs):
        return {'valid': True, 'sampling_assured': True, 'qualified_methods': list(runner.METHODS), 'runtime': runtime, 'errors': []}
    def fake_sample(spec, executable, directory, **kwargs):
        directory = Path(directory)
        directory.mkdir()
        path = directory / 'sample-receipt.json'
        runner.checkpoint(path, {'sampling_spec': spec, 'sample_indices': indices, 'runtime': runtime,
            'run_id': str(uuid.uuid4()), 'process': {'started_at': runner.utc_now(), 'finished_at': runner.utc_now()}})
        return path
    def fake_sample_check(path):
        document = load_document(path)
        return {'valid': document['sampling_spec'] == expected_sampling, 'method': 'monte_carlo_catalog',
            'sampling_spec': document['sampling_spec'], 'sample_indices': document['sample_indices'],
            'uniforms': [0.75, 0.75, 0.25], 'runtime': runtime, 'run_id': document['run_id'],
            'receipt_sha256': sha256_file(path), 'process': document['process'], 'errors': []}
    def fake_run(protocol, executable, directory, **kwargs):
        calls.append((str(protocol), str(directory), kwargs))
        directory = Path(directory)
        directory.mkdir()
        started = runner.utc_now()
        member = next(item for item in catalog if item['protocol_path'] == str(protocol))
        e_operations = list(dict.fromkeys(member['protocol_report']['required_A_operations']
                                         + kwargs['required_operations']))
        runner.checkpoint(directory / 'simulation-inputs.json',
                          {'cases': [{'simulation_timeout': kwargs['simulation_timeout']}], 'bindings': {
                              'environment_profile': runner.file_binding(kwargs['environment_profile']),
                              'environment_receipt': runner.file_binding(Path(kwargs['environment_profile']).parent / 'receipt.json'),
                              'simulation_profile': runner.file_binding(kwargs['simulation_profile']),
                              'simulation_profile_receipt': runner.file_binding(Path(kwargs['simulation_profile']).parent / 'simulation-profile-receipt.json'),
                              'required_A_operations': e_operations}})
        path = directory / 'simulation-receipt.json'
        runner.checkpoint(path, {'run_id': str(uuid.uuid4()), 'runtime': runtime, 'protocol': str(protocol),
            'value': load_document(protocol)['value'], 'process': {'started_at': started, 'finished_at': runner.utc_now()}})
        return {'valid': True, 'primary_run_complete': True, 'receipt_path': str(path), 'errors': [],
                'metrics': [{'id': 'final', 'value': load_document(protocol)['value'], 'passed': True}]}
    def fake_e_check(path, *, protocol_report=None, **kwargs):
        document = load_document(path)
        valid = document['protocol'] == protocol_report['contract_path']
        return {'valid': valid, 'primary_run_complete': valid, 'errors': [],
                'metrics': [{'id': 'final', 'value': document['value'], 'passed': True}]}
    old_load = runner.load_contract
    def fake_contract(path):
        if path == 'core/experiment_assurance_contract.yaml':
            return {'source_files': ['scripts/run_experiment.py'], 'evidence': {'profile_receipt': 'experiment-profile-receipt.json'}}
        return old_load(path)
    monkeypatch.setattr(runner, 'load_contract', fake_contract)
    monkeypatch.setattr(validate_experiment_design, 'validate_experiment_design', lambda *args, **kwargs: copy.deepcopy(report))
    monkeypatch.setattr(runner, 'validate_environment', fake_a)
    monkeypatch.setattr(validate_environment, 'validate_environment', fake_a)
    monkeypatch.setattr(runner, 'validate_simulation_profile', fake_e_profile)
    monkeypatch.setattr(validate_simulation_profile, 'validate_simulation_profile', fake_e_profile)
    monkeypatch.setattr(validate_experiment_profile, 'validate_experiment_profile', fake_g_profile)
    monkeypatch.setattr(experiment_sampling, 'sample_experiment', fake_sample)
    monkeypatch.setattr(experiment_sampling, 'validate_sample_receipt', fake_sample_check)
    monkeypatch.setattr(run_simulation, 'run_simulation', fake_run)
    monkeypatch.setattr(validate_simulation_receipt, 'validate_simulation_receipt', fake_e_check)
    monkeypatch.setattr(runner, 'same_runtime', lambda a, b: a == b)
    monkeypatch.setattr(consumer, 'same_runtime', lambda a, b: a == b)
    def run(**kwargs):
        return runner.run_experiment(design_path, executable, tmp_path / 'campaign', environment_profile=profiles['a'],
            simulation_profile=profiles['e'], experiment_profile=profiles['g'], project_root=tmp_path, **kwargs)
    return {'run': run, 'root': tmp_path, 'report': report, 'calls': calls, 'a_calls': a_calls,
            'indices': indices, 'e_run': fake_run, 'design': design_path, 'profiles': profiles,
            'g_profile_validator': fake_g_profile}


def reseal(directory, receipt):
    """Recompute ordinary byte hashes so semantic attacks reach independent readback."""
    runner.checkpoint(directory / runner.LEDGER, {'schema_version': 1, 'run_id': receipt['run_id'],
        'status': receipt['process']['status'], 'rows': receipt['rows'], 'errors': receipt['errors']})
    runner.checkpoint(directory / runner.SUMMARY, {'summary': receipt['summary']})
    receipt['artifacts'] = runner.artifact_manifest(directory)
    runner.checkpoint(directory / runner.RECEIPT, receipt)


def test_repeated_draws_keep_distinct_e_calls_and_fixed_n(campaign):
    result = campaign['run'](required_operations=['statistics.lhsdesign'])
    assert result['valid'], result['errors']
    assert [Path(call[0]).stem for call in campaign['calls']] == ['high', 'high', 'low']
    assert len({call[1] for call in campaign['calls']}) == 3
    assert all('statistics.lhsdesign' in call[2]['required_operations'] for call in campaign['calls'])
    assert all('statistics.lhsdesign' in operations for operations, _ in campaign['a_calls'])
    assert any(now is not None for _, now in campaign['a_calls'])
    assert result['summary']['event']['count'] == 2
    assert result['summary']['event']['denominator'] == 3
    assert result['summary']['n'] == 3


@pytest.mark.parametrize('attack', ['deduplicate', 'catalog_id', 'metric', 'event_denominator', 'probabilities', 'sample_probabilities', 'reuse_run_id', 'old_sources'])
def test_resealed_campaign_attacks_are_rejected(campaign, attack):
    assert campaign['run']()['valid']
    directory = campaign['root'] / 'campaign'
    receipt = load_document(directory / runner.RECEIPT)
    if attack == 'deduplicate':
        receipt['rows'].pop(1)
    elif attack == 'catalog_id':
        receipt['rows'][0]['catalog_id'] = 'low'
    elif attack == 'metric':
        receipt['rows'][0]['metric_value'] = 0.0
        receipt['summary'] = consumer.summarize([0.0, 1.0, 0.0], 'monte_carlo_catalog', EVENT)
    elif attack == 'event_denominator':
        receipt['summary']['event']['denominator'] = 2
    elif attack == 'sample_probabilities':
        sample_path = Path(receipt['sampling_receipt']['path'])
        sample = load_document(sample_path)
        sample['sampling_spec']['probabilities'] = [0.9, 0.1]
        runner.checkpoint(sample_path, sample)
        receipt['sampling_receipt']['sha256'] = sha256_file(sample_path)
    elif attack == 'reuse_run_id':
        first = load_document(receipt['rows'][0]['receipt']['path'])
        second_path = Path(receipt['rows'][1]['receipt']['path'])
        second = load_document(second_path)
        second['run_id'] = first['run_id']
        runner.checkpoint(second_path, second)
        receipt['rows'][1]['receipt']['sha256'] = sha256_file(second_path)
    else:
        request = load_document(directory / runner.INPUT)
        if attack == 'probabilities':
            request['sampling_spec']['probabilities'] = [0.9, 0.1]
        else:
            request['sources'] = {'old': 'source'}
            receipt['sources'] = request['sources']
        request['input_identity'] = canonical_digest({k:v for k,v in request.items() if k != 'input_identity'})
        receipt['input_identity'] = request['input_identity']
        runner.checkpoint(directory / runner.INPUT, request)
    reseal(directory, receipt)
    result = consumer.validate_experiment_receipt(directory / runner.RECEIPT, project_root=campaign['root'])
    assert not result['valid'] and not result['campaign_complete']


@pytest.mark.parametrize('attack', ['simulation_timeout', 'process_duration'])
def test_resealed_member_budget_evidence_is_required(campaign, attack):
    assert campaign['run']()['valid']
    directory = campaign['root'] / 'campaign'
    receipt = load_document(directory / runner.RECEIPT)
    row = receipt['rows'][0]
    e_path = Path(row['receipt']['path'])
    if attack == 'simulation_timeout':
        e_input_path = e_path.parent / 'simulation-inputs.json'
        e_input = load_document(e_input_path)
        e_input['cases'][0]['simulation_timeout'] = 60
        runner.checkpoint(e_input_path, e_input)
    else:
        e_receipt = load_document(e_path)
        e_start = consumer._time(e_receipt['process']['finished_at']) - timedelta(seconds=11)
        e_receipt['process']['started_at'] = e_start.isoformat()
        row['started_at'] = e_start.isoformat()
        receipt['process']['started_at'] = (e_start - timedelta(seconds=2)).isoformat()
        runner.checkpoint(e_path, e_receipt)
        row['receipt']['sha256'] = sha256_file(e_path)
        sample_path = Path(receipt['sampling_receipt']['path'])
        sample = load_document(sample_path)
        sample['process'] = {'started_at': (e_start - timedelta(seconds=1)).isoformat(),
                             'finished_at': (e_start - timedelta(seconds=0.5)).isoformat()}
        runner.checkpoint(sample_path, sample)
        receipt['sampling_receipt']['sha256'] = sha256_file(sample_path)
    reseal(directory, receipt)
    result = consumer.validate_experiment_receipt(directory / runner.RECEIPT, project_root=campaign['root'])
    assert not result['valid'] and not result['campaign_complete']
    assert any('reviewed member budget' in error for error in result['errors']), result['errors']


@pytest.mark.parametrize('attack', ['drop_caller_operation', 'replace_profile'])
def test_member_requires_exact_campaign_qualification_and_operations(campaign, attack):
    assert campaign['run'](required_operations=['statistics.lhsdesign'])['valid']
    directory = campaign['root'] / 'campaign'
    receipt = load_document(directory / runner.RECEIPT)
    e_input_path = Path(receipt['rows'][1]['receipt']['path']).parent / 'simulation-inputs.json'
    e_input = load_document(e_input_path)
    if attack == 'drop_caller_operation':
        e_input['bindings']['required_A_operations'].remove('statistics.lhsdesign')
    else:
        other = campaign['root'] / 'other-same-runtime-profile.json'
        runner.checkpoint(other, load_document(campaign['profiles']['e']))
        e_input['bindings']['simulation_profile'] = runner.file_binding(other)
    runner.checkpoint(e_input_path, e_input)
    reseal(directory, receipt)
    result = consumer.validate_experiment_receipt(directory / runner.RECEIPT)
    assert not result['valid'] and not result['campaign_complete']
    assert any('actual E qualification' in error or 'complete campaign union' in error
               for error in result['errors']), result['errors']


def test_member_historical_start_rechecks_campaign_ttl(campaign, monkeypatch):
    import validate_experiment_profile
    assert campaign['run']()['valid']
    directory = campaign['root'] / 'campaign'
    receipt = load_document(directory / runner.RECEIPT)
    expires = consumer._time(receipt['rows'][1]['started_at'])
    checked_times = []
    def bounded_g(path, **kwargs):
        now = kwargs.get('now')
        checked_times.append(now)
        result = campaign['g_profile_validator'](path, **kwargs)
        if now is not None and now >= expires:
            result.update(valid=False, errors=['G expired at this member start'])
        return result
    monkeypatch.setattr(validate_experiment_profile, 'validate_experiment_profile', bounded_g)
    result = consumer.validate_experiment_receipt(directory / runner.RECEIPT)
    assert not result['valid'] and not result['campaign_complete']
    assert expires in checked_times
    assert any('G expired at this member start' in error for error in result['errors'])


def test_member_operation_order_matches_public_e_producer(campaign):
    campaign['report']['catalog'][1]['protocol_report']['required_A_operations'].reverse()
    result = campaign['run'](required_operations=['statistics.lhsdesign'])
    assert result['valid'], result['errors']
    directory = campaign['root'] / 'campaign'
    receipt = load_document(directory / runner.RECEIPT)
    e_input = load_document(Path(receipt['rows'][0]['receipt']['path']).parent / 'simulation-inputs.json')
    assert e_input['bindings']['required_A_operations'] == [
        'simulink.library_load', 'matlab.basic_execution', 'statistics.lhsdesign']


def test_failure_stops_without_replacing_samples_or_publishing_ci(campaign, monkeypatch):
    import run_simulation
    calls = campaign['calls']
    def failed_second(protocol, executable, directory, **kwargs):
        if len(calls) == 1:
            calls.append((str(protocol), str(directory), kwargs))
            return {'valid': False, 'primary_run_complete': False, 'errors': ['technical simulation failure']}
        return campaign['e_run'](protocol, executable, directory, **kwargs)
    monkeypatch.setattr(run_simulation, 'run_simulation', failed_second)
    result = campaign['run']()
    assert not result['valid'] and len(calls) == 2
    receipt = load_document(campaign['root'] / 'campaign' / runner.RECEIPT)
    assert [row['status'] for row in receipt['rows']] == ['completed', 'failed', 'not_attempted']
    assert receipt['summary'] is None
    receipt['process']['status'], receipt['errors'] = 'completed', []
    receipt['summary'] = consumer.summarize([1.0], 'monte_carlo_catalog', EVENT)
    reseal(campaign['root'] / 'campaign', receipt)
    assert not consumer.validate_experiment_receipt(campaign['root'] / 'campaign' / runner.RECEIPT)['valid']


def test_current_qualification_failure_blocks_before_mkdir(campaign, monkeypatch):
    monkeypatch.setattr(runner, 'validate_environment', lambda *args, **kwargs: {'valid': False, 'errors': ['required operation stale']})
    with pytest.raises(ValueError, match='qualification failed'):
        campaign['run'](required_operations=['statistics.lhsdesign'])
    assert not (campaign['root'] / 'campaign').exists() and not campaign['calls']


def test_checkpoint_encoding_or_replace_failure_preserves_previous(tmp_path, monkeypatch):
    path = tmp_path / 'ledger.json'
    runner.checkpoint(path, {'status': 'running', 'completed': 2})
    original = path.read_bytes()
    with pytest.raises(ValueError):
        runner.checkpoint(path, {'status': 'failed', 'value': float('nan')})
    assert path.read_bytes() == original
    def reject_replace(*args):
        raise OSError('controlled replace failure')
    monkeypatch.setattr(runner.os, 'replace', reject_replace)
    with pytest.raises(OSError, match='replace failure'):
        runner.checkpoint(path, {'status': 'failed', 'completed': 2})
    assert path.read_bytes() == original
    assert any(tmp_path.glob('ledger.json.*.tmp'))


def test_nominal_wilson_endpoints_and_deterministic_summary():
    zero = consumer.summarize([0.0] * 16, 'monte_carlo_catalog', EVENT)['event']
    all_events = consumer.summarize([1.0] * 16, 'monte_carlo_catalog', EVENT)['event']
    assert zero['count'] == 0 and zero['upper'] == pytest.approx(0.19360768053443655)
    assert all_events['count'] == 16 and all_events['lower'] == pytest.approx(1 - zero['upper'])
    assert consumer.summarize([0.0, 1.0], 'scenario_matrix', None)['event'] is None
