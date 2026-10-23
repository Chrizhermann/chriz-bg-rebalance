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


class FixtureTests(unittest.TestCase):
    def test_written_native_effects_and_single_target_envelope(self):
        # resource -> (encoded duration, effects as (opcode, parameter1, parameter2))
        expected = {
            "CBRTBUF.SPL": (6, ((0, -2, 0),)),
            "CBRTREG.SPL": (12, ((98, 2, 3),)),
            "CBRTHST.SPL": (20, ((16, 0, 0),)),
            "CBRTIHS.SPL": (20, ((16, 0, 1),)),
            "CBRTSTP.SPL": (12, ((231, 0, 0),)),
            "CBRTSLW.SPL": (20, ((40, 0, 0),)),
            # Spell Revisions 4.19 SPWI305: movement rate, half an attack, the Haste icon; no op16.
            "CBRTSRH.SPL": (20, ((176, 6, 0), (1, 6, 0), (142, 0, 38))),
            "CBRTDIS.SPL": (20, ((78, 0, 0),)),
        }
        with tempfile.TemporaryDirectory(prefix="cbr-fixture-test-") as directory:
            output = Path(directory) / "assets"
            paths = builder.build_fixtures(output)
            self.assertEqual({p.name for p in paths}, set(expected))
            self.assertEqual({p.name for p in output.iterdir()}, set(expected))
            for path in paths:
                with self.subTest(resource=path.name):
                    duration, effects = expected[path.name]
                    data = path.read_bytes()
                    self.assertEqual(len(data), 0x72 + 0x28 + 0x30 * len(effects))
                    self.assertLessEqual(len(path.stem), 8)
                    spell = SplFile.from_bytes(data)
                    self.assertEqual(len(spell.abilities), 1)
                    self.assertEqual(spell.casting_effects, ())
                    ability = spell.abilities[0]
                    self.assertEqual((ability.target, ability.projectile), (1, 1))
                    self.assertEqual(ability.raw[0x0D], 1)
                    self.assertEqual(struct.unpack_from("<H", ability.raw, 0x12)[0], 0)
                    self.assertEqual(struct.unpack_from("<HH", ability.raw, 0x1E), (len(effects), 0))
                    self.assertEqual(
                        tuple((effect.opcode, effect.parameter1, effect.parameter2) for effect in ability.effects),
                        effects,
                    )
                    for effect in ability.effects:
                        self.assertEqual(effect.duration, duration)
                        self.assertEqual((effect.target, effect.timing, effect.power), (2, 0, 0))
                        self.assertEqual((effect.probability1, effect.probability2), (100, 0))
                        self.assertEqual((effect.save_type, effect.save_bonus), (0, 0))
                        self.assertEqual((effect.resource, effect.special), ("", 0))
                        self.assertEqual((effect.dice_number, effect.dice_size), (0, 0))
                        self.assertEqual(effect.resist_dispel, 2)
                    self.assertEqual(struct.unpack_from("<I", data, 0x18)[0], 0)
                    self.assertEqual(struct.unpack_from("<H", data, 0x1C)[0], 1)
                    for offset in (0x08, 0x0C, 0x50, 0x54):
                        self.assertEqual(struct.unpack_from("<i", data, offset)[0], -1)

    def test_time_stop_lab_fixtures_keep_their_bytes(self):
        # The five fixtures of the Time Stop lab's captures (staged 2026-10-20 to 2026-10-23).
        pinned = {
            "CBRTBUF.SPL": "0177281584093ebb21eaaf7752e3ec63cff6dce38fdc86b691eaf5de3835da8e",
            "CBRTREG.SPL": "3712341da93f64f82324fae83891ff4ae4a16b1d8ca567d361bfbc6a89e21666",
            "CBRTHST.SPL": "fa037db573ed9ff3703b380b375d5f00ad8fd8d629bb46b786a841aa3ff643c8",
            "CBRTIHS.SPL": "f47d0b3794eb6f099b5999b3828be672331eb19e324de29490ccdb7a4045a9b0",
            "CBRTSTP.SPL": "15f75bbda945424cb2e75896c5bdb53003e43cc611988f56eb2023b0940946a4",
        }
        resources = builder.fixture_bytes()
        for name, digest in pinned.items():
            with self.subTest(resource=name):
                self.assertEqual(hashlib.sha256(resources[name]).hexdigest(), digest)

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
            self.assertEqual(len(list(output.iterdir())), len(builder.fixture_bytes()) + 1)

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
