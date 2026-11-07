"""Publicly reproducible synthetic BCS/CRE coverage of the wing-buffet writer."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from tests.test_dragon_wing_buffet import LIB, WEIDU, ROSTER, write_ids, blocks, snapshot, simulate_buffet_paths


class WingOverwriteTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="cbr-wing-overwrite-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.fixture = self.root / "fixture"
        self.fixture.mkdir()
        write_ids(self.fixture)
        self.number = 0
        self.run_code('''LAF cbr_wb_build_family RET original = family END
OUTER_SPRINT source ~SC%LNL%%original%SC%LNL%~
COPY ~cbr_wb_empty~ ~fixture/original.bcs~
  DELETE_BYTES 0 BUFFER_LENGTH INSERT_BYTES 0 (STRING_LENGTH ~%source%~) WRITE_ASCIIE 0 ~%source%~
''')
        self.original = (self.fixture / "original.bcs").read_bytes()
        for cre, (script, dv, slot) in ROSTER.items():
            raw = bytearray(0x2d4)
            raw[:8] = b"CRE V1.0"
            raw[0x280:0x2a0] = dv.encode().ljust(32, b"\0")
            raw[slot:slot+8] = script.encode().ljust(8, b"\0")
            (self.fixture / f"{cre}.cre").write_bytes(raw)
            (self.fixture / f"{script}.bcs").write_bytes(self.original)

    def run_code(self, code):
        self.number += 1
        tp2 = self.root / f"run{self.number}.tp2"
        tp2.write_text(f'BACKUP ~backup{self.number}~\nAUTHOR ~test~\nBEGIN ~wing~\nINCLUDE ~{LIB.as_posix()}~\n'+code)
        result = subprocess.run([str(WEIDU), str(tp2), "--nogame", "--search-ids", str(self.fixture),
                                 "--force-install-list", "0", "--no-exit-pause", "--quick-log"],
                                cwd=self.root, capture_output=True, text=True, timeout=60)
        self.assertEqual(0, result.returncode, result.stdout+result.stderr)
        self.assertNotIn("INSTALLED WITH WARNINGS", result.stdout+result.stderr)
        return result.stdout+result.stderr

    def install(self):
        return self.run_code('LAF cbr_apply_dragon_wing_buffet INT_VAR game_mode = 0 STR_VAR resource_dir = ~fixture~ END\n')

    def test_normal_output_preserves_original_blocks_and_second_install(self):
        self.install()
        for script, actor, _ in ROSTER.values():
            data = (self.fixture / f"{script}.bcs").read_bytes()
            self.assertEqual(blocks(self.original), blocks(data)[2:])
            for cloud in (False, True):
                self.assertEqual((18, 3, 1), simulate_buffet_paths(data, actor, cloud=cloud, response=0))
                self.assertEqual((6, 3, 1), simulate_buffet_paths(data, "other", cloud=cloud, response=0))
        before = snapshot(self.fixture)
        self.install()
        self.assertEqual(before, snapshot(self.fixture))

    def test_edited_missing_and_duplicate_blocks_still_get_decided_pair(self):
        variants = [b"SC\nSC\n", self.original.replace(b'6 0 0 0 0"LOCALSBuffet"', b'99 0 0 0 0"LOCALSBuffet"'),
                    b"SC\n"+self.original[3:-3]*2+b"SC\n", self.original.replace(b"16408 12", b"16408 19")]
        for data, (script, actor, _) in zip(variants, ROSTER.values()):
            (self.fixture / f"{script}.bcs").write_bytes(data)
        self.install()
        for script, actor, _ in ROSTER.values():
            data = (self.fixture / f"{script}.bcs").read_bytes()
            self.assertEqual((18, 3, 1), simulate_buffet_paths(data, actor, cloud=True, response=0))
            self.assertEqual(3, data.count(b'18 0 0 0 0"LOCALSBuffet"'))
        path = self.fixture / "dragred.bcs"
        path.write_bytes(path.read_bytes().replace(b'18 0 0 0 0"LOCALSBuffet"', b'25 0 0 0 0"LOCALSBuffet"'))
        self.install()
        self.assertEqual(3, path.read_bytes().count(b'18 0 0 0 0"LOCALSBuffet"'))

    def test_current_actor_script_assignment_missing_script_and_missing_creature(self):
        path = self.fixture / "fsdragon.cre"
        raw = bytearray(path.read_bytes())
        raw[0x280:0x2a0] = b"OtherDra".ljust(32, b"\0")
        raw[0x250:0x258] = b"foreign\0"
        path.write_bytes(raw)
        (self.fixture / "shadra01.cre").unlink()
        output = self.install()
        self.assertIn("optional creature shadra01 is absent", output)
        data = (self.fixture / "foreign.bcs").read_bytes()
        self.assertEqual((18, 3, 1), simulate_buffet_paths(data, "OtherDra", cloud=True, response=0))
        self.assertEqual(self.original, (self.fixture / "draggree.bcs").read_bytes())
        self.assertIn(b'18 0 0 0 0"LOCALSBuffet"', (self.fixture / "dragred.bcs").read_bytes())

    def test_shared_script_keeps_both_actor_pairs_and_damaged_file_is_local(self):
        path = self.fixture / "fsdragon.cre"
        raw = bytearray(path.read_bytes()); raw[0x250:0x258] = b"dragred\0"; path.write_bytes(raw)
        (self.fixture / "shadra01.bcs").write_bytes(b"broken")
        self.install()
        data = (self.fixture / "dragred.bcs").read_bytes()
        for actor in ("firkra02", "FSdragon"):
            self.assertEqual((18, 3, 1), simulate_buffet_paths(data, actor, cloud=True, response=0))
        self.assertEqual(b"broken", (self.fixture / "shadra01.bcs").read_bytes())
        before = snapshot(self.fixture); self.install(); self.assertEqual(before, snapshot(self.fixture))
