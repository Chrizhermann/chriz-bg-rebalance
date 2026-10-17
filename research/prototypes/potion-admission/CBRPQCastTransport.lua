-- Inert, opt-in original op146 mode1 transport preparation. No automatic loader.
-- BG2EE2.7.3.0 / EEex1.3.0 only; no effect/message/native arguments are rewritten.
-- Composition supplies global callbacks and the scoped CBRPQWatchdog helper.
local M = {}
M.expectedExecutableSha256 = "b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57"
local guards = {
    {"parentQueued", 0x1A8594, "4881C168170000498BD6E81DC90500"},
    {"castEnter", 0x212DD0, "40534883EC60"},
    {"castLeave", 0x212E89, "488B4C2458"},
    {"castDestroy", 0x165200, "48895C2408574883EC20"},
    {"childCreated", 0x16B047, "8B4314FFC8"},
    {"directEnter1", 0x16B24A, "C744242001000000FF90E8000000"},
    {"directLeave1", 0x16B258, "E9D4000000"},
    {"directEnter2", 0x16B1D0, "C744242001000000FF90E8000000"},
    {"directLeave2", 0x16B1E7, "E945010000"},
    {"childQueued", 0x16B0F9, "4881C168170000E8BB9D0900"},
    {"childProjectile", 0x16B1EC, "488BD3498BCDE879F00B00"},
    {"castCall", 0x212E63, "C744243801000000C74424300100000048C744242800000000C7442420FFFFFFFFE8377DF5FF"},
    {"fireFrame", 0x16ABC0, "48895C24205556574154415541564157488D6C24804881EC80010000"},
    {"abilityIndex", 0x16AFAC, "8D43FF89442450"},
    {"ordinal", 0x16AFC0, "4D8BCE448BC78BD0498BCF"},
    {"queuedPointer", 0x16B0D7, "48895A10C6421A00"},
    {"directArgs1", 0x16B236, "498B064533C9440FB6051F1C4400488BD3498BCE"},
    {"directArgs2", 0x16B1BC, "498B064533C9440FB605991C4400488BD3498BCE"},
    {"directCleanup2", 0x16B1DE, "488D4D40E859252900"},
}
local callbackKeys = {"parentQueued", "castEnter", "castLeave", "castDestroy", "childCreated",
    "childDirectEnter", "childDirectLeave", "childQueued", "childProjectile"}
local capabilities = {"EEex_GetImageBase", "EEex_ReadU8", "EEex_GenLuaCall", "EEex_FlattenTable",
    "EEex_HookBeforeRestoreWithLabels", "EEex_DisableCodeProtection", "EEex_EnableCodeProtection"}

function M.validate(api, config, watchdog)
    assert(not M.installed and not M.failed, "cast transport: already attempted; restart required")
    assert(type(api.EEex_HookIntegrityWatchdog_Load) == "boolean", "watchdog state unavailable")
    if api.EEex_HookIntegrityWatchdog_Load then
        assert(type(watchdog) == "table" and type(watchdog.validate) == "function"
            and type(watchdog.withPreservation) == "function", "watchdog preservation helper required")
        watchdog.validate(api)
    end
    for _, key in ipairs(capabilities) do
        assert(type(api[key]) == "function", "cast transport: missing API " .. key)
    end
    assert(type(config) == "table" and type(config.callbacks) == "table", "cast callbacks required")
    local names = {}
    for _, key in ipairs(callbackKeys) do
        local name = config.callbacks[key]
        assert(type(name) == "string" and name:match("^[%a_][%w_]*$"), "invalid cast callback " .. key)
        assert(type(api[name]) == "function", "cast callback must exist: " .. name)
        names[key] = name
    end
    local base = api.EEex_GetImageBase()
    assert(type(base) == "number" and base > 0 and base == math.floor(base), "invalid image base")
    local sites = {}
    for _, guard in ipairs(guards) do
        local address, hex = base + guard[2], guard[3]
        for i = 1, #hex, 2 do
            assert(api.EEex_ReadU8(address + (i-1)/2) == tonumber(hex:sub(i,i+1),16),
                "cast transport: unsupported/previously patched site " .. guard[1])
        end
        sites[guard[1]] = address
    end
    -- Shared destructor and Run observations require this actual message class
    -- to retain its original virtual dispatch. Detect a conflicting vtable patch.
    for _, pair in ipairs({{0x590D90,0x165200},{0x590DC0,0x212DD0}}) do
        local value = base+pair[2]
        for i=0,7 do
            assert(api.EEex_ReadU8(base+pair[1]+i)==value%256,
                "cast transport: unsupported/previously patched site castVtable")
            value=math.floor(value/256)
        end
    end
    return {base=base, sites=sites, callbacks=names}
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
local frame = calculated("lea rax, qword ptr ss:[rbp+0B8h]")
local ordinal = calculated("mov eax, edi")
local function callback(api, name, key, args)
    local suffix = "_cbrpq_cast_" .. key
    return api.EEex_FlattenTable({{save}, api.EEex_GenLuaCall(name, {args=args, labelSuffix=suffix}),
        {"call_error" .. suffix .. ": #ENDL", restore}})
end

-- Guard outside callback shadow allocation. Both paths restore the original
-- flags/RAX. The alternate path resets compile-time STACK_MOD before restoring.
local function guarded(api, key, condition, assembly)
    local skip, finish = "skip_cbrpq_cast_" .. key, "finish_cbrpq_cast_" .. key
    return api.EEex_FlattenTable({{
        "pushfq #ENDL push rax #ENDL #STACK_MOD(16) #ENDL", condition,
        "jnz " .. skip .. " #ENDL pop rax #ENDL popfq #ENDL #STACK_MOD(-16) #ENDL"},
        assembly, {"jmp " .. finish .. " #ENDL " .. skip .. ": #ENDL #STACK_MOD(16) #ENDL",
        "pop rax #ENDL popfq #ENDL #STACK_MOD(-16) #ENDL " .. finish .. ": #ENDL"}})
end

-- Every nativeFireFrame is original FireSpell entry RSP (=RBP+B8).
-- Runtime MUST additionally correlate it with the exact tracked cast-enter RSP
-- minus70h; assembly's return-address guard alone does not establish ownership.
-- castEnter/Leave observe unowned invocations too, for nested sentinel handling.
-- childProjectile always reports the actual pointer: the runtime must validate
-- its current class (supported instant vtable imageBase+59BFF0) and retire/reject
-- unsupported pending ownership. Silently filtering that callback would leave
-- childCreated tags alive without a class decision. Callback results are ignored.
-- Userdata is borrowed for this callback only. Correlate owned invocation before
-- reading sprite fields; unowned/general FireSpell callers may use other AI types.
function M.install(api, config, watchdog)
    local v = M.validate(api, config, watchdog)
    local sites, names, base = v.sites, v.callbacks, v.base
    local function child(key, callbackKey, args)
        return guarded(api, key, "mov rax, " .. (base+0x212E89) .. " #ENDL cmp qword ptr ss:[rbp+0B8h], rax #ENDL",
            callback(api, names[callbackKey], key, args))
    end
    local assembly = {
        parentQueued=callback(api,names.parentQueued,"parentQueued",{
            reg("rsi","CGameEffect"),reg("r14"),reg("r15","CGameSprite")}),
        castEnter=callback(api,names.castEnter,"castEnter",{
            reg("rcx"),calculated("lea rax, qword ptr ss:[rsp+#LAST_FRAME_TOP(160)]")}),
        castLeave=callback(api,names.castLeave,"castLeave",{reg("rbx")}),
        castDestroy=guarded(api,"castDestroy",
            "mov rax, " .. (base+0x590D90) .. " #ENDL cmp qword ptr ds:[rcx], rax #ENDL",
            callback(api,names.castDestroy,"castDestroy",{reg("rcx")})),
        childCreated=child("childCreated","childCreated",{frame,reg("rbx","CGameEffect"),ordinal,
            calculated("mov eax, dword ptr ss:[rsp+#LAST_FRAME_TOP(240)]"),
            reg("r14","CGameSprite"),reg("rsi","CGameSprite")}),
        directEnter1=child("directEnter1","childDirectEnter",{frame,reg("rdx"),calculated("mov eax, r9d")}),
        directLeave1=child("directLeave1","childDirectLeave",{frame}),
        directEnter2=child("directEnter2","childDirectEnter",{frame,reg("rdx"),calculated("mov eax, r9d")}),
        directLeave2=child("directLeave2","childDirectLeave",{frame}),
        childQueued=child("childQueued","childQueued",{frame,reg("rdx"),reg("rbx","CGameEffect"),ordinal}),
        childProjectile=child("childProjectile","childProjectile",{frame,reg("rbx","CGameEffect"),ordinal,reg("r13")}),
    }
    local function write()
        local function before(key, size, entry)
            api.EEex_HookBeforeRestoreWithLabels(sites[key],0,size,size,
                entry and {{"stack_mod",8}} or {},assembly[key])
        end
        local function leaveJump(key)
            -- Original JMP is relative. Re-emit its pinned absolute destination;
            -- copying five bytes into a JIT block would jump to the wrong place.
            local code = api.EEex_FlattenTable({assembly[key],{
                "#MANUAL_HOOK_EXIT(0) #ENDL jmp ",base+0x16B331," #ENDL"}})
            api.EEex_HookBeforeRestoreWithLabels(sites[key],0,0,5,
                {{"manual_hook_integrity_exit",true}},code)
        end
        before("parentQueued",7)
        before("castEnter",6,true)
        before("castLeave",5)
        before("castDestroy",5,true)
        before("childCreated",5)
        before("directEnter1",8)
        leaveJump("directLeave1")
        before("directEnter2",8)
        leaveJump("directLeave2")
        before("childQueued",7)
        before("childProjectile",6)
    end
    M.failed=true -- A partial patch failure has no claimed rollback; no retry.
    api.EEex_DisableCodeProtection()
    local ok,err=pcall(function()
        if watchdog then watchdog.withPreservation(api,write) else write() end
    end)
    api.EEex_EnableCodeProtection()
    if not ok then error(err,0) end
    M.installed,M.failed,M.sites=true,false,sites
    return sites
end

return M
