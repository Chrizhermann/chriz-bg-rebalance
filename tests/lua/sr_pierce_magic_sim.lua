-- Narrow EEex mock: business behavior, not native engine acceptance evidence.
-- Usage: lua sr_pierce_magic_sim.lua <stamped-runtime> <scenario>
local modulePath, scenario = arg[1], arg[2]
assert(modulePath and scenario, "missing simulator arguments")

local OWNER, now = "CBRPM", 1000
local calls, logs, statReads, listeners = {}, {}, 0, {}
local auxiliary = setmetatable({}, {__mode = "k"})
local worldTime = {m_gameTime = now}
EEex_EngineGlobal_CBaldurChitin = {m_pObjectGame = {m_worldTime = worldTime}}
EngineGlobals = {g_pBaldurChitin = EEex_EngineGlobal_CBaldurChitin}
EEex_Active = true
EEex_BAnd = function(a, b) return a & b end
bit = {band = EEex_BAnd}
print = function(...)
    local values = {...}
    for i, value in ipairs(values) do values[i] = tostring(value) end
    logs[#logs + 1] = table.concat(values, " ")
end

local function out(key, value) io.write(key, "\t", tostring(value), "\n") end
local function check(condition, message) assert(condition, message) end
local function equal(actual, expected, message)
    assert(actual == expected, (message or "unexpected value") .. ": expected "
        .. tostring(expected) .. ", got " .. tostring(actual))
end
local function setTime(value) now = value; worldTime.m_gameTime = value end
local function ref(value) return {get = function() return value end} end

local nativeKeys = {
    m_effectId = true, m_effectAmount = true, m_dWFlags = true,
    m_durationType = true, m_duration = true, m_sourceRes = true,
    m_done = true, m_deleted = true, m_sourceId = true,
    m_sourceTarget = true, m_sourceType = true, m_sourceFlags = true,
    m_casterLevel = true, m_flags = true, m_spellLevel = true,
}
local function nativeEffect(values)
    local data = {
        m_effectId = 166, m_effectAmount = 0, m_dWFlags = 0,
        m_durationType = 4096, m_duration = now + 450,
        m_sourceRes = ref(OWNER), m_done = 0, m_deleted = 0,
        m_sourceId = 77, m_sourceTarget = 42, m_sourceType = 1,
        m_sourceFlags = 0, m_casterLevel = 15, m_flags = 2, m_spellLevel = 0,
    }
    for key, value in pairs(values or {}) do data[key] = value end
    return setmetatable({}, {
        __index = function(_, key)
            if not nativeKeys[key] then error("unknown CGameEffect field: " .. tostring(key)) end
            return data[key]
        end,
        __newindex = function(_, key, value)
            if not nativeKeys[key] then error("unknown CGameEffect write: " .. tostring(key)) end
            data[key] = value
        end,
    })
end
local function active(effect)
    return effect.m_done ~= 1 and effect.m_done ~= true
        and effect.m_deleted ~= 1 and effect.m_deleted ~= true
        and effect.m_durationType == 4096 and effect.m_duration > now
end
local function owned(effect)
    return effect.m_sourceRes:get():upper() == OWNER
end
local function newSprite(base)
    return {m_id = 42, base = base, m_timedEffectList = {}, m_equippedEffectList = {}}
end
local function calculateMR(sprite)
    local result = sprite.base
    for _, effect in ipairs(sprite.m_timedEffectList) do
        if active(effect) and effect.m_effectId == 166 and effect.m_dWFlags == 0 then
            result = result + effect.m_effectAmount
        end
    end
    return math.max(0, result)
end
EEex_Sprite_GetStat = function(sprite, stat)
    equal(stat, 18, "runtime must use stamped MR stat")
    statReads = statReads + 1
    return sprite.staleMR ~= nil and sprite.staleMR or calculateMR(sprite)
end
EEex_Utility_IterateCPtrList = function(list, fn)
    for _, effect in ipairs(list) do if fn(effect) then break end end
end

local allowedArgs = {}
for _, key in ipairs({
    "effectID", "targetType", "spellLevel", "effectAmount", "dwFlags",
    "durationType", "duration", "effectList", "immediateResolve", "m_flags",
    "savingThrow", "saveMod", "probabilityUpper", "probabilityLower", "noSave",
    "m_sourceRes", "m_sourceType", "m_sourceFlags", "m_casterLevel", "sourceID",
    "sourceTarget", "m_school", "m_secondaryType", "res", "special",
}) do allowedArgs[key] = true end

EEex_GameObject_ApplyEffect = function(sprite, args)
    for key in pairs(args) do check(allowedArgs[key], "unknown applyEffect argument: " .. key) end
    calls[#calls + 1] = args
    local timing = args.durationType or 0
    check(timing == 0 or timing == 10, "new effects use limited seconds or limited ticks")
    local lifetime = args.duration * (timing == 0 and 15 or 1)
    check(lifetime > 0 and lifetime <= 450, "new lifetime fits original five-round window")
    equal(args.effectList or 1, 1, "timed list")
    equal(args.dwFlags or 0, args.effectID == 142 and 106 or 0, "opcode parameter2")
    equal(args.m_sourceRes, OWNER, "private owner")
    equal(args.m_sourceType, 1, "spell source type")
    equal(args.m_flags, 2, "SR MR bypass and nondispellability")
    equal(args.savingThrow or 0, 0, "no saving throw")
    check(args.noSave == nil or args.noSave == 0 or args.noSave == false,
        "runtime must not bypass native effect immunities")
    check(args.effectID == 166 or args.effectID == 142, "unexpected applied opcode")
    if args.effectID == 166 and sprite.blockMR then return end
    local effect = nativeEffect({
        m_effectId = args.effectID, m_effectAmount = args.effectAmount or 0,
        m_dWFlags = args.dwFlags or 0,
        m_durationType = 4096, m_duration = now + lifetime,
        m_sourceRes = ref(args.m_sourceRes), m_sourceId = args.sourceID or -1,
        m_sourceTarget = args.sourceTarget or -1, m_sourceType = args.m_sourceType,
        m_sourceFlags = args.m_sourceFlags or 0, m_casterLevel = args.m_casterLevel or 0,
    })
    sprite.m_timedEffectList[#sprite.m_timedEffectList + 1] = effect
    -- Like the real wrapper, return no success result or effect handle.
end

EEex_GetUDAux = function(sprite)
    auxiliary[sprite] = auxiliary[sprite] or {}
    return auxiliary[sprite]
end
EEex_Opcode_AddListsResolvedListener = function(fn) listeners[#listeners + 1] = fn end
local function resolved(sprite)
    for _, listener in ipairs(listeners) do listener(sprite) end
end
local function forbidden() error("runtime must keep its saved snapshot in native effects") end
EEex_Sprite_SetLocalInt = forbidden
EEex_Sprite_AddMarshalHandlers = forbidden

local function hit(sprite)
    CBRPM(nativeEffect({m_effectId = 402, m_sourceRes = ref("SPWI608B")}), sprite)
end
local function ownedEffects(sprite, opcode, onlyActive)
    local result = {}
    for _, effect in ipairs(sprite.m_timedEffectList) do
        if owned(effect) and effect.m_effectId == opcode and (not onlyActive or active(effect)) then
            result[#result + 1] = effect
        end
    end
    return result
end
local function snapshot(sprite)
    local effects = ownedEffects(sprite, 166, true)
    equal(#effects, 1, "exactly one active owned MR contribution")
    return effects[1]
end
local function icon(sprite)
    local effects = ownedEffects(sprite, 142, true)
    equal(#effects, 1, "exactly one active owned icon")
    equal(effects[1].m_dWFlags, 106, "MR lowered portrait icon")
    return effects[1]
end
local function fingerprint(effect)
    return table.concat({effect.m_effectId, effect.m_effectAmount, effect.m_dWFlags,
        effect.m_durationType, effect.m_duration, effect.m_sourceRes:get(),
        tostring(effect.m_done), effect.m_sourceId, effect.m_sourceTarget}, "|")
end

dofile(modulePath)
check(type(CBRPM) == "function", "runtime must publish global CBRPM(effect, sprite)")
local scenarios = {}

scenarios.curve = function()
    for value = 0, 150 do
        local sprite = newSprite(value)
        hit(sprite)
        local effect = snapshot(sprite)
        equal(calls[#calls - 1].durationType or 0, 0, "fresh impact uses seconds")
        equal(calls[#calls - 1].duration, 30, "fresh impact lasts five rounds")
        equal(effect.m_sourceId, 77, "preserve impact caster")
        equal(effect.m_sourceTarget, 42, "preserve impact target")
        equal(effect.m_casterLevel, 15, "preserve impact caster level")
        equal(effect.m_duration, now + 450)
        equal(icon(sprite).m_duration, now + 450)
        out("mr_" .. value, calculateMR(sprite))
    end
    local negative = newSprite(-10)
    negative.staleMR = -10 -- exercise the callback's clamp, not this mock's clamp
    hit(negative)
    out("negative_snapshot", -snapshot(negative).m_effectAmount)
end

scenarios.same_frame = function()
    local sprite = newSprite(100)
    for _ = 1, 25 do hit(sprite) end
    equal(calculateMR(sprite), 60)
    equal(snapshot(sprite).m_effectAmount, -40)
    equal(#ownedEffects(sprite, 166, false), 1)
    equal(#ownedEffects(sprite, 142, false), 1)
    equal(#calls, 2, "refresh must not remove and reapply")
end

scenarios.refresh = function()
    local sprite = newSprite(60)
    hit(sprite)
    local original, oldIcon = snapshot(sprite), icon(sprite)
    setTime(1200)
    hit(sprite)
    equal(snapshot(sprite), original, "keep original effect record")
    equal(icon(sprite), oldIcon, "keep original icon record")
    equal(original.m_effectAmount, -30)
    equal(original.m_durationType, 4096)
    equal(original.m_duration, 1650)
    equal(oldIcon.m_duration, 1650)
    equal(#calls, 2)
end

scenarios.changed_resistance = function()
    local sprite = newSprite(80)
    hit(sprite)
    sprite.base = 110
    setTime(1100)
    hit(sprite)
    equal(snapshot(sprite).m_effectAmount, -40)
    equal(calculateMR(sprite), 70)
    sprite.base = 20
    hit(sprite)
    equal(snapshot(sprite).m_effectAmount, -40)
    equal(calculateMR(sprite), 0)
end

scenarios.foreign_effects = function()
    local sprite = newSprite(60)
    local lower = nativeEffect({m_effectAmount = -20, m_sourceRes = ref("SPWI514"), m_duration = 5000})
    local foreignIcon = nativeEffect({m_effectId = 142, m_dWFlags = 106,
        m_sourceRes = ref("SPWI514"), m_duration = 5000})
    sprite.m_timedEffectList = {lower, foreignIcon}
    local before, iconBefore = fingerprint(lower), fingerprint(foreignIcon)
    hit(sprite)
    equal(snapshot(sprite).m_effectAmount, -20)
    equal(calculateMR(sprite), 20)
    setTime(1300)
    hit(sprite)
    equal(calculateMR(sprite), 20)
    equal(fingerprint(lower), before, "Lower Resistance must not be refreshed or removed")
    equal(fingerprint(foreignIcon), iconBefore)
end

scenarios.zero_snapshot = function()
    local sprite = newSprite(0)
    hit(sprite)
    equal(snapshot(sprite).m_effectAmount, 0)
    sprite.base = 70
    setTime(1100)
    hit(sprite)
    equal(snapshot(sprite).m_effectAmount, 0)
    equal(calculateMR(sprite), 70)
    equal(#calls, 2)
end

scenarios.save_load = function()
    local sprite = newSprite(70)
    hit(sprite)
    -- Serialize only primitive native-effect state; no retained userdata/Lua table.
    local rows = {}
    for _, effect in ipairs(sprite.m_timedEffectList) do
        rows[#rows + 1] = string.format("{%d,%d,%d,%d,%d,%q}", effect.m_effectId,
            effect.m_effectAmount, effect.m_dWFlags, effect.m_durationType,
            effect.m_duration, effect.m_sourceRes:get())
    end
    local saved = assert(load("return {" .. table.concat(rows, ",") .. "}"))()
    sprite = newSprite(90)
    for _, row in ipairs(saved) do
        sprite.m_timedEffectList[#sprite.m_timedEffectList + 1] = nativeEffect({
            m_effectId = row[1], m_effectAmount = row[2], m_dWFlags = row[3],
            m_durationType = row[4], m_duration = row[5], m_sourceRes = ref(row[6]),
        })
    end
    CBRPM = nil
    dofile(modulePath)
    setTime(1250)
    hit(sprite)
    equal(snapshot(sprite).m_effectAmount, -35)
    equal(snapshot(sprite).m_duration, 1700)
    equal(calculateMR(sprite), 55)
    equal(#calls, 2, "reload must reuse serialized snapshot")
end

local function staleRecord(done)
    local sprite = newSprite(60)
    local old = nativeEffect({m_effectAmount = -30,
        m_duration = done and 2000 or now, m_done = done and 1 or 0})
    sprite.m_timedEffectList = {old}
    sprite.staleMR = 30
    local before = fingerprint(old)
    hit(sprite)
    equal(#calls, 0, "expiry-boundary callback must not use cached old MR")
    local pending = EEex_GetUDAux(sprite).CBRPM_pending
    check(type(pending) == "table", "stale owned effect requires pending scalar impact")
    local function scalarTree(value)
        local kind = type(value)
        if kind == "table" then
            check(getmetatable(value) == nil, "pending state must not retain native wrappers")
            for key, child in pairs(value) do
                check(type(key) == "string" or type(key) == "number", "scalar pending keys")
                scalarTree(child)
            end
        else check(kind == "number" or kind == "string" or kind == "boolean", "scalar pending values") end
    end
    scalarTree(pending)
    resolved(sprite)
    equal(#calls, 0, "wait while stale native record is still linked")
    -- Engine removes the expired record and rebuilds derived stats before this hook.
    sprite.m_timedEffectList = {}
    sprite.staleMR = nil
    setTime(1015)
    resolved(sprite)
    equal(snapshot(sprite).m_effectAmount, -30, "read rebuilt60, not stale30")
    equal(calculateMR(sprite), 30)
    equal(snapshot(sprite).m_duration, 1450, "five rounds measured from original impact")
    equal(icon(sprite).m_duration, 1450)
    equal(fingerprint(old), before, "stale record must not be revived")
    local after = #calls
    resolved(sprite)
    equal(#calls, after, "pending impact consumed once")
end
scenarios.expired = function() staleRecord(false) end
scenarios.done = function() staleRecord(true) end

scenarios.pending_expired = function()
    local sprite = newSprite(60)
    sprite.m_timedEffectList = {nativeEffect({m_effectAmount = -30, m_duration = now})}
    sprite.staleMR = 30
    hit(sprite)
    equal(#calls, 0)
    setTime(1451)
    sprite.m_timedEffectList = {}
    sprite.staleMR = nil
    resolved(sprite)
    equal(#calls, 0, "do not apply after original five-round window")
    equal(#ownedEffects(sprite, 166, true), 0)
end

scenarios.foreign_owner_only = function()
    local sprite = newSprite(80)
    local foreign = nativeEffect({m_effectAmount = -10, m_sourceRes = ref("CBRPMX")})
    sprite.m_timedEffectList = {foreign}
    local before = fingerprint(foreign)
    hit(sprite)
    equal(snapshot(sprite).m_effectAmount, -35)
    equal(calculateMR(sprite), 35)
    equal(fingerprint(foreign), before)
end

scenarios.immunity = function()
    local sprite = newSprite(60)
    sprite.blockMR = true
    pcall(hit, sprite)
    equal(#ownedEffects(sprite, 166, false), 0, "native immunity must be respected")
    equal(#ownedEffects(sprite, 142, false), 0, "blocked MR effect must not advertise success")
    equal(calculateMR(sprite), 60)
    check(#calls >= 1, "immunity scenario must actually exercise native application")
end

local function invalidOwned(kind)
    local sprite = newSprite(60)
    local bad = nativeEffect({m_effectAmount = -20})
    if kind == "wrong_mode" then bad.m_dWFlags = 1
    elseif kind == "positive_amount" then bad.m_effectAmount = 20
    elseif kind == "invalid_amount" then bad.m_effectAmount = "bad"
    elseif kind == "permanent" then bad.m_durationType = 9
    elseif kind == "relative_timing" then bad.m_durationType = 0 end
    sprite.m_timedEffectList = {bad}
    if kind == "duplicate" then
        sprite.m_timedEffectList[2] = nativeEffect({m_effectAmount = -25})
    end
    local originalExpiry = bad.m_duration
    local ok = pcall(hit, sprite)
    equal(ok, false, "invalid owned state must report an error")
    equal(#calls, 0, "invalid state must not add or remove any effect")
    equal(bad.m_duration, originalExpiry, "preflight must precede expiry refresh")
end
for _, name in ipairs({"duplicate", "wrong_mode", "positive_amount", "invalid_amount", "permanent", "relative_timing"}) do
    scenarios[name] = function() invalidOwned(name) end
end

check(scenarios[scenario], "unknown scenario: " .. scenario)
scenarios[scenario]()
out("scenario_ok", scenario)
