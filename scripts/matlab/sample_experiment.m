function sample_experiment(inputPath)
% Actual finite catalog sample_plan only. Never load a project or simulate it.
request=jsondecode(fileread(inputPath));
directory=request.output_directory;
rawPath=fullfile(directory,'raw-sample.json');
report=struct('schema_version',1,'run_id',request.run_id,'channel','matlab_batch', ...
    'host_fingerprint',request.host_fingerprint,'source_identity',request.source_identity, ...
    'input_identity',request.input_identity,'status','running','started_at',utcNow(), ...
    'finished_at','','runtime',struct('release',['R' version('-release')], ...
    'version',version,'matlabroot',matlabroot,'platform',computer), ...
    'producer_file',mfilename('fullpath'),'installed_products',{jsonRecords(ver)}, ...
    'licenses_inuse',{jsonRecords(license('inuse'))},'license_test',license('test','MATLAB'), ...
    'functions',{{}},'cases',{{}});
report.producer_file=[report.producer_file '.m'];
for k=1:numel(request.required_functions)
    name=request.required_functions{k};
    report.functions{end+1}=struct('name',name,'path',which(name)); %#ok<AGROW>
end
writeJson(rawPath,report);
for k=1:numel(request.cases)
    item=request.cases(k);
    record=runCase(item,directory,request.run_id);
    report.cases{k}=record;
    writeJson(rawPath,report);
end
report.licenses_inuse=jsonRecords(license('inuse'));
report.finished_at=utcNow(); report.status='completed';
writeJson(rawPath,report);
fprintf('Actual Phase G sample-plan evidence preserved: %s\n',rawPath);
end

function r=runCase(item,directory,identity)
original=RandStream.getGlobalStream;
restore=[]; originalBefore=[];
ownedOverride=strcmp(item.control,'caller_special') || strcmp(item.control,'caller_special_error');
if ownedOverride
    originalBefore=snapshot(original);
    restore=onCleanup(@()RandStream.setGlobalStream(original));
    special=RandStream('mt19937ar','Seed',2026,'NormalTransform','Polar');
    special.Antithetic=true;
    RandStream.setGlobalStream(special);
elseif strcmp(item.control,'consume_global')
    rand(1,11); % Deliberately consume caller values before the sampler starts.
end
caller=RandStream.getGlobalStream;
r=struct('case_id',item.case_id,'method',item.sampling_spec.method,'status','running', ...
    'error','','error_identifier','','algorithm','','sample_indices',{{}},'uniforms',{{}}, ...
    'input_mat',item.input_mat,'data_file',[item.case_id '-sample.json'], ...
    'mat_file',[item.case_id '-sample.mat'],'matrix_shapes',struct, ...
    'caller_before',snapshot(caller),'caller_after',struct,'caller_unchanged',false, ...
    'caller_handle_unchanged',false, ...
    'owned_override',ownedOverride,'global_before_override',originalBefore, ...
    'global_after_restore',[],'global_handle_restored',false, ...
    'local_before',[],'local_after',[]);
sample_indices=zeros(0,1); uniforms=zeros(0,1);
try
    controlled=[];
    if strcmp(item.control,'uniform_boundary'), controlled=item.uniforms(:); end
    [sample_indices,uniforms,r.local_before,r.local_after,r.algorithm]= ...
        sampleCatalog(item.sampling_spec,fullfile(directory,item.input_mat),controlled);
    r.status='completed';
catch exception
    r.status='failed'; r.error=getReport(exception,'extended','hyperlinks','off');
    r.error_identifier=exception.identifier;
end
r.caller_after=snapshot(RandStream.getGlobalStream);
r.caller_unchanged=isequal(r.caller_before,r.caller_after);
r.caller_handle_unchanged=RandStream.getGlobalStream==caller;
clear restore; % Only an owned qualification override can invoke the global setter.
if ownedOverride
    r.global_after_restore=snapshot(RandStream.getGlobalStream);
    r.global_handle_restored=RandStream.getGlobalStream==original;
end
r.sample_indices=vector(sample_indices); r.uniforms=vector(uniforms);
r.matrix_shapes=struct('sample_indices',{vector(size(sample_indices))}, ...
    'uniforms',{vector(size(uniforms))});
data=struct('schema_version',1,'run_id',identity,'case_id',item.case_id,'method',r.method, ...
    'sample_indices',{r.sample_indices},'uniforms',{r.uniforms},'matrix_shapes',r.matrix_shapes);
save(fullfile(directory,r.mat_file),'sample_indices','uniforms','-v7');
writeJson(fullfile(directory,r.data_file),data);
end

function [indices,uniforms,before,after,algorithm]=sampleCatalog(s,inputMat,controlled)
% This kernel never changes global stream, even on validation failures.
validateWire(s);
numeric=load(inputMat);
expectedNames={'catalog_count';'cdf';'draws';'probabilities';'seed'};
assert(isequal(sort(fieldnames(numeric)),sort(expectedNames)), ...
    'PhaseG:InputMAT','Exact numeric sampling input variable set required.');
p=s.probabilities(:); seed=s.seed(:);
assert(realColumn(numeric.probabilities,numel(p)) && isequal(numeric.probabilities,p) && ...
    realColumn(numeric.seed,numel(seed)) && isequal(numeric.seed,seed) && ...
    realScalar(numeric.draws) && numeric.draws==s.draws && ...
    realScalar(numeric.catalog_count) && numeric.catalog_count==numel(s.catalog_ids), ...
    'PhaseG:InputMAT','Numeric sampling input class, shape or value differs.');
cdf=zeros(numel(p),1);
for j=1:numel(p), cdf(j)=accurateSum(p(1:j)); end
if ~isempty(cdf), cdf(end)=1; end % Floating endpoint only; no normalization.
assert(realColumn(numeric.cdf,numel(cdf)) && isequal(numeric.cdf,cdf), ...
    'PhaseG:InputMAT','Input CDF differs from exact declared probabilities.');
before=[]; after=[];
if ~strcmp(s.method,'monte_carlo_catalog')
    indices=double((1:s.draws)'); uniforms=zeros(0,1); algorithm='catalog_order';
    return;
end
stream=RandStream('mt19937ar','Seed',s.seed);
before=snapshot(stream);
uniforms=rand(stream,s.draws,1); % Explicit n-by-1 actual local stream draw.
algorithm='mt19937ar';
if ~isempty(controlled)
    assert(realColumn(controlled,s.draws) && all(controlled>=0 & controlled<1), ...
        'PhaseG:Uniform','Controlled uniform boundary vector differs.');
    uniforms=controlled; algorithm='controlled_uniform_boundary';
end
indices=selectCatalog(cdf,uniforms);
after=snapshot(stream);
assert(realColumn(indices,s.draws) && realColumn(uniforms,s.draws), ...
    'PhaseG:OutputShape','Actual sample arrays must be real double n-by-1.');
end

function validateWire(s)
fields={'method';'catalog_ids';'draws';'probabilities';'seed'};
assert(isstruct(s) && isscalar(s) && isequal(sort(fieldnames(s)),sort(fields)) && ...
    ischar(s.method) && any(strcmp(s.method,{'scenario_matrix','full_factorial','monte_carlo_catalog'})), ...
    'PhaseG:Surface','Exact supported catalog sampling specification required.');
ids=s.catalog_ids;
assert(iscell(ids) && numel(ids)>=1 && numel(ids)<=16 && ...
    all(cellfun(@(v)ischar(v) && ~isempty(strtrim(v)),ids)) && numel(unique(ids))==numel(ids), ...
    'PhaseG:Catalog','One to sixteen unique ordered catalog IDs required.');
assert(realScalar(s.draws) && s.draws==fix(s.draws) && s.draws>=1 && s.draws<=16, ...
    'PhaseG:Draws','Fixed integer draw count must be in [1,16].');
if ~strcmp(s.method,'monte_carlo_catalog')
    assert(s.draws==numel(ids) && isempty(s.probabilities) && isempty(s.seed), ...
        'PhaseG:Deterministic','Deterministic catalog order requires one draw per member and null probability/seed.');
    return;
end
p=s.probabilities;
assert(isa(p,'double') && isreal(p) && isvector(p) && numel(p)==numel(ids) && ...
    all(isfinite(p)) && all(p>=0) && accurateSum(p)==1, ...
    'PhaseG:Probability','Finite nonnegative categorical probabilities must sum exactly to one.');
assert(realScalar(s.seed) && s.seed==fix(s.seed) && s.seed>=0 && s.seed<2^32, ...
    'PhaseG:Seed','Explicit uint32 seed required.');
end

function indices=selectCatalog(cdf,uniforms)
indices=zeros(numel(uniforms),1);
for j=1:numel(uniforms)
    selected=find(uniforms(j)<cdf,1,'first');
    assert(~isempty(selected),'PhaseG:CDF','No catalog member selected.');
    indices(j)=double(selected); % Never <=; zero-probability endpoints are skipped.
end
end

function total=accurateSum(values)
% Floating expansion summation, including the final half-even correction.
% Nonnegative probabilities have at most sixteen bounded finite terms.
partials=zeros(1,0);
for value=reshape(values,1,[])
    x=value; next=zeros(1,0);
    for y=partials
        if abs(x)<abs(y), old=x; x=y; y=old; end
        high=x+y; low=y-(high-x);
        if low~=0, next(end+1)=low; end %#ok<AGROW>
        x=high;
    end
    partials=[next x]; %#ok<AGROW>
end
total=0; low=0; count=numel(partials);
if count==0, return; end
total=partials(count); count=count-1;
while count>0
    x=total; y=partials(count); count=count-1;
    total=x+y; low=y-(total-x);
    if low~=0, break; end
end
if count>0 && ((low<0 && partials(count)<0) || (low>0 && partials(count)>0))
    y=2*low; corrected=total+y;
    if corrected-total==y, total=corrected; end
end
end

function result=realScalar(value)
result=isa(value,'double') && isreal(value) && isequal(size(value),[1 1]) && isfinite(value);
end

function result=realColumn(value,n)
result=isa(value,'double') && isreal(value) && isequal(size(value),[n 1]) && all(isfinite(value(:)));
end

function value=snapshot(stream)
value=get(stream);
state=value.State;
value.StateClass=class(state); value.StateShape=vector(size(state));
value.State=arrayfun(@(number)sprintf('%u',number),state(:)','UniformOutput',false);
value.Seed=double(value.Seed); value.NumStreams=double(value.NumStreams);
value.StreamIndex=double(value.StreamIndex); value.Substream=double(value.Substream);
value.Antithetic=logical(value.Antithetic); value.FullPrecision=logical(value.FullPrecision);
end

function values=vector(value)
values=num2cell(double(value(:))'); % JSON arrays retain explicit empty/single/many shape.
end

function values=jsonRecords(items)
values=cell(1,numel(items));
for j=1:numel(items), values{j}=items(j); end
end

function value=utcNow()
value=char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSSSSS''Z'''));
end

function writeJson(path,value)
assert(~isfolder(path),'PhaseG:WriteReport','JSON evidence target cannot be a directory.');
encoded=jsonencode(value,'PrettyPrint',true);
bytes=unicode2native([encoded newline],'UTF-8');
temporary=[tempname(fileparts(path)) '.json.tmp'];
file=fopen(temporary,'wb');
assert(file~=-1,'PhaseG:WriteReport','Cannot preserve temporary G evidence.');
try
    written=fwrite(file,bytes,'uint8'); closed=fclose(file);
    assert(written==numel(bytes) && closed==0,'PhaseG:WriteReport','Incomplete G evidence write or close.');
catch exception
    if ismember(file,fopen('all')), fclose(file); end
    rethrow(exception);
end
[moved,message]=movefile(temporary,path,'f');
assert(moved,'PhaseG:WriteReport','Cannot replace G evidence: %s',message);
end
