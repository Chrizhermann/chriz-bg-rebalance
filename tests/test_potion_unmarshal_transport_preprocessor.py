"""Actual EEex preprocessing for the inert caller-side unmarshal observers."""
import unittest

from tests.test_potion_hook_preprocessor import EEEX, ROOT
from tests.test_potion_transport_preprocessor import TransportHarness, read_image, inspect_paths, BASE

MODULE = ROOT / "research/prototypes/potion-admission/CBRPQUnmarshalTransport.lua"
SITES = (0x37AA8B, 0x37AA97, 0x22BCA1, 0x22BCAB)
SIZES = (7, 7, 5, 12)
RANGES = ((0x37AA51, 0x37AA92), (0x37AA97, 0x37AA9E),
          (0x22BC74, 0x22BCAB), (0x22BCAB, 0x22BCB7))


class UnmarshalHarness(TransportHarness):
    def __init__(self, image, watchdog=True):
        super().__init__(image, watchdog=watchdog)
        self.lua.execute("function CBRPQUnmarshal_enter(...) end; function CBRPQUnmarshal_leave(...) end")
        self.config = self.lua.table_from({"callbacks": self.lua.table_from(
            {key: "CBRPQUnmarshal_" + key for key in ("enter", "leave")})})
        self.hook = self.lua.execute(MODULE.read_text(encoding="utf-8"))


@unittest.skipUnless(EEEX, "optional: set EEEX_LUA_DIR for actual EEex preprocessing")
class UnmarshalTransportPreprocessorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = read_image()

    def test_validate_inert_collision_guards_and_stock_wrapper_untouched(self):
        h = UnmarshalHarness(self.image)
        h.validate()
        self.assertEqual([], h.patches)
        self.assertEqual([], h.protection)
        for site in set(SITES + tuple(s for start, end in RANGES for s in (start, end - 1))):
            with self.subTest(site=hex(site)):
                h = UnmarshalHarness(self.image)
                h.image[site] ^= 1
                with self.assertRaisesRegex(Exception, "unsupported/previously patched site"):
                    h.install()
                self.assertEqual([], h.patches)
                self.assertEqual([], h.protection)
        h = UnmarshalHarness(self.image)
        # Existing EEex call wrapper and C++ override entry are deliberately not
        # authenticated/replaced by this independent caller observer.
        h.image[0x37AA92:0x37AA97] = b"\xcc" * 5
        h.image[0x1E88E0:0x1E88E5] = b"\xcc" * 5
        h.install()
        self.assertEqual([BASE + s for s in SITES], [p[0] for p in h.patches])
        for call in (0x37AA92, 0x22BCA6):
            self.assertTrue(all(not (s <= call < s + n) for s, n in zip(SITES, SIZES)))

    def test_generation_balances_all_paths_without_integrity_exemptions(self):
        for watchdog in (False, True):
            h = UnmarshalHarness(self.image, watchdog=watchdog)
            h.install()
            offset = 2 if watchdog else 0
            self.assertEqual(4 + offset, len(h.assemblies))
            self.assertEqual([], h.warnings)
            for i, (text, state) in enumerate(h.assemblies[offset:]):
                exits, _, indirect = inspect_paths(text, 0, set())
                self.assertEqual({BASE + SITES[i] + SIZES[i]}, exits)
                self.assertFalse(indirect)
                self.assertEqual(0, state.curStackTop)
                self.assertEqual(0, state.shadowSpaceStackTop)
            if watchdog:
                self.assertEqual([0] * 4, [a[2] for a in h.watchdog_metadata if len(a) == 3])

    def test_missing_callback_watchdog_and_no_double_arm(self):
        h = UnmarshalHarness(self.image)
        with self.assertRaisesRegex(Exception, "preservation helper required"):
            h.hook.install(h.lua.globals(), h.config)
        h.config.callbacks.leave = "AbsentUnmarshalCallback"
        with self.assertRaisesRegex(Exception, "callback must exist"):
            h.install()
        self.assertEqual([], h.patches)
        h = UnmarshalHarness(self.image)
        h.install()
        for action in (h.validate, h.install):
            with self.assertRaisesRegex(Exception, "already attempted"):
                action()
        self.assertEqual(4, len(h.patches))

    def test_partial_failure_cleanup_and_no_retry(self):
        h = UnmarshalHarness(self.image)
        original = h.lua.globals().EEex_HookIntegrityWatchdog_HookEnter
        capture = h.capture_at
        def fail(address, assembly):
            if len(h.patches) == 1:
                raise RuntimeError("unmarshal patch failure")
            capture(address, assembly)
        h.lua.globals().EEex_JITAt = fail
        with self.assertRaisesRegex(Exception, "unmarshal patch failure"):
            h.install()
        self.assertTrue(h.hook.failed)
        same = h.lua.eval("function(a,b) return rawequal(a,b) end")
        self.assertTrue(same(original, h.lua.globals().EEex_HookIntegrityWatchdog_HookEnter))
        self.assertEqual(["disable", "enable"], h.protection)
        with self.assertRaisesRegex(Exception, "already attempted"):
            h.install()


if __name__ == "__main__":
    unittest.main()
