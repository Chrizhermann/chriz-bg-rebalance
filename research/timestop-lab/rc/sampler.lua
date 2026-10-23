-- Per-frame sampler of the Time Clocks lab, in memory until sampler-export.lua writes it out.
-- The first call wraps EEexRemote.Poll (the console's per-frame call) and registers a global
-- projectile mutator; both stay for the life of the process. Every call:
-- ARGS.ids: the tracked creatures, comma-separated object IDs (default: portraits 0 and 1).
-- ARGS.sources: the tracked effect sources, comma-separated resrefs (default below).
-- ARGS.on = "0" stops recording (default "1").
-- A record is kept only when something but the frame changed: world tick, pause, Time Stop
-- counter and caster, each creature's HP, AI speed, effect clocks, action and tracked timed
-- effects, and each tracked projectile's state. Projectiles: each one decoded while recording,
-- found by its address in the object array once it has an ID; an area projectile also shows
-- arrival (+0x3C8), remaining explosions (+0x3C6), pulse countdown (+0x3CE) and its reload
-- (+0x3CC), as CProjectileArea::AIUpdate counts them (0x1402284B0). Script actions can mark the
-- tick they run on with EEex_LuaAction("CBTCLab_Mark('label')") (tc-queue.lua's mark step).
-- Diagnostic code for the pinned 2.7.3.0 x64 executable only (the observer checks it).
assert(EEex_GetImageBase and EEex_Read32 and EEex_ReadU16 and EEex_ReadPtr and EEex_Projectile_RegisterGlobalMutator,
    "EEEX_REQUIRED")
assert(type(EEexRemote) == "table" and type(EEexRemote.Poll) == "function", "CONSOLE_REQUIRED")
local function list(text)
    local out = {}
    for item in text:gmatch("[^,%s]+") do out[#out + 1] = item end
    return out
end
local args = type(ARGS) == "table" and ARGS or {}
local base = EEex_GetImageBase()
CBTCLab = CBTCLab or {records = {}, count = 0, max = 60000, overflow = false, lastKey = nil, lastFrame = -1,
    projectiles = {}, pending = {}, active = false, ids = {}, sources = {}, errors = 0,
    -- CGameObjectArray (GetDeny 0x140276700): entries of 16 bytes from 0x14068F910, a word
    -- uniqueness at +0 and the object at +8; the highest index in use is the word at 0x14068F8F4.
    array = base + 0x68F910, arrayTop = base + 0x68F8F4,
    chitin = base + 0x667548, scheduler = base + 0x667560}
local S = CBTCLab
assert(EEex_ReadU16(base + 0x27671B) == 0x3966 and EEex_ReadU16(base + 0x276735) == 0x8D4C,
    "UNEXPECTED_OBJECT_ARRAY_CODE")
assert(base + 0x276722 + EEex_Read32(base + 0x27671E) == S.arrayTop
    and base + 0x27673C + EEex_Read32(base + 0x276738) == S.array, "UNEXPECTED_OBJECT_ARRAY")

local function json(value)
    local kind = type(value)
    if kind == "number" then
        if value ~= value or value == math.huge or value == -math.huge then return "null" end
        return value % 1 == 0 and string.format("%d", value) or string.format("%.17g", value)
    elseif kind == "string" then
        return '"' .. value:gsub('[%c"\\]', function(c) return string.format("\\u%04x", c:byte()) end) .. '"'
    elseif kind == "boolean" then
        return value and "true" or "false"
    elseif kind == "table" then
        if value[1] ~= nil or next(value) == nil then
            local parts = {}
            for _, v in ipairs(value) do parts[#parts + 1] = json(v) end
            return "[" .. table.concat(parts, ",") .. "]"
        end
        local keys, parts = {}, {}
        for k in pairs(value) do keys[#keys + 1] = tostring(k) end
        table.sort(keys)
        for _, k in ipairs(keys) do parts[#parts + 1] = json(k) .. ":" .. json(value[k]) end
        return "{" .. table.concat(parts, ",") .. "}"
    end
    return "null"
end
S.json = json

local function game()
    return EEex_ReadPtr(EEex_ReadPtr(S.chitin) + 0x1090)
end
local function world()
    local g = game()
    return g ~= 0 and EEex_Read32(g + 0x3FA0) or -1
end
function S.push(record)
    if S.count >= S.max then S.overflow = true; S.active = false; return end
    S.count = S.count + 1
    S.records[S.count] = json(record)
end
-- `mark`: a label's number in CBTCLab_MarkNames (tc-queue.lua registers them), or a label.
function CBTCLab_Mark(mark)
    local actor = EEex_LuaAction_Object
    local label = type(mark) == "number" and CBTCLab_MarkNames and CBTCLab_MarkNames[mark] or mark
    S.push({k = "mark", label = tostring(label), f = Infinity_GetFrameCounter(), w = world(),
        actor = actor and actor.m_id or -1})
end

-- The object ID of a live object at `pointer`, or nil: only the object array is read.
local function idOf(pointer)
    local top = math.min(EEex_ReadU16(S.arrayTop), 0x7FFF)
    for index = 0, top do
        local entry = S.array + index * 16
        if EEex_ReadPtr(entry + 8) == pointer then
            local check = EEex_ReadU16(entry)
            if check ~= 0xFFFF then return index * 65536 + check end
        end
    end
    return nil
end

local function effects(sprite)
    local out = {}
    EEex_Utility_IterateCPtrList(sprite.m_timedEffectList, function(effect)
        local source = effect.m_sourceRes:get():upper()
        if S.sources[source] then
            out[#out + 1] = source .. "/" .. effect.m_effectId .. "/" .. effect.m_durationType .. "/" .. effect.m_duration
        end
    end)
    table.sort(out)
    return table.concat(out, ",")
end

local function actorState(id)
    local sprite = EEex_GameObject_Get(id)
    if not sprite or sprite.m_objectType ~= CGameObjectType.SPRITE then return {id = id, gone = true} end
    local p = EEex_UDToPtr(sprite)
    return {id = id, hp = sprite.m_baseStats.m_hitPoints, sp = EEex_ReadU8(p + 0x58), ck = EEex_Read32(p + 0x3A0),
        ls = EEex_Read32(p + 0x1A40), fz = EEex_Read32(p + 0x520C), ne = EEex_Read32(p + 0x4BA4),
        ac = sprite.m_curAction.m_actionID, x = sprite.m_pos.x, y = sprite.m_pos.y, fx = effects(sprite)}
end

local function projectileState(entry)
    local object = EEex_GameObject_Get(entry.id)
    if not object or EEex_UDToPtr(object) ~= entry.pointer then return nil end
    local out = {id = entry.id, ty = entry.type, x = object.m_pos.x, y = object.m_pos.y}
    if entry.area then
        local p = entry.pointer
        out.ar, out.rm, out.rl, out.cd = EEex_Read32(p + 0x3C8), EEex_ReadU16(p + 0x3C6), EEex_ReadU16(p + 0x3CC),
            EEex_ReadU16(p + 0x3CE)
    end
    return out
end

function S.sample()
    if not S.active then return end
    local frame = Infinity_GetFrameCounter()
    if frame == S.lastFrame then return end
    S.lastFrame = frame
    local g = game()
    if g == 0 then return end
    local chitin = EngineGlobals.g_pBaldurChitin
    local w = chitin.m_pEngineWorld
    local loaded = chitin.m_pObjectGame.m_bGameLoaded
    if loaded == 0 or loaded == false or loaded == nil then return end
    local now = EEex_Read32(g + 0x3FA0)
    for pointer, entry in pairs(S.pending) do
        entry.frames = entry.frames + 1
        local id = idOf(pointer)
        if id then
            entry.id = id
            S.projectiles[#S.projectiles + 1] = entry
            S.pending[pointer] = nil
            S.push({k = "fired", f = frame, w = now, id = id, ty = entry.type, decoded = entry.decoded})
        elseif entry.frames > 30 then
            S.pending[pointer] = nil
            S.push({k = "unresolved", f = frame, w = now, ty = entry.type, decoded = entry.decoded})
        end
    end
    local projectiles, kept = {}, {}
    for _, entry in ipairs(S.projectiles) do
        local state = projectileState(entry)
        if state then
            projectiles[#projectiles + 1] = state
            kept[#kept + 1] = entry
        else
            S.push({k = "gone", f = frame, w = now, id = entry.id, ty = entry.type})
        end
    end
    S.projectiles = kept
    local actors = {}
    for _, id in ipairs(S.ids) do actors[#actors + 1] = actorState(id) end
    local record = {k = "s", w = now, p = (tonumber(w.m_bPaused) or 0) ~= 0 or (tonumber(w.m_bHardPaused) or 0) ~= 0,
        ts = EEex_Read32(g + 0x9690), tc = EEex_Read32(g + 0x9694), a = actors, pj = projectiles}
    local key = json(record)
    if key == S.lastKey then return end
    S.lastKey = key
    record.f, record.au, record.ms = frame, EEex_Read32(EEex_ReadPtr(S.scheduler) + 0xFA0), Infinity_GetClockTicks()
    S.push(record)
end

if not S.wrapped then
    local poll = EEexRemote.Poll
    EEexRemote.Poll = function(...)
        if S.active then
            local ok, err = pcall(S.sample)
            if not ok then
                S.errors = S.errors + 1
                S.lastError = tostring(err)
                if S.errors >= 3 then S.active = false end
            end
        end
        return poll(...)
    end
    CBTCLab_ProjectileWatch = {projectileMutator = function(context)
        if not S.active then return end
        local ok, err = pcall(function()
            local projectile = context.projectile
            local pointer = EEex_UDToPtr(projectile)
            local kind = EEex_Projectile_GetType(projectile)
            local name = "Unknown"
            for typeName, flag in pairs(EEex_Projectile_Type) do if flag == kind then name = typeName end end
            local inheritance = EEex_Projectile_Private_Inheritance[kind]
            local sprite = context.originatingSprite
            local entry = {pointer = pointer, type = name, decoded = world(), frames = 0,
                area = inheritance ~= nil and EEex_BAnd(inheritance, EEex_Projectile_Type.CProjectileArea) ~= 0}
            S.pending[pointer] = entry
            S.push({k = "decode", f = Infinity_GetFrameCounter(), w = entry.decoded, ty = name,
                source = context.decodeSource, by = sprite and sprite.m_id or -1, pro = EEex_ReadU16(pointer + 0x60)})
        end)
        if not ok then S.errors = S.errors + 1; S.lastError = tostring(err) end
    end}
    EEex_Projectile_RegisterGlobalMutator("CBTCLab_ProjectileWatch")
    S.wrapped = true
end

local ids = {}
if args.ids and args.ids ~= "" then
    for _, text in ipairs(list(args.ids)) do
        local id = tonumber(text)
        assert(id and id % 1 == 0, "INVALID_ID:" .. text)
        ids[#ids + 1] = id
    end
else
    for slot = 0, 1 do
        local sprite = EEex_Sprite_GetInPortrait(slot)
        if sprite then ids[#ids + 1] = sprite.m_id end
    end
end
local sources = {}
for _, resref in ipairs(list(args.sources or ("CBRTBUF,CBRTREG,CBRTHST,CBRTIHS,CBRTSLW,CBRTSRH,CBRTDIS,CBRTSTP," ..
        "CBRTDMG,CBRTCON,CBRTHIT,CBRTSTL,CBRTSAV,SPWI112,SPWI304,SPWI213,SPWI502,SPWI712,SPWI313,CBRTSRCK"))) do
    assert(resref:match("^[%w_#-]+$") and #resref <= 8, "INVALID_SOURCE:" .. resref)
    sources[resref:upper()] = true
end
S.ids, S.sources = ids, sources
S.active = args.on ~= "0"
S.lastKey = nil
if S.active then S.errors = 0 end
return {active = S.active, ids = ids, records = S.count, overflow = S.overflow, errors = S.errors,
    last_error = S.lastError, pending = (function() local n = 0 for _ in pairs(S.pending) do n = n + 1 end return n end)(),
    projectiles = #S.projectiles, world = world(), frame = Infinity_GetFrameCounter()}
