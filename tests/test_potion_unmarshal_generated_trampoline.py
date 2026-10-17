"""Execute generated observer instructions and native Unmarshal argument setup."""
from pathlib import Path
import struct
import tempfile
import unittest

from tests.test_potion_generated_trampoline import GeneratedMachine, EEEX, LIBS, ML64
from tests.test_potion_cast_generated_trampoline import native_replay
from tests.test_potion_unmarshal_transport_preprocessor import UnmarshalHarness, read_image, SITES, SIZES, BASE

if EEEX and LIBS and ML64:
    import unicorn
    from unicorn import x86_const as x86


@unittest.skipUnless(EEEX and LIBS and ML64,
                     "optional: EEEX_LUA_DIR, EEEX_POTION_PYLIBS and EEEX_POTION_ML64")
class UnmarshalGeneratedTrampolineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = Path(tempfile.mkdtemp(prefix="cbr-potion-unmarshal-generated-"))
        cls.image = read_image()

    def execute(self, index, version, error=False):
        h = UnmarshalHarness(self.image, watchdog=True)
        h.install()
        def initialize(m):
            m.initial_rsp = m.STACK + 0x20000
            m.write("RSP", m.initial_rsp)
            m.uc.mem_write(m.initial_rsp, bytes(range(128)))
            m.write("RBX", m.DATA + 0x100)
            m.write("RDI", m.DATA + 0x200)
            m.write("RCX", m.DATA + 0x700)
            m.write("RDX", m.DATA + 0x1000)
            m.write("R8", 0x1234567800000528)  # native DWORD, not whole qword
            m.write("R9", m.DATA + 0x100 if index < 2 else 0)
            m.uc.mem_write(m.initial_rsp + 0x20, struct.pack("<Q", 0x8765432112345600 | version))
            m.uc.mem_write(m.DATA + 0x100 + 0x56A, b"\x34\x12")
            m.uc.mem_write(m.DATA + 0x200 + 0x1B, b"\x71")
        m = GeneratedMachine(h, self.directory, index + 2, {BASE + SITES[index] + SIZES[index]},
                             lua_error=error, initializer=initialize)
        expected, stack = native_replay(m, bytes(self.image[SITES[index]:SITES[index] + SIZES[index]]))
        self.assertEqual(expected, m.snapshot())
        self.assertEqual(stack, bytes(m.uc.mem_read(m.initial_rsp, 128)))
        self.assertEqual(1, m.watchdog_checks)
        values = [v for _, v in m.lua_arguments]
        if index == 0:
            self.assertEqual([m.initial_rsp, m.DATA + 0x4B00, m.DATA + 0x1000, 0x528,
                              m.DATA + 0x100, version], values)
        elif index == 2:
            self.assertEqual([m.initial_rsp, m.DATA + 0x700, m.DATA + 0x1000, 0x528, 0, 1], values)
        else:
            self.assertEqual([m.initial_rsp], values)

    def test_every_generated_site_preserves_native_state_arguments_and_error_path(self):
        for index in range(4):
            for version in (0, 1):
                for error in (False, True):
                    with self.subTest(site=hex(SITES[index]), version=version, error=error):
                        self.execute(index, version, error)

    def test_executable_direct_call_inventory_is_sprite_and_projectile_only(self):
        pe = struct.unpack_from("<I", self.image, 0x3C)[0]
        count = struct.unpack_from("<H", self.image, pe + 6)[0]
        optional_size = struct.unpack_from("<H", self.image, pe + 20)[0]
        calls = []
        for i in range(count):
            section = pe + 24 + optional_size + 40 * i
            virtual_size, rva = struct.unpack_from("<II", self.image, section + 8)
            flags = struct.unpack_from("<I", self.image, section + 36)[0]
            if not flags & 0x20000000:
                continue
            at = self.image.find(b"\xe8", rva, rva + virtual_size)
            while at >= 0:
                if at + 5 + struct.unpack_from("<i", self.image, at + 1)[0] == 0x1E88E0:
                    calls.append(at)
                at = self.image.find(b"\xe8", at + 1, rva + virtual_size)
        self.assertEqual([0x22BCA6, 0x37AA92], calls)
        self.assertEqual(-1, self.image.find(struct.pack("<Q", BASE + 0x1E88E0)))

    def test_actual_native_argument_setup_and_original_call_destinations(self):
        for kind in ("sprite", "projectile"):
            for version in (0, 1, 7):
                with self.subTest(kind=kind, version=version):
                    u = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_64)
                    u.mem_map(BASE, (len(self.image) + 4095) & ~4095)
                    u.mem_write(BASE, bytes(self.image))
                    memory, stack = 0x200000000, 0x300000000
                    u.mem_map(memory, 0x10000)
                    u.mem_map(stack, 0x1000)
                    rsp, sprite, source, area, header = stack + 0x800, memory, memory + 0x6000, memory + 0x8000, memory + 0x9000
                    u.reg_write(x86.UC_X86_REG_RSP, rsp)
                    u.reg_write(x86.UC_X86_REG_RBX, sprite if kind == "sprite" else area)
                    u.reg_write(x86.UC_X86_REG_R12, source)
                    u.reg_write(x86.UC_X86_REG_RBP, source + 0x300)
                    u.reg_write(x86.UC_X86_REG_R14, 0x528)
                    u.reg_write(x86.UC_X86_REG_RDI, header)
                    u.mem_write(sprite + 0x58B, bytes([version]))
                    u.mem_write(source + 0x2C4, struct.pack("<II", 0x300, 5))
                    start, call = (0x37AA51, 0x37AA92) if kind == "sprite" else (0x22BC74, 0x22BCA6)
                    u.emu_start(BASE + start, BASE + call, count=100)
                    got = [u.reg_read(r) for r in (x86.UC_X86_REG_RCX, x86.UC_X86_REG_RDX,
                                                  x86.UC_X86_REG_R8, x86.UC_X86_REG_R9)]
                    got.append(u.mem_read(rsp + 0x20, 1)[0])
                    expected = ([sprite + 0x4A00, source + 0x300, (0x108 if version else 0x30) * 5,
                                 sprite, int(bool(version))] if kind == "sprite" else
                                [area + 0x78, source + 0x300, 0x528, 0, 1])
                    self.assertEqual(expected, got)
                    self.assertEqual(0xE8, self.image[call])
                    self.assertEqual(0x1E88E0, call + 5 + struct.unpack_from("<i", self.image, call + 1)[0])


if __name__ == "__main__":
    unittest.main()
