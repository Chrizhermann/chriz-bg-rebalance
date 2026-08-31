-- Fake EEex surface for component 121 (M_CBRRDY.lua).
--
-- usage: lua ambient_readiness_sim.lua <stamped-runtime.lua> <scenario>
-- Output is one key<TAB>value observation per line.  This fake models only
-- the state transitions named by the approved design.  Task 6 updates the
-- binding shapes to the exact installed EEex capability profile before the
-- production runtime is implemented.

local runtimePath = arg[1]
local scenarioName = arg[2]

-------------------------------------------------------------------------------
-- Small fake containers / engine values
-------------------------------------------------------------------------------

local function out(key, value)
    io.write(key, "\t", tostring(value), "\n")
end

local function lower(value)
    return string.lower(tostring(value or ""))
end

local function bitAnd(a, b)
    local result = 0
    local place = 1
    while a > 0 or b > 0 do
        local aa = a % 2
        local bb = b % 2
        if aa == 1 and bb == 1 then result = result + place end
        a = math.floor(a / 2)
        b = math.floor(b / 2)
        place = place * 2
    end
    return result
end

local function bitOr(a, b)
    local result = 0
    local place = 1
    while a > 0 or b > 0 do
        local aa = a % 2
        local bb = b % 2
        if aa == 1 or bb == 1 then result = result + place end
        a = math.floor(a / 2)
        b = math.floor(b / 2)
        place = place * 2
    end
    return result
end

EEex_BAnd = bitAnd
EEex_BOr = bitOr

local function newPtrList(values)
    return { values = values or {} }
end

function EEex_Utility_IterateCPtrList(list, callback)
    if not list then return end
    for _, value in ipairs(list.values or {}) do
        if callback(value) then return end
    end
end

local function newLevelArray()
    local result = { levels = {} }
    function result:getReference(index)
        return self.levels[index]
    end
    return result
end

local function newResRef(value)
    local result = { value = lower(value) }
    function result:get() return self.value end
    function result:set(nextValue) self.value = lower(nextValue) end
    return result
end

local function newCString(value)
    return { m_pchData = newResRef(value) }
end

function EEex_RunWithStackManager(specifications, callback)
    local values = {}
    for _, specification in ipairs(specifications or {}) do
        if specification.struct == "CAbilityId" then
            values[specification.name] = {
                m_itemType = 0,
                m_res = newResRef(""),
            }
        else
            values[specification.name] = {}
        end
    end
    callback({
        getUD = function(_, name) return values[name] end,
    })
end

local spellLevels = {
    spwi102 = 1,
    spwi310 = 3,
    spwi408 = 4,
    sppr506 = 5,
    sppr735 = 7,
    spwi802 = 8,
    spwi611 = 6,
    spwi708 = 7,
    spwi808 = 8,
    spwi907 = 9,
}

function EEex_Resource_Demand(resref, resourceType)
    if resourceType ~= "SPL" then return nil end
    local level = spellLevels[lower(resref)]
    if not level then return nil end
    return { spellLevel = level }
end

local deliveryToSpell = {
    dwsp506 = "sppr506",
    dwsp735 = "sppr735",
    dwsw102 = "spwi102",
    dwsw310 = "spwi310",
    dwsw408 = "spwi408",
    dwsw802 = "spwi802",
}

local ambientDurations = {
    sppr506 = 2400,
    sppr735 = 2880,
    spwi102 = 2400,
    spwi310 = 2400,
    spwi408 = 2400,
    spwi802 = 7200,
}

local ambientDetection = {
    sppr506 = { 218, 0 }, sppr735 = { 206, 0 },
    spwi102 = { 0, 16 }, spwi310 = { 69, 0 },
    spwi408 = { 218, 0 }, spwi802 = { 101, 213 },
}

local fakeClock = 1000
local fakeGameTimeTicks = fakeClock * 15
local nextSpriteID = 100
local spritesByID = {}
local auxBySprite = setmetatable({}, { __mode = "k" })
local printed = {}
local originalPrint = print
local projectImageResref = "spwi703"

print = function(...)
    local values = {}
    for index = 1, select("#", ...) do
        values[#values + 1] = tostring(select(index, ...))
    end
    printed[#printed + 1] = table.concat(values, "\t")
end

function EEex_GameObject_Get(id)
    return spritesByID[id]
end

function EEex_GetUDAux(sprite)
    local aux = auxBySprite[sprite]
    if not aux then
        aux = {}
        auxBySprite[sprite] = aux
    end
    return aux
end

-- EEex v1.2 exposes the engine's world-time field; it does not define
-- EEex_GameState_GetTime() or Infinity_GetGameTime(). m_gameTime is measured
-- in 1/15-second engine ticks.
local fakeWorldTime = { m_gameTime = fakeGameTimeTicks }
function fakeWorldTime:GetCurrentTime()
    return self.m_gameTime
end
EngineGlobals = {
    g_pBaldurChitin = {
        m_pObjectGame = { m_worldTime = fakeWorldTime },
    },
}

local function advanceClockTicks(ticks)
    fakeGameTimeTicks = fakeGameTimeTicks + ticks
    fakeClock = fakeGameTimeTicks / 15
    EngineGlobals.g_pBaldurChitin.m_pObjectGame.m_worldTime.m_gameTime =
        fakeGameTimeTicks
end

local function advanceClockSeconds(seconds)
    advanceClockTicks(seconds * 15)
end

local function countAvailable(sprite, resref)
    local wanted = lower(resref)
    local count = 0
    for _, field in ipairs({ "m_memorizedSpellsMage", "m_memorizedSpellsPriest" }) do
        local lists = sprite[field]
        if lists then
            for _, list in pairs(lists.levels) do
                for _, record in ipairs(list.values) do
                    if lower(record.m_spellId:get()) == wanted and bitAnd(record.m_flags, 1) ~= 0 then
                        count = count + 1
                    end
                end
            end
        end
    end
    return count
end

local function setFirstAvailable(sprite, resref, available)
    local wanted = lower(resref)
    for _, field in ipairs({ "m_memorizedSpellsMage", "m_memorizedSpellsPriest" }) do
        local lists = sprite[field]
        if lists then
            for _, list in pairs(lists.levels) do
                for _, record in ipairs(list.values) do
                    if lower(record.m_spellId:get()) == wanted and bitAnd(record.m_flags, 1) ~= 0 then
                        if available == 0 then
                            record.m_flags = record.m_flags - 1
                        end
                        return record
                    end
                end
            end
        end
    end
    return nil
end

local function restoreRecord(record)
    if record and bitAnd(record.m_flags, 1) == 0 then
        record.m_flags = bitOr(record.m_flags, 1)
    end
end

local function newSprite(options)
    options = options or {}
    nextSpriteID = nextSpriteID + 1
    local sprite = {
        m_id = options.id or nextSpriteID,
        m_scriptName = newResRef(options.name or "cbr_default"),
        m_typeAI = { m_EnemyAlly = options.ea or 255 },
        m_pArea = {},
        m_curAction = { m_actionID = options.action or 0 },
        m_queuedActions = newPtrList(options.queue or {}),
        m_timedEffectList = newPtrList({}),
        m_equipedEffectList = newPtrList({}),
        m_memorizedSpellsMage = newLevelArray(),
        m_memorizedSpellsPriest = newLevelArray(),
        locals = {
            caster_label_ini = options.scsCaster == false and 0 or 1,
            instantprep = options.instantprep or 0,
            inafight = options.inCombat and 1 or 0,
        },
        seeParty = options.seeParty ~= false,
        cutscene = options.cutscene == true,
        conscious = options.conscious ~= false,
        state = options.state or 0,
        genuineWeaponImmunity = options.genuineWeaponImmunity == true,
        active = {},
        applications = {},
        quickListRebuilds = 0,
        queuedResponses = {},
        queueCount = 0,
        starts = 0,
        directEffects = 0,
        engineSlotDebits = 0,
        engineAura = 0,
        engineCastingTime = 0,
        interrupted = options.interrupted == true,
        autoStart = options.autoStart ~= false,
        retainFailedQueue = options.retainFailedQueue == true,
        failApply = options.failApply == true,
        failQuickList = options.failQuickList == true,
        failVisibility = options.failVisibility == true,
    }
    function sprite:getLocalInt(name)
        return self.locals[name] or 0
    end
    function sprite:setLocalInt(name, value)
        self.locals[name] = value
    end
    function sprite:CheckQuickLists(abilityID, changeAmount, remove, unknown)
        if self.failQuickList then error("injected quick-list failure") end
        self.quickListRebuilds = self.quickListRebuilds + 1
        self.lastQuickListArgs = { abilityID, changeAmount, remove, unknown }
    end
    function sprite:virtual_ClearActions()
        self.m_curAction = { m_actionID = 0 }
        self.m_queuedActions = newPtrList({})
        self.actionsCleared = (self.actionsCleared or 0) + 1
    end
    if options.settled == false then sprite.m_pArea = nil end
    if options.queueUnavailable then sprite.m_queuedActions = nil end
    if options.effectListsUnavailable then
        sprite.m_timedEffectList = nil
        sprite.m_equipedEffectList = nil
    elseif options.timedEffectsUnavailable then
        sprite.m_timedEffectList = nil
    elseif options.equippedEffectsUnavailable then
        sprite.m_equipedEffectList = nil
    end
    if options.conscious == false then sprite.state = 1 end
    if options.genuineWeaponImmunity then
        sprite.m_timedEffectList.values[#sprite.m_timedEffectList.values + 1] = {
            m_effectId = 120,
            m_dWFlags = 2,
            m_sourceRes = newResRef("spwi611"),
        }
    end
    spritesByID[sprite.m_id] = sprite
    return sprite
end

local function memorize(sprite, resref, copies, flags)
    local normalized = lower(resref)
    local level = spellLevels[normalized] or 1
    local field = normalized:sub(1, 4) == "sppr"
        and sprite.m_memorizedSpellsPriest or sprite.m_memorizedSpellsMage
    local index = level - 1
    local list = field.levels[index]
    if not list then
        list = newPtrList({})
        field.levels[index] = list
    end
    for _ = 1, (copies or 1) do
        list.values[#list.values + 1] = {
            m_spellId = newResRef(normalized),
            m_flags = flags or 1,
        }
    end
end

function EEex_Sprite_GetLocalInt(sprite, name)
    return sprite:getLocalInt(name)
end

function EEex_Sprite_SetLocalInt(sprite, name, value)
    sprite:setLocalInt(name, value)
end

function EEex_Trigger_EvalConditionalStringAsAIBase(trigger, sprite)
    if sprite.failVisibility then error("injected visibility failure") end
    if trigger == "See([PC])" or trigger == "See(NearestEnemyOf(Myself))" then
        return sprite.seeParty
    end
    if trigger == "!See([PC])" then return not sprite.seeParty end
    return false
end

function EEex_Sprite_GetState(sprite)
    return sprite.state
end

function Infinity_GetInCutsceneMode()
    for _, sprite in pairs(spritesByID) do
        if sprite.cutscene then return true end
    end
    return false
end

function EEex_GameObject_ApplyEffect(sprite, args)
    sprite.directEffects = sprite.directEffects + 1
    if sprite.failApply then return end
    if args.effectID ~= 146 or args.dwFlags ~= 1 then
        error("ambient delivery must use instant opcode 146")
    end
    local delivered = lower(args.res or args.m_sourceRes)
    local managed = deliveryToSpell[delivered] or delivered
    sprite.active[managed] = {
        appliedAt = fakeClock,
        expectedExpiry = fakeClock + (ambientDurations[managed] or 0),
    }
    sprite.applications[managed] = (sprite.applications[managed] or 0) + 1
    local marker = ambientDetection[managed]
    if marker then
        sprite.m_timedEffectList.values[#sprite.m_timedEffectList.values + 1] = {
            m_effectId = marker[1],
            m_dWFlags = marker[2],
            m_sourceRes = newResRef(delivered),
        }
    end
end

local function addProjectImageClone(sprite, ownerID)
    sprite.m_timedEffectList.values[#sprite.m_timedEffectList.values + 1] = {
        m_effectId = 237,
        m_dWFlags = 2,
        m_sourceId = ownerID,
        m_sourceRes = newResRef(projectImageResref),
    }
end

local function addProjectImageOwnerLock(sprite)
    sprite.state = 0x30
    sprite.m_timedEffectList.values[#sprite.m_timedEffectList.values + 1] = {
        m_effectId = 233,
        m_effectAmount = 2,
        m_dWFlags = 127,
        m_sourceRes = newResRef(projectImageResref),
    }
    sprite.m_timedEffectList.values[#sprite.m_timedEffectList.values + 1] = {
        m_effectId = 20,
        m_dWFlags = 0,
        m_sourceRes = newResRef(projectImageResref),
    }
end

-------------------------------------------------------------------------------
-- Listener registration and action engine
-------------------------------------------------------------------------------

local deferredTickListeners = {}
local legacyTickListeners = {}
local startedActionListeners = {}
local resetListeners = {}
local marshalHandlers = {}

function EEex_Opcode_AddDeferredListsResolvedListener(callback)
    deferredTickListeners[#deferredTickListeners + 1] = callback
end

function EEex_Opcode_AddListsResolvedListener(callback)
    legacyTickListeners[#legacyTickListeners + 1] = callback
end

function EEex_Action_AddSpriteStartedActionListener(callback)
    startedActionListeners[#startedActionListeners + 1] = callback
end

function EEex_Sprite_AddQuickListCountsResetListener(callback)
    resetListeners[#resetListeners + 1] = callback
end

function EEex_Sprite_AddMarshalHandlers(name, exporter, importer)
    marshalHandlers[name] = { exporter = exporter, importer = importer }
end

local function fireStarted(sprite, action)
    sprite.starts = sprite.starts + 1
    sprite.m_curAction = action
    for _, callback in ipairs(startedActionListeners) do callback(sprite, action) end
end

function EEex_Action_QueueResponseStringOnAIBase(response, sprite)
    sprite.queueCount = sprite.queueCount + 1
    sprite.queuedResponses[#sprite.queuedResponses + 1] = response
    local resref = response:match('[Ss]pellRES%(%s*"([^"]+)"')
    if not resref then return end
    if not sprite.autoStart then
        if sprite.retainFailedQueue then
            sprite.m_queuedActions = newPtrList({ {
                m_actionID = 31,
                m_string1 = newCString(lower(resref)),
            } })
        end
        return
    end
    local action = {
        m_actionID = 31,
        m_string1 = newCString(lower(resref)),
        cbrNormalSpellRES = 1,
    }
    fireStarted(sprite, action)
    sprite.engineAura = 1
    sprite.engineCastingTime = 1
    if not sprite.interrupted then
        local consumed = setFirstAvailable(sprite, resref, 0)
        if consumed then sprite.engineSlotDebits = sprite.engineSlotDebits + 1 end
        sprite.active[lower(resref)] = {
            appliedAt = fakeClock,
            expectedExpiry = fakeClock + 24,
        }
        sprite.m_timedEffectList.values[#sprite.m_timedEffectList.values + 1] = {
            m_effectId = 120,
            m_dWFlags = 2,
            m_sourceRes = newResRef(lower(resref)),
        }
    end
    sprite.m_curAction = { m_actionID = 0 }
end

local function fireTick(sprite)
    for _, callback in ipairs(deferredTickListeners) do callback(sprite) end
    for _, callback in ipairs(legacyTickListeners) do callback(sprite) end
end

local function fireSpellbookReset(sprite)
    for _, callback in ipairs(resetListeners) do callback(sprite) end
end

local function exportedLedger(sprite)
    for _, handler in pairs(marshalHandlers) do
        return handler.exporter(sprite)
    end
    return nil
end

local function importedLedger(sprite, value)
    for _, handler in pairs(marshalHandlers) do
        handler.importer(sprite, value)
        return
    end
end

local function reloadRuntime()
    dofile(runtimePath)
end

local function active(sprite, resref)
    return sprite.active[lower(resref)] and 1 or 0
end

local function removeActive(sprite, resref)
    local normalized = lower(resref)
    sprite.active[normalized] = nil
    local retained = {}
    for _, effect in ipairs(sprite.m_timedEffectList.values) do
        local source = effect.m_sourceRes and lower(effect.m_sourceRes:get()) or ""
        if deliveryToSpell[source] ~= normalized then
            retained[#retained + 1] = effect
        end
    end
    sprite.m_timedEffectList.values = retained
end

local function addActiveDefense(sprite, resref, source)
    local normalized = lower(resref)
    local marker = ambientDetection[normalized]
    assert(marker, "missing fake detection metadata for " .. normalized)
    sprite.active[normalized] = {
        appliedAt = fakeClock,
        expectedExpiry = fakeClock + (ambientDurations[normalized] or 0),
    }
    sprite.m_timedEffectList.values[#sprite.m_timedEffectList.values + 1] = {
        m_effectId = marker[1],
        m_dWFlags = marker[2],
        m_sourceRes = newResRef(source or normalized),
    }
end

local function applicationCount(sprite, resref)
    return sprite.applications[lower(resref)] or 0
end

local function bool(value)
    return value and 1 or 0
end

local function countPrinted(pattern)
    local count = 0
    for _, line in ipairs(printed) do
        if lower(line):find(lower(pattern), 1, true) then count = count + 1 end
    end
    return count
end

-------------------------------------------------------------------------------
-- Scenarios
-------------------------------------------------------------------------------

local scenarios = {}

scenarios.runtime_missing_urgent_api = function()
    local sprite = newSprite({ seeParty = false })
    memorize(sprite, "spwi408")
    fireTick(sprite)
    out("ambient_live", active(sprite, "spwi408"))
    out("ambient_faulted", CBR_RDY_STATE.ambient_faulted or 0)
    out("urgent_faulted", CBR_RDY_STATE.urgent_faulted or 0)
    out("urgent_unsupported_logs", countPrinted("urgent disabled: required EEex API"))
end

scenarios.runtime_missing_ambient_api = function()
    local sprite = newSprite({})
    memorize(sprite, "spwi611")
    fireTick(sprite)
    out("urgent_live", bool(sprite.queueCount == 1))
    out("urgent_faulted", CBR_RDY_STATE.urgent_faulted or 0)
    out("ambient_faulted", CBR_RDY_STATE.ambient_faulted or 0)
    out("ambient_unsupported_logs", countPrinted("ambient disabled: required EEex API"))
end

scenarios.runtime_missing_project_image_identity =
    scenarios.runtime_missing_urgent_api

scenarios.runtime_missing_game_time = function()
    local sprite = newSprite({})
    memorize(sprite, "spwi408")
    memorize(sprite, "spwi611")
    fireTick(sprite)
    out("ambient_applications", applicationCount(sprite, "spwi408"))
    out("ambient_available", countAvailable(sprite, "spwi408"))
    out("urgent_queues", sprite.queueCount)
    out("ambient_faulted", CBR_RDY_STATE.ambient_faulted or 0)
    out("urgent_faulted", CBR_RDY_STATE.urgent_faulted or 0)
    out("sprite_aux_created", bool(auxBySprite[sprite] ~= nil))
    out("classification_cached",
        bool(CBR_RDY_STATE.classifications[sprite.m_id] ~= nil))
    out("ambient_session_cached",
        bool(CBR_RDY_STATE.ambient_sessions[sprite.m_id] ~= nil))
end

scenarios.runtime_legacy_missing_raw_time =
    scenarios.runtime_missing_game_time

scenarios.runtime_legacy_v011_surface = function()
    local sprite = newSprite({})
    memorize(sprite, "spwi408")
    memorize(sprite, "spwi611")
    fireTick(sprite)
    out("ambient_applications", applicationCount(sprite, "spwi408"))
    out("ambient_available", countAvailable(sprite, "spwi408"))
    out("urgent_queues", sprite.queueCount)
end

scenarios.runtime_legacy_repeated_callbacks = function()
    local sprite = newSprite({})
    memorize(sprite, "spwi408")
    memorize(sprite, "spwi611")
    for _ = 1, 8 do fireTick(sprite) end
    out("ambient_applications", applicationCount(sprite, "spwi408"))
    out("ambient_available", countAvailable(sprite, "spwi408"))
    out("urgent_queues", sprite.queueCount)
end

local function isEmptyTable(value)
    if type(value) ~= "table" then return false end
    return next(value) == nil
end

scenarios.runtime_legacy_marshal_exports = function()
    local normal = newSprite({ seeParty = false })
    memorize(normal, "spwi408")
    fireTick(normal)
    local normalExport = exportedLedger(normal)
    out("normal_export_type", type(normalExport))
    out("normal_export_version", normalExport and normalExport.version or 0)

    local inactive = newSprite({})
    CBR_RDY_AMBIENT_ENABLED = 0
    local disabledExport = exportedLedger(inactive)
    out("disabled_export_type", type(disabledExport))
    out("disabled_export_empty", bool(isEmptyTable(disabledExport)))
    CBR_RDY_AMBIENT_ENABLED = 1

    CBR_RDY_EXTERNAL_OWNER = 1
    local ownedExport = exportedLedger(inactive)
    out("owned_export_type", type(ownedExport))
    out("owned_export_empty", bool(isEmptyTable(ownedExport)))
    CBR_RDY_EXTERNAL_OWNER = 0

    CBR_RDY_STATE.ambient_faulted = 1
    local faultedExport = exportedLedger(inactive)
    out("faulted_export_type", type(faultedExport))
    out("faulted_export_empty", bool(isEmptyTable(faultedExport)))
end

scenarios.v12_inactive_marshal_exports = function()
    local sprite = newSprite({})
    CBR_RDY_AMBIENT_ENABLED = 0
    out("disabled_export_type", type(exportedLedger(sprite)))
    CBR_RDY_AMBIENT_ENABLED = 1

    CBR_RDY_EXTERNAL_OWNER = 1
    out("owned_export_type", type(exportedLedger(sprite)))
    CBR_RDY_EXTERNAL_OWNER = 0

    CBR_RDY_STATE.ambient_faulted = 1
    out("faulted_export_type", type(exportedLedger(sprite)))
end

scenarios.runtime_missing_game_time_callbacks = function()
    local action_sprite = newSprite({})
    fireStarted(action_sprite, { m_actionID = 0, m_specificID = 0 })
    out("action_aux_created", bool(auxBySprite[action_sprite] ~= nil))

    CBR_RDY_STATE.ambient_faulted = 0
    CBR_RDY_STATE.urgent_faulted = 0
    local reset_sprite = newSprite({})
    fireSpellbookReset(reset_sprite)
    out("reset_aux_created", bool(auxBySprite[reset_sprite] ~= nil))

    CBR_RDY_STATE.ambient_faulted = 0
    local export_sprite = newSprite({})
    exportedLedger(export_sprite)
    out("export_aux_created", bool(auxBySprite[export_sprite] ~= nil))

    CBR_RDY_STATE.ambient_faulted = 0
    local import_sprite = newSprite({})
    importedLedger(import_sprite, { version = 1, spells = {} })
    out("import_aux_created", bool(auxBySprite[import_sprite] ~= nil))
end

scenarios.runtime_shell = function()
    reloadRuntime()
    out("listeners_after_reload", #deferredTickListeners + #legacyTickListeners)
    out("started_after_reload", #startedActionListeners)
    out("reset_after_reload", #resetListeners)

    local ambientCalls = 0
    local urgentCalls = 0
    CBR_RDY_HANDLERS.ambient_tick = function() ambientCalls = ambientCalls + 1 end
    CBR_RDY_HANDLERS.urgent_tick = function() urgentCalls = urgentCalls + 1 end
    local sprite = newSprite({})

    CBR_RDY_AMBIENT_ENABLED = 0
    fireTick(sprite)
    out("ambient_enable_gate", bool(ambientCalls == 0))
    CBR_RDY_AMBIENT_ENABLED = 1

    CBR_RDY_EXTERNAL_OWNER = 1
    fireTick(sprite)
    out("ambient_owner_gate", bool(ambientCalls == 0))
    out("urgent_owner_independent", bool(urgentCalls == 2))

    CBR_RDY_EXTERNAL_OWNER = 2
    fireTick(sprite)
    out("urgent_owner_gate", bool(urgentCalls == 2))
    out("ambient_owner_independent", bool(ambientCalls == 1))

    CBR_RDY_EXTERNAL_OWNER = 0
    CBR_RDY_HANDLERS.ambient_tick = function() error("injected shell fault") end
    fireTick(sprite)
    fireTick(sprite)
    out("ambient_tracebacks", countPrinted("ambient disabled"))
    out("ambient_fused", CBR_RDY_STATE.ambient_faulted or 0)
    out("urgent_after_ambient_fault", bool(urgentCalls == 4))
end

scenarios.ambient_classification = function()
    local settled = newSprite({})
    memorize(settled, "spwi408")
    fireTick(settled)
    out("settled_scs", active(settled, "spwi408"))
    out("grade_default", active(settled, "spwi408"))

    local unsettled = newSprite({ settled = false })
    memorize(unsettled, "spwi408")
    fireTick(unsettled)
    out("unsettled", active(unsettled, "spwi408"))

    local unrecognized = newSprite({ scsCaster = false })
    memorize(unrecognized, "spwi408")
    fireTick(unrecognized)
    out("unrecognized", active(unrecognized, "spwi408"))

    local zero = newSprite({ name = "cbr_grade_zero" })
    memorize(zero, "spwi408")
    fireTick(zero)
    out("grade_zero", active(zero, "spwi408"))

    local reserved = newSprite({ name = "cbr_reserved_grade" })
    memorize(reserved, "spwi408")
    fireTick(reserved)
    out("grade_reserved", active(reserved, "spwi408") == 1 and 3 or 0)

    local include = newSprite({ name = "cbr_sparse_include" })
    memorize(include, "spwi802")
    fireTick(include)
    out("sparse_include", active(include, "spwi802"))

    local exclude = newSprite({ name = "cbr_sparse_exclude" })
    memorize(exclude, "spwi408")
    fireTick(exclude)
    out("sparse_exclude", active(exclude, "spwi408"))
end

scenarios.ambient_qualification = function()
    local sprite = newSprite({})
    memorize(sprite, "spwi408")
    memorize(sprite, "spwi212")
    memorize(sprite, "cbrally")
    memorize(sprite, "cbroffns")
    fireTick(sprite)
    out("long_self_defense", active(sprite, "spwi408"))
    out("short_duration", active(sprite, "spwi212"))
    out("other_target", active(sprite, "cbrally"))
    out("offensive", active(sprite, "cbroffns"))
    out("unmemorized", active(sprite, "spwi802"))
end

scenarios.ambient_existing_defense = function()
    local sprite = newSprite({})
    memorize(sprite, "spwi408")
    addActiveDefense(sprite, "spwi408", "spwi408")
    fireTick(sprite)
    out("available", countAvailable(sprite, "spwi408"))
    out("component_applications", applicationCount(sprite, "spwi408"))
    out("ledger_created", bool((exportedLedger(sprite).spells or {}).spwi408 ~= nil))
end

scenarios.ambient_priest_debit = function()
    local sprite = newSprite({})
    memorize(sprite, "sppr506")
    fireTick(sprite)
    out("available_after", countAvailable(sprite, "sppr506"))
    out("active_after", active(sprite, "sppr506"))
    out("quicklist_rebuilds", sprite.quickListRebuilds)
end

scenarios.ambient_spellbook_cache = function()
    local sprite = newSprite({})
    fireTick(sprite)
    memorize(sprite, "spwi408")
    fireTick(sprite)
    out("without_reset", applicationCount(sprite, "spwi408"))
    fireSpellbookReset(sprite)
    fireTick(sprite)
    out("after_reset", applicationCount(sprite, "spwi408"))
end

scenarios.ambient_first_debit_and_refresh = function()
    local sprite = newSprite({})
    memorize(sprite, "spwi408")
    out("available_before", countAvailable(sprite, "spwi408"))
    fireTick(sprite)
    out("available_after_first", countAvailable(sprite, "spwi408"))
    out("active_after_first", active(sprite, "spwi408"))
    local ledger = exportedLedger(sprite) or {}
    local record = ledger.spells and ledger.spells.spwi408 or {}
    out("ledger_charged", record.charged or 0)
    out("quicklist_rebuilds", sprite.quickListRebuilds)
    removeActive(sprite, "spwi408")
    advanceClockSeconds(2400)
    sprite.seeParty = false
    sprite.locals.inafight = 0
    for _ = 1, 15 do fireTick(sprite) end
    out("available_after_refresh", countAvailable(sprite, "spwi408"))
    out("applications", applicationCount(sprite, "spwi408"))
end

scenarios.ambient_natural_expiry = function()
    local sprite = newSprite({})
    memorize(sprite, "spwi408")
    fireTick(sprite)
    removeActive(sprite, "spwi408")
    advanceClockSeconds(2400)
    sprite.seeParty = true
    for _ = 1, 15 do fireTick(sprite) end
    out("visible_blocked", bool(applicationCount(sprite, "spwi408") == 1))
    sprite.seeParty = false
    sprite.locals.inafight = 1
    for _ = 1, 15 do fireTick(sprite) end
    out("combat_blocked", bool(applicationCount(sprite, "spwi408") == 1))
    sprite.locals.inafight = 0
    for _ = 1, 15 do fireTick(sprite) end
    out("safe_refresh", bool(applicationCount(sprite, "spwi408") == 2))
end

scenarios.ambient_early_removal = function()
    local sprite = newSprite({})
    memorize(sprite, "spwi408", 2)
    fireTick(sprite)
    removeActive(sprite, "spwi408")
    advanceClockSeconds(60)
    sprite.seeParty = false
    for _ = 1, 30 do fireTick(sprite) end
    local before = exportedLedger(sprite) or {}
    local beforeRecord = before.spells and before.spells.spwi408 or {}
    out("suppressed", beforeRecord.suppressed or 0)
    out("applications_before_reset", applicationCount(sprite, "spwi408"))
    for _, list in pairs(sprite.m_memorizedSpellsMage.levels) do
        for _, record in ipairs(list.values) do restoreRecord(record) end
    end
    fireSpellbookReset(sprite)
    fireTick(sprite)
    local after = exportedLedger(sprite) or {}
    local afterRecord = after.spells and after.spells.spwi408 or {}
    out("suppressed_after_reset", afterRecord.suppressed or 0)
    out("applications_after_reset", applicationCount(sprite, "spwi408"))
end

scenarios.ambient_reset_boundaries = function()
    local sprite = newSprite({})
    memorize(sprite, "spwi408", 2)
    fireTick(sprite)
    advanceClockSeconds(10000)
    fireTick(sprite)
    out("after_elapsed_time", applicationCount(sprite, "spwi408"))
    local saved = exportedLedger(sprite)
    local loaded = newSprite({})
    memorize(loaded, "spwi408", 2)
    setFirstAvailable(loaded, "spwi408", 0)
    loaded.active.spwi408 = sprite.active.spwi408
    for _, effect in ipairs(sprite.m_timedEffectList.values) do
        loaded.m_timedEffectList.values[#loaded.m_timedEffectList.values + 1] = effect
    end
    importedLedger(loaded, saved)
    fireTick(loaded)
    out("after_save_load", applicationCount(sprite, "spwi408") + applicationCount(loaded, "spwi408"))
    loaded.m_pArea = {}
    fireTick(loaded)
    out("after_area_transition", applicationCount(sprite, "spwi408") + applicationCount(loaded, "spwi408"))
    loaded.locals.CBR_TEST_PARTY_REST = 1
    fireTick(loaded)
    out("after_party_rest_only", applicationCount(sprite, "spwi408") + applicationCount(loaded, "spwi408"))
    removeActive(loaded, "spwi408")
    loaded.seeParty = false
    for _, list in pairs(loaded.m_memorizedSpellsMage.levels) do
        for _, record in ipairs(list.values) do restoreRecord(record) end
    end
    fireSpellbookReset(loaded)
    fireTick(loaded)
    out("after_engine_reset", applicationCount(sprite, "spwi408") + applicationCount(loaded, "spwi408"))
end

scenarios.ambient_scs_reimbursement = function()
    local exact = newSprite({})
    memorize(exact, "spwi408", 2)
    fireTick(exact)
    local before = countAvailable(exact, "spwi408")
    fireStarted(exact, { m_actionID = 181, m_string1 = newCString("dwsw408") })
    setFirstAvailable(exact, "spwi408", 0)
    fireStarted(exact, { m_actionID = 147, m_specificID = 2408 })
    out("exact_initial_reimbursed", bool(countAvailable(exact, "spwi408") == before))

    local combat = newSprite({})
    memorize(combat, "spwi408", 2)
    fireTick(combat)
    setFirstAvailable(combat, "spwi408", 0)
    fireStarted(combat, { m_actionID = 31, m_string1 = newCString("spwi408") })
    out("unrelated_combat_reimbursed", bool(countAvailable(combat, "spwi408") > 0))

    local renewal = newSprite({ instantprep = 1 })
    memorize(renewal, "spwi408", 2)
    fireTick(renewal)
    fireStarted(renewal, { m_actionID = 181, m_string1 = newCString("dwsw408") })
    setFirstAvailable(renewal, "spwi408", 0)
    fireStarted(renewal, { m_actionID = 147, m_specificID = 2408 })
    out("renewal_reimbursed", bool(countAvailable(renewal, "spwi408") > 0))
end

scenarios.ambient_transaction_failure = function()
    local apply = newSprite({ failApply = true })
    memorize(apply, "spwi408")
    fireTick(apply)
    for _ = 1, 60 do fireTick(apply) end
    local applyFailures = (CBR_RDY_STATE.ambient_failures[apply.m_id] or {}).spells or {}
    out("apply_availability_restored", countAvailable(apply, "spwi408"))
    out("apply_disabled", (applyFailures.spwi408 or {}).disabled or 0)
    out("apply_attempts", (applyFailures.spwi408 or {}).attempts or 0)

    local quick = newSprite({ failQuickList = true })
    memorize(quick, "spwi408")
    fireTick(quick)
    for _ = 1, 60 do fireTick(quick) end
    local quickFailures = (CBR_RDY_STATE.ambient_failures[quick.m_id] or {}).spells or {}
    out("quick_availability_restored", countAvailable(quick, "spwi408"))
    out("quick_disabled", (quickFailures.spwi408 or {}).disabled or 0)
    out("quick_attempts", (quickFailures.spwi408 or {}).attempts or 0)
end

scenarios.ambient_malformed_ledger = function()
    local malformed = newSprite({})
    memorize(malformed, "spwi408")
    memorize(malformed, "spwi102")
    importedLedger(malformed, {
        version = 1,
        spells = {
            spwi408 = {
                version = 1, resref = "spwi408", charged = "yes",
                expected_expiry = fakeClock + 2400, suppressed = 0,
            },
        },
    })
    fireTick(malformed)
    out("malformed_spell_disabled", active(malformed, "spwi408"))
    out("other_spell_continues", active(malformed, "spwi102"))

    local legacy = newSprite({})
    memorize(legacy, "spwi408")
    importedLedger(legacy, { version = 0, spells = {} })
    fireTick(legacy)
    out("legacy_discarded", active(legacy, "spwi408"))
end

local function primitiveOnly(value, seen)
    local kind = type(value)
    if kind == "nil" or kind == "number" or kind == "string" then return true end
    if kind ~= "table" then return false end
    seen = seen or {}
    if seen[value] then return false end
    seen[value] = true
    for key, child in pairs(value) do
        if not primitiveOnly(key, seen) or not primitiveOnly(child, seen) then return false end
    end
    seen[value] = nil
    return true
end

scenarios.ambient_marshal = function()
    local sprite = newSprite({})
    memorize(sprite, "spwi408")
    fireTick(sprite)
    local ledger = exportedLedger(sprite) or {}
    out("schema_version", ledger.version or 0)
    out("primitive_only", bool(primitiveOnly(ledger)))
    out("has_userdata", bool(type(ledger.sprite) == "userdata"))
    out("has_object_id", bool(ledger.object_id ~= nil or ledger.sprite_id ~= nil))
    local record = ledger.spells and ledger.spells.spwi408 or {}
    local allowed = {
        version = true, resref = true, charged = true,
        expected_expiry = true, suppressed = true,
    }
    local exact = true
    for key in pairs(record) do
        if not allowed[key] then exact = false end
    end
    for key in pairs(allowed) do
        if record[key] == nil then exact = false end
    end
    out("record_fields_exact", bool(exact))
end

scenarios.ambient_runtime_safety = function()
    local disabled = newSprite({})
    memorize(disabled, "spwi408")
    CBR_RDY_AMBIENT_ENABLED = 0
    fireTick(disabled)
    out("ambient_disabled_inert", bool(active(disabled, "spwi408") == 0))
    CBR_RDY_AMBIENT_ENABLED = 1

    local owned = newSprite({})
    memorize(owned, "spwi408")
    CBR_RDY_EXTERNAL_OWNER = 1
    fireTick(owned)
    out("ambient_owner_inert", bool(active(owned, "spwi408") == 0))

    CBR_RDY_EXTERNAL_OWNER = 0

    reloadRuntime()
    out("listeners_after_reload", #deferredTickListeners + #legacyTickListeners)

    local fault = newSprite({ failVisibility = true })
    memorize(fault, "spwi408")
    fireTick(fault)
    removeActive(fault, "spwi408")
    advanceClockSeconds(2400)
    for _ = 1, 30 do fireTick(fault) end
    out("ambient_tracebacks", countPrinted("ambient disabled"))
    out("ambient_inert_after_fault", bool(applicationCount(fault, "spwi408") == 1))
end

scenarios.ambient_sprite_lifetime = function()
    local first = newSprite({ id = 7001, failApply = true })
    memorize(first, "spwi408")
    fireTick(first)
    local replacement = newSprite({ id = 7001 })
    memorize(replacement, "spwi408")
    fireTick(replacement)
    out("replacement_active", active(replacement, "spwi408"))
    out("replacement_available_after", countAvailable(replacement, "spwi408"))
end

scenarios.ambient_incomplete_effect_view = function()
    local sprite = newSprite({ equippedEffectsUnavailable = true })
    memorize(sprite, "spwi408")
    fireTick(sprite)
    out("effect_active", active(sprite, "spwi408"))
    out("available_after", countAvailable(sprite, "spwi408"))
    out("ambient_faulted", CBR_RDY_STATE.ambient_faulted or 0)
end

local function urgentResult(options, spells)
    local sprite = newSprite(options)
    for _, resref in ipairs(spells or { "spwi611" }) do memorize(sprite, resref) end
    fireTick(sprite)
    return sprite
end

scenarios.urgent_hard_gates = function()
    out("eligible", bool(urgentResult({}, { "spwi611" }).queueCount == 1))
    out("not_hostile", bool(urgentResult({ ea = 128 }, { "spwi611" }).queueCount > 0))
    out("not_visible", bool(urgentResult({ seeParty = false }, { "spwi611" }).queueCount > 0))
    out("unsettled", bool(urgentResult({ settled = false }, { "spwi611" }).queueCount > 0))
    out("unrecognized", bool(urgentResult({ scsCaster = false }, { "spwi611" }).queueCount > 0))
    out("unconscious", bool(urgentResult({ conscious = false }, { "spwi611" }).queueCount > 0))
    out("already_protected", bool(urgentResult({ genuineWeaponImmunity = true }, { "spwi611" }).queueCount > 0))
    out("unknown_effect_lists", bool(urgentResult({ effectListsUnavailable = true }, { "spwi611" }).queueCount > 0))
    out("partial_effect_lists", bool(urgentResult({ timedEffectsUnavailable = true }, { "spwi611" }).queueCount > 0))
    out("no_slot", bool(urgentResult({}, {}).queueCount > 0))
    out("dialogue", bool(urgentResult({ action = 137 }, { "spwi611" }).queueCount > 0))
    out("cutscene", bool(urgentResult({ cutscene = true }, { "spwi611" }).queueCount > 0))
end

local function queuedResref(sprite)
    local response = sprite.queuedResponses[1] or ""
    return lower(response:match('[Ss]pellRES%(%s*"([^"]+)"') or "")
end

scenarios.urgent_candidates = function()
    local all = urgentResult({}, { "spwi907", "spwi808", "spwi708", "spwi611" })
    out("all_available", queuedResref(all))
    local noAbsolute = urgentResult({}, { "spwi808", "spwi708", "spwi611" })
    out("without_absolute", queuedResref(noAbsolute))
    local pfmw = urgentResult({}, { "spwi808", "spwi611" })
    out("pfmw_fallback", queuedResref(pfmw))
    out("moment_of_prescience_selected", bool(queuedResref(noAbsolute) == "spwi808" or queuedResref(pfmw) == "spwi808"))
end

scenarios.urgent_action_safety = function()
    local cases = {
        idle = { action = 0 },
        wander = { action = 85 },
        movement = { action = 23 },
        cast = { action = 31 },
        attack = { action = 3 },
        tactical = { action = 100 },
        dialogue = { action = 137 },
        cutscene = { action = 121 },
        passive_queue = { action = 0, queue = { { m_actionID = 23 }, { m_actionID = 85 } } },
        unsafe_queue = { action = 0, queue = { { m_actionID = 3 } } },
        unknown_queue = { action = 0, queueUnavailable = true },
    }
    for key, options in pairs(cases) do
        local sprite = urgentResult(options, { "spwi611" })
        out(key, bool(sprite.queueCount > 0))
    end
end

scenarios.urgent_project_image = function()
    out("ordinary_actor", bool(urgentResult({}).queueCount == 1))

    local uncertain = newSprite({})
    memorize(uncertain, "spwi611")
    addProjectImageClone(uncertain, -1)
    fireTick(uncertain)
    out("owner_uncertain", bool(uncertain.queueCount > 0))

    local owner = newSprite({})
    memorize(owner, "spwi611")
    addProjectImageOwnerLock(owner)
    fireTick(owner)
    out("locked_owner", bool(owner.queueCount > 0))

    local clone = newSprite({})
    memorize(clone, "spwi611")
    addProjectImageClone(clone, owner.m_id)
    fireTick(clone)
    out("valid_clone", bool(clone.queueCount > 0))
end

scenarios.urgent_normal_cast = function()
    local sprite = urgentResult({}, { "spwi611" })
    out("queued_spellres", bool(queuedResref(sprite) == "spwi611"))
    out("direct_effects", sprite.directEffects)
    out("engine_slot_debits", sprite.engineSlotDebits)
    out("engine_aura", sprite.engineAura)
    out("engine_casting_time", sprite.engineCastingTime)
    out("interruptible", 1)
end

scenarios.urgent_interrupted_started = function()
    local sprite = urgentResult({ interrupted = true }, { "spwi611" })
    for _ = 1, 30 do fireTick(sprite) end
    local state = EEex_GetUDAux(sprite).CBR_RDY_CONTACT or {}
    out("started", sprite.starts)
    out("effect_active", active(sprite, "spwi611"))
    out("engine_slot_debits", sprite.engineSlotDebits)
    out("available_after", countAvailable(sprite, "spwi611"))
    out("queues", sprite.queueCount)
    out("episode_spent", state.spent or 0)
end

scenarios.urgent_never_started_retry = function()
    local sprite = newSprite({ autoStart = false })
    memorize(sprite, "spwi611")
    fireTick(sprite)
    advanceClockSeconds(2)
    fireTick(sprite)
    advanceClockSeconds(2)
    fireTick(sprite)
    advanceClockSeconds(20)
    for _ = 1, 30 do fireTick(sprite) end
    local state = EEex_GetUDAux(sprite).CBR_RDY_CONTACT or {}
    out("queues", sprite.queueCount)
    out("starts", sprite.starts)
    out("episode_spent", state.spent or 0)
end

scenarios.urgent_never_started_unsafe_queue = function()
    local sprite = newSprite({ autoStart = false, retainFailedQueue = true })
    memorize(sprite, "spwi611")
    fireTick(sprite)
    advanceClockSeconds(2)
    fireTick(sprite)
    local state = EEex_GetUDAux(sprite).CBR_RDY_CONTACT or {}
    out("queues", sprite.queueCount)
    out("episode_spent", state.spent or 0)
end

scenarios.urgent_contact_rearm = function()
    local sprite = newSprite({ interrupted = true })
    memorize(sprite, "spwi611", 2)
    fireTick(sprite)
    for _ = 1, 30 do fireTick(sprite) end
    out("continuous_sight_queues", sprite.queueCount)
    sprite.seeParty = false
    fireTick(sprite)
    advanceClockSeconds(5)
    fireTick(sprite)
    sprite.seeParty = true
    fireTick(sprite)
    out("short_loss_queues", sprite.queueCount)
    sprite.seeParty = false
    fireTick(sprite)
    advanceClockSeconds(6)
    fireTick(sprite)
    sprite.seeParty = true
    fireTick(sprite)
    out("full_round_loss_queues", sprite.queueCount)
end

scenarios.v12_world_time_units = function()
    local sprite = newSprite({ autoStart = false })
    memorize(sprite, "spwi611")
    fireTick(sprite)
    advanceClockTicks(2)
    fireTick(sprite)
    out("queues_before_two_seconds", sprite.queueCount)
    advanceClockTicks(28)
    fireTick(sprite)
    out("queues_at_two_seconds", sprite.queueCount)
end

scenarios.urgent_fault_fuse = function()
    local fault = newSprite({ failVisibility = true })
    memorize(fault, "spwi611")
    fireTick(fault)
    fireTick(fault)
    out("urgent_tracebacks", countPrinted("urgent disabled"))
    out("urgent_inert_after_fault", bool(fault.queueCount == 0))
    local ambient = newSprite({ seeParty = false })
    memorize(ambient, "spwi408")
    fireTick(ambient)
    out("ambient_still_active", active(ambient, "spwi408"))
end

-------------------------------------------------------------------------------

assert(runtimePath and scenarioName,
    "usage: lua ambient_readiness_sim.lua <stamped-runtime.lua> <scenario>")
if scenarioName == "runtime_missing_urgent_api" then
    EEex_Sprite_GetState = nil
elseif scenarioName == "runtime_missing_ambient_api" then
    EEex_GameObject_ApplyEffect = nil
elseif scenarioName == "runtime_missing_game_time"
        or scenarioName == "runtime_missing_game_time_callbacks" then
    EngineGlobals.g_pBaldurChitin.m_pObjectGame.m_worldTime = nil
elseif scenarioName == "runtime_legacy_v011_surface"
        or scenarioName == "runtime_legacy_repeated_callbacks"
        or scenarioName == "runtime_legacy_marshal_exports"
        or scenarioName == "runtime_legacy_missing_raw_time" then
    EEex_Opcode_AddDeferredListsResolvedListener = nil
    fakeWorldTime.GetCurrentTime = nil
    if scenarioName == "runtime_legacy_missing_raw_time" then
        fakeWorldTime.m_gameTime = nil
    end
end
reloadRuntime()
out("tick_listeners", #deferredTickListeners + #legacyTickListeners)
out("deferred_tick_listeners", #deferredTickListeners)
out("legacy_tick_listeners", #legacyTickListeners)
out("started_action_listeners", #startedActionListeners)
out("reset_listeners", #resetListeners)
local marshalCount = 0
for _ in pairs(marshalHandlers) do marshalCount = marshalCount + 1 end
out("marshal_handlers", marshalCount)
local scenario = scenarios[scenarioName]
assert(scenario, "unknown scenario " .. tostring(scenarioName))
scenario()
print = originalPrint
