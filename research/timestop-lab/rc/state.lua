-- Read-only: lab identity, EEex/LuaJIT and whether this is still the fresh main menu.
local chitin = EngineGlobals and EngineGlobals.g_pBaldurChitin
local game = chitin and chitin.m_pObjectGame
local active, start = chitin and chitin.pActiveEngine, chitin and chitin.m_pEngineStart
local f = io.open("CBRTSLab.id", "rb")
local id = f and f:read("*a")
if f then f:close() end
return {lab_id = id, cbrts_loaded = CBRTS ~= nil, cbrts_installed = CBRTS and CBRTS.installed or false,
    eeex_active = EEex_Active and true or false, jit = jit and jit.version,
    image_base = string.format("0x%X", EEex_GetImageBase()),
    game_loaded = game and game.m_bGameLoaded, in_load_game = game and game.m_bInLoadGame,
    in_load_area = game and game.m_bInLoadArea,
    at_start_engine = (active and start and EEex_UDToPtr(active) == EEex_UDToPtr(start)) or false}
