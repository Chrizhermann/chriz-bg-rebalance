-- Personal rounds across committed world-time jumps, component 361.
-- Native instruction and field contracts are in research/16-time-jump-round-and-cooldowns.md.
CBRRC = CBRRC or {}
local C = CBRRC
if C.core then return end
C.core = true

local U32 = 4294967296
local function signed32(n) return (n + 2147483648) % U32 - 2147483648 end
local function log(message) print("[CBR Round Clock] "..message:gsub("[\r\n]+", " ")) end
local function pointer(p) return p and p >= 0x10000 and p < 2^47 and p % 8 == 0 end
local mem
function C.UseMemory(m) mem = m end

-- UI work is deferred until the world toolbar is read or pressed. Keep a
-- generation, never a sprite, button array or menu item from the clock hook.
local pending, refreshing, updateButtons
local function markSelected(id)
    EEex_Sprite_IterateSelectedIDs(function(selected)
        if selected == id then pending = {}; return true end
    end)
end

local function refreshToolbar()
    local generation = pending
    if not generation or refreshing or not C.installed then return end
    if not e or not worldScreen or e:GetActiveEngine() ~= worldScreen
        or not EEex_Sprite_GetSelected() then return end
    refreshing = true
    local ok, refreshed = pcall(updateButtons)
    refreshing = false
    if ok and refreshed and pending == generation then pending = nil end
    if not ok then log("toolbar refresh: "..tostring(refreshed)) end
end

local bound = setmetatable({}, {__mode="k"})
local function bindToolbar()
    local methods = buttonArray and getmetatable(buttonArray)
    if not methods or bound[methods] then return end
    -- These are the engine's UI bindings. Stock toolbar items query enabled
    -- before painting; a queued UI click can reach OnLButtonPressed first.
    for _, key in ipairs({"GetButtonEnabled", "OnLButtonPressed"}) do
        local original = methods[key]
        methods[key] = function(self, ...)
            if pending and self == buttonArray then refreshToolbar() end
            return original(self, ...)
        end
    end
    bound[methods] = true
end

local function elapsed(origin, arg, old, hourOrForce)
    if origin == 1 or origin == 2 then return signed32(arg) end
    if origin == 3 and hourOrForce == 1 then return signed32(arg - old) end
    if origin == 4 and hourOrForce == 4500 then return hourOrForce end
    return 0
end
C.Elapsed = elapsed

-- Count eligible virtual engine frames in (2*old, 2*(old+d)]. Also return the
-- parity of the first eligible frame for DoAction's special first haste increment.
local function masked(n, mask)
    local result, bit = 0, 1
    while mask > 0 do
        if mask % 2 == 1 and n % 2 == 1 then result = result + bit end
        n, mask, bit = math.floor(n / 2), math.floor(mask / 2), bit * 2
    end
    return result
end

local function updates(old, d, mask, id)
    if d <= 0 then return 0 end
    local start, span = (2 * old) % 256, 2 * d
    if mask == 0 or mask == 1 or mask == 3 then
        local period = mask + 1
        local first = (id - start - 1) % period + 1
        if first > span then return 0 end
        return 1 + math.floor((span - first) / period), (start + first) % 2
    end
    local phase = masked(id % 256, mask)
    local tail, perCycle, partial, firstParity = span % 256, 0, 0, nil
    for k = 1, math.min(span, 256) do
        if masked((start + k) % 256, mask) == phase then
            perCycle = perCycle + 1
            if k <= tail then partial = partial + 1 end
            if firstParity == nil then firstParity = (start + k) % 2 end
        end
    end
    return math.floor(span / 256) * perCycle + partial, firstParity
end
C.Updates = updates

local attackAction = {
    [3]=true, [27]=true, [29]=true, [38]=true, [87]=true, [98]=true,
    [105]=true, [134]=true, [184]=true, [339]=true, [354]=true, [355]=true,
}
local function age(sprite, id, stats, old, delta)
    local mask = mem.u8(sprite + 0x58)
    local u, firstParity = updates(old, delta, mask, id)
    if u == 0 then return end
    local action, cast = mem.s16(sprite + 0x3F8), mem.s16(sprite + 0x4990)
    if cast >= 0 and mem.i32(sprite + 0x4998) == 0
        and not ((action == 34 or action == 97) and mem.i32(sprite + 0x4994) ~= 0) then
        local h = u
        if math.floor(mem.u32(stats) / 0x8000) % 2 == 1 and mask % 2 == 0 then
            h = updates(old, delta, mask + 1, id)
            if cast == 0 and firstParity ~= id % 2 then h = h + 1 end
        end
        if h > 0 then mem.w16(sprite + 0x4990, cast + h >= 100 and 0xFFFF or cast + h) end
    end
    local attack = mem.s16(sprite + 0x4B9A)
    if attack >= 0 and not attackAction[action]
        and mem.u8(sprite + 0x4BA8) == 0 and mem.i32(sprite + 0x4CA0) == 0 then
        mem.w16(sprite + 0x4B9A, attack + u >= 100 and 0xFFFE or attack + u)
    end
    local hide, poll = mem.i32(sprite + 0x4E70), mem.i32(sprite + 0x5040)
    if hide > 0 then
        mem.w32(sprite + 0x4E70, math.max(0, hide - u))
        if u >= hide then markSelected(id) end
    end
    if poll > 0 then mem.w32(sprite + 0x5040, math.max(0, poll - u)) end
end

C.commits, C.actors, C.sessions = 0, 0, 0
function C.SessionEnded()
    pending = nil
    C.commits, C.actors, C.sessions = 0, 0, C.sessions + 1
    if C.block then
        mem.w32(C.block + 4, 0)
        mem.w32(C.block + 12, 0)
    end
end

-- Only the main-thread gate enters here. No actor or area address escapes this call.
function C.Commit(timer, origin, argDeltaOrNew, argOld, argHourOrForce)
    local delta = elapsed(origin, argDeltaOrNew, argOld, argHourOrForce)
    if delta <= 0 then return 0 end
    local a = C.addresses
    local chitin = mem.ptr(a.chitin)
    if not pointer(chitin) then return 0 end
    local game = mem.ptr(chitin + 0x1090)
    if not pointer(game) or timer ~= game + 0x3FA0 then return 0 end
    local old = origin == 3 and argOld % U32 or (mem.u32(timer) - delta) % U32
    local max, serial = mem.s16(a.maxSlot), mem.s16(a.serial)
    if max < 0 or max > a.slotLimit or serial <= 0 then return 0 end
    local network = mem.ptr(a.network)
    if not pointer(network) then return 0 end
    local owner
    if mem.u8(network + 0x2C9) ~= 0 then owner = mem.u32(network + 0x374) end
    local caster
    if mem.i32(game + 0x9690) ~= 0 then caster = mem.u32(game + 0x9694) end
    local party, areas = {}, {}
    for i = 0, math.min(6, mem.s16(game + 0x6630)) - 1 do
        party[mem.u32(game + 0x6600 + i * 4)] = true
    end
    for i = 0, 11 do
        local area = mem.ptr(game + 0x6598 + i * 8)
        if pointer(area) then areas[area] = true end
    end
    C.commits = C.commits + 1
    for i = 0, max do
        local slot = a.slots + 16 * i
        local generation = mem.s16(slot)
        if generation >= 0 and generation < serial then
            local id, sprite = i * 65536 + generation, mem.ptr(slot + 8)
            if pointer(sprite) and mem.u32(sprite + 0x48) == id and mem.u8(sprite + 8) == 0x31
                and mem.i32(sprite + 0x4EC0) == 0
                and (owner == nil or mem.u32(sprite + 0x50) == owner)
                and (party[id] or areas[mem.ptr(sprite + 0x18)]) then
                local stats = sprite + (mem.i32(sprite + 0x4EA4) == 0 and 0x1DC8 or 0x1120)
                if caster == nil or caster == id or mem.i32(stats + 0x2D8) ~= 0 then
                    age(sprite, id, stats, old, delta)
                    C.actors = C.actors + 1
                end
            end
        end
    end
    return 0
end

function CBRRC_Commit(...)
    local ok, result = pcall(C.Commit, ...)
    if ok then return result end
    log("off, the game stays native: "..tostring(result))
    return -2  -- the gate disarms and counts this error exactly once
end

-- Instruction RVAs for the four origins and registry lookup move together by
-- 0x80 on IWD. Writable globals move by 0x6000, the read-only hour by 0x2000.
C.build = {
    [0x6A18D6DC]={name="BG:EE / SoD", size=0x3524000, code=0, data=0, ro=0},
    [0x6A18D73D]={name="BG2:EE / EET", size=0x3532000, code=0, data=0, ro=0},
    [0x6A18D7E9]={name="IWD:EE", size=0x3563000, code=0x80, data=0x6000, ro=0x2000},
}
local function bytes(hex)
    return (hex:gsub("%x%x", function(pair) return string.char(tonumber(pair, 16)) end))
end
local displaced = bytes("8B39B8716EB036")
local signature = bytes("48895C24084889742410574883EC20")..displaced..bytes("F7E78BC7488BF12BC2")

-- A ReadLString may end at the first NUL. Consume that byte, then resume in
-- bounds. Limit each binding call separately from the overlapping search chunks.
local function readBytes(address, count)
    local parts = {}
    while count > 0 do
        local limit = math.min(count, 1024)
        local part = EEex_ReadLString(address, limit)
        assert(#part <= limit, "invalid EEex string read")
        parts[#parts + 1] = part
        local n = #part
        if n < limit then
            parts[#parts + 1] = "\0"
            n = n + 1
        end
        address, count = address + n, count - n
    end
    return table.concat(parts)
end

local function findChecker(sections)
    local hits = {}
    for _, section in ipairs(sections) do
        if section.exec then
            local overlap = ""
            for address = section.first, section.limit - 1, 8192 do
                local chunk = overlap..readBytes(address, math.min(8192, section.limit - address))
                local from = 1
                while true do
                    local at = chunk:find(signature, from, true)
                    if not at then break end
                    hits[#hits + 1] = address - #overlap + at - 1
                    from = at + 1
                end
                overlap = chunk:sub(2 - #signature)
            end
        end
    end
    assert(#hits == 1, "expected one clock checker, found "..#hits)
    return hits[1]
end

-- Validate the PE header and every virtual section before scanning any section.
function C.Inspect()
    local base = EEex_GetImageBase()
    assert(pointer(base) and base % 4096 == 0 and readBytes(base, 2) == "MZ", "invalid DOS header")
    local nt = mem.u32(base + 0x3C)
    assert(nt >= 0x40 and nt + 24 <= 4096, "invalid PE offset")
    local pe = base + nt
    assert(readBytes(pe, 6) == bytes("504500006486"), "expected x64 PE")
    local count, opt = mem.s16(pe + 6), mem.s16(pe + 20)
    local tableEnd = nt + 24 + opt + count * 40
    assert(count >= 1 and count <= 96 and opt >= 112 and tableEnd <= 4096, "invalid PE section table")
    assert(mem.s16(pe + 24) == 0x20B, "expected PE32+")
    local build = C.build[mem.u32(pe + 8)]
    assert(build and build.size == mem.u32(pe + 24 + 56), "unsupported engine build or image size")
    local headers = mem.u32(pe + 24 + 60)
    assert(tableEnd <= headers and headers <= 4096 and mem.u32(pe + 24 + 32) == 4096,
        "invalid PE headers or section alignment")
    local sections, previousEnd = {}, headers
    for i = 0, count - 1 do
        local s = pe + 24 + opt + 40 * i
        local rva, size, flags = mem.u32(s + 12), mem.u32(s + 8), mem.u32(s + 36)
        assert(rva >= previousEnd and rva % 4096 == 0 and size > 0 and rva + size <= build.size,
            "invalid PE section bounds")
        local exec = math.floor(flags / 0x20000000) % 2 == 1
        local readable = math.floor(flags / 0x40000000) % 2 == 1
        assert(not exec or readable, "unreadable executable section")
        sections[#sections + 1] = {first=base+rva, limit=base+rva+size, exec=exec,
            data=readable and not exec and flags >= 0x80000000,
            ro=readable and not exec and flags < 0x80000000}
        previousEnd = rva + size
    end
    local function checked(address, n, kind)
        for _, s in ipairs(sections) do
            if s[kind] and address >= s.first and address + n <= s.limit then return address end
        end
        error("address outside required PE "..kind.." section", 0)
    end
    local function instruction(rva, hex)
        local expected = bytes(hex)
        local pc = checked(base + build.code + rva, #expected, "exec")
        assert(readBytes(pc, #expected) == expected, "unexpected instruction at RVA "..string.format("%X", pc-base))
        return pc + #expected
    end
    local function relative(rva, opcode)
        local disp = instruction(rva, opcode)
        checked(disp - #opcode/2, #opcode/2 + 4, "exec")
        return disp + 4 + mem.i32(disp)
    end
    local function reference(rva, opcode, target, length, kind)
        assert(relative(rva, opcode) == target, "incorrect native "..kind.." reference")
        return checked(target, length, kind)
    end
    local fn = findChecker(sections)
    local returns = {}
    for i, rva in ipairs({0x251289, 0x25136E, 0x143AFB, 0x2F656C}) do
        assert(relative(rva, "E8") == fn, "incorrect clock caller "..i)
        returns[i] = base + build.code + rva + 5
    end
    instruction(0x25120C, "48895C2408574883EC20")
    instruction(0x25121D, "8BDA488BF9")        -- Add: EBX = delta, RDI = timer
    instruction(0x251251, "8B1103D38911")
    instruction(0x251286, "488BCF")
    instruction(0x2512B0, "48895C2408574883EC20448B09448BC2488BF9") -- Advance: R9D = old time
    instruction(0x2512ED, "2BD94103D881FB84030000")
    instruction(0x251336, "418D14198917")
    instruction(0x25136B, "488BCF")
    instruction(0x143A80, "4883EC28")
    instruction(0x143AAB, "48895C2430488974243848897C2420428B1C018D4104420FB63400")
    instruction(0x143ACD, "498B8090100000488D88A03F00008B394080FE017416")
    instruction(0x143AF9, "8919")
    instruction(0x2F3B10, "48895C2410488974241848897C2420554154415541564157")
    instruction(0x2F6556, "488B8890100000")
    instruction(0x2F6563, "4881C1A03F00000101")
    local hour = reference(0x2F655D, "8B05", base + build.ro + 0x59E75C, 4, "ro")
    assert(mem.u32(hour) == 4500, "incorrect world-screen hour")
    local data = base + build.data
    -- The normal world UI pass re-fetches the current game and passes its
    -- embedded array as the sole argument. EEex already hooks the SetState
    -- caller, so validate the independent world caller and the callee entry.
    instruction(0x2EE2E1, "488B88901000004881C140410000")
    local update = relative(0x2EE2EF, "E8")
    assert(update == base + build.code + 0x267800, "incorrect toolbar refresh target")
    instruction(0x267800, "488BC4488958104889701848897820554154415541564157")
    local capacity = 0x7FFF
    return {name=build.name, fn=fn, site=fn+15, returns=returns, slotLimit=capacity-1, update=update,
        chitin=reference(0x143AC6, "4C8B05", data+0x667548, 8, "data"),
        network=reference(0x17DBF5, "488B15", data+0x667560, 8, "data"),
        maxSlot=reference(0x27671B, "663905", data+0x68F8F4, 2, "data"),
        serial=reference(0x276729, "66390D", data+0x68F8F8, 2, "data"),
        slots=reference(0x276735, "4C8D05", data+0x68F910, 16*capacity, "data")}
end

-- Block layout: enabled, Lua errors, owner thread, off-thread skips (four
-- dwords), then the four verified 64-bit return PCs in origin order.
local registers = {"rax","rdx","rcx","rbx","rbp","rsi","rdi","r8","r9","r10","r11","r12","r13","r14","r15"}
local function decimal(address) return string.format("%.0f", address) end
function C.BuildGate(block, luaCall)
    local lines = {
        "pushfq", "push rax", "push rdx", "mov rdx, "..decimal(block),
        "cmp dword ptr [rdx], 1", "jne cbr_rc_fast_exit",
        "mov rax, qword ptr [rsp+64]", -- return PC at native RSP+40, plus our first three pushes
    }
    local function emit(s) lines[#lines+1] = s end
    for i = 1, 4 do
        emit("cmp rax, qword ptr [rdx+"..(8+8*i).."]")
        emit("je cbr_rc_origin"..i)
    end
    emit("jmp cbr_rc_fast_exit")
    for i = 1, 4 do
        emit("cbr_rc_origin"..i..":")
        if i == 3 then
            emit("cmp sil, 1")
            emit("jne cbr_rc_fast_exit")
        end
        emit("mov eax, "..i)
        if i < 4 then emit("jmp cbr_rc_thread") end
    end
    emit("cbr_rc_thread:")
    emit("push rcx")
    emit("mov ecx, dword ptr gs:[0x48]")
    emit("cmp ecx, dword ptr [rdx+8]")
    emit("je cbr_rc_main")
    emit("lock inc dword ptr [rdx+12]")
    emit("jmp cbr_rc_restore_rcx")
    emit("cbr_rc_main:")
    for i = 4, #registers do emit("push "..registers[i]) end
    emit("#STACK_MOD(128)")
    emit("lea rsp, [rsp-96]")
    emit("#STACK_MOD(96)")
    for i = 0, 5 do emit("movdqu xmmword ptr [rsp+"..(16*i).."], xmm"..i) end
    emit("mov r12, qword ptr [rsp+192]")    -- original RCX, third saved GPR
    emit("mov r13d, eax")                   -- origin ID
    emit("mov r14d, ebx")                   -- committed delta or new time
    emit("mov r15d, edi")                   -- pre-commit time for sync
    emit("mov ebp, dword ptr [rsp+208]")    -- original EAX for the direct hour
    emit("cmp eax, 3")
    emit("jne cbr_rc_call")
    emit("movzx ebp, sil")                  -- the fifth argument for a broadcast
    emit("cbr_rc_call:")
    local before = table.concat(lines, "\n").."\n"
    lines = {}
    emit("cmp rax, -2")
    emit("jne cbr_rc_done")
    emit("mov rdx, "..decimal(block))
    emit("mov dword ptr [rdx], 0")
    emit("inc dword ptr [rdx+4]")
    emit("cbr_rc_done:")
    for i = 0, 5 do emit("movdqu xmm"..i..", xmmword ptr [rsp+"..(16*i).."]") end
    emit("lea rsp, [rsp+96]")
    emit("#STACK_MOD(-96)")
    for i = #registers, 4, -1 do emit("pop "..registers[i]) end
    emit("#STACK_MOD(-128)")
    emit("cbr_rc_restore_rcx:")
    emit("pop rcx")
    emit("cbr_rc_fast_exit:")
    emit("pop rdx")
    emit("pop rax")
    emit("popfq")
    return {before, luaCall, table.concat(lines, "\n").."\n"}
end

local function commitCall()
    local args = {}
    for i, reg in ipairs({"r12","r13","r14","r15","rbp"}) do
        args[i] = function(offset)
            return {"mov qword ptr ss:[rsp+#$(1)], "..reg.." #ENDL", {offset}}
        end
    end
    return EEex_FlattenTable({
        "#MAKE_SHADOW_SPACE(72) #ENDL",
        -- With shadow space already present, GenLuaCall's #ALIGN adds zero.
        -- Initialize lua_pcallk's actual Win64 stack args (ctx and continuation).
        "mov qword ptr ss:[rsp+32], 0 #ENDL mov qword ptr ss:[rsp+40], 0 #ENDL",
        EEex_GenLuaCall("CBRRC_Commit", {args=args, returnType=EEex_LuaCallReturnType.Number}),
        "jmp cbr_rc_lua_ok #ENDL call_error: #ENDL mov rax, -2 #ENDL",
        "cbr_rc_lua_ok: #ENDL #DESTROY_SHADOW_SPACE #ENDL",
    })
end

C.requiredFunctions = {"EEex_GameState_AddInitializedListener", "EEex_GameState_AddDestroyedListener",
    "EEex_Menu_AddAfterMainFileLoadedListener", "EEex_Actionbar_AddButtonsUpdatedListener",
    "EEex_Sprite_IterateSelectedIDs", "EEex_Sprite_GetSelected", "EEex_Key_AddPressedListener",
    "EEex_GetImageBase", "EEex_ReadLString", "EEex_ReadU8", "EEex_Read16", "EEex_Read32",
    "EEex_ReadU32", "EEex_ReadPtr", "EEex_WriteU16", "EEex_Write32", "EEex_WritePtr",
    "EEex_Malloc", "EEex_Free", "EEex_JITNear", "EEex_ExposeToLua", "EEex_GenLuaCall",
    "EEex_FlattenTable", "EEex_HookBeforeRestoreWithLabels", "EEex_JITAt",
    "EEex_DisableCodeProtection", "EEex_EnableCodeProtection"}

local gateMayRun = false
local function patch(a)
    local block = EEex_Malloc(48)
    assert(pointer(block), "cannot allocate round clock block")
    C.block = block
    for offset = 0, 12, 4 do mem.w32(block + offset, 0) end
    for i, pc in ipairs(a.returns) do EEex_WritePtr(block + 8 + i * 8, pc) end

    -- EEex_ExposeToLua expects a lua_CFunction. Store the TID in memory and
    -- return zero Lua results. Returning the TID in EAX would claim that many results.
    local helper = EEex_JITNear({[[
        mov eax, dword ptr gs:[0x48]
        mov rdx, ]]..decimal(block)..[[

        mov dword ptr [rdx+8], eax
        xor eax, eax
        ret
    ]]})
    assert(helper and helper > 0, "cannot assemble main-thread helper")
    EEex_ExposeToLua(helper, "CBRRC_CaptureThread")
    local captured, why = pcall(CBRRC_CaptureThread)
    CBRRC_CaptureThread = nil
    assert(captured and mem.u32(block + 8) ~= 0, "cannot capture main thread: "..tostring(why))
    -- lua_CFunction. RBX preserves the Lua state over the engine call. The
    -- push aligns RSP; both calls have 32 bytes of Win64 shadow space.
    local refresh = EEex_JITNear({([[
        push rbx
        sub rsp, 32
        mov rbx, rcx
        mov rax, %s
        mov edx, dword ptr gs:[0x48]
        cmp edx, dword ptr [rax+8]
        jne cbr_rc_ui_skip
        cmp dword ptr [rax], 1
        jne cbr_rc_ui_skip
        mov rax, %s
        mov rax, qword ptr [rax]
        test rax, rax
        jz cbr_rc_ui_skip
        mov rcx, qword ptr [rax+0x1090]
        test rcx, rcx
        jz cbr_rc_ui_skip
        add rcx, 0x4140
        mov rax, %s
        call rax
        mov edx, 1
        jmp cbr_rc_ui_result
        cbr_rc_ui_skip:
        xor edx, edx
        cbr_rc_ui_result:
        mov rcx, rbx
        call #L(Hardcoded_lua_pushboolean)
        mov eax, 1
        add rsp, 32
        pop rbx
        ret
    ]]):format(decimal(block), decimal(a.chitin), decimal(a.update))})
    assert(refresh and refresh > 0, "cannot assemble toolbar refresh")
    EEex_ExposeToLua(refresh, "CBRRC_UpdateButtons")
    updateButtons, CBRRC_UpdateButtons = assert(CBRRC_UpdateButtons), nil
    local body = EEex_FlattenTable(C.BuildGate(block, commitCall()))
    EEex_GameState_AddDestroyedListener(C.SessionEnded)
    bindToolbar()
    EEex_Menu_AddAfterMainFileLoadedListener(bindToolbar)
    EEex_Actionbar_AddButtonsUpdatedListener(function()
        if not refreshing then pending = nil end
    end)
    -- A toolbar hotkey can be dispatched before any item is painted.
    EEex_Key_AddPressedListener(function() if pending then refreshToolbar() end end)
    EEex_DisableCodeProtection()
    local ok, reason = pcall(function()
        assert(readBytes(a.site, 7) == displaced, "clock hook window changed before installation")
        -- EEex assembles the complete trampoline before writing the jump at the site.
        gateMayRun = true
        local hooked, err = pcall(EEex_HookBeforeRestoreWithLabels, a.site, 0, 7, 7, {}, body)
        local after = readBytes(a.site, 7)
        if hooked and after:byte(1) == 0xE9 and after:sub(6) == "\144\144"
            and math.abs(mem.i32(a.site + 1)) > 7 then return end
        if after ~= displaced then
            -- The site was ours to write in this initialization window. Restore just
            -- these two original instructions if publication was incomplete.
            EEex_JITAt(a.site, {"mov edi, dword ptr [rcx] #ENDL mov eax, 0x36B06E71 #ENDL"})
            assert(readBytes(a.site, 7) == displaced, "cannot restore incomplete round clock hook")
        end
        gateMayRun = false
        error("cannot install round clock hook: "..tostring(err), 0)
    end)
    EEex_EnableCodeProtection()
    if not ok then error(reason, 0) end
    C.addresses, C.installed = a, true
    mem.w32(block, 1)
end

function C.Status()
    local block = C.block
    return {enabled=block ~= nil and mem.u32(block) == 1, installed=C.installed == true,
        refused=C.refused, commits=C.commits, actors=C.actors, sessions=C.sessions,
        lua_errors=block and mem.u32(block + 4) or 0,
        off_thread_skips=block and mem.u32(block + 12) or 0}
end

function C.Start()
    if C.started then return C.Status() end
    C.started = true
    local ok, why = pcall(function()
        assert(EEex_Active, "EEex is not active")
        for _, name in ipairs(C.requiredFunctions) do
            assert(type(_G[name]) == "function", "missing "..name)
        end
        assert(type(EEex_LuaCallReturnType) == "table" and EEex_LuaCallReturnType.Number ~= nil,
            "missing EEex_LuaCallReturnType.Number")
        C.UseMemory({ptr=EEex_ReadPtr, u8=EEex_ReadU8, s16=EEex_Read16, i32=EEex_Read32,
            u32=EEex_ReadU32, w16=EEex_WriteU16, w32=EEex_Write32})
        patch(C.Inspect())
    end)
    if ok then
        log("on ("..C.addresses.name.." 2.7.3.0)")
    else
        CBRRC_CaptureThread = nil
        if C.block and not gateMayRun then
            EEex_Free(C.block)
            C.block = nil
        end
        C.refused = tostring(why)
        log("off, the game stays native: "..C.refused)
    end
    return C.Status()
end
