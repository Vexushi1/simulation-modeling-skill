"""Read-only H history and claim decisions; no state promotion or runtime gate."""
from pathlib import Path

from runtime_common import contained_path, sha256_file

STAGES = {'NUMERICALLY_VERIFIED', 'MODEL_VERIFICATION_DECIDED', 'MODEL_VERIFIED'}
SCOPES = {'numerical_verification', 'model_verification'}
HISTORICAL_ROLES = {'numerical_verification', 'model_verification'}


def primary_errors(report, state, root, result):
    """Only the primary model maps to state; other C/D chains stay in the bundle."""
    invalid = []
    for field, anchor in (('primary_receipt', 'primary_run'), ('primary_protocol', 'protocol')):
        binding, expected = report.get(field), state.get(anchor)
        if (not binding or not expected or contained_path(root, binding['path']) !=
                contained_path(root, expected['path']) or binding['sha256'] != expected['sha256']):
            invalid.append('H primary differs from state ' + anchor + ' binding')
    for anchor in ('problem', 'model', 'approval', 'mapping'):
        binding = (report.get('primary_upstream') or {}).get(anchor)
        expected = state.get(anchor)
        if (not binding or not expected or contained_path(root, binding['path']) !=
                contained_path(root, expected['path']) or binding['sha256'] != expected['sha256']):
            invalid.append('H primary differs from state ' + anchor + ' binding')
    if not result.get('implementation_ready') or not result.get('primary_run_complete'):
        invalid.append('H requires current primary B/C/D/E historical evidence')
    return invalid


def validate_bindings(state, root, result, errors, stale, scope):
    result.update(numerical_verification_checked=False, model_verification_checked=False,
                  numerically_verified=False, model_verification_decided=False, model_verified=False)
    for anchor in HISTORICAL_ROLES:
        binding = state.get(anchor)
        path = contained_path(root, binding['path']) if binding else None
        result[anchor + '_path'] = str(path) if path else None
    if scope not in {'all'} | SCOPES:
        return
    from validate_verification_receipt import validate_verification_receipt
    for anchor, kind in (('numerical_verification', 'H1'), ('model_verification', 'H2')):
        if anchor == 'model_verification' and scope == 'numerical_verification':
            continue
        result[anchor + '_checked'] = True
        binding = state.get(anchor)
        if not binding:
            continue
        path = Path(result[anchor + '_path'])
        report = validate_verification_receipt(path, project_root=root, kind=kind)
        result[anchor + '_validation'] = report
        invalid = list(report['errors']) if not report['valid'] else []
        if not report.get('evidence_complete') or report.get('project_id') != state['project_id']:
            invalid.append('H needs complete current project evidence')
        if not path.is_file() or sha256_file(path) != binding['sha256']:
            invalid.append('H receipt SHA differs from state binding')
        invalid.extend(primary_errors(report, state, root, result))
        if kind == 'H1' and not report.get('numerically_verified'):
            invalid.append('H1 numerical criteria have not passed')
        if kind == 'H2' and not result['numerically_verified']:
            invalid.append('H2 state requires the bound successful primary H1')
        if invalid:
            errors.extend(anchor + ': ' + error for error in invalid)
            stale.add(anchor)
        elif kind == 'H1':
            result['numerically_verified'] = True
        else:
            result['model_verification_decided'] = bool(report.get('model_verification_decided'))
            result['model_verified'] = bool(report.get('model_verified'))
    enforce_stage(state, result, errors, scope)


def enforce_stage(state, result, errors, scope):
    if scope not in {'all'} | SCOPES or state['current_stage'] not in STAGES:
        return
    if not result['numerically_verified']:
        errors.append('NUMERICALLY_VERIFIED requires current passing H1 evidence')
    if scope != 'numerical_verification' and state['current_stage'] in {'MODEL_VERIFICATION_DECIDED', 'MODEL_VERIFIED'}:
        if not result['model_verification_decided']:
            errors.append('MODEL_VERIFICATION_DECIDED requires complete H2 evidence')
        if state['current_stage'] == 'MODEL_VERIFIED' and not result['model_verified']:
            errors.append('MODEL_VERIFIED requires support with no open required actions')


def validate_artifact(item, *, state, result, root, environment_dependents, ancestor_roles):
    anchor = item['role']
    binding = state.get(anchor)
    path = contained_path(root, item['path'])
    needed = {'problem', 'model', 'approval', 'mapping', 'protocol', 'primary_run', anchor}
    if anchor == 'model_verification':
        needed.add('numerical_verification')
    invalid = []
    if item['id'] in environment_dependents:
        invalid.append('historical H evidence cannot depend on current runtime readiness')
    if (not binding or path != Path(result[anchor + '_path']) or item['sha256'] != binding['sha256'] or
            not needed <= set(item['depends_on'])):
        invalid.append('accepted H evidence must match and depend on its primary historical anchors')
    if not {'simulation_run', 'simulation_protocol'} <= ancestor_roles(item):
        invalid.append('accepted H evidence lacks its primary E dependency chain')
    gate = 'numerically_verified' if anchor == 'numerical_verification' else 'model_verification_decided'
    if not result.get(gate):
        invalid.append('accepted H evidence requires current recomputed evidence')
    if anchor == 'model_verification' and 'numerical_verification' not in ancestor_roles(item):
        invalid.append('accepted H2 evidence lacks its H1 dependency chain')
    return invalid
