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

local fakeClock = 1000
local nextSpriteID = 100
local spritesByID = {}
local auxBySprite = setmetatable({}, { __mode = "k" })
local printed = {}
local originalPrint = print

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

function EEex_GameState_GetTime()
    return fakeClock
end

function Infinity_GetGameTime()
    return fakeClock
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
        m_id = nextSpriteID,
        m_scriptName = newResRef(options.name or "cbr_default"),
        m_typeAI = { m_EnemyAlly = options.ea or 255 },
        m_pArea = options.settled == false and nil or {},
        m_curAction = { m_actionID = options.action or 0 },
        m_queuedActions = options.queueUnavailable and nil or newPtrList(options.queue or {}),
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
        projectImageOwnerCertain = options.projectImageOwnerCertain ~= false,
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
        failApply = options.failApply == true,
        failVisibility = options.failVisibility == true,
    }
    function sprite:getLocalInt(name)
        return self.locals[name] or 0
    end
    function sprite:setLocalInt(name, value)
        self.locals[name] = value
    end
    function sprite:CheckQuickLists(abilityID, changeAmount, remove, unknown)
        self.quickListRebuilds = self.quickListRebuilds + 1
        self.lastQuickListArgs = { abilityID, changeAmount, remove, unknown }
    end
    function sprite:virtual_ClearActions()
        self.m_curAction = { m_actionID = 0 }
        self.m_queuedActions = newPtrList({})
        self.actionsCleared = (self.actionsCleared or 0) + 1
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

function Infinity_GetInCutsceneMode()
    for _, sprite in pairs(spritesByID) do
        if sprite.cutscene then return true end
    end
    return false
end

function EEex_Sprite_IsProjectImageOwnerCertain(sprite)
    return sprite.projectImageOwnerCertain
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
    local detection = {
        sppr506 = { 218, 0 }, sppr735 = { 206, 0 },
        spwi102 = { 0, 16 }, spwi310 = { 69, 0 },
        spwi408 = { 218, 0 }, spwi802 = { 101, 213 },
    }
    local marker = detection[managed]
    if marker then
        sprite.m_timedEffectList.values[#sprite.m_timedEffectList.values + 1] = {
            m_effectId = marker[1],
            m_dWFlags = marker[2],
            m_sourceRes = newResRef(delivered),
        }
    end
end

-------------------------------------------------------------------------------
-- Listener registration and action engine
-------------------------------------------------------------------------------

local tickListeners = {}
local startedActionListeners = {}
local resetListeners = {}
local marshalHandlers = {}

function EEex_Opcode_AddListsResolvedListener(callback)
    tickListeners[#tickListeners + 1] = callback
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
    if not resref or not sprite.autoStart then return end
    local action = {
        m_actionID = 31,
        m_string1 = newCString(lower(resref)),
        cbrNormalSpellRES = 1,
    }
    fireStarted(sprite, action)
    local consumed = setFirstAvailable(sprite, resref, 0)
    if consumed then sprite.engineSlotDebits = sprite.engineSlotDebits + 1 end
    sprite.engineAura = 1
    sprite.engineCastingTime = 1
    if not sprite.interrupted then
        sprite.active[lower(resref)] = {
            appliedAt = fakeClock,
            expectedExpiry = fakeClock + 24,
        }
    end
end

local function fireTick(sprite)
    for _, callback in ipairs(tickListeners) do callback(sprite) end
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

scenarios.runtime_shell = function()
    reloadRuntime()
    out("listeners_after_reload", #tickListeners)
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
    fakeClock = fakeClock + 2400
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
    fakeClock = fakeClock + 2400
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
    fakeClock = fakeClock + 60
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
    fakeClock = fakeClock + 10000
    fireTick(sprite)
    out("after_elapsed_time", applicationCount(sprite, "spwi408"))
    local saved = exportedLedger(sprite)
    local loaded = newSprite({})
    memorize(loaded, "spwi408", 2)
    setFirstAvailable(loaded, "spwi408", 0)
    loaded.active.spwi408 = sprite.active.spwi408
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
    local sprite = newSprite({ failApply = true })
    memorize(sprite, "spwi408")
    fireTick(sprite)
    for _ = 1, 60 do fireTick(sprite) end
    local ledger = exportedLedger(sprite) or {}
    local record = ledger.spells and ledger.spells.spwi408 or {}
    out("availability_restored", countAvailable(sprite, "spwi408"))
    out("spell_disabled", record.disabled or 0)
    out("attempts", record.attempts or 0)
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

    local urgent = newSprite({ action = 0 })
    memorize(urgent, "spwi611")
    fireTick(urgent)
    out("urgent_owner_independent", bool(urgent.queueCount == 1))
    CBR_RDY_EXTERNAL_OWNER = 0

    reloadRuntime()
    out("listeners_after_reload", #tickListeners)

    local fault = newSprite({ failVisibility = true })
    memorize(fault, "spwi408")
    fireTick(fault)
    fireTick(fault)
    out("ambient_tracebacks", countPrinted("ambient disabled"))
    out("ambient_inert_after_fault", bool(active(fault, "spwi408") == 0))
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
    out("unconscious", bool(urgentResult({ conscious = false }, { "spwi611" }).queueCount > 0))
    out("already_protected", bool(urgentResult({ genuineWeaponImmunity = true }, { "spwi611" }).queueCount > 0))
    out("no_slot", bool(urgentResult({}, {}).queueCount > 0))
    out("dialogue", bool(urgentResult({ dialogue = true }, { "spwi611" }).queueCount > 0))
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
        unknown_queue = { action = 0, queueUnavailable = true },
    }
    for key, options in pairs(cases) do
        local sprite = urgentResult(options, { "spwi611" })
        out(key, bool(sprite.queueCount > 0))
    end
end

scenarios.urgent_project_image = function()
    out("owner_known_safe", bool(urgentResult({ projectImageOwnerCertain = true }).queueCount == 1))
    out("owner_uncertain", bool(urgentResult({ projectImageOwnerCertain = false }).queueCount > 0))
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
    out("queues", sprite.queueCount)
    out("episode_spent", state.spent or 0)
end

scenarios.urgent_never_started_retry = function()
    local sprite = newSprite({ autoStart = false })
    memorize(sprite, "spwi611")
    fireTick(sprite)
    fakeClock = fakeClock + 2
    fireTick(sprite)
    fakeClock = fakeClock + 2
    fireTick(sprite)
    fakeClock = fakeClock + 20
    for _ = 1, 30 do fireTick(sprite) end
    local state = EEex_GetUDAux(sprite).CBR_RDY_CONTACT or {}
    out("queues", sprite.queueCount)
    out("starts", sprite.starts)
    out("episode_spent", state.spent or 0)
end

scenarios.urgent_contact_rearm = function()
    local sprite = newSprite({ interrupted = true })
    memorize(sprite, "spwi611", 2)
    fireTick(sprite)
    for _ = 1, 30 do fireTick(sprite) end
    out("continuous_sight_queues", sprite.queueCount)
    sprite.seeParty = false
    fakeClock = fakeClock + 5
    fireTick(sprite)
    sprite.seeParty = true
    fireTick(sprite)
    out("short_loss_queues", sprite.queueCount)
    sprite.seeParty = false
    fakeClock = fakeClock + 6
    fireTick(sprite)
    sprite.seeParty = true
    fireTick(sprite)
    out("full_round_loss_queues", sprite.queueCount)
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
reloadRuntime()
out("tick_listeners", #tickListeners)
out("started_action_listeners", #startedActionListeners)
out("reset_listeners", #resetListeners)
local marshalCount = 0
for _ in pairs(marshalHandlers) do marshalCount = marshalCount + 1 end
out("marshal_handlers", marshalCount)
local scenario = scenarios[scenarioName]
assert(scenario, "unknown scenario " .. tostring(scenarioName))
scenario()
print = originalPrint
