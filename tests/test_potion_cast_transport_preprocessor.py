"""Optional real EEex preprocessing of inert original-mode1 cast transport."""
import struct
import unittest

from tests.test_potion_hook_preprocessor import EEEX, ROOT
from tests.test_potion_transport_preprocessor import TransportHarness, read_image, inspect_paths, BASE

MODULE = ROOT / "research/prototypes/potion-admission/CBRPQCastTransport.lua"
CALLBACKS = ("parentQueued", "castEnter", "castLeave", "castDestroy", "childCreated",
             "childDirectEnter", "childDirectLeave", "childQueued", "childProjectile")
SITES = (0x1A8594, 0x212DD0, 0x212E89, 0x165200, 0x16B047, 0x16B24A,
         0x16B258, 0x16B1D0, 0x16B1E7, 0x16B0F9, 0x16B1EC)
SIZES = (7, 6, 5, 5, 5, 8, 5, 8, 5, 7, 6)
GUARDS = SITES + (0x212E63, 0x16ABC0, 0x16AFAC, 0x16AFC0, 0x16B0D7,
                  0x16B236, 0x16B1BC, 0x16B1DE, 0x590D90, 0x590DC0)
ENTRY_INDICES = (1, 3)
LEAVE_INDICES = (6, 8)
CALLS = (0x1A859E, 0x212E84, 0x16B252, 0x16B1D8, 0x16B1E2, 0x16B100, 0x16B1F2)


class CastHarness(TransportHarness):
    def __init__(self, image, watchdog=True):
        super().__init__(image, watchdog=watchdog)
        for name in CALLBACKS:
            self.lua.execute(f"function CBRPQCast_{name}(...) end")
        self.config = self.lua.table_from({"callbacks": self.lua.table_from(
            {key: "CBRPQCast_"+key for key in CALLBACKS})})
        self.hook = self.lua.execute(MODULE.read_text(encoding="utf-8"))


@unittest.skipUnless(EEEX, "optional: set EEEX_LUA_DIR for actual EEex preprocessing")
class CastTransportPreprocessorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = read_image()

    def test_inert_validation_and_all_guard_failures_before_any_patch(self):
        h = CastHarness(self.image)
        h.validate()
        self.assertEqual(2, len(h.assemblies))  # only original watchdog helper setup
        self.assertEqual([], h.patches)
        self.assertEqual([], h.protection)
        for site in GUARDS:
            with self.subTest(site=hex(site)):
                h = CastHarness(self.image)
                h.image[site] ^= 1
                with self.assertRaisesRegex(Exception, "unsupported/previously patched site"):
                    h.install()
                self.assertEqual([], h.patches)
                self.assertEqual([], h.protection)

    def test_actual_generator_balances_every_path_and_keeps_calls_in_place(self):
        for watchdog in (False, True):
            with self.subTest(watchdog=watchdog):
                h = CastHarness(self.image, watchdog=watchdog)
                h.install()
                offset = 2 if watchdog else 0
                self.assertEqual(11+offset, len(h.assemblies))
                self.assertEqual([BASE+s for s in SITES], [p[0] for p in h.patches])
                self.assertEqual([], h.warnings)
                for index, (text, state) in enumerate(h.assemblies[offset:]):
                    exits, _, indirect = inspect_paths(text, 8 if index in ENTRY_INDICES else 0, set())
                    expected = BASE+0x16B331 if index in LEAVE_INDICES else BASE+SITES[index]+SIZES[index]
                    self.assertEqual({expected}, exits)
                    self.assertFalse(indirect)
                    self.assertEqual(8 if index in ENTRY_INDICES else 0, state.curStackTop)
                    self.assertEqual(0, state.shadowSpaceStackTop)
                for call in CALLS:
                    self.assertTrue(all(not (site <= call < site+size) for site,size in zip(SITES,SIZES)))
                if watchdog:
                    masks = [args[2] for args in h.watchdog_metadata if len(args)==3]
                    self.assertEqual([0]*11, masks)

    def test_argument_code_and_native_direct_branch_preconditions(self):
        h = CastHarness(self.image)
        h.install()
        code = [text for text,_ in h.assemblies[2:]]
        self.assertIn("lea rax, qword ptr ss:[rsp+", code[1])
        self.assertIn("lea rax, qword ptr ss:[rbp+0B8h]", code[4])
        self.assertIn("mov eax, dword ptr ss:[rsp+", code[4])
        for index in range(4,11):
            self.assertIn(str(BASE+0x212E89), code[index])
            self.assertIn("cmp qword ptr ss:[rbp+0B8h], rax", code[index])
        for index in (5,7):
            self.assertIn("mov eax, r9d", code[index])
        self.assertIn(str(BASE+0x590D90), code[3])
        self.assertEqual(BASE+0x165200, struct.unpack_from("<Q", self.image, 0x590D90)[0])

    def test_missing_callback_watchdog_failure_and_no_double_arm(self):
        h = CastHarness(self.image)
        with self.assertRaisesRegex(Exception,"preservation helper required"):
            h.hook.install(h.lua.globals(),h.config)
        h.config.callbacks.childCreated="MissingCastCallback"
        with self.assertRaisesRegex(Exception,"callback must exist"):
            h.install()
        self.assertEqual([],h.patches)
        h = CastHarness(self.image)
        h.install()
        count=len(h.patches)
        with self.assertRaisesRegex(Exception,"already attempted"):
            h.validate()
        with self.assertRaisesRegex(Exception,"already attempted"):
            h.install()
        self.assertEqual(count,len(h.patches))

    def test_partial_failure_restores_scoped_templates_and_code_protection(self):
        h=CastHarness(self.image)
        before=h.lua.globals().EEex_HookIntegrityWatchdog_HookEnter
        capture=h.capture_at
        def fail(address,assembly):
            if len(h.patches)==2:
                raise RuntimeError("cast patch failure")
            capture(address,assembly)
        h.lua.globals().EEex_JITAt=fail
        with self.assertRaisesRegex(Exception,"cast patch failure"):
            h.install()
        self.assertTrue(h.hook.failed)
        self.assertFalse(h.hook.installed)
        same=h.lua.eval("function(a,b) return rawequal(a,b) end")
        self.assertTrue(same(before,h.lua.globals().EEex_HookIntegrityWatchdog_HookEnter))
        self.assertEqual(["disable","enable"],h.protection)
        with self.assertRaisesRegex(Exception,"already attempted"):
            h.install()


if __name__=="__main__":
    unittest.main()
