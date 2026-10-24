"""Offline structural/safety checks; run with python -B this_file.py."""

from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
import build_fixtures as builder
from ie_formats import SplFile


# (opcode, parameter1, parameter2, duration, timing, resource) per effect, in order.
EXPECTED = {
    "CBRTBUF.SPL": ((0, -2, 0, 6, 0, ""),),
    "CBRTREG.SPL": ((98, 2, 3, 12, 0, ""),),
    "CBRTHST.SPL": ((16, 0, 0, 20, 0, ""),),
    "CBRTIHS.SPL": ((16, 0, 1, 20, 0, ""),),
    "CBRTSTP.SPL": ((231, 0, 0, 12, 0, ""),),
    "CBRTWHS.SPL": ((16, 0, 2, 20, 0, ""),),
    "CBRTSRH.SPL": ((176, 6, 0, 20, 0, ""), (1, 6, 0, 20, 0, ""), (142, 0, 38, 20, 0, "")),
    "CBRTSLW.SPL": ((40, 0, 0, 20, 0, ""),),
    "CBRTTSI.SPL": ((310, 0, 1, 40, 0, ""),),
    "CBRTRMB.SPL": ((321, 0, 0, 0, 1, "CBRTBUF"),),
    "CBRTRMR.SPL": ((321, 0, 0, 0, 1, "CBRTREG"),),
    "CBRTDUM.SPL": ((208, 1, 0, 900, 0, ""), (175, 0, 2, 900, 0, "")),
}

# The captures up to step 4 used these bytes; later fixtures must leave them alone.
FIRST_CAPTURE_SHA256 = {
    "CBRTBUF.SPL": "0177281584093ebb21eaaf7752e3ec63cff6dce38fdc86b691eaf5de3835da8e",
    "CBRTREG.SPL": "3712341da93f64f82324fae83891ff4ae4a16b1d8ca567d361bfbc6a89e21666",
    "CBRTHST.SPL": "fa037db573ed9ff3703b380b375d5f00ad8fd8d629bb46b786a841aa3ff643c8",
    "CBRTIHS.SPL": "f47d0b3794eb6f099b5999b3828be672331eb19e324de29490ccdb7a4045a9b0",
    "CBRTSTP.SPL": "15f75bbda945424cb2e75896c5bdb53003e43cc611988f56eb2023b0940946a4",
}


class FixtureTests(unittest.TestCase):
    def test_written_native_effects_and_single_target_envelope(self):
        with tempfile.TemporaryDirectory(prefix="cbr-fixture-test-") as directory:
            output = Path(directory) / "assets"
            paths = builder.build_fixtures(output)
            self.assertEqual({p.name for p in paths}, set(EXPECTED))
            self.assertEqual({p.name for p in output.iterdir()}, set(EXPECTED))
            for path in paths:
                with self.subTest(resource=path.name):
                    data = path.read_bytes()
                    expected = EXPECTED[path.name]
                    self.assertEqual(len(data), 0x72 + 0x28 + 0x30 * len(expected))
                    self.assertLessEqual(len(path.stem), 8)
                    spell = SplFile.from_bytes(data)
                    self.assertEqual(len(spell.abilities), 1)
                    self.assertEqual(spell.casting_effects, ())
                    ability = spell.abilities[0]
                    self.assertEqual((ability.target, ability.projectile), (1, 1))
                    self.assertEqual(ability.raw[0x0D], 1)
                    self.assertEqual(struct.unpack_from("<H", ability.raw, 0x12)[0], 0)
                    self.assertEqual(struct.unpack_from("<HH", ability.raw, 0x1E), (len(expected), 0))
                    self.assertEqual(
                        tuple((e.opcode, e.parameter1, e.parameter2, e.duration, e.timing, e.resource)
                              for e in ability.effects),
                        expected,
                    )
                    for effect in ability.effects:
                        self.assertEqual((effect.target, effect.power), (2, 0))
                        self.assertEqual((effect.probability1, effect.probability2), (100, 0))
                        self.assertEqual((effect.save_type, effect.save_bonus), (0, 0))
                        self.assertEqual(effect.special, 0)
                        self.assertEqual((effect.dice_number, effect.dice_size), (0, 0))
                        self.assertEqual(effect.resist_dispel, 2)
                    self.assertEqual(struct.unpack_from("<I", data, 0x18)[0], 0)
                    self.assertEqual(struct.unpack_from("<H", data, 0x1C)[0], 1)
                    for offset in (0x08, 0x0C, 0x50, 0x54):
                        self.assertEqual(struct.unpack_from("<i", data, offset)[0], -1)

    def test_first_capture_fixtures_keep_their_bytes(self):
        resources = builder.fixture_bytes()
        for name, digest in FIRST_CAPTURE_SHA256.items():
            with self.subTest(resource=name):
                self.assertEqual(hashlib.sha256(resources[name]).hexdigest(), digest)

    def test_removal_fixtures_name_lab_fixtures_only(self):
        # op321 with an empty or foreign resource would strip unrelated effects from the subject.
        for name, effects in EXPECTED.items():
            for effect in effects:
                if effect[0] == 321:
                    with self.subTest(resource=name):
                        self.assertIn(f"{effect[5]}.SPL", EXPECTED)
                        self.assertNotEqual(f"{effect[5]}.SPL", name)

    def test_collision_is_refused_before_any_fixture_write(self):
        with tempfile.TemporaryDirectory(prefix="cbr-fixture-test-") as directory:
            output = Path(directory)
            collision = output / "cbrtstp.spl"
            collision.write_bytes(b"foreign resource")
            unrelated = output / "unrelated.txt"
            unrelated.write_bytes(b"preserve")
            with self.assertRaises(FileExistsError):
                builder.build_fixtures(output)
            self.assertEqual({p.name for p in output.iterdir()}, {collision.name, unrelated.name})
            self.assertEqual(collision.read_bytes(), b"foreign resource")
            self.assertEqual(unrelated.read_bytes(), b"preserve")

    def test_repeat_build_does_not_overwrite_existing_resources(self):
        with tempfile.TemporaryDirectory(prefix="cbr-fixture-test-") as directory:
            output = Path(directory)
            builder.build_fixtures(output)
            before = {p.name: p.read_bytes() for p in output.iterdir()}
            with self.assertRaises(FileExistsError):
                builder.build_fixtures(output)
            self.assertEqual({p.name: p.read_bytes() for p in output.iterdir()}, before)

    def test_unrelated_output_files_remain_untouched(self):
        with tempfile.TemporaryDirectory(prefix="cbr-fixture-test-") as directory:
            output = Path(directory)
            unrelated = output / "foreign.bin"
            unrelated.write_bytes(b"preserve")
            builder.build_fixtures(output)
            self.assertEqual(unrelated.read_bytes(), b"preserve")
            self.assertEqual(len(list(output.iterdir())), len(EXPECTED) + 1)

    def test_relative_and_parent_traversal_paths_are_refused(self):
        with self.assertRaises(ValueError):
            builder.build_fixtures("relative-fixtures")
        with tempfile.TemporaryDirectory(prefix="cbr-fixture-test-") as directory:
            with self.assertRaises(ValueError):
                builder.build_fixtures(Path(directory) / ".." / "outside-fixtures")

    def test_linked_output_is_refused(self):
        with tempfile.TemporaryDirectory(prefix="cbr-fixture-test-") as directory:
            root = Path(directory)
            target = root / "target"
            target.mkdir()
            link = root / "linked"
            try:
                link.symlink_to(target, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"host cannot create directory symlink: {error}")
            with self.assertRaises(ValueError):
                builder.build_fixtures(link)
            self.assertEqual(list(target.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
