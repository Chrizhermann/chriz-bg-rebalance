-- Kit-specific native bard spellbook progression. Provider API 1.
-- Native lookup verified on BG2EE/EET and IWDEE 2.7.3.
-- Required EEex APIs checked in 1.2/1.3; IWDEE live acceptance is pending.
-- See research/09 for the shared native instruction layout.
-- The original engine still calculates levels, capacities and bonus slots.
-- This hook changes only the C2DArray pointer at the bard-table lookup.

CBRSpellProgression = CBRSpellProgression or { API = 1, Status = "not initialized" }
local state = CBRSpellProgression
if state.queued or state.installed then return end
if not EEex_Active then
    state.Status = "EEex is required"
    print("CBR bard progression: " .. state.Status)
    return
end

local function requireValue(condition, message)
    if not condition then error("CBR bard progression: " .. message) end
end

local function initialize()
    local version = EEex_Resource_Load2DA("CBRSPVER")
    requireValue(version:getAtLabels("VALUE", "API") == "1", "unsupported provider API")
    local registry = EEex_Resource_Load2DA("CBRSPKIT")
    requireValue(registry:findColumnLabel("CLASS") == 0
        and registry:findColumnLabel("KIT") == 1
        and registry:findColumnLabel("TABLE") == 2, "invalid CBRSPKIT registry")

    -- Keep these userdata alive for the entire process. Generated native code
    -- embeds their addresses; freeing/replacing them would leave dangling pointers.
    state.tables = {}
    state.kits = {}
    for row in EEex_Resource_Get2DARowTableIterator(registry, false) do
        local class, kit, resref = tonumber(row[1]), tonumber(row[2]), row[3]:upper()
        requireValue(class and class == math.floor(class), "invalid class identifier")
        -- Other class registrations are reserved for separate providers. This
        -- hook runs only inside the native bard branch and leaves them alone.
        if class == 5 then
            requireValue(kit and kit >= 0 and kit <= 4294967295 and kit == math.floor(kit),
                "invalid kit identifier")
            requireValue(#resref > 0 and #resref <= 8 and resref:match("^[%w_#]+$"),
                "invalid table resource name")
            requireValue(not state.kits[kit] or state.kits[kit] == resref,
                "conflicting tables for kit " .. kit)
            if not state.tables[resref] then
                local tab = EEex_Resource_Load2DA(resref)
                local _, rows = tab:getDimensions()
                requireValue(rows > 0, "missing or empty table " .. resref)
                for tier = 1, 9 do
                    requireValue(tab:findColumnLabel(tostring(tier)) >= 0,
                        resref .. " must contain spell levels 1 through 9")
                end
                state.tables[resref] = tab
            end
            state.kits[kit] = resref
        end
    end

    local site = EEex_TryLabel("CBR-BardSpellTable")
    requireValue(site ~= nil, "compatible bard hook signature was not loaded")
    local expected = {
        0x48,0x8D,0x8E,0x38,0x07,0x00,0x00,0x4C,0x8D,0x45,0xF0,0x48,
        0x8D,0x55,0xF8,0xE8,false,false,false,false,0x4C,0x8D,0x45,0xE4,
    }
    for i, byte in ipairs(expected) do
        -- The CALL displacement changes with executable layout (BG2EE/IWDEE).
        -- Keep checking the actual instructions and frame/table operands.
        requireValue(byte == false or EEex_ReadU8(site + i - 1) == byte,
            "bard lookup changed or another mod already hooked it")
    end

    local kits = {}
    for kit in pairs(state.kits) do kits[#kits + 1] = kit end
    table.sort(kits)
    local assembly = { "pushfq #ENDL" }
    for i, kit in ipairs(kits) do
        local ptr = EEex_UDToPtr(state.tables[state.kits[kit]])
        assembly[#assembly + 1] = string.format(
            "cmp ebx, 0x%X #ENDL jne cbr_next_%d #ENDL mov rcx, %d #ENDL jmp cbr_done #ENDL cbr_next_%d: #ENDL",
            kit, i, ptr, i)
    end
    assembly[#assembly + 1] = "cbr_done: #ENDL popfq #ENDL"

    EEex_DisableCodeProtection()
    local ok, err = pcall(function()
        -- Restore the seven-byte LEA first, then optionally replace its RCX.
        -- EBX contains the full kit id here. No calls or other registers change.
        EEex_HookAfterRestoreWithLabels(site, 0, 7, 7, {
            { "hook_integrity_watchdog_ignore_registers", { EEex_HookIntegrityWatchdogRegister.RCX } },
        }, assembly)
    end)
    EEex_EnableCodeProtection()
    if not ok then error(err) end
    state.installed = true
    state.Status = "active"
    print("CBR bard progression: active (" .. #kits .. " registered kits)")
end

-- Read-only console aid; counts exclude kit/item bonus slots.
function CBRSpellProgression.GetBaseSlots(kit, level, tier)
    local resref = state.kits and state.kits[kit]
    if not resref then return nil end
    return tonumber(state.tables[resref]:getAtLabels(tostring(tier), tostring(level)))
end

state.queued = true
EEex_GameState_AddInitializedListener(function()
    local ok, err = pcall(initialize)
    if not ok then
        state.Status = tostring(err)
        print(state.Status)
    end
end)
