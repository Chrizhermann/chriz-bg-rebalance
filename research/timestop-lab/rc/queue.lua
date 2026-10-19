-- Queue script actions on the subject (portrait 0) through its own action queue; they run
-- when the game runs. ARGS.subject: the subject's name, checked first.
-- ARGS.what = "fixtures": ApplySpellRES of CBRTBUF and CBRTREG; only while a capture is armed.
-- ARGS.what = "damage": ApplyDamage(Myself, ARGS.amount, crushing); only while disarmed.
assert(type(ARGS) == "table" and type(ARGS.subject) == "string" and type(ARGS.what) == "string",
    "ARGS.subject and ARGS.what required")
local chitin = EngineGlobals.g_pBaldurChitin
local world = chitin.m_pEngineWorld
assert((tonumber(world.m_bPaused) or 0) ~= 0 or (tonumber(world.m_bHardPaused) or 0) ~= 0, "PAUSE_FIRST")
local sprite = assert(EEex_Sprite_GetInPortrait(0), "NO_SUBJECT")
assert(EEex_Sprite_GetName(sprite) == ARGS.subject, "NOT_THE_SUBJECT")
local response
if ARGS.what == "fixtures" then
    assert(CBRTS and CBRTS.Status().armed, "ARM_FIRST")
    response = 'ApplySpellRES("CBRTBUF",Myself)\nApplySpellRES("CBRTREG",Myself)'
elseif ARGS.what == "damage" then
    assert(not (CBRTS and CBRTS.Status().armed), "DISARMED_ONLY")
    local amount = tonumber(ARGS.amount)
    assert(amount and amount >= 1 and amount <= 50 and amount % 1 == 0, "INVALID_AMOUNT")
    response = "ApplyDamage(Myself," .. amount .. ",0)"
else
    error("UNKNOWN_WHAT")
end
EEex_Action_QueueResponseStringOnAIBase(response, sprite)
return {queued = response, hp = sprite.m_baseStats.m_hitPoints,
    game_time = chitin.m_pObjectGame.m_worldTime.m_gameTime}
