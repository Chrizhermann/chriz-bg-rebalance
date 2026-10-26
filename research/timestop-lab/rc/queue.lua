-- Queue script actions through an actor's own action queue; they run when the game runs.
-- ARGS.subject: the subject's name (portrait 0), checked first. Portrait 1 is the controller
-- (ARGS.controller: its name) where a case needs one.
-- ARGS.what = "fixtures": ApplySpellRES of CBRTBUF and CBRTREG on the subject (ARGS.only: just that
--   one); only while a capture is armed and neither fixture (ARGS.only: that one) is still on the
--   subject (a refresh would mix two cases).
-- ARGS.what = "damage": ApplyDamage(Myself, ARGS.amount, crushing) on the subject; only while disarmed.
-- ARGS.what = "timestop": the caster waits ARGS.wait AI updates (SmallWait), then applies CBRTSTP
--   to itself. ARGS.caster = "controller" (default: the controller casts, the subject is frozen)
--   or "subject" (the subject casts and is not frozen). Only while a capture is armed, with exactly
--   one of each fixture on the subject, while no Time Stop runs, and with an idle caster (a current
--   action would run first and delay the stop by an unknown time). With the controller as caster,
--   ARGS.step adds one step ARGS.step_wait AI updates after the stop was applied, while the
--   subject is frozen; Player1 must resolve to the subject:
--     "stop": a second CBRTSTP on itself, so two stops follow each other;
--     "remove": CBRTRMR on Player1, which removes the regeneration;
--     "refresh": CBRTRMR, then CBRTREG on Player1;
--     "apply": CBRTREG on Player1; only with CBRTBUF alone on the subject before, because the
--       correction verifies its list walk on a timed effect before the stop.
-- ARGS.what = "speed": the subject waits ARGS.wait AI updates, then applies ARGS.spell to itself:
--   CBRTHST (Haste), CBRTIHS (Improved Haste), CBRTWHS (Weak Haste), CBRTSRH (SR-shaped Haste) or
--   CBRTSLW (Slow). Only while a capture is armed, with an idle subject, no speed fixture already on
--   it (a refresh would mix two cases), no fixtures or exactly one of each (a leftover would mix in
--   an earlier case), and while no Time Stop runs.
-- ARGS.what = "immunity": the subject applies CBRTTSI (Time Stop immunity) to itself. Only while a
--   capture is armed, before the fixtures, with an idle subject, without CBRTTSI already on it and
--   while no Time Stop runs.
-- ARGS.what = "remove": the subject waits ARGS.wait AI updates, then applies ARGS.spell (CBRTRMR or
--   CBRTRMB) to itself; with ARGS.reapply_wait it reapplies the removed fixture that many AI updates
--   later. Only while a capture is armed, with an idle subject, exactly one of each fixture and no
--   Time Stop.
-- ARGS.what = "dummy": the controller creates BATIN01 (neutral, no scripts) at ARGS.x, ARGS.y. Only
--   while disarmed, with an idle controller.
-- ARGS.what = "hold": creature ARGS.id, a BATIN01 outside the party, applies CBRTDUM (minimum 1 HP,
--   held) to itself, so it stays alive and every weapon swing at it hits.
-- ARGS.what = "activity": the subject walks to ARGS.x, ARGS.y, then attacks the held dummy ARGS.id.
--   Only while the activity recorder (rc/activity.lua) is armed on the subject, with an idle subject.
-- ARGS.what = "halt": the controller runs ClearActions(Player1), which also ends the subject's current
--   action (the subject's own ClearActions leaves it, and an attack on the held dummy never ends by
--   itself). Only while disarmed, with an idle controller; Player1 must resolve to the subject.
-- ARGS.what = "walk": the subject drops its queued actions and walks to ARGS.x, ARGS.y; only while
--   disarmed, after "halt" when it was attacking.
assert(type(ARGS) == "table" and type(ARGS.subject) == "string" and type(ARGS.what) == "string",
    "ARGS.subject and ARGS.what required")
local chitin = EngineGlobals.g_pBaldurChitin
local world = chitin.m_pEngineWorld
assert((tonumber(world.m_bPaused) or 0) ~= 0 or (tonumber(world.m_bHardPaused) or 0) ~= 0, "PAUSE_FIRST")
local sprite = assert(EEex_Sprite_GetInPortrait(0), "NO_SUBJECT")
assert(EEex_Sprite_GetName(sprite) == ARGS.subject, "NOT_THE_SUBJECT")
local SPEED = {CBRTHST = true, CBRTIHS = true, CBRTWHS = true, CBRTSRH = true, CBRTSLW = true}
local function sources(actor)
    local count = setmetatable({}, {__index = function() return 0 end})
    EEex_Utility_IterateCPtrList(actor.m_timedEffectList, function(effect)
        local source = effect.m_sourceRes:get()
        count[source] = count[source] + 1
    end)
    return count
end
local function speedOn(count)
    for spell in pairs(SPEED) do
        if count[spell] > 0 then return true end
    end
    return false
end
local function armed()
    assert(CBRTS and CBRTS.Status().armed, "ARM_FIRST")
end
local function idle(actor, guard)
    assert(actor.m_curAction.m_actionID == 0, guard)
end
local function noTimeStop()
    assert(EEex_Read32(EEex_UDToPtr(chitin.m_pObjectGame) + 0x9690) == 0, "TIME_STOP_ACTIVE")
end
local function updates(value, guard)
    local wait = tonumber(value)
    assert(wait and wait >= 0 and wait <= 300 and wait % 1 == 0, guard)
    return wait > 0 and "SmallWait(" .. wait .. ")\n" or ""
end
local function point()
    local x, y = tonumber(ARGS.x), tonumber(ARGS.y)
    assert(x and y and x >= 0 and y >= 0 and x <= 20000 and y <= 20000 and x % 1 == 0 and y % 1 == 0,
        "INVALID_POINT")
    return "[" .. x .. "." .. y .. "]"
end
local function controller()
    local actor = assert(EEex_Sprite_GetInPortrait(1), "NO_CONTROLLER")
    assert(type(ARGS.controller) == "string" and EEex_Sprite_GetName(actor) == ARGS.controller
        and actor.m_id ~= sprite.m_id, "NOT_THE_CONTROLLER")
    return actor
end
local function dummy()
    local id = tonumber(ARGS.id)
    local object = id and EEex_GameObject_Get(id)
    assert(object and object:isSprite() and object.m_resref:get() == "BATIN01", "NOT_A_DUMMY")
    for slot = 0, 5 do
        local member = EEex_Sprite_GetInPortrait(slot)
        assert(not member or member.m_id ~= object.m_id, "NOT_A_DUMMY")
    end
    return object
end
local actor, response = sprite, nil
local count = sources(sprite)
if ARGS.what == "fixtures" then
    armed()
    if ARGS.only ~= nil then
        assert(ARGS.only == "CBRTBUF" or ARGS.only == "CBRTREG", "UNKNOWN_FIXTURE")
        assert(count[ARGS.only] == 0, "FIXTURES_PRESENT")
        response = 'ApplySpellRES("' .. ARGS.only .. '",Myself)'
    else
        assert(count.CBRTBUF == 0 and count.CBRTREG == 0, "FIXTURES_PRESENT")
        response = 'ApplySpellRES("CBRTBUF",Myself)\nApplySpellRES("CBRTREG",Myself)'
    end
elseif ARGS.what == "damage" then
    assert(not (CBRTS and CBRTS.Status().armed), "DISARMED_ONLY")
    local amount = tonumber(ARGS.amount)
    assert(amount and amount >= 1 and amount <= 50 and amount % 1 == 0, "INVALID_AMOUNT")
    response = "ApplyDamage(Myself," .. amount .. ",0)"
elseif ARGS.what == "timestop" then
    armed()
    local caster = ARGS.caster or "controller"
    local step = ARGS.step
    if caster == "subject" then
        assert(step == nil, "STEP_NEEDS_CONTROLLER")
        idle(sprite, "SUBJECT_BUSY")
    else
        assert(caster == "controller", "UNKNOWN_CASTER")
        actor = controller()
        idle(actor, "CONTROLLER_BUSY")
    end
    if step == "apply" then
        assert(count.CBRTBUF == 1 and count.CBRTREG == 0, "BUFF_ONLY_FIRST")
    else
        assert(count.CBRTBUF == 1 and count.CBRTREG == 1, "FIXTURES_FIRST")
    end
    noTimeStop()
    response = updates(ARGS.wait, "INVALID_WAIT") .. 'ApplySpellRES("CBRTSTP",Myself)'
    if step ~= nil then
        local later = {stop = {'ApplySpellRES("CBRTSTP",Myself)'},
            remove = {'ApplySpellRES("CBRTRMR",Player1)'},
            refresh = {'ApplySpellRES("CBRTRMR",Player1)', 'ApplySpellRES("CBRTREG",Player1)'},
            apply = {'ApplySpellRES("CBRTREG",Player1)'}}
        assert(later[step], "UNKNOWN_STEP")
        if step ~= "stop" then
            local player1 = EEex_Object_EvalStringAsAIBase("Player1", actor)
            assert(player1 and player1.m_id == sprite.m_id, "PLAYER1_NOT_THE_SUBJECT")
        end
        response = response .. "\n" .. updates(ARGS.step_wait, "INVALID_STEP_WAIT") .. table.concat(later[step], "\n")
    end
elseif ARGS.what == "speed" then
    armed()
    assert(SPEED[ARGS.spell], "UNKNOWN_SPELL")
    idle(sprite, "SUBJECT_BUSY")
    assert(not speedOn(count), "SPEED_PRESENT")
    assert(count.CBRTBUF == count.CBRTREG and count.CBRTBUF <= 1, "FIXTURES_MIXED")
    noTimeStop()
    response = updates(ARGS.wait, "INVALID_WAIT") .. 'ApplySpellRES("' .. ARGS.spell .. '",Myself)'
elseif ARGS.what == "immunity" then
    armed()
    idle(sprite, "SUBJECT_BUSY")
    assert(count.CBRTTSI == 0, "IMMUNITY_PRESENT")
    assert(count.CBRTBUF == 0 and count.CBRTREG == 0, "FIXTURES_PRESENT")
    noTimeStop()
    response = 'ApplySpellRES("CBRTTSI",Myself)'
elseif ARGS.what == "remove" then
    armed()
    local removed = ({CBRTRMR = "CBRTREG", CBRTRMB = "CBRTBUF"})[ARGS.spell]
    assert(removed, "UNKNOWN_SPELL")
    idle(sprite, "SUBJECT_BUSY")
    assert(count.CBRTBUF == 1 and count.CBRTREG == 1, "FIXTURES_FIRST")
    noTimeStop()
    response = updates(ARGS.wait, "INVALID_WAIT") .. 'ApplySpellRES("' .. ARGS.spell .. '",Myself)'
    if ARGS.reapply_wait ~= nil then
        response = response .. "\n" .. updates(ARGS.reapply_wait, "INVALID_REAPPLY_WAIT")
            .. 'ApplySpellRES("' .. removed .. '",Myself)'
    end
elseif ARGS.what == "dummy" then
    assert(not (CBRTS and CBRTS.Status().armed), "DISARMED_ONLY")
    actor = controller()
    idle(actor, "CONTROLLER_BUSY")
    response = 'CreateCreature("BATIN01",' .. point() .. ",0)"
elseif ARGS.what == "hold" then
    actor = dummy()
    assert(sources(actor).CBRTDUM == 0, "DUMMY_HELD")
    response = 'ApplySpellRES("CBRTDUM",Myself)'
elseif ARGS.what == "activity" then
    assert(CBRTA and CBRTA.armed and CBRTA.subject == sprite.m_id, "ACTIVITY_NOT_ARMED")
    idle(sprite, "SUBJECT_BUSY")
    local target = dummy()
    assert(sources(target).CBRTDUM == 2, "DUMMY_NOT_HELD")
    sprite:setStoredScriptingTarget("CBRTDummy", target)
    response = "MoveToPoint(" .. point() .. ')\nAttack(EEex_Target("CBRTDummy"))'
elseif ARGS.what == "halt" then
    assert(not (CBRTS and CBRTS.Status().armed), "DISARMED_ONLY")
    actor = controller()
    idle(actor, "CONTROLLER_BUSY")
    local player1 = EEex_Object_EvalStringAsAIBase("Player1", actor)
    assert(player1 and player1.m_id == sprite.m_id, "PLAYER1_NOT_THE_SUBJECT")
    response = "ClearActions(Player1)"
elseif ARGS.what == "walk" then
    assert(not (CBRTS and CBRTS.Status().armed), "DISARMED_ONLY")
    sprite:virtual_ClearActions(false)
    response = "MoveToPoint(" .. point() .. ")"
else
    error("UNKNOWN_WHAT")
end
EEex_Action_QueueResponseStringOnAIBase(response, actor)
return {queued = response, actor = EEex_Sprite_GetName(actor), hp = sprite.m_baseStats.m_hitPoints,
    game_time = chitin.m_pObjectGame.m_worldTime.m_gameTime}
