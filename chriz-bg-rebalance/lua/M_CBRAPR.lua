-- chriz-bg-rebalance component 407 - Cleric of Tempus: specialization APR.
-- +1/2 APR while the SELECTED weapon is one the character has 2+ pips in.
--
-- Mechanism: EEex_Opcode_AddListsResolvedListener fires after every rebuild
-- of a sprite's derived stats (equip/switch/level-up/load/buff expiry all
-- funnel through CGameSprite::ProcessEffectList, which starts from a fresh
-- CDerivedStats). The write and the event that would erase it are the same
-- event, hook ordered after the erase: self-healing, no polling, no effect
-- objects, nothing persisted in saves. Removing this file reverts the game
-- to pure vanilla with zero residue.
--
-- Wielded semantics: m_selectedWeapon indexes the engine's own 39-slot
-- equipment array (SLOTS.IDS: 35-38 quick weapons, 9 off-hand, 10 fist AND
-- conjured weapons). The weapon's proficiency comes from its ITM header
-- (0x31). Conjured weapons (Spiritual Hammer) qualify on purpose - the kit
-- summons them; bare fists carry no weapon proficiency and drop out at the
-- range check. Off-hand is ignored: APR is a round-level pool keyed to the
-- main hand, same as the engine's own WSPATCK handling.
--
-- The kit id constant below is stamped by the installer from KIT.IDS - kit
-- ids are allocated per-install and must never be hardcoded.

-- The vanilla engine auto-loads every override/M_*.lua; without EEex the
-- listener API does not exist, so bow out instead of erroring at load.
if not (EEex_Opcode_AddListsResolvedListener and EEex_Sprite_GetStat) then
    print("M_CBRAPR: EEex not detected - Tempus specialization APR inactive")
    return
end

local CBR_APR_TEMPUS_KIT = %CBR_TEMPUS_KIT_ID%
local CBR_APR_STAT_KIT = 152

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
    if EEex_Sprite_GetStat(sprite, CBR_APR_STAT_KIT) ~= CBR_APR_TEMPUS_KIT then return end
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
    if EEex_Sprite_GetStat(sprite, prof) < 2 then return end
    local stats = sprite:getActiveStats()
    if not stats then return end
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
