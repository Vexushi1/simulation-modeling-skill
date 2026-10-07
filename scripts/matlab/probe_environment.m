function probe_environment(inputPath)
% Phase A only: operation-scoped smoke calls, no business simulation/model save.
% APIs: MathWorks R2025b license/normcdf/fitlm/lhsdesign/load_system docs.
request = jsondecode(fileread(inputPath));
rawPath = fullfile(request.output_directory, 'raw-probe.json');
report = struct('schema_version', 1, 'run_id', request.run_id, 'status', 'running', ...
    'channel', 'matlab_batch', 'host_fingerprint', request.host_fingerprint, ...
    'input_identity', request.input_identity, 'source_identity', request.source_identity, ...
    'started_at', utcNow(), 'finished_at', '');
report.runtime = struct('release', ['R' version('-release')], 'version', version, ...
    'matlabroot', matlabroot, 'platform', computer);
report.installed_products = ver;
report.licenses_inuse = license('inuse');
report.operations = repmat(emptyRecord(), 0, 1);
writeRaw(rawPath, report);
specifications = request.operation_specs;
for index = 1:numel(specifications)
    specification = specifications(index);
    result = emptyRecord();
    result.operation_id = specification.operation_id;
    result.parameters = specification.input;
    try
        result.license_test = license('test', specification.license_feature);
    catch exception
        result.license_error = errorRecord(exception);
    end
    functionNames = specification.functions;
    if ischar(functionNames), functionNames = {functionNames}; end
    result.functions = repmat(struct('name', '', 'path', ''), 0, 1);
    for functionIndex = 1:numel(functionNames)
        name = functionNames{functionIndex};
        result.functions(end+1) = struct('name', name, 'path', which(name)); %#ok<AGROW>
    end
    lastwarn('');
    result.attempted = true;
    try
        result.output = callOperation(specification.operation_id, specification.input);
        result.call_success = true;
    catch exception
        result.error = errorRecord(exception);
    end
    [result.warning_message, result.warning_identifier] = lastwarn;
    report.operations(end+1) = result; %#ok<AGROW>
    writeRaw(rawPath, report);
end
report.licenses_inuse = license('inuse');
report.finished_at = utcNow();
report.status = 'completed';
writeRaw(rawPath, report);
fprintf('Phase A operation probe completed: %s\n', rawPath);
end

function result = emptyRecord()
result = struct('operation_id', '', 'parameters', [], 'license_test', [], 'license_error', [], ...
    'functions', [], 'attempted', false, 'call_success', false, 'output', [], ...
    'error', [], 'warning_message', '', 'warning_identifier', '');
end

function output = callOperation(operationId, parameters)
switch operationId
    case 'matlab.basic_execution'
        output = struct('value', sum(parameters.values));
    case 'simulink.library_load'
        library = parameters.library;
        handle = load_system(library);
        cleanup = onCleanup(@() close_system(library, 0));
        output = struct('library_name', library, 'loaded', bdIsLoaded(library), ...
            'diagram_type', get_param(library, 'BlockDiagramType'), ...
            'file_name', get_param(library, 'FileName'), 'returned_handle', handle, ...
            'simulation_run', false, 'model_saved', false, 'closed_without_save', false);
        clear cleanup
        output.closed_without_save = ~bdIsLoaded(library);
    case 'statistics.normcdf'
        output = struct('value', normcdf(parameters.x));
    case 'statistics.fitlm'
        model = fitlm(parameters.x(:), parameters.y(:));
        output = struct('coefficients', model.Coefficients.Estimate, ...
            'predictions', predict(model, parameters.prediction_x(:)), 'rmse', model.RMSE);
    case 'statistics.lhsdesign'
        rng(parameters.seed, parameters.generator);
        output = struct('sample', lhsdesign(parameters.n, parameters.p));
    otherwise
        error('PhaseA:UnknownOperation', 'Unknown Phase A operation: %s', operationId);
end
end

function value = utcNow()
value = char(datetime('now', 'TimeZone', 'UTC', 'Format', 'yyyy-MM-dd''T''HH:mm:ss.SSSSSS''Z'''));
end

function output = errorRecord(exception)
output = struct('identifier', exception.identifier, 'message', exception.message, ...
    'stack', exception.stack, 'report', getReport(exception, 'extended', 'hyperlinks', 'off'));
end

function writeRaw(path, report)
file = fopen(path, 'w', 'n', 'UTF-8');
assert(file ~= -1, 'PhaseA:ReportWrite', 'Cannot write raw probe JSON.');
cleanup = onCleanup(@() fclose(file));
fprintf(file, '%s\n', jsonencode(report, 'PrettyPrint', true));
end
