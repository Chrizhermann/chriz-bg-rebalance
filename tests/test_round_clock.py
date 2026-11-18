"""Component 361 on actual Lua 5.2 and LuaJIT, with a byte-addressed substitute for EEex.

Steam tests map file sections at virtual addresses in Lua. No game code is executed.
"""
from __future__ import annotations

import os
import struct
import unittest
from pathlib import Path

from lupa.lua52 import LuaRuntime as Lua52
from lupa.luajit21 import LuaRuntime as LuaJIT

ROOT = Path(__file__).resolve().parents[1]
CORE = (ROOT / "chriz-bg-rebalance/lua/CBRRC.lua").read_text(encoding="ascii")
AUTO = (ROOT / "chriz-bg-rebalance/lua/M_CBRRC.lua").read_text(encoding="ascii")
BASE, BLOCK = 0x156780000, 0x212345000
STAMP = 0x6A18D73D
FN = 0x11FF4  # crosses the scanner's 8192-byte boundary in the synthetic image
PATTERN = bytes.fromhex("48895C24084889742410574883EC208B39B8716EB036F7E78BC7488BF12BC2")
CALLERS = (0x251289, 0x25136E, 0x143AFB, 0x2F656C)
CHITIN, NETWORK, GAME, AREA = 0x300000000, 0x300010000, 0x300020000, 0x300040000
TIMER = GAME + 0x3FA0
FIELDS = ((0x4990, 2), (0x4B9A, 2), (0x4E70, 4), (0x5040, 4))
ATTACKS = (3, 27, 29, 38, 87, 98, 105, 134, 184, 339, 354, 355)
DELTAS = (0, 1, 15, 89, 90, 99, 100, 899, 900, 901, 915, 4500, 36000)
OFF = "[CBR Round Clock] off, the game stays native: "

SHIM = r"""
pages, logs, writes = {}, {}, {}
loads, queues, destroys, hooks, allocations, frees = 0, 0, 0, 0, 0, 0
protected = true
function print(s) logs[#logs+1] = s end
function read(a, n)
    local i, offset = math.floor(a/4096), a%4096
    local p = assert(pages[i], "unmapped read at "..a)
    if offset+n <= 4096 then return p:sub(offset+1, offset+n) end
    return p:sub(offset+1)..read(a+4096-offset, n-4096+offset)
end
function put(a, s)
    local i, offset = math.floor(a/4096), a%4096
    local p = assert(pages[i], "unmapped write at "..a)
    local n = math.min(#s, 4096-offset)
    pages[i] = p:sub(1,offset)..s:sub(1,n)..p:sub(offset+n+1)
    if n < #s then put(a+n, s:sub(n+1)) end
end
local function uint(a, n)
    local s, result = read(a,n), 0
    for i=n,1,-1 do result=result*256+s:byte(i) end
    return result
end
local function integer(a, n)
    local v = uint(a,n)
    if v >= 2^(8*n-1) then return v-2^(8*n) end
    return v
end
local function write(a, v, n)
    if tracking then writes[#writes+1] = {a,n} end
    local out = {}
    for i=1,n do out[i]=string.char(v%256); v=math.floor(v/256) end
    put(a,table.concat(out))
end
EEex_Active = true
EEex_LuaCallReturnType = {Number=2}
function EEex_GetImageBase() return base end
function EEex_ReadLString(a,n)
    assert(n > 0 and n <= 1024)
    local s=read(a,n)
    local at=s:find("\0",1,true)
    if at then return s:sub(1,at-1) end
    return s
end
function EEex_ReadU8(a) return uint(a,1) end
function EEex_Read16(a) return integer(a,2) end
function EEex_Read32(a) return integer(a,4) end
function EEex_ReadU32(a) return uint(a,4) end
function EEex_ReadPtr(a) return integer(a,8) end
function EEex_Write32(a,v) write(a,v,4) end
function EEex_WriteU16(a,v) write(a,v,2) end
function EEex_WritePtr(a,v) write(a,v,8) end
function EEex_Malloc(n)
    assert(n==48); allocations=allocations+1
    pages[block/4096]=string.rep("\0",4096)
    return block
end
function EEex_Free(a) assert(a==block); frees=frees+1; pages[a/4096]=nil end
function EEex_FlattenTable(t)
    local out={}
    local function flatten(v)
        if type(v)=="table" then for _,s in ipairs(v) do flatten(s) end
        else out[#out+1]=v end
    end
    flatten(t); return out
end
function EEex_GenLuaCall(name, meta)
    assert(name=="CBRRC_Commit" and meta.returnType==EEex_LuaCallReturnType.Number)
    local r={}
    for i,arg in ipairs(meta.args) do r[i]=arg(64+(i-1)*8) end
    return {r,"; test Lua call #ENDL"}
end
function EEex_JITNear(t)
    local asm = table.concat(t,"\n")
    if asm:find("Hardcoded_lua_pushboolean",1,true) then
        refreshAsm = asm; return base-0x11000
    end
    helper=asm; return base-0x10000
end
function EEex_ExposeToLua(a,name)
    if name=="CBRRC_UpdateButtons" then
        assert(a==base-0x11000)
        _G[name]=function()
            if wrongThread or EEex_ReadU32(block)~=1 then return false end
            refreshed=(refreshed or 0)+1
            if insideRefresh then insideRefresh() end
            updated()
            return true
        end
        return
    end
    assert(a==base-0x10000)
    _G[name]=function() EEex_Write32(block+8,0x1234) end
end
function EEex_DisableCodeProtection() assert(protected); protected=false end
function EEex_EnableCodeProtection() assert(not protected); protected=true end
function EEex_HookBeforeRestoreWithLabels(a,delay,n,resume,labels,body)
    assert(not protected and delay==0 and n==7 and resume==7 and #labels==0)
    hooks=hooks+1; hookAddress=a; gate=table.concat(body,"\n")
    put(a,"\233\000\001\000\000\144\144")
end
function EEex_JITAt(a,body)
    assert(not protected and table.concat(body):find("0x36B06E71",1,true))
    put(a,"\139\057\184\113\110\176\054")
end
function Infinity_DoFile(name) assert(name=="CBRRC"); loads=loads+1; assert(load(core))() end
function EEex_GameState_AddInitializedListener(f) init=f; queues=queues+1 end
function EEex_GameState_AddDestroyedListener(f) destroy=f; destroys=destroys+1 end
selected={}
function EEex_Sprite_IterateSelectedIDs(f) for _,id in ipairs(selected) do if f(id) then break end end end
function EEex_Sprite_GetSelected() return selected[1] end
function EEex_Actionbar_AddButtonsUpdatedListener(f) updated=f end
function EEex_Menu_AddAfterMainFileLoadedListener(f) menuLoaded=f end
function EEex_Key_AddPressedListener(f) keyPressed=f end
worldScreen={}; activeScreen=worldScreen
e={GetActiveEngine=function() return activeScreen end}
function newBar()
    local mt={}
    mt.__index=mt
    mt.GetButtonEnabled=function(self,i) return i,true end
    mt.OnLButtonPressed=function(self,i) return i,refreshed or 0 end
    return setmetatable({},mt)
end
buttonArray=newBar()
"""


class Host:
    def __init__(self, runtime=Lua52):
        self.lua = runtime(encoding="latin-1", unpack_returned_tuples=True)
        self.lua.execute(SHIM)
        self.g = self.lua.globals()
        self.g.base, self.g.block, self.g.core = BASE, BLOCK, CORE
        self.lua.execute("io=nil; os=nil; ffi=nil; bit=nil; bit32=nil; require=nil")

    def map(self, addr, data):
        for page in range(addr // 4096, (addr + len(data) - 1) // 4096 + 1):
            if self.g.pages[page] is None:
                self.g.pages[page] = bytes(4096)
        # Avoid a recursively concatenated megabyte string at the Lua boundary.
        for start in range(0, len(data), 4096):
            self.g.put(addr + start, data[start:start+4096])

    def number(self, addr, value, width=4):
        self.g.put(addr, (value % (1 << (8*width))).to_bytes(width, "little"))

    def start(self):
        self.lua.execute(AUTO)
        if self.g.init:
            self.g.init()

    @property
    def c(self):
        return self.g.CBRRC

    def synthetic_pe(self):
        header = bytearray(4096)
        header[:2] = b"MZ"
        struct.pack_into("<I", header, 60, 0x80)
        # Spaced native instruction pages, read-only constants and writable virtual data.
        exec_sections = ((0x10000, 0x3000), (0x143000, 0x1000), (0x17D000, 0x1000),
                         (0x251000, 0x1000), (0x267000, 0x1000), (0x276000, 0x1000),
                         (0x2EE000, 0x1000), (0x2F3000, 0x4000))
        sections = [(r, n, 0x60000020) for r, n in exec_sections]
        sections += [(0x59E000, 4096, 0x40000040), (0x660000, 0x100000, 0xC0000040)]
        struct.pack_into("<4sHHI8xHH", header, 0x80, b"PE\0\0", 0x8664, len(sections), STAMP, 240, 2)
        struct.pack_into("<H", header, 0x98, 0x20B)
        struct.pack_into("<I", header, 0x98+32, 4096)
        struct.pack_into("<II", header, 0x98+56, 0x3532000, 4096)
        for i, (r, n, flags) in enumerate(sections):
            s = 0x188 + 40*i
            struct.pack_into("<II", header, s+8, n, r)
            struct.pack_into("<I", header, s+36, flags)
        self.map(BASE, bytes(header))
        for r, n in exec_sections:
            self.map(BASE+r, b"\xcc"*n)
        self.map(BASE+0x59E000, bytes(4096))
        self.number(BASE+0x59E75C, 4500)
        self.g.put(BASE+FN, PATTERN)
        for r, raw in {
            0x25120C:"48895c2408574883ec20", 0x25121D:"8bda488bf9", 0x251251:"8b1103d38911",
            0x251286:"488bcf", 0x2512B0:"48895c2408574883ec20448b09448bc2488bf9", 0x2512ED:"2bd94103d881fb84030000",
            0x251336:"418d14198917", 0x25136B:"488bcf",
            0x143A80:"4883ec28", 0x143AAB:"48895c2430488974243848897c2420428b1c018d4104420fb63400",
            0x143ACD:"498b8090100000488d88a03f00008b394080fe017416", 0x143AF9:"8919",
            0x2F3B10:"48895c2410488974241848897c2420554154415541564157", 0x2F6556:"488b8890100000",
            0x2F6563:"4881c1a03f00000101",
            0x2EE2E1:"488b88901000004881c140410000",
            0x267800:"488bc4488958104889701848897820554154415541564157",
        }.items():
            self.g.put(BASE+r, bytes.fromhex(raw))
        refs = [(r, "e8", FN) for r in CALLERS]
        refs += [(0x143AC6, "4c8b05", 0x667548), (0x17DBF5, "488b15", 0x667560),
                 (0x27671B, "663905", 0x68F8F4), (0x276729, "66390d", 0x68F8F8),
                 (0x276735, "4c8d05", 0x68F910), (0x2F655D, "8b05", 0x59E75C),
                 (0x2EE2EF, "e8", 0x267800)]
        for pc, hex_op, target in refs:
            op = bytes.fromhex(hex_op)
            self.g.put(BASE+pc, op + struct.pack("<i", target-pc-len(op)-4))
        return self

    def world(self):
        self.synthetic_pe()
        self.start()
        assert self.c.Status().enabled
        for addr, size in ((BASE+0x667000, 4096), (BASE+0x68F000, 8192),
                           (CHITIN, 8192), (NETWORK, 4096), (GAME, 0xA000)):
            self.map(addr, bytes(size))
        a = self.c.addresses
        self.number(a.chitin, CHITIN, 8)
        self.number(a.network, NETWORK, 8)
        self.number(CHITIN+0x1090, GAME, 8)
        self.number(a.serial, 1000, 2)
        self.number(GAME+0x6598+11*8, AREA, 8)
        return self

    def sprite(self, slot, generation, area=AREA):
        a = self.c.addresses
        addr = 0x400000000 + slot*0x6000
        self.map(addr, bytes(0x6000))
        self.number(a.maxSlot, slot, 2)
        self.number(a.slots+slot*16, generation, 2)
        self.number(a.slots+slot*16+8, addr, 8)
        self.number(addr+8, 0x31, 1)
        self.number(addr+0x18, area, 8)
        self.number(addr+0x48, slot*65536+generation)
        self.number(addr+0x58, 1, 1)
        self.set_fields(addr, (0, 0, 98, 100))
        return addr

    def set_fields(self, sprite, values):
        for (offset, width), value in zip(FIELDS, values, strict=True):
            self.number(sprite+offset, value, width)

    def fields(self, sprite):
        return tuple(int((self.g.EEex_Read16 if width == 2 else self.g.EEex_Read32)(sprite+offset))
                     for offset, width in FIELDS)

    def jump(self, old, d, origin=1, flag=1, timer=TIMER):
        new = (old+d) % 2**32
        self.number(TIMER, new)
        self.g.tracking = True
        try:
            return self.c.Commit(timer, origin, new if origin == 3 else d, old, d if origin == 4 else flag)
        finally:
            self.g.tracking = False


class StartupTests(unittest.TestCase):
    def refused(self, host, reason):
        host.start()
        host.start()
        self.assertEqual(len(host.g.logs), 1)
        self.assertTrue(host.g.logs[1].startswith(OFF), host.g.logs[1])
        self.assertIn(reason, host.g.logs[1])
        self.assertNotIn("\n", host.g.logs[1])
        self.assertTrue(host.g.protected)
        self.assertFalse(host.c.installed)

    def test_both_interpreters_start_and_load_only_once(self):
        for runtime in (Lua52, LuaJIT):
            with self.subTest(runtime=runtime):
                h = Host(runtime).synthetic_pe()
                h.start()
                h.start()
                self.assertTrue(h.c.Status().enabled, list(h.g.logs.values()))
                self.assertEqual((h.g.loads, h.g.queues, h.g.destroys, h.g.hooks, h.g.allocations), (1,)*5)
                self.assertTrue(h.g.protected)
                self.assertEqual(h.g.hookAddress, BASE+FN+15)
                self.assertEqual(h.g.EEex_ReadU32(BLOCK+8), 0x1234)
                self.assertEqual([h.g.EEex_ReadPtr(BLOCK+16+8*i) for i in range(4)],
                                 [BASE+r+5 for r in CALLERS])

    def test_loader_and_all_api_refusals(self):
        m = Host()
        m.lua.execute(CORE)
        required = list(m.c.requiredFunctions.values())
        for name in ["Infinity_DoFile", *required, "EEex_LuaCallReturnType", "EEex_LuaCallReturnType.Number"]:
            with self.subTest(missing=name):
                h = Host()
                h.lua.execute(name+"=nil")
                self.refused(h, name)
                self.assertEqual((h.g.allocations, h.g.hooks), (0, 0))
        for edit, reason in (("EEex_Active=false", "EEex is not active"),
                             ("Infinity_DoFile=function() end", "did not load"),
                             ("EEex_GameState_AddInitializedListener=function() error('queue failed') end", "queue failed")):
            with self.subTest(edit=edit):
                h = Host()
                h.lua.execute(edit)
                self.refused(h, reason)

    def test_pe_and_instruction_refusals_before_allocation(self):
        cases = [(0, b"ZM", "DOS"), (0x3C, struct.pack("<I", 0xFFFF), "PE offset"),
                 (0x80, b"PX", "x64"), (0x84, b"\x4c\x01", "x64"),
                 (0x86, b"\0\0", "section table"), (0x94, b"\xff\x7f", "section table"),
                 (0x98, b"\x0b\x01", "PE32+"), (0x88, bytes(4), "build"),
                 (0x98+56, bytes(4), "size"), (0x98+60, bytes(4), "headers"),
                 (0x188+8, b"\xff"*4, "bounds"), (0x188+40+12, b"\x00\x00\x01\x00", "bounds"),
                 (0x188+36, struct.pack("<I", 0x20000020), "unreadable"),
                 (FN, b"\xcc", "found 0"), (FN+15, b"\xe9", "found 0"),
                 (0x10060, PATTERN, "found 2"), (0x59E75C, bytes(4), "hour"),
                 (0x188+40*9+36, struct.pack("<I", 0x40000040), "data section"),
                 (0x188+40*9+8, struct.pack("<I", 0x31000), "data section"),
                 (0x2EE2EF+1, bytes(4), "toolbar refresh target"),
                 (0x267800, b"\xcc", "instruction")]
        for pc in (0x25120C, 0x251251, 0x2512B0, 0x25136B, 0x143A80, 0x143AC1, 0x143ADD,
                   0x2F3B10, 0x2F656A, 0x276735):
            cases.append((pc, b"\xcc", "instruction"))
        for pc in CALLERS:
            cases += [(pc, b"\xe9", "instruction"), (pc+1, bytes(4), "caller")]
        for pc, width in ((0x143AC6,3), (0x17DBF5,3), (0x27671B,3), (0x276729,3), (0x276735,3), (0x2F655D,2)):
            cases.append((pc+width, bytes(4), "reference"))
        for addr, data, reason in cases:
            with self.subTest(addr=hex(addr), reason=reason):
                h = Host().synthetic_pe()
                h.g.put(BASE+addr, data)
                self.refused(h, reason)
                self.assertEqual((h.g.allocations, h.g.hooks), (0, 0))

    def test_pattern_must_be_wholly_inside_one_executable_section(self):
        h = Host().synthetic_pe()
        h.g.put(BASE+FN, bytes(31))
        h.g.put(BASE+0x12FF0, PATTERN[:16])
        h.g.put(BASE+0x143000, PATTERN[16:])
        h.g.put(BASE+0x59E000, PATTERN)
        self.refused(h, "found 0")

    def test_allocation_compilation_and_publication_failures(self):
        for edit, reason, calls in (
            ("EEex_Malloc=function() return 0 end", "allocate", 0),
            ("EEex_JITNear=function() error('assembly failed') end", "assembly failed", 0),
            ("EEex_JITNear=function() return 0 end", "assemble", 0),
            ("EEex_ExposeToLua=function() end", "capture main thread", 0),
            ("EEex_GenLuaCall=function() error('arguments') end", "arguments", 0),
            ("EEex_HookBeforeRestoreWithLabels=function() error('hook failed') end", "hook failed", 0),
            ("EEex_HookBeforeRestoreWithLabels=function() end", "install", 0),
            ("local hook=EEex_HookBeforeRestoreWithLabels; EEex_HookBeforeRestoreWithLabels=function(...) "
             "hook(...); error('partial publication') end", "partial publication", 1),
        ):
            with self.subTest(edit=edit):
                h = Host().synthetic_pe()
                h.lua.execute(edit)
                self.refused(h, reason)
                self.assertEqual(h.g.hooks, calls)
                self.assertEqual(h.g.read(BASE+FN+15, 7).encode("latin-1"), PATTERN[15:22])
                self.assertIsNone(h.c.block)
                self.assertEqual(h.g.frees, h.g.allocations)
        h = Host().synthetic_pe()
        h.lua.execute("EEex_DisableCodeProtection=function() protected=false; put(base+0x12003,'X') end")
        self.refused(h, "window changed")
        self.assertEqual(h.g.read(BASE+FN+15, 1), "X")
        self.assertEqual(h.g.hooks, 0)

    def test_gate_layout_call_abi_and_native_exits(self):
        h = Host().synthetic_pe()
        h.start()
        body = h.g.gate
        regs = "rax rdx rcx rbx rbp rsi rdi r8 r9 r10 r11 r12 r13 r14 r15".split()
        lines = [s.strip() for s in body.splitlines()]
        self.assertEqual([s for s in lines if s.startswith("push")], ["pushfq", *["push "+r for r in regs]])
        self.assertEqual([s for s in lines if s.startswith("pop")], ["pop "+r for r in reversed(regs)]+["popfq"])
        self.assertIn("mov rax, qword ptr [rsp+64]", body)
        for i in range(4):
            self.assertIn(f"cmp rax, qword ptr [rdx+{16+8*i}]\nje cbr_rc_origin{i+1}", body)
        self.assertIn("cmp sil, 1\njne cbr_rc_fast_exit", body)
        self.assertIn("mov ecx, dword ptr gs:[0x48]\ncmp ecx, dword ptr [rdx+8]\nje cbr_rc_main\n"
                      "lock inc dword ptr [rdx+12]\njmp cbr_rc_restore_rcx", body)
        self.assertLess(body.index("cbr_rc_main:"), body.index("#MAKE_SHADOW_SPACE(72)"))
        for offset in (32,40):
            self.assertLess(body.index(f"mov qword ptr ss:[rsp+{offset}], 0"), body.index("; test Lua call"))
        self.assertIn("mov eax, dword ptr gs:[0x48]", h.g.helper)
        self.assertIn(f"mov rdx, {BLOCK}", h.g.helper)
        self.assertIn("mov dword ptr [rdx+8], eax", h.g.helper)
        self.assertIn("xor eax, eax", h.g.helper)
        for reg, src in (("r12","qword ptr [rsp+192]"), ("r13d","eax"), ("r14d","ebx"),
                         ("r15d","edi"), ("ebp","dword ptr [rsp+208]")):
            self.assertIn(f"mov {reg}, {src}", body)
        self.assertIn("movzx ebp, sil", body)
        for i, reg in enumerate(("r12","r13","r14","r15","rbp")):
            self.assertIn(f"mov qword ptr ss:[rsp+#$(1)], {reg} #ENDL\n{64+8*i}", body)
        self.assertIn("call_error: #ENDL mov rax, -2", body)
        self.assertIn(f"cmp rax, -2\njne cbr_rc_done\nmov rdx, {BLOCK}\n"
                      "mov dword ptr [rdx], 0\ninc dword ptr [rdx+4]", body)
        for i in range(6):
            self.assertIn(f"movdqu xmmword ptr [rsp+{16*i}], xmm{i}", lines)
            self.assertIn(f"movdqu xmm{i}, xmmword ptr [rsp+{16*i}]", lines)
        for amount in (128,96,-96,-128):
            self.assertIn(f"#STACK_MOD({amount})", lines)
        self.assertIn("#DESTROY_SHADOW_SPACE", body)


def simulate(old, delta, speed, actor_id, hasted, values):
    """Run each virtual frame independently, including the zero-aura exception."""
    cast, attack, hide, poll = values
    for frame in range(2*old+1, 2*(old+delta)+1):
        if (frame & speed) != (actor_id & speed):
            continue
        if cast >= 0 and (not hasted or cast == 0 or (frame & 1) == (actor_id & 1)):
            cast = -1 if cast+1 >= 100 else cast+1
        if attack >= 0:
            attack = -2 if attack+1 >= 100 else attack+1
        if hide > 0:
            hide -= 1
        if poll > 0:
            poll -= 1
    return cast, attack, hide, poll


class RecoveryTests(unittest.TestCase):
    def test_all_four_fields_against_single_frames_in_both_luas(self):
        for runtime in (Lua52, LuaJIT):
            h = Host(runtime).world()
            s = h.sprite(0, 0)
            for actor_id in (0, 1):
                h.number(h.c.addresses.slots, actor_id, 2)
                h.number(s+0x48, actor_id)
                for mask, hasted in ((0, True), (1, False), (3, False), (0b1010, True), (0xFE, False)):
                    h.number(s+0x58, mask, 1)
                    h.number(s+0x1DC8, 0x8000 if hasted else 0)
                    for old in (2, 0xFFFFFFFD):
                        for delta in DELTAS:
                            for cast in (0, 40):
                                with self.subTest(lua=runtime, id=actor_id, mask=mask, old=old, d=delta, c=cast):
                                    before = (cast, 9, 173, 100000)
                                    h.set_fields(s, before)
                                    h.jump(old, delta)
                                    self.assertEqual(h.fields(s), simulate(old, delta, mask, actor_id, hasted, before))
                            h.g.writes = h.lua.table()

    def test_every_byte_mask_and_large_signed_limit(self):
        h = Host()
        h.lua.execute(CORE)
        for mask in range(256):
            for actor_id, old, d in ((0x1092, 37, 1), (0x19B, 253, 147)):
                frames = [f for f in range(2*old+1, 2*(old+d)+1) if (f & mask) == (actor_id & mask)]
                actual = h.c.Updates(old, d, mask, actor_id)
                if not frames and isinstance(actual, tuple):
                    actual = actual[0]
                self.assertEqual(actual, (len(frames), frames[0] % 2) if frames else 0, mask)
        h = Host().world()
        s = h.sprite(0, 2)
        h.number(s+0x58, 0, 1)
        h.set_fields(s, (0, 0, 0x7FFFFFFF, 0x7FFFFFFF))
        h.jump(0xFFFFFF00, 0x7FFFFFFF)
        self.assertEqual(h.fields(s), (-1, -2, 0, 0))

    def test_origin_filters_timer_identity_and_forward_wrap(self):
        h = Host().world()
        s = h.sprite(0, 2)
        before = h.fields(s)
        for origin, delta, force, timer in ((0,15,1,TIMER), (5,15,1,TIMER), (3,15,0,TIMER),
                                            (3,15,2,TIMER), (4,4499,1,TIMER), (1,915,1,TIMER+4),
                                            (1,-15,1,TIMER), (2,0x80000000,1,TIMER),
                                            (3,-1,1,TIMER), (3,0,1,TIMER), (1,0,1,TIMER)):
            h.jump(7, delta, origin, force, timer)
            self.assertEqual(h.fields(s), before)
        self.assertEqual((len(h.g.writes), h.c.commits), (0,0))
        for origin in (1,2,3,4):
            d = 4500 if origin == 4 else 15
            h.set_fields(s, before)
            h.jump(0xFFFFFFFC, d, origin)
            self.assertEqual(h.fields(s), simulate(0xFFFFFFFC, d, 1, 2, False, before))
        self.assertEqual(h.c.commits, 4)

    def test_chained_jumps_compose_before_a_native_frame(self):
        h = Host().world()
        s = h.sprite(0, 1)
        for mask, state in ((0,0x8000), (1,0), (3,0), (0xA,0x8000)):
            h.number(s+0x58, mask, 1)
            h.number(s+0x1DC8, state)
            before = (0, 0, 400, 500)
            h.set_fields(s, before)
            old = 0xFFFFFFF3
            for origin, d in ((1,1), (2,15), (3,1)):
                h.jump(old, d, origin)
                old = (old+d) % 2**32
            self.assertEqual(h.fields(s), simulate(0xFFFFFFF3, 17, mask, 1, bool(state), before))

    def test_cast_item_attack_and_armed_sentinels(self):
        h = Host().world()
        s = h.sprite(0, 7)
        for act, in_cast, started, damage, swing, cast, attack, want in (
            (31,1,0,0,0,18,20,(18,-2)), (95,1,1,0,0,18,20,(18,-2)),
            (34,0,1,0,0,18,20,(18,-2)), (97,0,1,0,0,18,20,(18,-2)),
            (34,0,0,0,0,18,20,(-1,-2)), (31,0,1,0,0,18,20,(-1,-2)),
            (0,0,0,1,0,18,20,(-1,20)), (0,0,0,0,1,18,20,(-1,20)),
            (0,0,0,0,0,-1,-1,(-1,-1)), (0,0,0,0,0,-3,-2,(-3,-2)),
            *((act,0,0,0,0,18,20,(-1,20)) for act in ATTACKS),
        ):
            with self.subTest(act=act, flags=(in_cast,started,damage,swing)):
                for off,val,width in ((0x3F8,act,2),(0x4998,in_cast,4),(0x4994,started,4),
                                      (0x4BA8,damage,1),(0x4CA0,swing,4),(0x4BA9,255,1)):
                    h.number(s+off, val, width)
                h.set_fields(s, (cast, attack, -5, 0))
                h.jump(12, 4500)
                self.assertEqual(h.fields(s), (*want, -5, 0))

    def test_only_four_owned_fields_change(self):
        h = Host().world()
        s = h.sprite(0, 1)
        for offset in (0x3A8, 0x4E60, 0x4E4C, 0x503C, 0x49B0, 0x4A00, 0x4A08):
            h.number(s+offset, 0x789ABCDE)
        before = bytearray(h.g.read(s,0x6000).encode("latin-1"))
        h.jump(50, 15)
        writes = [(row[1]-s, row[2]) for row in h.g.writes.values()]
        self.assertCountEqual(writes, FIELDS)
        for (off,width), value in zip(FIELDS, (15,15,83,85)):
            before[off:off+width] = value.to_bytes(width, "little")
        self.assertEqual(h.g.read(s,0x6000).encode("latin-1"), before)

    def test_time_stop_and_derived_selector(self):
        h = Host().world()
        sprites = [h.sprite(i,i) for i in range(5)]
        h.number(GAME+0x9690, 25)
        h.number(GAME+0x9694, 65537)
        for i, s in enumerate(sprites):
            h.number(s+0x4EA4, i%2)
            selected, other = (0x1120,0x1DC8) if i%2 else (0x1DC8,0x1120)
            h.number(s+selected+0x2D8, int(i in (2,3)))
            h.number(s+other+0x2D8, int(i in (0,4)))
            h.number(s+0x58, 0, 1)
            h.number(s+selected, 0x8000)
        h.jump(7, 15)
        for i, s in enumerate(sprites):
            before = (0,0,98,100)
            want = simulate(7,15,0,i,True,before) if i in (1,2,3) else before
            self.assertEqual(h.fields(s), want)
        self.assertEqual(h.c.actors, 3)

    def test_registry_slot_eligibility_party_dedup_and_network_authority(self):
        h = Host().world()
        a = h.c.addresses
        sprites = [h.sprite(i,i, AREA if i != 1 else 0) for i in range(12)]
        h.number(GAME+0x6630, 2, 2)
        h.number(GAME+0x6600, 0)              # party + loaded area, only once
        h.number(GAME+0x6604, 65537)          # party in transit, area is null
        h.number(GAME+0x6608, 11*65536+11)    # beyond party count
        h.number(NETWORK+0x2C9, 2, 1)
        h.number(NETWORK+0x374, 0)
        h.number(a.slots+3*16, -1, 2)
        h.number(a.slots+4*16+8, -1, 8)       # pointer tombstone, live generation
        h.number(a.slots+5*16+8, 0, 8)
        h.number(a.slots+6*16, 1000, 2)       # exclusive serial bound
        h.number(sprites[7]+0x48, 7*65536+6)  # slot reused with stale packed ID
        h.number(sprites[8]+8, 0x30, 1)
        h.number(sprites[9]+0x4EC0, 1)
        h.number(sprites[10]+0x50, 123)
        h.number(sprites[11]+0x18, AREA+0x4000, 8)
        h.jump(123, 15)
        self.assertEqual([h.fields(s)[0] for s in sprites], [15,15,15]+[0]*9)
        self.assertEqual(h.c.actors, 3)
        h.number(NETWORK+0x2C9, 0, 1)
        h.jump(138, 15)
        self.assertEqual(h.fields(sprites[10])[0], 15)

    def test_registry_extremes_and_absent_singletons(self):
        h = Host().world()
        s = h.sprite(0, 0)
        a = h.c.addresses
        for addr,width,invalid,restore in (
            (a.chitin,8,0,CHITIN), (CHITIN+0x1090,8,0,GAME), (a.network,8,0,NETWORK),
            (a.maxSlot,2,-1,0), (a.maxSlot,2,0x7FFF,0), (a.serial,2,-1,1000), (a.serial,2,0,1000),
        ):
            h.number(addr, invalid, width)
            h.jump(15, 15)
            self.assertEqual(h.fields(s), (0,0,98,100))
            h.number(addr, restore, width)
        h.map(int(a.slots), b"\xff"*(16*0x7FFF))
        top = h.sprite(0x7FFE, 999)
        h.jump(10, 15)
        self.assertEqual(h.fields(top), (15,15,83,85))
        self.assertEqual(h.c.actors, 1)

    def test_session_teardown_and_guarded_lua_error(self):
        h = Host().world()
        s = h.sprite(0, 0)
        h.jump(15, 15)
        h.lua.execute("EEex_Write32(block+4,1); EEex_Write32(block+12,7); destroy()")
        status = h.c.Status()
        self.assertEqual((status.actors,status.commits,status.lua_errors,status.off_thread_skips,status.sessions),
                         (0,0,0,0,1))
        self.assertTrue(status.enabled)
        self.assertEqual(h.fields(s), (15,15,83,85))
        h.lua.execute("CBRRC.Commit=function() error('callback failure',0) end")
        self.assertEqual(h.g.CBRRC_Commit(0,1,15,0,0), -2)
        self.assertEqual(h.g.logs[2], OFF+"callback failure")
        h.number(BLOCK, 0)
        h.g.destroy()
        self.assertFalse(h.c.Status().enabled)


STEAM = Path(os.environ.get("CBR_STEAM_COMMON", r"C:\Program Files (x86)\Steam\steamapps\common"))
BG = STEAM / "Baldur's Gate Enhanced Edition/Baldur.exe"
BG2 = STEAM / "Baldur's Gate II Enhanced Edition/Baldur.exe"
IWD = STEAM / "Icewind Dale Enhanced Edition/icewind.exe"


class PausedToolbarTests(unittest.TestCase):
    def test_first_draw_click_and_hotkey_each_refresh_once(self):
        for runtime in (Lua52, LuaJIT):
            for entry in ("buttonArray:GetButtonEnabled(5)", "buttonArray:OnLButtonPressed(5)", "keyPressed()"):
                with self.subTest(runtime=runtime, entry=entry):
                    h = Host(runtime).world()
                    s = h.sprite(0, 7)
                    h.lua.execute("selected={12,7}; insideRefresh=function() buttonArray:OnLButtonPressed(2) end")
                    h.jump(100, 915)
                    self.assertEqual(h.fields(s)[2], 0)
                    self.assertIsNone(h.g.refreshed)
                    h.lua.execute(entry)
                    self.assertEqual(h.lua.eval("buttonArray:OnLButtonPressed(5)"), (5, 1))
                    self.assertEqual(h.lua.eval("buttonArray:GetButtonEnabled(3)"), (3, True))
                    self.assertEqual(h.g.refreshed, 1)

    def test_mark_requires_selected_positive_to_zero(self):
        h = Host().world()
        s = h.sprite(0, 7)
        for selected, hide, delta in ((7, 3, 1), (7, 0, 915), (8, 3, 915), (7, -1, 915)):
            h.lua.execute(f"selected={{{selected}}}")
            h.set_fields(s, (0, 0, hide, 88))
            h.jump(100, delta)
            h.lua.execute("buttonArray:GetButtonEnabled(5)")
        self.assertIsNone(h.g.refreshed)

    def test_reacquires_world_bar_and_selection_and_respects_native_completion(self):
        h = Host().world()
        s = h.sprite(0, 7)
        h.lua.execute("selected={7}")
        h.jump(100, 915)
        h.lua.execute("oldBar=buttonArray; buttonArray=newBar(); menuLoaded(); menuLoaded(); "
                      "oldBar:GetButtonEnabled(5); activeScreen={}; buttonArray:GetButtonEnabled(5); "
                      "activeScreen=worldScreen; selected={}; keyPressed(); "
                      "selected={7}; wrongThread=true; buttonArray:OnLButtonPressed(5)")
        self.assertIsNone(h.g.refreshed)
        h.lua.execute("wrongThread=false; buttonArray:OnLButtonPressed(5)")
        self.assertEqual(h.g.refreshed, 1)
        for completed in ("updated()", "destroy()"):
            h.set_fields(s, (0, 0, 90, 88))
            h.jump(100, 915)
            h.lua.execute(completed+"; buttonArray:GetButtonEnabled(5)")
            self.assertEqual(h.g.refreshed, 1)

    def test_commit_inside_refresh_survives_the_old_completion(self):
        h = Host().world()
        s = h.sprite(0, 7)
        h.lua.execute("selected={7}")
        h.jump(100, 915)
        h.lua.execute(f"insideRefresh=function() insideRefresh=nil; EEex_Write32({s}+0x4E70,90); "
                      f"CBRRC.Commit({TIMER},1,915,0,0) end; buttonArray:GetButtonEnabled(5)")
        self.assertEqual(h.g.refreshed, 1)
        h.lua.execute("buttonArray:GetButtonEnabled(5); buttonArray:GetButtonEnabled(5)")
        self.assertEqual(h.g.refreshed, 2)


class SteamImageTests(unittest.TestCase):
    def check_file(self, path, stamp, expected_size, code, data):
        raw = path.read_bytes()
        nt, = struct.unpack_from("<I", raw, 60)
        count, = struct.unpack_from("<H", raw, nt+6)
        opt, = struct.unpack_from("<H", raw, nt+20)
        self.assertEqual(struct.unpack_from("<I", raw, nt+8)[0], stamp)
        self.assertEqual(struct.unpack_from("<I", raw, nt+24+56)[0], expected_size)
        h = Host()
        h.map(BASE, raw[:struct.unpack_from("<I", raw, nt+24+60)[0]])
        for i in range(count):
            virtual, rva, raw_size, offset = struct.unpack_from("<4I", raw, nt+24+opt+40*i+8)
            h.map(BASE+rva, raw[offset:offset+min(virtual,raw_size)])
        h.start()
        self.assertTrue(h.c.Status().enabled, list(h.g.logs.values()))
        a = h.c.addresses
        self.assertEqual((a.fn-BASE,a.site-BASE), (0x2513A0+code,0x2513AF+code))
        self.assertEqual([a.returns[i]-BASE for i in range(1,5)], [r+code+5 for r in CALLERS])
        self.assertEqual([a[key]-BASE-data for key in ("chitin","network","maxSlot","serial","slots")],
                         [0x667548,0x667560,0x68F8F4,0x68F8F8,0x68F910])
        # Embedded Lua takes the full x64 integer and reads both outgoing pcallk stack arguments.
        for pc, pattern in ((0xD5A97, "f2480f2ac2"), (0xD6717, "488b8424b8000000"),
                            (0xD6750, "8b8424b0000000")):
            self.assertEqual(h.g.read(BASE+pc,len(pattern)//2).encode("latin-1"), bytes.fromhex(pattern))
        # Independent machine operands for the selector, lifetime, field widths and authority.
        for pc, pattern in ((0x2765A3,"8b848100660000"), (0x288466,"440fbfbf30660000"),
                            (0x2EC291,"483b9cc198650000"), (0x17DC01,"80bac902000001750b8b4150398274030000"),
                            (0x341FF2,"884608"), (0x26BAB9,"b8ff7f0000")):
            self.assertEqual(h.g.read(BASE+pc+code,len(pattern)//2).encode("latin-1"), bytes.fromhex(pattern))
        sprite_shift = 0x30 if code else 0
        for pc, pattern in ((0x344E09,"488b4b18"), (0x353165,"440fb651584c8bf1448b5948"),
                            (0x396091,"0fb787f8030000"), (0x392665,"440fb78190490000"),
                            (0x3B39DC,"89af94490000"), (0x3926D9,"83bf9849000000"),
                            (0x3926EA,"0fb7879a4b0000"), (0x3B39E8,"4088afa84b0000"),
                            (0x3B39C1,"89afa04c0000"), (0x344AB6,"8b83704e0000"), (0x3BE35A,"8b8140500000"),
                            (0x37A417,"c781c04e000001000000"), (0x37AC8F,"4533f6"), (0x37AD43,"4489b3c04e0000"),
                            (0x3AB5BA,"83ba909600000074148b4648398294960000740983b9d802000000"),
                            (0x3ABA83,"83bea44e000000b8f8130000baa02000000f44c2833c3000"),
                            (0x392678,"41b92011000041bac81d0000"), (0x392698,"f7040800800000")):
            self.assertEqual(h.g.read(BASE+pc+sprite_shift,len(pattern)//2).encode("latin-1"),
                             bytes.fromhex(pattern), hex(pc))

    @unittest.skipUnless(BG.is_file(), "Steam BG:EE executable absent")
    def test_bgee(self):
        self.check_file(BG, 0x6A18D6DC, 0x3524000, 0, 0)

    @unittest.skipUnless(BG2.is_file(), "Steam BG2:EE executable absent")
    def test_bg2ee(self):
        self.check_file(BG2, STAMP, 0x3532000, 0, 0)

    @unittest.skipUnless(IWD.is_file(), "Steam IWD:EE executable absent")
    def test_iwdee(self):
        self.check_file(IWD, 0x6A18D7E9, 0x3563000, 0x80, 0x6000)
