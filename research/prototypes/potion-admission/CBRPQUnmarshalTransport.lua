-- Inert caller context for native/EEex effect-list unmarshal. No automatic loader.
-- BG2EE2.7.3.0 / EEex1.3.0 only; no serializer/handler replacement or ownership work.
local M = {}
M.expectedExecutableSha256 = "b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57"
-- Preserve stock EEex's sprite call wrapper37AA92 and the Unmarshal entry jump.
-- Guard the exact caller arguments and independent before/after observer sites.
-- This does not authenticate foreign changes inside the stock EEex patch slots.
local guards = {
    {"spriteArguments", 0x37AA51,
        "0FB6838B050000B908010000418B9424C402000084C041B830000000410F95C184C044884C24204C8BCB440F45C14903D4450FAF8424C802" ..
        "0000488D8B004A0000"},
    {"spriteLeave", 0x37AA97,
        "0FB7836A050000"},
    {"projectileArgumentsAndCall", 0x22BC74,
        "0FB74710488D4B78668983CE0300004533C90FB74712458BC6668983C6030000488BD50FB6471A8883E0030000C644242001E835CCFBFF"},
    {"projectileLeave", 0x22BCAB,
        "0FB6471B488BB42480000000"},
}
local capabilities = {"EEex_GetImageBase", "EEex_ReadU8", "EEex_GenLuaCall", "EEex_FlattenTable",
    "EEex_HookBeforeRestoreWithLabels", "EEex_DisableCodeProtection", "EEex_EnableCodeProtection"}

function M.validate(api, config, watchdog)
    assert(not M.installed and not M.failed, "unmarshal transport: already attempted; restart required")
    assert(type(api.EEex_HookIntegrityWatchdog_Load) == "boolean", "watchdog state unavailable")
    if api.EEex_HookIntegrityWatchdog_Load then
        assert(type(watchdog) == "table" and type(watchdog.validate) == "function"
            and type(watchdog.withPreservation) == "function", "watchdog preservation helper required")
        watchdog.validate(api)
    end
    for _, key in ipairs(capabilities) do
        assert(type(api[key]) == "function", "unmarshal transport: missing API " .. key)
    end
    assert(type(config) == "table" and type(config.callbacks) == "table", "ununmarshal callbacks required")
    local names = {}
    for _, key in ipairs({"enter", "leave"}) do
        local name = config.callbacks[key]
        assert(type(name) == "string" and name:match("^[%a_][%w_]*$"), "invalid unmarshal callback " .. key)
        assert(type(api[name]) == "function", "unmarshal callback must exist: " .. name)
        names[key] = name
    end
    local base = api.EEex_GetImageBase()
    assert(type(base) == "number" and base > 0 and base == math.floor(base), "invalid image base")
    for _, guard in ipairs(guards) do
        local address, hex = base + guard[2], guard[3]
        for i=1,#hex,2 do
            assert(api.EEex_ReadU8(address+(i-1)/2) == tonumber(hex:sub(i,i+1),16),
                "unmarshal transport: unsupported/previously patched site " .. guard[1])
        end
    end
    return {base=base, sites={spriteEnter=base+0x37AA8B, spriteLeave=base+0x37AA97,
        projectileEnter=base+0x22BCA1, projectileLeave=base+0x22BCAB}, callbacks=names}
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
    local suffix = "_cbrpq_unmarshal_" .. key
    return api.EEex_FlattenTable({{save}, api.EEex_GenLuaCall(name, {args=args, labelSuffix=suffix}),
        {"call_error" .. suffix .. ": #ENDL", restore}})
end


-- enter(callerFrameRSP, listPtr, dataPtr, byteSizeDWORD, spritePtr, versionByte)
-- leave(callerFrameRSP)
-- All values are numeric; a projectile entry carries spritePtr=0, version=1.
-- Frame is the original native CALLER RSP, stable around the existing call and
-- its stock EEex wrapper. Nested/unowned invocations require sentinel contexts.
-- Sprite entry must snapshot/validate the ACTUAL existing list; do not assume
-- its native ClearMarshal path made it empty in the presence of other mods.
-- No userdata/list reading occurs here. Composition owns bounds, lifetime,
-- footer-last validation and failures; callback return values are ignored.
-- After-sprite runs after stock EEex UUID/loaded callbacks too; no dependence on
-- those callbacks firing (they are skipped under bNoUUID). Native exceptions or
-- nonlocal unwinding require reset; only ordinary call return emits leave.
function M.install(api, config, watchdog)
    local v=M.validate(api,config,watchdog)
    local frame=calculated("lea rax, qword ptr ss:[rsp+#LAST_FRAME_TOP(160)]")
    local size=calculated("mov eax, r8d")
    local assembly={
        spriteEnter=callback(api,v.callbacks.enter,"spriteEnter",{
            frame,calculated("lea rax, qword ptr ds:[rbx+4A00h]"),reg("rdx"),size,reg("rbx"),
            calculated("movzx eax, byte ptr ss:[rsp+#LAST_FRAME_TOP(192)]"),
        }),
        spriteLeave=callback(api,v.callbacks.leave,"spriteLeave",{frame}),
        projectileEnter=callback(api,v.callbacks.enter,"projectileEnter",{
            frame,reg("rcx"),reg("rdx"),size,calculated("xor eax, eax"),calculated("mov eax, 1"),
        }),
        projectileLeave=callback(api,v.callbacks.leave,"projectileLeave",{frame}),
    }
    local function write()
        for _,site in ipairs({{"spriteEnter",7},{"spriteLeave",7},{"projectileEnter",5},{"projectileLeave",12}}) do
            api.EEex_HookBeforeRestoreWithLabels(v.sites[site[1]],0,site[2],site[2],{},assembly[site[1]])
        end
    end
    M.failed=true -- Partial native patch failures have no claimed rollback/retry.
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
