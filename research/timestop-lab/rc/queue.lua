-- Queue script actions through an actor's own action queue; they run when the game runs.
-- ARGS.subject: the subject's name (portrait 0), checked first.
-- ARGS.what = "fixtures": ApplySpellRES of CBRTBUF and CBRTREG on the subject; only while a
--   capture is armed and neither fixture is still on the subject (a refresh would mix two cases).
-- ARGS.what = "damage": ApplyDamage(Myself, ARGS.amount, crushing) on the subject; only while disarmed.
-- ARGS.what = "timestop": the controller in portrait 1 (ARGS.controller: its name) waits ARGS.wait
--   AI updates (SmallWait), then applies CBRTSTP to itself, so it is the Time Stop caster and the
--   subject is frozen. Only while a capture is armed, with exactly one of each fixture on the
--   subject, and while no Time Stop runs.
assert(type(ARGS) == "table" and type(ARGS.subject) == "string" and type(ARGS.what) == "string",
    "ARGS.subject and ARGS.what required")
local chitin = EngineGlobals.g_pBaldurChitin
local world = chitin.m_pEngineWorld
assert((tonumber(world.m_bPaused) or 0) ~= 0 or (tonumber(world.m_bHardPaused) or 0) ~= 0, "PAUSE_FIRST")
local sprite = assert(EEex_Sprite_GetInPortrait(0), "NO_SUBJECT")
assert(EEex_Sprite_GetName(sprite) == ARGS.subject, "NOT_THE_SUBJECT")
local function fixtures()
    local count = {CBRTBUF = 0, CBRTREG = 0}
    EEex_Utility_IterateCPtrList(sprite.m_timedEffectList, function(effect)
        local source = effect.m_sourceRes:get()
        if count[source] then count[source] = count[source] + 1 end
    end)
    return count
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
    local count = fixtures()
    assert(count.CBRTBUF == 1 and count.CBRTREG == 1, "FIXTURES_FIRST")
    assert(EEex_Read32(EEex_UDToPtr(chitin.m_pObjectGame) + 0x9690) == 0, "TIME_STOP_ACTIVE")
    local wait = tonumber(ARGS.wait)
    assert(wait and wait >= 0 and wait <= 300 and wait % 1 == 0, "INVALID_WAIT")
    response = (wait > 0 and "SmallWait(" .. wait .. ")\n" or "") .. 'ApplySpellRES("CBRTSTP",Myself)'
else
    error("UNKNOWN_WHAT")
end
EEex_Action_QueueResponseStringOnAIBase(response, actor)
return {queued = response, actor = EEex_Sprite_GetName(actor), hp = sprite.m_baseStats.m_hitPoints,
    game_time = chitin.m_pObjectGame.m_worldTime.m_gameTime}
