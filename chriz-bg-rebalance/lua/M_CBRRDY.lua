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

local project_image_resref = normalize(manifest.project_image_resref)
local project_image_identity_supported = #project_image_resref >= 1
    and #project_image_resref <= 8
    and string.match(project_image_resref, "^[a-z0-9_#]+$") ~= nil

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
    generation = 0,
}
local state = _G.CBR_RDY_STATE
state.generation = flag(state.generation, 0) + 1

-- EEex v1.2 coalesces scheduling through the deferred listener.  Its legacy
-- synchronous listener is retained as a confirmation-only boundary for child
-- spell effects.  Older releases use one synchronous full scheduler instead.
local tick_listener_mode
local add_tick_listener
if type(EEex_Opcode_AddDeferredListsResolvedListener) == "function" then
    tick_listener_mode = "deferred"
    add_tick_listener = EEex_Opcode_AddDeferredListsResolvedListener
elseif type(EEex_Opcode_AddListsResolvedListener) == "function" then
    tick_listener_mode = "legacy"
    add_tick_listener = EEex_Opcode_AddListsResolvedListener
end
state.tick_listener_mode = tick_listener_mode or "unsupported"

local confirmation_listener_mode
local add_confirmation_listener
if tick_listener_mode == "deferred" then
    if type(EEex_Opcode_AddListsResolvedListener) == "function" then
        confirmation_listener_mode = "synchronous"
        add_confirmation_listener = EEex_Opcode_AddListsResolvedListener
    else
        confirmation_listener_mode = "unsupported"
    end
elseif tick_listener_mode == "legacy" then
    confirmation_listener_mode = "not_required"
else
    confirmation_listener_mode = "unsupported"
end
state.confirmation_listener_mode = confirmation_listener_mode
state.confirmation_listener_registered =
    flag(_G.CBR_RDY_AMBIENT_CONFIRMATION_LISTENER_REGISTERED, 0)

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

local passive_action = { [0] = 1, [23] = 1, [85] = 1 }

local function passive_actions_only(sprite)
    if not (sprite and sprite.m_queuedActions and EEex_Utility_IterateCPtrList) then
        return false
    end
    local current_id = sprite.m_curAction and tonumber(sprite.m_curAction.m_actionID)
    if not current_id or not passive_action[current_id] then return false end
    local safe = true
    EEex_Utility_IterateCPtrList(sprite.m_queuedActions, function(action)
        local action_id = action and tonumber(action.m_actionID)
        if not action_id or not passive_action[action_id] then safe = false end
    end)
    return safe
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

local urgent_records = {}
local urgent_by_resref = {}
for _, source in ipairs(manifest.urgent_candidates or {}) do
    local record = {
        key = normalize(source.key),
        resref = normalize(source.resref),
        spell_number = tonumber(source.spell_number),
        genuine = flag(source.genuine_weapon_immunity, 0),
    }
    if record.key ~= "" and record.resref ~= "" and record.spell_number then
        urgent_records[#urgent_records + 1] = record
        urgent_by_resref[record.resref] = record
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

local GAME_TIME_TICKS_PER_SECOND = 15

local function seconds_to_game_ticks(seconds)
    return flag(seconds, 0) * GAME_TIME_TICKS_PER_SECOND
end

local function game_time_ticks()
    local ok, value = pcall(function()
        local world_time =
            EngineGlobals.g_pBaldurChitin.m_pObjectGame.m_worldTime
        if tick_listener_mode ~= "deferred"
                and tick_listener_mode ~= "legacy" then
            error("no supported EEex tick listener")
        end
        return world_time.m_gameTime
    end)
    local ticks = ok and tonumber(value) or nil
    if not ticks or ticks < 0 then
        error("selected EEex world-time binding is unavailable")
    end
    return ticks
end

local function sprite_nonce(sprite)
    local aux = EEex_GetUDAux(sprite)
    local nonce = tonumber(aux.CBR_RDY_SESSION_NONCE)
    if not nonce or nonce < 1 then
        state.next_sprite_nonce = flag(state.next_sprite_nonce, 0) + 1
        nonce = state.next_sprite_nonce
        aux.CBR_RDY_SESSION_NONCE = nonce
    end
    return nonce
end

local function new_session(nonce)
    return {
        nonce = nonce,
        tick = 0,
        checked = {},
        delivery_pending = {},
        pending = nil,
    }
end

local function session_for(sprite, id)
    local nonce = sprite_nonce(sprite)
    local session = state.ambient_sessions[id]
    if not session or session.nonce ~= nonce then
        session = new_session(nonce)
        state.ambient_sessions[id] = session
    end
    return session
end

local function existing_session_for(sprite, id)
    local session = state.ambient_sessions[id]
    if not session then return nil end
    local aux = EEex_TryGetUDAux(sprite)
    local nonce = aux and tonumber(aux.CBR_RDY_SESSION_NONCE) or nil
    if not nonce or nonce ~= session.nonce then
        state.ambient_sessions[id] = nil
        return nil
    end
    return session
end

local function classify(sprite, id)
    if not sprite.m_pArea or get_local(sprite, "caster_label_ini") ~= 1 then
        return nil
    end
    local key = actor_key(sprite)
    local nonce = sprite_nonce(sprite)
    local cached = state.classifications[id]
    if key ~= "" and cached and cached.actor == key
            and cached.nonce == nonce then return cached end
    local override = actor_overrides[key]
    local classification = {
        actor = key,
        nonce = nonce,
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
    local lists = {}
    local found = false
    for _, field in ipairs({ "m_timedEffectList", "m_equipedEffectList" }) do
        local list = sprite[field]
        if not list then error("effect lists unavailable") end
        lists[#lists + 1] = list
    end
    for _, list in ipairs(lists) do
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
    return found
end

local function managed_effect_active(sprite, record)
    return matching_effect_active(sprite, record, true)
end

local function defensive_effect_active(sprite, record)
    return matching_effect_active(sprite, record, false)
end

local LEDGER_VERSION = 2

local function integer(value)
    return type(value) == "number" and value == math.floor(value)
end

local function finite_nonnegative(value)
    return type(value) == "number" and value == value
        and value >= 0 and value ~= math.huge
end

local function clear_reimbursement(record)
    record.reimbursement_eligible = 0
    record.token_field = ""
    record.token_level = -1
    record.token_ordinal = 0
    record.token_resref = ""
    record.original_flags = 0
    record.debited_flags = 0
end

local function new_ledger()
    return { version = LEDGER_VERSION, spells = {} }
end

local function migrate_v1_record(resref, record)
    if type(record) ~= "table" or record.version ~= 1
            or normalize(record.resref) ~= resref
            or record.charged ~= 1
            or not finite_nonnegative(record.expected_expiry)
            or (record.suppressed ~= 0 and record.suppressed ~= 1) then
        return nil
    end
    local result = {
        version = LEDGER_VERSION,
        resref = resref,
        charged = record.charged,
        expected_expiry = record.expected_expiry,
        suppressed = record.suppressed,
    }
    clear_reimbursement(result)
    return result
end

local function get_ledger(sprite)
    local aux = EEex_GetUDAux(sprite)
    local ledger = aux.CBR_RDY_LEDGER
    if type(ledger) == "table" and ledger.version == 1
            and type(ledger.spells) == "table" then
        local migrated = new_ledger()
        for key, record in pairs(ledger.spells) do
            local resref = normalize(key)
            local converted = ambient_by_resref[resref]
                and migrate_v1_record(resref, record)
            if converted then migrated.spells[resref] = converted end
        end
        ledger = migrated
        aux.CBR_RDY_LEDGER = ledger
    end
    if type(ledger) ~= "table" or ledger.version ~= LEDGER_VERSION
            or type(ledger.spells) ~= "table" then
        ledger = new_ledger()
        aux.CBR_RDY_LEDGER = ledger
    end
    return ledger
end

local function failure_for(sprite, id, resref)
    local nonce = sprite_nonce(sprite)
    local actor = state.ambient_failures[id]
    return actor and actor.nonce == nonce and actor.spells[resref] or nil
end

local function disable_spell(sprite, id, record, reason)
    local nonce = sprite_nonce(sprite)
    local actor = state.ambient_failures[id]
    if not actor or actor.nonce ~= nonce then
        actor = { nonce = nonce, spells = {} }
        state.ambient_failures[id] = actor
    end
    if not actor.spells[record.resref] then
        actor.spells[record.resref] = {
            disabled = 1,
            attempts = 1,
            reason = tostring(reason),
        }
        print("[CBR Ready] ambient spell disabled for this session: "
            .. record.resref .. " (" .. tostring(reason) .. ")")
    end
end

local function request_delivery(sprite, id, record)
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
end

local DELIVERY_CONFIRM_TIMEOUT_TICKS = seconds_to_game_ticks(2)

local ACTION_CONFIRM_TIMEOUT_TICKS = seconds_to_game_ticks(2)

local function make_ledger_record(record, requested_at)
    local result = {
        version = LEDGER_VERSION,
        resref = record.resref,
        charged = 1,
        expected_expiry = requested_at
            + seconds_to_game_ticks(record.duration),
        suppressed = 0,
    }
    clear_reimbursement(result)
    return result
end

local function reimbursement_token(ledger_record, resref)
    local level = spell_level(resref)
    if type(ledger_record) ~= "table"
            or ledger_record.reimbursement_eligible ~= 1
            or ledger_record.token_field ~= spellbook_field(resref)
            or not integer(ledger_record.token_level)
            or not level or ledger_record.token_level ~= level - 1
            or not integer(ledger_record.token_ordinal)
            or ledger_record.token_ordinal < 1
            or normalize(ledger_record.token_resref) ~= resref
            or not integer(ledger_record.original_flags)
            or ledger_record.original_flags < 1
            or not available(ledger_record.original_flags)
            or not integer(ledger_record.debited_flags)
            or ledger_record.debited_flags ~= ledger_record.original_flags - 1
            or available(ledger_record.debited_flags) then
        return nil
    end
    return {
        field = ledger_record.token_field,
        level = ledger_record.token_level,
        ordinal = ledger_record.token_ordinal,
        resref = resref,
    }
end

local function valid_v2_record(resref, record)
    if type(record) ~= "table" or record.version ~= LEDGER_VERSION
            or normalize(record.resref) ~= resref
            or record.charged ~= 1
            or not finite_nonnegative(record.expected_expiry)
            or (record.suppressed ~= 0 and record.suppressed ~= 1)
            or (record.reimbursement_eligible ~= 0
                and record.reimbursement_eligible ~= 1) then
        return false
    end
    if record.reimbursement_eligible == 1 then
        return reimbursement_token(record, resref) ~= nil
    end
    return record.token_field == ""
        and record.token_level == -1
        and record.token_ordinal == 0
        and record.token_resref == ""
        and record.original_flags == 0
        and record.debited_flags == 0
end

local function debit_confirmed_delivery(sprite, id, record, ledger, pending)
    if ledger.spells[record.resref] then
        disable_spell(sprite, id, record,
            "ledger changed before delivery confirmation")
        return false
    end
    local spell_record = resolve_record(sprite, pending.token)
    local current_flags = spell_record and tonumber(spell_record.m_flags) or nil
    local before = available_count(sprite, record.resref)
    if not current_flags or current_flags ~= pending.original_flags
            or not available(current_flags)
            or before ~= pending.available_before then
        disable_spell(sprite, id, record,
            "spell slot changed before delivery confirmation")
        return false
    end

    local debited_flags = pending.original_flags - 1
    spell_record.m_flags = debited_flags
    local quick_ok, quick_result = pcall(
        update_quick_lists, sprite, record.resref, -1)
    local after = available_count(sprite, record.resref)
    if not quick_ok or not quick_result
            or tonumber(spell_record.m_flags) ~= debited_flags
            or after ~= pending.available_before - 1 then
        if tonumber(spell_record.m_flags) == debited_flags then
            spell_record.m_flags = pending.original_flags
            pcall(update_quick_lists, sprite, record.resref, 1)
        end
        local restored = tonumber(spell_record.m_flags) == pending.original_flags
            and available_count(sprite, record.resref) == pending.available_before
        disable_spell(sprite, id, record, restored
            and "slot debit failed and was restored"
            or "slot debit restoration could not be confirmed")
        return false
    end

    local ledger_record = make_ledger_record(record, pending.requested_at)
    if pending.reimbursement_eligible == 1 then
        ledger_record.reimbursement_eligible = 1
        ledger_record.token_field = pending.token.field
        ledger_record.token_level = pending.token.level
        ledger_record.token_ordinal = pending.token.ordinal
        ledger_record.token_resref = pending.token.resref
        ledger_record.original_flags = pending.original_flags
        ledger_record.debited_flags = debited_flags
    end
    ledger.spells[record.resref] = ledger_record
    return true
end

local function preconfirm_holds_delivery(session, resref)
    local pending = session.pending
    return pending and pending.resref == resref
        and (pending.stage == "preconfirm_delivery_started"
            or (pending.stage == "remove_started" and pending.preconfirm == 1))
end

local function confirm_pending_delivery(sprite, id, record, ledger, session,
        now, allow_timeout)
    local pending = session.delivery_pending[record.resref]
    if not pending then return false end
    if managed_effect_active(sprite, record) then
        if pending.kind == "first"
                and preconfirm_holds_delivery(session, record.resref) then
            return true
        end
        session.delivery_pending[record.resref] = nil
        if pending.kind == "first" then
            debit_confirmed_delivery(sprite, id, record, ledger, pending)
        elseif pending.kind == "maintenance" then
            local ledger_record = ledger.spells[record.resref]
            if ledger_record and ledger_record.charged == 1
                    and ledger_record.suppressed == 0
                    and ledger_record.expected_expiry
                        == pending.expected_expiry_before then
                ledger_record.expected_expiry = pending.requested_at
                    + seconds_to_game_ticks(record.duration)
            else
                disable_spell(sprite, id, record,
                    "ledger changed before maintenance confirmation")
            end
        else
            disable_spell(sprite, id, record,
                "unknown pending delivery transaction")
        end
        return true
    end
    if allow_timeout and now >= pending.deadline then
        session.delivery_pending[record.resref] = nil
        disable_spell(sprite, id, record,
            pending.kind == "maintenance"
                and "maintenance delivery confirmation timed out"
                or "first delivery confirmation timed out")
    end
    return true
end

local function begin_delivery(sprite, id, record, ledger, session, pending, now)
    pending.requested_at = now
    pending.deadline = now + DELIVERY_CONFIRM_TIMEOUT_TICKS
    session.delivery_pending[record.resref] = pending
    local ok, delivery_error = pcall(request_delivery, sprite, id, record)
    if not ok then
        session.delivery_pending[record.resref] = nil
        error(delivery_error)
    end
    confirm_pending_delivery(
        sprite, id, record, ledger, session, now, false)
end

local function apply_first(sprite, id, record, ledger, session, now)
    local spell_record, token = find_available_record(sprite, record.resref)
    if not spell_record then return false end
    local before = available_count(sprite, record.resref)
    if not before or before < 1 then return false end
    local original_flags = tonumber(spell_record.m_flags)
    if not original_flags or not available(original_flags) then return false end
    begin_delivery(sprite, id, record, ledger, session, {
        kind = "first",
        token = token,
        available_before = before,
        original_flags = original_flags,
        reimbursement_eligible =
            get_local(sprite, "instantprep") == 0 and 1 or 0,
    }, now)
    return true
end

local function maintain(sprite, id, record, ledger, ledger_record, session,
        visible, now)
    if ledger_record.suppressed == 1 or managed_effect_active(sprite, record) then
        return
    end
    if now + seconds_to_game_ticks(6) < ledger_record.expected_expiry then
        ledger_record.suppressed = 1
        return
    end
    if visible or get_local(sprite, "inafight") ~= 0 then return end
    begin_delivery(sprite, id, record, ledger, session, {
        kind = "maintenance",
        expected_expiry_before = ledger_record.expected_expiry,
    }, now)
end

local function strict_restore_component_record(sprite, ledger_record, resref,
        expected_before)
    local token = reimbursement_token(ledger_record, resref)
    local spell_record = token and resolve_record(sprite, token) or nil
    if not spell_record
            or tonumber(spell_record.m_flags) ~= ledger_record.debited_flags then
        return false
    end
    spell_record.m_flags = ledger_record.original_flags
    local quick_ok, quick_result = pcall(
        update_quick_lists, sprite, resref, 1)
    if quick_ok and quick_result
            and tonumber(spell_record.m_flags) == ledger_record.original_flags
            and available_count(sprite, resref) == expected_before then
        return true
    end

    if tonumber(spell_record.m_flags) == ledger_record.original_flags then
        spell_record.m_flags = ledger_record.debited_flags
        pcall(update_quick_lists, sprite, resref, -1)
    end
    return false
end

local function disable_action_state(sprite, id, record, ledger_record, reason)
    if ledger_record then clear_reimbursement(ledger_record) end
    disable_spell(sprite, id, record, reason)
end

local function commit_scs_paid_delivery(sprite, id, record, ledger, session,
        action_pending)
    local delivery = session.delivery_pending[record.resref]
    if not delivery or delivery.kind ~= "first"
            or delivery.reimbursement_eligible ~= 1
            or ledger.spells[record.resref]
            or not managed_effect_active(sprite, record)
            or available_count(sprite, record.resref)
                ~= action_pending.available_before - 1 then
        return false
    end
    session.delivery_pending[record.resref] = nil
    ledger.spells[record.resref] =
        make_ledger_record(record, delivery.requested_at)
    return true
end

local function reconcile_action_state(sprite, id, ledger, session, now,
        action_start)
    local pending = session.pending
    if not pending then return nil end
    if pending.stage == "delivery_started"
            or pending.stage == "preconfirm_delivery_started" then
        if not action_start and now >= pending.deadline then
            session.pending = nil
            return pending.preconfirm == 1 and pending.resref or nil
        end
        return nil
    end
    if pending.stage ~= "remove_started" then
        session.pending = nil
        return pending.preconfirm == 1 and pending.resref or nil
    end

    local record = ambient_by_resref[pending.resref]
    local after = record and available_count(sprite, pending.resref) or nil
    if not record or not after then
        session.pending = nil
        if record then
            session.delivery_pending[pending.resref] = nil
            disable_action_state(sprite, id, record,
                ledger.spells[pending.resref],
                "SCS reimbursement state became unreadable")
        end
        return nil
    end

    if after == pending.available_before - 1 then
        if pending.preconfirm == 1 then
            if commit_scs_paid_delivery(
                    sprite, id, record, ledger, session, pending) then
                session.pending = nil
            elseif action_start or now >= pending.deadline then
                session.pending = nil
                session.delivery_pending[pending.resref] = nil
                disable_spell(sprite, id, record,
                    "initial SCS delivery could not be confirmed")
            end
        else
            local ledger_record = ledger.spells[pending.resref]
            local restored = ledger_record
                and strict_restore_component_record(
                    sprite, ledger_record, pending.resref,
                    pending.available_before)
            if ledger_record then clear_reimbursement(ledger_record) end
            session.pending = nil
            if not restored then
                disable_spell(sprite, id, record,
                    "initial SCS reimbursement restoration failed")
            end
        end
    elseif after == pending.available_before then
        if action_start or now >= pending.deadline then
            session.pending = nil
            return pending.preconfirm == 1 and pending.resref or nil
        end
    else
        session.pending = nil
        if pending.preconfirm == 1 then
            session.delivery_pending[pending.resref] = nil
        end
        disable_action_state(sprite, id, record,
            ledger.spells[pending.resref],
            "unexpected slot delta during SCS reimbursement")
    end
    return nil
end

local function confirm_existing_deliveries(sprite, id, ledger, session, now,
        allow_timeout)
    for resref in pairs(session.delivery_pending) do
        local record = ambient_by_resref[resref]
        if record then
            confirm_pending_delivery(
                sprite, id, record, ledger, session, now, allow_timeout)
        else
            session.delivery_pending[resref] = nil
        end
    end
end

local function ambient_tick(sprite)
    local current, id = resolve_sprite(sprite)
    if not current then return end
    local now = game_time_ticks()
    local session = existing_session_for(current, id)
    local ledger = session and get_ledger(current) or nil
    if session then
        reconcile_action_state(current, id, ledger, session, now, false)
        confirm_existing_deliveries(
            current, id, ledger, session, now, true)
    end

    local classification = classify(current, id)
    if not classification then return end
    if not session then
        session = session_for(current, id)
        ledger = get_ledger(current)
    end
    session.tick = session.tick + 1
    local cadence = flag(manifest.maintenance_cadence_ticks, 15)
    local maintenance_tick = cadence > 0 and session.tick % cadence == 0
    local visible = nil
    for _, record in ipairs(ambient_records) do
        if classification_allows(classification, record)
                and not failure_for(current, id, record.resref)
                and not session.delivery_pending[record.resref] then
            local ledger_record = ledger.spells[record.resref]
            if ledger_record and ledger_record.charged == 1 then
                if maintenance_tick then
                    if visible == nil then visible = sees_party(current) end
                    maintain(current, id, record, ledger, ledger_record,
                        session, visible, now)
                end
            elseif session.checked[record.resref] ~= 1 then
                session.checked[record.resref] = 1
                local spell_record = find_available_record(current, record.resref)
                if spell_record and not defensive_effect_active(current, record) then
                    apply_first(current, id, record, ledger, session, now)
                end
            end
        end
    end
end

local function ambient_confirm(sprite)
    local id = object_id(sprite)
    local raw_session = id and state.ambient_sessions[id] or nil
    if not raw_session then return end
    if not raw_session.pending
            and next(raw_session.delivery_pending) == nil then return end
    local current, resolved_id = resolve_sprite(sprite)
    if not current then return end
    local now = game_time_ticks()
    local session = existing_session_for(current, resolved_id)
    if not session then return end
    local ledger = get_ledger(current)
    reconcile_action_state(current, resolved_id, ledger, session, now, false)
    confirm_existing_deliveries(
        current, resolved_id, ledger, session, now, false)
end

local function pending_slot_unchanged(sprite, record, pending)
    local spell_record = resolve_record(sprite, pending.token)
    return spell_record
        and tonumber(spell_record.m_flags) == pending.original_flags
        and available(pending.original_flags)
        and available_count(sprite, record.resref) == pending.available_before
end

local function recover_reimbursement_session(sprite, id, record)
    local aux = EEex_TryGetUDAux(sprite)
    local ledger = aux and aux.CBR_RDY_LEDGER or nil
    local ledger_record = type(ledger) == "table"
        and ledger.version == LEDGER_VERSION
        and type(ledger.spells) == "table"
        and ledger.spells[record.resref] or nil
    if not valid_v2_record(record.resref, ledger_record) then return nil, nil end

    local token = reimbursement_token(ledger_record, record.resref)
    local spell_record = token and resolve_record(sprite, token) or nil
    if not spell_record
            or tonumber(spell_record.m_flags) ~= ledger_record.debited_flags then
        return nil, nil
    end

    local nonce = tonumber(aux.CBR_RDY_SESSION_NONCE)
    if not integer(nonce) or nonce < 1 then
        state.next_sprite_nonce = flag(state.next_sprite_nonce, 0) + 1
        nonce = state.next_sprite_nonce
        aux.CBR_RDY_SESSION_NONCE = nonce
    end
    local session = new_session(nonce)
    state.ambient_sessions[id] = session
    return session, ledger
end

local function ambient_action(sprite, action)
    local action_id = tonumber(action and action.m_actionID)
    local id = object_id(sprite)
    if not id then return end
    local recovery_record = action_id == 181
        and ambient_by_delivery[action_resref(action)] or nil
    if not state.ambient_sessions[id] and not recovery_record then return end
    local current, resolved_id = resolve_sprite(sprite)
    if not current then return end
    local now = game_time_ticks()
    local session = state.ambient_sessions[resolved_id]
        and existing_session_for(current, resolved_id) or nil
    local ledger = session and get_ledger(current) or nil
    if not session and recovery_record
            and get_local(current, "instantprep") == 0 then
        session, ledger = recover_reimbursement_session(
            current, resolved_id, recovery_record)
    end
    if not session then return end
    local released = reconcile_action_state(
        current, resolved_id, ledger, session, now, true)
    if released then
        local record = ambient_by_resref[released]
        if record then
            confirm_pending_delivery(
                current, resolved_id, record, ledger, session, now, false)
        end
    end

    local adjacent = session.pending
    if adjacent and (adjacent.stage == "delivery_started"
            or adjacent.stage == "preconfirm_delivery_started") then
        session.pending = nil
        if action_id == 147
                and tonumber(action.m_specificID) == adjacent.spell_number
                and get_local(current, "instantprep") == 0 then
            local before = available_count(current, adjacent.resref)
            if before == adjacent.available_before then
                session.pending = {
                    stage = "remove_started",
                    preconfirm = adjacent.preconfirm,
                    resref = adjacent.resref,
                    spell_number = adjacent.spell_number,
                    available_before = before,
                    deadline = now + ACTION_CONFIRM_TIMEOUT_TICKS,
                }
            else
                local record = ambient_by_resref[adjacent.resref]
                if adjacent.preconfirm == 1 then
                    session.delivery_pending[adjacent.resref] = nil
                end
                disable_action_state(current, resolved_id, record,
                    ledger.spells[adjacent.resref],
                    "slot changed between SCS delivery and removal")
            end
            return
        end
        if adjacent.preconfirm == 1 then
            local record = ambient_by_resref[adjacent.resref]
            if record then
                confirm_pending_delivery(
                    current, resolved_id, record, ledger, session, now, false)
            end
        end
    end

    if action_id ~= 181 then return end
    local record = ambient_by_delivery[action_resref(action)]
    if not record or get_local(current, "instantprep") ~= 0 then return end
    local before = available_count(current, record.resref)
    if not before or before < 1 then return end

    local delivery = session.delivery_pending[record.resref]
    if delivery and delivery.kind == "first"
            and delivery.reimbursement_eligible == 1
            and not ledger.spells[record.resref]
            and pending_slot_unchanged(current, record, delivery) then
        session.pending = {
            stage = "preconfirm_delivery_started",
            preconfirm = 1,
            resref = record.resref,
            spell_number = record.spell_number,
            available_before = before,
            deadline = now + ACTION_CONFIRM_TIMEOUT_TICKS,
        }
        return
    end

    local ledger_record = ledger.spells[record.resref]
    local token = ledger_record
        and reimbursement_token(ledger_record, record.resref)
    local component_record = token and resolve_record(current, token) or nil
    if not (ledger_record and ledger_record.charged == 1 and token
            and component_record
            and tonumber(component_record.m_flags)
                == ledger_record.debited_flags
            and managed_effect_active(current, record)) then
        return
    end
    session.pending = {
        stage = "delivery_started",
        preconfirm = 0,
        resref = record.resref,
        spell_number = record.spell_number,
        available_before = before,
        deadline = now + ACTION_CONFIRM_TIMEOUT_TICKS,
    }
end

local function ambient_reset(sprite)
    local current, id = resolve_sprite(sprite)
    if not current then return end
    state.ambient_sessions[id] = nil
    local aux = EEex_TryGetUDAux(current)
    if aux then aux.CBR_RDY_LEDGER = new_ledger() end
end

local function copy_v2_record(resref, record)
    if not valid_v2_record(resref, record) then return nil end
    return {
        version = LEDGER_VERSION,
        resref = resref,
        charged = record.charged,
        expected_expiry = record.expected_expiry,
        suppressed = record.suppressed,
        reimbursement_eligible = record.reimbursement_eligible,
        token_field = record.token_field,
        token_level = record.token_level,
        token_ordinal = record.token_ordinal,
        token_resref = record.token_resref,
        original_flags = record.original_flags,
        debited_flags = record.debited_flags,
    }
end

local function copy_ledger(sprite)
    local aux = EEex_TryGetUDAux(sprite)
    local source = aux and aux.CBR_RDY_LEDGER or nil
    if type(source) ~= "table"
            or (source.version ~= 1 and source.version ~= LEDGER_VERSION)
            or type(source.spells) ~= "table" then
        return nil
    end
    local result = new_ledger()
    for key, record in pairs(source.spells) do
        local resref = normalize(key)
        if ambient_by_resref[resref] and type(record) == "table" then
            local copied = source.version == 1
                and migrate_v1_record(resref, record)
                or copy_v2_record(resref, record)
            if copied then result.spells[resref] = copied end
        end
    end
    return result
end

local function import_ledger(sprite, saved)
    local current, id = resolve_sprite(sprite)
    if not current then return end
    state.ambient_sessions[id] = nil
    local result = new_ledger()
    if type(saved) == "table"
            and (saved.version == 1 or saved.version == LEDGER_VERSION)
            and type(saved.spells) == "table" then
        for key, record in pairs(saved.spells) do
            local resref = normalize(key)
            local valid = ambient_by_resref[resref]
            local copied = valid and (saved.version == 1
                and migrate_v1_record(resref, record)
                or copy_v2_record(resref, record))
            if copied then
                result.spells[resref] = copied
            elseif ambient_by_resref[resref] then
                disable_spell(current, id, ambient_by_resref[resref], "malformed saved ledger")
            end
        end
    end
    local aux = EEex_TryGetUDAux(current)
    if aux or next(result.spells) ~= nil then
        aux = aux or EEex_GetUDAux(current)
        aux.CBR_RDY_LEDGER = result
    end
end

local function for_each_effect(sprite, callback)
    local lists = {}
    for _, field in ipairs({ "m_timedEffectList", "m_equipedEffectList" }) do
        local list = sprite[field]
        if not list then return false end
        lists[#lists + 1] = list
    end
    for _, list in ipairs(lists) do
        EEex_Utility_IterateCPtrList(list, callback)
    end
    return true
end

local function weapon_immunity_active(sprite)
    local found = false
    local readable = for_each_effect(sprite, function(effect)
        if tonumber(effect.m_effectId) == 120 then
            found = true
            return true
        end
    end)
    if not readable then return true end
    return found
end

local function conscious(sprite)
    local value = tonumber(EEex_Sprite_GetState(sprite))
    if not value or type(EEex_BAnd) ~= "function" then return false end
    local disabled_mask = 0x8010202D
    return EEex_BAnd(value, disabled_mask) == 0
end

local function project_image_safe(sprite)
    local clone_owner = nil
    local clone_markers = 0
    local owner_lock_233 = false
    local owner_lock_20 = false
    local readable = for_each_effect(sprite, function(effect)
        local opcode = tonumber(effect.m_effectId)
        local parameter1 = tonumber(effect.m_effectAmount)
        local parameter2 = tonumber(effect.m_dWFlags)
        local source = effect_source(effect)
        if opcode == 237 and parameter2 == 2 then
            clone_markers = clone_markers + 1
            clone_owner = tonumber(effect.m_sourceId)
        elseif source == project_image_resref and opcode == 233
                and parameter1 == 2 and parameter2 == 127 then
            owner_lock_233 = true
        elseif source == project_image_resref and opcode == 20 then
            owner_lock_20 = true
        end
    end)
    if not readable then return false end
    if clone_markers > 0 then
        if clone_markers ~= 1 or not clone_owner or clone_owner < 0 then return false end
        local owner = EEex_GameObject_Get(clone_owner)
        if not owner or object_id(owner) ~= clone_owner
                or clone_owner == object_id(sprite) then return false end
        return false
    end
    if owner_lock_233 or owner_lock_20 then
        if not (owner_lock_233 and owner_lock_20) then return false end
        return false
    end
    return true
end

local function select_urgent_candidate(sprite)
    for _, record in ipairs(urgent_records) do
        if record.genuine == 1 then
            local available_record = find_available_record(sprite, record.resref)
            if available_record then return record end
        end
    end
    return nil
end

local function contact_for(sprite)
    local aux = EEex_GetUDAux(sprite)
    local contact = aux.CBR_RDY_CONTACT
    if type(contact) ~= "table" then
        contact = {
            spent = 0,
            attempts = 0,
            pending_resref = "",
            queued_at = 0,
            unseen_since = -1,
            rearmed = 0,
        }
        aux.CBR_RDY_CONTACT = contact
    end
    return contact
end

local function reset_contact(contact)
    contact.spent = 0
    contact.attempts = 0
    contact.pending_resref = ""
    contact.queued_at = 0
end

local function update_contact_visibility(contact, visible, now)
    local rearm_ticks = seconds_to_game_ticks(
        flag(manifest.contact_rearm_seconds, 6))
    if visible then
        if contact.unseen_since >= 0
                and now - contact.unseen_since >= rearm_ticks then
            reset_contact(contact)
        end
        contact.unseen_since = -1
        contact.rearmed = 0
        return true
    end
    if contact.unseen_since < 0 then contact.unseen_since = now end
    if contact.rearmed == 0
            and now - contact.unseen_since >= rearm_ticks then
        reset_contact(contact)
        contact.rearmed = 1
    end
    return false
end

local function urgent_tick(sprite)
    local current, id = resolve_sprite(sprite)
    if not current then return end
    local now = game_time_ticks()
    local classification = classify(current, id)
    if not classification then return end
    local enemy_ally = current.m_typeAI
        and tonumber(current.m_typeAI.m_EnemyAlly)
    if enemy_ally ~= 255 then return end
    local visible = sees_party(current)
    local contact = contact_for(current)
    if not update_contact_visibility(contact, visible, now) then return end
    if contact.spent == 1 then return end
    if not conscious(current) or not outside_cutscene() then return end
    if not project_image_safe(current) or weapon_immunity_active(current) then return end

    local retry = contact.pending_resref ~= ""
    if retry and now - contact.queued_at < seconds_to_game_ticks(2) then return end
    if retry and contact.attempts >= 2 then
        contact.spent = 1
        contact.pending_resref = ""
        return
    end

    local candidate = retry and urgent_by_resref[contact.pending_resref]
        or select_urgent_candidate(current)
    if retry then
        local available_record = candidate
            and candidate.genuine == 1
            and find_available_record(current, candidate.resref)
        if not available_record then
            contact.spent = 1
            contact.pending_resref = ""
            return
        end
    end
    if not candidate or not passive_actions_only(current)
            or type(current.virtual_ClearActions) ~= "function" then
        if retry then
            contact.spent = 1
            contact.pending_resref = ""
        end
        return
    end

    current:virtual_ClearActions(false)
    contact.attempts = contact.attempts + 1
    contact.pending_resref = candidate.resref
    contact.queued_at = now
    local response = string.format('SpellRES("%s",Myself)', candidate.resref)
    pcall(EEex_Action_QueueResponseStringOnAIBase, response, current)
    if contact.attempts >= 2 and contact.pending_resref ~= "" then
        contact.spent = 1
        contact.pending_resref = ""
    end
end

local function urgent_action(sprite, action)
    local current = resolve_sprite(sprite)
    if not current then return end
    game_time_ticks()
    local contact = contact_for(current)
    if contact.pending_resref ~= ""
            and tonumber(action and action.m_actionID) == 31
            and action_resref(action) == contact.pending_resref then
        contact.spent = 1
        contact.pending_resref = ""
    end
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

local function invoke_ambient_bookkeeping(event, ...)
    local handlers = _G.CBR_RDY_HANDLERS
    local callback = handlers and handlers["ambient_" .. event]
    if type(callback) ~= "function" then return nil end
    local arguments = { ... }
    local result = nil
    local ok, traceback = xpcall(function()
        result = callback(unpack_args(arguments))
    end, debug.traceback)
    if not ok then disable_layer("ambient", traceback) end
    return result
end

local function marshal_export_result(value)
    if tick_listener_mode == "legacy" and value == nil then return {} end
    return value
end

_G.CBR_RDY_HANDLERS = {
    ambient_tick = ambient_tick,
    ambient_confirm = ambient_confirm,
    ambient_action = ambient_action,
    ambient_reset = ambient_reset,
    ambient_export = copy_ledger,
    ambient_import = import_ledger,
    urgent_tick = urgent_tick,
    urgent_action = urgent_action,
    urgent_reset = function() end,
}

_G.CBR_RDY_TRAMPOLINES = {
    tick = function(sprite)
        invoke("ambient", "tick", sprite)
        invoke("urgent", "tick", sprite)
    end,
    confirm = function(sprite)
        invoke("ambient", "confirm", sprite)
    end,
    action = function(sprite, action)
        invoke("ambient", "action", sprite, action)
        invoke("urgent", "action", sprite, action)
    end,
    reset = function(sprite)
        invoke_ambient_bookkeeping("reset", sprite)
        invoke("urgent", "reset", sprite)
    end,
    export = function(sprite)
        return marshal_export_result(
            invoke_ambient_bookkeeping("export", sprite))
    end,
    import = function(sprite, saved)
        invoke_ambient_bookkeeping("import", sprite, saved)
    end,
}

local function apis_available(entries)
    for _, entry in ipairs(entries) do
        if type(entry[2]) ~= "function" then return false end
    end
    return true
end

local shared_supported = apis_available({
    { "selected EEex lists-resolved listener", add_tick_listener },
    { "EEex_Action_AddSpriteStartedActionListener", EEex_Action_AddSpriteStartedActionListener },
    { "EEex_GameObject_Get", EEex_GameObject_Get },
    { "EEex_GetUDAux", EEex_GetUDAux },
    { "EEex_Sprite_GetLocalInt", EEex_Sprite_GetLocalInt },
    { "EEex_Trigger_EvalConditionalStringAsAIBase", EEex_Trigger_EvalConditionalStringAsAIBase },
    { "EEex_Utility_IterateCPtrList", EEex_Utility_IterateCPtrList },
})
local confirmation_supported = tick_listener_mode == "legacy"
    or type(add_confirmation_listener) == "function"
local bookkeeping_supported = apis_available({
    { "EEex_GameObject_Get", EEex_GameObject_Get },
    { "EEex_GetUDAux", EEex_GetUDAux },
    { "EEex_TryGetUDAux", EEex_TryGetUDAux },
    { "EEex_Sprite_AddQuickListCountsResetListener", EEex_Sprite_AddQuickListCountsResetListener },
    { "EEex_Sprite_AddMarshalHandlers", EEex_Sprite_AddMarshalHandlers },
    { "EEex_Resource_Demand", EEex_Resource_Demand },
})
state.bookkeeping_supported = bookkeeping_supported and 1 or 0
local ambient_supported = shared_supported and confirmation_supported
    and bookkeeping_supported and apis_available({
    { "EEex_GameObject_ApplyEffect", EEex_GameObject_ApplyEffect },
    { "EEex_RunWithStackManager", EEex_RunWithStackManager },
})
local urgent_supported = shared_supported and project_image_identity_supported
    and apis_available({
    { "EEex_Sprite_GetState", EEex_Sprite_GetState },
    { "EEex_Action_QueueResponseStringOnAIBase", EEex_Action_QueueResponseStringOnAIBase },
    { "EEex_BAnd", EEex_BAnd },
    { "Infinity_GetInCutsceneMode", Infinity_GetInCutsceneMode },
})

local function retire_unsupported(layer, detail)
    state[layer .. "_faulted"] = 1
    local logged = layer .. "_unsupported_logged"
    if flag(state[logged], 0) == 0 then
        state[logged] = 1
        print("[CBR Ready] " .. layer
            .. " disabled: " .. detail)
    end
end

if not ambient_supported then
    retire_unsupported("ambient", "required EEex API is unavailable")
end
if not urgent_supported then
    retire_unsupported("urgent",
        "required EEex API or Project Image manifest identity is unavailable")
end

if shared_supported and (ambient_supported or urgent_supported)
        and not _G.CBR_RDY_TICK_ACTION_LISTENERS_REGISTERED then
    add_tick_listener(function(sprite)
        local current = _G.CBR_RDY_TRAMPOLINES
        if current and current.tick then current.tick(sprite) end
    end)
    EEex_Action_AddSpriteStartedActionListener(function(sprite, action)
        local current = _G.CBR_RDY_TRAMPOLINES
        if current and current.action then current.action(sprite, action) end
    end)
    _G.CBR_RDY_TICK_ACTION_LISTENERS_REGISTERED = 1
    _G.CBR_RDY_LISTENERS_REGISTERED = 1
end


if ambient_supported and tick_listener_mode == "deferred"
        and not _G.CBR_RDY_AMBIENT_CONFIRMATION_LISTENER_REGISTERED then
    add_confirmation_listener(function(sprite)
        local current = _G.CBR_RDY_TRAMPOLINES
        if current and current.confirm then current.confirm(sprite) end
    end)
    _G.CBR_RDY_AMBIENT_CONFIRMATION_LISTENER_REGISTERED = 1
end
state.confirmation_listener_registered =
    flag(_G.CBR_RDY_AMBIENT_CONFIRMATION_LISTENER_REGISTERED, 0)

if bookkeeping_supported
        and not _G.CBR_RDY_AMBIENT_STATE_LISTENERS_REGISTERED then
    EEex_Sprite_AddQuickListCountsResetListener(function(sprite)
        local current = _G.CBR_RDY_TRAMPOLINES
        if current and current.reset then current.reset(sprite) end
    end)
    EEex_Sprite_AddMarshalHandlers("CBR_RDY",
        function(sprite)
            local current = _G.CBR_RDY_TRAMPOLINES
            if current and current.export then return current.export(sprite) end
            return marshal_export_result(nil)
        end,
        function(sprite, saved)
            local current = _G.CBR_RDY_TRAMPOLINES
            if current and current.import then current.import(sprite, saved) end
        end)
    _G.CBR_RDY_AMBIENT_STATE_LISTENERS_REGISTERED = 1
end
