-- Session-only EEex capability probe for component 121.
--
-- Loading this file only defines the probe.  Nothing is registered until
-- CBR_RDY_PROBE.install() is called, and no slot is changed unless the caller
-- explicitly invokes debit_once().  teardown() makes the append-only
-- callbacks inert and attempts to restore every outstanding controlled debit.
-- Logs live only in this Lua process and are returned by dump(); this script
-- never writes a resource, save, or file.

_G.CBR_RDY_PROBE = _G.CBR_RDY_PROBE or {}
local probe = _G.CBR_RDY_PROBE

probe.version = 1
probe.active = probe.active or 0
probe.generation = probe.generation or 0
probe.listeners_registered = probe.listeners_registered or 0
probe.logs = probe.logs or {}
probe.watches = probe.watches or {}
probe.debits = probe.debits or {}
probe.selected_casts = probe.selected_casts or {}

local function timestamp()
    if EEex_GameState_GetTime then
        local ok, value = pcall(EEex_GameState_GetTime)
        if ok and type(value) == "number" then return value end
    end
    if Infinity_GetGameTime then
        local ok, value = pcall(Infinity_GetGameTime)
        if ok and type(value) == "number" then return value end
    end
    return os.clock()
end

local function normalize(value)
    return string.lower(tostring(value or ""))
end

local function object_id(sprite)
    if not sprite then return -1 end
    local ok, value = pcall(function()
        return sprite.m_id or sprite.m_idSelf or sprite.m_nId
    end)
    if ok and type(value) == "number" then return value end
    return -1
end

local function log(kind, message)
    probe.logs[#probe.logs + 1] = {
        time = timestamp(),
        kind = tostring(kind),
        message = tostring(message),
    }
end

local function get_local(sprite, name)
    if not sprite or not EEex_Sprite_GetLocalInt then return nil end
    local ok, value = pcall(EEex_Sprite_GetLocalInt, sprite, name)
    if ok then return value end
    return nil
end

local function sees_party(sprite)
    if not sprite or not EEex_Trigger_EvalConditionalStringAsAIBase then return nil end
    local ok, value = pcall(
        EEex_Trigger_EvalConditionalStringAsAIBase, "See([PC])", sprite)
    if not ok then return nil end
    return value and 1 or 0
end

local function current_action_id(sprite)
    local ok, value = pcall(function()
        return sprite.m_curAction and sprite.m_curAction.m_actionID
    end)
    if ok and type(value) == "number" then return value end
    return nil
end

local function action_resref(action)
    if not action then return "" end
    local ok, value = pcall(function()
        if action.m_string1 and action.m_string1.get then
            return action.m_string1:get()
        end
        return ""
    end)
    if ok then return normalize(value) end
    return ""
end

local function queue_ids(sprite)
    local result = {}
    local ok = pcall(function()
        if not (sprite and sprite.m_actionQueue and EEex_Utility_IterateCPtrList) then return end
        EEex_Utility_IterateCPtrList(sprite.m_actionQueue, function(action)
            result[#result + 1] = tostring(action.m_actionID)
        end)
    end)
    if not ok then return "<unavailable>" end
    return table.concat(result, ",")
end

local function spell_level(resref)
    if not EEex_Resource_Demand then return nil end
    local ok, header = pcall(EEex_Resource_Demand, resref, "SPL")
    if not ok or not header then return nil end
    local level = tonumber(header.spellLevel)
    if not level or level < 1 then return nil end
    return level
end

local function list_field(resref)
    local prefix = string.upper(string.sub(resref, 1, 4))
    if prefix == "SPWI" then return "m_memorizedSpellsMage" end
    if prefix == "SPPR" then return "m_memorizedSpellsPriest" end
    return nil
end

local function find_available_record(sprite, resref)
    if not (sprite and EEex_Utility_IterateCPtrList) then return nil, nil end
    local field = list_field(resref)
    local level = spell_level(resref)
    if not field or not level then return nil, nil end
    local found = nil
    local ok = pcall(function()
        local spell_lists = sprite[field]
        if not spell_lists then return end
        local level_list = spell_lists:getReference(level - 1)
        if not level_list then return end
        EEex_Utility_IterateCPtrList(level_list, function(record)
            local candidate = normalize(record.m_spellId:get())
            local flags = tonumber(record.m_flags)
            local available = flags and (flags % 2 == 1)
            if candidate == normalize(resref) and available then
                found = record
                return true
            end
        end)
    end)
    if not ok then return nil, nil end
    return found, level
end

local function rebuild_quick_lists(sprite, level)
    if not sprite or not sprite.CheckQuickLists then return false end
    local ok = pcall(function()
        -- The exact arguments are a Task 6 measurement, not a production
        -- claim.  A disposable actor is reloaded if this does not round-trip.
        sprite:CheckQuickLists(level - 1, -1, 0, 0)
    end)
    return ok
end

function probe.snapshot(sprite, label)
    if probe.active ~= 1 then return nil end
    local id = object_id(sprite)
    local ea = nil
    pcall(function() ea = sprite.m_typeAI.m_EnemyAlly end)
    local parts = {
        "label=" .. tostring(label or "snapshot"),
        "id=" .. tostring(id),
        "ea=" .. tostring(ea),
        "see_pc=" .. tostring(sees_party(sprite)),
        "action=" .. tostring(current_action_id(sprite)),
        "queue=" .. queue_ids(sprite),
        "caster_label_ini=" .. tostring(get_local(sprite, "caster_label_ini")),
        "instantprep=" .. tostring(get_local(sprite, "instantprep")),
        "inafight=" .. tostring(get_local(sprite, "inafight")),
        "dialogue_gate=" .. tostring(get_local(sprite, "dialogue")),
        "cutscene_gate=" .. tostring(get_local(sprite, "cutscene")),
        "project_image_owner=" .. tostring(get_local(sprite, "project_image_owner")),
    }
    log("snapshot", table.concat(parts, " "))
    return parts
end

function probe.watch(sprite, label)
    if probe.active ~= 1 then return false end
    local id = object_id(sprite)
    if id < 0 then return false end
    probe.watches[id] = {
        sprite = sprite,
        label = tostring(label or id),
        last_see = nil,
        last_action = nil,
        last_instantprep = nil,
    }
    probe.snapshot(sprite, "watch:" .. tostring(label or id))
    return true
end

function probe.unwatch(sprite_or_id)
    local id = tonumber(sprite_or_id) or object_id(sprite_or_id)
    probe.watches[id] = nil
end

function probe.available_count(sprite, resref)
    local count = 0
    local field = list_field(resref)
    local level = spell_level(resref)
    if not (sprite and field and level and EEex_Utility_IterateCPtrList) then return nil end
    local ok = pcall(function()
        local spell_lists = sprite[field]
        local level_list = spell_lists and spell_lists:getReference(level - 1)
        if not level_list then return end
        EEex_Utility_IterateCPtrList(level_list, function(record)
            local same = normalize(record.m_spellId:get()) == normalize(resref)
            local flags = tonumber(record.m_flags)
            if same and flags and flags % 2 == 1 then count = count + 1 end
        end)
    end)
    if not ok then return nil end
    return count
end

function probe.debit_once(sprite, resref)
    if probe.active ~= 1 then return nil, "probe inactive" end
    local id = object_id(sprite)
    local key = tostring(id) .. ":" .. normalize(resref)
    if probe.debits[key] then return nil, "an unrestored debit already exists" end
    local before = probe.available_count(sprite, resref)
    local record, level = find_available_record(sprite, resref)
    if not record then return nil, "no available memorized record" end
    local old_flags = tonumber(record.m_flags)
    record.m_flags = old_flags - 1
    local rebuilt = rebuild_quick_lists(sprite, level)
    local after = probe.available_count(sprite, resref)
    if not rebuilt or before == nil or after ~= before - 1 then
        record.m_flags = old_flags
        rebuild_quick_lists(sprite, level)
        return nil, "debit did not confirm and was restored"
    end
    local token = {
        key = key,
        sprite = sprite,
        record = record,
        level = level,
        old_flags = old_flags,
        resref = normalize(resref),
    }
    probe.debits[key] = token
    log("debit", key .. " before=" .. before .. " after=" .. after)
    return key
end

function probe.restore_debit(token_key)
    local token = probe.debits[token_key]
    if not token then return false, "unknown debit token" end
    local ok = pcall(function() token.record.m_flags = token.old_flags end)
    local rebuilt = ok and rebuild_quick_lists(token.sprite, token.level)
    local restored = rebuilt and probe.available_count(token.sprite, token.resref)
    if not (ok and rebuilt and restored and restored > 0) then
        log("restore_error", tostring(token_key))
        return false, "could not confirm restoration"
    end
    probe.debits[token_key] = nil
    log("restore", tostring(token_key))
    return true
end

function probe.queue_normal_cast(sprite, resref)
    if probe.active ~= 1 then return false, "probe inactive" end
    if not EEex_Action_QueueResponseStringOnAIBase then
        return false, "queue API unavailable"
    end
    local id = object_id(sprite)
    local normalized = normalize(resref)
    local before = probe.available_count(sprite, normalized)
    probe.selected_casts[id] = {
        resref = normalized,
        queued_at = timestamp(),
        before = before,
        started = 0,
    }
    local action = string.format('SpellRES("%s",Myself)', normalized)
    local ok, err = pcall(EEex_Action_QueueResponseStringOnAIBase, action, sprite)
    if not ok then
        probe.selected_casts[id] = nil
        return false, tostring(err)
    end
    log("cast_queued", "id=" .. id .. " resref=" .. normalized
        .. " available=" .. tostring(before))
    return true
end

function probe.dump()
    local result = {}
    for index, entry in ipairs(probe.logs) do
        result[index] = string.format("%.3f\t%s\t%s",
            tonumber(entry.time) or -1, entry.kind, entry.message)
    end
    return result
end

function probe.clear_log()
    probe.logs = {}
end

local function tick_callback(sprite)
    local current = _G.CBR_RDY_PROBE
    if not current or current.active ~= 1 then return end
    local watched = current.watches[object_id(sprite)]
    if not watched then return end
    local see = sees_party(sprite)
    local action = current_action_id(sprite)
    local prep = get_local(sprite, "instantprep")
    if see ~= watched.last_see or action ~= watched.last_action
            or prep ~= watched.last_instantprep then
        probe.snapshot(sprite, "transition:" .. watched.label)
        watched.last_see = see
        watched.last_action = action
        watched.last_instantprep = prep
    end
end

local function started_action_callback(sprite, action)
    local current = _G.CBR_RDY_PROBE
    if not current or current.active ~= 1 then return end
    local id = object_id(sprite)
    local resref = action_resref(action)
    log("action_started", "id=" .. id
        .. " action=" .. tostring(action and action.m_actionID)
        .. " resref=" .. resref
        .. " queue=" .. queue_ids(sprite))
    local selected = current.selected_casts[id]
    if selected and selected.resref == resref then
        selected.started = 1
        selected.started_at = timestamp()
        selected.after_start = probe.available_count(sprite, resref)
        log("selected_cast_started", "id=" .. id .. " resref=" .. resref
            .. " before=" .. tostring(selected.before)
            .. " after=" .. tostring(selected.after_start))
    end
end

function probe.install()
    if probe.active == 1 then return true end
    if not (EEex_Opcode_AddListsResolvedListener
            and EEex_Action_AddSpriteStartedActionListener) then
        return false, "required listener APIs unavailable"
    end
    probe.generation = probe.generation + 1
    probe.active = 1
    if probe.listeners_registered ~= 1 then
        EEex_Opcode_AddListsResolvedListener(function(sprite)
            local ok, err = xpcall(function() tick_callback(sprite) end, debug.traceback)
            if not ok then log("tick_error", err) end
        end)
        EEex_Action_AddSpriteStartedActionListener(function(sprite, action)
            local ok, err = xpcall(
                function() started_action_callback(sprite, action) end, debug.traceback)
            if not ok then log("action_error", err) end
        end)
        probe.listeners_registered = 1
    end
    log("install", "generation=" .. probe.generation)
    return true
end

function probe.teardown()
    local failures = {}
    local keys = {}
    for key in pairs(probe.debits) do keys[#keys + 1] = key end
    for _, key in ipairs(keys) do
        local ok, err = probe.restore_debit(key)
        if not ok then failures[#failures + 1] = key .. ":" .. tostring(err) end
    end
    probe.active = 0
    probe.watches = {}
    probe.selected_casts = {}
    log("teardown", "restore_failures=" .. #failures)
    return #failures == 0, failures
end

return probe
