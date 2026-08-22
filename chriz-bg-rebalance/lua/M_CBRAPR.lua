-- chriz-bg-rebalance component 407 - Cleric of Tempus: specialization APR.
-- +1/2 APR while the SELECTED weapon is one the character has 2+ pips in.
--
-- Mechanism: EEex_Opcode_AddListsResolvedListener fires at the tail of every
-- CGameSprite::ProcessEffectList() PASS - one per AI tick per sprite. The
-- engine REBUILDS CDerivedStats (Reload + effect lists re-applied) only on
-- some of those passes (every 15th tick, or when an effect was added); the
-- other passes reach this hook with the same, unrebuilt struct. A relative
-- write must therefore be made idempotent per rebuild, or it accumulates
-- (v0.1.0 shipped exactly that bug: 1.5 -> 2 -> ... -> 5, snapping back on
-- each rebuild). Evidence: research/07-spec-apr-listener-runaway.md.
--
-- Idempotence marker: a private spell state (SPLSTATE.IDS CBR_TEMPUS_SPEC_APR,
-- allocated at install time) set in the SAME CDerivedStats the bump lands in.
-- Reload clears every spell state, so the bit is clear exactly when this pass
-- rebuilt the stats, and still set on the passes that did not. Nothing is
-- persisted in saves; removing this file reverts the game to pure vanilla.
--
-- Wielded semantics: m_selectedWeapon indexes the engine's own 39-slot
-- equipment array (SLOTS.IDS: 35-38 quick weapons, 9 off-hand, 10 fist AND
-- conjured weapons). The weapon's proficiency comes from its ITM header
-- (0x31). Conjured weapons (Spiritual Hammer) qualify on purpose - the kit
-- summons them; bare fists carry no weapon proficiency and drop out at the
-- range check. Off-hand is ignored: APR is a round-level pool keyed to the
-- main hand, same as the engine's own WSPATCK handling.
--
-- The two constants below are stamped by the installer - kit ids and spell
-- state ids are allocated per-install and must never be hardcoded.
--
-- Runtime is LuaJIT (5.1 syntax): no |, &, << operators here - use the EEex
-- bit helpers. The file must also compile under plain Lua 5.3 (CI gate).

-- The vanilla engine auto-loads every override/M_*.lua; without EEex the
-- listener API does not exist, so bow out instead of erroring at load.
if not (EEex_Opcode_AddListsResolvedListener and EEex_Sprite_GetStat
        and EEex_BAnd and EEex_BOr and EEex_LShift) then
    print("M_CBRAPR: EEex not detected - Tempus specialization APR inactive")
    return
end

local CBR_APR_TEMPUS_KIT = %CBR_TEMPUS_KIT_ID%
local CBR_APR_MARKER_STATE = %CBR_TEMPUS_SPEC_APR_STATE%
local CBR_APR_STAT_KIT = 152

-- CDerivedStats.m_spellStates is Array<unsigned int,8>: bit id lives in
-- word id/32 at mask 1<<(id%32) (same packing as the engine's SetSpellState).
local CBR_APR_MARKER_WORD = math.floor(CBR_APR_MARKER_STATE / 32)
local CBR_APR_MARKER_MASK = EEex_LShift(1, CBR_APR_MARKER_STATE % 32)

local cbrAprDead = false
local cbrAprFailures = 0

-- Stat-8 key encoding: 0-5 whole attacks, 6-10 = 0.5-4.5.
local function cbrAprDecode(key)
    if key <= 5 then return key end
    return (key - 6) + 0.5
end

local function cbrAprEncode(apr)
    if apr >= 5 then return 5 end
    local whole = math.floor(apr)
    if apr == whole then return whole end
    return 6 + whole
end

local function cbrAprBody(sprite)
    -- Read and write the struct ProcessEffectList rebuilds; the marker and
    -- the bump must live in the same object.
    local stats = sprite.m_derivedStats
    if not stats then return end
    if stats:GetAtOffset(CBR_APR_STAT_KIT) ~= CBR_APR_TEMPUS_KIT then return end
    local states = stats.m_spellStates
    if not states then return end
    local word = states:get(CBR_APR_MARKER_WORD)
    if EEex_BAnd(word, CBR_APR_MARKER_MASK) ~= 0 then return end
    local equipment = sprite.m_equipment
    if not equipment then return end
    -- 39-slot equipment array; 0xFF marks "no selection" transients.
    local selected = equipment.m_selectedWeapon
    if selected == nil or selected < 0 or selected > 38 then return end
    local item = equipment.m_items:get(selected)
    if not item then return end
    local res = item.pRes
    if not res then return end
    local header = res.pHeader
    if not header then return end
    local prof = header.proficiencyType
    -- Weapon proficiencies: 89-107 and 115 (club); 111-114 are fighting
    -- styles and never legitimate ITM proficiency values.
    if prof < 89 or prof > 115 or (prof >= 111 and prof <= 114) then return end
    if stats:GetAtOffset(prof) < 2 then return end
    -- Marker first: if the array cannot be written, nothing is bumped and
    -- the failure fuse below retires the listener instead of letting it run
    -- away again.
    states:set(CBR_APR_MARKER_WORD, EEex_BOr(word, CBR_APR_MARKER_MASK))
    stats.m_nNumberOfAttacks = cbrAprEncode(cbrAprDecode(stats.m_nNumberOfAttacks) + 0.5)
end

EEex_Opcode_AddListsResolvedListener(function(sprite)
    if cbrAprDead then return end
    local ok = pcall(cbrAprBody, sprite)
    if not ok then
        cbrAprFailures = cbrAprFailures + 1
        if cbrAprFailures >= 10 then
            cbrAprDead = true
            print("CBR Tempus spec APR: disabled after repeated errors")
        end
    end
end)
