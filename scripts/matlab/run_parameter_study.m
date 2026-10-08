function run_parameter_study(inputPath)
% Three bounded candidate kernels. No task callbacks, expressions or adoption.
request = jsondecode(fileread(inputPath));
directory = request.output_directory;
cd(directory);
rawPath = fullfile(directory,'raw-parameter-study.json');
report = struct('schema_version',1,'run_id',request.run_id,'channel','matlab_batch', ...
    'host_fingerprint',request.host_fingerprint,'source_identity',request.source_identity, ...
    'input_identity',request.input_identity,'status','running','started_at',utcNow(), ...
    'finished_at','','runtime',struct('release',['R' version('-release')], ...
    'version',version,'matlabroot',matlabroot,'platform',computer), ...
    'installed_products',{jsonRecords(ver)},'licenses_inuse',{jsonRecords(license('inuse'))}, ...
    'functions',{{}},'operation_diagnostics',{{}},'cases',{{}});
for j=1:numel(request.required_functions)
    name=request.required_functions{j};
    report.functions{end+1}=struct('name',name,'path',which(name)); %#ok<AGROW>
end
for j=1:numel(request.operations)
    operation=request.operations{j};
    [feature,names]=methodSurface(operation);
    fs=cell(1,numel(names));
    for k=1:numel(names), fs{k}=struct('name',names{k},'path',which(names{k})); end
    report.operation_diagnostics{end+1}=struct('operation_id',operation, ...
        'license_test',license('test',feature),'functions',{fs}); %#ok<AGROW>
end
writeJson(rawPath,report);
for index=1:numel(request.cases)
    item=request.cases(index);
    record=emptyRecord(item.case_id,item.native_spec.method);
    report.cases{index}=record;
    lastwarn('');
    try
        record=executeCase(item,directory,request.run_id,record,@checkpoint);
    catch exception
        % checkpoint updates the parent record before exceptions unwind.
        record.status='failed';
        record.candidate_complete=false;
        record.error=getReport(exception,'extended','hyperlinks','off');
        record.error_identifier=exception.identifier;
    end
    [warningMessage,warningIdentifier]=lastwarn;
    if ~isempty(warningMessage)
        record.diagnostics{end+1}=struct('message',warningMessage,'identifier',warningIdentifier);
    end
    record=exportNumeric(record,directory,request.run_id);
    report.cases{index}=record;
    writeJson(rawPath,report);
end
report.licenses_inuse=jsonRecords(license('inuse'));
report.finished_at=utcNow();
report.status='completed';
writeJson(rawPath,report);
fprintf('Actual Phase F candidate evidence preserved: %s\n',rawPath);

    function checkpoint(progress)
        record=progress;
        report.cases{index}=progress;
        writeJson(rawPath,report);
    end
end

function r=emptyRecord(caseId,method)
r=struct('case_id',caseId,'method',method,'status','running','candidate_complete',false, ...
    'error','','error_identifier','','theta',{{}},'train_prediction',{{}},'holdout_prediction',{{}}, ...
    'train_residual',{{}},'holdout_residual',{{}},'objective',{{}},'exitflag',{{}}, ...
    'algorithm','','iterations',0,'func_count',0,'firstorderopt',NaN,'rank',NaN, ...
    'condition_number',NaN,'ledger',{{}},'diagnostics',{{}},'restored',false, ...
    'model_file','','data_file','','mat_file','');
end

function r=executeCase(item,directory,identity,r,checkpoint)
s=item.native_spec;
validateWire(s);
if strcmp(s.method,'identification.arx_111')
    assert(s.budget.max_evaluations>=2,'PhaseF:EvaluationBudget','ARX requires training and fixed-candidate holdout call budget.');
    assert(all(s.train.weights==1) && all(s.holdout.weights==1),'PhaseF:ARXWeights','Only unit-weight ARX supported.');
    X=[s.train.output(1:end-1),s.train.input(1:end-1)];
    r.rank=rank(X); r.condition_number=cond(X);
    checkpoint(r);
    assert(r.rank==2 && r.condition_number<=s.criteria.max_condition_number,'PhaseF:RankDeficient','Training ARX regressors are not sufficiently identified.');
    z=iddata(s.train.output(:),s.train.input(:),s.sample_time);
    options=arxOptions('Focus','prediction','Display','off');
    fitted=arx(z,[1 1 1],options);
    assert(isequal(size(fitted.A),[1 2]) && isequal(size(fitted.B),[1 2]) && fitted.Ts==s.sample_time, ...
        'PhaseF:ARXShape','ARX order/sample time changed.');
    theta=[-fitted.A(2);fitted.B(2)];
    r.theta=vector(theta); r.algorithm='arx_prediction_111';
    [p,e]=arxPrediction(s.train,theta);
    r.train_prediction=vector(p); r.train_residual=vector(e); r.objective=vector(sum(e.^2));
    r.ledger{1}=ledgerCall(1,'train',theta,p,e,sum(e.^2));
    checkpoint(r);
    [p,e]=arxPrediction(s.holdout,theta);
    r.holdout_prediction=vector(p); r.holdout_residual=vector(e);
    r.ledger{2}=ledgerCall(2,'holdout',theta,p,e,sum(e.^2));
    checkpoint(r);
    r.restored=true;
elseif strcmp(s.method,'optimization.quadratic_sqp')
    assert(numel(s.initial)<=2 && all(s.objective.weights>0) && all(s.objective.scales>0), ...
        'PhaseF:Quadratic','Only positive weighted one/two-dimensional quadratic supported.');
    options=optimoptions('fmincon','Algorithm','sqp','Display','off','UseParallel',false, ...
        'MaxIterations',s.budget.max_iterations,'MaxFunctionEvaluations',s.budget.max_evaluations, ...
        'OptimalityTolerance',1e-10,'StepTolerance',1e-12,'ConstraintTolerance',s.criteria.feasibility_tolerance);
    A=s.objective.A;
    if isempty(A), A=zeros(0,numel(s.initial)); else, A=reshape(A,[],numel(s.initial)); end
    [theta,value,flag,output]=fmincon(@quadraticObjective,s.initial(:),A,s.objective.b(:), ...
        [],[],s.lower(:),s.upper(:),[],options);
    r.theta=vector(theta); r.objective=vector(value); r.exitflag=vector(flag);
    r.algorithm=char(output.algorithm); r.iterations=output.iterations; r.func_count=output.funcCount;
    r.firstorderopt=output.firstorderopt; r.restored=true;
    checkpoint(r);
    if flag==0, r.status='budget_exhausted'; checkpoint(r); return; end
    if flag<0
        r.status='nonconverged'; r.error=char(output.message); r.error_identifier='PhaseF:Nonconverged';
        checkpoint(r); return;
    end
    assert(output.funcCount<=s.budget.max_evaluations && output.iterations<=s.budget.max_iterations, ...
        'PhaseF:EvaluationBudget','Optimizer exceeded the reviewed finite budget.');
    assert(all(A*theta-s.objective.b(:)<=s.criteria.feasibility_tolerance), ...
        'PhaseF:Infeasible','Returned quadratic candidate violates linear constraints.');
elseif strcmp(s.method,'calibration.simulink_gain')
    assert(numel(s.initial)==1 && any(s.train.input~=0),'PhaseF:GainExcitation','Single gain needs nonzero training excitation.');
    suffix=strrep(identity,'-','');
    model=['f_' item.case_id '_' suffix(1:12)];
    assert(~bdIsLoaded(model),'PhaseF:OwnedName','Owned model name already loaded.');
    wasLoaded=bdIsLoaded('simulink');
    libraryCleanup=onCleanup(@() closeLibrary(wasLoaded));
    oldConfig=Simulink.fileGenControl('getConfig');
    fileCleanup=onCleanup(@() Simulink.fileGenControl('setConfig','config',oldConfig));
    Simulink.fileGenControl('set','CacheFolder',fullfile(directory,'cache'), ...
        'CodeGenFolder',fullfile(directory,'codegen'),'createDir',true);
    new_system(model);
    modelCleanup=onCleanup(@() closeModel(model));
    add_block('simulink/Sources/In1',[model '/Input'],'Port','1','SampleTime','0');
    add_block('simulink/Math Operations/Gain',[model '/Gain'],'Gain','trial_k');
    add_block('simulink/Sinks/Out1',[model '/Output'],'Port','1','SampleTime','0');
    add_line(model,'Input/1','Gain/1'); add_line(model,'Gain/1','Output/1');
    workspace=get_param(model,'ModelWorkspace');
    parameter=Simulink.Parameter(s.initial(1));
    assignin(workspace,'trial_k',parameter);
    set_param(model,'SolverType','Fixed-step','Solver','ode4','FixedStep',numtext(s.sample_time));
    baselineParameter=workspace.getVariable('trial_k');
    baselineConfig=configSnapshot(model);
    baselineSampling=get_param([model '/Output'],'SampleTime');
    r.model_file=[model '.slx'];
    save_system(model,fullfile(directory,r.model_file));
    baselineBytes=fileBytes(fullfile(directory,r.model_file));
    checkpoint(r);
    options=optimoptions('lsqnonlin','Algorithm','trust-region-reflective','Display','off','UseParallel',false, ...
        'MaxIterations',max(0,s.budget.max_iterations-1),'MaxFunctionEvaluations',max(1,s.budget.max_evaluations-2), ...
        'FunctionTolerance',1e-12,'StepTolerance',1e-12,'OptimalityTolerance',1e-10);
    [theta,~,~,flag,output]=lsqnonlin(@gainObjective,s.initial(:),s.lower(:),s.upper(:),options);
    r.theta=vector(theta); r.exitflag=vector(flag); r.algorithm=char(output.algorithm);
    r.iterations=output.iterations; r.func_count=output.funcCount; r.firstorderopt=output.firstorderopt;
    checkpoint(r);
    if flag==0
        r.status='budget_exhausted';
    elseif flag<0
        r.status='nonconverged'; r.error=char(output.message); r.error_identifier='PhaseF:Nonconverged';
    else
        assert(output.funcCount<=s.budget.max_evaluations-2 && output.iterations<=s.budget.max_iterations, ...
            'PhaseF:EvaluationBudget','Optimizer exceeded the reviewed finite budget before holdout.');
        [p,e]=gainCall(theta,s.train,'final');
        r.train_prediction=vector(p); r.train_residual=vector(e); r.objective=vector(sum(e.^2));
        [p,e]=gainCall(theta,s.holdout,'holdout');
        r.holdout_prediction=vector(p); r.holdout_residual=vector(e);
    end
    r.restored=isequaln(workspace.getVariable('trial_k'),baselineParameter) && ...
        isequaln(configSnapshot(model),baselineConfig) && strcmp(get_param([model '/Output'],'SampleTime'),baselineSampling) && ...
        isequal(fileBytes(fullfile(directory,r.model_file)),baselineBytes);
    close_system(model,0);
    load_system(fullfile(directory,r.model_file));
    reopened=get_param(model,'ModelWorkspace');
    r.restored=r.restored && isequaln(reopened.getVariable('trial_k'),baselineParameter) && ...
        isequaln(configSnapshot(model),baselineConfig) && strcmp(get_param([model '/Output'],'SampleTime'),baselineSampling);
    clear modelCleanup fileCleanup libraryCleanup
    checkpoint(r);
    if flag<=0, return; end
else
    error('PhaseF:Unsupported','Unsupported candidate method.');
end
if ~isempty(s.train)
    assert(weightedRMSE(cell2mat(r.train_residual(:)),s.train,s.method)<=s.criteria.max_train_rmse, ...
        'PhaseF:TrainingCriterion','Training criterion failed.');
    assert(weightedRMSE(cell2mat(r.holdout_residual(:)),s.holdout,s.method)<=s.criteria.max_holdout_rmse, ...
        'PhaseF:HoldoutCriterion','Fixed-candidate holdout criterion failed.');
end
r.status='completed'; r.candidate_complete=true;
checkpoint(r);

    function value=quadraticObjective(theta)
        if numel(r.ledger)>=s.budget.max_evaluations
            call=ledgerCall(numel(r.ledger)+1,'train',theta,[],[],[]);
            call.error='Reviewed objective evaluation budget exhausted before this call.';
            call.error_identifier='PhaseF:EvaluationBudget'; r.ledger{end+1}=call; checkpoint(r);
            error('PhaseF:EvaluationBudget','Reviewed objective evaluation budget exhausted.');
        end
        value=sum(s.objective.weights(:).*((theta(:)-s.objective.centers(:))./s.objective.scales(:)).^2);
        r.ledger{end+1}=ledgerCall(numel(r.ledger)+1,'train',theta,[],[],value);
        checkpoint(r);
    end

    function e=gainObjective(theta)
        [~,e]=gainCall(theta,s.train,'train');
    end

    function [p,e]=gainCall(theta,data,phase)
        call=ledgerCall(numel(r.ledger)+1,phase,theta,[],[],[]);
        call.solver=''; call.solver_type=''; call.stop_event=''; call.simulation_file='';
        call.output_time={}; call.saved_time={}; call.parameter_before=baselineParameter.Value;
        call.parameter_after=NaN; call.configuration_restored=false;
        call.requested_solver='ode4'; call.requested_step=s.sample_time;
        try
            limit=s.budget.max_evaluations;
            if strcmp(phase,'train'), limit=limit-2; end
            assert(numel(r.ledger)<limit,'PhaseF:EvaluationBudget','Reviewed actual simulation-call budget exhausted.');
            in=Simulink.SimulationInput(model);
            candidateParameter=Simulink.Parameter(theta(1));
            in=setVariable(in,'trial_k',candidateParameter,'Workspace',model);
            in=setModelParameter(in,'SimulationMode','normal','Solver','ode4','SolverType','Fixed-step', ...
                'FixedStep',numtext(s.sample_time),'StartTime',numtext(data.time(1)), ...
                'StopTime',numtext(data.time(end)),'SaveOutput','on','OutputSaveName','yout', ...
                'SaveFormat','Dataset','DatasetSignalFormat','timeseries','SaveTime','on', ...
                'TimeSaveName','tout','SignalLogging','off','SaveState','off','LimitDataPoints','off', ...
                'Decimation','1','FastRestart','off','CaptureErrors','on','TimeOut',s.budget.simulation_timeout);
            in=setBlockParameter(in,[model '/Output'],'SampleTime','0');
            if ~isempty(item.control) && strcmp(item.control,'invalid_gain_expression')
                in=setBlockParameter(in,[model '/Gain'],'Gain','phase_f_controlled_missing_symbol');
            end
            inputs=Simulink.SimulationData.Dataset;
            signal=timeseries(data.input(:),data.time(:));
            signal=setinterpmethod(signal,'zoh');
            inputs=addElement(inputs,signal,'u');
            in=setExternalInput(in,inputs);
            lastwarn('');
            out=sim(in);
            simulation_output=out;
            call.simulation_file=sprintf('%s-call-%d-simulation.mat',item.case_id,call.sequence);
            save(fullfile(directory,call.simulation_file),'simulation_output','-v7');
            execution=out.SimulationMetadata.ExecutionInfo;
            info=out.SimulationMetadata.ModelInfo.SolverInfo;
            call.solver=char(publicField(info,{'SolverName','Solver'}));
            call.solver_type=char(publicField(info,{'Type','SolverType'}));
            call.stop_event=char(publicField(execution,{'StopEvent'}));
            assert(isempty(out.ErrorMessage),'PhaseF:SimulationError','%s',out.ErrorMessage);
            assert(strcmp(call.stop_event,'ReachedStopTime'),'PhaseF:EarlyStop','Trial simulation stopped early.');
            yout=out.get('yout'); signal=getElement(yout,1); values=signal.Values;
            assert(isa(values,'timeseries') && isa(values.Data,'double') && isreal(values.Data), ...
                'PhaseF:OutputClass','Real double timeseries required.');
            t=values.Time(:); p=values.Data(:); saved=out.get('tout'); saved=saved(:);
            call.output_time=vector(t); call.saved_time=vector(saved);
            assert(numel(t)==numel(data.time) && all(abs(t-data.time(:))<=1e-10) && all(isfinite(p)) && ...
                numel(saved)==numel(data.time) && all(abs(saved-data.time(:))<=1e-10), ...
                'PhaseF:OutputCoverage','Native fixed-grid time or output coverage differs.');
            call.parameter_after=workspace.getVariable('trial_k').Value;
            call.configuration_restored=isequaln(configSnapshot(model),baselineConfig) && ...
                isequaln(workspace.getVariable('trial_k'),baselineParameter) && ...
                strcmp(get_param([model '/Output'],'SampleTime'),baselineSampling);
            e=sqrt(data.weights(:)).*(p-data.output(:));
            call.prediction=vector(p); call.residual=vector(e); call.objective=sum(e.^2);
            diagnostics=publicField(execution,{'WarningDiagnostics'});
            [message,wid]=lastwarn;
            if ~isempty(diagnostics) || ~isempty(message)
                r.diagnostics{end+1}=struct('message',message,'identifier',wid,'native',diagnostics);
                assert(~strcmp(s.warning_policy,'reject'),'PhaseF:Warnings','Trial warning policy rejected diagnostics.');
            end
            r.ledger{end+1}=call; checkpoint(r);
        catch exception
            call.error=getReport(exception,'extended','hyperlinks','off');
            call.error_identifier=exception.identifier;
            r.ledger{end+1}=call; checkpoint(r);
            rethrow(exception);
        end
    end
end

function validateWire(s)
assert(any(strcmp(s.method,{'identification.arx_111','calibration.simulink_gain','optimization.quadratic_sqp'})), ...
    'PhaseF:Method','Unsupported method.');
if ~strcmp(s.method,'identification.arx_111')
    assert(all(isfinite(s.initial)) && all(isfinite(s.lower)) && all(isfinite(s.upper)) && ...
        all(s.lower<s.upper) && all(s.initial>=s.lower) && all(s.initial<=s.upper), ...
        'PhaseF:Bounds','Finite reviewed bounds/initialization required.');
end
assert(s.budget.max_iterations>=0 && s.budget.max_evaluations>=1,'PhaseF:Budget','Finite nonnegative iteration and positive call budgets required.');
if ~strcmp(s.method,'optimization.quadratic_sqp')
    splits={s.train,s.holdout};
    for j=1:2
        d=splits{j};
        assert(all(isfinite(d.time)) && all(isfinite(d.input)) && all(isfinite(d.output)) && ...
            all(isfinite(d.weights)) && all(d.weights>0) && numel(d.input)==numel(d.output) && ...
            all(abs(diff(d.time)-s.sample_time)<=max(1e-12,abs(s.sample_time)*1e-9)), ...
            'PhaseF:TimeGrid','Finite uniform matching observations required.');
    end
end
end

function call=ledgerCall(sequence,phase,theta,p,r,value)
if isempty(value), value=NaN; end
call=struct('sequence',sequence,'phase',phase,'theta',{vector(theta)}, ...
    'prediction',{vector(p)},'residual',{vector(r)},'objective',value,'error','','error_identifier','');
end

function [p,e]=arxPrediction(d,theta)
p=theta(1)*d.output(1:end-1)+theta(2)*d.input(1:end-1);
e=p-d.output(2:end);
end

function value=weightedRMSE(e,d,method)
offset=0;
if strcmp(method,'identification.arx_111'), offset=1; end
value=sqrt(sum(e.^2)/sum(d.weights(offset+1:end)));
end

function r=exportNumeric(r,directory,identity)
names={'theta','train_prediction','holdout_prediction','train_residual','holdout_residual','objective','exitflag'};
data=struct('schema_version',1,'run_id',identity,'case_id',r.case_id);
run_id=identity; case_id=r.case_id; %#ok<NASGU>
numeric=struct;
for j=1:numel(names)
    key=names{j}; values=cell2mat(r.(key)(:)); values=double(values(:));
    numeric.(key)=values;
    data.(key)=vector(values);
end
r.mat_file=[r.case_id '-numeric.mat']; r.data_file=[r.case_id '-numeric.json'];
save(fullfile(directory,r.mat_file),'-struct','numeric','-v7');
save(fullfile(directory,r.mat_file),'run_id','case_id','-append');
writeJson(fullfile(directory,r.data_file),data);
end

function values=vector(value)
values=num2cell(double(value(:))');
end

function values=jsonRecords(items)
values=cell(1,numel(items));
for j=1:numel(items), values{j}=items(j); end
end

function value=publicField(record,names)
value=[];
for j=1:numel(names)
    name=names{j};
    if isstruct(record) && isfield(record,name) || isobject(record) && isprop(record,name)
        value=record.(name); return;
    end
end
end

function [feature,names]=methodSurface(method)
if strcmp(method,'identification.arx_111')
    feature='Identification_Toolbox'; names={'iddata','arx','arxOptions'};
elseif strcmp(method,'calibration.simulink_gain')
    feature='Optimization_Toolbox';
    names={'lsqnonlin','optimoptions','Simulink.SimulationInput','Simulink.SimulationData.Dataset', ...
        'Simulink.Parameter','timeseries','sim','new_system','add_block','add_line','set_param', ...
        'get_param','close_system','bdIsLoaded','Simulink.fileGenControl','save_system','load_system'};
else
    feature='Optimization_Toolbox'; names={'fmincon','optimoptions'};
end
end

function value=configSnapshot(model)
names={'Solver','SolverType','FixedStep','StartTime','StopTime'};
value=struct;
for j=1:numel(names), value.(names{j})=get_param(model,names{j}); end
end

function bytes=fileBytes(path)
file=fopen(path,'rb'); assert(file~=-1,'PhaseF:ReadBytes','Cannot read owned model.');
cleanup=onCleanup(@() fclose(file)); bytes=fread(file,Inf,'*uint8');
end

function closeModel(model)
if bdIsLoaded(model), close_system(model,0); end
end

function closeLibrary(wasLoaded)
if ~wasLoaded && bdIsLoaded('simulink'), close_system('simulink',0); end
end

function value=numtext(number)
value=sprintf('%.17g',number);
end

function value=utcNow()
value=char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSSSSS''Z'''));
end

function writeJson(path,value)
file=fopen(path,'w','n','UTF-8'); assert(file~=-1,'PhaseF:WriteReport','Cannot preserve F evidence.');
cleanup=onCleanup(@() fclose(file)); fprintf(file,'%s\n',jsonencode(value,'PrettyPrint',true));
end
