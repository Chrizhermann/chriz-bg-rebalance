"""Copied native marshal paths plus actual EEex-generated observer instructions.

No game/DLL/save execution. Full native Marshal flow and generated trampolines
are checked separately; this does not emulate EEex's save collector or writer.
"""
from pathlib import Path
import struct
import sys
import tempfile
import unittest

from tests.test_potion_generated_trampoline import GeneratedMachine, EEEX, LIBS, ML64
from tests.test_potion_cast_generated_trampoline import native_replay
from tests.test_potion_marshal_transport_preprocessor import MarshalHarness, read_image, SITES, SIZES, BASE
from tests.test_potion_hook_preprocessor import ROOT

if EEEX and LIBS and ML64:
    import unicorn
    from unicorn import x86_const as x86
    sys.path.insert(0, str(ROOT / "research/prototypes/potion-admission"))
    import probe_native_admission as native
    from probe_native_potion_save import SaveMachine, LIST, OUT, BUFFER


@unittest.skipUnless(EEEX and LIBS and ML64,
                     "optional: EEEX_LUA_DIR, EEEX_POTION_PYLIBS and EEEX_POTION_ML64")
class MarshalGeneratedTrampolineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = Path(tempfile.mkdtemp(prefix="cbr-potion-marshal-generated-"))
        cls.image = read_image()

    def execute(self, index, version, only_nine, exclude_two, *, error=False):
        h = MarshalHarness(self.image, watchdog=True)
        h.install()
        def initialize(m):
            m.initial_rsp = m.STACK + 0x20000 + (8 if index == 0 else 0)
            m.write("RSP", m.initial_rsp)
            m.uc.mem_write(m.initial_rsp, bytes(range(128)))
            m.write("RCX", m.DATA + 0x400)
            m.write("RDI", m.DATA + 0x400)
            m.write("RBX", 0x318)
            m.write("R12", only_nine)
            m.write("R8", 0x1234567800000000 | version)
            m.write("R9", 0x1234567800000000 | only_nine)
            m.write("RAX", 0xABCDE)  # preserve pending native return size at leave
            # Distinct fifth-argument neighbours catch both stack alignment and
            # accidental qword reads. Native excludeTiming2 is only a DWORD.
            m.uc.mem_write(m.initial_rsp + 0x20, struct.pack("<IIII", 0xFEEDABBA, 0xBABECAFE,
                                                         exclude_two, 0x87654321))
        destination = (0x1E5347 if only_nine else 0x1E5382) if index == 1 else SITES[index] + SIZES[index]
        m = GeneratedMachine(h, self.directory, index + 2,
                             {BASE + destination},
                             lua_error=error, initializer=initialize)
        # Branch target is separately asserted by GeneratedMachine; compare its
        # original TEST flags/state without replaying a relocated short JZ.
        length = 3 if index == 1 else SIZES[index]
        expected, stack = native_replay(m, bytes(self.image[SITES[index]:SITES[index] + length]))
        self.assertEqual(expected, m.snapshot())
        self.assertEqual(stack, bytes(m.uc.mem_read(m.initial_rsp, 128)))
        self.assertEqual(1, m.watchdog_checks)
        arguments = [value for _, value in m.lua_arguments]
        if index == 0:
            self.assertEqual([m.initial_rsp, m.initial["RCX"], version, only_nine, exclude_two], arguments)
        elif index == 1:
            self.assertEqual([] if only_nine else [m.initial_rsp + 0x1B8, m.initial["RDI"], 0x318], arguments)
        elif index == 2:
            self.assertEqual([m.initial_rsp + 0x1B8, m.initial["RDI"], version * 0x108], arguments)
        else:
            self.assertEqual([m.initial_rsp + 0x1B8], arguments)
        return m

    def test_actual_generated_entry_exit_arguments_state_and_error_paths(self):
        for index in range(4):
            for values in ((0, 0, 0), (1, 1, 1), (255, 0x1234, 0x89ABCDEF)):
                for error in (False, True):
                    with self.subTest(site=hex(SITES[index]), args=values, error=error):
                        self.execute(index, *values, error=error)

    def test_only_native_ret_and_all_native_branch_destinations_remain_inside_guarded_function(self):
        import capstone
        cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        instructions = list(cs.disasm(bytes(self.image[0x1E50E0:0x1E5475]), 0x1E50E0))
        self.assertEqual([0x1E5474], [i.address for i in instructions if i.mnemonic == "ret"])
        for instruction in instructions:
            if instruction.mnemonic.startswith("j"):
                self.assertTrue(0x1E50E0 <= int(instruction.op_str, 16) < 0x1E5475)
        self.assertEqual(bytes.fromhex("488B8C24700100004833CCE83C2331004881C488010000415E415D415C5F5E5BC3"),
                         bytes(self.image[0x1E5454:0x1E5475]))

    def test_actual_native_empty_nonempty_and_filtered_paths_balance_same_entry_frame(self):
        class ObservedMarshal(SaveMachine):
            def __init__(self, *args):
                super().__init__(*args)
                self.observed = []
                self.counted, self.boundary = [], []

            def on_code(self, uc, address, size, data):
                if address == BASE + 0x1E50E0:
                    rsp = self.reg_read("RSP")
                    self.observed.append(("enter", rsp, self.reg_read("RCX"),
                                          self.reg_read("R8") & 255, self.reg_read("R9") & 0xFFFFFFFF,
                                          self.get(rsp + 0x28, "I")))
                elif address == BASE + 0x1E5454:
                    self.observed.append(("leave", self.reg_read("RSP") + 0x1B8))
                elif address == BASE + 0x1E5474:
                    self.observed.append(("return", self.reg_read("RSP")))
                elif address == BASE + 0x1E5342 and self.reg_read("R12D") == 0:
                    self.counted.append((self.reg_read("RSP") + 0x1B8, self.reg_read("RDI"), self.reg_read("EBX")))
                elif address == BASE + 0x1E537B:
                    self.counted.append((self.reg_read("RSP") + 0x1B8, self.reg_read("RDI"),
                                         (self.reg_read("R8D") * 0x108) & 0xFFFFFFFF))
                elif address == BASE + 0x1E5382:
                    self.boundary.append((self.reg_read("RSP") + 0x1B8, self.reg_read("RDI"), self.reg_read("EBX")))
                return super().on_code(uc, address, size, data)

        # V1 is observed for balanced context only; V2 serialized byte semantics
        # are independently asserted in probe_native_potion_save.py. V1's native
        # multi-record stride anomaly is not made a save-support claim here.
        for version in (0, 1, 255):
            for timing in (None, 2, 9, 4096):
                for only_nine, exclude_two in ((0, 0), (1, 0), (0, 1), (1, 1), (7, 11)):
                    with self.subTest(version=version, timing=timing, only9=only_nine, exclude2=exclude_two):
                        m = ObservedMarshal(bytes(self.image), unicorn, x86)
                        if timing is None:
                            m.put(LIST + 8, "QQI", 0, 0, 0)
                        else:
                            m.put(native.EFFECT + 0x24, "I", timing)
                            m.put(native.NODES, "QQQ", 0, 0, native.EFFECT)
                            m.put(LIST + 8, "QQI", native.NODES, native.NODES, 1)
                        m.run(0x1E50E0, LIST, OUT, version, only_nine, exclude_two)
                        entry_rsp = native.STACK + 0x6000 - 8
                        self.assertEqual([
                            ("enter", entry_rsp, LIST, version, only_nine, exclude_two),
                            ("leave", entry_rsp), ("return", entry_rsp)], m.observed)
                        selected = timing is not None and (not only_nine or timing == 9) and (not exclude_two or timing != 2)
                        self.assertEqual((0x108 if version else 0x30) if selected else 0, m.reg_read("EAX"))
                        self.assertEqual([(entry_rsp, LIST, 0x108 if selected else 0)] if version else [], m.counted)
                        self.assertEqual(m.counted, m.boundary)

    def test_retained_counterexample_exporter_append_overwrites_footer_at_old_native_count(self):
        # Model only the two inspected stock EEex hook services; normal count,
        # allocation dispatch and copy loop remain actual native instructions.
        # Passing reproduces the UNSUPPORTED count-changing-exporter problem.
        class MutatingExporter(SaveMachine):
            def on_code(self, uc, address, size, data):
                if address == BASE + 0x1E5384:
                    self.original_bytes = self.reg_read("EBX")
                    self.put(native.NODES, "Q", native.NODES + 0x30)
                    self.put(native.NODES + 0x30, "QQQ", 0, native.NODES, native.ACTIVE)
                    self.put(LIST + 0x10, "QI", native.NODES + 0x30, 2)
                    self.reg_write("EBX", self.original_bytes + 0x108)
                    # Both old and augmented counts are positive; native JLE
                    # flags equal the stock hook's positive add-result flags.
                elif address == BASE + 0x1E5392:
                    self.u.mem_write(BUFFER + self.original_bytes, b"X-BIV1.0")
                return super().on_code(uc, address, size, data)

        m = MutatingExporter(bytes(self.image), unicorn, x86)
        m.put(native.NODES, "QQQ", 0, 0, native.EFFECT)
        m.put(LIST + 8, "QQI", native.NODES, native.NODES, 1)
        m.run(0x1E50E0, LIST, OUT, 1, 0, 0)
        self.assertEqual(0x108, m.original_bytes)
        self.assertEqual(0x210, m.allocated)
        self.assertEqual(m.read(native.ACTIVE + 8, 0x108), m.read(BUFFER + 0x108, 0x108))
        self.assertNotEqual(b"X-BIV1.0", m.read(BUFFER + 0x108, 8))


if __name__ == "__main__":
    unittest.main()
