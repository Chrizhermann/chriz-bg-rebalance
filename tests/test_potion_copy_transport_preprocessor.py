"""Optional real EEex preprocessing of the inert post-base-copy observer."""
import unittest

from tests.test_potion_hook_preprocessor import EEEX, ROOT
from tests.test_potion_transport_preprocessor import TransportHarness, read_image, inspect_paths, BASE

MODULE = ROOT / "research/prototypes/potion-admission/CBRPQCopyTransport.lua"
SITE = 0x1DCCB0
RANGES = ((0x1DCAF0, 0x1DCB20), (0x1DCB25, 0x1DCCCD), (0x1E2DA3, 0x1E2DB4))


class CopyHarness(TransportHarness):
    def __init__(self, image, watchdog=True):
        super().__init__(image, watchdog=watchdog)
        self.lua.execute("function CBRPQCopy_copied(...) end")
        self.config = self.lua.table_from({"callbacks": self.lua.table_from({"copied": "CBRPQCopy_copied"})})
        self.hook = self.lua.execute(MODULE.read_text(encoding="utf-8"))


@unittest.skipUnless(EEEX, "optional: set EEEX_LUA_DIR for actual EEex preprocessing")
class CopyTransportPreprocessorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = read_image()

    def test_inert_guards_and_existing_eeex_hook_nonoverlap(self):
        h = CopyHarness(self.image)
        h.validate()
        self.assertEqual([], h.patches)
        self.assertEqual([], h.protection)
        for site in [SITE, 0x1DCCBB] + [s for start, end in RANGES for s in (start, end - 1)]:
            with self.subTest(site=hex(site)):
                h = CopyHarness(self.image)
                h.image[site] ^= 1
                with self.assertRaisesRegex(Exception, "unsupported/previously patched site"):
                    h.install()
                self.assertEqual([], h.patches)
                self.assertEqual([], h.protection)
        h = CopyHarness(self.image)
        # Existing EEex first-call patch intentionally not authenticated here.
        h.image[0x1DCB20:0x1DCB25] = b"\xcc" * 5
        h.install()
        self.assertEqual([BASE + SITE], [p[0] for p in h.patches])

    def test_real_generated_paths_and_watchdog_integrity(self):
        for watchdog in (False, True):
            h = CopyHarness(self.image, watchdog=watchdog)
            h.install()
            self.assertEqual(3 if watchdog else 1, len(h.assemblies))
            text, state = h.assemblies[-1]
            exits, _, indirect = inspect_paths(text, 0, set())
            self.assertEqual({BASE + SITE + 5}, exits)
            self.assertFalse(indirect)
            self.assertEqual(0, state.curStackTop)
            self.assertEqual(0, state.shadowSpaceStackTop)
            self.assertIn(str(BASE + 0x1E2DB1), text)
            self.assertEqual([], h.warnings)
            if watchdog:
                self.assertEqual([0], [args[2] for args in h.watchdog_metadata if len(args) == 3])

    def test_missing_callback_watchdog_and_no_repeated_arm(self):
        h = CopyHarness(self.image)
        with self.assertRaisesRegex(Exception, "preservation helper required"):
            h.hook.install(h.lua.globals(), h.config)
        h.config.callbacks.copied = "AbsentCopyCallback"
        with self.assertRaisesRegex(Exception, "callback must exist"):
            h.install()
        self.assertEqual([], h.patches)
        h = CopyHarness(self.image)
        h.install()
        for action in (h.validate, h.install):
            with self.assertRaisesRegex(Exception, "already attempted"):
                action()
        self.assertEqual(1, len(h.patches))

    def test_patch_failure_cleanup_and_no_retry(self):
        h = CopyHarness(self.image)
        before = h.lua.globals().EEex_HookIntegrityWatchdog_HookEnter
        def fail(*_):
            raise RuntimeError("copy patch failure")
        h.lua.globals().EEex_JITAt = fail
        with self.assertRaisesRegex(Exception, "copy patch failure"):
            h.install()
        self.assertTrue(h.hook.failed)
        same = h.lua.eval("function(a,b) return rawequal(a,b) end")
        self.assertTrue(same(before, h.lua.globals().EEex_HookIntegrityWatchdog_HookEnter))
        self.assertEqual(["disable", "enable"], h.protection)
        with self.assertRaisesRegex(Exception, "already attempted"):
            h.install()


if __name__ == "__main__":
    unittest.main()
