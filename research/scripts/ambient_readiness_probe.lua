-- Session-only EEex capability probe for component 121.
--
-- Loading this file only defines the probe.  Nothing is registered until
-- CBR_RDY_PROBE.install() is called, and no slot is changed unless the caller
-- explicitly invokes debit_once().  teardown() makes the append-only
-- callbacks inert and attempts to restore every outstanding controlled debit.
-- Logs live only in this Lua process and are returned by dump() as raw engine
-- ticks, derived seconds, kind, and message; this script never writes a
-- resource, save, or file.

_G.CBR_RDY_PROBE = _G.CBR_RDY_PROBE or {}
local probe = _G.CBR_RDY_PROBE

probe.version = 1
probe.active = probe.active or 0
probe.generation = probe.generation or 0
probe.listeners_registered = probe.listeners_registered or 0
probe.reset_listener_registered = probe.reset_listener_registered or 0
probe.logs = probe.logs or {}
probe.watches = probe.watches or {}
probe.debits = probe.debits or {}
probe.selected_casts = probe.selected_casts or {}

local GAME_TIME_TICKS_PER_SECOND = 15

local tick_listener_mode
local add_tick_listener
if type(EEex_Opcode_AddDeferredListsResolvedListener) == "function" then
    tick_listener_mode = "deferred"
    add_tick_listener = EEex_Opcode_AddDeferredListsResolvedListener
elseif type(EEex_Opcode_AddListsResolvedListener) == "function" then
    tick_listener_mode = "legacy"
    add_tick_listener = EEex_Opcode_AddListsResolvedListener
end
probe.tick_listener_mode = tick_listener_mode or "unsupported"

local function game_time_ticks()
    local ok, value = pcall(function()
        local world_time =
            EngineGlobals.g_pBaldurChitin.m_pObjectGame.m_worldTime
        if tick_listener_mode == "deferred" then
            return world_time:GetCurrentTime()
        end
        if tick_listener_mode == "legacy" then
            return world_time.m_gameTime
        end
        error("no supported EEex tick listener")
    end)
    local ticks = ok and tonumber(value) or nil
    if not ticks or ticks < 0 then
        error("selected EEex world-time binding is unavailable")
    end
    return ticks
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
    local ticks = game_time_ticks()
    probe.logs[#probe.logs + 1] = {
        time_ticks = ticks,
        time_seconds = ticks / GAME_TIME_TICKS_PER_SECOND,
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
        if action.m_string1 and action.m_string1.m_pchData then
            return action.m_string1.m_pchData:get()
        end
        return ""
    end)
    if ok then return normalize(value) end
    return ""
end

local function queue_ids(sprite)
    local result = {}
    local ok = pcall(function()
        if not (sprite and sprite.m_queuedActions and EEex_Utility_IterateCPtrList) then
            error("queued actions unavailable")
        end
        EEex_Utility_IterateCPtrList(sprite.m_queuedActions, function(action)
            result[#result + 1] = tostring(action.m_actionID)
        end)
    end)
    if not ok then return "<unavailable>" end
    return table.concat(result, ",")
end

local function project_image_relation(sprite)
    if not (sprite and EEex_Utility_IterateCPtrList and EEex_Sprite_GetState) then
        return "<unavailable>"
    end
    local state = nil
    local clone_owner = nil
    local owner_lock = false
    local ok = pcall(function()
        state = EEex_Sprite_GetState(sprite)
        EEex_Utility_IterateCPtrList(sprite.m_timedEffectList, function(effect)
            if effect.m_effectId == 237 and effect.m_dWFlags == 2 then
                clone_owner = tonumber(effect.m_sourceId)
            end
            local source = ""
            if effect.m_sourceRes then source = normalize(effect.m_sourceRes:get()) end
            if source == "spwi703"
                    and ((effect.m_effectId == 233
                            and effect.m_effectAmount == 2
                            and effect.m_dWFlags == 127)
                        or effect.m_effectId == 20) then
                owner_lock = true
            end
        end)
    end)
    if not ok then return "<unavailable>" end
    if clone_owner and clone_owner >= 0 then
        return "clone:owner=" .. tostring(clone_owner)
    end
    if owner_lock then
        return "owner_locked:state=" .. tostring(state)
    end
    return "none:state=" .. tostring(state)
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

local function update_quick_lists(sprite, resref, change_amount)
    if not (sprite and sprite.CheckQuickLists and EEex_RunWithStackManager) then
        return false
    end
    local ok = pcall(function()
        EEex_RunWithStackManager({
            { ["name"] = "abilityId", ["struct"] = "CAbilityId" },
        }, function(manager)
            local abilityId = manager:getUD("abilityId")
            abilityId.m_itemType = 1
            abilityId.m_res:set(resref)
            sprite:CheckQuickLists(abilityId, change_amount, 0, 0)
        end)
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
        "project_image=" .. project_image_relation(sprite),
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
    local rebuilt = update_quick_lists(sprite, resref, -1)
    local after = probe.available_count(sprite, resref)
    if not rebuilt or before == nil or after ~= before - 1 then
        record.m_flags = old_flags
        update_quick_lists(sprite, resref, 1)
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
    local rebuilt = ok and update_quick_lists(token.sprite, token.resref, 1)
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
    local queued_ticks = game_time_ticks()
    probe.selected_casts[id] = {
        resref = normalized,
        queued_at_ticks = queued_ticks,
        queued_at_seconds = queued_ticks / GAME_TIME_TICKS_PER_SECOND,
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
        result[index] = string.format("%.0f\t%.3f\t%s\t%s",
            tonumber(entry.time_ticks) or -1,
            tonumber(entry.time_seconds) or -1,
            entry.kind, entry.message)
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
        .. " specific=" .. tostring(action and action.m_specificID)
        .. " resref=" .. resref
        .. " queue=" .. queue_ids(sprite))
    local selected = current.selected_casts[id]
    if selected and selected.resref == resref then
        local started_ticks = game_time_ticks()
        selected.started = 1
        selected.started_at_ticks = started_ticks
        selected.started_at_seconds =
            started_ticks / GAME_TIME_TICKS_PER_SECOND
        selected.after_start = probe.available_count(sprite, resref)
        log("selected_cast_started", "id=" .. id .. " resref=" .. resref
            .. " before=" .. tostring(selected.before)
            .. " after=" .. tostring(selected.after_start))
    end
end

local function reset_callback(sprite)
    local current = _G.CBR_RDY_PROBE
    if not current or current.active ~= 1 then return end
    log("spellbook_reset", "id=" .. object_id(sprite))
end

function probe.install()
    if not (add_tick_listener
            and EEex_Action_AddSpriteStartedActionListener
            and EEex_Sprite_AddQuickListCountsResetListener) then
        return false, "required listener APIs unavailable"
    end
    local clock_ok = pcall(game_time_ticks)
    if not clock_ok then return false, "world-time binding unavailable" end
    local activating = probe.active ~= 1
    if activating then
        probe.generation = probe.generation + 1
        probe.active = 1
    end
    if probe.listeners_registered ~= 1 then
        add_tick_listener(function(sprite)
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
    if probe.reset_listener_registered ~= 1 then
        EEex_Sprite_AddQuickListCountsResetListener(function(sprite)
            local ok, err = xpcall(
                function() reset_callback(sprite) end, debug.traceback)
            if not ok then log("reset_error", err) end
        end)
        probe.reset_listener_registered = 1
    end
    if activating then log("install", "generation=" .. probe.generation) end
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
