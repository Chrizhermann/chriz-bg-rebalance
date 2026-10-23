-- Write the sampler's records to cbr-timestop-output/<ARGS.name>.samples.jsonl and clear them;
-- the sampler keeps its creatures and sources. Refuses an existing file. The first line is a
-- header: the lab, the Time Clocks mod's status and switches, what was tracked, and whether
-- anything was lost (overflow, sampler errors).
assert(type(ARGS) == "table" and type(ARGS.name) == "string" and ARGS.name:match("^[%w_-]+$"),
    "ARGS.name required")
assert(type(CBTCLab) == "table" and CBTCLab.json, "SAMPLER_FIRST")
local S = CBTCLab
local path = "cbr-timestop-output/" .. ARGS.name .. ".samples.jsonl"
local existing = io.open(path, "rb")
if existing then existing:close(); error("EXISTS:" .. path) end
local function read(name)
    local handle = io.open(name, "rb")
    if not handle then return nil end
    local text = handle:read("*a")
    handle:close()
    return text
end
local sources = {}
for resref in pairs(S.sources) do sources[#sources + 1] = resref end
table.sort(sources)
local clocks = CBTC_TimeClocks
local options = {}
if clocks and type(clocks.options) == "table" then
    for key, value in pairs(clocks.options) do
        if type(value) == "boolean" then options[key] = value end
    end
end
local header = {k = "header", lab = read("CBRTSLab.id"), ids = S.ids, sources = sources, records = S.count,
    overflow = S.overflow, errors = S.errors, last_error = S.lastError, frame = Infinity_GetFrameCounter(),
    mod = clocks and {status = clocks.Status, installed = clocks.installed == true, options = options,
        stats = clocks.core and clocks.core.stats} or "not loaded"}
local f = assert(io.open(path, "wb"))
local ok, why = f:write(S.json(header), "\n")
for index = 1, S.count do
    if not ok then break end
    ok, why = f:write(S.records[index], "\n")
end
f:close()
assert(ok, why)
local written, overflow = S.count, S.overflow
S.records, S.count, S.overflow, S.lastKey = {}, 0, false, nil
if overflow then S.active = false end
return {path = path, records = written, overflow = overflow, errors = S.errors, last_error = S.lastError,
    active = S.active}
