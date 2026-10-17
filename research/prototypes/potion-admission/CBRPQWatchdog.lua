-- Scoped EEex 1.3 watchdog template decoration. No automatic hooks or loading.
-- The original enter/exit checks and ignore policies remain intact. Their
-- native helpers may clobber volatile XMM/status state, so protect that state
-- outside each template while reporting the ORIGINAL native RSP to the check.
local M = {}
local before = [[
    lea rsp, qword ptr ss:[rsp-112]
    #STACK_MOD(112)
    movdqu xmmword ptr ss:[rsp+00h], xmm0
    movdqu xmmword ptr ss:[rsp+10h], xmm1
    movdqu xmmword ptr ss:[rsp+20h], xmm2
    movdqu xmmword ptr ss:[rsp+30h], xmm3
    movdqu xmmword ptr ss:[rsp+40h], xmm4
    movdqu xmmword ptr ss:[rsp+50h], xmm5
    pushfq
    pop qword ptr ss:[rsp+60h]
]]
local after = [[
    movdqu xmm0, xmmword ptr ss:[rsp+00h]
    movdqu xmm1, xmmword ptr ss:[rsp+10h]
    movdqu xmm2, xmmword ptr ss:[rsp+20h]
    movdqu xmm3, xmmword ptr ss:[rsp+30h]
    movdqu xmm4, xmmword ptr ss:[rsp+40h]
    movdqu xmm5, xmmword ptr ss:[rsp+50h]
    push qword ptr ss:[rsp+60h]
    popfq
    lea rsp, qword ptr ss:[rsp+112]
    #STACK_MOD(-112)
]]
local function decorate(template, extra, name)
    assert(type(template) == "table", "unsupported EEex watchdog " .. name .. " template")
    local result, frameReferences, shadowReferences, calls = {before}, 0, 0, 0
    for _, value in ipairs(template) do
        assert(type(value) == "string" or type(value) == "number", "unsupported watchdog template part")
        if type(value) == "string" then
            local count
            value, count = value:gsub("#LAST_FRAME_TOP%(0%)", "#LAST_FRAME_TOP(112)")
            frameReferences = frameReferences + count
            local _, shadows = value:gsub("#MAKE_SHADOW_SPACE%(" .. extra .. "%)", "")
            shadowReferences = shadowReferences + shadows
            local _, callCount = value:gsub("%f[%a]call%f[%A]", "")
            calls = calls + callCount
        end
        result[#result + 1] = value
    end
    -- These are native ABI/template guards, not game-resource fingerprints.
    assert(frameReferences == 1 and shadowReferences == 1 and calls == 1,
        "unsupported EEex watchdog " .. name .. " layout")
    result[#result + 1] = after
    return result
end

function M.validate(api)
    assert(api == _G, "watchdog preservation requires the global EEex state")
    assert(type(api.EEex_HookIntegrityWatchdog_Load) == "boolean", "watchdog state unavailable")
    if not api.EEex_HookIntegrityWatchdog_Load then return true end
    assert(type(api.EEex_HookIntegrityWatchdog_HookExit) == "function", "watchdog exit unavailable")
    decorate(api.EEex_HookIntegrityWatchdog_HookEnter, 32, "enter")
    decorate(api.EEex_HookIntegrityWatchdog_HookExit(0), 40, "exit")
    return true
end

function M.withPreservation(api, fn)
    M.validate(api)
    if not api.EEex_HookIntegrityWatchdog_Load then return fn() end
    local originalEnter = api.EEex_HookIntegrityWatchdog_HookEnter
    local originalExit = api.EEex_HookIntegrityWatchdog_HookExit
    api.EEex_HookIntegrityWatchdog_HookEnter = decorate(originalEnter, 32, "enter")
    api.EEex_HookIntegrityWatchdog_HookExit = function(instance)
        return decorate(originalExit(instance), 40, "exit")
    end
    local ok, result = pcall(fn)
    api.EEex_HookIntegrityWatchdog_HookEnter = originalEnter
    api.EEex_HookIntegrityWatchdog_HookExit = originalExit
    if not ok then error(result, 0) end
    return result
end

return M
