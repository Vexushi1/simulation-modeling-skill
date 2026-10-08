function probe_implementation(inputPath)
% Controlled R2025b structure building only. No sim/eval/base-workspace parameters.
request = jsondecode(fileread(inputPath));
directory = request.output_directory;
cd(directory); % This isolated batch process owns its output directory.
Simulink.fileGenControl('set', 'CacheFolder', directory, 'CodeGenFolder', directory);
rawPath = fullfile(directory, 'raw-implementation.json');
report = struct('schema_version', 1, 'run_id', request.run_id, 'status', 'running', ...
    'channel', 'matlab_batch', 'host_fingerprint', request.host_fingerprint, ...
    'input_identity', request.input_identity, 'source_identity', request.source_identity, ...
    'started_at', utcNow(), 'finished_at', '', 'simulation_run', false);
report.runtime = struct('release', ['R' version('-release')], 'version', version, ...
    'matlabroot', matlabroot, 'platform', computer);
report.installed_products = jsonRecords(ver);
report.license_test = license('test', 'SIMULINK');
report.licenses_inuse = jsonRecords(license('inuse'));
report.functions = {};
for index = 1:numel(request.required_functions)
    name = request.required_functions{index};
    report.functions{end+1} = struct('name', name, 'path', which(name)); %#ok<AGROW>
end
report.cases = {};
writeJson(rawPath, report);
for index = 1:numel(request.cases)
    requestedCase = request.cases(index);
    record = emptyCase();
    record.case_id = requestedCase.case_id;
    record.attempted = true;
    lastwarn('');
    try
        structure = buildAndInspect(requestedCase.build_spec, request.supported_blocks, directory);
        record.structure_file = [record.case_id '-structure.json'];
        record.model_file = [requestedCase.build_spec.model_name '.slx'];
        writeJson(fullfile(directory, record.structure_file), structure);
        record.call_success = true;
    catch exception
        record.error = struct('identifier', exception.identifier, 'message', exception.message, ...
            'report', getReport(exception, 'extended', 'hyperlinks', 'off'), 'stack', {jsonRecords(exception.stack)});
    end
    [record.warning_message, record.warning_identifier] = lastwarn;
    report.cases{end+1} = record; %#ok<AGROW>
    writeJson(rawPath, report);
end
report.licenses_inuse = jsonRecords(license('inuse'));
report.finished_at = utcNow();
report.status = 'completed';
writeJson(rawPath, report);
fprintf('Phase D structure checks completed without simulation: %s\n', rawPath);
end

function record = emptyCase()
record = struct('case_id', '', 'attempted', false, 'call_success', false, ...
    'structure_file', '', 'model_file', '', 'error', struct(), ...
    'warning_message', '', 'warning_identifier', '');
end

function output = buildAndInspect(spec, supported, directory)
model = spec.model_name;
assert(isvarname(model) && numel(model) <= 63, 'PhaseD:ModelName', 'Invalid controlled model name.');
assert(~bdIsLoaded(model), 'PhaseD:AlreadyLoaded', 'The owned model is already loaded.');
modelPath = fullfile(directory, [model '.slx']);
assert(~isfile(modelPath), 'PhaseD:ExistingModel', 'The output model already exists.');
libraryWasLoaded = bdIsLoaded('simulink');
load_system('simulink');
libraryPath = get_param('simulink', 'FileName');
libraryCleanup = onCleanup(@() closeOwnedLibrary(libraryWasLoaded));
new_system(model, 'Model', 'ErrorIfShadowed');
modelCleanup = onCleanup(@() closeOwnedModel(model));
assertNoCustomCallbacks(model);
workspace = get_param(model, 'ModelWorkspace');
workspace.DataSource = 'Model File';
for index = 1:numel(spec.parameters)
    item = spec.parameters(index);
    assert(isvarname(item.code_name), 'PhaseD:ParameterName', 'Invalid parameter name.');
    assert(isnumeric(item.value) && isscalar(item.value) && isfinite(item.value), ...
        'PhaseD:ParameterValue', 'A finite scalar parameter is required.');
    parameter = Simulink.Parameter(item.value);
    parameter.DataType = 'double';
    if ~isempty(item.unit), parameter.Unit = item.unit; end
    assignin(workspace, item.code_name, parameter);
end
for index = 1:numel(spec.blocks)
    item = spec.blocks(index);
    assert(isvarname(item.id) && strcmp(item.path, [model '/' item.id]), 'PhaseD:BlockPath', 'Only controlled flat block paths are supported.');
    assert(isfield(supported, item.type), 'PhaseD:BlockType', 'Unsupported native block type.');
    source = supported.(item.type).source;
    block = add_block(source, item.path);
    set_param(block, 'Position', [80+120*mod(index-1,4), 60+100*floor((index-1)/4), ...
                                120+120*mod(index-1,4), 90+100*floor((index-1)/4)]);
    names = fieldnames(item.parameters);
    allowed = supported.(item.type).parameters;
    if ischar(allowed), allowed = {allowed}; end
    assert(isequal(sort(names), sort(allowed(:))), 'PhaseD:BlockParameters', 'Unsupported native block parameter.');
    for parameterIndex = 1:numel(names)
        name = names{parameterIndex};
        value = item.parameters.(name);
        assert(ischar(value), 'PhaseD:BlockParameter', 'Expected a prevalidated string.');
        if any(strcmp(name, {'Gain', 'Value'}))
            assert(hasVariable(workspace, value) && isvarname(value), 'PhaseD:ParameterReference', 'Registered model parameter required.');
        elseif strcmp(name, 'InitialCondition')
            assert(~isempty(regexp(value, '^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$', 'once')) ...
                && isfinite(str2double(value)), 'PhaseD:InitialCondition', 'Finite literal initial condition required.');
        elseif strcmp(name, 'Inputs')
            assert(any(strcmp(value, {'++', '+-', '-+', '--'})), 'PhaseD:SumInputs', 'Only explicit two-input signs are allowed.');
        elseif strcmp(name, 'Port')
            assert(~isempty(regexp(value, '^[1-9]\d*$', 'once')), 'PhaseD:PortSetting', 'Positive port setting required.');
        else
            error('PhaseD:BlockParameter', 'Unsupported parameter.');
        end
        set_param(block, name, value);
    end
end
for index = 1:numel(spec.connections)
    connection = spec.connections(index);
    source = endpointBlock(spec, connection.source.block_id);
    destination = endpointBlock(spec, connection.destination.block_id);
    sourcePorts = get_param(source.path, 'PortHandles');
    destinationPorts = get_param(destination.path, 'PortHandles');
    assert(connection.source.port >= 1 && connection.source.port <= numel(sourcePorts.Outport) ...
        && connection.destination.port >= 1 && connection.destination.port <= numel(destinationPorts.Inport), ...
        'PhaseD:InvalidPort', 'Requested port is absent from the actual created core block.');
    add_line(model, sourcePorts.Outport(connection.source.port), destinationPorts.Inport(connection.destination.port), 'autorouting', 'on');
end
set_param(model, 'SimulationCommand', 'update');
save_system(model, modelPath);
close_system(model, 0);
closed = ~bdIsLoaded(model);
load_system(modelPath);
assertNoCustomCallbacks(model);
set_param(model, 'SimulationCommand', 'update');
output = inspectStructure(model, spec, supported, modelPath, libraryPath);
output.updated_before_save = true;
output.saved = isfile(modelPath);
output.closed_before_reload = closed;
output.reopened = bdIsLoaded(model);
output.updated_after_reload = true;
output.simulation_run = false;
clear modelCleanup libraryCleanup
end

function assertNoCustomCallbacks(model)
names = {'PreLoadFcn','PostLoadFcn','InitFcn','StartFcn','StopFcn','PreSaveFcn','PostSaveFcn','CloseFcn'};
for index = 1:numel(names)
    assert(isempty(get_param(model, names{index})), 'PhaseD:CustomCallback', 'Custom model callbacks are outside the controlled baseline.');
end
end

function item = endpointBlock(spec, identity)
indices = find(strcmp({spec.blocks.id}, identity));
assert(numel(indices) == 1, 'PhaseD:Endpoint', 'Endpoint block is unknown or ambiguous.');
item = spec.blocks(indices);
end

function output = inspectStructure(model, spec, supported, modelPath, libraryPath)
workspace = get_param(model, 'ModelWorkspace');
output = struct('schema_version', 1, 'model_name', model, 'diagram_type', get_param(model, 'BlockDiagramType'), ...
    'model_file', get_param(model, 'FileName'), 'library_file', libraryPath, 'model_workspace_source', workspace.DataSource);
assert(strcmp(output.model_file, modelPath), 'PhaseD:SavedPath', 'Reloaded model path differs.');
callbackNames = {'PreLoadFcn','PostLoadFcn','InitFcn','StartFcn','StopFcn','PreSaveFcn','PostSaveFcn','CloseFcn'};
output.callbacks = struct();
for index = 1:numel(callbackNames)
    output.callbacks.(callbackNames{index}) = get_param(model, callbackNames{index});
end
actualPaths = find_system(model, 'SearchDepth', 1, 'Type', 'block');
assert(numel(actualPaths) == numel(spec.blocks), 'PhaseD:BlockSet', 'Actual flat block count differs.');
output.blocks = {};
output.connections = {};
for index = 1:numel(actualPaths)
    path = actualPaths{index};
    identity = get_param(path, 'Name');
    expected = endpointBlock(spec, identity);
    kind = get_param(path, 'BlockType');
    ports = get_param(path, 'PortHandles');
    record = struct('id',identity,'path',path,'type',kind,'source',supported.(expected.type).source, ...
        'parameters',struct(),'ports',struct('inport_count',numel(ports.Inport),'outport_count',numel(ports.Outport)), ...
        'mask',get_param(path,'Mask'),'reference_model','');
    names = fieldnames(expected.parameters);
    for fieldIndex = 1:numel(names)
        record.parameters.(names{fieldIndex}) = get_param(path, names{fieldIndex});
    end
    output.blocks{end+1} = record; %#ok<AGROW>
    for portIndex = 1:numel(ports.Inport)
        line = get_param(ports.Inport(portIndex), 'Line');
        if line == -1, continue; end
        sourcePort = get_param(line, 'SrcPortHandle');
        sourceBlock = get_param(sourcePort, 'Parent');
        sourceIdentity = get_param(sourceBlock, 'Name');
        sourcePorts = get_param(sourceBlock, 'PortHandles');
        sourceIndex = find(sourcePorts.Outport == sourcePort);
        assert(numel(sourceIndex) == 1, 'PhaseD:ReadbackPort', 'Readback source port differs.');
        output.connections{end+1} = struct('source',struct('block_id',sourceIdentity,'port',sourceIndex), ...
            'destination',struct('block_id',identity,'port',portIndex)); %#ok<AGROW>
    end
end
output.parameters = {};
actualVariables = whos(workspace);
assert(numel(actualVariables) == numel(spec.parameters), 'PhaseD:WorkspaceSet', 'Workspace variable set differs.');
for index = 1:numel(actualVariables)
    name = actualVariables(index).name;
    parameter = getVariable(workspace, name);
    assert(isa(parameter, 'Simulink.Parameter'), 'PhaseD:WorkspaceClass', 'Registered parameter object required.');
    output.parameters{end+1} = struct('code_name',name,'value',parameter.Value, ...
        'unit',parameter.Unit,'class',class(parameter)); %#ok<AGROW>
end
end

function records = jsonRecords(items)
% A cell array preserves JSON array shape for zero, one, or many records.
records = cell(1, numel(items));
for index = 1:numel(items), records{index} = items(index); end
end

function closeOwnedModel(model)
if bdIsLoaded(model), close_system(model, 0); end
end

function closeOwnedLibrary(wasLoaded)
if ~wasLoaded && bdIsLoaded('simulink'), close_system('simulink', 0); end
end

function value = utcNow()
value = char(datetime('now', 'TimeZone', 'UTC', 'Format', 'yyyy-MM-dd''T''HH:mm:ss.SSSSSS''Z'''));
end

function writeJson(path, report)
file = fopen(path, 'w', 'n', 'UTF-8');
assert(file ~= -1, 'PhaseD:ReportWrite', 'Cannot write the native report.');
cleanup = onCleanup(@() fclose(file));
fprintf(file, '%s\n', jsonencode(report, 'PrettyPrint', true));
end
