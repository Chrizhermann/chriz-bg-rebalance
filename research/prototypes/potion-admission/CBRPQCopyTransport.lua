-- Inert post-CopyFromBase provenance observation. No automatic loader.
-- BG2EE2.7.3.0 / EEex1.3.0 only; does not propagate ownership itself.
local M = {}
M.expectedExecutableSha256 = "b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57"
-- Keep EEex's existing OnCopy call hook at 1DCB20..1DCB24 untouched. Guard the
-- source/destination frame, completed base-field copy and Decode caller return.
local guards = {
    {"frameAndArguments", 0x1DCAF0,
        "48895C24184889742420574883EC30488B05D27E48004833C44889442428488BF2488BF94C8BC24883C108488D542420"},
    {"baseCopyAndReturn", 0x1DCB25,
        "8B46084C8D4628894710488D5424208B460C488D4F308947148B46108947188B461489471C8B46188947208B461C8947248B46208947280F" ..
        "B746246689472C0FB746266689472EE80F2D2200488D4F30E8B63422008B46304C8D4668894738488D5424208B4634488D4F7089473C8B46" ..
        "388947408B463C8947448B46408947488B464489474C8B86C80000008987D00000008B464C8947548B46508947588B465489475C8B465889" ..
        "47608B465C8947648B46608947688B466489476CE89A2C2200488D4F70E8413422004C8D4670488D542420488D4F78E87F2C2200488D4F78" ..
        "E8263422008B46784C8D868C0000008987800000008B467C8987840000008B86800000008987880000008B868400000089878C0000008B86" ..
        "88000000898790000000488D8F94000000488D542420E8282C22008B869400000089879C0000008B86980000008987A00000008B869C0000" ..
        "008987A40000000F1086A00000000F1187A80000000F108EB00000000F118FB80000008B86C00000008987C80000008B86C40000008987CC" ..
        "000000488B4C24284833CCE8E3AA3100488B5C2450488B7424584883C4305FC3"},
    {"decodeCall", 0x1E2DA3,
        "488BD7488BC8488BD8E83F9DFFFF488BC3"},
}
local capabilities = {"EEex_GetImageBase", "EEex_ReadU8", "EEex_GenLuaCall", "EEex_FlattenTable",
    "EEex_HookBeforeRestoreWithLabels", "EEex_DisableCodeProtection", "EEex_EnableCodeProtection"}

function M.validate(api, config, watchdog)
    assert(not M.installed and not M.failed, "copy transport: already attempted; restart required")
    assert(type(api.EEex_HookIntegrityWatchdog_Load) == "boolean", "watchdog state unavailable")
    if api.EEex_HookIntegrityWatchdog_Load then
        assert(type(watchdog) == "table" and type(watchdog.validate) == "function"
            and type(watchdog.withPreservation) == "function", "watchdog preservation helper required")
        watchdog.validate(api)
    end
    for _, key in ipairs(capabilities) do
        assert(type(api[key]) == "function", "copy transport: missing API " .. key)
    end
    assert(type(config) == "table" and type(config.callbacks) == "table", "copy callbacks required")
    local names = {}
    for _, key in ipairs({"copied"}) do
        local name = config.callbacks[key]
        assert(type(name) == "string" and name:match("^[%a_][%w_]*$"), "invalid copy callback " .. key)
        assert(type(api[name]) == "function", "copy callback must exist: " .. name)
        names[key] = name
    end
    local base = api.EEex_GetImageBase()
    assert(type(base) == "number" and base > 0 and base == math.floor(base), "invalid image base")
    for _, guard in ipairs(guards) do
        local address, hex = base + guard[2], guard[3]
        for i=1,#hex,2 do
            assert(api.EEex_ReadU8(address+(i-1)/2) == tonumber(hex:sub(i,i+1),16),
                "copy transport: unsupported/previously patched site " .. guard[1])
        end
    end
    return {base=base, sites={copied=base+0x1DCCB0}, callbacks=names}
end

local save = [[
    pushfq
    push rax
    push rcx
    push rdx
    push r8
    push r9
    push r10
    push r11
    sub rsp, 60h
    movdqu xmmword ptr ss:[rsp+00h], xmm0
    movdqu xmmword ptr ss:[rsp+10h], xmm1
    movdqu xmmword ptr ss:[rsp+20h], xmm2
    movdqu xmmword ptr ss:[rsp+30h], xmm3
    movdqu xmmword ptr ss:[rsp+40h], xmm4
    movdqu xmmword ptr ss:[rsp+50h], xmm5
    #STACK_MOD(160)
]]
local restore = [[
    #DESTROY_SHADOW_SPACE
    movdqu xmm0, xmmword ptr ss:[rsp+00h]
    movdqu xmm1, xmmword ptr ss:[rsp+10h]
    movdqu xmm2, xmmword ptr ss:[rsp+20h]
    movdqu xmm3, xmmword ptr ss:[rsp+30h]
    movdqu xmm4, xmmword ptr ss:[rsp+40h]
    movdqu xmm5, xmmword ptr ss:[rsp+50h]
    add rsp, 60h
    pop r11
    pop r10
    pop r9
    pop r8
    pop rdx
    pop rcx
    pop rax
    popfq
    #STACK_MOD(-160)
]]
local function reg(register, userType)
    return function(offset)
        return {"mov qword ptr ss:[rsp+#$(1)], " .. register .. " #ENDL", {offset}}, userType
    end
end
local function calculated(instruction)
    return function(offset)
        return {instruction .. " #ENDL mov qword ptr ss:[rsp+#$(1)], rax #ENDL", {offset}}
    end
end

local function callback(api, name, key, args)
    local suffix = "_cbrpq_copy_" .. key
    return api.EEex_FlattenTable({{save}, api.EEex_GenLuaCall(name, {args=args, labelSuffix=suffix}),
        {"call_error" .. suffix .. ": #ENDL", restore}})
end


-- copied(destination CGameEffect userdata, originalNumericPointer)
-- originalNumericPointer is sourceBase-8, NOT proof of a live source. Reader
-- must require its known-live lifetime token and validate both native classes
-- and the proven copied fields. It must not compare/reset class-private tails.
-- All callback results are ignored. Composition owns error containment/reset.
function M.install(api, config, watchdog)
    local v=M.validate(api,config,watchdog)
    local code=api.EEex_FlattenTable({{
        "pushfq #ENDL push rax #ENDL #STACK_MOD(16) #ENDL mov rax, ",v.base+0x1E2DB1,
        " #ENDL cmp qword ptr ss:[rsp+#LAST_FRAME_TOP(72)], rax #ENDL",
        "jz skip_cbrpq_copy #ENDL pop rax #ENDL popfq #ENDL #STACK_MOD(-16) #ENDL"},
        callback(api,v.callbacks.copied,"copied",{
            reg("rdi","CGameEffect"),calculated("lea rax, qword ptr ds:[rsi-8]")}),
        {"jmp finish_cbrpq_copy #ENDL skip_cbrpq_copy: #ENDL #STACK_MOD(16) #ENDL",
         "pop rax #ENDL popfq #ENDL #STACK_MOD(-16) #ENDL finish_cbrpq_copy: #ENDL"}})
    local function write()
        api.EEex_HookBeforeRestoreWithLabels(v.sites.copied,0,5,5,{},code)
    end
    M.failed=true -- No claimed rollback/retry after partial native mutation.
    api.EEex_DisableCodeProtection()
    local ok,err=pcall(function()
        if watchdog then watchdog.withPreservation(api,write) else write() end
    end)
    api.EEex_EnableCodeProtection()
    if not ok then error(err,0) end
    M.installed,M.failed,M.sites=true,false,v.sites
    return v.sites
end

return M
