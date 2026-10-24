-- Activity recorder for movement and attack checks (global CBRTA). ARGS.op:
--   install: register two EEex listeners once per game process; both return nothing, so they
--     never block a hit or change an action.
--   arm: start recording for portrait 0, which must be ARGS.subject; clears earlier records.
--   read: the records so far. disarm: stop recording, keep the records for a later read.
-- Records: every action the subject starts (world time, action ID, position) and every weapon
-- swing of the subject that hits (world time, target ID). A miss calls no listener, so attack
-- counts need a target that every swing hits. At most 500 records of each kind; more end the
-- recording and set overflow.
assert(type(ARGS) == "table" and type(ARGS.op) == "string", "ARGS.op required")
local LIMIT = 500
local function worldTime()
    return EngineGlobals.g_pBaldurChitin.m_pObjectGame.m_worldTime.m_gameTime
end
if ARGS.op == "install" then
    if not (CBRTA and CBRTA.installed) then
        CBRTA = {installed = true, armed = false, subject = nil, actions = {}, hits = {}, overflow = false}
        EEex_Action_AddSpriteStartedActionListener(function(sprite, action)
            local recorder = CBRTA
            if not recorder.armed or sprite.m_id ~= recorder.subject then return end
            if #recorder.actions >= LIMIT then recorder.armed, recorder.overflow = false, true return end
            recorder.actions[#recorder.actions + 1] = {w = worldTime(), id = action.m_actionID,
                x = sprite.m_pos.x, y = sprite.m_pos.y}
        end)
        EEex_Sprite_AddBlockWeaponHitListener(function(context)
            local recorder = CBRTA
            if not recorder.armed or context.attackingSprite.m_id ~= recorder.subject then return end
            if #recorder.hits >= LIMIT then recorder.armed, recorder.overflow = false, true return end
            recorder.hits[#recorder.hits + 1] = {w = worldTime(), target = context.targetSprite.m_id}
        end)
    end
    return {installed = CBRTA.installed, armed = CBRTA.armed}
end
assert(CBRTA and CBRTA.installed, "INSTALL_FIRST")
if ARGS.op == "arm" then
    assert(type(ARGS.subject) == "string", "ARGS.subject required")
    local sprite = assert(EEex_Sprite_GetInPortrait(0), "NO_SUBJECT")
    assert(EEex_Sprite_GetName(sprite) == ARGS.subject, "NOT_THE_SUBJECT")
    CBRTA.subject, CBRTA.actions, CBRTA.hits, CBRTA.overflow = sprite.m_id, {}, {}, false
    CBRTA.armed = true
elseif ARGS.op == "disarm" then
    CBRTA.armed = false
elseif ARGS.op ~= "read" then
    error("UNKNOWN_OP")
end
return {armed = CBRTA.armed, subject = CBRTA.subject, overflow = CBRTA.overflow, game_time = worldTime(),
    actions = CBRTA.actions, hits = CBRTA.hits}
