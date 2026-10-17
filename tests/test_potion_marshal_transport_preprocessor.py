"""Optional actual EEex preprocessing of the inert native marshal observer."""
import unittest

from tests.test_potion_hook_preprocessor import EEEX, ROOT
from tests.test_potion_transport_preprocessor import TransportHarness, read_image, inspect_paths, BASE

MODULE = ROOT / "research/prototypes/potion-admission/CBRPQMarshalTransport.lua"
SITES = (0x1E50E0, 0x1E5342, 0x1E537B, 0x1E5454)
SIZES = (6, 5, 7, 8)
RANGES = ((0x1E50E0, 0x1E5384), (0x1E538A, 0x1E538D), (0x1E5392, 0x1E5475))
EEEX_SLOTS = ((0x1E5384, 0x1E538A), (0x1E538D, 0x1E5392))


class MarshalHarness(TransportHarness):
    def __init__(self, image, watchdog=True):
        super().__init__(image, watchdog=watchdog)
        self.lua.execute("function CBRPQMarshal_enter(...) end; function CBRPQMarshal_counted(...) end; function CBRPQMarshal_leave(...) end")
        self.config = self.lua.table_from({"callbacks": self.lua.table_from(
            {key: "CBRPQMarshal_" + key for key in ("enter", "counted", "leave")})})
        self.hook = self.lua.execute(MODULE.read_text(encoding="utf-8"))


@unittest.skipUnless(EEEX, "optional: set EEEX_LUA_DIR for real EEex preprocessing")
class MarshalTransportPreprocessorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = read_image()

    def test_validate_is_inert_and_native_topology_collisions_fail_before_mutation(self):
        h = MarshalHarness(self.image)
        h.validate()
        self.assertEqual(2, len(h.assemblies))  # original watchdog helper setup
        self.assertEqual([], h.patches)
        self.assertEqual([], h.protection)
        # Entry, exit, both ends of every guarded interval, filter decisions,
        # native copy operands, and sole RET must all retain their pinned ABI.
        sites = set(SITES + (0x1E513E, 0x1E52F0, 0x1E52F5, 0x1E5342, 0x1E53B0))
        for start, end in RANGES:
            sites.update((start, end - 1))
        for site in sorted(sites):
            with self.subTest(site=hex(site)):
                h = MarshalHarness(self.image)
                h.image[site] ^= 1
                with self.assertRaisesRegex(Exception, "unsupported/previously patched site"):
                    h.install()
                self.assertEqual([], h.patches)
                self.assertEqual([], h.protection)

    def test_stock_eeex_slots_and_sprite_wrapper_are_not_overwritten(self):
        h = MarshalHarness(self.image)
        # This deliberately demonstrates the boundary: we do not authenticate
        # these two pre-existing patches. Composition must retain stock EEex.
        for start, end in EEEX_SLOTS:
            h.image[start:end] = b"\xcc" * (end - start)
        h.image[0x361767:0x36176C] = b"\xcc" * 5
        h.install()
        self.assertEqual([BASE + site for site in SITES], [p[0] for p in h.patches])
        for start, end in EEEX_SLOTS + ((0x361767, 0x36176C),):
            self.assertTrue(all(not (site < end and site + size > start)
                                for site, size in zip(SITES, SIZES)))

    def test_every_generated_path_balances_and_retains_zero_watchdog_masks(self):
        for watchdog in (False, True):
            with self.subTest(watchdog=watchdog):
                h = MarshalHarness(self.image, watchdog=watchdog)
                h.install()
                offset = 2 if watchdog else 0
                self.assertEqual(4 + offset, len(h.assemblies))
                self.assertEqual([], h.warnings)
                for index, (text, state) in enumerate(h.assemblies[offset:]):
                    alignment = 8 if index == 0 else 0
                    exits, _, indirect = inspect_paths(text, alignment, set())
                    self.assertEqual({BASE + 0x1E5347, BASE + 0x1E5382} if index == 1 else
                                     {BASE + SITES[index] + SIZES[index]}, exits)
                    self.assertFalse(indirect)
                    self.assertEqual(alignment, state.curStackTop)
                    self.assertEqual(0, state.shadowSpaceStackTop)
                if watchdog:
                    masks = [args[2] for args in h.watchdog_metadata if len(args) == 3]
                    self.assertEqual([0, 0, 0, 0], masks)

    def test_callbacks_watchdog_and_already_attempted_guards(self):
        h = MarshalHarness(self.image)
        with self.assertRaisesRegex(Exception, "preservation helper required"):
            h.hook.install(h.lua.globals(), h.config)
        h.config.callbacks.leave = "MissingMarshalCallback"
        with self.assertRaisesRegex(Exception, "callback must exist"):
            h.install()
        self.assertEqual([], h.patches)
        h = MarshalHarness(self.image)
        h.install()
        for action in (h.validate, h.install):
            with self.assertRaisesRegex(Exception, "already attempted"):
                action()
        self.assertEqual(4, len(h.patches))

    def test_partial_failure_restores_templates_and_protection_without_retry(self):
        h = MarshalHarness(self.image)
        original = h.lua.globals().EEex_HookIntegrityWatchdog_HookEnter
        capture = h.capture_at
        def fail(address, assembly):
            if h.patches:
                raise RuntimeError("marshal patch failure")
            capture(address, assembly)
        h.lua.globals().EEex_JITAt = fail
        with self.assertRaisesRegex(Exception, "marshal patch failure"):
            h.install()
        self.assertTrue(h.hook.failed)
        same = h.lua.eval("function(a,b) return rawequal(a,b) end")
        self.assertTrue(same(original, h.lua.globals().EEex_HookIntegrityWatchdog_HookEnter))
        self.assertEqual(["disable", "enable"], h.protection)
        with self.assertRaisesRegex(Exception, "already attempted"):
            h.install()


if __name__ == "__main__":
    unittest.main()
