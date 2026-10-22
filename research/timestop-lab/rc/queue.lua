-- Queue script actions through an actor's own action queue; they run when the game runs.
-- ARGS.subject: the subject's name (portrait 0), checked first.
-- ARGS.what = "fixtures": ApplySpellRES of CBRTBUF and CBRTREG on the subject; only while a
--   capture is armed and neither fixture is still on the subject (a refresh would mix two cases).
-- ARGS.what = "damage": ApplyDamage(Myself, ARGS.amount, crushing) on the subject; only while disarmed.
-- ARGS.what = "timestop": the controller in portrait 1 (ARGS.controller: its name) waits ARGS.wait
--   AI updates (SmallWait), then applies CBRTSTP to itself, so it is the Time Stop caster and the
--   subject is frozen. Only while a capture is armed, with exactly one of each fixture on the
--   subject, while no Time Stop runs, and with an idle controller (a current action would run
--   first and delay the stop by an unknown time).
-- ARGS.what = "haste": the subject waits ARGS.wait AI updates, then applies ARGS.spell to itself:
--   CBRTHST (native Haste) or CBRTIHS (Improved Haste). Only while a capture is armed, with an
--   idle subject, no Haste fixture already on it (a refresh would mix two cases), no fixtures
--   or exactly one of each (a leftover would mix in an earlier case), and while no Time Stop runs.
assert(type(ARGS) == "table" and type(ARGS.subject) == "string" and type(ARGS.what) == "string",
    "ARGS.subject and ARGS.what required")
local chitin = EngineGlobals.g_pBaldurChitin
local world = chitin.m_pEngineWorld
assert((tonumber(world.m_bPaused) or 0) ~= 0 or (tonumber(world.m_bHardPaused) or 0) ~= 0, "PAUSE_FIRST")
local sprite = assert(EEex_Sprite_GetInPortrait(0), "NO_SUBJECT")
assert(EEex_Sprite_GetName(sprite) == ARGS.subject, "NOT_THE_SUBJECT")
local function fixtures()
    local count = {CBRTBUF = 0, CBRTREG = 0, CBRTHST = 0, CBRTIHS = 0}
    EEex_Utility_IterateCPtrList(sprite.m_timedEffectList, function(effect)
        local source = effect.m_sourceRes:get()
        if count[source] then count[source] = count[source] + 1 end
    end)
    return count
end
local function noTimeStop()
    assert(EEex_Read32(EEex_UDToPtr(chitin.m_pObjectGame) + 0x9690) == 0, "TIME_STOP_ACTIVE")
end
local function smallWait()
    local wait = tonumber(ARGS.wait)
    assert(wait and wait >= 0 and wait <= 300 and wait % 1 == 0, "INVALID_WAIT")
    return wait > 0 and "SmallWait(" .. wait .. ")\n" or ""
end
local actor, response = sprite, nil
if ARGS.what == "fixtures" then
    assert(CBRTS and CBRTS.Status().armed, "ARM_FIRST")
    local count = fixtures()
    assert(count.CBRTBUF == 0 and count.CBRTREG == 0, "FIXTURES_PRESENT")
    response = 'ApplySpellRES("CBRTBUF",Myself)\nApplySpellRES("CBRTREG",Myself)'
elseif ARGS.what == "damage" then
    assert(not (CBRTS and CBRTS.Status().armed), "DISARMED_ONLY")
    local amount = tonumber(ARGS.amount)
    assert(amount and amount >= 1 and amount <= 50 and amount % 1 == 0, "INVALID_AMOUNT")
    response = "ApplyDamage(Myself," .. amount .. ",0)"
elseif ARGS.what == "timestop" then
    assert(CBRTS and CBRTS.Status().armed, "ARM_FIRST")
    actor = assert(EEex_Sprite_GetInPortrait(1), "NO_CONTROLLER")
    assert(type(ARGS.controller) == "string" and EEex_Sprite_GetName(actor) == ARGS.controller
        and actor.m_id ~= sprite.m_id, "NOT_THE_CONTROLLER")
    assert(actor.m_curAction.m_actionID == 0, "CONTROLLER_BUSY")
    local count = fixtures()
    assert(count.CBRTBUF == 1 and count.CBRTREG == 1, "FIXTURES_FIRST")
    noTimeStop()
    response = smallWait() .. 'ApplySpellRES("CBRTSTP",Myself)'
elseif ARGS.what == "haste" then
    assert(CBRTS and CBRTS.Status().armed, "ARM_FIRST")
    assert(ARGS.spell == "CBRTHST" or ARGS.spell == "CBRTIHS", "UNKNOWN_SPELL")
    assert(sprite.m_curAction.m_actionID == 0, "SUBJECT_BUSY")
    local count = fixtures()
    assert(count.CBRTHST == 0 and count.CBRTIHS == 0, "HASTE_PRESENT")
    assert(count.CBRTBUF == count.CBRTREG and count.CBRTBUF <= 1, "FIXTURES_MIXED")
    noTimeStop()
    response = smallWait() .. 'ApplySpellRES("' .. ARGS.spell .. '",Myself)'
else
    error("UNKNOWN_WHAT")
end
EEex_Action_QueueResponseStringOnAIBase(response, actor)
return {queued = response, actor = EEex_Sprite_GetName(actor), hp = sprite.m_baseStats.m_hitPoints,
    game_time = chitin.m_pObjectGame.m_worldTime.m_gameTime}
