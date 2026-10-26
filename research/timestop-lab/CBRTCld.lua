-- BG2:EE 2.7.3.0 / EEex 1.3 lab observer for one area spell (a cloud) through a Time Stop (lab
-- step 7). It patches nothing and changes no game state: Install() registers a global projectile
-- mutator, which notes the area projectile the armed creature decodes next, and wraps the
-- correction's entry gate function CBRTC_Entry, which the gates call at every creature's
-- effect-list tail, frozen or not. Each update of a sampled creature then reads:
--   the cloud, a CProjectileArea, at the offsets its AIUpdate (0x2284B0 in the pinned executable)
--     uses: its object ID (+0x48), explosions left (+0x3C6, one less whenever the explosion
--     check returns nonzero), the arrival flag (+0x3C8, nonzero once it sits at its target),
--     the explosion interval (+0x3CC) and the countdown to the next check (+0x3CE);
--   the Time Stop: ticks left (game +0x9690) and the caster (game +0x9694);
--   every sampled creature's hit points.
-- A sample is kept only when something but the world time and the updated creature changed, so a
-- running stop leaves one per tick (its counter changes) and a cloud that runs one per tick (its
-- countdown changes). The gates must run, the correction enabled or observing. A Lua error here
-- is counted and never reaches the gate, which always gets the correction's own result.
if CBRTCL then return end
CBRTCL = {schema = 1, installed = false, on = false, capacity = 40000}
local L = CBRTCL

-- Abandon a decoded projectile whose object ID does not resolve within this many ticks: the
-- pointer is only read while the decode is this recent.
local RESOLVE_TICKS = 15
local OFF = {id = 0x48, left = 0x3C6, arrived = 0x3C8, interval = 0x3CC, countdown = 0x3CE,
    stop = 0x9690, stopCaster = 0x9694}
L.offsets = OFF

-- Host bindings, replaceable by host tests: memory reads, the object behind an ID, a creature's
-- hit points, world time, the game object, the pause state, the area projectile vtable, a
-- userdata's pointer and object ID, the mutator registration and file access.
local host
function L.UseHost(h) host = h end
local function eeexHost()
    return {
        u32 = EEex_ReadU32, r32 = EEex_Read32, s16 = EEex_Read16, u16 = EEex_ReadU16, ptr = EEex_ReadPtr,
        object = function(id)
            local object = EEex_GameObject_Get(id)
            return object and EEex_UDToPtr(object) or nil
        end,
        hp = function(id)
            local object = EEex_GameObject_Get(id)
            return object and object:isSprite(true) and object.m_baseStats.m_hitPoints or nil
        end,
        world = function() return EngineGlobals.g_pBaldurChitin.m_pObjectGame.m_worldTime.m_gameTime end,
        game = function() return EEex_UDToPtr(EngineGlobals.g_pBaldurChitin.m_pObjectGame) end,
        paused = function()
            local world = EngineGlobals.g_pBaldurChitin.m_pEngineWorld
            return (tonumber(world.m_bPaused) or 0) ~= 0 or (tonumber(world.m_bHardPaused) or 0) ~= 0
        end,
        areaVtable = function() return EEex_Label("CProjectileArea::VFTable") end,
        pointer = EEex_UDToPtr,
        id = function(object) return object.m_id end,
        register = EEex_Projectile_RegisterGlobalMutator,
        open = io.open,
    }
end

local function num(v)
    if v == nil then return "null" end
    return string.format("%.0f", v)
end
local function text(s)
    return '"'..tostring(s):gsub('[%c"\\]', function(c) return string.format("\\u%04x", c:byte()) end)..'"'
end

-- Recording state: the armed caster, the sampled creatures in order, the cloud, the samples and
-- the errors caught while recording.
local function clear()
    L.caster, L.watch, L.slot = nil, {}, {}
    L.cloud = {state = "none"}
    L.lines, L.n, L.lastKey, L.overflow, L.dirty = {}, 0, nil, false, false
    L.errors, L.firstError = 0, nil
end
clear()

local function fail(why)
    L.errors = L.errors + 1
    if L.firstError == nil then L.firstError = tostring(why) end
end

-- Mutator: the first area projectile the armed caster decodes. Its object ID is set only when
-- the engine adds it to the area after the decode, so the samples resolve it.
local function capture(context)
    local sprite = context.originatingSprite
    if sprite == nil or host.id(sprite) ~= L.caster then return end
    local pointer = host.pointer(context.projectile)
    if host.ptr(pointer) ~= host.areaVtable() then return end
    L.cloud = {state = "pending", pointer = pointer, decoded = host.world()}
end

local function resolve(world)
    local cloud = L.cloud
    local id = host.u32(cloud.pointer + OFF.id)
    if host.object(id) == cloud.pointer then
        cloud.state, cloud.id, cloud.resolved = "live", id, world
    elseif world - cloud.decoded > RESOLVE_TICKS then
        cloud.state, cloud.pointer = "lost", nil
    end
end

local function sample(sprite)
    if not L.slot[host.u32(sprite + OFF.id)] then return end
    local world = host.world()
    local cloud = L.cloud
    if cloud.state == "pending" then resolve(world) end
    local left, arrived, interval, countdown
    if cloud.state == "live" then
        local pointer = cloud.pointer
        if host.object(cloud.id) ~= pointer then
            cloud.state, cloud.gone, cloud.pointer = "gone", world, nil
        else
            left, arrived = host.s16(pointer + OFF.left), host.u32(pointer + OFF.arrived)
            interval, countdown = host.u16(pointer + OFF.interval), host.u16(pointer + OFF.countdown)
        end
    end
    local game = host.game()
    local hp = {}
    for i, id in ipairs(L.watch) do hp[i] = num(host.hp(id)) end
    local fields = {num(host.u32(game + OFF.stop)), num(host.r32(game + OFF.stopCaster)), text(cloud.state),
        num(left), num(arrived), num(interval), num(countdown), table.concat(hp, ",")}
    local key = table.concat(fields, ",")
    if key == L.lastKey then return end
    if L.n >= L.capacity then
        L.on, L.overflow = false, true
        return
    end
    L.lastKey = key
    L.n = L.n + 1
    L.lines[L.n] = '{"t":'..num(world)..',"by":'..num(host.u32(sprite + OFF.id))..',"stop":'..fields[1]..
        ',"caster":'..fields[2]..',"cloud":'..fields[3]..',"left":'..fields[4]..',"arrived":'..fields[5]..
        ',"interval":'..fields[6]..',"countdown":'..fields[7]..',"hp":['..fields[8]..']}'
end

-- Gate wrapper and mutator table; both only read, and only while a record runs.
local function wrap(inner)
    return function(...)
        if L.on then
            local ok, why = pcall(sample, (...))
            if not ok then fail(why) end
        end
        return inner(...)
    end
end
CBRTCL_Mutator = {projectileMutator = function(context)
    if L.on and L.cloud.state == "none" then
        local ok, why = pcall(capture, context)
        if not ok then fail(why) end
    end
end}

function L.Install()
    if L.installed then return L.Status() end
    assert(type(CBRTC_Entry) == "function", "Load the correction (CBRTCor.lua) first")
    host = host or eeexHost()
    L.inner = CBRTC_Entry
    CBRTC_Entry = wrap(L.inner)
    L.wrapper = CBRTC_Entry
    host.register("CBRTCL_Mutator")
    L.installed = true
    return L.Status()
end

-- A new record: `caster` is the creature whose next area projectile is followed, `ids` the
-- creatures sampled. An unexported record is kept unless `discard`.
function L.Arm(caster, ids, discard)
    assert(L.installed, "Install the cloud observer first")
    assert(host.paused(), "Pause the lab before this operation")
    assert(not L.on, "Already recording")
    assert(discard or not L.dirty, "Export the previous record first")
    assert(type(caster) == "number" and caster > 0 and caster % 1 == 0, "Caster object ID required")
    assert(#ids > 0, "Sample at least one creature")
    clear()
    for i, id in ipairs(ids) do
        assert(type(id) == "number" and id > 0 and id % 1 == 0 and not L.slot[id], "Distinct object IDs only")
        L.watch[i], L.slot[id] = id, i
    end
    L.caster, L.dirty, L.on = caster, true, true
    return L.Status()
end

function L.Stop()
    L.on = false
    return L.Status()
end

-- cbr-timestop-output/NAME.jsonl: a header object, then one sample per line.
function L.Export(name)
    assert(host.paused(), "Pause the lab before this operation")
    assert(not L.on, "Stop recording before the export")
    assert(L.caster, "Nothing recorded")
    assert(type(name) == "string" and name:match("^[%w_-]+$"), "Use a simple unique record name")
    local path = "cbr-timestop-output/"..name..".jsonl"
    local existing = host.open(path, "rb")
    if existing then existing:close(); error("Record already exists: "..path) end
    local watch = {}
    for i, id in ipairs(L.watch) do watch[i] = num(id) end
    local c = L.cloud
    local header = '{"schema":1,"name":'..text(name)..',"caster":'..num(L.caster)..',"watch":['..
        table.concat(watch, ",")..'],"cloud":{"state":'..text(c.state)..',"id":'..num(c.id)..
        ',"decoded":'..num(c.decoded)..',"resolved":'..num(c.resolved)..',"gone":'..num(c.gone)..
        '},"samples":'..num(L.n)..',"overflow":'..tostring(L.overflow)..',"errors":'..num(L.errors)..
        ',"first_error":'..(L.firstError and text(L.firstError) or "null")..'}\n'
    local f = assert(host.open(path, "wb"))
    local ok, why = f:write(header, table.concat(L.lines, "\n", 1, L.n), L.n > 0 and "\n" or "")
    f:close()
    assert(ok, why)
    L.dirty = false
    return {path = path, samples = L.n, overflow = L.overflow, cloud = c.state}
end

function L.Status()
    local c = L.cloud
    return {installed = L.installed, on = L.on, wrapped = L.installed and CBRTC_Entry == L.wrapper,
        caster = L.caster, watched = #L.watch, samples = L.n, overflow = L.overflow, unexported = L.dirty,
        errors = L.errors, first_error = L.firstError,
        cloud = {state = c.state, id = c.id, decoded = c.decoded, resolved = c.resolved, gone = c.gone}}
end
