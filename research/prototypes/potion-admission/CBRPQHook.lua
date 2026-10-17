-- Explicitly installed lab hook only; no M_ loader or production component.
-- BG2EE 2.7.3.0 candidate, after successful native CheckSave, before OnAdd.
-- Caller must supply a provenance-aware callback. Its true result rejects the
-- incoming original effect through CheckAdd's native failure path.
local M = {}
local offset = 0xAE9 -- CGameEffect::CheckAdd + AE9 = RVA 1CD1A9
local expected = {0x0F,0x84,0xF6,0xF7,0xFF,0xFF,0x8B,0x47,0x24,
    0x3D,0x00,0x10,0x00,0x00,0x74,0x0D,0x83,0xF8,0x02}

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

function M.validate(api, callbackName, watchdog)
    assert(not M.failed, "potion admission hook: prior install attempt failed; restart required")
    assert(type(callbackName) == "string" and callbackName:match("^[%a_][%w_]*$"),
        "invalid admission callback name")
    assert(type(api[callbackName]) == "function", "admission callback must exist before hooking")
    assert(type(api.EEex_HookIntegrityWatchdog_Load) == "boolean", "watchdog state unavailable")
    if api.EEex_HookIntegrityWatchdog_Load then
        assert(type(watchdog) == "table" and type(watchdog.validate) == "function"
            and type(watchdog.withPreservation) == "function", "watchdog preservation helper required")
        watchdog.validate(api)
    end
    if M.installed then
        assert(M.callbackName == callbackName, "admission hook already has another callback")
        return M.site
    end
    local base = assert(api.EEex_TryLabel("CGameEffect::CheckAdd"), "CheckAdd label unavailable")
    local site = base + offset
    for i, byte in ipairs(expected) do
        assert(api.EEex_ReadU8(site + i - 1) == byte,
            "potion admission hook: unsupported/previously patched CheckSave boundary")
    end
    return site
end

function M.install(api, callbackName, watchdog)
    local site = M.validate(api, callbackName, watchdog)
    if M.installed then return site end
    -- GenLuaCall preserves nonvolatile registers. Preserve flags, all volatile
    -- GPRs and XMM0..5 explicitly; no native field is used as a return mailbox.
    local call = api.EEex_GenLuaCall(callbackName, {
        args = {
            function(stackOffset)
                return {"mov qword ptr ss:[rsp+#$(1)], rdi #ENDL", {stackOffset}}, "CGameEffect"
            end,
            function(stackOffset)
                return {"mov qword ptr ss:[rsp+#$(1)], r14 #ENDL", {stackOffset}}, "CGameSprite"
            end,
        },
        returnType = api.EEex_LuaCallReturnType.Boolean,
    })
    local assembly = api.EEex_FlattenTable({save, call, [[
        test rax, rax
        jz cbrpq_allow
        #DESTROY_SHADOW_SPACE(KEEP_ENTRY)
    ]], restore, [[
        jmp #L(jmp_success)
        call_error:
        cbrpq_allow:
        #STACK_MOD(160)
        #RESUME_SHADOW_ENTRY
        #DESTROY_SHADOW_SPACE
    ]], restore, [[
        jmp #L(jmp_fail)
    ]]})
    M.failed = true
    api.EEex_DisableCodeProtection()
    local ok, err = pcall(function()
        -- The original conditional failure goes straight to its original target;
        -- only the success fallthrough executes this callback.
        local function write()
            api.EEex_HookConditionalJumpOnFailWithLabels(site, 0, {}, assembly)
        end
        if watchdog then watchdog.withPreservation(api, write) else write() end
    end)
    api.EEex_EnableCodeProtection()
    if not ok then error(err, 0) end
    M.installed, M.failed, M.site, M.callbackName = true, false, site, callbackName
    return site
end

return M
