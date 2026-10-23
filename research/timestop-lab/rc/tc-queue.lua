-- Queue script actions on one creature (Time Clocks lab); they run when the game runs.
-- ARGS.actor: a portrait slot "p0".."p5" or an object ID. ARGS.name: that creature's name, checked.
-- ARGS.steps: steps separated by ";", each one of
--   wait:N               SmallWait(N), 1-300 AI updates
--   mark:LABEL           the sampler records LABEL with the tick the step runs on: the action
--                        passes LABEL's number in CBTCLab_MarkNames to EEex_LuaAction, since the
--                        script parser drops quotes inside an action's string (session n2)
--   apply:RES:TARGET     ApplySpellRES("RES",TARGET)
--   cast:RES:TARGET      ReallyForceSpellRES("RES",TARGET)
--   castpoint:RES:X:Y    ReallyForceSpellPointRES("RES",[X.Y])
--   attack:TARGET        AttackOneRound(TARGET)
--   hostile:TARGET       ChangeEnemyAlly(TARGET,ENEMY), before an attack: in session n2,
--                        AttackOneRound against a neutral creature never hit it
--   damage:N             ApplyDamage(Myself,N,0), 1-50 crushing
--   spawn:CRE:X:Y        CreateCreature("CRE",[X.Y],0)
--   move:X:Y             MoveToPoint([X.Y])
--   destroy              DestroySelf(): the acting creature leaves the game
--   TARGET: self, p0..p5 (Player1..Player6), or t1..t4: the creature with the object ID in ARGS.t1..t4,
--   stored on the acting creature for EEex_Target("t1"), so the action finds it when it runs.
-- ARGS.idle = "1": refuse a creature with a current action (it would run first).
-- ARGS.nostop = "1": refuse while a Time Stop runs.
-- Only while paused, so the driver decides when the actions start.
assert(type(ARGS) == "table" and type(ARGS.actor) == "string" and type(ARGS.name) == "string"
    and type(ARGS.steps) == "string", "ARGS.actor, ARGS.name and ARGS.steps required")
local chitin = EngineGlobals.g_pBaldurChitin
local world, game = chitin.m_pEngineWorld, chitin.m_pObjectGame
assert((tonumber(world.m_bPaused) or 0) ~= 0 or (tonumber(world.m_bHardPaused) or 0) ~= 0, "PAUSE_FIRST")
local function sprite(text)
    local slot = text:match("^p([0-5])$")
    if slot then return EEex_Sprite_GetInPortrait(tonumber(slot)) end
    local id = text:match("^%d+$") and tonumber(text)
    local object = id and EEex_GameObject_Get(id)
    if object and object.m_objectType == CGameObjectType.SPRITE then return object end
    return nil
end
local actor = assert(sprite(ARGS.actor), "NO_ACTOR")
assert(EEex_Sprite_GetName(actor) == ARGS.name, "NOT_THE_ACTOR")
if ARGS.idle == "1" then assert(actor.m_curAction.m_actionID == 0, "ACTOR_BUSY") end
if ARGS.nostop == "1" then
    assert(EEex_Read32(EEex_UDToPtr(game) + 0x9690) == 0, "TIME_STOP_ACTIVE")
end
local function number(text, low, high, what)
    local n = text and text:match("^%-?%d+$") and tonumber(text)
    assert(n and n >= low and n <= high, "INVALID_" .. what)
    return n
end
local function resref(text)
    assert(text and text:match("^[%w_#-]+$") and #text <= 8, "INVALID_RESREF")
    return text:upper()
end
local bound = {}
local function target(text)
    if text == "self" then return "Myself" end
    local slot = text and text:match("^p([0-5])$")
    if slot then return "Player" .. (tonumber(slot) + 1) end
    local key = text and text:match("^(t[1-4])$")
    assert(key, "INVALID_TARGET")
    if not bound[key] then
        local creature = assert(sprite(assert(ARGS[key], "MISSING_" .. key:upper())), "NO_TARGET:" .. key)
        EEex_AIBase_SetStoredScriptingTarget(actor, key, creature)
        bound[key] = creature.m_id
    end
    return 'EEex_Target("' .. key .. '")'
end
local actions, marks = {}, {}
local markBase = #(CBTCLab_MarkNames or {})
for step in (ARGS.steps .. ";"):gmatch("([^;]*);") do
    local parts = {}
    for part in (step .. ":"):gmatch("([^:]*):") do parts[#parts + 1] = part end
    local verb = parts[1]
    local action
    if verb == "wait" and #parts == 2 then
        action = "SmallWait(" .. number(parts[2], 1, 300, "WAIT") .. ")"
    elseif verb == "mark" and #parts == 2 then
        assert(parts[2]:match("^[%w_]+$") and #parts[2] <= 32, "INVALID_LABEL")
        marks[#marks + 1] = parts[2]
        action = "EEex_LuaAction(\"CBTCLab_Mark(" .. (markBase + #marks) .. ")\")"
    elseif verb == "apply" and #parts == 3 then
        action = 'ApplySpellRES("' .. resref(parts[2]) .. '",' .. target(parts[3]) .. ")"
    elseif verb == "cast" and #parts == 3 then
        action = 'ReallyForceSpellRES("' .. resref(parts[2]) .. '",' .. target(parts[3]) .. ")"
    elseif verb == "castpoint" and #parts == 4 then
        action = 'ReallyForceSpellPointRES("' .. resref(parts[2]) .. '",[' .. number(parts[3], 0, 32767, "POINT")
            .. "." .. number(parts[4], 0, 32767, "POINT") .. "])"
    elseif verb == "attack" and #parts == 2 then
        action = "AttackOneRound(" .. target(parts[2]) .. ")"
    elseif verb == "hostile" and #parts == 2 then
        action = "ChangeEnemyAlly(" .. target(parts[2]) .. ",ENEMY)"
    elseif verb == "destroy" and #parts == 1 then
        action = "DestroySelf()"
    elseif verb == "damage" and #parts == 2 then
        action = "ApplyDamage(Myself," .. number(parts[2], 1, 50, "AMOUNT") .. ",0)"
    elseif verb == "spawn" and #parts == 4 then
        action = 'CreateCreature("' .. resref(parts[2]) .. '",[' .. number(parts[3], 0, 32767, "POINT") .. "."
            .. number(parts[4], 0, 32767, "POINT") .. "],0)"
    elseif verb == "move" and #parts == 3 then
        action = "MoveToPoint([" .. number(parts[2], 0, 32767, "POINT") .. "." .. number(parts[3], 0, 32767, "POINT") .. "])"
    else
        error("UNKNOWN_STEP:" .. tostring(step))
    end
    actions[#actions + 1] = action
end
assert(#actions >= 1 and #actions <= 24, "INVALID_STEP_COUNT")
local response = table.concat(actions, "\n")
-- Registered only now, so a refused request leaves no labels behind.
CBTCLab_MarkNames = CBTCLab_MarkNames or {}
for _, label in ipairs(marks) do CBTCLab_MarkNames[#CBTCLab_MarkNames + 1] = label end
EEex_Action_QueueResponseStringOnAIBase(response, actor)
return {queued = response, actor = actor.m_id, name = EEex_Sprite_GetName(actor), targets = bound,
    game_time = game.m_worldTime.m_gameTime}
