-- Opt-in, uninstalled lab transport hooks; no M_ loader or production component.
-- Pinned BG2EE 2.7.3.0 / EEex 1.3.0. Native instructions were read offline.
-- No native effect fields, message fields, arguments or return values are changed.
-- Callback failures continue native execution; the runtime must catch/report its
-- own errors and invalidate all transient uniqueness state before returning.
local M = {}
M.expectedExecutableSha256 = "b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57"

-- All RVAs are image-relative. Guards include direct self-message construction
-- and Run's argument setup: these item paths set noSave=0, immediateResolve=1.
-- Run still observes ALL messages. Its callback must reject support for noSave
-- ~= 0 and enter a sentinel for unrelated messages; it must not skip nesting.
local guards = {
    {"useBegin", 0x3BBA88, "418BF766453B7D1E"},
    {"useQueue", 0x3BBB7D, "E83E93E4FF"},
    {"useEnd", 0x3BBCF6, "B928000000"},
    {"fireBegin", 0x16A538, "4C8BF08BFB"},
    {"fireQueue", 0x16A623, "E898A80900"},
    {"fireEnd", 0x16A79E, "B928000000"},
    {"messageRun", 0x20FE5E, "FF90E800000048C7431000000000"},
    {"destroy", 0x1551B0, "48895C2408574883EC20"},
    -- Standard effect classes share 14C8E0. HP18 uses a separate, inlined
    -- destructor at1A45A0, so observing only the shared destructor misses HP.
    -- EEex's existing destruct hook is14C900, outside our five-byte entry patch.
    {"effectDestroy", 0x14C8E0, "48895C2408574883EC20"},
    {"hpEffectDestroy", 0x1A45A0, "48895C2408574883EC20"},
    {"reset", 0x2930C0, "488BC455535657415441564157"},
    -- Target2 dispatch, before argument setup. Original native CALL stays at
    -- its original address (and retains its original return address).
    {"useProjectile", 0x3BBBD0, "488B8BD84A0000488BD7E891E6E6FF"},
    {"fireProjectile", 0x16A66F, "488BD3498BCEE8F6FB0B00"},
    {"useZero", 0x3BAF2A, "4533FF"},
    {"useConstruct", 0x3BBB54, "48897A1044887A1A"},
    {"fireConstruct", 0x16A5FA, "48895A10C6421A00"},
    {"runArgs", 0x20FE42, "440FB64B1A440FB60514D03900488B5310488B01C744242001000000"},
}
local callbackKeys = {
    "useBegin", "useQueue", "useEnd", "fireBegin", "fireQueue", "fireEnd",
    "messageEnter", "messageLeave", "destroy", "effectDestroy", "reset",
    "useProjectile", "fireProjectile",
}
local capabilities = {
    "EEex_GetImageBase", "EEex_ReadU8", "EEex_GenLuaCall", "EEex_FlattenTable",
    "EEex_HookBeforeRestoreWithLabels",
    "EEex_StoreBytesAssembly", "EEex_DisableCodeProtection", "EEex_EnableCodeProtection",
}

-- Read-only preflight; call together with admission-hook validation BEFORE any
-- patch. This does not hash the executable: the external lab preflight must pin
-- the SHA256 above. Exact site/context guards additionally detect conflicts.
function M.validate(api, config, watchdog)
    assert(not M.failed, "potion transport: a prior install attempt failed; restart required")
    assert(type(api.EEex_HookIntegrityWatchdog_Load) == "boolean", "watchdog state unavailable")
    if api.EEex_HookIntegrityWatchdog_Load then
        assert(type(watchdog) == "table" and type(watchdog.validate) == "function"
            and type(watchdog.withPreservation) == "function", "watchdog preservation helper required")
        watchdog.validate(api)
    end
    for _, key in ipairs(capabilities) do
        assert(type(api[key]) == "function", "potion transport: missing API " .. key)
    end
    assert(type(config) == "table" and type(config.callbacks) == "table",
        "potion transport: callback configuration required")
    local names = {}
    for _, key in ipairs(callbackKeys) do
        local name = config.callbacks[key]
        assert(type(name) == "string" and name:match("^[%a_][%w_]*$"),
            "potion transport: invalid callback " .. key)
        assert(type(api[name]) == "function", "potion transport: callback must exist: " .. name)
        names[key] = name
    end
    local base = api.EEex_GetImageBase()
    assert(type(base) == "number" and base > 0 and base == math.floor(base),
        "potion transport: invalid executable image base")
    local sites = {}
    for _, guard in ipairs(guards) do
        local address, hex = base + guard[2], guard[3]
        for i = 1, #hex, 2 do
            assert(api.EEex_ReadU8(address + (i - 1) / 2) == tonumber(hex:sub(i, i + 1), 16),
                "potion transport: unsupported/previously patched site " .. guard[1])
        end
        sites[guard[1]] = address
    end
    return {sites = sites, callbacks = names}
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

-- Argument builders may clobber only RAX, which is already saved. GenLuaCall
-- emits arguments in reverse order; none of these builders consume scratch RAX.
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
local useFrame = reg("rbp")
local fireFrame = calculated("lea rax, qword ptr ss:[rsp+#LAST_FRAME_TOP(160)]")

local function callback(api, name, key, args)
    local suffix = "_cbrpq_transport_" .. key
    return api.EEex_FlattenTable({
        {save}, api.EEex_GenLuaCall(name, {args = args, labelSuffix = suffix}),
        {"call_error" .. suffix .. ": #ENDL", restore},
    })
end

-- Callback contract (all return values ignored; pointers are synchronous keys):
-- useBegin(RBP, signedAbilityIndex); fireBegin(originalRSP, abilityIndex)
-- useQueue(RBP, messagePtr, effectUserdata, ordinal)
-- fireQueue(originalRSP, messagePtr, effectUserdata, ordinal)
-- useEnd(RBP); fireEnd(originalRSP)
-- messageEnter(messagePtr, effectPtr, numericNoSave); messageLeave(messagePtr)
-- destroy(messagePtr); effectDestroy(effectPtr); reset()
-- useProjectile(RBP,effectUserdata,ordinal,projectilePtr)
-- fireProjectile(originalRSP,effectUserdata,ordinal,projectilePtr)
-- These report target2 ATTACHMENT only. Runtime must prove that the selected
-- projectile class delivers the same original pointer before binding a message.
-- Use/fire frame namespaces MUST differ. Null queue messages must be ignored.
-- Callback names resolve in the game's GLOBAL Lua state, not an API subtable.
-- No callback may retain borrowed effect userdata or alter native control flow.
function M.install(api, config, watchdog)
    assert(not M.installed and not M.failed, "potion transport: already attempted; do not retry")
    local validated = M.validate(api, config, watchdog)
    local sites, names = validated.sites, validated.callbacks
    local assemblies = {
        useBegin = callback(api, names.useBegin, "useBegin", {
            useFrame, calculated("movsx rax, word ptr ds:[rbx+4AF2h]")}),
        useQueue = callback(api, names.useQueue, "useQueue", {
            useFrame, reg("rdx"), reg("rdi", "CGameEffect"), calculated("mov eax, esi")}),
        useEnd = callback(api, names.useEnd, "useEnd", {useFrame}),
        fireBegin = callback(api, names.fireBegin, "fireBegin", {
            fireFrame, calculated("mov eax, r12d")}),
        fireQueue = callback(api, names.fireQueue, "fireQueue", {
            fireFrame, reg("rdx"), reg("rbx", "CGameEffect"), calculated("mov eax, edi")}),
        fireEnd = callback(api, names.fireEnd, "fireEnd", {fireFrame}),
        destroy = callback(api, names.destroy, "destroy", {reg("rcx")}),
        effectDestroy = callback(api, names.effectDestroy, "effectDestroy", {reg("rcx")}),
        hpEffectDestroy = callback(api, names.effectDestroy, "hpEffectDestroy", {reg("rcx")}),
        reset = callback(api, names.reset, "reset", {}),
        useProjectile = callback(api, names.useProjectile, "useProjectile", {
            useFrame, reg("rdi", "CGameEffect"), calculated("mov eax, esi"),
            calculated("mov rax, qword ptr ds:[rbx+4AD8h]")}),
        fireProjectile = callback(api, names.fireProjectile, "fireProjectile", {
            fireFrame, reg("rbx", "CGameEffect"), calculated("mov eax, edi"), reg("r14")}),
    }
    local function write()
    assemblies.messageRun = api.EEex_FlattenTable({
        callback(api, names.messageEnter, "messageEnter", {
            reg("rbx"), reg("rdx"), calculated("mov eax, r9d")}),
        -- Check our enter callback before the native callee may legitimately
        -- change volatile registers; start a new check after its return.
        {"#MANUAL_HOOK_EXIT(0) #ENDL"},
        -- FF /2 indirect call is unsupported by BeforeAndAfterCall (E8 only).
        -- Copy all six original bytes. Call at the ORIGINAL stack pointer so
        -- [rsp+20h]=immediateResolve and native register arguments remain intact.
        -- The callee's return address now points into JIT code. Other mods that
        -- inspect that address need separate compatibility review. Native
        -- exceptions/unwinds bypassing the ordinary return are not covered.
        api.EEex_StoreBytesAssembly(sites.messageRun, 6),
        api.EEex_HookIntegrityWatchdog_HookEnter,
        callback(api, names.messageLeave, "messageLeave", {reg("rbx")}),
    })
        local function before(key, bytes, functionEntry)
            local labels = functionEntry and {{"stack_mod", 8}} or {}
            api.EEex_HookBeforeRestoreWithLabels(sites[key], 0, bytes, bytes, labels, assemblies[key])
        end
        local function queue(key)
            -- The generic BeforeCall helper ignores RAX in its watchdog mask.
            -- We preserve it, so use a restore hook with the unweakened mask,
            -- exit the check, then make the original version-pinned call.
            local assembly = api.EEex_FlattenTable({assemblies[key], {
                "#MANUAL_HOOK_EXIT(0) #ENDL call ", api.EEex_GetImageBase() + 0x204EC0, " #ENDL"}})
            api.EEex_HookBeforeRestoreWithLabels(sites[key], 0, 0, 5,
                {{"manual_hook_integrity_exit", true}}, assembly)
        end
        before("useBegin", 8)
        queue("useQueue")
        before("useEnd", 5)
        before("fireBegin", 5)
        queue("fireQueue")
        before("fireEnd", 5)
        api.EEex_HookBeforeRestoreWithLabels(sites.messageRun, 0, 0, 6, {}, assemblies.messageRun)
        before("destroy", 5, true)
        before("effectDestroy", 5, true)
        before("hpEffectDestroy", 5, true)
        before("reset", 5, true)
        before("useProjectile", 7)
        before("fireProjectile", 6)
    end
    M.failed = true -- No rollback is claimed if an EEex patch operation fails.
    api.EEex_DisableCodeProtection()
    local ok, err = pcall(function()
        if watchdog then watchdog.withPreservation(api, write) else write() end
    end)
    api.EEex_EnableCodeProtection()
    if not ok then error(err, 0) end
    M.installed, M.failed, M.sites = true, false, sites
    return sites
end

return M
