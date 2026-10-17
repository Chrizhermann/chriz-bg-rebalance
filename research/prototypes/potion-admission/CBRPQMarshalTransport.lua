-- Inert observer of native CGameEffectList::Marshal context. No automatic loader.
-- BG2EE2.7.3.0 / EEex1.3.0 only; does not replace serialization or save handlers.
local M = {}
M.expectedExecutableSha256 = "b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57"
-- These ranges pin the native frame, filters, copy loop, and sole normal return.
-- The two existing EEex patches at 1E5384..1E5389 and 1E538D..1E5391 are excluded.
-- Their collector/writer provenance remains a composition precondition; this
-- observer does not authenticate arbitrary third-party code in those slots.
local guards = {
    {"entryAndFilters", 0x1E50E0,
        "405356574154415541564881EC88010000488B05E0F847004833C44889842470010000488BF9458BE1488D4C2460410FB6D84C8BEAE87691" ..
        "FBFF8B47184533F684DB0F85CD0100004889AC24D00100008D2C40C1E5044C89BC2480010000448BBC24E00100004585FF7437488B570845" ..
        "8BC64885D27424660F1F840000000000488B4210418D4801488B1283782402410F44C8448BC14885D275E5438D2C40C1E5044585E4743B48" ..
        "8B5708458BC64885D274280F1F4000660F1F840000000000488B4210418D4801488B1283782409410F45C8448BC14885D275E5438D2C40C1" ..
        "E50485ED0F8E100100004863CDE8F2253100488B7F084C8BF04885FF0F84F8000000488BF06666660F1F840000000000488B5F10488B3F45" ..
        "85E4740A837B24090F85CB0000004585FF740A837B24020F84BC0000000FB74310488D5424346689442420488D4C24500FB6431888442423" ..
        "0FB64314884424228B431C894424248B4320894424280FB74324668944242C8B43288944242E0FB6432C884424320FB6432E88442433488B" ..
        "43304889442450E8ECAC2100488B03488BCBFF504085C0740C8B43388944243C8B433CEB0A8B43588944243C8B43540F1044242089442440" ..
        "8B4340894424448B4344894424488B43488944244C0F11060F104C24300F114E100F104424400F1146204881C6080100004885FF0F8516FF" ..
        "FFFF4D8975008BC54C8BBC2480010000488BAC24D0010000E95F0100008BB424E001000069D80801000085F6743C488B5708458BC64885D2" ..
        "74290F1F400066660F1F840000000000488B4210418D4801488B1283782402410F44C8448BC14885D275E54169D8080100004585E4743B48" ..
        "8B5708458BC64885D274280F1F4000660F1F840000000000488B4210418D4801488B1283782409410F45C8448BC14885D275E54169D80801" ..
        "000085DB"},
    {"allocationArgument", 0x1E538A,
        "4863CB"},
    {"copyAndReturn", 0x1E5392,
        "4C8B47084C8BD04D85C00F84AC0000004C8BC86666660F1F840000000000498B50104D8B004885D2488D4208490F44C64585E47406837A24" ..
        "09757385F67406837A24027469498BD1B90200000090488D92800000000F1000488D80800000000F1142800F1048900F114A900F1040A00F" ..
        "1142A00F1048B00F114AB00F1040C00F1142C00F1048D00F114AD00F1040E00F1142E00F1048F00F114AF04883E90175AD488B084981C108" ..
        "01000048890A4D85C00F8567FFFFFFEB034D8BD64D8955008BC3488B8C24700100004833CCE83C2331004881C488010000415E415D415C5F" ..
        "5E5BC3"},
}
local capabilities = {"EEex_GetImageBase", "EEex_ReadU8", "EEex_GenLuaCall", "EEex_FlattenTable",
    "EEex_HookBeforeRestoreWithLabels", "EEex_DisableCodeProtection", "EEex_EnableCodeProtection"}

function M.validate(api, config, watchdog)
    assert(not M.installed and not M.failed, "marshal transport: already attempted; restart required")
    assert(type(api.EEex_HookIntegrityWatchdog_Load) == "boolean", "watchdog state unavailable")
    if api.EEex_HookIntegrityWatchdog_Load then
        assert(type(watchdog) == "table" and type(watchdog.validate) == "function"
            and type(watchdog.withPreservation) == "function", "watchdog preservation helper required")
        watchdog.validate(api)
    end
    for _, key in ipairs(capabilities) do
        assert(type(api[key]) == "function", "marshal transport: missing API " .. key)
    end
    assert(type(config) == "table" and type(config.callbacks) == "table", "marshal callbacks required")
    local names = {}
    for _, key in ipairs({"enter", "counted", "leave"}) do
        local name = config.callbacks[key]
        assert(type(name) == "string" and name:match("^[%a_][%w_]*$"), "invalid marshal callback " .. key)
        assert(type(api[name]) == "function", "marshal callback must exist: " .. name)
        names[key] = name
    end
    local base = api.EEex_GetImageBase()
    assert(type(base) == "number" and base > 0 and base == math.floor(base), "invalid image base")
    for _, guard in ipairs(guards) do
        local address, hex = base + guard[2], guard[3]
        for i=1,#hex,2 do
            assert(api.EEex_ReadU8(address+(i-1)/2) == tonumber(hex:sub(i,i+1),16),
                "marshal transport: unsupported/previously patched site " .. guard[1])
        end
    end
    return {base=base, sites={enter=base+0x1E50E0, countedNoNine=base+0x1E5342,
        countedNine=base+0x1E537B, leave=base+0x1E5454}, callbacks=names}
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
    local suffix = "_cbrpq_marshal_" .. key
    return api.EEex_FlattenTable({{save}, api.EEex_GenLuaCall(name, {args=args, labelSuffix=suffix}),
        {"call_error" .. suffix .. ": #ENDL", restore}})
end

-- enter(originalEntryRSP, listPtr, versionByte, onlyTiming9DWORD, excludeTiming2DWORD)
-- counted(originalEntryRSP, listPtr, normalBytesDWORD)
-- leave(originalEntryRSP)
-- Values are numeric and preserve original native widths. Version zero selects
-- V1; any nonzero byte selects V2. Both filter DWORDs use nonzero=true natively.
-- List pointers are borrowed, not userdata. Observes all invocations, including
-- unrelated/nested callers; runtime owns its context stack and sentinel policy.
-- Callbacks must be observational and error-contained by the composition layer.
-- Native exceptions/nonlocal exits do not have a leave notification. Reset the
-- observer context on abort; ordinary native paths all share the guarded exit.
-- counted occurs exactly once per ordinary V2 invocation, after the native
-- count is finalized and before stock EEex CalculateExtra; never for V1.
-- It reports native DWORD arithmetic without correcting overflows/corruption.
-- Composition must validate its frame/list, bounds, and multiple-of-108h size.
function M.install(api, config, watchdog)
    local v=M.validate(api,config,watchdog)
    local enter=callback(api,v.callbacks.enter,"enter",{
        calculated("lea rax, qword ptr ss:[rsp+#LAST_FRAME_TOP(160)]"),
        reg("rcx"), calculated("movzx eax, r8b"), calculated("mov eax, r9d"),
        calculated("mov eax, dword ptr ss:[rsp+#LAST_FRAME_TOP(200)]"),
    })
    -- Six native pushes + sub rsp,188h = 1B8h bytes below original entry RSP.
    local leave=callback(api,v.callbacks.leave,"leave",{
        calculated("lea rax, qword ptr ss:[rsp+#LAST_FRAME_TOP(600)]"),
    })
    local function counted(key, amount)
        return callback(api,v.callbacks.counted,key,{
            calculated("lea rax, qword ptr ss:[rsp+#LAST_FRAME_TOP(600)]"),
            reg("rdi"),calculated(amount),
        })
    end
    -- Without onlyTiming9, EBX already holds the final normal byte count at
    -- this branch. Preserve the incoming flags while deciding callback scope.
    local noNine=api.EEex_FlattenTable({{
        "pushfq #ENDL push rax #ENDL #STACK_MOD(16) #ENDL test r12d, r12d #ENDL",
        "jnz skip_cbrpq_marshal_no9 #ENDL pop rax #ENDL popfq #ENDL #STACK_MOD(-16) #ENDL"},
        counted("countedNoNine","mov eax, ebx"),{
        "jmp finish_cbrpq_marshal_no9 #ENDL skip_cbrpq_marshal_no9: #ENDL #STACK_MOD(16) #ENDL",
        "pop rax #ENDL popfq #ENDL #STACK_MOD(-16) #ENDL finish_cbrpq_marshal_no9: #ENDL",
        "#MANUAL_HOOK_EXIT(0) #ENDL test r12d, r12d #ENDL jz ",v.base+0x1E5382,
        " #ENDL jmp ",v.base+0x1E5347," #ENDL"}})
    -- onlyTiming9's count is R8D. Match the exact impending native DWORD IMUL.
    local nine=counted("countedNine","imul eax, r8d, 108h")
    local function write()
        api.EEex_HookBeforeRestoreWithLabels(v.sites.enter,0,6,6,{{"stack_mod",8}},enter)
        api.EEex_HookBeforeRestoreWithLabels(v.sites.countedNoNine,0,0,5,
            {{"manual_hook_integrity_exit",true}},noNine)
        api.EEex_HookBeforeRestoreWithLabels(v.sites.countedNine,0,7,7,{},nine)
        api.EEex_HookBeforeRestoreWithLabels(v.sites.leave,0,8,8,{},leave)
    end
    M.failed=true -- Partial patch failures have no claimed rollback or retry.
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
