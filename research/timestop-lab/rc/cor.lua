-- The clock correction for every creature (CBRTCor.lua). ARGS.op:
--   install  at the fresh main menu; the gates stay off
--   status, disable
--   record   ARGS.on = "1" starts a new record (ARGS.discard = "1" drops an unexported one),
--            "0" stops it
-- Paused only:
--   enable   the correction; portrait 0 proves the effect list layout
--   observe  the gates run with the recorder only, for native controls
--   watch    the recorder follows the party (portraits 0-5) and the creatures ARGS.ids (object
--            IDs separated by spaces)
--   export   cbr-timestop-output/ARGS.name.jsonl; refuses an existing file
assert(type(ARGS) == "table" and type(ARGS.op) == "string", "ARGS.op required")
assert(CBRTC, "COR_NOT_LOADED")
local op = ARGS.op
if op == "install" then return CBRTC.Install() end
if op == "status" then return CBRTC.Status() end
if op == "disable" then return CBRTC.Disable() end
if op == "record" then
    assert(ARGS.on == "1" or ARGS.on == "0", "ARGS.on required")
    return CBRTC.Record(ARGS.on == "1", ARGS.discard == "1")
end
assert(op == "enable" or op == "observe" or op == "watch" or op == "export", "UNKNOWN_OP")
local world = EngineGlobals.g_pBaldurChitin.m_pEngineWorld
assert((tonumber(world.m_bPaused) or 0) ~= 0 or (tonumber(world.m_bHardPaused) or 0) ~= 0, "PAUSE_FIRST")
if op == "enable" then return CBRTC.Enable(0) end
if op == "observe" then return CBRTC.Observe() end
if op == "export" then
    assert(type(ARGS.name) == "string", "ARGS.name required")
    return CBRTC.ExportRecord(ARGS.name)
end
local ids = {}
for slot = 0, 5 do
    local sprite = EEex_Sprite_GetInPortrait(slot)
    if sprite then ids[#ids + 1] = sprite.m_id end
end
for word in tostring(ARGS.ids or ""):gmatch("%S+") do
    local id = tonumber(word)
    assert(id and id > 0 and id % 1 == 0, "INVALID_ID")
    local object = EEex_GameObject_Get(id)
    assert(object and object:isSprite(true), "NOT_A_CREATURE")
    ids[#ids + 1] = id
end
return CBRTC.Watch(ids)
