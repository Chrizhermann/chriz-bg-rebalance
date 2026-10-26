-- One area spell through a Time Stop (CBRTCld.lua). ARGS.op:
--   install  wraps the correction's entry gate and registers the projectile mutator, once
--   status
--   stop     ends the record
-- Paused only:
--   arm      a new record: ARGS.caster is the creature whose next area projectile is followed,
--            ARGS.ids the creatures sampled (object IDs separated by spaces); ARGS.discard = "1"
--            drops an unexported record
--   cast     the armed caster casts ARGS.spell at the point ARGS.x, ARGS.y through its own action
--            queue, after ARGS.wait (optional, 0-300) AI updates, with ReallyForceSpellPointRES,
--            which skips the casting time. Incendiary Cloud (SPWI810) only: its projectile
--            1PINCIND explodes within 256 in the pinned game data, measured like
--            CGameArea::GetAllInRange with the vertical offset scaled by 4/3. Refused while a Time
--            Stop runs, with a busy caster, and while a creature that is not sampled stands within
--            that reach plus 64 of the point: a scripted bystander hit by the party may turn
--            hostile and change the lab. Returns every creature within 600 of the point.
--   export   cbr-timestop-output/ARGS.name.jsonl; refuses an existing file
assert(type(ARGS) == "table" and type(ARGS.op) == "string", "ARGS.op required")
assert(CBRTCL, "CLOUD_NOT_LOADED")
local op = ARGS.op
if op == "install" then return CBRTCL.Install() end
if op == "status" then return CBRTCL.Status() end
if op == "stop" then return CBRTCL.Stop() end
assert(op == "arm" or op == "cast" or op == "export", "UNKNOWN_OP")
local chitin = EngineGlobals.g_pBaldurChitin
local world = chitin.m_pEngineWorld
assert((tonumber(world.m_bPaused) or 0) ~= 0 or (tonumber(world.m_bHardPaused) or 0) ~= 0, "PAUSE_FIRST")
if op == "export" then
    assert(type(ARGS.name) == "string", "ARGS.name required")
    return CBRTCL.Export(ARGS.name)
end
local function creature(text)
    local id = tonumber(text)
    local object = id and id > 0 and id % 1 == 0 and EEex_GameObject_Get(id)
    assert(object and object:isSprite(true), "NOT_A_CREATURE")
    return object
end
if op == "arm" then
    local caster = creature(ARGS.caster)
    local ids = {}
    for word in tostring(ARGS.ids or ""):gmatch("%S+") do ids[#ids + 1] = creature(word).m_id end
    return CBRTCL.Arm(caster.m_id, ids, ARGS.discard == "1")
end
local REACH, MARGIN, RANGE = {SPWI810 = 256}, 64, 600
local reach = REACH[ARGS.spell]
assert(reach, "NOT_A_CLOUD_SPELL")
assert(CBRTCL.on and CBRTCL.caster, "ARM_FIRST")
local caster = creature(tostring(CBRTCL.caster))
assert(EEex_Read32(EEex_UDToPtr(chitin.m_pObjectGame) + 0x9690) == 0, "TIME_STOP_ACTIVE")
assert(caster.m_curAction.m_actionID == 0, "CASTER_BUSY")
local x, y, wait = tonumber(ARGS.x), tonumber(ARGS.y), tonumber(ARGS.wait or "0")
assert(x and y and x >= 0 and y >= 0 and x < 32768 and y < 32768 and x % 1 == 0 and y % 1 == 0,
    "INVALID_POINT")
assert(wait and wait >= 0 and wait <= 300 and wait % 1 == 0, "INVALID_WAIT")
local sampled = {}
for _, id in ipairs(CBRTCL.watch) do sampled[id] = true end
local near = {}
for _, object in ipairs(EEex_Area_GetAllOfTypeStringInRange(caster.m_pArea, x, y, "[ANYONE]", RANGE, 0, 0)) do
    local distance = math.sqrt((object.m_pos.x - x) ^ 2 + ((object.m_pos.y - y) * 4 / 3) ^ 2)
    assert(sampled[object.m_id] or distance > reach + MARGIN, "BYSTANDER_IN_REACH " .. object.m_id)
    near[#near + 1] = {id = object.m_id, resref = object.m_resref:get(), distance = math.floor(distance + 0.5),
        sampled = sampled[object.m_id] == true, inside = distance <= reach}
end
table.sort(near, function(a, b) return a.distance < b.distance end)
local response = (wait > 0 and "SmallWait(" .. wait .. ")\n" or "") ..
    'ReallyForceSpellPointRES("' .. ARGS.spell .. '",[' .. x .. "." .. y .. "])"
EEex_Action_QueueResponseStringOnAIBase(response, caster)
return {queued = response, caster = CBRTCL.caster, reach = reach, near = near,
    game_time = chitin.m_pObjectGame.m_worldTime.m_gameTime}
