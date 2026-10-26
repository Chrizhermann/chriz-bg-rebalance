"""Offline structural/safety checks; run with python -B this_file.py."""

from __future__ import annotations

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
        expected = {
            "CBRTBUF.SPL": (0, -2, 0, 6),
            "CBRTREG.SPL": (98, 2, 3, 12),
            "CBRTHST.SPL": (16, 0, 0, 20),
            "CBRTIHS.SPL": (16, 0, 1, 20),
            "CBRTSTP.SPL": (231, 0, 0, 12),
        }
        with tempfile.TemporaryDirectory(prefix="cbr-fixture-test-") as directory:
            output = Path(directory) / "assets"
            paths = builder.build_fixtures(output)
            self.assertEqual({p.name for p in paths}, set(expected))
            self.assertEqual({p.name for p in output.iterdir()}, set(expected))
            for path in paths:
                with self.subTest(resource=path.name):
                    data = path.read_bytes()
                    self.assertEqual(len(data), 0x72 + 0x28 + 0x30)
                    self.assertLessEqual(len(path.stem), 8)
                    spell = SplFile.from_bytes(data)
                    self.assertEqual(len(spell.abilities), 1)
                    self.assertEqual(spell.casting_effects, ())
                    ability = spell.abilities[0]
                    self.assertEqual((ability.target, ability.projectile), (1, 1))
                    self.assertEqual(ability.raw[0x0D], 1)
                    self.assertEqual(struct.unpack_from("<H", ability.raw, 0x12)[0], 0)
                    self.assertEqual(struct.unpack_from("<HH", ability.raw, 0x1E), (1, 0))
                    self.assertEqual(len(ability.effects), 1)
                    effect = ability.effects[0]
                    self.assertEqual(
                        (effect.opcode, effect.parameter1, effect.parameter2, effect.duration),
                        expected[path.name],
                    )
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
            self.assertEqual(len(list(output.iterdir())), 6)

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
