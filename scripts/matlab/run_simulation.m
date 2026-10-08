function run_simulation(inputPath)
% Owned normal-mode scalar simulation only; no user callbacks or expressions.
request = jsondecode(fileread(inputPath));
directory = request.output_directory;
originalRng = rng;
rngCleanup = onCleanup(@() rng(originalRng));
fileConfig = Simulink.fileGenControl('getConfig');
fileCleanup = onCleanup(@() Simulink.fileGenControl('setConfig', 'config', fileConfig));
Simulink.fileGenControl('set', 'CacheFolder', fullfile(directory, 'cache'), ...
    'CodeGenFolder', fullfile(directory, 'codegen'), 'createDir', true);
cd(directory);
rawPath = fullfile(directory, 'raw-simulation.json');
report = struct('schema_version', 1, 'run_id', request.run_id, 'status', 'running', ...
    'channel', 'matlab_batch', 'host_fingerprint', request.host_fingerprint, ...
    'input_identity', request.input_identity, 'source_identity', request.source_identity, ...
    'started_at', utcNow(), 'finished_at', '', 'runtime', struct(), ...
    'installed_products', {jsonRecords(ver)}, 'license_test', license('test', 'SIMULINK'), ...
    'licenses_inuse', {jsonRecords(license('inuse'))}, 'functions', {{}}, 'cases', {{}});
report.runtime = struct('release', ['R' version('-release')], 'version', version, ...
    'matlabroot', matlabroot, 'platform', computer);
for index = 1:numel(request.required_functions)
    name = request.required_functions{index};
    report.functions{end+1} = struct('name', name, 'path', which(name)); %#ok<AGROW>
end
writeJson(rawPath, report);
for index = 1:numel(request.cases)
    item = request.cases(index);
    record = emptyRecord(item.case_id);
    record.functions = report.functions;
    report.cases{index} = record;
    lastwarn('');
    try
        record = simulateOwned(item, request.mode, directory, request.run_id, record, @checkpoint);
    catch exception
        record.framework_error = exceptionRecord(exception);
    end
    [record.last_warning_message, record.last_warning_identifier] = lastwarn;
    report.cases{index} = record;
    writeJson(rawPath, report);
end
report.licenses_inuse = jsonRecords(license('inuse'));
report.finished_at = utcNow();
report.status = 'completed';
writeJson(rawPath, report);
fprintf('Actual Phase E simulation records preserved: %s\n', rawPath);
clear fileCleanup rngCleanup

    function checkpoint(progress)
        % Preserve returned data and partial diagnostics even if normalization fails.
        record = progress;
        report.cases{index} = progress;
        writeJson(rawPath, report);
    end
end

function record = emptyRecord(identity)
record = struct('case_id', identity, 'attempted', true, 'completed', false, ...
    'simulation_returned', false, 'error_message', '', 'framework_error', struct(), ...
    'warnings', {{}}, 'errors', {{}}, 'functions', {{}}, 'outputs', {{}}, ...
    'before_parameters', {{}}, 'applied_parameters', {{}}, 'after_parameters', {{}}, ...
    'reopened_parameters', {{}}, 'source_unchanged', false, 'owned_model_unchanged', false, ...
    'before_output_sampling', {{}}, 'configured_output_sampling', {{}}, ...
    'after_output_sampling', {{}}, 'reopened_output_sampling', {{}}, 'output_sampling_restored', false, ...
    'configuration_restored', false, 'parameters_restored', false, 'reopened', false, ...
    'closed_without_save', false, 'model_file', '', 'source_model_file', '', ...
    'mat_file', '', 'raw_mat_file', '', 'data_file', '', 'output_count', 0, 'output_boundary_error', '', ...
    'stop_event', '', 'stop_event_time', NaN, 'time_source', 'SimulationOutput.tout', 'saved_time', {{}}, 'requested_solver', struct(), ...
    'configured_parameters', struct(), 'effective_configuration', struct(), ...
    'observed_solver_info', struct(), 'last_warning_message', '', 'last_warning_identifier', '');
end

function record = simulateOwned(item, mode, directory, identity, record, checkpoint)
spec = item.run_spec;
model = spec.model_name;
assert(~bdIsLoaded(model), 'PhaseE:AlreadyLoaded', 'An owned model name is already loaded.');
ownedPath = fullfile(directory, [model '.slx']);
assert(~isfile(ownedPath), 'PhaseE:ExistingModel', 'A model copy already exists.');
sourcePath = spec.model_path;
if strcmp(mode, 'probe'), buildFixture(item.build_spec, sourcePath); end
assert(isfile(sourcePath), 'PhaseE:MissingSource', 'The bound original SLX is absent.');
sourceBytes = fileBytes(sourcePath);
copyfile(sourcePath, ownedPath);
ownedBytes = fileBytes(ownedPath);
assert(isequal(sourceBytes, ownedBytes), 'PhaseE:CopyBytes', 'The owned copy differs.');
load_system(ownedPath);
modelCleanup = onCleanup(@() closeOwnedModel(model));
assert(strcmp(get_param(model, 'FileName'), ownedPath), 'PhaseE:OwnedPath', 'Loaded a different model.');
assertSurface(model, item.build_spec);
record.model_file = ownedPath;
record.source_model_file = sourcePath;
beforeConfig = configurationSnapshot(model);
record.before_parameters = parameterSnapshot(model, spec.parameters);
record.before_output_sampling = outputSamplingSnapshot(spec.outputs);
in = Simulink.SimulationInput(model);
in = setModelParameter(in, 'SimulationMode', 'normal', 'StartTime', numtext(spec.start_time), ...
    'StopTime', numtext(spec.stop_time), 'CaptureErrors', 'on', 'TimeOut', item.simulation_timeout, ...
    'FastRestart', 'off', 'SaveOutput', 'on', 'OutputSaveName', 'yout', 'SaveFormat', 'Dataset', ...
    'DatasetSignalFormat', 'timeseries', 'SaveTime', 'on', 'TimeSaveName', 'tout', ...
    'SaveState', 'off', 'SignalLogging', 'off', 'LimitDataPoints', 'off', 'Decimation', '1');
solver = spec.solver;
solverType = 'Variable-step';
if strcmp(solver.type, 'fixed-step'), solverType = 'Fixed-step'; end
in = setModelParameter(in, 'Solver', solver.name, 'SolverType', solverType, 'ZeroCrossControl', solver.zero_crossing);
record.requested_solver = nullableSolver(solver);
record.configured_parameters = struct('Solver', solver.name, 'SolverType', solverType, 'ZeroCrossControl', solver.zero_crossing);
if strcmp(solver.name, 'ode4')
    in = setModelParameter(in, 'FixedStep', numtext(solver.fixed_step));
    record.configured_parameters.FixedStep = solver.fixed_step;
else
    in = setModelParameter(in, 'MaxStep', numtext(solver.max_step), 'MinStep', numtext(solver.min_step), ...
        'InitialStep', numtext(solver.initial_step), 'RelTol', numtext(solver.rel_tol), 'AbsTol', numtext(solver.abs_tol));
    record.configured_parameters.MaxStep = solver.max_step;
    record.configured_parameters.MinStep = solver.min_step;
    record.configured_parameters.InitialStep = solver.initial_step;
    record.configured_parameters.RelTol = solver.rel_tol;
    record.configured_parameters.AbsTol = solver.abs_tol;
end
for index = 1:numel(spec.parameters)
    parameterSpec = spec.parameters(index);
    parameter = Simulink.Parameter(parameterSpec.value);
    parameter.DataType = 'double';
    if ~isempty(parameterSpec.unit), parameter.Unit = parameterSpec.unit; end
    in = setVariable(in, parameterSpec.code_name, parameter, 'Workspace', model);
    variables = in.Variables;
    selected = find(strcmp({variables.Name}, parameterSpec.code_name) & strcmp({variables.Workspace}, model));
    assert(numel(selected) == 1, 'PhaseE:VariableScope', 'Override must target the exact model workspace.');
    bound = variables(selected).Value;
    record.applied_parameters{end+1} = parameterRecord(parameterSpec.code_name, bound); %#ok<AGROW>
end
if ~isempty(spec.inputs)
    ds = Simulink.SimulationData.Dataset;
    [~, order] = sort([spec.inputs.port]);
    for index = order
        signal = spec.inputs(index);
        ts = timeseries(signal.values(:), signal.time(:));
        ts.Name = signal.variable_id;
        if ~isempty(signal.unit), ts.DataInfo.Units = signal.unit; end
        ts.DataInfo.Interpolation = tsdata.interpolation(signal.interpolation);
        ds{signal.port} = ts;
        interpolation = 'off';
        if strcmp(signal.interpolation, 'linear'), interpolation = 'on'; end
        in = setBlockParameter(in, signal.block_path, 'Interpolate', interpolation);
    end
    in = setExternalInput(in, ds);
else
    in = setModelParameter(in, 'LoadExternalInput', 'off');
end
% Root output sampling is reviewed separately from the internal solver step.
% Read back the configured override from the actual SimulationInput object.
for index = 1:numel(spec.outputs)
    output = spec.outputs(index);
    assert(isa(output.sample_time, 'double') && isscalar(output.sample_time) && output.sample_time == 0, ...
        'PhaseE:OutputSampling', 'Only explicitly reviewed continuous root-output sampling is supported.');
    in = setBlockParameter(in, output.block_path, 'SampleTime', numtext(output.sample_time));
end
blockParameters = in.BlockParameters;
for index = 1:numel(spec.outputs)
    output = spec.outputs(index);
    selected = find(strcmp({blockParameters.BlockPath}, output.block_path) & strcmp({blockParameters.Name}, 'SampleTime'));
    assert(numel(selected) == 1 && strcmp(blockParameters(selected).Value, '0'), ...
        'PhaseE:OutputSamplingBinding', 'Expected the exact root Outport continuous sampling override.');
    record.configured_output_sampling{end+1} = struct('port', output.port, 'block_path', ...
        blockParameters(selected).BlockPath, 'sample_time', blockParameters(selected).Value); %#ok<AGROW>
end
% This only belongs to the fixed independent negative qualification case.
if strcmp(mode, 'probe') && strcmp(item.expectation, 'error')
    in = setBlockParameter(in, [model '/Forcing'], 'Gain', 'phase_e_missing_runtime_variable');
end
rng(spec.seed, 'twister');
checkpoint(record);
out = sim(in);
assert(isa(out, 'Simulink.SimulationOutput'), 'PhaseE:OutputClass', 'Expected native SimulationOutput.');
record.simulation_returned = true;
record.raw_mat_file = [record.case_id '-returned.mat'];
simulation_output = out;
run_id = identity;
save(fullfile(directory, record.raw_mat_file), 'simulation_output', 'run_id', '-v7');
checkpoint(record);
record.error_message = out.ErrorMessage;
metadata = out.SimulationMetadata;
modelInfo = metadata.ModelInfo;
executionInfo = metadata.ExecutionInfo;
record.stop_event = char(findMetadataField(executionInfo, {'StopEvent'}));
if any(strcmp(who(out), 'tout'))
    savedTime = get(out, 'tout');
    assert(isa(savedTime, 'double') && isreal(savedTime) && (isempty(savedTime) || isvector(savedTime)), ...
        'PhaseE:SavedTimeClass', 'Expected the native numeric saved-time vector.');
    savedTime = savedTime(:);
    record.saved_time = num2cell(savedTime');
    if ~isempty(savedTime) && isfinite(savedTime(end)), record.stop_event_time = savedTime(end); end
end
record.warnings = diagnosticRecords(findMetadataField(executionInfo, {'WarningDiagnostics'}));
record.errors = diagnosticRecords(findMetadataField(executionInfo, {'ErrorDiagnostic'}));
solverInfo = findMetadataField(modelInfo, {'SolverInfo'});
if isstruct(solverInfo)
    record.observed_solver_info = solverInfo;
end
record.observed_solver_name = char(findMetadataField(record.observed_solver_info, {'SolverName','Solver'}));
record.effective_configuration = struct('StartTime', findMetadataField(modelInfo, {'StartTime'}), ...
    'StopTime', findMetadataField(modelInfo, {'StopTime'}), 'SimulationMode', findMetadataField(modelInfo, {'SimulationMode'}), ...
    'Solver', record.observed_solver_name);
checkpoint(record);
record.after_parameters = parameterSnapshot(model, spec.parameters);
record.after_output_sampling = outputSamplingSnapshot(spec.outputs);
record.configuration_restored = isequaln(beforeConfig, configurationSnapshot(model));
record.parameters_restored = isequaln(record.before_parameters, record.after_parameters);
record.output_sampling_restored = isequaln(record.before_output_sampling, record.after_output_sampling);
record = exportOutputs(out, spec, directory, identity, record);
checkpoint(record);
close_system(model, 0);
record.closed_without_save = ~bdIsLoaded(model);
load_system(ownedPath);
assertSurface(model, item.build_spec);
record.reopened = bdIsLoaded(model);
record.reopened_parameters = parameterSnapshot(model, spec.parameters);
record.reopened_output_sampling = outputSamplingSnapshot(spec.outputs);
record.configuration_restored = record.configuration_restored && isequaln(beforeConfig, configurationSnapshot(model));
record.parameters_restored = record.parameters_restored && isequaln(record.before_parameters, record.reopened_parameters);
record.output_sampling_restored = record.output_sampling_restored && isequaln(record.before_output_sampling, record.reopened_output_sampling);
record.source_unchanged = isequal(sourceBytes, fileBytes(sourcePath));
record.owned_model_unchanged = isequal(ownedBytes, fileBytes(ownedPath));
record.completed = true;
clear modelCleanup
end

function record = exportOutputs(out, spec, directory, identity, record)
record.mat_file = [record.case_id '-output.mat'];
record.data_file = [record.case_id '-outputs.json'];
simulation_output = out;
run_id = identity;
output_ports = zeros(0,1);
output_variables = cell(0,1);
output_units = cell(0,1);
output_times = cell(0,1);
output_values = cell(0,1);
saved_time = cell2mat(record.saved_time(:));
if any(strcmp(who(out), 'yout'))
    yout = get(out, 'yout');
    assert(isa(yout, 'Simulink.SimulationData.Dataset'), 'PhaseE:DatasetOutput', 'Expected Dataset root outputs.');
    record.output_count = numElements(yout);
    if record.output_count == numel(spec.outputs)
        [~, order] = sort([spec.outputs.port]);
        for index = 1:record.output_count
            mapping = spec.outputs(order(index));
            signal = getElement(yout, index);
            values = signal.Values;
            assert(isa(values, 'timeseries') && isa(values.Data, 'double') && isreal(values.Data) && isvector(values.Data), ...
                'PhaseE:ScalarOutput', 'Only scalar real numeric timeseries are supported.');
            time = double(values.Time(:));
            data = double(values.Data(:));
            assert(numel(time) == numel(data), 'PhaseE:TimeShape', 'Time and data lengths differ.');
            csvFile = sprintf('%s-output-%d.csv', record.case_id, mapping.port);
            writeCsv(fullfile(directory, csvFile), time, data);
            item = struct('port', mapping.port, 'block_path', mapping.block_path, 'variable_id', mapping.variable_id, ...
                'unit', mapping.unit, 'sample_time', mapping.sample_time, 'observed_unit', values.DataInfo.Units, 'time', {num2cell(time')}, ...
                'values', {num2cell(data')}, 'csv_file', csvFile);
            record.outputs{end+1} = item; %#ok<AGROW>
            output_ports(index,1) = mapping.port;
            output_variables{index,1} = mapping.variable_id;
            output_units{index,1} = mapping.unit;
            output_times{index,1} = time;
            output_values{index,1} = data;
        end
    else
        record.output_boundary_error = 'Native Dataset output count differs from declared required ports.';
    end
end
if record.output_count == 0, record.output_boundary_error = 'No required root-Outport output is available.'; end
save(fullfile(directory, record.mat_file), 'simulation_output', 'run_id', 'output_ports', ...
    'output_variables', 'output_units', 'output_times', 'output_values', 'saved_time', '-v7');
% Check native MAT reload too; Python independently checks numeric fields.
loaded = load(fullfile(directory, record.mat_file), 'run_id', 'output_ports', 'output_variables', 'output_units', 'output_times', 'output_values');
assert(isequal(loaded.run_id, run_id) && isequaln(loaded.output_times, output_times) && isequaln(loaded.output_values, output_values), ...
    'PhaseE:MATRoundTrip', 'Native MAT output readback differs.');
writeJson(fullfile(directory, record.data_file), struct('schema_version',1,'run_id',identity,'outputs',{record.outputs}));
end

function buildFixture(spec, modelPath)
% Private controlled synthetic qualification only, never a user-model constructor.
model = spec.model_name;
assert(~bdIsLoaded(model) && ~isfile(modelPath), 'PhaseE:ExistingFixture', 'Fixture would overwrite a model.');
if ~isfolder(fileparts(modelPath)), mkdir(fileparts(modelPath)); end
wasLoaded = bdIsLoaded('simulink');
load_system('simulink');
libraryCleanup = onCleanup(@() closeOwnedLibrary(wasLoaded));
new_system(model, 'Model', 'ErrorIfShadowed');
modelCleanup = onCleanup(@() closeOwnedModel(model));
workspace = get_param(model, 'ModelWorkspace');
workspace.DataSource = 'Model File';
for index = 1:numel(spec.parameters)
    item = spec.parameters(index);
    % Deliberately different baseline makes Workspace=model overrides observable.
    parameter = Simulink.Parameter(item.value - 0.25);
    parameter.DataType = 'double';
    if ~isempty(item.unit), parameter.Unit = item.unit; end
    assignin(workspace, item.code_name, parameter);
end
sources = struct('Inport','simulink/Sources/In1','Outport','simulink/Sinks/Out1', ...
    'Constant','simulink/Sources/Constant','Gain','simulink/Math Operations/Gain', ...
    'Sum','simulink/Math Operations/Sum','Integrator','simulink/Continuous/Integrator');
for index = 1:numel(spec.blocks)
    item = spec.blocks(index);
    add_block(sources.(item.type), item.path);
    names = fieldnames(item.parameters);
    for parameterIndex = 1:numel(names)
        set_param(item.path, names{parameterIndex}, item.parameters.(names{parameterIndex}));
    end
end
for index = 1:numel(spec.connections)
    item = spec.connections(index);
    add_line(model, [item.source.block_id '/' num2str(item.source.port)], ...
        [item.destination.block_id '/' num2str(item.destination.port)], 'autorouting', 'on');
end
set_param(model, 'SimulationCommand', 'update');
save_system(model, modelPath);
close_system(model, 0);
clear modelCleanup libraryCleanup
end

function assertSurface(model, spec)
callbackNames = {'PreLoadFcn','PostLoadFcn','InitFcn','StartFcn','StopFcn','PreSaveFcn','PostSaveFcn','CloseFcn'};
for index = 1:numel(callbackNames)
    assert(isempty(get_param(model, callbackNames{index})), 'PhaseE:Callback', 'Custom callbacks are outside the controlled surface.');
end
paths = find_system(model, 'SearchDepth', 1, 'Type', 'block');
assert(numel(paths) == numel(spec.blocks), 'PhaseE:BlockSet', 'Actual flat block count differs.');
for index = 1:numel(spec.blocks)
    item = spec.blocks(index);
    assert(any(strcmp(paths, item.path)) && strcmp(get_param(item.path, 'BlockType'), item.type) ...
        && strcmp(get_param(item.path, 'Mask'), 'off'), 'PhaseE:BlockSurface', 'Actual block path/type/mask differs.');
    names = fieldnames(item.parameters);
    for parameterIndex = 1:numel(names)
        assert(strcmp(get_param(item.path, names{parameterIndex}), item.parameters.(names{parameterIndex})), ...
            'PhaseE:BlockParameter', 'Actual block parameters differ from reviewed implementation.');
    end
end
workspace = get_param(model, 'ModelWorkspace');
assert(strcmp(workspace.DataSource, 'Model File'), 'PhaseE:Workspace', 'Only Model File workspace is supported.');
assert(numel(whos(workspace)) == numel(spec.parameters), 'PhaseE:ParameterSet', 'Actual workspace variable set differs.');
end

function snapshot = configurationSnapshot(model)
names = {'Solver','SolverType','MaxStep','MinStep','InitialStep','RelTol','AbsTol','FixedStep', ...
    'ZeroCrossControl','StartTime','StopTime','SimulationMode','SaveOutput','OutputSaveName', ...
    'SaveFormat','DatasetSignalFormat','SaveTime','TimeSaveName','SaveState','SignalLogging', ...
    'LoadExternalInput','ExternalInput','LimitDataPoints','Decimation'};
snapshot = struct();
for index = 1:numel(names), snapshot.(names{index}) = get_param(model, names{index}); end
end

function records = parameterSnapshot(model, parameters)
workspace = get_param(model, 'ModelWorkspace');
records = {};
for index = 1:numel(parameters)
    name = parameters(index).code_name;
    records{end+1} = parameterRecord(name, getVariable(workspace, name)); %#ok<AGROW>
end
end

function record = parameterRecord(name, parameter)
assert(isa(parameter, 'Simulink.Parameter'), 'PhaseE:ParameterClass', 'Expected a registered parameter object.');
record = struct('code_name',name,'value',parameter.Value,'unit',parameter.Unit,'class',class(parameter));
end

function records = outputSamplingSnapshot(outputs)
records = {};
for index = 1:numel(outputs)
    output = outputs(index);
    assert(strcmp(get_param(output.block_path, 'BlockType'), 'Outport'), ...
        'PhaseE:OutputSamplingSurface', 'Sampling readback requires the exact root Outport.');
    records{end+1} = struct('port', output.port, 'block_path', output.block_path, ...
        'sample_time', get_param(output.block_path, 'SampleTime')); %#ok<AGROW>
end
end

function records = diagnosticRecords(items)
records = {};
for index = 1:numel(items)
    item = items(index);
    diagnostic = item.Diagnostic;
    record = struct('phase', item.SimulationPhase, 'time', item.SimulationTime, ...
        'class', class(diagnostic), 'identifier', '', 'message', '');
    for name = {'identifier','Identifier','ID'}
        if isprop(diagnostic, name{1}), record.identifier = char(diagnostic.(name{1})); break; end
    end
    for name = {'message','Message'}
        if isprop(diagnostic, name{1}), record.message = char(diagnostic.(name{1})); break; end
    end
    records{end+1} = record; %#ok<AGROW>
end
end

function value = findMetadataField(info, names)
value = '';
if ~isstruct(info), return; end
fields = fieldnames(info);
for index = 1:numel(names)
    match = find(strcmpi(fields, names{index}),1);
    if ~isempty(match), value = info.(fields{match}); return; end
end
end

function bytes = fileBytes(path)
file = fopen(path, 'rb');
assert(file ~= -1, 'PhaseE:ReadBytes', 'Cannot read model bytes.');
cleanup = onCleanup(@() fclose(file));
bytes = fread(file, Inf, '*uint8');
end

function writeCsv(path, time, data)
file = fopen(path, 'w', 'n', 'UTF-8');
assert(file ~= -1, 'PhaseE:CSVWrite', 'Cannot write numeric CSV output.');
cleanup = onCleanup(@() fclose(file));
fprintf(file, '%.17g,%.17g\n', [time data]');
end

function value = numtext(number)
value = sprintf('%.17g', number);
end

function value = nullableSolver(solver)
% jsondecode(null) is []; explicit NaN emits JSON null for declared n/a fields.
value = solver;
names = {'max_step','min_step','initial_step','rel_tol','abs_tol','fixed_step'};
for index = 1:numel(names)
    if isempty(value.(names{index})), value.(names{index}) = NaN; end
end
end

function closeOwnedModel(model)
if bdIsLoaded(model), close_system(model, 0); end
end

function closeOwnedLibrary(wasLoaded)
if ~wasLoaded && bdIsLoaded('simulink'), close_system('simulink', 0); end
end

function records = jsonRecords(items)
records = cell(1,numel(items));
for index = 1:numel(items), records{index} = items(index); end
end

function record = exceptionRecord(exception)
record = struct('identifier', exception.identifier, 'message', exception.message, ...
    'report', getReport(exception, 'extended', 'hyperlinks', 'off'), 'stack', {jsonRecords(exception.stack)});
end

function value = utcNow()
value = char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSSSSS''Z'''));
end

function writeJson(path, value)
file = fopen(path, 'w', 'n', 'UTF-8');
assert(file ~= -1, 'PhaseE:WriteReport', 'Cannot write native simulation evidence.');
cleanup = onCleanup(@() fclose(file));
fprintf(file, '%s\n', jsonencode(value, 'PrettyPrint', true));
end
