"""Real WeiDU 249 transformation checks; all writes stay in temporary fixtures.

These prove resource transformation, not live Spell Shield or casting behavior.
"""
from __future__ import annotations

import dataclasses
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.ie_formats import SplAbility, SplEffect, SplFile


ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "chriz-bg-rebalance/lib/sr_spellstrike.tpa"
HARNESS = ROOT / "tests/weidu/sr_spellstrike_harness.tp2"
WEIDU = Path(__import__("os").environ.get("WEIDU", ROOT / "weidu.exe"))


def _owned(effect: SplEffect) -> bool:
    return effect.opcode == 60 and effect.parameter2 in (0, 1)


def _refresh(resref: str) -> SplEffect:
    return SplEffect(opcode=321, target=2, parameter2=2, timing=1,
                     resist_dispel=2, resource=resref.upper())


def _fixture(*, casting_at_end: bool = False, foreign: bool = True) -> bytes:
    raw_header = bytearray(0x72)
    raw_header[0x18:0x1C] = b"\x12\x34\x56\x78"
    raw_header[0x27] = 1
    raw_header[0x38:0x40] = b"\x12\x23\x34\x45\x56\x67\x78\x89"
    abilities = []
    for level in (1, 20):
        donor = SplEffect(opcode=60, target=2, power=9, resist_dispel=2,
                          parameter1=100, timing=0, duration=6)
        effects = [
            SplEffect(opcode=221, target=2, power=9, parameter1=9,
                      parameter2=1, timing=1, resist_dispel=2),
            SplEffect(opcode=141, target=2, parameter2=63, timing=1),
            SplEffect(opcode=174, target=2, timing=1, resource="EFF_S09"),
            donor,
            dataclasses.replace(donor, parameter2=1),
            dataclasses.replace(donor, parameter1=50, duration=12),
            dataclasses.replace(donor, parameter1=50, duration=12, parameter2=1),
            SplEffect(opcode=142, target=2, power=9, resist_dispel=2,
                      parameter2=83, duration=12),
            # Its mod-allocated secondary type must never be rewritten.
            SplEffect(opcode=221, target=2, parameter1=9, parameter2=23,
                      timing=3, duration=0, resist_dispel=2),
            SplEffect(opcode=328, target=2, parameter2=42, duration=12),
            SplEffect(opcode=321, target=2, resource="FOREIGN", timing=1),
        ]
        if foreign:
            effects.extend((
                dataclasses.replace(donor, parameter2=2, parameter1=8),
                dataclasses.replace(donor, save_type=1, parameter1=9),
                dataclasses.replace(donor, timing=1, parameter1=10),
                dataclasses.replace(donor, target=1, parameter1=11),
            ))
        raw_ability = bytearray(0x28)
        raw_ability[0:4] = b"\x01\x04\x03\x02"
        raw_ability[0x12:0x16] = b"\x05\x00\xAA\xCC"
        abilities.append(SplAbility(level, 1, 157, tuple(effects), "SPWI903",
                                    bytes(raw_ability)))
    casting = (SplEffect(opcode=146, target=1, timing=1, resource="DWHOOK"),
               SplEffect(opcode=60, target=2, parameter1=33, duration=7))
    result = SplFile(tuple(abilities), casting, bytes(raw_header)).to_bytes()
    if casting_at_end:
        raw = bytearray(result)
        fx = struct.unpack_from("<I", raw, 0x6A)[0]
        total = (len(raw) - fx) // 0x30
        raw[fx:] = raw[fx + len(casting) * 0x30:] + raw[fx:fx + len(casting) * 0x30]
        struct.pack_into("<H", raw, 0x6E, total - len(casting))
        for index in range(len(abilities)):
            offset = 0x72 + index * 0x28 + 0x20
            struct.pack_into("<H", raw, offset, struct.unpack_from("<H", raw, offset)[0] - len(casting))
        result = bytes(raw)
    return result


def _mutate(data: bytes, callback) -> bytes:
    spell = SplFile.from_bytes(data)
    abilities = list(spell.abilities)
    abilities[-1] = dataclasses.replace(abilities[-1], effects=tuple(callback(list(abilities[-1].effects))))
    return dataclasses.replace(spell, abilities=tuple(abilities)).to_bytes()


class SpellstrikeTransformationTests(unittest.TestCase):
    def transform(self, payload: bytes, resref: str = "SPWI903B", *, error: str | None = None) -> bytes | None:
        (ROOT / "work").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="cbr-spellstrike-", dir=ROOT / "work") as temporary:
            folder = Path(temporary)
            source, destination = folder / "input.spl", folder / "output.spl"
            source.write_bytes(payload)
            (folder / "weidu.log").write_text("", encoding="ascii")
            command = [str(WEIDU), str(HARNESS), "--nogame", "--force-install-list", "0",
                       "--no-exit-pause", "--quick-log"]
            for argument in (LIBRARY, source, destination, resref):
                command.extend(("--args", str(argument)))
            result = subprocess.run(command, cwd=folder, capture_output=True, text=True,
                                    timeout=90, check=False)
            transcript = result.stdout + result.stderr
            self.assertEqual(payload, source.read_bytes())
            if error is not None:
                self.assertIn("NOT INSTALLED DUE TO ERRORS", transcript)
                self.assertIn(error, transcript)
                self.assertFalse(destination.exists())
                return None
            self.assertEqual(0, result.returncode, transcript)
            self.assertNotIn("WARNING", transcript)
            self.assertIn("SUCCESSFULLY INSTALLED", transcript)
            self.assertTrue(destination.exists(), transcript)
            return destination.read_bytes()

    def assert_preserved(self, before: bytes, after: bytes, resref: str) -> None:
        old, new = SplFile.from_bytes(before), SplFile.from_bytes(after)
        old_header, new_header = bytearray(old.header_raw), bytearray(new.header_raw)
        old_header[0x64:0x68] = new_header[0x64:0x68]
        old_header[0x6A:0x70] = new_header[0x6A:0x70]
        self.assertEqual(old_header, new_header)
        self.assertEqual([fx.to_bytes() for fx in old.casting_effects],
                         [fx.to_bytes() for fx in new.casting_effects])
        self.assertEqual(len(old.abilities), len(new.abilities))
        for original, output in zip(old.abilities, new.abilities):
            old_raw, new_raw = bytearray(original.raw), bytearray(output.raw)
            old_raw[0x1E:0x22] = new_raw[0x1E:0x22]
            self.assertEqual(old_raw, new_raw)
            self.assertEqual(_refresh(resref).to_bytes(), output.effects[0].to_bytes())
            for mode in (0, 1):
                failures = [fx for fx in output.effects if _owned(fx) and fx.parameter2 == mode]
                self.assertEqual(1, len(failures))
                donor = next((fx for fx in original.effects if _owned(fx)), SplEffect(resist_dispel=2))
                expected = dataclasses.replace(donor, opcode=60, target=2, timing=0,
                                               parameter1=15, parameter2=mode, duration=12,
                                               probability1=100, probability2=0,
                                               save_type=donor.save_type & ~31)
                self.assertEqual(expected.to_bytes(), failures[0].to_bytes())
            def retained_effect(fx):
                return not (_owned(fx) or (fx.opcode == 221 and fx.parameter2 == 1)
                            or (fx.opcode == 321 and fx.resource.upper() == resref.upper()))
            strips = [fx for fx in output.effects if fx.opcode == 221 and fx.parameter2 == 1]
            strip = next((fx for fx in original.effects if fx.opcode == 221 and fx.parameter2 == 1),
                         SplEffect(resist_dispel=2))
            self.assertEqual([dataclasses.replace(strip, opcode=221, target=2, parameter1=9,
                                                 parameter2=1, timing=1, resist_dispel=2, duration=0,
                                                 probability1=100, probability2=0,
                                                 save_type=strip.save_type & ~31).to_bytes()],
                             [fx.to_bytes() for fx in strips])
            retained = [fx.to_bytes() for fx in original.effects if retained_effect(fx)]
            actual = [fx.to_bytes() for fx in output.effects[1:] if retained_effect(fx)]
            self.assertEqual(retained, actual, "stripping, feedback or foreign effects changed")

    def test_direct_and_wrapped_payloads_preserve_all_other_fields(self):
        for resref in ("SPWI903", "SPWI903B", "zSSbody"):
            with self.subTest(resref=resref):
                before = _fixture()
                after = self.transform(before, resref)
                self.assert_preserved(before, after, resref)

    def test_casting_last_and_out_of_order_ability_groups_are_preserved(self):
        before = bytearray(_fixture(casting_at_end=True))
        first = bytes(before[0x72:0x9A])
        before[0x72:0x9A] = before[0x9A:0xC2]
        before[0x9A:0xC2] = first
        after = self.transform(bytes(before))
        self.assert_preserved(bytes(before), after, "SPWI903B")

    def test_no_casting_effects_and_end_index_are_supported(self):
        spell = dataclasses.replace(SplFile.from_bytes(_fixture()), casting_effects=())
        before = bytearray(spell.to_bytes())
        effect_offset = struct.unpack_from("<I", before, 0x6A)[0]
        struct.pack_into("<H", before, 0x6E, (len(before) - effect_offset) // 0x30)
        after = self.transform(bytes(before))
        self.assert_preserved(bytes(before), after, "SPWI903B")

    def test_each_payload_is_byte_idempotent(self):
        for resref in ("SPWI903", "SPWI903B", "ZSSBODY"):
            with self.subTest(resref=resref):
                first = self.transform(_fixture(), resref)
                second = self.transform(first, resref)
                self.assertEqual(first, second)

    def test_previous_refresh_is_moved_first_without_duplication(self):
        before = _mutate(_fixture(), lambda effects: effects + [_refresh("SPWI903B")])
        after = SplFile.from_bytes(self.transform(before))
        for ability in after.abilities:
            markers = [fx for fx in ability.effects if fx.opcode == 321 and fx.resource == "SPWI903B"]
            self.assertEqual(1, len(markers))
            self.assertEqual(_refresh("SPWI903B").to_bytes(), ability.effects[0].to_bytes())

    def test_amount_and_duration_are_not_old_value_fingerprints(self):
        before = _mutate(_fixture(), lambda effects: [
            dataclasses.replace(fx, parameter1=77, duration=19) if _owned(fx) else fx for fx in effects])
        after = self.transform(before)
        self.assert_preserved(before, after, "SPWI903B")

    def test_edited_failure_metadata_is_overwritten(self):
        before = _mutate(_fixture(), lambda effects: [
            dataclasses.replace(fx, save_type=0x01000000, save_bonus=3, special=0x11223344,
                                resource="OPAQUE", dice_number=2, dice_size=7)
            if _owned(fx) else fx for fx in effects])
        after = self.transform(before)
        self.assert_preserved(before, after, "SPWI903B")

    def test_missing_duplicate_and_edited_packages_are_rebuilt(self):
        variants = (
            lambda effects: [fx for fx in effects if fx.opcode not in (60, 221)],
            lambda effects: effects + effects,
            lambda effects: [dataclasses.replace(fx, parameter1=432, target=1, timing=4,
                                                 resist_dispel=3, probability1=12, save_type=31)
                             if _owned(fx) or fx.opcode == 221 and fx.parameter2 == 1 else fx
                             for fx in effects],
            lambda effects: effects + [dataclasses.replace(_refresh("SPWI903B"), parameter2=0)],
            lambda effects: [],
        )
        for index, mutation in enumerate(variants):
            with self.subTest(index=index):
                before = _mutate(_fixture(), mutation)
                after = self.transform(before)
                self.assert_preserved(before, after, "SPWI903B")
                self.assertEqual(after, self.transform(after))

    def test_empty_spell_receives_an_ability(self):
        before = dataclasses.replace(SplFile.from_bytes(_fixture()), abilities=()).to_bytes()
        after = SplFile.from_bytes(self.transform(before))
        self.assertEqual(1, len(after.abilities))
        self.assertEqual([321, 221, 60, 60], [fx.opcode for fx in after.abilities[0].effects])

    def test_shared_slices_and_unreferenced_effects_do_not_block_installation(self):
        raw = bytearray(_fixture())
        first = struct.unpack_from("<H", raw, 0x72 + 0x20)[0]
        struct.pack_into("<H", raw, 0x9A + 0x20, first)
        raw.extend(bytes(0x30))
        before = bytes(raw)
        self.assert_preserved(before, self.transform(before), "SPWI903B")

    def test_unreadable_tables_are_left_unchanged_without_warnings(self):
        for case in ("header", "abilities", "effects", "truncated"):
            with self.subTest(case=case):
                raw = bytearray(_fixture())
                if case == "header":
                    del raw[40:]
                elif case == "abilities":
                    struct.pack_into("<I", raw, 0x64, len(raw))
                elif case == "effects":
                    struct.pack_into("<H", raw, 0x72 + 0x20, 65535)
                else:
                    del raw[-1:]
                self.assertEqual(bytes(raw), self.transform(bytes(raw)))


if __name__ == "__main__":
    unittest.main()
