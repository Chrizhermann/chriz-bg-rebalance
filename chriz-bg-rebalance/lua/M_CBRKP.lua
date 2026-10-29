-- Kit weapon lists for multiclass characters (BG Rebalance 411).
-- The engine takes a kit's own WEAPPROF column only when the kit's KITLIST
-- CLASS equals the character's class, so a multiclass character with a kit
-- of one of its classes (Yeslick: fighter/cleric, cleric kit) trains from the
-- multiclass column. For the class/kit pairs in CBRKPKIT.2DA this hook lets
-- the native kit-column branch run instead. The engine still reads every
-- limit from WEAPPROF; nothing else that checks KITLIST CLASS changes.
-- Native lookup verified on BG2EE/EET 2.7.3.0 (the same code in 2.6.6.0).

CBRKitProficiency = CBRKitProficiency or { Status = "not initialized" }
local state = CBRKitProficiency
if state.queued or state.installed then return end
if not EEex_Active then
    state.Status = "EEex is required"
    print("CBR kit weapon lists: " .. state.Status)
    return
end

local function requireValue(condition, message)
    if not condition then error("CBR kit weapon lists: " .. message) end
end

local function initialize()
    local registry = EEex_Resource_Load2DA("CBRKPKIT")
    requireValue(registry:findColumnLabel("CLASS") == 0
        and registry:findColumnLabel("KIT") == 1, "invalid CBRKPKIT registry")
    local entries, seen = {}, {}
    for row in EEex_Resource_Get2DARowTableIterator(registry, false) do
        local class, kit = tonumber(row[1]), tonumber(row[2])
        requireValue(class and class == math.floor(class) and class >= 1 and class <= 255,
            "invalid class identifier")
        -- Only kits of the 0x4000 range take the native kit branch.
        requireValue(kit and kit == math.floor(kit) and kit > 0x4000 and kit < 0x8000,
            "invalid kit identifier")
        local key = class .. ":" .. kit
        if not seen[key] then
            seen[key] = true
            entries[#entries + 1] = { class = class, index = kit - 0x4000 }
        end
    end
    if #entries == 0 then
        state.Status = "no registered kits"
        return
    end

    local site = EEex_TryLabel("CBR-KitProficiencyColumn")
    requireValue(site ~= nil, "compatible kit-proficiency signature was not loaded")
    -- movzx eax,bpl; cmp [rsp+0x50],eax; jne (taken on a class mismatch);
    -- movsx edx,word [rdi+0x2640]. The label is the JNE.
    local expected = {
        0x40,0x0F,0xB6,0xC5,0x39,0x44,0x24,0x50,
        0x75,0x6A,0x0F,0xBF,0x97,0x40,0x26,0x00,0x00,
    }
    for i, byte in ipairs(expected) do
        requireValue(EEex_ReadU8(site - 8 + i - 1) == byte,
            "kit lookup changed or another mod already hooked it")
    end

    -- Runs only when the native JNE is taken. EBX holds the kit index (the
    -- kit without 0x4000), EBP the character's class. A registered pair goes
    -- on along the native kit-column path (jmp_fail); every other pair keeps
    -- the native jump to the class column. Only flags change.
    local assembly = {}
    for i, entry in ipairs(entries) do
        assembly[#assembly + 1] = string.format(
            "cmp ebx, 0x%X #ENDL jne cbr_kp_next_%d #ENDL cmp ebp, %d #ENDL je jmp_fail #ENDL cbr_kp_next_%d: #ENDL",
            entry.index, i, entry.class, i)
    end

    EEex_DisableCodeProtection()
    local ok, err = pcall(function()
        -- The JNE is two bytes; the seven-byte MOVSX after it is restored.
        EEex_HookConditionalJumpOnSuccess(site, 7, assembly)
    end)
    EEex_EnableCodeProtection()
    if not ok then error(err) end
    state.installed = true
    state.Status = "active"
    print("CBR kit weapon lists: active (" .. #entries .. " registered kit and class pairs)")
end

state.queued = true
EEex_GameState_AddInitializedListener(function()
    local ok, err = pcall(initialize)
    if not ok then
        state.Status = tostring(err)
        print(state.Status)
    end
end)
