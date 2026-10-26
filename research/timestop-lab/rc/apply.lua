-- Queue lab fixture applications through one creature's own action queue; they run when the game
-- runs. ARGS.actor: the object ID of the creature that acts; it must be idle, since a current
-- action would run first and delay the steps by an unknown time. ARGS.steps: up to 12 steps
-- separated by ";", each "WAIT:SPELL:TARGET": SmallWait(WAIT) AI updates (0-300), then
-- ApplySpellRES(SPELL) on TARGET, "self" or another creature's object ID. Lab fixtures (CBRT*)
-- only. Refused while a Time Stop runs; steps meant for a stop are queued with the stop itself.
assert(type(ARGS) == "table" and type(ARGS.actor) == "string" and type(ARGS.steps) == "string",
    "ARGS.actor and ARGS.steps required")
local chitin = EngineGlobals.g_pBaldurChitin
local world = chitin.m_pEngineWorld
assert((tonumber(world.m_bPaused) or 0) ~= 0 or (tonumber(world.m_bHardPaused) or 0) ~= 0, "PAUSE_FIRST")
assert(EEex_Read32(EEex_UDToPtr(chitin.m_pObjectGame) + 0x9690) == 0, "TIME_STOP_ACTIVE")
local function creature(text, guard)
    local id = tonumber(text)
    local object = id and id > 0 and id % 1 == 0 and EEex_GameObject_Get(id)
    assert(object and object:isSprite(true), guard)
    return object
end
local actor = creature(ARGS.actor, "NOT_A_CREATURE")
assert(actor.m_curAction.m_actionID == 0, "ACTOR_BUSY")
local lines, count = {}, 0
for step in ARGS.steps:gmatch("[^;%s][^;]*") do
    count = count + 1
    assert(count <= 12, "TOO_MANY_STEPS")
    local wait, spell, target = step:match("^%s*(%d+):([%w]+):(%w+)%s*$")
    wait = tonumber(wait)
    assert(wait and wait <= 300, "INVALID_STEP")
    assert(#spell <= 8 and spell:match("^CBRT[A-Z0-9]+$"), "NOT_A_LAB_FIXTURE")
    if wait > 0 then lines[#lines + 1] = "SmallWait(" .. wait .. ")" end
    if target == "self" then
        lines[#lines + 1] = 'ApplySpellRES("' .. spell .. '",Myself)'
    else
        local object = creature(target, "INVALID_TARGET")
        local key = "CBRTT" .. object.m_id
        actor:setStoredScriptingTarget(key, object)
        lines[#lines + 1] = 'ApplySpellRES("' .. spell .. '",EEex_Target("' .. key .. '"))'
    end
end
assert(count > 0, "NO_STEPS")
local response = table.concat(lines, "\n")
EEex_Action_QueueResponseStringOnAIBase(response, actor)
return {queued = response, actor = EEex_Sprite_GetName(actor), game_time = chitin.m_pObjectGame.m_worldTime.m_gameTime}
