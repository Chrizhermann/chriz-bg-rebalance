-- EEex ambient-readiness bridge for component 121.
-- The installer replaces the single placeholder below with a validated table.

local manifest = %CBR_RDY_MANIFEST%
local unpack_args = unpack or table.unpack

local function normalize(value)
    return string.lower(tostring(value or ""))
end

local function flag(value, fallback)
    if value == nil then return fallback end
    return tonumber(value) or fallback
end

if CBR_RDY_AMBIENT_ENABLED == nil then
    CBR_RDY_AMBIENT_ENABLED = flag(manifest.defaults.ambient_enabled, 1)
end
if CBR_RDY_URGENT_ENABLED == nil then
    CBR_RDY_URGENT_ENABLED = flag(manifest.defaults.urgent_enabled, 1)
end
if CBR_RDY_EXTERNAL_OWNER == nil then
    CBR_RDY_EXTERNAL_OWNER = flag(manifest.defaults.external_owner, 0)
end

_G.CBR_RDY_STATE = _G.CBR_RDY_STATE or {
    ambient_faulted = 0,
    urgent_faulted = 0,
    ambient_fault_logged = 0,
    urgent_fault_logged = 0,
    unsupported_logged = 0,
    generation = 0,
}
local state = _G.CBR_RDY_STATE
state.generation = flag(state.generation, 0) + 1

local function owner_has(bit)
    local value = flag(CBR_RDY_EXTERNAL_OWNER, 0)
    if EEex_BAnd then return EEex_BAnd(value, bit) ~= 0 end
    return math.floor(value / bit) % 2 == 1
end

local function action_resref(action)
    if not action then return "" end
    local value = action.m_string1
        and action.m_string1.m_pchData
        and action.m_string1.m_pchData:get()
    return normalize(value)
end

local function queued_actions_readable(sprite)
    if not (sprite and sprite.m_queuedActions and EEex_Utility_IterateCPtrList) then
        return false
    end
    local readable = true
    EEex_Utility_IterateCPtrList(sprite.m_queuedActions, function(action)
        if type(action.m_actionID) ~= "number" then readable = false end
    end)
    return readable
end

local function outside_cutscene()
    return type(Infinity_GetInCutsceneMode) == "function"
        and not Infinity_GetInCutsceneMode()
end

local function update_quick_lists(sprite, resref, change_amount)
    if not (sprite and sprite.CheckQuickLists and EEex_RunWithStackManager) then
        return false
    end
    EEex_RunWithStackManager({
        { name = "abilityId", struct = "CAbilityId" },
    }, function(manager)
        local ability_id = manager:getUD("abilityId")
        ability_id.m_itemType = 1
        ability_id.m_res:set(resref)
        sprite:CheckQuickLists(ability_id, change_amount, 0, 0)
    end)
    return true
end

local function layer_enabled(layer)
    if layer == "ambient" then
        return flag(CBR_RDY_AMBIENT_ENABLED, 0) == 1
            and not owner_has(1)
            and flag(state.ambient_faulted, 0) == 0
    end
    return flag(CBR_RDY_URGENT_ENABLED, 0) == 1
        and not owner_has(2)
        and flag(state.urgent_faulted, 0) == 0
end

local function disable_layer(layer, traceback)
    state[layer .. "_faulted"] = 1
    local logged = layer .. "_fault_logged"
    if flag(state[logged], 0) == 0 then
        state[logged] = 1
        print("[CBR Ready] " .. layer .. " disabled after callback error:\n"
            .. tostring(traceback))
    end
end

local function invoke(layer, event, ...)
    if not layer_enabled(layer) then return end
    local handlers = _G.CBR_RDY_HANDLERS
    local callback = handlers and handlers[layer .. "_" .. event]
    if type(callback) ~= "function" then return end
    local arguments = { ... }
    local ok, traceback = xpcall(function()
        return callback(unpack_args(arguments))
    end, debug.traceback)
    if not ok then disable_layer(layer, traceback) end
end

_G.CBR_RDY_HANDLERS = {
    ambient_tick = function() end,
    ambient_action = function() end,
    ambient_reset = function() end,
    ambient_export = function() return nil end,
    ambient_import = function() end,
    urgent_tick = function() end,
    urgent_action = function() end,
    urgent_reset = function() end,
}

_G.CBR_RDY_TRAMPOLINES = {
    tick = function(sprite)
        invoke("ambient", "tick", sprite)
        invoke("urgent", "tick", sprite)
    end,
    action = function(sprite, action)
        invoke("ambient", "action", sprite, action)
        invoke("urgent", "action", sprite, action)
    end,
    reset = function(sprite)
        invoke("ambient", "reset", sprite)
        invoke("urgent", "reset", sprite)
    end,
    export = function(sprite)
        if not layer_enabled("ambient") then return nil end
        local handlers = _G.CBR_RDY_HANDLERS
        local callback = handlers and handlers.ambient_export
        if type(callback) ~= "function" then return nil end
        local result = nil
        local ok, traceback = xpcall(function()
            result = callback(sprite)
        end, debug.traceback)
        if not ok then disable_layer("ambient", traceback) end
        return result
    end,
    import = function(sprite, saved)
        invoke("ambient", "import", sprite, saved)
    end,
}

local required = {
    EEex_Opcode_AddListsResolvedListener,
    EEex_Action_AddSpriteStartedActionListener,
    EEex_Sprite_AddQuickListCountsResetListener,
    EEex_Sprite_AddMarshalHandlers,
}
local supported = true
for _, callback in ipairs(required) do
    if type(callback) ~= "function" then supported = false end
end

if supported and not _G.CBR_RDY_LISTENERS_REGISTERED then
    EEex_Opcode_AddListsResolvedListener(function(sprite)
        local current = _G.CBR_RDY_TRAMPOLINES
        if current and current.tick then current.tick(sprite) end
    end)
    EEex_Action_AddSpriteStartedActionListener(function(sprite, action)
        local current = _G.CBR_RDY_TRAMPOLINES
        if current and current.action then current.action(sprite, action) end
    end)
    EEex_Sprite_AddQuickListCountsResetListener(function(sprite)
        local current = _G.CBR_RDY_TRAMPOLINES
        if current and current.reset then current.reset(sprite) end
    end)
    EEex_Sprite_AddMarshalHandlers("CBR_RDY",
        function(sprite)
            local current = _G.CBR_RDY_TRAMPOLINES
            if current and current.export then return current.export(sprite) end
            return nil
        end,
        function(sprite, saved)
            local current = _G.CBR_RDY_TRAMPOLINES
            if current and current.import then current.import(sprite, saved) end
        end)
    _G.CBR_RDY_LISTENERS_REGISTERED = 1
elseif not supported and flag(state.unsupported_logged, 0) == 0 then
    state.unsupported_logged = 1
    print("[CBR Ready] disabled: required EEex listener API is unavailable")
end
