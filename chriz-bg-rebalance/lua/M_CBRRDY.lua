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

local ambient_records = {}
local ambient_by_resref = {}
local ambient_by_delivery = {}
local ambient_by_number = {}
for _, source in ipairs(manifest.ambient_spells or {}) do
    local record = {
        key = normalize(source.key),
        resref = normalize(source.resref),
        spell_number = tonumber(source.spell_number),
        delivery = normalize(source.delivery),
        duration = tonumber(source.duration),
        minimum_grade = tonumber(source.minimum_grade),
        detection_opcode = tonumber(source.detection_opcode),
        detection_parameter2 = tonumber(source.detection_parameter2),
        self_target = tonumber(source.self_target),
        defensive = tonumber(source.defensive),
    }
    if record.key ~= "" and record.resref ~= "" and record.delivery ~= ""
            and record.spell_number and record.duration
            and record.duration >= flag(manifest.minimum_duration, 2400)
            and record.minimum_grade and record.minimum_grade >= 1
            and record.detection_opcode and record.detection_parameter2
            and record.self_target == 1 and record.defensive == 1 then
        ambient_records[#ambient_records + 1] = record
        ambient_by_resref[record.resref] = record
        ambient_by_delivery[record.delivery] = record
        ambient_by_number[record.spell_number] = record
    end
end

local function value_set(value)
    local result = {}
    if type(value) == "string" then
        for token in string.gmatch(value, "[^,%s]+") do
            result[normalize(token)] = 1
        end
    elseif type(value) == "table" then
        for token, enabled in pairs(value) do
            if flag(enabled, 0) ~= 0 then result[normalize(token)] = 1 end
        end
    end
    return result
end

local actor_overrides = {}
for actor, source in pairs(manifest.overrides or {}) do
    if type(source) == "table" then
        actor_overrides[normalize(actor)] = {
            grade = tonumber(source.grade),
            include = value_set(source.include),
            exclude = value_set(source.exclude),
        }
    end
end

state.classifications = {}
state.ambient_sessions = {}
state.ambient_failures = state.ambient_failures or {}

local function object_id(sprite)
    local id = sprite and tonumber(sprite.m_id)
    if not id or id < 0 then return nil end
    return id
end

local function resolve_sprite(sprite)
    local id = object_id(sprite)
    if not id or type(EEex_GameObject_Get) ~= "function" then return nil end
    local current = EEex_GameObject_Get(id)
    if not current or object_id(current) ~= id then return nil end
    return current, id
end

local function get_local(sprite, name)
    return tonumber(EEex_Sprite_GetLocalInt(sprite, name)) or 0
end

local function actor_key(sprite)
    if not (sprite and sprite.m_scriptName) then return "" end
    return normalize(sprite.m_scriptName:get())
end

local function sees_party(sprite)
    return EEex_Trigger_EvalConditionalStringAsAIBase("See([PC])", sprite) and true or false
end

local function game_time()
    return tonumber(EEex_GameState_GetTime()) or 0
end

local function session_for(id)
    local session = state.ambient_sessions[id]
    if not session then
        session = { tick = 0, checked = {}, reimbursement = {}, pending = nil }
        state.ambient_sessions[id] = session
    end
    return session
end

local function classify(sprite, id)
    if not sprite.m_pArea or get_local(sprite, "caster_label_ini") ~= 1 then
        return nil
    end
    local key = actor_key(sprite)
    local cached = state.classifications[id]
    if key ~= "" and cached and cached.actor == key then return cached end
    local override = actor_overrides[key]
    local classification = {
        actor = key,
        eligible = 1,
        grade = override and flag(override.grade,
            flag(manifest.defaults.scs_caster_grade, 1))
            or flag(manifest.defaults.scs_caster_grade, 1),
        include = override and override.include or {},
        exclude = override and override.exclude or {},
    }
    if key ~= "" then state.classifications[id] = classification end
    return classification
end

local function classification_allows(classification, record)
    if not classification or classification.eligible ~= 1 then return false end
    if classification.exclude[record.key] or classification.exclude[record.resref] then
        return false
    end
    if classification.include[record.key] or classification.include[record.resref] then
        return true
    end
    return classification.grade >= record.minimum_grade
end

local function spell_level(resref)
    local resource = EEex_Resource_Demand(resref, "SPL")
    local level = resource and tonumber(resource.spellLevel)
    if not level or level < 1 then return nil end
    return level
end

local function spellbook_field(resref)
    local prefix = string.sub(resref, 1, 4)
    if prefix == "spwi" then return "m_memorizedSpellsMage" end
    if prefix == "sppr" then return "m_memorizedSpellsPriest" end
    return nil
end

local function available(flags)
    flags = tonumber(flags)
    if not flags then return false end
    if EEex_BAnd then return EEex_BAnd(flags, 1) ~= 0 end
    return flags % 2 == 1
end

local function find_available_record(sprite, resref)
    local field = spellbook_field(resref)
    local level = spell_level(resref)
    if not field or not level then return nil, nil end
    local lists = sprite[field]
    local list = lists and lists:getReference(level - 1)
    if not list then return nil, nil end
    local found = nil
    local ordinal = 0
    EEex_Utility_IterateCPtrList(list, function(candidate)
        ordinal = ordinal + 1
        if normalize(candidate.m_spellId:get()) == resref
                and available(candidate.m_flags) then
            found = candidate
            return true
        end
    end)
    if not found then return nil, nil end
    return found, {
        field = field,
        level = level - 1,
        ordinal = ordinal,
        resref = resref,
    }
end

local function resolve_record(sprite, token)
    if type(token) ~= "table" then return nil end
    local lists = sprite[token.field]
    local list = lists and lists:getReference(token.level)
    if not list then return nil end
    local found = nil
    local ordinal = 0
    EEex_Utility_IterateCPtrList(list, function(candidate)
        ordinal = ordinal + 1
        if ordinal == token.ordinal then
            if normalize(candidate.m_spellId:get()) == token.resref then found = candidate end
            return true
        end
    end)
    return found
end

local function available_count(sprite, resref)
    local field = spellbook_field(resref)
    local level = spell_level(resref)
    if not field or not level then return nil end
    local lists = sprite[field]
    local list = lists and lists:getReference(level - 1)
    local count = 0
    if not list then return count end
    EEex_Utility_IterateCPtrList(list, function(candidate)
        if normalize(candidate.m_spellId:get()) == resref
                and available(candidate.m_flags) then
            count = count + 1
        end
    end)
    return count
end

local function effect_source(effect)
    if not (effect and effect.m_sourceRes) then return "" end
    return normalize(effect.m_sourceRes:get())
end

local function matching_effect_active(sprite, record, delivery_only)
    local readable = false
    local found = false
    for _, field in ipairs({ "m_timedEffectList", "m_equipedEffectList" }) do
        local list = sprite[field]
        if list then
            readable = true
            EEex_Utility_IterateCPtrList(list, function(effect)
                local source = effect_source(effect)
                if tonumber(effect.m_effectId) == record.detection_opcode
                        and tonumber(effect.m_dWFlags) == record.detection_parameter2
                        and (source == record.delivery
                            or (not delivery_only and source == record.resref)) then
                    found = true
                    return true
                end
            end)
        end
    end
    if not readable then error("effect lists unavailable") end
    return found
end

local function managed_effect_active(sprite, record)
    return matching_effect_active(sprite, record, true)
end

local function defensive_effect_active(sprite, record)
    return matching_effect_active(sprite, record, false)
end

local function new_ledger()
    return { version = 1, spells = {} }
end

local function get_ledger(sprite)
    local aux = EEex_GetUDAux(sprite)
    local ledger = aux.CBR_RDY_LEDGER
    if type(ledger) ~= "table" or ledger.version ~= 1
            or type(ledger.spells) ~= "table" then
        ledger = new_ledger()
        aux.CBR_RDY_LEDGER = ledger
    end
    return ledger
end

local function failure_for(id, resref)
    local actor = state.ambient_failures[id]
    return actor and actor[resref] or nil
end

local function disable_spell(id, record, reason)
    local actor = state.ambient_failures[id]
    if not actor then
        actor = {}
        state.ambient_failures[id] = actor
    end
    if not actor[record.resref] then
        actor[record.resref] = { disabled = 1, attempts = 1 }
        print("[CBR Ready] ambient spell disabled for this session: "
            .. record.resref .. " (" .. tostring(reason) .. ")")
    end
end

local function apply_delivery(sprite, id, record)
    EEex_GameObject_ApplyEffect(sprite, {
        effectID = 146,
        targetType = 1,
        dwFlags = 1,
        res = record.delivery,
        noSave = 1,
        immediateResolve = 1,
        sourceID = id,
        sourceTarget = id,
        m_sourceRes = record.delivery,
    })
    return managed_effect_active(sprite, record)
end

local function apply_first(sprite, id, record, ledger, session)
    local spell_record, token = find_available_record(sprite, record.resref)
    if not spell_record then return false end
    local before = available_count(sprite, record.resref)
    if not before or before < 1 then return false end
    if not apply_delivery(sprite, id, record) then
        disable_spell(id, record, "delivery effect was not confirmed")
        return false
    end

    local old_flags = tonumber(spell_record.m_flags)
    spell_record.m_flags = old_flags - 1
    local quick_ok, quick_result = pcall(
        update_quick_lists, sprite, record.resref, -1)
    local after = available_count(sprite, record.resref)
    if not quick_ok or not quick_result or after ~= before - 1 then
        spell_record.m_flags = old_flags
        pcall(update_quick_lists, sprite, record.resref, 1)
        local restored = available_count(sprite, record.resref)
        disable_spell(id, record, restored == before
            and "slot debit failed and was restored"
            or "slot debit restoration could not be confirmed")
        return false
    end

    ledger.spells[record.resref] = {
        version = 1,
        resref = record.resref,
        charged = 1,
        expected_expiry = game_time() + record.duration,
        suppressed = 0,
    }
    session.reimbursement[record.resref] = {
        eligible = get_local(sprite, "instantprep") == 0 and 1 or 0,
        token = token,
    }
    return true
end

local function maintain(sprite, id, record, ledger_record, visible)
    if ledger_record.suppressed == 1 or managed_effect_active(sprite, record) then
        return
    end
    local now = game_time()
    if now + 6 < ledger_record.expected_expiry then
        ledger_record.suppressed = 1
        return
    end
    if visible or get_local(sprite, "inafight") ~= 0 then return end
    if apply_delivery(sprite, id, record) then
        ledger_record.expected_expiry = now + record.duration
    else
        disable_spell(id, record, "maintenance delivery was not confirmed")
    end
end

local function ambient_tick(sprite)
    local current, id = resolve_sprite(sprite)
    if not current then return end
    local visible = sees_party(current)
    local classification = classify(current, id)
    if not classification then return end
    local session = session_for(id)
    session.tick = session.tick + 1
    local cadence = flag(manifest.maintenance_cadence_ticks, 15)
    local maintenance_tick = cadence > 0 and session.tick % cadence == 0
    local ledger = get_ledger(current)
    for _, record in ipairs(ambient_records) do
        if classification_allows(classification, record)
                and not failure_for(id, record.resref) then
            local ledger_record = ledger.spells[record.resref]
            if ledger_record and ledger_record.charged == 1 then
                if maintenance_tick then
                    maintain(current, id, record, ledger_record, visible)
                end
            elseif session.checked[record.resref] ~= 1 then
                session.checked[record.resref] = 1
                local spell_record = find_available_record(current, record.resref)
                if spell_record and not defensive_effect_active(current, record) then
                    apply_first(current, id, record, ledger, session)
                end
            end
        end
    end
end

local function restore_component_record(sprite, token, resref, expected_before)
    local spell_record = resolve_record(sprite, token)
    if not spell_record or available(spell_record.m_flags) then return false end
    spell_record.m_flags = tonumber(spell_record.m_flags) + 1
    local ok, result = pcall(update_quick_lists, sprite, resref, 1)
    return ok and result and available_count(sprite, resref) == expected_before
end

local function ambient_action(sprite, action)
    local current, id = resolve_sprite(sprite)
    if not current then return end
    local session = session_for(id)
    local action_id = tonumber(action and action.m_actionID)
    local pending = session.pending
    session.pending = nil

    if pending and action_id == 147
            and tonumber(action.m_specificID) == pending.spell_number then
        local after = available_count(current, pending.resref)
        if after == pending.available_before - 1
                and restore_component_record(current, pending.token,
                    pending.resref, pending.available_before) then
            session.reimbursement[pending.resref] = nil
        elseif after == pending.available_before - 1 then
            disable_spell(id, ambient_by_resref[pending.resref],
                "initial SCS reimbursement restoration failed")
        end
        return
    end

    if action_id ~= 181 then return end
    local record = ambient_by_delivery[action_resref(action)]
    local reimbursement = record and session.reimbursement[record.resref]
    local ledger_record = record and get_ledger(current).spells[record.resref]
    if not (record and reimbursement and reimbursement.eligible == 1
            and ledger_record and ledger_record.charged == 1
            and get_local(current, "instantprep") == 0
            and managed_effect_active(current, record)) then
        return
    end
    local before = available_count(current, record.resref)
    if not before or before < 1 then return end
    session.pending = {
        resref = record.resref,
        spell_number = record.spell_number,
        available_before = before,
        token = reimbursement.token,
    }
end

local function ambient_reset(sprite)
    local current, id = resolve_sprite(sprite)
    if not current then return end
    EEex_GetUDAux(current).CBR_RDY_LEDGER = new_ledger()
    state.ambient_sessions[id] = nil
end

local function copy_ledger(sprite)
    local source = get_ledger(sprite)
    local result = new_ledger()
    for resref, record in pairs(source.spells) do
        if ambient_by_resref[resref] and type(record) == "table" then
            result.spells[resref] = {
                version = 1,
                resref = resref,
                charged = flag(record.charged, 0),
                expected_expiry = tonumber(record.expected_expiry) or 0,
                suppressed = flag(record.suppressed, 0),
            }
        end
    end
    return result
end

local function import_ledger(sprite, saved)
    local current, id = resolve_sprite(sprite)
    if not current then return end
    local result = new_ledger()
    if type(saved) == "table" and saved.version == 1
            and type(saved.spells) == "table" then
        for key, record in pairs(saved.spells) do
            local resref = normalize(key)
            local valid = ambient_by_resref[resref]
                and type(record) == "table"
                and record.version == 1
                and normalize(record.resref) == resref
                and (record.charged == 0 or record.charged == 1)
                and type(record.expected_expiry) == "number"
                and (record.suppressed == 0 or record.suppressed == 1)
            if valid then
                result.spells[resref] = {
                    version = 1,
                    resref = resref,
                    charged = record.charged,
                    expected_expiry = record.expected_expiry,
                    suppressed = record.suppressed,
                }
            elseif ambient_by_resref[resref] then
                disable_spell(id, ambient_by_resref[resref], "malformed saved ledger")
            end
        end
    end
    EEex_GetUDAux(current).CBR_RDY_LEDGER = result
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
    ambient_tick = ambient_tick,
    ambient_action = ambient_action,
    ambient_reset = ambient_reset,
    ambient_export = copy_ledger,
    ambient_import = import_ledger,
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
    EEex_GameObject_Get,
    EEex_GetUDAux,
    EEex_Sprite_GetLocalInt,
    EEex_Trigger_EvalConditionalStringAsAIBase,
    EEex_GameState_GetTime,
    EEex_Resource_Demand,
    EEex_Utility_IterateCPtrList,
    EEex_GameObject_ApplyEffect,
    EEex_RunWithStackManager,
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
