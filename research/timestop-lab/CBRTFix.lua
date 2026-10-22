-- Disposable BG2:EE 2.7.3.0 / EEex 1.3 clock-correction prototype for one lab subject and the
-- CBRTBUF/CBRTREG fixtures. Nothing is patched on load. Install(), Select(), Verify() and
-- Disable() are explicit steps; the installed hooks stay inert until Select().
--   Time Stop: in each world tick in which the engine marks the subject frozen, every selected
--     timed parent's deadline (and the regeneration origin) moves one tick later, before that
--     pass checks for expiry. Effects applied mid-stop earn only the later ticks.
--   Haste: the selected regeneration worker runs at most once per world tick, on a pulse counter
--     that follows the subject's active time (world time minus its frozen ticks).
--   Rebuilds keep the worker's phase. After a heal the kept phase is the one a native, un-hasted
--     rebuild one tick later would seed (Christopher's choice on 2026-10-23).
if CBRTF then return end
CBRTF = {schema = 1, installed = false}
local F = CBRTF
local ffi = require("ffi")
local SIZE = 256
local regs = {"rax", "rcx", "rdx", "rbx", "rbp", "rsi", "rdi",
              "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15"}
local saved = {}
for i, name in ipairs(regs) do saved[name] = (#regs - i) * 8 end

-- Block offsets. Lua writes the block only while the game is paused; the hooks while it runs.
local B = {enabled=0, subject=8, subjectID=16, frozen=20, lastFrozen=24, listOffset=28,
    chitin=32, regenVtable=40, listVerified=48, shifts=52, admitted=56, suppressed=60, unmatched=64,
    restored=68, newParents=72, healReseeds=76, phaseRecords=80,
    parent=128, worker=136, origin0=144, frozen0=148, kappa=152, kappaSet=156,
    lastAdmitted=160, phase=164, phaseBefore=168, period=172, valid=176, activeOrigin=180}
F.layout = B

-- Each window was decoded from the pinned executable; none holds a relative operand or a
-- branch target past its first byte. "after" replays the window first, "before" last.
F.sites = {
    -- ProcessEffectList: the engine has just marked a frozen noncaster (sprite +0x520C).
    {id=1, name="frozen", rva=0x3ABA9D, bytes="44 89 AE 0C 52 00 00", kind="after", actor="rsi"},
    -- Periodic dispatch: the list counter is copied into the worker; r8d holds elapsed.
    {id=2, name="dispatch", rva=0x226543, bytes="89 43 1C 49 8B D7", kind="after",
        actor="r15", worker="rbx"},
    -- Regeneration ApplyEffect: native phase seeded, before the worker joins the list.
    {id=3, name="construct", rva=0x1BEDD2, bytes="66 89 53 1A 48 8D 8D 08 1A 00 00", kind="after",
        actor="rbp", parent="rdi", worker="rbx"},
    -- Regeneration AIUpdate epilog, reached by every return path.
    {id=4, name="worker_exit", rva=0x1A5F19, bytes="48 83 C4 58 5E 5B", kind="before",
        actor="rsi", worker="rbx"},
}

local CBRTREG, CBRTBUF = "0x0047455254524243", "0x0046554254524243"

local function hex(n) return string.format("0x%X", n) end
local function byteList(s)
    local out = {}
    for b in s:gmatch("%x%x") do out[#out+1] = tonumber(b, 16) end
    return out
end
local function checkBytes(address, bytes)
    for i, b in ipairs(byteList(bytes)) do
        assert(EEex_ReadU8(address+i-1) == b,
            "Unexpected instruction at "..hex(address+i-1).."; no correction installed")
    end
end
local function readFile(path)
    local f = assert(io.open(path, "rb"), "Missing lab guard: "..path)
    local s = f:read("*a"); f:close(); return s
end
local function assertLab()
    assert(readFile("CBRTSLab.id") == "CBR TimeStop Lab 2730\n", "Not the owned lab")
    assert(readFile("engine.lua"):match('engine_name%s*=%s*"CBR TimeStop Lab 2730"'),
        "Wrong game profile")
end
local function assertPaused()
    local chitin = EngineGlobals and EngineGlobals.g_pBaldurChitin
    local world = chitin and chitin.m_pEngineWorld
    assert(world and ((tonumber(world.m_bPaused) or 0) ~= 0 or
        (tonumber(world.m_bHardPaused) or 0) ~= 0), "Pause the lab before this operation")
end
local function assertFreshMainMenu()
    local chitin = EngineGlobals and EngineGlobals.g_pBaldurChitin
    local game = chitin and chitin.m_pObjectGame
    local active = chitin and chitin.pActiveEngine
    local start = chitin and chitin.m_pEngineStart
    assert(game and active and start and game.m_bGameLoaded == 0 and
        game.m_bInLoadGame == 0 and game.m_bInLoadArea == 0 and
        EEex_UDToPtr(active) == EEex_UDToPtr(start),
        "Install only at the fresh main menu, before loading or creating a game")
end

function F.Inspect()
    assertLab()
    assert(EEex_Active and jit and EEex_HookAfterRestoreWithLabels and EEex_HookBeforeRestoreWithLabels,
        "EEex/LuaJIT unavailable")
    local base = EEex_Label("Data-CGameEffect::vftable") - 0x58F020
    assert(base > 0 and base % 4096 == 0, "Unexpected image base")
    assert(EEex_GetImageBase() == base, "Image base disagrees with EEex")
    checkBytes(base, "4D 5A")
    local nt = EEex_Read32(base+0x3C)
    assert(nt >= 0x40 and nt <= 0x1000, "Unexpected PE header")
    checkBytes(base+nt, "50 45 00 00 64 86")
    assert(EEex_Read32(base+nt+8) == 0x6A18D73D, "Wrong executable timestamp")
    -- The regeneration worker's vtable must call the AIUpdate whose epilog site 4 patches.
    assert(EEex_ReadPtr(base+0x598B20) == base+0x1A5CA0, "Wrong regeneration vtable")
    for _, site in ipairs(F.sites) do checkBytes(base+site.rva, site.bytes) end
    return {base=base, sites=#F.sites, game="2.7.3.0"}
end

-- Public for offline assembly/emulation checks. No native memory is accessed here.
function F.BuildAssembly(site, block)
    local a = {}
    local function emit(s) a[#a+1] = s end
    local prefix = "cbrtf_"..site.id.."_"
    local function label(s) return prefix..s end
    local function at(offset) return "[r12+"..offset.."]" end
    local function loadRole(dest, original)
        if original then emit("mov "..dest..", qword ptr [rsp+"..saved[original].."]") end
    end
    -- World time into ebp, or jump to `fail` when the game object is absent.
    local function worldTime(fail)
        emit("mov rax, qword ptr "..at(B.chitin))
        emit("mov rax, qword ptr [rax]")
        emit("test rax, rax")
        emit("jz "..label(fail))
        emit("mov rax, qword ptr [rax+0x1090]")
        emit("test rax, rax")
        emit("jz "..label(fail))
        emit("mov ebp, dword ptr [rax+0x3FA0]")
    end
    local function subjectOnly()
        emit("cmp r13, qword ptr "..at(B.subject))
        emit("jne "..label("exit"))
        emit("mov eax, dword ptr [r13+0x48]")
        emit("cmp eax, dword ptr "..at(B.subjectID))
        emit("jne "..label("exit"))
    end
    emit("pushfq")
    for _, reg in ipairs(regs) do emit("push "..reg) end
    emit("mov r12, "..hex(block))
    emit("cmp dword ptr "..at(B.enabled)..", 1")
    emit("jne "..label("exit"))
    loadRole("r13", site.actor)
    loadRole("r14", site.parent)
    loadRole("r15", site.worker)
    if site.id == 1 then
        subjectOnly()
        -- Nothing is counted or walked until Lua has proven the list layout on this subject.
        emit("cmp dword ptr "..at(B.listVerified)..", 1")
        emit("jne "..label("exit"))
        worldTime("exit")
        -- One shift per distinct frozen tick: a hasted actor passes twice per tick, and a pause
        -- steps world time back one tick without undoing the ticks already counted.
        emit("cmp ebp, dword ptr "..at(B.lastFrozen))
        emit("jbe "..label("exit"))
        emit("mov dword ptr "..at(B.lastFrozen)..", ebp")
        emit("inc dword ptr "..at(B.frozen))
        emit("mov eax, dword ptr "..at(B.listOffset))
        emit("mov rbx, qword ptr [r13+rax+8]") -- CPtrList m_pNodeHead
        emit("mov ecx, 4096")
        emit(label("next")..":")
        emit("test rbx, rbx")
        emit("jz "..label("exit"))
        emit("dec ecx")
        emit("jz "..label("exit"))
        emit("mov r14, qword ptr [rbx+0x10]") -- CNode data
        emit("mov rbx, qword ptr [rbx]") -- CNode pNext
        emit("test r14, r14")
        emit("jz "..label("next"))
        emit("cmp dword ptr [r14+0x24], 0x1000") -- absolute deadline only
        emit("jne "..label("next"))
        emit("mov rax, qword ptr [r14+0x94]")
        emit("mov r10, "..CBRTREG)
        emit("cmp rax, r10")
        emit("je "..label("regeneration"))
        emit("mov r10, "..CBRTBUF)
        emit("cmp rax, r10")
        emit("jne "..label("next"))
        emit("inc dword ptr [r14+0x28]")
        emit("inc dword ptr "..at(B.shifts))
        emit("jmp "..label("next"))
        emit(label("regeneration")..":")
        emit("inc dword ptr [r14+0x28]")
        emit("inc dword ptr "..at(B.shifts))
        -- +0x6C is the time origin only for op98; other opcodes keep it.
        emit("cmp dword ptr [r14+0x10], 98")
        emit("jne "..label("next"))
        emit("inc dword ptr [r14+0x6C]")
        emit("jmp "..label("next"))
    elseif site.id == 2 then
        subjectOnly()
        emit("mov rax, qword ptr [r15]")
        emit("cmp rax, qword ptr "..at(B.regenVtable))
        emit("jne "..label("exit"))
        emit("cmp dword ptr "..at(B.valid)..", 1")
        emit("jne "..label("unmatched"))
        emit("cmp r15, qword ptr "..at(B.worker))
        emit("jne "..label("unmatched"))
        worldTime("exit")
        emit("movzx eax, word ptr [r15+0x1A]")
        emit("mov dword ptr "..at(B.phaseBefore)..", eax")
        emit("cmp ebp, dword ptr "..at(B.lastAdmitted))
        emit("jbe "..label("suppress"))
        emit("mov dword ptr "..at(B.lastAdmitted)..", ebp")
        emit("mov eax, ebp")
        emit("sub eax, dword ptr "..at(B.frozen)) -- active time T
        emit("cmp dword ptr "..at(B.kappaSet)..", 1")
        emit("je "..label("counter"))
        -- The first admitted pass keeps the native pulse grid: kappa + T = the copied counter.
        emit("mov ecx, dword ptr [r15+0x1C]")
        emit("sub ecx, eax")
        emit("mov dword ptr "..at(B.kappa)..", ecx")
        emit("mov dword ptr "..at(B.kappaSet)..", 1")
        emit(label("counter")..":")
        emit("add eax, dword ptr "..at(B.kappa))
        emit("mov dword ptr [r15+0x1C], eax")
        emit("inc dword ptr "..at(B.admitted))
        emit("jmp "..label("exit"))
        -- A second pass in the same tick runs as a no-op: elapsed 0, no 15-tick boundary.
        emit(label("suppress")..":")
        emit("mov dword ptr [r15+0x1C], 0")
        emit("mov qword ptr [rsp+"..saved.r8.."], 0")
        emit("inc dword ptr "..at(B.suppressed))
        emit("jmp "..label("exit"))
        emit(label("unmatched")..":")
        emit("inc dword ptr "..at(B.unmatched))
    elseif site.id == 3 then
        subjectOnly()
        -- Every regeneration worker is built here (copies are never dispatched), so a new
        -- object at the tracked address is never the tracked worker unless re-matched below.
        emit("cmp r15, qword ptr "..at(B.worker))
        emit("jne "..label("filter"))
        emit("mov qword ptr "..at(B.worker)..", 0")
        emit(label("filter")..":")
        emit("mov rax, qword ptr [r14+0x94]")
        emit("mov r10, "..CBRTREG)
        emit("cmp rax, r10")
        emit("jne "..label("exit"))
        emit("cmp dword ptr [r14+0x24], 0x1000")
        emit("jne "..label("exit"))
        emit("cmp dword ptr [r14+0x10], 98")
        emit("jne "..label("exit"))
        emit("cmp dword ptr "..at(B.valid)..", 1")
        emit("jne "..label("new"))
        emit("cmp r14, qword ptr "..at(B.parent))
        emit("jne "..label("new"))
        -- The same parent has moved by exactly the frozen ticks counted since it was tracked;
        -- a reused address with another origin is a new parent.
        emit("mov eax, dword ptr "..at(B.frozen))
        emit("sub eax, dword ptr "..at(B.frozen0))
        emit("add eax, dword ptr "..at(B.origin0))
        emit("cmp eax, dword ptr [r14+0x6C]")
        emit("jne "..label("new"))
        emit("mov eax, dword ptr "..at(B.phase))
        emit("mov word ptr [r15+0x1A], ax")
        emit("mov qword ptr "..at(B.worker)..", r15")
        emit("inc dword ptr "..at(B.restored))
        emit("jmp "..label("exit"))
        emit(label("new")..":")
        emit("mov qword ptr "..at(B.parent)..", r14")
        emit("mov qword ptr "..at(B.worker)..", r15")
        emit("mov eax, dword ptr [r14+0x6C]")
        emit("mov dword ptr "..at(B.origin0)..", eax")
        emit("mov ecx, dword ptr "..at(B.frozen))
        emit("mov dword ptr "..at(B.frozen0)..", ecx")
        emit("sub eax, ecx")
        emit("mov dword ptr "..at(B.activeOrigin)..", eax")
        emit("xor eax, eax")
        emit("mov dword ptr "..at(B.kappa)..", eax")
        emit("mov dword ptr "..at(B.kappaSet)..", eax")
        emit("mov dword ptr "..at(B.lastAdmitted)..", eax")
        emit("movzx eax, word ptr [r15+0x1A]") -- the native seed
        emit("mov dword ptr "..at(B.phase)..", eax")
        emit("mov dword ptr "..at(B.phaseBefore)..", eax")
        emit("movzx eax, word ptr [r15+0x18]")
        emit("mov dword ptr "..at(B.period)..", eax")
        emit("mov dword ptr "..at(B.valid)..", 1")
        emit("inc dword ptr "..at(B.newParents))
    else
        emit("cmp dword ptr "..at(B.valid)..", 1")
        emit("jne "..label("exit"))
        emit("cmp r15, qword ptr "..at(B.worker))
        emit("jne "..label("exit"))
        emit("cmp r13, qword ptr "..at(B.subject))
        emit("jne "..label("exit"))
        emit("movzx r9d, word ptr [r15+0x1A]")
        emit("mov ecx, dword ptr "..at(B.period))
        emit("cmp ecx, 2")
        emit("jb "..label("record"))
        emit("test r9d, r9d")
        emit("jne "..label("record"))
        emit("lea edx, [rcx-1]")
        emit("cmp dword ptr "..at(B.phaseBefore)..", edx")
        emit("jne "..label("record"))
        -- This call healed (period - 1 -> 0). Keep the phase a native rebuild on the next
        -- un-hasted tick would seed: floor((T + 1 - activeOrigin) / 15) % period.
        worldTime("record")
        emit("mov eax, ebp")
        emit("sub eax, dword ptr "..at(B.frozen))
        emit("inc eax")
        emit("sub eax, dword ptr "..at(B.activeOrigin))
        emit("xor edx, edx")
        emit("mov r8d, 15")
        emit("div r8d")
        emit("xor edx, edx")
        emit("div ecx")
        emit("mov r9d, edx")
        emit("inc dword ptr "..at(B.healReseeds))
        emit(label("record")..":")
        emit("mov dword ptr "..at(B.phase)..", r9d")
        emit("inc dword ptr "..at(B.phaseRecords))
    end
    emit(label("exit")..":")
    for i=#regs,1,-1 do emit("pop "..regs[i]) end
    emit("popfq")
    return table.concat(a, "\n").."\n"
end

local function verifyList(sprite)
    -- The frozen hook walks this list natively: m_pNodeHead +8, CNode pNext +0, data +0x10.
    local list = EEex_UDToPtr(sprite.m_timedEffectList)
    local walked, bound, node = {}, {}, EEex_ReadPtr(list + 8)
    while node ~= 0 and #walked < 4096 do
        walked[#walked+1] = EEex_ReadPtr(node + 0x10)
        node = EEex_ReadPtr(node)
    end
    EEex_Utility_IterateCPtrList(sprite.m_timedEffectList, function(effect)
        bound[#bound+1] = EEex_UDToPtr(effect)
    end)
    assert(#walked == #bound, "Timed effect list layout mismatch")
    for i = 1, #bound do assert(walked[i] == bound[i], "Timed effect list layout mismatch") end
    return #bound
end

function F.Install()
    assert(not F.failed, "Earlier install failed; restart this disposable process")
    if F.installed then return {installed=true, already_installed=true} end
    assertFreshMainMenu()
    local inspected = F.Inspect() -- Validate every site before the first mutation.
    F.base = inspected.base
    F.block = EEex_Malloc(SIZE)
    assert(F.block and F.block ~= 0, "Cannot allocate correction block")
    ffi.fill(ffi.cast("void*", F.block), SIZE, 0)
    EEex_WritePtr(F.block+B.chitin, F.base+0x667548)
    EEex_WritePtr(F.block+B.regenVtable, F.base+0x598B18)
    local bodies = {}
    for _, site in ipairs(F.sites) do bodies[site.id] = F.BuildAssembly(site, F.block) end
    -- Compile all bodies before patching. They contain no calls or external labels.
    for _, site in ipairs(F.sites) do EEex_JITNear({bodies[site.id], "ret"}) end
    EEex_DisableCodeProtection()
    local ok, why = pcall(function()
        for _, site in ipairs(F.sites) do
            local address, n = F.base+site.rva, #byteList(site.bytes)
            if site.kind == "after" then
                EEex_HookAfterRestoreWithLabels(address, 0, n, n, {}, {bodies[site.id]})
            else
                EEex_HookBeforeRestoreWithLabels(address, 0, n, n, {}, {bodies[site.id]})
            end
        end
    end)
    EEex_EnableCodeProtection()
    if not ok then
        F.failed = true; EEex_Write32(F.block+B.enabled, 0)
        error("Correction install incomplete; restart lab: "..tostring(why))
    end
    F.installed = true
    EEex_GameState_AddDestroyedListener(function()
        EEex_Write32(F.block+B.enabled, 0)
        F.sessionEnded = true
    end)
    return {installed=true, sites=#F.sites, enabled=false}
end

-- Select before the fixtures, so the first construct of the regeneration is tracked.
function F.Select(portrait)
    assert(F.installed and not F.failed, "Install the correction first")
    assertPaused()
    -- Fail closed: a refused selection leaves the correction disabled.
    EEex_Write32(F.block+B.enabled, 0)
    local sprite = assert(EEex_Sprite_GetInPortrait(portrait or 0), "No subject in that portrait")
    local pointer = EEex_UDToPtr(sprite)
    local offset = EEex_UDToPtr(sprite.m_timedEffectList) - pointer
    assert(offset > 0 and offset < 0x10000, "Unexpected timed effect list offset")
    -- An empty list proves no layout; the frozen body then stays idle until Verify().
    local verified = verifyList(sprite) > 0
    ffi.fill(ffi.cast("void*", F.block+B.shifts), 128-B.shifts, 0)
    ffi.fill(ffi.cast("void*", F.block+B.parent), SIZE-B.parent, 0)
    EEex_WritePtr(F.block+B.subject, pointer)
    EEex_Write32(F.block+B.subjectID, sprite.m_id)
    EEex_Write32(F.block+B.frozen, 0)
    EEex_Write32(F.block+B.lastFrozen, 0)
    EEex_Write32(F.block+B.listOffset, offset)
    EEex_Write32(F.block+B.listVerified, verified and 1 or 0)
    F.sessionEnded = false
    EEex_Write32(F.block+B.enabled, 1)
    return F.Status()
end

-- The frozen body walks the subject's timed list natively; prove the walk on its own effects.
function F.Verify(portrait)
    assert(F.installed and not F.failed, "Install the correction first")
    assertPaused()
    assert(EEex_Read32(F.block+B.enabled) == 1, "Select a subject first")
    local sprite = assert(EEex_Sprite_GetInPortrait(portrait or 0), "No subject in that portrait")
    assert(EEex_UDToPtr(sprite) == EEex_ReadPtr(F.block+B.subject) and
        sprite.m_id == EEex_Read32(F.block+B.subjectID), "Not the selected subject")
    local ok, count = pcall(verifyList, sprite)
    if not ok then
        EEex_Write32(F.block+B.enabled, 0)
        error(count, 0)
    end
    assert(count > 0, "No timed effect on the subject yet; apply the fixtures first")
    EEex_Write32(F.block+B.listVerified, 1)
    return F.Status()
end

-- One aligned store; a body already running finishes its pass, later passes stay native.
function F.Disable()
    if F.block then EEex_Write32(F.block+B.enabled, 0) end
    return F.Status()
end

function F.Status()
    if not F.block then return {installed=F.installed, failed=F.failed or false, enabled=false} end
    local function u32(name) return EEex_Read32(F.block+B[name]) end
    return {installed=F.installed, failed=F.failed or false, enabled=u32("enabled") == 1,
        session_ended=F.sessionEnded or false, subject=u32("subjectID"),
        layout_verified=u32("listVerified") == 1,
        frozen_ticks=u32("frozen"), last_frozen_world=u32("lastFrozen"), shifts=u32("shifts"),
        admitted=u32("admitted"), suppressed=u32("suppressed"), unmatched=u32("unmatched"),
        restored=u32("restored"), new_parents=u32("newParents"), heal_reseeds=u32("healReseeds"),
        phase_records=u32("phaseRecords"),
        entry={valid=u32("valid") == 1, kappa=u32("kappa"), kappa_set=u32("kappaSet") == 1,
            last_admitted=u32("lastAdmitted"), phase=u32("phase"), period=u32("period"),
            origin0=u32("origin0"), frozen0=u32("frozen0"), active_origin=u32("activeOrigin")}}
end
