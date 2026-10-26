-- The clock-correction prototype (CBRTFix.lua). ARGS.op: install (fresh main menu, hooks stay
-- inert), select (paused, before the fixtures), verify (paused, after them), disable or status.
-- select and verify act on portrait 0, which must be ARGS.subject.
assert(type(ARGS) == "table" and type(ARGS.op) == "string", "ARGS.op required")
assert(CBRTF, "FIX_NOT_LOADED")
if ARGS.op == "install" then return CBRTF.Install() end
if ARGS.op == "status" then return CBRTF.Status() end
if ARGS.op == "disable" then return CBRTF.Disable() end
assert(ARGS.op == "select" or ARGS.op == "verify", "UNKNOWN_OP")
assert(type(ARGS.subject) == "string", "ARGS.subject required")
local world = EngineGlobals.g_pBaldurChitin.m_pEngineWorld
assert((tonumber(world.m_bPaused) or 0) ~= 0 or (tonumber(world.m_bHardPaused) or 0) ~= 0, "PAUSE_FIRST")
local sprite = assert(EEex_Sprite_GetInPortrait(0), "NO_SUBJECT")
assert(EEex_Sprite_GetName(sprite) == ARGS.subject, "NOT_THE_SUBJECT")
if ARGS.op == "verify" then return CBRTF.Verify(0) end
return CBRTF.Select(0)
