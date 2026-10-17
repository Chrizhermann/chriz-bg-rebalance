"""Execute actual generated post-base-copy observer, including decode exclusion."""
from pathlib import Path
import struct
import tempfile
import unittest

from tests.test_potion_generated_trampoline import GeneratedMachine, EEEX, LIBS, ML64
from tests.test_potion_cast_generated_trampoline import native_replay
from tests.test_potion_copy_transport_preprocessor import CopyHarness, read_image, SITE, BASE

if EEEX and LIBS and ML64:
    import unicorn
    from unicorn import x86_const as x86


@unittest.skipUnless(EEEX and LIBS and ML64,
                     "optional: EEEX_LUA_DIR, EEEX_POTION_PYLIBS and EEEX_POTION_ML64")
class CopyGeneratedTrampolineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = Path(tempfile.mkdtemp(prefix="cbr-potion-copy-generated-"))
        cls.image = read_image()

    def execute(self, caller, source, error=False):
        h = CopyHarness(self.image, watchdog=True)
        h.install()
        def initialize(m):
            m.initial_rsp = m.STACK + 0x20000
            m.write("RSP", m.initial_rsp)
            m.uc.mem_write(m.initial_rsp, bytes(range(128)))
            m.write("RDI", m.DATA + 0x400)
            m.write("RSI", m.DATA + source)
            m.uc.mem_write(m.initial_rsp + 0x38, struct.pack("<Q", BASE + caller))
        m = GeneratedMachine(h, self.directory, 2, {BASE + SITE + 5},
                             lua_error=error, initializer=initialize)
        state, stack = native_replay(m, bytes(self.image[SITE:SITE + 5]))
        self.assertEqual(state, m.snapshot())
        self.assertEqual(stack, bytes(m.uc.mem_read(m.initial_rsp, 128)))
        self.assertEqual(1, m.watchdog_checks)
        return m

    def test_live_copy_callback_arguments_and_lua_error_preserve_native_state(self):
        for caller in (0x1CE243, 0x1D3631, 0x1DA7A3):  # AC, HP and lockpicking actual Copy callers
            for error in (False, True):
                with self.subTest(caller=hex(caller), error=error):
                    m = self.execute(caller, 0x108, error)
                    self.assertEqual([m.DATA + 0x400, m.DATA + 0x100],
                                     [value for _, value in m.lua_arguments])

    def test_decode_saved_buffer_and_known_live_base_both_skip_callback(self):
        for source in (0x1000, 0x108):
            with self.subTest(source=hex(source)):
                m = self.execute(0x1E2DB1, source)
                self.assertEqual([], m.lua_arguments)
                self.assertEqual([], m.lua_calls)


if __name__ == "__main__":
    unittest.main()
