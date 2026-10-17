-- Disposable BG2:EE 2.7.3.0 / EEex 1.3 diagnostic only. No clock correction.
-- Nothing is patched on load. Install(), Arm(), and Export() are explicit steps.
if CBRTS then return end
CBRTS = {schema = 1, capacity = 8192, epoch = 0, installed = false}
local T = CBRTS
local ffi = require("ffi")
local HEADER, RECORD = 128, 128
local regs = {"rax", "rcx", "rdx", "rbx", "rbp", "rsi", "rdi",
              "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15"}
local saved = {}
for i, name in ipairs(regs) do saved[name] = (#regs - i) * 8 end

-- Each window was decoded from the pinned executable. Relative calls/branches
-- use EEex's dedicated helpers; replay windows contain no relative operands.
T.sites = {
    {id=1, name="preexpiry", rva=0x1E847B, bytes="39 81 A0 3F 00 00", kind="restore",
        actor="rdi", parent="rbx"},
    {id=2, name="parent_remove", rva=0x1E5036, bytes="E8 35 29 22 00", kind="call",
        actor="r14", parent="rbx"},
    {id=3, name="construct", rva=0x1BEDE0, bytes="E8 DB 87 24 00", kind="call",
        actor="rbp", parent="rdi", worker="rbx"},
    {id=4, name="copy", rva=0x1DCAE3, bytes="8B 4B 14 89 4A 14", kind="restore",
        worker="rbx", related="rdx"},
    {id=5, name="dispatch", rva=0x226549, bytes="48 8B 03 48 8B CB", kind="restore",
        actor="r15", worker="rbx", elapsed="r14", list="rsi"},
    {id=6, name="returned", rva=0x226556, bytes="75 06 83 7B 08 00", kind="branch",
        actor="r15", worker="rbx", elapsed="r14", list="rsi"},
    {id=7, name="heal_submission", rva=0x1A5ECE, bytes="C7 44 24 20 01 00 00 00", kind="restore",
        actor="rsi", worker="rbx", related="rdi"},
    {id=8, name="worker_destruct", rva=0x1A475D, bytes="48 8B D9 48 89 01", kind="restore",
        worker="rcx"},
}

local function hex(n) return string.format("0x%X", n) end
local function byteList(s)
    local out = {}
    for b in s:gmatch("%x%x") do out[#out+1] = tonumber(b, 16) end
    return out
end
local function checkBytes(address, bytes)
    for i, b in ipairs(byteList(bytes)) do
        assert(EEex_ReadU8(address+i-1) == b,
            "Unexpected instruction at "..hex(address+i-1).."; no hooks installed")
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
    -- Native BOOL bindings are numbers: zero is truthy in Lua. Visual pause
    -- controls UI rendering and is not an engine pause guarantee.
    assert(world and ((tonumber(world.m_bPaused) or 0) ~= 0 or
        (tonumber(world.m_bHardPaused) or 0) ~= 0), "Pause the lab before this operation")
end
local function assertFreshMainMenu()
    local chitin = EngineGlobals and EngineGlobals.g_pBaldurChitin
    local game = chitin and chitin.m_pObjectGame
    local active = chitin and chitin:GetActiveEngine()
    local start = chitin and chitin.m_pEngineStart
    assert(game and active and start and game.m_bGameLoaded == 0 and
        game.m_bInLoadGame == 0 and game.m_bInLoadArea == 0 and
        EEex_UDToPtr(active) == EEex_UDToPtr(start),
        "Install only at the fresh main menu, before loading or creating a game")
end

function T.Inspect()
    assertLab()
    assert(EEex_Active and jit and EEex_HookBeforeRestoreWithLabels, "EEex/LuaJIT unavailable")
    local base = EEex_Label("Data-CGameEffect::vftable") - 0x58F020
    assert(base > 0 and base % 4096 == 0, "Unexpected image base")
    assert(EEex_GetImageBase() == base, "Image base disagrees with EEex")
    checkBytes(base, "4D 5A")
    local nt = EEex_Read32(base+0x3C)
    assert(nt >= 0x40 and nt <= 0x1000, "Unexpected PE header")
    checkBytes(base+nt, "50 45 00 00 64 86")
    assert(EEex_Read32(base+nt+8) == 0x6A18D73D, "Wrong executable timestamp")
    assert(EEex_ReadPtr(base+0x58F038) == base+0x1E83D0, "Wrong native resolver")
    assert(EEex_ReadPtr(base+0x598B20) == base+0x1A5CA0, "Wrong regeneration vtable")
    for _, site in ipairs(T.sites) do checkBytes(base+site.rva, site.bytes) end
    return {base=base, sites=#T.sites, mode="observation_only", game="2.7.3.0"}
end

-- Public for offline assembly/emulation checks. No native memory is accessed here.
function T.BuildAssembly(site, buffer)
    local a = {}
    local function emit(s) a[#a+1] = s end
    local prefix = "cbrts_"..site.id.."_"
    local function label(s) return prefix..s end
    local function loadRole(dest, original)
        if original then emit("mov "..dest..", qword ptr [rsp+"..saved[original].."]")
        else emit("xor "..dest..", "..dest) end
    end
    emit("pushfq")
    for _, reg in ipairs(regs) do emit("push "..reg) end
    emit("mov r12, "..hex(buffer))
    -- Count entries before reading armed. Once stopped and this count reaches
    -- zero, later disarmed entries cannot modify the payload being exported.
    emit("lock inc dword ptr [r12+56]")
    emit("cmp dword ptr [r12], 1")
    emit("jne "..label("exit"))
    loadRole("r13", site.actor)
    loadRole("r14", site.parent)
    loadRole("r15", site.worker)
    loadRole("rbp", site.related)
    if site.actor then
        emit("cmp r13, qword ptr [r12+16]")
        emit("jne "..label("exit"))
        emit("mov eax, dword ptr [r13+0x48]")
        emit("cmp eax, dword ptr [r12+24]")
        emit("jne "..label("exit"))
    end
    if site.parent then
        emit("mov rax, qword ptr [r14+0x94]")
        emit("mov r10, 0x0047455254524243") -- CBRTREG\0
        emit("cmp rax, r10")
        if site.id == 3 then emit("jne "..label("exit"))
        else
            emit("je "..label("parent_ok"))
            emit("mov r10, 0x0046554254524243") -- CBRTBUF\0
            emit("cmp rax, r10")
            emit("jne "..label("exit"))
            emit(label("parent_ok")..":")
        end
    end
    if site.worker then
        emit("mov rax, qword ptr [r15]")
        emit("cmp rax, qword ptr [r12+32]")
        emit("jne "..label("exit"))
    end
    -- Atomic reservation; records never overwrite earlier observations.
    emit("mov eax, 1")
    emit("lock xadd dword ptr [r12+8], eax")
    emit("cmp eax, dword ptr [r12+4]")
    emit("jae "..label("overflow"))
    emit("mov r11d, eax")
    emit("shl r11, 7")
    emit("add r11, r12")
    emit("add r11, 128")
    emit("mov dword ptr [r11+4], eax")
    emit("mov qword ptr [r11+24], r13")
    emit("mov qword ptr [r11+32], r14")
    emit("mov qword ptr [r11+40], r15")
    emit("mov qword ptr [r11+48], rbp")
    emit("mov eax, dword ptr [rsp+120]")
    emit("mov dword ptr [r11+120], eax")
    -- Read current global pointers, never an actor saved in a past event.
    emit("mov rax, qword ptr [r12+40]")
    emit("mov rax, qword ptr [rax]")
    emit("test rax, rax")
    emit("jz "..label("clock_done"))
    emit("mov rax, qword ptr [rax+0x1090]")
    emit("test rax, rax")
    emit("jz "..label("clock_done"))
    for _, pair in ipairs({{0x3FA0,8},{0x9690,12},{0x9694,16}}) do
        emit("mov edx, dword ptr [rax+"..hex(pair[1]).."]")
        emit("mov dword ptr [r11+"..pair[2].."], edx")
    end
    emit(label("clock_done")..":")
    if site.actor then
        for _, pair in ipairs({{0x48,20},{0x1120,104}}) do
            emit("mov eax, dword ptr [r13+"..hex(pair[1]).."]")
            emit("mov dword ptr [r11+"..pair[2].."], eax")
        end
        emit("movsx eax, word ptr [r13+0x57C]")
        emit("mov dword ptr [r11+100], eax")
        emit("movzx eax, byte ptr [r13+0x58]")
        emit("mov dword ptr [r11+108], eax")
        emit("mov eax, dword ptr [r13+0x20A0]")
        emit("cmp dword ptr [r13+0x4EA4], 0")
        emit("je "..label("immunity"))
        emit("mov eax, dword ptr [r13+0x13F8]")
        emit(label("immunity")..":")
        emit("mov dword ptr [r11+112], eax")
    end
    if site.parent then
        emit("mov rax, qword ptr [r14+0x94]")
        emit("mov qword ptr [r11+56], rax")
        for _, pair in ipairs({{0x24,64},{0x10,68},{0x28,72},{0x6C,76}}) do
            emit("mov eax, dword ptr [r14+"..hex(pair[1]).."]")
            emit("mov dword ptr [r11+"..pair[2].."], eax")
        end
    end
    if site.worker then
        for _, pair in ipairs({{0x1C,80},{0x18,84},{0x28,88},{8,92},{12,96}}) do
            emit("mov eax, dword ptr [r15+"..hex(pair[1]).."]")
            emit("mov dword ptr [r11+"..pair[2].."], eax")
        end
    end
    if site.id == 7 then
        emit("mov eax, dword ptr [rbp+0x10]")
        emit("mov dword ptr [r11+68], eax")
    end
    if site.elapsed then
        emit("mov eax, dword ptr [rsp+"..saved[site.elapsed].."]")
        emit("mov dword ptr [r11+116], eax")
    end
    if site.list then
        emit("mov rax, qword ptr [rsp+"..saved[site.list].."]")
        emit("mov eax, dword ptr [rax+0x38]")
        emit("mov dword ptr [r11+124], eax")
    end
    -- Commit last; a concurrent snapshot can identify an unfinished reservation.
    emit("mov dword ptr [r11], "..site.id)
    emit("jmp "..label("exit"))
    emit(label("overflow")..":")
    emit("lock inc dword ptr [r12+12]")
    emit("mov dword ptr [r12], 0")
    emit(label("exit")..":")
    emit("lock dec dword ptr [r12+56]")
    for i=#regs,1,-1 do emit("pop "..regs[i]) end
    emit("popfq")
    return table.concat(a, "\n").."\n"
end

function T.Install()
    assert(not T.failed, "Earlier install failed; restart this disposable process")
    if T.installed then return {installed=true, already_installed=true} end
    assertFreshMainMenu()
    local inspected = T.Inspect() -- Validate every site before the first mutation.
    T.base = inspected.base
    T.buffer = EEex_Malloc(HEADER + T.capacity * RECORD)
    assert(T.buffer and T.buffer ~= 0, "Cannot allocate diagnostic buffer")
    ffi.fill(ffi.cast("void*", T.buffer), HEADER + T.capacity * RECORD, 0)
    EEex_Write32(T.buffer+4, T.capacity)
    EEex_WritePtr(T.buffer+32, T.base+0x598B18)
    EEex_WritePtr(T.buffer+40, T.base+0x667548)
    EEex_Write32(T.buffer+48, RECORD)
    EEex_Write32(T.buffer+52, T.schema)
    local bodies = {}
    for _, site in ipairs(T.sites) do bodies[site.id] = T.BuildAssembly(site, T.buffer) end
    -- Compile all bodies before patching. They contain no calls or external labels.
    for _, site in ipairs(T.sites) do EEex_JITNear({bodies[site.id], "ret"}) end
    EEex_DisableCodeProtection()
    local ok, why = pcall(function()
        for _, site in ipairs(T.sites) do
            local address, body = T.base+site.rva, {bodies[site.id]}
            if site.kind == "call" then EEex_HookBeforeCallWithLabels(address, {}, body)
            elseif site.kind == "branch" then
                EEex_HookBeforeConditionalJumpWithLabels(address, 4, {}, body)
            else
                local n = #byteList(site.bytes)
                EEex_HookBeforeRestoreWithLabels(address, 0, n, n, {}, body)
            end
        end
    end)
    EEex_EnableCodeProtection()
    if not ok then
        T.failed = true; EEex_Write32(T.buffer, 0)
        error("Observer install incomplete; restart lab: "..tostring(why))
    end
    T.installed = true
    EEex_GameState_AddDestroyedListener(function()
        EEex_Write32(T.buffer, 0)
        T.sessionEnded = true
    end)
    return {installed=true, sites=#T.sites, armed=false, mode="observation_only"}
end

function T.Arm(portrait)
    assert(T.installed and not T.failed, "Install the observer first")
    assertPaused()
    assert(EEex_Read32(T.buffer) == 0, "Stop the previous capture first")
    assert(EEex_Read32(T.buffer+56) == 0, "A recorder is still active; retry in a later paused command")
    assert(not T.dirty, "Export the previous capture before starting another")
    local actor = assert(EEex_Sprite_GetInPortrait(portrait or 0), "No subject in that portrait")
    local pointer = EEex_UDToPtr(actor)
    T.epoch = T.epoch+1
    ffi.fill(ffi.cast("void*", T.buffer+HEADER), T.capacity * RECORD, 0)
    EEex_Write32(T.buffer+8, 0); EEex_Write32(T.buffer+12, 0)
    EEex_WritePtr(T.buffer+16, pointer)
    EEex_Write32(T.buffer+24, actor.m_id)
    EEex_Write32(T.buffer+28, T.epoch)
    T.sessionEnded = false; T.dirty = true
    EEex_Write32(T.buffer, 1)
    return {epoch=T.epoch, actor=actor.m_id, pointer=hex(pointer), mode="observation_only"}
end

function T.Stop()
    if T.buffer then EEex_Write32(T.buffer, 0) end
    return T.Status()
end
function T.Status()
    return {installed=T.installed, failed=T.failed or false, epoch=T.epoch,
        armed=T.buffer and EEex_Read32(T.buffer) == 1 or false,
        reserved=T.buffer and EEex_Read32(T.buffer+8) or 0,
        overflow=T.buffer and EEex_Read32(T.buffer+12) or 0,
        active_recorders=T.buffer and EEex_Read32(T.buffer+56) or 0,
        session_ended=T.sessionEnded or false}
end
function T.Export(name)
    assert(T.installed and T.buffer, "No diagnostic buffer")
    assertPaused()
    assert(EEex_Read32(T.buffer) == 0, "Stop capture, then export in a separate paused command")
    assert(EEex_Read32(T.buffer+56) == 0, "A recorder is still active; retry in a later paused command")
    assert(type(name) == "string" and name:match("^[%w_-]+$"), "Use a simple unique trace name")
    local path = "cbr-timestop-output/"..name..".bin"
    local existing = io.open(path, "rb")
    if existing then existing:close(); error("Trace already exists: "..path) end
    local n = math.min(EEex_Read32(T.buffer+8), T.capacity)
    local f = assert(io.open(path, "wb"))
    local ok, why = f:write("CBRTS001", ffi.string(ffi.cast("void*", T.buffer), HEADER+n*RECORD))
    f:close(); assert(ok, why)
    T.dirty = false
    return {path=path, records=n, status=T.Status()}
end
